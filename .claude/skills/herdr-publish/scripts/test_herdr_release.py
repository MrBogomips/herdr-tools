from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import List, Tuple

import herdr_release
import release_bump as rb
import release_notes
from repo_fixture import TempRepo, render_manifest

NOW = "2026-10-14T14:00:00Z"


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempRepo()
        self.addCleanup(self.repo.close)
        self.repo.add_plugin("sorter")
        self.first = self.repo.commit("feat(sorter): first")
        self.repo.tag("sorter-v0.1.0")
        self.repo.push("sorter-v0.1.0")
        self.index = self.repo.tmp / "index.json"
        self.index.write_text(json.dumps({
            "schemaVersion": 1,
            "generatedAt": "2026-10-14T13:30:00Z",
            "plugins": [{"fullName": "ACME/plugins", "headCommit": self.first,
                         "manifests": [{"path": "sorter/herdr-plugin.toml", "id": "acme.sorter",
                                        "version": "0.1.0"}]}],
        }), encoding="utf-8")

    def cli(self, *argv: str) -> Tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        base: List[str] = ["-C", str(self.repo.root), "--now", NOW, "--index", str(self.index)]
        with redirect_stdout(out), redirect_stderr(err):
            code = herdr_release.main(base + list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_status_as_json(self) -> None:
        self.repo.commit("fix(sorter): keep ~ first", {"sorter/sorter.py": "print('fixed')\n"})
        code, out, _ = self.cli("status", "--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["repo"], "ACME/plugins")
        self.assertEqual(report["plugins"][0]["next_version"], "0.1.1")

    def test_status_for_people(self) -> None:
        self.repo.commit("fix(sorter): keep ~ first", {"sorter/sorter.py": "print('fixed')\n"})
        code, out, _ = self.cli("status")
        self.assertEqual(code, 0)
        for words in ("ACME/plugins", "sorter", "unreleased", "0.1.1", "keep ~ first", "listed 0.1.0"):
            with self.subTest(words=words):
                self.assertIn(words, out)

    def test_status_survives_a_missing_index(self) -> None:
        self.index.unlink()
        code, out, _ = self.cli("status")
        self.assertEqual(code, 0)
        self.assertIn("index unavailable", out)

    def test_preflight_fails_on_errors(self) -> None:
        self.assertEqual(self.cli("preflight", "--no-tests", "--schema-file", "")[0], 0)
        self.repo.write("sorter/herdr-plugin.toml", render_manifest({"id": "acme.sorter", "version": "1.0"}))
        code, out, _ = self.cli("preflight", "--no-tests", "--schema-file", "")
        self.assertEqual(code, 1)
        self.assertIn("version", out)

    def test_notes_list_what_ships(self) -> None:
        self.repo.commit("fix(sorter): keep ~ first", {"sorter/sorter.py": "print('fixed')\n"})
        self.repo.commit("docs(sorter): explain", {"sorter/README.md": "# more\n"})
        code, out, _ = self.cli("notes", "sorter")
        self.assertEqual(code, 0)
        self.assertIn("sorter 0.1.1", out)
        self.assertIn("keep ~ first", out)
        self.assertNotIn("explain", out)

    def test_outside_git_is_a_usage_error(self) -> None:
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = herdr_release.main(["-C", str(self.repo.tmp / "home"), "status"])
        self.assertEqual(code, 2)
        self.assertIn("git", err.getvalue())


class NotesTest(unittest.TestCase):
    def commit(self, subject: str, *paths: str, body: str = "") -> rb.Commit:
        files = tuple(rb.FileChange(path, rb.classify_path(path), True) for path in paths)
        return rb.Commit("abcdef1234567890", subject, body, files)

    def test_groups_shipped_changes_and_drops_the_rest(self) -> None:
        text = release_notes.render("sorter", "0.2.0", [
            self.commit("feat(sorter): sort by date", "sorter.py"),
            self.commit("fix!: rename mode", "sorter.py", body="BREAKING CHANGE: mode is now order"),
            self.commit("perf(sorter): faster", "sorter.py"),
            self.commit("docs(sorter): readme", "README.md"),
            self.commit("test(sorter): more", "test_sorter.py"),
        ])
        self.assertTrue(text.startswith("sorter 0.2.0\n"))
        for heading, line in (("Breaking", "rename mode"), ("Features", "sort by date"), ("Other", "faster")):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)
                self.assertIn("- {} (abcdef1)".format(line), text)
        self.assertNotIn("readme", text)
        self.assertNotIn("more", text)

    def test_says_so_when_nothing_ships(self) -> None:
        text = release_notes.render("sorter", "0.1.0", [self.commit("docs: x", "README.md")])
        self.assertIn("No changes to shipped files", text)


if __name__ == "__main__":
    unittest.main()
