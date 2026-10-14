"""Plain-text reports for people (and the agent reading them): short lines, one fact each."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import release_bump as rb
import release_preflight as rp
import release_status as rs

LEVEL_ORDER = ("error", "warn", "info", "ok")
LEVEL_LABEL = {"error": "ERROR", "warn": "WARN ", "info": "info ", "ok": "ok   "}


def status(report: rs.StatusReport, now: datetime) -> str:
    gate = report.gate
    fetched = "fetched {}".format(_ago(gate.fetched_at, now)) if gate.fetched_at else "never fetched"
    lines = ["{}  {} @ {}  origin/main {}  ({})".format(
        report.repo, gate.branch, _short(gate.head), _short(gate.origin_main), fetched)]
    lines.extend("  ! {}".format(problem) for problem in gate.problems)
    lines.extend("  - {}".format(note) for note in gate.notes)
    lines.append(_index_line(report, now))
    for plugin in report.plugins:
        lines.append("")
        lines.extend(_plugin(plugin))
    return "\n".join(lines)


def preflight(report: rp.PreflightReport) -> str:
    findings = sorted(report.findings, key=lambda finding: LEVEL_ORDER.index(finding.level))
    lines = []
    for finding in findings:
        first, *rest = finding.message.splitlines() or [""]
        lines.append("{} {}".format(LEVEL_LABEL[finding.level], first))
        lines.extend("        {}".format(line) for line in rest)
    errors = sum(finding.level == "error" for finding in report.findings)
    warnings = sum(finding.level == "warn" for finding in report.findings)
    verdict = "passed" if report.ok else "FAILED"
    lines.append("preflight {}: {} error(s), {} warning(s)".format(verdict, errors, warnings))
    return "\n".join(lines)


def _index_line(report: rs.StatusReport, now: datetime) -> str:
    state = report.index
    if state is None:
        return "index unavailable: {}".format(report.index_error or "not read")
    parts = ["index {}".format(state.name)]
    if state.listed_head:
        parts.append("listed head {}".format(_short(state.listed_head)))
    if state.generated_at:
        parts.append("generated {} ({})".format(_clock(state.generated_at), _ago(state.generated_at, now)))
    if state.next_refresh and state.name != "current":
        parts.append("next refresh ~{}{}".format(_clock(state.next_refresh), " (overdue)" if state.overdue else ""))
    return "{}\n  {}".format(", ".join(parts), state.message)


def _plugin(plugin: rs.PluginStatus) -> List[str]:
    tag = "tag {} @ {}".format(plugin.last_tag, _short(plugin.last_tag_commit)) if plugin.last_tag else "no tag"
    listed = "listed {}".format(plugin.listed_version) if plugin.listed_version else "not listed"
    lines = ["{}  {}  manifest {}  {}  {}".format(
        plugin.folder, plugin.state, plugin.manifest_version, tag, listed)]
    lines.extend("  {}".format(line) for line in _next_step(plugin))
    lines.extend("    because {}".format(reason) for reason in plugin.reasons)
    if plugin.commits:
        shipping = plugin.state in ("unreleased", "tag-pending", "awaiting-merge")
        lines.append("  {} {}:".format("in this release, since" if shipping else "commits since", plugin.last_tag))
        lines.extend("    {} {}  [{}]".format(commit.short, commit.subject, _kinds(commit)) for commit in plugin.commits)
    if plugin.later:
        lines.append("  after the bump (not in this release):")
        lines.extend("    {} {}  [{}]".format(commit.short, commit.subject, _kinds(commit)) for commit in plugin.later)
    lines.extend("  ? {}".format(flag) for flag in plugin.flags)
    lines.extend("  ! {}".format(message) for message in plugin.problems + plugin.warnings)
    lines.append("  description: {}".format(plugin.description))
    lines.append("  README row:  {}".format(plugin.readme_row))
    return lines


def _next_step(plugin: rs.PluginStatus) -> List[str]:
    if plugin.state == "untagged":
        return ["first release: tag {}-v{} (annotated) on the commit that ships it".format(
            plugin.folder, plugin.manifest_version)]
    if plugin.state == "unreleased":
        return ["next: {} -> {} (bump the manifest, then tag {}-v{})".format(
            plugin.level, plugin.next_version, plugin.folder, plugin.next_version)]
    if plugin.state == "tag-pending":
        return ["next: tag {}-v{} on {}".format(plugin.folder, plugin.next_version, _short(plugin.tag_commit))]
    if plugin.state == "awaiting-merge" and plugin.last_tag is None:
        return ["next: merge the new plugin into main, then tag {}-v{} on the commit that lands there".format(
            plugin.folder, plugin.next_version)]
    if plugin.state == "awaiting-merge":
        return ["next: merge the bump to {} into main, then tag the commit that lands there".format(
            plugin.next_version)]
    if plugin.state == "released":
        return ["nothing to release" + (" (docs/tests only since the tag)" if plugin.commits else "")]
    return ["fix the problems below first"]


def _kinds(commit: rb.Commit) -> str:
    kinds = sorted({file.kind if file.semantic or file.kind not in rb.SHIPPED else file.kind + " (no-op)"
                    for file in commit.files})
    return ", ".join(kinds)


def _short(sha: Optional[str]) -> str:
    return sha[:7] if sha else "-"


def _clock(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%MZ")


def _ago(moment: Optional[datetime], now: datetime) -> str:
    if moment is None:
        return "unknown"
    minutes = int((now - moment).total_seconds() // 60)
    if minutes < 0:
        return "in {} min".format(-minutes)
    if minutes < 120:
        return "{} min ago".format(minutes)
    return "{} h ago".format(minutes // 60)
