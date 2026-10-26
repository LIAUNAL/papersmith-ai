# Open the dashboard from Windows with Ubuntu on WSL

## Keep the workspace in the Linux filesystem

Create and run the workspace under your Linux home (`~/papers/<name>`), not
on a Windows drive (`/mnt/c/...`):

- **Live updates.** Changes made on `/mnt/c` from Windows raise no Linux file
  notification. When the workspace is on `/mnt/<letter>/`, the dashboard
  falls back to polling, which works but costs CPU and reacts more slowly.
- **Symlinks.** `smith init` and `npm run setup:harnesses` project skills
  into the harness directories (`.claude/skills`, `.pi/skills`, ...) as
  symlinks. On `/mnt/c` they work only with Windows **Developer Mode**
  enabled (Settings → System → For developers); without it the projections
  fail or become plain files.
- **Line endings.** The repository's `.gitattributes` keeps shell scripts at
  LF, so a clone made by Windows git still runs `setup-harnesses.sh`; cloning
  from Ubuntu avoids the question entirely.

From Windows, the Linux files are under `\\wsl$\Ubuntu\home\<user>\` in
Explorer and in editors with WSL support.

## Start the dashboard

In Ubuntu, start the dashboard from an initialized workspace:

```sh
smith ui .
```

`smith ui` opens the browser itself:

1. `wslview <url>` (from the `wslu` package), which opens the Windows default
   browser;
2. otherwise `explorer.exe <url>`, through Windows interop;
3. otherwise, on a WSLg desktop (`DISPLAY` or `WAYLAND_DISPLAY` set), Python's
   own browser lookup;
4. otherwise it prints the URL; paste it into a Windows browser.

It never starts a text browser in the terminal that runs the server. A
launch failure does not stop the HTTP server. `--no-browser` skips automatic
opening altogether. If the support terminal is enabled, use the **login URL
printed by the command** rather than the bare root URL to activate its
cookie; keep that URL private because it contains a per-server secret. To
avoid issuing a terminal login URL, start with
`smith ui . --no-browser --no-terminal` and open `http://localhost:8080/`.

If Windows does not open automatically, check that Windows interop is
enabled and that `command -v wslview` or `command -v explorer.exe` finds a
launcher (`sudo apt install wslu` provides `wslview`).

## When the Windows browser cannot reach 127.0.0.1

With the default loopback bind, WSL2 forwards `localhost` to Windows. If the
browser cannot reach `http://localhost:8080/`, enable the forwarding in
`%UserProfile%\.wslconfig` and restart WSL (`wsl --shutdown` from Windows):

```ini
[wsl2]
localhostForwarding=true
```

Keep the Ubuntu process running while you use the dashboard. Do not expose
the server on another interface to work around forwarding: the dashboard has
no authentication.
