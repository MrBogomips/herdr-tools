from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Optional

import release_git as rg
import release_status as rs
from repo_fixture import TempRepo, render_manifest

NOW = datetime(2026, 10, 14, 14, 0, tzinfo=timezone.utc)


class StatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempRepo()
        self.addCleanup(self.repo.close)
        self.repo.add_plugin("sorter")
        self.first = self.repo.commit("feat(sorter): first")
        self.repo.tag("sorter-v0.1.0")
        self.repo.push("sorter-v0.1.0")

    def build(self, index: Optional[dict] = None) -> rs.StatusReport:
        return rs.build(rg.Git(self.repo.root), None, index, NOW)

    def plugin(self, index: Optional[dict] = None) -> rs.PluginStatus:
        return self.build(index).plugins[0]

    def manifest(self, version: str) -> dict:
        return {"sorter/herdr-plugin.toml": render_manifest({"version": version})}

    def test_an_untagged_plugin_is_a_first_release(self) -> None:
        self.repo.git("tag", "-d", "sorter-v0.1.0")
        status = self.plugin()
        self.assertEqual(status.state, "untagged")
        self.assertEqual(status.next_version, "0.1.0")

    def test_docs_only_changes_leave_the_plugin_released(self) -> None:
        self.repo.commit("docs(sorter): more", {"sorter/README.md": "# more\n"})
        status = self.plugin()
        self.assertEqual(status.state, "released")
        self.assertEqual(status.level, "none")
        self.assertEqual(len(status.commits), 1)

    def test_a_code_fix_is_unreleased_with_the_next_patch(self) -> None:
        self.repo.commit("fix(sorter): keep ~ first", {"sorter/sorter.py": "print('fixed')\n"})
        status = self.plugin()
        self.assertEqual(status.state, "unreleased")
        self.assertEqual((status.level, status.next_version), ("patch", "0.1.1"))

    def test_a_bumped_manifest_waits_for_its_tag_on_the_release_commit(self) -> None:
        self.repo.commit("fix(sorter): keep ~ first", {"sorter/sorter.py": "print('fixed')\n"})
        release = self.repo.commit("chore(sorter): release v0.1.1", self.manifest("0.1.1"))
        status = self.plugin()
        self.assertEqual(status.state, "tag-pending")
        self.assertEqual((status.next_version, status.tag_commit), ("0.1.1", release))
        self.assertEqual([commit.subject for commit in status.commits], ["fix(sorter): keep ~ first"])

    def test_a_bump_on_a_feature_branch_awaits_the_merge(self) -> None:
        # A squash merge creates a new commit: a tag on the branch commit would point outside main.
        self.repo.git("switch", "-q", "-c", "feature/x")
        self.repo.commit("fix(sorter): keep ~ first", {"sorter/sorter.py": "print('fixed')\n"})
        self.repo.commit("chore(sorter): release v0.1.1", self.manifest("0.1.1"))
        status = self.plugin()
        self.assertEqual(status.state, "awaiting-merge")
        self.assertIsNone(status.tag_commit)

    def test_a_new_plugin_on_a_branch_awaits_the_merge(self) -> None:
        self.repo.git("switch", "-q", "-c", "feature/lister")
        self.repo.add_plugin("lister")
        self.repo.commit("feat(lister): list things")
        status = rs.build(rg.Git(self.repo.root), ["lister"], None, NOW).plugins[0]
        self.assertEqual((status.state, status.next_version), ("awaiting-merge", "0.1.0"))

    def test_an_uncommitted_bump_is_a_problem(self) -> None:
        self.repo.write("sorter/herdr-plugin.toml", render_manifest({"version": "0.1.1"}))
        status = self.plugin()
        self.assertEqual(status.state, "error")
        self.assertTrue(any("not committed" in problem for problem in status.problems), status.problems)

    def test_commits_after_the_bump_stay_out_of_the_release(self) -> None:
        fix = self.repo.commit("fix(sorter): keep ~ first", {"sorter/sorter.py": "print('fixed')\n"})
        release = self.repo.commit("chore(sorter): release v0.1.1", self.manifest("0.1.1"))
        later = self.repo.commit("feat(sorter): by date", {"sorter/sorter.py": "print('date')\n"})
        status = self.plugin()
        self.assertEqual((status.state, status.tag_commit), ("tag-pending", release))
        self.assertEqual([commit.sha for commit in status.commits], [fix])
        self.assertEqual([commit.sha for commit in status.later], [later])
        warnings = " ".join(status.warnings)
        self.assertNotIn("0.2.0", warnings)
        self.assertIn("after the bump", warnings)

    def test_says_when_origin_cannot_be_checked(self) -> None:
        self.repo.git("config", "--remove-section", "url.{}".format(self.repo.bare))
        self.repo.git("config", "url.{}.insteadOf".format(self.repo.tmp / "gone.git"), self.repo.url)
        warnings = " ".join(self.plugin().warnings)
        self.assertIn("could not check", warnings)

    def test_a_bump_smaller_than_suggested_is_a_warning(self) -> None:
        self.repo.commit("feat(sorter): by date", {"sorter/sorter.py": "print('date')\n"})
        self.repo.commit("chore(sorter): release v0.1.1", self.manifest("0.1.1"))
        warnings = self.plugin().warnings
        self.assertTrue(any("0.2.0" in warning for warning in warnings), warnings)

    def test_a_tag_ahead_of_the_manifest_is_an_error(self) -> None:
        self.repo.tag("sorter-v0.2.0")
        status = self.plugin()
        self.assertEqual(status.state, "error")
        self.assertTrue(status.problems)

    def test_warns_about_unpushed_lightweight_or_orphaned_tags(self) -> None:
        self.repo.git("switch", "-q", "-c", "feature/x")
        self.repo.commit("fix(sorter): branch only", {"sorter/sorter.py": "print('b')\n"})
        self.repo.commit("chore(sorter): release v0.1.1", self.manifest("0.1.1"))
        self.repo.tag("sorter-v0.1.1", annotated=False)
        warnings = " ".join(self.plugin().warnings)
        for words in ("not on origin", "lightweight", "not reachable from origin/main"):
            with self.subTest(words=words):
                self.assertIn(words, warnings)

    def test_shows_the_description_next_to_the_readme_row(self) -> None:
        status = self.plugin()
        self.assertEqual(status.description, "Sort things.")
        self.assertEqual(status.readme_row, "Does sorter things")

    def test_the_git_gate_flags_a_dirty_tree_and_unpushed_commits(self) -> None:
        self.assertEqual(self.build().gate.problems, ())
        self.repo.commit("fix: local", {"sorter/sorter.py": "print('local')\n"})
        self.repo.write("sorter/scratch.py", "x = 1\n")
        problems = " ".join(self.build().gate.problems)
        self.assertIn("uncommitted", problems)
        self.assertIn("ahead", problems)

    def test_reads_the_listing_from_the_index(self) -> None:
        index = {
            "schemaVersion": 1,
            "generatedAt": "2026-10-14T13:30:00Z",
            "plugins": [{"fullName": "ACME/plugins", "headCommit": self.first,
                         "manifests": [{"path": "sorter/herdr-plugin.toml", "id": "acme.sorter",
                                        "version": "0.1.0"}]}],
        }
        report = self.build(index)
        self.assertEqual(report.index.name, "current")
        self.assertEqual(report.plugins[0].listed_version, "0.1.0")

    def test_flags_an_index_that_misreads_the_listed_manifest(self) -> None:
        index = {
            "schemaVersion": 1,
            "generatedAt": "2026-10-14T13:30:00Z",
            "plugins": [{"fullName": "ACME/plugins", "headCommit": self.first,
                         "manifests": [{"path": "sorter/herdr-plugin.toml", "id": "sort", "version": "0.1.0",
                                        "description": "Sort things."}]}],
        }
        warnings = " ".join(self.plugin(index).warnings)
        self.assertIn("'sort'", warnings)
        self.assertIn("'acme.sorter'", warnings)

    def test_rejects_an_unknown_plugin(self) -> None:
        with self.assertRaises(rs.StatusError):
            rs.build(rg.Git(self.repo.root), ["nope"], None, NOW)


if __name__ == "__main__":
    unittest.main()
