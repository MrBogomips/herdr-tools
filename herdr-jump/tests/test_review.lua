local h = ...
local review = h.load("review")

local function agent(pane, status, completion)
  return { pane_id = pane, agent_status = status, completion_seq = completion }
end

local function copy(t)
  local out = {}
  for k, v in pairs(t) do
    out[k] = type(v) == "table" and copy(v) or v
  end
  return out
end

return {
  markable_statuses_are_done_and_idle = function()
    h.eq(review.markable("done"), true)
    h.eq(review.markable("idle"), true)
    for _, status in ipairs({ "blocked", "working", "unknown" }) do
      h.eq(review.markable(status), false, status)
    end
  end,

  toggle_marks_an_idle_agent_with_the_time_and_its_completion_counter = function()
    local marks, seen = review.toggle({}, {}, agent("w1:p1", "idle", 7), "idle", 1000)
    h.eq(marks, { ["w1:p1"] = { at = 1000, completion = 7 } })
    h.eq(seen, {})
  end,

  toggle_on_a_done_agent_not_seen_also_marks_it_seen = function()
    local marks, seen = review.toggle({}, { ["w2:p1"] = 3 }, agent("w1:p1", "done", 9), "done", 1000)
    h.eq(marks, { ["w1:p1"] = { at = 1000, completion = 9 } })
    h.eq(seen, { ["w1:p1"] = 9, ["w2:p1"] = 3 })
  end,

  toggle_on_a_marked_agent_removes_the_mark_whatever_its_status = function()
    local before = { ["w1:p1"] = { at = 5, completion = 7 }, ["w2:p1"] = { at = 6, completion = 1 } }
    local marks = review.toggle(before, {}, agent("w1:p1", "working", 8), "working", 1000)
    h.eq(marks, { ["w2:p1"] = { at = 6, completion = 1 } })
  end,

  toggle_on_an_agent_that_cannot_be_marked_changes_nothing = function()
    for _, status in ipairs({ "working", "blocked", "unknown" }) do
      local marks, seen = review.toggle({}, { x = 1 }, agent("w1:p1", status, 4), status, 1000)
      h.eq(marks, {}, status)
      h.eq(seen, { x = 1 }, status)
    end
  end,

  toggle_never_changes_its_inputs = function()
    local marks = { ["w1:p1"] = { at = 5, completion = 7 } }
    local seen = { ["w1:p1"] = 2 }
    local marksBefore, seenBefore = copy(marks), copy(seen)
    review.toggle(marks, seen, agent("w2:p1", "done", 9), "done", 1000)
    review.toggle(marks, seen, agent("w1:p1", "idle", 7), "idle", 1000)
    h.eq(marks, marksBefore)
    h.eq(seen, seenBefore)
  end,

  prune_keeps_listed_panes_whose_counter_did_not_go_back = function()
    local marks = {
      ["gone"] = { at = 1, completion = 1 },
      ["no-counter"] = { at = 1, completion = 1 },
      ["restarted"] = { at = 1, completion = 9 },
      ["same"] = { at = 2, completion = 4 },
      ["grew"] = { at = 3, completion = 4 },
    }
    local agents = {
      agent("no-counter", "idle", nil), agent("restarted", "idle", 2),
      agent("same", "idle", 4), agent("grew", "working", 6), agent("unmarked", "idle", 1),
    }
    h.eq(review.prune(marks, agents), {
      same = { at = 2, completion = 4 }, grew = { at = 3, completion = 4 },
    })
    h.eq(marks.gone, { at = 1, completion = 1 }, "input untouched")
  end,

  valid_keeps_well_formed_entries_and_says_when_it_dropped_some = function()
    local marks, malformed = review.valid({ a = { at = 1, completion = 2 } })
    h.eq(marks, { a = { at = 1, completion = 2 } })
    h.eq(malformed, false)
    marks, malformed = review.valid({ a = { at = 1, completion = 2 }, b = { at = "x", completion = 1 }, c = 3, d = {} })
    h.eq(marks, { a = { at = 1, completion = 2 } })
    h.eq(malformed, true)
    marks, malformed = review.valid("junk")
    h.eq(marks, {})
    h.eq(malformed, true)
    marks, malformed = review.valid(nil)
    h.eq(marks, {})
    h.eq(malformed, false)
  end,

  same_compares_marks_by_value = function()
    h.eq(review.same({ a = { at = 1, completion = 2 } }, { a = { at = 1, completion = 2 } }), true)
    h.eq(review.same({ a = { at = 1, completion = 2 } }, { a = { at = 1, completion = 3 } }), false)
    h.eq(review.same({ a = { at = 1, completion = 2 } }, {}), false)
    h.eq(review.same({}, { a = { at = 1, completion = 2 } }), false)
  end,

  describe_gives_each_mark_its_time_and_clock = function()
    local clock = function(at, now) return ("%d@%d"):format(at, now) end
    h.eq(review.describe({ a = { at = 10, completion = 2 } }, 99, clock), { a = { at = 10, clock = "10@99" } })
  end,
}
