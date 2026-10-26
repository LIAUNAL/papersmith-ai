# Cross-platform and harness compatibility

Objective: make the current papersmith (main plus PR #135) behave alike on Linux, macOS and Windows under WSL, and keep Claude Code, OpenCode, Antigravity (`agy`) and Pi consistently wired and documented. Branch `fix/cross-platform-harness` from `feat/experiment-diagrams-doctor` (`0bf2dfd2`); delivery `single-pr` after #135. Runners: Python `.micromamba/envs/papersmith/bin/pytest` with `PYTHONPATH=<worktree>/src:<worktree>`, Node `node --test`.

## Specs

- **S1** "revisa que los cambios realizados, y el estado actual del proyecto paper smith, sea compatible con linux, mac, windows con wsl" — the defects found by the OS audit (L2) are fixed:
  - S1a: one TeX and rasterizer search order shared by `smith doctor`, `experiment-diagrams`, the dashboard's paper compile and its health inspector: PATH first, then the same fallback directories (macOS `/Library/TeX/texbin`, Homebrew, TeX Live `/usr/local/texlive/*/bin/*`, `/opt/texlive/*/bin/*`, `~/texlive/*/bin/*`, newest year first). A test fails when the copies drift.
  - S1b: `smith ui` opens the browser under WSL with `wslview`, then `explorer.exe`, before Python's `webbrowser`; with no graphical display on Linux it prints the URL instead of launching a text browser on the same terminal.
  - S1c: `.gitattributes` keeps LF endings for shell scripts and text files, so a clone made by Windows git into `/mnt/c` still runs `setup-harnesses.sh`.
  - S1d: the dashboard watcher polls when the workspace is on a Windows drive under WSL (`/mnt/<letter>/`), where file-change notifications do not arrive; `docs/wsl-dashboard.md` says to keep the workspace in the Linux filesystem and names the symlink and `localhostForwarding` requirements.
- **S2** "y con agentes claude code, opencode, antigravity agy, y pi" — the harness audit's defects (L2) are fixed:
  - S2a: `docs/cli.md` no longer claims `smith mcp print-config` emits OpenCode's format; it points OpenCode users to the `docs/mcp.md` snippet.
  - S2b: `docs/mcp.md`, `docs/harness-support-matrix.md` and the `core/init.py` comment list the three MCP servers init writes (`banco-lia`, `kaggle`, `colab`).
  - S2c: `docs/mcp.md` has a Pi (`.pi/mcp.json`) snippet for the papersmith MCP server.
  - S2d: the header bullets of `CLAUDE.md`, `OPENCODE.md`, `.agents/AGENTS.md` and `.pi/APPEND_SYSTEM.md` agree (release procedure, repository maintenance, domain-guidelines note).
- **S3** "aplica los cambios requeridos y comit, mergea y push".

## Tasks

| ID | Specs | Route | Status | Evidence |
|---|---|---|---|---|
| T1 | S1a-S1d | delegated (writer; parallel with T2, disjoint surfaces) | pending | |
| T2 | S2a-S2d | inline (docs and guides only) | pending | |
| T3 | S3 | inline (CI, merge after #135, push, QMLEEG upgrade) | pending | |

## Log

- **L1** (2026-10-26) User request, verbatim: "despues de correr y mergear, revisa que los cambios realizados, y el estado actual del proyecto paper smith, sea compatible con linux, mac, windows con wsl, y con agentes claude code, opencode, antigravity agy, y pi, aplica los cambios requeridos y comit, mergea y push"
- **L2** Two read-only audits on `0bf2dfd2`. OS: no macOS-only command and nothing that crashes on Linux; defects: `server._compile_paper` prepends only macOS TeX dirs (`server.py:475`); `health_inspector.py:463` searches PATH only; three disagreeing fallback lists (`doctor.py:49`, `diagram_cli.py:54-66,502` oldest-year-first, `raster.py`/`paper_latex.py:122` PATH only); `open_browser` (`server.py:2614-2628`) tries `explorer.exe` only after `webbrowser.open` returns False, and `xdg-open` returns True; a text browser can take the `smith ui` terminal; no `.gitattributes`. Advisories: watcher without polling on `/mnt/c` (`watcher.py:198`); CI is Ubuntu-only without TeX. Harness: the new skill is projected for all four harnesses in the repo and in a `smith init` workspace (183 focused tests pass, `sync-repo-harness --check` clean); defects are documentation drift (`docs/cli.md:810`, `docs/mcp.md:30-31`, `docs/harness-support-matrix.md:122`, `core/init.py:164`, no Pi snippet, guide headers). Not changed here (pre-existing design, reported to the user): Claude Code prefers `.claude/skills/<name>` over `.claude/commands/<name>.md`, so the command files are shadowed; OpenCode and Pi read the same skill through several links.
