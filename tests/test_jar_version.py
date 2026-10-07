#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wersja jara i reguła "zastąpiony przez nowszy oryginał"."""

import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pzupdater as pz


def make_jar(path, version, manifest=True):
    """Minimalny jar z manifestem takim, jak w prawdziwym ZombieBuddy."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("me/zed_0xff/zombie_buddy/Main.class", b"\xca\xfe\xba\xbe")
        if manifest:
            body = "Manifest-Version: 1.0\r\n"
            if version is not None:
                body += "Implementation-Version: %s\r\n" % version
            z.writestr("META-INF/MANIFEST.MF", body + "\r\n")
    return path


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pzupd_ver_")
        pz.JAR_VERSION_CACHE.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        pz.JAR_VERSION_CACHE.clear()

    def p(self, *parts):
        return os.path.join(self.tmp, *parts)


class TestJarVersion(TempCase):
    def test_reads_the_version_from_the_manifest(self):
        jar = make_jar(self.p("a.jar"), "2.3.4")
        self.assertEqual(pz.jar_version(jar), "2.3.4")

    def test_missing_file(self):
        self.assertIsNone(pz.jar_version(self.p("nie-ma.jar")))

    def test_not_a_jar(self):
        path = self.p("fake.jar")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"to nie jest zip")
        self.assertIsNone(pz.jar_version(path))

    def test_jar_without_manifest(self):
        self.assertIsNone(pz.jar_version(make_jar(self.p("b.jar"), "2.3.4", manifest=False)))

    def test_manifest_without_the_attribute(self):
        self.assertIsNone(pz.jar_version(make_jar(self.p("c.jar"), None)))

    def test_replacing_the_jar_drops_the_cached_version(self):
        """Po podmianie pliku (inny rozmiar/czas) wersja musi być odczytana na nowo."""
        jar = make_jar(self.p("d.jar"), "2.3.4")
        self.assertEqual(pz.jar_version(jar), "2.3.4")
        make_jar(jar, "2.3.5-longer-value")
        self.assertEqual(pz.jar_version(jar), "2.3.5-longer-value")


class TestSupersededByVersion(TempCase):
    def test_the_same_version_does_not_replace_the_jar(self):
        """Autor moda pisze wprost: ta sama wersja oryginału go nie zastępuje."""
        self.assertFalse(pz.superseded_by_version("2.3.4", "2.3.4"))

    def test_a_newer_release_does(self):
        self.assertTrue(pz.superseded_by_version("2.3.4", "2.3.5"))

    def test_an_older_release_does_not(self):
        self.assertFalse(pz.superseded_by_version("2.3.4", "2.3.3"))

    def test_numbers_compare_as_numbers_not_as_text(self):
        self.assertTrue(pz.superseded_by_version("2.3.9", "2.3.10"))
        self.assertFalse(pz.superseded_by_version("2.3.10", "2.3.9"))

    def test_unknown_versions_give_no_answer(self):
        for own, other in ((None, "2.3.4"), ("2.3.4", None), ("", "2.3.4"), ("brak", "2.3.4")):
            self.assertIsNone(pz.superseded_by_version(own, other), msg=(own, other))


class TestIsObsolete(TempCase):
    """Reguła z prawdziwymi wpisami rejestru i drzewem Warsztatu."""

    def setUp(self):
        super().setUp()
        self.base = next(m for m in pz.UPDATABLE_MODS if m["key"] == "zombiebuddy")
        self.fix = next(m for m in pz.UPDATABLE_MODS if m["key"] == "zombiebuddy_fix")
        self.ws_base = self.p("ws_base")
        self.ws_fix = self.p("ws_fix")
        self.steam_info = {self.base["workshop_id"]: {"time_updated": 200},
                           self.fix["workshop_id"]: {"time_updated": 100}}

    def app(self, base_version, fix_version):
        make_jar(os.path.join(self.ws_base, "mods", "ZombieBuddy", "libs", "ZombieBuddy.jar"),
                 base_version)
        make_jar(os.path.join(self.ws_fix, "mods", "ZombieBuddy_Extensions", "42.21",
                              "ZombieBuddy.jar"), fix_version)
        app = object.__new__(pz.PZUpdaterApp)
        app.paths = {"workshop": {"zombiebuddy": self.ws_base, "zombiebuddy_fix": self.ws_fix}}
        app.steam_info = self.steam_info
        return app

    def test_a_newer_official_release_makes_the_entry_pointless(self):
        self.assertTrue(self.app("2.3.5", "2.3.4")._is_obsolete(self.fix))

    def test_the_same_release_is_not_enough(self):
        """Oryginał opublikowany później, ale z tą samą wersją, niczego nie zastępuje."""
        self.assertFalse(self.app("2.3.4", "2.3.4")._is_obsolete(self.fix))

    def test_an_older_official_release_leaves_the_jar_in_place(self):
        self.assertFalse(self.app("2.3.3", "2.3.4")._is_obsolete(self.fix))

    def test_dates_are_the_fallback_when_the_jars_cannot_be_read(self):
        app = object.__new__(pz.PZUpdaterApp)
        app.paths = {"workshop": {}}
        app.steam_info = self.steam_info
        self.assertTrue(app._is_obsolete(self.fix))

    def test_a_mod_without_the_reference_is_never_obsolete(self):
        app = self.app("2.3.5", "2.3.4")
        self.assertFalse(app._is_obsolete(self.base))


if __name__ == "__main__":
    unittest.main(verbosity=2)
