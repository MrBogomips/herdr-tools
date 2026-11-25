local h = ...
local family = h.load("family")

-- An agent as `herdr agent list` reports it, trimmed to the fields family.lua reads.
local function agent(pane, tab, cwd, name)
  return { pane_id = pane, tab_id = tab, workspace_id = pane:match("^([^:]+)"), cwd = cwd, name = name }
end

return {
  named_agents_in_a_tab_are_children_of_its_only_unnamed_agent = function()
    local f = family.of({
      agent("w1:p1", "w1:t1", "/hub"),
      agent("w1:p2", "w1:t1", "/hub/design", "design"),
      agent("w1:p3", "w1:t1", "/hub/product", "product"),
      agent("w1:p9", "w1:t2", "/elsewhere"),
    })
    h.eq(f.parentOf, { ["w1:p2"] = "w1:p1", ["w1:p3"] = "w1:p1" })
    h.eq(f.childrenOf, { ["w1:p1"] = { "w1:p2", "w1:p3" } })
  end,

  a_child_in_its_own_tab_belongs_to_the_master_of_its_workspace_holding_its_folder = function()
    local f = family.of({
      agent("w1:p1", "w1:t1", "/hub/"),
      agent("w1:p2", "w1:t2", "/hub/design", "design"),
      agent("w1:p3", "w1:t3", "/hubble", "other"),
    })
    h.eq(f.parentOf, { ["w1:p2"] = "w1:p1" })
  end,

  a_child_in_another_workspace_is_not_matched_by_folder = function()
    local f = family.of({
      agent("w1:p1", "w1:t1", "/hub"),
      agent("w2:p2", "w2:t2", "/hub/design", "design"),
    })
    h.eq(f.parentOf, {})
  end,

  two_unnamed_agents_in_the_tab_leave_its_named_agents_top_level = function()
    local f = family.of({
      agent("w1:p1", "w1:t1", "/hub"),
      agent("w1:p2", "w1:t1", "/hub"),
      agent("w1:p3", "w1:t1", "/hub/design", "design"),
    })
    h.eq(f.parentOf, {})
    h.eq(f.childrenOf, {})
  end,

  two_masters_holding_the_folder_leave_the_child_top_level = function()
    local f = family.of({
      agent("w1:p1", "w1:t1", "/hub"),
      agent("w1:p2", "w1:t2", "/hub"),
      agent("w1:p3", "w1:t3", "/hub/design", "design"),
    })
    h.eq(f.parentOf, {})
  end,

  named_agents_alone_and_an_empty_name_are_top_level = function()
    local f = family.of({
      agent("w1:p1", "w1:t1", "/hub", "solo"),
      agent("w1:p2", "w1:t2", "/hub/x", ""),
      agent("w1:p3", "w1:t3", nil, "nofolder"),
    })
    h.eq(f.parentOf, {})
    h.eq(f.childrenOf, {})
  end,

  none_has_no_family = function()
    h.eq(family.none(), { parentOf = {}, childrenOf = {} })
  end,

  counts_say_how_many_masters_and_sub_sessions = function()
    local f = family.of({
      agent("w1:p1", "w1:t1", "/hub"),
      agent("w1:p2", "w1:t1", "/hub/a", "a"),
      agent("w1:p3", "w1:t1", "/hub/b", "b"),
    })
    h.eq(family.counts(f), { masters = 1, children = 2 })
    h.eq(family.counts(family.none()), { masters = 0, children = 0 })
  end,
}
