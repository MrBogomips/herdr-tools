local h = ...
local attention = h.load("attention")
local family = h.load("family")

-- An agent of `herdr agent list`; `name` makes it a sub-session of the unnamed agent in its tab.
local function agent(pane, status, seq, fields)
  local a = {
    pane_id = pane, agent_status = status, state_change_seq = seq, completion_seq = seq, focused = false,
    tab_id = pane:match("^([^:]+)") .. ":t", workspace_id = pane:match("^([^:]+)"),
  }
  for k, v in pairs(fields or {}) do
    a[k] = v
  end
  return a
end

local function panes(list)
  local out = {}
  for i, a in ipairs(list) do
    out[i] = a.pane_id
  end
  return out
end

-- Master w1:p1 with children design and product; w2:p1 on its own.
local function hub(masterStatus, designStatus, productStatus)
  return {
    agent("w1:p1", masterStatus, 10, { terminal_title_stripped = "Master", cwd = "/hub" }),
    agent("w1:p2", designStatus, 3, { name = "design", terminal_title_stripped = "design", cwd = "/hub/design" }),
    agent("w1:p3", productStatus, 4, { name = "product", terminal_title_stripped = "product", cwd = "/hub/product" }),
    agent("w2:p1", "done", 6, { terminal_title_stripped = "Solo", cwd = "/solo" }),
  }
end

return {
  a_done_child_is_quiet_and_not_counted = function()
    local agents = hub("idle", "done", "idle")
    local f = family.of(agents)
    h.eq(attention.quiet(agents[2], {}, f), true)
    h.eq(attention.quiet(agents[4], {}, f), false)
    h.eq(attention.count(agents, {}, f), 1)
  end,

  a_blocked_child_counts_like_a_master = function()
    local agents = hub("idle", "blocked", "done")
    local f = family.of(agents)
    h.eq(attention.quiet(agents[2], {}, f), false)
    h.eq(attention.count(agents, {}, f), 2)
  end,

  without_a_family_every_waiting_agent_counts = function()
    h.eq(attention.count(hub("idle", "done", "done"), {}), 3)
  end,

  children_follow_their_master_and_a_quiet_child_does_not_lift_the_group = function()
    local agents = hub("idle", "done", "working")
    local ranked = attention.rank(agents, {}, "fifo", family.of(agents))
    h.eq(panes(ranked), { "w2:p1", "w1:p1", "w1:p2", "w1:p3" })
  end,

  a_blocked_child_lifts_its_group_to_the_top = function()
    local agents = hub("working", "idle", "blocked")
    local ranked = attention.rank(agents, {}, "fifo", family.of(agents))
    h.eq(panes(ranked), { "w1:p1", "w1:p3", "w1:p2", "w2:p1" })
  end,

  groups_sort_by_master_name_in_name_order = function()
    local agents = hub("idle", "idle", "idle")
    agents[4].terminal_title_stripped = "Alpha"
    local ranked = attention.rank(agents, {}, "name", family.of(agents))
    h.eq(panes(ranked), { "w2:p1", "w1:p1", "w1:p2", "w1:p3" })
  end,

  child_rows_are_indented_and_the_master_row_sums_them_up = function()
    local agents = hub("idle", "done", "blocked")
    local rows = attention.rows(agents, {}, "fifo", {}, family.of(agents))
    h.eq(rows[1].text, "Master")
    h.eq(rows[1].subText, "idle · hub · +2 sub · 1 blocked · 1 done")
    h.eq(rows[1].depth, nil)
    h.eq({ rows[2].text, rows[2].depth, rows[2].subText }, { "product", 1, "blocked · product" })
    h.eq({ rows[3].text, rows[3].depth }, { "design", 1 })
  end,

  a_master_with_quiet_children_only_says_how_many = function()
    local agents = hub("idle", "idle", "working")
    local rows = attention.rows(agents, {}, "fifo", {}, family.of(agents))
    h.eq(rows[2].subText, "idle · hub · +2 sub")
  end,

  flat_rows_keep_the_order_and_name_the_master = function()
    local agents = hub("idle", "done", "working")
    local rows = attention.rows(agents, {}, "fifo", {}, family.of(agents), true)
    h.eq(rows[1].text, "design")
    h.eq(rows[1].subText, "done · design · sub of Master")
    h.eq(rows[1].depth, nil)
    h.eq(rows[2].text, "Solo")
  end,

  menu_indents_child_rows = function()
    local items = attention.menu({
      { text = "Master", subText = "idle", paneId = "w1:p1", status = "idle" },
      { text = "design", subText = "done", paneId = "w1:p2", status = "done", depth = 1 },
    }, nil, "fifo")
    h.eq(items[1].indent, nil)
    h.eq(items[2].indent, 1)
  end,
}
