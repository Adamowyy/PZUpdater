#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PZ Updater - updater for Project Zomboid mods that need a manual install."""

import os
import re
import json
import queue
import shutil
import filecmp
import sys
import time
import threading
import datetime
import webbrowser
import urllib.request
import urllib.parse

# PyInstaller --windowed leaves sys.stdout/stderr as None, and a stray print()
# would crash the exe before any window shows up.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import customtkinter as ctk

import i18n
from i18n import Translator

APP_NAME = "PZ Updater"
PROJECT_URL = "https://github.com/Adamowyy/PZUpdater"
APP_ID = "108600"  # Project Zomboid (Steam app id)
STEAM_API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"
PROFILE_URL = "https://steamcommunity.com/id/AdamowY/"


# Only mods that need a manual install belong here, not a plain subscription.
# "type" says how the files land in the game folder, "help" needs a text per
# language, "notice" a one-time message, and "obsolete_if_newer_than" /
# "visible_if_newer_than" let a row switch itself off by version.
UPDATABLE_MODS = [
    {
        "key": "zombiebuddy",
        "name": "ZombieBuddy",
        "workshop_id": "3619862853",
        "type": "files_copy",
        "src_dir": os.path.join("mods", "ZombieBuddy", "libs"),
        "files": ["ZombieBuddy.jar", "zbNative.dll"],
        "help": {
            "en": "Copies ZombieBuddy.jar and zbNative.dll into the game folder "
                  "(the Java mod loader).",
            "pl": "Kopiuje ZombieBuddy.jar i zbNative.dll do folderu gry "
                  "(ładowarka modów Java).",
        },
    },
    {
        "key": "zombiebuddy_fix",
        "name": "Temporary Fix for ZombieBuddy",
        "workshop_id": "3807686870",
        "type": "jar_replace",
        "jar_name": "ZombieBuddy.jar",
        "search_under": "mods",
        "target_rel": "ZombieBuddy.jar",
        # Once ZombieBuddy ships a newer jar of its own, this fix is pointless.
        "obsolete_if_newer_than": "3619862853",
        "help": {
            "en": "Replaces ZombieBuddy.jar in the game folder with a build that "
                  "works on 42.21. Skipped once ZombieBuddy gets a newer release.",
            "pl": "Podmienia ZombieBuddy.jar w folderze gry na wersję zgodną z 42.21. "
                  "Przestaje się nakładać, gdy ZombieBuddy dostanie nowszą wersję.",
        },
    },
    {
        "key": "better_car_physics",
        "name": "Better Car Physics",
        "workshop_id": "2909035179",
        "type": "folder_copy",
        "manual_dir": os.path.join("mods", "BetterCarPhysics", "manual_installation"),
        "copy_name": "zombie",
        "target_rel": "zombie",
        "help": {
            "en": "Copies the 'zombie' folder from the newest version "
                  "(for example 42.21.0) into the game folder.",
            "pl": "Kopiuje folder 'zombie' z najnowszej wersji (np. 42.21.0) do "
                  "folderu gry.",
        },
    },
]

# Mods on the "watched" list out of the box. Notifications only: the app never
# touches their files, it just says when the author published something new.
DEFAULT_MANUAL_MODS = [
    {"workshop_id": "3807349984", "name": "Immersive Visuals [Reshade Preset]"},
]


class UpdaterError(Exception):
    """Error carrying a translation key instead of a ready-made sentence."""

    def __init__(self, key, *args):
        self.key = key
        self.text_args = args
        super().__init__(key)

    def text(self, t):
        return t(self.key, *self.text_args)


