#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Podpisany jar gry: luźne klasy w folderze gry blokują uruchomienie (42.22+)."""

import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n
import pzupdater as pz

# Ścieżki klas w prawdziwym jarze, w oryginalnej wielkości liter
JAR_CLASSES = (
    "zombie/iso/IsoWorld.class",
    "zombie/iso/IsoChunkMap.class",
    "zombie/core/PerformanceSettings.class",
    "zombie/vehicles/BaseVehicle.class",
    "zombie/core/physics/CarController.class",
    "org/lwjgl/glfw/GLFW.class",
)

# To, co Tempo i Better Car Physics kopiują do folderu gry
STRAYS = (
    "zombie/iso/IsoWorld.class",
    "zombie/iso/IsoChunkMap.class",
    "zombie/core/PerformanceSettings.class",
    "zombie/vehicles/BaseVehicle.class",
    "zombie/core/physics/CarController.class",
)


def write(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


def make_jar(path, classes=JAR_CLASSES, signed=False, revision="3d39148846"):
    """Jar gry: klasy, wersja w GitVersion.class i, opcjonalnie, podpis 42.22+."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name in classes:
            z.writestr(name, b"\xca\xfe\xba\xbe")
        z.writestr("zombie/GitVersion.class", b"\xca\xfe\xba\xbe" + revision.encode())
        if signed:
            z.writestr("META-INF/PROJECTZ.SF", b"signature")
            z.writestr("META-INF/PROJECTZ.EC", b"block")
    return path


class RepairCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pzupd_repair_")
        self.game = os.path.join(self.tmp, "game")
        os.makedirs(self.game)
        self.profile = os.path.join(self.tmp, "profile")
        self._appdata = os.environ.get("APPDATA")
        self._userprofile = os.environ.get("USERPROFILE")
        os.environ["APPDATA"] = os.path.join(self.tmp, "appdata")
        os.environ["USERPROFILE"] = self.profile
        pz.JAR_INFO_CACHE.clear()
        pz.GAME_BUILD_CACHE.clear()
        self.t = i18n.Translator("pl")

    def tearDown(self):
        for name, value in (("APPDATA", self._appdata), ("USERPROFILE", self._userprofile)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        pz.JAR_INFO_CACHE.clear()
        pz.GAME_BUILD_CACHE.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def jar(self, signed=False):
        return make_jar(os.path.join(self.game, "projectzomboid.jar"), signed=signed)

    def stray(self, rel, content=b"patched"):
        return write(os.path.join(self.game, *rel.split("/")), content)

    def game_has(self, rel):
        return os.path.isfile(os.path.join(self.game, *rel.split("/")))

    def workshop(self):
        """Foldery warsztatu obu modów: Tempo trzy klasy, BCP dwie."""
        tempo_root = os.path.join(self.tmp, "ws_tempo")
        bcp_root = os.path.join(self.tmp, "ws_bcp")
        tempo = os.path.join(tempo_root, "mods", "Tempo_PerfKit",
                             "manual_installation", "42.21.0", "zombie")
        bcp = os.path.join(bcp_root, "mods", "BetterCarPhysics",
                           "manual_installation", "42.14.1", "zombie")
        for rel in STRAYS[:3]:
            write(os.path.join(tempo, *rel.split("/")[1:]), b"tempo")
        for rel in STRAYS[3:]:
            write(os.path.join(bcp, *rel.split("/")[1:]), b"bcp")
        return {"tempo_patches": tempo_root, "better_car_physics": bcp_root}


class TestJarInfo(RepairCase):
    def test_reads_classes_packages_and_roots(self):
        self.jar()
        info = pz.jar_info(self.game)
        self.assertFalse(info["signed"])
        self.assertIn("zombie/iso/isoworld.class", info["classes"])
        self.assertIn("zombie/iso", info["packages"])
        self.assertEqual(info["top"], {"zombie", "org"})

    def test_spots_the_signature_of_the_422_build(self):
        self.jar(signed=True)
        self.assertTrue(pz.jar_info(self.game)["signed"])

    def test_no_jar_no_info(self):
        self.assertIsNone(pz.jar_info(self.game))
        self.assertIsNone(pz.jar_info(None))


class TestClashingClasses(RepairCase):
    def test_class_overriding_one_in_the_jar(self):
        self.jar()
        self.stray("zombie/iso/IsoWorld.class")
        self.assertEqual(pz.clashing_classes(self.game), ["zombie/iso/IsoWorld.class"])

    def test_class_in_a_package_of_a_signed_jar(self):
        """Nawet inna klasa w paczce z jara wywala całą paczkę."""
        self.jar(signed=True)
        self.stray("zombie/iso/IsoGridSquare.class")
        self.assertEqual(pz.clashing_classes(self.game),
                         ["zombie/iso/IsoGridSquare.class"])

    def test_the_same_class_is_fine_next_to_an_unsigned_jar(self):
        """Stary, niepodpisany build pozwalał nadpisywać klasy - tak było zawsze."""
        self.jar()
        self.stray("zombie/iso/IsoGridSquare.class")
        self.assertEqual(pz.clashing_classes(self.game), [])

    def test_own_package_is_never_a_clash(self):
        self.jar(signed=True)
        self.stray("mymod/Client.class")
        self.assertEqual(pz.clashing_classes(self.game), [])

    def test_jar_folders_are_not_scanned(self):
        """jre64 i media mają własne .class, ale nie należą do classpath gry."""
        self.jar(signed=True)
        self.stray("jre64/lib/Some.class")
        self.stray("media/lua/Thing.class")
        self.assertEqual(pz.clashing_classes(self.game), [])


class TestPatchConflicts(RepairCase):
    def mod(self, mods_key="tempo_patches"):
        return next(m for m in pz.UPDATABLE_MODS if m["key"] == mods_key)

    def test_folder_of_classes_is_blocked_on_a_signed_jar(self):
        self.jar(signed=True)
        self.assertTrue(pz.patch_conflicts(self.game, self.mod()))
        self.assertTrue(pz.patch_conflicts(self.game, self.mod("better_car_physics")))

    def test_the_same_folder_is_allowed_on_an_unsigned_jar(self):
        self.jar(signed=False)
        self.assertFalse(pz.patch_conflicts(self.game, self.mod()))
        self.assertFalse(pz.patch_conflicts(self.game, self.mod("better_car_physics")))

    def test_a_mod_outside_the_game_packages_is_never_blocked(self):
        self.jar(signed=True)
        self.assertFalse(pz.patch_conflicts(self.game, {"key": "x", "copy_name": "mymod",
                                                        "target_rel": "mymod"}))
        self.assertFalse(pz.patch_conflicts(self.game, self.mod("zombiebuddy")))

    def test_no_game_folder_changes_nothing(self):
        self.assertFalse(pz.patch_conflicts(None, self.mod()))


class TestGameRepair(RepairCase):
    def test_splits_the_files_between_mods_and_unknown_ones(self):
        self.jar(signed=True)
        for rel in STRAYS:
            self.stray(rel)
        self.stray("org/lwjgl/glfw/GLFW.class")      # nikt się do tego nie przyznaje
        state = pz.game_repair(self.game, pz.UPDATABLE_MODS, self.workshop())
        self.assertTrue(state["signed"])
        self.assertEqual(sorted(state["by_mod"]["tempo_patches"]), sorted(STRAYS[:3]))
        self.assertEqual(sorted(state["by_mod"]["better_car_physics"]), sorted(STRAYS[3:]))
        self.assertEqual(state["unknown"], ["org/lwjgl/glfw/GLFW.class"])
        self.assertEqual(len(state["files"]), len(STRAYS) + 1)

    def test_a_recorded_install_names_the_owner_without_the_workshop(self):
        """Bez folderów warsztatu rozstrzyga manifest zapisany przy instalacji."""
        self.jar(signed=True)
        for rel in STRAYS[:3]:
            self.stray(rel)
        manifests = {rel: "tempo_patches" for rel in STRAYS[:3]}
        state = pz.game_repair(self.game, pz.UPDATABLE_MODS, manifests=manifests)
        self.assertEqual(sorted(state["by_mod"]["tempo_patches"]), sorted(STRAYS[:3]))

    def test_without_any_hint_the_folder_decides(self):
        """Tempo i BCP kopiują do tego samego 'zombie' - wtedy pierwszy w rejestrze."""
        self.jar(signed=True)
        self.stray(STRAYS[0])
        state = pz.game_repair(self.game, pz.UPDATABLE_MODS)
        self.assertEqual(list(state["by_mod"]), ["better_car_physics"])

    def test_nothing_to_repair_on_a_clean_folder(self):
        self.jar(signed=True)
        state = pz.game_repair(self.game, pz.UPDATABLE_MODS, self.workshop())
        self.assertEqual((state["files"], state["by_mod"], state["unknown"]), ([], {}, []))


class TestBackupTakenClasses(RepairCase):
    def test_moves_the_files_out_and_leaves_the_game_folder_clean(self):
        self.jar(signed=True)
        for rel in STRAYS:
            self.stray(rel)
        moved, kept, folder = pz.backup_taken_classes(self.game, list(STRAYS))
        self.assertEqual(len(moved), len(STRAYS))
        self.assertEqual(kept, [])
        for rel in STRAYS:
            self.assertFalse(self.game_has(rel), rel)
        self.assertFalse(os.path.isdir(os.path.join(self.game, "zombie")))
        # nic nie znika: pliki leżą w folderze aplikacji
        for rel in STRAYS:
            self.assertTrue(os.path.isfile(os.path.join(folder, *rel.split("/"))), rel)
        self.assertIn(os.path.join("PZUpdater", "removed"), folder)

    def test_keeps_a_file_that_is_already_gone_out_of_the_count(self):
        self.jar(signed=True)
        self.stray(STRAYS[0])
        moved, kept, folder = pz.backup_taken_classes(self.game,
                                                      [STRAYS[0], STRAYS[1]])
        self.assertEqual(moved, [STRAYS[0]])
        self.assertEqual(kept, [])

    def test_a_file_held_by_the_game_is_reported_not_lost(self):
        """Gra trzyma plik otwarty -> move zawodzi, plik zostaje na miejscu."""
        self.jar(signed=True)
        rel = STRAYS[0]
        path = self.stray(rel)
        original = pz.shutil.move

        def failing(*_a, **_k):
            raise OSError("file in use")

        pz.shutil.move = failing
        try:
            moved, kept, folder = pz.backup_taken_classes(self.game, [rel])
        finally:
            pz.shutil.move = original
        self.assertEqual((moved, kept, folder), ([], [rel], None))
        self.assertTrue(os.path.isfile(path))


class TestRowStatus(RepairCase):
    """Wiersz moda: blokada gry, ostrzeżenie o podpisanym jarze, ale update widoczny."""

    class App:
        _repair_state = pz.PZUpdaterApp._repair_state
        _repair_files = pz.PZUpdaterApp._repair_files
        _blocked_by_signature = pz.PZUpdaterApp._blocked_by_signature
        _manifests = pz.PZUpdaterApp._manifests
        _status_info = pz.PZUpdaterApp._status_info
        _mod_name = pz.PZUpdaterApp._mod_name
        _install_state = pz.PZUpdaterApp._install_state
        _installed_build = pz.PZUpdaterApp._installed_build
        _installed_files = pz.PZUpdaterApp._installed_files
        _prune_dead_records = pz.PZUpdaterApp._prune_dead_records
        _is_obsolete = lambda self, mod: False
        _saved_ts = lambda self, wid: 0
        _log = lambda self, *args: None

        def __init__(self, game, workshop):
            self.paths = {"game_dir": game, "workshop": workshop}
            self.steam_info = {}
            self.state = {"mods": {}}
            self._sources = pz.accepted_sources(pz.UPDATABLE_MODS, workshop)
            self._repair = None

        def t(self, key, *args):
            return key

        def _visible_mods(self):
            return list(pz.UPDATABLE_MODS)

    def mod(self, key):
        return next(m for m in pz.UPDATABLE_MODS if m["key"] == key)

    def build_for(self, build="42.22.2", revision="3d39148846"):
        write(os.path.join(self.profile, "Zomboid", "version.txt"),
              f"{build} {revision}\nrevision={revision}\n".encode())
        pz.GAME_BUILD_CACHE.clear()

    def tempo_for(self, build="42.22.2"):
        """Paczka Tempo zrobiona pod ten build - 'czeka na swój moment'."""
        ws = os.path.join(self.tmp, "ws_tempo_now")
        src = os.path.join(ws, "mods", "Tempo_PerfKit", "manual_installation",
                           build, "zombie")
        for rel in STRAYS[:3]:
            write(os.path.join(src, *rel.split("/")[1:]), b"tempo-" + build.encode())
        return {"tempo_patches": ws}

    def test_files_in_the_game_folder_make_the_row_a_repair(self):
        self.jar(signed=True)
        for rel in STRAYS[:3]:
            self.stray(rel)
        app = self.App(self.game, self.workshop())
        info = pz.PZUpdaterApp._status_info(app, self.mod("tempo_patches"))
        self.assertEqual(info["pending"], "repair")
        self.assertEqual(info["status"], "status.repair_needed")
        self.assertEqual(info["tag"], "err")
        self.assertEqual(info["repair"], 3)
        self.assertFalse(info["muted"])

    def test_a_patch_for_this_build_is_offered_even_with_a_signed_jar(self):
        """Sedno: autor wydał paczkę pod 42.22.2 -> jest do zainstalowania."""
        self.jar(signed=True)
        self.build_for("42.22.2")
        app = self.App(self.game, self.tempo_for("42.22.2"))
        info = pz.PZUpdaterApp._status_info(app, self.mod("tempo_patches"))
        self.assertEqual(info["pending"], "install")
        self.assertEqual(info["status"], "status.subscribed_not_installed")
        # Paczka zrobiona pod ten build gry: autor zdążył przed nami, więc wiersz
        # jest zwykły - bez ostrzeżenia i bez pomarańczowego przycisku.
        self.assertFalse(info["signed_warning"])
        self.assertIsNone(info["files_note"])
        # wyszarzony tytuł (jak każdy niezainstalowany), ale przycisk jest
        self.assertTrue(info["muted"])

    def test_no_patch_for_this_build_waits_instead_of_nagging(self):
        self.jar(signed=True)
        self.build_for("42.22.2")
        app = self.App(self.game, self.tempo_for("42.21.0"))
        info = pz.PZUpdaterApp._status_info(app, self.mod("tempo_patches"))
        self.assertEqual(info["status"], "status.no_patch_build")
        self.assertIsNone(info["pending"])
        self.assertTrue(info["signed_warning"])

    def test_a_mod_that_is_not_installed_still_reports_a_new_version(self):
        """Autor wydał paczkę pod ten build, ale plików moda nie ma w grze.

        Wiersz mówił wtedy tylko "Zasubskrybowany, nie zainstalowany", więc update
        moda przechodził bez żadnej informacji — zostawało samo ostrzeżenie.
        """
        self.jar(signed=True)
        self.build_for("42.22.2")
        app = self.App(self.game, self.tempo_for("42.22.2"))
        app.steam_info["3736629791"] = {"title": "Tempo", "time_updated": 1793000000}
        app._saved_ts = lambda wid: 1790775512
        info = pz.PZUpdaterApp._status_info(app, self.mod("tempo_patches"))
        self.assertEqual(info["status"], "status.new_version")
        self.assertEqual(info["tag"], "new")
        self.assertEqual(info["pending"], "install")
        self.assertFalse(info["muted"])          # nie wyszarzać: to jest news
        self.assertFalse(info["signed_warning"])  # paczka pod ten build = bez ostrzeżenia

    def test_a_first_subscription_is_not_a_new_version(self):
        """Nic jeszcze nie było wgrane -> nie ma czego porównać, wiersz jest szary."""
        self.jar(signed=True)
        self.build_for("42.22.2")
        app = self.App(self.game, self.tempo_for("42.22.2"))
        app.steam_info["3736629791"] = {"title": "Tempo", "time_updated": 1793000000}
        info = pz.PZUpdaterApp._status_info(app, self.mod("tempo_patches"))
        self.assertEqual(info["status"], "status.subscribed_not_installed")
        self.assertTrue(info["muted"])

    def test_a_folder_published_for_this_game_clears_the_warning(self):
        """Better Car Physics 42.22.0 przy grze 42.22.2: autor zdążył, wiersz zwykły."""
        self.jar(signed=True)
        self.build_for("42.22.2")
        app = self.App(self.game, self.bcp_versions("42.21.0", "42.22.0"))
        info = pz.PZUpdaterApp._status_info(app, self.mod("better_car_physics"))
        self.assertFalse(info["signed_warning"])
        self.assertIsNone(info["files_note"])
        self.assertEqual(info["pending"], "install")

    def test_a_folder_from_an_older_release_keeps_the_warning(self):
        self.jar(signed=True)
        self.build_for("42.22.2")
        app = self.App(self.game, self.bcp_versions("42.21.0"))
        info = pz.PZUpdaterApp._status_info(app, self.mod("better_car_physics"))
        self.assertTrue(info["signed_warning"])
        self.assertEqual(info["files_note"], "detail.signed_jar")

    def test_files_made_for_a_newer_game_keep_the_warning(self):
        self.jar(signed=True)
        self.build_for("42.23.1")
        app = self.App(self.game, self.bcp_versions("42.21.0", "42.22.0"))
        info = pz.PZUpdaterApp._status_info(app, self.mod("better_car_physics"))
        self.assertTrue(info["signed_warning"])

    def bcp_versions(self, *versions):
        """Folder Better Car Physics z jedną paczką na wersję gry."""
        ws = os.path.join(self.tmp, "ws_bcp_" + "_".join(versions))
        for version in versions:
            src = os.path.join(ws, "mods", "BetterCarPhysics",
                               "manual_installation", version, "zombie")
            for rel in STRAYS[3:]:
                write(os.path.join(src, *rel.split("/")[1:]), b"bcp-" + version.encode())
        return {"better_car_physics": ws}

    def test_an_unsigned_jar_has_no_warning_at_all(self):
        self.jar(signed=False)
        self.build_for("42.22.2")
        app = self.App(self.game, self.tempo_for("42.22.2"))
        info = pz.PZUpdaterApp._status_info(app, self.mod("tempo_patches"))
        self.assertFalse(info["signed_warning"])
        self.assertEqual(info["pending"], "install")

    # -- the record of an install has to match the disk -----------------------

    def record(self, app, rel):
        """Zapis instalacji, jaki aplikacja zostawia po wgraniu paczki."""
        mod = self.mod("tempo_patches")
        app.state["mods"][mod["workshop_id"]] = {"files": {rel: "abc"}}
        return mod

    def test_a_record_without_files_offers_no_uninstall(self):
        """Pliki wycofane ręcznie albo przez naprawę -> nie ma czego odinstalować."""
        app = self.App(self.game, self.workshop())
        mod = self.record(app, "zombie/iso/IsoWorld.class")
        self.assertEqual(pz.PZUpdaterApp._installed_files(app, mod), {})

    def test_a_record_with_files_on_disk_offers_the_uninstall(self):
        app = self.App(self.game, self.workshop())
        mod = self.record(app, "zombie/iso/IsoWorld.class")
        self.stray("zombie/iso/IsoWorld.class")
        self.assertEqual(list(pz.PZUpdaterApp._installed_files(app, mod)),
                         ["zombie/iso/IsoWorld.class"])

    def test_leftover_files_from_an_older_game_are_offered_for_removal(self):
        """Gra się zaktualizowała, paczki pod nowy build nie ma, a pliki zostały."""
        self.jar(signed=False)
        self.build_for("42.22.2")
        app = self.App(self.game, self.tempo_for("42.21.0"))
        mod = self.record(app, "extras/perf/Boost.class")
        self.stray("extras/perf/Boost.class")
        info = pz.PZUpdaterApp._status_info(app, mod)
        self.assertEqual(info["status"], "status.stale_files")
        self.assertEqual(info["pending"], "remove")
        self.assertEqual(info["files_note"], "detail.stale_files")
        self.assertFalse(info["muted"])

    def test_leftover_classes_that_clash_with_the_new_jar_ask_for_a_repair(self):
        """Ten sam przypadek, ale klasy wchodzą w pakiet gry: gra w ogóle nie wstanie."""
        self.jar(signed=True)
        self.build_for("42.22.2")
        app = self.App(self.game, self.tempo_for("42.21.0"))
        mod = self.record(app, "zombie/iso/IsoWorld.class")
        self.stray("zombie/iso/IsoWorld.class")
        info = pz.PZUpdaterApp._status_info(app, mod)
        self.assertEqual(info["status"], "status.repair_needed")
        self.assertEqual(info["pending"], "repair")
        self.assertEqual(info["repair"], 1)

    def test_a_dead_record_is_dropped_from_the_state(self):
        app = self.App(self.game, self.workshop())
        mod = self.record(app, "zombie/iso/IsoWorld.class")
        saved = []
        original = pz.save_state
        pz.save_state = saved.append
        self.addCleanup(setattr, pz, "save_state", original)
        pz.PZUpdaterApp._prune_dead_records(app)
        self.assertNotIn(mod["workshop_id"], app.state["mods"])
        self.assertEqual(len(saved), 1)

    def test_a_live_record_survives_the_prune(self):
        app = self.App(self.game, self.workshop())
        mod = self.record(app, "zombie/iso/IsoWorld.class")
        self.stray("zombie/iso/IsoWorld.class")
        original = pz.save_state
        pz.save_state = lambda state: self.fail("nic nie miało być zapisywane")
        self.addCleanup(setattr, pz, "save_state", original)
        pz.PZUpdaterApp._prune_dead_records(app)
        self.assertIn(mod["workshop_id"], app.state["mods"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
