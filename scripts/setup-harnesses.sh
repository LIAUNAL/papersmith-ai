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
# the checkout happened to live when the script last ran). Only symlinks are
# replaced: a real directory or file at a harness path is user-owned, so it is
# left intact, reported, and the script exits non-zero.
#
# Harnesses:
#   .claude/skills       Claude Code
#   .pi/skills           Pi
#   .opencode/skills     OpenCode
#   .agents/skills       Google Antigravity (skills invoked as /name)
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
  ".pi/skills:Pi"
  ".opencode/skills:OpenCode"
  ".agents/skills:Antigravity"
)

skipped=0
for entry in "${HARNESSES[@]}"; do
  rel="${entry%%:*}"
  label="${entry#*:}"
  target="$ROOT/$rel"

  mkdir -p "$(dirname "$target")"

  # Only a symlink is this script's own projection, so only a symlink is
  # replaced. Anything else at the harness path is user-owned: leave it intact
  # and report it instead of deleting it. An empty directory holds nothing to
  # lose and is cleared so `ln -sfn` cannot nest a link inside it.
  if [[ -L "$target" ]]; then
    rm -f "$target"
  elif [[ -d "$target" ]] && rmdir "$target" 2>/dev/null; then
    :
  elif [[ -e "$target" ]]; then
    printf 'skipped %-17s %s is not a symlink; move its contents into skills/ or elsewhere, remove it, and re-run\n' "$label" "$rel" >&2
    skipped=$((skipped + 1))
    continue
  fi

  # Relative link, computed rather than hardcoded so a harness nested deeper
  # than one level still resolves. python3 is already a hard repo dependency.
  link_target="$(python3 -c 'import os.path,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$CANONICAL" "$(dirname "$target")")"

  ln -sfn "$link_target" "$target"
  printf 'linked %-18s %s -> %s\n' "$label" "$rel" "$link_target"
done

if (( skipped > 0 )); then
  echo "error: $skipped harness path(s) left untouched because they hold user-owned content." >&2
  exit 1
fi
echo "Harness skill projection complete."
