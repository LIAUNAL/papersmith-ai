"""Cut 2 (`the-domain-crosses-the-seam`), design.md D8: mutation proof,
both directions, per leaf.

**Removal** is already proven for all sixteen leaves by
`test_implementation_profile.py`'s `DomainFieldLeafRefusalTests` -- each
raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming its own leaf. This
file is the OTHER half: **change**. A real, reverted mutation moves the
digest D1 predicted -- or, where measurement disagrees with prediction, the
digest actually measured, recorded honestly (design.md's own warning: Cut 1
shipped a false git-rename prediction, and this cut's own predictions are
claims apply must measure, never facts to cite).

**Never a monkeypatch** (the scar Cut 1 recorded and this cut carries
forward): every seal case is a real subprocess, so patching
`impl_domain_profile.PROFILE` or any engine attribute in-process has ZERO
effect on it. Every mutation here is a REAL file on disk -- a scratch copy
of `impl_profile.py`, with `kit.root`/`cli.path`/`documents.directory`'s
own base kept anchored to the real skill directory so only the ONE leaf
under test differs from the shipped profile -- reached by a REAL
`IMPLEMENTATION_DOMAIN_PROFILE` environment override on a REAL subprocess.
The shipped `impl_profile.py` is never edited by this file.

**Anchor discipline** (design.md D8): before every mutation, the real
source's occurrence count for the OLD spelling is asserted to be exactly 1
(so the substitution is unambiguous) and the NEW spelling to be absent; the
scratch copy is then asserted 0/1. An anchor that matched is not a mutation
that ran.

**Measured, not assumed.** Seven of the fourteen change-tested leaves below
did NOT move any of the 28 sealed cases against these particular fixtures,
despite a mover predicted in design.md D1. Each is recorded here as an
explicit ZERO-MOVER: its removal-refusal (above) and its lock coverage
(`test_implementation_domain_lock.py`) are its whole defence, per design.md
D8's own instruction -- never papered over, never hunted for a test that
would have moved it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
ENGINE_DIR = FORGE / "skills/_core/implementation/engine"
REAL_PROFILE = FORGE / "skills/proposal-implementation/impl_profile.py"
CASES_PATH = FORGE / "tests/seal/cases.json"

import sys  # noqa: E402
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from domain_profile import seeded_profile  # noqa: E402  (tests/ on path)

with seeded_profile(REAL_PROFILE):
    import implementation_engine as impl  # noqa: E402

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
from seal import corpus as seal_corpus  # noqa: E402  (path set above)
from seal import harness as seal_harness  # noqa: E402

REAL_PROFILE_SRC = REAL_PROFILE.read_text(encoding="utf-8")
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))

#: A case whose output is measured (during apply) to be non-deterministic
#: EVEN WITH ZERO CHANGES -- a fresh unmutated run's digest already
#: disagrees with the committed golden for this one id. Excluded from
#: every comparison below; recorded, not silently dropped. `propose`
#: composes `mintOrdinal`/timing-adjacent state the corpus's own
#: `IMPLEMENTATION_PROPOSALS`-free construction does not pin identically
#: run to run. Pre-existing to this cut -- no field mutation here touches
#: anything `propose` reads.
NON_DETERMINISTIC_CASE_IDS = frozenset({"propose"})

#: Leaf -> (old literal substring, new literal substring), each chosen to
#: occur EXACTLY ONCE in the real `impl_profile.py` (asserted below) so the
#: substitution is unambiguous -- the anchor discipline itself.
MUTATIONS: dict[str, tuple[str, str]] = {
    "provenance.claim_key": ('"claim_key": "equations",', '"claim_key": "claims",'),
    "provenance.authored_init_sentence": (
        '"Each module declares the sections and equations it implements in\\n"',
        '"Each module names what it establishes in\\n"'),
    "findings.locus_key": ('"locus_key": "equations",', '"locus_key": "loci",'),
    "findings.remedy_locus_key": (
        '"remedy_locus_key": "remedy_equations",', '"remedy_locus_key": "remedy_loci",'),
    "findings.notation_keys": ('"locus": "equations",', '"locus": "loci",'),
    "findings.citation_pattern": (
        r'r"Ecs?\.?\s*\(?(\d+)\)?|Eq\.?\s*\(?(\d+)\)?|Ecuaciones?\s*\((\d+)\)"',
        r'r"NOMATCHPATTERN_\d+"'),
    "vocabulary.subject_singular": (
        '"subject_singular": "equation",', '"subject_singular": "claim",'),
    "vocabulary.subject_plural": (
        '"subject_plural": "equations",', '"subject_plural": "claims",'),
    "vocabulary.subject_singular_es": (
        '"subject_singular_es": "ecuación",', '"subject_singular_es": "afirmación",'),
    "vocabulary.subject_plural_es": (
        '"subject_plural_es": "ecuaciones",', '"subject_plural_es": "afirmaciones",'),
    "vocabulary.subject_collective": (
        '"subject_collective": "mathematics",', '"subject_collective": "claims",'),
    "vocabulary.subject_collective_es": (
        '"subject_collective_es": "matemática",', '"subject_collective_es": "afirmación",'),
    "vocabulary.artifact_noun": ('"artifact_noun": "formulation",', '"artifact_noun": "method",'),
    "documents.label": ('"label": "proposal",', '"label": "document",'),
    # `new` is filled in per-test-run with the real sibling path (a fresh
    # `tempfile.mkdtemp()`, so it exists -- M3 requires absolute, not
    # existence, but an existing one keeps this mutation from ALSO
    # exercising the "documents.directory absent" path, which is not what
    # this leaf's mutation is proving).
    "documents.directory": ('"directory": _FORGE_ROOT / "proposals",', None),
    # `a-data-directory-somebody-can-owe` (B1, design.md D8): X2. `tests/
    # seal/corpus.py`'s own revision text already carries a line-leading
    # `## 2` (M7), authored two changes ago for an unrelated purpose --
    # mutating the sibling's declared `None` to that exact literal makes
    # the detector answer true against REAL document bytes nobody wrote
    # for this guard, never a fixture built to satisfy it.
    "documents.dataset_marker": ('"dataset_marker": None,', '"dataset_marker": "## 2",'),
    # `the-agreement-nothing-computes` (Slice D, design.md Mutation plan
    # Z2/Z3, tasks 1.27/1.28): the locator's matcher half and its renderer
    # half, each its own leaf -- the wiring proof: if either moves nothing,
    # the leaf is not wired and D1 has proven nothing.
    "documents.block_locator.pattern": (
        r'"pattern": r"\\tag\{([^}]+)\}",',
        r'"pattern": r"(?m)^## (\d+)$",'),
    "documents.block_locator.identity": (
        r'"identity": "\\tag{{{value}}}",',
        r'"identity": "[exp:{value}]",'),
}

#: Measured (this apply session, real subprocess runs, every one of the 28
#: sealed case ids compared): the case ids that actually moved for each
#: leaf, `NON_DETERMINISTIC_CASE_IDS` already excluded. An empty tuple is a
#: recorded zero-mover.
MEASURED_MOVERS: dict[str, tuple[str, ...]] = {
    "provenance.claim_key": ("probe", "verify-a", "verify-b", "verify-t"),
    "provenance.authored_init_sentence": (),  # ZERO-MOVER (see module docstring)
    "findings.locus_key": ("handoff-e1", "verify-a", "verify-b"),
    "findings.remedy_locus_key": ("handoff-e1", "verify-a", "verify-b"),
    "findings.notation_keys": ("handoff-e1", "verify-a", "verify-b"),
    # Re-measured, Cut 3 slice C (`the-second-document-verified-on-its-own-
    # terms`, design.md D3): this leaf's mutated value
    # (`r"NOMATCHPATTERN_\d+"`) has ZERO capturing groups. Before C1's
    # resolver-side group-count validation this was a genuine zero-mover
    # (a pattern that never matches still resolves; it just cites nothing).
    # C1 now refuses `IMPLEMENTATION_DOMAIN_PROFILE_INVALID_CITATION_PATTERN`
    # at import for ANY resolved `citation_pattern` without exactly three
    # groups, so every command that needs the profile to resolve at all
    # now fails the same way -- every sealed case except the one already
    # excluded as non-deterministic moves.
    "findings.citation_pattern": (
        "admit-e0", "admit-e1", "adopt-same-target", "apply", "close-e0",
        "close-e1", "compose",
        "defect", "discuss", "gate-e0", "gate-e1", "handoff-e0", "handoff-e1",
        "launch-plan",
        "materialize", "name", "offer-e0", "offer-e1", "plan-a", "plan-b",
        "position-e0", "position-e1", "probe", "settle", "step", "verify-a",
        "verify-b", "verify-t", "walk"),
    # Re-measured 2026-09-14, M2 closed: `handoff` stopped composing a sentence
    # of its own in one fixed human tongue and now hands the domain's six nouns
    # over as data, so an agent can put them into whichever tongue it was
    # addressed in. Every one of the six therefore reaches sealed output, where
    # three of them previously reached none at all: `subject_plural`,
    # `subject_collective` and `subject_collective_es` were ZERO-MOVERS purely
    # because no sentence happened to use them. Taken from the run, never
    # assumed -- the failure named each new set.
    "vocabulary.subject_singular": ("compose", "handoff-e1"),
    "vocabulary.subject_plural": ("handoff-e1",),
    "vocabulary.subject_singular_es": ("handoff-e1",),
    "vocabulary.subject_plural_es": ("handoff-e1",),
    "vocabulary.subject_collective": ("handoff-e1",),
    "vocabulary.subject_collective_es": ("handoff-e1",),
    "vocabulary.artifact_noun": (),  # ZERO-MOVER
    "documents.label": (),  # ZERO-MOVER
    "documents.directory": ("admit-e0", "close-e0", "gate-e0", "offer-e0", "position-e0"),
    # `a-data-directory-somebody-can-owe` (B1, design.md D8): MEASURED,
    # this apply session, real subprocess run over all 28 sealed cases --
    # matches the design's prediction exactly. `verify-b` (fixture B, no
    # `--revision`, discovers `seal-1.md`) and `verify-t` (fixture T,
    # `--revision draft-1.md`) both name a revision whose text is the
    # sibling's own `REVISION_TEXT` (M7's line-leading `## 2`); both
    # fixtures lack `Seal/Data/`, so `with_data` goes true and
    # `missingDirs` drops the `Data/` entry for both. `verify-a` (fixture
    # A, `Data/` already present) stays put -- never a fixture written to
    # make this true, the sibling's own pre-existing corpus.
    "documents.dataset_marker": ("verify-b", "verify-t"),
    # `the-agreement-nothing-computes` (Slice D, design.md Mutation plan
    # Z2/Z3, tasks 1.27/1.28): MEASURED, this apply session, real
    # subprocess runs over all 28 sealed cases -- and a correction of the
    # design's own prediction (`admit-e0`/`verify-t`/`handoff-e0` do NOT
    # move; `admit-e1`/`handoff-e1` do), never assumed. Non-empty for both,
    # so the leaf is proven wired either way (a null result would be a
    # blocker, per the design's own instruction).
    "documents.block_locator.pattern": (
        "admit-e1", "compose", "verify-a", "verify-b"),
    "documents.block_locator.identity": ("handoff-e1",),
}


#: Captured ONCE, at import time, before this module ever reassigns
#: `seal_harness.build_env` -- the wrapper below calls THIS reference, never
#: the module attribute (which becomes the wrapper itself once assigned;
#: calling through the attribute would recurse into itself forever).
_ORIGINAL_BUILD_ENV = seal_harness.build_env


def _build_env_with_profile_override(profile_path):
    """`seal_harness.build_env`'s own `ALLOWED_ENV_KEYS` deliberately does
    NOT pass `IMPLEMENTATION_DOMAIN_PROFILE` through (design.md D2: the
    seal always exercises the skill's OWN real profile via the launcher's
    `setdefault`). This wraps the real `build_env` to add exactly that one
    key when a mutation is under test -- a real env var reaching a real
    subprocess, never a monkeypatch of an engine or profile attribute."""
    def _wrapped(case, roots):
        env = _ORIGINAL_BUILD_ENV(case, roots)
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(profile_path)
        return env
    return _wrapped


def _run_all_cases_under(profile_path, roots, scratch_root) -> dict[str, dict]:
    seal_harness.build_env = _build_env_with_profile_override(profile_path)
    try:
        results = {}
        for case in CASES:
            result = seal_harness.run_case(case, roots, scratch_root=scratch_root)
            results[case["id"]] = seal_harness.digest_result(result)
        return results
    finally:
        seal_harness.build_env = _ORIGINAL_BUILD_ENV


def _write_scratch_profile(tmp_dir: Path, mutated_src: str) -> Path:
    """A scratch copy of `impl_profile.py` -- `_SKILL` re-anchored to the
    REAL skill directory (this file computes `kit.root`/`cli.path`/
    `documents.directory` from its own location, and a copy elsewhere
    would otherwise point those at the scratch directory instead)."""
    real_skill_dir = REAL_PROFILE.resolve().parent
    anchored = mutated_src.replace(
        "_SKILL = Path(__file__).resolve().parent",
        f"_SKILL = Path({str(real_skill_dir)!r})")
    scratch_profile = tmp_dir / "impl_profile.py"
    scratch_profile.write_text(anchored, encoding="utf-8")
    return scratch_profile


class PerLeafChangeMutationTests(unittest.TestCase):
    """D8's change proof, one subtest per leaf: anchor discipline, a real
    scratch mutation, a real subprocess seal run over all 28 cases, and an
    assertion that ONLY the measured movers (never any other case) moved."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._corpus_root = Path(cls._tmp.name) / "corpus"
        cls._roots = seal_corpus.build(cls._corpus_root)
        cls._scratch_root = FORGE / "implementations" / f"_domain_mutation_test_{os.getpid()}"
        cls._scratch_root.mkdir(parents=True, exist_ok=True)
        cls._baseline = _run_all_cases_under(REAL_PROFILE, cls._roots, cls._scratch_root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._scratch_root, ignore_errors=True)
        cls._tmp.cleanup()

    def test_every_leaf_moves_exactly_its_measured_case_set(self):
        for leaf, (old, new) in MUTATIONS.items():
            with self.subTest(leaf=leaf):
                if leaf == "documents.directory":
                    sibling = Path(tempfile.mkdtemp(prefix="mutation-sibling-proposals-"))
                    self.addCleanup(shutil.rmtree, sibling, ignore_errors=True)
                    new = f'"directory": Path({str(sibling)!r}),'

                # Anchor discipline (design.md D8): the real source carries
                # the old spelling exactly once and the new spelling not at
                # all, BEFORE any mutation.
                real_src = REAL_PROFILE.read_text(encoding="utf-8")
                self.assertEqual(
                    real_src.count(old), 1,
                    f"{leaf}: expected the OLD spelling exactly once in the real "
                    f"impl_profile.py, found {real_src.count(old)} -- an ambiguous "
                    "anchor is not a mutation that can run unambiguously")
                self.assertEqual(
                    real_src.count(new), 0,
                    f"{leaf}: the NEW spelling already appears in the real "
                    "impl_profile.py before any mutation -- anchor invalid")

                mutated_src = real_src.replace(old, new, 1)

                with tempfile.TemporaryDirectory() as scratch_dir:
                    scratch_profile = _write_scratch_profile(
                        Path(scratch_dir), mutated_src)
                    scratch_src = scratch_profile.read_text(encoding="utf-8")
                    # Anchor discipline, the mutated side: 0 old / 1 new.
                    self.assertEqual(scratch_src.count(old), 0)
                    self.assertEqual(scratch_src.count(new), 1)

                    mutated_results = _run_all_cases_under(
                        scratch_profile, self.__class__._roots,
                        self.__class__._scratch_root)

                moved = sorted(
                    cid for cid in mutated_results
                    if cid not in NON_DETERMINISTIC_CASE_IDS
                    and mutated_results[cid] != self.__class__._baseline[cid])
                expected = sorted(MEASURED_MOVERS[leaf])
                self.assertEqual(
                    moved, expected,
                    f"{leaf}: measured movers changed since apply-time measurement "
                    f"-- expected {expected}, got {moved}. If this is a genuine, "
                    "understood change, MEASURED_MOVERS must be updated with the "
                    "new measurement, never assumed")


