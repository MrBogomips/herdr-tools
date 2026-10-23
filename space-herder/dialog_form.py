"""The new-space and rename dialogs as pure state: a form, the keys that change it, its outcome.

No terminal I/O here (that is dialog_ui.py), so every behaviour is unit-tested. Keys arrive as
names: "tab", "shift-tab", "up", "down", "left", "right", "enter", "esc", "backspace", "ctrl-u",
"ctrl-w", or one printable character.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import date
from typing import Callable, List, Mapping, Optional, Tuple

from config import Config
from folders import ListDirs, Suggestion, complete, expand, filter_suggestions, shorten
from groups import BOTTOM, CHOOSABLE_GROUPS, DEFAULT, HEAD, HOME, compose, split_label
from herdr_api import Workspace, parent_of, worktree_parents
from keys import derive_key
from sticky import Entry

NEW, RENAME = "new", "rename"
FIELDS = {NEW: ("folder", "name", "group", "colour"), RENAME: ("name", "group", "colour")}
TEXT_FIELDS = ("folder", "name")
GROUP_KEYS = {"+": HEAD, "-": BOTTOM, "=": DEFAULT}


@dataclass(frozen=True)
class Setup:
    """Everything the dialog reads once, when it opens."""

    mode: str
    home: str
    cwd: str
    workspaces: Tuple[Workspace, ...]
    config: Config
    overrides: Mapping[str, str]
    stored: Mapping[str, Entry]
    today: date
    target_id: Optional[str]
    suggestions: Tuple[Suggestion, ...]
    list_dirs: ListDirs
    is_dir: Callable[[str], bool]

    def target(self) -> Optional[Workspace]:
        return next((space for space in self.workspaces if space["workspace_id"] == self.target_id), None)


@dataclass(frozen=True)
class Outcome:
    mode: str
    workspace_id: Optional[str]  # rename only
    cwd: Optional[str]  # new only
    label: Optional[str]  # None: Herdr names the new space after its folder
    colour_key: str
    colour_changed: bool
    colour: Optional[str]  # the new override; None clears it


@dataclass(frozen=True)
class Form:
    field: str
    folder: str = ""
    query: str = ""  # the typed folder text that filters the suggestions
    folder_edited: bool = False
    pick: int = -1
    candidates: Tuple[str, ...] = ()
    name: str = ""
    group: str = DEFAULT
    colour: Optional[str] = None
    colour_touched: bool = False
    message: str = ""
    result: Optional[str] = None  # "submit" or "cancel" once done

    def outcome(self, setup: Setup) -> Outcome:
        key = colour_key(self, setup)
        chosen = shown_colour(self, setup)
        changed = self.colour_touched and colour_lock(self, setup) is None and chosen != setup.overrides.get(key)
        if setup.mode == RENAME:
            return Outcome(RENAME, setup.target_id, None, effective_label(self, setup), key, changed, chosen if changed else None)
        name, group = effective_name_group(self)
        label = effective_label(self, setup) if name or group != DEFAULT else None
        return Outcome(NEW, None, os.path.normpath(expand(self.folder, setup.home)), label, key, changed, chosen if changed else None)


def initial_form(setup: Setup) -> Form:
    if setup.mode == NEW:
        folder = shorten(setup.cwd, setup.home)
        return Form(field="folder", folder=folder, query=folder)
    target = setup.target()
    name, group = split_label(target["label"]) if target else ("", DEFAULT)
    form = Form(field="name", name=name, group=group)
    return replace(form, colour=setup.overrides.get(colour_key(form, setup)))


def effective_name_group(form: Form) -> Tuple[str, str]:
    """(name, group): a suffix typed at the end of the name wins over the group control."""
    if not form.name.strip():
        return "", DEFAULT if form.group == HOME else form.group
    name, group = split_label(form.name)
    if group in (HEAD, BOTTOM, HOME):
        return name, group
    return name, DEFAULT if form.group == HOME else form.group


def effective_label(form: Form, setup: Setup) -> str:
    """The label the space will get; a new space without a name is labelled after its folder."""
    name, group = effective_name_group(form)
    if not name:
        name = os.path.basename(os.path.normpath(expand(form.folder, setup.home))) if setup.mode == NEW else ""
    return compose(name, group)


def _parent(setup: Setup) -> Optional[Workspace]:
    target = setup.target()
    if setup.mode != RENAME or target is None or not setup.config.worktrees_follow_parent:
        return None
    return parent_of(target, worktree_parents(list(setup.workspaces)))


def colour_label(form: Form, setup: Setup) -> str:
    """The label that picks the colour: the parent's for a worktree child, else the new label."""
    parent = _parent(setup)
    return parent["label"] if parent else effective_label(form, setup)


def colour_key(form: Form, setup: Setup) -> str:
    return derive_key(colour_label(form, setup), setup.config)


def colour_lock(form: Form, setup: Setup) -> Optional[str]:
    """Why the colour can't be chosen here, or None when it can."""
    parent = _parent(setup)
    if parent:
        return "colour follows its parent " + parent["label"]
    label = effective_label(form, setup)
    rule = next((rule for rule in setup.config.rules if rule.pattern.search(label)), None)
    return "colour set by rule " + rule.match if rule else None


