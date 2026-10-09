#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy wykrywania stanu modów (subskrybowany w warsztacie ≠ wgrany do gry)."""

import os
import sys
import shutil
import tempfile
import unittest
import zipfile
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n
import pzupdater as pz


def write(path, content=b"x", mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pzupd_test_")
        self.game = os.path.join(self.tmp, "game")
        os.makedirs(self.game)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def p(self, *parts):
        return os.path.join(self.tmp, *parts)


class TestFilesIdentical(TempCase):
    def test_same_content_different_mtime(self):
        old = write(self.p("a.bin"), b"hello", mtime=1000000000)
        new = write(self.p("b.bin"), b"hello", mtime=1700000000)
        self.assertTrue(pz.files_identical(old, new))

    def test_same_size_different_content(self):
        a = write(self.p("a.bin"), b"hello")
        b = write(self.p("b.bin"), b"HELLO")
        self.assertFalse(pz.files_identical(a, b))

    def test_same_size_and_same_timestamp_but_different_content(self):
        """Windows gives files written in one clock tick the same st_mtime_ns,
        so equal timestamps must not be taken as "identical"."""
        a = write(self.p("a.bin"), b"hello")
        b = write(self.p("b.bin"), b"WORLD")
        os.utime(a, ns=(1700000000000000000, 1700000000000000000))
        os.utime(b, ns=(1700000000000000000, 1700000000000000000))
        self.assertFalse(pz.files_identical(a, b))

    def test_missing_destination(self):
        a = write(self.p("a.bin"), b"hello")
        self.assertFalse(pz.files_identical(a, self.p("nie-ma.bin")))

    def test_directory_is_not_a_file(self):
        os.makedirs(self.p("dir"))
        write(self.p("dir", "f.bin"), b"hello")
        self.assertFalse(pz.files_identical(self.p("dir"), self.p("dir")))


class TestFolderCopyInstallState(TempCase):
    """Better Car Physics: folder_copy — kopiuje folder 'zombie' do gry."""

    def setUp(self):
        super().setUp()
        self.ws = self.p("ws")
        self.src = self.p("ws", "mods", "BetterCarPhysics", "manual_installation",
                          "42.21.0", "zombie")
        write(os.path.join(self.src, "core", "physics", "CarController.class"),
              b"car-controller", mtime=1700000000)
        write(os.path.join(self.src, "vehicles", "BaseVehicle.class"),
              b"base-vehicle", mtime=1700000000)
        write(os.path.join(self.src, "core", "physics", "CarController$ClientControls.class"),
              b"client-controls", mtime=1700000000)
        self.mod = next(m for m in pz.UPDATABLE_MODS if m["key"] == "better_car_physics")
        self.ws_map = {"better_car_physics": self.ws}

    def state(self):
        return pz.mod_install_state(self.mod, self.game, self.ws_map,
                                    pz.UPDATABLE_MODS)[0]

    def test_not_installed_when_folder_missing(self):
        self.assertEqual(self.state(), pz.INSTALL_MISSING)

    def test_installed_after_full_copy(self):
        shutil.copytree(self.src, os.path.join(self.game, "zombie"))
        self.assertEqual(self.state(), pz.INSTALL_OK)

    def test_installed_when_mtime_differs_but_content_matches(self):
        dst = os.path.join(self.game, "zombie")
        shutil.copytree(self.src, dst)
        for root, _dirs, files in os.walk(dst):
            for fn in files:
                os.utime(os.path.join(root, fn), (1000000000, 1000000000))
        self.assertEqual(self.state(), pz.INSTALL_OK)

    def test_partial_when_only_some_files_present(self):
        dst = os.path.join(self.game, "zombie")
        os.makedirs(os.path.join(dst, "core", "physics"))
        shutil.copy2(os.path.join(self.src, "core", "physics", "CarController.class"),
                     os.path.join(dst, "core", "physics", "CarController.class"))
        state, ok, total = pz.mod_install_state(self.mod, self.game, self.ws_map,
                                                pz.UPDATABLE_MODS)
        self.assertEqual(state, pz.INSTALL_PARTIAL)
        self.assertEqual((ok, total), (1, 3))

    def test_missing_when_stock_game_files_are_present(self):
        """Gra potrafi odtworzyć folder 'zombie' z własnego jara — pliki moda
        wciąż są nieobecne, więc mod musi zostać oznaczony jako do instalacji."""
        dst = os.path.join(self.game, "zombie", "core", "physics")
        write(os.path.join(dst, "CarController.class"), b"STOCK-CONTENT-X")
        write(os.path.join(self.game, "zombie", "vehicles", "BaseVehicle.class"), b"STOCK")
        self.assertEqual(self.state(), pz.INSTALL_MISSING)


class TestFilesCopyWithAlternateSource(TempCase):
    """ZombieBuddy.jar jest w grze z moda podstawowego ALBO z Extensions."""

    def setUp(self):
        super().setUp()
        self.ws_base = self.p("ws_base")
        self.ws_fix = self.p("ws_fix")
        self.base_jar = write(
            os.path.join(self.ws_base, "mods", "ZombieBuddy", "libs", "ZombieBuddy.jar"),
            b"BASE-JAR", mtime=1700000000)
        write(os.path.join(self.ws_base, "mods", "ZombieBuddy", "libs", "zbNative.dll"),
              b"NATIVE", mtime=1700000000)
        # Real layout of workshop 3807686870 since the author renamed the mod
        # from "Temporary Fix for ZombieBuddy" to "[B42] ZombieBuddy Extensions".
        self.fix_jar = write(
            os.path.join(self.ws_fix, "mods", "ZombieBuddy_Extensions",
                         "42.21", "ZombieBuddy.jar"),
            b"FIX-JAR", mtime=1700000000)
        self.base = next(m for m in pz.UPDATABLE_MODS if m["key"] == "zombiebuddy")
        self.fix = next(m for m in pz.UPDATABLE_MODS if m["key"] == "zombiebuddy_fix")
        self.ws_map = {"zombiebuddy": self.ws_base, "zombiebuddy_fix": self.ws_fix}

    def test_sources_include_both_jars(self):
        sources = pz.accepted_sources(pz.UPDATABLE_MODS, self.ws_map)
        jar_sources = sources["ZombieBuddy.jar"]
        self.assertEqual(len(jar_sources), 2)
        # kolejnosc: oryginal (0) przed fixem (1) — fix nadpisuje jar oryginalu
        base_idx = pz.UPDATABLE_MODS.index(self.base)
        fix_idx = pz.UPDATABLE_MODS.index(self.fix)
        self.assertLess(base_idx, fix_idx)

    def test_not_installed_when_nothing_copied(self):
        state = pz.mod_install_state(self.base, self.game, self.ws_map, pz.UPDATABLE_MODS)[0]
        self.assertEqual(state, pz.INSTALL_MISSING)

    def test_installed_from_base_mod(self):
        shutil.copy2(self.base_jar, self.game)
        shutil.copy2(os.path.join(self.ws_base, "mods", "ZombieBuddy", "libs", "zbNative.dll"),
                     self.game)
        state = pz.mod_install_state(self.base, self.game, self.ws_map, pz.UPDATABLE_MODS)[0]
        self.assertEqual(state, pz.INSTALL_OK)

    def test_installed_when_jar_comes_from_fix(self):
        """Fix nadpisuje jar — mod podstawowy nadal jest wgrany (fix jest nowszy)."""
        shutil.copy2(self.fix_jar, self.game)
        shutil.copy2(os.path.join(self.ws_base, "mods", "ZombieBuddy", "libs", "zbNative.dll"),
                     self.game)
        state = pz.mod_install_state(self.base, self.game, self.ws_map, pz.UPDATABLE_MODS)[0]
        self.assertEqual(state, pz.INSTALL_OK)

    def test_fix_is_not_satisfied_by_base_jar(self):
        """Tolerancja źródeł jest jednokierunkowa: sam jar oryginału nie znaczy,
        że fix jest nałożony (inaczej fix nigdy nie dałby się doinstalować)."""
        shutil.copy2(self.base_jar, self.game)
        shutil.copy2(os.path.join(self.ws_base, "mods", "ZombieBuddy", "libs", "zbNative.dll"),
                     self.game)
        state = pz.mod_install_state(self.fix, self.game, self.ws_map, pz.UPDATABLE_MODS)[0]
        self.assertEqual(state, pz.INSTALL_MISSING)

    def test_jar_replace_state(self):
        state = pz.mod_install_state(self.fix, self.game, self.ws_map, pz.UPDATABLE_MODS)[0]
        self.assertEqual(state, pz.INSTALL_MISSING)
        shutil.copy2(self.fix_jar, self.game)
        state = pz.mod_install_state(self.fix, self.game, self.ws_map, pz.UPDATABLE_MODS)[0]
        self.assertEqual(state, pz.INSTALL_OK)


class TestRealRegistry(TempCase):
    """Buduje drzewa dla prawdziwej konfiguracji UPDATABLE_MODS."""

    def setUp(self):
        super().setUp()
        self.ws_map = {}
        for mod in pz.UPDATABLE_MODS:
            ws = self.p("content", mod["workshop_id"])
            os.makedirs(ws, exist_ok=True)
            self.ws_map[mod["key"]] = ws
        # Mody kompilowane pod build gry (class_patch) potrzebują version.txt i rewizji
        # z projectzomboid.jar, inaczej aplikacja słusznie nic nie instaluje.
        self._env = os.environ.get("USERPROFILE")
        os.environ["USERPROFILE"] = self.p("profile")
        write(os.path.join(self.p("profile"), "Zomboid", "version.txt"),
              b"42.21.0 4a0e9546ec\nrevision=4a0e9546ec pzbullet=1.0.0.28\n")
        with zipfile.ZipFile(os.path.join(self.game, "projectzomboid.jar"), "w") as z:
            z.writestr("zombie/GitVersion.class", b"\xca\xfe\xba\xbe4a0e9546ec")
        pz.GAME_BUILD_CACHE.clear()
        # zombiebuddy
        base = self.ws_map["zombiebuddy"]
        for fn in ("ZombieBuddy.jar", "zbNative.dll"):
            write(os.path.join(base, "mods", "ZombieBuddy", "libs", fn), fn.encode())
        # zombiebuddy_fix (workshop 3807686870, "[B42] ZombieBuddy Extensions")
        write(os.path.join(self.ws_map["zombiebuddy_fix"], "mods",
                           "ZombieBuddy_Extensions", "42.21", "ZombieBuddy.jar"),
              b"FIX")
        # tempo_patches — paczka klas dla builda 42.21.0
        tempo = os.path.join(self.ws_map["tempo_patches"], "mods", "Tempo_PerfKit",
                             "manual_installation", "42.21.0", "zombie")
        for rel in ("iso/IsoChunkMap.class", "iso/IsoWorld.class",
                    "core/PerformanceSettings.class"):
            write(os.path.join(tempo, *rel.split("/")), rel.encode())
        # better_car_physics — kilka wersji, kopiowana ma być najnowsza
        manual = os.path.join(self.ws_map["better_car_physics"], "mods",
                              "BetterCarPhysics", "manual_installation")
        write(os.path.join(manual, "42.20.4", "zombie", "core", "Old.class"), b"old")
        write(os.path.join(manual, "42.21.0", "zombie", "core", "physics", "CarController.class"),
              b"new-car")
        write(os.path.join(manual, "42.21.0", "zombie", "vehicles", "BaseVehicle.class"),
              b"new-base")

    def tearDown(self):
        if self._env is None:
            os.environ.pop("USERPROFILE", None)
        else:
            os.environ["USERPROFILE"] = self._env
        pz.GAME_BUILD_CACHE.clear()
        super().tearDown()

    def test_unknown_without_workshop(self):
        state = pz.mod_install_state(pz.UPDATABLE_MODS[0], self.game, {}, pz.UPDATABLE_MODS)[0]
        self.assertEqual(state, pz.INSTALL_UNKNOWN)

    def test_better_car_physics_installs_newest_version(self):
        mod = next(m for m in pz.UPDATABLE_MODS if m["key"] == "better_car_physics")
        targets = pz.mod_targets(mod, self.ws_map["better_car_physics"])
        rel, kind, src = targets[0]
        self.assertEqual((rel, kind), ("zombie", "dir"))
        self.assertIn("42.21.0", src)
        self.assertNotIn("42.20.4", src)

    def test_all_mods_missing_before_install_and_ok_after(self):
        """Symulacja pełnej instalacji: każdy mod przechodzi missing -> ok."""
        t = i18n.Translator("en")
        for mod in pz.UPDATABLE_MODS:
            self.assertEqual(
                pz.mod_install_state(mod, self.game, self.ws_map, pz.UPDATABLE_MODS)[0],
                pz.INSTALL_MISSING, msg=mod["key"])
        for mod in pz.UPDATABLE_MODS:
            handler = pz.ACTION_HANDLERS[mod["type"]]
            ok, msg, _meta = handler(mod, self.game, self.ws_map[mod["key"]], t)
            self.assertTrue(ok, msg=msg)
        for mod in pz.UPDATABLE_MODS:
            self.assertEqual(
                pz.mod_install_state(mod, self.game, self.ws_map, pz.UPDATABLE_MODS)[0],
                pz.INSTALL_OK, msg=mod["key"])

    def test_deleting_folder_makes_mod_uninstalled_again(self):
        """Scenariusz zgłoszony przez użytkownika: usunięcie folderu z gry."""
        mod = next(m for m in pz.UPDATABLE_MODS if m["key"] == "better_car_physics")
        ws = self.ws_map[mod["key"]]
        pz.update_folder_copy(mod, self.game, ws, i18n.Translator("en"))
        self.assertEqual(pz.mod_install_state(mod, self.game, self.ws_map,
                                              pz.UPDATABLE_MODS)[0], pz.INSTALL_OK)
        shutil.rmtree(os.path.join(self.game, "zombie"))
        self.assertEqual(pz.mod_install_state(mod, self.game, self.ws_map,
                                              pz.UPDATABLE_MODS)[0], pz.INSTALL_MISSING)


class TestPlural(unittest.TestCase):
    def test_plurals(self):
        self.assertEqual(i18n.files_plural(1, "pl"), "1 plik")
        self.assertEqual(i18n.files_plural(3, "pl"), "3 pliki")
        self.assertEqual(i18n.files_plural(12, "pl"), "12 plików")
        self.assertEqual(i18n.files_plural(22, "pl"), "22 pliki")
        self.assertEqual(i18n.files_plural(25, "pl"), "25 plików")


class TestActionHandlerSignatures(unittest.TestCase):
    """Każdy handler dostaje od workera (mod, game, ws, t, prev), nie cztery argumenty."""

    def test_every_handler_accepts_prev_argument(self):
        for mod_type, handler in pz.ACTION_HANDLERS.items():
            with self.subTest(mod_type=mod_type):
                inspect.signature(handler).bind("m", "game", "ws", "t", {})
                # prev musi mieć domyślną wartość, by stare wywołania 4-arg działały
                params = inspect.signature(handler).parameters
                prev = params["prev"]
                self.assertIs(prev.default, None, msg=mod_type)


if __name__ == "__main__":
    unittest.main(verbosity=2)
