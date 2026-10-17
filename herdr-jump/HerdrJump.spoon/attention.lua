-- Which Herdr agents need the user, in what order, and what the menu bar says about them.
-- Pure Lua: no hs.* calls, so it runs under plain Lua in the tests.
--
-- An agent is one entry of `herdr agent list`; the fields read here are pane_id, agent_status,
-- focused, completion_seq, state_change_seq, terminal_title_stripped, terminal_title and cwd.
-- "seen" maps a pane_id to the completion_seq the user has already looked at.

local M = {}

-- Lower comes first. Statuses Herdr may add later rank with "unknown".
local PRIORITY = { blocked = 1, done = 2, unknown = 3, idle = 4, working = 5 }
local GLYPH = { blocked = "⏸", done = "✓", unknown = "?", idle = "·", working = "◐" }

-- The status the user should see: a done agent already viewed counts as idle.
function M.status(agent, seen)
  local status = agent.agent_status
  if PRIORITY[status] == nil then
    return "unknown"
  end
  local viewed = seen[agent.pane_id]
  if status == "done" and viewed and agent.completion_seq and agent.completion_seq <= viewed then
    return "idle"
  end
  return status
end

-- A new list, most urgent first; within a status, the latest state change first.
function M.rank(agents, seen)
  local ranked = {}
  for i, agent in ipairs(agents) do
    ranked[i] = agent
  end
  table.sort(ranked, function(a, b)
    local pa, pb = PRIORITY[M.status(a, seen)], PRIORITY[M.status(b, seen)]
    if pa ~= pb then
      return pa < pb
    end
    local sa, sb = a.state_change_seq or 0, b.state_change_seq or 0
    if sa ~= sb then
      return sa > sb
    end
    return tostring(a.pane_id) < tostring(b.pane_id)
  end)
  return ranked
end

-- How many agents wait for the user: blocked on a question, or done and not yet seen.
function M.count(agents, seen)
  local n = 0
  for _, agent in ipairs(agents) do
    local status = M.status(agent, seen)
    if status == "blocked" or status == "done" then
      n = n + 1
    end
  end
  return n
end

-- A new seen record: the focused done agent is seen when iTerm is in front. Panes that are gone are
-- dropped, and so are panes whose completion counter is missing or went backwards: Herdr restarted,
-- its sequence numbers start over and pane ids are reused.
function M.updateSeen(seen, agents, itermFrontmost)
  local updated = {}
  for _, agent in ipairs(agents) do
    local pane, completion = agent.pane_id, agent.completion_seq
    if pane ~= nil and completion ~= nil then
      local viewed = seen[pane]
      if viewed ~= nil and completion < viewed then
        viewed = nil
      end
      if itermFrontmost and agent.focused and agent.agent_status == "done" then
        viewed = math.max(viewed or completion, completion)
      end
      updated[pane] = viewed
    end
  end
  return updated
end

function M.sameSeen(a, b)
  for k, v in pairs(a) do
    if b[k] ~= v then
      return false
    end
  end
  for k in pairs(b) do
    if a[k] == nil then
      return false
    end
  end
  return true
end

local function folder(path)
  if type(path) ~= "string" then
    return nil
  end
  return (path:gsub("/+$", "")):match("([^/]+)$")
end

local function label(agent)
  -- A numeric loop: any of the candidates can be nil, which would stop ipairs early.
  local candidates = { agent.terminal_title_stripped, agent.terminal_title, folder(agent.cwd) }
  for i = 1, 3 do
    local candidate = candidates[i]
    if type(candidate) == "string" and candidate ~= "" then
      return candidate
    end
  end
  return tostring(agent.pane_id)
end

-- Chooser and menu rows, in rank order.
function M.rows(agents, seen)
  local rows = {}
  for i, agent in ipairs(M.rank(agents, seen)) do
    local status = M.status(agent, seen)
    local where = folder(agent.cwd)
    rows[i] = {
      text = GLYPH[status] .. " " .. label(agent),
      subText = where and (status .. " · " .. where) or status,
      paneId = agent.pane_id,
      status = status,
    }
  end
  return rows
end

-- Menu bar drop-down entries (hs.menubar format); the caller attaches the click handlers.
-- An error replaces the rows, which would be stale.
function M.menu(rows, err)
  if err then
    return { { title = err, disabled = true } }
  end
  if #rows == 0 then
    return { { title = "No Herdr agents", disabled = true } }
  end
  local items = {}
  for i, row in ipairs(rows) do
    items[i] = { title = row.text, tooltip = row.subText, paneId = row.paneId }
  end
  return items
end

-- The menu bar title, shown next to the icon: the count when something waits, nothing otherwise.
-- With an error the count is unknown, which must not look like "nothing waits".
function M.title(count, err)
  if err then
    return "?"
  end
  if not count or count == 0 then
    return ""
  end
  return tostring(count)
end

-- Which icon the menu bar shows: "down" when Herdr cannot be read, "waiting" while agents wait.
function M.state(count, err)
  if err then
    return "down"
  end
  return (count or 0) > 0 and "waiting" or "idle"
end

-- Statuses this module does not know, sorted, each once: Herdr may add or rename one, and such an
-- agent is never counted.
function M.unknownStatuses(agents)
  local found, list = {}, {}
  for _, agent in ipairs(agents) do
    local status = agent.agent_status
    if status ~= nil and PRIORITY[status] == nil and not found[status] then
      found[status] = true
      list[#list + 1] = tostring(status)
    end
  end
  table.sort(list)
  return list
end

return M
