"""Suggest a semver bump for one plugin from the commits and manifest changes since its last release.

Commits are attributed to a plugin by the paths they touch, not by their conventional-commit scope
(`fix(herdr_api)` changes every plugin). The files outrank the commit type: what ships decides whether
a release is needed, the type only decides between patch and minor. While a plugin is 0.x a breaking
change bumps the minor version, as Cargo and release-please do.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import FrozenSet, List, Optional, Sequence, Tuple

import release_manifest as rm

LEVELS = ("none", "patch", "minor", "breaking")
SHIPPED = frozenset({"code", "manifest", "config"})
NON_SHIPPING_TYPES = frozenset({"docs", "test", "chore", "ci", "style", "build"})

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_CONVENTIONAL = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?: ")
# Only the subjects the skill writes: `chore(<plugin>): release vX.Y.Z` and `chore(release): …`.
# A looser match would hide ordinary commits such as "chore(x): release the lock".
_RELEASE = re.compile(r"^chore(?:\(release\): |\([^)]*\): release v\d+\.\d+\.\d+\b)")
_DOC_SUFFIXES = (".md", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".txt")


@dataclass(frozen=True)
class FileChange:
    path: str  # relative to the plugin folder
    kind: str  # "code" | "manifest" | "config" | "docs" | "tests"
    semantic: bool  # False when only comments or formatting changed


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str
    files: Tuple[FileChange, ...]

    @property
    def short(self) -> str:
        return self.sha[:7]


@dataclass(frozen=True)
class Suggestion:
    level: str
    reasons: Tuple[str, ...]
    flags: Tuple[str, ...]
    breaking: Tuple[str, ...] = ()  # the reasons that make it breaking, for the release notes


def parse_version(text: Optional[str]) -> Optional[Tuple[int, int, int]]:
    match = _SEMVER.match(text or "")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else None


def bump(version: str, level: str) -> str:
    parsed = parse_version(version)
    if parsed is None:
        raise ValueError("not a plain X.Y.Z version: {!r}".format(version))
    major, minor, patch = parsed
    if level == "none":
        return version
    if level == "breaking" and major > 0:
        return "{}.0.0".format(major + 1)
    if level in ("breaking", "minor"):
        return "{}.{}.0".format(major, minor + 1)
    if level == "patch":
        return "{}.{}.{}".format(major, minor, patch + 1)
    raise ValueError("unknown bump level {!r}".format(level))


def conventional(subject: str, body: str) -> Tuple[Optional[str], Optional[str], bool]:
    match = _CONVENTIONAL.match(subject)
    breaking = "BREAKING CHANGE" in body or "BREAKING-CHANGE" in body
    if not match:
        return None, None, breaking
    return match.group("type"), match.group("scope"), breaking or bool(match.group("bang"))


def is_release_commit(subject: str) -> bool:
    return bool(_RELEASE.match(subject))


def classify_path(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if path.startswith("docs/") or name.lower().endswith(_DOC_SUFFIXES):
        return "docs"
    if name.startswith("test_") or name.endswith("_test.py") or path.startswith("tests/"):
        return "tests"
    if name == "herdr-plugin.toml":
        return "manifest"
    if name == "config.example.json":
        return "config"
    return "code"


def semantic_change(path: str, old: Optional[str], new: Optional[str]) -> bool:
    """False only when both versions parse to the same thing (comments, blank lines, formatting)."""
    if old is None or new is None:
        return True
    try:
        if path.endswith(".py"):
            return ast.dump(ast.parse(old)) != ast.dump(ast.parse(new))
        if path.endswith(".json"):
            return json.loads(old) != json.loads(new)
        if path.endswith(".toml"):
            return rm.parse(old) != rm.parse(new)
    except (SyntaxError, ValueError):
        return True
    return old != new


def suggest(
    commits: Sequence[Commit],
    old: rm.Summary,
    new: rm.Summary,
    old_keys: FrozenSet[str],
    new_keys: FrozenSet[str],
) -> Suggestion:
    signals: List[Tuple[str, str]] = []
    flags: List[str] = []
    for commit in commits:
        signals.extend(_commit_signals(commit, flags))
    # Always compare the contracts: a release commit (left out of `commits`) may drop a platform or raise
    # min_herdr_version, and equal contracts yield nothing.
    signals.extend(_contract_signals(old, new, old_keys, new_keys))
    level = max((level for level, _ in signals), key=LEVELS.index, default="none")
    breaking = tuple(reason for kind, reason in signals if kind == "breaking")
    return Suggestion(level, tuple(reason for _, reason in signals), tuple(flags), breaking)


def _commit_signals(commit: Commit, flags: List[str]) -> List[Tuple[str, str]]:
    kind, _, breaking = conventional(commit.subject, commit.body)
    shipped = sorted({file.kind for file in commit.files if file.kind in SHIPPED and file.semantic})
    signals = []
    if breaking:
        signals.append(("breaking", "{} is marked as a breaking change".format(commit.short)))
    if shipped:
        if kind == "feat":
            signals.append(("minor", "{} adds a feature (feat) in {}".format(commit.short, "/".join(shipped))))
        else:
            signals.append(("patch", "{} changes {} ({})".format(commit.short, "/".join(shipped), kind or "untyped")))
        if kind in NON_SHIPPING_TYPES:
            paths = ", ".join(file.path for file in commit.files if file.kind in SHIPPED and file.semantic)
            flags.append("{} is typed {} but changes shipped files: {}".format(commit.short, kind, paths))
    elif kind == "feat":
        flags.append("{} is typed feat but changes no shipped file".format(commit.short))
    return signals


def _contract_signals(
    old: rm.Summary, new: rm.Summary, old_keys: FrozenSet[str], new_keys: FrozenSet[str]
) -> List[Tuple[str, str]]:
    """What users bound or configured: removing it breaks them, adding it is a feature."""
    signals = []
    plugin_id = new.id or old.id or "<plugin id>"
    pairs = (
        ("action", old.actions, new.actions, "key bindings to {}.{{}} stop working".format(plugin_id)),
        ("pane", old.panes, new.panes, "pane entrypoint {} stops opening"),
        ("config key", old_keys, new_keys, "existing config.json files lose the {!r} setting"),
        ("platform", old.platforms, new.platforms, "users on {} can no longer install updates"),
    )
    for label, before, after, consequence in pairs:
        for removed in sorted(before - after):
            signals.append(("breaking", "removes {} {!r}: {}".format(label, removed, consequence.format(removed))))
        for added in sorted(after - before):
            signals.append(("minor", "adds {} {!r}".format(label, added)))
    for added in sorted(set(new.events) - set(old.events)):
        signals.append(("minor", "hooks event {!r}".format(added)))
    if new.startup > old.startup:
        signals.append(("minor", "adds a startup hook"))
    old_min, new_min = parse_version(old.min_herdr_version), parse_version(new.min_herdr_version)
    if old_min and new_min and new_min > old_min:
        signals.append(("breaking", "raises min_herdr_version {} -> {}: older Herdr refuses the update".format(
            old.min_herdr_version, new.min_herdr_version)))
    return signals
