#!/bin/sh
# Tests of install.sh, with a temporary HOME and stubs for every command that touches the system
# (uname, curl, open, brew, pgrep, killall, hs). The "download" is an archive of the working tree
# laid out like GitHub's: herdr-tools-main/herdr-jump/...
# Usage, from anywhere: sh herdr-jump/tests/test_install.sh
set -u

here=$(cd "$(dirname "$0")" && pwd)
script="$here/../install.sh"
root=$(mktemp -d "${TMPDIR:-/tmp}/herdr-jump-test.XXXXXX")
trap 'rm -rf "$root"' EXIT

tarball="$root/src.tar.gz"
mkdir -p "$root/stage/herdr-tools-main"
cp -R "$here/.." "$root/stage/herdr-tools-main/herdr-jump"
(cd "$root/stage" && tar -czf "$tarball" herdr-tools-main)

# --- stubs -----------------------------------------------------------------------------------
# Each stub appends its command line to $STUB_LOG; flag files in $STUB_STATE drive its answer.
# The bodies are written as they are, with their quotes, hence the single quotes.

# shellcheck disable=SC2016
stub() { # name, body, directory
  printf '#!/bin/sh\necho "%s $*" >> "$STUB_LOG"\n%s\n' "$1" "$2" > "$root/$3/$1"
  chmod +x "$root/$3/$1"
}

# shellcheck disable=SC2016
make_stubs() {
  mkdir -p "$root/bin" "$root/bin-brew" "$root/bin-hs"
  stub uname 'echo "$STUB_UNAME"' bin
  stub open 'case "$1" in -Ra) [ -e "$STUB_STATE/hammerspoon-installed" ] ;; *) exit 0 ;; esac' bin
  stub pgrep '[ -e "$STUB_STATE/hammerspoon-running" ]' bin
  stub killall 'exit 0' bin
  stub curl 'out=""; while [ $# -gt 0 ]; do [ "$1" = -o ] && out=$2; shift; done
[ -e "$STUB_STATE/download-fails" ] && exit 22
cp "$STUB_TARBALL" "$out"' bin
  # brew and hs fail when handed something on stdin: run from `curl | sh`, bash reads the script
  # from the pipe one line at a time, so a child that reads stdin eats the rest of the script
  # (the real hs runs what it reads as Lua).
  stub brew 'if read -r line; then exit 1; fi; touch "$STUB_STATE/hammerspoon-installed"' bin-brew
  stub hs 'if read -r line; then exit 65; fi; exit 0' bin-hs
}
make_stubs

# --- harness ---------------------------------------------------------------------------------

passed=0
failed=0
current=""
homes=0
# Knobs for the next run; run_install_keep resets them. PIPED=1 feeds the script to sh on
# stdin, as `curl | sh` does.
WITH_BREW=1
WITH_HS=0
STUB_UNAME=Darwin
PIPED=0

fail() {
  failed=$((failed + 1))
  printf 'FAIL %s: %s\n' "$current" "$1" >&2
}

# run_install_keep [options]: runs the script in the HOME the caller prepared.
run_install_keep() {
  export HOME
  STUB_STATE="$HOME/.stub"
  STUB_LOG="$STUB_STATE/log"
  mkdir -p "$STUB_STATE"
  : > "$STUB_LOG"
  path="$root/bin"
  [ "$WITH_BREW" = 1 ] && path="$path:$root/bin-brew"
  [ "$WITH_HS" = 1 ] && path="$path:$root/bin-hs"
  export STUB_STATE STUB_LOG STUB_UNAME
  STUB_TARBALL="$tarball"
  export STUB_TARBALL
  if [ "$PIPED" = 1 ]; then
    cat "$script" | PATH="$path:/usr/bin:/bin" sh -s -- "$@" > "$STUB_STATE/out" 2>&1
  else
    PATH="$path:/usr/bin:/bin" sh "$script" "$@" > "$STUB_STATE/out" 2>&1
  fi
  status=$?
  WITH_BREW=1
  WITH_HS=0
  STUB_UNAME=Darwin
  PIPED=0
}

