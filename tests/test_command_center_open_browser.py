"""`smith ui` opens the dashboard in a browser that fits the platform.

Under WSL it hands the URL to Windows (`wslview`, then `rundll32.exe
url.dll,FileProtocolHandler`; never `explorer.exe`, issue #188); on a
Linux without a graphical display it prints the URL instead of letting
Python's `webbrowser` start a text browser on the server's terminal; macOS
keeps `webbrowser`. A missing launcher never raises. Nothing is launched:
`shutil.which`, `subprocess.Popen` and `webbrowser.open` are replaced.
"""
from __future__ import annotations

import contextlib
import io
import os
import socket
import tempfile
import unittest
import webbrowser
from pathlib import Path
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
        no_x11 = tempfile.TemporaryDirectory()
        self.addCleanup(no_x11.cleanup)
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(server, "X11_SOCKET_DIR", Path(no_x11.name), create=True), \
                mock.patch.object(server.sys, "platform", platform), \
                mock.patch.object(server, "_is_wsl", lambda: wsl), \
                mock.patch.object(server.shutil, "which", lambda name: tools.get(name)), \
                mock.patch.object(server.subprocess, "Popen", fake_popen), \
                mock.patch.object(webbrowser, "open", fake_open), \
                contextlib.redirect_stdout(out):
            self.result = server.open_browser(URL)
        return launched, opened, out.getvalue()

    def test_wsl_prefers_wslview(self) -> None:
        launched, opened, _ = self._run(
            platform="linux", wsl=True, env={},
            tools={"wslview": "/usr/bin/wslview", "explorer.exe": "/mnt/c/Windows/explorer.exe"})
        self.assertEqual(launched, [["/usr/bin/wslview", URL]])
        self.assertEqual(opened, [])

    def test_wsl_falls_back_to_the_url_protocol_handler(self) -> None:
        # Issue #188: without wslview the URL, query string included, goes to
        # the default Windows browser through url.dll, not to Explorer.
        token_url = URL + "api/terminal/login?token=abc"
        launched: list[list[str]] = []
        with mock.patch.object(server, "_is_wsl", lambda: True), \
                mock.patch.object(server.shutil, "which",
                                  {"rundll32.exe": "/mnt/c/Windows/System32/rundll32.exe",
                                   "explorer.exe": "/mnt/c/Windows/explorer.exe"}.get), \
                mock.patch.object(server.subprocess, "Popen",
                                  lambda argv, **_: launched.append(list(argv)) or mock.Mock()):
            self.assertTrue(server.open_browser(token_url))
        self.assertEqual(launched, [["/mnt/c/Windows/System32/rundll32.exe",
                                     "url.dll,FileProtocolHandler", token_url]])

    def test_wsl_never_hands_a_url_to_explorer(self) -> None:
        # Explorer opens the Documents folder for a URL with a query string and
        # still "starts", so it would report a launch that never happened.
        launched, opened, out = self._run(
            platform="linux", wsl=True, env={},
            tools={"explorer.exe": "/mnt/c/Windows/explorer.exe"})
        self.assertEqual((launched, opened), ([], []))
        self.assertIn(URL, out)
        self.assertFalse(self.result, "nothing opened, so the page shows the printed-URL hint")

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


def _bind_socket(path: Path) -> None:
    """Leave a real Unix socket at ``path``, as a compositor or X server does."""
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.close()


