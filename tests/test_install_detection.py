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

# [B42] ZombieBuddy Extensions wycięty z apki 2026-11-11 (Adam: mod jest useless).
# Wpis zostaje tu, bo pokrywa podmianę jara i wygaszanie po nowszym wydaniu.
EXTS = {
    "key": "zombiebuddy_fix",
    "name": "[B42] ZombieBuddy Extensions",
    "workshop_id": "3807686870",
    "type": "jar_replace",
    "jar_name": "ZombieBuddy.jar",
    "search_under": "mods",
    "target_rel": "ZombieBuddy.jar",
    "obsolete_if_newer_than": "3619862853",
    "obsolete_if_installed": ["3619862853"],
    "layer": True,
}

# Better Car Physics wycięty z apki 2026-11-20. Wpis zostaje jako fixture, bo
# pokrywa typ folder_copy (kopiowanie całego folderu do gry).
BCP = {
    "key": "better_car_physics",
    "name": "Better Car Physics",
    "workshop_id": "2909035179",
    "type": "folder_copy",
    "manual_dir": os.path.join("mods", "BetterCarPhysics", "manual_installation"),
    "copy_name": "zombie",
    "target_rel": "zombie",
}

def with_extensions():
    """Rejestr z wpisem Extensions na jego dawnym miejscu: wydanie, fix."""
    mods = list(pz.UPDATABLE_MODS)
    at = next(i for i, m in enumerate(mods) if m["key"] == "zombiebuddy") + 1
    return mods[:at] + [EXTS] + mods[at:]


def with_bcp():
    """Rejestr z wpisem Better Car Physics, żeby typ folder_copy był pokryty."""
    return with_extensions() + [BCP]




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
    """Better Car Physics (fixture): folder_copy — kopiuje folder 'zombie' do gry."""

    def setUp(self):
        super().setUp()
        self._registry = pz.UPDATABLE_MODS
        pz.UPDATABLE_MODS = with_bcp()
        self.ws = self.p("ws")
        self.src = self.p("ws", "mods", "BetterCarPhysics", "manual_installation",
                          "42.21.0", "zombie")
        write(os.path.join(self.src, "core", "physics", "CarController.class"),
              b"car-controller", mtime=1700000000)
        write(os.path.join(self.src, "vehicles", "BaseVehicle.class"),
              b"base-vehicle", mtime=1700000000)
        write(os.path.join(self.src, "core", "physics", "CarController$ClientControls.class"),
              b"client-controls", mtime=1700000000)
        self.mod = BCP
        self.ws_map = {"better_car_physics": self.ws}

    def tearDown(self):
        pz.UPDATABLE_MODS = self._registry
        super().tearDown()

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
        self._registry = pz.UPDATABLE_MODS
        pz.UPDATABLE_MODS = with_extensions()
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
        self.fix = EXTS
        self.ws_map = {"zombiebuddy": self.ws_base, "zombiebuddy_fix": self.ws_fix}

    def tearDown(self):
        pz.UPDATABLE_MODS = self._registry
        super().tearDown()

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
        self._registry = pz.UPDATABLE_MODS
        pz.UPDATABLE_MODS = with_bcp()
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
        pz.UPDATABLE_MODS = self._registry
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


