"""The verification path carries no dependency on the operator's personal context.

**Why this exists, and what it cost to learn.** A suite that passes on the
machine that happens to have a memory provider installed proves nothing about
the machine that does not. This repository had exactly that shape: the canonical
context every harness entrypoint routes to declared an artifact store that named
a provider, and nothing checked it. The measured evidence is in
`openspec/changes/archive/`: twelve changes declared the memory-only `engram`
store, and when the provider was absent their artifacts landed in "a session
scratchpad ... that does not survive the session"
(`2026-08-21-the-pin-the-runner-can-actually-fetch/archive-report.md:9,355`).

**The load-bearing control is not in this file.** `scripts/clean_context_gate.py`
runs the declared gate under an empty `HOME` and under one carrying the shapes a
developer's machine has (`.pi/agent`, `.agents/skills`, `.claude/skills`,
`.engram`), and fails if the two disagree. That is the control that can detect a
personal context dependency, because it observes behavior. The rules below are a
regression lock over the declarations and calls that are legible statically —
they narrow the surface, they do not close it. A future document could require a
provider in prose no pattern here parses; the differential control is what
catches the consequence.

**Rule B passes before and after this feature's edits**, because the tracked tree
holds zero provider calls. That is stated rather than hidden: it is a lock
against a future call, not evidence that the provider-absent path was exercised.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

FORGE = Path(__file__).resolve().parent.parent
CONFIG = FORGE / "openspec" / "config.yaml"
CLEAN_CONTEXT_SCRIPT = FORGE / "scripts" / "clean_context_gate.py"

#: gentle-pi's own accepted artifact-store vocabulary, quoted from
#: `gentle-pi/lib/sdd-preflight.ts` (`- Artifact store: (?:openspec|engram|hybrid|none)`).
#: Quoted rather than read because this guard has to run where gentle-pi is not
#: installed (CI, and any user's machine), which is the whole point. The cost of
#: quoting is that a change to that vocabulary would not be seen here; the cost
#: of reading is that the guard would silently skip on exactly the machines this
#: feature exists for. The smaller cost was chosen deliberately.
ACCEPTED_MODES = ("openspec", "engram", "hybrid", "none")

#: Of those four, the two that need no provider at all. `engram` is memory-only
#: and `hybrid` writes the file half but still names a provider as a store; both
#: are what this repository must not declare for its own artifacts.
PROVIDER_FREE_MODES = ("openspec", "none")

#: Completed changes are an audit trail and are never rewritten, so a guard that
#: demanded history be edited would be demanding a lie. The rule is about the
#: present-tense declaration.
HISTORY_PREFIX = "openspec/changes/archive/"

#: A declaration is a LINE that states the store, never a mention of one. Every
#: pattern is anchored for that reason: `odd/tasks/engram-optional.md` quotes
#: `both`, `engram` and `hybrid` while discussing them, and a scanner that read
#: those quotations as declarations would fire on its own documentation.
DECLARATION_PATTERNS = (
    # `- Artifact store: `both` (hybrid: ...)` — the canonical context's shape.
    re.compile(r"(?im)^\s*[-*]\s*artifact store\s*:\s*`?([a-z]+)`?"),
    # `store: openspec` — the configuration's shape.
    re.compile(r"(?im)^\s*store\s*:\s*`?([a-z]+)`?\s*$"),
    # `Directory created by sdd-init (hybrid) on ...` — the .gitkeep's shape.
    re.compile(r"(?im)^\s*[-*]?\s*directory created by sdd-init\s*\(([a-z]+)\)"),
)

#: A tracked file that instructs an agent to mirror artifacts into a provider is
#: the same defect as declaring that provider as a store, spelled differently.
ENGRAM_MIRROR_PATTERN = re.compile(r"(?im)^\s*[-*]\s*engram mirrors?\s*:")

#: The provider's tool namespace. Both spellings are real: the MCP server exposes
#: `engram_mem_*`, and its Pi-native aliases are `mem_*`. Nineteen tools exist;
#: naming them would be a roster that rots and misses the twentieth, so the
#: namespace is what is matched.
MEMORY_TOOL_PATTERN = re.compile(r"\b(?:mem_[a-z_]+|engram_mem_[a-z_]+)\b")

CODE_SUFFIXES = (".py", ".ts", ".mjs", ".js", ".sh")

#: This file, excluded from the call scan. A scanner has to contain the pattern it
#: scans for, and the inversion controls below plant provider calls on purpose, so
#: a scan that reached this file would fire on its own fixtures and prove nothing.
#: Excluded by identity rather than by name: the one file that cannot be checked
#: for a pattern is the file that holds it.
SELF = Path(__file__).resolve()


def tracked_files() -> list[Path]:
    """Every tracked file except completed history, by `git ls-files`.

    Derived from the repository rather than listed, so a file added tomorrow is
    covered the day it lands.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=str(FORGE),
        capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    return [
        FORGE / name for name in listed
        if name and not name.startswith(HISTORY_PREFIX)
    ]


