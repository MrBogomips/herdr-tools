import unittest

from herdr_api import HerdrError
from sorting import autosort_enabled, sort_sidebar
from test_space_herder import FakeHerdr


class SortSidebarTest(unittest.TestCase):
    def test_moves_all_spaces_as_one_block_in_sorted_order(self):
        herdr = FakeHerdr(["beta", "~", "alpha"])

        changed, labels = sort_sidebar(herdr)

        self.assertTrue(changed)
        self.assertEqual(labels, ["~", "alpha", "beta"])
        self.assertEqual(herdr.calls[-1], ("workspace.move_block", {"workspace_ids": ["w2", "w3", "w1"]}))

    def test_skips_the_move_when_already_sorted(self):
        herdr = FakeHerdr(["~", "alpha"])

        changed, labels = sort_sidebar(herdr)

        self.assertFalse(changed)
        self.assertEqual(labels, ["~", "alpha"])
        self.assertEqual(herdr.methods(), ["workspace.list"])

    def test_retries_when_the_server_order_does_not_match_once(self):
        herdr = FakeHerdr(["beta", "alpha"], ignore_moves=1)

        changed, labels = sort_sidebar(herdr)

        self.assertTrue(changed)
        self.assertEqual(labels, ["alpha", "beta"])
        self.assertEqual(herdr.methods().count("workspace.move_block"), 2)

    def test_retries_when_a_space_disappeared_mid_run(self):
        herdr = FakeHerdr(["beta", "alpha"], missing_moves=1)

        changed, _ = sort_sidebar(herdr)

        self.assertTrue(changed)

    def test_fails_when_the_server_order_never_matches(self):
        herdr = FakeHerdr(["beta", "alpha"], ignore_moves=3)

        with self.assertRaises(HerdrError):
            sort_sidebar(herdr)

        self.assertEqual(herdr.methods().count("workspace.move_block"), 3)

    def test_other_errors_are_not_retried(self):
        herdr = FakeHerdr(["beta", "alpha"], failing=["workspace.list"])

        with self.assertRaises(HerdrError):
            sort_sidebar(herdr)

        self.assertEqual(herdr.methods(), ["workspace.list"])


class AutosortTest(unittest.TestCase):
    def test_each_setting_enables_its_events(self):
        cases = {
            "off": (False, False),
            "created": (True, False),
            "renamed": (False, True),
            "both": (True, True),
        }
        for setting, (on_create, on_rename) in cases.items():
            with self.subTest(setting=setting):
                self.assertEqual(autosort_enabled(setting, "created"), on_create)
                self.assertEqual(autosort_enabled(setting, "renamed"), on_rename)

    def test_other_events_never_sort(self):
        for event in ("startup", "focused", "updated"):
            with self.subTest(event=event):
                self.assertFalse(autosort_enabled("both", event))


if __name__ == "__main__":
    unittest.main()
