#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wiersz ZombieBuddy mówi, czy Zed's Better FPS jest zasubskrybowany."""

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
    """Sam kawałek aplikacji, który czyta stan wymaganego moda."""

    class App:
        _requirements = pz.PZUpdaterApp._requirements
        _manual_subscribed = pz.PZUpdaterApp._manual_subscribed

        def __init__(self, libraries):
            self.paths = {"libraries": libraries}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pzupd_needs_")
        self.library = os.path.join(self.tmp, "SteamLibrary")
        self.t = i18n.Translator("pl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def subscribe(self, workshop_id=BETTER_FPS, mod="ZBBetterFPS"):
        folder = os.path.join(self.library, "steamapps", "workshop", "content",
                              pz.APP_ID, workshop_id, "mods", mod)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "mod.info"), "w", encoding="utf-8") as f:
            f.write("name=Zed's Better FPS\nid=ZBBetterFPS\n")
        return folder

    def mod(self, key):
        return next(m for m in pz.UPDATABLE_MODS if m["key"] == key)

    def test_both_zombiebuddy_entries_watch_better_fps(self):
        for key in ZB_KEYS:
            needs = self.mod(key).get("requires") or ()
            self.assertEqual([n["workshop_id"] for n in needs], [BETTER_FPS], key)

    def test_a_subscription_is_reported_as_present(self):
        self.subscribe()
        app = self.App([self.library])
        for key in ZB_KEYS:
            self.assertEqual(app._requirements(self.mod(key)),
                             [{"name": "Zed's Better FPS", "ok": True}], key)

    def test_without_the_subscription_it_says_so(self):
        app = self.App([self.library])
        for key in ZB_KEYS:
            self.assertEqual(app._requirements(self.mod(key)),
                             [{"name": "Zed's Better FPS", "ok": False}], key)

    def test_a_workshop_folder_without_content_does_not_count(self):
        """Pusty folder po odsubskrybowaniu to nie subskrypcja."""
        os.makedirs(os.path.join(self.library, "steamapps", "workshop", "content",
                                 pz.APP_ID, BETTER_FPS), exist_ok=True)
        app = self.App([self.library])
        self.assertFalse(app._requirements(self.mod("zombiebuddy"))[0]["ok"])

    def test_no_library_at_all_does_not_raise(self):
        app = self.App([])
        self.assertFalse(app._requirements(self.mod("zombiebuddy"))[0]["ok"])

    def test_the_row_text_is_short(self):
        """Wiersz jest ciasny: nazwa moda plus stan musi się zmieścić."""
        for language in ("pl", "en"):
            t = i18n.Translator(language)
            for state in ("detail.requires_ok", "detail.requires_missing"):
                text = t("detail.requires", "Zed's Better FPS", t(state))
                self.assertLessEqual(len(text), 50, f"{language}: {text}")

    def test_both_languages_have_the_words(self):
        for key in ("detail.requires", "detail.requires_ok", "detail.requires_missing"):
            for language in i18n.LANGUAGES:
                self.assertIn(key, i18n.STRINGS[language], language)


if __name__ == "__main__":
    unittest.main()
