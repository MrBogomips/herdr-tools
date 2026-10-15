import copy
import os
import unittest
from typing import Any, Dict, List, Optional

from plan import Plan, Rename, auto_labels, plan_tabs, set_follow
from state import TabState


def label_for(cwd: str) -> Optional[str]:
    return os.path.basename(cwd)


def tab(tab_id: str, label: str, number: int, workspace_id: str = "wA") -> Dict[str, Any]:
    return {"tab_id": tab_id, "workspace_id": workspace_id, "label": label, "number": number}


def pane(pane_id: str, tab_id: str, cwd: Optional[str] = None, foreground_cwd: Optional[str] = None,
         focused: bool = False) -> Dict[str, Any]:
    return {"pane_id": pane_id, "tab_id": tab_id, "focused": focused, "cwd": cwd,
            "foreground_cwd": foreground_cwd}


class PlanTestCase(unittest.TestCase):
    def plan(self, tabs: List[Dict[str, Any]], panes: List[Dict[str, Any]],
             states: Optional[Dict[str, TabState]] = None, source: str = "foreground_cwd",
             only: Optional[set] = None) -> Plan:
        return plan_tabs(tabs, panes, states or {}, label_for, source, only)

    def renames(self, plan: Plan) -> List[Any]:
        return [(rename.tab_id, rename.label) for rename in plan.renames]


class NewTabTest(PlanTestCase):
    def test_new_auto_named_tab_is_followed_and_renamed(self) -> None:
        plan = self.plan([tab("wA:t1", "1", 1)], [pane("wA:p1", "wA:t1", foreground_cwd="/work/acme")])
        self.assertEqual(self.renames(plan), [("wA:t1", "acme")])
        self.assertEqual(plan.states["wA:t1"], TabState(True, "acme", "acme", None))

    def test_new_tab_named_by_hand_is_left_alone(self) -> None:
        plan = self.plan([tab("wA:t1", "Lumon", 1)], [pane("wA:p1", "wA:t1", foreground_cwd="/work/globex")])
        self.assertEqual(plan.renames, ())
        self.assertEqual(plan.states["wA:t1"], TabState(False, None, "Lumon", None))

    def test_new_tab_already_showing_its_folder_is_adopted(self) -> None:
        plan = self.plan([tab("wA:t1", "globex", 3)], [pane("wA:p1", "wA:t1", foreground_cwd="/work/globex")])
        self.assertEqual(plan.renames, ())
        self.assertEqual(plan.states["wA:t1"], TabState(True, "globex", "globex", None))


class FollowedTabTest(PlanTestCase):
    def test_folder_change_renames(self) -> None:
        states = {"wA:t1": TabState(True, "acme", "acme", None)}
        plan = self.plan([tab("wA:t1", "acme", 1)], [pane("wA:p1", "wA:t1", foreground_cwd="/work/globex")], states)
        self.assertEqual(self.renames(plan), [("wA:t1", "globex")])
        self.assertEqual(plan.states["wA:t1"], TabState(True, "globex", "globex", None))

    def test_manual_rename_stops_following(self) -> None:
        states = {"wA:t1": TabState(True, "acme", "acme", None)}
        plan = self.plan([tab("wA:t1", "Lumon", 1)], [pane("wA:p1", "wA:t1", foreground_cwd="/work/globex")], states)
        self.assertEqual(plan.renames, ())
        self.assertEqual(plan.states["wA:t1"], TabState(False, "acme", "Lumon", None))

    def test_label_equal_to_desired_stays_followed_with_stale_written(self) -> None:
        states = {"wA:t1": TabState(True, "acme", "acme", None)}
        plan = self.plan([tab("wA:t1", "globex", 1)], [pane("wA:p1", "wA:t1", foreground_cwd="/work/globex")], states)
        self.assertEqual(plan.renames, ())
        self.assertEqual(plan.states["wA:t1"], TabState(True, "globex", "globex", None))

    def test_reset_to_its_position_stays_followed_and_is_renamed(self) -> None:
        states = {"wA:t2": TabState(True, "acme", "acme", None)}
        tabs = [tab("wA:t1", "Lumon", 1), tab("wA:t2", "2", 2)]
        plan = self.plan(tabs, [pane("wA:p2", "wA:t2", foreground_cwd="/work/acme")], states)
        self.assertEqual(self.renames(plan), [("wA:t2", "acme")])

    def test_renamed_to_its_number_but_not_its_position_stops_following(self) -> None:
        states = {"wA:t3": TabState(True, "globex", "globex", None)}
        tabs = [tab("wA:t1", "Lumon", 1), tab("wA:t3", "3", 3)]
        plan = self.plan(tabs, [pane("wA:p3", "wA:t3", foreground_cwd="/work/globex")], states)
        self.assertEqual(plan.renames, ())
        self.assertFalse(plan.states["wA:t3"].follow)


