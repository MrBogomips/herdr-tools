/* demo.js: the home page's session mock. A space named after its folder is renamed
   "Initech - billing +": it takes Initech's colour as you type, joins the head group on Enter
   and slides into place; then an agent blocks and herdr-jump's count goes up. It loops while it
   is on screen; with reduced motion it shows the end state. Sorting and colours come from
   herd.js, the same rules as Space Herder. */
(function () {
  "use strict";

  const root = document.getElementById("demo");
  if (!root || !window.Herd || !window.PALETTES) return;

  const ROW_HEIGHT = 24;
  // Palettes whose sticky colours keep the demo's five customers clearly apart; one per loop.
  const DEMO_PALETTES = ["nord", "kanagawa"];
  const NEW_NAME = "Initech - billing +";
  const FOLDER_NAME = "initech-billing";
  const WAITING = ["blocked", "done"];
  const GLYPHS = { blocked: "●", working: "●", done: "●", idle: "○", none: "·" };
  const STATE_COLOURS = { blocked: "#f38ba8", working: "#f9e2af", done: "#94e2d5", idle: "#a6e3a1", none: "#6c7086" };
  const START = [
    { label: "~", state: "none" },
    { label: "LUMON +", state: "blocked" },
    { label: "ACME - api", state: "working" },
    { label: "feature-checkout", state: "working", child: true },
    { label: "ACME - web", state: "working" },
    { label: "Globex - etl", state: "idle" },
    { label: "Initech - crm", state: "idle" },
    { label: "SYS -", state: "none" },
    { label: FOLDER_NAME, state: "none", focus: true },
  ];

  const rowsHost = root.querySelector("[data-rows]");
  const dialog = root.querySelector("[data-dialog]");
  const nameField = root.querySelector("[data-name]");
  const groupField = root.querySelector("[data-group]");
  const coloursField = root.querySelector("[data-colours]");
  const landsField = root.querySelector("[data-lands]");
  const note = root.querySelector("[data-note]");
  const jump = root.querySelector("[data-jump]");
  const count = root.querySelector("[data-count]");
  const paletteLabel = root.querySelector("[data-palette]");
  const pauseButton = root.querySelector("[data-pause]");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  let visible = false;
  let paused = false;
  let palette = window.PALETTES[DEMO_PALETTES[0]];
  let waiters = [];

  function freshSpaces() {
    let parent = null;
    return START.map((space, index) => {
      const id = String(index + 1);
      const entry = { id, label: space.label, number: index + 1, parent: space.child ? parent : null, state: space.state, focus: !!space.focus };
      if (!space.child) parent = id;
      return entry;
    });
  }

  function ordinal(n) {
    const suffix = n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th";
    return n + suffix;
  }

  function rowFor(space) {
    let row = rowsHost.querySelector('[data-id="' + space.id + '"]');
    if (!row) {
      row = document.createElement("div");
      row.className = "srow";
      row.dataset.id = space.id;
      row.innerHTML = '<span class="dot"></span><span class="bar"></span><span class="name"></span>';
      rowsHost.appendChild(row);
    }
    return row;
  }

  // Draws the spaces in `order` (ids), each in its palette colour.
  function draw(spaces, order, colours) {
    const byId = new Map(spaces.map((space) => [space.id, space]));
    rowsHost.style.height = spaces.length * ROW_HEIGHT + "px";
    order.forEach((id, index) => {
      const space = byId.get(id);
      const row = rowFor(space);
      row.style.transform = "translateY(" + index * ROW_HEIGHT + "px)";
      row.style.color = palette[colours[id]];
      row.classList.toggle("child", !!space.parent);
      row.classList.toggle("focus", space.focus);
      const dot = row.querySelector(".dot");
      dot.textContent = GLYPHS[space.state];
      dot.style.color = STATE_COLOURS[space.state];
      row.querySelector(".name").textContent = space.label;
    });
    count.textContent = spaces.filter((space) => WAITING.includes(space.state)).length;
  }

  function sidebarOrder(spaces) {
    return spaces.map((space) => space.id); // as Herdr shows them until the sort runs
  }

  async function paint(spaces, order) {
    draw(spaces, order || sidebarOrder(spaces), await window.Herd.colourSpaces(spaces, palette, "sticky"));
  }

  function renderSwatches(chosen) {
    coloursField.textContent = "";
    for (let i = 0; i < palette.length; i++) {
      const sw = document.createElement("span");
      sw.className = "sw" + (i === chosen ? " on" : "");
      sw.style.background = palette[i];
      coloursField.appendChild(sw);
    }
  }

  async function preview(spaces, focused, typed) {
    focused.label = typed || FOLDER_NAME;
    const colours = await window.Herd.colourSpaces(spaces, palette, "sticky");
    const group = window.Herd.splitLabel(focused.label).group;
    nameField.firstChild.textContent = typed;
    groupField.querySelectorAll("[data-g]").forEach((item) => item.classList.toggle("on", item.dataset.g === group));
    renderSwatches(colours[focused.id]);
    const place = window.Herd.planOrder(spaces).indexOf(focused.id) + 1;
    landsField.textContent = ordinal(place) + " of " + spaces.length;
    draw(spaces, sidebarOrder(spaces), colours);
  }

  function usePalette(name) {
    palette = window.PALETTES[name];
    paletteLabel.textContent = name;
  }

  function setVisible(isVisible) {
    visible = isVisible;
    if (visible && !document.hidden && !paused) {
      waiters.forEach((resolve) => resolve());
      waiters = [];
    }
  }

  // Waits `ms`, then for as long as the mock is off screen, the tab hidden or the visitor paused it.
  async function sleep(ms) {
    await new Promise((resolve) => setTimeout(resolve, ms));
    while (!visible || document.hidden || paused) await new Promise((resolve) => waiters.push(resolve));
  }

  function togglePause() {
    paused = !paused;
    root.classList.toggle("paused", paused);
    pauseButton.setAttribute("aria-pressed", String(paused));
    pauseButton.textContent = paused ? "▶ play animation" : "❚❚ pause animation";
    setVisible(visible);
  }

  async function finalState() {
    usePalette(DEMO_PALETTES[0]);
    const spaces = freshSpaces();
    const focused = spaces.find((space) => space.focus);
    focused.label = NEW_NAME;
    spaces.find((space) => space.label === "ACME - web").state = "blocked";
    dialog.hidden = true;
    note.textContent = "Renamed, recoloured, sorted · herdr-jump counts 2 agents waiting";
    await paint(spaces, window.Herd.planOrder(spaces));
  }

  async function loop() {
    for (let round = 0; ; round++) {
      usePalette(DEMO_PALETTES[round % DEMO_PALETTES.length]);
      const spaces = freshSpaces();
      const focused = spaces.find((space) => space.focus);
      dialog.hidden = true;
      jump.classList.remove("bump");
      note.textContent = "A new space, named after its folder, lands at the bottom.";
      await paint(spaces);
      await sleep(1600);

      dialog.hidden = false;
      note.textContent = "Rename it: the colour follows the customer as you type.";
      await preview(spaces, focused, "");
      await sleep(700);
      for (let i = 1; i <= NEW_NAME.length; i++) {
        await preview(spaces, focused, NEW_NAME.slice(0, i));
        await sleep(NEW_NAME[i - 1] === " " ? 120 : 75);
      }
      await sleep(900);

      dialog.hidden = true;
      note.textContent = "Enter: \" +\" pins it to the head group, next to its customer's colour.";
      await paint(spaces, window.Herd.planOrder(spaces));
      const row = rowFor(focused);
      row.classList.add("flash");
      await sleep(2200);
      row.classList.remove("flash");

      spaces.find((space) => space.label === "ACME - web").state = "blocked";
      await paint(spaces, window.Herd.planOrder(spaces));
      jump.classList.add("bump");
      note.textContent = "An agent needs you: herdr-jump counts it. ⌃⌥⌘A takes you there.";
      await sleep(4200);
    }
  }

  // Without crypto.subtle (plain HTTP) there are no colours to show: keep the static fallback.
  function giveUp() {
    root.classList.add("static");
  }

  nameField.innerHTML = '<span></span><span class="caret">&nbsp;</span>';
  if (reducedMotion) {
    pauseButton.hidden = true;
    finalState().catch(giveUp);
    return;
  }
  pauseButton.addEventListener("click", togglePause);
  new IntersectionObserver((entries) => setVisible(entries[0].isIntersecting), { threshold: 0.25 }).observe(root);
  document.addEventListener("visibilitychange", () => setVisible(visible));
  loop().catch(giveUp);
})();
