# Antigravity test fixtures

This directory contains sanitized test fixtures derived from real runs and synthetic test cases for the Antigravity adapter.

## Real run captures (sanitized)

- `edit-turn.jsonl`: Derived from real call R1 (`agy -p` editing `main.tex`). All real paths are sanitized to `/work/project`, real conversation IDs replaced with fixed placeholder UUIDs, and account/system data removed. Payload tools list trimmed to representative subset.
- `search-turn.jsonl`: Derived from real call R2 (`agy -p` refusing shell command execution and running `list_dir`). Sanitized similarly to `edit-turn.jsonl`.

## Synthetic fixtures

The following fixtures are written by hand to test failure modes and edge cases not produced by normal successful runs:

- `synthetic-auth-failure.jsonl`: Simulates an authentication error with an `AGY_ERROR` message and failed result status.
- `synthetic-disallowed-tool.jsonl`: Simulates a turn attempting to invoke a disallowed tool (`run_command`), triggering the tool guard.
- `synthetic-missing-result.jsonl`: Simulates a process terminating or closing stdout before emitting a final `result` event.
- `synthetic-malformed-line.jsonl`: Contains 20 unparseable non-JSON lines to verify the malformed output threshold.
- `synthetic-error-result.jsonl`: Simulates a `result` event with `status: "ERROR"` and an error message.
