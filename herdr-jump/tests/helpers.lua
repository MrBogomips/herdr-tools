-- Assertions and module loading shared by the test files.

local M = {}

local here = debug.getinfo(1, "S").source:match("^@(.*)/[^/]*$") or "."

-- Loads a Spoon module the way init.lua does: by file, not through package.path.
function M.load(name)
  return dofile(here .. "/../HerdrJump.spoon/" .. name .. ".lua")
end

local function show(value)
  if type(value) ~= "table" then
    return type(value) == "string" and ("%q"):format(value) or tostring(value)
  end
  local keys = {}
  for k in pairs(value) do
    keys[#keys + 1] = k
  end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  local parts = {}
  for _, k in ipairs(keys) do
    parts[#parts + 1] = tostring(k) .. "=" .. show(value[k])
  end
  return "{" .. table.concat(parts, ", ") .. "}"
end

local function same(a, b)
  if type(a) ~= "table" or type(b) ~= "table" then
    return a == b
  end
  for k, v in pairs(a) do
    if not same(v, b[k]) then return false end
  end
  for k in pairs(b) do
    if a[k] == nil then return false end
  end
  return true
end

-- Deep equality with both values printed on failure.
function M.eq(actual, expected, label)
  if not same(actual, expected) then
    error(("%s\n  expected: %s\n  actual:   %s"):format(label or "values differ", show(expected), show(actual)), 2)
  end
end

return M
