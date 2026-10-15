"""auto-tab-name git lookup: find the repository of a folder by reading `.git`, never running git."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

GIT_ENTRY = ".git"
GITDIR_PREFIX = "gitdir:"
REF_PREFIX = "ref:"
BRANCH_PREFIX = "refs/heads/"
BARE_SUFFIX = ".git"
SHORT_SHA_LENGTH = 7
SHA_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


@dataclass(frozen=True)
class RepoInfo:
    name: str  # the main repo's name, also for a linked worktree
    root: Path  # the folder that holds `.git`, as walked (symlinks not resolved)
    ref: Optional[str]  # branch, short SHA when detached, None when unreadable


def find_repo(path: Path) -> Optional[RepoInfo]:
    """The repository holding `path`, or None when there is none or `.git` is malformed."""
    start = Path(os.path.normpath(str(path)))
    for root in (start, *start.parents):
        entry = root / GIT_ENTRY
        if entry.is_dir():
            return RepoInfo(root.name, root, _read_ref(entry))
        if entry.is_file():
            return _from_git_file(root, entry)
    return None


def _from_git_file(root: Path, entry: Path) -> Optional[RepoInfo]:
    gitdir = _read_gitdir(root, entry)
    if gitdir is None:
        return None
    return RepoInfo(_linked_name(root, gitdir), root, _read_ref(gitdir))


def _read_gitdir(root: Path, entry: Path) -> Optional[Path]:
    text = _read_text(entry)
    if text is None or not text.startswith(GITDIR_PREFIX):
        return None
    value = text[len(GITDIR_PREFIX):].strip()
    return root / value if value else None  # an absolute value replaces `root`


def _linked_name(root: Path, gitdir: Path) -> str:
    """A linked worktree reports its main repository; a submodule its own folder."""
    common = _read_text(gitdir / "commondir")
    if not common:
        return root.name
    shared = (gitdir / common).resolve()
    if shared.name == GIT_ENTRY:
        return shared.parent.name
    if shared.name.endswith(BARE_SUFFIX):
        return shared.name[: -len(BARE_SUFFIX)]
    return shared.name


def _read_ref(gitdir: Path) -> Optional[str]:
    head = _read_text(gitdir / "HEAD")
    if head is None:
        return None
    if head.startswith(REF_PREFIX):
        target = head[len(REF_PREFIX):].strip()
        if target.startswith(BRANCH_PREFIX):
            target = target[len(BRANCH_PREFIX):]
        return target or None
    if SHA_PATTERN.match(head):
        return head[:SHORT_SHA_LENGTH]
    return None


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
