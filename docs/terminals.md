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

The dashboard's **Agents Office** tab (`static/office-panel.js`) draws a 2.5D
vanilla-canvas view of the same facts: the orchestrator's desk, one desk per
smith agent with its role, model (or `not measured` — nothing invents one),
and live status dot, animated flow lines for working agents, and a
**grand-brain memory area** that glows while Engram interactions
(`mem_*`/`engram` command lines) are observed in live session output.
Clicking a desk opens a read-only card with the agent's role, model and
current task — the phase run this browser tracks, else its session state —
and can open the existing CLI console on that agent. The panel never closes,
interrupts or writes to a session; a disabled terminal or an unauthorized
page says so instead of drawing fiction. The state comes from
`GET /api/office/state` (`skills/_core/command_center/office.py`), which
answers under the same authorization semantics as the terminal.
`tests/test_command_center_office.py` pins the measured-state contract, the
route wiring and the panel's vanilla-canvas surface.
