-- Which Herdr agents need the user, in what order, and what the menu bar says about them.
-- Pure Lua: no hs.* calls, so it runs under plain Lua in the tests.
--
-- An agent is one entry of `herdr agent list`; the fields read here are pane_id, agent_status,
-- focused, completion_seq, state_change_seq, terminal_title_stripped, terminal_title and cwd.
-- "seen" maps a pane_id to the completion_seq the user has already looked at.
-- "times" maps a pane_id to how long its current state has lasted and when it began, as
-- since.describe() says it: { age = "12m", clock = "09:41" }.

local M = {}

-- Lower comes first. Statuses Herdr may add later rank with "unknown".
local PRIORITY = { blocked = 1, done = 2, unknown = 3, idle = 4, working = 5 }
local STATUSES = { "blocked", "done", "unknown", "idle", "working" }
-- The legend's text glyphs, close to the symbol inside each status icon (icon.lua).
local GLYPH = { blocked = "⏸", done = "✓", unknown = "?", idle = "○", working = "◐" }
local MEANING = { done = "done, not seen" }

-- Status colors (hs.drawing.color tables), readable on light and dark backgrounds.
M.COLOR = {
  blocked = { red = 1.0, green = 0.58, blue = 0.0, alpha = 1 },
  done = { red = 0.2, green = 0.78, blue = 0.35, alpha = 1 },
  unknown = { red = 0.69, green = 0.32, blue = 0.87, alpha = 1 },
  idle = { red = 0.56, green = 0.56, blue = 0.58, alpha = 1 },
  working = { red = 0.04, green = 0.52, blue = 1.0, alpha = 1 },
}

-- The sort orders, in the order Tab cycles them. state_change_seq is one counter for all panes, so
-- it orders the queue exactly. fifo: oldest change first; lifo: newest first; name: by title.
M.ORDERS = { "fifo", "lifo", "name" }
local ORDER_NAME = { fifo = "FIFO", lifo = "LIFO", name = "by name" }
local ORDER_SHORT = { fifo = "FIFO", lifo = "LIFO", name = "name" }
local SORT_TITLE = { fifo = "FIFO: oldest first", lifo = "LIFO: newest first", name = "By name" }

-- A known order, "fifo" otherwise.
function M.order(order)
  return ORDER_NAME[order] and order or M.ORDERS[1]
end

