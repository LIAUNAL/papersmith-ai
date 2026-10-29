"""The experiments tutor: a read-only skill and agent whose doctrine covers the
experiment decisions the operator asked to consult and iterate on, and which
hands every change of decision to `/experimental-deliberation`."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import experiments_tutor, server, tutor

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "experiments-tutor" / "SKILL.md"
AGENT = ROOT / ".claude" / "agents" / "experiments-tutor.md"

#: The decision areas, by the id the turn's `decision_area` carries.
AREAS = ("architecture", "hyperparameters", "ablation", "significance", "toy-set", "training",
         "upper-bounds", "baselines", "validation", "compute", "reproducibility")


def flat(text: str) -> str:
    return " ".join(text.split())


class DoctrineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = flat(SKILL.read_text(encoding="utf-8"))
        self.agent = AGENT.read_text(encoding="utf-8")

    def test_the_agent_reads_and_never_writes_or_runs(self) -> None:
        tools = re.search(r"^tools:\s*(.+)$", self.agent, re.MULTILINE).group(1)
        self.assertEqual([t.strip() for t in tools.split(",")], ["Read", "Glob", "Grep"])
        self.assertIn("skills/experiments-tutor/SKILL.md", self.agent)

    def test_every_decision_area_is_in_the_doctrine(self) -> None:
        for area in AREAS + ("general",):
            self.assertIn(f"`{area}`", self.skill, area)
        for topic in ("network architecture", "hyperparameter search", "ablation",
                      "statistical significance", "toy set", "training strateg", "upper bound",
                      "oracle", "baseline", "leakage", "compute budget", "reproducib"):
            self.assertIn(topic, self.skill.lower(), topic)

    def test_numbers_are_never_invented_and_secrets_never_read(self) -> None:
        self.assertIn("nothing measured yet", self.skill)
        for secret in (".papersmith/team.json", ".remote-execution", "credential"):
            self.assertIn(secret, self.skill)

    def test_a_change_of_decision_goes_to_the_deliberation(self) -> None:
        self.assertIn("/experimental-deliberation", self.skill)
        self.assertIn("deliberation_prompt", self.skill)
        self.assertIn("delegates to the `experiments-tutor` agent", self.skill)


class _Root(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()


SCHEMA = {"type": "object", "required": ["reply"], "properties": {"reply": {"type": "string"}}}


def _demo_valid(turn):
    if not (isinstance(turn, dict) and isinstance(turn.get("reply"), str)):
        raise tutor.TutorError("no reply")
    return {"reply": turn["reply"]}


def _profile(**changes) -> tutor.Profile:
    fields = dict(name="demo", folder=(".papersmith", "demo-tutor"),
                  doctrine=(".claude/agents/demo.md",), fallback="Demo doctrine.",
                  headless="Headless demo.", schema=SCHEMA, modes=("ask",),
                  context=lambda root: {"demo": True}, valid=_demo_valid)
    fields.update(changes)
    return tutor.Profile(**fields)


class ProfileTests(_Root):
    """The math tutor's machinery, generalized: each profile has its own thread
    folder, doctrine, schema and lock, and the math profile is the default."""

    def test_the_math_profile_is_the_default_and_keeps_its_folder(self) -> None:
        self.assertEqual(tutor.MATH.folder, (".papersmith", "math-tutor"))
        self.assertIs(tutor.MATH.schema, tutor.TURN_SCHEMA)
        self.assertEqual(tutor.MATH.modes, tutor.MODES)
        self.assertEqual(tutor.folder(self.root), tutor.folder(self.root, tutor.MATH))

    def test_a_profile_keeps_its_own_thread_beside_the_math_one(self) -> None:
        demo = _profile()
        seen = {}

        def fake(root, system, prompt, images):
            seen.update(system=system, prompt=prompt)
            return {"reply": "hi"}, "fake"

        turn = tutor.converse(demo, self.root, {"mode": "ask", "message": "m"},
                              lambda thread: f"turns so far: {len(thread['turns'])}", [], fake)
        self.assertEqual((turn["reply"], turn["agent"]), ("hi", "fake"))
        self.assertEqual(seen["prompt"], "turns so far: 0")
        self.assertIn("Demo doctrine.", seen["system"])
        self.assertIn("Headless demo.", seen["system"])
        saved = json.loads((self.root / ".papersmith/demo-tutor/thread.json").read_text())
        self.assertEqual([t["role"] for t in saved["turns"]], ["reader", "tutor"])
        self.assertEqual(saved["turns"][0]["message"], "m")
        self.assertEqual(tutor.load_thread(self.root)["turns"], [])
        tutor.reset_thread(self.root, demo)
        self.assertEqual(tutor.load_thread(self.root, demo)["turns"], [])

    def test_each_profile_has_its_own_lock(self) -> None:
        self.assertIsNot(_profile().lock, _profile().lock)
        self.assertIsNot(_profile().lock, tutor.MATH.lock)

    def test_the_claude_command_carries_the_profiles_schema(self) -> None:
        argv = tutor.claude_argv("/bin/claude", "S", "P", SCHEMA, ("Read", "Glob", "Grep"))
        self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1]), SCHEMA)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Glob,Grep")
        self.assertEqual(argv[argv.index("--allowedTools") + 1], "Read,Glob,Grep")
        self.assertEqual(tutor.MATH.tools, ("Read",))
        self.assertEqual(tutor.claude_argv("/bin/claude", "S", "P"),
                         tutor.claude_argv("/bin/claude", "S", "P", tutor.TURN_SCHEMA))


TURN = {
    "reply": "The scaler is fitted before the split (`src/demo/data.py`).",
    "question": "Which subjects does the normalization see?",
    "assessment": {"level": 2, "label": "justificada", "evidence": "the protocol says subject-wise",
                   "gaps": ["normalization fitted on all subjects"]},
    "next_step": "Read `src/demo/data.py` and find where the scaler is fitted.",
    "decision_area": "validation",
    "evidence": ["experiments/experiments-demo-v01.md"],
    "risks": ["test subjects leak into training statistics"],
    "deliberation_prompt": "In [exp:E1], fit the scaler inside each training fold.",
}

PROTOCOL = """# Experiments demo v01