#: X4 (`a-data-directory-somebody-can-owe`, B1, design.md's Mutation
#: plan): the or-fold's own index read, anchor-counted both directions.
#: Never mutate the shipped engine -- planted into a scratch copy only.
_FOLD_INDEX_ANCHOR = 'DOCUMENTS[index].get("dataset_marker")'
_FOLD_INDEX_MUTATED = 'DOCUMENTS[0].get("dataset_marker")'


class OrFoldIndexHardcodeMutationTests(unittest.TestCase):
    """X4 (design.md, task 6.3): `dataset_marker`'s or-fold reads
    `DOCUMENTS[index]`, never a fixed index. Anchor-counted, planted into
    a SCRATCH copy of the engine only, and run directly (never through
    the launcher, whose own `sys.path.insert(0, ...)` would always
    resolve `implementation_engine` back to the shipped copy)."""

    def _run_declares_dataset(self, engine_source: str, profile_path: Path,
                              revision: str) -> str:
        """Runs `implementation_engine.declares_dataset(revision)` in a
        fresh subprocess against a scratch copy of the WHOLE `_core/
        implementation/` tree (the engine's own `sys.path.insert(0, ...
        parents[1])` resolves its sibling imports -- `impl_domain_
        profile`, `impl_layout`, etc. -- relative to the engine file's
        OWN location, so a lone copy of just the engine file cannot
        import them). Only `engine/implementation_engine.py` differs
        from CORE's real, unedited siblings."""
        with tempfile.TemporaryDirectory() as scratch_dir:
            scratch_core = Path(scratch_dir) / "core"
            shutil.copytree(
                ENGINE_DIR.parent, scratch_core,
                ignore=shutil.ignore_patterns("__pycache__"))
            (scratch_core / "engine" / "implementation_engine.py").write_text(
                engine_source, encoding="utf-8")
            env = os.environ.copy()
            env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(profile_path)
            code = (
                "import sys\n"
                f"sys.path.insert(0, {str(scratch_core / 'engine')!r})\n"
                "import implementation_engine as impl\n"
                f"print(impl.declares_dataset({revision!r}))\n"
            )
            proc = subprocess.run([sys.executable, "-c", code],
                                  capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return proc.stdout.strip()

    def test_hardcoding_index_zero_blinds_the_fold_to_document_one(self):
        real_engine_source = (ENGINE_DIR / "implementation_engine.py").read_text(
            encoding="utf-8")
        self.assertEqual(real_engine_source.count(_FOLD_INDEX_ANCHOR), 1)
        self.assertEqual(real_engine_source.count(_FOLD_INDEX_MUTATED), 0)
        mutated_engine_source = real_engine_source.replace(
            _FOLD_INDEX_ANCHOR, _FOLD_INDEX_MUTATED, 1)
        self.assertEqual(mutated_engine_source.count(_FOLD_INDEX_ANCHOR), 0)
        self.assertEqual(mutated_engine_source.count(_FOLD_INDEX_MUTATED), 1)

        # The exact 2.4 configuration: two documents, only index 1
        # declares, index 1's own revision carries the marker. Appended
        # right before the documents list's own closing bracket -- the
        # LAST bytes of the real profile file, asserted unique first.
        doc1_dir = Path(tempfile.mkdtemp(prefix="x4-doc1-"))
        self.addCleanup(shutil.rmtree, doc1_dir, ignore_errors=True)
        (doc1_dir / "r1.md").write_text(
            "**Dataset:** declared only here\n", encoding="utf-8")
        documents_close_anchor = "        },\n    ],\n}"
        self.assertEqual(REAL_PROFILE_SRC.count(documents_close_anchor), 1)
        # `the-agreement-nothing-computes` (Slice D, design.md D1/R2):
        # required, own tier, non-nullable -- this second entry needs one
        # too, real content irrelevant to what X4 exists to prove. Built
        # via `repr()`, never hand-escaped, so the written source's own
        # backslashes are correct by construction.
        extra_block_locator_repr = repr({
            "pattern": r"\\tag\{([^}]+)\}",
            "block_pattern": r"(?s)\$\$.*?\$\$",
            "identity": "\\tag{{{value}}}",
        })
        two_doc_close = (
            "        },\n"
            f"        {{'directory': Path({str(doc1_dir)!r}), 'label': 'extra',\n"
            "         'dataset_marker': '**Dataset:**',\n"
            f"         'block_locator': {extra_block_locator_repr},\n"
            # `the-agreement-nothing-computes` (Slice D, design.md D5/R1):
            # required, own tier, NULLABLE -- `None` here, real content
            # irrelevant to what X4 exists to prove.
            "         'cross_citation': None},\n"
            "    ],\n}"
        )
        two_doc_profile_src = REAL_PROFILE_SRC.replace(
            documents_close_anchor, two_doc_close, 1)

        with tempfile.TemporaryDirectory() as scratch_dir:
            two_doc_profile = _write_scratch_profile(
                Path(scratch_dir), two_doc_profile_src)

            original_result = self._run_declares_dataset(
                real_engine_source, two_doc_profile, "r0-does-not-exist.md")
            mutated_result = self._run_declares_dataset(
                mutated_engine_source, two_doc_profile, "r0-does-not-exist.md")

        self.assertEqual(
            original_result, "True",
            "the unmutated fold must find index 1's own declared marker "
            "even though document 0's own revision does not exist")
        self.assertEqual(
            mutated_result, "False",
            "hardcoding the fold's read to index 0 must blind it to "
            "document 1's own declared marker -- this is the mutation "
            "tests/test_experimental_implementation.py's own or-fold case "
            "(2.4) is written to catch")

    def test_the_sibling_seal_is_unaffected_because_it_has_only_one_document(self):
        """`tests/seal/` still survives this exact mutation: the sibling
        declares exactly ONE document, so reading `DOCUMENTS[0]` instead
        of `DOCUMENTS[index]` is a no-op there by construction -- proven
        by execution, both engines answering identically against the
        sibling's own real, unedited profile."""
        real_engine_source = (ENGINE_DIR / "implementation_engine.py").read_text(
            encoding="utf-8")
        mutated_engine_source = real_engine_source.replace(
            _FOLD_INDEX_ANCHOR, _FOLD_INDEX_MUTATED, 1)

        original_result = self._run_declares_dataset(
            real_engine_source, REAL_PROFILE, "seal-1.md")
        mutated_result = self._run_declares_dataset(
            mutated_engine_source, REAL_PROFILE, "seal-1.md")
        self.assertEqual(original_result, mutated_result)
        self.assertEqual(
            original_result, "False",
            "the sibling's own dataset_marker is None; both engines must "
            "agree, unaffected by this mutation")


class SeedForcedNoneMutationTests(unittest.TestCase):
    """X5 (design.md, task 6.4): `cmd_apply` and `_materialize_plan_gate`
    both re-derive the seed from the approved plan's own `boundTo` key --
    mutate each, in turn, to pass `None` instead, and confirm an
    apply/materialize that should succeed against a real declared marker
    instead refuses `PLAN_STALE`, because `current["createDirs"]` (built
    with no seed) no longer agrees with the approved plan (built with the
    real one). This is the exact failure `RevisionThreadingAgreementTests`
    (`tests/test_experimental_implementation.py`) is written to catch."""

    PACKAGE = "X5SeedForced"
    _SEED_ANCHOR = ('    seed = (approved.get("boundTo") or {}).get("revision")\n'
                    '    current = build_plan(target, name, seed)')
    _FORCED_NONE = '    current = build_plan(target, name, None)'

    def setUp(self):
        # A whole SCRATCH forge, not just a scratch engine file:
        # `impl_layout.FORGE_ROOT` is `Path(__file__).resolve().parents[4]`,
        # so the copied core tree must sit at the SAME four-level depth
        # under some root, and that root needs its own `implementations/`
        # for `resolve_target`'s workspace guard to accept a box under it.
        self.scratch_forge = Path(tempfile.mkdtemp(prefix="x5-forge-"))
        self.addCleanup(shutil.rmtree, self.scratch_forge, ignore_errors=True)
        self.scratch_core = (
            self.scratch_forge / "skills" / "_core" / "implementation")
        shutil.copytree(ENGINE_DIR.parent, self.scratch_core,
                        ignore=shutil.ignore_patterns("__pycache__"))
        (self.scratch_forge / "implementations").mkdir(parents=True)

    def _git_env(self) -> dict:
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "x5-mutation-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = (
            "x5-mutation-tests@example.invalid")
        return env

    def _scratch_profile_with_marker(self, docs_dir: Path) -> Path:
        mutated_profile_src = REAL_PROFILE_SRC.replace(
            '"directory": _FORGE_ROOT / "proposals",',
            f'"directory": Path({str(docs_dir)!r}),', 1)
        mutated_profile_src = mutated_profile_src.replace(
            '"dataset_marker": None,', '"dataset_marker": "**Dataset:**",', 1)
        tmp_dir = Path(tempfile.mkdtemp(prefix="x5-profile-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        # `_write_scratch_profile` (already established in this file) also
        # re-anchors `_SKILL` to the REAL skill directory, or `kit.root`/
        # `cli.path` would point at THIS tmp_dir instead.
        return _write_scratch_profile(tmp_dir, mutated_profile_src)

    def _box(self, suffix: str) -> Path:
        box = self.scratch_forge / "implementations" / f"x5{suffix}"
        box.mkdir(parents=True)
        env = self._git_env()
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / self.PACKAGE).mkdir(parents=True)
        (box / "src" / self.PACKAGE / "__init__.py").write_text(
            "__all__ = []\n", encoding="utf-8")
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "add", "-A"], cwd=box, env=env, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=box, env=env,
                       check=True, capture_output=True)
        return box

    def _run_main(self, engine_source: str, profile_path: Path, argv: list[str]):
        (self.scratch_core / "engine" / "implementation_engine.py").write_text(
            engine_source, encoding="utf-8")
        env = self._git_env()
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(profile_path)
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(self.scratch_core / 'engine')!r})\n"
            "import implementation_engine as impl\n"
            f"raise SystemExit(impl.main({argv!r}))\n"
        )
        return subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env)

    def _mutate_first_occurrence(self, source: str) -> str:
        idx = source.index(self._SEED_ANCHOR)
        return source[:idx] + self._FORCED_NONE + source[idx + len(self._SEED_ANCHOR):]

    def _mutate_second_occurrence(self, source: str) -> str:
        first_end = source.index(self._SEED_ANCHOR) + len(self._SEED_ANCHOR)
        head, tail = source[:first_end], source[first_end:]
        idx = tail.index(self._SEED_ANCHOR)
        return head + tail[:idx] + self._FORCED_NONE + tail[idx + len(self._SEED_ANCHOR):]

    def test_cmd_apply_forced_to_none_refuses_plan_stale(self):
        real_engine_source = (ENGINE_DIR / "implementation_engine.py").read_text(
            encoding="utf-8")
        self.assertEqual(real_engine_source.count(self._SEED_ANCHOR), 2)
        mutated_engine_source = self._mutate_first_occurrence(real_engine_source)
        self.assertEqual(mutated_engine_source.count(self._SEED_ANCHOR), 1)

        docs_dir = Path(tempfile.mkdtemp(prefix="x5-docs-apply-"))
        self.addCleanup(shutil.rmtree, docs_dir, ignore_errors=True)
        (docs_dir / "r1.md").write_text(
            "**Dataset:** declared here\n", encoding="utf-8")
        profile_path = self._scratch_profile_with_marker(docs_dir)
        box = self._box("_apply")

        plan_proc = self._run_main(
            real_engine_source, profile_path,
            ["plan", "--target", str(box), "--name", self.PACKAGE,
             "--revision", "r1.md"])
        self.assertEqual(plan_proc.returncode, 0, plan_proc.stdout + plan_proc.stderr)
        plan = json.loads(plan_proc.stdout)
        self.assertIn(f"{self.PACKAGE}/Data", plan["createDirs"])
        plan_dir = Path(tempfile.mkdtemp(prefix="x5-plan-"))
        self.addCleanup(shutil.rmtree, plan_dir, ignore_errors=True)
        plan_path = plan_dir / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

        original_apply = self._run_main(
            real_engine_source, profile_path,
            ["apply", "--target", str(box), "--name", self.PACKAGE,
             "--plan", str(plan_path)])
        self.assertEqual(
            original_apply.returncode, 0,
            original_apply.stdout + original_apply.stderr)

        # Undo the successful apply's own commit so the box is clean again
        # for the mutated run, against the exact same approved plan.
        subprocess.run(["git", "reset", "-q", "--hard", "HEAD~1"], cwd=box,
                       env=self._git_env(), check=True, capture_output=True)

        mutated_apply = self._run_main(
            mutated_engine_source, profile_path,
            ["apply", "--target", str(box), "--name", self.PACKAGE,
             "--plan", str(plan_path)])
        self.assertEqual(
            mutated_apply.returncode, 2, mutated_apply.stdout + mutated_apply.stderr)
        self.assertEqual(
            json.loads(mutated_apply.stdout).get("code"), "PLAN_STALE",
            "forcing cmd_apply's seed to None must refuse PLAN_STALE -- "
            "this is the exact failure the PLAN_STALE agreement test "
            "exists to catch")

    def test_materialize_plan_gate_forced_to_none_refuses_plan_stale(self):
        real_engine_source = (ENGINE_DIR / "implementation_engine.py").read_text(
            encoding="utf-8")
        mutated_engine_source = self._mutate_second_occurrence(real_engine_source)
        self.assertEqual(mutated_engine_source.count(self._SEED_ANCHOR), 1)

        docs_dir = Path(tempfile.mkdtemp(prefix="x5-docs-materialize-"))
        self.addCleanup(shutil.rmtree, docs_dir, ignore_errors=True)
        (docs_dir / "r1.md").write_text(
            "**Dataset:** declared here\n", encoding="utf-8")
        profile_path = self._scratch_profile_with_marker(docs_dir)
        box = self._box("_materialize")

        plan_proc = self._run_main(
            real_engine_source, profile_path,
            ["plan", "--target", str(box), "--name", self.PACKAGE,
             "--revision", "r1.md"])
        self.assertEqual(plan_proc.returncode, 0, plan_proc.stdout + plan_proc.stderr)
        plan = json.loads(plan_proc.stdout)
        plan_dir = Path(tempfile.mkdtemp(prefix="x5-plan-materialize-"))
        self.addCleanup(shutil.rmtree, plan_dir, ignore_errors=True)
        plan_path = plan_dir / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

        argv = ["materialize", "--target", str(box), "--name", self.PACKAGE,
                "--stage", "scaffold", "--plan", str(plan_path), "--seed", "7"]
        original = self._run_main(real_engine_source, profile_path, argv)
        self.assertNotEqual(
            json.loads(original.stdout or "{}").get("code"), "PLAN_STALE",
            "the unmutated gate must not refuse PLAN_STALE against its own "
            "matching plan")

        # The unmutated call may have written (uncommitted) scaffold
        # files past the gate -- restore the pristine, committed state
        # before the mutated run, or DIRTY_WORKTREE fires before the gate
        # is even reached.
        subprocess.run(["git", "reset", "-q", "--hard"], cwd=box,
                       env=self._git_env(), check=True, capture_output=True)
        subprocess.run(["git", "clean", "-qfd"], cwd=box,
                       env=self._git_env(), check=True, capture_output=True)

        mutated = self._run_main(mutated_engine_source, profile_path, argv)
        self.assertEqual(mutated.returncode, 2, mutated.stdout + mutated.stderr)
        self.assertEqual(
            json.loads(mutated.stdout).get("code"), "PLAN_STALE",
            "forcing _materialize_plan_gate's seed to None must refuse "
            "PLAN_STALE")


