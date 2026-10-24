-- Runs every test file with plain Lua (5.4 or newer), no dependencies.
-- Usage, from anywhere: lua herdr-jump/tests/run.lua
-- A test file receives the helpers module as its chunk argument and returns a table of
-- test name -> function; a test fails by raising an error.

local here = (arg and arg[0] or ""):match("^(.*)/[^/]*$") or "."
local helpers = dofile(here .. "/helpers.lua")

local FILES = {
  "test_attention", "test_diagnostics", "test_herdr", "test_icon", "test_locate", "test_picker", "test_procs",
  "test_since", "test_terminal",
}

local passed, failed = 0, 0
for _, file in ipairs(FILES) do
  local cases = assert(loadfile(here .. "/" .. file .. ".lua"))(helpers)
  local names = {}
  for name in pairs(cases) do
    names[#names + 1] = name
  end
  table.sort(names)
  for _, name in ipairs(names) do
    local ok, err = xpcall(cases[name], debug.traceback)
    if ok then
      passed = passed + 1
    else
      failed = failed + 1
      io.stderr:write(("FAIL %s: %s\n%s\n\n"):format(file, name, err))
    end
  end
end

print(("%d passed, %d failed"):format(passed, failed))
os.exit(failed == 0 and 0 or 1)
