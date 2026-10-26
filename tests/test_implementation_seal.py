"""The stdout characterization seal for `proposal-implementation`'s CLI.

Built across `openspec/changes/archive/2026-09-11-the-seal-before-the-cut/`: proposal.md, design.md,
tasks.md. Proves preservation across the later profile-driven extraction
(`the-engine-leaves-its-skill` and its successors) by capturing byte-exact stdout
and exit status for all 20 subcommands against a fixed corpus, and hosts the two
sanctioned behaviour changes (F3, F5) under a declared-delta discipline.

This module is built incrementally, phase by phase, per tasks.md:

- Phase 2 (this section): F3's two permanent anchor/behaviour tests.
- Phase 4: threat-matrix RED tests for the harness itself.
- Phase 5: normalizer mutation proofs (reach + guard pairs).
- Phase 7: the comparison suite, coverage tests, membership tests.
- Phase 8: F5's identity tests and the zero-delta re-comparison.

Governs the seal only, not the CLI's existing runtime behavior — this file adds
no assertion about the CLI's non-F3/F5 behaviour that isn't already covered
elsewhere.
"""

import hashlib
import inspect
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
#: The published launcher (meaning 1/3) -- unchanged path.
CLI = FORGE / "skills/proposal-implementation/scripts/implementation_cli.py"
#: The engine source (meaning 2) -- `impl` below resolves here, never to
#: the launcher, which exposes none of the engine's attributes (design.md
#: D1).
ENGINE = FORGE / "skills/_core/implementation/engine/implementation_engine.py"
sys.path.insert(0, str(ENGINE.parent))
from domain_profile import seeded_profile  # noqa: E402  (path set above)
with seeded_profile(FORGE / "skills/proposal-implementation/impl_profile.py"):
    import implementation_engine as impl  # noqa: E402  (path set above)

TESTS_DIR = Path(__file__).resolve().parent
SEAL_DIR = TESTS_DIR / "seal"
sys.path.insert(0, str(TESTS_DIR))
from seal import corpus as seal_corpus  # noqa: E402  (path set above)
from seal import harness as seal_harness  # noqa: E402
from seal import normalize as seal_normalize  # noqa: E402
import seal_capture  # noqa: E402  (the capture entry point itself, for its constants)


def _load_cases() -> list:
    return json.loads(seal_capture.CASES_PATH.read_text(encoding="utf-8"))


def _load_digests() -> dict:
    return json.loads(seal_capture.DIGESTS_PATH.read_text(encoding="utf-8"))


def _load_unsealed() -> dict:
    return json.loads(seal_capture.UNSEALED_PATH.read_text(encoding="utf-8"))


#: Built once per `unittest discover` process, lazily, on first use — the
#: comparison suite runs each case ONCE (never twice; that is capture's
#: job, design.md D1/D5), and every test class below that needs live
#: output shares this single build.
_CAPTURED_RESULTS: dict = {}


def _captured_results() -> dict:
    if not _CAPTURED_RESULTS:
        cases = _load_cases()
        with tempfile.TemporaryDirectory(prefix="seal-compare-corpus-") as tmp:
            roots = seal_corpus.build(Path(tmp) / "corpus")
            scratch_root = (impl.FORGE_ROOT / "implementations"
                           / f"_seal_compare_{os.getpid()}")
            scratch_root.mkdir(parents=True)
            try:
                for case in cases:
                    _CAPTURED_RESULTS[case["id"]] = seal_harness.run_case(
                        case, roots, scratch_root=scratch_root)
            finally:
                shutil.rmtree(scratch_root, ignore_errors=True)
    return _CAPTURED_RESULTS


