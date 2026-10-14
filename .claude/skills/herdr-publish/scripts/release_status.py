"""Where each plugin stands: last release tag, what changed since, the suggested next version, and
whether the marketplace index shows origin/main yet. Read-only."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

import release_bump as rb
import release_index as ri
import release_manifest as rm
import release_repo as repo
from release_git import Git, RawCommit, Tag


class StatusError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitGate:
    branch: str
    head: Optional[str]
    origin_main: Optional[str]
    clean: bool
    ahead: int
    behind: int
    linked_worktree: bool
    fetched_at: Optional[datetime]
    problems: Tuple[str, ...]
    notes: Tuple[str, ...]


@dataclass(frozen=True)
class PluginStatus:
    folder: str
    id: Optional[str]
    manifest_version: Optional[str]
    description: Optional[str]
    readme_row: Optional[str]
    last_tag: Optional[str]
    last_tag_commit: Optional[str]
    listed_version: Optional[str]
    state: str  # "untagged" | "released" | "unreleased" | "tag-pending" | "error"
    level: str
    next_version: Optional[str]
    tag_commit: Optional[str]
    commits: Tuple[rb.Commit, ...]
    reasons: Tuple[str, ...]
    flags: Tuple[str, ...]
    warnings: Tuple[str, ...]
    problems: Tuple[str, ...]


@dataclass(frozen=True)
class StatusReport:
    repo: str
    gate: GitGate
    index: Optional[ri.IndexState]
    index_error: Optional[str]
    plugins: Tuple[PluginStatus, ...]


def build(git: Git, plugins: Optional[Sequence[str]], index: Optional[dict], now: datetime,
          index_error: Optional[str] = None) -> StatusReport:
    slug = git.slug()
    if slug is None:
        raise StatusError("origin is not a GitHub repository; the marketplace only indexes GitHub")
    folders = select(git, plugins)
    origin_main = git.rev("origin/main")
    state = None
    listed: Dict[str, dict] = {}
    if index is not None:
        pushed_at = git.ref_set_time("refs/remotes/origin/main", origin_main) if origin_main else None
        state = ri.repo_state(index, "/".join(slug), origin_main, git.is_ancestor, pushed_at, now)
        listed = ri.listed_manifests(ri.find_repo(index, "/".join(slug)))
    remote_tags = git.remote_tags()
    rows = repo.readme_rows(git.root)
    statuses = tuple(
        plugin_status(git, folder, origin_main, remote_tags, rows.get(folder), listed.get(folder + "/" + repo.MANIFEST))
        for folder in folders
    )
    return StatusReport("/".join(slug), gate(git, origin_main), state, index_error, statuses)


def select(git: Git, plugins: Optional[Sequence[str]]) -> List[str]:
    folders = repo.plugin_folders(git.root)
    unknown = sorted(set(plugins or ()) - set(folders))
    if unknown:
        raise StatusError("no plugin folder named {}; plugins here: {}".format(", ".join(unknown), ", ".join(folders)))
    return list(plugins) if plugins else folders


def gate(git: Git, origin_main: Optional[str]) -> GitGate:
    branch = git.branch()
    clean = git.is_clean()
    ahead, behind = git.ahead_behind("HEAD", "origin/main") if origin_main else (0, 0)
    linked = git.in_linked_worktree()
    problems: List[str] = []
    notes: List[str] = []
    if not clean:
        problems.append("uncommitted changes: commit them (or set them aside) before releasing")
    if origin_main is None:
        problems.append("no origin/main: run `git fetch origin --tags` first")
    elif branch == "main" and ahead:
        problems.append("main is {} commit(s) ahead of origin/main: unpushed work would ship with the release".format(ahead))
    elif branch == "main" and behind:
        problems.append("main is {} commit(s) behind origin/main: pull before releasing".format(behind))
    if branch != "main":
        notes.append("on branch {}: tags go on main after the PR merges".format(branch))
    if linked:
        notes.append("inside a linked worktree: tag and push releases from the main checkout")
    return GitGate(branch, git.rev("HEAD"), origin_main, clean, ahead, behind, linked, git.fetch_time(),
                   tuple(problems), tuple(notes))


def plugin_status(git: Git, folder: str, origin_main: Optional[str], remote_tags: Optional[Set[str]],
                  row: Optional[List[str]], listed: Optional[dict]) -> PluginStatus:
    path = git.root / folder / repo.MANIFEST
    problems: List[str] = []
    warnings: List[str] = []
    summary = _summary(path.read_text(encoding="utf-8"), problems, "manifest")
    tags = git.plugin_tags(folder)
    last = tags[-1] if tags else None
    commits = _commits(git, folder, last) if last else ()
    suggestion = _suggest(git, folder, last, summary, commits) if last else rb.Suggestion("none", (), ())
    state, next_version, tag_commit = _state(git, folder, last, summary.version, suggestion, problems, warnings)
    if last:
        warnings.extend(_tag_warnings(git, last, origin_main, remote_tags))
    return PluginStatus(
        folder=folder, id=summary.id, manifest_version=summary.version, description=summary.description,
        readme_row=row[1] if row and len(row) > 1 else None,
        last_tag=last.name if last else None, last_tag_commit=last.commit if last else None,
        listed_version=(listed or {}).get("version"), state=state, level=suggestion.level,
        next_version=next_version, tag_commit=tag_commit, commits=commits, reasons=suggestion.reasons,
        flags=suggestion.flags, warnings=tuple(warnings), problems=tuple(problems),
    )


def _state(git: Git, folder: str, last: Optional[Tag], version: Optional[str], suggestion: rb.Suggestion,
           problems: List[str], warnings: List[str]) -> Tuple[str, Optional[str], Optional[str]]:
    """(state, next version, commit to tag) from the manifest version against the last tag."""
    current = rb.parse_version(version)
    if current is None:
        problems.append("manifest version {!r} is not plain X.Y.Z".format(version))
        return "error", None, None
    if last is None:
        return "untagged", version, None
    released = ".".join(str(part) for part in last.version)
    if current < last.version:
        problems.append("manifest {} is behind the last tag {}".format(version, last.name))
        return "error", None, None
    suggested = rb.bump(released, suggestion.level)
    if current == last.version:
        return ("released", None, None) if suggestion.level == "none" else ("unreleased", suggested, None)
    if rb.parse_version(suggested) > current:
        warnings.append("manifest says {} but the changes since {} suggest {}".format(version, last.name, suggested))
    manifest = "{}/{}".format(folder, repo.MANIFEST)
    return "tag-pending", version, git.last_version_change(last.commit, "HEAD", manifest)


def _tag_warnings(git: Git, last: Tag, origin_main: Optional[str], remote_tags: Optional[Set[str]]) -> List[str]:
    warnings = []
    if not last.annotated:
        warnings.append("{} is a lightweight tag; release tags are annotated with the notes".format(last.name))
    if remote_tags is not None and last.name not in remote_tags:
        warnings.append("{} is not on origin yet".format(last.name))
    if origin_main and not git.is_ancestor(last.commit, origin_main):
        warnings.append("{} is not reachable from origin/main (tagged on a branch or before a squash merge?)".format(
            last.name))
    return warnings


def _commits(git: Git, folder: str, last: Tag) -> Tuple[rb.Commit, ...]:
    raw = git.commits_touching(last.commit, "HEAD", folder)
    return tuple(_classify(git, folder, commit) for commit in raw if not rb.is_release_commit(commit.subject))


def _classify(git: Git, folder: str, commit: RawCommit) -> rb.Commit:
    parent = git.parent(commit.sha)
    changes = []
    for path in commit.paths:
        kind = rb.classify_path(path)
        semantic = True
        if kind in rb.SHIPPED:
            full = "{}/{}".format(folder, path)
            before = git.show_file(parent, full) if parent else None
            semantic = rb.semantic_change(path, before, git.show_file(commit.sha, full))
        changes.append(rb.FileChange(path, kind, semantic))
    return rb.Commit(commit.sha, commit.subject, commit.body, tuple(changes))


def _suggest(git: Git, folder: str, last: Tag, summary: rm.Summary, commits: Sequence[rb.Commit]) -> rb.Suggestion:
    old_text = git.show_file(last.commit, "{}/{}".format(folder, repo.MANIFEST))
    old = _summary(old_text, [], "tagged manifest") if old_text else summary
    old_keys = _config_keys(git.show_file(last.commit, "{}/config.example.json".format(folder)))
    config = git.root / folder / "config.example.json"
    new_keys = _config_keys(config.read_text(encoding="utf-8") if config.exists() else None)
    return rb.suggest(commits, old, summary, old_keys, new_keys)


def _summary(text: str, problems: List[str], label: str) -> rm.Summary:
    try:
        return rm.summarise(rm.parse(text))
    except rm.ManifestError as exc:
        problems.append("{} does not parse: {}".format(label, exc))
        return rm.summarise({})


def _config_keys(text: Optional[str]) -> FrozenSet[str]:
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        return frozenset()
    return frozenset(data) if isinstance(data, dict) else frozenset()
