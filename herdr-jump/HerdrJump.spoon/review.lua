-- The agents the user marked "to review": seen, maybe left, but not reviewed yet.
-- Pure Lua: no hs.* calls, so it runs under plain Lua in the tests.
--
-- A record maps a pane_id to { at = epoch seconds of the marking, completion = the agent's
-- completion_seq then (0 when it had none), color = 1 to COLORS }. Any agent can be marked; each
-- toggle moves the mark to the next color, and past the last one clears it. A mark stays while the
-- agent works; it goes when the user clears it, when the pane is gone, or when Herdr restarted (its
-- counters start over and pane ids are reused).

local M = {}

-- How many mark colors the toggle cycles through.
M.COLORS = 3

local function copy(record)
  local out = {}
  for k, v in pairs(record) do
    out[k] = v
  end
  return out
end

-- New marks and seen records after the user toggles an agent whose status is `status`: an
-- unmarked agent is marked now in the first color, and a done one counts as seen too; a marked one
-- moves to the next color, keeping its time, or is unmarked after the last color.
function M.toggle(marks, seen, agent, status, now)
  local pane = agent.pane_id
  local newMarks, newSeen = copy(marks), copy(seen)
  local mark = marks[pane]
  local color = mark and mark.color
  if mark == nil then
    newMarks[pane] = { at = now, completion = agent.completion_seq or 0, color = 1 }
    if status == "done" and agent.completion_seq ~= nil then
      newSeen[pane] = agent.completion_seq
    end
  elseif color < M.COLORS then
    newMarks[pane] = { at = mark.at, completion = mark.completion, color = color + 1 }
  else
    newMarks[pane] = nil
  end
  return newMarks, newSeen
end

-- The marks of the listed agents whose completion counter did not go backwards (no counter reads 0).
-- A kept mark takes the counter as it grows: one set before the agent ever completed (0) would
-- otherwise never see a restart.
function M.prune(marks, agents)
  local out = {}
  for _, agent in ipairs(agents) do
    local mark = marks[agent.pane_id]
    local seq = agent.completion_seq or 0
    if mark and seq >= mark.completion then
      out[agent.pane_id] = { at = mark.at, completion = seq, color = mark.color }
    end
  end
  return out
end

local function validColor(color)
  return color == nil or (type(color) == "number" and color % 1 == 0 and color >= 1 and color <= M.COLORS)
end

-- A mark stored before colors existed has none: it reads as the first.
local function wellFormed(mark)
  return type(mark) == "table" and type(mark.at) == "number" and type(mark.completion) == "number"
    and validColor(mark.color)
end

-- A record from stored settings, and whether something malformed was dropped.
function M.valid(stored)
  if stored == nil then
    return {}, false
  end
  if type(stored) ~= "table" then
    return {}, true
  end
  local out, malformed = {}, false
  for pane, mark in pairs(stored) do
    if type(pane) == "string" and wellFormed(mark) then
      out[pane] = { at = mark.at, completion = mark.completion, color = mark.color or 1 }
    else
      malformed = true
    end
  end
  return out, malformed
end

function M.same(a, b)
  for pane, mark in pairs(a) do
    local other = b[pane]
    if other == nil or other.at ~= mark.at or other.completion ~= mark.completion or other.color ~= mark.color then
      return false
    end
  end
  for pane in pairs(b) do
    if a[pane] == nil then
      return false
    end
  end
  return true
end

-- What the rows need of each mark: when it was set, that time as clock(at, now) says it, its color.
function M.describe(marks, now, clock)
  local out = {}
  for pane, mark in pairs(marks) do
    out[pane] = { at = mark.at, clock = clock(mark.at, now), color = mark.color }
  end
  return out
end

return M
