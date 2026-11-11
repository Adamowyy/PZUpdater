#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tytuł wiersza BETA: „zalecany" tylko wtedy, gdy beta jest tym nowszym buildem."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n
import pzupdater as pz

BETA_KEYS = ["zombiebuddy", "zombiebuddy_beta"]


class BetaTitle(unittest.TestCase):
    """Tyle aplikacji, ile trzeba, żeby złożyć tytuł karty."""

    class App:
        _display_name = pz.PZUpdaterApp._display_name
        _name_note = pz.PZUpdaterApp._name_note
        _is_hidden = pz.PZUpdaterApp._is_hidden
        _mod_name = pz.PZUpdaterApp._mod_name

        def __init__(self, versions, language="pl"):
            self.versions = versions
            self.steam_info = {}
            self.t = i18n.Translator(language)

        def _jar_version_of(self, mod):
            return self.versions.get(mod["key"])

    def mod(self, key):
        return next(m for m in pz.UPDATABLE_MODS if m["key"] == key)

    def title(self, release, beta, language="pl"):
        app = self.App({"zombiebuddy": release, "zombiebuddy_beta": beta}, language)
        return app._display_name(self.mod("zombiebuddy_beta")), app

    def test_a_newer_beta_is_recommended(self):
        name, app = self.title("2.3.4", "2.4.0-beta1")
        self.assertFalse(app._is_hidden(self.mod("zombiebuddy_beta")))
        self.assertIn(i18n.STRINGS["pl"]["mod.beta.note"], name)
        self.assertIn("zalecany", name)

    def test_a_release_that_passes_the_beta_drops_the_word(self):
        name, app = self.title("2.4.0", "2.3.4")
        self.assertTrue(app._is_hidden(self.mod("zombiebuddy_beta")))
        self.assertNotIn("zalecany", name)
        self.assertIn("(opcjonalny)", name)

    def test_the_same_version_is_not_enough_to_stay_recommended(self):
        name, _app = self.title("2.4.0", "2.4.0")
        self.assertNotIn("zalecany", name)

    def test_english_drops_the_word_too(self):
        name, _app = self.title("2.4.0", "2.3.4", "en")
        self.assertNotIn("recommended", name)
        self.assertIn("(optional)", name)

    def test_english_keeps_it_while_the_beta_leads(self):
        name, _app = self.title("2.3.4", "2.4.0-beta1", "en")
        self.assertIn("recommended", name)

    def test_a_mod_without_a_remark_is_just_its_name(self):
        app = self.App({})
        self.assertEqual(app._display_name(self.mod("tempo_patches")),
                         self.mod("tempo_patches")["name"])

    def test_both_languages_have_the_plain_note(self):
        for language in i18n.LANGUAGES:
            self.assertIn("mod.beta.note_plain", i18n.STRINGS[language], language)


if __name__ == "__main__":
    unittest.main()
