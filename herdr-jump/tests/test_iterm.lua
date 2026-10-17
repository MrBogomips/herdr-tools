local h = ...
local iterm = h.load("iterm")

local ITERM = "com.googlecode.iterm2"

-- Output of `ps -axo tty=,command=` as macOS prints it.
local PS = table.concat({
  "??       /opt/homebrew/bin/herdr server",
  "ttys035  herdr",
  "ttys012  /opt/homebrew/bin/herdr --session acme",
  "ttys020  herdr session attach globex",
  "ttys021  herdr agent list",
  "ttys022  herdr pane run w1:p1 make",
  "??       /Users/acme/.config/herdr/plugins/github/usagebar-1/bin/usagebar watch",
  "ttys001  -zsh",
  "ttys002  herdrx",
  "ttys035  herdr",
  "",
}, "\n")

return {
  client_ttys_lists_the_terminals_running_a_herdr_client = function()
    h.eq(iterm.clientTtys(PS), { "/dev/ttys035", "/dev/ttys012", "/dev/ttys020" })
  end,

  client_ttys_is_empty_without_a_client = function()
    h.eq(iterm.clientTtys("??  /opt/homebrew/bin/herdr server\n"), {})
    h.eq(iterm.clientTtys(""), {})
    h.eq(iterm.clientTtys(nil), {})
  end,

  raise_script_names_every_client_tty = function()
    local script = iterm.raiseScript({ "/dev/ttys035", "/dev/ttys012" }, ITERM)
    h.eq(script:find('"/dev/ttys035"', 1, true) ~= nil, true)
    h.eq(script:find('"/dev/ttys012"', 1, true) ~= nil, true)
    h.eq(script:find(ITERM, 1, true) ~= nil, true)
  end,

  raise_script_drops_anything_that_is_not_a_tty = function()
    local script = iterm.raiseScript({ '/dev/ttys1" & (do shell script "id") & "', "/dev/ttys007" }, ITERM)
    h.eq(script:find("do shell script", 1, true), nil)
    h.eq(script:find('"/dev/ttys007"', 1, true) ~= nil, true)
  end,

  raise_script_is_nil_without_a_valid_tty = function()
    h.eq(iterm.raiseScript({}, ITERM), nil)
    h.eq(iterm.raiseScript({ "ttys035" }, ITERM), nil)
  end,

  toggle_from_another_app_shows_iterm = function()
    h.eq(iterm.toggleAction("com.microsoft.edgemac", ITERM, true), "show-iterm")
    h.eq(iterm.toggleAction(nil, ITERM, false), "show-iterm")
  end,

  toggle_from_iterm_goes_back_to_the_previous_app = function()
    h.eq(iterm.toggleAction(ITERM, ITERM, true), "back")
  end,

  toggle_from_iterm_without_a_previous_app_stays = function()
    h.eq(iterm.toggleAction(ITERM, ITERM, false), "stay")
  end,
}