class TestOneTimeNotices(unittest.TestCase):
    """Powiadomienie pokazuje się tylko po pierwszej instalacji i tylko raz."""

    MOD = {"key": "zombiebuddy", "notice": "zombiebuddy_launch_options"}
    OK = [("ZombieBuddy", True, "copied")]
    FAIL = [("ZombieBuddy", False, "boom")]

    def test_a_first_install_raises_it(self):
        names = pz.notices_to_show([self.MOD], self.OK, {"zombiebuddy": "install"}, {})
        self.assertEqual(names, ["zombiebuddy_launch_options"])

    def test_an_update_stays_quiet(self):
        names = pz.notices_to_show([self.MOD], self.OK, {"zombiebuddy": "update"}, {})
        self.assertEqual(names, [])

    def test_a_failed_install_stays_quiet(self):
        names = pz.notices_to_show([self.MOD], self.FAIL, {"zombiebuddy": "install"}, {})
        self.assertEqual(names, [])

    def test_an_already_shown_notice_is_not_repeated(self):
        shown = {"zombiebuddy_launch_options": True}
        names = pz.notices_to_show([self.MOD], self.OK, {"zombiebuddy": "install"}, shown)
        self.assertEqual(names, [])

    def test_a_mod_without_a_notice_raises_nothing(self):
        mod = {"key": "tempo_patches"}
        names = pz.notices_to_show([mod], [("Tempo", True, "copied")],
                                   {"tempo_patches": "install"}, {})
        self.assertEqual(names, [])

    def test_zombiebuddy_carries_the_launch_option_notice(self):
        mod = next(m for m in pz.UPDATABLE_MODS if m["key"] == "zombiebuddy")
        self.assertEqual(mod["notice"], "zombiebuddy_launch_options")

    def test_every_notice_a_mod_uses_is_known(self):
        used = {m["notice"] for m in pz.UPDATABLE_MODS if m.get("notice")}
        self.assertTrue(used)
        self.assertEqual(used - set(pz.NOTICE_KEYS), set())


class TestDeprecatedRow(unittest.TestCase):
    """Przestarzały wpis (np. fix przy zainstalowanej becie) ma wyszarzony tytuł."""

    class App:
        """Tyle aplikacji, ile trzeba, żeby zbudować stan wiersza bez okna."""

        _repair_state = pz.PZUpdaterApp._repair_state
        _repair_files = pz.PZUpdaterApp._repair_files
        _blocked_by_signature = pz.PZUpdaterApp._blocked_by_signature
        _manifests = pz.PZUpdaterApp._manifests
        _requirements = pz.PZUpdaterApp._requirements
        _files_present = pz.PZUpdaterApp._files_present
        _manual_subscribed = pz.PZUpdaterApp._manual_subscribed
        _installed_files = pz.PZUpdaterApp._installed_files

        def __init__(self, obsolete):
            self.obsolete = obsolete
            self.paths = {"workshop": {"zombiebuddy_fix": "ws"}}
            self.steam_info = {}
            self.steam_failed = set()
            self.state = {"mods": {}}
            self._repair = None

        def t(self, key, *args):
            return key

        def _mod_name(self, mod):
            return mod["name"]

        def _install_state(self, mod):
            return (pz.INSTALL_OK, True, 1)

        def _saved_ts(self, workshop_id):
            return 0

        def _is_obsolete(self, mod):
            return self.obsolete

        def _visible_mods(self):
            return list(pz.UPDATABLE_MODS)

    FIX = EXTS

    def test_an_obsolete_row_comes_out_muted(self):
        info = pz.PZUpdaterApp._status_info(self.App(True), self.FIX)
        self.assertEqual(info["tag"], "old")
        self.assertTrue(info["muted"])

    def test_a_row_left_alone_is_not_muted(self):
        info = pz.PZUpdaterApp._status_info(self.App(False), self.FIX)
        self.assertFalse(info["muted"])


