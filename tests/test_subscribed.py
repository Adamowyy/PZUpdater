#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the subscription list and the workshop collection view."""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n
import pzupdater as pz

NOW = 1_800_000_000          # a fixed "now" so the day thresholds stay put
DAY = 86400

ACF = '''"AppWorkshop"
{
\t"appid"\t\t"108600"
\t"TimeLastUpdated"\t\t"1795874570"
\t"WorkshopItemsInstalled"
\t{
\t\t"2447729538"
\t\t{
\t\t\t"size"\t\t"9469808"
\t\t\t"timeupdated"\t\t"1794143179"
\t\t\t"manifest"\t\t"599299838658182414"
\t\t}
\t\t"2503622437"
\t\t{
\t\t\t"size"\t\t"4471917"
\t\t\t"timeupdated"\t\t"1794941167"
\t\t\t"manifest"\t\t"9024373936359073987"
\t\t}
\t}
\t"WorkshopItemDetails"
\t{
\t\t"1"
\t\t{
\t\t\t"manifest"\t\t"1"
\t\t}
\t}
}
'''


class TestAppWorkshopFile(unittest.TestCase):
    def test_reads_the_installed_map(self):
        items = pz.parse_appworkshop(ACF)
        self.assertEqual(set(items), {"2447729538", "2503622437"})
        self.assertEqual(items["2447729538"]["timeupdated"], 1794143179)
        self.assertEqual(items["2503622437"]["size"], 4471917)

    def test_ignores_the_item_details_section(self):
        """WorkshopItemDetails describes files, not subscriptions - no 6-digit ids there."""
        self.assertNotIn("1", pz.parse_appworkshop(ACF))

    def test_missing_section_reads_as_empty(self):
        self.assertEqual(pz.parse_appworkshop('"AppWorkshop" { "appid" "108600" }'), {})

    def test_a_body_without_timestamps_keeps_the_mod(self):
        text = ('"WorkshopItemsInstalled" { "1234567" { "size" "10" } }')
        self.assertEqual(pz.parse_appworkshop(text), {"1234567": {"timeupdated": 0, "size": 10}})


class TestSubscribedItems(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _library(self, name, text):
        lib = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(lib, "steamapps", "workshop"))
        with open(os.path.join(lib, "steamapps", "workshop", "appworkshop_108600.acf"),
                  "w", encoding="utf-8") as f:
            f.write(text)
        return lib

    def test_merges_one_file_per_library(self):
        first = self._library("a", '"WorkshopItemsInstalled" { "1111111" { "timeupdated" "10" } }')
        second = self._library("b", '"WorkshopItemsInstalled" { "2222222" { "timeupdated" "20" } }')
        items = pz.subscribed_items([first, second])
        self.assertEqual(set(items), {"1111111", "2222222"})

    def test_the_newest_timestamp_wins(self):
        first = self._library("a", '"WorkshopItemsInstalled" { "1111111" { "timeupdated" "10" } }')
        second = self._library("b", '"WorkshopItemsInstalled" { "1111111" { "timeupdated" "20" } }')
        self.assertEqual(pz.subscribed_items([first, second])["1111111"]["timeupdated"], 20)

    def test_a_missing_file_is_not_an_error(self):
        self.assertEqual(pz.subscribed_items([os.path.join(self.tmp, "nope")]), {})

    def test_no_libraries_at_all(self):
        self.assertEqual(pz.subscribed_items(None), {})


