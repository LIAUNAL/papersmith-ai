# Codex fixtures: documentation-derived

The `codex` command is not installed on the machine these were written on, so none of these files is a capture of a
real run. Each one is written by hand from the event types the OpenAI Codex documentation lists for `codex exec --json`
(`thread.started`, `turn.started`, `turn.completed` with `usage`, `turn.failed`, `item.started` and `item.completed`
with an `item` that has an `id`, a `type` and, for commands, `command` and `status`, agent messages with `text`, and
`error`). The page says it does not document every field, so the fields beyond those are the shape the open-source
client uses and are unverified against a real run. Every id and path is a placeholder.

The file names start with `documented-` on purpose: when a real capture is available it replaces these, and it is
named after what it shows, not with this prefix.
