import unittest
from datetime import date

from config import DEFAULTS, build_config
from plan import MAX_KEYS_PER_REPORT, Choice, choose, clear_reports, display_value, plan_reports

# Eight colours, so the golden hash indices are acme -> 0, umbrella -> 0, globex -> 7, initech -> 3.
PALETTE = ["#000001", "#000002", "#000003", "#000004", "#000005", "#000006", "#000007", "#000008"]
TODAY = date(2026, 10, 14)


def config(**overrides):
    return build_config({**DEFAULTS, "palette": PALETTE, **overrides}, "config.json")


def ws(workspace_id, label, tokens=None, worktree=None):
    record = {"workspace_id": workspace_id, "label": label, "number": 1}
    if tokens is not None:
        record["tokens"] = tokens
    if worktree is not None:
        record["worktree"] = worktree
    return record


def slots(spaces, cfg, stored=None):
    choices, _ = choose(spaces, cfg, stored or {}, TODAY)
    return {workspace_id: choice.slot for workspace_id, choice in choices.items()}


def reports(spaces, cfg):
    choices, _ = choose(spaces, cfg, {}, TODAY)
    return plan_reports(spaces, choices, cfg.marker)


class HashChoiceTest(unittest.TestCase):
    def test_hashes_the_prefix(self):
        spaces = [ws("a", "ACME - api"), ws("b", "ACME - web +"), ws("g", "Globex - etl")]

        self.assertEqual(slots(spaces, config()), {"a": 0, "b": 0, "g": 7})

    def test_hash_mode_leaves_the_remembered_keys_alone(self):
        stored = {"globex": {"color": "#000002", "seen": "2026-01-01"}}

        choices, kept = choose([ws("g", "Globex - etl")], config(), stored, TODAY)

        self.assertEqual((choices["g"].slot, kept), (7, stored))

    def test_first_matching_rule_beats_the_hash(self):
        cfg = config(rules=[{"match": "^globex", "color": 2}, {"match": "etl", "color": 5}])

        self.assertEqual(slots([ws("g", "Globex - etl"), ws("i", "Initech - etl")], cfg), {"g": 2, "i": 5})

    def test_reports_the_key_and_the_reason(self):
        cfg = config(rules=[{"match": "^globex", "color": 2}])
        choices, _ = choose([ws("a", "ACME - api"), ws("g", "Globex - etl")], cfg, {}, TODAY)

        self.assertEqual(choices["a"], Choice("acme", 0, "hash"))
        self.assertEqual(choices["g"], Choice("globex", 2, "rule ^globex"))


class StickyChoiceTest(unittest.TestCase):
    def test_clashing_customers_get_different_colors(self):
        spaces = [ws("a", "ACME - api"), ws("u", "Umbrella - x"), ws("b", "ACME - web")]

        choices, stored = choose(spaces, config(assign="sticky"), {}, TODAY)

        self.assertEqual({key: choice.slot for key, choice in choices.items()}, {"a": 0, "u": 1, "b": 0})
        self.assertEqual(choices["u"].reason, "sticky")
        self.assertEqual(set(stored), {"acme", "umbrella"})

    def test_a_remembered_customer_keeps_its_color(self):
        stored = {"umbrella": {"color": "#000001", "seen": "2026-10-01"}}

        self.assertEqual(slots([ws("a", "ACME - api"), ws("u", "Umbrella - x")], config(assign="sticky"), stored),
                         {"a": 1, "u": 0})

    def test_new_customers_avoid_palette_colors_pinned_by_rules(self):
        cfg = config(assign="sticky", rules=[{"match": "^lumon", "color": 0}, {"match": "^globex", "color": "#abcdef"}])
        spaces = [ws("l", "Lumon - x"), ws("a", "ACME - api"), ws("g", "Globex - etl")]

        self.assertEqual(slots(spaces, cfg), {"l": 0, "a": 1, "g": 8})

    def test_spaces_colored_by_a_rule_are_not_remembered(self):
        cfg = config(assign="sticky", rules=[{"match": "^globex", "color": 2}])

        _, stored = choose([ws("g", "Globex - etl")], cfg, {}, TODAY)

        self.assertEqual(stored, {})


