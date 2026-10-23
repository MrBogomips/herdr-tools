/* site.js: the ink/paper switch, copy buttons, and the palette swatches of the Space Herder page. */
(function () {
  "use strict";

  const MODE_KEY = "herdr-tools.mode";
  const COPIED_MS = 1400;

  function currentMode() {
    const explicit = document.documentElement.dataset.mode;
    if (explicit) return explicit;
    return matchMedia("(prefers-color-scheme: light)").matches ? "paper" : "ink";
  }

  function setupModeSwitch() {
    const button = document.querySelector(".mode");
    if (!button) return;
    button.addEventListener("click", () => {
      const next = currentMode() === "ink" ? "paper" : "ink";
      document.documentElement.dataset.mode = next;
      try {
        localStorage.setItem(MODE_KEY, next);
      } catch (err) {
        // Private windows can refuse storage: the switch still works for this page.
      }
    });
  }

  async function copyText(button, text) {
    // Read the label once: a second click while "copied" shows must not keep that as the label.
    if (!button.dataset.label) button.dataset.label = button.textContent;
    const label = button.dataset.label;
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "copied";
      button.dataset.done = "";
    } catch (err) {
      button.textContent = "select & copy";
    }
    setTimeout(() => {
      button.textContent = label;
      delete button.dataset.done;
    }, COPIED_MS);
  }

  // A `.cmd` box copies its command; every `pre.code` gets a copy button for its text.
  function setupCopyButtons() {
    document.querySelectorAll(".cmd").forEach((box) => {
      const button = box.querySelector("button");
      const code = box.querySelector("code");
      if (button && code) button.addEventListener("click", () => copyText(button, code.textContent));
    });
    document.querySelectorAll("pre.code").forEach((pre) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "copy";
      button.textContent = "copy";
      button.setAttribute("aria-label", "Copy this code");
      button.addEventListener("click", () => copyText(button, pre.querySelector("code").textContent));
      pre.appendChild(button);
    });
  }

  function swatch(colour) {
    const span = document.createElement("span");
    span.className = "sw";
    span.style.background = colour;
    span.title = colour;
    return span;
  }

  function renderPalettes() {
    const host = document.getElementById("palettes");
    if (!host || !window.PALETTES) return;
    for (const [name, colours] of Object.entries(window.PALETTES)) {
      const card = document.createElement("div");
      const title = document.createElement("b");
      const count = document.createElement("small");
      title.textContent = name;
      count.textContent = colours.length + " colours";
      title.appendChild(count);
      card.appendChild(title);
      colours.forEach((colour) => card.appendChild(swatch(colour)));
      host.appendChild(card);
    }
  }

  setupModeSwitch();
  setupCopyButtons();
  renderPalettes();
})();