def read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def configured_store_mode() -> str | None:
    document = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return document.get("store") if isinstance(document, dict) else None


def scan_declarations(sources) -> list[tuple[str, int, str]]:
    """`[(label, line, mode)]` for every store declaration in `sources`.

    Takes `(label, text)` pairs rather than reading the tree itself, so the
    inversion controls below drive this exact code path against a planted
    declaration instead of re-implementing the match.
    """
    found = []
    for label, text in sources:
        for pattern in DECLARATION_PATTERNS:
            for match in pattern.finditer(text):
                found.append((label, text[: match.start()].count("\n") + 1, match.group(1)))
    return found


def scan_engram_mirrors(sources) -> list[tuple[str, int]]:
    found = []
    for label, text in sources:
        for match in ENGRAM_MIRROR_PATTERN.finditer(text):
            found.append((label, text[: match.start()].count("\n") + 1))
    return found


def scan_memory_tool_calls(sources) -> list[tuple[str, int, str]]:
    found = []
    for label, text in sources:
        for match in MEMORY_TOOL_PATTERN.finditer(text):
            found.append((label, text[: match.start()].count("\n") + 1, match.group(0)))
    return found


def text_sources(paths) -> list[tuple[str, str]]:
    sources = []
    for path in paths:
        text = read(path)
        if text is not None:
            sources.append((str(path.relative_to(FORGE)), text))
    return sources


class ArtifactStoreDeclarationTests(unittest.TestCase):
    """The repository declares one store, and it is one that needs no provider."""

    def test_the_configuration_declares_a_store_mode(self):
        """The expected value is derived from the repository's own configuration
        rather than restated in this guard. A guard whose expectation lives in
        the same change that edits the file it checks is a guard that agrees with
        whatever it is handed."""
        self.assertIsNotNone(
            configured_store_mode(),
            f"{CONFIG.relative_to(FORGE)} declares no `store:` mode, so this "
            "guard has nothing to derive its expectation from. The declaration "
            "must live in the repository, not in the operator's head")

    def test_the_configured_mode_needs_no_provider(self):
        mode = configured_store_mode()
        self.assertIn(
            mode, PROVIDER_FREE_MODES,
            f"the configured artifact store is {mode!r}, which needs a memory "
            f"provider. This repository's verification path must work on a "
            f"machine that has none, so the store must be one of "
            f"{PROVIDER_FREE_MODES}. The generator's accepted vocabulary is "
            f"{ACCEPTED_MODES} (gentle-pi `lib/sdd-preflight.ts`); `engram` is "
            "memory-only and `hybrid` still names a provider as a store")

    def test_the_scan_reaches_a_declaration(self):
        """A scope that silently found nothing would let every assertion below
        pass over an empty set, which reads exactly like a clean result."""
        found = scan_declarations(text_sources(tracked_files()))
        self.assertTrue(
            found,
            "no artifact-store declaration was found anywhere in the tracked "
            "tree, so this guard is checking nothing -- either the declaration "
            "shape changed or the scan scope is broken")

    def test_every_tracked_declaration_carries_the_configured_mode(self):
        expected = configured_store_mode()
        found = scan_declarations(text_sources(tracked_files()))
        mismatched = [
            f"{label}:{line} declares {mode!r}"
            for label, line, mode in found if mode != expected
        ]
        self.assertEqual(
            mismatched, [],
            f"these tracked files declare an artifact store other than the "
            f"configured {expected!r}. A declaration is what an agent reads "
            "before it decides where an artifact lives, so a stale one is a "
            "provider-shaped instruction that outlives its removal:\n  "
            + "\n  ".join(mismatched))

    def test_no_tracked_file_declares_an_engram_mirror(self):
        found = scan_engram_mirrors(text_sources(tracked_files()))
        self.assertEqual(
            found, [],
            "these tracked files instruct an agent to mirror artifacts into a "
            "memory provider. That is the store declaration spelled a second "
            "way, and a user without the provider cannot carry it out:\n  "
            + "\n  ".join(f"{label}:{line}" for label, line in found))


