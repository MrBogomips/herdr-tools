/* herd.js: Space Herder's sort and colour rules, for the site's playground and demo.

   A port of space-herder/groups.py (split_label, plan_order), keys.py (derive_key, color_index)
   and sticky.py (assign), with the default config and no rules or overrides. test_herd.py runs
   it under node against the Python code, so the two cannot drift apart unnoticed.

   A space is {id, label, number, parent}: `number` is its 1-based place in the current sidebar,
   `parent` the id of the space holding its main checkout when it is a worktree, else null. */
(function (root) {
  "use strict";

  const GROUPS = ["home", "head", "default", "bottom"];
  const HOME_LABEL = "~";
  const MARKED_LABEL = /^(.*\S)\s+([+-])\s*$/;
  const MARKER_GROUPS = { "+": "head", "-": "bottom" };
  const SEPARATOR = " -";
  const IGNORE_SUFFIXES = [" +", " -"];
  const HASH_BYTES = 8;

  // Python's str.casefold for the names people type: lower case, plus the letters whose case
  // fold differs from their lower case form. Rarer folds (and the few whitespace characters the
  // two languages class differently) are left out.
  const FOLDS = { "ß": "ss", "ς": "σ", "µ": "μ", "ſ": "s", "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st" };
  const FOLDABLE = new RegExp("[" + Object.keys(FOLDS).join("") + "]", "g");

  function casefold(text) {
    return text.toLowerCase().replace(FOLDABLE, (char) => FOLDS[char]);
  }

  function strip(text) {
    return text.replace(/^\s+|\s+$/g, "");
  }

  // [name without the group suffix, group]
  function splitLabel(label) {
    const marked = MARKED_LABEL.exec(label);
    const name = marked ? marked[1] : strip(label);
    const group = marked ? MARKER_GROUPS[marked[2]] : "default";
    return { name, group: name === HOME_LABEL ? "home" : group };
  }

  // Strings compare by code point, as in Python; `<` on strings compares UTF-16 code units,
  // which puts an emoji before "Ａ" (U+FF21).
  function compareValues(a, b) {
    if (typeof a !== "string") return a < b ? -1 : a > b ? 1 : 0;
    const left = Array.from(a, (char) => char.codePointAt(0));
    const right = Array.from(b, (char) => char.codePointAt(0));
    for (let i = 0; i < Math.min(left.length, right.length); i++) {
      if (left[i] !== right[i]) return left[i] < right[i] ? -1 : 1;
    }
    return left.length - right.length;
  }

  function compareTuples(a, b) {
    for (let i = 0; i < a.length; i++) {
      const order = compareValues(a[i], b[i]);
      if (order) return order;
    }
    return 0;
  }

  // Ids in sidebar order: by group, then by name without the suffix, ignoring case; worktree
  // children right under their parent.
  function planOrder(spaces) {
    const byId = new Map(spaces.map((space) => [space.id, space]));
    const sortKey = (space) => {
      const parent = space.parent ? byId.get(space.parent) || null : null;
      const head = parent || space;
      const headLabel = splitLabel(head.label);
      return [
        GROUPS.indexOf(headLabel.group),
        casefold(headLabel.name),
        head.number,
        parent ? 1 : 0,
        casefold(splitLabel(space.label).name),
        space.number,
      ];
    };
    const keyed = spaces.map((space) => ({ id: space.id, key: sortKey(space) }));
    keyed.sort((a, b) => compareTuples(a.key, b.key));
    return keyed.map((entry) => entry.id);
  }

  function stripSuffix(text) {
    for (const suffix of IGNORE_SUFFIXES) {
      if (text.endsWith(suffix) && text.length > suffix.length) {
        return text.slice(0, -suffix.length).replace(/\s+$/, "");
      }
    }
    return text;
  }

  // The part of the name that picks the colour: the text before " -", or the whole name.
  function deriveKey(label) {
    let text = label.normalize("NFC").split(/\s+/).filter(Boolean).join(" ");
    text = stripSuffix(text);
    const at = text.indexOf(SEPARATOR);
    const side = at >= 0 ? strip(text.slice(0, at)) : "";
    return casefold(at >= 0 && side ? side : text);
  }

  function subtleCrypto() {
    if (root.crypto && root.crypto.subtle) return root.crypto.subtle;
    return require("crypto").webcrypto.subtle; // node without a global crypto
  }

  // sha256 of the key, first 8 bytes big-endian, modulo the palette size.
  async function colorIndex(key, size) {
    const digest = new Uint8Array(await subtleCrypto().digest("SHA-256", new TextEncoder().encode(key)));
    let value = 0n;
    for (let i = 0; i < HASH_BYTES; i++) value = (value << 8n) | BigInt(digest[i]);
    return Number(value % BigInt(size));
  }

  // Sticky mode with nothing remembered: from its hash colour on, each new key takes the first
  // colour used by the fewest keys so far. Returns a Map, since a key can be any text
  // ("__proto__", say).
  async function assignSticky(keys, size) {
    const use = new Array(size).fill(0);
    const indices = new Map();
    for (const key of keys) {
      const start = await colorIndex(key, size);
      let best = start;
      for (let offset = 1; offset < size; offset++) {
        const index = (start + offset) % size;
        if (use[index] < use[best]) best = index;
      }
      indices.set(key, best);
      use[best] += 1;
    }
    return indices;
  }

  // {space id: palette index}; worktree children take their parent's colour.
  async function colourSpaces(spaces, palette, assign) {
    const size = palette.length;
    const byId = new Map(spaces.map((space) => [space.id, space]));
    const keyOf = new Map();
    for (const space of spaces) {
      const parent = space.parent ? byId.get(space.parent) : null;
      keyOf.set(space.id, deriveKey((parent || space).label));
    }
    const keys = [...new Set(keyOf.values())];
    let indices = new Map();
    if (assign === "sticky") {
      indices = await assignSticky(keys, size);
    } else {
      for (const key of keys) indices.set(key, await colorIndex(key, size));
    }
    const colours = {};
    for (const space of spaces) colours[space.id] = indices.get(keyOf.get(space.id));
    return colours;
  }

  // One space per non-blank line, in sidebar order; an indented line is a worktree of the
  // closest unindented line above it.
  function parseSpaces(text) {
    const spaces = [];
    let parent = null;
    for (const line of text.split(/\r?\n/)) {
      const label = strip(line);
      if (!label) continue;
      const id = String(spaces.length + 1);
      const indented = /^\s/.test(line);
      spaces.push({ id, label, number: spaces.length + 1, parent: indented && parent ? parent : null });
      if (!indented) parent = id;
    }
    return spaces;
  }

  const api = { GROUPS, splitLabel, planOrder, deriveKey, colorIndex, colourSpaces, parseSpaces };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Herd = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