class LockAHonestyTests(unittest.TestCase):
    """Task 4.1 (design.md D6, the M1 finding): `LockADiscoveryTests
    .test_every_declared_name_really_is_that_domain_speaking` searched
    `entry["source"]` -- the profile FILE's own text -- which trivially
    contains every literal in its own `names` list, since that list's
    declaration lives in the same file. Mutation X4: plant
    `"zzz-nothing"` into a scratch profile's `names`. Proven BOTH ways,
    the control this strengthening needs: the OLD check (searching the raw
    source) must be shown SURVIVING it first -- never merely asserted --
    and only then must the NEW check (`profile_values_text`, `vocabulary.
    names` excluded) be shown catching it."""

    #: A minimal, self-contained profile SOURCE -- real enough to exercise
    #: both checks, never the shipped file (which this test does not touch).
    _SCRATCH_PROFILE_SRC = (
        "PROFILE = {\n"
        "    'kit': {'root': '/scratch/skill'},\n"
        # `the-holder-each-skill-declares` (design.md D1): the 8th
        # top-level `PROFILE` section, present here for the same
        # "every synthesized profile carries it" reason as every other
        # fixture in this suite (tasks.md 1.1) -- this scratch source is
        # never resolved through `impl_domain_profile._resolve()`, only
        # scanned as text by `_old_check`/`_new_check` below, so the
        # section is inert to both checks but keeps the fixture honest.
        "    'holder': {'filename': 'Fixture_AGREED.md', "
        "'headings': ('# Agreed', '## Ladder'), "
        "'scaffold': '# Agreed\\n\\n## Ladder\\n'},\n"
        "    'vocabulary': {\n"
        "        'subject_singular': 'widget',\n"
        "        'names': ['widget', 'zzz-nothing'],\n"
        "    },\n"
        "}\n"
    )

    @staticmethod
    def _old_check(source: str, names: list[str]) -> list[str]:
        """The check as it stood before D6: searches the profile FILE's own
        source text -- the vacuous shape M1 found."""
        lower_source = source.lower()
        return [n for n in names if n.lower() not in lower_source]

    @staticmethod
    def _new_check(profile: dict, names: list[str]) -> list[str]:
        """The strengthened check (design.md D6): searches the profile's
        declared VALUES, `vocabulary.names` itself excluded -- reimplemented
        inline here rather than imported from
        `test_implementation_domain_lock.py`, mirroring
        `LockBHonestyTests`'s own established precedent of duplicating the
        scan rather than importing across test files."""
        parts: list[str] = []

        def walk(value, path):
            if path == ("vocabulary", "names"):
                return
            if isinstance(value, dict):
                for key, val in value.items():
                    walk(val, path + (key,))
            elif isinstance(value, (list, tuple)):
                for item in value:
                    walk(item, path)
            else:
                parts.append(str(value))

        walk(profile, ())
        haystack = " ".join(parts).lower()
        return [n for n in names if n.lower() not in haystack]

    def test_the_old_check_survives_a_planted_name_and_the_new_check_catches_it(self):
        names = ["widget", "zzz-nothing"]
        profile = {
            "kit": {"root": "/scratch/skill"},
            "vocabulary": {"subject_singular": "widget",
                          "names": list(names)},
        }

        # X4: `"zzz-nothing"` is planted into `names` with no other profile
        # leaf carrying it. The OLD check, searching the FILE'S OWN source,
        # finds it trivially -- it is written right there, in the `names`
        # list literal -- and SURVIVES: this is the control proving the
        # strengthening did something, per task 4.1's own acceptance
        # condition.
        old_unused = self._old_check(self._SCRATCH_PROFILE_SRC, names)
        self.assertEqual(
            old_unused, [],
            "the OLD check did not survive the planted name -- the control "
            "is invalid: it should have found 'zzz-nothing' vacuously "
            "present in the file's own source and reported nothing unused")

        # The NEW check, searching declared VALUES with `vocabulary.names`
        # excluded, catches it: "zzz-nothing" is not `subject_singular`'s
        # value, not `kit.root`'s, not anything but its own declaration.
        new_unused = self._new_check(profile, names)
        self.assertEqual(
            new_unused, ["zzz-nothing"],
            "the strengthened check did not catch the planted name -- it "
            "should report 'zzz-nothing' as unused by any OTHER profile "
            "value")