class WorktreeChoiceTest(unittest.TestCase):
    def setUp(self):
        self.parent = ws("p", "ACME - api", worktree={"repo_key": "r", "is_linked_worktree": False})
        self.child = ws("c", "Initech", worktree={"repo_key": "r", "is_linked_worktree": True})

    def test_children_take_their_parent_color(self):
        spaces = [self.parent, self.child]

        self.assertEqual(slots(spaces, config())["c"], 0)
        self.assertEqual(slots(spaces, config(rules=[{"match": "^acme", "color": 4}]))["c"], 4)
        self.assertEqual(slots(spaces, config(worktrees_follow_parent=False))["c"], 3)

    def test_orphan_child_uses_its_own_name(self):
        orphan = ws("c", "Initech", worktree={"repo_key": "gone", "is_linked_worktree": True})

        self.assertEqual(slots([orphan], config()), {"c": 3})


class DisplayValueTest(unittest.TestCase):
    def test_puts_the_marker_before_the_name(self):
        self.assertEqual(display_value(" ACME - api ", "▌"), "▌ACME - api")
        self.assertEqual(display_value("ACME - api", ""), "ACME - api")

    def test_drops_control_characters_like_herdr(self):
        self.assertEqual(display_value("AC\x1bME\x07", ""), "ACME")

    def test_long_names_are_cut_to_herdrs_80_characters(self):
        value = display_value("x" * 100, "▌")

        self.assertEqual(len(value), 80)
        self.assertTrue(value.endswith("…"))
        self.assertEqual(display_value("y" * 79, "▌"), "▌" + "y" * 79)


class PlanReportsTest(unittest.TestCase):
    def test_reports_the_colored_name_for_a_new_space(self):
        self.assertEqual(reports([ws("a", "ACME - api")], config()), [("a", {"spc0": "▌ACME - api"})])

    def test_nothing_to_report_when_tokens_are_current(self):
        self.assertEqual(reports([ws("a", "ACME - api", {"spc0": "▌ACME - api"})], config()), [])

    def test_a_new_color_sets_the_new_slot_and_clears_the_old_one(self):
        spaces = [ws("a", "ACME - api", {"spc3": "▌Initech"})]

        self.assertEqual(reports(spaces, config()), [("a", {"spc0": "▌ACME - api", "spc3": None})])

    def test_a_rename_within_the_same_color_updates_the_text(self):
        spaces = [ws("a", "ACME - web", {"spc0": "▌ACME - api"})]

        self.assertEqual(reports(spaces, config()), [("a", {"spc0": "▌ACME - web"})])

    def test_slots_left_over_from_a_bigger_palette_are_cleared(self):
        spaces = [ws("a", "ACME - api", {"spc0": "▌ACME - api", "spc14": "▌old"})]

        self.assertEqual(reports(spaces, config()), [("a", {"spc14": None})])

    def test_tokens_of_other_reporters_are_left_alone(self):
        spaces = [ws("a", "ACME - api", {"jj_status": "2 changes", "spcx": "x"})]

        self.assertEqual(reports(spaces, config()), [("a", {"spc0": "▌ACME - api"})])

    def test_large_patches_are_split_into_herdr_sized_reports(self):
        stale = {"spc{}".format(number): "old" for number in range(1, 31)}
        planned = reports([ws("a", "ACME - api", stale)], config())

        self.assertTrue(all(len(patch) <= MAX_KEYS_PER_REPORT for _, patch in planned))
        merged = {key: value for _, patch in planned for key, value in patch.items()}
        self.assertEqual(merged, {"spc0": "▌ACME - api", **{key: None for key in stale}})

    def test_ignores_a_malformed_tokens_value(self):
        self.assertEqual(reports([ws("a", "ACME", "oops")], config()), [("a", {"spc0": "▌ACME"})])

    def test_renaming_a_worktree_parent_recolors_its_children_in_the_same_run(self):
        parent = ws("p", "Globex - api", {"spc0": "▌ACME - api"}, {"repo_key": "r", "is_linked_worktree": False})
        child = ws("c", "feature", {"spc0": "▌feature"}, {"repo_key": "r", "is_linked_worktree": True})

        planned = dict(reports([parent, child], config()))

        self.assertEqual(planned["c"], {"spc7": "▌feature", "spc0": None})


class ClearReportsTest(unittest.TestCase):
    def test_clears_only_our_tokens(self):
        spaces = [ws("a", "ACME", {"spc0": "▌ACME", "jj_status": "x"}), ws("b", "Globex"), ws("c", "Lumon", {})]

        self.assertEqual(clear_reports(spaces), [("a", {"spc0": None})])


if __name__ == "__main__":
    unittest.main()
