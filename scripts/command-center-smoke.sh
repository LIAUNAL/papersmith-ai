#!/usr/bin/env bash
#
# Paper Command Center end-to-end smoke.
#
# Runs the dashboard backend the way a workspace runs it, then asserts the
# contract the frontend and the CLI depend on:
#
#   1. The server starts standalone with `python -m skills._core.command_center.server`
#      on a free port (9876 preferred).
#   2. It becomes live within 15 seconds.
#   3. `/api/state` carries `paper_metadata`, `sections`, `gates` and
#      `pipeline_stages`, and `/api/health/wiring` reports every core skill
#      WIRED.
#   4. Touching a section file produces a `state_update` SSE frame within 2
#      seconds on `/api/events`.
#   5. `POST /api/health/run-wiring-smoke` runs the workspace's own
#      `scripts/cli-paper-wiring-smoke.sh` and returns exit code 0.
#   6. Teardown kills the server and reports success only if every assertion
#      held.
#
# Hermetic apart from the local HTTP socket: no network, no npm.
#
# Interpreter: the first candidate that can import the server's runtime
# dependencies (fastapi, uvicorn), in this order: the canonical test runtime
# `.micromamba/envs/papersmith/bin/python` (the env `smith env` provisions and
# `npm run test:py` runs), the workspace `.venv/bin/python`, then `python3` and
# `python` on PATH. A candidate that exists but lacks those dependencies is
# skipped, never used; when none qualifies the smoke fails before starting
# anything and names every candidate it rejected. `--which-python` prints the
# selected interpreter and exits without running the smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() {
  echo "command-center smoke: FAIL (check $1): $2" >&2
  exit 1
}

# The repository's own environments first: the micromamba env `smith env`
# provisions, then a plain venv, and only then whatever python is on PATH.
select_python() {
  local candidate
  for candidate in "$ROOT/.micromamba/envs/papersmith/bin/python" "$ROOT/.venv/bin/python" \
      "$(command -v python3 || true)" "$(command -v python || true)"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if "$candidate" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
      PY="$candidate"
      return 0
    fi
    REJECTED="$REJECTED $candidate"
  done
  return 1
}

PY=""
REJECTED=""
select_python \
  || fail runtime "no interpreter can import fastapi and uvicorn; rejected:${REJECTED:- none found}"
if [[ "${1:-}" == "--which-python" ]]; then
  printf '%s\n' "$PY"
  exit 0
fi
HOST="127.0.0.1"
PREFERRED_PORT="${COMMAND_CENTER_PORT:-9876}"

STATE_JSON="$(mktemp)"
HEALTH_JSON="$(mktemp)"
SMOKE_JSON="$(mktemp)"
SSE_FILE="$(mktemp)"
SERVER_LOG="$(mktemp)"
SERVER_PID=""
SSE_PID=""

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  if [[ -n "$SSE_PID" ]]; then kill "$SSE_PID" 2>/dev/null || true; fi
  if [[ -n "$SERVER_PID" ]]; then kill "$SERVER_PID" 2>/dev/null || true; fi
  wait 2>/dev/null || true
  rm -f "$STATE_JSON" "$HEALTH_JSON" "$SMOKE_JSON" "$SSE_FILE" "$SERVER_LOG"
  if [[ "$rc" -eq 0 ]]; then
    echo "command-center smoke: ok"
  else
    echo "command-center smoke: FAIL (rc=$rc)" >&2
  fi
  exit "$rc"
}
trap cleanup EXIT INT TERM

# Pick a free port at or after the preferred one, so a busy 9876 on a dev
# machine does not fail the smoke.
PORT="$("$PY" - "$PREFERRED_PORT" <<'PYEOF'
import socket
import sys

start = int(sys.argv[1])
for port in range(start, start + 25):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        continue
    finally:
        sock.close()
    print(port)
    break
else:
    raise SystemExit(1)
PYEOF
)" || fail 1 "no free port at or after $PREFERRED_PORT"
BASE="http://$HOST:$PORT"

# Check 1: start the standalone backend from the workspace root.
cd "$ROOT"
"$PY" -m skills._core.command_center.server --port "$PORT" --no-browser --root "$ROOT" \
  >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

# Check 2: liveness, at most 15 seconds.
deadline=$((SECONDS + 15))
code=""
while [[ $SECONDS -lt $deadline ]]; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/state" 2>/dev/null || true)"
  [[ "$code" == "200" ]] && break
  sleep 0.25
