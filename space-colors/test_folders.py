import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from folders import (
    RECENT_LIMIT,
    Suggestion,
    complete,
    expand,
    filter_suggestions,
    list_dirs,
    load_recent,
    merge_suggestions,
    remember,
    save_recent,
    shorten,
    zoxide_folders,
)
from herdr_api import ConfigError

HOME = "/home/ann"
TREE = {
    "/home/ann": ["git", "Documents", ".config"],
    "/home/ann/git": ["acme-api", "acme-web", "globex"],
    "/": ["home", "tmp"],
}


def fake_dirs(path):
    return TREE.get(path.rstrip("/") or "/", [])


class ExpandShortenTest(unittest.TestCase):
    def test_expands_the_home_tilde(self):
        self.assertEqual(expand("~", HOME), HOME)
        self.assertEqual(expand("~/git", HOME), "/home/ann/git")
        self.assertEqual(expand("/tmp", HOME), "/tmp")
        self.assertEqual(expand("  ~/git ", HOME), "/home/ann/git")

    def test_shortens_paths_under_home(self):
        self.assertEqual(shorten("/home/ann/git", HOME), "~/git")
        self.assertEqual(shorten(HOME, HOME), "~")
        self.assertEqual(shorten("/home/anna", HOME), "/home/anna")


class CompleteTest(unittest.TestCase):
    def test_a_single_match_completes_with_a_slash(self):
        self.assertEqual(complete("~/gi", HOME, fake_dirs), ("~/git/", ("git",)))

    def test_several_matches_extend_to_their_common_prefix(self):
        self.assertEqual(complete("~/git/a", HOME, fake_dirs), ("~/git/acme-", ("acme-api", "acme-web")))

    def test_nothing_to_extend_keeps_the_text_and_lists_the_candidates(self):
        self.assertEqual(complete("~/git/acme-", HOME, fake_dirs), ("~/git/acme-", ("acme-api", "acme-web")))

    def test_a_trailing_slash_lists_visible_subfolders(self):
        self.assertEqual(complete("~/", HOME, fake_dirs), ("~/", ("Documents", "git")))

    def test_hidden_folders_only_when_asked_for(self):
        self.assertEqual(complete("~/.c", HOME, fake_dirs), ("~/.config/", (".config",)))

    def test_matching_ignores_case(self):
        self.assertEqual(complete("~/doc", HOME, fake_dirs), ("~/Documents/", ("Documents",)))

    def test_no_match_or_a_relative_path_completes_nothing(self):
        self.assertEqual(complete("~/zzz", HOME, fake_dirs), ("~/zzz", ()))
        self.assertEqual(complete("git", HOME, fake_dirs), ("git", ()))
        self.assertEqual(complete("", HOME, fake_dirs), ("", ()))

    def test_bare_tilde_gets_its_slash(self):
        self.assertEqual(complete("~", HOME, fake_dirs), ("~/", ("Documents", "git")))


class SuggestionsTest(unittest.TestCase):
    def test_merges_sources_in_order_without_duplicates(self):
        merged = merge_suggestions(["/a", "/b"], ["/b", "/c", "/c"], ["/d", "/a"])

        self.assertEqual(
            merged,
            [Suggestion("/a", "recent"), Suggestion("/b", "recent"), Suggestion("/c", "open"), Suggestion("/d", "zoxide")],
        )

    def test_filters_by_the_typed_text_ignoring_case(self):
        suggestions = [Suggestion("/home/ann/git/acme-api", "recent"), Suggestion("/srv/globex", "open")]

        self.assertEqual(filter_suggestions(suggestions, "ACME", HOME), suggestions[:1])
        self.assertEqual(filter_suggestions(suggestions, "~/git", HOME), suggestions[:1])
        self.assertEqual(filter_suggestions(suggestions, "", HOME), suggestions)


class RecentTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "recent.json"

    def tearDown(self):
        self.directory.cleanup()

    def test_remember_puts_the_folder_first_and_caps_the_list(self):
        folders = ["/f{}".format(number) for number in range(RECENT_LIMIT)]

        updated = remember(folders, "/f5")
        self.assertEqual(updated[:2], ["/f5", "/f0"])
        self.assertEqual(len(updated), RECENT_LIMIT)
        self.assertEqual(remember(folders, "/new")[:1] + remember(folders, "/new")[-1:], ["/new", "/f18"])

    def test_saves_and_loads_back(self):
        save_recent(self.path, ["/a", "/b"])

        self.assertEqual(load_recent(self.path), ["/a", "/b"])
        self.assertEqual(load_recent(Path(self.directory.name) / "missing.json"), [])

    def test_a_damaged_file_is_an_error_that_names_it(self):
        self.path.write_text('{"folders": [1]}')

        with self.assertRaisesRegex(ConfigError, "recent.json"):
            load_recent(self.path)


class ZoxideTest(unittest.TestCase):
    def test_missing_zoxide_gives_nothing(self):
        self.assertEqual(zoxide_folders(which=lambda name: None), [])

    def test_lists_the_first_folders(self):
        output = "".join("/z{}\n".format(number) for number in range(15))
        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0, stdout=output))

        folders = zoxide_folders(run=run, which=lambda name: "/usr/bin/zoxide")

        self.assertEqual(folders, ["/z{}".format(number) for number in range(10)])
        self.assertEqual(run.call_args.args[0], ["/usr/bin/zoxide", "query", "--list"])

    def test_a_failing_or_slow_zoxide_gives_nothing(self):
        for error in (subprocess.TimeoutExpired("zoxide", 1), OSError("boom"), subprocess.CalledProcessError(1, "z")):
            with self.subTest(error=error):
                run = mock.Mock(side_effect=error)
                self.assertEqual(zoxide_folders(run=run, which=lambda name: "/usr/bin/zoxide"), [])


class ListDirsTest(unittest.TestCase):
    def test_lists_only_folders_and_tolerates_a_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "sub").mkdir()
            (Path(directory) / "file.txt").write_text("x")

            self.assertEqual(list_dirs(directory), ["sub"])
            self.assertEqual(list_dirs(directory + "/missing"), [])


if __name__ == "__main__":
    unittest.main()