class UnfollowedTabTest(PlanTestCase):
    def test_renamed_back_to_its_number_follows_again(self) -> None:
        states = {"wA:t1": TabState(False, None, "Lumon", None)}
        plan = self.plan([tab("wA:t1", "1", 1)], [pane("wA:p1", "wA:t1", foreground_cwd="/work/initech")], states)
        self.assertEqual(self.renames(plan), [("wA:t1", "initech")])
        self.assertTrue(plan.states["wA:t1"].follow)

    def test_still_showing_its_number_stays_unfollowed(self) -> None:
        states = {"wA:t1": TabState(False, "1", "1", None)}
        plan = self.plan([tab("wA:t1", "1", 1)], [pane("wA:p1", "wA:t1", foreground_cwd="/work/initech")], states)
        self.assertEqual(plan.renames, ())
        self.assertFalse(plan.states["wA:t1"].follow)

    def test_other_label_stays_unfollowed(self) -> None:
        states = {"wA:t1": TabState(False, None, "Lumon", None)}
        plan = self.plan([tab("wA:t1", "Lumon", 1)], [pane("wA:p1", "wA:t1", foreground_cwd="/work/initech")], states)
        self.assertEqual(plan.renames, ())
        self.assertEqual(plan.states["wA:t1"], TabState(False, None, "Lumon", None))


class AutomaticLabelTest(PlanTestCase):
    """Herdr shows an unnamed tab as its position in its workspace; `number` is never reused."""

    def test_auto_labels_count_positions_per_workspace(self) -> None:
        tabs = [tab("wA:t1", "x", 1, "wA"), tab("wB:t1", "x", 1, "wB"), tab("wA:t3", "x", 3, "wA")]
        self.assertEqual(auto_labels(tabs), {"wA:t1": "1", "wB:t1": "1", "wA:t3": "2"})

    def test_tab_after_a_closed_one_is_automatic_at_its_position(self) -> None:
        tabs = [tab("wA:t1", "1", 1), tab("wA:t3", "2", 3)]  # tab 2 was closed
        panes = [pane("wA:p1", "wA:t1", foreground_cwd="/work/acme"),
                 pane("wA:p3", "wA:t3", foreground_cwd="/work/globex")]
        plan = self.plan(tabs, panes)
        self.assertEqual(self.renames(plan), [("wA:t1", "acme"), ("wA:t3", "globex")])
        self.assertTrue(plan.states["wA:t3"].follow)

    def test_label_equal_to_its_number_but_not_its_position_is_a_name(self) -> None:
        tabs = [tab("wA:t1", "1", 1), tab("wA:t3", "3", 3)]
        panes = [pane("wA:p3", "wA:t3", foreground_cwd="/work/globex")]
        plan = self.plan(tabs, panes)
        self.assertEqual(plan.renames, ())
        self.assertEqual(plan.states["wA:t3"], TabState(False, None, "3", None))

    def test_positions_count_within_each_workspace(self) -> None:
        tabs = [tab("wA:t1", "1", 1, "wA"), tab("wA:t2", "2", 2, "wA"),
                tab("wB:t1", "2", 1, "wB"), tab("wB:t2", "2", 2, "wB")]
        plan = self.plan(tabs, [])
        follows = {tab_id: state.follow for tab_id, state in plan.states.items()}
        self.assertEqual(follows, {"wA:t1": True, "wA:t2": True, "wB:t1": False, "wB:t2": True})

    def test_interleaved_workspaces_keep_their_own_count(self) -> None:
        tabs = [tab("wA:t1", "1", 1, "wA"), tab("wB:t1", "1", 1, "wB"), tab("wA:t2", "2", 2, "wA")]
        plan = self.plan(tabs, [])
        self.assertTrue(all(state.follow for state in plan.states.values()))

    def test_pinned_unfollowed_tab_stays_unfollowed_when_positions_shift(self) -> None:
        states = {"wA:t3": TabState(False, "2", "2", None)}  # unfollow pinned "2" at position 2
        tabs = [tab("wA:t3", "2", 3)]  # the tab in front closed: position 1, the name stays "2"
        plan = self.plan(tabs, [pane("wA:p3", "wA:t3", foreground_cwd="/work/globex")], states)
        self.assertEqual(plan.renames, ())
        self.assertEqual(plan.states["wA:t3"], TabState(False, "2", "2", None))

    def test_unpinned_unfollowed_tab_reads_as_renamed_back_when_positions_shift(self) -> None:
        states = {"wA:t3": TabState(False, None, "2", None)}  # automatic "2", never pinned
        tabs = [tab("wA:t3", "1", 3)]  # the tab in front closed: Herdr now shows "1"
        plan = self.plan(tabs, [pane("wA:p3", "wA:t3", foreground_cwd="/work/globex")], states)
        self.assertEqual(self.renames(plan), [("wA:t3", "globex")])
        self.assertTrue(plan.states["wA:t3"].follow)