class F3AnchorTests(unittest.TestCase):
    """F3 — the five `REVISION_UNREADABLE` refusal sites must read the
    directory the code actually consults (`proposals_root()`), never spell a
    hardcoded `FORGE_ROOT / 'proposals'` the `IMPLEMENTATION_PROPOSALS`
    override silently bypasses (design.md D7, f3-message-delta.md).

    **Anchor discipline** (recorded scar: an anchor that matched is not a
    mutation that ran; `sd -s` can exit 0 and change nothing). This reads the
    SOURCE directly, not a byproduct of the CLI's own behaviour.
    """

    def test_no_refusal_names_a_directory_the_code_never_read(self):
        source = ENGINE.read_text(encoding="utf-8")
        self.assertEqual(source.count("FORGE_ROOT / 'proposals'"), 0)
        self.assertEqual(source.count("{proposals_root()}"), 5)

    def _box(self):
        box = (FORGE / "implementations"
               / f"_seal_f3_override_{os.getpid()}_{id(self)}")
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        return box

    def test_a_refusal_under_an_override_names_the_override(self):
        """The rendering the message-count assertion above cannot see: run
        `admit` with `IMPLEMENTATION_PROPOSALS` pointed at an empty
        directory and an unreadable `--revision`. The refusal must name
        THAT directory, never `FORGE_ROOT / "proposals"` — the exact bug
        F3 fixes. `proposals_root()` renders byte-identically to the old
        literal only when the override is unset; this is the one case
        where it must not."""
        override = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, override, ignore_errors=True)
        box = self._box()
        env = dict(os.environ)
        env["IMPLEMENTATION_PROPOSALS"] = str(override)
        proc = subprocess.run(
            [sys.executable, str(CLI), "admit", "--target", str(box),
             "--name", "Method", "--revision", "does-not-exist.md"],
            capture_output=True, text=True, cwd=FORGE, env=env)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "REVISION_UNREADABLE")
        self.assertIn(str(override), payload["detail"])
        self.assertNotIn(str(FORGE / "proposals"), payload["detail"])


class RosterValidationTests(unittest.TestCase):
    """Threat-matrix guards over the roster VALIDATOR itself (tasks 4.1,
    4.3) — synthetic bad cases, never the real 29, so a legitimate case
    needing `$$` (compose's LaTeX) or `#` (settle's heading) is never
    mistaken for an attack. `shell=False` makes every character harmless to
    actually run; this is belt-and-braces against a case authored as if a
    shell would parse it."""

    def test_refuses_a_case_whose_argv_contains_a_shell_metacharacter(self):
        bad = {"id": "bad", "command": "verify",
              "argv": ["--target", "<TARGET>; rm -rf /"]}
        with self.assertRaises(seal_harness.RosterValidationError):
            seal_harness.validate_case(bad)

    def test_a_legitimate_case_with_dollar_signs_is_not_refused(self):
        """`compose`'s real `--entry-text` carries literal `$$` for a LaTeX
        display block — the guard must not flag it."""
        benign = {"id": "benign", "command": "compose",
                 "argv": ["--target", "<TARGET>", "--finding", "x",
                          "--entry-text", "$$\nc = d \\tag{2.1}\n$$"]}
        seal_harness.validate_case(benign)  # must not raise

    def test_refuses_a_case_whose_target_is_not_the_placeholder(self):
        bad = {"id": "bad", "command": "verify",
              "argv": ["--target", "/etc/passwd", "--name", "Seal"]}
        with self.assertRaises(seal_harness.RosterValidationError):
            seal_harness.validate_case(bad)

    def test_the_real_roster_passes_validation(self):
        seal_harness.validate_roster(_load_cases())  # must not raise


class EnvAllowListTests(unittest.TestCase):
    """Task 4.2: the child env builder emits no key outside the allow-list,
    and `IMPLEMENTATION_PROPOSALS` only when the case says so (design.md D2)."""

    def _roots(self):
        return seal_corpus.Roots(
            root=Path("/x"), fixture_a=Path("/x/A"), fixture_b=Path("/x/B"),
            fixture_t=Path("/x/T"), proposals=Path("/x/P"), plan_template={})

    def test_env_builder_emits_no_key_outside_the_allow_list(self):
        roots = self._roots()
        for proposals_flag in (True, False):
            env = seal_harness.build_env({"proposals": proposals_flag}, roots)
            self.assertTrue(set(env) <= seal_harness.ALLOWED_ENV_KEYS,
                            set(env) - seal_harness.ALLOWED_ENV_KEYS)

    def test_implementation_proposals_only_present_when_the_case_says_so(self):
        roots = self._roots()
        self.assertNotIn("IMPLEMENTATION_PROPOSALS",
                         seal_harness.build_env({"proposals": False}, roots))
        self.assertIn("IMPLEMENTATION_PROPOSALS",
                      seal_harness.build_env({"proposals": True}, roots))


