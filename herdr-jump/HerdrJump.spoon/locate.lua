-- Where the herdr binary is, which session a socket belongs to, and version checks. Pure:
-- Hammerspoon's PATH has none of the usual install folders, so the Spoon looks in each of them.

local M = {}

-- Homebrew (Apple silicon, Intel), Herdr's own installer, cargo, Nix (nix-darwin, home-manager,
-- profile), MacPorts and mise, in that order. Entries needing an unknown home or user are skipped.
function M.herdrCandidates(home, user)
  local dirs = { "/opt/homebrew/bin", "/usr/local/bin" }
  if home then
    dirs[#dirs + 1] = home .. "/.local/bin"
    dirs[#dirs + 1] = home .. "/.cargo/bin"
  end
  if user then
    dirs[#dirs + 1] = "/etc/profiles/per-user/" .. user .. "/bin"
  end
  dirs[#dirs + 1] = "/run/current-system/sw/bin"
  if home then
    dirs[#dirs + 1] = home .. "/.nix-profile/bin"
  end
  dirs[#dirs + 1] = "/opt/local/bin"
  if home then
    dirs[#dirs + 1] = home .. "/.local/share/mise/shims"
  end
  local candidates = {}
  for i, dir in ipairs(dirs) do
    candidates[i] = dir .. "/herdr"
  end
  return candidates
end

-- The herdr to run: the setting when it is a file, else the first candidate that is. Returns the
-- path, "setting" or "found", and a list holding the setting when it was missing; nil, nil and
-- every path tried when none is a file.
function M.herdr(setting, candidates, isFile)
  local missing = {}
  if setting then
    if isFile(setting) then
      return setting, "setting", missing
    end
    missing[1] = setting
  end
  for _, path in ipairs(candidates) do
    if isFile(path) then
      return path, "found", missing
    end
  end
  local tried = { table.unpack(missing) }
  for _, path in ipairs(candidates) do
    tried[#tried + 1] = path
  end
  return nil, nil, tried
end

-- The named session a socket path belongs to, nil for the default one.
function M.sessionOf(socketPath)
  return type(socketPath) == "string" and socketPath:match("/sessions/([^/]+)/herdr%.sock$") or nil
end

-- The x.y.z version in `herdr --version` output.
function M.version(output)
  return type(output) == "string" and output:match("(%d+%.%d+%.%d+)") or nil
end

local function parts(version)
  local list = {}
  for number in tostring(version):gmatch("%d+") do
    list[#list + 1] = tonumber(number)
  end
  return #list > 0 and list or nil
end

-- Whether a version is older than a minimum; nil when either is not a version.
function M.older(version, minimum)
  local a, b = parts(version), parts(minimum)
  if a == nil or b == nil then
    return nil
  end
  for i = 1, math.max(#a, #b) do
    local x, y = a[i] or 0, b[i] or 0
    if x ~= y then
      return x < y
    end
  end
  return false
end

return M