function M.nextOrder(order)
  order = M.order(order)
  for i, name in ipairs(M.ORDERS) do
    if name == order then
      return M.ORDERS[i % #M.ORDERS + 1]
    end
  end
end

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

-- The comparison of two agents for an order; each returns nil on a tie.
local function byStatus(a, b, seen)
  local pa, pb = PRIORITY[M.status(a, seen)], PRIORITY[M.status(b, seen)]
  if pa ~= pb then
    return pa < pb
  end
end

local function byChange(a, b, newestFirst)
  local sa, sb = a.state_change_seq or 0, b.state_change_seq or 0
  if sa ~= sb then
    return (sa > sb) == newestFirst
  end
end

local function byName(a, b)
  local la, lb = label(a):lower(), label(b):lower()
  if la ~= lb then
    return la < lb
  end
end

-- Whether agent a comes before agent b in the given order: by status, most urgent first, then by
-- state change; or by title, then status. A full tie goes by pane id, so the order is stable.
local function before(a, b, seen, order)
  local first
  if order == "name" then
    first = byName(a, b)
    if first == nil then
      first = byStatus(a, b, seen)
    end
  else
    first = byStatus(a, b, seen)
    if first == nil then
      first = byChange(a, b, order == "lifo")
    end
  end
  if first == nil then
    return tostring(a.pane_id) < tostring(b.pane_id)
  end
  return first
end

local function sorted(agents, seen, order)
  local list = {}
  for i, agent in ipairs(agents) do
    list[i] = agent
  end
  table.sort(list, function(a, b) return before(a, b, seen, order) end)
  return list
end

-- Whether an agent waits without a sound or a count: a sub-session that is done. Its master hears
-- about it; one blocked on a question still needs the user. fam comes from family.of().
function M.quiet(agent, seen, fam)
  return fam ~= nil and fam.parentOf[agent.pane_id] ~= nil and M.status(agent, seen) == "done"
end

-- Each master or top-level agent with its sub-sessions, keyed by the member that ranks the group:
-- the most urgent one that is not quiet (the head, in the name order).
local function groups(agents, seen, order, fam)
  local byPane, list = {}, {}
  for _, agent in ipairs(agents) do
    byPane[agent.pane_id] = agent
  end
  for _, agent in ipairs(agents) do
    if fam.parentOf[agent.pane_id] == nil then
      local children, key = {}, agent
      for _, pane in ipairs(fam.childrenOf[agent.pane_id] or {}) do
        local child = byPane[pane]
        if child then
          children[#children + 1] = child
          if order ~= "name" and not M.quiet(child, seen, fam) and before(child, key, seen, order) then
            key = child
          end
        end
      end
      list[#list + 1] = { head = agent, key = key, children = sorted(children, seen, order) }
    end
  end
  -- Keys are distinct agents and before() breaks every tie, so the groups' order is stable.
  table.sort(list, function(a, b) return before(a.key, b.key, seen, order) end)
  return list
end

-- A new list in the given order (default "fifo"), see before(). With a family (family.of()), each
-- master is followed by its sub-sessions, and the group ranks as its most urgent member that is
-- not quiet.
function M.rank(agents, seen, order, fam)
  order = M.order(order)
  if fam == nil then
    return sorted(agents, seen, order)
  end
  local ranked = {}
  for _, group in ipairs(groups(agents, seen, order, fam)) do
    ranked[#ranked + 1] = group.head
    for _, child in ipairs(group.children) do
      ranked[#ranked + 1] = child
    end
  end
  return ranked
end

-- How many agents wait for the user: blocked on a question, or done and not yet seen; with a
-- family, a sub-session that is done does not count (see quiet()).
function M.count(agents, seen, fam)
  local n = 0
  for _, agent in ipairs(agents) do
    local status = M.status(agent, seen)
    if (status == "blocked" or status == "done") and not M.quiet(agent, seen, fam) then
      n = n + 1
    end
  end
  return n
end

-- A new seen record: the focused done agent is seen when Herdr's terminal is in front. Panes that are
-- gone are dropped, and so are panes whose completion counter is missing or went backwards: Herdr
-- restarted, its sequence numbers start over and pane ids are reused.
function M.updateSeen(seen, agents, terminalFrontmost)
  local updated = {}
  for _, agent in ipairs(agents) do
    local pane, completion = agent.pane_id, agent.completion_seq
    if pane ~= nil and completion ~= nil then
      local viewed = seen[pane]
      if viewed ~= nil and completion < viewed then
        viewed = nil
      end
      if terminalFrontmost and agent.focused and agent.agent_status == "done" then
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

local function waiting(status)
  return status == "blocked" or status == "done"
end

-- What a master's row says about its sub-sessions: how many, and how many wait.
local function summary(pane, byPane, seen, fam)
  local children = fam.childrenOf[pane]
  if children == nil then
    return nil
  end
  local waits = { blocked = 0, done = 0 }
  for _, child in ipairs(children) do
    local status = byPane[child] and M.status(byPane[child], seen)
    if waits[status] then
      waits[status] = waits[status] + 1
    end
  end
  local parts = { ("+%d sub"):format(#children) }
  for _, status in ipairs({ "blocked", "done" }) do
    if waits[status] > 0 then
      parts[#parts + 1] = ("%d %s"):format(waits[status], status)
    end
  end
  return table.concat(parts, " · ")
end

-- Chooser and menu rows, in the given order; the caller shows the status icon. `when` is the status
-- and how long it has lasted ("blocked 12m"); a waiting agent's subText also says since when.
-- With a family (family.of()), sub-sessions follow their master, indented (depth 1), and the
-- master's subText sums them up; `flat` keeps one list and names the master in the subText instead.
function M.rows(agents, seen, order, times, fam, flat)
  times = times or {}
  local byPane = {}
  for _, agent in ipairs(agents) do
    byPane[agent.pane_id] = agent
  end
  local rows = {}
  for i, agent in ipairs(M.rank(agents, seen, order, not flat and fam or nil)) do
    local status = M.status(agent, seen)
    local time = times[agent.pane_id]
    local age = time and time.age
    local when = age and (status .. " " .. age) or status
    local parts = { when }
    if time and waiting(status) then
      parts[#parts + 1] = "since " .. time.clock
    end
    parts[#parts + 1] = folder(agent.cwd)
    local master = fam and fam.parentOf[agent.pane_id]
    local depth
    if master and flat then
      parts[#parts + 1] = "↳ " .. label(byPane[master] or { pane_id = master })
    elseif master then
      depth = 1
    elseif fam then
      parts[#parts + 1] = summary(agent.pane_id, byPane, seen, fam)
    end
    rows[i] = {
      text = depth and ("↳ " .. label(agent)) or label(agent),
      subText = table.concat(parts, " · "),
      paneId = agent.pane_id,
      status = status,
      when = when,
      age = age,
      depth = depth,
    }
  end
  return rows
end

-- What each glyph means, most urgent first, as parts (to color each glyph).
local function legendParts()
  local parts = {}
  for i, status in ipairs(STATUSES) do
    parts[i] = { status = status, glyph = GLYPH[status], meaning = MEANING[status] or status }
  end
  return parts
end

-- The orders Tab moves to from this one, in cycle order.
local function others(order)
  local names, following = {}, M.nextOrder(order)
  while following ~= order do
    names[#names + 1] = ORDER_SHORT[following]
    following = M.nextOrder(following)
  end
  return table.concat(names, ", ")
end

-- The picker's footer line: what the glyphs mean, then the order and where Tab goes.
function M.legend(order)
  order = M.order(order)
  return {
    parts = legendParts(),
    hint = ("Sorted %s · Tab: %s"):format(ORDER_NAME[order], others(order)),
  }
end

-- The chooser's search field text while nothing is typed.
function M.placeholder(order)
  return ("Filter agents · sorted %s (Tab to change)"):format(ORDER_NAME[M.order(order)])
end

-- Menu bar drop-down entries (hs.menubar format): the rows, the sort choices, the legend. The caller
-- attaches the status icons and the click handlers: a jump for an entry with a paneId, a sort for
-- one with an order. An error replaces the rows, which would be stale.
function M.menu(rows, err, order)
  if err then
    return { { title = err, disabled = true } }
  end
  if #rows == 0 then
    return { { title = "No Herdr agents", disabled = true } }
  end
  order = M.order(order)
  local items = {}
  for i, row in ipairs(rows) do
    local title = row.age and (row.text .. " · " .. row.age) or row.text
    items[i] = { title = title, tooltip = row.subText, paneId = row.paneId, status = row.status, indent = row.depth }
  end
  local sorts, legend = {}, {}
  for i, name in ipairs(M.ORDERS) do
    sorts[i] = { title = SORT_TITLE[name], order = name, checked = name == order }
  end
  for i, part in ipairs(legendParts()) do
    legend[i] = { title = part.meaning, status = part.status }
  end
  items[#items + 1] = { title = "-" }
  items[#items + 1] = { title = "Sort by", menu = sorts }
  items[#items + 1] = { title = "Legend", menu = legend }
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
