#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wiersz ZombieBuddy mowi "wymagany przez Zed's Better FPS".

Czerwono, gdy Better FPS jest zasubskrybowany, a ladowarki nie ma w grze.
Szaro, gdy oba sa na miejscu. Nic, gdy Better FPS nie ma wcale.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n
import pzupdater as pz

BETTER_FPS = "3622986450"
ZB_KEYS = ("zombiebuddy", "zombiebuddy_beta")


class Requirements(unittest.TestCase):
    """Sam kawalek aplikacji, ktory czyta stan moda wymagajacego tego wiersza."""

    class App:
        _requirements = pz.PZUpdaterApp._requirements
        _manual_subscribed = pz.PZUpdaterApp._manual_subscribed

        def __init__(self, libraries):
            self.paths = {"libraries": libraries}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pzupd_needs_")
        self.library = os.path.join(self.tmp, "SteamLibrary")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def subscribe_better_fps(self):
        folder = os.path.join(self.library, "steamapps", "workshop", "content",
                              pz.APP_ID, BETTER_FPS, "mods", "ZBBetterFPS")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "mod.info"), "w", encoding="utf-8") as f:
            f.write("name=Zed's Better FPS\nid=ZBBetterFPS\n")
        return folder

    def mod(self, key):
        return next(m for m in pz.UPDATABLE_MODS if m["key"] == key)

    # -- ktory mod jest oznaczony ------------------------------------------

    def test_both_zombiebuddy_entries_are_required_by_better_fps(self):
        for key in ZB_KEYS:
            needs = self.mod(key).get("required_by") or ()
            self.assertEqual([n["workshop_id"] for n in needs], [BETTER_FPS], key)

    # -- trzy stany --------------------------------------------------------

    def test_nothing_is_said_without_better_fps(self):
        """Bez Better FPS nikt ladowarki nie potrzebuje - wiersz milczy."""
        app = self.App([self.library])
        for key in ZB_KEYS:
            self.assertEqual(app._requirements(self.mod(key), False), [],
                             key)

    def test_subscribed_but_not_in_the_game_is_loud(self):
        self.subscribe_better_fps()
        app = self.App([self.library])
        for key in ZB_KEYS:
            self.assertEqual(app._requirements(self.mod(key), False),
                             [{"name": "Zed's Better FPS", "ok": False}], key)

    def test_both_in_place_is_quiet(self):
        self.subscribe_better_fps()
        app = self.App([self.library])
        for install in (True, True, True):
            self.assertEqual(app._requirements(self.mod("zombiebuddy"), install),
                             [{"name": "Zed's Better FPS", "ok": True}], install)

    def test_a_workshop_folder_without_content_is_not_a_subscription(self):
        """Pusty folder po odsubskrybowaniu to nie subskrypcja."""
        os.makedirs(os.path.join(self.library, "steamapps", "workshop", "content",
                                 pz.APP_ID, BETTER_FPS), exist_ok=True)
        app = self.App([self.library])
        self.assertEqual(app._requirements(self.mod("zombiebuddy"), False), [])

    def test_no_library_at_all_does_not_raise(self):
        app = self.App([])
        self.assertEqual(app._requirements(self.mod("zombiebuddy"), False), [])

    # -- tekst -------------------------------------------------------------

    def test_the_row_text_is_short(self):
        for language in ("pl", "en"):
            text = i18n.Translator(language)("detail.required_by", "Zed's Better FPS")
            self.assertLessEqual(len(text), 50, "%s: %s" % (language, text))

    def test_both_languages_have_the_words(self):
        for language in i18n.LANGUAGES:
            self.assertIn("detail.required_by", i18n.STRINGS[language], language)
            for gone in ("detail.requires", "detail.requires_ok",
                         "detail.requires_missing"):
                self.assertNotIn(gone, i18n.STRINGS[language], language)


if __name__ == "__main__":
    unittest.main()
