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

  a_pane_label_names_an_agent_that_herdr_left_unnamed = function()
    -- `herdr agent start` timed out: the child runs, unnamed, in the pane its master labelled.
    local child = agent("w1:p3G", "w1:t1", "/hub/design")
    child.pane_label = "pr59-design"
    local f = family.of({ agent("w1:p2K", "w1:t1", "/hub"), child })
    h.eq(f.parentOf, { ["w1:p3G"] = "w1:p2K" })
  end,

  a_labelled_master_keeps_its_named_helpers = function()
    local master = agent("w1:p1", "w1:t1", "/r")
    master.pane_label = "main"
    local f = family.of({ master, agent("w1:p2", "w1:t1", "/r/x", "helper"), agent("w1:p3", "w1:t2", "/") })
    h.eq(f.parentOf, { ["w1:p2"] = "w1:p1" })
  end,

  a_labelled_agent_alone_in_its_tab_is_not_a_helper_of_another_tab = function()
    local alone = agent("w1:p2", "w1:t2", "/hub/x")
    alone.pane_label = "notes"
    local f = family.of({ agent("w1:p1", "w1:t1", "/hub"), alone })
    h.eq(f.parentOf, {})
  end,

  an_empty_pane_label_does_not_name_an_agent = function()
    local other = agent("w1:p3", "w1:t1", "/hub/design")
    other.pane_label = ""
    local f = family.of({ agent("w1:p1", "w1:t1", "/hub"), other, agent("w1:p4", "w1:t1", "/hub/x", "x") })
    -- Two unnamed agents, the oldest holding the others: the fallback below nests them all.
    h.eq(f.parentOf, { ["w1:p3"] = "w1:p1", ["w1:p4"] = "w1:p1" })
  end,

  the_oldest_unnamed_agent_of_a_tab_is_its_master_when_its_folder_holds_the_others = function()
    -- Pane ids count up in base 36 within a workspace: p2K is older than p3H and p3J.
    local f = family.of({
      agent("w12:p3J", "w12:tS", "/hub/prototipo"),
      agent("w12:p2K", "w12:tS", "/hub"),
      agent("w12:p3H", "w12:tS", "/hub/design/.claude/worktrees/f68"),
    })
    h.eq(f.parentOf, { ["w12:p3H"] = "w12:p2K", ["w12:p3J"] = "w12:p2K" })
    h.eq(f.childrenOf, { ["w12:p2K"] = { "w12:p3J", "w12:p3H" } })
  end,

  unnamed_agents_in_the_same_folder_stay_top_level = function()
    local f = family.of({ agent("w1:p1", "w1:t1", "/repo"), agent("w1:p2", "w1:t1", "/repo") })
    h.eq(f.parentOf, {})
  end,

  an_older_agent_outside_the_folder_leaves_the_tab_top_level = function()
    local f = family.of({
      agent("w1:p1", "w1:t1", "/hub"),
      agent("w1:p2", "w1:t1", "/hub/design"),
      agent("w1:p3", "w1:t1", "/elsewhere"),
    })
    h.eq(f.parentOf, {})
  end,

  a_younger_agent_holding_the_folder_is_not_a_master = function()
    local f = family.of({ agent("w1:pA", "w1:t1", "/hub/design"), agent("w1:pB", "w1:t1", "/hub") })
    h.eq(f.parentOf, {})
  end,

  pane_ids_without_a_counter_give_no_order = function()
    local f = family.of({ agent("w1:main", "w1:t1", "/hub"), agent("w1:p2", "w1:t1", "/hub/design") })
    h.eq(f.parentOf, {})
  end,

  an_unnamed_child_is_not_a_master_for_named_agents_in_other_tabs = function()
    local f = family.of({
      agent("w1:p1", "w1:t1", "/hub"),
      agent("w1:p2", "w1:t1", "/hub/design"),
      agent("w1:p3", "w1:t2", "/hub/design/sub", "sub"),
    })
    h.eq(f.parentOf, { ["w1:p2"] = "w1:p1", ["w1:p3"] = "w1:p1" })
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
