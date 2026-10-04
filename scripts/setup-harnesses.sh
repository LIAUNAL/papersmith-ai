#!/usr/bin/env bash
#
# setup-harnesses.sh — project the canonical `skills/` tree into every agent
# harness this repository supports.
#
# `skills/` at the repository root is the single source of truth. Each harness
# reads skills from its own convention directory, so this script links the
# canonical tree into each one. The links are relative and idempotent: re-running
# converges to the same layout without duplicating or nesting anything, and the
# checkout stays relocatable (an absolute link would keep pointing at wherever
# the checkout happened to live when the script last ran).
#
# Harnesses:
#   .claude/skills       Claude Code
#   .opencode/skills     OpenCode
#   .antigravity/skills  Google Antigravity
#
# Pi is deliberately absent. It discovers project skills through
# `.pi/settings.json`, whose `"../skills"` entry points at the canonical tree
# -- no symlink needed, which matters because `ln -sfn` is the one mechanism
# this repository never made portable and nothing tests on Windows. Pi dedupes
# skills by canonical path, so keeping the link as well would not have
# collided; it would have been a second mechanism for one job. See the
# workspace seed in `src/papersmith/core/init.py`.
#
# Usage:
#   npm run setup:harnesses
#   bash scripts/setup-harnesses.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANONICAL="$ROOT/skills"

if [[ ! -d "$CANONICAL" ]]; then
  echo "error: canonical skills directory not found at $CANONICAL" >&2
  exit 1
fi

# harness-relative skill directory -> human label (order preserved)
HARNESSES=(
  ".claude/skills:Claude Code"
  ".opencode/skills:OpenCode"
  ".antigravity/skills:Google Antigravity"
)

for entry in "${HARNESSES[@]}"; do
  rel="${entry%%:*}"
  label="${entry#*:}"
  target="$ROOT/$rel"

  mkdir -p "$(dirname "$target")"

  # Remove a prior link or a leftover real directory so `ln -sfn` can't nest
  # a symlink inside a stale directory.
  if [[ -e "$target" || -L "$target" ]]; then
    rm -rf "$target"
  fi

  # Relative link, computed rather than hardcoded so a harness nested deeper
  # than one level still resolves. python3 is already a hard repo dependency.
  link_target="$(python3 -c 'import os.path,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$CANONICAL" "$(dirname "$target")")"

  ln -sfn "$link_target" "$target"
  printf 'linked %-18s %s -> %s\n' "$label" "$rel" "$link_target"
done

echo "Harness skill projection complete."
