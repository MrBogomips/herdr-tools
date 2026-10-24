from __future__ import annotations

import unittest
from typing import Iterable, Optional, Tuple

import release_bump as rb
import release_manifest as rm
from repo_fixture import TABLES, render_manifest

SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"


def commit(subject: str, *files: Tuple[str, bool], body: str = "") -> rb.Commit:
    """A commit touching (path, semantic) files of the plugin folder."""
    changes = tuple(rb.FileChange(path, rb.classify_path(path), semantic) for path, semantic in files)
    return rb.Commit(SHA, subject, body, changes)


def summary(overrides: Optional[dict] = None, tables: str = TABLES) -> rm.Summary:
    return rm.summarise(rm.parse(render_manifest(overrides, tables=tables), use_tomllib=False))


def suggest(commits: Iterable[rb.Commit], old: Optional[rm.Summary] = None, new: Optional[rm.Summary] = None,
            old_keys: Iterable[str] = ("mode",), new_keys: Iterable[str] = ("mode",)) -> rb.Suggestion:
    old = old or summary()
    return rb.suggest(list(commits), old, new or old, frozenset(old_keys), frozenset(new_keys))


class VersionTest(unittest.TestCase):
    def test_parses_plain_semver_only(self) -> None:
        self.assertEqual(rb.parse_version("0.2.10"), (0, 2, 10))
        for text in ("v1.0.0", "1.0", "1.0.0-rc.1", "", None):
            with self.subTest(text=text):
                self.assertIsNone(rb.parse_version(text))

    def test_bumps_with_breaking_as_minor_before_1_0(self) -> None:
        cases = [
            ("0.2.0", "patch", "0.2.1"),
            ("0.2.3", "minor", "0.3.0"),
            ("0.2.3", "breaking", "0.3.0"),
            ("1.4.2", "patch", "1.4.3"),
            ("1.4.2", "minor", "1.5.0"),
            ("1.4.2", "breaking", "2.0.0"),
            ("1.4.2", "none", "1.4.2"),
        ]
        for version, level, expected in cases:
            with self.subTest(version=version, level=level):
                self.assertEqual(rb.bump(version, level), expected)

    def test_tells_a_version_that_can_carry_a_breaking_change(self) -> None:
        cases = [
            ("0.1.0", "0.1.1", False),
            ("0.1.0", "0.2.0", True),
            ("0.9.3", "1.0.0", True),
            ("1.2.3", "1.3.0", False),
            ("1.2.3", "2.0.0", True),
            ("1.0", "1.1.0", True),  # unreadable: assume it can, the notes then keep the Breaking section
            ("1.2.3", "next", True),
        ]
        for previous, version, expected in cases:
            with self.subTest(previous=previous, version=version):
                self.assertEqual(rb.allows_breaking(previous, version), expected)


class ConventionalTest(unittest.TestCase):
    def test_reads_type_scope_and_breaking_marks(self) -> None:
        cases = [
            ("fix(space-herder): keep ~ first", "", ("fix", "space-herder", False)),
            ("feat!: drop the clear action", "", ("feat", None, True)),
            ("refactor(x): rename keys", "BREAKING CHANGE: assign is now mode", ("refactor", "x", True)),
            ("Update README", "", (None, None, False)),
        ]
        for subject, body, expected in cases:
            with self.subTest(subject=subject):
                self.assertEqual(rb.conventional(subject, body), expected)

    def test_spots_release_commits(self) -> None:
        self.assertTrue(rb.is_release_commit("chore(space-herder): release v0.1.1"))
        self.assertTrue(rb.is_release_commit("chore(release): space-herder v0.1.1, auto-tab-name v0.2.1"))
        self.assertFalse(rb.is_release_commit("chore(space-herder): tidy imports"))
        self.assertFalse(rb.is_release_commit("chore(space-herder): release the lock before sorting"))


class ClassifyPathTest(unittest.TestCase):
    def test_sorts_files_into_what_ships_and_what_does_not(self) -> None:
        cases = {
            "README.md": "docs",
            "docs/sidebar.png": "docs",
            "test_sorter.py": "tests",
            "test_herdr_api.py": "tests",
            "herdr-plugin.toml": "manifest",
            "config.example.json": "config",
            "sorter.py": "code",
            "herdr_api.py": "code",
            "lib/helpers.py": "code",
        }
        for path, kind in cases.items():
            with self.subTest(path=path):
                self.assertEqual(rb.classify_path(path), kind)