class SourcePaneTest(PlanTestCase):
    def test_stored_pane_wins(self) -> None:
        states = {"wA:t1": TabState(True, "1", "1", "wA:p2")}
        panes = [pane("wA:p1", "wA:t1", foreground_cwd="/work/acme"),
                 pane("wA:p2", "wA:t1", foreground_cwd="/work/globex")]
        plan = self.plan([tab("wA:t1", "1", 1)], panes, states)
        self.assertEqual(self.renames(plan), [("wA:t1", "globex")])
        self.assertEqual(plan.states["wA:t1"].pane, "wA:p2")

    def test_missing_stored_pane_falls_back_to_the_first_pane(self) -> None:
        states = {"wA:t1": TabState(True, "1", "1", "wA:gone")}
        panes = [pane("wA:p1", "wA:t1", foreground_cwd="/work/acme"),
                 pane("wA:p2", "wA:t1", foreground_cwd="/work/globex")]
        plan = self.plan([tab("wA:t1", "1", 1)], panes, states)
        self.assertEqual(self.renames(plan), [("wA:t1", "acme")])

    def test_focused_pane_becomes_the_stored_pane(self) -> None:
        states = {"wA:t1": TabState(True, "1", "1", "wA:p1")}
        panes = [pane("wA:p1", "wA:t1", foreground_cwd="/work/acme"),
                 pane("wA:p2", "wA:t1", foreground_cwd="/work/globex", focused=True)]
        plan = self.plan([tab("wA:t1", "1", 1)], panes, states)
        self.assertEqual(plan.states["wA:t1"].pane, "wA:p2")
        self.assertEqual(self.renames(plan), [("wA:t1", "globex")])

    def test_tab_without_panes_is_not_renamed_but_rules_still_apply(self) -> None:
        plan = self.plan([tab("wA:t1", "1", 1), tab("wA:t2", "Lumon", 2)], [])
        self.assertEqual(plan.renames, ())
        self.assertTrue(plan.states["wA:t1"].follow)
        self.assertFalse(plan.states["wA:t2"].follow)

    def test_panes_of_other_tabs_are_ignored(self) -> None:
        panes = [pane("wA:p1", "wA:t2", foreground_cwd="/work/acme")]
        plan = self.plan([tab("wA:t1", "1", 1)], panes)
        self.assertEqual(plan.renames, ())


class FolderSourceTest(PlanTestCase):
    def one(self, source: str, cwd: Optional[str], foreground: Optional[str]) -> Plan:
        panes = [pane("wA:p1", "wA:t1", cwd=cwd, foreground_cwd=foreground)]
        return self.plan([tab("wA:t1", "1", 1)], panes, source=source)

    def test_foreground_source_uses_foreground_cwd(self) -> None:
        plan = self.one("foreground_cwd", "/work/acme", "/work/globex")
        self.assertEqual(self.renames(plan), [("wA:t1", "globex")])

    def test_foreground_source_falls_back_to_cwd(self) -> None:
        plan = self.one("foreground_cwd", "/work/acme", None)
        self.assertEqual(self.renames(plan), [("wA:t1", "acme")])

    def test_cwd_source_uses_cwd(self) -> None:
        plan = self.one("cwd", "/work/acme", "/work/globex")
        self.assertEqual(self.renames(plan), [("wA:t1", "acme")])

    def test_cwd_source_falls_back_to_foreground_cwd(self) -> None:
        plan = self.one("cwd", None, "/work/globex")
        self.assertEqual(self.renames(plan), [("wA:t1", "globex")])

    def test_empty_text_counts_as_missing(self) -> None:
        plan = self.one("cwd", "", "/work/globex")
        self.assertEqual(self.renames(plan), [("wA:t1", "globex")])

    def test_no_folder_means_no_rename(self) -> None:
        plan = self.one("cwd", None, None)
        self.assertEqual(plan.renames, ())
        self.assertTrue(plan.states["wA:t1"].follow)

    def test_label_for_returning_none_means_no_rename(self) -> None:
        panes = [pane("wA:p1", "wA:t1", foreground_cwd="/work/acme")]
        plan = plan_tabs([tab("wA:t1", "1", 1)], panes, {}, lambda cwd: None, "foreground_cwd")
        self.assertEqual(plan.renames, ())