class SubprocessTimeoutTests(unittest.TestCase):
    """Task 4.4: every `subprocess.run` call carries `timeout=120`; a
    timeout is a hard failure, never routed to `unsealed.json`."""

    def test_every_subprocess_run_call_in_the_harness_carries_the_timeout(self):
        source = (SEAL_DIR / "harness.py").read_text(encoding="utf-8")
        calls = source.count("subprocess.run(")
        self.assertGreaterEqual(calls, 1)
        self.assertEqual(seal_harness.TIMEOUT_SECONDS, 120)
        self.assertEqual(source.count("timeout=TIMEOUT_SECONDS"), calls)


class NormalizerMutationTests(unittest.TestCase):
    """Phase 5: each normalizer's reach pair (its named mutation collapses)
    and guard pair (real adjacent output stays distinct), per design.md D4."""

    def _roots(self, **overrides):
        base = dict(target=Path("/scratch/case1"), corpus=Path("/tmp/corpus9"),
                   forge=Path("/repo"), proposals=Path("/tmp/corpus9/P"))
        base.update(overrides)
        return seal_normalize.Roots(**base)

    # --- N1 iso8601_timestamps ---

    def test_n1_reach_two_timestamp_only_samples_collapse(self):
        roots = self._roots()
        a = 'X "at": "2026-09-10T12:00:00Z" Y'
        b = 'X "at": "2026-09-10T12:00:07Z" Y'
        self.assertNotEqual(a, b)  # sanity: they DO differ before normalizing
        self.assertEqual(seal_normalize.n1_iso8601_timestamps(a, roots),
                         seal_normalize.n1_iso8601_timestamps(b, roots))

    def test_n1_guard_bare_dates_stay_distinct(self):
        roots = self._roots()
        a = seal_normalize.n1_iso8601_timestamps("revision 2026-09-10", roots)
        b = seal_normalize.n1_iso8601_timestamps("revision 2026-09-11", roots)
        self.assertNotEqual(a, b)

    # --- N2 absolute_roots ---

    def test_n2_reach_tmpdir_only_difference_collapses(self):
        roots1 = self._roots(target=Path("/tmp/aaa/case1"))
        roots2 = self._roots(target=Path("/tmp/bbb/case1"))
        text1 = f"path: {roots1.target}/x.py"
        text2 = f"path: {roots2.target}/x.py"
        self.assertEqual(seal_normalize.n2_absolute_roots(text1, roots1),
                         seal_normalize.n2_absolute_roots(text2, roots2))

    def test_n2_guard_sibling_modules_stay_distinct(self):
        roots = self._roots()
        a = seal_normalize.n2_absolute_roots("src/Seal/__init__.py", roots)
        b = seal_normalize.n2_absolute_roots("src/Seal/steps.py", roots)
        self.assertNotEqual(a, b)

    def test_n2_guard_unrelated_absolute_path_untouched(self):
        roots = self._roots()
        self.assertEqual(seal_normalize.n2_absolute_roots("/usr/bin/x", roots),
                         "/usr/bin/x")

    # --- N3 cli_invocation (narrowed, per the coordinator's directed fix) ---

    def test_n3_reach_interpreter_only_difference_collapses(self):
        """Two samples differing only in the interpreter path collapse.
        `n3_cli_invocation` reads `sys.executable` fresh at call time, so a
        temporary monkeypatch between two builds simulates two different
        machines' own captures, each correctly normalized against ITS OWN
        interpreter."""
        roots = self._roots()
        original = sys.executable
        try:
            sys.executable = "/opt/interpreter-a/bin/python3"
            text_a = (f"cmd: {shlex.quote(sys.executable)} "
                     "/repo/skills/proposal-implementation/scripts/"
                     "implementation_cli.py step")
            normalized_a = seal_normalize.n3_cli_invocation(text_a, roots)
            sys.executable = "/opt/interpreter-b/bin/python3"
            text_b = (f"cmd: {shlex.quote(sys.executable)} "
                     "/repo/skills/proposal-implementation/scripts/"
                     "implementation_cli.py step")
            normalized_b = seal_normalize.n3_cli_invocation(text_b, roots)
        finally:
            sys.executable = original
        self.assertNotEqual(text_a, text_b)  # sanity
        self.assertEqual(normalized_a, normalized_b)
        self.assertIn("<PYTHON>", normalized_a)

    def test_n3_guard_cli_path_difference_survives(self):
        """`python3 other.py` remains different from `python3 another.py`
        — the CLI_PATH difference must survive N3 (and, per the coordinator
        fix, N2 too — see the pinned assertion below)."""
        roots = self._roots()
        interpreter = shlex.quote(sys.executable)
        a = f"cmd: {interpreter} /repo/scripts/other.py step"
        b = f"cmd: {interpreter} /repo/scripts/another.py step"
        self.assertNotEqual(seal_normalize.n3_cli_invocation(a, roots),
                            seal_normalize.n3_cli_invocation(b, roots))

    def test_the_sealed_cli_path_names_the_launcher(self):
        """N3's pinned companion (design.md D4/D5, the coordinator's
        directed fix): after full `normalize()`, every case whose captured
        stdout embeds `CLI_INVOCATION`-derived text contains the literal,
        repo-relative launcher path. Verified live against gate-e1/step/
        offer-e1 during apply, 2026-09-11 — this is the single most
        load-bearing mutation in the change (design.md D4)."""
        expected = ("<FORGE>/skills/proposal-implementation/scripts/"
                   "implementation_cli.py")
        results = _captured_results()
        carriers = [cid for cid, result in results.items()
                   if "implementation_cli.py" in result.stdout_text]
        self.assertTrue(carriers)
        for case_id in carriers:
            with self.subTest(case=case_id):
                self.assertIn(expected, results[case_id].stdout_text)

    def test_a_different_resolved_cli_path_would_have_been_caught(self):
        """The mutation: substitute a different resolved path for the
        launcher in the RAW (pre-normalization) text before calling
        `normalize()` — the pinned assertion above must go red."""
        roots = self._roots(forge=Path("/repo"))
        raw = ('{"resolve": {"command": "' + shlex.quote(sys.executable) + ' '
              + shlex.quote(str(roots.forge / "skills/proposal-implementation"
                                "/scripts/implementation_cli.py"))
              + ' step --target x"}}')
        normalized = seal_normalize.normalize(raw, roots)
        expected = ("<FORGE>/skills/proposal-implementation/scripts/"
                   "implementation_cli.py")
        self.assertIn(expected, normalized)

        mutated_raw = raw.replace("implementation_cli.py", "engine.py")
        mutated_normalized = seal_normalize.normalize(mutated_raw, roots)
        self.assertNotIn(expected, mutated_normalized)
        self.assertIn(
            "<FORGE>/skills/proposal-implementation/scripts/engine.py",
            mutated_normalized)

    # --- N4 session_identity (pinned, not erased) ---

    ALLOWED_SESSIONS = frozenset({"seal-s1", "seal-s2"})

    def test_n4_no_session_outside_the_pinned_set(self):
        for case in _load_cases():
            argv = case["argv"]
            if "--session" in argv:
                value = argv[argv.index("--session") + 1]
                self.assertIn(value, self.ALLOWED_SESSIONS, case["id"])

    def test_n4_reach_a_changed_session_literal_moves_the_digest(self):
        """Session identity REACHES the sealed bytes rather than being
        erased: change one case's `--session`, its digest must move.
        `defect`'s output echoes `session` directly and is otherwise fully
        deterministic (the only other varying field, `at`, is N1-normalized
        uniformly), so it isolates the session's own effect cleanly."""
        cases = _load_cases()
        case = next(c for c in cases if c["id"] == "defect")
        original = json.loads(json.dumps(case))
        mutated = json.loads(json.dumps(case))
        argv = mutated["argv"]
        argv[argv.index("--session") + 1] = "seal-s2"

        with tempfile.TemporaryDirectory(prefix="seal-n4-") as tmp:
            roots = seal_corpus.build(Path(tmp) / "corpus")
            scratch_root = impl.FORGE_ROOT / "implementations" / f"_seal_n4_{os.getpid()}"
            scratch_root.mkdir(parents=True)
            try:
                result_original = seal_harness.run_case(original, roots, scratch_root=scratch_root)
                result_mutated = seal_harness.run_case(mutated, roots, scratch_root=scratch_root)
            finally:
                shutil.rmtree(scratch_root, ignore_errors=True)
        self.assertNotEqual(seal_harness.digest_result(result_original)["sha256"],
                            seal_harness.digest_result(result_mutated)["sha256"])

    # --- N5 git_shas ---

    def test_n5_reach_forty_hex_collapses(self):
        roots = self._roots()
        a = "sha " + "a" * 40
        b = "sha " + "b" * 40
        self.assertEqual(seal_normalize.n5_git_shas(a, roots),
                         seal_normalize.n5_git_shas(b, roots))
        self.assertIn("<GITSHA>", seal_normalize.n5_git_shas(a, roots))

    def test_n5_guard_sixty_four_hex_sha256_survives(self):
        roots = self._roots()
        value = "c" * 64
        text = f"fileSha256: {value}"
        self.assertIn(value, seal_normalize.n5_git_shas(text, roots))

    def test_n5_guard_no_short_sha_survives_in_any_captured_case(self):
        short_sha_re = re.compile(r"\b[0-9a-f]{7,12}\b")
        for case_id, result in _captured_results().items():
            with self.subTest(case=case_id):
                self.assertNotRegex(result.stdout_text, short_sha_re)

    # --- N6 content_digests (deliberately NOT normalized) ---

    def test_n6_content_digest_moves_with_the_source_it_hashes(self):
        """`source_digest`/`suite_digest`/`revisionSha256` are content-
        derived over byte-fixed input, so they are already deterministic;
        normalizing them would blind the seal to a change in the digest
        ALGORITHM. `suiteDigest`/`source_digest` are never reached by this
        corpus (`step` is pinned at `INTERPRETER_ABSENT`, by design, to
        avoid a minutes-long suite run); `admit`'s own `revisionSha256`
        lands in `tests/admissibility.json` INSIDE the target, never in
        stdout, so it is unreachable here too. `position` IS a direct
        stdout carrier (`cmd_position`'s own returned dict). Adapted from
        design.md's literal `src/Seal/__init__.py` wording (measured:
        production code skips `__init__.py` for provenance, so nothing
        there is reachable this way) to the field and command this corpus
        actually surfaces it through: flip one byte of the REVISION TEXT —
        `position-e1`'s digest must move. A future `<DIGEST>` normalizer
        erasing `revisionSha256` would make this stop moving and this test
        would go red."""
        original_revision = seal_corpus.REVISION_TEXT
        mutated_revision = original_revision[:-2] + "X" + original_revision[-1]
        self.assertNotEqual(original_revision, mutated_revision)

        def _run(revision_text, label):
            seal_corpus.REVISION_TEXT = revision_text
            try:
                with tempfile.TemporaryDirectory(prefix="seal-n6-") as tmp:
                    roots = seal_corpus.build(Path(tmp) / "corpus")
                    scratch_root = (impl.FORGE_ROOT / "implementations"
                                   / f"_seal_n6_{label}_{os.getpid()}")
                    scratch_root.mkdir(parents=True)
                    try:
                        case = next(c for c in _load_cases() if c["id"] == "position-e1")
                        return seal_harness.run_case(case, roots, scratch_root=scratch_root)
                    finally:
                        shutil.rmtree(scratch_root, ignore_errors=True)
            finally:
                seal_corpus.REVISION_TEXT = original_revision

        original_result = _run(original_revision, "orig")
        mutated_result = _run(mutated_revision, "mut")
        self.assertNotEqual(seal_harness.digest_result(original_result)["sha256"],
                            seal_harness.digest_result(mutated_result)["sha256"])
        self.assertIn("revisionSha256", original_result.stdout_text)

    # --- normalizer order ---

    def test_normalizer_order_is_pinned(self):
        self.assertEqual(seal_normalize.NORMALIZERS,
                         (seal_normalize.n3_cli_invocation,
                          seal_normalize.n2_absolute_roots,
                          seal_normalize.n1_iso8601_timestamps,
                          seal_normalize.n5_git_shas))


