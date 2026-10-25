"""#93: `kaggle_driver.py fetch` reads every page of a kernel's output listing.

`list_kernel_session_output` is paged (`page_token` in, `next_page_token`
out). Before the fix `cmd_fetch` asked for the first page only and still
reported success, so a run whose output spans pages came back short.

Drives `cmd_fetch` directly against a fake client that answers a scripted
sequence of pages; `_fetch_file` is replaced so nothing touches the network.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DRIVER_SCRIPT = REPOSITORY_ROOT / "skills/remote-execution/scripts/adapters/kaggle_driver.py"


def _load_driver():
    spec = importlib.util.spec_from_file_location("kaggle_driver_paging", DRIVER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _page(files, token="", log=""):
    entries = [SimpleNamespace(file_name=name, url=f"https://example.invalid/{name}")
               for name in files]
    return SimpleNamespace(files=entries, next_page_token=token, log=log)


class PagedClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.tokens: list[str] = []
        self._client = SimpleNamespace(_session=object())

    def list_kernel_session_output(self, request):
        self.tokens.append(request.page_token or "")
        return self.pages.pop(0)


@unittest.skipUnless(importlib.util.find_spec("kagglesdk"), "kagglesdk is not installed")
class OutputPagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = _load_driver()
        self.addCleanup(sys.modules.pop, "kaggle_driver_paging", None)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.into = Path(tmp.name) / "out"
        self.downloads: list[str] = []

        def fake_fetch(_session, url, destination, _budget):
            # The log must already be on disk before the first download.
            self.downloads.append((self.into / "log.txt").exists())
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"x")
            return 1

        patcher = mock.patch.object(self.driver, "_fetch_file", side_effect=fake_fetch)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_page_is_requested_and_downloaded(self) -> None:
        client = PagedClient([_page(["a.txt"], "t2", log="run log"),
                              _page(["b.txt"], "t3"), _page(["c/d.txt"])])
        result = self.driver.cmd_fetch(client, "acct/kernel", self.into)
        self.assertEqual(client.tokens, ["", "t2", "t3"])
        self.assertEqual(result["files"], ["a.txt", "b.txt", "c/d.txt", "log.txt"])
        self.assertEqual((self.into / "log.txt").read_text(encoding="utf-8"), "run log")
        self.assertTrue((self.into / "c/d.txt").exists())
        self.assertEqual(self.downloads, [True, True, True])

    def test_a_repeated_page_token_refuses(self) -> None:
        client = PagedClient([_page(["a.txt"], "t2"), _page(["b.txt"], "t2"),
                              _page(["c.txt"])])
        with self.assertRaises(self.driver.DriverError) as caught:
            self.driver.cmd_fetch(client, "acct/kernel", self.into)
        self.assertIn("repeated page token", str(caught.exception))
        self.assertEqual(client.tokens, ["", "t2"])

    def test_the_page_ceiling_refuses(self) -> None:
        ceiling = self.driver.FETCH_MAX_PAGES
        client = PagedClient([_page([f"f{n}.txt"], f"t{n + 1}") for n in range(ceiling + 1)])
        with self.assertRaises(self.driver.DriverError) as caught:
            self.driver.cmd_fetch(client, "acct/kernel", self.into)
        self.assertIn(f"more than {ceiling} pages", str(caught.exception))
        self.assertEqual(len(client.tokens), ceiling)

    def test_a_single_page_listing_still_fetches(self) -> None:
        client = PagedClient([_page(["only.txt"], log="log")])
        result = self.driver.cmd_fetch(client, "acct/kernel", self.into)
        self.assertEqual(client.tokens, [""])
        self.assertEqual(result["files"], ["log.txt", "only.txt"])


if __name__ == "__main__":
    unittest.main()