class SocketDisplayTests(unittest.TestCase):
    """A terminal multiplexer started outside the desktop session inherits no
    DISPLAY or WAYLAND_DISPLAY, yet the session's sockets are there: the
    compositor's ``wayland-N`` in XDG_RUNTIME_DIR, an X server's ``X<N>`` in
    /tmp/.X11-unix. Found only that way, the browser is launched with an
    environment that names the display, and the server's own is left alone."""

    def setUp(self) -> None:
        runtime = tempfile.TemporaryDirectory()
        x11 = tempfile.TemporaryDirectory()
        self.addCleanup(runtime.cleanup)
        self.addCleanup(x11.cleanup)
        self.runtime = Path(runtime.name)
        self.x11 = Path(x11.name)

    def _run(self, *, tools: dict[str, str] | None = None, exit_code: int = 0,
             uid: int | None = None):
        tools = {"xdg-open": "/usr/bin/xdg-open"} if tools is None else tools
        launched: list[tuple[list[str], dict]] = []
        opened: list[str] = []

        def fake_popen(argv, **kwargs):
            launched.append((list(argv), kwargs))
            return mock.Mock(**{"wait.return_value": exit_code})

        def fake_open(url, *args, **kwargs):
            opened.append(url)
            return True

        out = io.StringIO()
        getuid = (lambda: uid) if uid is not None else os.getuid
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(self.runtime),
                                          "XDG_SESSION_TYPE": "tty"}, clear=True), \
                mock.patch.object(server, "X11_SOCKET_DIR", self.x11, create=True), \
                mock.patch.object(server.os, "getuid", getuid), \
                mock.patch.object(server.sys, "platform", "linux"), \
                mock.patch.object(server, "_is_wsl", lambda: False), \
                mock.patch.object(server.shutil, "which", lambda name: tools.get(name)), \
                mock.patch.object(server.subprocess, "Popen", fake_popen), \
                mock.patch.object(webbrowser, "open", fake_open), \
                contextlib.redirect_stdout(out):
            detected = server._has_graphical_display()
            result = server.open_browser(URL)
            environ_after = dict(os.environ)
        return detected, result, launched, opened, out.getvalue(), environ_after

    def test_a_wayland_socket_is_a_display_named_to_the_launcher(self) -> None:
        _bind_socket(self.runtime / "wayland-0")
        (self.runtime / "wayland-0.lock").touch()
        detected, result, launched, opened, out, environ_after = self._run()
        self.assertTrue(detected)
        self.assertTrue(result)
        self.assertEqual(opened, [])
        self.assertEqual(len(launched), 1)
        argv, kwargs = launched[0]
        self.assertEqual(argv, ["/usr/bin/xdg-open", URL])
        self.assertEqual(kwargs["env"]["WAYLAND_DISPLAY"], "wayland-0")
        self.assertNotIn("DISPLAY", kwargs["env"])
        self.assertEqual(kwargs["env"]["XDG_RUNTIME_DIR"], str(self.runtime))
        for stream in ("stdin", "stdout", "stderr"):
            self.assertEqual(kwargs[stream], server.subprocess.DEVNULL)
        self.assertTrue(kwargs["close_fds"])
        # The server's own environment is not changed, and nothing is printed.
        self.assertNotIn("WAYLAND_DISPLAY", environ_after)
        self.assertNotIn(URL, out)

    def test_an_x11_socket_is_a_display_named_to_the_launcher(self) -> None:
        _bind_socket(self.x11 / "X1")
        detected, result, launched, _, _, environ_after = self._run()
        self.assertTrue(detected)
        self.assertTrue(result)
        self.assertEqual(launched[0][1]["env"]["DISPLAY"], ":1")
        self.assertNotIn("DISPLAY", environ_after)

    def test_a_lock_file_alone_is_not_a_display(self) -> None:
        (self.runtime / "wayland-0.lock").touch()
        detected, result, launched, opened, out, _ = self._run()
        self.assertFalse(detected)
        self.assertFalse(result)
        self.assertEqual((launched, opened), ([], []))
        self.assertIn(URL, out)

    def test_a_plain_file_named_like_a_socket_is_not_a_display(self) -> None:
        (self.runtime / "wayland-0").touch()
        (self.x11 / "X0").touch()
        detected, result, launched, _, out, _ = self._run()
        self.assertFalse(detected)
        self.assertEqual((result, launched), (False, []))
        self.assertIn(URL, out)

    def test_no_socket_prints_the_url_and_starts_no_text_browser(self) -> None:
        detected, result, launched, opened, out, _ = self._run(
            tools={"xdg-open": "/usr/bin/xdg-open", "w3m": "/usr/bin/w3m"})
        self.assertFalse(detected)
        self.assertFalse(result)
        self.assertEqual((launched, opened), ([], []))
        self.assertIn(URL, out)

    def test_another_users_socket_is_not_a_display(self) -> None:
        _bind_socket(self.runtime / "wayland-0")
        _bind_socket(self.x11 / "X0")
        detected, result, launched, _, out, _ = self._run(uid=os.getuid() + 1)
        self.assertFalse(detected)
        self.assertEqual((result, launched), (False, []))
        self.assertIn(URL, out)

    def test_a_failed_or_missing_launcher_prints_the_url(self) -> None:
        _bind_socket(self.runtime / "wayland-0")
        for tools, exit_code in (({}, 0), (None, 3)):
            with self.subTest(tools=tools, exit_code=exit_code):
                _, result, _, opened, out, _ = self._run(tools=tools, exit_code=exit_code)
                self.assertFalse(result)
                self.assertEqual(opened, [])
                self.assertIn(URL, out)


if __name__ == "__main__":
    unittest.main()