class SealEntryPointTests(unittest.TestCase):
    """Design.md D6 amendment to `Seal Capture Scope`: the sealed invocation
    TARGET must be the per-skill published launcher, never the shared
    engine -- pinned separately from `test_the_sealed_cli_path_names_the_
    launcher` above, which pins the BYTES the seal digested. This pins the
    FILE the harness ran. The two cannot diverge today because `harness.py`
    derives argv from the same `CLI_INVOCATION`, and that is exactly why
    the requirement pins both: the divergence becomes available the moment
    `harness.py`'s import route is edited, which this change does."""

    #: A pinned literal suffix -- never derived from `CLI`/`ENGINE` above,
    #: so a mutation that re-points both this test's OWN constants and the
    #: production code together in lockstep still cannot pass vacuously.
    LAUNCHER_SUFFIX = ("/skills/proposal-implementation/scripts/"
                       "implementation_cli.py")
    ENGINE_SUFFIX = ("/skills/_core/implementation/engine/"
                     "implementation_engine.py")

    def test_the_seal_invokes_the_published_launcher(self):
        tokens = shlex.split(impl.CLI_INVOCATION)
        invoked = Path(tokens[1])
        self.assertEqual(invoked, CLI)
        self.assertNotEqual(invoked, ENGINE)
        self.assertTrue(str(invoked).endswith(self.LAUNCHER_SUFFIX), invoked)
        self.assertFalse(str(invoked).endswith(self.ENGINE_SUFFIX), invoked)


