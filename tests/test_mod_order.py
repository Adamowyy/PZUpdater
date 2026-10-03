#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Order of the two mod lists: a row waiting for a click goes up, a row that is
not on this machine at all goes down.

Run with (venv with customtkinter):
    .buildenv/Scripts/python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pzupdater as pz


def info(pending=None, tag=""):
    """The part of `_status_info()` the ordering reads."""
    return {"pending": pending, "tag": tag, "status": "", "muted": False,
            "install": pz.INSTALL_UNKNOWN, "ok": 0, "total": 0}


def sort_left(pairs):
    """The same expression `refresh_statuses` uses for the left column."""
    infos = dict(pairs)
    return sorted(infos, key=lambda k: pz.supported_rank(infos[k]))


def sort_right(pairs):
    """The same expression `refresh_statuses` uses for the right column:
    `pairs` is [(workshop_id, (tag, subscribed)), ...]."""
    ranks = {wid: pz.watched_rank(*state) for wid, state in pairs}
    return sorted(ranks, key=ranks.get)


class TestSupportedRank(unittest.TestCase):
    def test_a_pending_action_beats_everything_else(self):
        for tag in ("info", "new", "gray"):
            self.assertLess(pz.supported_rank(info(pending="update", tag=tag)),
                            pz.supported_rank(info(tag="ok")),
                            f"tag {tag!r} should sort above an up to date mod")

    def test_wrong_files_beat_a_newer_version_and_a_missing_copy(self):
        """Outdated files in the game folder are what actually breaks the game,
        so they outrank "the author published something" and "subscribed but
        never copied"."""
        wrong = pz.supported_rank(info(pending="update", tag="info"))
        newer = pz.supported_rank(info(pending="update", tag="new"))
        missing = pz.supported_rank(info(pending="install", tag="gray"))
        self.assertLess(wrong, newer)
        self.assertLess(newer, missing)
        self.assertEqual(missing[0], pz.LEFT_TODO)

    def test_current_mods_beat_the_ones_that_are_not_here(self):
        self.assertLess(pz.supported_rank(info(tag="ok")),
                        pz.supported_rank(info(tag="gray")))

    def test_a_mod_with_no_subscription_sinks(self):
        """The reported case: a mod that is neither installed nor subscribed sat
        at the top of a static list."""
        self.assertEqual(pz.supported_rank(info(tag="gray"))[0], pz.LEFT_IDLE)

    def test_an_obsolete_mod_is_idle_too(self):
        self.assertEqual(pz.supported_rank(info(tag="old"))[0], pz.LEFT_IDLE)

    def test_an_unknown_state_is_not_mistaken_for_current(self):
        self.assertEqual(pz.supported_rank(info())[0], pz.LEFT_IDLE)


class TestSupportedListOrder(unittest.TestCase):
    def test_the_reported_scenario(self):
        """not subscribed / up to date / outdated, in registry order -> the row
        with something to do first, the one that is not here last."""
        pairs = [("not_subscribed", info(tag="gray")),
                 ("up_to_date", info(tag="ok")),
                 ("outdated", info(pending="update", tag="info"))]
        self.assertEqual(sort_left(pairs),
                         ["outdated", "up_to_date", "not_subscribed"])

    def test_rows_in_the_same_state_keep_the_registry_order(self):
        pairs = [("a", info(tag="ok")), ("b", info(tag="ok")),
                 ("c", info(tag="gray")), ("d", info(tag="gray"))]
        self.assertEqual(sort_left(pairs), ["a", "b", "c", "d"])

    def test_an_empty_list_is_fine(self):
        self.assertEqual(sort_left([]), [])


class TestWatchedRank(unittest.TestCase):
    def test_something_new_on_steam_goes_first(self):
        self.assertEqual(pz.watched_rank("new", True)[0], pz.WATCHED_NEW)
        self.assertLess(pz.watched_rank("new", True),
                        pz.watched_rank("info", True))

    def test_a_not_subscribed_up_to_date_mod_goes_last(self):
        self.assertLess(pz.watched_rank("ok", True),
                        pz.watched_rank("ok", False))
        self.assertEqual(pz.watched_rank("ok", False)[0], pz.WATCHED_GONE)

    def test_a_warning_still_outranks_a_missing_subscription(self):
        """The red and amber badges carry real information, so a row keeping one
        does not sink just because the mod is not subscribed."""
        self.assertLess(pz.watched_rank("info", False), pz.watched_rank("ok", False))
        self.assertLess(pz.watched_rank("new", False), pz.watched_rank("ok", True))

    def test_steam_data_not_fetched_yet_is_not_treated_as_current(self):
        self.assertEqual(pz.watched_rank("", True)[0], pz.WATCHED_UNKNOWN)
        self.assertLess(pz.watched_rank("ok", True), pz.watched_rank("", True))


class TestWatchedListOrder(unittest.TestCase):
    def test_the_reported_scenario(self):
        pairs = [("gone", ("ok", False)),
                 ("fine", ("ok", True)),
                 ("updated", ("new", True)),
                 ("never_marked", ("info", True))]
        self.assertEqual(sort_right(pairs),
                         ["updated", "never_marked", "fine", "gone"])

    def test_rows_in_the_same_state_keep_the_order_they_were_added_in(self):
        pairs = [("a", ("new", True)), ("b", ("new", False)),
                 ("c", ("ok", True))]
        self.assertEqual(sort_right(pairs), ["a", "b", "c"])

    def test_a_watched_mod_that_was_removed_from_the_list_is_ignored(self):
        self.assertEqual(sort_right([]), [])


if __name__ == "__main__":
    unittest.main()
