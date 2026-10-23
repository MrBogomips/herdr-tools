"""Folder input for the new-space dialog: Tab completion and suggested folders.

Suggestions come from the folders recently used in the dialog (`recent.json` in the plugin state
dir), the folders of open panes, and zoxide when it is installed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from herdr_api import ConfigError
from statefile import write_json_atomic

RECENT_FILE_NAME = "recent.json"
RECENT_VERSION = 1
RECENT_LIMIT = 20
ZOXIDE_LIMIT = 10
ZOXIDE_TIMEOUT_SECONDS = 1.0

ListDirs = Callable[[str], List[str]]


class Suggestion(NamedTuple):
    path: str  # absolute
    source: str  # "recent", "open" or "zoxide"


def expand(text: str, home: str) -> str:
    """The typed path with a leading "~" replaced by the home folder."""
    text = text.strip()
    if text == "~" or text.startswith("~/"):
        return home + text[1:]
    return text


def shorten(path: str, home: str) -> str:
    """The path with the home folder written as "~"."""
    if path == home:
        return "~"
    if path.startswith(home.rstrip("/") + "/"):
        return "~" + path[len(home.rstrip("/")) :]
    return path


def complete(text: str, home: str, list_dirs: ListDirs) -> Tuple[str, Tuple[str, ...]]:
    """Complete the last part of a typed path; returns (new text, matching folder names).

    One match completes it with a trailing slash; several extend it to their common prefix.
    Hidden folders match only when the typed part starts with ".". Paths must be absolute or
    start with "~".
    """
    if text == "~":
        text = "~/"
    if "/" not in text:
        return text, ()
    head, base = text.rsplit("/", 1)
    head_text = head + "/"
    names = sorted(
        (
            name
            for name in list_dirs(expand(head_text, home))
            if name.casefold().startswith(base.casefold()) and (base.startswith(".") or not name.startswith("."))
        ),
        key=str.casefold,
    )
    if not names:
        return text, ()
    if len(names) == 1:
        return head_text + names[0] + "/", tuple(names)
    common = len(os.path.commonprefix([name.casefold() for name in names]))
    if common > len(base):
        return head_text + names[0][:common], tuple(names)
    return text, tuple(names)


def list_dirs(path: str) -> List[str]:
    """Names of the folders in `path` (symlinks to folders included); [] when unreadable."""
    try:
        with os.scandir(path) as entries:
            return [entry.name for entry in entries if _is_dir(entry)]
    except OSError:
        return []


def _is_dir(entry: os.DirEntry) -> bool:
    try:
        return entry.is_dir()
    except OSError:
        return False


def merge_suggestions(recent: Iterable[str], open_folders: Iterable[str], zoxide: Iterable[str]) -> List[Suggestion]:
    """Every suggested folder once, recent ones first, then open panes, then zoxide."""
    merged: List[Suggestion] = []
    seen = set()
    for source, paths in (("recent", recent), ("open", open_folders), ("zoxide", zoxide)):
        for path in paths:
            if path and path not in seen:
                seen.add(path)
                merged.append(Suggestion(path, source))
    return merged


def filter_suggestions(suggestions: Sequence[Suggestion], text: str, home: str) -> List[Suggestion]:
    """The suggestions whose path contains the typed text, ignoring case."""
    needle = expand(text, home).casefold()
    return [suggestion for suggestion in suggestions if needle in suggestion.path.casefold()]


def zoxide_folders(
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> List[str]:
    """zoxide's best-ranked folders, or [] when zoxide is missing, slow or failing."""
    binary = which("zoxide")
    if not binary:
        return []
    try:
        result = run(
            [binary, "query", "--list"], capture_output=True, text=True, timeout=ZOXIDE_TIMEOUT_SECONDS, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in result.stdout.splitlines() if line.strip()][:ZOXIDE_LIMIT]


def load_recent(path: Path) -> List[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as err:
        raise ConfigError("{}: {} (delete it to start over)".format(path, err)) from err
    folders = raw.get("folders") if isinstance(raw, dict) else None
    if not isinstance(folders, list) or not all(isinstance(folder, str) for folder in folders):
        raise ConfigError("{}: not a space-colors recent folders file (delete it to start over)".format(path))
    return folders


def save_recent(path: Path, folders: Sequence[str]) -> None:
    write_json_atomic(path, {"version": RECENT_VERSION, "folders": list(folders)})


def remember(folders: Sequence[str], folder: str) -> List[str]:
    """`folders` with `folder` moved to the front, at most RECENT_LIMIT long."""
    return ([folder] + [item for item in folders if item != folder])[:RECENT_LIMIT]
