#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Why does the main Update button sit greyed out on this machine?

Rebuilds the left column exactly like the GUI does (same functions, no window)
straight from the real game folder, workshop folders and state.json, then prints
the badge, the pending action and whether the main button would be clickable.
Run with the build venv:  .buildenv/Scripts/python.exe tools/check_main_button.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n
import pzupdater as pz


class Headless(pz.PZUpdaterApp):
    """The app without the window: real state maths, no widgets."""

    def __init__(self, paths, state):
        self.paths = paths
        self.state = state
        self.steam_info = {}
        self.steam_failed = set()
        self.manual_mods = state["manual_mods"]
        self.t = i18n.Translator(state["language"])
        self._selected = None
        self._repair = None
        self._sources = pz.accepted_sources(self._visible_mods(), paths["workshop"])


def report(app, title):
    print(f"\n== {title} ==")
    for m in app._visible_mods():
        info = app._status_info(m)
        note = f"  {info['files_note']}" if info["files_note"] else ""
        print(f"  {m['key']:20s} {info['status']:32s} pending={str(info['pending']):8s}"
              f" muted={str(info['muted']):5s}"
              f" remove={bool(app._installed_files(m))}{note}")
    pending = app._pending_actions()
    print("  status bar, to install/update:", pending or "—")
    print("  main Update button:", [m["key"] for m in app._installed_for_update()] or "GREYED OUT")


def main():
    libs = pz.find_libraries(pz.find_steam_root())
    game = pz.find_game_dir(libs)
    paths = {"libraries": libs, "game_dir": game,
             "workshop": {m["key"]: pz.find_workshop_dir(libs, m["workshop_id"])
                          for m in pz.UPDATABLE_MODS}}
    state = pz.load_state()
    app = Headless(paths, state)
    for m in app._visible_mods():
        try:
            app.steam_info[m["workshop_id"]] = pz.steam_get_details(m["workshop_id"])
        except Exception as e:      # noqa: BLE001 - a probe must not die on the API
            print(f"  (steam {m['workshop_id']}: {e})")

    jar = os.path.join(game, "ZombieBuddy.jar")
    print(f"game: {game}")
    print(f"ZombieBuddy.jar in the game folder: {pz.jar_version(jar)}")
    for key, ws in paths["workshop"].items():
        if not ws:
            print(f"  {key}: no subscription")
            continue
        for mod in pz.UPDATABLE_MODS:
            if mod["key"] != key:
                continue
            for rel, _kind, src in pz.mod_targets(mod, ws, game):
                if src and rel.lower().endswith(".jar"):
                    print(f"  {key}: {pz.jar_version(src)}  ({rel})")

    report(app, "Row state on this machine")


if __name__ == "__main__":
    main()
