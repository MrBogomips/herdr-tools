from __future__ import annotations

import unittest
from pathlib import Path
from typing import Callable, Iterator, List, Tuple

import release_manifest as rm
from repo_fixture import TABLES, render_manifest

REPO_ROOT = Path(__file__).resolve().parents[4]

FULL = '''# comment
id = "acme.sorter"   # trailing comment
name = "Sorter"
version = "0.1.0"
min_herdr_version = "0.9.3"
description = "Sort # not a comment"
platforms = [
  "macos",   # first
  "linux",
]

[[actions]]
id = "sort"
command = ["python3", "sorter.py"]

[[actions]]
id = "clear"
command = ["python3", "sorter.py", "clear"]

[[events]]
on = "workspace.created"
command = ["python3", "sorter.py"]

[[startup]]
command = ["python3", "sorter.py"]

[[panes]]
id = "board"
'''


def parsers() -> Iterator[Tuple[str, Callable[[str], dict]]]:
    yield "fallback", lambda text: rm.parse(text, use_tomllib=False)
    if rm.tomllib is not None:
        yield "tomllib", rm.parse


class ParseTest(unittest.TestCase):
    def test_reads_top_level_keys_and_arrays_of_tables(self) -> None:
        for label, parse in parsers():
            with self.subTest(parser=label):
                data = parse(FULL)
                self.assertEqual(data["id"], "acme.sorter")
                self.assertEqual(data["description"], "Sort # not a comment")
                self.assertEqual(data["platforms"], ["macos", "linux"])
                self.assertEqual([action["id"] for action in data["actions"]], ["sort", "clear"])
                self.assertEqual(data["events"][0]["on"], "workspace.created")
                self.assertEqual(len(data["startup"]), 1)

    def test_rejects_malformed_text(self) -> None:
        broken = ('id = "unterminated\n', 'id = "a"\nid = "b"\n', "just words\n", 'platforms = ["a",\n')
        for label, parse in parsers():
            for text in broken:
                with self.subTest(parser=label, text=text):
                    with self.assertRaises(rm.ManifestError):
                        parse(text)

    def test_the_fallback_agrees_with_tomllib_on_the_repo_manifests(self) -> None:
        if rm.tomllib is None:
            self.skipTest("tomllib needs Python 3.11+")
        manifests = sorted(REPO_ROOT.glob("*/herdr-plugin.toml"))
        if not manifests:
            self.skipTest("no plugin manifests next to this skill")
        for path in manifests:
            text = path.read_text(encoding="utf-8")
            with self.subTest(manifest=path.parent.name):
                self.assertEqual(rm.parse(text, use_tomllib=False), rm.parse(text))


class SummariseTest(unittest.TestCase):
    def test_collects_the_metadata_the_bump_heuristic_compares(self) -> None:
        summary = rm.summarise(rm.parse(FULL, use_tomllib=False))
        self.assertEqual(summary.id, "acme.sorter")
        self.assertEqual(summary.version, "0.1.0")
        self.assertEqual(summary.min_herdr_version, "0.9.3")
        self.assertEqual(summary.platforms, frozenset({"macos", "linux"}))
        self.assertEqual(summary.actions, frozenset({"sort", "clear"}))
        self.assertEqual(summary.events, ("workspace.created",))
        self.assertEqual(summary.panes, frozenset({"board"}))
        self.assertEqual(summary.startup, 1)

    def test_tolerates_missing_keys(self) -> None:
        summary = rm.summarise({})
        self.assertIsNone(summary.version)
        self.assertEqual(summary.actions, frozenset())


class CheckTest(unittest.TestCase):
    def errors(self, text: str, folder: str = "sorter", owner: str = "ACME") -> List[str]:
        findings = rm.check(rm.parse(text, use_tomllib=False), folder, owner)
        return [finding.message for finding in findings if finding.level == "error"]

    def test_a_complete_manifest_passes(self) -> None:
        self.assertEqual(self.errors(render_manifest()), [])

    def test_reports_each_missing_key(self) -> None:
        for key in ("id", "name", "version", "min_herdr_version", "description", "platforms"):
            with self.subTest(key=key):
                errors = self.errors(render_manifest(drop=[key]))
                self.assertTrue(any(key in error for error in errors), errors)

    def test_versions_must_be_plain_semver(self) -> None:
        for key, value in (("version", "1.0"), ("version", "v1.0.0"), ("min_herdr_version", "0.9")):
            with self.subTest(key=key, value=value):
                errors = self.errors(render_manifest({key: value}))
                self.assertTrue(any(key in error for error in errors), errors)

    def test_the_id_is_the_owner_dot_folder(self) -> None:
        errors = self.errors(render_manifest({"id": "globex.sorter"}))
        self.assertTrue(any("acme.sorter" in error for error in errors), errors)

    def test_platforms_must_be_known_and_not_empty(self) -> None:
        for platforms in ([], ["macos", "beos"], "macos"):
            with self.subTest(platforms=platforms):
                self.assertTrue(self.errors(render_manifest({"platforms": platforms})))

    def test_local_ids_have_no_dots(self) -> None:
        tables = TABLES.replace('id = "sort"', 'id = "so.rt"')
        errors = self.errors(render_manifest(tables=tables))
        self.assertTrue(any("so.rt" in error for error in errors), errors)

    def test_an_empty_description_is_an_error(self) -> None:
        self.assertTrue(self.errors(render_manifest({"description": "  "})))


if __name__ == "__main__":
    unittest.main()
