"""Decide each space's colour slot and the token patches that bring Herdr up to date.

Pure functions over `workspace.list` records: no I/O, so every rule is unit-tested.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Mapping, Optional, Tuple

from config import Config, Rule
from herdr_api import Workspace, parent_of, worktree_parents
from keys import color_index, derive_key
from sticky import Entry, assign

TOKEN_PREFIX = "spc"
OWN_TOKEN = re.compile(r"^{}\d+$".format(TOKEN_PREFIX))
# Herdr limits: token values are cut at 80 characters, a report may name at most 16 keys.
MAX_VALUE_CHARS = 80
MAX_KEYS_PER_REPORT = 16
ELLIPSIS = "…"

Patch = Dict[str, Optional[str]]
Report = Tuple[str, Patch]


def token_name(slot: int) -> str:
    return "{}{}".format(TOKEN_PREFIX, slot)


@dataclass(frozen=True)
class Choice:
    key: str
    slot: int
    reason: str  # "hash", "sticky", "override" or "rule <pattern>"


def choose(
    workspaces: List[Workspace],
    config: Config,
    stored: Mapping[str, Entry],
    today: date,
    overrides: Optional[Mapping[str, str]] = None,
) -> Tuple[Dict[str, Choice], Mapping[str, Entry]]:
    """Pick every space's slot; returns ({workspace id: choice}, the remembered sticky keys).

    Rules come first (first match wins), then a colour chosen for the key in a dialog (`overrides`,
    palette colours only). Other spaces get their key's colour by hash, or in sticky mode the
    colour remembered for the key; overridden colours count as taken there. Worktree children use
    their parent's name, so a repo's checkouts share its colour.
    """
    named = colour_sources(workspaces, config)
    overridden = {key: color for key, color in (overrides or {}).items() if color in config.palette}
    automatic = list(dict.fromkeys(key for key, rule in named.values() if rule is None and key not in overridden))
    indices = {key: config.palette.index(color) for key, color in overridden.items()}
    if config.assign == "sticky":
        pinned = [config.slots[rule.slot] for _, rule in named.values() if rule and rule.slot < len(config.palette)]
        open_overrides = [overridden[key] for key, rule in named.values() if rule is None and key in overridden]
        assigned, stored = assign(automatic, config.palette, stored, today, reserved=pinned + open_overrides)
    else:
        assigned = {key: color_index(key, len(config.palette)) for key in automatic}
    indices.update(assigned)
    choices = {
        workspace_id: _choice(key, rule, indices, "override" if key in overridden else config.assign)
        for workspace_id, (key, rule) in named.items()
    }
    return choices, stored


def colour_sources(workspaces: List[Workspace], config: Config) -> Dict[str, Tuple[str, Optional[Rule]]]:
    """{workspace id: (colour key, first matching rule or None)}; children use their parent's name."""
    parents = worktree_parents(workspaces)
    named: Dict[str, Tuple[str, Optional[Rule]]] = {}
    for space in workspaces:
        parent = parent_of(space, parents) if config.worktrees_follow_parent else None
        label = (parent or space)["label"]
        rule = next((rule for rule in config.rules if rule.pattern.search(label)), None)
        named[space["workspace_id"]] = (derive_key(label, config), rule)
    return named


def _choice(key: str, rule: Optional[Rule], indices: Mapping[str, int], reason: str) -> Choice:
    if rule:
        return Choice(key, rule.slot, "rule " + rule.match)
    return Choice(key, indices[key], reason)


def display_value(label: str, marker: str) -> str:
    """The token text, normalized the way Herdr stores it so later runs compare equal."""
    text = "".join(char for char in marker + label.strip() if unicodedata.category(char) != "Cc").strip()
    if len(text) > MAX_VALUE_CHARS:
        text = text[: MAX_VALUE_CHARS - 1] + ELLIPSIS
    return text


def own_tokens(space: Workspace) -> Dict[str, str]:
    tokens = space.get("tokens")
    if not isinstance(tokens, dict):
        return {}
    return {name: value for name, value in tokens.items() if OWN_TOKEN.match(name)}


def plan_reports(workspaces: List[Workspace], choices: Mapping[str, Choice], marker: str) -> List[Report]:
    """Token patches for the spaces whose coloured name is missing or out of date."""
    reports: List[Report] = []
    for space in workspaces:
        slot = choices[space["workspace_id"]].slot
        target = {token_name(slot): display_value(space["label"], marker)}
        current = own_tokens(space)
        patch: Patch = {name: value for name, value in target.items() if current.get(name) != value}
        patch.update({name: None for name in current if name not in target})
        reports += _split(space["workspace_id"], patch)
    return reports


def clear_reports(workspaces: List[Workspace]) -> List[Report]:
    """Patches removing every space-colors token, e.g. before uninstalling."""
    reports: List[Report] = []
    for space in workspaces:
        reports += _split(space["workspace_id"], {name: None for name in own_tokens(space)})
    return reports


def _split(workspace_id: str, patch: Patch) -> List[Report]:
    items = list(patch.items())
    return [
        (workspace_id, dict(items[start : start + MAX_KEYS_PER_REPORT]))
        for start in range(0, len(items), MAX_KEYS_PER_REPORT)
    ]
