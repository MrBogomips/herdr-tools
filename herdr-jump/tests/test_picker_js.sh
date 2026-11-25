#!/bin/sh
# Tests of the picker's arrow-key navigation: nextIndex(), in picker.html's <script id="nav"> block,
# runs under node with no DOM. Without node the tests are skipped, not failed.
# Usage, from anywhere: sh herdr-jump/tests/test_picker_js.sh
set -u

if ! command -v node >/dev/null 2>&1; then
  echo "skipped: node not found"
  exit 0
fi

here=$(cd "$(dirname "$0")" && pwd)
page="$here/../HerdrJump.spoon/picker.html"
work=$(mktemp -d "${TMPDIR:-/tmp}/herdr-jump-js.XXXXXX")
trap 'rm -rf "$work"' EXIT

# The block between <script id="nav"> and its </script>, each on a line of its own.
sed -n '/<script id="nav">/,/<\/script>/p' "$page" | sed '1d;$d' > "$work/nav.js"
if ! grep -q 'function nextIndex' "$work/nav.js"; then
  echo "FAIL: no nextIndex in a <script id=\"nav\"> block of $page"
  exit 1
fi

cat "$work/nav.js" - > "$work/test.js" <<'EOF'
const tests = [];
const test = (name, body) => tests.push([name, body]);
const eq = (got, want) => {
  if (got !== want) throw new Error(`got ${got}, want ${want}`);
};

// A master with two sub-sessions (one blocked), an agent alone, a master with a done sub-session.
const T = (waits) => ({ depth: 0, waits: !!waits });
const C = (waits) => ({ depth: 1, waits: !!waits });
const rows = [T(), C(), C(true), T(true), T(), C(true)];

test("all moves one row down and up", () => {
  eq(nextIndex(rows, 0, 1, "all"), 1);
  eq(nextIndex(rows, 3, -1, "all"), 2);
});
test("all stays at the ends", () => {
  eq(nextIndex(rows, 5, 1, "all"), 5);
  eq(nextIndex(rows, 0, -1, "all"), 0);
});
test("top skips sub-sessions down", () => {
  eq(nextIndex(rows, 0, 1, "top"), 3);
  eq(nextIndex(rows, 3, 1, "top"), 4);
});
test("top skips sub-sessions up", () => {
  eq(nextIndex(rows, 4, -1, "top"), 3);
  eq(nextIndex(rows, 3, -1, "top"), 0);
});
test("top from a sub-session goes up to its master", () => {
  eq(nextIndex(rows, 2, -1, "top"), 0);
  eq(nextIndex(rows, 5, -1, "top"), 4);
});
test("top from a sub-session goes down to the next top-level row", () => {
  eq(nextIndex(rows, 1, 1, "top"), 3);
});
test("top with no top-level row below stays put", () => {
  eq(nextIndex(rows, 4, 1, "top"), 4);
  eq(nextIndex(rows, 5, 1, "top"), 5);
});
test("waiting visits waiting rows, sub-sessions included", () => {
  eq(nextIndex(rows, 0, 1, "waiting"), 2);
  eq(nextIndex(rows, 2, 1, "waiting"), 3);
  eq(nextIndex(rows, 3, 1, "waiting"), 5);
  eq(nextIndex(rows, 5, -1, "waiting"), 3);
});
test("waiting with none in that direction stays put", () => {
  eq(nextIndex(rows, 5, 1, "waiting"), 5);
  eq(nextIndex(rows, 2, -1, "waiting"), 2);
});
test("waiting reaches rows beyond the ninth", () => {
  const many = Array.from({ length: 12 }, () => T(true));
  eq(nextIndex(many, 9, 1, "waiting"), 10);
  eq(nextIndex(many, 10, 1, "waiting"), 11);
});
test("nothing selected stays unselected", () => {
  eq(nextIndex(rows, -1, 1, "all"), -1);
  eq(nextIndex([], -1, 1, "top"), -1);
});
test("a single row stays selected", () => {
  eq(nextIndex([T()], 0, 1, "all"), 0);
  eq(nextIndex([T()], 0, -1, "waiting"), 0);
});
test("an unknown mode moves like all", () => {
  eq(nextIndex(rows, 0, 1, "other"), 1);
});

let failed = 0;
for (const [name, body] of tests) {
  try {
    body();
    console.log(`ok ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL ${name}: ${error.message}`);
  }
}
console.log(`${tests.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
EOF

node "$work/test.js"
