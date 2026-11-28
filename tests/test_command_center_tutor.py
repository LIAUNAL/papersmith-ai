"""The math tutor's backend: image uploads, the thread, and one headless turn
of the `math-tutor` agent behind the terminal's secret and origin guards."""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess as sp
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import server, tutor

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
DATA_URL = "data:image/png;base64," + base64.b64encode(PNG).decode()

TURN = {
    "image_reading": "$$k(x,x') = \\langle \\psi(x) \\mid \\psi(x') \\rangle$$ and an arrow from x to psi",
    "reply": "Look at what the modulus does to a phase.",
    "question": "What happens to $k(x,x)$?",
    "latex": ["k(x,x') = \\lvert \\langle \\psi(x) \\mid \\psi(x') \\rangle \\rvert^{2}"],
    "assessment": {"level": 1, "label": "reconoce", "evidence": "wrote the inner product",
                   "gaps": ["missing modulus squared"]},
    "novelty_link": "The fidelity kernel is the paper's claim.",
    "next_step": "Draw the feature map for two epochs.",
}

SAME = {"Host": "127.0.0.1:8080", "Origin": "http://127.0.0.1:8080",
        "Sec-Fetch-Site": "same-origin", "Content-Type": "application/json",
        "X-Papersmith-Terminal": "1"}


class _Request:
    def __init__(self, headers=None, body=None, cookies=None) -> None:
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body
        self.cookies = dict(cookies or {})

    async def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _route(app, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or ()):
            return route.endpoint
    raise AssertionError(f"no {method} {path}")


def _call(endpoint, *args):
    result = endpoint(*args)
    return asyncio.run(result) if asyncio.iscoroutine(result) else result


def _body(response) -> dict:
    return json.loads(bytes(response.body))


