-- The terminal app that runs the Herdr client: which one it is, and bringing it forward, on the
-- exact window and tab where the terminal has a scripting adapter (iTerm2 and Terminal select the
-- tab by its tty), the whole app otherwise.
-- Everything is pure except regularApps, installed, nameOf, show and raise, which need Hammerspoon.

local M = {}

M.ITERM = "com.googlecode.iterm2"
M.TERMINAL = "com.apple.Terminal"

local TTY = "^/dev/ttys%d+$"
local BUNDLE_ID = "^[%w%.%-]+$"
-- errAEEventNotPermitted: the user has not allowed Hammerspoon to control the terminal.
local NOT_PERMITTED = -1743
-- iTerm2 keeps its shells under an iTermServer process, which an iTerm2 restart leaves behind,
-- parented to launchd.
local ITERM_SERVER = "/iTermServer-"
-- Processes between a client and its terminal that hide the terminal: their server runs on its own.
local HIDERS = { tmux = "tmux", screen = "screen", zellij = "zellij", sshd = "ssh", ["mosh-server"] = "mosh" }
local NO_CLIENT = "no Herdr client runs in a terminal"

local function quoted(ttys)
  local list = {}
  for _, tty in ipairs(ttys or {}) do
    if type(tty) == "string" and tty:match(TTY) then
      list[#list + 1] = '"' .. tty .. '"'
    end
  end
  return #list > 0 and table.concat(list, ", ") or nil
end

-- Selecting the session alone switches neither the tab nor the window.
local function itermScript(bundleID, ttys)
  return table.concat({
    'tell application id "' .. bundleID .. '"',
    "  repeat with w in windows",
    "    repeat with t in tabs of w",
    "      repeat with s in sessions of t",
    "        if (tty of s) is in {" .. ttys .. "} then",
    "          select w",
    "          tell t to select",
    "          tell s to select",
    "          activate",
    '          return "raised"',
    "        end if",
    "      end repeat",
    "    end repeat",
    "  end repeat",
    "end tell",
    'return "missing"',
  }, "\n")
end

-- Terminal's tabs carry the tty themselves; a minimized window must come back first.
local function terminalScript(bundleID, ttys)
  return table.concat({
    'tell application id "' .. bundleID .. '"',
    "  repeat with w in windows",
    "    repeat with t in tabs of w",
    "      if (tty of t) is in {" .. ttys .. "} then",
    "        if miniaturized of w then set miniaturized of w to false",
    "        set selected of t to true",
    "        set index of w to 1",
    "        activate",
    '        return "raised"',
    "      end if",
    "    end repeat",
    "  end repeat",
    "end tell",
    'return "missing"',
  }, "\n")
end

local ADAPTERS = {
  [M.ITERM] = { name = "iterm2", script = itermScript },
  [M.TERMINAL] = { name = "terminal", script = terminalScript },
}

-- "iterm2" or "terminal" when the app can select the client's tab, "generic" otherwise.
function M.adapter(bundleID)
  local adapter = ADAPTERS[bundleID]
  return adapter and adapter.name or "generic"
end

-- AppleScript that brings forward the window and tab on one of the ttys and returns "raised", or
-- "missing" when none matches; nil without an adapter or a valid tty. Only strings shaped like
-- /dev/ttysNNN and bundle ids reach the script.
function M.raiseScript(bundleID, ttys)
  local adapter, list = ADAPTERS[bundleID], quoted(ttys)
  if adapter == nil or list == nil or type(bundleID) ~= "string" or not bundleID:match(BUNDLE_ID) then
    return nil
  end
  return adapter.script(bundleID, list)
end

local function basename(command)
  local first = (command or ""):match("^(%S+)") or ""
  return ((first:match("[^/]+$") or first):gsub(":$", ""))
end

-- The app of one client's chain of parents: the nearest regular app, else iTerm2 when an iTerm
-- server is in the chain; nil and a note when neither is.
local function appOf(chain, apps)
  for _, proc in ipairs(chain.ancestors) do
    local app = apps[proc.pid]
    if app then
      return app.bundleID, app.name, "detected"
    end
  end
  for _, proc in ipairs(chain.ancestors) do
    if proc.command:find(ITERM_SERVER, 1, true) then
      return M.ITERM, "iTerm2", "hint"
    end
  end
  for _, proc in ipairs(chain.ancestors) do
    local hider = HIDERS[basename(proc.command)]
    if hider then
      return nil, ("Herdr runs inside %s, so its terminal is unknown"):format(hider)
    end
  end
  return nil, "no app found above the Herdr client on " .. chain.tty
end

-- The terminals running the clients, one per app in the order of their first client, with the
-- ttys of their clients; and notes on the clients whose terminal is unknown.
-- chains = { {tty, ancestors = {proc...}} }, apps = { [pid] = {bundleID, name} } (regular apps).
function M.resolve(chains, apps)
  local targets, byID, notes = {}, {}, {}
  for _, chain in ipairs(chains) do
    local bundleID, name, source = appOf(chain, apps)
    if bundleID == nil then
      notes[#notes + 1] = name
    elseif byID[bundleID] then
      local ttys = byID[bundleID].ttys
      ttys[#ttys + 1] = chain.tty
    else
      byID[bundleID] = { bundleID = bundleID, name = name, ttys = { chain.tty }, source = source }
      targets[#targets + 1] = byID[bundleID]
    end
  end
  return targets, notes
end

-- The terminal to use when no client shows its own: terminalBundleID, the older itermBundleID,
-- iTerm2 when installed, else Terminal. installed(bundleID) tells whether an app is there.
function M.fallback(settings, installed)
  if settings.terminalBundleID then
    return { bundleID = settings.terminalBundleID, source = "setting" }
  end
  if settings.itermBundleID then
    return { bundleID = settings.itermBundleID, source = "setting", legacy = true }
  end
  if installed(M.ITERM) then
    return { bundleID = M.ITERM, source = "default" }
  end
  return { bundleID = M.TERMINAL, source = "default" }
end

-- The first detected terminal, or the fallback (named by the caller) with the reason.
function M.choose(targets, fallback, notes)
  if targets[1] then
    return targets[1]
  end
  return {
    bundleID = fallback.bundleID, name = fallback.name, ttys = {}, source = fallback.source,
    legacy = fallback.legacy, note = notes[1] or NO_CLIENT,
  }
end

-- A message for an hs.osascript error dictionary, and whether it is the Automation permission.
function M.scriptFailure(details)
  if type(details) ~= "table" then
    return "AppleScript failed", false
  end
  local number, message = details.NSAppleScriptErrorNumber, details.NSAppleScriptErrorMessage
  if type(message) ~= "string" or message == "" then
    message = number and ("AppleScript error " .. tostring(number)) or "AppleScript failed"
  end
  return message, number == NOT_PERMITTED
end

-- Nothing once the script raised the tab; otherwise why not, and whether the permission is missing.
function M.scriptOutcome(name, ok, result, details)
  if ok and result == "raised" then
    return
  end
  if ok then
    return ("no %s tab runs the Herdr client"):format(name), false
  end
  local message, blocked = M.scriptFailure(details)
  return "cannot select the Herdr tab: " .. message, blocked
end

-- Why only the app comes forward, for a terminal with no script to run.
function M.unscriptedReason(target)
  if target.note then
    return target.note
  end
  if #target.ttys == 0 then
    return NO_CLIENT
  end
  return ("%s has no tab selection here: the app comes forward"):format(target.name)
end

-- What to show for a raise outcome: an alert only when the user must act (the permission) or the
-- terminal did not come forward at all; the log line otherwise.
function M.report(outcome, name)
  if outcome.level == "exact" then
    return
  end
  if outcome.blocked then
    return ("allow Hammerspoon to control %s in System Settings › Privacy & Security › Automation"):format(name),
      outcome.reason
  end
  if outcome.level == "failed" then
    return outcome.reason, outcome.reason
  end
  return nil, outcome.reason
end

-- What the "back to the terminal" key does: "show" the terminal, "back" to the previous app, or "stay".
function M.toggleAction(frontBundleID, terminalBundleID, hasPrevious)
  if frontBundleID ~= terminalBundleID then
    return "show"
  end
  return hasPrevious and "back" or "stay"
end

-- The regular (Dock) apps by pid: hs.application.applicationForPID logs an error for every pid
-- that is not an app, so a whole chain of shells would flood the console.
function M.regularApps()
  local apps = {}
  for _, app in ipairs(hs.application.runningApplications()) do
    if app:kind() == 1 and app:bundleID() then
      apps[app:pid()] = { bundleID = app:bundleID(), name = app:name() }
    end
  end
  return apps
end

function M.installed(bundleID)
  return hs.application.infoForBundleID(bundleID) ~= nil
end

function M.nameOf(bundleID)
  return hs.application.nameForBundleID(bundleID) or bundleID
end

-- Activates the app; macOS brings its last key window forward and switches Space if needed.
function M.show(bundleID)
  return hs.application.launchOrFocusByBundleID(bundleID)
end

-- Brings the terminal forward: { level = "exact" } on the client's tab, "app" for the whole app,
-- "failed" when not even that worked; with the reason, and blocked when the permission is missing.
-- The script runs only in a running app: AppleScript would launch it and wait for it (an iTerm2
-- that quit and left its server behind), where show() launches it without blocking.
function M.raise(target)
  local script = M.raiseScript(target.bundleID, target.ttys)
  local reason, blocked
  if script and hs.application.get(target.bundleID) == nil then
    script, reason = nil, target.name .. " was not running"
  end
  if script then
    reason, blocked = M.scriptOutcome(target.name, hs.osascript.applescript(script))
    if reason == nil then
      return { level = "exact" }
    end
  else
    reason = reason or M.unscriptedReason(target)
  end
  if not M.show(target.bundleID) then
    return { level = "failed", reason = reason .. "; " .. target.name .. " could not be activated either", blocked = blocked }
  end
  return { level = "app", reason = reason, blocked = blocked }
end

return M
