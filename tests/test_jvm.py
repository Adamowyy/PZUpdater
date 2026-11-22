#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the JVM settings written into ProjectZomboid64.json."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pzupdater as pz


STOCK = {
    "mainClass": "zombie/gameStates/MainScreenState",
    "classpath": [".", "projectzomboid.jar"],
    "vmArgs": [
        "-Djava.awt.headless=true",
        "--enable-native-access=ALL-UNNAMED",
        "-Xmx3072m",
        "-Dzomboid.steam=1",
        "-XX:-CreateCoredumpOnCrash",
    ],
    "windows": {
        "6.1": {"vmArgs": ["-XX:+UseG1GC"]},
        "10.0.17134": {"vmArgs": ["-XX:+UseZGC"]},
    },
}


class TestArgs(unittest.TestCase):
    def test_reads_the_ram_in_gb(self):
        self.assertEqual(pz.jvm_ram_gb(["-Xmx3072m"]), 3)
        self.assertEqual(pz.jvm_ram_gb(["-Xmx8g"]), 8)
        self.assertIsNone(pz.jvm_ram_gb(["-Djava.awt.headless=true"]))
        self.assertIsNone(pz.jvm_ram_gb([]))

    def test_reads_the_collector(self):
        self.assertEqual(pz.jvm_gc(["-XX:+UseZGC"]), "ZGC")
        self.assertEqual(pz.jvm_gc(["-XX:+UseG1GC"]), "G1GC")
        self.assertIsNone(pz.jvm_gc(["-Xmx3072m"]))

    def test_settings_keep_one_xmx_and_it_comes_first(self):
        args = pz.jvm_settings(STOCK["vmArgs"], 8)
        self.assertEqual([a for a in args if a.startswith("-Xmx")], ["-Xmx8g"])
        self.assertIn("-Dzomboid.steam=1", args)
        self.assertEqual(args[:2], [pz.JVM_GC_ARG, "-Xmx8g"])
        # everything the game shipped survives, in its own order
        self.assertEqual(args[2:], ["-Djava.awt.headless=true",
                                    "--enable-native-access=ALL-UNNAMED",
                                    "-Dzomboid.steam=1",
                                    "-XX:-CreateCoredumpOnCrash"])

    def test_settings_leave_exactly_one_collector(self):
        args = pz.jvm_settings(["-Xmx4g", "-XX:+UseZGC", "-XX:+UseSerialGC"], 6)
        self.assertEqual([a for a in args if a.endswith("GC")], [pz.JVM_GC_ARG])

    def test_settings_add_the_xmx_when_the_file_has_none(self):
        args = pz.jvm_settings(["-Dzomboid.steam=1"], 12)
        self.assertIn("-Xmx12g", args)

    def test_settings_are_idempotent(self):
        once = pz.jvm_settings(STOCK["vmArgs"], 8)
        self.assertEqual(pz.jvm_settings(once, 8), once)


class TestVerdict(unittest.TestCase):
    def test_ok_when_the_flags_are_there(self):
        current = {"ram_gb": 8, "gc": "G1GC"}
        self.assertEqual(pz.jvm_verdict(current, 8), "ok")
        self.assertEqual(pz.jvm_verdict(current), "ok")

    def test_gone_when_the_file_was_reset(self):
        stock = {"ram_gb": 3, "gc": "ZGC"}
        self.assertEqual(pz.jvm_verdict(stock, 8), "gone")
        self.assertEqual(pz.jvm_verdict({"ram_gb": None, "gc": None}, 8), "gone")

    def test_gone_when_the_ram_is_not_the_one_we_wrote(self):
        self.assertEqual(pz.jvm_verdict({"ram_gb": 4, "gc": "G1GC"}, 8), "gone")

    def test_none_for_a_launcher_we_never_touched(self):
        self.assertEqual(pz.jvm_verdict({"ram_gb": 3, "gc": "ZGC"}, None), "none")
        self.assertEqual(pz.jvm_verdict({}, None), "none")


class TestConfigFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.game = os.path.join(self.dir, "Game")
        os.makedirs(self.game)
        self.appdata = os.path.join(self.dir, "appdata")
        os.makedirs(self.appdata)
        self.path = os.path.join(self.game, pz.JVM_CONFIG_NAME)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(STOCK, fh, indent="\t")
        patcher = mock.patch.object(pz, "state_path",
                                    return_value=os.path.join(self.appdata, "state.json"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_current_reports_the_bucket_collector(self):
        """The per-Windows bucket is what actually runs, so it has to win."""
        current = pz.jvm_current(self.game)
        self.assertEqual(current["ram_gb"], 3)
        self.assertEqual(current["gc"], "ZGC")

    def test_apply_writes_the_ram_and_g1(self):
        pz.jvm_apply_config(self.game, 10)
        data = self.read()
        self.assertIn("-Xmx10g", data["vmArgs"])
        self.assertNotIn("-Xmx3072m", data["vmArgs"])
        self.assertEqual(data["vmArgs"].count(pz.JVM_GC_ARG), 1)

    def test_apply_clears_the_bucket_collectors(self):
        """Two collectors on one command line stop the JVM."""
        pz.jvm_apply_config(self.game, 8)
        data = self.read()
        for bucket in data["windows"].values():
            self.assertEqual(bucket["vmArgs"], [])
        self.assertEqual(pz.jvm_current(self.game)["gc"], "G1GC")

    def test_apply_keeps_everything_else(self):
        pz.jvm_apply_config(self.game, 8)
        data = self.read()
        self.assertEqual(data["mainClass"], STOCK["mainClass"])
        self.assertEqual(data["classpath"], STOCK["classpath"])
        self.assertEqual(set(data["windows"]), set(STOCK["windows"]))

    def test_apply_leaves_a_backup_of_the_original(self):
        backup = pz.jvm_apply_config(self.game, 8)["backup"]
        self.assertTrue(os.path.isfile(backup))
        with open(backup, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), STOCK)

    def test_apply_twice_changes_nothing_more(self):
        pz.jvm_apply_config(self.game, 8)
        first = self.read()
        pz.jvm_apply_config(self.game, 8)
        self.assertEqual(self.read(), first)

    def test_missing_file_is_an_error(self):
        os.remove(self.path)
        with self.assertRaises(pz.UpdaterError) as caught:
            pz.jvm_apply_config(self.game, 8)
        self.assertEqual(caught.exception.key, "error.no_launcher_config")


if __name__ == "__main__":
    unittest.main(verbosity=2)
