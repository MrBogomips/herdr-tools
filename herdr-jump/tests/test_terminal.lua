local h = ...
local terminal = h.load("terminal")
local procs = h.load("procs")

local ITERM, TERMINAL = terminal.ITERM, terminal.TERMINAL
local CODE = "com.microsoft.VSCode"

-- Herdr clients in iTerm2, in Terminal, in VS Code's integrated terminal, under an iTerm2 server
-- left behind by a restart, and in tmux.
local PS = table.concat({
  "  500     1 ??       /Applications/iTerm.app/Contents/MacOS/iTerm2",
  "  510   500 ??       /Users/acme/Library/Application Support/iTerm2/iTermServer-3.7.6 /Users/acme/x.socket",
  "  520   510 ttys005  /usr/bin/login -fpl acme /Applications/iTerm.app/Contents/MacOS/ShellLauncher",
  "  530   520 ttys005  -zsh",
  "  540   530 ttys005  herdr",
  "  600     1 ??       /System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal",
  "  610   600 ttys007  login -pf acme",
  "  620   610 ttys007  -zsh",
  "  630   620 ttys007  herdr",
  "  650   620 ttys008  herdr",
  "  651   600 ttys008  -zsh",
  "  700     1 ??       /Applications/Visual Studio Code.app/Contents/MacOS/Electron",
  "  701   700 ??       /Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper.app/Contents/MacOS/Code Helper",
  "  702   701 ttys010  /bin/zsh -il",
  "  703   702 ttys010  herdr",
  "  800     1 ??       /Users/acme/Library/Application Support/iTerm2/iTermServer-3.7.6 /Users/acme/y.socket",
  "  810   800 ttys012  -zsh",
  "  820   810 ttys012  herdr",
  "  900     1 ??       tmux new -s acme",
  "  910   900 ttys014  -zsh",
  "  920   910 ttys014  herdr",
  "",
}, "\n")

local APPS = {
  [500] = { bundleID = ITERM, name = "iTerm2" },
  [600] = { bundleID = TERMINAL, name = "Terminal" },
  [700] = { bundleID = CODE, name = "Code" },
}

