import unittest

from groups import BOTTOM, DEFAULT, HEAD, HOME, compose, plan_order, split_label


def ws(workspace_id, label, number, worktree=None):
    record = {"workspace_id": workspace_id, "label": label, "number": number}
    if worktree is not None:
        record["worktree"] = worktree
    return record


def worktree(repo_key, linked):
    return {"repo_key": repo_key, "is_linked_worktree": linked}


class SplitLabelTest(unittest.TestCase):
    def test_reads_the_group_from_the_suffix(self):
        cases = {
            "LUMON +": ("LUMON", HEAD),
            "SYS -": ("SYS", BOTTOM),
            "ACME - api": ("ACME - api", DEFAULT),
            "LAB + ": ("LAB", HEAD),
            "~": ("~", HOME),
            "C++": ("C++", DEFAULT),
            "b-": ("b-", DEFAULT),
            "+": ("+", DEFAULT),
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(split_label(label), expected)


class ComposeTest(unittest.TestCase):
    def test_adds_the_suffix_of_the_group(self):
        self.assertEqual(compose("LUMON", HEAD), "LUMON +")
        self.assertEqual(compose(" SYS ", BOTTOM), "SYS -")
        self.assertEqual(compose("ACME - api", DEFAULT), "ACME - api")

    def test_home_has_no_suffix(self):
        self.assertEqual(compose("~", HOME), "~")
        self.assertEqual(compose("~", HEAD), "~")

    def test_round_trips_with_split(self):
        for label in ("LUMON +", "SYS -", "ACME - api", "~"):
            with self.subTest(label=label):
                self.assertEqual(compose(*split_label(label)), label)


class PlanOrderTest(unittest.TestCase):
    """The same order as sort-spaces (`sort_spaces.plan_order`); keep the two in step."""

    def test_groups_then_names_ignoring_case(self):
        spaces = [ws("w1", "SYS -", 1), ws("w2", "beta", 2), ws("w3", "LAB +", 3), ws("w4", "Alpha", 4), ws("w5", "~", 5)]

        self.assertEqual(plan_order(spaces), ["w5", "w3", "w4", "w2", "w1"])

    def test_sorts_by_name_without_marker_inside_a_group(self):
        spaces = [ws("w1", "personal +", 1), ws("w2", "b -", 2), ws("w3", "LUMON +", 3), ws("w4", "A -", 4)]

        self.assertEqual(plan_order(spaces), ["w3", "w1", "w4", "w2"])

    def test_keeps_current_order_for_equal_labels(self):
        spaces = [ws("w1", "zeta", 1), ws("w2", "Same", 2), ws("w3", "same", 3)]

        self.assertEqual(plan_order(spaces), ["w2", "w3", "w1"])

    def test_worktree_children_follow_their_parent_and_its_group(self):
        spaces = [
            ws("w1", "alpha", 1),
            ws("w2", "aa-repo -", 2, worktree("rm", False)),
            ws("w3", "aa-child +", 3, worktree("rm", True)),
            ws("w4", "beta", 4),
        ]

        self.assertEqual(plan_order(spaces), ["w1", "w4", "w2", "w3"])

    def test_worktree_groups_with_equal_parent_labels_stay_together(self):
        spaces = [
            ws("A", "api", 1, worktree("ra", False)),
            ws("B", "api", 2, worktree("rb", False)),
            ws("a1", "feat-a", 3, worktree("ra", True)),
            ws("b1", "feat-b", 4, worktree("rb", True)),
        ]

        self.assertEqual(plan_order(spaces), ["A", "a1", "B", "b1"])

    def test_orphan_worktree_child_sorts_by_its_own_label(self):
        spaces = [ws("w1", "beta", 1), ws("w2", "alpha", 2, worktree("repo-x", True))]

        self.assertEqual(plan_order(spaces), ["w2", "w1"])


if __name__ == "__main__":
    unittest.main()
