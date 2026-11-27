local h = ...
local attention = h.load("attention")

-- Agents as `herdr agent list` reports them, trimmed to the fields HerdrJump reads.
local function agent(pane, status, fields)
  local a = { pane_id = pane, agent_status = status, focused = false }
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

return {
  rank_puts_blocked_then_done_then_unknown_then_idle_then_working = function()
    local agents = {
      agent("w1:p1", "working", { state_change_seq = 50 }),
      agent("w2:p1", "idle", { state_change_seq = 40 }),
      agent("w3:p1", "done", { state_change_seq = 10, completion_seq = 10 }),
      agent("w4:p1", "unknown", { state_change_seq = 30 }),
      agent("w5:p1", "blocked", { state_change_seq = 5 }),
    }
    h.eq(panes(attention.rank(agents, {})), { "w5:p1", "w3:p1", "w4:p1", "w2:p1", "w1:p1" })
  end,

  fifo_is_the_default_and_puts_the_oldest_state_change_first_within_a_status = function()
    local agents = {
      agent("w1:p1", "done", { state_change_seq = 7, completion_seq = 7 }),
      agent("w2:p1", "done", { state_change_seq = 9, completion_seq = 9 }),
      agent("w3:p1", "done", { state_change_seq = 8, completion_seq = 8 }),
    }
    h.eq(panes(attention.rank(agents, {})), { "w1:p1", "w3:p1", "w2:p1" })
    h.eq(panes(attention.rank(agents, {}, "fifo")), { "w1:p1", "w3:p1", "w2:p1" })
  end,

  fifo_serves_blocked_agents_before_done_ones_however_old = function()
    local agents = {
      agent("w1:p1", "done", { state_change_seq = 2, completion_seq = 2 }),
      agent("w2:p1", "blocked", { state_change_seq = 9 }),
      agent("w3:p1", "blocked", { state_change_seq = 5 }),
      agent("w4:p1", "done", { state_change_seq = 1, completion_seq = 1 }),
    }
    h.eq(panes(attention.rank(agents, {}, "fifo")), { "w3:p1", "w2:p1", "w4:p1", "w1:p1" })
  end,

  lifo_puts_the_latest_state_change_first_within_a_status = function()
    local agents = {
      agent("w1:p1", "done", { state_change_seq = 7, completion_seq = 7 }),
      agent("w2:p1", "blocked", { state_change_seq = 3 }),
      agent("w3:p1", "done", { state_change_seq = 9, completion_seq = 9 }),
      agent("w4:p1", "done", { state_change_seq = 8, completion_seq = 8 }),
    }
    h.eq(panes(attention.rank(agents, {}, "lifo")), { "w2:p1", "w3:p1", "w4:p1", "w1:p1" })
  end,

  name_sorts_every_agent_by_title_ignoring_case = function()
    local agents = {
      agent("w1:p1", "blocked", { state_change_seq = 1, terminal_title_stripped = "lumon-Offsite" }),
      agent("w2:p1", "working", { state_change_seq = 2, terminal_title_stripped = "ACME-API" }),
      agent("w3:p1", "idle", { state_change_seq = 3, cwd = "/srv/globex" }),
    }
    h.eq(panes(attention.rank(agents, {}, "name")), { "w2:p1", "w3:p1", "w1:p1" })
  end,

  name_breaks_a_tie_by_status_then_pane_id = function()
    local agents = {
      agent("w3:p1", "idle", { terminal_title_stripped = "ACME" }),
      agent("w2:p1", "blocked", { terminal_title_stripped = "acme" }),
      agent("w1:p1", "idle", { terminal_title_stripped = "Acme" }),
    }
    h.eq(panes(attention.rank(agents, {}, "name")), { "w2:p1", "w1:p1", "w3:p1" })
  end,

  an_unknown_order_ranks_as_fifo = function()
    local agents = {
      agent("w1:p1", "idle", { state_change_seq = 9 }),
      agent("w2:p1", "idle", { state_change_seq = 4 }),
    }
    h.eq(panes(attention.rank(agents, {}, "bogus")), { "w2:p1", "w1:p1" })
    h.eq(attention.order("bogus"), "fifo")
    h.eq(attention.order(nil), "fifo")
    h.eq(attention.order("name"), "name")
  end,

  nextOrder_cycles_fifo_lifo_name = function()
    h.eq(attention.nextOrder("fifo"), "lifo")
    h.eq(attention.nextOrder("lifo"), "name")
    h.eq(attention.nextOrder("name"), "fifo")
    h.eq(attention.nextOrder("bogus"), "lifo")
  end,

  rank_breaks_a_full_tie_by_pane_id_so_the_order_is_stable = function()
    local agents = {
      agent("w3:p1", "idle", { state_change_seq = 4 }),
      agent("w1:p2", "idle", { state_change_seq = 4 }),
      agent("w2:p1", "idle", { state_change_seq = 4 }),
    }
    h.eq(panes(attention.rank(agents, {})), { "w1:p2", "w2:p1", "w3:p1" })
  end,

  rank_treats_a_missing_or_new_status_as_unknown = function()
    local agents = {
      agent("w1:p1", "idle", { state_change_seq = 3 }),
      agent("w2:p1", nil, { state_change_seq = 2 }),
      agent("w3:p1", "thinking", { state_change_seq = 1 }),
      agent("w4:p1", "done", { state_change_seq = 1, completion_seq = 1 }),
    }
    h.eq(panes(attention.rank(agents, {})), { "w4:p1", "w3:p1", "w2:p1", "w1:p1" })
  end,

  rank_leaves_the_input_list_untouched = function()
    local agents = { agent("w1:p1", "idle"), agent("w2:p1", "blocked") }
    attention.rank(agents, {})
    h.eq(panes(agents), { "w1:p1", "w2:p1" })
  end,

  count_includes_only_blocked_and_done = function()
    local agents = {
      agent("w1:p1", "blocked"),
      agent("w2:p1", "done", { completion_seq = 4 }),
      agent("w3:p1", "idle"),
      agent("w4:p1", "working"),
      agent("w5:p1", "unknown"),
    }
    h.eq(attention.count(agents, {}), 2)
  end,

  a_done_agent_already_seen_counts_and_ranks_as_idle = function()
    local agents = {
      agent("w1:p1", "done", { state_change_seq = 9, completion_seq = 12 }),
      agent("w2:p1", "idle", { state_change_seq = 3 }),
    }
    local seen = { ["w1:p1"] = 12 }
    h.eq(attention.count(agents, seen), 0)
    h.eq(attention.status(agents[1], seen), "idle")
    -- As a done agent it would come first; as an idle one it follows the older idle agent.
    h.eq(panes(attention.rank(agents, seen)), { "w2:p1", "w1:p1" })
  end,

  a_newer_completion_than_the_one_seen_is_done_again = function()
    local agents = { agent("w1:p1", "done", { completion_seq = 13 }) }
    local seen = { ["w1:p1"] = 12 }
    h.eq(attention.count(agents, seen), 1)
    h.eq(attention.status(agents[1], seen), "done")
  end,

  a_done_agent_without_completion_seq_stays_done = function()
    local agents = { agent("w1:p1", "done") }
    h.eq(attention.status(agents[1], { ["w1:p1"] = 99 }), "done")
  end,

  seen_records_the_focused_done_agent_while_iterm_is_in_front = function()
    local agents = {
      agent("w1:p1", "done", { completion_seq = 21, focused = true }),
      agent("w2:p1", "done", { completion_seq = 22 }),
    }
    h.eq(attention.updateSeen({}, agents, true), { ["w1:p1"] = 21 })
  end,

  seen_ignores_the_focused_agent_while_another_app_is_in_front = function()
    local agents = { agent("w1:p1", "done", { completion_seq = 21, focused = true }) }
    h.eq(attention.updateSeen({}, agents, false), {})
  end,

  seen_ignores_a_focused_agent_that_is_not_done = function()
    local agents = { agent("w1:p1", "working", { completion_seq = 21, focused = true }) }
    h.eq(attention.updateSeen({}, agents, true), {})
  end,

  seen_keeps_listed_panes_and_drops_closed_ones = function()
    local agents = { agent("w1:p1", "working", { completion_seq = 5 }) }
    local seen = { ["w1:p1"] = 5, ["w9:p1"] = 8 }
    h.eq(attention.updateSeen(seen, agents, true), { ["w1:p1"] = 5 })
  end,

  seen_forgets_a_pane_whose_completion_counter_went_backwards = function()
    -- Herdr restarted: its sequence numbers start over and pane ids are reused.
    local agents = {
      agent("w1:p1", "done", { completion_seq = 3 }),
      agent("w2:p1", "working"),
      agent("w3:p1", "idle", { completion_seq = 40 }),
    }
    local seen = { ["w1:p1"] = 900, ["w2:p1"] = 901, ["w3:p1"] = 40 }
    local updated = attention.updateSeen(seen, agents, false)
    h.eq(updated, { ["w3:p1"] = 40 })
    h.eq(attention.count(agents, updated), 1)
  end,

  seen_returns_a_new_table_and_leaves_the_old_one_alone = function()
    local agents = { agent("w1:p1", "done", { completion_seq = 30, focused = true }) }
    local seen = { ["w1:p1"] = 5 }
    local updated = attention.updateSeen(seen, agents, true)
    h.eq(seen, { ["w1:p1"] = 5 })
    h.eq(updated, { ["w1:p1"] = 30 })
  end,

  sameSeen_compares_contents = function()
    h.eq(attention.sameSeen({ a = 1, b = 2 }, { b = 2, a = 1 }), true)
    h.eq(attention.sameSeen({ a = 1 }, { a = 2 }), false)
    h.eq(attention.sameSeen({ a = 1 }, { a = 1, b = 2 }), false)
    h.eq(attention.sameSeen({}, {}), true)
  end,

  rows_show_title_status_and_folder_in_rank_order = function()
    local agents = {
      agent("w1:p1", "idle", {
        state_change_seq = 2,
        terminal_title_stripped = "GLOBEX-ETL-Reviewing-Loader",
        cwd = "/Users/acme/git/globex-etl",
      }),
      agent("w2:p3", "blocked", {
        state_change_seq = 1,
        terminal_title_stripped = "ACME-API-Fixing-Auth",
        cwd = "/Users/acme/git/acme-api",
      }),
    }
    h.eq(attention.rows(agents, {}), {
      { text = "ACME-API-Fixing-Auth", subText = "blocked · acme-api", paneId = "w2:p3", status = "blocked", when = "blocked" },
      { text = "GLOBEX-ETL-Reviewing-Loader", subText = "idle · globex-etl", paneId = "w1:p1", status = "idle", when = "idle" },
    })
  end,

  rows_fall_back_to_the_raw_title_then_the_folder_then_the_pane = function()
    local agents = {
      agent("w1:p1", "working", { state_change_seq = 3, terminal_title_stripped = "", terminal_title = "◐ Initech" }),
      agent("w2:p1", "working", { state_change_seq = 2, cwd = "/srv/lumon/" }),
      agent("w3:p1", "working", { state_change_seq = 1 }),
    }
    local texts = {}
    for i, row in ipairs(attention.rows(agents, {}, "lifo")) do
      texts[i] = row.text .. " | " .. row.subText
    end
    h.eq(texts, { "◐ Initech | working", "lumon | working · lumon", "w3:p1 | working" })
  end,

  rows_follow_the_chosen_order = function()
    local agents = {
      agent("w1:p1", "done", { state_change_seq = 4, completion_seq = 4 }),
      agent("w2:p1", "done", { state_change_seq = 6, completion_seq = 6 }),
    }
    local function order(name)
      local out = {}
      for i, row in ipairs(attention.rows(agents, {}, name)) do
        out[i] = row.paneId
      end
      return out
    end
    h.eq(order("fifo"), { "w1:p1", "w2:p1" })
    h.eq(order("lifo"), { "w2:p1", "w1:p1" })
  end,

  rows_show_a_seen_done_agent_as_idle = function()
    local agents = { agent("w1:p1", "done", { completion_seq = 4, terminal_title_stripped = "ACME" }) }
    local row = attention.rows(agents, { ["w1:p1"] = 4 })[1]
    h.eq({ row.text, row.status }, { "ACME", "idle" })
  end,

  rows_say_how_long_and_since_when_a_waiting_agent_waits = function()
    local agents = {
      agent("w1:p1", "blocked", { state_change_seq = 5, terminal_title_stripped = "ACME", cwd = "/srv/acme-api" }),
      agent("w2:p1", "done", { state_change_seq = 6, completion_seq = 6, terminal_title_stripped = "Globex" }),
    }
    local times = {
      ["w1:p1"] = { age = "12m", clock = "09:41" },
      ["w2:p1"] = { age = "≥4m", clock = "≤09:49" },
    }
    local rows = attention.rows(agents, {}, "fifo", times)
    h.eq({ rows[1].when, rows[1].age, rows[1].subText }, { "blocked 12m", "12m", "blocked 12m · since 09:41 · acme-api" })
    h.eq({ rows[2].when, rows[2].age, rows[2].subText }, { "done ≥4m", "≥4m", "done ≥4m · since ≤09:49" })
  end,

  rows_say_how_long_without_since_for_agents_not_waiting = function()
    local agents = { agent("w1:p1", "working", { state_change_seq = 5, cwd = "/srv/initech-crm" }) }
    local times = { ["w1:p1"] = { age = "1m", clock = "09:52" } }
    local row = attention.rows(agents, {}, "fifo", times)[1]
    h.eq({ row.when, row.subText }, { "working 1m", "working 1m · initech-crm" })
  end,

  every_status_has_a_color = function()
    for _, status in ipairs({ "blocked", "done", "unknown", "idle", "working" }) do
      local color = attention.COLOR[status]
      h.eq(type(color), "table", status)
      h.eq(type(color.red) == "number" and type(color.green) == "number" and type(color.blue) == "number", true, status)
    end
  end,

  the_marks_have_three_colors_outside_the_status_colors = function()
    h.eq(#attention.MARK_COLORS, 3)
    h.eq(attention.MARK_COLORS[1], { red = 1.0, green = 0.22, blue = 0.37, alpha = 1 })
    h.eq(attention.COLOR.mark, nil)
    for _, mark in ipairs(attention.MARK_COLORS) do
      for status, color in pairs(attention.COLOR) do
        h.eq(mark == color, false, status)
      end
    end
  end,

  unknownStatuses_lists_each_status_herdr_added_once = function()
    local agents = {
      agent("w1:p1", "blocked"),
      agent("w2:p1", "waiting_input"),
      agent("w3:p1", "waiting_input"),
      agent("w4:p1", "paused"),
      agent("w5:p1", nil),
    }
    h.eq(attention.unknownStatuses(agents), { "paused", "waiting_input" })
  end,
  a_marked_idle_agent_ranks_between_done_and_unknown = function()
    local agents = {
      agent("w1:p1", "idle", { state_change_seq = 1 }),
      agent("w2:p1", "unknown", { state_change_seq = 2 }),
      agent("w3:p1", "done", { state_change_seq = 3, completion_seq = 3 }),
      agent("w4:p1", "idle", { state_change_seq = 4 }),
      agent("w5:p1", "done", { state_change_seq = 5, completion_seq = 5 }),
    }
    local marked = { ["w4:p1"] = { at = 100, clock = "10:00" }, ["w5:p1"] = { at = 90, clock = "09:50" } }
    -- w5 is seen, so it reads idle and its mark lifts it too.
    h.eq(panes(attention.rank(agents, { ["w5:p1"] = 5 }, "fifo", nil, marked)),
      { "w3:p1", "w5:p1", "w4:p1", "w2:p1", "w1:p1" })
  end,

  marked_idle_agents_sort_by_mark_time_not_by_state_change = function()
    local agents = {
      agent("w1:p1", "idle", { state_change_seq = 1 }),
      agent("w2:p1", "idle", { state_change_seq = 2 }),
    }
    local marked = { ["w1:p1"] = { at = 200, clock = "b" }, ["w2:p1"] = { at = 100, clock = "a" } }
    h.eq(panes(attention.rank(agents, {}, "fifo", nil, marked)), { "w2:p1", "w1:p1" })
    h.eq(panes(attention.rank(agents, {}, "lifo", nil, marked)), { "w1:p1", "w2:p1" })
  end,

  a_marked_agent_with_another_status_ranks_with_that_status = function()
    local agents = {
      agent("w1:p1", "working", { state_change_seq = 1 }),
      agent("w2:p1", "idle", { state_change_seq = 2 }),
    }
    local marked = { ["w1:p1"] = { at = 100, clock = "10:00" } }
    h.eq(panes(attention.rank(agents, {}, "fifo", nil, marked)), { "w2:p1", "w1:p1" })
  end,

  name_order_ignores_marks_between_different_titles = function()
    local agents = {
      agent("w1:p1", "idle", { terminal_title_stripped = "Beta" }),
      agent("w2:p1", "idle", { terminal_title_stripped = "Alpha" }),
    }
    local marked = { ["w1:p1"] = { at = 100, clock = "10:00" } }
    h.eq(panes(attention.rank(agents, {}, "name", nil, marked)), { "w2:p1", "w1:p1" })
  end,

  rows_of_marked_agents_keep_their_status_and_say_since_when_to_review = function()
    local agents = {
      agent("w1:p1", "idle", { state_change_seq = 1, cwd = "/srv/initech-reports" }),
      agent("w2:p1", "blocked", { state_change_seq = 2, cwd = "/srv/acme-api" }),
    }
    local times = { ["w1:p1"] = { age = "2h", clock = "09:00" }, ["w2:p1"] = { age = "4m", clock = "11:58" } }
    local marked = { ["w1:p1"] = { at = 100, clock = "10:02", color = 3 }, ["w2:p1"] = { at = 50, clock = "09:30", color = 1 } }
    local rows = attention.rows(agents, {}, "fifo", times, nil, nil, marked)
    h.eq({ rows[1].status, rows[1].markColor, rows[1].subText },
      { "blocked", 1, "blocked 4m · since 11:58 · to review since 09:30 · acme-api" })
    h.eq({ rows[2].status, rows[2].markColor, rows[2].subText },
      { "idle", 3, "idle 2h · to review since 10:02 · initech-reports" })
  end,

  rows_without_a_mark_have_no_mark_color = function()
    local agents = { agent("w1:p1", "idle", {}) }
    local row = attention.rows(agents, {}, "fifo", {}, nil, nil, {})[1]
    h.eq(row.markColor, nil)
  end,
}
