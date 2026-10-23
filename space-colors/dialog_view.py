"""What the dialogs show besides the fields: the sidebar preview, the hints and the key help.

Pure functions of the form and its setup; dialog_ui.py lays them out on the terminal.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional

from dialog_form import (
    NEW,
    Form,
    Setup,
    colour_label,
    colour_lock,
    effective_label,
    effective_name_group,
    shown_colour,
)
from groups import BOTTOM, HEAD, HOME, plan_order
from herdr_api import Workspace, parent_of, worktree_parents
from keys import derive_key
from overrides import with_override
from plan import choose, display_value

NEW_SPACE_ID = "__new__"
GROUP_HINTS = {
    HOME: '"~" is the home space: always first',
    HEAD: 'head: the name ends with " +", pinned above the other spaces',
    BOTTOM: 'bottom: the name ends with " -", kept at the end',
}
DEFAULT_HINT = 'default: no suffix, sorted by name between head (" +") and bottom (" -")'
FIELD_HELP = {
    "folder": "Tab complete  ↑↓ suggestions",
    "name": 'end with " +" or " -" to pick the group  Tab next',
    "group": "←→ group  Tab next",
    "colour": "←→ colour  a auto  Tab next",
}


@dataclass(frozen=True)
class PreviewRow:
    text: str
    colour: Optional[str]  # None: Herdr's default text colour
    target: bool  # the space being created or renamed
    child: bool = False  # a worktree child, drawn under its parent


def preview_rows(form: Form, setup: Setup) -> List[PreviewRow]:
    """The sidebar as sort-spaces will order it and space-colors colour it, with this space in it."""
    spaces = _spaces_with_target(form, setup)
    parents = worktree_parents(spaces)
    overrides = dict(setup.overrides)
    if form.colour_touched and colour_lock(form, setup) is None:
        key = derive_key(colour_label(form, setup), setup.config)
        overrides = with_override(overrides, key, form.colour)
    choices, _ = choose(spaces, setup.config, setup.stored, setup.today, overrides)
    by_id: Dict[str, Workspace] = {space["workspace_id"]: space for space in spaces}
    target_id = NEW_SPACE_ID if setup.mode == NEW else setup.target_id
    return [
        PreviewRow(
            display_value(by_id[workspace_id]["label"], setup.config.marker),
            setup.config.slots[choices[workspace_id].slot],
            workspace_id == target_id,
            parent_of(by_id[workspace_id], parents) is not None,
        )
        for workspace_id in plan_order(spaces)
    ]


def _spaces_with_target(form: Form, setup: Setup) -> List[Workspace]:
    label = effective_label(form, setup)
    if setup.mode == NEW:
        number = max([space["number"] for space in setup.workspaces] + [0]) + 1
        return list(setup.workspaces) + [{"workspace_id": NEW_SPACE_ID, "label": label, "number": number}]
    return [
        {**space, "label": label} if space["workspace_id"] == setup.target_id else space for space in setup.workspaces
    ]


def group_hint(form: Form, setup: Setup) -> str:
    return GROUP_HINTS.get(effective_name_group(form)[1], DEFAULT_HINT)


def colour_hint(form: Form, setup: Setup) -> str:
    lock = colour_lock(form, setup)
    if lock:
        return lock
    key = derive_key(colour_label(form, setup), replace(setup.config, ignore_case=False))
    if shown_colour(form, setup) is None:
        return "auto: every {} space keeps its automatic colour".format(key)
    return "every {} space takes this colour".format(key)


def help_line(form: Form, setup: Setup) -> str:
    verb = "create" if setup.mode == NEW else "rename"
    return "{}  Enter {}  Esc cancel".format(FIELD_HELP[form.field], verb)