class MemoryProviderCallTests(unittest.TestCase):
    """No tracked code calls a provider tool. A regression lock, not proof."""

    def test_no_tracked_code_calls_a_memory_provider_tool(self):
        paths = [
            path for path in tracked_files()
            if path.suffix in CODE_SUFFIXES and path.resolve() != SELF
        ]
        found = scan_memory_tool_calls(text_sources(paths))
        self.assertEqual(
            found, [],
            "tracked code calls a memory-provider tool. The provider is a "
            "harness package, not a papersmith dependency, so this call "
            "resolves on the maintainer's machine and nowhere else:\n  "
            + "\n  ".join(f"{label}:{line} calls {name}" for label, line, name in found))


class ScannerInversionTests(unittest.TestCase):
    """Every scanner above is proven to fire, on a planted input.

    A scanner that never fires and a scanner that finds nothing are
    indistinguishable from the outside, which is the `kind=guard-never-fires`
    defect this repository's own audit doctrine names. These controls drive the
    same functions the rules above use.
    """

    def test_the_declaration_scanner_fires_on_a_planted_mismatch(self):
        planted = [("planted.md", "- Artifact store: `engram` (memory only)\n")]
        found = scan_declarations(planted)
        self.assertEqual(
            [(label, mode) for label, _, mode in found], [("planted.md", "engram")],
            "the declaration scanner did not see a declaration planted directly "
            "in front of it, so its clean result above proves nothing")

    def test_the_declaration_scanner_sees_the_gitkeep_shape(self):
        planted = [("planted/.gitkeep", "Directory created by sdd-init (hybrid) on 2026-09-09\n")]
        self.assertEqual(
            [mode for _, _, mode in scan_declarations(planted)], ["hybrid"],
            "the scanner misses the shape a `.gitkeep` actually uses, so one "
            "declaration could hide behind the other's pattern")

    def test_the_mirror_scanner_fires_on_a_planted_mirror(self):
        planted = [("planted.md", "- Engram mirrors: sdd/example/design\n")]
        self.assertEqual(
            [label for label, _ in scan_engram_mirrors(planted)], ["planted.md"],
            "the mirror scanner did not see a mirror declaration planted "
            "directly in front of it")

    def test_the_call_scanner_fires_on_a_planted_call(self):
        planted = [("planted.py", "def f():\n    mem_save(title='x')\n")]
        self.assertEqual(
            [name for _, _, name in scan_memory_tool_calls(planted)], ["mem_save"],
            "the call scanner did not see a provider call planted directly in "
            "front of it, so `MemoryProviderCallTests` passing proves nothing")

    def test_the_call_scanner_sees_the_mcp_spelling(self):
        planted = [("planted.py", "engram_mem_search(query='x')\n")]
        self.assertEqual(
            [name for _, _, name in scan_memory_tool_calls(planted)],
            ["engram_mem_search"],
            "the scanner covers only the Pi-native `mem_*` spelling and misses "
            "the MCP `engram_mem_*` rows")

    def test_the_call_scan_does_not_reach_this_file(self):
        """The exclusion that keeps the rule honest. Without it the scan fires on
        this file's own planted fixtures, which is a failure that says nothing
        about papersmith and would train a reader to ignore the rule."""
        self.assertNotIn(
            SELF, [path.resolve() for path in tracked_files()
                   if path.suffix in CODE_SUFFIXES and path.resolve() != SELF],
            "this guard's own file is still in the call scan, so its fixtures "
            "make the rule fail for a reason that is not a dependency")


