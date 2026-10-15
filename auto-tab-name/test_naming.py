import dataclasses
import tempfile
import unittest
from pathlib import Path
from typing import Callable, Optional

from config import Config
from gitinfo import RepoInfo
from naming import ELLIPSIS, tab_label

HOME = "/Users/acme"
CWD = "/Users/acme/tools/initech/sort"
REPO = RepoInfo(name="initech", root=Path("/Users/acme/tools/initech"), ref="main")


def fixed(info: Optional[RepoInfo]) -> Callable[[Path], Optional[RepoInfo]]:
    return lambda _path: info


def label(cwd: Optional[str], fmt: str, info: Optional[RepoInfo] = REPO, **options: object) -> Optional[str]:
    config = dataclasses.replace(Config(), **dict({"format": fmt, "max_length": 0}, **options))
    return tab_label(cwd, config, HOME, repo_of=fixed(info))


class FormatTests(unittest.TestCase):
    CASES = (
        # (cwd, format, repo, options, expected)
        (CWD, "basename", REPO, {}, "sort"),
        (HOME, "basename", REPO, {}, "~"),
        (HOME, "basename", REPO, {"home_tilde": False}, "acme"),
        ("/", "basename", None, {}, "/"),
        (CWD, "repo", REPO, {}, "initech/sort"),
        (str(REPO.root), "repo", REPO, {}, "initech"),
        (CWD, "repo", None, {}, "sort"),
        (CWD, "last_n", REPO, {"depth": 2}, "initech/sort"),
        (CWD, "last_n", REPO, {"depth": 1}, "sort"),
        (HOME + "/tools", "last_n", REPO, {"depth": 2}, "~/tools"),
        (HOME + "/tools/initech", "last_n", REPO, {"depth": 2}, "tools/initech"),
        ("/usr", "last_n", None, {"depth": 2}, "/usr"),
        ("/usr/local/bin", "last_n", None, {"depth": 2}, "local/bin"),
        (HOME, "last_n", None, {"depth": 2}, "~"),
        (CWD, "home_path", REPO, {}, "~/tools/initech/sort"),
        (CWD, "home_path", REPO, {"home_tilde": False}, CWD),
        ("/opt/globex", "home_path", None, {}, "/opt/globex"),
        (CWD, "repo_branch", REPO, {}, "initech@main"),
        (CWD, "repo_branch", dataclasses.replace(REPO, ref=None), {}, "initech"),
        (CWD, "repo_branch", None, {}, "sort"),
        ("/Users/acmex/lumon", "home_path", None, {}, "/Users/acmex/lumon"),
        ("/Users/acmex", "basename", None, {}, "acmex"),
        (CWD + "/", "basename", REPO, {}, "sort"),
        (CWD + "//", "home_path", REPO, {}, "~/tools/initech/sort"),
    )

    def test_table(self) -> None:
        for cwd, fmt, info, options, expected in self.CASES:
            with self.subTest(cwd=cwd, format=fmt, options=options):
                self.assertEqual(label(cwd, fmt, info, **options), expected)

    def test_no_cwd_gives_no_label(self) -> None:
        for fmt in ("basename", "repo", "last_n", "home_path", "repo_branch"):
            with self.subTest(format=fmt):
                self.assertIsNone(label(None, fmt))
                self.assertIsNone(label("", fmt))

    def test_repo_root_outside_cwd_falls_back_to_basename(self) -> None:
        elsewhere = RepoInfo(name="globex", root=Path("/srv/globex"), ref="main")
        self.assertEqual(label(CWD, "repo", elsewhere), "sort")

    def test_repo_lookup_receives_the_normalised_cwd(self) -> None:
        seen = []
        config = dataclasses.replace(Config(), format="repo", max_length=0)
        tab_label(CWD + "/", config, HOME, repo_of=lambda path: seen.append(path))
        self.assertEqual(seen, [Path(CWD)])

    def test_root_or_missing_home_never_becomes_tilde(self) -> None:
        config = dataclasses.replace(Config(), format="home_path", max_length=0)
        for home in ("/", "//", ""):
            with self.subTest(home=home):
                self.assertEqual(tab_label("/usr/bin", config, home, repo_of=fixed(None)), "/usr/bin")
                self.assertEqual(tab_label("/", config, home, repo_of=fixed(None)), "/")


class TruncationTests(unittest.TestCase):
    def test_right_formats_cut_the_end(self) -> None:
        info = RepoInfo(name="initech", root=Path("/Users/acme/tools/initech"), ref="main")
        self.assertEqual(label(CWD, "basename", info, max_length=3), "so" + ELLIPSIS)
        self.assertEqual(label(CWD, "repo", info, max_length=8), "initech" + ELLIPSIS)
        self.assertEqual(label(CWD, "repo_branch", info, max_length=9), "initech@" + ELLIPSIS)

    def test_left_formats_cut_the_start(self) -> None:
        self.assertEqual(label(CWD, "last_n", depth=2, max_length=5), ELLIPSIS + "sort")
        self.assertEqual(label(CWD, "home_path", max_length=8), ELLIPSIS + "ch/sort")

    def test_result_has_exactly_max_length_characters(self) -> None:
        for fmt in ("basename", "repo", "last_n", "home_path", "repo_branch"):
            with self.subTest(format=fmt):
                self.assertEqual(len(label(CWD, fmt, max_length=3)), 3)

    def test_label_at_the_limit_is_kept(self) -> None:
        self.assertEqual(label(CWD, "basename", max_length=4), "sort")

    def test_zero_never_truncates(self) -> None:
        self.assertEqual(label(CWD, "home_path", max_length=0), "~/tools/initech/sort")

    def test_max_length_one_leaves_only_the_ellipsis(self) -> None:
        self.assertEqual(label(CWD, "basename", max_length=1), ELLIPSIS)
        self.assertEqual(label(CWD, "home_path", max_length=1), ELLIPSIS)


class RealRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "ACME"
        (self.root / ".git").mkdir(parents=True)
        (self.root / ".git" / "HEAD").write_text("ref: refs/heads/feature/x\n", encoding="utf-8")
        (self.root / "src" / "lib").mkdir(parents=True)

    def real_label(self, cwd: Path, fmt: str) -> Optional[str]:
        config = dataclasses.replace(Config(), format=fmt, max_length=0)
        return tab_label(str(cwd), config, HOME)

    def test_repo_relative_to_the_given_cwd(self) -> None:
        self.assertEqual(self.real_label(self.root / "src" / "lib", "repo"), "ACME/src/lib")

    def test_repo_branch_with_the_default_lookup(self) -> None:
        self.assertEqual(self.real_label(self.root / "src", "repo_branch"), "ACME@feature/x")


if __name__ == "__main__":
    unittest.main()