class _Root(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()


class StoreTests(_Root):
    def test_an_image_is_stored_by_content_under_the_tutor_folder(self) -> None:
        saved = tutor.save_image(self.root, DATA_URL)
        path = self.root / ".papersmith" / "math-tutor" / "images" / f"{saved['id']}.png"
        self.assertEqual(path.read_bytes(), PNG)
        self.assertEqual(tutor.save_image(self.root, DATA_URL)["id"], saved["id"])

    def test_a_non_image_or_oversized_upload_is_refused(self) -> None:
        for bad in ("data:text/plain;base64,aGVsbG8=", "data:image/png;base64,aGVsbG8=", "nope",
                    "data:image/png;base64," + base64.b64encode(PNG + b"x" * tutor.MAX_IMAGE_BYTES).decode()):
            with self.subTest(bad=bad[:30]):
                with self.assertRaises(tutor.TutorError):
                    tutor.save_image(self.root, bad)

    def test_a_polyglot_image_is_refused(self) -> None:
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 16 + b"\xff\xd9"
        webp = b"RIFF" + (len(b"WEBPVP8 ") + 4).to_bytes(4, "little") + b"WEBPVP8 " + b"\x00" * 4
        self.assertEqual(tutor.save_image(self.root, "data:image/jpeg;base64,"
                                          + base64.b64encode(jpeg).decode())["type"], "image/jpeg")
        self.assertEqual(tutor.save_image(self.root, "data:image/webp;base64,"
                                          + base64.b64encode(webp).decode())["type"], "image/webp")
        for name, data in (("png+html", PNG + b"<html><script>alert(1)</script></html>"),
                           ("jpeg+html", jpeg + b"<script>"),
                           ("webp wrong size", webp + b"<script>")):
            with self.subTest(name):
                url = "data:image/png;base64," + base64.b64encode(data).decode()
                with self.assertRaises(tutor.TutorError):
                    tutor.save_image(self.root, url)

    def test_an_image_id_never_escapes_the_folder(self) -> None:
        for bad in ("../../etc/passwd", "a/b", "", "x" * 200):
            with self.assertRaises(tutor.TutorError):
                tutor.image_path(self.root, bad)


class TurnTests(_Root):
    def test_a_turn_records_the_reader_and_the_tutor(self) -> None:
        image = tutor.save_image(self.root, DATA_URL)["id"]
        seen = {}

        def fake(root, system, prompt, images):
            seen.update(system=system, prompt=prompt, images=images)
            return TURN, "fake"

        turn = tutor.run_turn(self.root, "Is my kernel right?", [image], "evaluate", runner=fake)
        self.assertEqual(turn["assessment"]["level"], 1)
        self.assertEqual(turn["agent"], "fake")
        thread = tutor.load_thread(self.root)
        self.assertEqual([t["role"] for t in thread["turns"]], ["reader", "tutor"])
        self.assertEqual(thread["turns"][0]["images"], [image])
        self.assertIn("mode: evaluate", seen["prompt"])
        self.assertIn(f".papersmith/math-tutor/images/{image}.png", seen["prompt"])
        self.assertIn("Socratic", seen["system"])
        self.assertEqual(seen["images"], [self.root / ".papersmith/math-tutor/images" / f"{image}.png"])

    def test_a_malformed_agent_answer_is_reported_not_recorded(self) -> None:
        def broken(root, system, prompt, images):
            return {"reply": 3}, "fake"

        with self.assertRaises(tutor.TutorError):
            tutor.run_turn(self.root, "hi", [], "ask", runner=broken)
        self.assertEqual(tutor.load_thread(self.root)["turns"], [])

    def test_a_boolean_level_or_non_text_gaps_are_refused(self) -> None:
        for assessment in ({**TURN["assessment"], "level": True}, {**TURN["assessment"], "gaps": [3]}):
            with self.assertRaises(tutor.TutorError):
                tutor.run_turn(self.root, "hi", [], "ask", runner=lambda *a, x=assessment: ({**TURN, "assessment": x}, "f"))

    def test_an_image_id_with_a_trailing_newline_is_refused(self) -> None:
        image = tutor.save_image(self.root, DATA_URL)["id"]
        with self.assertRaises(tutor.TutorError):
            tutor.image_path(self.root, image + "\n")

    def test_unknown_modes_and_images_are_refused(self) -> None:
        with self.assertRaises(tutor.TutorError):
            tutor.run_turn(self.root, "hi", [], "grade-me", runner=lambda *a: (TURN, "x"))
        with self.assertRaises(tutor.TutorError):
            tutor.run_turn(self.root, "hi", ["0123456789abcdef"], "ask", runner=lambda *a: (TURN, "x"))

    def test_the_json_turn_is_found_inside_free_text(self) -> None:
        text = "Sure.\n```json\n" + json.dumps(TURN) + "\n```\nthanks"
        self.assertEqual(tutor.extract_turn(text)["question"], TURN["question"])

    def test_the_agent_never_reads_the_servers_stdin(self) -> None:
        import subprocess as sp
        calls = []
        original_run, original_find = tutor.subprocess.run, tutor.find_executable
        tutor.find_executable = lambda name: "/bin/claude" if name == "claude" else None
        tutor.subprocess.run = lambda argv, **kw: calls.append(kw) or sp.CompletedProcess(
            argv, 0, json.dumps({"structured_output": TURN}), "")
        self.addCleanup(setattr, tutor.subprocess, "run", original_run)
        self.addCleanup(setattr, tutor, "find_executable", original_find)
        turn, agent = tutor.run_agent(self.root, "S", "P", [])
        self.assertEqual((agent, turn["question"]), ("claude", TURN["question"]))
        self.assertIs(calls[0]["stdin"], sp.DEVNULL)

    def test_the_claude_command_is_read_only_and_lean(self) -> None:
        argv = tutor.claude_argv("/bin/claude", "SYS", "PROMPT")
        self.assertEqual(argv[:2], ["/bin/claude", "-p"])
        self.assertEqual(argv[argv.index("--tools") + 1], "Read")
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "local")
        self.assertIn("--no-session-persistence", argv)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1])["required"],
                         tutor.TURN_SCHEMA["required"])

    def test_the_claude_command_carries_a_declared_model_and_only_then(self) -> None:
        argv = tutor.claude_argv("/bin/claude", "SYS", "PROMPT", model="sonnet")
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")
        self.assertEqual(argv[-1], "PROMPT")
        self.assertNotIn("--model", tutor.claude_argv("/bin/claude", "SYS", "PROMPT"))

    def _agent_file(self, model_line: str) -> None:
        agents = self.root / ".claude" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / "math-tutor.md").write_text(
            f"---\nname: math-tutor\ndescription: \"tutor\"\ntools: Read\n{model_line}---\n\n# Body\nmodel: opus\n",
            encoding="utf-8")

    def _converse_argv(self, available: tuple[str, ...]) -> list[str]:
        calls = []
        original_run, original_find = tutor.subprocess.run, tutor.find_executable
        tutor.find_executable = lambda name: f"/bin/{name}" if name in available else None
        tutor.subprocess.run = lambda argv, **kw: calls.append(argv) or sp.CompletedProcess(
            argv, 0, json.dumps({"structured_output": TURN, "response": json.dumps(TURN)}), "")
        self.addCleanup(setattr, tutor.subprocess, "run", original_run)
        self.addCleanup(setattr, tutor, "find_executable", original_find)
        tutor.converse(tutor.MATH, self.root, {"mode": "ask", "message": "hi"}, lambda thread: "P", [])
        return calls[0]

    def test_a_claude_turn_runs_the_model_its_agent_file_declares(self) -> None:
        self._agent_file("model: sonnet\n")
        argv = self._converse_argv(("claude",))
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")

    def test_a_turn_without_a_declared_model_inherits_the_session_model(self) -> None:
        self._agent_file("")
        self.assertNotIn("--model", self._converse_argv(("claude",)))

    def test_a_model_value_that_is_not_a_plain_name_is_ignored(self) -> None:
        self._agent_file("model: --dangerously-skip-permissions\n")
        self.assertNotIn("--model", self._converse_argv(("claude",)))

    def test_agy_and_pi_keep_inheriting_their_own_model(self) -> None:
        # A Claude alias is not an agy or Pi model slug, so neither gets --model.
        self._agent_file("model: sonnet\n")
        self.assertNotIn("--model", self._converse_argv(("agy",)))
        self.assertNotIn("--model", self._converse_argv(("pi",)))