class SealComparisonTests(unittest.TestCase):
    """The recurring guard (design.md's own top-level distinction from
    capture, which runs each case TWICE): every SEALED case runs ONCE,
    normalized, compared against the stored golden."""

    def test_every_sealed_case_matches_its_golden(self):
        digests = _load_digests()
        results = _captured_results()
        sealed_ids = sorted(cid for cid in digests
                            if cid != seal_capture.CORPUS_FINGERPRINT_KEY)
        self.assertTrue(sealed_ids)
        for case_id in sealed_ids:
            with self.subTest(case=case_id):
                actual = seal_harness.digest_result(results[case_id])
                self.assertEqual(actual, digests[case_id], case_id)


class SealMutationProofTests(unittest.TestCase):
    """Spec.md "Seal Is Mutation-Provable": a single-byte change in any
    captured golden must turn the comparison red. Demonstrated in memory —
    the stored `digests.json` on disk is never touched, so "revert" is
    trivial and automatic (a fresh dict copy, never the original)."""

    def test_flipping_one_byte_of_a_golden_turns_the_comparison_red(self):
        digests = _load_digests()
        results = _captured_results()
        case_id = "admit-e1"
        actual = seal_harness.digest_result(results[case_id])
        golden = digests[case_id]
        self.assertEqual(actual, golden)  # agrees BEFORE the mutation

        mutated_golden = dict(golden)
        flipped_char = "0" if mutated_golden["sha256"][0] != "0" else "1"
        mutated_golden["sha256"] = flipped_char + mutated_golden["sha256"][1:]

        self.assertNotEqual(actual, mutated_golden)  # the seal goes red

        # revert: `digests[case_id]` (the on-disk golden, loaded above) was
        # never mutated — `mutated_golden` was always a separate dict.
        self.assertEqual(actual, digests[case_id])