class LockBHonestyTests(unittest.TestCase):
    """14.5: plant a declared `vocabulary.names` word anywhere in `engine/`
    (including a comment); Lock B must redden, naming the file and word;
    revert; green. Proven against a SCRATCH COPY of the engine file, never
    the shipped one -- Lock B's own test already proves the shipped file is
    clean (test_implementation_domain_lock.py); this proves the LOCK ITSELF
    is not vacuously green."""

    def test_a_planted_names_word_reddens_lock_b_and_reverting_restores_green(self):
        import re
        real_source = (ENGINE_DIR / "implementation_engine.py").read_text(encoding="utf-8")

        # Before: the real file carries none of the planted word.
        planted_word = "formulation"
        self.assertNotIn(planted_word, real_source.lower())

        with tempfile.TemporaryDirectory() as tmp:
            scratch_engine_dir = Path(tmp) / "engine"
            scratch_engine_dir.mkdir()
            planted_source = real_source + f"\n# a planted {planted_word} comment\n"
            (scratch_engine_dir / "implementation_engine.py").write_text(
                planted_source, encoding="utf-8")

            # Reddens: a Lock-B-shaped scan over the SCRATCH directory finds it.
            leaks_with_plant = []
            for path in sorted(scratch_engine_dir.rglob("*.py")):
                source = path.read_text(encoding="utf-8")
                if re.search(rf"\b{planted_word}\b", source, re.IGNORECASE):
                    leaks_with_plant.append(path.name)
            self.assertEqual(leaks_with_plant, ["implementation_engine.py"])

            # Revert: remove the plant, the scratch copy is clean again.
            (scratch_engine_dir / "implementation_engine.py").write_text(
                real_source, encoding="utf-8")
            leaks_after_revert = []
            for path in sorted(scratch_engine_dir.rglob("*.py")):
                source = path.read_text(encoding="utf-8")
                if re.search(rf"\b{planted_word}\b", source, re.IGNORECASE):
                    leaks_after_revert.append(path.name)
            self.assertEqual(leaks_after_revert, [])


