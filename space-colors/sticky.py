"""Sticky colours: each new customer key gets the least-used colour and keeps it.

Hashing alone lets two customers share a colour (with 15 colours and 6 customers, more often than
not). In sticky mode a new key starts from its hash colour but moves on to the least-used one, and
the choice is remembered in the plugin state dir, so a customer keeps its colour from then on.
Keys not seen for FORGET_AFTER_DAYS are dropped, so the folder names of unnamed spaces do not
pile up.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from herdr_api import ConfigError
from keys import color_index
from palettes import Palette

STATE_FILE_NAME = "assignments.json"
STATE_VERSION = 1
FORGET_AFTER_DAYS = 90

Entry = Dict[str, str]
Stored = Dict[str, Entry]


def assign(keys: List[str], palette: Palette, stored: Mapping[str, Entry], today: date) -> Tuple[Dict[str, int], Stored]:
    """Return ({key: palette index} for the open keys, the updated remembered entries).

    A remembered key keeps its colour while that colour is in the palette. A new key takes, from
    its hash colour onwards, the first colour used by the fewest open keys, then by the fewest
    remembered ones, so a closed customer's colour is reused last.
    """
    entries = {key: dict(value) for key, value in stored.items()}
    open_use: Counter = Counter()
    indices: Dict[str, int] = {}
    for key in keys:
        color = entries.get(key, {}).get("color")
        if color in palette:
            indices[key] = palette.index(color)
            open_use[color] += 1
            entries[key]["seen"] = today.isoformat()
    remembered_use = Counter(entry["color"] for entry in entries.values())
    for key in keys:
        if key in indices:
            continue
        index = _least_used(color_index(key, len(palette)), palette, open_use, remembered_use)
        color = palette[index]
        entries[key] = {"color": color, "seen": today.isoformat()}
        indices[key] = index
        open_use[color] += 1
        remembered_use[color] += 1
    return indices, _forget_stale(entries, set(keys), today)


def _least_used(start: int, palette: Palette, open_use: Counter, remembered_use: Counter) -> int:
    size = len(palette)
    order = [(start + offset) % size for offset in range(size)]
    # min() keeps the first of equal candidates, so ties go to the colour nearest the hash.
    return min(order, key=lambda index: (open_use[palette[index]], remembered_use[palette[index]]))


def _forget_stale(entries: Stored, open_keys: set, today: date) -> Stored:
    oldest = today - timedelta(days=FORGET_AFTER_DAYS)
    return {
        key: entry
        for key, entry in entries.items()
        if key in open_keys or date.fromisoformat(entry["seen"]) >= oldest
    }


def load_state(path: Path) -> Stored:
    """Remembered keys from the state file; a missing file is an empty state."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as err:
        raise ConfigError("{}: {} (delete it to start over)".format(path, err)) from err
    keys = raw.get("keys") if isinstance(raw, dict) else None
    if not isinstance(keys, dict) or not all(_valid_entry(entry) for entry in keys.values()):
        raise ConfigError("{}: not a space-colors state file (delete it to start over)".format(path))
    return keys


def _valid_entry(entry: Any) -> bool:
    if not isinstance(entry, dict) or not isinstance(entry.get("color"), str) or not isinstance(entry.get("seen"), str):
        return False
    try:
        date.fromisoformat(entry["seen"])
    except ValueError:
        return False
    return True


def save_state(path: Path, stored: Mapping[str, Entry]) -> None:
    """Write the state atomically, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"version": STATE_VERSION, "keys": stored}, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