def resource_path(*parts):
    """Path to a file shipped with the app (source checkout or onefile exe)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


# Locating Steam, its libraries, the game and the workshop folders

def _read_reg(root_key, path, value):
    try:
        import winreg
        with winreg.OpenKey(root_key, path) as k:
            val, _ = winreg.QueryValueEx(k, value)
            return val
    except Exception:
        return None


def find_steam_root():
    import winreg
    for key, path, value in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ):
        v = _read_reg(key, path, value)
        if v and os.path.isdir(v):
            return os.path.normpath(v)
    for p in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam",
              r"D:\Steam", r"D:\Gry\Steam", r"E:\Steam", r"E:\Gry\Steam"):
        if os.path.isdir(p):
            return os.path.normpath(p)
    return None


def parse_libraryfolders(steam_root):
    """Extra library paths from steamapps/libraryfolders.vdf (games on other drives)."""
    libs = []
    vdf = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return libs
    for m in re.finditer(r'"path"\s+"((?:[^"\\]|\\.)*)"', text):
        p = m.group(1).replace("\\\\", "\\")
        if p and os.path.isdir(p) and p not in libs:
            libs.append(os.path.normpath(p))
    return libs


def find_libraries(steam_root):
    libs = []
    seen = set()

    def _add(path):
        key = os.path.normcase(os.path.normpath(path))
        if key not in seen:
            seen.add(key)
            libs.append(os.path.normpath(path))

    if steam_root:
        _add(steam_root)
        for p in parse_libraryfolders(steam_root):
            _add(p)
    return libs


def _looks_like_pz(folder):
    for exe in ("ProjectZomboid64.exe", "ProjectZomboid32.exe", "ProjectZomboid.exe"):
        if os.path.isfile(os.path.join(folder, exe)):
            return True
    return False


def find_game_dir(libraries):
    for lib in libraries:
        p = os.path.join(lib, "steamapps", "common", "ProjectZomboid")
        if os.path.isdir(p) and _looks_like_pz(p):
            return os.path.normpath(p)
    return None


def workshop_has_content(ws_dir):
    """True when the workshop folder holds files (unsubscribing leaves an empty one)."""
    if not os.path.isdir(ws_dir):
        return False
    for _dirpath, _dirs, files in os.walk(ws_dir):
        if files:
            return True
    return False


def find_workshop_dir(libraries, workshop_id):
    for lib in libraries:
        p = os.path.join(lib, "steamapps", "workshop", "content", APP_ID, workshop_id)
        if workshop_has_content(p):
            return os.path.normpath(p)
    return None


# Steam API - last update timestamp

def steam_get_details(workshop_id):
    body = urllib.parse.urlencode(
        {"itemcount": "1", "publishedfileids[0]": workshop_id}
    ).encode()
    req = urllib.request.Request(
        STEAM_API,
        data=body,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    d = data["response"]["publishedfiledetails"][0]
    if d.get("result") != 1:
        raise UpdaterError("error.steam_no_data", workshop_id)
    return {
        "title": d.get("title", ""),
        "time_updated": int(d.get("time_updated", 0)),
        "time_created": int(d.get("time_created", 0)),
    }


def fmt_ts(ts):
    if not ts:
        return "—"
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


# Version folders

def version_key(name):
    return [int(x) for x in re.findall(r"\d+", name)]


def newest_version_folder(directory):
    """Newest folder inside a "manual_installation" style directory."""
    best = None
    best_key = None
    try:
        entries = os.listdir(directory)
    except OSError:
        return None
    for e in entries:
        full = os.path.join(directory, e)
        if not os.path.isdir(full):
            continue
        key = version_key(e)
        if not key:
            continue
        if best_key is None or key > best_key:
            best, best_key = full, key
    return best


# State: applied timestamps, watched mods, language

def state_path():
    appdata = os.environ.get("APPDATA")
    base = os.path.join(appdata, "PZUpdater") if appdata else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "state.json")


def load_state():
    p = state_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    state.setdefault("mods", {})
    if "manual_mods" not in state:
        state["manual_mods"] = list(DEFAULT_MANUAL_MODS)
    if state.get("language") not in i18n.LANGUAGES:
        state["language"] = i18n.DEFAULT_LANGUAGE
    return state


def save_state(state):
    p = state_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"          # written next to the target so os.replace stays atomic
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


# Update actions

def find_jar(workshop_dir, jar_name, search_under):
    root = os.path.join(workshop_dir, search_under) if search_under else workshop_dir
    if not os.path.isdir(root):
        return None
    for dirpath, _dirs, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower() == jar_name.lower():
                return os.path.join(dirpath, fn)
    return None


def update_jar_replace(mod, game, ws, t):
    jar = find_jar(ws, mod["jar_name"], mod.get("search_under"))
    if not jar:
        return False, t("action.jar_missing", mod["jar_name"]), {}
    version = os.path.basename(os.path.dirname(jar))
    shutil.copy2(jar, os.path.join(game, mod["target_rel"]))
    return True, t("action.jar_replaced"), {"version": version}


def update_folder_copy(mod, game, ws, t):
    manual = os.path.join(ws, mod["manual_dir"])
    version_dir = newest_version_folder(manual)
    if not version_dir:
        return False, t("action.no_version_folders"), {}
    src = os.path.join(version_dir, mod["copy_name"])
    if not os.path.isdir(src):
        return False, t("action.no_copy_folder", mod["copy_name"],
                        os.path.basename(version_dir)), {}
    dst = os.path.join(game, mod["target_rel"])
    os.makedirs(dst, exist_ok=True)
    copied = 0
    for dirpath, _dirs, filenames in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        out_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(out_dir, exist_ok=True)
        for fn in filenames:
            shutil.copy2(os.path.join(dirpath, fn), os.path.join(out_dir, fn))
            copied += 1
    version = os.path.basename(version_dir)
    return True, t("action.folder_copied", mod["copy_name"], version, t.files(copied)), \
        {"version": version}


def update_files(mod, game, ws, t):
    src_dir = os.path.join(ws, mod["src_dir"])
    for fn in mod["files"]:
        if not os.path.isfile(os.path.join(src_dir, fn)):
            return False, t("action.source_file_missing", fn), {}
    for fn in mod["files"]:
        shutil.copy2(os.path.join(src_dir, fn), os.path.join(game, fn))
    return True, t("action.files_copied", t.files(len(mod["files"]))), {}


ACTION_HANDLERS = {
    "jar_replace": update_jar_replace,
    "folder_copy": update_folder_copy,
    "files_copy": update_files,
}


# Is the mod actually in the game folder?

INSTALL_OK = "ok"            # every mod file is in the game folder and matches
INSTALL_PARTIAL = "partial"  # only some of them match (usually an older version)
INSTALL_MISSING = "missing"  # none of the mod files are in the game folder
INSTALL_UNKNOWN = "unknown"  # nothing to compare against


def files_identical(a, b):
    """Byte-for-byte comparison; a missing file is never "identical"."""
    try:
        if not (os.path.isfile(a) and os.path.isfile(b)):
            return False
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def dir_files(root):
    """{relative path: full path} for every file inside a directory."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            full = os.path.join(dirpath, fn)
            out[os.path.relpath(full, root)] = full
    return out


def mod_targets(mod, ws):
    """What a mod writes into the game folder: [(relative path, kind, source)]."""
    if not ws or not os.path.isdir(ws):
        return []
    kind = mod["type"]
    if kind == "files_copy":
        return [(fn, "file", os.path.join(ws, mod["src_dir"], fn)) for fn in mod["files"]]
    if kind == "jar_replace":
        jar = find_jar(ws, mod["jar_name"], mod.get("search_under"))
        return [(mod["target_rel"], "file", jar)] if jar else []
    if kind == "folder_copy":
        version_dir = newest_version_folder(os.path.join(ws, mod["manual_dir"]))
        src = os.path.join(version_dir, mod["copy_name"]) if version_dir else None
        return [(mod["target_rel"], "dir", src)] if src and os.path.isdir(src) else []
    return []


def accepted_sources(mods, workshop_map):
    """{target path: [(position of the mod, source), ...]}."""
    out = {}
    for idx, m in enumerate(mods):
        for rel, _kind, src in mod_targets(m, workshop_map.get(m["key"])):
            out.setdefault(rel, []).append((idx, src))
    return out


def mod_install_state(mod, game, workshop_map, mods=None, sources=None):
    """Files of a mod inside the game folder -> (state, matching, total)."""
    if not game:
        return INSTALL_UNKNOWN, 0, 0
    targets = mod_targets(mod, workshop_map.get(mod["key"]))
    if not targets:
        return INSTALL_UNKNOWN, 0, 0
    mods = list(mods) if mods is not None else [mod]
    own_index = next((i for i, m in enumerate(mods) if m is mod), 0)
    if sources is None:
        sources = accepted_sources(mods, workshop_map)
    total = ok = 0
    for rel, kind, src in targets:
        dst = os.path.join(game, rel)
        if kind == "dir":
            src_files = dir_files(src)
            total += len(src_files)
            for sub, full in src_files.items():
                if files_identical(full, os.path.join(dst, sub)):
                    ok += 1
        else:
            total += 1
            candidates = [s for idx, s in sources.get(rel, []) if idx >= own_index] or [src]
            if any(files_identical(c, dst) for c in candidates):
                ok += 1
    if total == 0:
        return INSTALL_UNKNOWN, 0, 0
    if ok == 0:
        return INSTALL_MISSING, 0, total
    if ok < total:
        return INSTALL_PARTIAL, ok, total
    return INSTALL_OK, ok, total


# Theme

BG = "#141518"
CARD = "#1e2126"
CARD_SEL = "#242a33"
BORDER = "#2b3038"
TEXT = "#e6e8ec"
MUTED = "#9aa0aa"
SUBTLE = "#6b7280"

ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
ON_ACCENT = "#ffffff"

DISABLED_BG = "#3a3d42"
DISABLED_TEXT = "#6b7280"

# Full-window curtain shown while the app is talking to Steam. A check can be
# over in ~0.3 s on a fast connection, so it stays up for a moment to be seen.
OVERLAY_BG = "#0b0c0e"
OVERLAY_MIN_SECONDS = 0.9

