# The support terminal: platforms, agents and activation

The dashboard's floating CLI console (`skills/_core/command_center/`) runs the
workspace's agents on a pseudo-terminal and streams them over Server-Sent
Events. This page records what each platform supports and how the console is
activated. The security posture is fixed: the terminal is offered on a
loopback bind, and on a network bind only when `smith ui` is started with
`--network-terminal` (see [On a network bind](#on-a-network-bind---network-terminal));
either way a browser page only gets sessions after it holds the cookie the
login URL sets (see [wsl-dashboard.md](wsl-dashboard.md) for the WSL variant of
the same flow).

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
entirely, for shared or headless machines. On a network bind the page never
activates itself (below).

## On a network bind (`--network-terminal`)

`smith ui --lan` (or `PAPERSMITH_UI_LAN=1`) sets all of this up in one switch:
the network bind, this machine's own addresses and names for the `Host`
check, and a login secret kept in `~/.config/papersmith/terminal-token`,
printed once when it is created. See
[cli.md](cli.md) (*One switch for your home network*).

A non-loopback `--host` does not offer the terminal, not even with
`--allow-unauthenticated-network`: the console shows "Terminal disabled", and
every terminal and API-key route answers 404. Adding `--network-terminal`
offers both behind a secret, for example
`smith ui --host 0.0.0.0 --allow-unauthenticated-network --allowed-host 192.168.1.10:8080 --network-terminal`:

- **The login secret.** Generated at each start and printed once, in the start
  banner, inside one login URL per address a browser may use (the bind address
  unless it is a wildcard, then each `--allowed-host`). With
  `--terminal-token-file <path>` it is read from that file instead and never
  printed. The file follows the API keys' rule: a regular file you own, not a
  symlink, mode `600`, in a directory that is not a symlink, holding 32 to 256
  characters from `A-Z a-z 0-9 . _ ~ -`, for example
  `(umask 077; python -c 'import secrets; print(secrets.token_urlsafe(32))' > ~/.config/papersmith/terminal-token)`.
  Any other file, or `--network-terminal` beside `--no-terminal` or on a
  loopback `--host`, stops the server with exit code 2: the terminal is never
  half configured.
- **The one-time login.** Opening `/api/terminal/login?token=<secret>` once in
  each browser trades the secret for the session cookie (`papersmith_terminal`:
  HttpOnly, SameSite=Strict, `Path=/api/terminal`) and redirects to the
  dashboard. The cookie holds a second random secret, new at each start, so the
  login secret is never stored in a browser or sent again, and a cookie dies
  with its server. The page never activates itself (`POST
  /api/terminal/activate` answers 403), and the browser `smith ui` opens gets
  the plain dashboard URL, never the secret.
- **Every route checks it.** Every terminal route (sessions, input and resize,
  the SSE stream, tools, the external launch, both tutors) and every API-key
  route answers 403 without the cookie, comparing secrets with
  `hmac.compare_digest`. `GET /api/terminal/agents` and
  `GET /api/terminal/office` still answer an unauthorized page, without any
  agent or session data. The SSE stream's URL holds no secret: it travels as
  the cookie.
- **Same origin.** The `Host` allow-list still answers 421 to anything but the
  bind address and `--allowed-host`, and the request guards stay. A
  state-changing request (POST, PUT, DELETE) must also carry this server's
  `Origin`: over plain HTTP to a network address browsers send no
  `Sec-Fetch-Site`, so the origin is what refuses a cross-site request.
- **Never logged.** uvicorn's logs show the login URL as `token=[REDACTED]`
  (the access log, and the ASGI trace of `--log-level trace`, on a loopback
  bind too), and no response carries the login secret.

The rest of the dashboard stays unauthenticated, which is why
`--allow-unauthenticated-network` is still required. Plain HTTP carries the
secret, the cookie and every keystroke unencrypted, and the login URL stays in
each browser's history: on a network you do not trust, keep the loopback bind
and forward the port (`ssh -L 8080:127.0.0.1:8080 <server>`).

## Tests

`tests/test_command_center_terminal.py` pins the launch argvs per platform,
the macOS `open(1)` path, the unauthorized-page behavior, the activation
endpoint and the console's activation affordances;
`tests/test_command_center_cli_activation.py` runs the real `cli-console.js`
in node through the click → activate → session flow.
`tests/test_command_center_network_terminal.py` pins the network bind: the
terminal off without the opt-in, a 403 on every terminal and key route
without the cookie, the login exchange, the `Origin` rule, the token file's
rule, the start banner and a real uvicorn access log without the secret.

## The Agents Office panel

The dashboard's **Agents Office** tab is a 3D office in the style of weherd
(amalvarezme/weherd): the same library, three.js 0.183.0, vendored under
`static/vendor/three/` and mapped by an import map, with no addons, no build
step and no network. `static/office3d.js` ports weherd's procedural office:
an orthographic isometric camera, the cream floor, walls with windows, desks
with monitor and mug, procedural people and the coffee counter. Its lounge is
the **Engram memory core**: a floating brain on a pedestal with one orbiting
cube per observed memory interaction.

Desks are grouped into **tramo zones** (the agent's stretch of the pipeline,
in pipeline order), each with a colored floor and a sign; shirts take the
zone color, each desk carries an object for the agent's role (magnifier for
auditors and reviewers, books for tutors, pens for writers, a globe for
scouts, a chart for figures, a server for data, a toolbox for builders), and
people have rounded bodies, faces that blink and several hair styles.

Built to stay sharp and fluid without a GPU (software WebGL): every static
piece is baked into one vertex-colored mesh (the room and its desks, and the
parts of each limb), so the scene is a few hundred draws; the measured frame
rate picks a quality tier (pixel ratio 2 with shadows, 1.5, then 1 with a
soft disc under each person) and only steps down. Names, states, zone signs
and bubbles are HTML tags over the canvas, sized in rem, so the dashboard's
text-size control (A ×1 … ×2) scales them. On a software-rendered 1440×900
window the office runs at about 33 fps (it was 16 before baking).

The camera follows the activity (the orchestrator, the active agents and,
when memory is in use, the brain) until the operator drags to pan, wheels to
zoom at the cursor, or clicks an agent (the camera flies to it); **Follow
activity** and **Fit all** reframe.

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
| working | the agent's invocation at the start of a line (`● sota-scout(…)`, `Task(sota-scout: …)`, `subagent_type: "sota-scout"`; prose that only names an agent does not count) with no completion marker (`⎿ Done (…)`) after it; completions close agents in launch order | seated, typing, a scrolling code screen, a lit arc from the orchestrator with data pulses along it |
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

Changes between two measured snapshots are drawn as events. A task given
(an agent goes from available to working: the orchestrator invoked it) sends
a document along an arc from the orchestrator's desk with the bubble
"Orchestrator → agent"; a task done (working → available) sends it back with
"✓ done"; each Engram interaction flashes the brain and its tag. The
**Events** strip lists the last 8 with their time: tasks given and done, the
orchestrator session opening and closing, and every Engram interaction the
server observed (with the time the server measured it; the first snapshot
contributes only these).

The state is served at `GET /api/terminal/office`: under `/api/terminal/`
because the terminal cookie is scoped to that path (the older
`/api/office/state` still answers, but a browser never sends the cookie
there, so it always reads as unauthorized). The roster shows to every page;
the activity only to a page authorized for the terminal, otherwise every
agent is available and the status line says why.
`tests/test_command_center_office.py` pins the detection rules, the roster,
the authorization, the route, the panel helpers (run in node) and the
vendored, hash-pinned three.js.