class KitLockHonestyTests(unittest.TestCase):
    """14.6: change `module.py`'s `"equations"` key in a SCRATCH COPY, not
    the shipped file; the kit lock must redden; discard the scratch copy.
    The shipped kit template is never touched (D4: `verify`'s `kitSource`
    compares a materialized target file byte-for-byte against its kit
    template; editing the template would reclassify files in repositories
    this change never opened)."""

    def test_a_scratch_kit_mutation_reddens_the_agreement_and_the_shipped_file_is_untouched(self):
        real_module_path = (
            FORGE / "skills/proposal-implementation/assets/kit/src/module.py")
        real_source = real_module_path.read_text(encoding="utf-8")
        self.assertIn('"equations": ["{{EQUATION}}"],', real_source)

        with tempfile.TemporaryDirectory() as tmp:
            scratch_module = Path(tmp) / "module.py"
            mutated = real_source.replace(
                '"equations": ["{{EQUATION}}"],', '"claims": ["{{EQUATION}}"],', 1)
            self.assertNotEqual(mutated, real_source)
            scratch_module.write_text(mutated, encoding="utf-8")

            # The lock's own assertion (kit agreement lock #1), run against the
            # SCRATCH file: the declared key set no longer matches claim_key.
            import re
            match = re.search(r"__provenance__\s*=\s*\{(.*?)\n\}", mutated, re.DOTALL)
            self.assertIsNotNone(match)
            keys = set(re.findall(r'"(\w+)":', match.group(1)))
            claim_key = impl.CLAIM_KEY
            self.assertNotEqual(
                keys, {"revision", "sections", claim_key, "invariants"},
                "the scratch mutation should have reddened the kit agreement")

        # The shipped file was never touched by this test.
        self.assertEqual(
            real_module_path.read_text(encoding="utf-8"), real_source)