**Validation scheme:** leave-one-subject-out

## Experiment [exp:E1] — Kernel versus EEGNet

- **Hypothesis:** the fidelity kernel beats EEGNet
- **Success criterion:** accuracy gain of at least 2 points

### Expected Report: Accuracy per subject

| subject | kernel | eegnet |
|---|---|---|
| s01 | | |
"""

SECRETS = ("SECRET-TEAM-123", "SECRET-LEDGER-456", "SECRET-WORKER-789", "SECRET-TOKEN-000",
           "SECRET-STORE-111", "SECRET-ENV-222")


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _numbers(value) -> list:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, dict):
        return [n for v in value.values() for n in _numbers(v)]
    if isinstance(value, list):
        return [n for v in value for n in _numbers(v)]
    return []


class DigestTests(_Root):
    def populate(self) -> None:
        _write(self.root, "experiments/experiments-demo-v01.md", PROTOCOL)
        poc = "implementations/demo/Poc"
        _write(self.root, f"{poc}/AGREED.md", "# Agreed\n")
        _write(self.root, "implementations/demo/src/demo/__init__.py", "")
        _write(self.root, f"{poc}/Results/tables/accuracy.csv", "subject,kernel,eegnet\ns01,0.81,0.77\n")
        _write(self.root, f"{poc}/Results/significance.json", json.dumps(
            [{"comparison": "kernel vs eegnet", "test": "wilcoxon", "p_value": 0.031, "n": 9}]))
        _write(self.root, f"{poc}/Results/timing.json", json.dumps(
            {"schema": 1, "measurements": [{"host": "local:cpu", "unit": "epoch", "secondsPerUnit": 4.5}]}))
        _write(self.root, "datasets/registry.json", json.dumps(
            [{"slug": "toy-eeg", "role": "toy", "title": "Seeded toy set", "qc": {"status": "pass"}}]))

    def test_a_fresh_workspace_has_nothing_measured_and_no_numbers(self) -> None:
        digest = experiments_tutor.digest(self.root)
        self.assertIs(digest["measured"], False)
        self.assertIsNone(digest["protocol"])
        self.assertEqual((digest["products"], digest["read"]), ([], []))
        self.assertEqual(_numbers(digest), [])
        prompt = experiments_tutor.build_prompt(self.root, "Is my toy set enough?", "ask", "toy-set",
                                                {"turns": []})
        self.assertIn("nothing measured yet", prompt)

    def test_the_digest_carries_the_protocol_and_each_products_evidence(self) -> None:
        self.populate()
        digest = experiments_tutor.digest(self.root)
        self.assertIs(digest["measured"], True)
        self.assertEqual(digest["protocol"]["validation_scheme"], "leave-one-subject-out")
        self.assertEqual(digest["protocol"]["experiments"][0]["id"], "E1")
        self.assertEqual(digest["protocol"]["experiments"][0]["expected_reports"][0]["headers"],
                         ["subject", "kernel", "eegnet"])
        product = digest["products"][0]
        self.assertEqual((product["repo"], product["name"], product["kind"]), ("demo", "Poc", "poc"))
        self.assertEqual(product["significance"][0]["p_value"], 0.031)
        self.assertEqual(product["tables"][0], {"path": "implementations/demo/Poc/Results/tables/accuracy.csv",
                                                "headers": ["subject", "kernel", "eegnet"], "rows": 1})
        self.assertEqual(product["timing"]["measurements"][0]["secondsPerUnit"], 4.5)
        self.assertEqual(product["runs"], {"count": 0, "by_state": {}})
        self.assertEqual(digest["datasets"]["items"][0]["slug"], "toy-eeg")
        for path in ("experiments/experiments-demo-v01.md", "implementations/demo/Poc/AGREED.md",
                     "implementations/demo/src/"):
            self.assertIn(path, digest["read"])
        self.assertNotIn("implementations/demo/Poc/Experimental_AGREED.md", digest["read"])

    def test_the_digest_is_size_capped(self) -> None:
        self.populate()
        rows = [{"comparison": f"arm {i} vs baseline " + "x" * 150, "test": "wilcoxon", "p_value": 0.5}
                for i in range(200)]
        for repo in range(12):
            for name in range(4):
                folder = f"implementations/r{repo}/P{name}"
                _write(self.root, f"{folder}/AGREED.md", "")
                _write(self.root, f"{folder}/Results/significance.json", json.dumps(rows))
        digest = experiments_tutor.digest(self.root)
        self.assertLessEqual(len(json.dumps(digest, ensure_ascii=False)), experiments_tutor.MAX_DIGEST_CHARS)
        self.assertIs(digest["truncated"], True)
        self.assertIs(digest["measured"], True)

    def test_the_digest_never_carries_credentials_or_remote_secrets(self) -> None:
        self.populate()
        poc = "implementations/demo/Poc"
        _write(self.root, ".papersmith/team.json", json.dumps({"members": [{"token": SECRETS[0]}]}))
        _write(self.root, f"{poc}/.remote-execution/ledger.jsonl", json.dumps(
            {"kind": "submitted", "submissionId": "s1", "entrypoint": SECRETS[1], "worker": SECRETS[2]}) + "\n")
        _write(self.root, f"{poc}/.remote-execution/token.json", json.dumps({"key": SECRETS[3]}))
        _write(self.root, "skills/kaggle-accounts/scripts/accounts_cli.py",
               'STORE_NAME = "store"\nSTORE_FILE = "accounts.json"\n')
        _write(self.root, "skills/kaggle-accounts/store/accounts.json", json.dumps({"key": SECRETS[4]}))
        _write(self.root, ".env", f"KAGGLE_KEY={SECRETS[5]}\n")
        _write(self.root, f"{poc}/Results/tables/.remote-execution/leak.csv", f"k\n{SECRETS[3]}\n")
        _write(self.root, f"{poc}/Results/tables/team.json", json.dumps([{"token": SECRETS[0]}]))
        digest = experiments_tutor.digest(self.root)
        self.assertEqual(digest["products"][0]["runs"], {"count": 1, "by_state": {"submitted": 1}})
        prompt = experiments_tutor.build_prompt(self.root, "Check my runs", "ask", "compute", {"turns": []})
        for text in (json.dumps(digest, ensure_ascii=False), prompt):
            for secret in SECRETS + ("team.json", ".remote-execution", "accounts.json", ".env"):
                self.assertNotIn(secret, text)


class ExperimentsTurnTests(_Root):
    def test_a_turn_records_the_operator_and_the_tutor(self) -> None:
        seen = {}

        def fake(root, system, prompt, images):
            seen.update(system=system, prompt=prompt, images=images)
            return dict(TURN), "fake"

        turn = experiments_tutor.run_turn(self.root, "Is my split leak-free?", "evaluate", "validation",
                                          runner=fake)
        self.assertEqual((turn["decision_area"], turn["agent"]), ("validation", "fake"))
        self.assertEqual(turn["deliberation_prompt"], TURN["deliberation_prompt"])
        thread = json.loads((self.root / ".papersmith/experiments-tutor/thread.json").read_text())
        self.assertEqual([t["role"] for t in thread["turns"]], ["reader", "tutor"])
        self.assertEqual({k: thread["turns"][0][k] for k in ("mode", "area", "message")},
                         {"mode": "evaluate", "area": "validation", "message": "Is my split leak-free?"})
        self.assertEqual(tutor.load_thread(self.root)["turns"], [])
        self.assertIn("mode: evaluate", seen["prompt"])
        self.assertIn("decision area: validation", seen["prompt"])
        self.assertIn("experiments tutor", seen["system"])
        self.assertEqual(seen["images"], [])
        experiments_tutor.run_turn(self.root, "And now?", "ask", "general", runner=fake)
        self.assertIn("Which subjects does the normalization see?", seen["prompt"])

    def test_bad_requests_and_malformed_answers_are_refused_not_recorded(self) -> None:
        ok = lambda *a: (dict(TURN), "f")  # noqa: E731
        for message, mode, area in (("hi", "grade-me", "general"), ("hi", "ask", "astrology"),
                                    ("  ", "ask", "general"), (3, "ask", "general")):
            with self.subTest(mode=mode, area=area), self.assertRaises(tutor.TutorError):
                experiments_tutor.run_turn(self.root, message, mode, area, runner=ok)
        for broken in ({**TURN, "decision_area": "astrology"}, {**TURN, "evidence": "a.md"},
                       {**TURN, "risks": [3]}, {**TURN, "deliberation_prompt": None},
                       {**TURN, "assessment": {**TURN["assessment"], "level": True}}, {"reply": "x"}):
            with self.subTest(broken=broken), self.assertRaises(tutor.TutorError):
                experiments_tutor.run_turn(self.root, "hi", "ask", "general",
                                           runner=lambda *a, b=broken: (b, "f"))
        self.assertEqual(tutor.load_thread(self.root, experiments_tutor.PROFILE)["turns"], [])

    def test_the_label_follows_the_level(self) -> None:
        answer = {**TURN, "assessment": {**TURN["assessment"], "level": 4, "label": "x"}}
        turn = experiments_tutor.run_turn(self.root, "hi", "ask", "general", runner=lambda *a: (answer, "f"))
        self.assertEqual(turn["assessment"]["label"], "defendible")

    def test_the_schema_and_the_read_only_command(self) -> None:
        schema = experiments_tutor.TURN_SCHEMA
        self.assertEqual(schema["required"], ["reply", "question", "assessment", "next_step",
                                              "decision_area", "evidence", "risks",
                                              "deliberation_prompt"])
        self.assertEqual(schema["properties"]["decision_area"]["enum"], list(AREAS) + ["general"])
        self.assertEqual(experiments_tutor.AREAS, AREAS + ("general",))
        self.assertEqual(experiments_tutor.PROFILE.modes, ("ask", "explain", "evaluate"))
        profile = experiments_tutor.PROFILE
        argv = tutor.claude_argv("/bin/claude", "S", "P", profile.schema, profile.tools)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Glob,Grep")
        for word in ("Bash", "Write", "Edit"):
            self.assertNotIn(word, argv[argv.index("--tools") + 1])
        self.assertEqual(profile.folder, (".papersmith", "experiments-tutor"))


SAME = {"Host": "127.0.0.1:8080", "Origin": "http://127.0.0.1:8080",
        "Sec-Fetch-Site": "same-origin", "Content-Type": "application/json",
        "X-Papersmith-Terminal": "1"}


class _Request:
    def __init__(self, headers=None, body=None, cookies=None) -> None:
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body
        self.cookies = dict(cookies or {})

    async def json(self):
        return self._body


def _route(app, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or ()):
            return route.endpoint
    raise AssertionError(f"no {method} {path}")


def _call(endpoint, *args):
    result = endpoint(*args)
    return asyncio.run(result) if asyncio.iscoroutine(result) else result


class ExperimentsRouteTests(_Root):
    BASE = "/api/terminal/tutor/experiments"

    def setUp(self) -> None:
        super().setUp()
        self.app = server.create_app(self.root, history_store=None, enable_terminal=True)
        self.cookie = {server.TERMINAL_COOKIE: self.app.state.terminal.token}
        self.calls = []
        original = tutor.run_agent
        self.addCleanup(setattr, tutor, "run_agent", original)
        tutor.run_agent = lambda *args, **kw: self.calls.append(kw) or (dict(TURN), "fake")

    def req(self, body=None, headers=SAME, cookie=True):
        return _Request(headers, body, self.cookie if cookie else None)

    def test_every_route_requires_the_secret_and_same_origin(self) -> None:
        body = {"message": "hi", "mode": "ask", "area": "general"}
        for path, method in (("/thread", "GET"), ("/thread", "DELETE"), ("/turn", "POST")):
            endpoint = _route(self.app, self.BASE + path, method)
            with self.subTest(path=path, method=method):
                self.assertEqual(_call(endpoint, self.req(body, cookie=False)).status_code, 403)
                self.assertEqual(_call(endpoint, self.req(body, {**SAME, "Origin": "http://evil.example"}))
                                 .status_code, 403)
        self.assertEqual(self.calls, [])

    def test_a_turn_runs_through_the_route_with_the_experiments_schema(self) -> None:
        turn = _route(self.app, self.BASE + "/turn", "POST")
        response = _call(turn, self.req({"message": "help", "mode": "explain", "area": "ablation"}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(bytes(response.body))["decision_area"], "validation")
        self.assertIs(self.calls[0]["schema"], experiments_tutor.TURN_SCHEMA)
        self.assertEqual(self.calls[0]["tools"], ("Read", "Glob", "Grep"))
        thread = _call(_route(self.app, self.BASE + "/thread", "GET"), self.req())
        self.assertEqual(len(json.loads(bytes(thread.body))["turns"]), 2)
        self.assertEqual(tutor.load_thread(self.root)["turns"], [])
        reset = _call(_route(self.app, self.BASE + "/thread", "DELETE"), self.req({}))
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(tutor.load_thread(self.root, experiments_tutor.PROFILE)["turns"], [])

    def test_an_invalid_turn_is_422_and_a_timeout_is_504(self) -> None:
        turn = _route(self.app, self.BASE + "/turn", "POST")
        self.assertEqual(_call(turn, self.req({"message": "hi", "mode": "ask", "area": "nope"})).status_code, 422)
        self.assertEqual(_call(turn, self.req(None)).status_code, 422)

        def slow(*args, **kw):
            raise subprocess.TimeoutExpired("claude", 300)

        tutor.run_agent = slow
        self.assertEqual(_call(turn, self.req({"message": "hi", "mode": "ask", "area": "general"})).status_code, 504)

    def test_the_tutor_is_off_when_the_terminal_is(self) -> None:
        app = server.create_app(self.root, history_store=None)
        response = _call(_route(app, self.BASE + "/thread", "GET"), self.req())
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
