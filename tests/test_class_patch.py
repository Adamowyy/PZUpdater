#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Klasy kompilowane pod konkretny build gry (Tempo: manual_installation/<build>/zombie)."""

import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n
import pzupdater as pz

REV = "4a0e9546ec"
CLASSES = ("zombie/iso/IsoChunkMap.class", "zombie/iso/IsoWorld.class",
           "zombie/core/PerformanceSettings.class")


def write(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


def make_jar(path, revision):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("zombie/GitVersion.class", b"\xca\xfe\xba\xbe" + revision.encode())
    return path


class PatchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pzupd_patch_")
        self.game = os.path.join(self.tmp, "game")
        os.makedirs(self.game)
        self.profile = os.path.join(self.tmp, "profile")
        self.ws = os.path.join(self.tmp, "ws")
        os.makedirs(self.ws)
        self._env = os.environ.get("USERPROFILE")
        os.environ["USERPROFILE"] = self.profile
        pz.GAME_BUILD_CACHE.clear()
        self.mod = next(m for m in pz.UPDATABLE_MODS if m["key"] == "tempo_patches")
        self.t = i18n.Translator("pl")

    def tearDown(self):
        if self._env is None:
            os.environ.pop("USERPROFILE", None)
        else:
            os.environ["USERPROFILE"] = self._env
        pz.GAME_BUILD_CACHE.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ------------------------------------------------------------

    def version_file(self, build="42.21.0", revision=REV):
        write(os.path.join(self.profile, "Zomboid", "version.txt"),
              f"{build} {revision}\nrevision={revision} pzbullet=1.0.0.28\n".encode())

    def game_jar(self, revision=REV):
        make_jar(os.path.join(self.game, "projectzomboid.jar"), revision)

    def ready(self, build="42.21.0", revision=REV):
        self.version_file(build, revision)
        self.game_jar(revision)

    def patches(self, build="42.21.0"):
        root = os.path.join(self.ws, "mods", "Tempo_PerfKit", "manual_installation",
                            build, "zombie")
        for rel in CLASSES:
            # CLASSES to ścieżki w grze, a folder źródłowy to już sam "zombie"
            inside = rel.split("/", 1)[1]
            write(os.path.join(root, *inside.split("/")), b"patched:" + inside.encode())
        return root

    def game_has(self, rel):
        return os.path.isfile(os.path.join(self.game, *rel.split("/")))

    def install(self, prev=None):
        return pz.update_class_patch(self.mod, self.game, self.ws, self.t, prev)


class TestGameBuild(PatchCase):
    def test_reads_the_build_and_confirms_it_against_the_jar(self):
        self.ready("42.21.0", REV)
        b = pz.game_build(self.game)
        self.assertEqual((b["build"], b["revision"], b["jar_revision"]), ("42.21.0", REV, REV))
        self.assertTrue(b["trusted"])

    def test_not_trusted_when_the_jar_is_another_revision(self):
        """Gra zaktualizowana, ale jeszcze nie uruchomiona: version.txt jest stary."""
        self.ready("42.21.0", REV)
        self.game_jar("aaaaaaaaaa")
        b = pz.game_build(self.game)
        self.assertEqual(b["build"], "42.21.0")
        self.assertFalse(b["trusted"])

    def test_not_trusted_without_the_version_file(self):
        self.game_jar(REV)
        b = pz.game_build(self.game)
        self.assertIsNone(b["build"])
        self.assertFalse(b["trusted"])


class TestSourceFolder(PatchCase):
    def test_found_for_the_exact_build(self):
        root = self.patches("42.21.0")
        self.assertEqual(pz.class_patch_folder(self.mod, self.ws, "42.21.0"), root)

    def test_not_found_for_another_build(self):
        self.patches("42.21.0")
        self.assertIsNone(pz.class_patch_folder(self.mod, self.ws, "42.22.0"))

    def test_targets_are_named_after_the_folder_in_the_game(self):
        self.ready()
        self.patches()
        rels = sorted(rel for rel, _kind, _src in pz.mod_targets(self.mod, self.ws, self.game))
        self.assertEqual(rels, sorted(CLASSES))

    def test_targets_need_the_build(self):
        self.patches()
        self.assertEqual(pz.mod_targets(self.mod, self.ws), [])
        self.assertEqual(pz.mod_targets(self.mod, self.ws, self.game), [])


class TestInstall(PatchCase):
    def test_installs_the_three_classes(self):
        self.ready()
        self.patches()
        ok, msg, meta = self.install()
        self.assertTrue(ok, msg)
        for rel in CLASSES:
            self.assertTrue(self.game_has(rel), rel)
        self.assertEqual(meta["version"], "42.21.0")
        self.assertEqual(sorted(meta["files"]), sorted(CLASSES))
        state, ok_n, total = pz.mod_install_state(self.mod, self.game,
                                                  {"tempo_patches": self.ws},
                                                  pz.UPDATABLE_MODS)
        self.assertEqual((state, ok_n, total), (pz.INSTALL_OK, 3, 3))

    def test_refuses_without_a_build(self):
        self.game_jar(REV)
        self.patches()
        ok, _msg, _meta = self.install()
        self.assertFalse(ok)
        self.assertFalse(self.game_has(CLASSES[0]))

    def test_refuses_when_the_build_is_not_confirmed(self):
        self.ready()
        self.game_jar("aaaaaaaaaa")
        self.patches()
        ok, _msg, _meta = self.install()
        self.assertFalse(ok)
        self.assertFalse(self.game_has(CLASSES[0]))

    def test_refuses_when_the_mod_ships_no_package_for_this_build(self):
        self.ready("42.22.0", "bbbbbbbbbb")
        self.patches("42.21.0")
        ok, msg, _meta = self.install()
        self.assertFalse(ok)
        self.assertIn("42.22.0", msg)
        self.assertFalse(self.game_has(CLASSES[0]))

    def test_replacing_a_build_drops_what_the_new_package_lacks(self):
        self.ready()
        self.patches("42.21.0")
        _ok, _msg, meta = self.install()
        old = dict(meta["files"])
        stray = "zombie/iso/IsoGridSquare.class"
        write(os.path.join(self.game, *stray.split("/")), b"from-the-old-package")
        old[stray] = pz.file_sha256(os.path.join(self.game, *stray.split("/")))
        self.ready("42.22.0", "cccccccccc")
        self.patches("42.22.0")
        ok, msg, meta = self.install({"files": old})
        self.assertTrue(ok, msg)
        self.assertFalse(self.game_has(stray))
        self.assertEqual(sorted(meta["files"]), sorted(CLASSES))


class TestRemove(PatchCase):
    def test_takes_back_the_files_and_the_folders_they_left(self):
        self.ready()
        self.patches()
        _ok, _msg, meta = self.install()
        ok, msg, res = pz.remove_class_patch(self.mod, self.game, self.t, meta)
        self.assertTrue(ok, msg)
        self.assertEqual(len(res["removed"]), 3)
        for rel in CLASSES:
            self.assertFalse(self.game_has(rel), rel)
        self.assertFalse(os.path.isdir(os.path.join(self.game, "zombie")))
        self.assertTrue(os.path.isdir(self.game))

    def test_leaves_a_file_that_changed_since_the_install(self):
        self.ready()
        self.patches()
        _ok, _msg, meta = self.install()
        changed = CLASSES[0]
        write(os.path.join(self.game, *changed.split("/")), b"somebody-else-wrote-this")
        ok, msg, res = pz.remove_class_patch(self.mod, self.game, self.t, meta)
        self.assertTrue(ok, msg)
        self.assertTrue(self.game_has(changed))
        self.assertEqual(res["kept"], [changed])
        self.assertEqual(len(res["removed"]), 2)

    def test_nothing_to_do_without_a_manifest(self):
        ok, _msg, _meta = pz.remove_class_patch(self.mod, self.game, self.t, {})
        self.assertFalse(ok)

    def test_nothing_to_do_when_the_files_are_already_gone(self):
        self.ready()
        self.patches()
        _ok, _msg, meta = self.install()
        for rel in CLASSES:
            os.remove(os.path.join(self.game, *rel.split("/")))
        ok, _msg, _meta = pz.remove_class_patch(self.mod, self.game, self.t, meta)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
