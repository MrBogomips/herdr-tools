/* playground.js: "try it" on the home page. The visitor's space names are sorted and coloured
   by herd.js, Space Herder's own rules, with the palette and assign mode they pick, and the
   matching config.json is shown ready to copy. */
(function () {
  "use strict";

  const host = document.getElementById("playground");
  if (!host || !window.Herd || !window.PALETTES) return;

  const MAX_SPACES = 200;
  const DEBOUNCE_MS = 120;
  const GROUP_LABELS = { home: "home", head: "head +", default: "", bottom: "bottom -" };

  const names = host.querySelector("#pg-names");
  const palette = host.querySelector("#pg-palette");
  const rows = host.querySelector("[data-rows]");
  const counter = host.querySelector("[data-count]");
  const swatches = host.querySelector("[data-swatches]");
  const config = host.querySelector("[data-config]");

  let generation = 0;
  let timer = null;

  function assignMode() {
    const checked = host.querySelector('input[name="pg-assign"]:checked');
    return checked ? checked.value : "sticky";
  }

  function fillPalettes() {
    for (const name of Object.keys(window.PALETTES)) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name + " (" + window.PALETTES[name].length + ")";
      option.selected = name === "catppuccin";
      palette.appendChild(option);
    }
  }

  function row(space, colour) {
    const line = document.createElement("div");
    line.className = "srow" + (space.parent ? " child" : "");
    line.style.color = colour;
    const bar = document.createElement("span");
    bar.className = "bar";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = space.label;
    const group = document.createElement("span");
    group.className = "grp";
    group.textContent = space.parent ? "" : GROUP_LABELS[window.Herd.splitLabel(space.label).group];
    line.append(bar, name, group);
    return line;
  }

  function drawSwatches(colours, used) {
    swatches.textContent = "";
    colours.forEach((colour, index) => {
      const sw = document.createElement("span");
      sw.className = "sw" + (used.has(index) ? " used" : "");
      sw.style.background = colour;
      sw.title = colour + (used.has(index) ? " · in use" : "");
      swatches.appendChild(sw);
    });
  }

  function drawConfig(paletteName, assign) {
    config.textContent = JSON.stringify({ auto_sort: "both", palette: paletteName, assign }, null, 2);
  }

  async function update() {
    const run = ++generation;
    const spaces = window.Herd.parseSpaces(names.value).slice(0, MAX_SPACES);
    const paletteName = palette.value;
    const colours = window.PALETTES[paletteName];
    const assign = assignMode();
    let indices;
    try {
      indices = await window.Herd.colourSpaces(spaces, colours, assign);
    } catch (err) {
      // crypto.subtle exists only on HTTPS and localhost pages.
      counter.textContent = "colours need the page over HTTPS";
      return;
    }
    if (run !== generation) return; // a newer edit is already drawing
    const byId = new Map(spaces.map((space) => [space.id, space]));
    rows.textContent = "";
    for (const id of window.Herd.planOrder(spaces)) rows.appendChild(row(byId.get(id), colours[indices[id]]));
    const keys = new Set(spaces.filter((space) => !space.parent).map((space) => window.Herd.deriveKey(space.label)));
    counter.textContent = spaces.length + " spaces · " + keys.size + " customers";
    drawSwatches(colours, new Set(Object.values(indices)));
    drawConfig(paletteName, assign);
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(update, DEBOUNCE_MS);
  }

  fillPalettes();
  names.addEventListener("input", schedule);
  palette.addEventListener("change", update);
  host.querySelectorAll('input[name="pg-assign"]').forEach((input) => input.addEventListener("change", update));
  update();
})();
