"""Colours chosen in the new-space and rename dialogs: one colour per key, kept until cleared.

A chosen colour beats the key's hash or sticky colour, but not a rule. Unlike sticky
assignments, overrides never expire: each one is an explicit choice. The file lives in the plugin
state dir; write it under `plugin_lock(per_server=False)`, since every Herdr server shares it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from herdr_api import ConfigError
from statefile import write_json_atomic

OVERRIDES_FILE_NAME = "overrides.json"
OVERRIDES_VERSION = 1

Overrides = Dict[str, str]


def load_overrides(path: Path) -> Overrides:
    """{key: "#rrggbb"} from the overrides file; a missing file has none."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as err:
        raise ConfigError("{}: {} (delete it to start over)".format(path, err)) from err
    keys = raw.get("keys") if isinstance(raw, dict) else None
    if not isinstance(keys, dict) or not all(_valid_entry(entry) for entry in keys.values()):
        raise ConfigError("{}: not a space-colors overrides file (delete it to start over)".format(path))
    return {key: entry["color"] for key, entry in keys.items()}


def _valid_entry(entry: Any) -> bool:
    return isinstance(entry, dict) and isinstance(entry.get("color"), str)


def save_overrides(path: Path, overrides: Mapping[str, str]) -> None:
    keys = {key: {"color": color} for key, color in overrides.items()}
    write_json_atomic(path, {"version": OVERRIDES_VERSION, "keys": keys})


def with_override(overrides: Mapping[str, str], key: str, color: Optional[str]) -> Overrides:
    """A copy of `overrides` with `key` set to `color`, or removed when `color` is None."""
    updated = {name: value for name, value in overrides.items() if name != key}
    if color is not None:
        updated[key] = color
    return updated
