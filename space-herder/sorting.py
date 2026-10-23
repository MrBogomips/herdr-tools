"""Sort the spaces sidebar: by group (`~`, head " +", default, bottom " -"), then by name.

Herdr has no sort setting for spaces, so this reorders them through the socket API
(`workspace.move_block`): on demand from a key binding, or by itself after a space is created
or renamed when `auto_sort` enables it. The order is `groups.plan_order`.
"""
from __future__ import annotations

from typing import List, Tuple

from config import AUTO_SORT_EVENTS
from groups import plan_order
from herdr_api import Call, HerdrError, check_workspaces, list_workspaces

SORT_ATTEMPTS = 3
RETRYABLE_CODES = {"workspace_not_found", "order_mismatch"}


def sort_sidebar(call: Call, attempts: int = SORT_ATTEMPTS) -> Tuple[bool, List[str]]:
    """Reorder the spaces through `call(method, params) -> result`.

    A space created or closed between the list and the move makes the move fail or come back
    in another order; the whole list-plan-move cycle is then retried. Returns (changed, labels
    in the final order).
    """
    for attempt in range(1, attempts + 1):
        try:
            return _sort_once(call)
        except HerdrError as err:
            if err.code not in RETRYABLE_CODES or attempt == attempts:
                raise
    raise AssertionError("unreachable: attempts must be at least 1")


def _sort_once(call: Call) -> Tuple[bool, List[str]]:
    current = list_workspaces(call)
    target_ids = plan_order(current)
    labels_by_id = {space["workspace_id"]: space["label"] for space in current}
    if target_ids == [space["workspace_id"] for space in current]:
        return False, [labels_by_id[workspace_id] for workspace_id in target_ids]

    moved = check_workspaces(call("workspace.move_block", {"workspace_ids": target_ids}))
    if [space["workspace_id"] for space in moved] != target_ids:
        order = ", ".join(space["label"] for space in moved)
        raise HerdrError("Herdr returned a different order: " + order, "order_mismatch")
    return True, [space["label"] for space in moved]


def dry_run_lines(call: Call) -> List[str]:
    """The current and the target order, for `sort --dry-run`."""
    current = list_workspaces(call)
    labels_by_id = {space["workspace_id"]: space["label"] for space in current}
    return [
        "current: " + ", ".join(space["label"] for space in current),
        "target:  " + ", ".join(labels_by_id[workspace_id] for workspace_id in plan_order(current)),
    ]


def autosort_enabled(setting: str, event: str) -> bool:
    """Whether the `auto_sort` setting sorts after this hook event."""
    return event in AUTO_SORT_EVENTS[setting]