class ScopeAndOrderTest(PlanTestCase):
    def setUp(self) -> None:
        self.tabs = [tab("wA:t1", "1", 1), tab("wA:t2", "2", 2), tab("wA:t3", "3", 3)]
        self.panes = [pane("wA:p1", "wA:t1", foreground_cwd="/work/acme"),
                      pane("wA:p2", "wA:t2", foreground_cwd="/work/globex"),
                      pane("wA:p3", "wA:t3", foreground_cwd="/work/initech")]

    def test_renames_follow_the_order_of_tabs(self) -> None:
        plan = self.plan(self.tabs, list(reversed(self.panes)))
        self.assertEqual([rename.tab_id for rename in plan.renames], ["wA:t1", "wA:t2", "wA:t3"])

    def test_only_limits_renames_but_not_states(self) -> None:
        plan = self.plan(self.tabs, self.panes, only={"wA:t2"})
        self.assertEqual(self.renames(plan), [("wA:t2", "globex")])
        self.assertEqual(set(plan.states), {"wA:t1", "wA:t2", "wA:t3"})
        self.assertEqual(plan.states["wA:t1"], TabState(True, None, "1", None))
        self.assertEqual(plan.states["wA:t2"], TabState(True, "globex", "globex", None))

    def test_closed_tabs_are_dropped(self) -> None:
        states = {"wA:t1": TabState(True, "acme", "acme", None), "wA:gone": TabState(True, "x", "x", None)}
        plan = self.plan(self.tabs[:1], self.panes[:1], states)
        self.assertEqual(set(plan.states), {"wA:t1"})

    def test_inputs_are_not_mutated(self) -> None:
        states = {"wA:t1": TabState(True, "acme", "acme", None)}
        before = copy.deepcopy((self.tabs, self.panes, states))
        self.plan(self.tabs, self.panes, states, only={"wA:t1"})
        self.assertEqual((self.tabs, self.panes, states), before)

    def test_planning_again_after_the_renames_changes_nothing(self) -> None:
        first = self.plan(self.tabs, self.panes)
        renamed = {rename.tab_id: rename.label for rename in first.renames}
        applied = [dict(item, label=renamed.get(item["tab_id"], item["label"])) for item in self.tabs]
        second = self.plan(applied, self.panes, dict(first.states))
        self.assertEqual(second.renames, ())
        self.assertEqual(dict(second.states), dict(first.states))

    def test_rename_is_a_value_object(self) -> None:
        self.assertEqual(Rename("wA:t1", "acme"), Rename("wA:t1", "acme"))


class SetFollowTest(unittest.TestCase):
    def test_follow_marks_the_current_label_as_ours(self) -> None:
        states = {"wA:t1": TabState(False, "x", "y", "wA:p1"), "wA:t2": TabState(True, "Lumon")}
        before = copy.deepcopy(states)
        new = set_follow(states, tab("wA:t1", "Lumon", 1), True)
        self.assertEqual(new["wA:t1"], TabState(True, "Lumon", "Lumon", "wA:p1"))
        self.assertEqual(new["wA:t2"], states["wA:t2"])
        self.assertEqual(states, before)

    def test_unfollow_keeps_the_name_and_works_without_a_previous_entry(self) -> None:
        new = set_follow({}, tab("wA:t1", "Globex", 1), False)
        self.assertEqual(new, {"wA:t1": TabState(False, "Globex", "Globex", None)})


if __name__ == "__main__":
    unittest.main()
