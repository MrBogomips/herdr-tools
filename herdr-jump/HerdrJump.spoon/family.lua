-- Which Herdr agents are sub-sessions of another one, read from `herdr agent list` and the pane labels.
-- Pure Lua: no hs.* calls, so it runs under plain Lua in the tests.
--
-- A session that starts helpers with `herdr agent start <name>` gives each one a Herdr name; the
-- session itself has none. So:
--   * in a tab, the named agents are the children of the only unnamed agent there (helpers split
--     into panes next to their master);
--   * a named agent in a tab without any unnamed agent (helpers in tabs of their own) is the child
--     of the only unnamed agent of its workspace whose folder holds the child's folder.
-- Two fallbacks cover a helper that Herdr left unnamed (`herdr agent start` timed out, yet the
-- agent came up and Herdr detected it on its own):
--   * in a tab where only one unnamed agent has an unlabelled pane, that one is the master and the
--     others are its helpers: the master labels a helper's pane before starting it (a pane label
--     alone never makes an agent a helper, as users label panes of their own too);
--   * in a tab with several unnamed agents, the oldest one (pane ids count up within a workspace)
--     is the master when its folder strictly holds the folder of every other agent of the tab.
-- Anything else ambiguous (two unnamed agents in one folder, two masters holding the folder)
-- stays a top-level agent: no guess.
--
-- Fields read: pane_id, name, pane_label (added by herdr.lua from `herdr pane list`), tab_id,
-- workspace_id, cwd.

local M = {}

local function text(value)
  return type(value) == "string" and value ~= ""
end

-- A Herdr name. A pane label is weaker: it names a helper only next to an unlabelled master (see
-- tabFamily), since users label panes of their own too.
local function named(agent)
  return text(agent.name)
end

local function labelled(agent)
  return text(agent.pane_label)
end

local function trimmed(path)
  if type(path) ~= "string" or path == "" then
    return nil
  end
  local stripped = path:gsub("/+$", "")
  return stripped ~= "" and stripped or "/"
end

-- Whether folder `outer` is `inner` or holds it.
local function holds(outer, inner)
  outer, inner = trimmed(outer), trimmed(inner)
  if outer == nil or inner == nil then
    return false
  end
  if outer == inner or outer == "/" then
    return true
  end
  return inner:sub(1, #outer + 1) == outer .. "/"
end

-- Whether folder `outer` holds `inner` and is not `inner` itself.
local function strictlyHolds(outer, inner)
  return holds(outer, inner) and trimmed(outer) ~= trimmed(inner)
end

-- The creation rank of a pane: Herdr numbers panes in base 36 within a workspace ("w12:p3G").
-- nil when the id has no such counter.
local function age(agent)
  local counter = type(agent.pane_id) == "string" and agent.pane_id:match(":p(%w+)$")
  return counter and tonumber(counter, 36)
end

local function add(index, key, agent)
  if key ~= nil then
    index[key] = index[key] or {}
    table.insert(index[key], agent)
  end
end

-- The agents of each tab, in list order.
local function byTab(agents)
  local tabs, order = {}, {}
  for _, agent in ipairs(agents) do
    if agent.tab_id ~= nil and tabs[agent.tab_id] == nil then
      tabs[agent.tab_id] = {}
      order[#order + 1] = agent.tab_id
    end
    add(tabs, agent.tab_id, agent)
  end
  return tabs, order
end

local function unnamedOf(members)
  local list = {}
  for _, agent in ipairs(members) do
    if not named(agent) then
      list[#list + 1] = agent
    end
  end
  return list
end

-- The oldest of the given agents, or nil when one has no creation rank.
local function oldest(list)
  local found, foundAge
  for _, agent in ipairs(list) do
    local rank = age(agent)
    if rank == nil then
      return nil
    end
    if foundAge == nil or rank < foundAge then
      found, foundAge = agent, rank
    end
  end
  return found
end

-- The agents of the list other than master.
local function others(members, master)
  local list = {}
  for _, agent in ipairs(members) do
    if agent ~= master then
      list[#list + 1] = agent
    end
  end
  return list
end

-- The master of a tab and its children there, or nil, tried in this order:
--   * the only unnamed agent, with the named ones;
--   * the only unnamed agent whose pane has no label, with all the others (helpers Herdr left
--     unnamed in the panes their master labelled);
--   * the oldest unnamed agent, with all the others, when its folder strictly holds theirs.
local function tabFamily(members)
  local unnamed = unnamedOf(members)
  if #unnamed == 0 then
    return nil
  end
  if #unnamed == 1 then
    return unnamed[1], others(members, unnamed[1])
  end
  local plain = {}
  for _, agent in ipairs(unnamed) do
    if not labelled(agent) then
      plain[#plain + 1] = agent
    end
  end
  if #plain == 1 then
    return plain[1], others(members, plain[1])
  end
  local master = oldest(unnamed)
  if not master then
    return nil
  end
  local children = {}
  for _, agent in ipairs(members) do
    if agent ~= master then
      if not strictlyHolds(master.cwd, agent.cwd) then
        return nil
      end
      children[#children + 1] = agent
    end
  end
  return master, children
end

-- The master of a named agent in a tab without a master, or nil: the only master candidate of its
-- workspace whose folder holds the agent's folder.
local function workspaceMaster(agent, candidates)
  local found
  for _, candidate in ipairs(agent.workspace_id and candidates[agent.workspace_id] or {}) do
    if holds(candidate.cwd, agent.cwd) then
      if found then
        return nil
      end
      found = candidate
    end
  end
  return found
end

-- { parentOf = child pane id -> master pane id, childrenOf = master pane id -> { child pane ids } }.
function M.of(agents)
  local parentOf, childrenOf = {}, {}
  local function link(child, master)
    parentOf[child.pane_id] = master.pane_id
    childrenOf[master.pane_id] = childrenOf[master.pane_id] or {}
    table.insert(childrenOf[master.pane_id], child.pane_id)
  end
  local tabs, order = byTab(agents)
  local settled = {}
  for _, tab in ipairs(order) do
    local unnamed = unnamedOf(tabs[tab])
    local master, children = tabFamily(tabs[tab])
    if master then
      for _, child in ipairs(children) do
        link(child, master)
      end
    end
    -- A tab with unnamed agents but no master is ambiguous: its named agents stay top-level.
    settled[tab] = master ~= nil or #unnamed > 0
  end
  -- Masters for helpers in tabs of their own: unnamed agents that are no one's child.
  local candidates = {}
  for _, agent in ipairs(agents) do
    if not named(agent) and parentOf[agent.pane_id] == nil then
      add(candidates, agent.workspace_id, agent)
    end
  end
  for _, agent in ipairs(agents) do
    if named(agent) and parentOf[agent.pane_id] == nil and not (agent.tab_id and settled[agent.tab_id]) then
      local master = workspaceMaster(agent, candidates)
      if master then
        link(agent, master)
      end
    end
  end
  return { parentOf = parentOf, childrenOf = childrenOf }
end

-- How many masters and sub-sessions a family has, for Diagnostics.
function M.counts(fam)
  local counts = { masters = 0, children = 0 }
  for _, children in pairs(fam.childrenOf) do
    counts.masters = counts.masters + 1
    counts.children = counts.children + #children
  end
  return counts
end

-- No family at all: every agent top-level.
function M.none()
  return { parentOf = {}, childrenOf = {} }
end

return M
