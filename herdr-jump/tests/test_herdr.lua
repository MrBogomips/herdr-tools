local h = ...
local herdr = h.load("herdr")

-- Replaces the socket round trip (Hammerspoon only) with a canned reply and records the requests.
local function fakeCall(result, err, detail)
  local sent = {}
  herdr.call = function(socketPath, request, callback)
    sent[#sent + 1] = { socketPath = socketPath, request = request }
    callback(result, err, detail)
  end
  return sent
end

-- Calls fn(callback) and returns every argument the callback received.
local function capture(fn)
  local got
  fn(function(...) got = table.pack(...) end)
  return got
end

return {
  listAgents_returns_the_listed_agents = function()
    local list = { { pane_id = "w1:p1", agent_status = "blocked" } }
    local sent = fakeCall({ type = "agent_list", agents = list }, nil)
    local got = capture(function(cb) herdr.listAgents("/tmp/acme.sock", cb) end)
    h.eq({ got[1], got[2] }, { list, nil })
    h.eq(sent, { { socketPath = "/tmp/acme.sock", request = herdr.listRequest() } })
  end,

  listAgents_passes_on_a_failed_call = function()
    fakeCall(nil, "Herdr is not running")
    local got = capture(function(cb) herdr.listAgents("/tmp/acme.sock", cb) end)
    h.eq({ got[1], got[2] }, { nil, "Herdr is not running" })
  end,

  listAgents_passes_on_the_details_of_a_failed_call_for_the_log = function()
    fakeCall(nil, "unexpected reply from Herdr", "not JSON: <html>")
    local got = capture(function(cb) herdr.listAgents("/tmp/acme.sock", cb) end)
    h.eq({ got[1], got[2], got[3] }, { nil, "unexpected reply from Herdr", "not JSON: <html>" })
  end,

  listAgents_reports_how_many_malformed_agents_it_dropped = function()
    fakeCall({ type = "agent_list", agents = { { pane_id = "w1:p1" }, "junk" } }, nil)
    local got = capture(function(cb) herdr.listAgents("/tmp/acme.sock", cb) end)
    h.eq({ got[1], got[2], got[3] }, { { { pane_id = "w1:p1" } }, nil, "dropped 1 malformed agent(s)" })
  end,

  listAgents_rejects_a_reply_that_is_not_an_agent_list = function()
    fakeCall({ type = "pane_info" }, nil)
    local got = capture(function(cb) herdr.listAgents("/tmp/acme.sock", cb) end)
    h.eq({ got[1], got[2] }, { nil, "unexpected reply from Herdr" })
  end,

  focus_sends_the_pane_and_reports_success_as_nil = function()
    local sent = fakeCall({ type = "agent_info" }, nil)
    local got = capture(function(cb) herdr.focus("/tmp/acme.sock", "wR:p1", cb) end)
    h.eq(got.n, 1)
    h.eq(got[1], nil)
    h.eq(sent[1].request.params, { target = "wR:p1" })
  end,

  focus_reports_the_error_of_the_call = function()
    fakeCall(nil, "agent target wR:p1 not found (agent_not_found)")
    local got = capture(function(cb) herdr.focus("/tmp/acme.sock", "wR:p1", cb) end)
    h.eq(got[1], "agent target wR:p1 not found (agent_not_found)")
  end,

  focus_never_sends_a_malformed_pane_id = function()
    local sent = fakeCall({ type = "agent_info" }, nil)
    local got = capture(function(cb) herdr.focus("/tmp/acme.sock", 'x" , "y', cb) end)
    h.eq(sent, {})
    h.eq(type(got[1]), "string")
  end,

  list_request_asks_for_agent_list = function()
    h.eq(herdr.listRequest(), { id = "herdrjump", method = "agent.list", params = {} })
  end,

  focus_request_targets_the_pane = function()
    h.eq(herdr.focusRequest("wR:p1"), { id = "herdrjump", method = "agent.focus", params = { target = "wR:p1" } })
  end,

  focus_request_rejects_a_malformed_pane_id = function()
    for _, bad in ipairs({ "", "wR", 'wR:p1" , "x', "wR:p1 extra", "wR:p1\n", 42 }) do
      local request, err = herdr.focusRequest(bad)
      h.eq(request, nil, "accepted " .. tostring(bad))
      h.eq(type(err), "string")
    end
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