class DifferentialControlTests(unittest.TestCase):
    """The control that can actually detect a personal-context dependency.

    A comparator that never reports a difference is indistinguishable from a
    verification path that has none, which is the `kind=guard-never-fires`
    defect this repository's audit doctrine names. These drive the exact
    functions `scripts/clean_context_gate.py` runs.
    """

    def module(self):
        """Imported by path: `scripts/` is not a package, and the point is to
        test the function the script runs, not a re-implementation of it."""
        spec = importlib.util.spec_from_file_location(
            "papersmith_clean_context_gate", CLEAN_CONTEXT_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def result(self, home, code, failures=()):
        return {"home": home, "code": code, "failures": list(failures)}

    def test_the_comparator_fires_on_a_planted_disagreement(self):
        control = self.module()
        differences = control.compare(
            self.result("empty", 0), self.result("decoy", 1))
        self.assertTrue(
            differences,
            "the comparator called two runs with different exit codes equal, so "
            "a green differential control would prove nothing")

    def test_the_comparator_names_a_test_that_fails_under_one_home_only(self):
        control = self.module()
        differences = control.compare(
            self.result("empty", 1), self.result("decoy", 1, ["FAILED tests/test_x.py::test_y"]))
        self.assertTrue(
            any("test_x.py::test_y" in line for line in differences),
            f"a test failing under one home and not the other was not named: {differences}")

    def test_a_baseline_that_fails_under_the_empty_home_is_reported(self):
        control = self.module()
        failing = self.result("empty", 1, ["FAILED tests/test_x.py::test_y"])
        self.assertTrue(
            control.baseline_failures(failing),
            "a gate that fails identically under both homes was called clean, so "
            "this step could not stand in for a plain run of the suite")
        self.assertEqual(
            control.compare(failing, self.result("decoy", 1, failing["failures"])), [],
            "agreeing failures are still not a disagreement; the baseline check "
            "is separate from the comparator")

    def test_the_failure_details_keep_what_a_failing_test_said(self):
        control = self.module()
        log = ("tests/test_x.py F\n"
               "E   AssertionError: read-only tools changed the workspace: tool: a.json\n"
               "FAILED tests/test_x.py::test_y - AssertionError: read-only tools changed\n"
               "FAILED tests/test_x.py::test_z\n"
               "1 failed, 2 passed\n")
        self.assertEqual(control.failure_details(log), [
            "E   AssertionError: read-only tools changed the workspace: tool: a.json",
            "FAILED tests/test_x.py::test_y - AssertionError: read-only tools changed"])
        self.assertEqual(control.failure_details("E   x\n" * 100), ["E   x"] * control.DETAIL_LINES)

    def test_a_baseline_that_passes_under_the_empty_home_is_silent(self):
        control = self.module()
        self.assertEqual(control.baseline_failures(self.result("empty", 0)), [])

    def test_the_comparator_is_silent_when_the_runs_agree(self):
        control = self.module()
        same = ["FAILED tests/test_x.py::test_y", "not ok a suite"]
        self.assertEqual(
            control.compare(self.result("empty", 1, same), self.result("decoy", 1, reversed(same))),
            [],
            "the comparator reports a difference between two runs that failed "
            "the same tests in a different order, which would make the control "
            "noisy enough to be ignored")

    def test_the_failure_signature_reads_both_halves(self):
        control = self.module()
        pytest_output = "FAILED tests/test_a.py::test_b\nERROR tests/test_c.py\n1 failed"
        tap_output = "not ok 3 - a suite name\n# fail 1\n"
        self.assertEqual(
            control.failure_signature(pytest_output),
            ["ERROR tests/test_c.py", "FAILED tests/test_a.py::test_b"],
            "the signature does not read pytest's own failure lines")
        self.assertEqual(
            control.failure_signature(tap_output), ["not ok a suite name"],
            "the signature does not read a TAP-shaped Node run")

    def test_the_failure_signature_reads_the_measured_node_shape(self):
        """The shape `node --test` actually prints, measured, not the one TAP
        would print.

        This control previously planted `not ok 3 - ...` and asserted the reader
        saw it, while a real run emitted `x a suite that fails (0.95ms)` and the
        reader saw nothing: an inversion control proving a reader on a line no
        run produces, which is the `kind=guard-never-fires` defect this
        repository's audit doctrine names.
        """
        control = self.module()
        measured = (
            "\u2716 a suite that fails (0.955203ms)\n"
            "\u2714 a suite that passes (0.133999ms)\n"
            "\u2716 failing tests:\n"
            "\u2716 a suite that fails (0.955203ms)\n")
        self.assertEqual(
            control.failure_signature(measured),
            ["node a suite that fails"],
            "the reader does not see the Node shape a real run emits, so the "
            "Node half compares exit codes alone")

    def test_an_unrunnable_gate_is_detected(self):
        """A gate that never started is not a differential result."""
        control = self.module()
        self.assertTrue(
            control.gate_could_not_run("", 127),
            "exit 127 -- the interpreter is not there -- was read as a test result")
        self.assertTrue(
            control.gate_could_not_run(
                "sh: .micromamba/envs/papersmith/bin/pytest: No such file or directory", 1),
            "a missing interpreter reported in the output was not detected")

    def test_a_normally_failing_run_is_not_called_unrunnable(self):
        """Non-vacuity: a red gate must stay a red gate, not become a broken
        control, or the step would fail for the wrong reason on every red run."""
        control = self.module()
        self.assertFalse(
            control.gate_could_not_run("FAILED tests/test_a.py::test_b\n1 failed", 1),
            "an ordinary failing run was mistaken for a gate that could not run")
        self.assertFalse(control.gate_could_not_run("", 0))

    def test_the_comparator_refuses_an_unrunnable_gate(self):
        """The hole this closes: identical exit codes and identical (empty)
        failure sets read as agreement even when neither run started."""
        control = self.module()
        unrunnable = {"home": "empty", "code": 127, "failures": [], "unrunnable": True}
        same = {"home": "decoy", "code": 127, "failures": [], "unrunnable": True}
        differences = control.compare(unrunnable, same)
        self.assertTrue(
            differences,
            "two runs of a gate that never started were reported as identical, "
            "so a green control would not mean the gate ran")
        self.assertTrue(any("could not run" in line for line in differences), differences)

    def test_the_failure_signature_reads_subfailures(self):
        """Measured the hard way: without this, a real run reported three
        failing tests where pytest counted six, because `SUBFAILED` lines do not
        match `^(FAILED|ERROR)`. Two runs differing only in a subfailure would
        have been called equal -- an under-observing control, which is the same
        defect class this whole feature exists to close."""
        control = self.module()
        line = ("SUBFAILED(document='a/b.py') tests/test_x.py::ProseTests::test_y")
        self.assertEqual(
            control.failure_signature(line),
            ["SUBFAILED document='a/b.py' tests/test_x.py::ProseTests::test_y"],
            "a subfailure is invisible to the signature, so the differential "
            "control cannot see a difference that lives in one")

    def test_the_decoy_home_carries_personal_context(self):
        """Non-vacuous: a decoy home that held nothing would prove only that
        the gate does not read a directory that does not exist."""
        control = self.module()
        with tempfile.TemporaryDirectory() as holder:
            root = Path(holder)
            decoy = control.build_decoy_home(root)
            empty = control.build_empty_home(root)
            planted = sorted(
                str(path.relative_to(decoy))
                for path in decoy.rglob("*") if path.is_file())
            self.assertTrue(
                planted,
                "the decoy home is empty, so the differential control compares "
                "two bare homes and cannot fail")
            self.assertEqual(
                sorted(empty.rglob("*")), [],
                "the empty home is not empty, so it is not the baseline the "
                "control claims")
            self.assertTrue(
                any(name.endswith("settings.json") for name in planted),
                f"the decoy carries no agent settings to be ignored: {planted}")

    def test_the_gate_is_read_from_the_manifest(self):
        """Derived, never restated: a restated command string would have to be
        edited alongside the defect it was meant to catch."""
        control = self.module()
        stages = control.declared_gate()
        self.assertTrue(stages, "the declared gate is empty")
        self.assertEqual(
            control.half_stages("node"), [["npm", "run", "test:node"]],
            "the Node half is not resolved from the manifest's test:all script")
        self.assertEqual(
            control.half_stages("python"), [["npm", "run", "test:py"]],
            "the Python half is not resolved from the manifest's test:all script")
        # The interpreter is one delegation deeper than test:all, so it is asked
        # of the manifest rather than assumed. A drift here would make this
        # control run a different pytest than the gate does, and both would
        # still call themselves the declared gate.
        manifest = json.loads((FORGE / "package.json").read_text(encoding="utf-8"))
        self.assertIn(
            ".micromamba/envs/papersmith/bin/pytest", manifest["scripts"]["test:py"],
            "package.json's test:py no longer names the provisioned interpreter, "
            "so the differential control would run a different pytest than the "
            "gate it claims to re-run")


if __name__ == "__main__":
    unittest.main()
