import tempfile
import unittest
from pathlib import Path
from typing import Optional

from gitinfo import RepoInfo, find_repo

SHA = "0123456789abcdef0123456789abcdef01234567"


class GitInfoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)

    def make_repo(self, name: str, head: Optional[str] = "ref: refs/heads/main\n") -> Path:
        root = self.dir / name
        (root / ".git").mkdir(parents=True)
        if head is not None:
            (root / ".git" / "HEAD").write_text(head, encoding="utf-8")
        return root

    def make_gitdir(self, path: Path, head: str = "ref: refs/heads/main\n", commondir: Optional[str] = None) -> Path:
        path.mkdir(parents=True)
        (path / "HEAD").write_text(head, encoding="utf-8")
        if commondir is not None:
            (path / "commondir").write_text(commondir + "\n", encoding="utf-8")
        return path

    def make_checkout(self, root: Path, gitdir_line: str) -> Path:
        root.mkdir(parents=True)
        (root / ".git").write_text(gitdir_line, encoding="utf-8")
        return root


class PlainRepoTests(GitInfoTestCase):
    def test_repo_root_name_and_branch(self) -> None:
        root = self.make_repo("ACME")
        self.assertEqual(find_repo(root), RepoInfo(name="ACME", root=root, ref="main"))

    def test_walks_up_from_a_subfolder(self) -> None:
        root = self.make_repo("ACME")
        sub = root / "src" / "lib"
        sub.mkdir(parents=True)
        info = find_repo(sub)
        self.assertEqual((info.name, info.root), ("ACME", root))

    def test_walks_up_from_a_missing_folder(self) -> None:
        root = self.make_repo("ACME")
        info = find_repo(root / "gone" / "deeper")
        self.assertEqual(info.root, root)

    def test_trailing_parts_are_normalised(self) -> None:
        root = self.make_repo("ACME")
        self.assertEqual(find_repo(root / "src" / "..").root, root)

    def test_branch_with_slash_is_kept(self) -> None:
        root = self.make_repo("ACME", "ref: refs/heads/feature/x\n")
        self.assertEqual(find_repo(root).ref, "feature/x")

    def test_other_ref_is_kept_whole(self) -> None:
        root = self.make_repo("ACME", "ref: refs/remotes/origin/main\n")
        self.assertEqual(find_repo(root).ref, "refs/remotes/origin/main")

    def test_detached_head_is_short_sha(self) -> None:
        root = self.make_repo("ACME", SHA + "\n")
        self.assertEqual(find_repo(root).ref, SHA[:7])

    def test_detached_sha256_is_short_sha(self) -> None:
        root = self.make_repo("ACME", "ab" * 32)
        self.assertEqual(find_repo(root).ref, "abababa")

    def test_garbage_head_has_no_ref(self) -> None:
        root = self.make_repo("ACME", "what is this\n")
        self.assertIsNone(find_repo(root).ref)

    def test_missing_head_has_no_ref(self) -> None:
        root = self.make_repo("ACME", None)
        info = find_repo(root)
        self.assertEqual((info.name, info.ref), ("ACME", None))

    def test_unreadable_head_has_no_ref(self) -> None:
        root = self.make_repo("ACME", None)
        (root / ".git" / "HEAD").mkdir()  # a directory: reading it raises OSError
        self.assertIsNone(find_repo(root).ref)


class LinkedCheckoutTests(GitInfoTestCase):
    def test_linked_worktree_uses_main_repo_name(self) -> None:
        main = self.make_repo("Globex")
        gitdir = self.make_gitdir(main / ".git" / "worktrees" / "wt1", "ref: refs/heads/topic\n", "../..")
        root = self.make_checkout(self.dir / "wt-feature", "gitdir: {}\n".format(gitdir))
        self.assertEqual(find_repo(root / "src"), RepoInfo(name="Globex", root=root, ref="topic"))

    def test_relative_gitdir(self) -> None:
        main = self.make_repo("Globex")
        self.make_gitdir(main / ".git" / "worktrees" / "wt1", commondir="../..")
        root = self.make_checkout(self.dir / "wt-feature", "gitdir: ../Globex/.git/worktrees/wt1\n")
        info = find_repo(root)
        self.assertEqual((info.name, info.root, info.ref), ("Globex", root, "main"))

    def test_bare_repo_worktree(self) -> None:
        bare = self.dir / "Initech.git"
        gitdir = self.make_gitdir(bare / "worktrees" / "wt1", commondir="../..")
        root = self.make_checkout(self.dir / "wt-bare", "gitdir: {}".format(gitdir))
        self.assertEqual(find_repo(root).name, "Initech")

    def test_submodule_uses_its_folder_name(self) -> None:
        parent = self.make_repo("Lumon")
        self.make_gitdir(parent / ".git" / "modules" / "lib", "ref: refs/heads/dev\n")
        root = self.make_checkout(parent / "lib", "gitdir: ../.git/modules/lib\n")
        self.assertEqual(find_repo(root), RepoInfo(name="lib", root=root, ref="dev"))

    def test_gitdir_without_head_has_no_ref(self) -> None:
        gitdir = self.dir / "elsewhere"
        gitdir.mkdir()
        root = self.make_checkout(self.dir / "ACME", "gitdir: {}".format(gitdir))
        info = find_repo(root)
        self.assertEqual((info.name, info.ref), ("ACME", None))


class UnreadableTests(GitInfoTestCase):
    def test_malformed_git_file_is_none(self) -> None:
        root = self.make_checkout(self.dir / "ACME", "not a gitdir line\n")
        self.assertIsNone(find_repo(root))

    def test_empty_gitdir_value_is_none(self) -> None:
        root = self.make_checkout(self.dir / "ACME", "gitdir:   \n")
        self.assertIsNone(find_repo(root))

    def test_no_git_in_the_tree(self) -> None:
        sub = self.dir / "plain" / "deeper"
        sub.mkdir(parents=True)
        info = find_repo(sub)
        # A stray .git above the temp dir would be found; it must then lie outside it.
        if info is not None:
            self.assertNotIn(self.dir, [info.root, *info.root.parents])


if __name__ == "__main__":
    unittest.main()
