#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Odinstalowanie moda: aplikacja musi wiedzieć, które pliki sama wrzuciła."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n
import pzupdater as pz

# [B42] ZombieBuddy Extensions wycięty z apki 2026-11-11 (Adam: mod jest useless).
# Wpis zostaje tu, bo pokrywa podmianę jara, warstwę i wygaszanie po nowszym wydaniu.
EXTS = {
    "key": "zombiebuddy_fix",
    "name": "[B42] ZombieBuddy Extensions",
    "workshop_id": "3807686870",
    "type": "jar_replace",
    "jar_name": "ZombieBuddy.jar",
    "search_under": "mods",
    "target_rel": "ZombieBuddy.jar",
    "obsolete_if_newer_than": "3619862853",
    "obsolete_if_installed": ["3812624292"],
    "layer": True,
    "alternative_to": "3619862853",
}


BCP_CLASSES = (
    "core/physics/CarController.class",
    "core/physics/CarController$ClientControls.class",
    "vehicles/BaseVehicle.class",
)


def write(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


def read(path):
    with open(path, "rb") as f:
        return f.read()


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pzupd_remove_")
        self.game = os.path.join(self.tmp, "game")
        os.makedirs(self.game)
        self.t = i18n.Translator("pl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mod(self, key):
        if key == EXTS["key"]:      # wpis wycięty z rejestru, ale typ dalej działa
            return EXTS
        return next(m for m in pz.UPDATABLE_MODS if m["key"] == key)

    def game_path(self, rel):
        return os.path.join(self.game, *rel.split("/"))

    def game_has(self, rel):
        return os.path.isfile(self.game_path(rel))


class TestFolderCopyRecord(TempCase):
    """Better Car Physics: kopiowany folder ma się dać wycofać."""

    def setUp(self):
        super().setUp()
        self.mod = self.mod("better_car_physics")
        self.ws = os.path.join(self.tmp, "ws")
        self.src = os.path.join(self.ws, "mods", "BetterCarPhysics",
                                "manual_installation", "42.22.0", "zombie")
        for rel in BCP_CLASSES:
            write(os.path.join(self.src, *rel.split("/")), b"bcp-" + rel.encode())

    def test_the_install_records_every_file_it_wrote(self):
        ok, _msg, meta = pz.update_folder_copy(self.mod, self.game, self.ws, self.t)
        self.assertTrue(ok)
        self.assertEqual(sorted(meta["files"]),
                         sorted("zombie/" + rel for rel in BCP_CLASSES))
        for rel, digest in meta["files"].items():
            self.assertEqual(digest, pz.file_sha256(self.game_path(rel)))

    def test_the_record_takes_the_files_and_their_folders_back(self):
        _ok, _msg, meta = pz.update_folder_copy(self.mod, self.game, self.ws, self.t)
        ok, _msg, res = pz.remove_mod_files(self.game, meta["files"], self.t)
        self.assertTrue(ok)
        self.assertEqual(len(res["removed"]), len(BCP_CLASSES))
        for rel in BCP_CLASSES:
            self.assertFalse(self.game_has("zombie/" + rel), rel)
        self.assertFalse(os.path.isdir(os.path.join(self.game, "zombie")))
        self.assertTrue(os.path.isdir(self.game))

    def test_a_file_changed_after_the_install_stays(self):
        _ok, _msg, meta = pz.update_folder_copy(self.mod, self.game, self.ws, self.t)
        changed = "zombie/" + BCP_CLASSES[2]
        write(self.game_path(changed), b"someone-else-wrote-this")
        ok, _msg, res = pz.remove_mod_files(self.game, meta["files"], self.t)
        self.assertTrue(ok)
        self.assertTrue(self.game_has(changed))
        self.assertEqual(res["kept"], [changed])


class TestFilesCopyRecord(TempCase):
    """ZombieBuddy: dwa pliki w korzeniu gry też mają się dać wycofać."""

    def test_the_install_records_the_copied_files(self):
        mod = self.mod("zombiebuddy")
        ws = os.path.join(self.tmp, "ws_zb")
        src = os.path.join(ws, mod["src_dir"])
        for fn in mod["files"]:
            write(os.path.join(src, fn), b"zb-" + fn.encode())
        ok, _msg, meta = pz.update_files(mod, self.game, ws, self.t)
        self.assertTrue(ok)
        self.assertEqual(sorted(meta["files"]), sorted(mod["files"]))
        ok, _msg, res = pz.remove_mod_files(self.game, meta["files"], self.t)
        self.assertTrue(ok)
        self.assertEqual(len(res["removed"]), len(mod["files"]))
        for fn in mod["files"]:
            self.assertFalse(self.game_has(fn), fn)


class TestAdoptionWithoutRecord(TempCase):
    """Instalacja sprzed zapisu: pliki moda rozpoznane po bajtach."""

    class App:
        _installed_files = pz.PZUpdaterApp._installed_files

        def __init__(self, game, workshop, state=None):
            self.paths = {"game_dir": game, "workshop": workshop}
            self.state = state or {"mods": {}}

    def setUp(self):
        super().setUp()
        self.mod = self.mod("better_car_physics")
        self.ws = os.path.join(self.tmp, "ws")
        self.old = os.path.join(self.ws, "mods", "BetterCarPhysics",
                                "manual_installation", "42.21.0", "zombie")
        self.new = os.path.join(self.ws, "mods", "BetterCarPhysics",
                                "manual_installation", "42.22.0", "zombie")
        for rel in BCP_CLASSES:
            write(os.path.join(self.old, *rel.split("/")), b"old-" + rel.encode())
            write(os.path.join(self.new, *rel.split("/")), b"new-" + rel.encode())

    def put_old_install(self):
        """To, co w grze zostało po instalacji starszej wersji moda."""
        for rel in BCP_CLASSES:
            dst = self.game_path("zombie/" + rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(self.old, *rel.split("/")), dst)

    def app(self, state=None):
        return self.App(self.game, {"better_car_physics": self.ws}, state)

    def test_files_of_an_older_version_are_recognised_as_the_mods_own(self):
        self.put_old_install()
        found = pz.adopted_files(self.mod, self.game, self.ws)
        self.assertEqual(sorted(found), sorted("zombie/" + rel for rel in BCP_CLASSES))

    def test_the_row_offers_the_uninstall_for_such_an_install(self):
        self.put_old_install()
        files = pz.PZUpdaterApp._installed_files(self.app(), self.mod)
        self.assertEqual(len(files), len(BCP_CLASSES))
        ok, _msg, res = pz.remove_mod_files(self.game, files, self.t)
        self.assertTrue(ok)
        self.assertEqual(len(res["removed"]), len(BCP_CLASSES))

    def test_a_class_the_mod_does_not_ship_is_never_ours(self):
        write(self.game_path("zombie/iso/IsoWorld.class"), b"by-hand")
        self.assertEqual(pz.adopted_files(self.mod, self.game, self.ws), {})

    def test_the_record_wins_over_what_is_on_disk(self):
        """Zapis mówi dokładnie, co wgraliśmy — bajty tylko go zastępują."""
        self.put_old_install()
        state = {"mods": {self.mod["workshop_id"]: {
            "files": {"zombie/" + BCP_CLASSES[0]: "0" * 64}}}}
        files = pz.PZUpdaterApp._installed_files(self.app(state), self.mod)
        self.assertEqual(sorted(files), ["zombie/" + BCP_CLASSES[0]])

    def test_a_mod_without_a_workshop_folder_has_nothing_to_remove(self):
        self.put_old_install()
        app = self.App(self.game, {}, {"mods": {}})
        self.assertEqual(pz.PZUpdaterApp._installed_files(app, self.mod), {})


class TestNoUninstallForAJarReplacement(TempCase):
    def test_a_replaced_jar_is_never_taken_back(self):
        """Podmieniony jar leży na jarze moda — wycofanie zostawiłoby dziurę."""
        mod = self.mod("zombiebuddy_fix")
        ws = os.path.join(self.tmp, "ws_fix")
        write(os.path.join(ws, "mods", "ZBExt", "42.21", mod["jar_name"]), b"fixed")
        write(self.game_path(mod["target_rel"]), b"fixed")
        self.assertEqual(pz.adopted_files(mod, self.game, ws), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
