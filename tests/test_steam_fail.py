#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jeden martwy workshop id nie może wywrócić sprawdzania wszystkich wierszy.

Zgłoszenie Adama: wiersz ZombieBuddy BETA nie pokazywał daty ani stanu, bo
sprawdzanie kończyło się błędem na jednej pozycji z prawej kolumny („Immersive
Moodles", 3830422267 — Steam nie zna tego id) i `steam_info` zostawało puste.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pzupdater as pz

GOOD_ID = "3812624292"


def headless_app(failed=(), steam_info=None, install=pz.INSTALL_OK, saved=100):
    """Tyle aplikacji, ile trzeba, żeby policzyć stan wiersza bez okna."""

    class App:
        _status_info = pz.PZUpdaterApp._status_info
        _manual_status = pz.PZUpdaterApp._manual_status
        _requirements = pz.PZUpdaterApp._requirements
        _files_present = pz.PZUpdaterApp._files_present
        _manual_subscribed = pz.PZUpdaterApp._manual_subscribed
        _repair_state = pz.PZUpdaterApp._repair_state
        _repair_files = pz.PZUpdaterApp._repair_files
        _blocked_by_signature = pz.PZUpdaterApp._blocked_by_signature
        _manifests = pz.PZUpdaterApp._manifests
        _installed_files = pz.PZUpdaterApp._installed_files
        _visible_mods = pz.PZUpdaterApp._visible_mods
        _is_hidden = pz.PZUpdaterApp._is_hidden
        _jar_version_of = pz.PZUpdaterApp._jar_version_of
        _mod_by_workshop_id = pz.PZUpdaterApp._mod_by_workshop_id

        def __init__(self):
            self.paths = {"game_dir": None,
                          "workshop": {m["key"]: "ws" for m in pz.UPDATABLE_MODS}}
            self.steam_info = steam_info if steam_info is not None else {}
            self.steam_failed = set(failed)
            self.state = {"mods": {}}
            self.manual_mods = [{"workshop_id": "3830422267", "name": "Immersive Moodles"}]
            self._repair = None

        def t(self, key, *args):
            return key

        def _mod_name(self, mod):
            return mod["name"]

        def _install_state(self, mod):
            return (install, install == pz.INSTALL_OK, 1)

        def _installed_build(self, mod, mods=None):
            return None

        def _saved_ts(self, workshop_id):
            return saved

        def _is_obsolete(self, mod):
            return False

    return App()


class FetchDetailsKeepsGoing(unittest.TestCase):
    """Zbieranie odpowiedzi Steam: błąd jednej pozycji jest notowany, nie rzucany."""

    def test_one_dead_id_does_not_lose_the_others(self):
        dead = "3830422267"
        calls = []

        def fake(wid):
            if wid == dead:
                raise pz.UpdaterError("error.steam_no_data", wid)
            return {"title": wid, "time_updated": 5}

        original = pz.steam_get_details
        pz.steam_get_details = fake
        try:
            seen = []
            details, failed = pz.fetch_details(["1", dead, "2"],
                                               lambda i, n: seen.append((i, n)))
        finally:
            pz.steam_get_details = original

        self.assertEqual(set(details), {"1", "2"})
        self.assertEqual(set(failed), {dead})
        self.assertIsInstance(failed[dead], pz.UpdaterError)
        self.assertEqual(seen, [(1, 3), (2, 3), (3, 3)])

    def test_a_total_failure_is_reported_id_by_id(self):
        original = pz.steam_get_details

        def fake(wid):
            raise OSError("no network")

        pz.steam_get_details = fake
        try:
            details, failed = pz.fetch_details(["1", "2"])
        finally:
            pz.steam_get_details = original

        self.assertEqual(details, {})
        self.assertEqual(set(failed), {"1", "2"})

    def test_nothing_fails_when_steam_answers(self):
        original = pz.steam_get_details
        pz.steam_get_details = lambda wid: {"title": wid, "time_updated": 1}
        try:
            details, failed = pz.fetch_details(["1"])
        finally:
            pz.steam_get_details = original
        self.assertEqual(details, {"1": {"title": "1", "time_updated": 1}})
        self.assertEqual(failed, {})


class TheRowSaysWhy(unittest.TestCase):
    """Wiersz bez danych ze Steam nie może wisieć na „…"."""

    def mod(self, key):
        return next(m for m in pz.UPDATABLE_MODS if m["key"] == key)

    def test_a_tracked_row_without_steam_data_says_so(self):
        app = headless_app(failed=[GOOD_ID])
        info = app._status_info(self.mod("zombiebuddy_beta"))
        self.assertEqual(info["status"], "status.no_steam_data")
        self.assertEqual(info["tag"], "err")
        self.assertFalse(info["muted"])
        self.assertIsNone(info["pending"])

    def test_a_watched_row_without_steam_data_says_so(self):
        app = headless_app(failed=["3830422267"])
        status, tag = app._manual_status(app.manual_mods[0])
        self.assertEqual(status, "status.no_steam_data")
        self.assertEqual(tag, "err")

    def test_a_row_still_waiting_keeps_the_dots(self):
        app = headless_app()
        info = app._status_info(self.mod("zombiebuddy_beta"))
        self.assertEqual(info["status"], "status.pending")
        self.assertEqual(app._manual_status(app.manual_mods[0])[0], "status.pending")

    def test_steam_data_makes_the_row_current_again(self):
        app = headless_app(steam_info={GOOD_ID: {"title": "B", "time_updated": 100}})
        info = app._status_info(self.mod("zombiebuddy_beta"))
        self.assertEqual(info["status"], "status.up_to_date")
        self.assertEqual(info["tag"], "ok")


if __name__ == "__main__":
    unittest.main()
