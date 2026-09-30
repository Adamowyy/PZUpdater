#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PZ Updater — aktualizator modów Project Zomboid wymagających ręcznej instalacji.

Znajduje Steama i grę samodzielnie (rejestr + libraryfolders.vdf), sprawdza datę
ostatniej aktualizacji moda na Steamie i podmienia/kopiuje pliki do folderu gry.
Stan (oraz ręcznie dodane mody informacyjne) zapisuje w %APPDATA%\\PZUpdater\\state.json.

GUI: customtkinter (ciemny motyw). Zależności: pip install customtkinter.
"""

import os
import re
import json
import queue
import shutil
import sys
import threading
import datetime
import webbrowser
import urllib.request
import urllib.parse

# PyInstaller --windowed: sys.stdout/stderr są None, więc print() by wysypał aplikację
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import customtkinter as ctk

APP_NAME = "PZ Updater"
APP_ID = "108600"  # Project Zomboid (Steam app id)
STEAM_API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"
PROFILE_URL = "https://steamcommunity.com/id/AdamowY/"


# --------------------------------------------------------------------------- #
#  Rejestr obsługiwanych modów (aktualizowalnych)
# --------------------------------------------------------------------------- #
#  type: "jar_replace"  -> znajdź plik .jar w folderze moda i podmień w grze
#        "folder_copy"  -> skopiuj folder (np. "zombie") z najnowszej wersji
# --------------------------------------------------------------------------- #
UPDATABLE_MODS = [
    {
        "key": "zombiebuddy",
        "name": "ZombieBuddy",
        "workshop_id": "3619862853",
        "type": "files_copy",
        "src_dir": os.path.join("mods", "ZombieBuddy", "libs"),
        "files": ["ZombieBuddy.jar", "zbNative.dll"],
        "help": "Kopiuje ZombieBuddy.jar i zbNative.dll do folderu gry (ładowarka modów Java).",
    },
    {
        "key": "zombiebuddy_fix",
        "name": "Temporary Fix for ZombieBuddy",
        "workshop_id": "3807686870",
        "type": "jar_replace",
        "jar_name": "ZombieBuddy.jar",
        "search_under": "mods",
        "target_rel": "ZombieBuddy.jar",
        "obsolete_if_newer_than": "3619862853",
        "help": "Podmienia ZombieBuddy.jar w folderze gry na wersję zgodną z 42.21. "
                "Przestaje się nakładać, gdy ZombieBuddy dostanie nowszą wersję.",
    },
    {
        "key": "better_car_physics",
        "name": "Better Car Physics",
        "workshop_id": "2909035179",
        "type": "folder_copy",
        "manual_dir": os.path.join("mods", "BetterCarPhysics", "manual_installation"),
        "copy_name": "zombie",
        "target_rel": "zombie",
        "help": "Kopiuje folder 'zombie' z najnowszej wersji (np. 42.21.0) do folderu gry.",
    },
]

# Mod domyślnie obecny na liście "ręcznych" (tylko informacja).
DEFAULT_MANUAL_MODS = [
    {"workshop_id": "3807349984", "name": "Immersive Visuals [Reshade Preset]"},
]


# --------------------------------------------------------------------------- #
#  Wykrywanie ścieżek (Steam / biblioteki / gra / workshop)
# --------------------------------------------------------------------------- #

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

    def _add(p):
        key = os.path.normcase(os.path.normpath(p))
        if key not in seen:
            seen.add(key)
            libs.append(os.path.normpath(p))

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
    """True, jeśli folder warsztatu zawiera pliki (a nie jest pustym leftoverem po odsubskrybowaniu)."""
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


# --------------------------------------------------------------------------- #
#  Steam API — data ostatniej aktualizacji
# --------------------------------------------------------------------------- #

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
        raise RuntimeError(f"Steam nie zwrócił danych dla warsztatu {workshop_id}.")
    return {
        "title": d.get("title", ""),
        "time_updated": int(d.get("time_updated", 0)),
        "time_created": int(d.get("time_created", 0)),
    }


def fmt_ts(ts):
    if not ts:
        return "—"
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


# --------------------------------------------------------------------------- #
#  Wersje semantyczne
# --------------------------------------------------------------------------- #

def version_key(s):
    return [int(x) for x in re.findall(r"\d+", s)]


def newest_version_folder(directory):
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


# --------------------------------------------------------------------------- #
#  Stan (zapisana ostatnia aktualizacja + ręczne mody)
# --------------------------------------------------------------------------- #

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
    return state


def save_state(state):
    p = state_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


# --------------------------------------------------------------------------- #
#  Akcje aktualizacji
# --------------------------------------------------------------------------- #

def find_jar(workshop_dir, jar_name, search_under):
    root = os.path.join(workshop_dir, search_under) if search_under else workshop_dir
    if not os.path.isdir(root):
        return None
    for dirpath, _dirs, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower() == jar_name.lower():
                return os.path.join(dirpath, fn)
    return None


def update_zombiebuddy(mod, game, ws):
    jar = find_jar(ws, mod["jar_name"], mod.get("search_under"))
    if not jar:
        return False, f"Nie znaleziono {mod['jar_name']} w folderze moda.", {}
    version = os.path.basename(os.path.dirname(jar))
    target = os.path.join(game, mod["target_rel"])
    shutil.copy2(jar, target)
    return True, "ZombieBuddy.jar podmieniony.", {"version": version}


def update_bettercar(mod, game, ws):
    manual = os.path.join(ws, mod["manual_dir"])
    version_dir = newest_version_folder(manual)
    if not version_dir:
        return False, "Brak folderów wersji w manual_installation.", {}
    src = os.path.join(version_dir, mod["copy_name"])
    if not os.path.isdir(src):
        return False, f"Brak folderu '{mod['copy_name']}' w {os.path.basename(version_dir)}.", {}
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
    return True, f"Skopiowano 'zombie' (wersja {os.path.basename(version_dir)}, {copied} plików).", \
        {"version": os.path.basename(version_dir)}


def update_files(mod, game, ws):
    src_dir = os.path.join(ws, mod["src_dir"])
    files = mod["files"]
    for fn in files:
        if not os.path.isfile(os.path.join(src_dir, fn)):
            return False, f"Brak pliku '{fn}' w folderze moda.", {}
    for fn in files:
        shutil.copy2(os.path.join(src_dir, fn), os.path.join(game, fn))
    return True, f"Skopiowano {len(files)} pliki do folderu gry.", {}


# --------------------------------------------------------------------------- #
#  Kolory / motyw
# --------------------------------------------------------------------------- #

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

# badge: tag -> (text_color, fg_color) — solidne, czytelne pigułki
BADGE = {
    "ok":   ("#ffffff", "#16a34a"),  # zielony  — Aktualny
    "new":  ("#ffffff", "#d97706"),  # bursztyn — Nowa aktualizacja
    "info": ("#ffffff", "#dc2626"),  # czerwony — Do aktualizacji
    "gray": ("#ffffff", "#4b5563"),  # szary    — nie zainstalowany
    "old":  ("#ffffff", "#92400e"),  # ciemny bursztyn — Przestarzały
    "err":  ("#ffffff", "#dc2626"),  # czerwony — błąd
    "":     ("#9aa0aa", "#2a2d33"),
}


# --------------------------------------------------------------------------- #
#  GUI (customtkinter)
# --------------------------------------------------------------------------- #

class PZUpdaterApp:
    def __init__(self, root):
        self.root = root
        # Ikona okna (spójna z ikoną exe)
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            ico = os.path.join(base, "icon.ico")
            if os.path.exists(ico):
                self.root.iconbitmap(ico)
        except Exception:
            pass
        self.root.withdraw()   # ukryj okno do czasu załadowania (żeby nie migać stanem "wczytywania")
        self._revealed = False
        self.state = load_state()
        self.manual_mods = self.state["manual_mods"]  # [{workshop_id, name}, ...]
        self.steam_info = {}   # workshop_id -> details
        self._busy = False
        self._queue = queue.Queue()
        self._selected = None
        self._cards = {}
        self._manual_cards = {}
        self._log_entries = []
        self._toast = None
        self._console = None
        self.paths = self._detect()

        self._log("INFO", f"Start — Steam: {self.paths['steam_root']}")
        self._log("INFO", f"Gra: {self.paths['game_dir']}")

        self._build_ui()
        self._populate()
        self._select(UPDATABLE_MODS[0]["key"])
        self._install_excepthook()
        self.root.after(100, self._poll_queue)
        self.check_updates(silent=True)
        self.root.after(1500, self._reveal)   # awaryjnie pokaż okno, nawet gdy sprawdzanie się opóźni

    # -- wykrywanie -----------------------------------------------------------
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

    def _saved_ts(self, workshop_id):
        return self.state.get("mods", {}).get(workshop_id, {}).get("steam_time_updated", 0)

    def _manual_subscribed(self, workshop_id):
        return bool(find_workshop_dir(self.paths["libraries"], workshop_id))

    # -- UI -------------------------------------------------------------------
    def _build_ui(self):
        self.root.title(f"{APP_NAME} — Project Zomboid")
        self.root.geometry("1080x640")
        self.root.minsize(960, 540)
        self.root.configure(fg_color=BG)

        self.f_title = ctk.CTkFont(size=20, weight="bold")
        self.f_sub = ctk.CTkFont(size=12)
        self.f_mod = ctk.CTkFont(size=14, weight="bold")
        self.f_man = ctk.CTkFont(size=12, weight="bold")
        self.f_small = ctk.CTkFont(size=12)
        self.f_muted = ctk.CTkFont(size=11)
        self.f_badge = ctk.CTkFont(size=12, weight="bold")

        # nagłówek
        head = ctk.CTkFrame(self.root, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 10))

        top = ctk.CTkFrame(head, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text="PZ Updater", font=self.f_title,
                     text_color=TEXT).pack(side="left")
        sig = ctk.CTkLabel(top, text="by AdamowY", font=self.f_muted,
                           text_color=ACCENT, cursor="hand2")
        sig.pack(side="right")
        sig.bind("<Button-1>", lambda e: self._open_profile())
        sig.bind("<Enter>", lambda e: sig.configure(text_color=ACCENT_HOVER))
        sig.bind("<Leave>", lambda e: sig.configure(text_color=ACCENT))

        ctk.CTkLabel(head, text="Automatyczna aktualizacja modów Project Zomboid",
                     font=self.f_sub, text_color=MUTED).pack(anchor="w", pady=(2, 0))

        # dwie kolumny
        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20)

        # ---- LEWA kolumna: mody aktualizowalne ----
        left = ctk.CTkFrame(main, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)

        left_box = ctk.CTkFrame(left, fg_color=CARD, corner_radius=14)
        left_box.pack(fill="both", expand=True)

        l_head = ctk.CTkFrame(left_box, fg_color="transparent")
        l_head.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(l_head, text="Obsługiwane mody", font=self.f_mod,
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(l_head, text="Program aktualizuje je automatycznie",
                     font=self.f_muted, text_color=MUTED).pack(anchor="w", pady=(1, 0))

        self.scroll = ctk.CTkScrollableFrame(left_box, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # info (uproszczone)
        self.info_frame = ctk.CTkFrame(left, fg_color=CARD, corner_radius=12)
        self.info_frame.pack(fill="x", pady=(8, 0))

        info_top = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        info_top.pack(fill="x", padx=14, pady=(10, 2))
        self.info_name = ctk.CTkLabel(info_top, text="", font=self.f_mod, text_color=TEXT,
                                      anchor="w")
        self.info_name.pack(side="left")
        self.btn_steam = ctk.CTkButton(
            info_top, text="Otwórz na Steam", width=130, height=28,
            fg_color="transparent", hover_color=CARD_SEL, text_color=ACCENT,
            border_width=1, border_color=ACCENT, corner_radius=8,
            font=self.f_muted, command=self._open_steam)
        self.btn_steam.pack(side="right")

        self.info_help = ctk.CTkLabel(self.info_frame, text="", font=self.f_muted,
                                      text_color=MUTED, justify="left", anchor="w",
                                      wraplength=620)
        self.info_help.pack(fill="x", padx=14, pady=(0, 12))

        # przyciski akcji
        bar = ctk.CTkFrame(left, fg_color="transparent")
        bar.pack(fill="x", pady=(8, 0))
        self.btn_check = ctk.CTkButton(
            bar, text="Sprawdź aktualizacje", height=40, width=170,
            fg_color=CARD_SEL, hover_color=BORDER, text_color=TEXT,
            corner_radius=10, font=ctk.CTkFont(size=13, weight="bold"),
            command=self.check_updates)
        self.btn_check.pack(side="left")
        self.btn_update = ctk.CTkButton(
            bar, text="Aktualizuj", height=40, width=170,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
            corner_radius=10, font=ctk.CTkFont(size=13, weight="bold"),
            command=self.do_update)
        self.btn_update.pack(side="left", padx=(10, 0))

        # ---- PRAWA kolumna: mody ręczne (info) ----
        right = ctk.CTkFrame(main, fg_color=CARD, corner_radius=14, width=330)
        right.pack(side="right", fill="both", padx=(16, 0))
        right.pack_propagate(False)

        r_head = ctk.CTkFrame(right, fg_color="transparent")
        r_head.pack(fill="x", padx=14, pady=(12, 6))

        r_title = ctk.CTkFrame(r_head, fg_color="transparent")
        r_title.pack(fill="x")
        ctk.CTkLabel(r_title, text="Obserwowane mody", font=self.f_man,
                     text_color=TEXT).pack(side="left")
        self.btn_add = ctk.CTkButton(
            r_title, text="＋ Dodaj", width=80, height=28,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
            corner_radius=8, font=self.f_muted, command=self._add_manual_mod)
        self.btn_add.pack(side="right")

        ctk.CTkLabel(r_head, text="Tylko powiadomienia — instalujesz ręcznie",
                     font=self.f_muted, text_color=MUTED, anchor="w", justify="left",
                     wraplength=280).pack(anchor="w", pady=(2, 0))

        self.manual_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.manual_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # status (pełna szerokość, na dole)
        self.status = ctk.CTkLabel(self.root, text="", font=self.f_muted,
                                   text_color=MUTED, anchor="w", justify="left",
                                   wraplength=1040)
        self.status.pack(fill="x", padx=20, pady=(10, 14))

    def _populate(self):
        for m in UPDATABLE_MODS:
            card = ctk.CTkFrame(self.scroll, fg_color=CARD, corner_radius=12,
                                border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=3)

            name = ctk.CTkLabel(card, text=m["name"], font=self.f_mod,
                                text_color=TEXT, anchor="w")
            name.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))

            badge = ctk.CTkLabel(card, text="…", font=self.f_badge,
                                 text_color="#9aa0aa", fg_color="#2a2d33",
                                 corner_radius=8, height=22)
            badge.grid(row=0, column=1, sticky="e", padx=12, pady=(8, 0))

            sub = ctk.CTkLabel(card, text="", font=self.f_muted, text_color=MUTED,
                               anchor="w")
            sub.grid(row=1, column=0, sticky="w", padx=12, pady=(2, 8))

            foot = ctk.CTkFrame(card, fg_color="transparent")
            foot.grid(row=1, column=1, sticky="e", padx=12, pady=(2, 8))
            wid = m["workshop_id"]
            ctk.CTkButton(foot, text="↗ Steam", width=68, height=22,
                          fg_color="transparent", hover_color=CARD_SEL, text_color=ACCENT,
                          corner_radius=6, font=self.f_muted,
                          command=lambda w=wid: self._open_steam_wid(w)).pack(side="left")
            ctk.CTkButton(foot, text="Kopiuj ID", width=74, height=22,
                          fg_color="transparent", hover_color=CARD_SEL, text_color=MUTED,
                          corner_radius=6, font=self.f_muted,
                          command=lambda w=wid: self._copy_id(w)).pack(side="left", padx=(8, 0))

            card.grid_columnconfigure(0, weight=1)

            self._cards[m["key"]] = {"frame": card, "name": name,
                                     "badge": badge, "sub": sub}
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

        rm = ctk.CTkButton(card, text="✕", width=24, height=24,
                           fg_color="transparent", hover_color="#3a1a1a",
                           text_color=SUBTLE, corner_radius=6,
                           font=self.f_muted, command=lambda w=wid: self._remove_manual_mod(w))
        rm.grid(row=0, column=1, sticky="e", padx=(0, 10), pady=(10, 0))

        sub = ctk.CTkLabel(card, text="", font=self.f_muted, text_color=MUTED,
                           anchor="w", justify="left")
        sub.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(2, 0))

        badges = ctk.CTkFrame(card, fg_color="transparent")
        badges.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 8))

        badge = ctk.CTkLabel(badges, text="…", font=self.f_muted, text_color="#9aa0aa",
                             fg_color="#2a2d33", corner_radius=8, height=22)
        badge.pack(side="left")

        sub_badge = ctk.CTkLabel(badges, text="…", font=self.f_muted, text_color="#9aa0aa",
                                 fg_color="#2a2d33", corner_radius=8, height=22)
        sub_badge.pack(side="left", padx=(6, 0))

        foot = ctk.CTkFrame(card, fg_color="transparent")
        foot.grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 0))
        ctk.CTkButton(foot, text="↗ Steam", width=70, height=24,
                      fg_color="transparent", hover_color=BORDER, text_color=ACCENT,
                      corner_radius=6, font=self.f_muted,
                      command=lambda w=wid: self._open_steam_wid(w)).pack(side="left")
        ctk.CTkButton(foot, text="Kopiuj ID", width=76, height=24,
                      fg_color="transparent", hover_color=BORDER, text_color=MUTED,
                      corner_radius=6, font=self.f_muted,
                      command=lambda w=wid: self._copy_id(w)).pack(side="left", padx=(8, 0))

        done = ctk.CTkButton(card, text="✓ Oznacz jako zaktualizowane", height=32,
                             fg_color="#16a34a", hover_color="#15803d",
                             text_color="#ffffff", corner_radius=8, font=self.f_mod,
                             command=lambda w=wid: self._mark_manual_done(w))
        done.grid(row=4, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 12))

        card.grid_columnconfigure(0, weight=1)
        self._manual_cards[wid] = {"name": name, "sub": sub, "badge": badge,
                                   "sub_badge": sub_badge, "done": done}

    def _bind_click(self, widget, key):
        widget.bind("<Button-1>", lambda e: self._select(key))

    # -- pomocnicze -----------------------------------------------------------
    def _has_pending_updates(self):
        for m in UPDATABLE_MODS:
            _status, tag = self._updatable_status(m)
            if tag in ("info", "new"):
                return True
        return False

    def _refresh_buttons(self):
        if self._busy:
            self.btn_check.configure(state="disabled")
            self.btn_update.configure(state="disabled")
            self.btn_add.configure(state="disabled")
            return
        self.btn_check.configure(state="normal")
        self.btn_add.configure(state="normal")
        if self._has_pending_updates():
            self.btn_update.configure(state="normal", fg_color=ACCENT,
                                      hover_color=ACCENT_HOVER, text_color=ON_ACCENT)
        else:
            self.btn_update.configure(state="disabled", fg_color="#3a3d42",
                                      text_color="#6b7280")

    def _open_steam_wid(self, wid):
        url = WORKSHOP_URL.format(wid)
        try:
            os.startfile(url)   # Windows: otwiera domyślną przeglądarką (ShellExecute)
        except Exception:
            webbrowser.open(url)   # fallback

    def _copy_id(self, wid):
        self.root.clipboard_clear()
        self.root.clipboard_append(str(wid))
        self.set_status(f"Skopiowano Workshop ID: {wid}")

    def _open_profile(self):
        try:
            os.startfile(PROFILE_URL)
        except Exception:
            webbrowser.open(PROFILE_URL)

    def _open_steam(self):
        mod = next((m for m in UPDATABLE_MODS if m["key"] == self._selected), None)
        if mod:
            self._open_steam_wid(mod["workshop_id"])

    def _select(self, key):
        self._selected = key
        mod = next(m for m in UPDATABLE_MODS if m["key"] == key)
        for k, c in self._cards.items():
            sel = (k == key)
            c["frame"].configure(border_color=ACCENT if sel else BORDER,
                                 border_width=2 if sel else 1,
                                 fg_color=CARD_SEL if sel else CARD)
        self.info_name.configure(text=mod["name"])
        self.info_help.configure(text=mod["help"])

    def set_status(self, text):
        self.status.configure(text=text)

    def _reveal(self):
        if self._revealed:
            return
        self._revealed = True
        self.root.update_idletasks()
        self.root.deiconify()
        self.root.lift()

    # -- statusy --------------------------------------------------------------
    def _is_obsolete(self, mod):
        ref = mod.get("obsolete_if_newer_than")
        if not ref:
            return False
        own = self.steam_info.get(mod["workshop_id"], {}).get("time_updated", 0)
        newer = self.steam_info.get(ref, {}).get("time_updated", 0)
        return own > 0 and newer > 0 and newer > own

    def _updatable_status(self, mod):
        ws = self.paths["workshop"].get(mod["key"])
        if not ws:
            return "Nie zainstalowany", "gray"
        if self._is_obsolete(mod):
            return "Przestarzały", "old"
        details = self.steam_info.get(mod["workshop_id"])
        saved = self._saved_ts(mod["workshop_id"])
        cur = details["time_updated"] if details else 0
        if not cur:
            return "…", ""
        if not saved:
            return "Do aktualizacji", "info"
        if cur > saved:
            return "Nowa aktualizacja", "new"
        return "Aktualny", "ok"

    def _manual_status(self, m):
        details = self.steam_info.get(m["workshop_id"])
        saved = self._saved_ts(m["workshop_id"])
        cur = details["time_updated"] if details else 0
        if not cur:
            return "…", ""
        if not saved:
            return "Do aktualizacji", "info"
        if cur > saved:
            return "Nowa aktualizacja", "new"
        return "Aktualny", "ok"

    def refresh_statuses(self):
        # lewa kolumna
        for m in UPDATABLE_MODS:
            key = m["key"]
            status, tag = self._updatable_status(m)
            details = self.steam_info.get(m["workshop_id"])
            ws = self.paths["workshop"].get(key)

            bits = [f"Workshop {m['workshop_id']}"]
            if details:
                bits.append("Steam: " + fmt_ts(details["time_updated"]))
            if m["type"] == "folder_copy" and ws:
                vd = newest_version_folder(os.path.join(ws, m["manual_dir"]))
                if vd:
                    bits.append("wersja " + os.path.basename(vd))
            if self._is_obsolete(m):
                bits.append("ZombieBuddy nowszy — fix zbędny")
            if not ws:
                bits.append("brak subskrypcji")

            card = self._cards[key]
            tc, bc = BADGE.get(tag, BADGE[""])
            if not ws:
                tc, bc = BADGE["gray"]
                card["name"].configure(text_color=SUBTLE)
            else:
                card["name"].configure(text_color=TEXT)
            card["badge"].configure(text=status, text_color=tc, fg_color=bc)
            card["sub"].configure(text="  ·  ".join(bits))

        # prawa kolumna
        for m in self.manual_mods:
            wid = m["workshop_id"]
            status, tag = self._manual_status(m)
            details = self.steam_info.get(wid)
            card = self._manual_cards.get(wid)
            if not card:
                continue
            subscribed = self._manual_subscribed(wid)
            tc, bc = BADGE.get(tag, BADGE[""])
            card["badge"].configure(text=status, text_color=tc, fg_color=bc)
            if subscribed:
                card["sub_badge"].configure(text="✓ subskrybowany",
                                            text_color="#4ade80", fg_color="#14301f")
                card["name"].configure(text_color=TEXT)
            else:
                card["sub_badge"].configure(text="brak subskrypcji",
                                            text_color="#9aa0aa", fg_color="#2a2d33")
                card["name"].configure(text_color=SUBTLE)
            if subscribed and tag in ("info", "new"):
                card["done"].grid()
            else:
                card["done"].grid_remove()
            sub = f"Workshop {wid}"
            if details:
                sub += "  ·  " + fmt_ts(details["time_updated"])
            card["sub"].configure(text=sub)
        self._refresh_buttons()

    # -- akcje (w tle) --------------------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                fn, arg = self._queue.get_nowait()
                fn(arg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _run_async(self, fn, on_done):
        def worker():
            try:
                result = fn()
            except Exception as e:  # noqa: BLE001
                result = ("error", str(e))
            self._queue.put((on_done, result))
        threading.Thread(target=worker, daemon=True).start()

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
            self.set_status("Sprawdzam aktualizacje…")

        ids = self._all_workshop_ids()

        def work():
            return {wid: steam_get_details(wid) for wid in ids}

        def on_done(result):
            self._busy = False
            self._refresh_buttons()
            self._refresh_workshop_dirs()
            if isinstance(result, tuple) and result[0] == "error":
                self.set_status(f"Błąd sprawdzania: {result[1]}")
                self._error(f"Błąd sprawdzania aktualizacji: {result[1]}")
                self._reveal()
                return
            self.steam_info = result
            self.refresh_statuses()
            self._reveal()
            if not silent:
                new = [m["name"] for m in UPDATABLE_MODS if self._updatable_status(m)[1] == "new"]
                new += [m["name"] for m in self.manual_mods if self._manual_status(m)[1] == "new"]
                self.set_status("Nowa aktualizacja: " + ", ".join(new) if new else "Wszystko aktualne.")

        self._run_async(work, on_done)

    def do_update(self):
        if self._busy:
            return
        if not self.paths["game_dir"]:
            self.set_status("⚠ Nie znaleziono folderu gry Project Zomboid.")
            return
        installed = [m for m in UPDATABLE_MODS
                     if self.paths["workshop"].get(m["key"]) and not self._is_obsolete(m)]
        if not installed:
            self.set_status("⚠ Brak zainstalowanych (subskrybowanych) modów do aktualizacji.")
            return

        self._busy = True
        self._refresh_buttons()
        self.set_status("Aktualizuję…")

        def work():
            results = []
            for m in installed:
                key = m["key"]
                ws = self.paths["workshop"][key]
                try:
                    if m["type"] == "jar_replace":
                        ok, msg, meta = update_zombiebuddy(m, self.paths["game_dir"], ws)
                    elif m["type"] == "folder_copy":
                        ok, msg, meta = update_bettercar(m, self.paths["game_dir"], ws)
                    elif m["type"] == "files_copy":
                        ok, msg, meta = update_files(m, self.paths["game_dir"], ws)
                    else:
                        ok, msg, meta = False, "Nieznany typ.", {}
                    if ok:
                        details = steam_get_details(m["workshop_id"])
                        self.steam_info[m["workshop_id"]] = details
                        entry = {"steam_time_updated": details["time_updated"],
                                 "applied_at": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")}
                        if meta.get("version"):
                            entry["applied_version"] = meta["version"]
                        self.state.setdefault("mods", {})[m["workshop_id"]] = entry
                except Exception as e:  # noqa: BLE001
                    ok, msg = False, str(e)
                results.append((m["name"], ok, msg))
            save_state(self.state)
            return results

        def on_done(result):
            self._busy = False
            self._refresh_buttons()
            if isinstance(result, tuple) and result[0] == "error":
                self.set_status(f"Błąd aktualizacji: {result[1]}")
                self._error(f"Błąd aktualizacji: {result[1]}")
                return
            lines = [f"{'OK' if ok else 'BŁĄD'} — {name}: {msg}" for name, ok, msg in result]
            failed = [f"{name}: {msg}" for name, ok, msg in result if not ok]
            for f in failed:
                self._log("ERROR", "Nie udało się zaktualizować — " + f)
            if failed:
                self._show_toast(f"{len(failed)} mod(ów) nie zaktualizowano — kliknij, by zobaczyć log")
            self.refresh_statuses()
            self.set_status("   |   ".join(lines))

        self._run_async(work, on_done)

    # -- dodawanie / usuwanie modów ręcznych ----------------------------------
    def _ask_workshop_id(self):
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Dodaj mod")
        dlg.geometry("400x170")
        dlg.configure(fg_color=CARD)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        self.root.eval(f"tk::PlaceWindow {dlg._w} center")

        result = {"id": None}

        ctk.CTkLabel(dlg, text="Workshop ID moda:", font=self.f_small,
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(16, 6))
        entry = ctk.CTkEntry(dlg, font=self.f_small, placeholder_text="np. 3807349984")
        entry.pack(fill="x", padx=16)
        entry.focus_set()

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=16)

        def ok():
            result["id"] = entry.get().strip()
            dlg.destroy()

        ctk.CTkButton(btns, text="Anuluj", width=90, height=32,
                      fg_color=CARD_SEL, hover_color=BORDER, text_color=TEXT,
                      corner_radius=8, font=self.f_muted, command=dlg.destroy).pack(side="left")
        ctk.CTkButton(btns, text="Dodaj", width=90, height=32,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                      corner_radius=8, font=self.f_muted, command=ok).pack(side="right", padx=(8, 0))
        entry.bind("<Return>", lambda e: ok())

        self.root.wait_window(dlg)
        return result["id"]

    def _add_manual_mod(self):
        wid = self._ask_workshop_id()
        if not wid:
            return
        if not wid.isdigit():
            self.set_status("⚠ Workshop ID musi być liczbą.")
            return
        if any(m["workshop_id"] == wid for m in self.manual_mods):
            self.set_status("⚠ Ten mod jest już na liście.")
            return

        name = "Workshop " + wid
        try:
            d = steam_get_details(wid)
            name = d["title"]
            self.steam_info[wid] = d
        except Exception as e:  # noqa: BLE001
            self.set_status(f"⚠ Dodano z domyślną nazwą (błąd pobierania: {e})")

        self.manual_mods.append({"workshop_id": wid, "name": name})
        self.state["manual_mods"] = self.manual_mods
        save_state(self.state)
        self._build_manual_cards()
        self.refresh_statuses()
        self.set_status(f"✓ Dodano: {name}")

    def _remove_manual_mod(self, wid):
        self.manual_mods = [m for m in self.manual_mods if m["workshop_id"] != wid]
        self.state["manual_mods"] = self.manual_mods
        self.state.get("mods", {}).pop(wid, None)
        save_state(self.state)
        self._build_manual_cards()
        self.refresh_statuses()

    def _mark_manual_done(self, wid):
        d = self.steam_info.get(wid)
        if not d:
            self.set_status("⚠ Najpierw sprawdź aktualizacje (brak danych ze Steama).")
            return
        self.state.setdefault("mods", {})[wid] = {
            "steam_time_updated": d["time_updated"],
            "applied_at": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        }
        save_state(self.state)
        self.refresh_statuses()

    # -- logi i obsługa błędów ------------------------------------------------
    def _log(self, level, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {level}: {msg}"
        self._log_entries.append(line)
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
            self._log("ERROR", "Nieobsłużony błąd:\n" + text)
            try:
                self._show_toast("Wystąpił błąd — kliknij, by zobaczyć log")
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
        ctk.CTkLabel(top, text="⚠ Wystąpił błąd", font=self.f_man,
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
        self._console.title("Log — PZ Updater")
        self._console.geometry("680x440")
        self._console.configure(fg_color=BG)
        self._console.transient(self.root)

        ctk.CTkLabel(self._console, text="Log błędów i zdarzeń", font=self.f_mod,
                     text_color=TEXT).pack(anchor="w", padx=14, pady=(12, 6))

        self._console_box = ctk.CTkTextbox(self._console, fg_color=CARD, text_color=TEXT,
                                           font=ctk.CTkFont(family="Consolas", size=11),
                                           wrap="none")
        self._console_box.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self._refresh_console_text()

        bar = ctk.CTkFrame(self._console, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(bar, text="Wyczyść", width=90, height=32,
                      fg_color=CARD_SEL, hover_color=BORDER, text_color=TEXT,
                      corner_radius=8, font=self.f_muted,
                      command=self._clear_log).pack(side="left")
        ctk.CTkButton(bar, text="Zamknij", width=90, height=32,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                      corner_radius=8, font=self.f_muted,
                      command=self._console.destroy).pack(side="right")

    def _refresh_console_text(self):
        box = getattr(self, "_console_box", None)
        if box is not None and box.winfo_exists():
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", "\n".join(self._log_entries) or "(brak wpisów)")
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
