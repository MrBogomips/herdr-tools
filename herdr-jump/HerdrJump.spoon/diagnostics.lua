-- What HerdrJump found and uses, as text lines for the menu's Diagnostics submenu, the clipboard and
-- `install.sh --check`. Pure: init.lua gathers the state.
--
-- state = { version, minHerdr, hammerspoon,
--   herdr = { path, source = "setting"|"found", missing = {paths}, version },
--   socket = { path, exists }, terminal = { name, source, legacy, note, selects }, clients,
--   agentsError, lastRaise = { reason }, automation = name of a terminal Hammerspoon may not control }

local M = {}

local SOURCE = {
  detected = "detected",
  hint = "detected through its iTerm2 server",
  default = "default",
}

local function herdrLine(herdr, minimum)
  if herdr.path == nil then
    return ("herdr: not found in %s: set spoon.HerdrJump.herdrBin"):format(table.concat(herdr.missing or {}, ", "))
  end
  local line = ("herdr: %s (%s)"):format(herdr.path, herdr.source == "setting" and "herdrBin" or "found")
  if herdr.version then
    line = line .. " · " .. herdr.version
    if herdr.older then
      line = line .. ", older than " .. minimum
    end
  end
  return line
end

local function terminalLine(terminal)
  local source = SOURCE[terminal.source]
  if terminal.source == "setting" then
    source = terminal.legacy and "itermBundleID (renamed terminalBundleID)" or "terminalBundleID"
  end
  local line = ("terminal: %s · %s · %s"):format(terminal.name, source or tostring(terminal.source),
    terminal.selects and "selects the Herdr tab" or "brings the app forward")
  if terminal.note then
    line = line .. " (" .. terminal.note .. ")"
  end
  return line
end

function M.lines(state)
  local lines = {
    ("HerdrJump %s · Hammerspoon %s"):format(state.version, state.hammerspoon),
    herdrLine(state.herdr, state.minHerdr),
  }
  if state.herdr.path and #(state.herdr.missing or {}) > 0 then
    lines[#lines + 1] = ("herdrBin %s is missing: using %s"):format(state.herdr.missing[1], state.herdr.path)
  end
  lines[#lines + 1] = "socket: " .. state.socket.path .. (state.socket.exists and "" or " · missing: is Herdr running?")
  lines[#lines + 1] = terminalLine(state.terminal)
  lines[#lines + 1] = ("Herdr clients: %d"):format(state.clients or 0)
  if state.agentsError then
    lines[#lines + 1] = "agents: " .. state.agentsError
  end
  if state.lastRaise and state.lastRaise.reason then
    lines[#lines + 1] = "last jump: " .. state.lastRaise.reason
  end
  if state.automation then
    lines[#lines + 1] = ("Automation: allow Hammerspoon to control %s"):format(state.automation)
  end
  return lines
end

function M.text(state)
  return table.concat(M.lines(state), "\n")
end

-- hs.menubar items: the lines, disabled, then the actions; init.lua runs an item's `action`.
function M.menu(state)
  local items = {}
  for i, line in ipairs(M.lines(state)) do
    items[i] = { title = line, disabled = true }
  end
  items[#items + 1] = { title = "-" }
  items[#items + 1] = { title = "Copy diagnostics", action = "copy" }
  items[#items + 1] = { title = "Open the Hammerspoon console", action = "console" }
  if state.automation then
    items[#items + 1] = { title = "Open the Automation settings", action = "automation" }
  end
  return items
end

return M