class SemanticChangeTest(unittest.TestCase):
    def test_ignores_comments_and_formatting(self) -> None:
        self.assertFalse(rb.semantic_change("a.py", "x = 1\n", "# why\nx = 1  # same\n"))
        self.assertFalse(rb.semantic_change("config.example.json", '{"a": 1}', '{\n  "a": 1\n}\n'))
        self.assertFalse(rb.semantic_change("herdr-plugin.toml", 'id = "a"\n', '# note\nid = "a"\n'))

    def test_sees_real_changes(self) -> None:
        self.assertTrue(rb.semantic_change("a.py", "x = 1\n", "x = 2\n"))
        self.assertTrue(rb.semantic_change("a.py", None, "x = 1\n"))
        self.assertTrue(rb.semantic_change("a.py", "x = 1\n", None))
        self.assertTrue(rb.semantic_change("a.py", "x = 1\n", "def (:\n"))
        self.assertTrue(rb.semantic_change("run.sh", "echo a\n", "echo b\n"))


class SuggestTest(unittest.TestCase):
    def test_docs_and_tests_alone_need_no_release(self) -> None:
        result = suggest([commit("docs(sorter): explain sorting", ("README.md", True), ("test_sorter.py", True))])
        self.assertEqual(result.level, "none")

    def test_a_fix_to_code_is_a_patch(self) -> None:
        result = suggest([commit("fix(sorter): keep ~ first", ("sorter.py", True))])
        self.assertEqual(result.level, "patch")
        self.assertTrue(any(SHA[:7] in reason for reason in result.reasons))

    def test_a_feature_is_minor(self) -> None:
        self.assertEqual(suggest([commit("feat(sorter): sort by date", ("sorter.py", True))]).level, "minor")

    def test_a_breaking_mark_is_breaking(self) -> None:
        self.assertEqual(suggest([commit("fix!: new config", ("sorter.py", True))]).level, "breaking")

    def test_comment_only_code_changes_need_no_release(self) -> None:
        self.assertEqual(suggest([commit("fix(sorter): typo in comment", ("sorter.py", False))]).level, "none")

    def test_a_docs_commit_that_changes_code_is_flagged_and_counted(self) -> None:
        result = suggest([commit("docs(sorter): clarify", ("sorter.py", True))])
        self.assertEqual(result.level, "patch")
        self.assertTrue(any("docs" in flag for flag in result.flags), result.flags)

    def test_removing_an_action_breaks_key_bindings(self) -> None:
        new = summary(tables=TABLES.replace('id = "sort"', 'id = "order"'))
        result = suggest([commit("refactor(sorter): rename", ("herdr-plugin.toml", True))], new=new)
        self.assertEqual(result.level, "breaking")
        # The breaking reasons name the exact binding users must change, for the release notes.
        self.assertTrue(any("acme.sorter.sort" in reason for reason in result.breaking), result.breaking)
        self.assertFalse(any("adds" in reason for reason in result.breaking), result.breaking)

    def test_removing_a_config_key_is_breaking(self) -> None:
        result = suggest([commit("fix(sorter): x", ("config.example.json", True))], new_keys=("other",))
        self.assertEqual(result.level, "breaking")

    def test_raising_min_herdr_version_is_breaking(self) -> None:
        new = summary({"min_herdr_version": "0.9.4"})
        result = suggest([commit("fix(sorter): x", ("herdr-plugin.toml", True))], new=new)
        self.assertEqual(result.level, "breaking")

    def test_dropping_a_platform_is_breaking(self) -> None:
        new = summary({"platforms": ["macos"]})
        result = suggest([commit("fix(sorter): x", ("herdr-plugin.toml", True))], new=new)
        self.assertEqual(result.level, "breaking")

    def test_additions_are_minor(self) -> None:
        added_action = TABLES + '\n[[actions]]\nid = "clear"\ncommand = ["python3", "sorter.py"]\n'
        cases = {
            "action": dict(new=summary(tables=added_action)),
            "config key": dict(new_keys=("mode", "extra")),
        }
        for label, change in cases.items():
            with self.subTest(change=label):
                result = suggest([commit("fix(sorter): x", ("herdr-plugin.toml", True))], **change)
                self.assertEqual(result.level, "minor")

    def test_contract_changes_count_even_without_a_listed_commit(self) -> None:
        # Release commits are left out of the commit list, but what they change in the manifest still counts.
        new = summary({"min_herdr_version": "0.9.4"})
        result = suggest([], new=new)
        self.assertEqual(result.level, "breaking")
        self.assertTrue(result.breaking)

    def test_breaking_reasons_hold_only_contract_breaks(self) -> None:
        # A `!` is already in the commit's own line of the notes; repeating it as a reason says nothing new.
        result = suggest([commit("feat(plugins)!: require Herdr 0.9.5", ("sorter.py", True))])
        self.assertEqual(result.level, "breaking")
        self.assertEqual(result.breaking, ())

    def test_the_highest_signal_wins(self) -> None:
        commits = [commit("fix: a", ("sorter.py", True)), commit("feat: b", ("sorter.py", True))]
        self.assertEqual(suggest(commits).level, "minor")


if __name__ == "__main__":
    unittest.main()
