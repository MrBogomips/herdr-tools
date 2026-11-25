-- Which Herdr agents are sub-sessions of another one, read from `herdr agent list` alone.
-- Pure Lua: no hs.* calls, so it runs under plain Lua in the tests.
--
-- A session that starts helpers with `herdr agent start <name>` gives each one a Herdr name; the
-- session itself has none. So:
--   * in a tab, the named agents are the children of the only unnamed agent there (helpers split
--     into panes next to their master);
--   * a named agent in a tab without any unnamed agent (helpers in tabs of their own) is the child
--     of the only unnamed agent of its workspace whose folder holds the child's folder.
-- Anything ambiguous (two unnamed agents in the tab, two masters holding the folder) stays a
-- top-level agent: no guess.
--
-- Fields read: pane_id, name, tab_id, workspace_id, cwd.

local M = {}

local function named(agent)
  return type(agent.name) == "string" and agent.name ~= ""
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

local function add(index, key, agent)
  if key ~= nil then
    index[key] = index[key] or {}
    table.insert(index[key], agent)
  end
end

-- The unnamed agents of each tab and of each workspace.
local function masters(agents)
  local byTab, byWorkspace = {}, {}
  for _, agent in ipairs(agents) do
    if not named(agent) then
      add(byTab, agent.tab_id, agent)
      add(byWorkspace, agent.workspace_id, agent)
    end
  end
  return byTab, byWorkspace
end

-- The master of a named agent, or nil.
local function masterOf(agent, byTab, byWorkspace)
  local inTab = agent.tab_id and byTab[agent.tab_id] or {}
  if #inTab == 1 then
    return inTab[1]
  end
  if #inTab > 1 then
    return nil
  end
  local found
  for _, candidate in ipairs(agent.workspace_id and byWorkspace[agent.workspace_id] or {}) do
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
  local byTab, byWorkspace = masters(agents)
  for _, agent in ipairs(agents) do
    if named(agent) then
      local master = masterOf(agent, byTab, byWorkspace)
      if master then
        parentOf[agent.pane_id] = master.pane_id
        childrenOf[master.pane_id] = childrenOf[master.pane_id] or {}
        table.insert(childrenOf[master.pane_id], agent.pane_id)
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
