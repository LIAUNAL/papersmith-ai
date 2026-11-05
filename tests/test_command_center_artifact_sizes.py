"""The artifacts explorer shows the size the backend sends: `size_kb`, already
in kilobytes (issue 154). Reading a field the backend never sends printed
"NaN KB" on every row."""

from __future__ import annotations

import unittest
from pathlib import Path

from skills._core.command_center import server

STATIC = Path(server.__file__).resolve().parent / "static"
SERVER = Path(server.__file__).read_text(encoding="utf-8")


class ArtifactSizeLabelTests(unittest.TestCase):
    def test_the_sidebar_reads_the_field_the_backend_sends(self) -> None:
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('"size_kb":', SERVER)
        self.assertNotIn('"size":', SERVER)
        self.assertIn("${art.size_kb} KB", page)
        self.assertNotIn("art.size /", page)


if __name__ == "__main__":
    unittest.main()
