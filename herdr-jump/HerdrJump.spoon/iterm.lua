-- Bringing iTerm forward: the whole app for the "back to iTerm" key, or the exact window, tab and
-- session that runs the Herdr client after a jump to an agent.
-- clientTtys, raiseScript and toggleAction are pure; show and raiseHerdr need Hammerspoon.

local M = {}

local TTY = "^/dev/ttys%d+$"
local BUNDLE_ID = "^[%w%.%-]+$"

-- A Herdr client is `herdr` alone, with options only, or `herdr session attach <name>`;
-- `herdr server` and the one-shot subcommands (agent, pane, ...) are not.
local function isClient(command)
  local words = {}
  for word in command:gmatch("%S+") do
    words[#words + 1] = word
  end
  if words[1] == nil or words[1]:match("[^/]+$") ~= "herdr" then
    return false
  end
  local first = words[2]
  return first == nil or first:sub(1, 1) == "-" or (first == "session" and words[3] == "attach")
end

-- The /dev/ttysNNN of every Herdr client in `ps -axo tty=,command=` output, first seen first.
function M.clientTtys(ps)
  local ttys, listed = {}, {}
  for line in (ps or ""):gmatch("[^\n]+") do
    local tty, command = line:match("^%s*(%S+)%s+(.-)%s*$")
    if tty and tty:match("^ttys%d+$") and isClient(command) then
      local device = "/dev/" .. tty
      if not listed[device] then
        listed[device] = true
        ttys[#ttys + 1] = device
      end
    end
  end
  return ttys
end

-- AppleScript that selects the frontmost iTerm session on one of the ttys, with its tab and window,
-- and returns "raised"; "missing" when no session matches. Nil when nothing valid is left to match.
-- Only strings shaped like /dev/ttysNNN reach the script.
function M.raiseScript(ttys, bundleID)
  local quoted = {}
  for _, tty in ipairs(ttys) do
    if type(tty) == "string" and tty:match(TTY) then
      quoted[#quoted + 1] = '"' .. tty .. '"'
    end
  end
  if #quoted == 0 or type(bundleID) ~= "string" or not bundleID:match(BUNDLE_ID) then
    return nil
  end
  return table.concat({
    'tell application id "' .. bundleID .. '"',
    "  repeat with w in windows",
    "    repeat with t in tabs of w",
    "      repeat with s in sessions of t",
    "        if (tty of s) is in {" .. table.concat(quoted, ", ") .. "} then",
    -- Selecting the session alone switches neither the tab nor the window.
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

-- errAEEventNotPermitted: the user has not allowed Hammerspoon to control iTerm2.
local NOT_PERMITTED = -1743

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

-- What the "back to iTerm" key does: "show-iterm", "back" to the previous app, or "stay".
function M.toggleAction(frontBundleID, itermBundleID, hasPrevious)
  if frontBundleID ~= itermBundleID then
    return "show-iterm"
  end
  return hasPrevious and "back" or "stay"
end

-- Activates iTerm; macOS brings its last key window forward and switches Space if needed.
function M.show(bundleID)
  return hs.application.launchOrFocusByBundleID(bundleID)
end

-- Falls back to activating the whole app, and says so when even that fails.
local function fallBack(bundleID, reason, blocked)
  if not M.show(bundleID) then
    reason = reason .. "; iTerm could not be activated either"
  end
  return reason, blocked
end

-- Brings forward the iTerm session that runs the Herdr client; falls back to the whole app.
-- Returns nil on success, or a short reason the exact session could not be selected, plus true
-- when macOS refused the Automation permission and the user must allow it.
function M.raiseHerdr(bundleID)
  local ps, listed = hs.execute("/bin/ps -axo tty=,command=")
  if not listed then
    return fallBack(bundleID, "cannot list processes with ps", false)
  end
  local script = M.raiseScript(M.clientTtys(ps), bundleID)
  if not script then
    return fallBack(bundleID, "no Herdr client is running in a terminal", false)
  end
  local ok, result, details = hs.osascript.applescript(script)
  if ok and result == "raised" then
    return nil, false
  end
  if not ok then
    local message, blocked = M.scriptFailure(details)
    return fallBack(bundleID, "cannot select the Herdr tab: " .. message, blocked)
  end
  return fallBack(bundleID, "no iTerm session runs the Herdr client", false)
end

return M