class TestStaleness(unittest.TestCase):
    def test_thresholds(self):
        self.assertIsNone(pz.stale_level(NOW - 179 * DAY, NOW))
        self.assertEqual(pz.stale_level(NOW - 180 * DAY, NOW), "yellow")
        self.assertEqual(pz.stale_level(NOW - 364 * DAY, NOW), "yellow")
        self.assertEqual(pz.stale_level(NOW - 365 * DAY, NOW), "red")

    def test_no_timestamp_is_not_stale(self):
        self.assertIsNone(pz.stale_level(0, NOW))
        self.assertIsNone(pz.age_days(0, NOW))

    def test_age_days_never_goes_negative(self):
        self.assertEqual(pz.age_days(NOW + 10 * DAY, NOW), 0)

    def test_age_text_switches_to_months(self):
        t = i18n.Translator("en")
        self.assertEqual(pz.age_text(9, t), "9 d ago")
        self.assertEqual(pz.age_text(45, t), "1 mo ago")
        self.assertEqual(pz.age_text(None, t), "—")
        self.assertEqual(pz.age_text(45, i18n.Translator("pl")), "1 mies. temu")


class TestSorting(unittest.TestCase):
    def test_oldest_update_on_top_and_unknown_at_the_bottom(self):
        rows = [{"id": "a", "time_updated": NOW},
                {"id": "b", "time_updated": 0},
                {"id": "c", "time_updated": NOW - 400 * DAY}]
        self.assertEqual([r["id"] for r in pz.oldest_first(rows)], ["c", "a", "b"])

    def test_stale_count_counts_a_year_only(self):
        rows = [{"time_updated": NOW - 400 * DAY}, {"time_updated": NOW - 200 * DAY},
                {"time_updated": NOW - 10 * DAY}]
        self.assertEqual(pz.stale_count(rows, NOW), 1)


class TestCollectionId(unittest.TestCase):
    def test_bare_id(self):
        self.assertEqual(pz.parse_collection_id("3550116466"), "3550116466")

    def test_from_a_link(self):
        self.assertEqual(
            pz.parse_collection_id(
                "https://steamcommunity.com/sharedfiles/filedetails/?id=3550116466&x=1"),
            "3550116466")

    def test_garbage(self):
        self.assertIsNone(pz.parse_collection_id(""))
        self.assertIsNone(pz.parse_collection_id("not a collection"))
        self.assertIsNone(pz.parse_collection_id(None))


class TestSteamBatch(unittest.TestCase):
    """The batch call is faked at the HTTP layer: no network in the suite."""

    def setUp(self):
        self.posted = []
        self.original = pz._steam_post

    def tearDown(self):
        pz._steam_post = self.original

    def _fake(self, answer):
        def fake(url, fields, timeout=20):
            self.posted.append(fields)
            return answer(fields)
        pz._steam_post = fake

    def test_chunks_a_long_list(self):
        def answer(fields):
            count = int(fields["itemcount"])
            return {"response": {"publishedfiledetails": [
                {"result": 1, "publishedfileid": fields["publishedfileids[%d]" % i],
                 "title": "mod", "time_updated": 100} for i in range(count)]}}
        self._fake(answer)
        details, failed = pz.steam_batch_details(["%07d" % i for i in range(250)], chunk=100)
        self.assertEqual(len(details), 250)
        self.assertEqual(failed, {})
        self.assertEqual([int(f["itemcount"]) for f in self.posted], [100, 100, 50])

    def test_one_dead_id_does_not_blank_the_list(self):
        def answer(fields):
            out = []
            for i in range(int(fields["itemcount"])):
                wid = fields["publishedfileids[%d]" % i]
                result = 9 if wid == "9999999" else 1
                out.append({"result": result, "publishedfileid": wid, "title": wid,
                            "time_updated": 5})
            return {"response": {"publishedfiledetails": out}}
        self._fake(answer)
        details, failed = pz.steam_batch_details(["1111111", "9999999", "2222222"])
        self.assertEqual(set(details), {"1111111", "2222222"})
        self.assertIn("9999999", failed)

    def test_an_id_steam_never_answers_for_fails_alone(self):
        self._fake(lambda f: {"response": {"publishedfiledetails": [
            {"result": 1, "publishedfileid": "1111111", "title": "a", "time_updated": 5}]}})
        details, failed = pz.steam_batch_details(["1111111", "2222222"])
        self.assertEqual(set(details), {"1111111"})
        self.assertIn("2222222", failed)

    def test_a_failed_chunk_keeps_the_other_chunks(self):
        seen = {"n": 0}

        def answer(fields):
            seen["n"] += 1
            if seen["n"] == 1:
                raise OSError("network down")
            return {"response": {"publishedfiledetails": [
                {"result": 1, "publishedfileid": fields["publishedfileids[0]"],
                 "title": "b", "time_updated": 5}]}}
        self._fake(answer)
        details, failed = pz.steam_batch_details(["1111111", "2222222"], chunk=1)
        self.assertEqual(set(details), {"2222222"})
        self.assertIn("1111111", failed)

    def test_progress_reaches_the_total(self):
        self._fake(lambda f: {"response": {"publishedfiledetails": []}})
        seen = []
        pz.steam_batch_details(["1111111", "2222222"], chunk=1,
                               on_progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen[-1], (2, 2))


