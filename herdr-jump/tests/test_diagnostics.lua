local h = ...
local diagnostics = h.load("diagnostics")

local ITERM, CODE = "com.googlecode.iterm2", "com.microsoft.VSCode"

-- A healthy setup, changed per test.
local function state(changes)
  local base = {
    version = "0.4.0",
    minHerdr = "0.9.5",
    hammerspoon = "1.1.1",
    herdr = { path = "/opt/homebrew/bin/herdr", source = "found", missing = {}, version = "0.9.5" },
    socket = { path = "/Users/acme/.config/herdr/herdr.sock", exists = true },
    terminal = { bundleID = ITERM, name = "iTerm2", ttys = { "/dev/ttys005" }, source = "detected", selects = true },
    clients = 1,
  }
  for key, value in pairs(changes or {}) do
    base[key] = value
  end
  return base
end

local function has(lines, text)
  for _, line in ipairs(lines) do
    if line:find(text, 1, true) then
      return true
    end
  end
  return false
end

return {
  a_healthy_setup = function()
    h.eq(diagnostics.lines(state()), {
      "HerdrJump 0.4.0 · Hammerspoon 1.1.1",
      "herdr: /opt/homebrew/bin/herdr (found) · 0.9.5",
      "socket: /Users/acme/.config/herdr/herdr.sock",
      "terminal: iTerm2 · detected · selects the Herdr tab",
      "Herdr clients: 1",
    })
  end,

  herdr_not_found_lists_where_it_looked = function()
    local lines = diagnostics.lines(state({ herdr = { missing = { "/a/herdr", "/b/herdr" } } }))
    h.eq(lines[2], "herdr: not found in /a/herdr, /b/herdr: set spoon.HerdrJump.herdrBin")
  end,

  a_missing_setting_and_an_old_herdr_are_said = function()
    local lines = diagnostics.lines(state({
      herdr = { path = "/usr/local/bin/herdr", source = "found", missing = { "/old/herdr" }, version = "0.9.3", older = true },
    }))
    h.eq(lines[2], "herdr: /usr/local/bin/herdr (found) · 0.9.3, older than 0.9.5")
    h.eq(has(lines, "herdrBin /old/herdr is missing"), true)
  end,

  a_missing_socket_asks_whether_herdr_runs = function()
    local lines = diagnostics.lines(state({ socket = { path = "/x/herdr.sock", exists = false } }))
    h.eq(lines[3], "socket: /x/herdr.sock · missing: is Herdr running?")
  end,

  a_terminal_without_an_adapter_brings_the_app_forward = function()
    local lines = diagnostics.lines(state({ terminal = { bundleID = CODE, name = "Code", ttys = { "/dev/ttys010" }, source = "detected" } }))
    h.eq(lines[4], "terminal: Code · detected · brings the app forward")
  end,

  a_fallback_terminal_says_why = function()
    local lines = diagnostics.lines(state({
      terminal = { bundleID = ITERM, name = "iTerm2", ttys = {}, source = "default", note = "Herdr runs inside tmux, so its terminal is unknown" },
      clients = 0,
    }))
    h.eq(lines[4], "terminal: iTerm2 · default · brings the app forward (Herdr runs inside tmux, so its terminal is unknown)")
  end,

  settings_are_named = function()
    local lines = diagnostics.lines(state({ terminal = { bundleID = CODE, name = "Code", ttys = {}, source = "setting", legacy = true, note = "x" } }))
    h.eq(lines[4], "terminal: Code · itermBundleID (renamed terminalBundleID) · brings the app forward (x)")
  end,

  errors_the_last_jump_and_the_permission_are_listed = function()
    local lines = diagnostics.lines(state({
      agentsError = "Herdr is not running",
      lastRaise = { level = "app", reason = "no iTerm2 tab runs the Herdr client" },
      automation = "iTerm2",
    }))
    h.eq(has(lines, "agents: Herdr is not running"), true)
    h.eq(has(lines, "last jump: no iTerm2 tab runs the Herdr client"), true)
    h.eq(has(lines, "Automation: allow Hammerspoon to control iTerm2"), true)
  end,

  text_joins_the_lines = function()
    h.eq(diagnostics.text(state()):match("^[^\n]+"), "HerdrJump 0.4.0 · Hammerspoon 1.1.1")
  end,

  menu_shows_the_lines_then_the_actions = function()
    local menu = diagnostics.menu(state())
    h.eq(menu[1], { title = "HerdrJump 0.4.0 · Hammerspoon 1.1.1", disabled = true })
    h.eq(menu[6], { title = "-" })
    h.eq(menu[7], { title = "Copy diagnostics", action = "copy" })
    h.eq(menu[8], { title = "Open the Hammerspoon console", action = "console" })
    h.eq(menu[9], nil)
  end,

  menu_offers_the_automation_settings_when_blocked = function()
    local menu = diagnostics.menu(state({ automation = "Terminal" }))
    h.eq(menu[#menu], { title = "Open the Automation settings", action = "automation" })
  end,
}
