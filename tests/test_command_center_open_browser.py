"""`smith ui` opens the dashboard in a browser that fits the platform.

Under WSL it hands the URL to Windows (`wslview`, then `explorer.exe`); on a
Linux without a graphical display it prints the URL instead of letting
Python's `webbrowser` start a text browser on the server's terminal; macOS
keeps `webbrowser`. A missing launcher never raises. Nothing is launched:
`shutil.which`, `subprocess.Popen` and `webbrowser.open` are replaced.
"""
from __future__ import annotations

import contextlib
import io
import os
import unittest
import webbrowser
from unittest import mock

from skills._core.command_center import server

URL = "http://127.0.0.1:8765/"


class OpenBrowserTests(unittest.TestCase):
    def _run(self, *, platform: str, wsl: bool, env: dict[str, str],
             tools: dict[str, str], popen_error: Exception | None = None):
        launched: list[list[str]] = []
        opened: list[str] = []

        def fake_popen(argv, **_kwargs):
            if popen_error is not None:
                raise popen_error
            launched.append(list(argv))
            return mock.Mock()

        def fake_open(url, *args, **kwargs):
            opened.append(url)
            return True

        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(server.sys, "platform", platform), \
                mock.patch.object(server, "_is_wsl", lambda: wsl), \
                mock.patch.object(server.shutil, "which", lambda name: tools.get(name)), \
                mock.patch.object(server.subprocess, "Popen", fake_popen), \
                mock.patch.object(webbrowser, "open", fake_open), \
                contextlib.redirect_stdout(out):
            server.open_browser(URL)
        return launched, opened, out.getvalue()

    def test_wsl_prefers_wslview(self) -> None:
        launched, opened, _ = self._run(
            platform="linux", wsl=True, env={},
            tools={"wslview": "/usr/bin/wslview", "explorer.exe": "/mnt/c/Windows/explorer.exe"})
        self.assertEqual(launched, [["/usr/bin/wslview", URL]])
        self.assertEqual(opened, [])

    def test_wsl_falls_back_to_explorer(self) -> None:
        launched, opened, _ = self._run(
            platform="linux", wsl=True, env={},
            tools={"explorer.exe": "/mnt/c/Windows/explorer.exe"})
        self.assertEqual(launched, [["/mnt/c/Windows/explorer.exe", URL]])
        self.assertEqual(opened, [])

    def test_wsl_without_launchers_or_display_prints_the_url(self) -> None:
        launched, opened, out = self._run(platform="linux", wsl=True, env={}, tools={})
        self.assertEqual((launched, opened), ([], []))
        self.assertIn(URL, out)

    def test_wsl_launcher_failure_does_not_raise(self) -> None:
        launched, opened, out = self._run(
            platform="linux", wsl=True, env={}, tools={"wslview": "/usr/bin/wslview"},
            popen_error=OSError("exec format error"))
        self.assertEqual((launched, opened), ([], []))
        self.assertIn(URL, out)

    def test_linux_without_display_never_calls_webbrowser(self) -> None:
        launched, opened, out = self._run(platform="linux", wsl=False, env={},
                                          tools={"w3m": "/usr/bin/w3m"})
        self.assertEqual((launched, opened), ([], []))
        self.assertIn(URL, out)

    def test_linux_with_a_display_uses_webbrowser(self) -> None:
        for env in ({"DISPLAY": ":0"}, {"WAYLAND_DISPLAY": "wayland-0"}):
            with self.subTest(env=env):
                launched, opened, _ = self._run(platform="linux", wsl=False, env=env, tools={})
                self.assertEqual((launched, opened), ([], [URL]))

    def test_macos_uses_webbrowser(self) -> None:
        launched, opened, _ = self._run(platform="darwin", wsl=False, env={}, tools={})
        self.assertEqual((launched, opened), ([], [URL]))


if __name__ == "__main__":
    unittest.main()
