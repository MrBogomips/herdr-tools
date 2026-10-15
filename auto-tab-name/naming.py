"""auto-tab-name labels: turn the folder of a pane into the text of its tab."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

from config import Config
from gitinfo import RepoInfo, find_repo

ELLIPSIS = "…"
SEPARATOR = "/"
TILDE = "~"
REPO_BRANCH_JOINER = "@"
CUT_RIGHT_FORMATS = ("basename", "repo", "repo_branch")  # the others cut from the left


def tab_label(cwd: Optional[str], config: Config, home: str,
              repo_of: Callable[[Path], Optional[RepoInfo]] = find_repo) -> Optional[str]:
    """The tab name for `cwd` in the configured format, or None when there is no folder."""
    if not cwd:
        return None
    folder = os.path.normpath(cwd)
    shown = _display_path(folder, config, home)
    text = _format(folder, shown, config, repo_of)
    return _truncate(text, config)


def _display_path(folder: str, config: Config, home: str) -> str:
    base = os.path.normpath(home)
    if config.home_tilde and (folder == base or folder.startswith(base.rstrip(SEPARATOR) + SEPARATOR)):
        return TILDE + folder[len(base):]
    return folder


def _components(shown: str) -> List[str]:
    return [part for part in shown.split(SEPARATOR) if part]


def _basename(shown: str) -> str:
    parts = _components(shown)
    return parts[-1] if parts else shown  # the root folder is "/"


def _format(folder: str, shown: str, config: Config,
            repo_of: Callable[[Path], Optional[RepoInfo]]) -> str:
    if config.format == "home_path":
        return shown
    if config.format == "last_n":
        return _last_n(shown, config.depth)
    if config.format == "basename":
        return _basename(shown)
    info = repo_of(Path(folder))
    if info is None:
        return _basename(shown)
    if config.format == "repo":
        return _repo_path(folder, info, shown)
    return info.name if info.ref is None else info.name + REPO_BRANCH_JOINER + info.ref


def _last_n(shown: str, depth: int) -> str:
    parts = _components(shown)
    if len(parts) <= depth:
        return shown
    return SEPARATOR.join(parts[-depth:])


def _repo_path(folder: str, info: RepoInfo, shown: str) -> str:
    try:
        relative = Path(folder).relative_to(info.root)
    except ValueError:  # the repo root is not an ancestor of the folder
        return _basename(shown)
    if relative == Path("."):
        return info.name
    return info.name + SEPARATOR + relative.as_posix()


def _truncate(text: str, config: Config) -> str:
    limit = config.max_length
    if limit <= 0 or len(text) <= limit:
        return text
    if config.format in CUT_RIGHT_FORMATS:
        return text[: limit - 1] + ELLIPSIS
    return ELLIPSIS + text[len(text) - (limit - 1):]  # not text[-0:] when limit == 1
