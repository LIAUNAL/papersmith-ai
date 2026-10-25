"""The candidates view never executes scouted text; action POSTs refuse other origins.

`sota-pool/candidates.json` is filled from external literature, so a title,
family or URL is attacker-shaped data. The view used to interpolate it raw
into an `<option>`, into the inline `<script>` that carries the JSON, and into
`innerHTML` row templates. `/api/pdf/execute` and `/api/phase/run` (which
writes files / runs the TeX toolchain) accepted any origin.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import server

HOSTILE_TITLE = "</script><script>alert('title')</script>"
HOSTILE_FAMILY = '"><img src=x onerror=alert(1)>'


class _Request:
    def __init__(self, payload: dict, headers: dict) -> None:
        self._payload = payload
        self.headers = headers

    async def json(self) -> dict:
        return self._payload


class CandidatesViewEscapingTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        (self.root / "sota-pool").mkdir()
        (self.root / "sota-pool" / "candidates.json").write_text(
            json.dumps(
                [
                    {
                        "title": HOSTILE_TITLE,
                        "family": HOSTILE_FAMILY,
                        "identifier": "10.1/x",
                        "source_url": "javascript:alert(1)",
                        "abstract": "<img src=x onerror=alert(2)>",
                        "authors": ["<b>A</b>"],
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.app = server.create_app(self.root)

    def _endpoint(self, path: str):
        return next(r.endpoint for r in self.app.routes if getattr(r, "path", None) == path)

    def _view(self) -> str:
        return bytes(self._endpoint("/api/atlas/candidates/view")().body).decode("utf-8")

    def test_embedded_json_cannot_close_its_script(self):
        body = self._view()
        self.assertNotIn("</script><script>alert", body)
        script = body.split("const CANDIDATES = ", 1)[1].split(";\n", 1)[0]
        self.assertEqual(json.loads(script)[0]["title"], HOSTILE_TITLE)

    def test_family_option_is_attribute_escaped(self):
        body = self._view()
        self.assertNotIn(HOSTILE_FAMILY, body)
        self.assertIn("&quot;&gt;&lt;img src=x onerror=alert(1)&gt;", body)

    def test_every_rendered_candidate_field_goes_through_esc(self):
        body = self._view()
        raw = [
            m
            for m in re.findall(r"\$\{\s*\(?c\.[a-z_]+[^}]*\}", body)
            if not m.startswith("${c.identifier ?")
        ]
        self.assertEqual(raw, [], "candidate fields interpolated without esc()")
        self.assertIn("function safeUrl", body)

    @unittest.skipIf(shutil.which("node") is None, "node runs the page's own helpers")
    def test_shipped_helpers_neutralise_hostile_values(self):
        body = self._view()
        helpers = body[body.index("function esc(v)"):body.index("function getFamilyBadgeClass")]
        program = helpers + """
globalThis.location = {href: 'http://127.0.0.1:8765/api/atlas/candidates/view'};
process.stdout.write(JSON.stringify([
  esc(`<img src=x onerror="alert(1)">'&`),
  safeUrl('javascript:alert(1)'),
  safeUrl(' JaVaScRiPt:alert(1)'),
  safeUrl('data:text/html,<b>x</b>'),
  safeUrl('https://doi.org/10.1/x'),
  safeUrl('http://example.org/a?b=1'),
]));
"""
        result = subprocess.run(["node", "-e", program], capture_output=True, text=True,
                                timeout=60, check=True)
        self.assertEqual(json.loads(result.stdout), [
            "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&#39;&amp;",
            "#", "#", "#",
            "https://doi.org/10.1/x",
            "http://example.org/a?b=1",
        ])


class ActionOriginTests(unittest.TestCase):
    def test_cross_origin_actions_are_refused(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        app = server.create_app(root)
        for path, payload in (
            ("/api/pdf/execute", {"annotations": []}),
            ("/api/phase/run", {"phase_id": "paper"}),
        ):
            endpoint = next(r.endpoint for r in app.routes if getattr(r, "path", None) == path)
            request = _Request(
                payload, {"origin": "https://evil.example", "host": "127.0.0.1:8765"}
            )
            response = asyncio.run(endpoint(request))
            self.assertEqual(response.status_code, 403, path)
        self.assertFalse((root / ".papersmith").exists())

    def test_same_origin_and_originless_actions_still_run(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        app = server.create_app(root)
        endpoint = next(r.endpoint for r in app.routes
                        if getattr(r, "path", None) == "/api/pdf/execute")
        for headers in ({"origin": "http://127.0.0.1:8765", "host": "127.0.0.1:8765"},
                        {"host": "127.0.0.1:8765"}):
            response = asyncio.run(endpoint(_Request({"annotations": []}, headers)))
            self.assertEqual(response.status_code, 200, headers)
        self.assertTrue((root / ".papersmith" / "anotaciones_pdf.json").is_file())


if __name__ == "__main__":
    unittest.main()
