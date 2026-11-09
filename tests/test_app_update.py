#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aktualizacja samej aplikacji: wydanie z GitHuba, pobranie i podmiana exe."""

import hashlib
import http.server
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n
import pzupdater as pz

EXE_BYTES = b"MZ" + b"\x00" * 4096


def release(tag="v1.1.0", with_exe=True, with_sha=True):
    assets = []
    if with_exe:
        assets.append({"name": "PZUpdater.exe",
                       "browser_download_url": "https://example.invalid/PZUpdater.exe"})
    if with_sha:
        assets.append({"name": "PZUpdater.exe.sha256",
                       "browser_download_url": "https://example.invalid/PZUpdater.exe.sha256"})
    return {"tag_name": tag, "assets": assets}


class TestParseRelease(unittest.TestCase):
    def test_reads_the_version_and_both_assets(self):
        info = pz.parse_release(release())
        self.assertEqual(info["version"], "1.1.0")
        self.assertTrue(info["exe"].endswith("PZUpdater.exe"))
        self.assertTrue(info["sha256"].endswith("PZUpdater.exe.sha256"))

    def test_the_v_prefix_is_dropped(self):
        self.assertEqual(pz.parse_release(release("v1.2.3"))["version"], "1.2.3")

    def test_a_release_without_the_exe_is_not_an_update(self):
        self.assertIsNone(pz.parse_release(release(with_exe=False)))

    def test_a_release_without_a_checksum_is_still_usable(self):
        info = pz.parse_release(release(with_sha=False))
        self.assertIsNone(info["sha256"])

    def test_a_tag_that_is_not_a_version_is_ignored(self):
        self.assertIsNone(pz.parse_release(release("latest")))
        self.assertIsNone(pz.parse_release({}))

    def test_asset_names_are_matched_without_case(self):
        data = {"tag_name": "v2.0.0",
                "assets": [{"name": "pzupdater.EXE",
                            "browser_download_url": "https://example.invalid/x"}]}
        self.assertIsNotNone(pz.parse_release(data))


class TestNewerVersion(unittest.TestCase):
    def test_a_higher_release_wins(self):
        self.assertTrue(pz.newer_version("1.1.0", "1.0.7"))
        self.assertTrue(pz.newer_version("1.10.0", "1.9.9"))
        self.assertTrue(pz.newer_version("2.0.0", "1.99.99"))

    def test_the_same_release_is_not_an_update(self):
        self.assertFalse(pz.newer_version("1.0.7", "1.0.7"))

    def test_an_older_release_does_not_win(self):
        self.assertFalse(pz.newer_version("1.0.6", "1.0.7"))


