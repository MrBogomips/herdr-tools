"""The playground's JavaScript (assets/js/herd.js) must sort and colour like Space Herder.

Each case runs through herd.js under node and through Space Herder's own Python code, and the two
sidebars must match: same order, same palette index per space. Skipped when node is missing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

SITE = Path(__file__).resolve().parent
SPACE_HERDER = SITE.parent / "space-herder"
sys.path.insert(0, str(SPACE_HERDER))

from config import DEFAULTS, build_config  # noqa: E402
from groups import plan_order  # noqa: E402
from palettes import PRESETS  # noqa: E402
from plan import choose  # noqa: E402

NODE = shutil.which("node")
HERD_JS = SITE / "assets" / "js" / "herd.js"

# Reads {"cases": [...]} on stdin, prints one result per case.
HARNESS = """
const Herd = require(process.argv[1]);
let input = "";
process.stdin.on("data", chunk => { input += chunk; });
process.stdin.on("end", async () => {
  const out = [];
  for (const c of JSON.parse(input).cases) {
    const spaces = Herd.parseSpaces(c.text);
    const colours = await Herd.colourSpaces(spaces, c.colors, c.assign);
    out.push({spaces, order: Herd.planOrder(spaces), colours});
  }
  process.stdout.write(JSON.stringify(out));
});
"""

README_SIDEBAR = """\
SYS -
ACME - web
~
Globex - etl
LUMON +
ACME - api
  feature-checkout
Initech - crm
Initech - billing +
"""

EDGE_CASES = """\
  orphan child
C++
ACME-api
acme  -  web \u0020
Globex\t-\u00a0etl
Straße - ops
STRASSE - db
Ünïcode - x
x +
+
-
A -
 - b
ACME - api
ACME - api
Head +
  head-wt
  head-wt-2
~
zeta
"""

# Where JavaScript strings differ from Python's: code units against code points, case folds
# that are not lower case, and keys that are Object.prototype names.
UNICODE_CASES = """\
\uff21\uff23\uff2d\uff25 - x
\U0001f680 launch
\u2764\ufe0f a
\u2764\U0001f600 b
\ufb01nance - billing
finance - ops
\u00b5Service - api
\u03bcservice - web
\u017ftate - etl
state - crm
__proto__ - api
constructor - web
toString +
"""

MANY_CUSTOMERS = "\n".join("Customer{} - app".format(n) for n in range(20)) + "\n"


def expected(spaces: List[Dict[str, Any]], palette: str, assign: str) -> Dict[str, Any]:
    """Space Herder's order and palette indices for herd.js's parsed spaces."""
    workspaces = []
    parents = {space["parent"] for space in spaces if space["parent"]}
    for space in spaces:
        workspace = {"workspace_id": space["id"], "label": space["label"], "number": space["number"]}
        if space["parent"]:
            workspace["worktree"] = {"repo_key": space["parent"], "is_linked_worktree": True}
        elif space["id"] in parents:
            workspace["worktree"] = {"repo_key": space["id"], "is_linked_worktree": False}
        workspaces.append(workspace)
    config = build_config(dict(DEFAULTS, palette=palette, assign=assign), "test")
    choices, _ = choose(workspaces, config, {}, date.today(), {})
    return {
        "order": plan_order(workspaces),
        "colours": {workspace_id: choice.slot for workspace_id, choice in choices.items()},
    }


def run_herd(cases: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    result = subprocess.run(
        [NODE, "-e", HARNESS, str(HERD_JS)],
        input=json.dumps({"cases": cases}),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError("herd.js failed under node:\n" + result.stderr)
    return json.loads(result.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class HerdMatchesSpaceHerder(unittest.TestCase):
    def check(self, text: str, palettes: List[str]) -> None:
        cases = [
            {"text": text, "palette": name, "colors": list(PRESETS[name]), "assign": assign}
            for name in palettes
            for assign in ("hash", "sticky")
        ]
        for case, got in zip(cases, run_herd(cases)):
            with self.subTest(palette=case["palette"], assign=case["assign"]):
                want = expected(got["spaces"], case["palette"], case["assign"])
                self.assertEqual(got["order"], want["order"])
                self.assertEqual(got["colours"], want["colours"])

    def test_readme_sidebar_in_every_palette(self) -> None:
        self.check(README_SIDEBAR, sorted(PRESETS))

    def test_edge_cases(self) -> None:
        self.check(EDGE_CASES, ["catppuccin", "nord", "solarized"])

    def test_unicode_and_prototype_names(self) -> None:
        self.check(UNICODE_CASES, ["catppuccin", "nord", "one-dark"])

    def test_more_customers_than_colours(self) -> None:
        self.check(MANY_CUSTOMERS, ["nord", "one-dark", "tokyo-night"])


@unittest.skipUnless(NODE, "node is not installed")
class ParseSpaces(unittest.TestCase):
    def test_indented_lines_are_worktrees_of_the_space_above(self) -> None:
        text = "  orphan\nACME - api\n  checkout\n\n  login\nSYS -\n"
        cases = [{"text": text, "palette": "nord", "colors": list(PRESETS["nord"]), "assign": "hash"}]
        spaces = run_herd(cases)[0]["spaces"]
        self.assertEqual(
            [(space["label"], space["parent"]) for space in spaces],
            [("orphan", None), ("ACME - api", None), ("checkout", "2"), ("login", "2"), ("SYS -", None)],
        )
        self.assertEqual([space["number"] for space in spaces], [1, 2, 3, 4, 5])


if __name__ == "__main__":
    unittest.main()
