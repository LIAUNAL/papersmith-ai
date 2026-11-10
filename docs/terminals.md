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
console says so and shows a dismissible banner explaining the fix — open the
access link `smith ui` prints (it carries the one-time token that sets the
cookie). Starting `smith ui` with `--no-terminal` disables the terminal
entirely, for shared or headless machines.

## Tests

`tests/test_command_center_terminal.py` pins the launch argvs per platform,
the macOS `open(1)` path, the unauthorized-page behavior and the console's
activation affordances.

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