# run_install [options]: a fresh, empty HOME, then the script.
run_install() {
  homes=$((homes + 1))
  HOME="$root/home-$homes"
  mkdir -p "$HOME"
  run_install_keep "$@"
}

# fresh_home: a new HOME for the caller to prepare before run_install_keep.
fresh_home() {
  homes=$((homes + 1))
  HOME="$root/home-$homes"
  mkdir -p "$HOME/.stub" "$HOME/.hammerspoon"
}

spoon() { echo "$HOME/.hammerspoon/Spoons/HerdrJump.spoon"; }
init() { echo "$HOME/.hammerspoon/init.lua"; }

assert_status() {
  [ "$status" = "$1" ] || fail "exit status $status, expected $1: $(cat "$STUB_STATE/out")"
}
assert_output() {
  grep -q -- "$1" "$STUB_STATE/out" || fail "output lacks '$1': $(cat "$STUB_STATE/out")"
}
assert_called() {
  grep -q -- "$1" "$STUB_LOG" || fail "no call matching '$1' in: $(cat "$STUB_LOG")"
}
assert_not_called() {
  grep -q -- "$1" "$STUB_LOG" && fail "unexpected call matching '$1' in: $(cat "$STUB_LOG")"
}
assert_same() {
  cmp -s "$1" "$2" || fail "$1 differs from $2"
}

test_case() {
  current=$1
  before=$failed
  "$1"
  [ "$failed" = "$before" ] && passed=$((passed + 1))
}

# --- tests -----------------------------------------------------------------------------------

a_fresh_mac_gets_hammerspoon_the_spoon_and_the_example_init() {
  run_install
  assert_status 0
  assert_called "brew install --cask hammerspoon"
  assert_same "$(spoon)/init.lua" "$here/../HerdrJump.spoon/init.lua"
  assert_same "$(init)" "$here/../init.example.lua"
  assert_called "open -a Hammerspoon"
  assert_output "⌃⌥⌘A"
}

an_installed_hammerspoon_is_not_installed_again() {
  fresh_home
  touch "$HOME/.stub/hammerspoon-installed"
  run_install_keep
  assert_status 0
  assert_not_called "brew"
}

without_homebrew_a_missing_hammerspoon_stops_with_the_download_link() {
  WITH_BREW=0
  run_install
  assert_status 1
  assert_output "hammerspoon.org"
  [ -e "$(spoon)" ] && fail "the Spoon was installed anyway"
}

an_existing_init_gets_the_three_lines_appended() {
  fresh_home
  printf -- '-- mine\nhs.alert.show("hi")\n' > "$(init)"
  run_install_keep
  assert_status 0
  head -n 2 "$(init)" > "$HOME/.stub/head"
  printf -- '-- mine\nhs.alert.show("hi")\n' | cmp -s - "$HOME/.stub/head" || fail "the original lines changed: $(cat "$(init)")"
  grep -q 'hs.loadSpoon("HerdrJump")' "$(init)" || fail "loadSpoon missing: $(cat "$(init)")"
  grep -q 'spoon.HerdrJump:bindHotkeys(spoon.HerdrJump.defaultHotkeys)' "$(init)" || fail "bindHotkeys missing"
  grep -q 'spoon.HerdrJump:start()' "$(init)" || fail "start missing"
}

an_init_that_already_loads_herdrjump_is_left_alone() {
  fresh_home
  printf 'hs.loadSpoon("HerdrJump")\nspoon.HerdrJump:start()\n' > "$(init)"
  cp "$(init)" "$HOME/.stub/before.lua"
  run_install_keep
  assert_status 0
  assert_same "$(init)" "$HOME/.stub/before.lua"
  assert_output "left as it is"
}

a_second_run_replaces_the_spoon_and_drops_stale_files() {
  fresh_home
  mkdir -p "$(spoon)"
  echo "old" > "$(spoon)/old.lua"
  run_install_keep
  assert_status 0
  [ -e "$(spoon)/old.lua" ] && fail "old.lua survived"
  assert_same "$(spoon)/attention.lua" "$here/../HerdrJump.spoon/attention.lua"
}