class RouteTests(_Root):
    def setUp(self) -> None:
        super().setUp()
        self.app = server.create_app(self.root, history_store=None, enable_terminal=True)
        self.cookie = {server.TERMINAL_COOKIE: self.app.state.terminal.token}

    def req(self, body=None, headers=SAME, cookie=True):
        return _Request(headers, body, self.cookie if cookie else None)

    def test_uploads_and_turns_require_the_secret_and_same_origin(self) -> None:
        upload = _route(self.app, "/api/terminal/tutor/images", "POST")
        self.assertEqual(_call(upload, self.req({"data_url": DATA_URL}, cookie=False)).status_code, 403)
        self.assertEqual(_call(upload, self.req({"data_url": DATA_URL},
                                                {**SAME, "Origin": "http://evil.example"})).status_code, 403)
        ok = _call(upload, self.req({"data_url": DATA_URL}))
        self.assertEqual(ok.status_code, 200)
        image = _body(ok)["id"]
        fetch = _route(self.app, "/api/terminal/tutor/images/{image_id}", "GET")
        self.assertEqual(_call(fetch, image, self.req(cookie=False)).status_code, 403)
        got = _call(fetch, image, self.req())
        self.assertEqual((got.status_code, got.media_type), (200, "image/png"))

    def test_a_turn_runs_through_the_route(self) -> None:
        tutor_runner = tutor.run_agent
        tutor.run_agent = lambda root, system, prompt, images: (TURN, "fake")
        self.addCleanup(setattr, tutor, "run_agent", tutor_runner)
        turn = _route(self.app, "/api/terminal/tutor/turn", "POST")
        response = _call(turn, self.req({"message": "help", "images": [], "mode": "ask"}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_body(response)["question"], TURN["question"])
        thread = _call(_route(self.app, "/api/terminal/tutor/thread", "GET"), self.req())
        self.assertEqual(len(_body(thread)["turns"]), 2)
        reset = _call(_route(self.app, "/api/terminal/tutor/thread", "DELETE"), self.req({}))
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(tutor.load_thread(self.root)["turns"], [])

    def test_the_tutor_is_off_when_the_terminal_is(self) -> None:
        app = server.create_app(self.root, history_store=None)
        response = _call(_route(app, "/api/terminal/tutor/thread", "GET"), self.req())
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
