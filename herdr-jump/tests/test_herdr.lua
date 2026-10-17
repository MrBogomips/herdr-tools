local h = ...
local herdr = h.load("herdr")

local CONN = { bin = "/opt/homebrew/bin/herdr", socket = "/tmp/acme.sock" }

-- Replaces the herdr process run (Hammerspoon only) with a canned outcome and records the calls.
local function fakeRun(result, err, detail)
  local runs = {}
  herdr.run = function(conn, args, callback)
    runs[#runs + 1] = { conn = conn, args = args }
    callback(result, err, detail)
  end
  return runs
end

-- Calls fn(callback) and returns every argument the callback received.
local function capture(fn)
  local got
  fn(function(...) got = table.pack(...) end)
  return got
end

-- Stands in for hs.json.decode: the known payloads below, an error for anything else.
local DECODED = {
  LIST = { id = "cli:agent:list", result = { type = "agent_list", agents = {} } },
  FOCUSED = { id = "cli:agent:focus", result = { type = "agent_info" } },
  NOT_FOUND = { id = "cli:agent:focus", error = { code = "agent_not_found", message = "agent target zz:p9 not found" } },
  NO_SERVER = {
    id = "cli:agent:list",
    error = { code = "server_not_running", message = "no herdr server is running at /tmp/acme.sock; run `herdr` to start or attach it" },
  },
  NUMBER = 42,
}
local function decode(text)
  local value = DECODED[text]
  if value == nil then
    error("invalid JSON")
  end
  return value
end

return {
  listAgents_returns_the_listed_agents = function()
    local list = { { pane_id = "w1:p1", agent_status = "blocked" } }
    local runs = fakeRun({ type = "agent_list", agents = list }, nil)
    local got = capture(function(cb) herdr.listAgents(CONN, cb) end)
    h.eq({ got[1], got[2] }, { list, nil })
    h.eq(runs, { { conn = CONN, args = { "agent", "list" } } })
  end,

  listAgents_passes_on_a_failed_run = function()
    fakeRun(nil, "Herdr is not running")
    local got = capture(function(cb) herdr.listAgents(CONN, cb) end)
    h.eq({ got[1], got[2] }, { nil, "Herdr is not running" })
  end,

  listAgents_passes_on_the_details_of_a_failed_run_for_the_log = function()
    fakeRun(nil, "unexpected reply from Herdr", "exit 0: <html>")
    local got = capture(function(cb) herdr.listAgents(CONN, cb) end)
    h.eq({ got[1], got[2], got[3] }, { nil, "unexpected reply from Herdr", "exit 0: <html>" })
  end,

  listAgents_reports_how_many_malformed_agents_it_dropped = function()
    fakeRun({ type = "agent_list", agents = { { pane_id = "w1:p1" }, "junk" } }, nil)
    local got = capture(function(cb) herdr.listAgents(CONN, cb) end)
    h.eq({ got[1], got[2], got[3] }, { { { pane_id = "w1:p1" } }, nil, "dropped 1 malformed agent(s)" })
  end,

  listAgents_rejects_a_reply_that_is_not_an_agent_list = function()
    fakeRun({ type = "pane_info" }, nil)
    local got = capture(function(cb) herdr.listAgents(CONN, cb) end)
    h.eq({ got[1], got[2] }, { nil, "unexpected reply from Herdr" })
  end,

  focus_runs_agent_focus_on_the_pane_and_reports_success_as_nil = function()
    local runs = fakeRun({ type = "agent_info" }, nil)
    local got = capture(function(cb) herdr.focus(CONN, "wR:p1", cb) end)
    h.eq(got.n, 1)
    h.eq(got[1], nil)
    h.eq(runs, { { conn = CONN, args = { "agent", "focus", "wR:p1" } } })
  end,

  focus_reports_the_error_of_the_run = function()
    fakeRun(nil, "agent target wR:p1 not found (agent_not_found)")
    local got = capture(function(cb) herdr.focus(CONN, "wR:p1", cb) end)
    h.eq(got[1], "agent target wR:p1 not found (agent_not_found)")
  end,

  focus_never_runs_with_a_malformed_pane_id = function()
    local runs = fakeRun({ type = "agent_info" }, nil)
    for _, bad in ipairs({ "", "wR", 'wR:p1" , "x', "wR:p1 extra", "wR:p1\n", "--help:x", 42 }) do
      local got = capture(function(cb) herdr.focus(CONN, bad, cb) end)
      h.eq(type(got[1]), "string", "accepted " .. tostring(bad))
    end
    h.eq(runs, {})
  end,

  reply_returns_the_result_of_a_successful_run = function()
    h.eq({ herdr.reply(0, "LIST", "", decode) }, { { type = "agent_list", agents = {} } })
    h.eq({ herdr.reply(0, "FOCUSED", "", decode) }, { { type = "agent_info" } })
  end,

  -- herdr prints results on stdout and error envelopes on stderr.
  reply_reads_the_error_envelope_from_stderr = function()
    h.eq({ herdr.reply(1, "", "NOT_FOUND", decode) }, { nil, "agent target zz:p9 not found (agent_not_found)" })
  end,

  reply_also_reads_an_error_envelope_on_stdout = function()
    h.eq({ herdr.reply(1, "NOT_FOUND", "", decode) }, { nil, "agent target zz:p9 not found (agent_not_found)" })
  end,

  reply_says_plainly_that_herdr_is_not_running = function()
    h.eq({ herdr.reply(1, "", "NO_SERVER", decode) }, { nil, "Herdr is not running" })
  end,

  reply_keeps_both_outputs_for_the_log_when_neither_is_json = function()
    h.eq({ herdr.reply(0, "<html>", "", decode) }, { nil, "unexpected reply from Herdr", "exit 0: <html>" })
    h.eq({ herdr.reply(0, "NUMBER", nil, decode) }, { nil, "unexpected reply from Herdr", "exit 0: NUMBER" })
    h.eq(
      { herdr.reply(101, "", "thread main panicked", decode) },
      { nil, "herdr failed (exit 101)", "exit 101:  stderr: thread main panicked" }
    )
  end,

  reply_reports_a_failed_exit_without_an_error_envelope = function()
    h.eq({ herdr.reply(2, "", "", decode) }, { nil, "herdr failed (exit 2)", "exit 2: " })
    h.eq({ herdr.reply(2, "LIST", "", decode) }, { nil, "herdr failed (exit 2)", "exit 2: LIST" })
  end,

  parse_returns_the_result_of_a_reply = function()
    local result = herdr.parse({ id = "herdrjump", result = { type = "agent_list", agents = {} } })
    h.eq(result, { type = "agent_list", agents = {} })
  end,

  parse_turns_an_error_reply_into_its_message = function()
    local result, err = herdr.parse({
      id = "herdrjump",
      error = { code = "agent_not_found", message = "agent target zz:p9 not found" },
    })
    h.eq(result, nil)
    h.eq(err, "agent target zz:p9 not found (agent_not_found)")
  end,

  parse_keeps_an_error_without_message_or_given_as_text = function()
    h.eq({ herdr.parse({ id = "x", error = { code = "internal" } }) }, { nil, "Herdr error (internal)" })
    h.eq({ herdr.parse({ id = "x", error = { message = "socket busy" } }) }, { nil, "socket busy" })
    h.eq({ herdr.parse({ id = "x", error = "server shutting down" }) }, { nil, "server shutting down" })
  end,

  parse_rejects_anything_that_is_not_a_reply = function()
    for _, reply in ipairs({ "text", 7, {}, { id = "x" }, { error = 42 } }) do
      local result, err = herdr.parse(reply)
      h.eq(result, nil)
      h.eq(err, "unexpected reply from Herdr")
    end
    h.eq({ herdr.parse(nil) }, { nil, "unexpected reply from Herdr" })
  end,

  agents_reads_an_agent_list = function()
    local list = { { pane_id = "w1:p1", agent_status = "idle" } }
    h.eq(herdr.agents({ type = "agent_list", agents = list }), list)
    h.eq(herdr.agents({ type = "agent_list" }), {})
  end,

  agents_rejects_another_result_type = function()
    local agents, err = herdr.agents({ type = "pane_info" })
    h.eq(agents, nil)
    h.eq(err, "unexpected reply from Herdr")
  end,

  agents_rejects_a_list_that_is_not_a_table = function()
    h.eq({ herdr.agents({ type = "agent_list", agents = "none" }) }, { nil, "unexpected reply from Herdr" })
  end,

  agents_drops_malformed_entries_and_counts_them = function()
    local good = { pane_id = "wA:p2", agent_status = "done", completion_seq = 4, state_change_seq = 9 }
    local list = {
      good,
      "junk",
      { agent_status = "idle" },
      { pane_id = 'x" , "y' },
      { pane_id = "wB:p1", completion_seq = "7" },
      { pane_id = "wC:p1", state_change_seq = {} },
    }
    h.eq({ herdr.agents({ type = "agent_list", agents = list }) }, { { good }, nil, 5 })
  end,
}
