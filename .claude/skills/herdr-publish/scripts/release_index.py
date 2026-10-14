"""Read the Herdr marketplace index and say whether it shows what origin/main holds.

The marketplace (herdr.dev/plugins) is an automatic index of public GitHub repositories tagged
`herdr-plugin`; it refreshes about every 30 minutes and records each repository's default-branch head
commit. A push therefore shows up on the next refresh, never instantly.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DEFAULT_URL = "https://assets.herdr.dev/plugins/index.json"
USER_AGENT = "herdr-publish-release-helper/1"
REFRESH = timedelta(minutes=30)
OVERDUE_SLACK = timedelta(minutes=10)
TIMEOUT_SECONDS = 20


class IndexLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class IndexState:
    name: str  # "current" | "pending" | "lagging" | "diverged" | "missing"
    listed_head: Optional[str]
    generated_at: Optional[datetime]
    next_refresh: Optional[datetime]
    overdue: bool
    message: str


def load(source: str) -> Dict[str, Any]:
    """The index from a URL or a local file (fixtures, offline runs)."""
    try:
        if source.startswith(("https://", "http://")):
            text = _fetch(source)
        else:
            text = Path(source).read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError) as exc:
        raise IndexLoadError("cannot read the marketplace index {}: {}".format(source, exc)) from exc
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
        raise IndexLoadError("{} is not a marketplace index (no `plugins` list)".format(source))
    return data


def _fetch(url: str) -> str:
    """urllib with a User-Agent (the CDN refuses urllib's default one), then curl, which trusts the
    system certificate store when a python.org build has no CA bundle installed."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError as first:
        curl = shutil.which("curl")
        if curl is None:
            raise IndexLoadError("cannot read the marketplace index {}: {}".format(url, first)) from first
        result = subprocess.run([curl, "-fsSL", "--max-time", str(TIMEOUT_SECONDS), "-A", USER_AGENT, url],
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise IndexLoadError("cannot read the marketplace index {}: urllib: {}; curl: {}".format(
                url, first, result.stderr.strip())) from first
        return result.stdout


def parse_time(text: Any) -> Optional[datetime]:
    if not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def find_repo(index: Dict[str, Any], slug: str) -> Optional[Dict[str, Any]]:
    wanted = slug.lower()
    for entry in index.get("plugins", []):
        if isinstance(entry, dict) and str(entry.get("fullName", "")).lower() == wanted:
            return entry
    return None


def listed_manifests(entry: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    manifests = (entry or {}).get("manifests") or []
    return {m["path"]: m for m in manifests if isinstance(m, dict) and isinstance(m.get("path"), str)}


def other_repos_with_id(index: Dict[str, Any], slug: str, plugin_id: str) -> List[str]:
    owners = []
    for entry in index.get("plugins", []):
        if not isinstance(entry, dict) or str(entry.get("fullName", "")).lower() == slug.lower():
            continue
        if any(m.get("id") == plugin_id for m in listed_manifests(entry).values()):
            owners.append(str(entry.get("fullName")))
    return owners


def repo_state(
    index: Dict[str, Any],
    slug: str,
    origin_head: Optional[str],
    is_ancestor: Callable[[str, str], bool],
    pushed_at: Optional[datetime],
    now: datetime,
) -> IndexState:
    """Compare the listed head with origin/main.

    pushed_at is when origin/main reached its current commit here (reflog), the best local proxy for
    the push time: a refresh generated before it cannot know the commit yet.
    """
    generated = parse_time(index.get("generatedAt"))
    next_refresh = generated + REFRESH if generated else None
    entry = find_repo(index, slug)
    if entry is None:
        return IndexState("missing", None, generated, next_refresh, False,
                          "{} is not in the index; see references/marketplace.md, 'Not listed?'".format(slug))
    head = entry.get("headCommit") if isinstance(entry.get("headCommit"), str) else None
    if head and origin_head and head == origin_head:
        return IndexState("current", head, generated, next_refresh, False, "the index shows origin/main")
    if not (head and origin_head and is_ancestor(head, origin_head)):
        return IndexState("diverged", head, generated, next_refresh, False,
                          "the listed head is not in origin/main's history; fetch, or check for a force push")
    if pushed_at is None or generated is None or generated < pushed_at:
        overdue = bool(next_refresh and now > next_refresh + OVERDUE_SLACK)
        return IndexState("pending", head, generated, next_refresh, overdue,
                          "the push is newer than the last refresh; it shows up on the next one")
    return IndexState("lagging", head, generated, next_refresh, False,
                      "a refresh after the push still lists the old head; re-check after the next refresh, "
                      "then run preflight (a malformed manifest is dropped)")
