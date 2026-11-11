#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Oczko na karcie moda: zwinięty wiersz i zapamiętany wybór."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pzupdater as pz

TEMPO = "tempo_patches"


def tempo():
    return next(m for m in pz.UPDATABLE_MODS if m["key"] == TEMPO)


class StateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pzupd_fold_")
        self._appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self.tmp

    def tearDown(self):
        if self._appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._appdata
        shutil.rmtree(self.tmp, ignore_errors=True)

    class App:
        _is_collapsed = pz.PZUpdaterApp._is_collapsed
        _toggle_collapsed = pz.PZUpdaterApp._toggle_collapsed

        def __init__(self, state=None, info=None):
            self.state = state if state is not None else {"mods": {}, "collapsed": []}
            self.info = info or {"pending": None, "status": "status.up_to_date",
                                 "tag": "ok", "install": pz.INSTALL_OK,
                                 "switch": False}
            self.log = []
            self.refreshed = 0

        def _log(self, level, text):
            self.log.append(text)

        def refresh_statuses(self):
            self.refreshed += 1

        def _visible_mods(self):
            return [tempo()]

        def _status_info(self, mod):
            return dict(self.info)

        def _installed_build(self, mod):
            return mod


class TestFold(StateCase):
    def test_a_fresh_state_has_nothing_folded(self):
        app = self.App({"mods": {}})
        self.assertFalse(app._is_collapsed(TEMPO))

    def test_the_eye_folds_and_unfolds_one_card(self):
        app = self.App()
        app._toggle_collapsed(TEMPO)
        self.assertTrue(app._is_collapsed(TEMPO))
        self.assertIn(TEMPO, app.state["collapsed"])
        self.assertEqual(app.refreshed, 1)
        app._toggle_collapsed(TEMPO)
        self.assertFalse(app._is_collapsed(TEMPO))
        self.assertEqual(app.state["collapsed"], [])
        self.assertEqual(app.log, [f"folded: {TEMPO}", f"unfolded: {TEMPO}"])

    def test_the_choice_is_written_to_the_state_file(self):
        app = self.App()
        app._toggle_collapsed(TEMPO)
        saved = pz.load_state()
        self.assertEqual(saved["collapsed"], [TEMPO])

    def test_a_state_from_an_older_build_gets_an_empty_list(self):
        path = pz.state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"mods": {}}')
        self.assertEqual(pz.load_state()["collapsed"], [])

    def test_a_broken_collapsed_value_is_dropped(self):
        path = pz.state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"mods": {}, "collapsed": "tempo_patches"}')
        self.assertEqual(pz.load_state()["collapsed"], [])


class TestFoldedCardsAreNotOffered(StateCase):
    """Zwinięty mod nie jest w użyciu: duży przycisk i pasek stanu go pomijają."""

    class Pending(StateCase.App):
        _pending_actions = pz.PZUpdaterApp._pending_actions
        _installed_for_update = pz.PZUpdaterApp._installed_for_update

    def pending_app(self, folded, info):
        outer = self

        class App(outer.Pending):
            def _is_collapsed(self, key):
                return key in folded

        return App({"mods": {}, "collapsed": []}, info)

    def test_a_folded_mod_is_not_pending(self):
        info = {"pending": "install", "status": "status.new_version", "tag": "new",
                "install": pz.INSTALL_OK, "switch": False}
        app = self.pending_app([TEMPO], info)
        self.assertEqual(app._pending_actions(), {})
        self.assertEqual(app._installed_for_update(), [])

    def test_an_unfolded_mod_stays_pending(self):
        info = {"pending": "install", "status": "status.new_version", "tag": "new",
                "install": pz.INSTALL_OK, "switch": False}
        app = self.pending_app([], info)
        self.assertEqual(app._pending_actions(), {TEMPO: "install"})
        self.assertEqual([m["key"] for m in app._installed_for_update()], [TEMPO])

    def test_a_folded_card_sinks_below_every_mod_in_use(self):
        """Zwinięte mody idą pod spód — nawet pod te, które nie mają update'u."""
        folded = pz.supported_rank({"collapsed": True, "pending": "install", "tag": "new"})
        waiting = pz.supported_rank({"collapsed": False, "pending": "install", "tag": "new"})
        idle = pz.supported_rank({"collapsed": False, "pending": None, "tag": ""})
        current = pz.supported_rank({"collapsed": False, "pending": None, "tag": "ok"})
        self.assertGreater(folded, waiting)
        self.assertGreater(folded, current)
        self.assertGreater(folded, idle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
