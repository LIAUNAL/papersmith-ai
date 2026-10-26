"""The dashboard watcher polls on a Windows drive under WSL.

Under WSL2, `/mnt/<letter>/` is a 9P mount of a Windows drive: inotify
events for changes made from Windows never arrive, so watchfiles must poll
there. Elsewhere it keeps native notifications. No watcher thread starts.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import watcher


class PollingDecisionTests(unittest.TestCase):
    def test_wsl_windows_drive_polls(self) -> None:
        for root in ("/mnt/c/Users/ana/paper", "/mnt/d", "/mnt/C/work"):
            with self.subTest(root=root):
                self.assertTrue(watcher.needs_polling(Path(root), wsl=True))

    def test_wsl_linux_filesystem_does_not_poll(self) -> None:
        for root in ("/home/ana/paper", "/mnt/wsl/shared", "/mnt/cdrom/x", "/tmp/mnt/c/x"):
            with self.subTest(root=root):
                self.assertFalse(watcher.needs_polling(Path(root), wsl=True))

    def test_outside_wsl_never_polls(self) -> None:
        self.assertFalse(watcher.needs_polling(Path("/mnt/c/Users/ana/paper"), wsl=False))

    def test_default_detection_follows_the_kernel_release(self) -> None:
        with mock.patch.object(watcher.sys, "platform", "linux"), \
                mock.patch.object(watcher.platform, "release",
                                  return_value="5.15.0-microsoft-standard-WSL2"):
            self.assertTrue(watcher.needs_polling(Path("/mnt/c/paper")))
        with mock.patch.object(watcher.sys, "platform", "linux"), \
                mock.patch.object(watcher.platform, "release", return_value="6.8.0-generic"):
            self.assertFalse(watcher.needs_polling(Path("/mnt/c/paper")))

    def test_the_watch_call_receives_the_decision(self) -> None:
        seen: dict[str, object] = {}

        def fake_watch(*paths, **kwargs):
            seen.update(kwargs)
            return iter(())

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sections").mkdir()
            ws = watcher.WorkspaceWatcher(Path(tmp), lambda _paths: None)
            with mock.patch("watchfiles.watch", fake_watch), \
                    mock.patch.object(watcher, "needs_polling", return_value=True):
                ws._run()
        self.assertIs(seen.get("force_polling"), True)


if __name__ == "__main__":
    unittest.main()
