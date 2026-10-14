"""Release notes for an annotated tag: the shipped changes since the last release, grouped."""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import release_bump as rb

GROUPS = ("Breaking", "Features", "Fixes", "Other")


def render(plugin: str, version: str, commits: Sequence[rb.Commit], breaking: Sequence[str] = ()) -> str:
    """`breaking` holds contract breaks found by comparing manifests, which a commit may not mark with `!`."""
    groups: Dict[str, List[str]] = {name: [] for name in GROUPS}
    groups["Breaking"].extend("- {}".format(reason) for reason in breaking)
    for commit in commits:
        if rb.is_release_commit(commit.subject) or not _ships(commit):
            continue
        kind, _, breaking = rb.conventional(commit.subject, commit.body)
        group = "Breaking" if breaking else {"feat": "Features", "fix": "Fixes"}.get(kind or "", "Other")
        groups[group].append("- {} ({})".format(_description(commit.subject), commit.short))
    lines = ["{} {}".format(plugin, version), ""]
    if not any(groups.values()):
        lines.append("No changes to shipped files.")
    for name in GROUPS:
        if groups[name]:
            lines.extend([name, *groups[name], ""])
    return "\n".join(lines).rstrip() + "\n"


def render_first(plugin: str, version: str, description: Optional[str]) -> str:
    """A plugin's first tag has no previous release to diff against: say what the plugin does."""
    lines = ["{} {}".format(plugin, version), "", "First release."]
    if description:
        lines.extend(["", description])
    return "\n".join(lines) + "\n"


def _ships(commit: rb.Commit) -> bool:
    return any(file.kind in rb.SHIPPED and file.semantic for file in commit.files)


def _description(subject: str) -> str:
    _, separator, rest = subject.partition(": ")
    return rest if separator and rb.conventional(subject, "")[0] else subject