# PZUPDATER_SLOW_SECONDS=8 makes every Steam request take 8 s - handy when
# working on the overlay without a slow connection.
try:
    DEBUG_SLOW_SECONDS = max(0.0, float(os.environ.get("PZUPDATER_SLOW_SECONDS", "0") or 0))
except ValueError:
    DEBUG_SLOW_SECONDS = 0.0

# badge tag -> (text colour, background colour)
BADGE = {
    "ok":   ("#ffffff", "#16a34a"),   # green - up to date
    "new":  ("#ffffff", "#d97706"),   # amber - newer version on Steam
    "info": ("#ffffff", "#dc2626"),   # red   - files need replacing
    "gray": ("#ffffff", "#4b5563"),   # grey  - not installed / not subscribed
    "old":  ("#ffffff", "#92400e"),   # brown - superseded by another mod
    "err":  ("#ffffff", "#dc2626"),   # red   - error
    "":     ("#9aa0aa", "#2a2d33"),
}


# Application window

class PZUpdaterApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()     # stay hidden until the first check is done
        self._revealed = False

        self.state = load_state()
        self.manual_mods = self.state["manual_mods"]     # [{workshop_id, name}, ...]
        self.t = Translator(self.state["language"])
        self.steam_info = {}     # workshop_id -> details from the Steam API

        self._busy = False
        self._queue = queue.Queue()
        self._selected = None
        self._cards = {}
        self._manual_cards = {}
        self._status_text = ""
        self._status_key = None
        self._summary = None
        self._log_entries = []
        self._toast = None
        self._console = None
        self._overlay_visible = False
        self._overlay_shown_at = 0.0

        self.paths = self._detect()
        self._sources = {}       # {target path: acceptable sources}, refreshed per check
        self._refresh_sources()

        self._log("INFO", self.t("msg.start", self.paths["steam_root"]))
        self._log("INFO", self.t("msg.game_dir", self.paths["game_dir"]))

        self._build_ui()
        self._populate()
        self._select(UPDATABLE_MODS[0]["key"])
        self._install_excepthook()
        self.root.after(100, self._poll_queue)
        self.check_updates(silent=True)
        self.root.after(1500, self._reveal)   # fallback when the check drags on
        self.root.after(250, self._reveal)    # ...but usually reveal the curtain at once

    # -- detection ------------------------------------------------------------
    def _detect(self):
        steam_root = find_steam_root()
        libs = find_libraries(steam_root)
        game = find_game_dir(libs)
        workshop = {m["key"]: find_workshop_dir(libs, m["workshop_id"]) for m in UPDATABLE_MODS}
        return {"steam_root": steam_root, "libraries": libs,
                "game_dir": game, "workshop": workshop}

    def _refresh_workshop_dirs(self):
        libs = self.paths["libraries"]
        self.paths["workshop"] = {
            m["key"]: find_workshop_dir(libs, m["workshop_id"]) for m in UPDATABLE_MODS
        }
        self._refresh_sources()

    def _refresh_sources(self):
        self._sources = accepted_sources(UPDATABLE_MODS, self.paths["workshop"])

    def _saved_ts(self, workshop_id):
        return self.state.get("mods", {}).get(workshop_id, {}).get("steam_time_updated", 0)

    def _manual_subscribed(self, workshop_id):
        return bool(find_workshop_dir(self.paths["libraries"], workshop_id))

    # -- language -------------------------------------------------------------
    def set_language(self, language):
        if language not in i18n.LANGUAGES or language == self.t.language:
            return
        self.t.set_language(language)
        self.state["language"] = language
        save_state(self.state)
        # A click that does not reach the window (focus, covered window) leaves no
        # trace here, which makes the log useful when a switch "does nothing".
        self._log("INFO", f"language: {language}")
        self._rebuild_ui()

    def _flag_image(self, language):
        """Flag icon for a language button, or None when it cannot be loaded."""
        name = i18n.FLAGS.get(language)
        path = resource_path("assets", name) if name else None
        if not path or not os.path.isfile(path):
            return None
        try:
            from PIL import Image
            image = Image.open(path)
            return ctk.CTkImage(light_image=image, dark_image=image,
                                size=(image.width, image.height))
        except Exception:      # a missing flag must not stop the app
            return None

    def _bind_flag_click(self, button, code):
        """Switch the language on a real click, regardless of customtkinter state."""
        state = {"pressed": False}

        def on_press(_event):
            state["pressed"] = True

        def on_release(event):
            was_pressed, state["pressed"] = state["pressed"], False
            if not was_pressed:
                return
            # released outside the button means the click was cancelled
            inside = (0 <= event.x_root - button.winfo_rootx() < button.winfo_width()
                      and 0 <= event.y_root - button.winfo_rooty() < button.winfo_height())
            if inside:
                self.set_language(code)

        button.bind("<Button-1>", on_press, add=True)
        button.bind("<ButtonRelease-1>", on_release, add=True)

    def _rebuild_ui(self):
        """Recreate the widgets after a language change (texts live in widgets)."""
        for widget in self.root.winfo_children():
            widget.destroy()
        self._cards = {}
        self._manual_cards = {}
        self._toast = None
        self._console = None
        self._overlay_visible = False
        self._build_ui()
        self._populate()
        self._select(self._selected or UPDATABLE_MODS[0]["key"])
        self.refresh_statuses()
        self._restore_status_text()

    # -- UI -------------------------------------------------------------------
    def _build_ui(self):
        self.root.title(f"{APP_NAME} — Project Zomboid")
        self.root.geometry("1080x640")
        self.root.minsize(960, 540)
        self.root.configure(fg_color=BG)

        icon = resource_path("icon.ico")
        if os.path.exists(icon):
            try:
                self.root.iconbitmap(icon)
            except Exception:
                pass

        self.f_title = ctk.CTkFont(size=20, weight="bold")
        self.f_sub = ctk.CTkFont(size=12)
        self.f_mod = ctk.CTkFont(size=14, weight="bold")
        self.f_man = ctk.CTkFont(size=12, weight="bold")
        self.f_small = ctk.CTkFont(size=12)
        self.f_muted = ctk.CTkFont(size=11)
        self.f_badge = ctk.CTkFont(size=12, weight="bold")
        self.f_button = ctk.CTkFont(size=13, weight="bold")

        # header: title on the left, language flags in the corner, signature beside them
        head = ctk.CTkFrame(self.root, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 10))

        top = ctk.CTkFrame(head, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=self.t("app.title"), font=self.f_title,
                     text_color=TEXT).pack(side="left")

        lang_box = ctk.CTkFrame(top, fg_color="transparent")
        lang_box.pack(side="right")
        self._lang_buttons = {}
        for code in i18n.LANGUAGES:
            image = self._flag_image(code)
            active = (code == self.t.language)
            btn = ctk.CTkButton(
                lang_box,
                text="" if image else code.upper(),
                image=image,
                width=44 if image else 36, height=26, corner_radius=7,
                fg_color=CARD_SEL if active else "transparent",
                hover_color=CARD_SEL,
                border_width=1, border_color=ACCENT if active else BORDER,
                text_color=TEXT if active else MUTED, font=self.f_muted,
                command=lambda c=code: self.set_language(c))
            btn.pack(side="left", padx=(4, 0))
            self._bind_flag_click(btn, code)
            self._lang_buttons[code] = btn

        sig = ctk.CTkLabel(top, text=self.t("app.signature"), font=self.f_muted,
                           text_color=ACCENT, cursor="hand2")
        sig.pack(side="right", padx=(0, 12))
        sig.bind("<Button-1>", lambda e: self._open_url(PROFILE_URL))
        sig.bind("<Enter>", lambda e: sig.configure(text_color=ACCENT_HOVER))
        sig.bind("<Leave>", lambda e: sig.configure(text_color=ACCENT))

        ctk.CTkLabel(head, text=self.t("app.tagline"), font=self.f_sub,
                     text_color=MUTED).pack(anchor="w", pady=(2, 0))

        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20)

        # ---- left column: mods the app can update ----
        left = ctk.CTkFrame(main, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)

        left_box = ctk.CTkFrame(left, fg_color=CARD, corner_radius=14)
        left_box.pack(fill="both", expand=True)

        l_head = ctk.CTkFrame(left_box, fg_color="transparent")
        l_head.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(l_head, text=self.t("panel.mods.title"), font=self.f_mod,
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(l_head, text=self.t("panel.mods.subtitle"), font=self.f_muted,
                     text_color=MUTED).pack(anchor="w", pady=(1, 0))

        self.scroll = ctk.CTkScrollableFrame(left_box, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # help for the selected mod
        self.info_frame = ctk.CTkFrame(left, fg_color=CARD, corner_radius=12)
        self.info_frame.pack(fill="x", pady=(8, 0))

        info_top = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        info_top.pack(fill="x", padx=14, pady=(10, 2))
        self.info_name = ctk.CTkLabel(info_top, text="", font=self.f_mod, text_color=TEXT,
                                      anchor="w")
        self.info_name.pack(side="left")
        self.btn_steam = ctk.CTkButton(
            info_top, text=self.t("btn.open_steam"), width=130, height=28,
            fg_color="transparent", hover_color=CARD_SEL, text_color=ACCENT,
            border_width=1, border_color=ACCENT, corner_radius=8,
            font=self.f_muted, command=self._open_selected_on_steam)
        self.btn_steam.pack(side="right")

        self.info_help = ctk.CTkLabel(self.info_frame, text="", font=self.f_muted,
                                      text_color=MUTED, justify="left", anchor="w",
                                      wraplength=620)
        self.info_help.pack(fill="x", padx=14, pady=(0, 12))

        # main actions
        bar = ctk.CTkFrame(left, fg_color="transparent")
        bar.pack(fill="x", pady=(8, 0))
        self.btn_check = ctk.CTkButton(
            bar, text=self.t("btn.check"), height=40, width=170,
            fg_color=CARD_SEL, hover_color=BORDER, text_color=TEXT,
            corner_radius=10, font=self.f_button,
            command=self.check_updates)
        self.btn_check.pack(side="left")
        self.btn_update = ctk.CTkButton(
            bar, text=self.t("btn.update"), height=40, width=170,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
            corner_radius=10, font=self.f_button,
            command=self.do_update)
        self.btn_update.pack(side="left", padx=(10, 0))

        # ---- right column: watched mods (notifications only) ----
        right = ctk.CTkFrame(main, fg_color=CARD, corner_radius=14, width=330)
        right.pack(side="right", fill="both", padx=(16, 0))
        right.pack_propagate(False)

        r_head = ctk.CTkFrame(right, fg_color="transparent")
        r_head.pack(fill="x", padx=14, pady=(12, 6))

        r_title = ctk.CTkFrame(r_head, fg_color="transparent")
        r_title.pack(fill="x")
        ctk.CTkLabel(r_title, text=self.t("panel.manual.title"), font=self.f_man,
                     text_color=TEXT).pack(side="left")
        self.btn_add = ctk.CTkButton(
            r_title, text=self.t("panel.manual.add"), width=80, height=28,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
            corner_radius=8, font=self.f_muted, command=self._add_manual_mod)
        self.btn_add.pack(side="right")

        ctk.CTkLabel(r_head, text=self.t("panel.manual.subtitle"),
                     font=self.f_muted, text_color=MUTED, anchor="w", justify="left",
                     wraplength=280).pack(anchor="w", pady=(2, 0))

        self.manual_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.manual_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # status line, full width at the bottom
        self.status = ctk.CTkLabel(self.root, text="", font=self.f_muted,
                                   text_color=MUTED, anchor="w", justify="left",
                                   wraplength=1040)
        self.status.pack(fill="x", padx=20, pady=(10, 14))

        self.overlay = ctk.CTkFrame(main, fg_color=OVERLAY_BG, corner_radius=0)
        inner = ctk.CTkFrame(self.overlay, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")
        self.overlay_bar = ctk.CTkProgressBar(inner, width=280, height=6, corner_radius=3,
                                              mode="indeterminate", progress_color=ACCENT,
                                              fg_color=BORDER)
        self.overlay_bar.pack()
        self.overlay_bar.set(0)
        ctk.CTkLabel(inner, text=self.t("overlay.title"), font=self.f_mod,
                     text_color=TEXT).pack(pady=(18, 4))
        self.overlay_sub = ctk.CTkLabel(inner, text="", font=self.f_muted,
                                        text_color=MUTED)
        self.overlay_sub.pack()

    def _populate(self):
        for m in UPDATABLE_MODS:
            card = ctk.CTkFrame(self.scroll, fg_color=CARD, corner_radius=12,
                                border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=3)

            name = ctk.CTkLabel(card, text=m["name"], font=self.f_mod,
                                text_color=TEXT, anchor="w")
            name.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))

            badge = ctk.CTkLabel(card, text=self.t("status.pending"), font=self.f_badge,
                                 text_color="#9aa0aa", fg_color="#2a2d33",
                                 corner_radius=8, height=22)
            badge.grid(row=0, column=1, sticky="e", padx=12, pady=(8, 0))

            sub = ctk.CTkLabel(card, text="", font=self.f_muted, text_color=MUTED,
                               anchor="w")
            sub.grid(row=1, column=0, sticky="w", padx=12, pady=(2, 8))

            foot = ctk.CTkFrame(card, fg_color="transparent")
            foot.grid(row=1, column=1, sticky="e", padx=12, pady=(2, 8))
            wid = m["workshop_id"]
            ctk.CTkButton(foot, text=self.t("btn.steam"), width=68, height=22,
                          fg_color="transparent", hover_color=CARD_SEL, text_color=ACCENT,
                          corner_radius=6, font=self.f_muted,
                          command=lambda w=wid: self._open_url(WORKSHOP_URL.format(w))
                          ).pack(side="left")
            ctk.CTkButton(foot, text=self.t("btn.copy_id"), width=74, height=22,
                          fg_color="transparent", hover_color=CARD_SEL, text_color=MUTED,
                          corner_radius=6, font=self.f_muted,
                          command=lambda w=wid: self._copy_id(w)
                          ).pack(side="left", padx=(8, 0))

            act = ctk.CTkButton(card, text=self.t("btn.install"), height=30,
                                fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                text_color=ON_ACCENT, corner_radius=8, font=self.f_small,
                                command=lambda k=m["key"]: self._update_one(k))
            act.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
            act.grid_remove()

            card.grid_columnconfigure(0, weight=1)

            self._cards[m["key"]] = {"frame": card, "name": name, "badge": badge,
                                     "sub": sub, "action": act}
            for w in (card, name, badge, sub):
                self._bind_click(w, m["key"])

        self._build_manual_cards()

    def _build_manual_cards(self):
        for w in self.manual_scroll.winfo_children():
            w.destroy()
        self._manual_cards = {}
        for m in self.manual_mods:
            self._add_manual_card(m)

    def _add_manual_card(self, m):
        wid = m["workshop_id"]
        card = ctk.CTkFrame(self.manual_scroll, fg_color=CARD_SEL, corner_radius=10)
        card.pack(fill="x", pady=4)

        name = ctk.CTkLabel(card, text=m["name"], font=self.f_man, text_color=TEXT,
                            anchor="w", justify="left", wraplength=180)
        name.grid(row=0, column=0, sticky="w", padx=(12, 6), pady=(10, 0))

        remove = ctk.CTkButton(card, text="✕", width=24, height=24,
                               fg_color="transparent", hover_color="#3a1a1a",
                               text_color=SUBTLE, corner_radius=6, font=self.f_muted,
                               command=lambda w=wid: self._remove_manual_mod(w))
        remove.grid(row=0, column=1, sticky="e", padx=(0, 10), pady=(10, 0))

        sub = ctk.CTkLabel(card, text="", font=self.f_muted, text_color=MUTED,
                           anchor="w", justify="left")
        sub.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(2, 0))

        badges = ctk.CTkFrame(card, fg_color="transparent")
        badges.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 8))

        badge = ctk.CTkLabel(badges, text=self.t("status.pending"), font=self.f_muted,
                             text_color="#9aa0aa", fg_color="#2a2d33",
                             corner_radius=8, height=22)
        badge.pack(side="left")

        sub_badge = ctk.CTkLabel(badges, text=self.t("status.pending"), font=self.f_muted,
                                 text_color="#9aa0aa", fg_color="#2a2d33",
                                 corner_radius=8, height=22)
        sub_badge.pack(side="left", padx=(6, 0))

        foot = ctk.CTkFrame(card, fg_color="transparent")
        foot.grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 0))
        ctk.CTkButton(foot, text=self.t("btn.steam"), width=70, height=24,
                      fg_color="transparent", hover_color=BORDER, text_color=ACCENT,
                      corner_radius=6, font=self.f_muted,
                      command=lambda w=wid: self._open_url(WORKSHOP_URL.format(w))
                      ).pack(side="left")
        ctk.CTkButton(foot, text=self.t("btn.copy_id"), width=76, height=24,
                      fg_color="transparent", hover_color=BORDER, text_color=MUTED,
                      corner_radius=6, font=self.f_muted,
                      command=lambda w=wid: self._copy_id(w)).pack(side="left", padx=(8, 0))

        done = ctk.CTkButton(card, text=self.t("btn.manual_done"), height=32,
                             fg_color="#16a34a", hover_color="#15803d",
                             text_color="#ffffff", corner_radius=8, font=self.f_mod,
                             command=lambda w=wid: self._mark_manual_done(w))
        done.grid(row=4, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 12))

        card.grid_columnconfigure(0, weight=1)
        self._manual_cards[wid] = {"name": name, "sub": sub, "badge": badge,
                                   "sub_badge": sub_badge, "done": done}

    def _bind_click(self, widget, key):
        widget.bind("<Button-1>", lambda e: self._select(key))

    # -- mod state ------------------------------------------------------------
    def _install_state(self, mod):
        return mod_install_state(mod, self.paths["game_dir"], self.paths["workshop"],
                                 UPDATABLE_MODS, self._sources)

    def _files_note(self, info):
        state, ok, total = info["install"], info["ok"], info["total"]
        if state == INSTALL_OK:
            return self.t("detail.files_ok", self.t.files(total))
        if state == INSTALL_MISSING:
            return self.t("detail.files_missing")
        if state == INSTALL_PARTIAL:
            return self.t("detail.files_partial", ok, total)
        return self.t("detail.files_unknown")

    def _status_info(self, mod):
        """Badge text, file state and the action available for one mod."""
        ws = self.paths["workshop"].get(mod["key"])
        install, ok, total = self._install_state(mod)
        info = {"install": install, "ok": ok, "total": total, "pending": None,
                "muted": False, "status": "", "tag": ""}
        if not ws:
            info.update(status=self.t("status.not_subscribed"), tag="gray", muted=True)
            return info
        if self._is_obsolete(mod):
            info.update(status=self.t("status.deprecated"), tag="old")
            return info

        details = self.steam_info.get(mod["workshop_id"])
        saved = self._saved_ts(mod["workshop_id"])
        cur = details["time_updated"] if details else 0

        if install == INSTALL_MISSING:
            # Subscribed, but the files are not in the game folder: the card is
            # greyed out like an unsubscribed one and installing stays a click away.
            info.update(status=self.t("status.subscribed_not_installed"), tag="gray",
                        pending="install", muted=True)
        elif install == INSTALL_PARTIAL:
            info.update(status=self.t("status.needs_update"), tag="info", pending="install")
        elif install != INSTALL_OK or not cur:
            info.update(status=self.t("status.pending"), tag="")
        elif not saved:
            info.update(status=self.t("status.needs_update"), tag="info", pending="update")
        elif cur > saved:
            info.update(status=self.t("status.new_update"), tag="new", pending="update")
        else:
            info.update(status=self.t("status.up_to_date"), tag="ok")
        return info

    def _pending_actions(self):
        """{mod key: "install"|"update"} - what can be done with each mod."""
        pending = {}
        for m in UPDATABLE_MODS:
            action = self._status_info(m)["pending"]
            if action:
                pending[m["key"]] = action
        return pending

    def _installed_for_update(self):
        """Mods the main Update button may touch."""
        out = []
        for m in UPDATABLE_MODS:
            info = self._status_info(m)
            if info["pending"] and info["install"] in (INSTALL_OK, INSTALL_PARTIAL):
                out.append(m)
        return out

    def _refresh_buttons(self):
        if self._busy:
            self.btn_check.configure(state="disabled")
            self.btn_update.configure(state="disabled")
            self.btn_add.configure(state="disabled")
            for card in self._cards.values():
                card["action"].configure(state="disabled")
            return
        self.btn_check.configure(state="normal")
        self.btn_add.configure(state="normal")
        for card in self._cards.values():
            card["action"].configure(state="normal")
        if self._installed_for_update():
            self.btn_update.configure(state="normal", text=self.t("btn.update"),
                                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                      text_color=ON_ACCENT)
        else:
            self.btn_update.configure(state="disabled", text=self.t("btn.update"),
                                      fg_color=DISABLED_BG, text_color=DISABLED_TEXT)

    def _open_url(self, url):
        try:
            os.startfile(url)      # Windows: opens the default browser via ShellExecute
        except Exception:
            webbrowser.open(url)

    def _copy_id(self, wid):
        self.root.clipboard_clear()
        self.root.clipboard_append(str(wid))
        self.set_status_key("msg.id_copied", wid)

    def _open_selected_on_steam(self):
        mod = next((m for m in UPDATABLE_MODS if m["key"] == self._selected), None)
        if mod:
            self._open_url(WORKSHOP_URL.format(mod["workshop_id"]))

    def _select(self, key):
        self._selected = key
        mod = next(m for m in UPDATABLE_MODS if m["key"] == key)
        for k, c in self._cards.items():
            sel = (k == key)
            c["frame"].configure(border_color=ACCENT if sel else BORDER,
                                 border_width=2 if sel else 1,
                                 fg_color=CARD_SEL if sel else CARD)
        self.info_name.configure(text=mod["name"])
        self.info_help.configure(text=self.t.help_text(mod.get("help")))

    def set_status(self, text):
        """Plain text status (error details, operation results)."""
        self._status_text = text
        self._status_key = None
        self._summary = None
        self.status.configure(text=text)

    def set_status_key(self, key, *args):
        """Status built from a translation key, so it follows the language."""
        self._status_text = self.t(key, *args)
        self._status_key = (key, args)
        self._summary = None
        self.status.configure(text=self._status_text)

    def set_status_summary(self, installs, updates):
        """Status listing what the last check found (re-rendered on language change)."""
        self._summary = (installs, updates)
        self._status_key = None
        self._status_text = self._render_summary(installs, updates)
        self.status.configure(text=self._status_text)

    def _render_summary(self, installs, updates):
        parts = []
        if installs:
            parts.append(self.t("msg.to_install", ", ".join(installs)))
        if updates:
            parts.append(self.t("msg.new_update", ", ".join(updates)))
        return "   |   ".join(parts) if parts else self.t("msg.all_up_to_date")

    def _restore_status_text(self):
        """Re-render the last status in the current language after a UI rebuild."""
        if self._status_key:
            self.set_status_key(*self._status_key)
        elif self._summary:
            self.set_status_summary(*self._summary)
        else:
            self.set_status(self._status_text)

    def _reveal(self):
        if self._revealed:
            return
        self._revealed = True
        self.root.update_idletasks()
        self.root.deiconify()
        self.root.lift()

    # -- overlay --------------------------------------------------------------
    def _show_overlay(self, sub=""):
        try:
            self.overlay_sub.configure(text=sub)
            self.overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.overlay.lift()
            if not self._overlay_visible:
                self._overlay_visible = True
                self._overlay_shown_at = time.perf_counter()
                self.overlay_bar.set(0)
                self.overlay_bar.start()
        except Exception:
            pass

    def _hide_overlay(self):
        if not self._overlay_visible:
            return
        self._overlay_visible = False
        try:
            self.overlay_bar.stop()
            self.overlay.place_forget()
        except Exception:
            pass

    def _hide_overlay_after_min_time(self):
        left = OVERLAY_MIN_SECONDS - (time.perf_counter() - self._overlay_shown_at)
        if left > 0.05:
            self.root.after(int(left * 1000) + 20, self._hide_overlay)
        else:
            self._hide_overlay()

    def _overlay_progress(self, progress):
        """Called on the main thread through the queue; argument is (done, total)."""
        done, total = progress
        if self._overlay_visible:
            try:
                self.overlay_sub.configure(text=self.t("overlay.progress", done, total))
            except Exception:
                pass

    # -- statuses -------------------------------------------------------------
    def _is_obsolete(self, mod):
        """True when another mod makes this one pointless (the fix vs the loader)."""
        ref = mod.get("obsolete_if_newer_than")
        if not ref:
            return False
        own = self.steam_info.get(mod["workshop_id"], {}).get("time_updated", 0)
        newer = self.steam_info.get(ref, {}).get("time_updated", 0)
        return own > 0 and newer > 0 and newer > own

    def _manual_status(self, m):
        details = self.steam_info.get(m["workshop_id"])
        saved = self._saved_ts(m["workshop_id"])
        cur = details["time_updated"] if details else 0
        if not cur:
            return self.t("status.pending"), ""
        if not saved:
            return self.t("status.needs_update"), "info"
        if cur > saved:
            return self.t("status.new_update"), "new"
        return self.t("status.up_to_date"), "ok"

    def refresh_statuses(self):
        # left column: mods the app updates
        for m in UPDATABLE_MODS:
            key = m["key"]
            info = self._status_info(m)
            status, tag = info["status"], info["tag"]
            details = self.steam_info.get(m["workshop_id"])
            ws = self.paths["workshop"].get(key)

            bits = [self.t("detail.workshop", m["workshop_id"])]
            if details:
                bits.append(self.t("detail.steam", fmt_ts(details["time_updated"])))
            if m["type"] == "folder_copy" and ws:
                version_dir = newest_version_folder(os.path.join(ws, m["manual_dir"]))
                if version_dir and info["install"] != INSTALL_UNKNOWN:
                    bits.append(self.t("detail.version", os.path.basename(version_dir)))
            if self._is_obsolete(m):
                bits.append(self.t("detail.fix_obsolete"))
            bits.append(self._files_note(info) if ws else self.t("status.no_subscription"))

            card = self._cards[key]
            if info["muted"]:
                tc, bc = BADGE["gray"]
                card["name"].configure(text_color=SUBTLE)
            else:
                tc, bc = BADGE.get(tag, BADGE[""])
                card["name"].configure(text_color=TEXT)
            card["badge"].configure(text=status, text_color=tc, fg_color=bc)
            card["sub"].configure(text="  ·  ".join(bits))

            if info["pending"]:
                card["action"].configure(
                    text=self.t("btn.install") if info["install"] == INSTALL_MISSING
                    else self.t("btn.update"))
                card["action"].grid()
            else:
                card["action"].grid_remove()

        # right column: watched mods
        for m in self.manual_mods:
            wid = m["workshop_id"]
            status, tag = self._manual_status(m)
            details = self.steam_info.get(wid)
            card = self._manual_cards.get(wid)
            if not card:
                continue
            subscribed = self._manual_subscribed(wid)
            # A watched-but-unsubscribed mod is not tracked in the game folder,
            # so a green "up to date" badge would be misleading: show it grey.
            effective_tag = tag if (subscribed or tag != "ok") else "gray"
            tc, bc = BADGE.get(effective_tag, BADGE[""])
            card["badge"].configure(text=status, text_color=tc, fg_color=bc)
            if subscribed:
                card["sub_badge"].configure(text=self.t("status.subscribed"),
                                            text_color="#4ade80", fg_color="#14301f")
                card["name"].configure(text_color=TEXT)
            else:
                card["sub_badge"].configure(text=self.t("status.no_subscription"),
                                            text_color="#9aa0aa", fg_color="#2a2d33")
                card["name"].configure(text_color=SUBTLE)
            if subscribed and tag in ("info", "new"):
                card["done"].grid()
            else:
                card["done"].grid_remove()
            sub = self.t("detail.workshop", wid)
            if details:
                sub += "  ·  " + fmt_ts(details["time_updated"])
            card["sub"].configure(text=sub)
        self._refresh_buttons()

    # -- background work ------------------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                fn, arg = self._queue.get_nowait()
                fn(arg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _run_async(self, fn, on_done):
        """Run fn in a thread and hand the result back to the Tk main thread."""
        def worker():
            try:
                result = fn()
            except Exception as e:  # noqa: BLE001 - the UI has to survive anything
                result = ("error", e)
            self._queue.put((on_done, result))
        threading.Thread(target=worker, daemon=True).start()

    def _error_text(self, exc):
        return exc.text(self.t) if isinstance(exc, UpdaterError) else str(exc)

    def _all_workshop_ids(self):
        ids = [m["workshop_id"] for m in UPDATABLE_MODS]
        ids += [m["workshop_id"] for m in self.manual_mods]
        return ids

    def check_updates(self, silent=False):
        if self._busy:
            return
        self._busy = True
        self._refresh_buttons()
        if not silent:
            self.set_status_key("msg.checking")

        ids = self._all_workshop_ids()
        total = len(ids)
        self._show_overlay(self.t("overlay.progress", 0, total) if total else "")

        def work():
            out = {}
            for i, wid in enumerate(ids, 1):
                # progress goes through the queue: only the main thread touches widgets
                self._queue.put((self._overlay_progress, (i, total)))
                if DEBUG_SLOW_SECONDS:
                    time.sleep(DEBUG_SLOW_SECONDS)
                out[wid] = steam_get_details(wid)
            return out

        def on_done(result):
            self._busy = False
            self._refresh_buttons()
            self._refresh_workshop_dirs()
            if isinstance(result, tuple) and result[0] == "error":
                self._hide_overlay()
                message = self._error_text(result[1])
                self.set_status_key("msg.check_failed", message)
                self._error(self.t("msg.check_failed_details", message))
                self._reveal()
                return
            self.steam_info = result
            self.refresh_statuses()
            self._hide_overlay_after_min_time()
            self._reveal()
            actions = self._pending_actions()
            installs = [m["name"] for m in UPDATABLE_MODS if actions.get(m["key"]) == "install"]
            updates = [m["name"] for m in UPDATABLE_MODS if actions.get(m["key"]) == "update"]
            updates += [m["name"] for m in self.manual_mods
                        if self._manual_status(m)[1] == "new"]
            self.set_status_summary(installs, updates)

        self._run_async(work, on_done)

    def _update_one(self, key):
        """Per-card button: installs or updates that one mod only."""
        mod = next((m for m in UPDATABLE_MODS if m["key"] == key), None)
        if mod is not None:
            self.do_update([mod])

    def do_update(self, mods=None):
        """Updates the given mods; without an argument only the ones already in
        the game folder (the main button never installs a missing mod)."""
        if self._busy:
            return
        if not self.paths["game_dir"]:
            self.set_status_key("msg.no_game_dir")
            return

        actions = self._pending_actions()
        if mods is None:
            mods = self._installed_for_update()
        mods = [m for m in mods
                if self.paths["workshop"].get(m["key"]) and not self._is_obsolete(m)]
        if not mods:
            self.set_status_key("msg.nothing_to_update")
            return

        self._busy = True
        self._refresh_buttons()
        installing = any(actions.get(m["key"]) == "install" for m in mods)
        if len(mods) == 1:
            self.set_status_key("msg.installing_one" if installing else "msg.updating_one",
                                mods[0]["name"])
        else:
            self.set_status_key("msg.installing_many" if installing else "msg.updating_many",
                                len(mods))
        self._show_overlay(self.t("overlay.progress", 0, len(mods)))

        def work():
            results = []
            for i, m in enumerate(mods, 1):
                ws = self.paths["workshop"][m["key"]]
                self._queue.put((self._overlay_progress, (i, len(mods))))
                if DEBUG_SLOW_SECONDS:
                    time.sleep(DEBUG_SLOW_SECONDS)
                try:
                    handler = ACTION_HANDLERS.get(m["type"])
                    if handler is None:
                        ok, msg, meta = False, self.t("action.unknown_type"), {}
                    else:
                        ok, msg, meta = handler(m, self.paths["game_dir"], ws, self.t)
                    if ok:
                        details = steam_get_details(m["workshop_id"])
                        self.steam_info[m["workshop_id"]] = details
                        entry = {"steam_time_updated": details["time_updated"],
                                 "applied_at": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")}
                        if meta.get("version"):
                            entry["applied_version"] = meta["version"]
                        self.state.setdefault("mods", {})[m["workshop_id"]] = entry
                except Exception as e:  # noqa: BLE001 - one bad mod must not stop the rest
                    ok, msg = False, self._error_text(e)
                results.append((m["name"], ok, msg))
            save_state(self.state)
            return results

        def on_done(result):
            self._busy = False
            self._refresh_buttons()
            if isinstance(result, tuple) and result[0] == "error":
                self._hide_overlay()
                message = self._error_text(result[1])
                self.set_status_key("msg.update_failed", message)
                self._error(self.t("msg.update_failed", message))
                return
            self._refresh_workshop_dirs()
            ok_word, err_word = self.t("msg.result_ok"), self.t("msg.result_error")
            lines = [f"{ok_word if ok else err_word} — {name}: {msg}" for name, ok, msg in result]
            failed = [f"{name}: {msg}" for name, ok, msg in result if not ok]
            for entry in failed:
                self._log("ERROR", self.t("msg.update_failed_log", entry))
            self.refresh_statuses()
            self._hide_overlay_after_min_time()
            if failed:
                self._show_toast(self.t("msg.some_failed", len(failed)))
            self.set_status("   |   ".join(lines))

        self._run_async(work, on_done)

    # -- watched mods ---------------------------------------------------------
    def _ask_workshop_id(self):
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(self.t("dialog.add.title"))
        dlg.geometry("400x170")
        dlg.configure(fg_color=CARD)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        self.root.eval(f"tk::PlaceWindow {dlg._w} center")

        result = {"id": None}

        ctk.CTkLabel(dlg, text=self.t("dialog.add.label"), font=self.f_small,
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(16, 6))
        entry = ctk.CTkEntry(dlg, font=self.f_small,
                             placeholder_text=self.t("dialog.add.placeholder"))
        entry.pack(fill="x", padx=16)
        entry.focus_set()

        def ok():
            result["id"] = entry.get().strip()
            dlg.destroy()

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=16)
        ctk.CTkButton(btns, text=self.t("btn.cancel"), width=90, height=32,
                      fg_color=CARD_SEL, hover_color=BORDER, text_color=TEXT,
                      corner_radius=8, font=self.f_muted,
                      command=dlg.destroy).pack(side="left")
        ctk.CTkButton(btns, text=self.t("btn.add"), width=90, height=32,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                      corner_radius=8, font=self.f_muted,
                      command=ok).pack(side="right", padx=(8, 0))
        entry.bind("<Return>", lambda e: ok())

        self.root.wait_window(dlg)
        return result["id"]

    def _add_manual_mod(self):
        wid = self._ask_workshop_id()
        if not wid:
            return
        if not wid.isdigit():
            self.set_status_key("msg.id_not_a_number")
            return
        if any(m["workshop_id"] == wid for m in self.manual_mods):
            self.set_status_key("msg.already_on_list")
            return

        name = self.t("detail.workshop", wid)
        try:
            details = steam_get_details(wid)
            name = details["title"]
            self.steam_info[wid] = details
        except Exception as e:  # noqa: BLE001
            self.set_status_key("msg.added_default_name", self._error_text(e))

        self.manual_mods.append({"workshop_id": wid, "name": name})
        self.state["manual_mods"] = self.manual_mods
        save_state(self.state)
        self._build_manual_cards()
        self.refresh_statuses()
        self.set_status_key("msg.added", name)

    def _remove_manual_mod(self, wid):
        self.manual_mods = [m for m in self.manual_mods if m["workshop_id"] != wid]
        self.state["manual_mods"] = self.manual_mods
        self.state.get("mods", {}).pop(wid, None)
        save_state(self.state)
        self._build_manual_cards()
        self.refresh_statuses()

    def _mark_manual_done(self, wid):
        details = self.steam_info.get(wid)
        if not details:
            self.set_status_key("msg.check_first")
            return
        self.state.setdefault("mods", {})[wid] = {
            "steam_time_updated": details["time_updated"],
            "applied_at": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        }
        save_state(self.state)
        self.refresh_statuses()

    # -- log, toast, error handling -------------------------------------------
    def _log(self, level, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log_entries.append(f"[{ts}] {level}: {msg}")
        if len(self._log_entries) > 500:
            self._log_entries = self._log_entries[-500:]
        self._refresh_console_text()

    def _error(self, msg):
        self._log("ERROR", msg)
        self._show_toast(msg)

    def _install_excepthook(self):
        import traceback

        def handle_exc(etype, value, tb):
            text = "".join(traceback.format_exception(etype, value, tb))
            self._log("ERROR", self.t("msg.unhandled_error", text))
            try:
                self._show_toast(self.t("msg.error_toast"))
            except Exception:
                pass

        sys.excepthook = handle_exc

        def tk_report(exc, val, tb):
            handle_exc(type(exc), val if val is not None else exc, tb)

        try:
            self.root.report_callback_exception = tk_report
        except Exception:
            pass

    def _show_toast(self, msg):
        try:
            if self._toast is not None and self._toast.winfo_exists():
                self._toast_msg.configure(text=msg)
                self._toast.lift()
                return
        except Exception:
            self._toast = None

        self._toast = ctk.CTkToplevel(self.root)
        self._toast.overrideredirect(True)
        self._toast.attributes("-topmost", True)
        self._toast.configure(fg_color="#7f1d1d")

        frame = ctk.CTkFrame(self._toast, fg_color="#7f1d1d", corner_radius=12)
        frame.pack(fill="both", expand=True)

        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(top, text=self.t("toast.title"), font=self.f_man,
                     text_color="#fecaca").pack(side="left")
        ctk.CTkButton(top, text="✕", width=22, height=22, fg_color="transparent",
                      hover_color="#991b1b", text_color="#fecaca", corner_radius=6,
                      font=self.f_muted, command=self._dismiss_toast).pack(side="right")

        self._toast_msg = ctk.CTkLabel(frame, text=msg, font=self.f_muted,
                                       text_color="#fca5a5", justify="left",
                                       wraplength=290)
        self._toast_msg.pack(anchor="w", padx=14, pady=(0, 12))

        for w in (frame, top, self._toast_msg):
            w.bind("<Button-1>", lambda e: self._open_console())

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        tw, th = 340, 96
        self._toast.geometry(f"{tw}x{th}+{sw - tw - 24}+{sh - th - 84}")

    def _dismiss_toast(self):
        if self._toast is not None:
            try:
                self._toast.destroy()
            except Exception:
                pass
            self._toast = None

    def _open_console(self):
        if self._console is not None and self._console.winfo_exists():
            self._console.lift()
            self._console.focus()
            return
        self._console = ctk.CTkToplevel(self.root)
        self._console.title(self.t("console.title"))
        self._console.geometry("680x440")
        self._console.configure(fg_color=BG)
        self._console.transient(self.root)

        ctk.CTkLabel(self._console, text=self.t("console.heading"), font=self.f_mod,
                     text_color=TEXT).pack(anchor="w", padx=14, pady=(12, 6))

        self._console_box = ctk.CTkTextbox(self._console, fg_color=CARD, text_color=TEXT,
                                           font=ctk.CTkFont(family="Consolas", size=11),
                                           wrap="none")
        self._console_box.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self._refresh_console_text()

        bar = ctk.CTkFrame(self._console, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(bar, text=self.t("btn.clear"), width=90, height=32,
                      fg_color=CARD_SEL, hover_color=BORDER, text_color=TEXT,
                      corner_radius=8, font=self.f_muted,
                      command=self._clear_log).pack(side="left")
        ctk.CTkButton(bar, text=self.t("btn.close"), width=90, height=32,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                      corner_radius=8, font=self.f_muted,
                      command=self._console.destroy).pack(side="right")

    def _refresh_console_text(self):
        box = getattr(self, "_console_box", None)
        if box is not None and box.winfo_exists():
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", "\n".join(self._log_entries) or self.t("console.empty"))
            box.configure(state="disabled")

    def _clear_log(self):
        self._log_entries = []
        self._refresh_console_text()


def main():
    try:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        root = ctk.CTk()
        PZUpdaterApp(root)
        root.mainloop()
    except Exception:
        # --windowed has no console, so a crash on startup would be silent
        import traceback
        log = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                           "pzupdater_error.log")
        try:
            with open(log, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()