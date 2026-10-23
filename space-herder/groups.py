"""The sidebar groups and their order, shared by the sort and the dialogs' preview.

A name suffix picks the group: home (the name "~"), head (ends with " +"), default (no suffix),
bottom (ends with " -"). The space before the suffix is required, so `C++` stays in the default
group.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from herdr_api import Workspace, parent_of, worktree_parents

HOME, HEAD, DEFAULT, BOTTOM = "home", "head", "default", "bottom"
GROUPS = (HOME, HEAD, DEFAULT, BOTTOM)
CHOOSABLE_GROUPS = (HEAD, DEFAULT, BOTTOM)
HOME_LABEL = "~"
SUFFIXES = {HEAD: " +", BOTTOM: " -"}
MARKED_LABEL = re.compile(r"^(.*\S)\s+([+-])\s*$")
MARKER_GROUPS = {"+": HEAD, "-": BOTTOM}


def split_label(label: str) -> Tuple[str, str]:
    """Return (name without the group suffix, group) for a space label."""
    marked = MARKED_LABEL.match(label)
    if marked:
        name, group = marked.group(1), MARKER_GROUPS[marked.group(2)]
    else:
        name, group = label.strip(), DEFAULT
    return name, (HOME if name == HOME_LABEL else group)


def compose(name: str, group: str) -> str:
    """The label for a name in a group: the name plus the group's suffix ("~" never gets one)."""
    name = name.strip()
    if name == HOME_LABEL:
        return name
    return name + SUFFIXES.get(group, "")


def plan_order(workspaces: List[Workspace]) -> List[str]:
    """Workspace ids in sidebar order: by group, then by name without the suffix, ignoring case.

    Worktree children sort with their parent (its group, label, then position), so a worktree
    group stays together even when other spaces share the parent's label. Equal keys keep their
    current order.
    """
    parents = worktree_parents(workspaces)

    def sort_key(space: Workspace) -> tuple:
        parent = parent_of(space, parents)
        group = parent or space
        group_name, group_group = split_label(group["label"])
        own_name, _ = split_label(space["label"])
        return (
            GROUPS.index(group_group),
            group_name.casefold(),
            group["number"],
            parent is not None,
            own_name.casefold(),
            space["number"],
        )

    return [space["workspace_id"] for space in sorted(workspaces, key=sort_key)]
