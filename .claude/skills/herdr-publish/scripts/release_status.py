"""Where each plugin stands: last release tag, what changed since, the suggested next version, and
whether the marketplace index shows origin/main yet. Read-only."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

import release_bump as rb
import release_index as ri
import release_manifest as rm
import release_repo as repo
from release_git import Git, RawCommit, Tag

NO_SUGGESTION = rb.Suggestion("none", (), ())


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
    # "untagged" | "released" | "unreleased" | "tag-pending" | "awaiting-merge" | "error"
    state: str
    level: str
    next_version: Optional[str]
    tag_commit: Optional[str]
    commits: Tuple[rb.Commit, ...]  # what the next release contains
    later: Tuple[rb.Commit, ...]  # commits after a committed bump: not in its tag
    reasons: Tuple[str, ...]
    flags: Tuple[str, ...]
    warnings: Tuple[str, ...]
    problems: Tuple[str, ...]
    breaking: Tuple[str, ...] = ()  # contract breaks, for the Breaking section of the notes


@dataclass(frozen=True)
class StatusReport:
    repo: str
    gate: GitGate
    index: Optional[ri.IndexState]
    index_error: Optional[str]
    plugins: Tuple[PluginStatus, ...]


@dataclass(frozen=True)
class _Release:
    """What plugin_status works out from the manifest version against the last tag."""
    state: str
    next_version: Optional[str] = None
    tag_commit: Optional[str] = None
    commits: Tuple[rb.Commit, ...] = ()
    later: Tuple[rb.Commit, ...] = ()
    suggestion: rb.Suggestion = NO_SUGGESTION


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
        pushed_at = git.push_time("refs/remotes/origin/main", origin_main) if origin_main else None
        committed_at = git.commit_time(origin_main) if origin_main else None
        state = ri.repo_state(index, "/".join(slug), origin_main, git.is_ancestor, now, pushed_at, committed_at)
        listed = ri.listed_manifests(ri.find_repo(index, "/".join(slug)))
    remote_tags = git.remote_tags()
    rows = repo.readme_rows(git.root)
    listed_head = state.listed_head if state else None
    statuses = []
    for folder in folders:
        status = plugin_status(git, folder, origin_main, remote_tags, rows.get(folder),
                               listed.get(folder + "/" + repo.MANIFEST), listed_head)
        misread = _listing_mismatches(git, folder, listed.get(folder + "/" + repo.MANIFEST), listed_head)
        statuses.append(replace(status, warnings=status.warnings + misread) if misread else status)
    return StatusReport("/".join(slug), gate(git, origin_main), state, index_error, tuple(statuses))


def _listing_mismatches(git: Git, folder: str, listed: Optional[dict], listed_head: Optional[str]) -> Tuple[str, ...]:
    """Fields the index lists differently from the manifest at the very commit it read."""
    if not listed or not listed_head:
        return ()
    text = git.show_file(listed_head, "{}/{}".format(folder, repo.MANIFEST))
    if text is None:
        return ()
    actual = _summary(text, [], "")
    return tuple(
        "the index lists {} {!r} but the manifest at {} says {!r}: an index-side misread; report it upstream if "
        "the next refresh keeps it".format(field, listed.get(field), listed_head[:7], getattr(actual, field))
        for field in ("id", "version", "description")
        if listed.get(field) is not None and listed.get(field) != getattr(actual, field)
    )


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
                  row: Optional[List[str]], listed: Optional[dict], listed_head: Optional[str] = None) -> PluginStatus:
    problems: List[str] = []
    warnings: List[str] = []
    summary = _summary((git.root / folder / repo.MANIFEST).read_text(encoding="utf-8"), problems, "manifest")
    tags = git.plugin_tags(folder)
    last = tags[-1] if tags else None
    release = _release(git, folder, last, summary.version, origin_main, problems, warnings)
    if release.state == "untagged":
        release = replace(release, tag_commit=_first_tag_commit(
            git, folder, summary.version or "", origin_main, listed, listed_head))
    if last:
        warnings.extend(_tag_warnings(git, last, origin_main, remote_tags))
    return PluginStatus(
        folder=folder, id=summary.id, manifest_version=summary.version, description=summary.description,
        readme_row=row[1] if row and len(row) > 1 else None,
        last_tag=last.name if last else None, last_tag_commit=last.commit if last else None,
        listed_version=(listed or {}).get("version"), state=release.state, level=release.suggestion.level,
        next_version=release.next_version, tag_commit=release.tag_commit, commits=release.commits,
        later=release.later, reasons=release.suggestion.reasons, flags=release.suggestion.flags,
        warnings=tuple(warnings), problems=tuple(problems), breaking=release.suggestion.breaking,
    )


def _release(git: Git, folder: str, last: Optional[Tag], version: Optional[str], origin_main: Optional[str],
             problems: List[str], warnings: List[str]) -> _Release:
    current = rb.parse_version(version)
    if current is None:
        problems.append("manifest version {!r} is not plain X.Y.Z".format(version))
        return _Release("error")
    if last is None:
        manifest = "{}/{}".format(folder, repo.MANIFEST)
        if origin_main and git.show_file(origin_main, manifest) is None:
            warnings.append("new plugin, not on main yet: merge it, then tag {}-v{} on the commit that lands "
                            "on main".format(folder, version))
            return _Release("awaiting-merge", next_version=version)
        return _Release("untagged", next_version=version)
    if current < last.version:
        problems.append("manifest {} is behind the last tag {}".format(version, last.name))
        return _Release("error")
    if current == last.version:
        commits = _commits(git, folder, last.commit, "HEAD")
        suggestion = _suggest(git, folder, last.commit, "HEAD", commits)
        if suggestion.level == "none":
            return _Release("released", commits=commits, suggestion=suggestion)
        return _Release("unreleased", rb.bump(_version(last), suggestion.level), commits=commits,
                        suggestion=suggestion)
    return _bumped(git, folder, last, version or "", origin_main, problems, warnings)


def _bumped(git: Git, folder: str, last: Tag, version: str, origin_main: Optional[str],
            problems: List[str], warnings: List[str]) -> _Release:
    """The manifest is ahead of the last tag: find the commit that bumped it and check it can be tagged."""
    manifest = "{}/{}".format(folder, repo.MANIFEST)
    bump = git.last_version_change(last.commit, "HEAD", manifest)
    if bump is None or _summary(git.show_file(bump, manifest) or "", [], "").version != version:
        problems.append("the version bump to {} is not committed yet: commit it, then tag that commit".format(version))
        return _Release("error")
    commits = _commits(git, folder, last.commit, bump)
    later = _commits(git, folder, bump, "HEAD")
    suggestion = _suggest(git, folder, last.commit, bump, commits)
    suggested = rb.bump(_version(last), suggestion.level)
    if rb.parse_version(suggested) > rb.parse_version(version):
        warnings.append("manifest says {} but the changes since {} suggest {}".format(version, last.name, suggested))
    shipped_later = [commit for commit in later if _ships(commit)]
    if shipped_later:
        warnings.append("{} commit(s) after the bump ship code that {}-v{} will not include: release them next".format(
            len(shipped_later), folder, version))
    on_main = git.rev("main") is not None and git.is_ancestor(bump, "main")
    if not (on_main or (origin_main and git.is_ancestor(bump, origin_main))):
        warnings.append("the bump {} is not on main: merge it first, then tag the commit that lands on main".format(
            bump[:7]))
        return _Release("awaiting-merge", version, None, commits, later, suggestion)
    if origin_main and not git.is_ancestor(bump, origin_main):
        warnings.append("the bump {} is not on origin/main yet: push main and the tag together (--atomic)".format(
            bump[:7]))
    return _Release("tag-pending", version, bump, commits, later, suggestion)


def _first_tag_commit(git: Git, folder: str, version: str, origin_main: Optional[str], listed: Optional[dict],
                      listed_head: Optional[str]) -> Optional[str]:
    """Where a plugin's first tag goes: the commit the index read, when it lists this version and the folder
    has not changed since (what users were offered); otherwise the commit on origin/main that set the version
    (for a new plugin, the commit its merge landed as)."""
    if not origin_main:
        return None
    if (listed and listed.get("version") == version and listed_head and git.is_ancestor(listed_head, origin_main)
            and not git.commits_touching(listed_head, origin_main, folder)):
        return listed_head
    return git.last_version_change(None, origin_main, "{}/{}".format(folder, repo.MANIFEST))


def _tag_warnings(git: Git, last: Tag, origin_main: Optional[str], remote_tags: Optional[Set[str]]) -> List[str]:
    warnings = []
    if not last.annotated:
        warnings.append("{} is a lightweight tag; release tags are annotated with the notes".format(last.name))
    if remote_tags is None:
        warnings.append("could not check that {} is on origin: origin is unreachable".format(last.name))
    elif last.name not in remote_tags:
        warnings.append("{} is not on origin yet".format(last.name))
    if origin_main and not git.is_ancestor(last.commit, origin_main):
        warnings.append("{} is not reachable from origin/main (tagged on a branch or before a squash merge?)".format(
            last.name))
    return warnings


def _commits(git: Git, folder: str, since: str, until: str) -> Tuple[rb.Commit, ...]:
    raw = git.commits_touching(since, until, folder)
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


def _suggest(git: Git, folder: str, since: str, until: str, commits: Sequence[rb.Commit]) -> rb.Suggestion:
    """Compare the manifest and config.example.json contracts at the tag and at `until`."""
    manifest = "{}/{}".format(folder, repo.MANIFEST)
    config = "{}/config.example.json".format(folder)
    new = _summary(git.show_file(until, manifest) or "", [], "")
    old_text = git.show_file(since, manifest)
    old = _summary(old_text, [], "") if old_text else new
    return rb.suggest(commits, old, new, _config_keys(git.show_file(since, config)),
                      _config_keys(git.show_file(until, config)))


def _ships(commit: rb.Commit) -> bool:
    return any(file.kind in rb.SHIPPED and file.semantic for file in commit.files)


def _version(tag: Tag) -> str:
    return ".".join(str(part) for part in tag.version)


def _summary(text: str, problems: List[str], label: str) -> rm.Summary:
    try:
        return rm.summarise(rm.parse(text))
    except rm.ManifestError as exc:
        if label:
            problems.append("{} does not parse: {}".format(label, exc))
        return rm.summarise({})


def _config_keys(text: Optional[str]) -> FrozenSet[str]:
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        return frozenset()
    return frozenset(data) if isinstance(data, dict) else frozenset()
