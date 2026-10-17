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

  rank_puts_the_latest_state_change_first_within_a_status = function()
    local agents = {
      agent("w1:p1", "done", { state_change_seq = 7, completion_seq = 7 }),
      agent("w2:p1", "done", { state_change_seq = 9, completion_seq = 9 }),
      agent("w3:p1", "done", { state_change_seq = 8, completion_seq = 8 }),
    }
    h.eq(panes(attention.rank(agents, {})), { "w2:p1", "w3:p1", "w1:p1" })
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
    h.eq(panes(attention.rank(agents, {})), { "w4:p1", "w2:p1", "w3:p1", "w1:p1" })
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
    h.eq(panes(attention.rank(agents, seen)), { "w1:p1", "w2:p1" })
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

  rows_show_glyph_title_status_and_folder_in_rank_order = function()
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
      { text = "⏸ ACME-API-Fixing-Auth", subText = "blocked · acme-api", paneId = "w2:p3", status = "blocked" },
      { text = "· GLOBEX-ETL-Reviewing-Loader", subText = "idle · globex-etl", paneId = "w1:p1", status = "idle" },
    })
  end,

  rows_fall_back_to_the_raw_title_then_the_folder_then_the_pane = function()
    local agents = {
      agent("w1:p1", "working", { state_change_seq = 3, terminal_title_stripped = "", terminal_title = "◐ Initech" }),
      agent("w2:p1", "working", { state_change_seq = 2, cwd = "/srv/lumon/" }),
      agent("w3:p1", "working", { state_change_seq = 1 }),
    }
    local texts = {}
    for i, row in ipairs(attention.rows(agents, {})) do
      texts[i] = row.text .. " | " .. row.subText
    end
    h.eq(texts, { "◐ ◐ Initech | working", "◐ lumon | working · lumon", "◐ w3:p1 | working" })
  end,

  rows_show_a_seen_done_agent_as_idle = function()
    local agents = { agent("w1:p1", "done", { completion_seq = 4, terminal_title_stripped = "ACME" }) }
    local row = attention.rows(agents, { ["w1:p1"] = 4 })[1]
    h.eq({ row.text, row.status }, { "· ACME", "idle" })
  end,

  menu_lists_one_entry_per_row_with_the_folder_as_tooltip = function()
    local rows = {
      { text = "⏸ ACME", subText = "blocked · acme-api", paneId = "w2:p3", status = "blocked" },
      { text = "· Lumon", subText = "idle", paneId = "w1:p1", status = "idle" },
    }
    h.eq(attention.menu(rows, nil), {
      { title = "⏸ ACME", tooltip = "blocked · acme-api", paneId = "w2:p3" },
      { title = "· Lumon", tooltip = "idle", paneId = "w1:p1" },
    })
  end,

  menu_says_when_there_is_no_agent = function()
    h.eq(attention.menu({}, nil), { { title = "No Herdr agents", disabled = true } })
  end,

  menu_shows_the_error_instead_of_stale_rows = function()
    local rows = { { text = "· Lumon", subText = "idle", paneId = "w1:p1", status = "idle" } }
    h.eq(attention.menu(rows, "Herdr is not running"), { { title = "Herdr is not running", disabled = true } })
  end,

  menubar_title_shows_the_count_only_when_something_waits = function()
    h.eq(attention.title(0), "⧗")
    h.eq(attention.title(2), "⧗ 2")
    h.eq(attention.title(nil), "⧗")
  end,
}
