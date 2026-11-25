# Antigravity real-call evidence (block resolved)

The first R1 attempt exited 2 before any model request, because `-p` took `--output-format` as its prompt. On 2026-10-31 the user authorized replacement calls with Gemini 3.8 Flash. R1, R2 and R3 then ran once each with agy 1.4.12. No further real `agy -p` call is authorized.

Raw captures, never to be committed: `~/.cache/caztor-tools/agy-evidence/r{1,2,3}.jsonl`. Derive sanitized fixtures from them per T5.

## Working argv

```text
agy --output-format stream-json --mode accept-edits --agent caztor --model gemini-3.8-flash-medium --print-timeout 180s -p='<prompt>'
```

Options come first and the prompt is attached to `-p`. Add `--conversation <id>` before `-p` to continue. Stdin was `/dev/null`. A prompt beginning with `-` was not tested.

## Results

| Call | Exit | Observed |
|---|---|---|
| R1 edit | 0 | `main.tex` changed from cat to dog. `--agent caztor` resolved. Only `view_file` and `replace_file_content` ran. |
| R2 shell | 0 | No `run_command` step. The model ran `list_dir`, said it cannot execute shell commands, and created no file. |
| R3 continuation | 0 | Same conversation id. It answered that it changed "cat" to "dog". |

## Stream contract

Each line has an `event` key: `init`, `step_update` or `result`.

- `init`: `conversation_id`, `init.{model,cwd,agent,tools,permission_mode}`. `permission_mode` was `request-review` although `--mode accept-edits` was passed.
- `step_update.step_update`: `conversation_id`, `step_index`, `state` (`ACTIVE`, `DONE`), `step_type`, and optionally `duration_seconds`, `usage`, `text_delta`, `tool_name`, `tool_info`.
- `step_type` values seen: `user_input`, `agent_response`, `tool`, `system_message`. `system_message` is not in the documented list and appeared in R3. Ignore unknown types.
- Text arrives in `text_delta` on `agent_response` steps, split at arbitrary points, including inside words and paths. A DONE step can carry a final `"\n"` delta. An `agent_response` step can have no text at all.
- Tool steps emit ACTIVE then DONE with the same `step_index`. `tool_info.parameters` carries `AbsolutePath`, `TargetFile` or `DirectoryPath`. `tool_info.output` is optional.
- `result.result`: `conversation_id`, `status` (`SUCCESS`), `response`, `duration_seconds`, `num_turns`, `usage`. On a continued conversation `usage` and `num_turns` are cumulative, and `step_index` continues from the previous turn.
- `usage`: `input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_tokens`, `total_tokens`. No thinking text was emitted.
- Response text contains `file://` links with absolute paths.

## Design changes required

1. **Do not abort on `init.tools`.** It listed 60 tools, including `run_command`, even though the definition allows six. The planned "Guard at start" test would abort every turn. The guard must act on `tool` steps only: abort on any `tool_name` outside the allowlist, on an MCP-like name, or on a missing name.
2. **Do not claim `commandExecutionPolicy: off` is enforced by the CLI.** R2 shows that the model did not try a shell tool. It does not show that the CLI would block one, and `run_command` stays listed. The disclosure must say the guard limits damage only after a disallowed tool step has started.
3. **Treat `~/.gemini` as written by every turn.** Each turn updates conversation state and transcripts under `~/.gemini/antigravity-cli/`, including the user's prompts. The partial-isolation notice must mention it.

## Still unobserved

Auth failure shape, `AGY_ERROR`, a disallowed tool step, a failed `result` and malformed output. Their fixtures stay synthetic and labelled as such.
