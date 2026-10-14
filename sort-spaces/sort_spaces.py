#!/usr/bin/env python3
"""Sort Herdr spaces (workspaces) into groups, then by name ignoring case.

Groups, in order: the home space "~", head (name ends with " +"), default (no marker),
bottom (name ends with " -"). The marker is ignored when sorting inside a group.

Herdr has no sort setting for spaces, so this reorders them through the socket API
(`workspace.move_block`): on demand from a key binding, or by itself after a space is created
or renamed when `auto_sort` enables it. See the README.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from herdr_api import (
    Call,
    ConfigError,
    HerdrError,
    Workspace,
    check_workspaces,
    config_path,
    list_workspaces,
    load_json_config,
    notify,
    parent_of,
    plugin_lock,
    report_failure,
    socket_path,
    socket_rpc,
    worktree_parents,
)

PLUGIN_ID = "mrbogomips.sort-spaces"
HOME_LABEL = "~"
HEAD_MARKER = "+"
BOTTOM_MARKER = "-"
PINNED, HEAD, DEFAULT, BOTTOM = range(4)
MARKER_RANKS = {HEAD_MARKER: HEAD, BOTTOM_MARKER: BOTTOM}
MARKED_LABEL = re.compile(r"^(.*\S)\s+([{}])\s*$".format(re.escape(HEAD_MARKER + BOTTOM_MARKER)))
SORT_ATTEMPTS = 3
RETRYABLE_CODES = {"workspace_not_found", "order_mismatch"}
HOOK_EVENTS = ("created", "renamed")
AUTO_SORT_EVENTS = {"off": (), "created": ("created",), "renamed": ("renamed",), "both": HOOK_EVENTS}
DEFAULTS = {"auto_sort": "off"}


def parse_label(label: str) -> Tuple[int, str]:
    """Return (group rank, name without the group marker) for a space label."""
    marked = MARKED_LABEL.match(label)
    if marked:
        name, rank = marked.group(1), MARKER_RANKS[marked.group(2)]
    else:
        name, rank = label.strip(), DEFAULT
    return (PINNED if name == HOME_LABEL else rank), name


def plan_order(workspaces: List[Workspace]) -> List[str]:
    """Return workspace ids in the target order: by group, then by name.

    Worktree children sort with their parent (its group, label, then position), so a
    worktree group stays together even when other spaces share the parent's label. Equal
    keys keep their current order.
    """
    parents = worktree_parents(workspaces)

    def sort_key(space: Workspace) -> tuple:
        parent = parent_of(space, parents)
        group = parent or space
        group_rank, group_name = parse_label(group["label"])
        _, own_name = parse_label(space["label"])
        return (
            group_rank,
            group_name.casefold(),
            group["number"],
            parent is not None,
            own_name.casefold(),
            space["number"],
        )

    return [space["workspace_id"] for space in sorted(workspaces, key=sort_key)]


def sort_spaces(call: Call, attempts: int = SORT_ATTEMPTS) -> Tuple[bool, List[str]]:
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


def autosort_enabled(setting: str, event: str) -> bool:
    return event in AUTO_SORT_EVENTS[setting]


def load_settings(path: Path) -> Dict[str, Any]:
    settings = load_json_config(path, DEFAULTS)
    if not isinstance(settings["auto_sort"], str) or settings["auto_sort"] not in AUTO_SORT_EVENTS:
        raise ConfigError(
            "{}: auto_sort must be one of {}, not {!r}".format(
                path, ", ".join(AUTO_SORT_EVENTS), settings["auto_sort"]
            )
        )
    return settings


def print_dry_run(call: Call) -> None:
    current = list_workspaces(call)
    labels_by_id = {space["workspace_id"]: space["label"] for space in current}
    print("current:", ", ".join(space["label"] for space in current))
    print("target: ", ", ".join(labels_by_id[workspace_id] for workspace_id in plan_order(current)))


def run(args: argparse.Namespace) -> Optional[Tuple[bool, List[str]]]:
    """Do what the arguments ask; None means nothing was sorted (dry run or disabled hook)."""
    call = socket_rpc(socket_path(), "sort-spaces")
    if args.dry_run:
        print_dry_run(call)
        return None
    if args.hook:
        settings = load_settings(config_path(PLUGIN_ID, args.config))
        if not autosort_enabled(settings["auto_sort"], args.hook):
            return None
    with plugin_lock(PLUGIN_ID):
        return sort_spaces(call)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the current and target order only")
    parser.add_argument("--hook", choices=HOOK_EVENTS, help="run as the Herdr event hook for this event")
    parser.add_argument("--config", help="config file (default: the plugin config dir)")
    args = parser.parse_args(argv)

    try:
        outcome = run(args)
    except Exception as err:  # noqa: BLE001 - a detached key binding or hook has no other place to report
        return report_failure("sort-spaces", "Space sort failed", err, PLUGIN_ID if args.hook else None)

    if outcome is None:
        return 0
    changed, labels = outcome
    print(("sorted: " if changed else "already sorted: ") + ", ".join(labels))
    if not args.hook:
        notify("Spaces sorted" if changed else "Spaces already sorted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
