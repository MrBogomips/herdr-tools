-- When each agent's current state began, and how to say it. Herdr reports counters, not times,
-- so HerdrJump stamps a state with the time of the poll that first sees it.
-- Pure Lua: no hs.* calls, so it runs under plain Lua in the tests.
--
-- A record maps a pane_id to { seq = state_change_seq, at = epoch seconds, approx = boolean }.
-- approx marks a state first seen after a gap (start, Herdr not answering): it began before `at`.

local M = {}

local MINUTE, HOUR, DAY = 60, 3600, 86400
local WEEK_DAYS = 6 -- further back, the weekday alone would be ambiguous

-- A new record for the listed agents. A pane keeps its stamp while its state change counter stays;
-- a new pane or a changed counter (gone backwards too: Herdr restarted) is stamped now. Panes that
-- are gone or have no counter are dropped. exact is false on the first poll after a gap.
function M.update(record, agents, now, exact)
  local updated = {}
  for _, agent in ipairs(agents) do
    local pane, seq = agent.pane_id, agent.state_change_seq
    if pane ~= nil and type(seq) == "number" then
      local stamp = record[pane]
      if stamp == nil or stamp.seq ~= seq then
        stamp = { seq = seq, at = now, approx = not exact }
      end
      updated[pane] = stamp
    end
  end
  return updated
end

local function sameStamp(a, b)
  return b ~= nil and a.seq == b.seq and a.at == b.at and a.approx == b.approx
end

function M.same(a, b)
  for pane, stamp in pairs(a) do
    if not sameStamp(stamp, b[pane]) then
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

-- A record from stored settings, without malformed entries.
function M.valid(stored)
  local record = {}
  if type(stored) ~= "table" then
    return record
  end
  for pane, stamp in pairs(stored) do
    if type(pane) == "string" and type(stamp) == "table"
      and type(stamp.seq) == "number" and type(stamp.at) == "number" then
      record[pane] = { seq = stamp.seq, at = stamp.at, approx = stamp.approx == true }
    end
  end
  return record
end

local function units(big, bigUnit, small, smallUnit)
  if small > 0 then
    return ("%d%s %d%s"):format(big, bigUnit, small, smallUnit)
  end
  return ("%d%s"):format(big, bigUnit)
end

-- A duration in two units at most, rounded down: "<1m", "12m", "1h 5m", "2d 3h".
-- approx says "at least": "≥12m".
function M.ago(seconds, approx)
  local s = math.max(0, math.floor(seconds))
  local text
  if s < MINUTE then
    text = approx and "0m" or "<1m"
  elseif s < HOUR then
    text = ("%dm"):format(s // MINUTE)
  elseif s < DAY then
    text = units(s // HOUR, "h", s % HOUR // MINUTE, "m")
  else
    text = units(s // DAY, "d", s % DAY // HOUR, "h")
  end
  return approx and ("≥" .. text) or text
end

-- The local time a state began: "09:41" today, "Tue 23:05" within the week, "Oct 03" before.
function M.clock(at, now)
  if os.date("%Y-%m-%d", at) == os.date("%Y-%m-%d", now) then
    return os.date("%H:%M", at)
  end
  if now - at < WEEK_DAYS * DAY then
    return os.date("%a %H:%M", at)
  end
  return os.date("%b %d", at)
end

-- What the rows show for each pane: { age = "12m", clock = "09:41" }; an approximate start reads
-- "at least" and "at or before": { age = "≥12m", clock = "≤09:41" }.
function M.describe(record, now)
  local times = {}
  for pane, stamp in pairs(record) do
    local clock = M.clock(stamp.at, now)
    times[pane] = { age = M.ago(now - stamp.at, stamp.approx), clock = stamp.approx and ("≤" .. clock) or clock }
  end
  return times
end

return M