class SealCorpusUntouchedTests(unittest.TestCase):
    """14.7: `tests/seal/` carries no uncommitted changes at the end of this
    phase -- asserted here via the same mechanism, in-process, rather than
    shelling out from inside the suite.

    TANDA B M5: `git diff --exit-code` reads worktree against the index and
    never reports an untracked path, since it is in neither. `git status
    --porcelain` reads both states, so a stray file beside the seal is
    reported the same way a modified one already was."""

    def test_the_seal_corpus_directory_has_no_uncommitted_changes(self):
        import subprocess
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--", "tests/seal/"],
            cwd=str(FORGE), capture_output=True, text=True)
        self.assertEqual(
            proc.stdout, "",
            f"tests/seal/ has uncommitted changes:\n{proc.stdout}")

    def test_an_untracked_file_beside_the_seal_is_caught(self):
        import subprocess
        planted = FORGE / "tests/seal/PLANTED_extra_M5.json"
        planted.write_text("{}\n", encoding="utf-8")
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain", "--", "tests/seal/"],
                cwd=str(FORGE), capture_output=True, text=True)
            self.assertIn("PLANTED_extra_M5.json", proc.stdout)
        finally:
            planted.unlink()


import test_implementation_domain_lock as domain_lock  # noqa: E402  (path set above)


