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

-- The result of a decoded reply, or nil and a message for the user.
function M.parse(reply)
  if type(reply) ~= "table" then
    return nil, UNEXPECTED
  end
  if type(reply.error) == "table" then
    return nil, ("%s (%s)"):format(tostring(reply.error.message), tostring(reply.error.code))
  end
  if type(reply.result) ~= "table" then
    return nil, UNEXPECTED
  end
  return reply.result
end

function M.agents(result)
  if type(result) ~= "table" or result.type ~= "agent_list" then
    return nil, UNEXPECTED
  end
  return result.agents or {}
end

-- The socket and timer of each live call, by call number. This table is their only owner: the
-- callbacks capture the number, never the objects. Hammerspoon holds callbacks strongly until the
-- object is collected, so a callback that captured its own socket or timer would keep it alive
-- forever, and a poll every few seconds would leak one of each per poll.
local inFlight = {}
local lastCall = 0

-- Sends one request and calls callback(result, err) exactly once.
function M.call(socketPath, request, callback, timeoutSeconds)
  if not hs.fs.attributes(socketPath) then
    callback(nil, "Herdr is not running")
    return
  end
  lastCall = lastCall + 1
  local id = lastCall
  local function finish(result, err)
    local live = inFlight[id]
    if live == nil then
      return
    end
    inFlight[id] = nil
    live.timer:stop()
    live.socket:disconnect()
    callback(result, err)
  end
  local socket = hs.socket.new(function(data)
    local ok, reply = pcall(hs.json.decode, data)
    if not ok then
      finish(nil, UNEXPECTED)
      return
    end
    finish(M.parse(reply))
  end)
  local timer = hs.timer.doAfter(timeoutSeconds or 2, function()
    finish(nil, "Herdr is not answering")
  end)
  inFlight[id] = { socket = socket, timer = timer }
  local line = hs.json.encode(request) .. "\n"
  socket:connect(socketPath, function()
    local live = inFlight[id]
    if live then
      live.socket:write(line)
      live.socket:read("\n")
    end
  end)
end

-- callback(agents, err)
function M.listAgents(socketPath, callback)
  M.call(socketPath, M.listRequest(), function(result, err)
    if err then
      callback(nil, err)
      return
    end
    callback(M.agents(result))
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