-- The chains of the clients on the given ttys, as init.lua builds them.
local function chains(ttys)
  local parsed, wanted, out = procs.parse(PS), {}, {}
  for _, tty in ipairs(ttys) do
    wanted["/dev/" .. tty] = true
  end
  for _, client in ipairs(procs.clients(parsed, nil)) do
    if wanted[client.tty] then
      out[#out + 1] = { tty = client.tty, ancestors = procs.ancestry(parsed, client.pid) }
    end
  end
  return out
end

local function installed(list)
  local set = {}
  for _, id in ipairs(list) do
    set[id] = true
  end
  return function(id) return set[id] == true end
end

return {
  adapters_exist_for_iterm_and_terminal_only = function()
    h.eq(terminal.adapter(ITERM), "iterm2")
    h.eq(terminal.adapter(TERMINAL), "terminal")
    h.eq(terminal.adapter(CODE), "generic")
    h.eq(terminal.adapter(nil), "generic")
  end,

  iterm_script_selects_the_window_tab_and_session_of_every_client_tty = function()
    local script = terminal.raiseScript(ITERM, { "/dev/ttys035", "/dev/ttys012" })
    h.eq(script:find('tell application id "com.googlecode.iterm2"', 1, true) ~= nil, true)
    h.eq(script:find('"/dev/ttys035", "/dev/ttys012"', 1, true) ~= nil, true)
    h.eq(script:find("tell s to select", 1, true) ~= nil, true)
  end,

  terminal_script_selects_the_tab_and_brings_its_window_forward = function()
    local script = terminal.raiseScript(TERMINAL, { "/dev/ttys007" })
    h.eq(script:find('tell application id "com.apple.Terminal"', 1, true) ~= nil, true)
    h.eq(script:find('if (tty of t) is in {"/dev/ttys007"} then', 1, true) ~= nil, true)
    h.eq(script:find("set selected of t to true", 1, true) ~= nil, true)
    h.eq(script:find("set index of w to 1", 1, true) ~= nil, true)
    h.eq(script:find("set miniaturized of w to false", 1, true) ~= nil, true)
  end,

  scripts_drop_anything_that_is_not_a_tty = function()
    for _, id in ipairs({ ITERM, TERMINAL }) do
      local script = terminal.raiseScript(id, { '/dev/ttys1" & (do shell script "id") & "', "/dev/ttys007" })
      h.eq(script:find("do shell script", 1, true), nil, id)
      h.eq(script:find('"/dev/ttys007"', 1, true) ~= nil, true, id)
    end
  end,

  no_script_without_an_adapter_or_a_valid_tty = function()
    h.eq(terminal.raiseScript(CODE, { "/dev/ttys010" }), nil)
    h.eq(terminal.raiseScript(ITERM, {}), nil)
    h.eq(terminal.raiseScript(ITERM, { "ttys035" }), nil)
    h.eq(terminal.raiseScript('x" & "y', { "/dev/ttys035" }), nil)
  end,

  resolve_finds_the_app_that_started_each_client = function()
    local targets, notes = terminal.resolve(chains({ "ttys005", "ttys007", "ttys010" }), APPS)
    h.eq(targets, {
      { bundleID = ITERM, name = "iTerm2", ttys = { "/dev/ttys005" }, source = "detected" },
      { bundleID = TERMINAL, name = "Terminal", ttys = { "/dev/ttys007" }, source = "detected" },
      { bundleID = CODE, name = "Code", ttys = { "/dev/ttys010" }, source = "detected" },
    })
    h.eq(notes, {})
  end,

  resolve_gathers_the_ttys_of_one_app = function()
    local targets = terminal.resolve(chains({ "ttys007", "ttys008" }), APPS)
    h.eq(targets, { { bundleID = TERMINAL, name = "Terminal", ttys = { "/dev/ttys007", "/dev/ttys008" }, source = "detected" } })
  end,

  resolve_takes_an_orphaned_iterm_server_for_iterm = function()
    local targets = terminal.resolve(chains({ "ttys012" }), APPS)
    h.eq(targets, { { bundleID = ITERM, name = "iTerm2", ttys = { "/dev/ttys012" }, source = "hint" } })
  end,

  resolve_notes_a_client_inside_tmux = function()
    local targets, notes = terminal.resolve(chains({ "ttys014" }), APPS)
    h.eq(targets, {})
    h.eq(notes, { "Herdr runs inside tmux, so its terminal is unknown" })
  end,

  fallback_is_the_setting_then_the_old_setting_then_an_installed_terminal = function()
    local both = installed({ ITERM, TERMINAL })
    h.eq(terminal.fallback({ terminalBundleID = CODE, itermBundleID = ITERM }, both), { bundleID = CODE, source = "setting" })
    h.eq(terminal.fallback({ itermBundleID = "com.example.term" }, both),
      { bundleID = "com.example.term", source = "setting", legacy = true })
    h.eq(terminal.fallback({}, both), { bundleID = ITERM, source = "default" })
    h.eq(terminal.fallback({}, installed({ TERMINAL })), { bundleID = TERMINAL, source = "default" })
  end,

  choose_takes_the_first_detected_terminal = function()
    local targets = terminal.resolve(chains({ "ttys005", "ttys007" }), APPS)
    h.eq(terminal.choose(targets, { bundleID = TERMINAL, name = "Terminal", source = "default" }, {}).bundleID, ITERM)
  end,

  choose_falls_back_with_the_reason = function()
    local fallback = { bundleID = TERMINAL, name = "Terminal", source = "default" }
    h.eq(terminal.choose({}, fallback, { "Herdr runs inside tmux, so its terminal is unknown" }), {
      bundleID = TERMINAL, name = "Terminal", ttys = {}, source = "default",
      note = "Herdr runs inside tmux, so its terminal is unknown",
    })
    h.eq(terminal.choose({}, fallback, {}).note, "no Herdr client runs in a terminal")
  end,

  script_outcome_is_nil_once_the_tab_is_raised = function()
    h.eq({ terminal.scriptOutcome("Terminal", true, "raised", nil) }, {})
  end,

  script_outcome_says_when_no_tab_runs_herdr = function()
    h.eq({ terminal.scriptOutcome("Terminal", true, "missing", nil) }, { "no Terminal tab runs the Herdr client", false })
  end,

  script_outcome_flags_a_refused_automation_permission = function()
    local details = { NSAppleScriptErrorNumber = -1743, NSAppleScriptErrorMessage = "Not authorized to send Apple events to iTerm2." }
    h.eq({ terminal.scriptOutcome("iTerm2", false, nil, details) },
      { "cannot select the Herdr tab: Not authorized to send Apple events to iTerm2.", true })
  end,

  script_failure_reports_other_errors_without_the_permission_hint = function()
    local details = { NSAppleScriptErrorNumber = -1728, NSAppleScriptErrorMessage = "Can't get session 2." }
    h.eq({ terminal.scriptFailure(details) }, { "Can't get session 2.", false })
    h.eq({ terminal.scriptFailure(nil) }, { "AppleScript failed", false })
    h.eq({ terminal.scriptFailure({ NSAppleScriptErrorNumber = -2700 }) }, { "AppleScript error -2700", false })
  end,

  without_a_script_the_reason_says_why = function()
    h.eq(terminal.unscriptedReason({ bundleID = CODE, name = "Code", ttys = { "/dev/ttys010" } }),
      "Code has no tab selection here: the app comes forward")
    h.eq(terminal.unscriptedReason({ bundleID = ITERM, name = "iTerm2", ttys = {}, note = "no Herdr client runs in a terminal" }),
      "no Herdr client runs in a terminal")
  end,

  report_alerts_only_for_the_permission_or_a_terminal_that_cannot_come_forward = function()
    h.eq({ terminal.report({ level = "exact" }, "iTerm2") }, {})
    h.eq({ terminal.report({ level = "app", reason = "Code has no tab selection here: the app comes forward" }, "Code") },
      { nil, "Code has no tab selection here: the app comes forward" })
    h.eq({ terminal.report({ level = "app", reason = "x", blocked = true }, "Terminal") },
      { "allow Hammerspoon to control Terminal in System Settings › Privacy & Security › Automation", "x" })
    h.eq({ terminal.report({ level = "failed", reason = "y" }, "Ghostty") }, { "y", "y" })
  end,

  toggle_from_another_app_shows_the_terminal = function()
    h.eq(terminal.toggleAction("com.microsoft.edgemac", ITERM, true), "show")
    h.eq(terminal.toggleAction(nil, TERMINAL, false), "show")
  end,

  toggle_from_the_terminal_goes_back_to_the_previous_app = function()
    h.eq(terminal.toggleAction(TERMINAL, TERMINAL, true), "back")
  end,

  toggle_from_the_terminal_without_a_previous_app_stays = function()
    h.eq(terminal.toggleAction(ITERM, ITERM, false), "stay")
  end,
}
