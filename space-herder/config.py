"""Space Herder settings: read config.json, validate it, and lay out the colour slots.

`auto_sort` says when the hooks sort the sidebar; every other key is about colours.

A slot is one sidebar token (`$spc<N>`) styled with one colour in Herdr's config.toml. Slots are
the palette colours in order, then each extra colour named by a rule, then one unstyled slot when
a rule asks for no colour. The order never changes for a given config, so the generated snippet
and the reported tokens agree.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Pattern, Tuple

from herdr_api import ConfigError, load_json_config
from palettes import DEFAULT_PALETTE, Palette, normalize_hex, resolve_palette

PLUGIN_ID = "mrbogomips.space-herder"
# The hook events after which each `auto_sort` setting sorts the sidebar.
AUTO_SORT_EVENTS = {"off": (), "created": ("created",), "renamed": ("renamed",), "both": ("created", "renamed")}
KEY_MODES = ("whole", "prefix", "suffix")
ASSIGN_MODES = ("hash", "sticky")
RULE_KEYS = {"match", "color"}
# A sidebar row holds at most 16 tokens and `state_icon` takes one of them.
SLOT_LIMIT = 15

DEFAULTS: Dict[str, Any] = {
    "auto_sort": "off",
    "palette": DEFAULT_PALETTE,
    "palette_size": None,
    "assign": "hash",
    "key": "prefix",
    "separator": " -",
    "ignore_case": True,
    "ignore_suffixes": [" +", " -"],
    "marker": "▌",
    "worktrees_follow_parent": True,
    "rules": [],
}


@dataclass(frozen=True)
class Rule:
    match: str
    pattern: Pattern[str]
    slot: int


@dataclass(frozen=True)
class Config:
    auto_sort: str
    palette: Palette
    palette_name: str
    assign: str
    key_mode: str
    separator: str
    ignore_case: bool
    ignore_suffixes: Tuple[str, ...]
    marker: str
    worktrees_follow_parent: bool
    rules: Tuple[Rule, ...]
    slots: Tuple[Optional[str], ...]


def load_config(path: Path) -> Config:
    return build_config(load_json_config(path, DEFAULTS), str(path))


def build_config(raw: Mapping[str, Any], source: str) -> Config:
    """Validate merged settings; every error names `source` and the offending key."""
    try:
        return _build(raw)
    except ValueError as err:
        raise ConfigError("{}: {}".format(source, err)) from err


def _build(raw: Mapping[str, Any]) -> Config:
    if not isinstance(raw["auto_sort"], str) or raw["auto_sort"] not in AUTO_SORT_EVENTS:
        raise ValueError("auto_sort must be one of {}, not {!r}".format(", ".join(AUTO_SORT_EVENTS), raw["auto_sort"]))
    palette = _palette(raw["palette"], raw["palette_size"])
    if raw["assign"] not in ASSIGN_MODES:
        raise ValueError("assign must be one of {}, not {!r}".format(", ".join(ASSIGN_MODES), raw["assign"]))
    if raw["key"] not in KEY_MODES:
        raise ValueError("key must be one of {}, not {!r}".format(", ".join(KEY_MODES), raw["key"]))
    if not isinstance(raw["separator"], str) or not raw["separator"]:
        raise ValueError("separator must be a non-empty string")
    for name in ("ignore_case", "worktrees_follow_parent"):
        if not isinstance(raw[name], bool):
            raise ValueError("{} must be true or false".format(name))
    if not isinstance(raw["marker"], str):
        raise ValueError('marker must be a string ("" for none)')
    suffixes = raw["ignore_suffixes"]
    if not isinstance(suffixes, list) or not all(isinstance(item, str) and item for item in suffixes):
        raise ValueError("ignore_suffixes must be a list of non-empty strings")
    rules, slots = _layout_rules(raw["rules"], palette, raw["ignore_case"])
    return Config(
        auto_sort=raw["auto_sort"],
        palette=palette,
        palette_name=raw["palette"].strip().lower() if isinstance(raw["palette"], str) else "custom",
        assign=raw["assign"],
        key_mode=raw["key"],
        separator=raw["separator"],
        ignore_case=raw["ignore_case"],
        ignore_suffixes=tuple(suffixes),
        marker=raw["marker"],
        worktrees_follow_parent=raw["worktrees_follow_parent"],
        rules=rules,
        slots=slots,
    )


def _palette(spec: Any, size: Any) -> Palette:
    """The palette, cut to its first `palette_size` colours when set."""
    try:
        palette = resolve_palette(spec)
    except ValueError as err:
        raise ValueError("palette: {}".format(err)) from err
    if size is None:
        return palette
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= len(palette):
        raise ValueError("palette_size must be a number from 1 to {}, or null for all colours".format(len(palette)))
    return palette[:size]


def _layout_rules(raw_rules: Any, palette: Palette, ignore_case: bool) -> Tuple[Tuple[Rule, ...], Tuple[Optional[str], ...]]:
    if not isinstance(raw_rules, list):
        raise ValueError('rules must be a list of {"match": ..., "color": ...} objects')
    slots: List[Optional[str]] = list(palette)
    parsed = [_parse_rule(number, rule, palette, ignore_case) for number, rule in enumerate(raw_rules, 1)]
    for _, _, color in parsed:
        if color is not None and color not in slots:
            slots.append(color)
    if any(color is None for _, _, color in parsed):
        slots.append(None)
    if len(slots) > SLOT_LIMIT:
        raise ValueError(_too_many_slots(len(slots), len(palette)))
    rules = tuple(Rule(match, pattern, slots.index(color)) for match, pattern, color in parsed)
    return rules, tuple(slots)


def _too_many_slots(slots: int, palette_size: int) -> str:
    message = "{} colour slots (palette plus rule colours) but a sidebar row fits {}: ".format(slots, SLOT_LIMIT)
    room = SLOT_LIMIT - (slots - palette_size)
    if room < 1:
        return message + "use fewer distinct rule colours, or palette colours in the rules"
    return message + "set palette_size to {} or less, or give the rules palette colours".format(room)


def _parse_rule(number: int, rule: Any, palette: Palette, ignore_case: bool) -> Tuple[str, Pattern[str], Optional[str]]:
    """Return (match, compiled pattern, colour); the colour is None for the unstyled slot."""
    where = "rule {}".format(number)
    if not isinstance(rule, dict):
        raise ValueError('{} must be an object like {{"match": "^ACME", "color": "#ff5555"}}'.format(where))
    unknown = sorted(set(rule) - RULE_KEYS)
    if unknown:
        raise ValueError("{}: unknown key(s) {}".format(where, ", ".join(unknown)))
    if not isinstance(rule.get("match"), str):
        raise ValueError("{}: match must be a regular expression string".format(where))
    try:
        pattern = re.compile(rule["match"], re.IGNORECASE if ignore_case else 0)
    except re.error as err:
        raise ValueError("{}: bad regular expression {!r}: {}".format(where, rule["match"], err)) from err
    return rule["match"], pattern, _rule_color(where, rule.get("color"), palette)


def _rule_color(where: str, color: Any, palette: Palette) -> Optional[str]:
    if color is None:
        return None
    if isinstance(color, int) and not isinstance(color, bool):
        if not 0 <= color < len(palette):
            raise ValueError("{}: color index {} is outside the palette (0-{})".format(where, color, len(palette) - 1))
        return palette[color]
    try:
        return normalize_hex(color)
    except ValueError as err:
        raise ValueError("{}: color must be #RGB, #RRGGBB, a palette index or null ({})".format(where, err)) from err
