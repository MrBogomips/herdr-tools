"""Checks to pass before a plugin reaches main: what the marketplace needs to list it, and what this
repository's conventions and CI expect. Reads the working tree, so it also covers uncommitted work."""
from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

import release_index as ri
import release_manifest as rm
import release_repo as repo
from release_git import Git
from release_manifest import Finding

VENDORED = ("herdr_api.py", "test_herdr_api.py")
# Accepted by the schema but never delivered to [[events]] hooks (herdr plugin link warns on 0.9.3).
NOT_HOOKABLE = frozenset({"pane.updated", "layout.updated"})
TEST_TIMEOUT_SECONDS = 300
_RAN = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)


@dataclass(frozen=True)
class PreflightReport:
    findings: Tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        return not any(finding.level == "error" for finding in self.findings)


def run(git: Git, plugins: Optional[Sequence[str]], index: Optional[dict], events: Optional[FrozenSet[str]],
        python: str, run_tests: bool = True, events_note: str = "no Herdr API schema") -> PreflightReport:
    slug = git.slug()
    if slug is None:
        return PreflightReport((Finding("error", "origin is not a GitHub repository"),))
    owner, name = slug
    every = repo.plugin_folders(git.root)
    selected = list(plugins) if plugins else every
    findings: List[Finding] = [
        Finding("error", "{}: no plugin folder by that name (plugins here: {})".format(name, ", ".join(every)))
        for name in selected if name not in every
    ]
    findings.extend(_stray_manifests(git, every))
    findings.extend(_vendored(git.root, every))
    manifests = {folder: _parse(git.root / folder / repo.MANIFEST, folder, findings) for folder in every}
    findings.extend(_duplicate_ids(manifests))
    rows = repo.readme_rows(git.root)
    if events is None:
        findings.append(Finding("info", "event names not checked: {}".format(events_note)))
    for folder in selected:
        data = manifests.get(folder)
        if data is None:
            continue
        findings.extend(rm.check(data, folder, owner))
        findings.extend(_readme_row(rows.get(folder), repo.install_command(owner, name, folder), folder))
        findings.extend(_events(rm.summarise(data).events, events, folder))
        if index is not None and isinstance(data.get("id"), str):
            for other in ri.other_repos_with_id(index, "{}/{}".format(owner, name), data["id"]):
                findings.append(Finding("warn", "{}: id {} is also used by {} in the marketplace".format(
                    folder, data["id"], other)))
        if run_tests:
            findings.append(_tests(git.root / folder, folder, python))
    return PreflightReport(tuple(findings))


def schema_events(schema: Dict[str, Any]) -> Optional[FrozenSet[str]]:
    """Event names from `herdr api schema --json`: the `type` constants of the Subscription request."""
    try:
        variants = schema["schemas"]["request"]["$defs"]["Subscription"]["oneOf"]
        names = frozenset(variant["properties"]["type"]["const"] for variant in variants)
    except (KeyError, TypeError):
        return None
    return names or None


def load_schema_events(schema_file: Optional[str], herdr: str) -> Tuple[Optional[FrozenSet[str]], str]:
    """(event names, why they are missing). schema_file "" skips the check; None asks the herdr binary."""
    if schema_file == "":
        return None, "skipped (--schema-file '')"
    try:
        if schema_file:
            text = Path(schema_file).read_text(encoding="utf-8")
        else:
            text = subprocess.run([herdr, "api", "schema", "--json"], capture_output=True, text=True,
                                  check=True, timeout=30).stdout
        events = schema_events(json.loads(text))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return None, "cannot read the Herdr API schema ({})".format(exc)
    return events, "" if events else "the Herdr API schema has no Subscription types"


def _parse(path: Path, folder: str, findings: List[Finding]) -> Optional[Dict[str, Any]]:
    try:
        data = rm.parse(path.read_text(encoding="utf-8"))
    except (OSError, rm.ManifestError) as exc:
        findings.append(Finding("error", "{}: manifest does not parse, so the marketplace drops it: {}".format(
            folder, exc)))
        return None
    parser = "tomllib" if rm.tomllib is not None else "the 3.9 fallback parser (exotic TOML is refused)"
    findings.append(Finding("ok", "{}: manifest parses with {}".format(folder, parser)))
    return data


def _stray_manifests(git: Git, folders: Sequence[str]) -> List[Finding]:
    expected = {"{}/{}".format(folder, repo.MANIFEST) for folder in folders}
    return [
        Finding("error", "{}: the indexer scans the whole default branch and would list this as a plugin; "
                         "keep fixtures out of the repo or rename them".format(path))
        for path in git.tracked(repo.MANIFEST) if path not in expected
    ]


def _vendored(root: Path, folders: Sequence[str]) -> List[Finding]:
    findings = []
    for name in VENDORED:
        copies: Dict[bytes, List[str]] = defaultdict(list)
        for folder in folders:
            path = root / folder / name
            if not path.exists():
                findings.append(Finding("error", "{}: missing the vendored {} (CI compares every copy)".format(
                    folder, name)))
                continue
            copies[path.read_bytes()].append(folder)
        if len(copies) > 1:
            groups = "; ".join(", ".join(group) for group in copies.values())
            findings.append(Finding("error", "{} differs between plugins ({}): copy one over the others".format(
                name, groups)))
    return findings


def _duplicate_ids(manifests: Dict[str, Optional[Dict[str, Any]]]) -> List[Finding]:
    owners: Dict[str, List[str]] = defaultdict(list)
    for folder, data in manifests.items():
        if data and isinstance(data.get("id"), str):
            owners[data["id"]].append(folder)
    return [Finding("error", "id {} is used by {}".format(plugin_id, ", ".join(folders)))
            for plugin_id, folders in owners.items() if len(folders) > 1]


def _readme_row(row: Optional[List[str]], command: str, folder: str) -> List[Finding]:
    if row is None:
        return [Finding("error", "{}: the root README table has no `[{f}]({f}/)` row".format(folder, f=folder))]
    if not any(command in cell for cell in row):
        return [Finding("error", "{}: the README row lacks the install command `{}`".format(folder, command))]
    return []


def _events(names: Sequence[str], known: Optional[FrozenSet[str]], folder: str) -> List[Finding]:
    findings = []
    for name in names:
        if name in NOT_HOOKABLE:
            findings.append(Finding("error", "{}: [[events]] on = {!r} is never delivered to plugin hooks".format(
                folder, name)))
        elif known is not None and name not in known:
            findings.append(Finding("warn", "{}: [[events]] on = {!r} is not in this Herdr's API schema".format(
                folder, name)))
    if names and known is not None and not findings:
        findings.append(Finding("ok", "{}: hooks name known events ({})".format(folder, ", ".join(sorted(set(names))))))
    return findings


def _tests(folder_path: Path, folder: str, python: str) -> Finding:
    try:
        result = subprocess.run([python, "-m", "unittest"], cwd=str(folder_path), capture_output=True, text=True,
                                timeout=TEST_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Finding("error", "{}: tests did not run with {}: {}".format(folder, python, exc))
    ran = _RAN.search(result.stderr)
    count = ran.group(1) if ran else "?"
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        return Finding("error", "{}: tests failed with {}:\n{}".format(folder, python, tail))
    return Finding("ok", "{}: tests passed ({} tests, {})".format(folder, count, python))