class TestSteamCollection(unittest.TestCase):
    def setUp(self):
        self.original_post = pz._steam_post
        self.original_batch = pz.steam_batch_details

    def tearDown(self):
        pz._steam_post = self.original_post
        pz.steam_batch_details = self.original_batch

    def test_reads_children_and_the_title(self):
        pz._steam_post = lambda url, fields, timeout=20: {"response": {"collectiondetails": [
            {"result": 1, "publishedfileid": "3550116466", "children": [
                {"publishedfileid": "1111111", "sortorder": 1, "filetype": 0},
                {"publishedfileid": "2222222", "sortorder": 2, "filetype": 0}]}]}}
        pz.steam_batch_details = lambda ids, chunk=100, on_progress=None: (
            {"3550116466": {"title": "My collection", "time_updated": 1}}, {})
        coll = pz.steam_collection("3550116466")
        self.assertEqual(coll["title"], "My collection")
        self.assertEqual(coll["children"], ["1111111", "2222222"])

    def test_a_missing_collection_raises_a_translated_error(self):
        pz._steam_post = lambda url, fields, timeout=20: {"response": {"collectiondetails": [
            {"result": 9}]}}
        with self.assertRaises(pz.UpdaterError) as caught:
            pz.steam_collection("1234567")
        self.assertEqual(caught.exception.key, "error.collection_missing")

    def test_a_dead_network_raises_a_translated_error(self):
        def boom(url, fields, timeout=20):
            raise OSError("no route to host")
        pz._steam_post = boom
        with self.assertRaises(pz.UpdaterError) as caught:
            pz.steam_collection("1234567")
        self.assertEqual(caught.exception.key, "error.collection_failed")


class TestListStrings(unittest.TestCase):
    def test_every_new_key_is_translated(self):
        keys = ["tab.updates", "tab.subscribed", "tab.collections",
                "panel.subs.title", "panel.subs.subtitle", "panel.subs.legend",
                "panel.subs.refresh", "panel.subs.f_all", "panel.subs.f_stale",
                "panel.subs.count", "panel.subs.stale_count", "panel.subs.truncated",
                "panel.subs.none_stale", "panel.coll.title", "panel.coll.subtitle",
                "panel.coll.placeholder", "panel.coll.show", "panel.coll.in_subs",
                "panel.coll.not_in_subs", "age.days", "age.months"]
        for key in keys:
            for language in i18n.LANGUAGES:
                self.assertTrue(i18n.STRINGS[language].get(key), msg=f"{language}: {key}")

    def test_the_tab_values_are_distinct(self):
        """The tab bar finds a view by its label, so two equal labels would lie."""
        for language in i18n.LANGUAGES:
            values = [i18n.STRINGS[language][pz.TAB_KEYS[v]] for v in pz.VIEWS]
            self.assertEqual(len(set(values)), len(values), msg=language)


if __name__ == "__main__":
    unittest.main(verbosity=2)
