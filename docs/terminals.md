# The support terminal: platforms, agents and activation

The dashboard's floating CLI console (`skills/_core/command_center/`) runs the
workspace's agents on a pseudo-terminal and streams them over Server-Sent
Events. This page records what each platform supports and how the console is
activated. The security posture is fixed: the terminal is only offered on a
loopback bind, and a browser page only gets sessions after it holds the cookie
the login URL sets (see [wsl-dashboard.md](wsl-dashboard.md) for the WSL
variant of the same flow).

## Agents

The agent picker offers every agent `smith` knows: `herdr`, `claude`,
`opencode`, `pi`, `antigravity` and a plain login `shell`. Only agents found
on `PATH` are selectable; the choice is remembered per browser and changing
it restarts the session. Each phase console offers the same picker for its
own runs.

## External terminal launch (the launch button)

The console's launch button opens the project in `herdr` inside an external
terminal emulator. What `smith` probes, in preference order:

| Platform | Terminals probed | Launch mechanism |
| --- | --- | --- |
| macOS | Ghostty (`.app` or `PATH`), WezTerm (`.app` or `PATH`) | `open -na Ghostty --args …` / `wezterm start` |
| Linux and other POSIX | Ghostty, WezTerm, GNOME Terminal, Konsole, `x-terminal-emulator` (in that order) | direct `Popen` of the emulator with a working-directory flag; `x-terminal-emulator` wraps the command in `/bin/sh -c 'cd … && exec …'` |

`/api/terminal/tools` reports the probed result: `preferred_terminal` names
the emulator that would launch, and `missing` lists what is absent (`herdr`,
or a generic `terminal emulator` outside macOS). The button's label follows
the probed emulator.

## Activation

A page that is served by `smith ui` but holds no login cookie is *not*
authorized: the agent list comes back empty and sessions are refused. The
console says so and shows a dismissible banner with an **Activate** button.
This happens with a tab left open from an earlier `smith ui`, a bookmark, or a
`localhost` page when the server runs on `127.0.0.1` (the cookie belongs to one
host).

The page activates itself on a click — the CLI button, a phase run, or
**Activate** — never on load: it sends `POST /api/terminal/activate`
(same-origin, at most once every 10 s), and the server opens its login URL in
the desktop browser. The URL is built from the loopback socket the server
listens on, never from the request's `Host` (another local user could listen
on `[::1]:PORT` beside an IPv4-only server), and the token goes to the browser
through the OS only, never back to the caller. The login sets the cookie for
that address, so the tab that asked becomes authorized too; it polls for the
cookie (up to 45 s) and then opens the agent session. A tab reached under
another name (`localhost` for a `127.0.0.1` server) cannot share that cookie:
the console names the address where the activated dashboard opened. When the server cannot
open a browser (a headless Linux server, a dashboard reached through an SSH
tunnel), it prints the link on its console instead, and the page says to open
it from there. Starting `smith ui` with `--no-terminal` disables the terminal
entirely, for shared or headless machines.

## Tests

`tests/test_command_center_terminal.py` pins the launch argvs per platform,
the macOS `open(1)` path, the unauthorized-page behavior, the activation
endpoint and the console's activation affordances;
`tests/test_command_center_cli_activation.py` runs the real `cli-console.js`
in node through the click → activate → session flow.

## The Agents Office panel

The dashboard's **Agents Office** tab is a 3D office in the style of weherd
(amalvarezme/weherd): the same library, three.js 0.183.0, vendored under
`static/vendor/three/` and mapped by an import map, with no addons, no build
step and no network. `static/office3d.js` ports weherd's procedural office:
an orthographic isometric camera, the cream floor, walls with windows, desks
with monitor and mug, box-built people and the coffee counter. Its lounge is
the **Engram memory core**: a floating brain on a pedestal with one orbiting
cube per observed memory interaction.

Who is in the office:

- **One desk per agent defined in smith**: every `.claude/agents/*.md` of
  the workspace, read through `agents_view.get_agents_view` (29 today). The
  card shows the role, the model (`model:` frontmatter, else "inherits the
  orchestrator's model"), the stretch, the phases and the current task.
- **The orchestrator** at the front desk with three monitors: the main CLI
  session (claude, opencode, pi, …) that runs the skills and calls the
  agents. The CLI programs are not desks; the card names the CLIs where the
  orchestrator runs. Without a live agent CLI session its chair is empty.

Each person shows one state, measured by `office.py` from the output tail of
the live CLI sessions (each line read up to 400 characters, so any output scans in linear time), never invented:

| State | Measured from | Mechanic |
|---|---|---|
| working | the agent's invocation at the start of a line (`● sota-scout(…)`, `Task(sota-scout: …)`, `subagent_type: "sota-scout"`; prose that only names an agent does not count) with no completion marker (`⎿ Done (…)`) after it; completions close agents in launch order | seated, typing, bright screen with scrolling lines, flow line from the orchestrator |
| saving | an Engram write printed as a tool call at the start of a line (`mem_save`, `mem_update`, `mem_session_summary`, `engram save`, …) while that agent runs, for 8 s | stands by the desk facing the brain, lime cubes stream desk → brain |
| loading | an Engram read (`mem_search`, `mem_context`, `mem_get_observation`, `engram search`, …) while that agent runs, for 8 s | same pose, teal cubes stream brain → desk |
| available | none of the above | seated, leaning back with a coffee cup, dim screen |

An Engram call belongs to the transcript entry it is printed in: nested
under an agent's entry (`⎿`) it is that agent's, a top-level entry (`●`) is
the orchestrator's, and text in the input prompt (`❯`) is the operator's
typing, never a call. Claude Code repaints only the cells that change, using
cursor moves instead of newlines, so the office keeps a small screen model
per session (`office.Screen`, bounded, fed only the output written since the
last poll) and counts a call when a new call row appears on that screen; a
repaint adds no row. Who is running is read from the output history, where
Claude Code closes background agents with `● Agent "…" finished`.

Claude Code folds MCP calls into `Called engram` without the tool name. The
direction of a folded call is measured from the Engram store,
`engram stats --all` (its observation count only, run only around a call):
a save when the count grew, a read otherwise. A save that updates an
existing memory (same title or topic) does not grow the count, so it shows
as a read. Without Engram on `PATH` the direction stays unknown (violet).
In smith, every agent definition lists its own tools and none includes
Engram, so the agents never read or write Engram themselves: the
orchestrator does, and the office shows it at the orchestrator's desk. What
a session showed before the office first read it is history, not activity. The
agents of a phase this browser is running (its phase runs) get a soft ring.
Clicking a person opens a read-only card; "Open console" only opens the CLI
console. The panel never closes, interrupts or writes to a session.

The state is served at `GET /api/terminal/office`: under `/api/terminal/`
because the terminal cookie is scoped to that path (the older
`/api/office/state` still answers, but a browser never sends the cookie
there, so it always reads as unauthorized). The roster shows to every page;
the activity only to a page authorized for the terminal, otherwise every
agent is available and the status line says why.
`tests/test_command_center_office.py` pins the detection rules, the roster,
the authorization, the route, the panel helpers (run in node) and the
vendored, hash-pinned three.js.
