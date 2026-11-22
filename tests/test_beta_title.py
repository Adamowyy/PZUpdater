#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tytuł wiersza BETA: sama nazwa, bez dopisków."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n
import pzupdater as pz


class BetaTitle(unittest.TestCase):
    """Tyle aplikacji, ile trzeba, żeby złożyć tytuł karty."""

    class App:
        _display_name = pz.PZUpdaterApp._display_name
        _is_hidden = pz.PZUpdaterApp._is_hidden
        _mod_name = pz.PZUpdaterApp._mod_name

        def __init__(self, versions, language="pl"):
            self.versions = versions
            self.steam_info = {}
            self.steam_failed = set()
            self.t = i18n.Translator(language)

        def _jar_version_of(self, mod):
            return self.versions.get(mod["key"])

    def mod(self, key):
        return next(m for m in pz.UPDATABLE_MODS if m["key"] == key)

    def title(self, release, beta, language="pl"):
        app = self.App({"zombiebuddy": release, "zombiebuddy_beta": beta}, language)
        return app._display_name(self.mod("zombiebuddy_beta")), app

    def test_the_beta_title_is_just_the_name(self):
        for language in i18n.LANGUAGES:
            name, app = self.title("2.3.4", "2.4.0-beta1", language)
            self.assertFalse(app._is_hidden(self.mod("zombiebuddy_beta")))
            self.assertEqual(name, self.mod("zombiebuddy_beta")["name"])

    def test_no_remark_anywhere_in_the_title(self):
        for language in i18n.LANGUAGES:
            for release, beta in (("2.3.4", "2.4.0-beta1"), ("2.4.0", "2.3.4")):
                name, _app = self.title(release, beta, language)
                for word in ("zalecany", "recommended", "opcjonalny", "optional"):
                    self.assertNotIn(word, name.lower(), f"{language}: {release}/{beta}")

    def test_a_release_that_passes_the_beta_still_hides_it(self):
        _name, app = self.title("2.4.0", "2.3.4")
        self.assertTrue(app._is_hidden(self.mod("zombiebuddy_beta")))

    def test_the_same_version_is_not_enough_to_stay_visible(self):
        _name, app = self.title("2.4.0", "2.4.0")
        self.assertTrue(app._is_hidden(self.mod("zombiebuddy_beta")))

    def test_a_mod_without_a_remark_is_just_its_name(self):
        app = self.App({})
        self.assertEqual(app._display_name(self.mod("tempo_patches")),
                         self.mod("tempo_patches")["name"])

    def test_no_mod_carries_a_name_note_anymore(self):
        for mod in pz.UPDATABLE_MODS:
            self.assertNotIn("name_note", mod, mod["key"])
            self.assertNotIn("name_note_when_old", mod, mod["key"])


if __name__ == "__main__":
    unittest.main()
