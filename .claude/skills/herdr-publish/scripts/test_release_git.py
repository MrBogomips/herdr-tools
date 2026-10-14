from __future__ import annotations

import subprocess
import time
import unittest

import release_git as rg
from repo_fixture import TempRepo


class SlugTest(unittest.TestCase):
    def test_parses_github_urls(self) -> None:
        cases = {
            "https://github.com/ACME/plugins.git": ("ACME", "plugins"),
            "https://github.com/ACME/plugins": ("ACME", "plugins"),
            "git@github.com:ACME/plugins.git": ("ACME", "plugins"),
            "ssh://git@github.com/ACME/plugins.git": ("ACME", "plugins"),
            "/srv/git/plugins.git": None,
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(rg.parse_slug(url), expected)


class GitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempRepo()
        self.addCleanup(self.repo.close)
        self.repo.add_plugin("sorter")
        self.first = self.repo.commit("feat(sorter): first")
        self.repo.push()
        self.git = rg.Git(self.repo.root / "sorter")

    def test_finds_the_top_level_and_the_slug_behind_insteadof(self) -> None:
        self.assertEqual(self.git.root, self.repo.root)
        self.assertEqual(self.git.slug(), ("ACME", "plugins"))

    def test_refuses_a_folder_outside_git(self) -> None:
        with self.assertRaises(rg.GitError):
            rg.Git(self.repo.tmp / "home")

    def test_lists_plugin_tags_strictly_in_semver_order(self) -> None:
        for name in ("sorter-v0.1.0", "sorter-v0.10.0", "sorter-v0.2.0", "sorterx-v1.0.0"):
            self.repo.tag(name)
        self.repo.tag("sorter-vim", annotated=False)
        tags = self.git.plugin_tags("sorter")
        self.assertEqual([tag.name for tag in tags], ["sorter-v0.1.0", "sorter-v0.2.0", "sorter-v0.10.0"])
        self.assertEqual(tags[-1].version, (0, 10, 0))
        self.assertEqual(tags[-1].commit, self.first)
        self.assertTrue(tags[-1].annotated)

    def test_tells_lightweight_tags_apart(self) -> None:
        self.repo.tag("sorter-v0.1.0", annotated=False)
        self.assertFalse(self.git.plugin_tags("sorter")[0].annotated)

    def test_lists_commits_touching_a_folder_with_relative_paths(self) -> None:
        self.repo.commit("fix(sorter): x", {"sorter/sorter.py": "print('x')\n"})
        self.repo.commit("docs: root", {"README.md": "# changed\n"})
        self.repo.commit("docs(sorter): y", {"sorter/README.md": "# y\n"})
        commits = self.git.commits_touching(self.first, "HEAD", "sorter")
        self.assertEqual([commit.subject for commit in commits], ["fix(sorter): x", "docs(sorter): y"])
        self.assertEqual(commits[0].paths, ("sorter.py",))
        self.assertEqual(commits[1].paths, ("README.md",))

    def test_lists_all_commits_without_an_anchor(self) -> None:
        self.assertEqual(len(self.git.commits_touching(None, "HEAD", "sorter")), 1)

    def test_shows_files_at_a_revision(self) -> None:
        self.assertEqual(self.git.show_file(self.first, "sorter/sorter.py"), "print('sort')\n")
        self.assertIsNone(self.git.show_file(self.first, "sorter/missing.py"))

    def test_reports_ancestry(self) -> None:
        second = self.repo.commit("fix: z", {"sorter/sorter.py": "print(2)\n"})
        self.assertTrue(self.git.is_ancestor(self.first, second))
        self.assertFalse(self.git.is_ancestor(second, self.first))

    def test_reports_tree_and_branch_state(self) -> None:
        self.assertTrue(self.git.is_clean())
        self.assertEqual(self.git.branch(), "main")
        self.assertEqual(self.git.ahead_behind("main", "origin/main"), (0, 0))
        self.repo.commit("fix: local", {"sorter/sorter.py": "print(3)\n"})
        self.assertEqual(self.git.ahead_behind("main", "origin/main"), (1, 0))
        self.repo.write("sorter/new.py", "x = 1\n")
        self.assertFalse(self.git.is_clean())

    def test_knows_which_tags_reached_origin(self) -> None:
        self.repo.tag("sorter-v0.1.0")
        self.assertNotIn("sorter-v0.1.0", self.git.remote_tags())
        self.repo.push("sorter-v0.1.0")
        self.assertIn("sorter-v0.1.0", self.git.remote_tags())

    def test_dates_a_push_made_from_this_checkout(self) -> None:
        when = self.git.push_time("refs/remotes/origin/main", self.first)
        self.assertIsNotNone(when)
        self.assertLess(abs(when.timestamp() - time.time()), 120)

    def test_a_fetched_head_has_no_push_time(self) -> None:
        other = self.repo.tmp / "other"
        self.repo.git("clone", "-q", str(self.repo.bare), str(other))
        rg_other = ["git", "-C", str(other)]
        subprocess.run(rg_other + ["commit", "-q", "--allow-empty", "-m", "elsewhere"], check=True)
        subprocess.run(rg_other + ["push", "-q", "origin", "main"], check=True)
        self.repo.git("fetch", "-q", "origin")
        head = self.repo.git("rev-parse", "origin/main")
        self.assertIsNone(self.git.push_time("refs/remotes/origin/main", head))
        self.assertIsNotNone(self.git.commit_time(head))

    def test_finds_the_last_commit_that_changed_the_version(self) -> None:
        manifest = (self.repo.root / "sorter/herdr-plugin.toml").read_text(encoding="utf-8")
        bumped = self.repo.commit("chore(sorter): release v0.1.1",
                                  {"sorter/herdr-plugin.toml": manifest.replace('"0.1.0"', '"0.1.1"')})
        self.repo.commit("docs(sorter): later", {"sorter/README.md": "# later\n"})
        self.assertEqual(self.git.last_version_change(self.first, "HEAD", "sorter/herdr-plugin.toml"), bumped)

    def test_lists_tracked_manifests(self) -> None:
        self.repo.commit("test: fixture", {"fixtures/deep/herdr-plugin.toml": 'id = "x"\n'})
        self.assertEqual(self.git.tracked("herdr-plugin.toml"),
                         ["fixtures/deep/herdr-plugin.toml", "sorter/herdr-plugin.toml"])

    def test_detects_a_linked_worktree(self) -> None:
        self.assertFalse(self.git.in_linked_worktree())
        linked = self.repo.tmp / "linked"
        self.repo.git("worktree", "add", "-q", "-b", "feature/x", str(linked))
        self.assertTrue(rg.Git(linked).in_linked_worktree())

    def test_a_fetch_in_the_main_checkout_counts_in_linked_worktrees(self) -> None:
        # FETCH_HEAD is per worktree, but remote-tracking refs are shared by all of them.
        self.assertIsNone(self.git.fetch_time())
        self.repo.git("fetch", "-q", "origin")
        linked = self.repo.tmp / "linked"
        self.repo.git("worktree", "add", "-q", "-b", "feature/y", str(linked))
        self.assertIsNotNone(rg.Git(linked).fetch_time())


if __name__ == "__main__":
    unittest.main()
