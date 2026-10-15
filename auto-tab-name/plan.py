"""auto-tab-name decisions: which tabs follow their folder and which of them to rename."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Collection, Dict, List, Mapping, Optional, Sequence, Tuple

from config import SOURCES
from state import TabState


@dataclass(frozen=True)
class Rename:
    tab_id: str
    label: str


@dataclass(frozen=True)
class Plan:
    renames: Tuple[Rename, ...]
    states: Mapping[str, TabState]  # the complete new state map


def plan_tabs(tabs: Sequence[Mapping[str, Any]], panes: Sequence[Mapping[str, Any]],
              states: Mapping[str, TabState], label_for: Callable[[str], Optional[str]],
              source: str, only: Optional[Collection[str]] = None) -> Plan:
    """Decide the renames and the new state map; pure, the inputs are never changed."""
    panes_by_tab = _group_panes(panes)
    focused = {item["tab_id"]: item["pane_id"] for item in panes if item["focused"]}
    renames: List[Rename] = []
    new_states: Dict[str, TabState] = {}
    for tab in tabs:
        tab_id = tab["tab_id"]
        previous = states.get(tab_id)
        state = _with_pane(previous, focused.get(tab_id))
        tab_panes = panes_by_tab.get(tab_id, [])
        desired = _desired_label(_source_pane(state, tab_panes), source, label_for)
        state = replace(state, follow=_follows(previous, tab["label"], str(tab["number"]), desired))
        state, rename = _settle(state, tab, desired, only)
        new_states[tab_id] = state
        if rename is not None:
            renames.append(rename)
    return Plan(tuple(renames), new_states)


def set_follow(states: Mapping[str, TabState], tab: Mapping[str, Any], follow: bool) -> Dict[str, TabState]:
    """Mark a tab as followed or not, treating its current label as ours."""
    previous = states.get(tab["tab_id"])
    entry = TabState(follow, tab["label"], tab["label"], previous.pane if previous else None)
    return {**states, tab["tab_id"]: entry}


def _group_panes(panes: Sequence[Mapping[str, Any]]) -> Dict[str, List[Mapping[str, Any]]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = {}
    for item in panes:
        grouped.setdefault(item["tab_id"], []).append(item)
    return grouped


def _with_pane(previous: Optional[TabState], focused_pane: Optional[str]) -> TabState:
    state = previous if previous is not None else TabState(follow=False)
    return replace(state, pane=focused_pane) if focused_pane is not None else state


def _source_pane(state: TabState, tab_panes: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """The remembered pane while it exists, else the first pane of the tab."""
    for item in tab_panes:
        if item["pane_id"] == state.pane:
            return item
    return tab_panes[0] if tab_panes else None


def _desired_label(source_pane: Optional[Mapping[str, Any]], source: str,
                   label_for: Callable[[str], Optional[str]]) -> Optional[str]:
    """The label for the pane's folder: the chosen source, else the other one."""
    if source_pane is None:
        return None
    order = [source] + [name for name in SOURCES if name != source]
    for name in order:
        folder = source_pane.get(name)
        if folder:
            return label_for(folder)
    return None


def _follows(previous: Optional[TabState], label: str, number: str, desired: Optional[str]) -> bool:
    """Whether the tab follows its folder after this run (rule 4)."""
    if previous is None:
        return label == number or (desired is not None and label == desired)
    if previous.follow:
        # Anything but our last label, the default number or the folder is a manual rename.
        return label in (previous.written, number, desired)
    return label == number and previous.seen != label


def _settle(state: TabState, tab: Mapping[str, Any], desired: Optional[str],
            only: Optional[Collection[str]]) -> Tuple[TabState, Optional[Rename]]:
    """Apply rule 5: the rename to make, if any, and the matching written/seen."""
    label = tab["label"]
    if not state.follow or desired is None:
        return replace(state, seen=label), None
    if desired == label:
        return replace(state, written=label, seen=label), None
    if only is not None and tab["tab_id"] not in only:
        return replace(state, seen=label), None
    return replace(state, written=desired, seen=desired), Rename(tab["tab_id"], desired)
