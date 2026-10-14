"""Repository layout shared by status and preflight: plugin folders and the root README table."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

MANIFEST = "herdr-plugin.toml"
_ROW_LINK = re.compile(r"^\[(?P<folder>[^\]]+)\]\((?P=folder)/?\)$")


def plugin_folders(root: Path) -> List[str]:
    """Top-level folders holding a manifest, as CI finds them (`*/herdr-plugin.toml`)."""
    return sorted(path.parent.name for path in root.glob("*/" + MANIFEST))


def readme_rows(root: Path) -> Dict[str, List[str]]:
    """{folder: cells} for each `| [folder](folder/) | ... |` row of the root README table."""
    readme = root / "README.md"
    if not readme.exists():
        return {}
    rows = {}
    for line in readme.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        match = _ROW_LINK.match(cells[0]) if cells else None
        if match:
            rows[match.group("folder")] = cells
    return rows


def install_command(owner: str, name: str, folder: str) -> str:
    return "herdr plugin install {}/{}/{}".format(owner, name, folder)
