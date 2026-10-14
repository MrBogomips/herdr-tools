from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest import mock
from urllib.error import URLError

import release_index as ri

OLD = "1" * 40
NEW = "2" * 40
GENERATED = datetime(2026, 10, 14, 13, 30, 19, 180000, tzinfo=timezone.utc)


def index(head: str = OLD) -> dict:
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-10-14T13:30:19.180Z",
        "plugins": [
            {
                "fullName": "ACME/plugins",
                "headCommit": head,
                "manifests": [
                    {"path": "sorter/herdr-plugin.toml", "id": "acme.sorter", "name": "Sorter", "version": "0.1.0"}
                ],
            },
            {"fullName": "Globex/tools", "headCommit": "3" * 40,
             "manifests": [{"path": "herdr-plugin.toml", "id": "acme.sorter", "version": "9.0.0"}]},
        ],
    }


def ancestor(older: str, newer: str) -> bool:
    return (older, newer) == (OLD, NEW)


def state(head: str = OLD, origin: str = NEW, pushed_at: Optional[datetime] = None,
          committed_at: Optional[datetime] = None, now: Optional[datetime] = None) -> ri.IndexState:
    return ri.repo_state(index(head), "acme/PLUGINS", origin, ancestor, now or GENERATED,
                         pushed_at=pushed_at, committed_at=committed_at)


class LoadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.tmp))

    def test_reads_a_file(self) -> None:
        path = self.tmp / "index.json"
        path.write_text(json.dumps(index()), encoding="utf-8")
        self.assertEqual(ri.load(str(path))["schemaVersion"], 1)

    def test_fetches_a_url_with_a_user_agent(self) -> None:
        # The CDN answers 403 to urllib's default User-Agent.
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(index()).encode("utf-8")
        with mock.patch.object(ri.urllib.request, "urlopen", return_value=response) as urlopen:
            self.assertEqual(ri.load("https://example.invalid/index.json")["schemaVersion"], 1)
        request = urlopen.call_args[0][0]
        self.assertTrue(request.get_header("User-agent"))

    def test_falls_back_to_curl_when_urllib_fails(self) -> None:
        # python.org builds without "Install Certificates" cannot verify TLS; curl uses the system store.
        done = subprocess.CompletedProcess([], 0, stdout=json.dumps(index()), stderr="")
        with mock.patch.object(ri.urllib.request, "urlopen", side_effect=URLError("CERTIFICATE_VERIFY_FAILED")), \
                mock.patch.object(ri.shutil, "which", return_value="/usr/bin/curl"), \
                mock.patch.object(ri.subprocess, "run", return_value=done) as run:
            self.assertEqual(ri.load("https://example.invalid/index.json")["schemaVersion"], 1)
        self.assertEqual(run.call_args[0][0][0], "/usr/bin/curl")

    def test_reports_both_failures(self) -> None:
        failed = subprocess.CompletedProcess([], 6, stdout="", stderr="curl: (6) Could not resolve host")
        with mock.patch.object(ri.urllib.request, "urlopen", side_effect=URLError("offline")), \
                mock.patch.object(ri.shutil, "which", return_value="/usr/bin/curl"), \
                mock.patch.object(ri.subprocess, "run", return_value=failed):
            with self.assertRaises(ri.IndexLoadError) as caught:
                ri.load("https://example.invalid/index.json")
        self.assertIn("offline", str(caught.exception))
        self.assertIn("Could not resolve host", str(caught.exception))

    def test_rejects_what_is_not_an_index(self) -> None:
        for name, text in (("bad.json", "{"), ("other.json", '{"plugins": {}}'), ("none.json", None)):
            with self.subTest(name=name):
                if text is not None:
                    (self.tmp / name).write_text(text, encoding="utf-8")
                with self.assertRaises(ri.IndexLoadError):
                    ri.load(str(self.tmp / name))


class FindTest(unittest.TestCase):
    def test_matches_the_repo_case_insensitively(self) -> None:
        self.assertEqual(ri.find_repo(index(), "acme/PLUGINS")["fullName"], "ACME/plugins")
        self.assertIsNone(ri.find_repo(index(), "Initech/other"))

    def test_lists_other_repos_using_an_id(self) -> None:
        self.assertEqual(ri.other_repos_with_id(index(), "ACME/plugins", "acme.sorter"), ["Globex/tools"])
        self.assertEqual(ri.other_repos_with_id(index(), "ACME/plugins", "acme.unique"), [])

    def test_maps_listed_manifests_by_path(self) -> None:
        listed = ri.listed_manifests(ri.find_repo(index(), "ACME/plugins"))
        self.assertEqual(listed["sorter/herdr-plugin.toml"]["version"], "0.1.0")

    def test_parses_index_timestamps(self) -> None:
        self.assertEqual(ri.parse_time("2026-10-14T13:30:19.180Z"), GENERATED)
        self.assertIsNone(ri.parse_time("yesterday"))


class StateTest(unittest.TestCase):
    def test_current_when_the_index_has_origin_main(self) -> None:
        self.assertEqual(state(head=NEW, origin=NEW).name, "current")

    def test_pending_when_this_checkout_pushed_after_the_last_refresh(self) -> None:
        result = state(pushed_at=GENERATED + timedelta(minutes=5), now=GENERATED + timedelta(minutes=10))
        self.assertEqual((result.name, result.certain), ("pending", True))
        self.assertEqual(result.next_refresh, GENERATED + timedelta(minutes=30))
        self.assertFalse(result.overdue)

    def test_pending_when_the_head_commit_is_newer_than_the_refresh(self) -> None:
        # A commit cannot be pushed before it exists, so its date bounds the push time from below.
        result = state(committed_at=GENERATED + timedelta(minutes=3))
        self.assertEqual((result.name, result.certain), ("pending", True))

    def test_pending_is_overdue_well_after_the_next_refresh(self) -> None:
        result = state(pushed_at=GENERATED + timedelta(minutes=5), now=GENERATED + timedelta(minutes=50))
        self.assertTrue(result.overdue)

    def test_an_unknown_push_time_is_said_not_assumed(self) -> None:
        # Cloned or fetched, not pushed from here: the refresh may already have seen the push.
        result = state(committed_at=GENERATED - timedelta(hours=1))
        self.assertEqual((result.name, result.certain), ("pending", False))
        self.assertIn("unknown", result.message)

    def test_lagging_when_a_refresh_after_the_push_kept_the_old_head(self) -> None:
        self.assertEqual(state(pushed_at=GENERATED - timedelta(minutes=5)).name, "lagging")

    def test_diverged_when_the_listed_head_is_not_an_ancestor(self) -> None:
        self.assertEqual(state(head="9" * 40).name, "diverged")

    def test_missing_when_the_repo_is_not_listed(self) -> None:
        result = ri.repo_state(index(), "Initech/other", NEW, ancestor, GENERATED)
        self.assertEqual(result.name, "missing")


if __name__ == "__main__":
    unittest.main()
