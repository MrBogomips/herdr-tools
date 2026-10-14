"""Read-only git queries for the release helper. Nothing here commits, tags, fetches or pushes."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set, Tuple

import release_bump as rb

_SLUG = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$")
_REFLOG_TIME = re.compile(r"@\{(\d+)")


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Tag:
    name: str
    version: Tuple[int, int, int]
    commit: str
    annotated: bool


@dataclass(frozen=True)
class RawCommit:
    sha: str
    subject: str
    body: str
    paths: Tuple[str, ...]  # relative to the plugin folder


def parse_slug(url: str) -> Optional[Tuple[str, str]]:
    match = _SLUG.search(url.strip())
    return (match.group("owner"), match.group("name")) if match else None


class Git:
    def __init__(self, cwd: Path) -> None:
        try:
            top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(cwd),
                                 capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise GitError("{} is not inside a git repository".format(cwd)) from exc
        self.root = Path(top)

    def run(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(["git", *args], cwd=str(self.root), capture_output=True, text=True)
        if check and result.returncode != 0:
            raise GitError("git {} failed: {}".format(" ".join(args), result.stderr.strip()))
        return result.stdout.strip() if result.returncode == 0 else ""

    def ok(self, *args: str) -> bool:
        return subprocess.run(["git", *args], cwd=str(self.root), capture_output=True).returncode == 0

    def slug(self) -> Optional[Tuple[str, str]]:
        """owner/name from the raw origin URL (`git remote get-url` would apply insteadOf rewrites)."""
        url = self.run("config", "--get", "remote.origin.url", check=False)
        return parse_slug(url) if url else None

    def rev(self, ref: str) -> Optional[str]:
        return self.run("rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False) or None

    def branch(self) -> str:
        return self.run("rev-parse", "--abbrev-ref", "HEAD", check=False)

    def is_clean(self) -> bool:
        return self.run("status", "--porcelain") == ""

    def ahead_behind(self, ref: str, upstream: str) -> Tuple[int, int]:
        counts = self.run("rev-list", "--left-right", "--count", "{}...{}".format(ref, upstream)).split()
        return int(counts[0]), int(counts[1])

    def is_ancestor(self, older: str, newer: str) -> bool:
        return self.ok("merge-base", "--is-ancestor", older, newer)

    def in_linked_worktree(self) -> bool:
        git_dir = Path(self.run("rev-parse", "--absolute-git-dir"))
        common = Path(self.run("rev-parse", "--git-common-dir"))
        common = common if common.is_absolute() else (self.root / common)
        return git_dir.resolve() != common.resolve()

    def fetch_time(self) -> Optional[datetime]:
        """Last fetch from any worktree: FETCH_HEAD is per worktree, remote-tracking refs are shared."""
        candidates = [Path(self.run("rev-parse", "--git-path", "FETCH_HEAD")),
                      Path(self.run("rev-parse", "--git-common-dir")) / "FETCH_HEAD"]
        times = [path.stat().st_mtime for path in (p if p.is_absolute() else self.root / p for p in candidates)
                 if path.exists()]
        return datetime.fromtimestamp(max(times), timezone.utc) if times else None

    def plugin_tags(self, plugin: str) -> List[Tag]:
        """<plugin>-vX.Y.Z tags in semver order; a strict match keeps `sorter-vim` and `sorterx-v1.0.0` out."""
        pattern = re.compile(r"^{}-v(\d+\.\d+\.\d+)$".format(re.escape(plugin)))
        lines = self.run("for-each-ref", "--format=%(refname:short)%09%(objecttype)%09%(*objectname)%09%(objectname)",
                         "refs/tags/{}-v*".format(plugin)).splitlines()
        tags = []
        for line in lines:
            name, kind, peeled, target = line.split("\t")
            match = pattern.match(name)
            version = rb.parse_version(match.group(1)) if match else None
            if version:
                tags.append(Tag(name, version, peeled if kind == "tag" else target, kind == "tag"))
        return sorted(tags, key=lambda tag: tag.version)

    def remote_tags(self) -> Optional[Set[str]]:
        """Tag names on origin, or None when origin cannot be reached."""
        result = subprocess.run(["git", "ls-remote", "--tags", "origin"], cwd=str(self.root),
                                capture_output=True, text=True)
        if result.returncode != 0:
            return None
        names = (line.split("\t", 1)[1] for line in result.stdout.splitlines() if "\t" in line)
        return {name[len("refs/tags/"):].replace("^{}", "") for name in names}

    def commits_touching(self, since: Optional[str], until: str, folder: str) -> List[RawCommit]:
        """Non-merge commits in since..until that touch folder/, oldest first, paths relative to folder."""
        span = "{}..{}".format(since, until) if since else until
        shas = self.run("rev-list", "--reverse", "--no-merges", span, "--", folder + "/").split()
        commits = []
        for sha in shas:
            subject, _, body = self.run("show", "-s", "--format=%s%x00%b", sha).partition("\x00")
            paths = self.run("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha,
                             "--", folder + "/").splitlines()
            relative = tuple(path[len(folder) + 1:] for path in paths if path.startswith(folder + "/"))
            commits.append(RawCommit(sha, subject, body.strip(), relative))
        return commits

    def show_file(self, rev: str, path: str) -> Optional[str]:
        result = subprocess.run(["git", "show", "{}:{}".format(rev, path)], cwd=str(self.root),
                                capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else None

    def parent(self, sha: str) -> Optional[str]:
        return self.rev(sha + "^")

    def ref_set_time(self, ref: str, sha: str) -> Optional[datetime]:
        """When the reflog of ref last moved it to sha (push, fetch or clone)."""
        lines = self.run("log", "-g", "--date=unix", "--format=%H %gd", ref, check=False).splitlines()
        for line in lines:
            commit, _, selector = line.partition(" ")
            match = _REFLOG_TIME.search(selector)
            if commit == sha and match:
                return datetime.fromtimestamp(int(match.group(1)), timezone.utc)
        return None

    def last_version_change(self, since: Optional[str], until: str, manifest: str) -> Optional[str]:
        span = "{}..{}".format(since, until) if since else until
        out = self.run("log", "-n1", "--format=%H", "-G", "^version[[:space:]]*=", span, "--", manifest, check=False)
        return out or None

    def tracked(self, filename: str) -> List[str]:
        """Tracked and untracked (not ignored) files with this name anywhere in the tree."""
        out = self.run("ls-files", "-co", "--exclude-standard", "--", ":(glob)**/" + filename)
        return sorted(set(out.splitlines()))
