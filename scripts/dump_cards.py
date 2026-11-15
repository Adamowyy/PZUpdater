#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print what every card in the real PZ Updater window actually shows.

Use when the screen cannot answer: the window sits behind a fullscreen game, a
screenshot returns the game, or you only need the text, the colours and whether a
widget is hidden.

    cd /d/Adam/Projekty/PZUpdater
    .buildenv/Scripts/python.exe scripts/dump_cards.py
    APPDATA=<tmp>/fakeappdata .buildenv/Scripts/python.exe scripts/dump_cards.py

APPDATA decides which state.json is read, so a staged state (folded cards, install
records) can be exercised without touching the real one. One block per card on
stdout; the process quits itself once the cards have settled.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk

import pzupdater as pz

WAIT_MS = 4000      # one Steam round trip per mod is done well before this


def dump(app):
    try:
        print(f"version={pz.APP_VERSION} game={app.paths.get('game_dir')}")
        for key, card in app._cards.items():
            name = card["name"]
            print(f"{key}:")
            print(f"   name   = {name.cget('text')!r}  colour={name.cget('text_color')}")
            print(f"   badge  = {card['badge'].cget('text')!r}"
                  f"  shown={card['badge'].winfo_ismapped()}")
            for part in ("sub", "foot", "action"):
                extra = ""
                if part == "action":
                    extra = f"  text={card['action'].cget('text')!r}"
                print(f"   {part:<6} = shown={card[part].winfo_ismapped()}{extra}")
            eye = card.get("eye")
            if eye is not None:
                print(f"   eye    = {eye.cget('text')!r}  colour={eye.cget('text_color')}"
                      f"  mapped={bool(eye.winfo_manager())}")
    finally:
        sys.stdout.flush()
        os._exit(0)      # skip Tk teardown: after() jobs and threads are still queued


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()      # a tkinter.Tk() root fails on customtkinter options (-fg_color)
    app = pz.PZUpdaterApp(root)
    root.after(WAIT_MS, lambda: dump(app))
    root.mainloop()


if __name__ == "__main__":
    main()
