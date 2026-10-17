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

-- Brings forward the iTerm session that runs the Herdr client; falls back to the whole app.
-- Returns nil on success, or a short reason the exact session could not be selected, plus true
-- when the AppleScript itself failed (usually the Automation permission) and the user must act.
function M.raiseHerdr(bundleID)
  local ps = hs.execute("/bin/ps -axo tty=,command=")
  local script = M.raiseScript(M.clientTtys(ps), bundleID)
  if not script then
    M.show(bundleID)
    return "no Herdr client found", false
  end
  local ok, result, details = hs.osascript.applescript(script)
  if ok and result == "raised" then
    return nil, false
  end
  M.show(bundleID)
  if not ok then
    return "AppleScript failed: " .. hs.inspect(details), true
  end
  return "no iTerm session runs the Herdr client", false
end

return M