class CorpusFingerprintTests(unittest.TestCase):
    """Design.md D3's anti-trim guard: `sha256(corpus.py)` vs stored."""

    def test_corpus_fingerprint_matches(self):
        digests = _load_digests()
        stored = digests[seal_capture.CORPUS_FINGERPRINT_KEY]
        actual = hashlib.sha256(
            seal_corpus.CORPUS_FINGERPRINT_SOURCE.read_bytes()).hexdigest()
        self.assertEqual(stored["sha256"], actual)

    def test_trimming_the_corpus_source_moves_the_fingerprint(self):
        real = seal_corpus.CORPUS_FINGERPRINT_SOURCE.read_bytes()
        trimmed = real[:-1]
        self.assertNotEqual(hashlib.sha256(real).hexdigest(),
                            hashlib.sha256(trimmed).hexdigest())


class SealMembershipTests(unittest.TestCase):
    """Design.md D6: sealed ∪ unsealed == cases; unsealed == literal;
    commands == `COMMANDS`."""

    #: A literal, not derived — growing this requires editing the test,
    #: deliberate friction so the unsealed set cannot grow silently.
    EXPECTED_UNSEALED = frozenset({"propose"})

    def test_every_case_is_either_sealed_or_declared_unsealed(self):
        cases = {c["id"] for c in _load_cases()}
        digests = set(_load_digests()) - {seal_capture.CORPUS_FINGERPRINT_KEY}
        unsealed = set(_load_unsealed())
        self.assertEqual(digests | unsealed, cases)
        self.assertEqual(digests & unsealed, set())

    def test_the_unsealed_set_is_exactly_its_declared_membership(self):
        self.assertEqual(frozenset(_load_unsealed()), self.EXPECTED_UNSEALED)

    def test_the_case_roster_covers_the_command_roster_exactly(self):
        commands = {c["command"] for c in _load_cases()}
        self.assertEqual(commands, set(impl.COMMANDS))

    def test_every_unsealed_entry_states_a_reason(self):
        for case_id, reason in _load_unsealed().items():
            with self.subTest(case=case_id):
                self.assertIsInstance(reason, str)
                self.assertGreaterEqual(len(reason), 20)


