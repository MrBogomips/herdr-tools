local h = ...
local since = h.load("since")

local function agent(pane, seq)
  return { pane_id = pane, agent_status = "idle", state_change_seq = seq }
end

-- 2026-10-21 (a Wednesday) at the given local time.
local function at(hour, min, day)
  return os.time({ year = 2026, month = 10, day = day or 21, hour = hour, min = min, sec = 0 })
end

return {
  update_stamps_a_new_pane_with_the_time_of_the_poll = function()
    h.eq(since.update({}, { agent("w1:p1", 7) }, 1000, true), { ["w1:p1"] = { seq = 7, at = 1000, approx = false } })
  end,

  update_keeps_the_time_while_the_state_change_counter_stays = function()
    local record = { ["w1:p1"] = { seq = 7, at = 1000, approx = false } }
    h.eq(since.update(record, { agent("w1:p1", 7) }, 1500, true), record)
  end,

  update_restamps_a_pane_whose_state_changed = function()
    local record = { ["w1:p1"] = { seq = 7, at = 1000, approx = false } }
    h.eq(since.update(record, { agent("w1:p1", 9) }, 1500, true), { ["w1:p1"] = { seq = 9, at = 1500, approx = false } })
  end,

  update_restamps_a_pane_whose_counter_went_backwards = function()
    -- Herdr restarted: its sequence numbers start over and pane ids are reused.
    local record = { ["w1:p1"] = { seq = 900, at = 1000, approx = false } }
    h.eq(since.update(record, { agent("w1:p1", 3) }, 1500, true), { ["w1:p1"] = { seq = 3, at = 1500, approx = false } })
  end,

  update_marks_changes_seen_after_a_gap_as_approximate = function()
    local record = { ["w1:p1"] = { seq = 7, at = 1000, approx = false } }
    local updated = since.update(record, { agent("w1:p1", 7), agent("w2:p1", 4) }, 1500, false)
    h.eq(updated, {
      ["w1:p1"] = { seq = 7, at = 1000, approx = false },
      ["w2:p1"] = { seq = 4, at = 1500, approx = true },
    })
  end,

  update_drops_closed_panes_and_panes_without_a_counter = function()
    local record = { ["w1:p1"] = { seq = 7, at = 1000, approx = false }, ["w9:p1"] = { seq = 2, at = 900, approx = false } }
    h.eq(since.update(record, { agent("w1:p1", 7), agent("w2:p1", nil) }, 1500, true), {
      ["w1:p1"] = { seq = 7, at = 1000, approx = false },
    })
  end,

  update_returns_a_new_table_and_leaves_the_old_one_alone = function()
    local record = { ["w1:p1"] = { seq = 7, at = 1000, approx = false } }
    since.update(record, { agent("w1:p1", 8) }, 1500, true)
    h.eq(record, { ["w1:p1"] = { seq = 7, at = 1000, approx = false } })
  end,

  same_compares_contents = function()
    local a = { ["w1:p1"] = { seq = 7, at = 1000, approx = false } }
    h.eq(since.same(a, { ["w1:p1"] = { seq = 7, at = 1000, approx = false } }), true)
    h.eq(since.same(a, { ["w1:p1"] = { seq = 7, at = 1001, approx = false } }), false)
    h.eq(since.same(a, { ["w1:p1"] = { seq = 7, at = 1000, approx = true } }), false)
    h.eq(since.same(a, {}), false)
    h.eq(since.same({}, a), false)
    h.eq(since.same({}, {}), true)
  end,

  valid_keeps_well_formed_entries_only = function()
    local stored = {
      ["w1:p1"] = { seq = 7, at = 1000, approx = true },
      ["w2:p1"] = { seq = 3, at = 900 },
      ["w3:p1"] = { seq = "7", at = 1000 },
      ["w4:p1"] = { seq = 7 },
      ["w5:p1"] = 12,
      [4] = { seq = 1, at = 1 },
    }
    h.eq(since.valid(stored), {
      ["w1:p1"] = { seq = 7, at = 1000, approx = true },
      ["w2:p1"] = { seq = 3, at = 900, approx = false },
    })
  end,

  valid_turns_anything_else_into_an_empty_record = function()
    h.eq(since.valid(nil), {})
    h.eq(since.valid("junk"), {})
  end,

  ago_rounds_down_to_minutes_hours_and_days = function()
    h.eq(since.ago(0), "<1m")
    h.eq(since.ago(59), "<1m")
    h.eq(since.ago(60), "1m")
    h.eq(since.ago(59 * 60 + 59), "59m")
    h.eq(since.ago(3600), "1h")
    h.eq(since.ago(3600 + 5 * 60), "1h 5m")
    h.eq(since.ago(23 * 3600 + 59 * 60), "23h 59m")
    h.eq(since.ago(86400), "1d")
    h.eq(since.ago(2 * 86400 + 3 * 3600 + 59 * 60), "2d 3h")
  end,

  ago_treats_a_clock_gone_backwards_as_now = function()
    h.eq(since.ago(-30), "<1m")
  end,

  ago_says_at_least_when_the_start_is_approximate = function()
    h.eq(since.ago(12 * 60, true), "≥12m")
    h.eq(since.ago(20, true), "≥0m")
  end,

  clock_shows_the_time_on_the_same_day = function()
    h.eq(since.clock(at(9, 41), at(10, 5)), "09:41")
  end,

  clock_adds_the_weekday_within_the_week = function()
    h.eq(since.clock(at(23, 5, 20), at(10, 5)), "Tue 23:05")
  end,

  clock_shows_the_date_further_back = function()
    h.eq(since.clock(at(8, 0, 3), at(10, 5)), "Oct 03")
  end,

  describe_says_each_pane_age_and_start = function()
    local now = at(9, 53)
    local record = {
      ["w1:p1"] = { seq = 5, at = at(9, 41), approx = false },
      ["w2:p1"] = { seq = 6, at = at(9, 49), approx = true },
    }
    h.eq(since.describe(record, now), {
      ["w1:p1"] = { age = "12m", clock = "09:41" },
      -- Approximate: it began at 09:49 or before, so it has lasted 4 minutes or more.
      ["w2:p1"] = { age = "≥4m", clock = "≤09:49" },
    })
  end,
}
