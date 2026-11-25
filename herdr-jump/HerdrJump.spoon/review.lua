-- The agents the user marked "to review": seen, maybe left, but not reviewed yet.
-- Pure Lua: no hs.* calls, so it runs under plain Lua in the tests.
--
-- A record maps a pane_id to { at = epoch seconds of the marking, completion = the agent's
-- completion_seq then }. A mark stays while the agent works again; it goes when the user toggles it,
-- when the pane is gone, or when Herdr restarted (its counters start over and pane ids are reused).

local M = {}

local MARKABLE = { done = true, idle = true }

-- Whether an agent with this status (attention.status: a done already seen reads idle) can be
-- marked: it has delivered.
function M.markable(status)
  return MARKABLE[status] == true
end

local function copy(record)
  local out = {}
  for k, v in pairs(record) do
    out[k] = v
  end
  return out
end

-- New marks and seen records after the user toggles an agent whose status is `status`: a marked
-- agent is unmarked; a markable one is marked now, and a done one counts as seen too. Anything
-- else leaves both as they were.
function M.toggle(marks, seen, agent, status, now)
  local pane = agent.pane_id
  local newMarks, newSeen = copy(marks), copy(seen)
  if marks[pane] ~= nil then
    newMarks[pane] = nil
  elseif M.markable(status) and agent.completion_seq ~= nil then
    newMarks[pane] = { at = now, completion = agent.completion_seq }
    if status == "done" then
      newSeen[pane] = agent.completion_seq
    end
  end
  return newMarks, newSeen
end

-- The marks of the listed agents whose completion counter did not go backwards.
function M.prune(marks, agents)
  local out = {}
  for _, agent in ipairs(agents) do
    local mark = marks[agent.pane_id]
    if mark and agent.completion_seq ~= nil and agent.completion_seq >= mark.completion then
      out[agent.pane_id] = mark
    end
  end
  return out
end

local function wellFormed(mark)
  return type(mark) == "table" and type(mark.at) == "number" and type(mark.completion) == "number"
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
      out[pane] = { at = mark.at, completion = mark.completion }
    else
      malformed = true
    end
  end
  return out, malformed
end

function M.same(a, b)
  for pane, mark in pairs(a) do
    local other = b[pane]
    if other == nil or other.at ~= mark.at or other.completion ~= mark.completion then
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

-- What the rows need of each mark: when it was set, and that time as clock(at, now) says it.
function M.describe(marks, now, clock)
  local out = {}
  for pane, mark in pairs(marks) do
    out[pane] = { at = mark.at, clock = clock(mark.at, now) }
  end
  return out
end

return M