class SealReachesBehaviorTests(unittest.TestCase):
    """#52: a case argparse refuses (usage on stderr, empty stdout, exit 2)
    seals the usage text, not the command. `adopt-same-target` once omitted
    the required `--name` and sealed exactly that."""

    def test_seal_adopt_reaches_behavior(self):
        result = _captured_results()["adopt-same-target"]
        self.assertEqual(result.exit_status, 2)
        payload = json.loads(result.stdout_text)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "DESTINATION_CONFLICT")

    def test_no_sealed_case_is_an_argparse_usage_failure(self):
        # A deliberate refusal prints its envelope on stdout; only argparse
        # exits 2 with nothing there.
        for case_id, golden in _load_digests().items():
            if case_id == seal_capture.CORPUS_FINGERPRINT_KEY:
                continue
            with self.subTest(case=case_id):
                self.assertFalse(golden["exit"] == 2 and golden["bytes"] == 0,
                                 f"{case_id} seals an argparse usage failure")


class CoverageTests(unittest.TestCase):
    """Coverage asserted over the captured OUTPUT, not the fixture
    (design.md D3)."""

    def test_provenance_reaches_the_output(self):
        payload = json.loads(_captured_results()["verify-a"].stdout_text)
        modules = payload["fidelity"]["modules"]
        self.assertTrue(any(m["equations"] for m in modules))
        unreached = payload["fidelity"]["benchmark"]["unreachedModules"]
        self.assertTrue(any(m["declaredBy"] for m in unreached))

    def test_findings_reach_the_output(self):
        payload = json.loads(_captured_results()["handoff-e1"].stdout_text)
        self.assertTrue(payload["settleInline"])
        self.assertTrue(payload["deferToOwnSession"])
        self.assertTrue(payload["alreadyAdopted"])
        self.assertTrue(any(item["introduces"]
                            for item in payload["deferToOwnSession"]))

    def test_corpus_provably_exercises_data_present_and_absent(self):
        """Construction-level, not output-level (design.md D3's correction,
        coordinator decision, 2026-09-11): fixture A's `Seal/Data/` exists
        on disk, fixture B's does not — `verify`'s OUTPUT is proven
        byte-identical between the two today (measurement finding B4), so
        this coverage claim is about the corpus, never the captured bytes.
        See `NormalizerMutationTests`... no — see `F5IdentityTests` (Phase
        8) for the instrument that WOULD catch a botched F5 through case
        13's digest."""
        with tempfile.TemporaryDirectory(prefix="seal-coverage-data-") as tmp:
            roots = seal_corpus.build(Path(tmp) / "corpus")
            self.assertTrue((roots.fixture_a / "Seal" / "Data").is_dir())
            self.assertFalse((roots.fixture_b / "Seal" / "Data").is_dir())

    def test_both_revision_families_and_a_tie_are_exercised(self):
        verify_a = json.loads(_captured_results()["verify-a"].stdout_text)
        self.assertTrue(verify_a["fidelity"]["markerOwned"])
        verify_t = json.loads(_captured_results()["verify-t"].stdout_text)
        self.assertTrue(verify_t["fidelity"]["revisionTie"])

    def test_every_f3_site_is_sealed_in_both_env_states(self):
        f3_commands = {"admit", "position", "gate", "offer", "close"}
        cases = _load_cases()
        by_command = {}
        for case in cases:
            if case["command"] in f3_commands:
                by_command.setdefault(case["command"], set()).add(case["proposals"])
        for command in f3_commands:
            self.assertEqual(by_command.get(command), {True, False}, command)

        digests = _load_digests()
        sealed_ids = set(digests) - {seal_capture.CORPUS_FINGERPRINT_KEY}
        for case in cases:
            if case["command"] in f3_commands:
                self.assertIn(case["id"], sealed_ids, case["id"])


