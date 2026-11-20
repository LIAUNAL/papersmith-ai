# Pi test fixtures

Every fixture here is synthetic: written by hand from the event shapes Pi 1.4.0 documents in `docs/json.md` and
`docs/message-types.md` of its package, not captured from a real run. No real turn was run while building the Pi
adapter, so none of them holds a path, id or account data from a real machine. The project root is `/work/project` and
the session id is the fixed placeholder `00000000-0000-4000-8000-000000000001`.

- `synthetic-edit-turn.jsonl`: a whole turn. Pi reads `main.tex`, edits it, then answers in two text deltas, with the
  session header first and `agent_settled` last.
- `synthetic-disallowed-tool.jsonl`: the model calls `bash`, which the runner's guard must stop at `toolcall_start`.
- `synthetic-rate-limit.jsonl`: every attempt fails with a 429, Pi retries twice and ends with
  `auto_retry_end{success:false}`, then exits 0.
- `synthetic-failed-response.jsonl`: one response with `stopReason: "error"`, no retry, and exit 0.
- `synthetic-retry-success.jsonl`: an overloaded first attempt, then a retry that answers.
- `synthetic-missing-settled.jsonl`: the stream stops in the middle of an answer.
- `synthetic-malformed-line.jsonl`: 20 lines that are not JSON, enough to reach the malformed-output limit.
