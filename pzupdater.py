#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PZ Updater - updater for Project Zomboid mods that need a manual install."""

import os
import re
import json
import queue
import shutil
import filecmp
import hashlib
import subprocess
import sys
import tempfile
import time
import threading
import datetime
import webbrowser
import urllib.request
import urllib.parse
import zipfile

# PyInstaller --windowed leaves sys.stdout/stderr as None, and a stray print()
# would crash the exe before any window shows up.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import customtkinter as ctk
from tkinter import messagebox

import i18n
from i18n import Translator

APP_NAME = "PZ Updater"
PROJECT_URL = "https://github.com/Adamowyy/PZUpdater"
APP_ID = "108600"  # Project Zomboid (Steam app id)
STEAM_API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"
PROFILE_URL = "https://steamcommunity.com/id/AdamowY/"

# Bumped by hand with every release. The running exe compares itself against the
# newest GitHub release, so the number here has to match the tag of the build.
APP_VERSION = "1.1.1"
RELEASES_API = "https://api.github.com/repos/Adamowyy/PZUpdater/releases/latest"
APP_EXE_NAME = "PZUpdater.exe"
USER_AGENT = f"{APP_NAME}/{APP_VERSION}"


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
        # the loader does nothing until the game starts with the agent launch option
        "notice": "zombiebuddy_launch_options",
        "help": {
            "en": "Copies ZombieBuddy.jar and zbNative.dll into the game folder "
                  "(the Java mod loader).",
            "pl": "Kopiuje ZombieBuddy.jar i zbNative.dll do folderu gry "
                  "(ładowarka modów Java).",
        },
    },
    {
        # Renamed to "[B42] ZombieBuddy Extensions"; the jar and its target are unchanged
        "key": "zombiebuddy_fix",
        "name": "[B42] ZombieBuddy Extensions",
        "workshop_id": "3807686870",
        "type": "jar_replace",
        "jar_name": "ZombieBuddy.jar",
        "search_under": "mods",
        "target_rel": "ZombieBuddy.jar",
        # Obsolete once ZombieBuddy ships past it; the beta alone does not count
        "obsolete_if_newer_than": "3619862853",
        "obsolete_if_installed": ["3812624292"],
        # a patch laid over the loader, not a build anyone chooses between
        "layer": True,
        "alternative_to": "3619862853",
        "help": {
            "en": "Replaces ZombieBuddy.jar in the game folder with the jar from "
                  "ZombieBuddy Extensions (the 42.21 temporary fix under its new "
                  "name). Skipped once ZombieBuddy is newer than the release this "
                  "jar was built on.",
            "pl": "Podmienia ZombieBuddy.jar w folderze gry na wersję z ZombieBuddy "
                  "Extensions (dawny Temporary Fix dla 42.21). Przestaje się "
                  "nakładać, gdy ZombieBuddy wyprzedzi wersję, na której zbudowany "
                  "jest ten jar.",
        },
    },
    {
        "key": "zombiebuddy_beta",
        "name": "ZombieBuddy BETA",
        "workshop_id": "3812624292",
        "type": "files_copy",
        "src_dir": os.path.join("mods", "ZombieBuddy", "libs"),
        "files": ["ZombieBuddy.jar", "zbNative.dll"],
        "notice": "zombiebuddy_launch_options",
        "visible_if_newer_than": "3619862853",
        "alternative_to": "3619862853",
        "name_note": "mod.beta.note",
        "help": {
            "en": "Beta of the next ZombieBuddy release. It installs the same two "
                  "files and replaces the release build, so the two can never be "
                  "active at the same time.",
            "pl": "Beta następnego wydania ZombieBuddy. Wgrywa te same dwa pliki i "
                  "zastępuje wersję z wydania, więc obie nigdy nie działają "
                  "jednocześnie.",
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
                  "(for example 42.21.0) into the game folder. Builds of the game "
                  "with a signed jar do not accept copied classes: the app says so "
                  "and offers to take the old ones out again.",
            "pl": "Kopiuje folder 'zombie' z najnowszej wersji (np. 42.21.0) do "
                  "folderu gry. Buildy gry z podpisanym jarem nie przyjmują "
                  "kopiowanych klas: aplikacja to zgłasza i proponuje usunięcie "
                  "starych plików.",
        },
    },
    {
        # Only the compiled patches; the Lua part is a normal Workshop install
        "key": "tempo_patches",
        "name": "Tempo - A Performance & FPS Optimizer",
        "workshop_id": "3736629791",
        "type": "class_patch",
        "src_dir": os.path.join("mods", "Tempo_PerfKit", "manual_installation"),
        "copy_name": "zombie",
        "target_rel": "zombie",
        "help": {
            "en": "Copies Tempo's optional files into the game folder. They are made "
                  "for one game version each, so the app takes the ones matching "
                  "yours. If the game gets a newer version and the mod has no files "
                  "for it yet, nothing is copied. Builds with a signed game jar "
                  "refuse copied classes altogether, and the app then offers to take "
                  "the old ones out.",
            "pl": "Kopiuje opcjonalne pliki Tempo do folderu gry. Są zrobione pod "
                  "konkretną wersję gry, więc aplikacja wgrywa tylko te zgodne z "
                  "Twoją. Gdy gra dostanie nowszą wersję i mod nie będzie miał dla "
                  "niej plików, nic nie zostanie wgrane. Buildy z podpisanym jarem "
                  "w ogóle nie przyjmują kopiowanych klas — aplikacja proponuje "
                  "wtedy usunięcie starych plików.",
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


# alpha, beta, rc... - anything an author puts in front of a release number
PRERELEASE = re.compile(r"(alpha|beta|rc|pre|snapshot|dev)[-_.]?", re.IGNORECASE)


def release_key(name):
    """Comparable key that keeps a pre-release below its own release."""
    text = name or ""
    found = PRERELEASE.search(text)
    if found:
        return (version_key(text[:found.start()]), 0, version_key(text[found.end():]))
    return (version_key(text), 1, [])


def version_folders(directory):
    """Every version folder inside a "manual_installation" style directory."""
    try:
        entries = os.listdir(directory)
    except OSError:
        return []
    out = []
    for e in entries:
        full = os.path.join(directory, e)
        if version_key(e) and os.path.isdir(full):
            out.append(full)
    return out


def newest_version_folder(directory):
    """Newest folder inside a "manual_installation" style directory."""
    best = None
    best_key = None
    for full in version_folders(directory):
        key = version_key(os.path.basename(full))
        if best_key is None or key > best_key:
            best, best_key = full, key
    return best


JAR_VERSION_CACHE = {}


def jar_version(path):
    """Version a jar declares in its manifest, None when it cannot be read."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (os.path.normcase(os.path.abspath(path)), st.st_size, st.st_mtime_ns)
    if key in JAR_VERSION_CACHE:
        return JAR_VERSION_CACHE[key]
    version = None
    try:
        with zipfile.ZipFile(path) as z:
            text = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        for line in text.splitlines():
            name, _, value = line.partition(":")
            if name.strip().lower() == "implementation-version":
                version = value.strip() or None
                break
    except (OSError, KeyError, zipfile.BadZipFile, RuntimeError):
        version = None
    JAR_VERSION_CACHE[key] = version
    return version


def superseded_by_version(own_version, other_version):
    """True when the other jar is built on a newer release than this one."""
    own, other = version_key(own_version or ""), version_key(other_version or "")
    if not own or not other:
        return None
    return other > own


def newer_version(candidate, other):
    """True when `candidate` is a newer version than `other`."""
    cand, ref = release_key(candidate), release_key(other)
    if not cand[0] or not ref[0]:
        return None
    return cand > ref


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
    state.setdefault("notices", {})
    # jar revision the repair warning was shown for, so it is not raised twice
    state.setdefault("repair_shown_for", None)
    # release the user said "later" to, so a newer one is offered again
    state.setdefault("app_update_skipped", None)
    if "manual_mods" not in state:
        state["manual_mods"] = list(DEFAULT_MANUAL_MODS)
    # mod cards folded down to their title (a mod nobody uses)
    if not isinstance(state.get("collapsed"), list):
        state["collapsed"] = []
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


def removed_dir():
    """Where repaired files are put aside, next to the state file."""
    return os.path.join(os.path.dirname(state_path()), "removed")


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


def update_jar_replace(mod, game, ws, t, prev=None):
    jar = find_jar(ws, mod["jar_name"], mod.get("search_under"))
    if not jar:
        return False, t("action.jar_missing", mod["jar_name"]), {}
    version = os.path.basename(os.path.dirname(jar))
    shutil.copy2(jar, os.path.join(game, mod["target_rel"]))
    return True, t("action.jar_replaced"), {"version": version}


def update_folder_copy(mod, game, ws, t, prev=None):
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
    files = {}
    for dirpath, _dirs, filenames in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        out_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(out_dir, exist_ok=True)
        for fn in filenames:
            target = os.path.join(out_dir, fn)
            shutil.copy2(os.path.join(dirpath, fn), target)
            # The record is what lets the app take these very files back out:
            # a copied folder is exactly as uninstallable as a copied class.
            recorded = os.path.relpath(target, game).replace("\\", "/")
            digest = file_sha256(target)
            if digest:
                files[recorded] = digest
            copied += 1
    version = os.path.basename(version_dir)
    return True, t("action.folder_copied", mod["copy_name"], version, t.files(copied)), \
        {"version": version, "files": files}


def update_files(mod, game, ws, t, prev=None):
    src_dir = os.path.join(ws, mod["src_dir"])
    for fn in mod["files"]:
        if not os.path.isfile(os.path.join(src_dir, fn)):
            return False, t("action.source_file_missing", fn), {}
    files = {}
    for fn in mod["files"]:
        target = os.path.join(game, fn)
        shutil.copy2(os.path.join(src_dir, fn), target)
        recorded = fn.replace("\\", "/")
        digest = file_sha256(target)
        if digest:
            files[recorded] = digest
    return True, t("action.files_copied", t.files(len(mod["files"]))), {"files": files}


def update_class_patch(mod, game, ws, t, prev=None):
    """Copies the compiled patches of the build the game reports."""
    build = game_build(game)
    if not build["build"]:
        return False, t("action.no_game_build"), {}
    if not build["trusted"]:
        return False, t("action.unverified_game_build"), {}
    src = class_patch_folder(mod, ws, build["build"])
    if not src:
        return False, t("action.no_patch_build", build["build"]), {}
    files = dir_files(src)
    if not files:
        return False, t("action.no_patch_files"), {}
    prefix = mod.get("target_rel") or mod["copy_name"]
    new = {os.path.join(prefix, rel).replace("\\", "/"): full for rel, full in files.items()}
    # A package for another build can ship a different set of classes; anything the
    # previous one wrote and this one does not is left otherwise loaded by the game.
    old = (prev or {}).get("files") or {}
    obsolete = [rel for rel in old if rel not in new]
    for rel, full in new.items():
        dst = os.path.join(game, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(full, dst)
    removed, _kept = remove_installed_files(game, obsolete, old)
    meta = {"version": build["build"], "files": {rel: file_sha256(full)
                                                 for rel, full in new.items()}}
    if removed:
        return True, t("action.patches_replaced", t.files(len(new)), build["build"],
                       t.files(len(removed))), meta
    return True, t("action.patches_installed", t.files(len(new)), build["build"]), meta


ACTION_HANDLERS = {
    "jar_replace": update_jar_replace,
    "folder_copy": update_folder_copy,
    "files_copy": update_files,
    "class_patch": update_class_patch,
}


# One-time notices

NOTICE_KEYS = ("zombiebuddy_launch_options",)


def preview_hidden(mod, version_of):
    """True when a preview entry has nothing left to show."""
    ref_id = mod.get("visible_if_newer_than")
    if not ref_id:
        return False
    ref = next((m for m in UPDATABLE_MODS if m["workshop_id"] == ref_id), None)
    if ref is None:
        return False
    return newer_version(version_of(mod), version_of(ref)) is False


def notices_to_show(mods, results, actions, shown):
    """Notices to raise after an update run."""
    names = []
    for mod, (_name, ok, _msg) in zip(mods, results):
        notice = mod.get("notice")
        if not ok or notice not in NOTICE_KEYS:
            continue
        if actions.get(mod["key"]) != "install" or shown.get(notice):
            continue
        if notice not in names:
            names.append(notice)
    return names


# Is the mod actually in the game folder?

INSTALL_OK = "ok"            # every mod file is in the game folder and matches
INSTALL_PARTIAL = "partial"  # only some of them match (usually an older version)
INSTALL_MISSING = "missing"  # none of the mod files are in the game folder
INSTALL_UNKNOWN = "unknown"  # nothing to compare against


# List order

LEFT_TODO = 0      # something to install or update - a click is waiting
LEFT_CURRENT = 1   # installed and matching the workshop copy
LEFT_IDLE = 2      # not subscribed, or superseded by another mod

TODO_WRONG = 0     # files in the game folder are outdated or only partly there
TODO_NEWER = 1     # files are fine, the author published something newer
TODO_NOT_COPIED = 2  # subscribed, but the files were never copied by hand

WATCHED_NEW = 0        # the author published something - the reason to watch
WATCHED_UNCONFIRMED = 1  # no "I installed it" mark yet, so it needs a look
WATCHED_CURRENT = 2    # nothing new on Steam and the mod is subscribed
WATCHED_UNKNOWN = 3    # Steam details not fetched yet
WATCHED_GONE = 4       # not subscribed any more, so nothing to compare against


def supported_rank(info):
    """Place of a mod from `UPDATABLE_MODS` in the left column."""
    if info.get("collapsed"):
        return (LEFT_IDLE, 0)           # folded away: a mod that is not in use
    if info.get("pending") == "repair":
        return (LEFT_TODO, -1)          # a game that does not start comes first
    if info["pending"]:
        return (LEFT_TODO, {"info": TODO_WRONG, "new": TODO_NEWER,
                            "gray": TODO_NOT_COPIED}.get(info["tag"], 3))
    return (LEFT_CURRENT if info["tag"] == "ok" else LEFT_IDLE, 0)


def watched_rank(tag, subscribed):
    """Place of a watched mod in the right column."""
    if tag == "new":
        return (WATCHED_NEW, 0)
    if tag == "info":
        return (WATCHED_UNCONFIRMED, 0)
    if tag == "ok":
        return (WATCHED_CURRENT if subscribed else WATCHED_GONE, 0)
    return (WATCHED_UNKNOWN, 0)


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


def file_sha256(path):
    """Hash of a file, or None when it cannot be read."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _stat_sig(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


def remove_installed_files(game, rels, manifest):
    """Deletes files an install wrote, by their recorded hash -> (removed, kept)."""
    removed, kept = [], []
    for rel in rels:
        path = os.path.join(game, *str(rel).split("/"))
        if not os.path.isfile(path):
            continue
        recorded = (manifest or {}).get(rel)
        if recorded and file_sha256(path) != recorded:
            kept.append(rel)
            continue
        try:
            os.remove(path)
        except OSError:
            kept.append(rel)
            continue
        removed.append(rel)
        _drop_empty_dirs(os.path.dirname(path), game)
    return removed, kept


def _drop_empty_dirs(folder, stop):
    stop = os.path.normcase(os.path.abspath(stop))
    folder = os.path.abspath(folder)
    while (os.path.normcase(folder) != stop and os.path.isdir(folder)
           and not os.listdir(folder)):
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)


def remove_mod_files(game, files, t):
    """Deletes the files of an install from the game folder -> (ok, msg, meta)."""
    if not files:
        return False, t("action.nothing_to_remove"), {}
    removed, kept = remove_installed_files(game, list(files), files)
    if not removed:
        return False, t("action.nothing_to_remove"), {"kept": kept}
    if kept:
        return True, t("action.patches_removed_kept", t.files(len(removed)),
                       t.files(len(kept))), {"removed": removed, "kept": kept}
    return True, t("action.patches_removed", t.files(len(removed))), {"removed": removed}


def remove_class_patch(mod, game, t, entry=None):
    """Takes the files of a class-patch install out of the game folder again."""
    return remove_mod_files(game, (entry or {}).get("files") or {}, t)


def shipped_files(mod, ws):
    """{path in the game folder: [every copy of it this mod ships]}.

    The install record is the exact answer to "which files are ours", but an
    install made before the app started recording one has no manifest at all.
    The files a mod ships answer it too: a file in the game folder that is
    byte-identical to one of them came from this mod, whichever version it is.
    """
    out = {}
    if not ws or not os.path.isdir(ws) or not mod:
        return out

    def add(prefix, root):
        for rel, full in dir_files(root).items():
            key = f"{prefix}/{rel}".replace("\\", "/").strip("/")
            out.setdefault(key, []).append(full)

    kind = mod["type"]
    if kind == "files_copy":
        src = os.path.join(ws, mod["src_dir"])
        for fn in mod["files"]:
            full = os.path.join(src, fn)
            if os.path.isfile(full):
                out.setdefault(fn.replace("\\", "/"), []).append(full)
    elif kind == "folder_copy":
        for version in version_folders(os.path.join(ws, mod["manual_dir"])):
            src = os.path.join(version, mod["copy_name"])
            if os.path.isdir(src):
                add(mod["target_rel"], src)
    elif kind == "class_patch":
        prefix = mod.get("target_rel") or mod["copy_name"]
        for version in version_folders(os.path.join(ws, mod["src_dir"])):
            src = os.path.join(version, mod["copy_name"])
            if os.path.isdir(src):
                add(prefix, src)
    return out


def adopted_files(mod, game, ws):
    """{path: hash} of this mod's files already in the game folder, no record needed.

    A jar replacement has none: the file it wrote sits on top of the mod's own
    jar, so taking it back out would leave nothing behind.
    """
    out = {}
    if not game:
        return out
    for rel, sources in shipped_files(mod, ws).items():
        dst = os.path.join(game, *rel.split("/"))
        if not os.path.isfile(dst):
            continue
        if any(files_identical(src, dst) for src in sources):
            digest = file_sha256(dst)
            if digest:
                out[rel] = digest
    return out


def user_zomboid_dir():
    """Project Zomboid's folder in the user profile (version.txt, console.txt)."""
    profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(profile, "Zomboid")


def jar_revision(game_dir):
    """Revision stamped into projectzomboid.jar, from zombie/GitVersion.class."""
    if not game_dir:
        return None
    try:
        with zipfile.ZipFile(os.path.join(game_dir, "projectzomboid.jar")) as z:
            raw = z.read("zombie/GitVersion.class")
    except (OSError, KeyError, zipfile.BadZipFile, RuntimeError):
        return None
    m = re.search(rb"[0-9a-f]{10}", raw)
    return m.group(0).decode("ascii") if m else None


GAME_BUILD_CACHE = {}


def game_build(game_dir):
    """{"build", "revision", "jar_revision", "trusted"} for the game in this folder."""
    version_file = os.path.join(user_zomboid_dir(), "version.txt")
    jar = os.path.join(game_dir, "projectzomboid.jar") if game_dir else None
    key = (os.path.normcase(str(game_dir)), _stat_sig(version_file),
           _stat_sig(jar) if jar else None)
    if key in GAME_BUILD_CACHE:
        return GAME_BUILD_CACHE[key]
    build = revision = None
    try:
        with open(version_file, "r", encoding="utf-8", errors="replace") as f:
            first = f.readline().split()
        if first:
            build = first[0]
        if len(first) > 1:
            revision = first[1]
    except OSError:
        pass
    jar_rev = jar_revision(game_dir)
    out = {"build": build, "revision": revision, "jar_revision": jar_rev,
           "trusted": bool(build and revision and jar_rev and revision == jar_rev)}
    GAME_BUILD_CACHE[key] = out
    return out


# Signed game jar: classes copied next to it stop the game from starting
#
# The game folder is the first entry of the classpath (".;projectzomboid.jar"),
# so a .class file lying there wins over the one inside the jar. Since build
# 42.22 the jar is signed (META-INF/PROJECTZ.SF + .EC), and the JVM refuses to
# mix signed and unsigned classes of one package:
#   java.lang.SecurityException: class "zombie.iso.IsoWorld"'s signer
#   information does not match signer information of other classes in the
#   same package
# The game dies about five seconds in, inside its own logger, so console.txt and
# every log stay empty - nothing to read, nothing to guess from. Anything that
# writes classes into the game folder has to be kept out while the jar is
# signed, and whatever is already there has to be taken out again.

# Markers of that signature, lower case, inside the jar.
JAR_SIGNATURE_MARKERS = ("meta-inf/projectz.sf", "meta-inf/projectz.ec")

# Folders that never hold game classes; skipped so a scan of the game folder
# stays a fraction of a second.
GAME_SCAN_SKIP = {"jre64", "media", "natives", "license", "launcher",
                  "reshade-shaders", "steamapps", "workshop", "zomboid", "mods",
                  "installer_backups", "backups", "docs"}

JAR_INFO_CACHE = {}


def game_jar_path(game_dir):
    return os.path.join(game_dir, "projectzomboid.jar") if game_dir else None


def jar_info(game_dir):
    """{"signed", "classes", "packages", "top"} of the game jar, or None.

    "classes" holds every class path in lower case, "packages" every package
    directory that holds a class, "top" the first segment of those paths (the
    package roots - "zombie", "org", "net"...). All lower case: Windows compares
    paths that way anyway.
    """
    jar = game_jar_path(game_dir)
    if not jar:
        return None
    key = (os.path.normcase(jar), _stat_sig(jar))
    if key in JAR_INFO_CACHE:
        return JAR_INFO_CACHE[key]
    info = None
    try:
        with zipfile.ZipFile(jar) as z:
            names = z.namelist()
    except (OSError, zipfile.BadZipFile, RuntimeError):
        names = None
    if names is not None:
        classes, packages, top = set(), set(), set()
        signed = False
        for name in names:
            low = name.replace("\\", "/").lower()
            if low in JAR_SIGNATURE_MARKERS:
                signed = True
            elif low.endswith(".class"):
                classes.add(low)
                package = low.rsplit("/", 1)[0] if "/" in low else ""
                if package:
                    packages.add(package)
                    top.add(package.split("/", 1)[0])
        info = {"signed": signed, "classes": classes, "packages": packages,
                "top": top}
    JAR_INFO_CACHE[key] = info
    return info


def loose_classes(game_dir):
    """.class files in the game folder, as paths relative to it (forward slashes)."""
    out = []
    if not game_dir or not os.path.isdir(game_dir):
        return out
    for dirpath, dirs, files in os.walk(game_dir):
        dirs[:] = [d for d in dirs if d.lower() not in GAME_SCAN_SKIP]
        for fn in files:
            if fn.lower().endswith(".class"):
                rel = os.path.relpath(os.path.join(dirpath, fn), game_dir)
                out.append(rel.replace("\\", "/"))
    return out


def clashing_classes(game_dir, rels=None):
    """Loose classes the JVM will not accept next to the game jar, sorted.

    A file that is also inside the jar is always a clash: it silently replaces
    the game's own class. While the jar is signed, any class from a package the
    jar also uses breaks the whole package, so those count too.
    """
    info = jar_info(game_dir)
    if not info:
        return []
    out = []
    for rel in (loose_classes(game_dir) if rels is None else rels):
        low = rel.replace("\\", "/").lower()
        if not low.endswith(".class"):
            continue
        if low in info["classes"]:
            out.append(rel)
            continue
        if info["signed"]:
            package = low.rsplit("/", 1)[0] if "/" in low else ""
            if package and package in info["packages"]:
                out.append(rel)
    return sorted(out)


def patch_conflicts(game_dir, mod):
    """True when this mod would write classes the JVM refuses next to the jar.

    Only a signed jar is a problem: with an unsigned one, copying classes over the
    game's own is exactly what these mods have always done. When it is signed, a
    mod that writes into a package the jar also uses breaks that whole package -
    the version does not matter there, the signer does.
    """
    info = jar_info(game_dir)
    if not info or not info["signed"]:
        return False
    rel = (mod.get("target_rel") or mod.get("copy_name") or "").strip("/\\")
    if not rel:
        return False
    low = rel.replace("\\", "/").lower()
    return low.split("/", 1)[0] in info["top"] or low in info["packages"]


def mod_owned_paths(mod, ws):
    """Lower-case paths this mod would write below its target folder.

    Tempo and Better Car Physics both copy into the same "zombie" folder, so the
    folder alone cannot say whose file a stray class is. The classes each mod
    ships can: they are read from every version folder the mod carries, because
    the one for the current build may be missing exactly when the game updated.
    """
    out = set()
    if not ws or not os.path.isdir(ws):
        return out

    def add(src):
        for rel in dir_files(src):
            out.add(rel.replace("\\", "/").lower())

    if mod["type"] == "class_patch":
        root = os.path.join(ws, mod["src_dir"])
        if os.path.isdir(root):
            for version in os.listdir(root):
                src = os.path.join(root, version, mod["copy_name"])
                if os.path.isdir(src):
                    add(src)
    elif mod["type"] == "folder_copy":
        version = newest_version_folder(os.path.join(ws, mod["manual_dir"]))
        src = os.path.join(version, mod["copy_name"]) if version else None
        if src and os.path.isdir(src):
            add(src)
    return out


def game_repair(game_dir, mods, workshop_map=None, manifests=None):
    """What stops the game from starting: {"signed", "files", "by_mod", "unknown"}.

    `by_mod` maps a mod key to the files that mod left in the game folder and
    which the JVM now refuses, `unknown` lists files no registered mod claims -
    they were put there by hand or by a mod the app does not know.

    Who owns a file is decided in this order: the manifest of a recorded install,
    then the mod that actually ships a class of that name, then the first mod
    that copies into that folder.
    """
    info = jar_info(game_dir)
    files = clashing_classes(game_dir)
    workshop_map = workshop_map or {}
    manifests = manifests or {}
    claims = []      # [(prefix, key, shipped paths)] in registry order
    for m in mods:
        rel = (m.get("target_rel") or m.get("copy_name") or "").strip("/\\")
        if not rel:
            continue
        claims.append((rel.replace("\\", "/").lower() + "/", m["key"],
                       mod_owned_paths(m, workshop_map.get(m["key"]))))

    by_mod, unknown = {}, []
    for rel in files:
        low = rel.lower()
        owner = manifests.get(low) or manifests.get(rel)
        if not owner:
            candidates = [c for c in claims if low.startswith(c[0])]
            exact = [c for c in candidates if low[len(c[0]):] in c[2]]
            owner = (exact or candidates or [(None, None, None)])[0][1]
        if owner:
            by_mod.setdefault(owner, []).append(rel)
        else:
            unknown.append(rel)
    return {"signed": bool(info and info["signed"]), "files": files,
            "by_mod": by_mod, "unknown": unknown}


def backup_taken_classes(game_dir, rels, stamp=None):
    """Moves the given classes out of the game folder into the app's own folder.

    Nothing is deleted outright: the files land in the app folder under
    %LOCALAPPDATA%, in a subfolder named after the moment of the repair, and
    that path is logged: a wrong guess stays recoverable.
    """
    stamp = stamp or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target_root = os.path.join(removed_dir(), stamp)
    moved, kept = [], []
    for rel in rels:
        src = os.path.join(game_dir, *rel.split("/"))
        if not os.path.isfile(src):
            continue
        dst = os.path.join(target_root, *rel.split("/"))
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
        except OSError:
            kept.append(rel)
            continue
        moved.append(rel)
        _drop_empty_dirs(os.path.dirname(src), game_dir)
    return moved, kept, target_root if moved else None


def class_patch_folder(mod, ws, build):
    """Folder holding the patches compiled for this game build, or None."""
    if not ws or not build:
        return None
    src = os.path.join(ws, mod["src_dir"], build, mod["copy_name"])
    return src if os.path.isdir(src) else None


def mod_targets(mod, ws, game=None):
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
    if kind == "class_patch":
        src = class_patch_folder(mod, ws, game_build(game)["build"] if game else None)
        if not src:
            return []
        prefix = mod.get("target_rel") or mod["copy_name"]
        return [("/".join((prefix, rel.replace("\\", "/"))), "file", full)
                for rel, full in dir_files(src).items()]
    return []


def build_family(mod, mods=None):
    """Every entry that installs the same files as this one, itself included."""
    mods = list(mods) if mods is not None else list(UPDATABLE_MODS)
    root_id = mod.get("alternative_to") or mod["workshop_id"]
    return [m for m in mods
            if m["workshop_id"] == root_id or m.get("alternative_to") == root_id]


def build_lane(name):
    """The marker an author put in front of a release number (beta, rc...)."""
    found = PRERELEASE.search(name or "")
    return found.group(1).lower() if found else ""


def installed_build(mod, game, workshop_map, mods=None):
    """The entry of this mod's family whose jar is in the game folder.

    Byte identity is the exact answer, but it disappears the moment the build in
    the game gets an update: the jar in the game is then one step behind its own
    source in the workshop. The version still says where it came from - it is
    the closest source that supersedes it, staying on the same lane so a beta is
    never taken for a release.
    """
    if not game:
        return None
    sources = []
    for candidate in build_family(mod, mods):
        for rel, kind, src in mod_targets(candidate, workshop_map.get(candidate["key"]), game):
            if kind == "file" and src and rel.lower().endswith(".jar"):
                sources.append((candidate, src, os.path.join(game, rel)))
                break       # one jar per entry names the whole entry
    for candidate, src, dst in sources:
        if files_identical(src, dst):
            return candidate
    version = next((jar_version(dst) for _c, _s, dst in sources
                    if os.path.isfile(dst)), None)
    if not version:
        return None
    lane, key = build_lane(version), release_key(version)
    same_lane = []
    for candidate, src, _dst in sources:
        source = jar_version(src)
        if source and build_lane(source) == lane:
            same_lane.append((candidate, release_key(source)))
    if not same_lane:
        return None
    newer = [(c, k) for c, k in same_lane if k >= key]
    # The build in the game sits one step below the source it came from, so the
    # first source that follows that version is the one that put it there.
    return (min(newer, key=lambda ck: ck[1]) if newer
            else max(same_lane, key=lambda ck: ck[1]))[0]


def offers_switch(mod, installed):
    """True when this row should offer to swap the game onto its own build."""
    if installed is None or installed is mod or mod.get("layer"):
        return False
    if installed.get("layer"):
        return mod["workshop_id"] != installed.get("alternative_to")
    return True


def clashing_build(mod, mods, workshop_map):
    """The other build of this pair that sits in the workshop next to this one."""
    if mod.get("layer"):
        return None
    for other in build_family(mod, mods):
        if other is mod or other.get("layer"):
            continue
        if workshop_map.get(other["key"]):
            return other
    return None


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
    targets = mod_targets(mod, workshop_map.get(mod["key"]), game)
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


# Updating the app itself
#
# Everybody runs a single exe, so a new release has to reach them without a
# trip to GitHub. The app asks the releases API for the newest tag, downloads
# the asset next to itself and lets a small batch file swap the file once this
# process is gone - Windows will not let a running exe be overwritten.

def app_frozen():
    """True inside the PyInstaller exe, False when running from the sources."""
    return bool(getattr(sys, "frozen", False))


def app_exe_path():
    """The file that has to be replaced: the exe, or the script in a source run."""
    return os.path.abspath(sys.executable if app_frozen() else __file__)


def update_dir():
    """Scratch folder for a downloaded release."""
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(base, "PZUpdater", "update")


def parse_release(data, exe_name=APP_EXE_NAME):
    """{"version", "exe", "sha256"} out of a GitHub release payload, or None.

    Only a release that carries a downloadable exe is usable; anything else
    (a draft, a notes-only tag) is ignored rather than shown as an update.
    """
    version = str((data or {}).get("tag_name") or "").strip().lstrip("vV")
    if not version_key(version):
        return None
    assets = {}
    for asset in (data or {}).get("assets") or []:
        name = str(asset.get("name") or "").strip().lower()
        url = asset.get("browser_download_url")
        if name and url:
            assets[name] = url
    exe = assets.get(exe_name.lower())
    if not exe:
        return None
    return {"version": version, "exe": exe,
            "sha256": assets.get(exe_name.lower() + ".sha256")}


def fetch_latest_release(timeout=15):
    """Newest published release, or None when GitHub has nothing usable."""
    req = urllib.request.Request(RELEASES_API, headers={
        "Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_release(json.loads(r.read().decode("utf-8")))


def _fetch_text(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def download_release_asset(url, dest, sha256_url=None, timeout=120):
    """Fetches an asset to `dest`, checking the hash when the release has one."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        if sha256_url:
            expected = (_fetch_text(sha256_url).split() or [""])[0].strip().lower()
            if len(expected) == 64 and file_sha256(tmp) != expected:
                raise UpdaterError("error.update_checksum")
        with open(tmp, "rb") as f:
            if f.read(2) != b"MZ":       # not a Windows executable
                raise UpdaterError("error.update_broken")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return dest


def download_app_update(release):
    """Downloads the release exe into the app's update folder, returns its path."""
    version = re.sub(r"[^0-9A-Za-z._-]", "", release.get("version") or "")
    if not version:
        raise UpdaterError("error.update_broken")
    dest = os.path.join(update_dir(), f"PZUpdater-{version}.exe")
    return download_release_asset(release["exe"], dest, release.get("sha256"))


# Windows keeps a lock on a running exe, so the swap happens in a batch file
# that waits for this process to disappear, moves the new file over the old one
# and starts it again. The wait is on the PID: tasklist does not see processes
# from a windowless cmd, and waiting on the image name would also catch an
# unrelated copy of the app. A second move 2 s later covers a file the system
# still holds for a moment; if every try fails it gives up, and because the old
# file was never touched the app the user has still runs.
NEWLINE_CRLF = chr(13) + chr(10)      # a batch file needs real CRLF, whatever this file uses

SELF_UPDATE_SCRIPT = NEWLINE_CRLF.join([
    "@echo off",
    "setlocal",
    "set \"TARGET={target}\"",
    "set \"NEW={new}\"",
    "set \"OLD={old}\"",
    "set \"MARKER={marker}\"",
    "set \"FAILED={failed}\"",
    "set \"_MEIPASS2=\"",
    "set \"_PYI_APPLICATION_HOME_DIR=\"",
    "set \"_PYI_PARENT_PROCESS_LEVEL=\"",
    "powershell -NoProfile -WindowStyle Hidden -Command \"Wait-Process -Id {pid} -ErrorAction SilentlyContinue\" 2>nul",
    "set /a tries=0",
    ":move",
    "copy /y \"%TARGET%\" \"%OLD%\" >nul 2>&1",
    "move /y \"%NEW%\" \"%TARGET%\" >nul 2>&1",
    "if not errorlevel 1 goto start",
    "set /a tries+=1",
    "if %tries% geq 15 exit /b 1",
    "timeout /t 1 /nobreak >nul",
    "goto move",
    ":start",
    "del /q \"%MARKER%\" >nul 2>&1",
    "start \"\" \"%TARGET%\"",
    "powershell -NoProfile -WindowStyle Hidden -Command \"for($i=0;$i -lt 30;$i++){{ Start-Sleep -Milliseconds 500; if(Test-Path '{marker}'){{ if((Get-Content -Raw '{marker}') -match '{version}'){{ exit 0 }} }} }}; exit 1\"",
    "if not errorlevel 1 goto done",
    "copy /y \"%OLD%\" \"%TARGET%\" >nul 2>&1",
    "echo {version}> \"%FAILED%\"",
    "start \"\" \"%TARGET%\"",
    ":done",
    "",
])


def update_marker():
    """Plik, który aplikacja zapisuje przy starcie - dowód, że build wstał."""
    return os.path.join(update_dir(), "started.txt")


def update_failed_file():
    """Wersja, która nie wystartowała po podmianie (skrypt podmiany ją zapisuje)."""
    return os.path.join(update_dir(), "failed.txt")


def write_start_marker():
    """Zapisuje znacznik startu; brak zapisu nie może przewrócić aplikacji."""
    try:
        os.makedirs(update_dir(), exist_ok=True)
        with open(update_marker(), "w", encoding="utf-8") as f:
            f.write(f"{APP_VERSION} {datetime.datetime.now().isoformat(timespec='seconds')}")
    except OSError:
        pass


def update_failed_version():
    """Wersja, która nie wstała po aktualizacji (albo None)."""
    try:
        with open(update_failed_file(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def clear_update_failed():
    try:
        os.remove(update_failed_file())
    except OSError:
        pass


def launch_self_update(new_exe, target=None):
    """Starts the swap script for a new exe; the caller has to exit afterwards."""
    target = os.path.abspath(target or app_exe_path())
    script = SELF_UPDATE_SCRIPT.format(
        target=target, new=os.path.abspath(new_exe), pid=os.getpid(),
        old=target + ".old", marker=update_marker(), failed=update_failed_file(),
        version=APP_VERSION)
    os.makedirs(update_dir(), exist_ok=True)
    bat = os.path.join(update_dir(), "apply_update.bat")
    # newline="" keeps the CRLF that is already in the script
    with open(bat, "w", encoding="utf-8", newline="") as f:
        f.write(script)
    # A frozen onefile build tells whatever it starts where it unpacked itself.
    # Passing that on would make the next build reuse a folder this one deletes
    # on the way out, and it dies with "LoadLibrary: python311.dll not found".
    env = {k: v for k, v in os.environ.items()
           if k != "_MEIPASS2" and not k.startswith("_PYI")}
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200    # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen(["cmd.exe", "/c", bat], creationflags=flags, close_fds=True, env=env)
    return bat


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
DANGER = "#dc2626"      # the uninstall button: the only action that deletes
ALERT = "#f87171"       # a detail line that has to be read: which build is ahead
WARN = "#f59e0b"        # an action that may break the game: installing a signed-jar mod
WARN_HOVER = "#d97706"
ON_WARN = "#20140a"     # dark text, because white on amber is unreadable

DISABLED_BG = "#3a3d42"
DISABLED_TEXT = "#6b7280"

# The eye on a mod card: it folds the card down to its greyed-out title. A folded
# card is a mod that is not used, so the app also stops offering it to the main
# Update button.
EYE_OPEN = "👁"
EYE_SHUT = "🙈"

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
        self._left_order = []     # card keys, in the order they are stacked
        self._manual_order = []   # the same for the watched column
        self._status_text = ""
        self._status_key = None
        self._summary = None
        self._log_entries = []
        self._toast = None
        self._console = None
        self._overlay_visible = False
        self._overlay_shown_at = 0.0
        self._repair = None       # cached {"signed", "files", "by_mod", "unknown"}
        self._app_update = None   # newer release offered by GitHub, if any

        self.paths = self._detect()
        self._sources = {}       # {target path: acceptable sources}, refreshed per check
        self._refresh_sources()

        self._log("INFO", self.t("msg.start", self.paths["steam_root"]))
        self._log("INFO", self.t("msg.game_dir", self.paths["game_dir"]))
        self._log("INFO", self.t("msg.app_version", APP_VERSION))

        self._build_ui()
        self._populate()
        self._select(UPDATABLE_MODS[0]["key"])
        self._install_excepthook()
        self.root.after(100, self._poll_queue)
        self.check_updates(silent=True)
        self.root.after(1500, self._reveal)   # fallback when the check drags on
        self.root.after(250, self._reveal)    # ...but usually reveal the curtain at once
        self.root.after(1200, self._startup_checks)

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
        self._sources = accepted_sources(self._visible_mods(), self.paths["workshop"])

    def _saved_ts(self, workshop_id):
        return self.state.get("mods", {}).get(workshop_id, {}).get("steam_time_updated", 0)

    # -- folded cards ---------------------------------------------------------
    def _is_collapsed(self, key):
        """True when this mod's card is folded down to its title."""
        return key in (self.state.get("collapsed") or [])

    def _toggle_collapsed(self, key):
        """Folds or unfolds one mod card; the choice survives a restart."""
        folded = list(self.state.get("collapsed") or [])
        if key in folded:
            folded.remove(key)
        else:
            folded.append(key)
        self.state["collapsed"] = folded
        save_state(self.state)
        self._log("INFO", f"{'folded' if key in folded else 'unfolded'}: {key}")
        self.refresh_statuses()

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
        self._left_order = []
        self._manual_order = []
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
        self.root.title(f"{APP_NAME} {APP_VERSION} — Project Zomboid")
        self.root.geometry("1240x730")
        self.root.minsize(1000, 600)
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

        # Appears only when GitHub has a newer build of the app itself
        self.btn_app_update = ctk.CTkButton(
            top, text="", width=104, height=26, fg_color=ACCENT_HOVER,
            hover_color="#1e40af", text_color="#ffffff", corner_radius=7,
            border_width=1, border_color=ACCENT, font=self.f_muted,
            command=self._start_app_update)
        self.btn_app_update.pack(side="right", padx=(0, 8))
        self.btn_app_update.pack_forget()

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
        self._left_order = []
        for m in self._visible_mods():
            card = ctk.CTkFrame(self.scroll, fg_color=CARD, corner_radius=12,
                                border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=3)

            name = ctk.CTkLabel(card, text=m["name"], font=self.f_mod,
                                text_color=TEXT, anchor="w")
            name.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))

            badge = ctk.CTkLabel(card, text=self.t("status.pending"), font=self.f_badge,
                                 text_color="#9aa0aa", fg_color="#2a2d33",
                                 corner_radius=8, height=22)
            badge.grid(row=0, column=1, sticky="e", padx=(0, 4), pady=(8, 0))

            # The eye folds the card down to its title: a mod nobody uses must not
            # take a third of the column. Which cards are folded is remembered.
            eye = ctk.CTkButton(card, text=EYE_OPEN, width=22, height=22,
                                fg_color="transparent", hover_color=CARD_SEL,
                                text_color=SUBTLE, corner_radius=6, font=self.f_muted,
                                command=lambda k=m["key"]: self._toggle_collapsed(k))
            eye.grid(row=0, column=2, sticky="e", padx=(0, 8), pady=(8, 0))

            # A frame rather than one label: the hint about which build is ahead
            # has to stand out, and a label is painted in a single colour.
            sub = ctk.CTkFrame(card, fg_color="transparent")
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
            # Appears only for a mod whose install the app recorded, so it can take
            # exactly those files back out again.
            rem = ctk.CTkButton(foot, text=self.t("btn.uninstall"), width=88, height=22,
                                fg_color="transparent", hover_color=CARD_SEL,
                                text_color=DANGER, corner_radius=6, font=self.f_muted,
                                command=lambda k=m["key"]: self.do_remove(k))
            rem.pack(side="left", padx=(8, 0))
            rem.pack_forget()

            act = ctk.CTkButton(card, text=self.t("btn.install"), height=30,
                                fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                text_color=ON_ACCENT, corner_radius=8, font=self.f_small,
                                command=lambda k=m["key"]: self._update_one(k))
            act.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
            act.grid_remove()

            card.grid_columnconfigure(0, weight=1)

            self._cards[m["key"]] = {"frame": card, "name": name, "badge": badge,
                                     "sub": sub, "foot": foot, "eye": eye,
                                     "action": act, "remove": rem, "bits": None}
            for w in (card, name, badge, sub):
                self._bind_click(w, m["key"])

        self._build_manual_cards()

    def _build_manual_cards(self):
        for w in self.manual_scroll.winfo_children():
            w.destroy()
        self._manual_cards = {}
        self._manual_order = []
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
        self._manual_cards[wid] = {"frame": card, "name": name, "sub": sub,
                                   "badge": badge, "sub_badge": sub_badge,
                                   "done": done}

    def _bind_click(self, widget, key):
        widget.bind("<Button-1>", lambda e: self._select(key))

    def _fill_bits(self, key, card, bits, note=None):
        """Short details on the first line, a longer hint on its own line below.

        Everything used to share one line, so a hint like "the game has a signed
        jar" ran past the card and was cut off. The hint now gets the full width
        and wraps instead.
        """
        if card.get("bits") == (bits, note):
            return
        frame = card["sub"]
        for child in frame.winfo_children():
            child.destroy()
        line = ctk.CTkFrame(frame, fg_color="transparent")
        line.pack(anchor="w", fill="x")
        for index, (text, colour) in enumerate(bits):
            if index:
                separator = ctk.CTkLabel(line, text="·", font=self.f_muted,
                                         text_color=SUBTLE, anchor="w")
                separator.pack(side="left", padx=6)
                self._bind_click(separator, key)
            label = ctk.CTkLabel(line, text=text, font=self.f_muted,
                                 text_color=colour, anchor="w")
            label.pack(side="left")
            self._bind_click(label, key)
        if note:
            text, colour = note
            hint = ctk.CTkLabel(frame, text=text, font=self.f_muted,
                                text_color=colour, anchor="w", justify="left",
                                wraplength=self._note_wrap())
            hint.pack(anchor="w", fill="x", pady=(2, 0))
            self._bind_click(hint, key)
        card["bits"] = (bits, note)

    def _note_wrap(self):
        """Width for the hint line - the window is wide, the card is not."""
        try:
            width = self.root.winfo_width()
        except Exception:      # noqa: BLE001 - before the window is mapped
            width = 1240
        return max(300, min(900, width - 700))

    # -- mod state ------------------------------------------------------------
    def _installed_files(self, mod):
        """Files from the last install that are still in the game folder.

        The record alone is not enough: the repair and the user both move files
        out by hand, and a record without files left an "Uninstall" button on a
        mod that was not installed anywhere.

        An install made before the app recorded what it wrote has no manifest at
        all, so the files are found the other way round: a file in the game
        folder that is byte-identical to one this mod ships is the mod's own.
        """
        entry = self.state.get("mods", {}).get(mod["workshop_id"]) or {}
        game = self.paths.get("game_dir")
        files = entry.get("files") or {}
        if not game:
            return {}
        if files:
            return {rel: digest for rel, digest in files.items()
                    if os.path.exists(os.path.join(game, rel))}
        return adopted_files(mod, game, self.paths.get("workshop", {}).get(mod["key"]))

    def _prune_dead_records(self):
        """Drops install records whose files are gone from the game folder."""
        game = self.paths.get("game_dir")
        mods = self.state.get("mods") or {}
        if not game or not mods:
            return
        dead = [wid for wid, entry in mods.items()
                if (entry.get("files") or {})
                and not any(os.path.exists(os.path.join(game, rel))
                            for rel in entry["files"])]
        for wid in dead:
            mods.pop(wid, None)
            self._log("INFO", self.t("msg.forgot_install", wid))
        if dead:
            save_state(self.state)

    def _install_state(self, mod):
        return mod_install_state(mod, self.paths["game_dir"], self.paths["workshop"],
                                 self._visible_mods(), self._sources)

    def _installed_build(self, mod):
        """The half of an either/or pair whose jar is in the game folder."""
        return installed_build(mod, self.paths.get("game_dir"),
                               self.paths.get("workshop") or {}, self._visible_mods())

    def _files_note(self, info):
        state, ok, total = info["install"], info["ok"], info["total"]
        if state == INSTALL_OK:
            return self.t("detail.files_ok", self.t.files(total))
        if state == INSTALL_MISSING:
            return self.t("detail.files_missing")
        if state == INSTALL_PARTIAL:
            return self.t("detail.files_partial", ok, total)
        return self.t("detail.files_unknown")

    def _mod_name(self, mod):
        """Live workshop title when Steam answered, the registry name otherwise."""
        details = self.steam_info.get(mod["workshop_id"]) or {}
        return (details.get("title") or "").strip() or mod["name"]

    def _display_name(self, mod):
        """Name for the card: the workshop title plus the remark a mod carries."""
        note = self.t(mod["name_note"]) if mod.get("name_note") else ""
        return f"{self._mod_name(mod)} {note}".strip() if note else self._mod_name(mod)

    # -- game repair ----------------------------------------------------------
    def _repair_state(self):
        """{"signed", "files", "by_mod", "unknown"} for the game folder, cached."""
        if self._repair is None:
            self._repair = game_repair(self.paths.get("game_dir"), self._visible_mods(),
                                       self.paths.get("workshop") or {}, self._manifests())
        return self._repair

    def _manifests(self):
        """{path in the game folder: mod key} for the installs the app recorded."""
        out = {}
        by_id = {m["workshop_id"]: m["key"] for m in self._visible_mods()}
        for workshop_id, entry in (self.state.get("mods") or {}).items():
            key = by_id.get(workshop_id)
            if not key:
                continue
            for rel in (entry.get("files") or {}):
                out[rel] = key
        return out

    def _invalidate_repair(self):
        self._repair = None

    def _repair_files(self, mod):
        """Classes of this mod that are in the game folder and stop it starting."""
        return self._repair_state()["by_mod"].get(mod["key"]) or []

    def _blocked_by_signature(self, mod):
        """True when this mod may not write anything into the game folder now."""
        return patch_conflicts(self.paths.get("game_dir"), mod)

    def _status_info(self, mod):
        """Badge text, file state and the action available for one mod."""
        ws = self.paths["workshop"].get(mod["key"])
        install, ok, total = self._install_state(mod)
        info = {"install": install, "ok": ok, "total": total, "pending": None,
                "muted": False, "status": "", "tag": "", "files_note": None,
                "switch": False, "switch_name": "", "repair": 0,
                "signed_warning": False, "name": self._mod_name(mod)}
        # Files of this mod that are in the game folder and which the JVM refuses:
        # the game does not start at all, so nothing else about this row matters.
        strays = self._repair_files(mod)
        if strays:
            info.update(status=self.t("status.repair_needed"), tag="err",
                        pending="repair", repair=len(strays))
            return info
        if not ws:
            info.update(status=self.t("status.not_subscribed"), tag="gray", muted=True)
            return info
        # A signed game jar refuses copied classes, but that is a warning on the
        # row, not a ban: the author may have changed the way the mod works, and
        # an update has to stay visible and installable either way.
        if self._blocked_by_signature(mod):
            info["signed_warning"] = True
            info["files_note"] = self.t("detail.signed_jar")
        if mod["type"] == "class_patch":
            # Made for one game version each: without the matching files, or without a
            # way to tell which version the game folder holds, nothing may be copied.
            build = game_build(self.paths["game_dir"])
            if not build["build"]:
                info.update(status=self.t("status.build_unknown"), tag="old", muted=True,
                            files_note=self.t("detail.patch_start_game"))
                return info
            if not build["trusted"]:
                info.update(status=self.t("status.build_unverified"), tag="old", muted=True,
                            files_note=self.t("detail.patch_start_game"))
                return info
            if not class_patch_folder(mod, ws, build["build"]):
                # No package for this build. If the mod's own files were left in
                # the game folder by an earlier install, they are older than the
                # game now and nothing looks after them - say so and offer to
                # take them out, instead of a quiet "no build for this game".
                if self._installed_files(mod):
                    info.update(status=self.t("status.stale_files"), tag="old",
                                pending="remove",
                                files_note=self.t("detail.stale_files"))
                    return info
                info.update(status=self.t("status.no_patch_build", build["build"]),
                            tag="old", muted=True,
                            files_note=self.t("detail.patch_wait"))
                return info
        if self._is_obsolete(mod):
            info.update(status=self.t("status.deprecated"), tag="old", muted=True)
            return info

        # One loader per game folder: the other entries offer the switch instead.
        installed = self._installed_build(mod)
        if offers_switch(mod, installed):
            info.update(status=self.t("status.other_build", installed["name"]), tag="info",
                        pending="install", switch=True, switch_name=mod["name"])
            return info

        details = self.steam_info.get(mod["workshop_id"])
        saved = self._saved_ts(mod["workshop_id"])
        cur = details["time_updated"] if details else 0

        if install == INSTALL_MISSING:
            # Subscribed, but the files are not in the game folder: the card is
            # greyed out like an unsubscribed one and installing stays a click
            # away. A version the author published after the one the app last saw
            # is news either way - without it an update lands in silence and the
            # only thing left on the card is the warning about the signed jar.
            if saved and cur > saved:
                info.update(status=self.t("status.new_version"), tag="new",
                            pending="install")
            else:
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
        for m in self._visible_mods():
            # A folded card is a mod that is not in use: no offer, no nagging.
            if self._is_collapsed(m["key"]):
                continue
            info = self._status_info(m)
            # A switch has its own button: the main one must never turn the user
            # over to the other build on its own. A repair is not an install.
            if info["pending"] in ("install", "update") and not info["switch"]:
                pending[m["key"]] = info["pending"]
        return pending

    def _installed_for_update(self):
        """Mods the main Update button may touch."""
        out = []
        visible = self._visible_mods()
        for m in visible:
            if self._is_collapsed(m["key"]):
                continue
            info = self._status_info(m)
            if not (info["pending"] in ("install", "update") and not info["switch"]
                    and info["install"] in (INSTALL_OK, INSTALL_PARTIAL)):
                continue
            if len(build_family(m, visible)) > 1 and self._installed_build(m) is not m:
                continue
            out.append(m)
        return out

    def _refresh_buttons(self):
        if self._busy:
            self.btn_check.configure(state="disabled")
            self.btn_update.configure(state="disabled")
            self.btn_add.configure(state="disabled")
            for card in self._cards.values():
                card["action"].configure(state="disabled")
                card["remove"].configure(state="disabled")
            return
        self.btn_check.configure(state="normal")
        self.btn_add.configure(state="normal")
        for card in self._cards.values():
            card["action"].configure(state="normal")
            card["remove"].configure(state="normal")
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
        self.info_name.configure(text=self._display_name(mod))
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
    def _jar_version_of(self, mod):
        """Version of the jar this mod would copy into the game folder."""
        for _rel, kind, src in mod_targets(mod, self.paths["workshop"].get(mod["key"])):
            if kind == "file" and src:
                version = jar_version(src)
                if version:
                    return version
        return None

    def _is_obsolete(self, mod):
        """True when another mod makes this one pointless."""
        # A mod can also be pointless because the build it replaces is the one in
        # the game folder, whatever the versions say.
        for other_id in mod.get("obsolete_if_installed") or []:
            other = self._mod_by_workshop_id(other_id)
            if other is not None and self._installed_build(other) is other:
                return True
        refs = mod.get("obsolete_if_newer_than")
        if not refs:
            return False
        if isinstance(refs, str):
            refs = [refs]
        own_version = self._jar_version_of(mod)
        own_ts = self.steam_info.get(mod["workshop_id"], {}).get("time_updated", 0)
        for ref_id in refs:
            ref = self._mod_by_workshop_id(ref_id)
            if ref is not None:
                verdict = superseded_by_version(own_version, self._jar_version_of(ref))
                if verdict is not None:
                    if verdict:
                        return True
                    continue
            ref_ts = self.steam_info.get(ref_id, {}).get("time_updated", 0)
            if own_ts > 0 and ref_ts > own_ts:
                return True
        return False

    def _mod_by_workshop_id(self, workshop_id):
        return next((m for m in UPDATABLE_MODS if m["workshop_id"] == workshop_id), None)

    def _preview_of(self, mod):
        """The entry that previews the next version of this mod, if one is registered."""
        return next((m for m in UPDATABLE_MODS
                     if m.get("visible_if_newer_than") == mod["workshop_id"]), None)

    def _is_hidden(self, mod):
        """True when a preview entry (the BETA) should be off the list."""
        return preview_hidden(mod, self._jar_version_of)

    def _visible_mods(self):
        return [m for m in UPDATABLE_MODS if not self._is_hidden(m)]

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

    def _restack(self, cards, order, attr, pady):
        """Stack the card frames so they follow `order` (a list of card keys)."""
        keys = [k for k in order if k in cards]
        if getattr(self, attr) == keys:
            return
        frames = [cards[k]["frame"] for k in keys]
        for frame in frames:
            frame.pack_forget()
        for frame in frames:
            frame.pack(fill="x", pady=pady)
        setattr(self, attr, keys)

    def refresh_statuses(self):
        # The beta row can come and go, so the column is rebuilt when the list changes
        if set(self._cards) != {m["key"] for m in self._visible_mods()}:
            self._rebuild_ui()
            return
        # left column: mods the app updates
        self._prune_dead_records()
        infos = {}
        for m in self._visible_mods():
            key = m["key"]
            info = self._status_info(m)
            infos[key] = info
            status, tag = info["status"], info["tag"]
            details = self.steam_info.get(m["workshop_id"])
            ws = self.paths["workshop"].get(key)

            bits = [(self.t("detail.workshop", m["workshop_id"]), MUTED)]
            if details:
                bits.append((self.t("detail.steam", fmt_ts(details["time_updated"])), MUTED))
            if m["type"] == "folder_copy" and ws:
                version_dir = newest_version_folder(os.path.join(ws, m["manual_dir"]))
                if version_dir and info["install"] != INSTALL_UNKNOWN:
                    bits.append((self.t("detail.version", os.path.basename(version_dir)),
                                 MUTED))
            if m["type"] == "class_patch" and ws:
                build = game_build(self.paths["game_dir"])["build"]
                if build:
                    bits.append((self.t("detail.build", build), MUTED))
            if self._is_obsolete(m):
                bits.append((self.t("detail.fix_obsolete"), MUTED))
            if info["repair"]:
                bits.append((self.t("detail.repair_files",
                                    self.t.files(info["repair"])), ALERT))
            # Which build is ahead, so a BETA row appearing is never a guess
            preview = self._preview_of(m)
            if preview is not None and not info["switch"]:
                bits.append((self.t("detail.newer_than_beta") if self._is_hidden(preview)
                             else self.t("detail.beta_offered"), ALERT))
            # The warning owns the note line below, so the fact that the files are
            # not in the game folder would otherwise vanish from the card.
            if info["files_note"] and info["install"] == INSTALL_MISSING:
                bits.append((self.t("detail.files_missing"), MUTED))
            # The file hint is long, so it goes on its own line and wraps
            note = None
            if info["switch"]:
                pass      # the badge already names the build that is in the game
            elif info["files_note"]:
                note = (info["files_note"], ALERT if info["signed_warning"] else MUTED)
            elif ws:
                note = (self._files_note(info), MUTED)
            else:
                note = (self.t("status.no_subscription"), MUTED)

            card = self._cards[key]
            display = self._display_name(m)
            if card["name"].cget("text") != display:
                card["name"].configure(text=display)
            if info["muted"]:
                tc, bc = BADGE["gray"]
                card["name"].configure(text_color=SUBTLE)
            else:
                tc, bc = BADGE.get(tag, BADGE[""])
                card["name"].configure(text_color=TEXT)
            card["badge"].configure(text=status, text_color=tc, fg_color=bc)
            self._fill_bits(key, card, bits, note)

            # A folded card keeps its title only, greyed out: the mod is not in
            # use and nothing on it is worth reading until the eye brings it back.
            folded = self._is_collapsed(key)
            infos[key]["collapsed"] = folded
            card["eye"].configure(text=EYE_SHUT if folded else EYE_OPEN,
                                  text_color=ACCENT if folded else SUBTLE)
            if folded:
                card["name"].configure(text_color=SUBTLE)
            for part in ("badge", "sub", "foot"):
                if folded:
                    card[part].grid_remove()
                else:
                    card[part].grid()

            if info["pending"] and not folded:
                if info["pending"] == "repair":
                    card["action"].configure(text=self.t("btn.repair"),
                                             fg_color=DANGER, hover_color="#b91c1c",
                                             command=lambda k=key: self.do_repair(k))
                elif info["pending"] == "remove":
                    card["action"].configure(text=self.t("btn.remove_files"),
                                             fg_color=CARD_SEL, hover_color=BORDER,
                                             text_color=TEXT,
                                             command=lambda k=key: self.do_remove(k))
                else:
                    if info["switch"]:
                        label = self.t("btn.switch_to", info["switch_name"])
                    elif info["install"] == INSTALL_MISSING:
                        label = self.t("btn.install")
                    else:
                        label = self.t("btn.update")
                    # Amber, not blue, when the row warns that copying may stop the
                    # game from starting: the click still works, but has to look risky.
                    warn = info["signed_warning"] and not info["switch"]
                    card["action"].configure(text=label,
                                             fg_color=WARN if warn else ACCENT,
                                             hover_color=WARN_HOVER if warn else ACCENT_HOVER,
                                             text_color=ON_WARN if warn else ON_ACCENT,
                                             command=lambda k=key: self._update_one(k))
                card["action"].grid()
            else:
                card["action"].grid_remove()

            removable = bool(self._installed_files(m))
            if removable and not card["remove"].winfo_manager():
                card["remove"].pack(side="left", padx=(8, 0))
            elif not removable and card["remove"].winfo_manager():
                card["remove"].pack_forget()

        # A row waiting for a click goes up, one that is not on this machine
        # goes down; inside a group the registry order stays.
        self._restack(self._cards, sorted(infos, key=lambda k: supported_rank(infos[k])),
                      "_left_order", 3)

        # right column: watched mods
        ranks = {}
        for m in self.manual_mods:
            wid = m["workshop_id"]
            status, tag = self._manual_status(m)
            details = self.steam_info.get(wid)
            card = self._manual_cards.get(wid)
            if not card:
                continue
            subscribed = self._manual_subscribed(wid)
            ranks[wid] = watched_rank(tag, subscribed)
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

        # Something new on Steam goes up, a mod that is not subscribed any more
        # goes down; inside a group the order they were added in stays.
        order = [m["workshop_id"] for m in self.manual_mods if m["workshop_id"] in ranks]
        self._restack(self._manual_cards, sorted(order, key=ranks.get),
                      "_manual_order", 4)
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
            installs = [self._mod_name(m) for m in self._visible_mods()
                        if actions.get(m["key"]) == "install"]
            updates = [self._mod_name(m) for m in self._visible_mods()
                       if actions.get(m["key"]) == "update"]
            updates += [m["name"] for m in self.manual_mods
                        if self._manual_status(m)[1] == "new"]
            self.set_status_summary(installs, updates)

        self._run_async(work, on_done)

    def _update_one(self, key):
        """Per-card button: installs or updates that one mod only."""
        mod = next((m for m in UPDATABLE_MODS if m["key"] == key), None)
        if mod is not None:
            self.do_update([mod])

    def do_remove(self, key):
        """Takes back exactly the files the app itself put in the game folder."""
        mod = next((m for m in UPDATABLE_MODS if m["key"] == key), None)
        if mod is None or self._busy or not self.paths["game_dir"]:
            return
        files = self._installed_files(mod)
        if not files:
            self.set_status_key("action.nothing_to_remove")
            self.refresh_statuses()
            return
        if not messagebox.askyesno(self.t("dialog.remove.title"),
                                   self.t("dialog.remove.body", self._mod_name(mod),
                                          self.t.files(len(files)))):
            return
        self.set_status_key("msg.removing_one", self._mod_name(mod))
        ok, msg, meta = remove_mod_files(self.paths["game_dir"], files, self.t)
        if ok:
            kept = meta.get("kept") or []
            record = self.state.get("mods", {}).get(mod["workshop_id"])
            if kept and record is not None:
                # What could not be taken back is still the mod's own: the record
                # stays, so the card keeps offering to remove the rest.
                record["files"] = {rel: files[rel] for rel in kept if rel in files}
            else:
                self.state.get("mods", {}).pop(mod["workshop_id"], None)
            save_state(self.state)
            self._log("INFO", msg)
            self.set_status(msg)
            if kept:
                self._log("ERROR", self.t("action.patches_removed_kept",
                                          self.t.files(len(meta.get("removed") or [])),
                                          self.t.files(len(kept))))
        else:
            self._log("ERROR", self.t("msg.remove_failed", msg))
            self.set_status_key("msg.remove_failed", msg)
        self._invalidate_repair()
        self.refresh_statuses()

    # -- repairing the game folder --------------------------------------------
    def do_repair(self, key=None):
        """Moves the classes that stop the game from starting out of the game folder.

        With `key` only that mod's files, without it everything that clashes. The
        files are put aside in the app's own folder rather than deleted, so the
        repair can be undone by hand.
        """
        if self._busy or not self.paths["game_dir"]:
            return
        self._invalidate_repair()
        mod = next((m for m in self._visible_mods() if m["key"] == key), None) if key else None
        files = self._repair_files(mod) if mod else list(self._repair_state()["files"])
        if not files:
            self.set_status_key("action.nothing_to_remove")
            self.refresh_statuses()
            return
        listed = "\n".join(files[:10]) + ("\n…" if len(files) > 10 else "")
        if not messagebox.askyesno(self.t("dialog.repair.title"),
                                   self.t("dialog.repair.body", len(files), listed)):
            return

        self._busy = True
        self._refresh_buttons()
        self.set_status_key("msg.repairing")
        moved, kept, folder = backup_taken_classes(self.paths["game_dir"], files)
        # The recorded manifests no longer describe the game folder
        mods = self.state.get("mods", {})
        for entry in mods.values():
            recorded = entry.get("files") or {}
            for rel in moved:
                recorded.pop(rel, None)
            if "files" in entry and not recorded:
                entry.pop("files", None)
        save_state(self.state)

        self._busy = False
        self._invalidate_repair()
        self._refresh_buttons()
        if moved:
            if kept:
                message = self.t("msg.repaired_kept", self.t.files(len(moved)),
                                 self.t.files(len(kept)))
            else:
                message = self.t("msg.repaired", self.t.files(len(moved)))
            self._log("INFO", message)
            if folder:
                self._log("INFO", self.t("msg.repaired_folder", folder))
            self.set_status(message)
        else:
            self._log("ERROR", self.t("msg.repair_failed"))
            self.set_status_key("msg.repair_failed")
        self.refresh_statuses()

    def _startup_checks(self):
        """Once the window is up: does the game start, and is this app current?"""
        self._invalidate_repair()
        self.refresh_statuses()
        self._maybe_warn_repair()
        self._maybe_warn_update_failed()
        self._check_app_update()

    def _maybe_warn_update_failed(self):
        """The swap script put the old exe back - it means the new build did not
        start. Say so once and stop offering that same build again."""
        failed = update_failed_version()
        if not failed:
            return
        clear_update_failed()
        self.state["app_update_skipped"] = failed
        save_state(self.state)
        message = self.t("msg.update_rolled_back", failed, APP_VERSION)
        self._log("WARN", message)
        self.set_status(message)
        self._show_toast(message)

    def _maybe_warn_repair(self):
        """Raises the repair dialog once per game build, when something blocks it."""
        state = self._repair_state()
        if not state["files"]:
            return
        build = game_build(self.paths.get("game_dir"))
        token = build.get("jar_revision") or build.get("build") or "unknown"
        if self.state.get("repair_shown_for") == token:
            return
        self.state["repair_shown_for"] = token
        save_state(self.state)
        self._show_repair_notice(state)

    def _show_repair_notice(self, state):
        files = state["files"]
        listed = "\n".join(files[:10]) + ("\n…" if len(files) > 10 else "")
        dlg, btns = self._notice_shell(
            self.t("dialog.repair.title"),
            self.t("dialog.repair.body", len(files), listed),
            window_title=self.t("dialog.repair.title"), width=620, height=380)
        ctk.CTkButton(btns, text=self.t("btn.repair"), width=150, height=34,
                      fg_color=DANGER, hover_color="#b91c1c", text_color="#ffffff",
                      corner_radius=8, font=self.f_small,
                      command=lambda: (dlg.destroy(), self.do_repair())).pack(side="left")

    # -- updating the app itself ----------------------------------------------
    def _check_app_update(self):
        """Asks GitHub for a newer build of the app; silent when it cannot tell."""
        def work():
            return fetch_latest_release()

        def on_done(result):
            if isinstance(result, tuple) and result[0] == "error":
                self._log("INFO", self.t("msg.app_update_check_failed",
                                         self._error_text(result[1])))
                return
            release = result
            if not release or not newer_version(release["version"], APP_VERSION):
                return
            self._app_update = release
            self._log("INFO", self.t("msg.app_update_found", release["version"]))
            self._show_app_update_button()
            if self.state.get("app_update_skipped") != release["version"]:
                self._show_app_update_notice()

        self._run_async(work, on_done)

    def _show_app_update_button(self):
        if not self._app_update:
            return
        try:
            self.btn_app_update.configure(
                text=self.t("btn.app_update", self._app_update["version"]))
            self.btn_app_update.pack(side="right", padx=(0, 8))
        except Exception:      # the header may be gone during a UI rebuild
            pass

    def _show_app_update_notice(self):
        release = self._app_update
        if not release:
            return
        dlg, btns = self._notice_shell(
            self.t("dialog.app_update.title", release["version"]),
            self.t("dialog.app_update.body", APP_VERSION, release["version"]),
            window_title=f"{APP_NAME} {release['version']}", width=560, height=260)
        ctk.CTkButton(btns, text=self.t("btn.update_now"), width=160, height=34,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                      corner_radius=8, font=self.f_small,
                      command=lambda: (dlg.destroy(), self._start_app_update())
                      ).pack(side="left")
        ctk.CTkButton(btns, text=self.t("btn.later"), width=110, height=34,
                      fg_color=CARD_SEL, hover_color=BORDER, text_color=TEXT,
                      corner_radius=8, font=self.f_muted,
                      command=lambda: (dlg.destroy(), self._skip_app_update())
                      ).pack(side="right", padx=(8, 0))

    def _skip_app_update(self):
        """Remembers the "later" so the same release is not offered again."""
        if not self._app_update:
            return
        self.state["app_update_skipped"] = self._app_update["version"]
        save_state(self.state)

    def _start_app_update(self):
        """Downloads the release and hands the file swap to a detached script."""
        release = self._app_update
        if not release or self._busy:
            return
        if not app_frozen():
            self.set_status_key("msg.update_source_run")
            return
        self._busy = True
        self._refresh_buttons()
        label = self.t("msg.app_update_downloading", release["version"])
        self.set_status(label)
        self._show_overlay(label)

        def work():
            return download_app_update(release)

        def on_done(result):
            self._busy = False
            self._refresh_buttons()
            self._hide_overlay()
            if isinstance(result, tuple) and result[0] == "error":
                message = self._error_text(result[1])
                self.set_status_key("msg.update_failed", message)
                self._error(self.t("msg.update_failed", message))
                return
            self.set_status_key("msg.app_update_ready", release["version"])
            self._log("INFO", self.t("msg.app_update_ready", release["version"]))
            self.root.after(400, lambda: self._quit_for_update(result))

        self._run_async(work, on_done)

    def _quit_for_update(self, new_exe):
        """Starts the swapper and closes the window so the exe can be replaced."""
        try:
            launch_self_update(new_exe)
        except Exception as e:  # noqa: BLE001 - the app must survive a bad update
            self._error(self.t("msg.update_failed", self._error_text(e)))
            return
        self._dismiss_toast()
        self.root.after(150, self.root.destroy)

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
        # A signed game jar refuses copied classes. The user asked for the mods to
        # be installable anyway, so warn once and then do what was asked - the
        # repair button and the check after the install cover the damage.
        blocked = [m for m in mods if patch_conflicts(self.paths["game_dir"], m)]
        if blocked:
            names = ", ".join(self._mod_name(m) for m in blocked)
            if not messagebox.askyesno(self.t("dialog.signed.title"),
                                       self.t("dialog.signed.body", names)):
                mods = [m for m in mods if m not in blocked]
                if not mods:
                    self.set_status_key("msg.nothing_to_update")
                    return
            else:
                self._log("WARN", self.t("msg.installing_signed", names))
        if not mods:
            self.set_status_key("msg.nothing_to_update")
            return

        self._busy = True
        self._refresh_buttons()
        installing = any(actions.get(m["key"]) == "install" for m in mods)
        if len(mods) == 1:
            self.set_status_key("msg.installing_one" if installing else "msg.updating_one",
                                self._mod_name(mods[0]))
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
                        prev = self.state.get("mods", {}).get(m["workshop_id"]) or {}
                        ok, msg, meta = handler(m, self.paths["game_dir"], ws, self.t, prev)
                    if ok:
                        details = steam_get_details(m["workshop_id"])
                        self.steam_info[m["workshop_id"]] = details
                        entry = {"steam_time_updated": details["time_updated"],
                                 "applied_at": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")}
                        if meta.get("version"):
                            entry["applied_version"] = meta["version"]
                        if meta.get("files"):
                            entry["files"] = meta["files"]
                        self.state.setdefault("mods", {})[m["workshop_id"]] = entry
                except Exception as e:  # noqa: BLE001 - one bad mod must not stop the rest
                    ok, msg = False, self._error_text(e)
                results.append((self._mod_name(m), ok, msg))
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
            self._invalidate_repair()
            ok_word, err_word = self.t("msg.result_ok"), self.t("msg.result_error")
            lines = [f"{ok_word if ok else err_word} — {name}: {msg}" for name, ok, msg in result]
            failed = [f"{name}: {msg}" for name, ok, msg in result if not ok]
            for entry in failed:
                self._log("ERROR", self.t("msg.update_failed_log", entry))
            # The install may have put classes into a game folder whose jar is
            # signed - check at once, so a game that no longer starts is repaired
            # a click away instead of found out by the player tomorrow.
            fresh = self._repair_state()
            self.refresh_statuses()
            self._hide_overlay_after_min_time()
            if failed:
                self._show_toast(self.t("msg.some_failed", len(failed)))
            self.set_status("   |   ".join(lines))
            notices = notices_to_show(mods, result, actions, self.state["notices"])
            clashing = self._clashing_builds(mods, result)
            for notice in notices:
                self.state["notices"][notice] = True
            for notice, _other in clashing:
                self.state["notices"][notice] = True
            if notices or clashing:
                save_state(self.state)   # never raise the same notice twice
                for notice in notices:
                    self._show_notice(notice)
                for _notice, other in clashing:
                    self._show_unsubscribe_notice(other)
            if fresh["files"]:
                self._log("WARN", self.t("msg.repair_after_install",
                                         self.t.files(len(fresh["files"]))))
                self.root.after(500, lambda s=fresh: self._show_repair_notice(s))

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

    # -- one-time notices -----------------------------------------------------
    def _clashing_builds(self, mods, results):
        """[(notice name, the build to unsubscribe from)] - once per build."""
        visible = self._visible_mods()
        out = []
        for mod, (_name, ok, _msg) in zip(mods, results):
            other = clashing_build(mod, visible, self.paths["workshop"]) if ok else None
            if other is None:
                continue
            notice = f"unsub_{other['key']}"
            if self.state["notices"].get(notice):
                continue
            if not any(name == notice for name, _ in out):
                out.append((notice, other))
        return out

    def _notice_shell(self, title, body=None, window_title=None, width=580, height=340):
        """Window and heading shared by the notices; returns (dialog, button row)."""
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(window_title or title)
        dlg.geometry(f"{width}x{height}")
        dlg.configure(fg_color=CARD)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.after(200, dlg.lift)          # Tk can open a dialog behind the main window
        self.root.eval(f"tk::PlaceWindow {dlg._w} center")

        wrap = width - 52
        ctk.CTkLabel(dlg, text=title, font=self.f_mod, text_color=TEXT, justify="left",
                     anchor="w", wraplength=wrap).pack(fill="x", padx=18, pady=(18, 8))
        if body:
            ctk.CTkLabel(dlg, text=body, font=self.f_small, text_color=TEXT,
                         justify="left", anchor="w",
                         wraplength=wrap).pack(fill="x", padx=18)

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=16, side="bottom")
        ctk.CTkButton(btns, text=self.t("btn.close"), width=110, height=34,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                      corner_radius=8, font=self.f_muted,
                      command=dlg.destroy).pack(side="right")
        return dlg, btns

    def _show_notice(self, name):
        """A step the app cannot do for the user, shown once after a first install."""
        value = self.t(f"notice.{name}.value")
        dlg, btns = self._notice_shell(self.t(f"notice.{name}.title"),
                                      self.t(f"notice.{name}.body"))
        entry = ctk.CTkEntry(dlg, font=ctk.CTkFont(family="Consolas", size=14),
                             height=38, justify="center")
        entry.insert(0, value)
        entry.configure(state="readonly")
        entry.pack(fill="x", padx=18, pady=(16, 0))

        copy_btn = ctk.CTkButton(btns, text=self.t("btn.copy"), width=110, height=34,
                                 fg_color=CARD_SEL, hover_color=BORDER, text_color=TEXT,
                                 corner_radius=8, font=self.f_muted)
        copy_btn.pack(side="left")

        def copy_value():
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            copy_btn.configure(text=self.t("notice.copied"))

        copy_btn.configure(command=copy_value)
        entry.focus_set()
        entry.select_range(0, "end")      # so Ctrl+C works without dragging

    def _show_unsubscribe_notice(self, other):
        """One line telling the user to drop the other build, with its workshop page."""
        dlg, btns = self._notice_shell(self.t("notice.unsub.text", self._mod_name(other)),
                                      window_title="ZombieBuddy", width=470, height=200)
        ctk.CTkButton(btns, text=self.t("btn.open_steam"), width=150, height=34,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                      corner_radius=8, font=self.f_small,
                      command=lambda w=other["workshop_id"]:
                          self._open_url(WORKSHOP_URL.format(w))).pack(side="left")
        return dlg

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
    write_start_marker()      # dowód dla skryptu podmiany, że ten build wstał
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