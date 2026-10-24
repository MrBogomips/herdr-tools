from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import FrozenSet, List, Optional

import release_git as rg
import release_preflight as rp
from repo_fixture import FAILING_TEST, TABLES, TempRepo, render_manifest

EVENTS = frozenset({"workspace.created", "workspace.renamed", "pane.updated", "workspace.metadata_updated"})


class PreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempRepo()
        self.addCleanup(self.repo.close)
        self.repo.add_plugin("sorter")
        self.repo.add_plugin("lister")
        self.repo.commit("feat: two plugins")

    def run_preflight(self, plugins: Optional[List[str]] = None, events: Optional[FrozenSet[str]] = EVENTS,
                      index: Optional[dict] = None, tests: bool = False) -> rp.PreflightReport:
        return rp.run(rg.Git(self.repo.root), plugins, index, events, sys.executable, run_tests=tests)

    def messages(self, report: rp.PreflightReport, level: str) -> str:
        return " | ".join(finding.message for finding in report.findings if finding.level == level)

    def test_a_conventional_repo_passes(self) -> None:
        report = self.run_preflight(tests=True)
        self.assertEqual(self.messages(report, "error"), "")
        self.assertTrue(report.ok)
        self.assertIn("tests passed", self.messages(report, "ok"))

    def test_an_unknown_plugin_is_an_error(self) -> None:
        report = self.run_preflight(["sortre"])
        self.assertFalse(report.ok)
        self.assertIn("sortre", self.messages(report, "error"))

    def test_a_failing_test_is_an_error(self) -> None:
        self.repo.write("sorter/test_sorter.py", FAILING_TEST)
        report = self.run_preflight(["sorter"], tests=True)
        self.assertFalse(report.ok)
        self.assertIn("tests failed", self.messages(report, "error"))

    def test_vendored_copies_must_match(self) -> None:
        self.repo.write("lister/herdr_api.py", "API = 2\n")
        self.assertIn("herdr_api.py", self.messages(self.run_preflight(), "error"))

    def test_the_readme_needs_a_row_with_the_install_command(self) -> None:
        readme = (self.repo.root / "README.md").read_text(encoding="utf-8")
        self.repo.write("README.md", readme.replace("`herdr plugin install ACME/plugins/sorter`", "soon"))
        self.assertIn("herdr plugin install ACME/plugins/sorter", self.messages(self.run_preflight(), "error"))
        self.repo.write("README.md", "# plugins\n")
        self.assertIn("README", self.messages(self.run_preflight(["lister"]), "error"))

    def test_a_manifest_outside_a_plugin_folder_would_be_indexed(self) -> None:
        self.repo.commit("test: fixture", {"fixtures/deep/herdr-plugin.toml": 'id = "x"\n'})
        self.assertIn("fixtures/deep/herdr-plugin.toml", self.messages(self.run_preflight(), "error"))

    def test_ids_are_unique_in_the_repo(self) -> None:
        self.repo.write("lister/herdr-plugin.toml", render_manifest({"id": "acme.sorter"}))
        self.assertIn("acme.sorter", self.messages(self.run_preflight(), "error"))

    def test_manifest_errors_are_reported_per_plugin(self) -> None:
        self.repo.write("sorter/herdr-plugin.toml", render_manifest({"id": "acme.sorter", "version": "1.0"}))
        self.assertIn("sorter", self.messages(self.run_preflight(), "error"))
        self.repo.write("sorter/herdr-plugin.toml", 'id = "broken\n')
        self.assertIn("parse", self.messages(self.run_preflight(), "error"))

    def test_hooks_must_name_hookable_events(self) -> None:
        unhookable = TABLES.replace("workspace.created", "pane.updated")
        self.repo.write("sorter/herdr-plugin.toml", render_manifest({"id": "acme.sorter"}, tables=unhookable))
        self.assertIn("pane.updated", self.messages(self.run_preflight(["sorter"]), "error"))
        unhookable = TABLES.replace("workspace.created", "workspace.metadata_updated")
        self.repo.write("sorter/herdr-plugin.toml", render_manifest({"id": "acme.sorter"}, tables=unhookable))
        self.assertIn("workspace.metadata_updated", self.messages(self.run_preflight(["sorter"]), "error"))
        unknown = TABLES.replace("workspace.created", "workspace.exploded")
        self.repo.write("sorter/herdr-plugin.toml", render_manifest({"id": "acme.sorter"}, tables=unknown))
        self.assertIn("workspace.exploded", self.messages(self.run_preflight(["sorter"]), "warn"))

    def test_says_when_the_hooks_name_known_events(self) -> None:
        self.assertIn("sorter: hooks name known events", self.messages(self.run_preflight(["sorter"]), "ok"))

    def test_skips_the_event_check_without_a_schema(self) -> None:
        report = self.run_preflight(["sorter"], events=None)
        self.assertIn("schema", self.messages(report, "info"))

    def test_warns_when_another_listed_repo_uses_the_id(self) -> None:
        index = {"schemaVersion": 1, "plugins": [
            {"fullName": "Globex/tools", "manifests": [{"path": "herdr-plugin.toml", "id": "acme.sorter"}]}]}
        self.assertIn("Globex/tools", self.messages(self.run_preflight(["sorter"], index=index), "warn"))


class SchemaEventsTest(unittest.TestCase):
    def test_reads_subscription_types(self) -> None:
        schema = {"schemas": {"request": {"$defs": {"Subscription": {"oneOf": [
            {"properties": {"type": {"const": "workspace.created"}}},
            {"properties": {"type": {"const": "pane.updated"}}},
        ]}}}}}
        self.assertEqual(rp.schema_events(schema), frozenset({"workspace.created", "pane.updated"}))

    def test_an_unexpected_schema_yields_nothing(self) -> None:
        self.assertIsNone(rp.schema_events({"schemas": {}}))

    def test_loads_a_saved_schema_or_says_why_not(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(tmp))
        saved = tmp / "schema.json"
        saved.write_text(json.dumps({"schemas": {"request": {"$defs": {"Subscription": {"oneOf": [
            {"properties": {"type": {"const": "tab.created"}}}]}}}}}), encoding="utf-8")
        self.assertEqual(rp.load_schema_events(str(saved), "herdr"), (frozenset({"tab.created"}), ""))
        self.assertEqual(rp.load_schema_events("", "herdr")[0], None)
        events, note = rp.load_schema_events(None, str(tmp / "no-herdr"))
        self.assertIsNone(events)
        self.assertIn("cannot read", note)


if __name__ == "__main__":
    unittest.main()