a_symlinked_spoon_is_refused_unless_forced() {
  fresh_home
  mkdir -p "$HOME/.hammerspoon/Spoons" "$HOME/checkout"
  ln -s "$HOME/checkout" "$(spoon)"
  run_install_keep
  assert_status 1
  assert_output "force"
  [ -L "$(spoon)" ] || fail "the link is gone"
  run_install_keep --force
  assert_status 0
  [ -L "$(spoon)" ] && fail "still a link"
  [ -d "$HOME/checkout" ] || fail "the link's target was removed"
  assert_same "$(spoon)/init.lua" "$here/../HerdrJump.spoon/init.lua"
}

a_running_hammerspoon_is_reloaded_through_hs_when_present() {
  fresh_home
  touch "$HOME/.stub/hammerspoon-running" "$HOME/.stub/hammerspoon-installed"
  WITH_HS=1
  run_install_keep
  assert_status 0
  assert_called "hs -c hs.reload()"
  assert_not_called "killall"
  assert_not_called "open -a"
}

a_running_hammerspoon_is_restarted_without_hs() {
  fresh_home
  touch "$HOME/.stub/hammerspoon-running" "$HOME/.stub/hammerspoon-installed"
  run_install_keep
  assert_status 0
  assert_called "killall Hammerspoon"
  assert_called "open -a Hammerspoon"
}

a_failed_download_changes_nothing() {
  fresh_home
  touch "$HOME/.stub/download-fails" "$HOME/.stub/hammerspoon-installed"
  run_install_keep
  assert_status 1
  assert_output "download failed"
  [ -e "$(spoon)" ] && fail "a Spoon appeared"
  [ -e "$(init)" ] && fail "an init.lua appeared"
}

ref_chooses_the_archive_to_download() {
  run_install
  assert_called "github.com/MrBogomips/herdr-tools/archive/main.tar.gz"
  run_install --ref herdr-jump-v0.2.0
  assert_status 0
  assert_called "github.com/MrBogomips/herdr-tools/archive/herdr-jump-v0.2.0.tar.gz"
}

another_system_is_refused() {
  STUB_UNAME=Linux
  run_install
  assert_status 1
  assert_output "macOS"
}

an_unknown_option_is_refused_with_a_hint() {
  run_install --bogus
  assert_status 1
  assert_output "help"
}

help_describes_the_options() {
  run_install --help
  assert_status 0
  assert_output "ref REF"
  assert_output "force"
}

piped_into_sh_the_whole_script_runs_even_when_brew_reads_stdin() {
  PIPED=1
  run_install
  assert_status 0
  assert_called "brew install --cask hammerspoon"
  assert_same "$(spoon)/init.lua" "$here/../HerdrJump.spoon/init.lua"
  assert_output "done:"
}

piped_into_sh_a_running_hammerspoon_is_still_reloaded_through_hs() {
  fresh_home
  touch "$HOME/.stub/hammerspoon-running" "$HOME/.stub/hammerspoon-installed"
  WITH_HS=1
  PIPED=1
  run_install_keep
  assert_status 0
  assert_called "hs -c hs.reload()"
  assert_not_called "killall"
  assert_output "done:"
}

for t in \
  a_fresh_mac_gets_hammerspoon_the_spoon_and_the_example_init \
  an_installed_hammerspoon_is_not_installed_again \
  without_homebrew_a_missing_hammerspoon_stops_with_the_download_link \
  an_existing_init_gets_the_three_lines_appended \
  an_init_that_already_loads_herdrjump_is_left_alone \
  a_second_run_replaces_the_spoon_and_drops_stale_files \
  a_symlinked_spoon_is_refused_unless_forced \
  a_running_hammerspoon_is_reloaded_through_hs_when_present \
  a_running_hammerspoon_is_restarted_without_hs \
  a_failed_download_changes_nothing \
  ref_chooses_the_archive_to_download \
  another_system_is_refused \
  an_unknown_option_is_refused_with_a_hint \
  help_describes_the_options \
  piped_into_sh_the_whole_script_runs_even_when_brew_reads_stdin \
  piped_into_sh_a_running_hammerspoon_is_still_reloaded_through_hs
do
  test_case "$t"
done

printf '%d passed, %d failed\n' "$passed" "$failed"
[ "$failed" = 0 ]