class M5MutationTests(unittest.TestCase):
    """Task 4.7 (design.md D9): X5/X6/X7, each against a SCRATCH COPY of
    the engine only -- never the real engine -- the same mechanism
    `test_implementation_domain_mutation.py` already has for its own
    per-leaf change mutations. Reuses `domain_lock.build_denylist`/
    `discover_profiles` directly (both Python, both this same suite --
    unlike `LockBHonestyTests`'s inline duplication, which exists
    specifically to avoid a shared import between the TS lock and this
    one)."""

    @staticmethod
    def _scratch_engine_dir(real_source: str) -> Path:
        tmp = tempfile.mkdtemp(prefix="m5-scratch-engine-")
        scratch_dir = Path(tmp) / "engine"
        scratch_dir.mkdir()
        (scratch_dir / "implementation_engine.py").write_text(
            real_source, encoding="utf-8")
        return scratch_dir

    def test_x5_a_planted_denylist_word_reddens_test_2(self):
        """Plant a denylist word into a scratch engine copy; the scan
        `test_2_no_unpinned_denylist_word_appears_in_the_engine` performs
        must find it, naming the file and word."""
        real_source = (ENGINE_DIR / "implementation_engine.py").read_text(
            encoding="utf-8")
        denylist = domain_lock.build_denylist(domain_lock.discover_profiles())
        # An unpinned word: present in the denylist, absent from
        # `M5_PINNED_RESIDUE` -- one of the five genuinely-absent words.
        unpinned = [w for w in denylist
                   if w not in domain_lock.M5_PINNED_RESIDUE]
        self.assertGreater(len(unpinned), 0, "no unpinned denylist word to plant")
        planted_word = unpinned[0]
        self.assertNotIn(planted_word, real_source.lower())

        with tempfile.TemporaryDirectory() as tmp:
            scratch_dir = Path(tmp) / "engine"
            scratch_dir.mkdir()
            planted_source = real_source + f"\n# a planted {planted_word} comment\n"
            (scratch_dir / "implementation_engine.py").write_text(
                planted_source, encoding="utf-8")

            leaks = []
            for path in sorted(scratch_dir.rglob("*.py")):
                source = path.read_text(encoding="utf-8")
                if re.search(rf"\b{planted_word}\b", source, re.IGNORECASE):
                    leaks.append(path.name)
            self.assertEqual(leaks, ["implementation_engine.py"])

    def test_x6_deleting_a_pinned_occurrence_reddens_test_3(self):
        """Delete one occurrence of a pinned residue word from a scratch
        engine copy; the count `test_3` measures against that scratch copy
        must disagree with the real pin."""
        real_source = (ENGINE_DIR / "implementation_engine.py").read_text(
            encoding="utf-8")
        word = "materialized"
        pinned_count = domain_lock.M5_PINNED_RESIDUE[word]
        real_count = len(re.findall(rf"\b{word}\b", real_source, re.IGNORECASE))
        self.assertEqual(real_count, pinned_count)

        pattern = re.compile(rf"\b{word}\b", re.IGNORECASE)
        mutated_source = pattern.sub("REMOVED", real_source, count=1)
        mutated_count = len(re.findall(rf"\b{word}\b", mutated_source, re.IGNORECASE))
        self.assertEqual(mutated_count, pinned_count - 1)

    def test_x7_copying_the_siblings_purpose_over_this_norths_empties_the_denylist(self):
        """Copy the sibling's `purpose` text over this north's own; the
        vacuity guard (`test_1`) must fail: with both norths sharing the
        SAME purpose text, every word in it becomes common to both and can
        no longer be a single-owner subject word."""
        profiles = domain_lock.discover_profiles()
        by_name = {entry["skill_name"]: entry["profile"] for entry in profiles}
        sibling = by_name["proposal-implementation"]
        this_skill = by_name["experimental-implementation"]

        mutated_this_skill = dict(this_skill)
        mutated_objective = dict(this_skill["objective"])
        mutated_objective["purpose"] = sibling["objective"]["purpose"]
        mutated_this_skill["objective"] = mutated_objective

        mutated_profiles = [
            {"skill_name": "experimental-implementation",
             "profile": mutated_this_skill},
            {"skill_name": "proposal-implementation", "profile": sibling},
        ]
        denylist = domain_lock.build_denylist(mutated_profiles)
        shared_purpose_words = domain_lock.north_words(
            {"objective": {"purpose": sibling["objective"]["purpose"],
                          "arrival": "", "humanStops": [], "stages": []}})
        self.assertTrue(shared_purpose_words, "no >=5-letter word in the shared purpose")
        for word in shared_purpose_words:
            self.assertNotIn(
                word, denylist,
                f"{word!r} is shared between both norths' purpose text now "
                "and must not remain single-owner")


if __name__ == "__main__":
    unittest.main()