def headless_app(game, ws_map, state=None):
    """Aplikacja bez okna: prawdziwe metody liczenia stanu, atrapa tylko reszty."""
    class App:
        _install_state = pz.PZUpdaterApp._install_state
        _installed_files = pz.PZUpdaterApp._installed_files
        _jar_version_of = pz.PZUpdaterApp._jar_version_of
        _mod_by_workshop_id = pz.PZUpdaterApp._mod_by_workshop_id
        _is_obsolete = pz.PZUpdaterApp._is_obsolete
        _is_collapsed = pz.PZUpdaterApp._is_collapsed
        _visible_mods = pz.PZUpdaterApp._visible_mods
        _status_info = pz.PZUpdaterApp._status_info
        _pending_actions = pz.PZUpdaterApp._pending_actions
        _installed_for_update = pz.PZUpdaterApp._installed_for_update
        _files_note = pz.PZUpdaterApp._files_note
        _mod_name = pz.PZUpdaterApp._mod_name
        _saved_ts = pz.PZUpdaterApp._saved_ts
        _requirements = pz.PZUpdaterApp._requirements
        _files_present = pz.PZUpdaterApp._files_present
        _manual_subscribed = pz.PZUpdaterApp._manual_subscribed
        _repair_state = pz.PZUpdaterApp._repair_state
        _repair_files = pz.PZUpdaterApp._repair_files
        _blocked_by_signature = pz.PZUpdaterApp._blocked_by_signature
        _manifests = pz.PZUpdaterApp._manifests

        def __init__(self):
            self.paths = {"game_dir": game, "workshop": ws_map}
            self.steam_info = {}
            self.steam_failed = set()
            self.state = state or {"mods": {}}
            self._sources = pz.accepted_sources(pz.UPDATABLE_MODS, ws_map)
            self._repair = None

        def t(self, key, *args):
            return key

    return App()


class TestObsoleteIfInstalled(TempCase):
    """Wpis gaśnie, gdy mod, który go zastępuje, leży już w folderze gry."""

    def setUp(self):
        super().setUp()
        self._registry = pz.UPDATABLE_MODS
        pz.UPDATABLE_MODS = with_extensions()
        self.base = next(m for m in pz.UPDATABLE_MODS if m["key"] == "zombiebuddy")
        self.ws = self.p("ws")
        for fn in ("ZombieBuddy.jar", "zbNative.dll"):
            write(os.path.join(self.ws, "mods", "ZombieBuddy", "libs", fn),
                  b"zb-" + fn.encode())

    def tearDown(self):
        pz.UPDATABLE_MODS = self._registry
        super().tearDown()

    def test_the_fix_steps_aside_once_the_release_is_in_the_game(self):
        for fn in ("ZombieBuddy.jar", "zbNative.dll"):
            write(os.path.join(self.game, fn),
                  b"zb-" + fn.encode())
        app = headless_app(self.game, {"zombiebuddy": self.ws})
        self.assertTrue(app._is_obsolete(EXTS))

    def test_an_empty_game_folder_leaves_the_fix_alone(self):
        app = headless_app(self.game, {"zombiebuddy": self.ws})
        self.assertFalse(app._is_obsolete(EXTS))


class TestRegistryRelations(unittest.TestCase):
    """Pola wiążące wpisy muszą wskazywać na istniejące mody i nie na siebie."""

    def ids(self):
        return {m["workshop_id"] for m in pz.UPDATABLE_MODS}

    def targets(self, mod, field):
        value = mod.get(field) or []
        return [value] if isinstance(value, str) else list(value)

    def test_every_relation_points_at_a_registered_entry(self):
        for mod in pz.UPDATABLE_MODS:
            for field in ("obsolete_if_newer_than", "obsolete_if_installed"):
                for target in self.targets(mod, field):
                    self.assertIn(target, self.ids(), msg=f"{mod['key']}.{field}")


class TestReleaseKey(unittest.TestCase):
    def test_a_prerelease_sorts_below_its_own_release(self):
        self.assertLess(pz.release_key("3.0.0-beta1"), pz.release_key("3.0.0"))
        self.assertLess(pz.release_key("1.2.0-rc2"), pz.release_key("1.2.0"))

    def test_a_prerelease_of_a_higher_number_still_wins(self):
        self.assertTrue(pz.newer_version("3.0.0-beta1", "2.3.4"))
        # ...ale samo wydanie jest nowsze od swojej bety
        self.assertTrue(pz.newer_version("3.0.0", "3.0.0-beta1"))

    def test_a_later_prerelease_beats_an_earlier_one(self):
        self.assertLess(pz.release_key("3.0.0-beta1"), pz.release_key("3.0.0-beta2"))

    def test_versions_without_numbers_cannot_be_compared(self):
        self.assertIsNone(pz.newer_version("", "2.3.4"))
        self.assertIsNone(pz.newer_version("2.3.4", None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