done
if [[ "$code" != "200" ]]; then
  cat "$SERVER_LOG" >&2
  fail 2 "server did not answer /api/state with 200 within 15s"
fi

# Check 3: payload contract and core-skill wiring.
curl -s "$BASE/api/state" >"$STATE_JSON" || fail 3 "GET /api/state failed"
curl -s "$BASE/api/health/wiring" >"$HEALTH_JSON" || fail 3 "GET /api/health/wiring failed"
"$PY" - "$STATE_JSON" "$HEALTH_JSON" <<'PYEOF' || fail 3 "payload contract violated"
import json
import sys

state = json.load(open(sys.argv[1], encoding="utf-8"))
health = json.load(open(sys.argv[2], encoding="utf-8"))

for key in ("paper_metadata", "sections", "gates", "pipeline_stages"):
    if key not in state:
        raise SystemExit(f"missing /api/state key: {key}")
if not isinstance(state["gates"], list) or not state["gates"]:
    raise SystemExit("gates must be a non-empty list")
if not isinstance(state["pipeline_stages"], list) or not state["pipeline_stages"]:
    raise SystemExit("pipeline_stages must be a non-empty list")

core = {row["name"]: row["state"] for row in health.get("skills", []) if row.get("core")}
if not core:
    raise SystemExit("no core skills reported by /api/health/wiring")
unwired = {name: value for name, value in core.items() if value != "WIRED"}
if unwired:
    raise SystemExit(f"core skills not WIRED: {unwired}")
print(f"payload contract: ok ({len(core)} core skills wired)")
PYEOF

# Check 4: SSE reactivity within 2 seconds of a section touch, and the frame
# carries the wrapped `{type, payload}` envelope whose payload holds `state`
# and `changed` (the shape the dashboard hook unwraps).
curl -sN --max-time 8 "$BASE/api/events" >"$SSE_FILE" 2>/dev/null &
SSE_PID=$!
sleep 1
touch "$ROOT/sections/01-materials-and-methods.md"
sse_deadline=$((SECONDS + 2))
while [[ $SECONDS -lt $sse_deadline ]]; do
  grep -q '"type":"state_update"' "$SSE_FILE" && break
  sleep 0.1
done
grep -q '"type":"state_update"' "$SSE_FILE" \
  || fail 4 "no state_update SSE frame within 2s of touching a section"
"$PY" - "$SSE_FILE" <<'PYEOF' || fail 4 "state_update SSE frame has no wrapped payload"
import json
import sys

frames = []
for line in open(sys.argv[1], encoding="utf-8"):
    if not line.startswith("data:"):
        continue
    try:
        frames.append(json.loads(line[len("data:"):].strip()))
    except json.JSONDecodeError:
        continue

updates = [f for f in frames if isinstance(f, dict) and f.get("type") == "state_update"]
if not updates:
    raise SystemExit("no state_update frame parsed from the SSE body")
payload = updates[-1].get("payload")
if not isinstance(payload, dict):
    raise SystemExit("state_update frame carries no payload object")
if not isinstance(payload.get("state"), dict):
    raise SystemExit("state_update payload is missing the state object")
if not isinstance(payload.get("changed"), list):
    raise SystemExit("state_update payload is missing the changed list")
print("state_update SSE payload: ok")
PYEOF

# Check 5: the wiring smoke runner.
curl -s -X POST "$BASE/api/health/run-wiring-smoke" >"$SMOKE_JSON" \
  || fail 5 "POST /api/health/run-wiring-smoke failed"
"$PY" - "$SMOKE_JSON" <<'PYEOF' || fail 5 "wiring smoke runner did not pass"
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
if not result.get("available"):
    raise SystemExit(f"wiring smoke script unavailable: {result.get('detail')}")
if result.get("exit_code") != 0:
    tail = "\n".join((result.get("output") or "").splitlines()[-20:])
    raise SystemExit(f"wiring smoke exited {result.get('exit_code')}:\n{tail}")
if "wiring smoke: ok" not in (result.get("output") or ""):
    raise SystemExit("wiring smoke output did not report ok")
print("wiring smoke runner: ok")
PYEOF

# Check 6: teardown happens in the EXIT trap; reaching here means all passed.
exit 0
