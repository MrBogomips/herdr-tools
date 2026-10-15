"""auto-tab-name memory: which tabs follow their folder, kept per Herdr server."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from herdr_api import socket_path, state_dir
from jsonfile import write_json_atomic

VERSION = 1
HASH_LENGTH = 12
TEXT_KEYS = ("written", "seen", "pane")


@dataclass(frozen=True)
class TabState:
    follow: bool
    written: Optional[str] = None  # last label this plugin wrote (or adopted)
    seen: Optional[str] = None  # label observed on the last run
    pane: Optional[str] = None  # last focused pane of this tab


def state_file(plugin_id: str) -> Path:
    """The state file of the Herdr server this process talks to."""
    digest = hashlib.sha256(str(socket_path()).encode()).hexdigest()[:HASH_LENGTH]
    return state_dir(plugin_id) / "tabs-{}.json".format(digest)


def load_states(path: Path) -> Tuple[Dict[str, TabState], Optional[str]]:
    """Read the saved states; a missing file is empty, a damaged one is empty plus a warning."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, None
    except (OSError, UnicodeDecodeError) as err:
        return {}, "{}: cannot read state ({})".format(path, err)
    try:
        return _parse(json.loads(text)), None
    except ValueError as err:  # json.JSONDecodeError is a ValueError too
        return {}, "{}: {}".format(path, err)


def _parse(data: Any) -> Dict[str, TabState]:
    if not isinstance(data, dict):
        raise ValueError("state must be a JSON object")
    if data.get("version") != VERSION:
        raise ValueError("unsupported state version {!r}".format(data.get("version")))
    tabs = data.get("tabs")
    if not isinstance(tabs, dict):
        raise ValueError("'tabs' must be an object")
    return {tab_id: _parse_entry(tab_id, entry) for tab_id, entry in tabs.items()}


def _parse_entry(tab_id: str, entry: Any) -> TabState:
    if not isinstance(entry, dict) or not isinstance(entry.get("follow"), bool):
        raise ValueError("tab {!r} needs a boolean 'follow'".format(tab_id))
    for key in TEXT_KEYS:
        value = entry.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError("tab {!r}: '{}' must be text, not {!r}".format(tab_id, key, value))
    return TabState(entry["follow"], *(entry.get(key) for key in TEXT_KEYS))


def save_states(path: Path, states: Mapping[str, TabState]) -> None:
    """Write the states atomically, so a crash never leaves half a file."""
    write_json_atomic(path, {"version": VERSION, "tabs": {tab_id: asdict(state) for tab_id, state in states.items()}})