def shown_colour(form: Form, setup: Setup) -> Optional[str]:
    """The chosen colour: the user's pick, else the key's current override (None is automatic)."""
    return form.colour if form.colour_touched else setup.overrides.get(colour_key(form, setup))


def folder_choices(form: Form, setup: Setup) -> List[Suggestion]:
    """Completion matches of the last Tab, then the suggestions matching the typed folder."""
    head = form.query.rsplit("/", 1)[0] + "/" if "/" in form.query else ""
    matches = [Suggestion(os.path.join(expand(head, setup.home), name), "match") for name in form.candidates]
    suggestions = list(setup.suggestions)
    if form.folder_edited:
        suggestions = filter_suggestions(suggestions, form.query, setup.home)
    seen = {match.path for match in matches}
    return matches + [suggestion for suggestion in suggestions if suggestion.path not in seen]


def type_text(form: Form, text: str, setup: Setup) -> Form:
    for char in text:
        form = handle(form, char, setup)
    return form


def handle(form: Form, key: str, setup: Setup) -> Form:
    """The form after one key press."""
    form = replace(form, message="")
    if key == "esc":
        return replace(form, result="cancel")
    if key == "enter":
        return _submit(form, setup)
    if key in ("tab", "shift-tab"):
        return _tab(form, setup, 1 if key == "tab" else -1)
    if form.field in TEXT_FIELDS:
        return _edit_text(form, key, setup)
    if form.field == "group":
        return _choose_group(form, key)
    return _choose_colour(form, key, setup)


def _submit(form: Form, setup: Setup) -> Form:
    form = _normalize_name(form)
    if setup.mode == NEW:
        if not form.folder.strip():
            return replace(form, message="Choose a folder")
        if not setup.is_dir(expand(form.folder, setup.home)):
            return replace(form, message="No such folder: " + form.folder.strip())
    elif not effective_name_group(form)[0]:
        return replace(form, message="Type a name for the space")
    return replace(form, result="submit")


def _tab(form: Form, setup: Setup, step: int) -> Form:
    if step > 0 and form.field == "folder":
        text, candidates = complete(form.folder, setup.home, setup.list_dirs)
        # Completing a full folder name only adds its slash: that is no reason to stay. Several
        # matches that extend nothing are listed on the first Tab; the next one moves on.
        extended = text.rstrip("/") != form.folder.rstrip("/")
        if extended or (len(candidates) > 1 and candidates != form.candidates):
            return replace(form, folder=text, query=text, folder_edited=True, pick=-1, candidates=candidates)
    fields = FIELDS[setup.mode]
    following = fields[(fields.index(form.field) + step) % len(fields)]
    return replace(_normalize_name(form), field=following, candidates=())


def _normalize_name(form: Form) -> Form:
    """Move a suffix typed in the name into the group control."""
    name, group = effective_name_group(form)
    if not form.name.strip():
        return replace(form, group=group)
    return replace(form, name=name, group=group)


def _edit_text(form: Form, key: str, setup: Setup) -> Form:
    if form.field == "folder" and key in ("up", "down"):
        return _pick(form, setup, -1 if key == "up" else 1)
    text = form.folder if form.field == "folder" else form.name
    if key == "backspace":
        text = text[:-1]
    elif key == "ctrl-u":
        text = ""
    elif key == "ctrl-w":
        text = _drop_last_word(text, "/" if form.field == "folder" else " ")
    elif len(key) == 1 and key.isprintable():
        text += key
    else:
        return form
    if form.field == "name":
        return replace(form, name=text)
    return replace(form, folder=text, query=text, folder_edited=True, pick=-1, candidates=())


def _drop_last_word(text: str, separator: str) -> str:
    trimmed = text.rstrip(separator)
    cut = trimmed.rfind(separator)
    return trimmed[: cut + 1] if cut >= 0 else ""


def _pick(form: Form, setup: Setup, step: int) -> Form:
    choices = folder_choices(form, setup)
    pick = max(-1, min(len(choices) - 1, form.pick + step))
    folder = form.query if pick < 0 else shorten(choices[pick].path, setup.home)
    return replace(form, pick=pick, folder=folder)


def _choose_group(form: Form, key: str) -> Form:
    form = _normalize_name(form)
    if form.group == HOME:
        return form
    if key in GROUP_KEYS:
        return replace(form, group=GROUP_KEYS[key])
    step = {"left": -1, "up": -1, "right": 1, "down": 1}.get(key)
    if step is None:
        return form
    index = CHOOSABLE_GROUPS.index(form.group) + step
    return replace(form, group=CHOOSABLE_GROUPS[index % len(CHOOSABLE_GROUPS)])


def _choose_colour(form: Form, key: str, setup: Setup) -> Form:
    if colour_lock(form, setup):
        return form
    choices: List[Optional[str]] = [None] + list(setup.config.palette)
    if key in ("a", "backspace"):
        return replace(form, colour=None, colour_touched=True)
    step = {"left": -1, "up": -1, "right": 1, "down": 1}.get(key)
    if step is None:
        return form
    current = shown_colour(form, setup)
    index = choices.index(current) if current in choices else 0
    return replace(form, colour=choices[(index + step) % len(choices)], colour_touched=True)