class ServerCase(unittest.TestCase):
    """Serwuje katalog tymczasowy po HTTP, żeby pobieranie szło prawdziwą drogą."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pzupd_update_")
        self.served = os.path.join(self.tmp, "served")
        os.makedirs(self.served)
        self._appdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = os.path.join(self.tmp, "local")

        handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(
            *a, directory=self.served, **k)
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._appdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._appdata
        shutil.rmtree(self.tmp, ignore_errors=True)

    def url(self, name):
        return f"http://127.0.0.1:{self.port}/{name}"

    def serve(self, name, content):
        path = os.path.join(self.served, name)
        with open(path, "wb") as f:
            f.write(content)
        return path


class TestDownload(ServerCase):
    def test_downloads_the_exe_and_keeps_the_hash_checked(self):
        self.serve("PZUpdater.exe", EXE_BYTES)
        digest = hashlib.sha256(EXE_BYTES).hexdigest()
        self.serve("PZUpdater.exe.sha256", (digest + "  PZUpdater.exe\n").encode())
        dest = os.path.join(self.tmp, "out", "PZUpdater-1.1.0.exe")
        path = pz.download_release_asset(self.url("PZUpdater.exe"), dest,
                                         sha256_url=self.url("PZUpdater.exe.sha256"))
        self.assertEqual(path, dest)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), EXE_BYTES)
        self.assertFalse(os.path.exists(dest + ".part"))

    def test_a_wrong_checksum_stops_the_update(self):
        self.serve("PZUpdater.exe", EXE_BYTES)
        self.serve("PZUpdater.exe.sha256", (("0" * 64) + "\n").encode())
        dest = os.path.join(self.tmp, "out", "PZUpdater-1.1.0.exe")
        with self.assertRaises(pz.UpdaterError) as caught:
            pz.download_release_asset(self.url("PZUpdater.exe"), dest,
                                      sha256_url=self.url("PZUpdater.exe.sha256"))
        self.assertEqual(caught.exception.key, "error.update_checksum")
        self.assertFalse(os.path.exists(dest))

    def test_something_that_is_not_an_exe_is_refused(self):
        self.serve("PZUpdater.exe", b"<html>404</html>")
        dest = os.path.join(self.tmp, "out", "PZUpdater-1.1.0.exe")
        with self.assertRaises(pz.UpdaterError) as caught:
            pz.download_release_asset(self.url("PZUpdater.exe"), dest)
        self.assertEqual(caught.exception.key, "error.update_broken")
        self.assertFalse(os.path.exists(dest))


class TestSelfUpdateScript(unittest.TestCase):
    def script(self, **over):
        values = {"target": "C:/x/PZUpdater.exe", "new": "C:/y/new.exe", "pid": 4242,
                  "old": "C:/x/PZUpdater.exe.old", "marker": "C:/x/started.txt",
                  "failed": "C:/x/failed.txt", "version": "9.9.9"}
        values.update(over)
        return pz.SELF_UPDATE_SCRIPT.format(**values)

    def test_waits_for_the_app_to_close_before_the_swap(self):
        script = self.script()
        self.assertIn("Wait-Process -Id 4242", script)
        self.assertIn("move /y", script)
        # podmiana musi być PO oczekiwaniu, inaczej Windows trzyma plik
        self.assertLess(script.index("Wait-Process"), script.index("move /y"))
        self.assertIn("start", script)
        self.assertTrue(script.startswith("@echo off"))

    def test_the_wait_does_not_go_through_tasklist(self):
        """tasklist nie widzi procesów z cmd bez okna - czekanie szło w 0.2 s."""
        self.assertNotIn("tasklist", pz.SELF_UPDATE_SCRIPT)
        self.assertIn("Wait-Process -Id {pid}", pz.SELF_UPDATE_SCRIPT)

    def test_the_restarted_build_is_not_told_where_this_one_unpacked(self):
        self.assertIn('set "_MEIPASS2="', pz.SELF_UPDATE_SCRIPT)
        self.assertIn('set "_PYI_APPLICATION_HOME_DIR="', pz.SELF_UPDATE_SCRIPT)

    def test_the_move_is_retried_before_giving_up(self):
        self.assertIn(":move", pz.SELF_UPDATE_SCRIPT)
        self.assertIn("goto move", pz.SELF_UPDATE_SCRIPT)
        script = self.script()
        self.assertLess(script.index("if %tries% geq"), script.index(':start'))

    def test_the_old_exe_is_kept_before_the_swap(self):
        """Bez kopii nie ma do czego wrócić, gdy nowy build nie wstanie."""
        script = self.script()
        self.assertIn('copy /y "%TARGET%" "%OLD%"', script)
        self.assertIn("PZUpdater.exe.old", script)
        self.assertLess(script.index('"%OLD%"'), script.index("move /y"))

    def test_a_build_that_does_not_start_is_rolled_back(self):
        """Dokładnie błąd z 1.1.1: nowy exe wstał i padł na LoadLibrary."""
        script = self.script()
        self.assertIn("started.txt", script)
        self.assertIn("9.9.9", script)          # znacznik musi nieść wersję builda
        self.assertIn("if not errorlevel 1 goto done", script)
        # po nieudanym starcie: przywrócenie starego exe, zapis i ponowny start
        rollback = script[script.index("if not errorlevel 1 goto done"):]
        self.assertIn('copy /y "%OLD%" "%TARGET%"', rollback)
        self.assertIn('echo 9.9.9> "%FAILED%"', rollback)
        self.assertIn('start "" "%TARGET%"', rollback)

    def test_the_batch_file_has_real_crlf(self):
        self.assertIn(pz.NEWLINE_CRLF, pz.SELF_UPDATE_SCRIPT)
        self.assertNotIn("\n\n", pz.SELF_UPDATE_SCRIPT.replace(pz.NEWLINE_CRLF, "|"))


class TestStartMarker(unittest.TestCase):
    """Znacznik startu i plik 'nie wstało' - to na nich stoi wycofywanie."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pzupd_marker_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self.tmp
        self.addCleanup(lambda: os.environ.__setitem__("LOCALAPPDATA", self._old)
                        if self._old else os.environ.pop("LOCALAPPDATA", None))

    def test_the_marker_carries_the_version(self):
        pz.write_start_marker()
        with open(pz.update_marker(), encoding="utf-8") as f:
            self.assertTrue(f.read().startswith(pz.APP_VERSION))

    def test_a_failed_build_is_reported_once(self):
        os.makedirs(os.path.dirname(pz.update_failed_file()), exist_ok=True)
        with open(pz.update_failed_file(), "w", encoding="utf-8") as f:
            f.write("1.1.2\n")
        self.assertEqual(pz.update_failed_version(), "1.1.2")
        pz.clear_update_failed()
        self.assertIsNone(pz.update_failed_version())

    def test_no_failed_file_means_nothing_to_report(self):
        self.assertIsNone(pz.update_failed_version())

    def test_launch_writes_the_script_and_starts_it_detached(self):
        tmp = tempfile.mkdtemp(prefix="pzupd_launch_")
        self.addCleanup(shutil.rmtree, tmp, True)
        old_localapp = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = tmp
        self.addCleanup(lambda: os.environ.__setitem__("LOCALAPPDATA", old_localapp)
                        if old_localapp else os.environ.pop("LOCALAPPDATA", None))
        started = {}
        original = pz.subprocess.Popen

        def fake_popen(args, **kwargs):
            started["args"] = args
            started["flags"] = kwargs.get("creationflags", 0)
            started["env"] = kwargs.get("env")

        pz.subprocess.Popen = fake_popen
        os.environ["_MEIPASS2"] = r"C:\gone\_MEI123"
        os.environ["_PYI_APPLICATION_HOME_DIR"] = r"C:\gone\_MEI123"
        try:
            bat = pz.launch_self_update(os.path.join(tmp, "new.exe"),
                                        target=os.path.join(tmp, "PZUpdater.exe"))
        finally:
            pz.subprocess.Popen = original
            os.environ.pop("_MEIPASS2", None)
            os.environ.pop("_PYI_APPLICATION_HOME_DIR", None)
        self.assertTrue(os.path.isfile(bat))
        with open(bat, "rb") as f:
            raw = f.read()
        self.assertIn(b"move /y", raw)
        self.assertIn(pz.NEWLINE_CRLF.encode(), raw)
        self.assertEqual(started["args"][0], "cmd.exe")
        self.assertEqual(started["args"][1], "/c")
        self.assertTrue(started["flags"] & 0x00000008)     # DETACHED_PROCESS
        # nic z tego, co powie nowemu buildowi, gdzie ten się rozpakował
        env = started["env"]
        self.assertIsNotNone(env)
        self.assertNotIn("_MEIPASS2", env)
        self.assertFalse([k for k in env if k.startswith("_PYI")])
        # ... ale reszta środowiska zostaje (PATH, APPDATA itd.)
        self.assertIn("PATH", env)


class TestTranslations(unittest.TestCase):
    def test_every_key_exists_in_both_languages(self):
        en = set(i18n.STRINGS["en"])
        pl = set(i18n.STRINGS["pl"])
        self.assertEqual(sorted(en - pl), [])
        self.assertEqual(sorted(pl - en), [])

    def test_the_repair_dialog_takes_the_count_and_the_list(self):
        for code in ("en", "pl"):
            text = i18n.Translator(code)("dialog.repair.body", 3, "a.class\nb.class")
            self.assertIn("3", text)
            self.assertIn("a.class", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
