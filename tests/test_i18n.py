#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the translation layer.

Run with:
    .buildenv/Scripts/python.exe -m unittest discover -s tests -v
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n


class TestTables(unittest.TestCase):
    def test_every_language_has_the_same_keys(self):
        """A translation missing in one table would silently fall back to English."""
        reference = set(i18n.STRINGS[i18n.DEFAULT_LANGUAGE])
        for language in i18n.LANGUAGES:
            self.assertIn(language, i18n.STRINGS)
            self.assertEqual(reference - set(i18n.STRINGS[language]), set(),
                             msg=f"{language}: brakujące klucze")
            self.assertEqual(set(i18n.STRINGS[language]) - reference, set(),
                             msg=f"{language}: klucze bez odpowiednika w EN")

    def test_placeholders_match_between_languages(self):
        """Both texts of a key must take the same arguments, in the same order."""
        pattern = re.compile(r"\{\}")
        for key, english in i18n.STRINGS[i18n.DEFAULT_LANGUAGE].items():
            for language in i18n.LANGUAGES:
                text = i18n.STRINGS[language].get(key, "")
                self.assertEqual(len(pattern.findall(text)), len(pattern.findall(english)),
                                 msg=f"{language}/{key}: inna liczba argumentów niż w EN")

    def test_translator_has_a_flag(self):
        for language in i18n.LANGUAGES:
            self.assertIn(language, i18n.FLAGS)


class TestTranslator(unittest.TestCase):
    def test_returns_text_for_the_selected_language(self):
        self.assertEqual(i18n.Translator("en")("btn.update"), "Update")
        self.assertEqual(i18n.Translator("pl")("btn.update"), "Aktualizuj")

    def test_formats_arguments(self):
        self.assertEqual(i18n.Translator("pl")("detail.version", "42.21.0"), "wersja 42.21.0")
        self.assertEqual(i18n.Translator("en")("detail.version", "42.21.0"), "version 42.21.0")

    def test_unknown_language_falls_back_to_default(self):
        self.assertEqual(i18n.Translator("de").language, i18n.DEFAULT_LANGUAGE)

    def test_unknown_key_falls_back_to_english_then_to_the_key(self):
        t = i18n.Translator("pl")
        self.assertEqual(t("nie.ma.takiego.klucza"), "nie.ma.takiego.klucza")

    def test_broken_placeholder_does_not_raise(self):
        self.assertEqual(i18n.Translator("en")("detail.version", "a", "b"), "version a")

    def test_switch_language(self):
        t = i18n.Translator("en")
        t.set_language("pl")
        self.assertEqual(t("btn.install"), "Zainstaluj")
        t.set_language("klingon")
        self.assertEqual(t.language, i18n.DEFAULT_LANGUAGE)

    def test_help_text_picks_the_language(self):
        spec = {"en": "English help", "pl": "Polska pomoc"}
        self.assertEqual(i18n.Translator("pl").help_text(spec), "Polska pomoc")
        self.assertEqual(i18n.Translator("en").help_text(spec), "English help")
        # a plain string still works (a mod without a translation shows something)
        self.assertEqual(i18n.Translator("pl").help_text("tylko tekst"), "tylko tekst")
        self.assertEqual(i18n.Translator("pl").help_text(None), "")


class TestFilesPlural(unittest.TestCase):
    def test_english(self):
        self.assertEqual(i18n.files_plural(1, "en"), "1 file")
        self.assertEqual(i18n.files_plural(3, "en"), "3 files")

    def test_polish(self):
        self.assertEqual(i18n.files_plural(1, "pl"), "1 plik")
        self.assertEqual(i18n.files_plural(3, "pl"), "3 pliki")
        self.assertEqual(i18n.files_plural(12, "pl"), "12 plików")
        self.assertEqual(i18n.files_plural(22, "pl"), "22 pliki")
        self.assertEqual(i18n.files_plural(25, "pl"), "25 plików")

    def test_translator_uses_its_language(self):
        self.assertEqual(i18n.Translator("pl").files(3), "3 pliki")
        self.assertEqual(i18n.Translator("en").files(3), "3 files")


if __name__ == "__main__":
    unittest.main(verbosity=2)