class F5IdentityTests(unittest.TestCase):
    """F5 — `PRODUCT_DATA = PRODUCT_DIRS[1]` replacing the bare `"Data"`
    literal in `expected_dirs`. Applied AFTER capture (design.md's own
    ordering discipline: F5 must land after digests exist, or its zero-delta
    claim is unfalsifiable). Zero seal delta required (design.md D8): five
    independent instruments, not one green suite."""

    def test_the_data_category_is_read_from_the_tuple(self):
        """The exact shape of the existing precedent
        `test_the_notebook_category_is_read_from_the_forge_not_written_here`."""
        self.assertEqual(impl.PRODUCT_DATA, "Data")
        self.assertIs(impl.PRODUCT_DATA, impl.PRODUCT_DIRS[1])
        source = inspect.getsource(impl.expected_dirs)
        self.assertNotIn(f'"{impl.PRODUCT_DATA}"', source)

    def test_expected_dirs_with_data_true_pinned(self):
        """Pinned literal, never derived from `PRODUCT_DIRS` — a derived
        expectation moves with the code and would prove nothing."""
        self.assertEqual(
            impl.expected_dirs("Seal", with_data=True),
            ["Seal/Notebooks", "Seal/Data", "Seal/Results", "Seal/Models",
             "src/Seal", "tests"])

    def test_expected_dirs_with_data_false_pinned(self):
        self.assertEqual(
            impl.expected_dirs("Seal", with_data=False),
            ["Seal/Notebooks", "Seal/Results", "Seal/Models",
             "src/Seal", "tests"])

    def test_the_seal_reproduces_pre_f5_digests_unchanged(self):
        """Instrument 3 (design.md D8): cases 3 (`plan-a`), 4 (`plan-b`), 12
        (`verify-a`), 13 (`verify-b`) run the comparison AFTER F5 and must
        reproduce the pre-F5 digests unchanged — checked against the
        EXISTING `digests.json`, never by recapture. This is the F5
        zero-delta claim."""
        digests = _load_digests()
        results = _captured_results()
        for case_id in ("plan-a", "plan-b", "verify-a", "verify-b"):
            with self.subTest(case=case_id):
                self.assertEqual(seal_harness.digest_result(results[case_id]),
                                 digests[case_id], case_id)

    def test_a_wrong_product_data_would_move_case_13_but_not_case_12(self):
        """Instrument 4, the mutation that matters (design.md D8, coordinator
        decision 2026-09-11): zero-delta alone only proves this refactor is
        an identity; it says nothing about whether the seal COULD have
        caught it if it were not one. `expected_dirs`'s `or with_data`
        short-circuit makes fixture A (case 12, `with_data=True`)
        structurally BLIND to `PRODUCT_DATA`'s value — only fixture B (case
        13, `with_data=False`) can see a wrong index move. In-process,
        never touching the file a subprocess would read (a permanent test
        cannot safely mutate `implementation_cli.py` on disk); the ONE-TIME
        subprocess-level demonstration — proving this reaches an actual
        captured digest, not merely the pure function — is recorded in
        `f5-zero-delta.md` instead, exactly the way F3's RED→GREEN mutation
        proof was demonstrated and reverted rather than left as a permanent
        file-mutating test."""
        original = impl.PRODUCT_DATA
        try:
            correct_with_data_false = impl.expected_dirs("Seal", with_data=False)
            correct_with_data_true = impl.expected_dirs("Seal", with_data=True)
            impl.PRODUCT_DATA = impl.PRODUCT_DIRS[2]  # "Results" -- wrong, on purpose
            wrong_with_data_false = impl.expected_dirs("Seal", with_data=False)
            wrong_with_data_true = impl.expected_dirs("Seal", with_data=True)
        finally:
            impl.PRODUCT_DATA = original

        self.assertNotEqual(correct_with_data_false, wrong_with_data_false,
                            "case 13 (Data/ absent): a wrong PRODUCT_DATA must "
                            "move the expected-dirs list, and so missingDirs, "
                            "and so the sealed digest")
        self.assertEqual(correct_with_data_true, wrong_with_data_true,
                         "case 12 (Data/ present): fixture A is structurally "
                         "blind to PRODUCT_DATA -- the `or with_data` "
                         "short-circuit makes every branch true regardless")


if __name__ == "__main__":
    unittest.main()
