-- Talks to the Herdr server over its Unix socket: newline-delimited JSON, one request per
-- connection (the server closes it after replying). No herdr process is spawned.
-- The request and reply helpers are pure; call() needs Hammerspoon.

local M = {}

local ID = "herdrjump"
local UNEXPECTED = "unexpected reply from Herdr"
-- Pane ids look like "wR:p1": letters, digits, "_" or "-" on both sides of the colon.
local PANE_ID = "^[%w_%-]+:[%w_%-]+$"

function M.listRequest()
  return { id = ID, method = "agent.list", params = {} }
end

function M.focusRequest(paneId)
  if type(paneId) ~= "string" or not paneId:match(PANE_ID) then
    return nil, "not a Herdr pane id: " .. tostring(paneId)
  end
  return { id = ID, method = "agent.focus", params = { target = paneId } }
end

local function text(value)
  return type(value) == "string" and value ~= "" and value or nil
end

-- The message of an error reply: {message, code}, either one alone, or plain text.
local function errorMessage(err)
  if type(err) == "string" then
    return text(err)
  end
  if type(err) ~= "table" then
    return nil
  end
  local message, code = text(err.message), text(err.code)
  if message and code then
    return ("%s (%s)"):format(message, code)
  end
  return message or (code and ("Herdr error (%s)"):format(code))
end

-- The result of a decoded reply, or nil and a message for the user.
function M.parse(reply)
  if type(reply) ~= "table" then
    return nil, UNEXPECTED
  end
  if reply.error ~= nil then
    return nil, errorMessage(reply.error) or UNEXPECTED
  end
  if type(reply.result) ~= "table" then
    return nil, UNEXPECTED
  end
  return reply.result
end

local function optionalNumber(value)
  return value == nil or type(value) == "number"
end

-- An agent HerdrJump can rank and jump to: a well-formed pane id and numeric sequences.
local function wellFormed(agent)
  return type(agent) == "table"
    and type(agent.pane_id) == "string"
    and agent.pane_id:match(PANE_ID) ~= nil
    and optionalNumber(agent.completion_seq)
    and optionalNumber(agent.state_change_seq)
end

-- The agents of an agent_list result, without malformed entries; also returns how many were dropped.
function M.agents(result)
  if type(result) ~= "table" or result.type ~= "agent_list" then
    return nil, UNEXPECTED
  end
  if result.agents == nil then
    return {}, nil, 0
  end
  if type(result.agents) ~= "table" then
    return nil, UNEXPECTED
  end
  local agents, dropped = {}, 0
  for _, agent in ipairs(result.agents) do
    if wellFormed(agent) then
      agents[#agents + 1] = agent
    else
      dropped = dropped + 1
    end
  end
  return agents, nil, dropped
end

-- The socket and timer of each live call, by call number. This table is their only owner: the
-- callbacks capture the number, never the objects. Hammerspoon holds callbacks strongly until the
-- object is collected, so a callback that captured its own socket or timer would keep it alive
-- forever, and a poll every few seconds would leak one of each per poll.
local inFlight = {}
local lastCall = 0

-- Sends one request and calls callback(result, err, detail) exactly once; detail is for the log.
function M.call(socketPath, request, callback, timeoutSeconds)
  local attributes = hs.fs.attributes(socketPath)
  if attributes == nil or attributes.mode ~= "socket" then
    callback(nil, "Herdr is not running", "no socket at " .. socketPath)
    return
  end
  lastCall = lastCall + 1
  local id = lastCall
  local function finish(result, err, detail)
    local live = inFlight[id]
    if live == nil then
      return
    end
    inFlight[id] = nil
    live.timer:stop()
    live.socket:disconnect()
    callback(result, err, detail)
  end
  local socket = hs.socket.new(function(data)
    local ok, reply = pcall(hs.json.decode, data)
    if not ok then
      finish(nil, UNEXPECTED, "not JSON: " .. tostring(data):sub(1, 200))
      return
    end
    local result, err = M.parse(reply)
    finish(result, err, err == UNEXPECTED and ("reply: " .. tostring(data):sub(1, 200)) or nil)
  end)
  local timer = hs.timer.doAfter(timeoutSeconds or 2, function()
    -- A stale socket file left by a crashed server refuses the connection.
    if inFlight[id] and inFlight[id].connected then
      finish(nil, "Herdr is not answering", "no reply to " .. request.method)
    else
      finish(nil, "cannot connect to Herdr", "connection to " .. socketPath .. " refused or stuck")
    end
  end)
  inFlight[id] = { socket = socket, timer = timer, connected = false }
  local line = hs.json.encode(request) .. "\n"
  socket:connect(socketPath, function()
    local live = inFlight[id]
    if live then
      live.connected = true
      live.socket:write(line)
      live.socket:read("\n")
    end
  end)
end

-- callback(agents, err, detail): detail is for the log (what went wrong, what was dropped).
function M.listAgents(socketPath, callback)
  M.call(socketPath, M.listRequest(), function(result, err, detail)
    if err then
      callback(nil, err, detail)
      return
    end
    local agents, invalid, dropped = M.agents(result)
    if invalid then
      callback(nil, invalid)
      return
    end
    callback(agents, nil, dropped > 0 and ("dropped %d malformed agent(s)"):format(dropped) or nil)
  end)
end

-- callback(err): nil on success.
function M.focus(socketPath, paneId, callback)
  local request, invalid = M.focusRequest(paneId)
  if not request then
    callback(invalid)
    return
  end
  M.call(socketPath, request, function(_, err)
    callback(err)
  end)
end

return M
