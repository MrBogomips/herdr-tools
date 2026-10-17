#!/bin/sh
# Installs or updates HerdrJump, the Hammerspoon Spoon of herdr-jump, straight from GitHub.
#
#   curl -fsSL https://raw.githubusercontent.com/MrBogomips/herdr-tools/main/herdr-jump/install.sh | sh
#
# Safe to run again: the Spoon is replaced, init.lua is kept. See README.md.
set -eu

REPO="${HERDR_JUMP_REPO:-MrBogomips/herdr-tools}"
REF=main
FORCE=0
SPOONS="$HOME/.hammerspoon/Spoons"
SPOON="$SPOONS/HerdrJump.spoon"
INIT="$HOME/.hammerspoon/init.lua"

usage() {
  cat <<EOF
Usage: install.sh [--ref REF] [--force]

Installs or updates HerdrJump, the Hammerspoon Spoon of herdr-jump, from GitHub:
  - installs Hammerspoon with Homebrew when it is missing
  - copies HerdrJump.spoon into ~/.hammerspoon/Spoons, replacing the previous copy
  - creates ~/.hammerspoon/init.lua from init.example.lua, or appends the HerdrJump lines to yours
  - reloads Hammerspoon, or starts it

Options:
  --ref REF   branch or tag of $REPO to install (default: main)
  --force     replace a HerdrJump.spoon that is a symbolic link (a development checkout)
  --help      this text
EOF
}

say() {
  printf 'herdr-jump: %s\n' "$*"
}

fail() {
  printf 'herdr-jump: %s\n' "$*" >&2
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --ref)
      [ $# -ge 2 ] || fail "--ref needs a branch or tag (try --help)"
      REF=$2
      shift 2
      ;;
    --ref=*)
      REF=${1#--ref=}
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option '$1' (try --help)"
      ;;
  esac
done

[ "$(uname -s)" = Darwin ] || fail "HerdrJump runs in Hammerspoon, on macOS only"
command -v curl > /dev/null 2>&1 || fail "curl is required"
command -v tar > /dev/null 2>&1 || fail "tar is required"

if open -Ra Hammerspoon > /dev/null 2>&1; then
  say "Hammerspoon is installed"
else
  command -v brew > /dev/null 2>&1 \
    || fail "Hammerspoon is not installed and Homebrew is missing: install it from https://www.hammerspoon.org, then run this again"
  say "installing Hammerspoon with Homebrew"
  brew install --cask hammerspoon
fi

if [ -L "$SPOON" ] && [ "$FORCE" = 0 ]; then
  fail "$SPOON is a symbolic link (a development checkout?): remove it, or pass --force to replace it"
fi

tmp=$(mktemp -d "${TMPDIR:-/tmp}/herdr-jump.XXXXXX")
trap 'rm -rf "$tmp"' EXIT

url="https://github.com/$REPO/archive/$REF.tar.gz"
say "downloading $url"
curl -fsSL "$url" -o "$tmp/src.tar.gz" || fail "download failed: $url"
mkdir "$tmp/src"
tar -xzf "$tmp/src.tar.gz" -C "$tmp/src"
src=$(find "$tmp/src" -type d -name HerdrJump.spoon -path '*/herdr-jump/*' | head -n 1)
[ -n "$src" ] && [ -f "$src/init.lua" ] || fail "no herdr-jump/HerdrJump.spoon in $url"
example="$(dirname "$src")/init.example.lua"
[ -f "$example" ] || fail "no herdr-jump/init.example.lua in $url"

mkdir -p "$SPOONS"
rm -rf "$SPOON.new"
cp -R "$src" "$SPOON.new"
rm -rf "$SPOON"
mv "$SPOON.new" "$SPOON"
say "installed $SPOON"

if [ ! -f "$INIT" ]; then
  cp "$example" "$INIT"
  say "created $INIT from init.example.lua"
elif grep -q HerdrJump "$INIT"; then
  say "$INIT already loads HerdrJump, left as it is"
else
  cat >> "$INIT" <<'EOF'

-- HerdrJump, added by install.sh
hs.loadSpoon("HerdrJump")
spoon.HerdrJump:bindHotkeys(spoon.HerdrJump.defaultHotkeys)
spoon.HerdrJump:start()
EOF
  say "added HerdrJump to $INIT"
fi

if pgrep -xq Hammerspoon; then
  if command -v hs > /dev/null 2>&1 && hs -c 'return 1' > /dev/null 2>&1; then
    # The command line loses its connection while Hammerspoon reloads and exits non-zero.
    hs -c 'hs.reload()' > /dev/null 2>&1 || true
    say "reloaded Hammerspoon"
  else
    say "restarting Hammerspoon"
    killall Hammerspoon
    sleep 1
    open -a Hammerspoon
  fi
else
  say "starting Hammerspoon"
  open -a Hammerspoon
fi

say "done: ⌃⌥⌘I goes back to iTerm, ⌃⌥⌘A opens the agents picker"
say "macOS asks for Accessibility when Hammerspoon first starts, and for Automation of iTerm2 on the first jump"
