"""Change `the-second-skill-the-seam-was-for`, slice A1: this skill's own
profile resolves through the SAME shared resolver
(`_core/implementation/impl_domain_profile.py`) the sibling
(`proposal-implementation`) already proves generically. This file proves the
SECOND host, not the resolver again -- one refusal case per validated leaf
(mirroring `tests/test_implementation_profile.py`'s
`DomainFieldLeafRefusalTests`, structurally, never a shared import), the
launcher's byte-equality to the sibling's (design.md D4/M4, mutation X3),
and the citation pattern's exactly-three-group shape (task 1.4, M2).
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Mapping

FORGE = Path(__file__).resolve().parents[1]
SKILL_DIR = FORGE / "skills" / "experimental-implementation"
PROFILE_FILE = SKILL_DIR / "impl_profile.py"
LAUNCHER = SKILL_DIR / "scripts" / "implementation_cli.py"
SIBLING_LAUNCHER = (
    FORGE / "skills" / "proposal-implementation" / "scripts"
    / "implementation_cli.py")
RESOLVER = FORGE / "skills/_core/implementation/impl_domain_profile.py"

_counter = itertools.count()


def _load_module(path: Path, prefix: str):
    """A fresh, uncached load -- never the plain `import` statement, which
    would share `sys.modules` state with every other test file that has
    already imported the same-named module under a different profile."""
    name = f"{prefix}_{next(_counter)}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _real_profile() -> Mapping:
    return _load_module(PROFILE_FILE, "experimental_impl_profile_probe").PROFILE


def _resolve_with(profile_file: Path):
    """A fresh, uncached load of the RESOLVER under a controlled env --
    the resolver validates and raises at import time."""
    import os
    import contextlib

    @contextlib.contextmanager
    def _env(value):
        had = "IMPLEMENTATION_DOMAIN_PROFILE" in os.environ
        original = os.environ.get("IMPLEMENTATION_DOMAIN_PROFILE")
        os.environ["IMPLEMENTATION_DOMAIN_PROFILE"] = value
        try:
            yield
        finally:
            if had:
                os.environ["IMPLEMENTATION_DOMAIN_PROFILE"] = original
            else:
                os.environ.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)

    name = f"experimental_impl_resolver_probe_{next(_counter)}"
    spec = importlib.util.spec_from_file_location(name, RESOLVER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        with _env(str(profile_file)):
            spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _to_source(value) -> str:
    if isinstance(value, Mapping):
        items = ", ".join(f"{k!r}: {_to_source(v)}" for k, v in value.items())
        return "{" + items + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_to_source(v) for v in value) + "]"
    if isinstance(value, Path):
        return f"Path({str(value)!r})"
    return repr(value)


#: The sixteen validated leaves this skill's profile must declare (design.md
#: D2), named the same way `test_implementation_profile.py::_CUT2_LEAVES`
#: names them, `documents[0].*` indexed rather than flat (Cut 3, D4).
_LEAVES: tuple[str, ...] = (
    "kit.root",
    "cli.path",
    "provenance.claim_key",
    "provenance.authored_init_sentence",
    "findings.locus_key",
    "findings.remedy_locus_key",
    "findings.notation_keys",
    "findings.citation_pattern",
    "vocabulary.subject_singular",
    "vocabulary.subject_plural",
    "vocabulary.subject_singular_es",
    "vocabulary.subject_plural_es",
    "vocabulary.subject_collective",
    "vocabulary.subject_collective_es",
    "vocabulary.artifact_noun",
    "vocabulary.names",
    "documents[0].directory",
    "documents[0].label",
)

_INDEXED_LEAF_RE = re.compile(r"^documents\[(\d+)\]\.(directory|label)$")


def _without_leaf(profile: dict, dotted: str) -> dict:
    clone = copy.deepcopy(profile)
    indexed = _INDEXED_LEAF_RE.match(dotted)
    if indexed:
        index, key = int(indexed.group(1)), indexed.group(2)
        del clone["documents"][index][key]
        return clone
    section, key = dotted.split(".", 1)
    del clone[section][key]
    return clone


class LeafRefusalTests(unittest.TestCase):
    """Mutation X1 (design.md): delete each of the sixteen validated leaves
    one at a time -- the resolver refuses `..._INCOMPLETE` naming exactly
    that leaf, never its section alone."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="experimental-impl-leaf-"))
        self.addCleanup(__import__("shutil").rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_each_validated_leaf_refuses_incomplete_and_names_itself(self):
        full = dict(_real_profile())
        for dotted in _LEAVES:
            with self.subTest(leaf=dotted):
                tmp_dir = self._tmp_dir()
                incomplete = _without_leaf(full, dotted)
                profile_file = tmp_dir / "impl_profile.py"
                profile_file.write_text(
                    "from pathlib import Path\n"
                    f"PROFILE = {_to_source(incomplete)}\n",
                    encoding="utf-8")
                with self.assertRaises(RuntimeError) as ctx:
                    _resolve_with(profile_file)
                message = str(ctx.exception)
                self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
                self.assertIn(dotted, message)

    def test_the_real_profile_resolves_cleanly(self):
        """The positive control every refusal case above is a mutation OF."""
        module = _resolve_with(PROFILE_FILE)
        self.assertEqual(module.PROFILE["provenance"]["claim_key"], "experiments")
        self.assertEqual(module.PROFILE["documents"][0]["label"], "experiments")


class CitationPatternGroupCountTests(unittest.TestCase):
    """Task 1.4 (M2, design.md): `_impact_class` reads `match.group(1) or
    match.group(2) or match.group(3)` -- a two-group pattern raises
    `IndexError`, a four-group pattern silently drops the fourth. Scoped to
    THIS profile's own pattern only; validating `_resolve()`/`_impact_class`
    itself is out of scope (D2/M2, deferred to change C per design.md Q3)."""

    def test_this_profiles_citation_pattern_compiles_to_exactly_three_groups(self):
        pattern = _real_profile()["findings"]["citation_pattern"]
        compiled = re.compile(pattern)
        self.assertEqual(compiled.groups, 3)


#: `a-data-directory-somebody-can-owe` (B1). The engine's shared
#: `impl_domain_profile` import is a plain `from impl_domain_profile import
#: PROFILE` (fixed module name), cached process-wide in `sys.modules` --
#: every fresh engine re-import below must `pop` it first, or a later call
#: silently reads an earlier test's already-resolved profile (the exact
#: scar `test_implementation_domain_mutation.py` records for its own
#: mutation harness).
ENGINE_DIR = FORGE / "skills" / "_core" / "implementation" / "engine"


def _engine_with_documents(documents: list[dict]):
    """A fresh engine import whose ONLY difference from the real,
    resolving `experimental-implementation` profile is its `documents`
    list -- every other leaf is untouched, so the resolver's other checks
    stay satisfied and only the detector's own behaviour is exercised.

    `IMPLEMENTATION_DOMAIN_PROFILE` and the `impl_domain_profile` entry
    in `sys.modules` are both restored to their PRE-CALL state before
    returning -- this whole process's environment and module cache are
    shared with every other test file `unittest discover` runs in the
    same process, and leaving either one set would silently redirect an
    unrelated, later-running suite's own profile resolution (measured:
    it did, reddening ~110 cases in `test_proposal_implementation.py`
    before this restore existed)."""
    profile = dict(_real_profile())
    profile["documents"] = documents
    tmp_dir = Path(tempfile.mkdtemp(prefix="dataset-marker-detector-"))
    profile_file = tmp_dir / "impl_profile.py"
    profile_file.write_text(
        "from pathlib import Path\n"
        f"PROFILE = {_to_source(profile)}\n",
        encoding="utf-8")

    env_var = "IMPLEMENTATION_DOMAIN_PROFILE"
    had_env = env_var in os.environ
    original_env = os.environ.get(env_var)
    os.environ[env_var] = str(profile_file)
    sys.modules.pop("impl_domain_profile", None)
    if str(ENGINE_DIR) not in sys.path:
        sys.path.insert(0, str(ENGINE_DIR))
    name = f"experimental_impl_engine_probe_{next(_counter)}"
    spec = importlib.util.spec_from_file_location(
        name, ENGINE_DIR / "implementation_engine.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
        sys.modules.pop("impl_domain_profile", None)
        if had_env:
            os.environ[env_var] = original_env
        else:
            os.environ.pop(env_var, None)
    return module, tmp_dir


#: `the-agreement-nothing-computes` (Slice D, design.md D1/R2): every
#: `documents[N]` entry this file constructs by hand now needs a complete,
#: valid `block_locator` -- required and non-nullable. Real content is
#: irrelevant to what these fixtures exist to prove.
def _block_locator() -> dict:
    return {
        "pattern": r"(?m)^## (\d+)$",
        "block_pattern": r"(?s)## \d+.*?(?=\n## |\Z)",
        "identity": "## {value}",
    }

class DatasetDeclaredDetectorTests(unittest.TestCase):
    """B1 (`a-data-directory-somebody-can-owe`, design.md D1/D2, tasks.md
    Phase 2): the dataset-declared detector, proven directly -- pure
    function, no CLI dispatch, so an in-process fresh-engine import is not
    the "monkeypatch has zero effect on a subprocess" scar (that scar is
    about a DIFFERENT process reading a patched attribute; this is the
    SAME process calling a freshly-imported module's own function)."""

    def _tmp_docs_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="dataset-marker-docs-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_a_none_marker_never_opens_the_document(self):
        """The revision names a file that does not exist at all -- proving
        only that a missing file does not raise would be true of ANY
        marker (`revision_source` already tolerates absence); the
        property under test is that a `None`-marked entry never attempts
        the read in the first place, proven by a spy on `revision_source`
        itself."""
        docs_dir = self._tmp_docs_dir()
        engine, _ = _engine_with_documents([
            {"directory": docs_dir, "label": "experiments", "dataset_marker": None,
             "block_locator": _block_locator(), "cross_citation": None},
        ])
        calls = []
        original = engine.revision_source

        def _spy(revision, index=0):
            calls.append((revision, index))
            return original(revision, index)

        engine.revision_source = _spy
        self.assertFalse(engine.declares_dataset("does-not-exist.md"))
        self.assertEqual(
            calls, [],
            "a None-marked document must never open a file at all, and this "
            "spy proves revision_source was never called for it")

    def test_a_declared_marker_present_at_line_start_answers_true(self):
        docs_dir = self._tmp_docs_dir()
        (docs_dir / "r1.md").write_text(
            "intro line\n**Dataset:** the corpus\nmore text\n", encoding="utf-8")
        engine, _ = _engine_with_documents([
            {"directory": docs_dir, "label": "experiments",
             "dataset_marker": "**Dataset:**",
             "block_locator": _block_locator(), "cross_citation": None},
        ])
        self.assertTrue(engine.declares_dataset("r1.md"))

    def test_a_mid_sentence_only_occurrence_answers_false(self):
        """X3's own strength case: `lstrip().startswith(marker)`, never a
        bare substring test -- a document that only DISCUSSES its own
        format ("every protocol needs a **Dataset:** line") must not
        satisfy a substring test while declaring nothing (design.md D1)."""
        docs_dir = self._tmp_docs_dir()
        (docs_dir / "r1.md").write_text(
            "every protocol needs a **Dataset:** line somewhere\n"
            "but this one never puts it first\n", encoding="utf-8")
        engine, _ = _engine_with_documents([
            {"directory": docs_dir, "label": "experiments",
             "dataset_marker": "**Dataset:**",
             "block_locator": _block_locator(), "cross_citation": None},
        ])
        self.assertFalse(engine.declares_dataset("r1.md"))

    def test_a_marker_with_regex_metacharacters_matches_only_literally(self):
        """Threat-matrix row (host-supplied text matched against file
        bytes): the marker is a literal, never a regex -- a document
        carrying unrelated text a regex interpretation of the marker
        WOULD match must still answer false."""
        docs_dir = self._tmp_docs_dir()
        marker = "Da.*taset:"
        (docs_dir / "r1.md").write_text(
            # A regex built from `marker` would match this line (any char
            # for `.`, zero-or-more `a` for `*`); a literal match must not.
            "Dazzzztaset: this is not the literal marker\n", encoding="utf-8")
        engine, _ = _engine_with_documents([
            {"directory": docs_dir, "label": "experiments",
             "dataset_marker": marker, "block_locator": _block_locator(),
             "cross_citation": None},
        ])
        self.assertFalse(engine.declares_dataset("r1.md"))

        (docs_dir / "r2.md").write_text(f"{marker} literally, at line start\n",
                                        encoding="utf-8")
        self.assertTrue(engine.declares_dataset("r2.md"))

    def test_or_fold_only_index_one_declares_and_the_demand_still_holds(self):
        """Kills "read index 0 always" (design.md D2): index 0 declares
        `None`, index 1 declares a real marker present in ITS OWN
        discovered revision -- the demand must still answer true,
        or-folded across every declared document."""
        doc0_dir = self._tmp_docs_dir()
        (doc0_dir / "r1.md").write_text("no marker here\n", encoding="utf-8")
        doc1_dir = self._tmp_docs_dir()
        (doc1_dir / "only-candidate-9.md").write_text(
            "**Dataset:** declared only here\n", encoding="utf-8")
        engine, _ = _engine_with_documents([
            {"directory": doc0_dir, "label": "experiments", "dataset_marker": None,
             "block_locator": _block_locator(), "cross_citation": None},
            {"directory": doc1_dir, "label": "proposal",
             "dataset_marker": "**Dataset:**", "block_locator": _block_locator(),
             "cross_citation": None},
        ])
        self.assertTrue(engine.declares_dataset("r1.md"))

    def test_no_revision_at_all_answers_false_and_discovers_nothing(self):
        """Property 2 (design.md): a `None` seed (`plan` with no
        `--revision`) must short-circuit before EVER discovering document
        1's own revision -- proven the same way as the None-marker case,
        by spying on the discovery entry point."""
        doc0_dir = self._tmp_docs_dir()
        doc1_dir = self._tmp_docs_dir()
        (doc1_dir / "candidate-9.md").write_text(
            "**Dataset:** would be found if discovery ran\n", encoding="utf-8")
        engine, _ = _engine_with_documents([
            {"directory": doc0_dir, "label": "experiments", "dataset_marker": None,
             "block_locator": _block_locator(), "cross_citation": None},
            {"directory": doc1_dir, "label": "proposal",
             "dataset_marker": "**Dataset:**", "block_locator": _block_locator(),
             "cross_citation": None},
        ])
        calls = []
        original = engine.document_revision_names

        def _spy(revision):
            calls.append(revision)
            return original(revision)

        engine.document_revision_names = _spy
        self.assertFalse(engine.declares_dataset(None))
        self.assertEqual(
            calls, [],
            "declares_dataset(None) must never call document_revision_names "
            "at all -- no discovery, ever, absent an explicit revision")


class RevisionThreadingAgreementTests(unittest.TestCase):
    """Phase 3 (design.md D3/D4, tasks.md 3.1-3.3): `--revision` reaches
    all three `build_plan` call sites -- `plan` (the ONLY parser
    registration), `apply` and `materialize`'s own gate (both re-derive
    the seed from the approved plan's own `boundTo` key, never a second
    `--revision` flag). Real subprocesses throughout, against a SCRATCH
    profile declaring a real marker -- never the shipped
    experimental-implementation profile, whose own marker stays `None`
    until B2 (design.md D10)."""

    PACKAGE = "PlanRevision"

    def setUp(self):
        self.docs_dir = Path(tempfile.mkdtemp(prefix="plan-revision-docs-"))
        self.addCleanup(shutil.rmtree, self.docs_dir, ignore_errors=True)
        (self.docs_dir / "r1.md").write_text(
            "**Dataset:** declared here\n", encoding="utf-8")
        self.profile_file = self._write_profile_with_marker(self.docs_dir)

    def _write_profile_with_marker(self, docs_dir: Path) -> Path:
        profile = dict(_real_profile())
        profile["documents"] = [
            {"directory": docs_dir, "label": "experiments",
             "dataset_marker": "**Dataset:**",
             # `the-agreement-nothing-computes` (Slice D, design.md D1/R2):
             # required, own tier, non-nullable.
             "block_locator": {
                 "pattern": r"(?m)^## (\d+)$",
                 "block_pattern": r"(?s)## \d+.*?(?=\n## |\Z)",
                 "identity": "## {value}",
             },
             # `the-agreement-nothing-computes` (Slice D, design.md D5/R1):
             # required, own tier, NULLABLE -- this scratch profile is
             # single-document, so there is no other declared label to
             # cross against.
             "cross_citation": None},
        ]
        tmp_profile_dir = Path(tempfile.mkdtemp(prefix="plan-revision-profile-"))
        self.addCleanup(shutil.rmtree, tmp_profile_dir, ignore_errors=True)
        profile_file = tmp_profile_dir / "impl_profile.py"
        profile_file.write_text(
            "from pathlib import Path\n"
            f"PROFILE = {_to_source(profile)}\n",
            encoding="utf-8")
        return profile_file

    def _env(self, profile_file: Path | None = None) -> dict:
        env = dict(os.environ)
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(profile_file or self.profile_file)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "plan-revision-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = (
            "plan-revision-tests@example.invalid")
        return env

    def _box(self, suffix: str) -> Path:
        box = FORGE / "implementations" / f"_plan_revision_{os.getpid()}_{id(self)}{suffix}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        env = self._env()
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

    def _run(self, *args: str, profile_file: Path | None = None):
        return subprocess.run(
            [sys.executable, str(LAUNCHER), *args],
            capture_output=True, text=True, cwd=FORGE,
            env=self._env(profile_file))

    def _approved_plan_path(self, plan: dict) -> Path:
        plan_dir = Path(tempfile.mkdtemp(prefix="plan-revision-approved-"))
        self.addCleanup(shutil.rmtree, plan_dir, ignore_errors=True)
        plan_path = plan_dir / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return plan_path

    def test_plan_with_no_revision_opens_no_document_and_stays_byte_identical(self):
        """Property 2 (design.md), reading-at-plan-time threat row:
        absent `--revision`, `plan`'s output must not depend on the
        document at all. Proven by pointing the profile's own document
        root at a NONEXISTENT directory and asserting `plan` still
        succeeds, identically to the same command against the real one --
        a read attempt against a missing directory would surface
        differently were it ever made."""
        missing_root = Path(tempfile.mkdtemp(prefix="plan-revision-missing-")) / "gone"
        self.addCleanup(shutil.rmtree, missing_root.parent, ignore_errors=True)
        missing_docs_profile = self._write_profile_with_marker(missing_root)
        box = self._box("_control")

        with_docs = self._run("plan", "--target", str(box), "--name", self.PACKAGE)
        without_docs = self._run(
            "plan", "--target", str(box), "--name", self.PACKAGE,
            profile_file=missing_docs_profile)

        self.assertEqual(with_docs.returncode, 0, with_docs.stderr)
        self.assertEqual(without_docs.returncode, 0, without_docs.stderr)
        self.assertEqual(with_docs.stdout, without_docs.stdout)
        self.assertNotIn("boundTo", json.loads(with_docs.stdout))

    def test_plan_approve_apply_agree_and_create_dirs_holds_the_declared_data(self):
        box = self._box("_agreement")
        plan_proc = self._run(
            "plan", "--target", str(box), "--name", self.PACKAGE,
            "--revision", "r1.md")
        self.assertEqual(plan_proc.returncode, 0, plan_proc.stderr)
        plan = json.loads(plan_proc.stdout)
        self.assertIn(f"{self.PACKAGE}/Data", plan["createDirs"])
        self.assertEqual(plan["boundTo"]["revision"], "r1.md")

        apply_proc = self._run(
            "apply", "--target", str(box), "--name", self.PACKAGE,
            "--plan", str(self._approved_plan_path(plan)))
        self.assertEqual(apply_proc.returncode, 0, apply_proc.stderr)
        applied = json.loads(apply_proc.stdout)
        self.assertIn(f"{self.PACKAGE}/Data", applied["createdDirs"])

    def test_a_bare_apply_after_plan_revision_cannot_produce_plan_stale(self):
        """D3's own risk: an operator who ran `plan --revision X` and then
        a bare `apply` must not refuse `PLAN_STALE` -- the seed is
        carried in the approved plan's own `boundTo` key, never
        re-typed."""
        box = self._box("_bare_apply")
        plan_proc = self._run(
            "plan", "--target", str(box), "--name", self.PACKAGE,
            "--revision", "r1.md")
        self.assertEqual(plan_proc.returncode, 0, plan_proc.stderr)
        plan = json.loads(plan_proc.stdout)

        apply_proc = self._run(
            "apply", "--target", str(box), "--name", self.PACKAGE,
            "--plan", str(self._approved_plan_path(plan)))
        self.assertEqual(apply_proc.returncode, 0, apply_proc.stderr)
        self.assertNotEqual(
            json.loads(apply_proc.stdout).get("code"), "PLAN_STALE")

    def test_materialize_stage_gate_refuses_plan_stale_on_the_same_drift_apply_would(self):
        """Repeat through `materialize --stage` (tasks.md 3.2):
        `_materialize_plan_gate` alone, proven independent of any
        specific stage's own kit requirement (this domain ships none,
        SKILL.md) -- the marker is removed from the SAME revision file
        after approval, so the gate's own re-derivation of `createDirs`
        disagrees with the approved plan and refuses before any
        stage-specific write."""
        box = self._box("_materialize_gate")
        plan_proc = self._run(
            "plan", "--target", str(box), "--name", self.PACKAGE,
            "--revision", "r1.md")
        self.assertEqual(plan_proc.returncode, 0, plan_proc.stderr)
        plan_path = self._approved_plan_path(json.loads(plan_proc.stdout))

        (self.docs_dir / "r1.md").write_text("no marker anymore\n", encoding="utf-8")

        proc = self._run(
            "materialize", "--target", str(box), "--name", self.PACKAGE,
            "--stage", "scaffold", "--plan", str(plan_path), "--seed", "7")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout).get("code"), "PLAN_STALE")

    def test_a_pre_existing_plan_with_no_bound_to_key_still_applies(self):
        """Data-integrity row (design.md): an approved plan.json with no
        `boundTo` key at all (every plan.json on disk before this
        change) still applies --
        `(approved.get("boundTo") or {}).get("revision")` falls back to
        `None`, today's exact branch."""
        box = self._box("_no_bound_to")
        plan_proc = self._run("plan", "--target", str(box), "--name", self.PACKAGE)
        self.assertEqual(plan_proc.returncode, 0, plan_proc.stderr)
        plan = json.loads(plan_proc.stdout)
        self.assertNotIn("boundTo", plan)

        apply_proc = self._run(
            "apply", "--target", str(box), "--name", self.PACKAGE,
            "--plan", str(self._approved_plan_path(plan)))
        self.assertEqual(apply_proc.returncode, 0, apply_proc.stderr)


class LauncherByteEqualityTests(unittest.TestCase):
    """Design.md D4/M4: a byte-for-byte copy of the sibling's launcher --
    not a symlink, not an import. Mutation X3: flip one byte, confirm this
    test fails, restore."""

    def test_the_launcher_is_byte_identical_to_the_siblings(self):
        self.assertEqual(
            LAUNCHER.read_bytes(), SIBLING_LAUNCHER.read_bytes(),
            "the launcher must be a byte-for-byte copy of the sibling's own "
            "launcher (design.md D4): every value in it is derived from "
            "Path(__file__).resolve(), so a byte-identical copy placed here "
            "resolves to THIS skill's own profile")


class PublishedCommandsRunVerbatimTests(unittest.TestCase):
    """Task 3.7 (design.md D8): every command string this skill's OWN
    `SKILL.md` publishes must run verbatim through THIS skill's own
    launcher. The sibling's own `PublishedCommandsRunVerbatimTests`
    (`tests/test_proposal_implementation.py`) is bound to `SKILL_ROOT =
    proposal-implementation` and cannot see this file at all -- this is
    the new suite's own, never a shared import."""

    SKILL_MD = SKILL_DIR / "SKILL.md"

    #: Every fenced ```bash block whose first non-blank line begins with
    #: this skill's own launcher path -- a syntactic shape, not a
    #: hand-kept list of which lines to check.
    _FENCE_RE = re.compile(r"```bash\n(.*?)```", re.DOTALL)

    def _published_commands(self) -> list[str]:
        text = self.SKILL_MD.read_text(encoding="utf-8")
        launcher_rel = str(LAUNCHER.relative_to(FORGE))
        commands = []
        for block in self._FENCE_RE.findall(text):
            for line in block.splitlines():
                line = line.strip()
                # `<command>`/`<TARGET>`-shaped placeholders name the usage
                # TEMPLATE, never a concrete runnable line -- skipped here,
                # never silently "run" against a literal `<...>` string.
                if line.startswith(launcher_rel) and "<" not in line:
                    commands.append(line)
        return commands

    def test_the_doctrine_publishes_at_least_one_concrete_command(self):
        self.assertGreater(
            len(self._published_commands()), 0,
            "SKILL.md publishes no concrete, runnable command line -- this "
            "check would otherwise be vacuous")

    def test_every_published_command_runs_verbatim_through_this_launcher(self):
        launcher_rel = str(LAUNCHER.relative_to(FORGE))
        for command in self._published_commands():
            with self.subTest(command=command):
                argv = command[len(launcher_rel):].strip().split()
                proc = subprocess.run(
                    [sys.executable, str(LAUNCHER)] + argv,
                    cwd=str(FORGE), capture_output=True, text=True, timeout=30)
                self.assertEqual(
                    proc.returncode, 0,
                    f"published command {command!r} did not run cleanly "
                    f"through this skill's own launcher: "
                    f"{proc.stdout}{proc.stderr}")


class DoctrineVocabularyLeakTests(unittest.TestCase):
    """Task 3.8: `tests/forge_vocabulary.py::shipped_documents()` scans this
    skill's directory unedited -- proven directly, not assumed -- and the
    doctrine spells none of the denylisted target words."""

    def test_shipped_documents_discovers_this_skills_own_files(self):
        sys.path.insert(0, str(FORGE / "tests"))
        import forge_vocabulary  # noqa: E402  (path set above)
        documents = forge_vocabulary.shipped_documents()
        under_this_skill = [
            path for path in documents
            if SKILL_DIR in path.parents]
        self.assertGreater(
            len(under_this_skill), 0,
            "shipped_documents() discovers no file under this skill's own "
            "directory")

    def test_the_doctrine_spells_no_denylisted_target_word(self):
        sys.path.insert(0, str(FORGE / "tests"))
        import forge_vocabulary  # noqa: E402  (path set above)
        for document in (SKILL_DIR / "SKILL.md",
                         FORGE / ".claude" / "agents" / "experiments-build.md",
                         FORGE / ".claude" / "agents" / "experiments-walk.md",
                         PROFILE_FILE):
            with self.subTest(document=document.name):
                text = document.read_text(encoding="utf-8")
                leaks = forge_vocabulary.leaks_in(text)
                self.assertEqual(leaks, [], f"{document.name} spells {leaks}")


class RemedyCompatibilityPerDocumentTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md D4/M4, tasks.md
    1.16-1.20, 1.29-1.30): `remedy_compatibility`'s per-document field
    loop, proven against THIS skill's own shipped two-document profile --
    `documents[0]` (`experiments`, heading locator) and `documents[1]`
    (`proposal`, LaTeX locator, `claim_key: "equations"`).

    Pure function, no CLI dispatch: an in-process fresh-engine import is
    not the "monkeypatch has zero effect on a subprocess" scar (that scar
    is about a DIFFERENT process reading a patched attribute; this is the
    SAME process calling a freshly-imported module's own function),
    mirroring `DatasetDeclaredDetectorTests`'s own standing rule.
    """

    def _tmp_dir(self, prefix: str) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _engine_with_proposals_override(self, doc0_dir: Path, doc1_dir: Path):
        """The real, unmodified two-document profile, with both documents'
        proposals roots overridden via the engine's own supported env
        vars (`proposals_root`'s own `setdefault`-independent override) --
        never a `directory` edit, which would exercise a different code
        path than what ships."""
        module, _ = _engine_with_documents(_real_profile()["documents"])
        had_0 = "IMPLEMENTATION_PROPOSALS" in os.environ
        original_0 = os.environ.get("IMPLEMENTATION_PROPOSALS")
        had_1 = "IMPLEMENTATION_PROPOSALS_1" in os.environ
        original_1 = os.environ.get("IMPLEMENTATION_PROPOSALS_1")
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(doc0_dir)
        os.environ["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_dir)

        def _restore():
            if had_0:
                os.environ["IMPLEMENTATION_PROPOSALS"] = original_0
            else:
                os.environ.pop("IMPLEMENTATION_PROPOSALS", None)
            if had_1:
                os.environ["IMPLEMENTATION_PROPOSALS_1"] = original_1
            else:
                os.environ.pop("IMPLEMENTATION_PROPOSALS_1", None)

        self.addCleanup(_restore)
        return module

    def test_a_finding_naming_document_one_alone_is_checked_against_its_own_keys(self):
        """The M4 control (task 1.16): a finding whose `document` is
        `["proposal"]` alone, declaring `remedy_equations` (document 1's
        own `remedy_locus_key`) naming a locus absent from document 1's
        text. Reported as an unmet locus -- where before this capability
        `finding.get("remedy_experiments", [])` was `[]` and the finding
        read compatible (spec `implementation-block-locator`, "A finding
        naming a second document is checked against its own keys")."""
        doc0_dir = self._tmp_dir("m4-doc0-")
        doc1_dir = self._tmp_dir("m4-doc1-")
        (doc0_dir / "e1.md").write_text("## 1\n\nnothing relevant.\n", encoding="utf-8")
        (doc1_dir / "p1.md").write_text(
            "The proposal declares $$a = b \\tag{1}$$ only.\n", encoding="utf-8")
        module = self._engine_with_proposals_override(doc0_dir, doc1_dir)

        finding = {
            "id": "doc1-only", "document": ["proposal"],
            "remedy_equations": ["99"], "uses": ["a = b"], "introduces": [],
        }
        result = module.remedy_compatibility(
            [finding], "e1.md",
            sources_by_document={"experiments": module.revision_source("e1.md", 0),
                                 "proposal": module.revision_source("p1.md", 1)})
        unknown = result[module.NOTATION_KEYS["unknown"]]
        self.assertEqual(unknown, ["doc1-only.remedy_equations: ['99']"])
        self.assertEqual(result["status"], "incompatible")

    def test_a_finding_naming_document_one_with_a_declared_locus_is_compatible(self):
        """Positive control: the identical shape, but the locus IS declared
        in document 1's own text."""
        doc0_dir = self._tmp_dir("m4-pos-doc0-")
        doc1_dir = self._tmp_dir("m4-pos-doc1-")
        (doc0_dir / "e1.md").write_text("## 1\n\nnothing relevant.\n", encoding="utf-8")
        (doc1_dir / "p1.md").write_text(
            "The proposal declares $$a = b \\tag{99}$$.\n", encoding="utf-8")
        module = self._engine_with_proposals_override(doc0_dir, doc1_dir)

        finding = {
            "id": "doc1-declared", "document": ["proposal"],
            "remedy_equations": ["99"], "uses": ["a = b"], "introduces": [],
        }
        result = module.remedy_compatibility(
            [finding], "e1.md",
            sources_by_document={"experiments": module.revision_source("e1.md", 0),
                                 "proposal": module.revision_source("p1.md", 1)})
        self.assertEqual(result[module.NOTATION_KEYS["unknown"]], [])

    def test_z4_reverting_to_the_bare_module_scalar_reads_compatible_again(self):
        """Z4 (design.md Mutation plan, task 1.29): replace
        `vocab["locus_key"]`/`vocab["remedy_locus_key"]` with the bare
        `LOCUS_KEY`/`REMEDY_LOCUS_KEY` module scalars in a SCRATCH copy of
        the engine; confirm the M4 case above goes red (reads compatible
        again); confirm `tests/seal/` survives (the branch is unreachable
        under one document -- proven separately by the sibling's own
        suite, unaffected by this scratch copy)."""
        real_source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        anchor = (
            "for field in (vocab[\"locus_key\"], vocab[\"remedy_locus_key\"]):")
        # `cmd_admit` (index 0, unchanged per D3) already spells the bare
        # `LOCUS_KEY, REMEDY_LOCUS_KEY` pair at its own, unrelated site --
        # so the replacement text is not a fresh spelling engine-wide, only
        # a fresh spelling AT THIS anchor. `anchor`'s own count (1, both
        # directions) is what proves this specific mutation ran.
        mutated_anchor = "for field in (LOCUS_KEY, REMEDY_LOCUS_KEY):"
        self.assertEqual(real_source.count(anchor), 1)
        mutated_source = real_source.replace(anchor, mutated_anchor, 1)
        self.assertEqual(mutated_source.count(anchor), 0)

        doc0_dir = self._tmp_dir("z4-doc0-")
        doc1_dir = self._tmp_dir("z4-doc1-")
        (doc0_dir / "e1.md").write_text("## 1\n\nnothing relevant.\n", encoding="utf-8")
        (doc1_dir / "p1.md").write_text(
            "The proposal declares $$a = b \\tag{1}$$ only.\n", encoding="utf-8")

        scratch_core = Path(tempfile.mkdtemp(prefix="z4-core-"))
        self.addCleanup(shutil.rmtree, scratch_core, ignore_errors=True)
        shutil.copytree(ENGINE_DIR.parent, scratch_core / "core",
                        ignore=shutil.ignore_patterns("__pycache__"),
                        dirs_exist_ok=True)
        (scratch_core / "core" / "engine" / "implementation_engine.py").write_text(
            mutated_source, encoding="utf-8")

        env = os.environ.copy()
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(PROFILE_FILE)
        env["IMPLEMENTATION_PROPOSALS"] = str(doc0_dir)
        env["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_dir)
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(scratch_core / 'core' / 'engine')!r})\n"
            "import implementation_engine as impl\n"
            "finding = {'id': 'doc1-only', 'document': ['proposal'], "
            "'remedy_equations': ['99'], 'uses': ['a = b'], 'introduces': []}\n"
            "result = impl.remedy_compatibility([finding], 'e1.md', "
            "sources_by_document={'experiments': impl.revision_source('e1.md', 0), "
            "'proposal': impl.revision_source('p1.md', 1)})\n"
            "print(result['status'])\n"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # The mutation reverts to document 0's own scalar keys
        # ("experiments"/"remedy_experiments"), under which this finding's
        # "remedy_equations" field is never read at all -- so it reads
        # compatible again, exactly the pre-capability defect.
        self.assertEqual(proc.stdout.strip(), "ok")

    def test_z5_reverting_finding_tags_to_index_zero_desyncs_the_both_documents_case(self):
        """Z5 (design.md Mutation plan, task 1.30): replace
        `finding_tags[index]`-equivalent per-index tag computation with
        document 0's own tags for every index, in a SCRATCH engine copy;
        confirm the both-documents case (a locus declared only in document
        1's text) goes red."""
        real_source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        anchor = (
            "index_tags = (set(document_block_locator(label_index)[\"pattern\"]\n"
            "                              .findall(index_text)) if index_text is not None\n"
            "                          else set())")
        mutated_anchor = (
            "index_tags = (set(document_block_locator(0)[\"pattern\"]\n"
            "                              .findall(index_text)) if index_text is not None\n"
            "                          else set())")
        self.assertEqual(real_source.count(anchor), 1)
        self.assertEqual(real_source.count(mutated_anchor), 0)
        mutated_source = real_source.replace(anchor, mutated_anchor, 1)
        self.assertEqual(mutated_source.count(anchor), 0)
        self.assertEqual(mutated_source.count(mutated_anchor), 1)

        doc0_dir = self._tmp_dir("z5-doc0-")
        doc1_dir = self._tmp_dir("z5-doc1-")
        (doc0_dir / "e1.md").write_text("## 1\n\nnothing relevant.\n", encoding="utf-8")
        (doc1_dir / "p1.md").write_text(
            "The proposal declares $$a = b \\tag{99}$$.\n", encoding="utf-8")

        scratch_core = Path(tempfile.mkdtemp(prefix="z5-core-"))
        self.addCleanup(shutil.rmtree, scratch_core, ignore_errors=True)
        shutil.copytree(ENGINE_DIR.parent, scratch_core / "core",
                        ignore=shutil.ignore_patterns("__pycache__"),
                        dirs_exist_ok=True)
        (scratch_core / "core" / "engine" / "implementation_engine.py").write_text(
            mutated_source, encoding="utf-8")

        env = os.environ.copy()
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(PROFILE_FILE)
        env["IMPLEMENTATION_PROPOSALS"] = str(doc0_dir)
        env["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_dir)
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(scratch_core / 'core' / 'engine')!r})\n"
            "import implementation_engine as impl\n"
            # Same shape as the M4 positive control above -- document 1's
            # own text DOES declare the locus. Under the mutation, every
            # index reads document 0's (empty) tags, so this locus is
            # reported unknown -- the desync.
            "finding = {'id': 'doc1-declared', 'document': ['proposal'], "
            "'remedy_equations': ['99'], 'uses': ['a = b'], 'introduces': []}\n"
            "result = impl.remedy_compatibility([finding], 'e1.md', "
            "sources_by_document={'experiments': impl.revision_source('e1.md', 0), "
            "'proposal': impl.revision_source('p1.md', 1)})\n"
            "print(result['status'])\n"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.strip(), "incompatible")


class WalkPromisesOnlyWhatItPerformsTests(unittest.TestCase):
    """`walk` listed `rehearse` in `WALK_PERFORMS`, and no code path performs
    it. Its dispatch has exactly two argv shapes -- `step` for run-local and
    `generate_job_argv` for everything else -- and `generate_job_argv` never
    passes `--regenerate`, which remote-execution's job writer requires to
    touch a folder that already exists. A `rehearse` act is classified
    PRECISELY when the job folder exists and is not smoke-ready, so on the
    one state the act exists for, walk ran the wrong command and stopped on
    a refusal about a folder that is supposed to be there.

    The engine's own comment beside `WALK_PERFORMS` already says rehearsal is
    "the rehearsal the doctrine already makes the agent's to run". The
    roster disagreed with the sentence next to it.

    Retiring the promise rather than building the act: the doctrine that
    rehearsal is run by hand is documented, works, and is what both hosts
    actually do. Building an automated act to match a sentence would be
    adding surface to justify prose.
    """

    def test_the_engine_does_not_claim_to_perform_an_act_it_cannot(self):
        module, _ = _engine_with_documents(_real_profile()["documents"])
        self.assertNotIn(
            module.ACT_REHEARSE, module.WALK_PERFORMS,
            "walk claims to perform rehearse; nothing in the engine composes "
            "`--regenerate`, `submit --smoke`, `fetch` or `smoke record`")
        self.assertIn(
            module.ACT_REHEARSE, module.WALK_STOPS_AT,
            "an act walk does not perform must be a stop, not unclassified -- "
            "`walk_plan` answers 'nothing here knows whether a walk may take "
            "it' for anything in neither roster")

    def test_a_walk_stops_at_a_rehearse_act_instead_of_running_generate_job(self):
        module, _ = _engine_with_documents(_real_profile()["documents"])
        plan = module.walk_plan([
            {"step": "s1", "act": module.ACT_RUN_LOCAL, "needs": None},
            {"step": "s2", "act": module.ACT_REHEARSE, "needs": None},
            {"step": "s3", "act": module.ACT_RUN_LOCAL, "needs": None},
        ])
        self.assertEqual([a["step"] for a in plan["performs"]], ["s1"])
        self.assertIsNotNone(plan["stopsAt"])
        self.assertEqual(plan["stopsAt"]["step"], "s2")

    def test_no_shipped_document_promises_walk_rehearses(self):
        """The four documents that carried the promise: the first host's
        SKILL.md and both walk agents' descriptions."""
        offenders = []
        for path, phrase in (
                (FORGE / "skills/proposal-implementation/SKILL.md",
                 "and `rehearse`"),
                (FORGE / ".claude/agents/implementation-walk.md",
                 "rehearse them on a worker"),
                (FORGE / ".claude/agents/experiments-walk.md",
                 "rehearse them on a worker")):
            if phrase in path.read_text(encoding="utf-8"):
                offenders.append(f"{path.name}: {phrase!r}")
        self.assertEqual(offenders, [], f"still promise an act walk cannot perform: {offenders}")


class FrontDoorIdentityTests(unittest.TestCase):
    """`-h` is the only self-description this host offers: its own SKILL.md
    says "every argument, subcommand and exit code is the shared engine's;
    nothing here re-documents them". It introduced itself by the SIBLING's
    name, because `argparse(description=__doc__)` read the shared engine's
    module docstring, and that docstring also hand-listed four subcommands
    out of twenty-one.

    Both halves are held here. The name must come from the profile that is
    actually loaded, and the description must not hand-maintain a list
    argparse already prints in full -- prose duplicating a machine-generated
    list is this repository's most-recorded defect class, waiting its turn.
    """

    def _help(self, skill: str) -> str:
        cli = (FORGE / "skills" / skill / "scripts"
               / "implementation_cli.py")
        # The launcher uses `setdefault`, so an IMPLEMENTATION_DOMAIN_PROFILE
        # left in this process's environment by a sibling test would be
        # INHERITED by the child and win -- the front door would then
        # correctly name whatever host that variable points at, and this test
        # would read it as the wrong name. Passing alone and failing in the
        # full run is how that showed up. Cleared here so the child resolves
        # the profile from its own launcher, which is the thing under test.
        env = {k: v for k, v in os.environ.items()
               if k != "IMPLEMENTATION_DOMAIN_PROFILE"}
        done = subprocess.run([sys.executable, str(cli), "-h"], env=env,
                              capture_output=True, text=True, check=True)
        return done.stdout

    def test_each_host_names_itself_and_not_its_sibling(self):
        for skill, sibling in (("experimental-implementation", "proposal-implementation"),
                               ("proposal-implementation", "experimental-implementation")):
            with self.subTest(skill=skill):
                text = self._help(skill)
                self.assertIn(skill, text, f"{skill}'s own front door never names it")
                # The sibling's name may not appear at all: there is nothing
                # in a front door that should mention the other host.
                self.assertNotIn(
                    sibling, text,
                    f"{skill}'s front door introduces itself as {sibling}")

    def test_the_description_does_not_hand_list_a_subset_of_the_subcommands(self):
        """argparse prints the complete roster on its own. A prose list beside
        it can only ever be right by accident -- it was four of twenty-one."""
        text = self._help("experimental-implementation")
        # argparse reflows the description into one paragraph, so an
        # indentation-anchored regex passes whatever the docstring says --
        # it did, on this test's first run. The hand-written blurbs
        # themselves are the evidence, and they survive reflowing.
        blurbs = [b for b in ("create/verify the target repository's own virtualenv",
                              "read-only migration plan",
                              "execute an approved plan as a single, separate commit",
                              "layout compliance + revision fidelity")
                  if b in text]
        self.assertEqual(
            blurbs, [],
            f"the description hand-lists subcommands argparse already prints "
            f"in full: {blurbs}")


class HandoffPerDocumentDisplayTests(unittest.TestCase):
    """The same premise's display tier. `cmd_handoff` builds each item's
    locus fields as `finding.get(LOCUS_KEY)`/`finding.get(REMEDY_LOCUS_KEY)`
    -- document 0's scalars -- so a `documents[1]` finding, which declares
    `equations`/`remedy_equations`, renders both as `null`.

    Worse than a display gap: the deferral branch tells the operator the
    finding "no declara qué reescribiría (`remedy_experiments` está vacío)"
    when the finding declares `remedy_equations` and names it. A refusal
    message that states a falsehood about the document the finding names is
    the same defect as admitting it wrongly, one tier out.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'e1.md',\n"
        "    'arms': {},\n"
        "    'report': {'renderers': [], 'conclusions': []},\n"
        "}\n"
    )

    def _tmp_dir(self, prefix: str) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _handoff(self, findings: str) -> dict:
        doc0_dir = self._tmp_dir("handoff-doc0-")
        doc1_dir = self._tmp_dir("handoff-doc1-")
        (doc0_dir / "e1.md").write_text("## 1\n\nnothing relevant.\n", encoding="utf-8")
        (doc1_dir / "p1.md").write_text(
            "The proposal declares $$a = b \\tag{1}$$.\n", encoding="utf-8")
        module, _ = _engine_with_documents(_real_profile()["documents"])
        saved = {k: os.environ.get(k) for k in
                 ("IMPLEMENTATION_PROPOSALS", "IMPLEMENTATION_PROPOSALS_1")}
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(doc0_dir)
        os.environ["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_dir)

        def _restore():
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        self.addCleanup(_restore)
        box = FORGE / "implementations" / f"_handoff_perdoc_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")
        (box / "tests" / "findings.py").write_text(findings, encoding="utf-8")
        return module.cmd_handoff(argparse.Namespace(
            target=str(box), name="Method", revision="e1.md"))

    FINDING = (
        "FINDINGS = [\n"
        "    {\n"
        "        'id': 'doc1-display',\n"
        "        'document': ['proposal'],\n"
        "        'kind': 'gap', 'status': 'measured', 'rate': 'always',\n"
        "        'equations': ['1'],\n"
        "        'remedy_equations': ['1'],\n"
        "        'uses': ['a = b'],\n"
        "        'introduces': [],\n"
        "        'statement': 'x', 'remedy': 'y',\n"
        "    },\n"
        "]\n")

    def _item(self, result: dict) -> dict:
        for bucket in ("settleInline", "deferToOwnSession", "settled"):
            for item in result.get(bucket, []):
                if item["id"] == "doc1-display":
                    return item
        self.fail(f"finding not present in any bucket: {list(result)}")

    def test_the_item_carries_the_loci_the_finding_declares(self):
        item = self._item(self._handoff(self.FINDING))
        declared = [value for key, value in item.items()
                    if key.lower().startswith(("equation", "remedyequation",
                                               "experiment", "remedyexperiment"))]
        self.assertNotEqual(
            declared, [None, None],
            "a documents[1] finding's own loci render as null because the item "
            f"is built from document 0's keys: {item}")

    def test_the_deferral_message_does_not_name_a_key_the_finding_does_not_use(self):
        """The falsehood. A finding declaring `remedy_equations` must never be
        told that `remedy_experiments` is empty."""
        result = self._handoff(self.FINDING)
        item = self._item(result)
        prompts = [entry.get("prompt", "") for entry in result.get("deferToOwnSession", [])]
        self.assertFalse(
            any("remedy_experiments" in p for p in prompts),
            f"names a key the finding does not declare: {prompts}\nitem: {item}")


class FindingImpactPerDocumentTests(unittest.TestCase):
    """`finding_impact`'s per-document `class` is the same premise's second
    consumer: `remedy_loci` is read once, under document 0's
    `REMEDY_LOCUS_KEY`, and that same list is handed to `_impact_class`
    inside the per-document loop. A `documents[1]` finding declares
    `remedy_equations`; read under `remedy_experiments` it is `[]`, so the
    class arithmetic runs over an empty list and answers `local` for a
    remedy of any width at all.

    `local_reach` gates three sites in `cmd_handoff` and `cmd_verify`'s
    `localRemediesNotWritten`, and this host's Flow B routes `settleInline`
    entries into `compose` -- so a structural remedy is offered to the
    deliberation as settleable inline, sized by a measurement that read
    nothing.

    The scalar `locus`/`introducesNotation`/`citedElsewhere` fields stay
    document 0's by design (Cut 3, D6, "representation only"); only the
    per-document `class` is under test here.
    """

    def test_a_wide_document_one_remedy_is_not_classified_local(self):
        module, _ = _engine_with_documents(_real_profile()["documents"])
        finding = {
            "id": "doc1-wide", "document": ["proposal"],
            # Five loci, in document 1's OWN remedy key.
            "remedy_equations": ["1", "2", "3", "4", "5"],
            "uses": ["a = b"], "introduces": [],
        }
        impact = module.finding_impact(
            finding, "## 1\n\nnothing relevant.\n",
            sources_by_document={
                "experiments": "## 1\n\nnothing relevant.\n",
                "proposal": ("$$a = b \\tag{1}$$ $$c \\tag{2}$$ $$d \\tag{3}$$ "
                             "$$e \\tag{4}$$ $$f \\tag{5}$$\n")})
        self.assertEqual(impact["class"].get("proposal"), "structural")
        self.assertFalse(module.local_reach(impact))

    def test_a_single_locus_document_one_remedy_is_still_local(self):
        """Positive control: the per-document read must not turn every
        `documents[1]` remedy structural. One locus, nothing introduced."""
        module, _ = _engine_with_documents(_real_profile()["documents"])
        finding = {
            "id": "doc1-narrow", "document": ["proposal"],
            "remedy_equations": ["1"], "uses": ["a = b"], "introduces": [],
        }
        impact = module.finding_impact(
            finding, "## 1\n\nnothing relevant.\n",
            sources_by_document={
                "experiments": "## 1\n\nnothing relevant.\n",
                "proposal": "$$a = b \\tag{1}$$\n"})
        self.assertEqual(impact["class"].get("proposal"), "local")
        self.assertTrue(module.local_reach(impact))


class AdmitPerDocumentTests(unittest.TestCase):
    """`cmd_admit` is a fourth consumer of the premise
    `RemedyCompatibilityPerDocumentTests` above already had corrected, and
    the lock never reached it: the gate that rules admissibility BEFORE
    anything is measured reads document 0's `locus_key`/`remedy_locus_key`
    and document 0's TEXT for every finding -- including one that names
    `documents[1]` and declares this host's `equations`/`remedy_equations`.

    Both directions are held here because either alone leaves the other
    standing. A bogus `documents[1]` finding must not be admitted (its
    verdict is written into `tests/admissibility.json`, which the target's
    remedy suite trusts before measuring), and a legitimate one must not be
    refused with reasons that are false about the document it names.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'e1.md',\n"
        "    'arms': {},\n"
        "    'report': {'renderers': [], 'conclusions': []},\n"
        "}\n"
    )

    def _tmp_dir(self, prefix: str) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _engine_with_proposals_override(self, doc0_dir: Path, doc1_dir: Path):
        """Copied from `RemedyCompatibilityPerDocumentTests` rather than
        extracted, for the reason that file's own siblings state: a helper
        shared between a passing lock and a new one couples what goes red."""
        module, _ = _engine_with_documents(_real_profile()["documents"])
        saved = {key: os.environ.get(key)
                 for key in ("IMPLEMENTATION_PROPOSALS", "IMPLEMENTATION_PROPOSALS_1")}
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(doc0_dir)
        os.environ["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_dir)

        def _restore():
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(_restore)
        return module

    def _box(self, tag: str, findings: str) -> Path:
        # Under `implementations/`, never a temp dir: `resolve_target`
        # refuses anything outside it, and that refusal is the shipped
        # behaviour, not an obstacle to route around.
        box = FORGE / "implementations" / f"_admit_perdoc_{tag}_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")
        (box / "tests" / "findings.py").write_text(findings, encoding="utf-8")
        return box

    def _admit(self, doc0_text: str, doc1_text: str, findings: str) -> dict:
        doc0_dir = self._tmp_dir("admit-doc0-")
        doc1_dir = self._tmp_dir("admit-doc1-")
        (doc0_dir / "e1.md").write_text(doc0_text, encoding="utf-8")
        (doc1_dir / "p1.md").write_text(doc1_text, encoding="utf-8")
        module = self._engine_with_proposals_override(doc0_dir, doc1_dir)
        box = self._box("run", findings)
        return module.cmd_admit(argparse.Namespace(
            target=str(box), name="Method", revision="e1.md"))

    def test_a_bogus_document_one_finding_is_not_admitted(self):
        """Direction 1. The finding names `documents[1]` and cites tag 99,
        which exists in NEITHER document. `remedy_compatibility` already
        refuses it; `admit` must not write `admissible: true` for it.

        The adoption marker and the notation are deliberately present in
        DOCUMENT 0's text, so that those two checks cannot fire: the only
        thing left that can refuse this finding is its locus, which is the
        read under test. Without that, the test passes for a reason
        unrelated to the defect -- which it did, on its first run.
        """
        result = self._admit(
            doc0_text="## 1\n\nThe experiments mention $$a = b$$ in passing.\n",
            doc1_text="The proposal declares $$a = b \\tag{1}$$ only.\n",
            findings=(
                "FINDINGS = [\n"
                "    {\n"
                "        'id': 'doc1-bogus-locus',\n"
                "        'document': ['proposal'],\n"
                "        'equations': ['99'],\n"
                "        'remedy_equations': ['99'],\n"
                "        'uses': ['a = b'],\n"
                "        'introduces': [],\n"
                "        'adoption': {'absent': 'a = b', 'expect': []},\n"
                "    },\n"
                "]\n"))
        self.assertNotIn("doc1-bogus-locus", result["admitted"])
        self.assertIn("doc1-bogus-locus", result["inadmissible"])

    def test_a_legitimate_document_one_finding_is_not_refused_with_false_reasons(self):
        """Direction 2. The finding's locus, adoption marker and notation
        are all real text of the document it NAMES, and absent from
        document 0. No reason may claim otherwise."""
        result = self._admit(
            doc0_text="## 1\n\nnothing relevant.\n",
            doc1_text="The proposal declares $$a = b \\tag{1}$$.\n",
            findings=(
                "FINDINGS = [\n"
                "    {\n"
                "        'id': 'doc1-legit',\n"
                "        'document': ['proposal'],\n"
                "        'equations': ['1'],\n"
                "        'remedy_equations': ['1'],\n"
                "        'uses': ['a = b'],\n"
                "        'introduces': [],\n"
                "        'adoption': {'absent': 'a = b', 'expect': []},\n"
                "    },\n"
                "]\n"))
        self.assertEqual(result["inadmissible"].get("doc1-legit"), None,
                         "refused a finding whose locus, marker and notation "
                         "are all real text of the document it names")


class CrossingStateTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md D6, tasks.md
    2.8): `crossing_state`'s own four-membership unit matrix, proven
    against THIS skill's own shipped two-document profile -- `documents[0]`
    (`experiments`) declares `cross_citation` resolving against
    `documents[1]`'s (`proposal`) own `block_locator.pattern`.

    Pure function, no CLI dispatch: an in-process fresh-engine import is
    not the "monkeypatch has zero effect on a subprocess" scar, mirroring
    `RemedyCompatibilityPerDocumentTests`'s own standing rule."""

    def _tmp_dir(self, prefix: str) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _engine_with_proposals_override(self, doc0_dir: Path, doc1_dir: Path):
        """The real, unmodified two-document profile, both documents'
        proposals roots overridden via the engine's own supported env
        vars -- identical mechanism to
        `RemedyCompatibilityPerDocumentTests`'s own helper, not shared by
        import since each test class owns its fixture lifecycle."""
        module, _ = _engine_with_documents(_real_profile()["documents"])
        had_0 = "IMPLEMENTATION_PROPOSALS" in os.environ
        original_0 = os.environ.get("IMPLEMENTATION_PROPOSALS")
        had_1 = "IMPLEMENTATION_PROPOSALS_1" in os.environ
        original_1 = os.environ.get("IMPLEMENTATION_PROPOSALS_1")
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(doc0_dir)
        os.environ["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_dir)

        def _restore():
            if had_0:
                os.environ["IMPLEMENTATION_PROPOSALS"] = original_0
            else:
                os.environ.pop("IMPLEMENTATION_PROPOSALS", None)
            if had_1:
                os.environ["IMPLEMENTATION_PROPOSALS_1"] = original_1
            else:
                os.environ.pop("IMPLEMENTATION_PROPOSALS_1", None)

        self.addCleanup(_restore)
        return module

    def test_a_crossing_that_resolves_both_ways_reports_no_discrepancy(self):
        doc0_dir = self._tmp_dir("crossing-both-doc0-")
        doc1_dir = self._tmp_dir("crossing-both-doc1-")
        (doc0_dir / "e1.md").write_text(
            "## 1\n\nSustains the claim, citing [claims:9].\n", encoding="utf-8")
        (doc1_dir / "p1.md").write_text(
            "The proposal declares $$a = b \\tag{9}$$.\n", encoding="utf-8")
        module = self._engine_with_proposals_override(doc0_dir, doc1_dir)
        state = module.crossing_state(0, "e1.md")
        self.assertEqual(
            state, {"crossed": ["9"], "declared": ["9"], "absent": [], "untested": []})

    def test_absent_only_a_cited_claim_the_target_no_longer_declares(self):
        """Kind 1: the experiments document cites a claim the proposal's
        current revision does not declare."""
        doc0_dir = self._tmp_dir("crossing-absent-doc0-")
        doc1_dir = self._tmp_dir("crossing-absent-doc1-")
        (doc0_dir / "e1.md").write_text(
            "## 1\n\nCiting a claim the proposal dropped: [claims:9].\n",
            encoding="utf-8")
        (doc1_dir / "p1.md").write_text(
            "The proposal declares nothing matching that claim.\n", encoding="utf-8")
        module = self._engine_with_proposals_override(doc0_dir, doc1_dir)
        state = module.crossing_state(0, "e1.md")
        self.assertEqual(
            state, {"crossed": ["9"], "declared": [], "absent": ["9"], "untested": []})

    def test_untested_only_a_declared_claim_no_experiment_cites(self):
        """Kind 2: the proposal declares a claim no experiment cites."""
        doc0_dir = self._tmp_dir("crossing-untested-doc0-")
        doc1_dir = self._tmp_dir("crossing-untested-doc1-")
        (doc0_dir / "e1.md").write_text("## 1\n\nCites nothing at all.\n", encoding="utf-8")
        (doc1_dir / "p1.md").write_text(
            "The proposal declares $$a = b \\tag{9}$$.\n", encoding="utf-8")
        module = self._engine_with_proposals_override(doc0_dir, doc1_dir)
        state = module.crossing_state(0, "e1.md")
        self.assertEqual(
            state, {"crossed": [], "declared": ["9"], "absent": [], "untested": ["9"]})

    def test_both_non_empty_at_once(self):
        doc0_dir = self._tmp_dir("crossing-both-nonempty-doc0-")
        doc1_dir = self._tmp_dir("crossing-both-nonempty-doc1-")
        (doc0_dir / "e1.md").write_text(
            "## 1\n\nCites a dropped claim: [claims:9].\n", encoding="utf-8")
        (doc1_dir / "p1.md").write_text(
            "The proposal declares $$a = b \\tag{7}$$, untested.\n", encoding="utf-8")
        module = self._engine_with_proposals_override(doc0_dir, doc1_dir)
        state = module.crossing_state(0, "e1.md")
        self.assertEqual(
            state, {"crossed": ["9"], "declared": ["7"], "absent": ["9"], "untested": ["7"]})

    def test_none_cross_citation_answers_every_membership_empty(self):
        """`documents[1]` (the proposal) declares `cross_citation: None` --
        every membership empty, no discrepancy possible in either
        direction (design.md's own Open Question, ruled)."""
        doc0_dir = self._tmp_dir("crossing-none-doc0-")
        doc1_dir = self._tmp_dir("crossing-none-doc1-")
        module = self._engine_with_proposals_override(doc0_dir, doc1_dir)
        state = module.crossing_state(1, "p1.md")
        self.assertEqual(
            state, {"crossed": [], "declared": [], "absent": [], "untested": []})

    def test_sorted_and_deduplicated_a_repeated_crossing_is_one_discrepancy(self):
        """A crossing repeated twice is one discrepancy, not two (design.md
        D6)."""
        doc0_dir = self._tmp_dir("crossing-dedup-doc0-")
        doc1_dir = self._tmp_dir("crossing-dedup-doc1-")
        (doc0_dir / "e1.md").write_text(
            "## 1\n\n[claims:9] and again [claims:9], and [claims:2].\n",
            encoding="utf-8")
        (doc1_dir / "p1.md").write_text("Nothing declared here.\n", encoding="utf-8")
        module = self._engine_with_proposals_override(doc0_dir, doc1_dir)
        state = module.crossing_state(0, "e1.md")
        self.assertEqual(state["crossed"], ["2", "9"])
        self.assertEqual(state["absent"], ["2", "9"])

    def test_z6_computing_declared_from_the_declaring_documents_own_locator_flips_to_absent(self):
        """Z6 (design.md Mutation plan, task 2.13): replace
        `document_block_locator(target_index)` with
        `document_block_locator(index)` in `crossing_state`'s own
        `declared` computation, in a SCRATCH engine copy; confirm the
        resolving case (this class's first test) flips to `absent` -- the
        one a weaker fixture (supplying only a resolving crossing) would
        survive, because it never checks that `declared` came from the
        TARGET's own locator rather than the declaring document's."""
        real_source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        anchor = (
            'document_block_locator(target_index)["pattern"]'
            '.findall(target_source or "")')
        mutated_anchor = (
            'document_block_locator(index)["pattern"]'
            '.findall(target_source or "")')
        self.assertEqual(real_source.count(anchor), 1)
        self.assertEqual(real_source.count(mutated_anchor), 0)
        mutated_source = real_source.replace(anchor, mutated_anchor, 1)
        self.assertEqual(mutated_source.count(anchor), 0)
        self.assertEqual(mutated_source.count(mutated_anchor), 1)

        doc0_dir = self._tmp_dir("z6-doc0-")
        doc1_dir = self._tmp_dir("z6-doc1-")
        (doc0_dir / "e1.md").write_text(
            "## 1\n\nSustains the claim, citing [claims:9].\n", encoding="utf-8")
        (doc1_dir / "p1.md").write_text(
            "The proposal declares $$a = b \\tag{9}$$.\n", encoding="utf-8")

        scratch_core = Path(tempfile.mkdtemp(prefix="z6-core-"))
        self.addCleanup(shutil.rmtree, scratch_core, ignore_errors=True)
        shutil.copytree(ENGINE_DIR.parent, scratch_core / "core",
                        ignore=shutil.ignore_patterns("__pycache__"),
                        dirs_exist_ok=True)
        (scratch_core / "core" / "engine" / "implementation_engine.py").write_text(
            mutated_source, encoding="utf-8")

        env = os.environ.copy()
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(PROFILE_FILE)
        env["IMPLEMENTATION_PROPOSALS"] = str(doc0_dir)
        env["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_dir)
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(scratch_core / 'core' / 'engine')!r})\n"
            "import implementation_engine as impl\n"
            "import json\n"
            "print(json.dumps(impl.crossing_state(0, 'e1.md')))\n"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        mutated_state = json.loads(proc.stdout.strip())
        # Document 0's own `block_locator` (the heading form, `## N`)
        # finds nothing in `crossed`'s `[claims:9]`-shaped text -- so
        # `declared` reads empty under the mutation, and the resolving
        # crossing flips to `absent` instead of clearing.
        self.assertEqual(mutated_state["declared"], [])
        self.assertEqual(mutated_state["absent"], ["9"])

        # `tests/seal/` is untouched: the mutation lives only in this
        # scratch copy, never the shipped engine.
        seal_diff = subprocess.run(
            ["git", "diff", "--exit-code", "tests/seal/"], cwd=FORGE)
        self.assertEqual(seal_diff.returncode, 0)


class FindingImpactPerDocumentUnitTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md D10, tasks.md
    5.5/5.6): `finding_impact`'s own per-document mapping, confirmed
    directly (spec `implementation-document-binding`'s three scenarios --
    already implemented by Slice C; this phase's own consumer gives the
    mapping its first real reader, so this re-confirms the representation
    itself rather than assuming it still holds). Two documents, distinct
    `citation_pattern`s, a fresh in-process engine -- no subprocess
    needed, `finding_impact` is a pure function of its arguments."""

    def _engine(self):
        doc0_dir = Path(tempfile.mkdtemp(prefix="impact-doc0-"))
        self.addCleanup(shutil.rmtree, doc0_dir, ignore_errors=True)
        doc1_dir = Path(tempfile.mkdtemp(prefix="impact-doc1-"))
        self.addCleanup(shutil.rmtree, doc1_dir, ignore_errors=True)
        engine, tmp_dir = _engine_with_documents([
            # Document 0 declares its OWN vocabulary overlay explicitly
            # (never left to inherit the real experimental-implementation
            # profile's own top-level "experiments"/"Exp." values, which
            # `document_vocabulary(0)` would otherwise fall back to) --
            # `REMEDY_LOCUS_KEY` (module-level, from `document_vocabulary
            # (0)`) is therefore "remedy_equations" here, matching every
            # finding built below.
            {"directory": doc0_dir, "label": "proposal", "dataset_marker": None,
             "block_locator": _block_locator(), "cross_citation": None,
             "claim_key": "equations", "locus_key": "equations",
             "remedy_locus_key": "remedy_equations",
             "notation_keys": {"locus": "equations",
                               "remedyLocus": "remedyEquations",
                               "unknown": "unknownEquations"},
             "citation_pattern": (
                 r"Ecs?\.?\s*\(?(\d+)\)?|Eq\.?\s*\(?(\d+)\)?|"
                 r"Ecuaciones?\s*\((\d+)\)")},
            {"directory": doc1_dir, "label": "experiments", "dataset_marker": None,
             "block_locator": _block_locator(), "cross_citation": None,
             "claim_key": "experiments", "locus_key": "experiments",
             "remedy_locus_key": "remedy_experiments",
             "notation_keys": {"locus": "experiments",
                               "remedyLocus": "remedyExperiments",
                               "unknown": "unknownExperiments"},
             "citation_pattern": (
                 r"Exps?\.?\s*\(?(\d+)\)?|Experiment\.?\s*\(?(\d+)\)?|"
                 r"Experimentos?\s*\((\d+)\)")},
        ])
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return engine

    def test_a_finding_against_one_document_maps_to_that_document_alone(self):
        engine = self._engine()
        finding = {"document": "proposal", "remedy_equations": ["9"],
                   "introduces": []}
        impact = engine.finding_impact(
            finding, "Ec.(9) cited once.",
            {"proposal": "Ec.(9) cited once.", "experiments": "no citation here"})
        self.assertEqual(impact["class"], {"proposal": "local"})

    def test_a_finding_against_both_documents_carries_both_uninterpreted(self):
        engine = self._engine()
        finding = {"document": ["proposal", "experiments"],
                   "remedy_equations": ["9"], "introduces": []}
        impact = engine.finding_impact(
            finding, "Ec.(9) once, Ec.(9) twice, Ec.(9) thrice.",
            {"proposal": "Ec.(9) once, Ec.(9) twice, Ec.(9) thrice.",
             "experiments": "no citation of this locus at all"})
        self.assertEqual(
            impact["class"], {"proposal": "structural", "experiments": "local"},
            "one class per named document, no combined or summarized verdict")

    def test_each_named_documents_citations_are_matched_by_its_own_pattern(self):
        """Document 0 ('Ec.') and document 1 ('Exp.') declare different
        patterns; a citation spelled in document 1's own syntax must never
        be visible under document 0's."""
        engine = self._engine()
        finding = {"document": ["proposal", "experiments"],
                   "remedy_equations": ["9"], "introduces": []}
        impact = engine.finding_impact(
            finding, "no Ec. citation here at all",
            {"proposal": "no Ec. citation here at all",
             "experiments": "Exp.(9) cited, Exp.(9) again, Exp.(9) a third time"})
        self.assertEqual(impact["class"]["proposal"], "local")
        self.assertEqual(
            impact["class"]["experiments"], "structural",
            "document 1's own three citations, under its own pattern, "
            "must be visible -- never cross-applied from document 0's")


class LocalReachUnitTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md D10, tasks.md
    5.2): `local_reach`'s own shape table, pure -- no profile dependency,
    so a single trivial document is enough to get a fresh engine handle."""

    def _engine(self):
        engine, tmp_dir = _engine_with_documents([
            {"directory": Path(tempfile.mkdtemp(prefix="local-reach-")),
             "label": "experiments", "dataset_marker": None,
             "block_locator": _block_locator(), "cross_citation": None},
        ])
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return engine

    def test_a_plain_local_string_is_reachable(self):
        engine = self._engine()
        self.assertTrue(engine.local_reach({"class": "local"}))

    def test_a_plain_structural_string_is_not_reachable(self):
        engine = self._engine()
        self.assertFalse(engine.local_reach({"class": "structural"}))

    def test_a_mapping_all_local_is_reachable(self):
        engine = self._engine()
        self.assertTrue(engine.local_reach(
            {"class": {"proposal": "local", "experiments": "local"}}))

    def test_a_mixed_mapping_is_not_reachable(self):
        """Local in one document and structural in the other is
        structural -- the reach is the union, never the best case."""
        engine = self._engine()
        self.assertFalse(engine.local_reach(
            {"class": {"proposal": "local", "experiments": "structural"}}))

    def test_an_empty_mapping_falls_back_to_the_string_path(self):
        """`all()`'s own vacuous truth over zero elements would read an
        empty mapping as local by accident; `local_reach` must not."""
        engine = self._engine()
        self.assertFalse(engine.local_reach({"class": {}}))


class AdmissibilityMultiDocumentAbsenceFailOpenTests(unittest.TestCase):
    """M10: `admissibility_record`'s multi-document staleness check must
    not read an absent `documents[1]` entry, or an unreadable document-1
    source, as fresh. Both used to fall through to `"present"`; both must
    now answer `"unknown"`."""

    def _tmp_dir(self, prefix: str) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _engine(self, doc0_dir: Path, doc1_dir: Path):
        module, _ = _engine_with_documents(_real_profile()["documents"])
        pairs = [("IMPLEMENTATION_PROPOSALS", str(doc0_dir)),
                 ("IMPLEMENTATION_PROPOSALS_1", str(doc1_dir))]
        saved = [(key, os.environ.get(key)) for key, _ in pairs]
        for key, value in pairs:
            os.environ[key] = value

        def _restore():
            for key, original in saved:
                if original is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original

        self.addCleanup(_restore)
        return module

    def test_a_missing_document_one_entry_is_unknown_not_fresh(self):
        doc0_dir = self._tmp_dir("m10-entry-doc0-")
        doc1_dir = self._tmp_dir("m10-entry-doc1-")
        (doc0_dir / "e1.md").write_text("## 1\n\nbody.\n", encoding="utf-8")
        (doc1_dir / "p1.md").write_text("proposal body.\n", encoding="utf-8")
        module = self._engine(doc0_dir, doc1_dir)

        box = self._tmp_dir("m10-entry-box-")
        (box / "tests").mkdir()
        source = (doc0_dir / "e1.md").read_text(encoding="utf-8")
        record = {
            "revision": "e1.md",
            "revisionSha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "findings": {},
            # No entry at all for document 1 ("proposal").
            "documents": [],
        }
        (box / "tests" / "admissibility.json").write_text(
            json.dumps(record), encoding="utf-8")

        result = module.admissibility_record(box, "e1.md")
        self.assertNotEqual(result["status"], "present",
                            "a missing documents[1] entry reads as fresh")
        self.assertEqual(result["status"], "unknown")

    def test_an_unreadable_document_one_source_is_unknown_not_fresh(self):
        doc0_dir = self._tmp_dir("m10-source-doc0-")
        doc1_dir = self._tmp_dir("m10-source-doc1-")
        (doc0_dir / "e1.md").write_text("## 1\n\nbody.\n", encoding="utf-8")
        # doc1_dir is left with no digit-named file at all, so document 1's
        # own name never resolves and its text can never be read.
        module = self._engine(doc0_dir, doc1_dir)

        box = self._tmp_dir("m10-source-box-")
        (box / "tests").mkdir()
        source = (doc0_dir / "e1.md").read_text(encoding="utf-8")
        record = {
            "revision": "e1.md",
            "revisionSha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "findings": {},
            "documents": [{"label": "proposal", "revision": "p1.md",
                           "revisionSha256": "deadbeef"}],
        }
        (box / "tests" / "admissibility.json").write_text(
            json.dumps(record), encoding="utf-8")

        result = module.admissibility_record(box, "e1.md")
        self.assertNotEqual(result["status"], "present",
                            "an unreadable document-1 source reads as fresh")
        self.assertEqual(result["status"], "unknown")


class PositionStateAbsentBranchKeyParityTests(unittest.TestCase):
    """M11: the absent-position return must carry every key the full
    return does, `unmeasurable` included -- a consumer reading
    `position["unmeasurable"]` on an absent target must not `KeyError`."""

    def _engine(self):
        engine, tmp_dir = _engine_with_documents([
            {"directory": Path(tempfile.mkdtemp(prefix="posstate-doc-")),
             "label": "experiments", "dataset_marker": None,
             "block_locator": _block_locator(), "cross_citation": None},
        ])
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return engine

    def test_the_absent_branch_carries_unmeasurable(self):
        engine = self._engine()
        target = Path(tempfile.mkdtemp(prefix="posstate-target-"))
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        result = engine.position_state(target, "Nope", {}, None, None)
        self.assertEqual(result["status"], "absent")
        self.assertIn("unmeasurable", result)
        self.assertEqual(result["unmeasurable"], [])

    def _function_docstring(self, name: str) -> str:
        source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        definition = next(
            node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name == name)
        return ast.get_docstring(definition) or ""

    def test_the_docstring_no_longer_claims_filesystem_free_beyond_the_block(self):
        doc = self._function_docstring("position_state")
        self.assertNotIn("reads no filesystem itself", doc)
        self.assertIn("position.jsonl", doc)

    def test_the_docstring_cites_returned_keys_own_stated_limitation_correctly(self):
        doc = self._function_docstring("position_state")
        test_source = (FORGE / "tests" / "test_proposal_implementation.py").read_text(
            encoding="utf-8")
        lines = test_source.splitlines()
        # `returned_keys`'s own stated dict-literal-only limitation, wherever
        # it currently sits -- proven against the real file rather than a
        # number carried in this test.
        self.assertIn("dict literal", "\n".join(lines[239:242]))
        self.assertIn("test_proposal_implementation.py:240-242", doc)


class IntrospectBenchmarkConfigFallbackTests(unittest.TestCase):
    """M12: the `INTROSPECT` script's own `__benchmark__` read must fall
    back to `config.py`, exactly like `resolve_benchmark_declaration`
    does -- a declaration living only there must not read as absent here."""

    def _write_fixture_interpreter(self, bin_dir: Path) -> Path:
        bin_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            target = bin_dir / "python.exe"
            os.symlink(sys.executable, target)
            return target
        target = bin_dir / "python"
        import shlex as _shlex
        target.write_text(
            f"#!/bin/sh\nexec {_shlex.quote(sys.executable)} \"$@\"\n",
            encoding="utf-8")
        target.chmod(0o755)
        return target

    def _box(self, suffix: str, files: dict) -> Path:
        path = Path(tempfile.mkdtemp(prefix=f"m12-{suffix}-"))
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        package = path / "src" / "Method_Benchmark"
        package.mkdir(parents=True)
        for name, source in files.items():
            (package / name).write_text(source, encoding="utf-8")
        self._write_fixture_interpreter(
            path / ".venv" / ("Scripts" if os.name == "nt" else "bin"))
        return path

    def _engine(self):
        engine, tmp_dir = _engine_with_documents(_real_profile()["documents"])
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return engine

    def test_a_declaration_only_in_config_py_is_not_read_as_absent(self):
        """`__init__.py` binds nothing; `config.py` alone declares
        `__benchmark__` with a `conclusionEntry` naming a function that does
        not exist. Before the fix, `contract` reads `{}` and the inert
        entry names `"*"` ("el contrato no declara conclusionEntry"); after
        it, `contract` is read from `config.py` and the inert entry names
        the declared (unresolvable) entry instead -- proof the text was
        actually read, not merely that some inert entry exists."""
        engine = self._engine()
        target = self._box("config-only", {
            "__init__.py": "",
            "config.py": (
                "__benchmark__ = {'report': "
                "{'conclusionEntry': 'entrypoint.nonexistent_fn'}}\n"),
            "entrypoint.py": "VALUE = 1\n",
        })
        # Non-empty, so INTROSPECT reaches the "try to exercise the
        # conclusion" branch rather than its own "no record" one.
        record = target / "record.json"
        record.write_text(json.dumps({"x": 1}), encoding="utf-8")
        result = engine.introspect(
            target, "Method", record, entry_module="Method_Benchmark.entrypoint")
        self.assertEqual(result["status"], "ok", result)
        conclusions = result["inertConclusions"]
        self.assertEqual(len(conclusions), 1, conclusions)
        self.assertEqual(conclusions[0]["conclusion"],
                         "entrypoint.nonexistent_fn")
        self.assertIn("no se pudo ejercitar", conclusions[0]["reason"])


class JobExecutionFieldsSharedReaderTests(unittest.TestCase):
    """M13: `accelerator`/`localBudget` must be read off `run_config`
    through one shared function both `remote_execution_jobs_state` and
    `cmd_gate` call, never two separately drifting expressions."""

    def _engine(self):
        engine, tmp_dir = _engine_with_documents(_real_profile()["documents"])
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return engine

    def test_the_shared_reader_returns_both_fields(self):
        engine = self._engine()
        self.assertEqual(
            engine._job_execution_fields(
                {"accelerator": "T4", "localBudget": 3, "other": "x"}),
            {"accelerator": "T4", "localBudget": 3})

    def test_the_shared_reader_returns_none_for_either_absent(self):
        engine = self._engine()
        self.assertEqual(
            engine._job_execution_fields({}),
            {"accelerator": None, "localBudget": None})

    def _calls_the_shared_reader(self, function_name: str) -> bool:
        source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        definition = next(
            node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name == function_name)
        return any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "_job_execution_fields"
            for node in ast.walk(definition))

    def test_remote_execution_jobs_state_calls_the_shared_reader(self):
        self.assertTrue(
            self._calls_the_shared_reader("remote_execution_jobs_state"))

    def test_cmd_gate_calls_the_shared_reader(self):
        """Through `_job_remote_necessity`, which `gate` and `launch-plan`
        share, so the election one refuses is the one the other predicts."""
        self.assertTrue(self._calls_the_shared_reader("_job_remote_necessity"))
        source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        gate = next(node for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.FunctionDef) and node.name == "cmd_gate")
        self.assertTrue(any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "_job_remote_necessity" for node in ast.walk(gate)))


class DeadGatingRefusalJustificationTests(unittest.TestCase):
    """L3: `_skipped_rung_detail`, `_step_operand_detail`,
    `_record_operand_detail` and `_record_shape_detail` no longer justify
    the detail/raise split with the retired `raised_refusal_codes` walk --
    `reachable_refusal_codes` (test_proposal_implementation.py) follows
    references into helper modules today, so a helper-deep `Refused`
    would not go unclassified either way."""

    FUNCTIONS = ("_skipped_rung_detail", "_step_operand_detail",
                "_record_operand_detail", "_record_shape_detail")

    def test_none_of_the_four_docstrings_cites_the_retired_walk(self):
        source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        by_name = {node.name: node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef)
                  and node.name in self.FUNCTIONS}
        self.assertEqual(set(by_name), set(self.FUNCTIONS))
        leaks = []
        for name, node in by_name.items():
            doc = ast.get_docstring(node) or ""
            if "raised_refusal_codes" in doc or "GatingRefusalRosterTests" in doc:
                leaks.append(name)
        self.assertEqual(leaks, [],
                         f"still cites the retired walk: {leaks}")


class DeadImportAndStaleCallerCitationTests(unittest.TestCase):
    """L4: six names imported by the engine and never used elsewhere in
    it. `latest_revision`'s own dead-caller claim lives in a test this
    file does not own (`test_proposal_implementation.py`), and is only
    reported here, never edited."""

    #: Five, not six. `LFS_POINTER_PREFIX` was removed with them and put back:
    #: `tests/test_proposal_implementation.py:701` reads it as
    #: `impl.LFS_POINTER_PREFIX`, so the engine re-exports it on purpose.
    #: Reaching a name through this module's namespace is a consumer, and a
    #: search for uses INSIDE the engine cannot see one -- which is exactly how
    #: it got called dead.
    UNUSED = ("WORKSPACE", "TEXT_EXT", "read_text", "text_files", "is_nesting")
    REEXPORTED = ("LFS_POINTER_PREFIX",)

    def test_the_engine_still_reexports_what_a_test_reads_through_it(self):
        source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported.add(alias.asname or alias.name)
        missing = [name for name in self.REEXPORTED if name not in imported]
        self.assertEqual(
            missing, [],
            f"a test reads these through the engine and they are gone: {missing}")

    def test_the_engine_imports_none_of_the_five_dead_names(self):
        source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported.add(alias.asname or alias.name)
        leaked = [name for name in self.UNUSED if name in imported]
        self.assertEqual(leaked, [], f"still imported: {leaked}")

    def test_latest_revision_has_no_production_caller_left(self):
        """The engine's own production code never calls `latest_revision`
        -- `revision_discovery` replaced its one caller. The keeper test's
        own "one production caller" wording is reported to the orchestrator
        for the agent that owns `test_proposal_implementation.py`; this
        file does not edit it."""
        source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        callers = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.FunctionDef)
                    and node.name != "latest_revision"):
                for call in ast.walk(node):
                    if (isinstance(call, ast.Call)
                            and isinstance(call.func, ast.Name)
                            and call.func.id == "latest_revision"):
                        callers.append(node.name)
        self.assertEqual(callers, [])


class HolderCollisionTests(unittest.TestCase):
    """`the-holder-each-skill-declares` (design D3, tasks.md 2.13): the
    measured defect this change closes. `proposal-implementation` and
    `experimental-implementation` share one engine and one product folder
    shape, so a target already holding the proposal's declared `AGREED.md`
    used to be picked up by the experimental skill too (the by-shape scan
    alone, `agreements_state`'s `holders`), and a `documents=` header group
    written by one profile permanently poisoned that holder for the other.
    Reproduced directly against `holder_resolution`/`_chosen_holder` --
    lighter than a full `position --sequence` CLI round trip, and it proves
    the identical resolution a write would go through.
    """

    def _load_engine(self):
        """A fresh, uncached load of the shared engine under the
        EXPERIMENTAL profile -- `_load_module`'s own discipline, so this
        module's `HOLDER_FILENAME` (`Experimental_AGREED.md`) never leaks
        into or from any other test file's cached `sys.modules` entry.

        `impl_domain_profile` is evicted from `sys.modules` before AND
        after the load -- the sibling helper `_engine_with_documents`'s
        own discipline, a few hundred lines up in this same file, and
        its own docstring names the reason: the engine's import is a
        plain `from impl_domain_profile import PROFILE` (fixed module
        name), cached process-wide, so a prior test FILE's own already-
        resolved profile survives here otherwise and this class ends up
        testing the collision against the WRONG profile -- measured
        directly: `pytest test_proposal_implementation.py
        test_experimental_implementation.py -k HolderCollisionTests`
        read `engine.HOLDER_FILENAME == 'AGREED.md'` under this method
        (the proposal's own name, leaked in from the first file) before
        this eviction existed, with no eviction at all guarding this
        specific helper."""
        env = os.environ.copy()
        env_backup = dict(os.environ)
        os.environ["IMPLEMENTATION_DOMAIN_PROFILE"] = str(PROFILE_FILE)
        sys.modules.pop("impl_domain_profile", None)
        try:
            sys.path.insert(0, str(ENGINE_DIR))
            return _load_module(
                ENGINE_DIR / "implementation_engine.py", "experimental_engine_probe")
        finally:
            sys.path.remove(str(ENGINE_DIR))
            sys.modules.pop("impl_domain_profile", None)
            os.environ.clear()
            os.environ.update(env_backup)

    def test_the_declared_names_differ(self):
        engine = self._load_engine()
        self.assertEqual(engine.HOLDER_FILENAME, "Experimental_AGREED.md")

    def test_a_target_holding_the_proposals_declared_holder_creates_this_skills_own(self):
        """The sibling's declared holder is not an undeclared checklist.

        Before 0.14.0 a target already holding an item-holding `AGREED.md`
        (the proposal skill's own declared name) resolved `"undeclared"`
        here, and `HOLDER_UNDECLARED` proposed renaming the sibling's file
        or adopting its name -- both destructive to the sibling. Every
        filename a profile sharing this engine declares is excluded from
        the by-shape candidates, so the resolution is `"create"` and this
        skill writes its own holder beside the sibling's, untouched."""
        engine = self._load_engine()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True, exist_ok=True)
            (root / "Method" / "AGREED.md").write_text(
                "- [ ] an agreement the proposal skill settled here\n",
                encoding="utf-8")
            resolution = engine.holder_resolution(root, "Method")
            self.assertEqual(resolution["action"], "create")
            # `agreements_state` sets the sibling's holder aside; the
            # exclusion is reported, never hidden.
            self.assertEqual(resolution["byShape"], [])
            self.assertEqual(resolution["siblings"], ["Method/AGREED.md"])
            chosen = engine._chosen_holder(root, "Method", root / "Method")
            self.assertEqual(chosen, root / "Method" / "Experimental_AGREED.md")
            self.assertEqual(chosen.read_text(encoding="utf-8"),
                             engine.HOLDER_SCAFFOLD)
            self.assertEqual(
                (root / "Method" / "AGREED.md").read_text(encoding="utf-8"),
                "- [ ] an agreement the proposal skill settled here\n")

    def test_a_hand_created_holder_beside_the_siblings_stays_declared(self):
        """A workspace that already worked around the collision by hand --
        `Experimental_AGREED.md` carrying exactly the scaffold, beside the
        sibling's item-holding `AGREED.md` -- keeps resolving `"declared"`."""
        engine = self._load_engine()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True, exist_ok=True)
            (root / "Method" / "AGREED.md").write_text(
                "- [x] an agreement the proposal skill settled here\n",
                encoding="utf-8")
            own = root / "Method" / "Experimental_AGREED.md"
            own.write_text(engine.HOLDER_SCAFFOLD, encoding="utf-8")
            resolution = engine.holder_resolution(root, "Method")
            self.assertEqual(resolution["action"], "declared")
            self.assertEqual(resolution["write"], own)
            self.assertEqual(engine._chosen_holder(root, "Method", root / "Method"), own)

    def test_an_unknown_candidate_beside_the_siblings_holder_still_refuses(self):
        """Fail-closed stays: a checklist no skill declares is still the
        D3 middle row, and the refusal names only that file -- never the
        sibling's, which it recognizes and leaves alone."""
        engine = self._load_engine()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True, exist_ok=True)
            (root / "Method" / "AGREED.md").write_text(
                "- [ ] the sibling's agreement\n", encoding="utf-8")
            (root / "Method" / "TASKS.md").write_text(
                "- [ ] a checklist nobody declares\n", encoding="utf-8")
            resolution = engine.holder_resolution(root, "Method")
            self.assertEqual(resolution["action"], "undeclared")
            self.assertEqual(resolution["read"], root / "Method" / "TASKS.md")
            with self.assertRaises(engine.Refused) as caught:
                engine._chosen_holder(root, "Method", root / "Method")
            self.assertEqual(caught.exception.code, "HOLDER_UNDECLARED")
            detail = str(caught.exception)
            self.assertIn("rename Method/TASKS.md", detail)
            self.assertNotIn("rename Method/AGREED.md", detail)
            self.assertIn("left alone: Method/AGREED.md", detail)
            self.assertFalse((root / "Method" / "Experimental_AGREED.md").exists())

    def test_agreements_never_count_the_siblings_holder_as_this_skills(self):
        """The READ face, agreements: before this skill has a holder of its
        own, the sibling's open items are not this skill's open agreements
        (`verify` and `close` read them through here)."""
        engine = self._load_engine()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True, exist_ok=True)
            (root / "Method" / "AGREED.md").write_text(
                "- [ ] an agreement the proposal skill settled here\n",
                encoding="utf-8")
            state = engine.agreements_state(root, "Method")
            self.assertEqual(state["status"], "absent")
            self.assertEqual(state["open"], [])
            self.assertEqual(state["siblingHolders"], ["Method/AGREED.md"])

            (root / "Method" / "Experimental_AGREED.md").write_text(
                engine.HOLDER_SCAFFOLD + "\n- [x] this skill's own\n",
                encoding="utf-8")
            state = engine.agreements_state(root, "Method")
            self.assertEqual(state["holders"], ["Method/Experimental_AGREED.md"])
            self.assertEqual(state["status"], "settled")
            self.assertEqual(state["open"], [])

    def test_position_never_reads_the_siblings_block_as_this_skills(self):
        """The READ face, position: the sibling's real block (written by its
        own launcher) is not this skill's position for `verify`, `probe`,
        `close`, `discuss` and the other position readers -- not only for
        `gate`."""
        box = self._box()
        proposals_root = self._tmp_dir("collision-read-proposals-")
        (proposals_root / "r1.md").write_text("## 1\ntexto\n", encoding="utf-8")
        self._install_siblings_holder(box, proposals_root)
        engine = self._load_engine()
        state = engine.position_state(box, "Method", {}, None, None)
        self.assertEqual(state["status"], "absent")
        self.assertIsNone(state["holder"])
        agreements = engine.agreements_state(box, "Method")
        self.assertEqual(agreements["status"], "absent")

    def _box(self, suffix: str = "") -> Path:
        box = FORGE / "implementations" / f"_holder_collision_{os.getpid()}_{id(self)}{suffix}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        (box / "Method").mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        return box

    def _tmp_dir(self, prefix: str) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _install_siblings_holder(self, box: Path, proposals_root: Path) -> bytes:
        """Real subprocesses, `proposal-implementation` only: `settle`
        first, so `Method/AGREED.md` holds a checklist item OUTSIDE any
        `<!-- position -->` block -- `agreements_state`'s own by-shape
        scan excises a position block's items before it ever counts one
        (`implementation_engine.py:406-410`), so a target whose ONLY
        checklist items live inside a position block reports `byShape:
        []` and resolves `"create"`, not `"undeclared"`, under the
        experimental profile (measured directly against
        `holder_resolution` while writing this test). Then `position
        --sequence` adds a real block on top of that settled item --
        the sibling's own declared holder, now both item-holding (by
        `settle`'s line) and block-carrying (by `position`'s), which is
        what actually reproduces the CRITICAL defect's D3 middle row
        with a pre-existing block. Returns the bytes on disk right
        after both writes."""
        env = os.environ.copy()
        env.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)
        discuss = subprocess.run(
            [sys.executable, str(SIBLING_LAUNCHER), "discuss",
             "--target", str(box), "--name", "Method", "--about", "record",
             "--question", "Should this be settled?", "--answer", "Yes."],
            capture_output=True, text=True, cwd=FORGE, env=env)
        self.assertEqual(discuss.returncode, 0, discuss.stdout + discuss.stderr)
        settle = subprocess.run(
            [sys.executable, str(SIBLING_LAUNCHER), "settle",
             "--target", str(box), "--name", "Method", "--session", "s0",
             "--about", "record", "--text", "an existing settled agreement",
             "--under", "## Ladder"],
            capture_output=True, text=True, cwd=FORGE, env=env)
        self.assertEqual(settle.returncode, 0, settle.stdout + settle.stderr)

        env["IMPLEMENTATION_PROPOSALS"] = str(proposals_root)
        sequence = json.dumps([{"text": "an agreement the sibling settled",
                                "witness": {"kind": "rehearsal", "operand": "job1"}}])
        install = subprocess.run(
            [sys.executable, str(SIBLING_LAUNCHER), "position",
             "--target", str(box), "--name", "Method", "--revision", "r1.md",
             "--session", "s1", "--target-level", "final",
             "--sequence", "-"],
            input=sequence, capture_output=True, text=True, cwd=FORGE, env=env)
        self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
        before = (box / "Method" / "AGREED.md").read_bytes()
        self.assertIn(b"an existing settled agreement", before)
        self.assertIn(b"an agreement the sibling settled", before)
        self.assertNotIn(b"documents=", before)
        return before

    def _install_siblings_block_only_holder(self, box: Path, proposals_root: Path) -> bytes:
        """Real subprocesses, `proposal-implementation` only, and
        deliberately WITHOUT `settle`: a bare `position --sequence` against
        a target with no prior holder at all creates the sibling's declared
        `Method/AGREED.md` itself (D5, `action == "create"`) and splices its
        block straight in -- every checklist line lives INSIDE that block,
        none outside it. `agreements_state`'s `byShape` excludes a position
        block's own items (`implementation_engine.py:406-410`), so under the
        experimental profile this resolves `holder_resolution`'s `"create"`
        action, not `"undeclared"` -- the DIFFERENT, documented blind spot
        `cmd_position`'s own `elif ... == "undeclared":` comment names.
        Returns the bytes on disk right after the install."""
        env = os.environ.copy()
        env.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)
        env["IMPLEMENTATION_PROPOSALS"] = str(proposals_root)
        sequence = json.dumps([{"text": "an agreement the sibling settled",
                                "witness": {"kind": "rehearsal", "operand": "job1"}}])
        install = subprocess.run(
            [sys.executable, str(SIBLING_LAUNCHER), "position",
             "--target", str(box), "--name", "Method", "--revision", "r1.md",
             "--session", "s1", "--target-level", "final",
             "--sequence", "-"],
            input=sequence, capture_output=True, text=True, cwd=FORGE, env=env)
        self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
        before = (box / "Method" / "AGREED.md").read_bytes()
        self.assertIn(b"an agreement the sibling settled", before)
        self.assertNotIn(b"documents=", before)
        return before

    def test_reconcile_never_writes_into_the_siblings_block_only_holder(self):
        """The `"create"`-action collision (the blind spot `cmd_position`'s
        own comment beside its `elif ... == "undeclared":` branch names,
        and `tasks.md` 7.5 reported rather than fixed, pending this exact
        measurement): a sibling's declared holder carrying ONLY a position
        block -- no checklist item outside it -- is invisible to
        `holder_resolution`'s `"undeclared"` classification and resolves
        `"create"` instead, but `cmd_position`'s dispatch used to key off
        `holder_resolution_result["path"]` alone (`None` for `"create"`),
        falling into the same `else` branch an `"undeclared"` candidate
        used to reach before Phase 7 -- silently adopting the sibling's
        block as "existing" for a `--reconcile` merge. Measured directly
        (this test's own RED run, pre-fix): `documents=` landed straight in
        the sibling's `AGREED.md`. Widening the dispatch to key off
        `holder_resolution_result["write"]` instead (non-`None` for both
        `"declared"` and `"create"`) makes this branch's own inner lookup
        -- still keyed on `["path"]`, which stays `None` for `"create"` --
        correctly find no existing entry in `holders_with_block`, so this
        skill's OWN declared holder is created instead."""
        box = self._box()
        proposals_root = self._tmp_dir("collision-create-proposals-")
        (proposals_root / "r1.md").write_text("## 1\ntexto\n", encoding="utf-8")
        before = self._install_siblings_block_only_holder(box, proposals_root)

        doc1_root = self._tmp_dir("collision-create-doc1-")
        (doc1_root / "p1.md").write_text("$$a = b \\tag{1}$$\n", encoding="utf-8")
        env = os.environ.copy()
        env.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)
        env["IMPLEMENTATION_PROPOSALS"] = str(proposals_root)
        env["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_root)

        reconcile = subprocess.run(
            [sys.executable, str(LAUNCHER), "position",
             "--target", str(box), "--name", "Method", "--revision", "r1.md",
             "--session", "s1", "--target-level", "final", "--reconcile"],
            capture_output=True, text=True, cwd=FORGE, env=env)

        self.assertEqual(reconcile.returncode, 0, reconcile.stdout + reconcile.stderr)
        payload = json.loads(reconcile.stdout)
        self.assertEqual(payload["holder"], "Method/Experimental_AGREED.md")
        self.assertEqual((box / "Method" / "AGREED.md").read_bytes(), before)
        self.assertTrue((box / "Method" / "Experimental_AGREED.md").exists())

    def test_reconcile_never_writes_into_the_siblings_declared_holder(self):
        """The measured CRITICAL defect (`sdd/the-holder-each-skill-
        declares/verify-critical`, Engram obs 2139): `cmd_position` used
        to dispatch off `holder_resolution`'s `["path"]` alone, never its
        `["action"]`/`["write"]` -- so an UNDECLARED candidate that
        already carried a `<!-- position -->` block (written by the
        sibling `proposal-implementation`) was silently adopted as
        "existing" here, and `--reconcile` then merged the sibling's own
        items and spliced a fresh `documents=` group straight into the
        sibling's own file (this profile declares 2 documents; the
        sibling's declares 1, so the merge poisons it). Real subprocesses
        throughout, against the SAME target, exactly the reproduction the
        CRITICAL verify finding recorded end-to-end."""
        box = self._box()
        proposals_root = self._tmp_dir("collision-proposals-")
        (proposals_root / "r1.md").write_text("## 1\ntexto\n", encoding="utf-8")
        before = self._install_siblings_holder(box, proposals_root)

        doc1_root = self._tmp_dir("collision-doc1-")
        (doc1_root / "p1.md").write_text("$$a = b \\tag{1}$$\n", encoding="utf-8")
        env = os.environ.copy()
        env.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)
        env["IMPLEMENTATION_PROPOSALS"] = str(proposals_root)
        env["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_root)

        reconcile = subprocess.run(
            [sys.executable, str(LAUNCHER), "position",
             "--target", str(box), "--name", "Method", "--revision", "r1.md",
             "--session", "s1", "--target-level", "final", "--reconcile"],
            capture_output=True, text=True, cwd=FORGE, env=env)

        # 0.14.0: the sibling's declared holder is no longer a candidate,
        # so this skill creates its own holder -- the sibling's bytes stay
        # exactly as written (no merge, no `documents=` group).
        self.assertEqual(reconcile.returncode, 0,
                         reconcile.stdout + reconcile.stderr)
        payload = json.loads(reconcile.stdout)
        self.assertEqual(payload["holder"], "Method/Experimental_AGREED.md")
        self.assertEqual((box / "Method" / "AGREED.md").read_bytes(), before)
        self.assertTrue((box / "Method" / "Experimental_AGREED.md").exists())

    def test_sequence_replace_never_overwrites_the_siblings_declared_holder(self):
        """The same collision through `--sequence --replace`: the exit
        `POSITION_BLOCK_EXISTS` itself names ("pass --replace to
        overwrite it") is precisely the remedy that would destroy the
        sibling's own position history if a caller followed it here --
        before 0.14.0 `HOLDER_UNDECLARED` refused here; now the sibling's
        declared holder is excluded from the candidates, `--replace` finds
        no block of this skill's own to overwrite, and the install lands in
        this skill's own holder -- the sibling's bytes never change."""
        box = self._box()
        proposals_root = self._tmp_dir("collision-seq-proposals-")
        (proposals_root / "r1.md").write_text("## 1\ntexto\n", encoding="utf-8")
        before = self._install_siblings_holder(box, proposals_root)

        doc1_root = self._tmp_dir("collision-seq-doc1-")
        (doc1_root / "p1.md").write_text("$$a = b \\tag{1}$$\n", encoding="utf-8")
        env = os.environ.copy()
        env.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)
        env["IMPLEMENTATION_PROPOSALS"] = str(proposals_root)
        env["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_root)

        fresh_sequence = json.dumps([{"text": "an experimental agreement",
                                      "witness": {"kind": "rehearsal", "operand": "job2"}}])
        install_experimental = subprocess.run(
            [sys.executable, str(LAUNCHER), "position",
             "--target", str(box), "--name", "Method", "--revision", "r1.md",
             "--session", "s1", "--target-level", "final",
             "--sequence", "-", "--replace"],
            input=fresh_sequence, capture_output=True, text=True, cwd=FORGE, env=env)

        self.assertEqual(install_experimental.returncode, 0,
                         install_experimental.stdout + install_experimental.stderr)
        self.assertEqual((box / "Method" / "AGREED.md").read_bytes(), before)
        own = (box / "Method" / "Experimental_AGREED.md").read_bytes()
        self.assertIn(b"an experimental agreement", own)
        self.assertNotIn(b"an agreement the sibling settled", own)

    def test_gate_never_authorizes_a_launch_against_the_siblings_position(self):
        """The READ face of the same CRITICAL defect (`sdd/the-holder-
        each-skill-declares/verify-critical`, Engram obs 2139/2140), left
        open when Phase 7 closed only the WRITE face: `position_state`
        falls back to its own raw by-shape block scan -- independent of
        `holder_resolution` and of `agreements_state`'s item-holding
        `byShape` -- with no check that the block it finds belongs to a
        DIFFERENT skill. `cmd_gate` calls `position_state` for its own
        launch-authorization inputs, so before this fix it read the
        sibling `proposal-implementation`'s own position as if it were
        `experimental-implementation`'s: measured directly (this test's
        own RED run, pre-fix) as `NOT_READY` -- `gate` evaluated `job1`'s
        readiness against the sibling's sequence -- rather than the
        correct `POSITION_ABSENT`, since this skill's own declared holder
        (`Experimental_AGREED.md`) never existed on this target at all.

        No new refusal code: `POSITION_ABSENT` already exists and already
        fires whenever `position_state`'s `status` reads `"absent"`
        (`impl_availability.position_honest`); this proves only that
        `cmd_gate` now folds a foreign-holder read to that same shape
        before ever computing a verdict from it."""
        box = self._box()
        proposals_root = self._tmp_dir("collision-gate-proposals-")
        (proposals_root / "r1.md").write_text("## 1\ntexto\n", encoding="utf-8")
        before = self._install_siblings_holder(box, proposals_root)

        env = os.environ.copy()
        env.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)
        env["IMPLEMENTATION_PROPOSALS"] = str(proposals_root)

        gate = subprocess.run(
            [sys.executable, str(LAUNCHER), "gate",
             "--target", str(box), "--name", "Method", "--revision", "r1.md",
             "--session", "s1", "--job", "job1", "--worker", "w1",
             "--justification", "Reproduction of the read-side gap only.",
             "--authorization", "bogus-token"],
            capture_output=True, text=True, cwd=FORGE, env=env)

        self.assertEqual(gate.returncode, 2, gate.stdout + gate.stderr)
        payload = json.loads(gate.stdout)
        self.assertEqual(payload["code"], "POSITION_ABSENT")
        # No `gate` ledger event -- the refusal fires before `gate` ever
        # appends one. (`position.jsonl` already carries the sibling's OWN
        # `position` event from `_install_siblings_holder` above -- that
        # file's existence is not evidence either way, only its contents.)
        ledger_path = box / "Method" / ".implementation" / "position.jsonl"
        ledger_events = [json.loads(line) for line in
                         ledger_path.read_text(encoding="utf-8").splitlines()]
        self.assertFalse(any(e.get("kind") == "gate" for e in ledger_events))
        self.assertEqual((box / "Method" / "AGREED.md").read_bytes(), before)
        self.assertFalse((box / "Method" / "Experimental_AGREED.md").exists())


class PilotLadderWithoutBaselinesTests(unittest.TestCase):
    """Comparability does not gate the declared flow, under this profile too.

    The ladder lives in the shared engine, so the proposal skill's own
    `PilotLadderWithoutBaselinesTests` covers its logic; this class proves the
    same answer through this skill's own launcher and its own holder
    (`Experimental_AGREED.md`): a target with no prior-work package under
    `src/` whose declared steps all finished at pilot reaches
    `pilot-decisions` and publishes one placement question per step.
    """

    STEPS = ("__steps__ = {\n"
             "    'first': {'module': 'Method.steps', 'function': 'a',"
             " 'advances': 1},\n"
             "    'second': {'module': 'Method.steps', 'function': 'b',"
             " 'advances': 2},\n"
             "}\n")
    SEQUENCE = ("- [ ] 1. The first step's evidence. "
                "`@notebook Notebooks/one.ipynb`\n"
                "- [ ] 2. The second step's evidence. `@record`\n")

    def build(self, ran):
        engine = HolderCollisionTests._load_engine(self)
        box = (FORGE / "implementations"
               / f"_exp_pilot_nobase_{len(ran)}_{os.getpid()}")
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        for directory in ("src/Method", "Method/Notebooks"):
            (box / directory).mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        (box / "src/Method/__init__.py").write_text(
            "__implementation__ = {'revision': 'r01.md'}\n" + self.STEPS,
            encoding="utf-8")
        (box / "src/Method/steps.py").write_text(
            "def a():\n    return 1\n\n\ndef b():\n    return 2\n",
            encoding="utf-8")
        digest = engine.source_digest(box, engine.package_name("Method"))
        (box / "Method/Notebooks/one.ipynb").write_text(json.dumps({
            "cells": [{"cell_type": "code", "execution_count": 1,
                       "metadata": {},
                       "outputs": [{"output_type": "stream", "name": "stdout",
                                    "text": [f"{engine.DIGEST_MARKER} "
                                             f"{digest}\n"]}],
                       "source": ["print('measured')\n"]}],
            "metadata": {}, "nbformat": 4, "nbformat_minor": 5,
        }), encoding="utf-8")
        self.assertEqual(engine.HOLDER_FILENAME, "Experimental_AGREED.md")
        (box / "Method" / engine.HOLDER_FILENAME).write_text(
            "<!-- position revision=r01.md sha256=" + "a" * 64
            + " derivedAt=2026-08-27T00:00:00Z session=s0 target=pilot -->\n"
            + self.SEQUENCE + "<!-- /position -->\n", encoding="utf-8")
        ledger = box / "Method" / ".implementation" / "position.jsonl"
        ledger.parent.mkdir(parents=True)
        live = engine.suite_digest(box)
        with ledger.open("w", encoding="utf-8") as handle:
            for step in ran:
                handle.write(json.dumps({
                    "kind": "step", "step": step, "outcome": "returned",
                    "suiteDigest": live, "at": "2026-08-27T00:00:00Z"}) + "\n")
        return box

    def probe(self, box):
        env = dict(os.environ)
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(PROFILE_FILE)
        proc = subprocess.run(
            [sys.executable, str(LAUNCHER), "probe", "--target", str(box),
             "--name", "Method", "--revision", "r01.md"],
            capture_output=True, text=True, cwd=FORGE, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def test_an_unfinished_pilot_is_asked_for_with_nothing_to_compare(self):
        probe = self.probe(self.build(ran=("first",)))
        self.assertIs(probe["comparable"], False)
        self.assertEqual(probe["pilotCompleteness"]["status"], "incomplete")
        self.assertEqual(probe["nextStep"], "pilot-first")
        self.assertIn("deliberately deferred", probe["resolve"]["question"])

    def test_a_finished_pilot_publishes_every_placement_question(self):
        probe = self.probe(self.build(ran=("first", "second")))
        self.assertIs(probe["comparable"], False)
        self.assertEqual(probe["pilotCompleteness"]["status"], "complete")
        self.assertEqual(probe["nextStep"], "pilot-decisions")
        asked = [entry["question"] for entry in probe["toDiscuss"]]
        self.assertEqual(len(asked), 3, asked)
        for index, step in enumerate(("first", "second"), start=1):
            self.assertIn(f"'{step}'", asked[index])
            self.assertIn("on a remote worker, or locally", asked[index])


class SiblingScaffoldSealProvenanceTests(unittest.TestCase):
    """The kit's seal owes no provenance under this profile either.

    This domain ships no kit, so a target it reads was scaffolded by the
    sibling: `src/<Package>/report_digest.py` is the sibling's seal, written
    by `materialize --stage scaffold` and recorded in the receipt as such.
    `verify` here used to list it under `missingProvenance`; it is exempt
    while its bytes are the ones that receipt entry names, and reports the
    moment they are not.
    """

    NAME = "Seal-Target"
    PACKAGE = "Seal_Target"

    def _git(self, box, *args):
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "seal-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = (
            "seal-tests@example.invalid")
        subprocess.run(["git", *args], cwd=box, env=env, check=True,
                       capture_output=True)

    def _cli(self, launcher, profile, *args):
        env = dict(os.environ)
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(profile)
        # `apply` commits in the target; never depend on the operator's
        # global git identity (CI runs the gate under an empty home).
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "seal-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = (
            "seal-tests@example.invalid")
        proc = subprocess.run([sys.executable, str(launcher), *args],
                              capture_output=True, text=True, cwd=FORGE,
                              env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def _sibling(self, *args):
        return self._cli(SIBLING_LAUNCHER,
                         FORGE / "skills/proposal-implementation/impl_profile.py",
                         *args)

    def _plan_file(self, box):
        plan = self._sibling("plan", "--target", str(box), "--name", self.NAME)
        path = Path(tempfile.mkdtemp(prefix="seal-plan-")) / "plan.json"
        self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        path.write_text(json.dumps(plan), encoding="utf-8")
        return str(path)

    def _scaffolded_by_the_sibling(self, tag):
        box = FORGE / "implementations" / f"_exp_seal_{tag}_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        self._git(box, "init", "-q")
        self._sibling("apply", "--target", str(box), "--name", self.NAME,
                      "--plan", self._plan_file(box))
        for directory in box.rglob("*"):
            if directory.is_dir() and ".git" not in directory.parts:
                (directory / ".gitkeep").touch()
        self._git(box, "add", "-A")
        self._git(box, "commit", "-q", "-m", "initial")
        self._sibling("materialize", "--target", str(box), "--name",
                      self.NAME, "--stage", "scaffold", "--plan",
                      self._plan_file(box), "--seed", "7")
        return box

    def _missing(self, box):
        payload = self._cli(LAUNCHER, PROFILE_FILE, "verify", "--target",
                            str(box), "--name", self.NAME)
        return payload["fidelity"]["missingProvenance"]

    def test_the_siblings_unmodified_seal_owes_no_provenance_here(self):
        box = self._scaffolded_by_the_sibling("fresh")
        self.assertTrue((box / "src" / self.PACKAGE / "report_digest.py")
                        .is_file())
        self.assertEqual(self._missing(box), [])

    def test_a_modified_seal_still_reports_here(self):
        box = self._scaffolded_by_the_sibling("edited")
        seal = box / "src" / self.PACKAGE / "report_digest.py"
        seal.write_text(seal.read_text(encoding="utf-8") + "\nEXTRA = 1\n",
                        encoding="utf-8")
        self.assertEqual(self._missing(box),
                         [f"src/{self.PACKAGE}/report_digest.py"])


class ShippedHolderObligationsTests(unittest.TestCase):
    """`experimental-implementation-skill`'s own requirement that this skill
    SHIPS `references/usage.md` carrying the holder's obligations.

    Written because nothing checked it. Measured, not assumed: with the file
    moved aside, `test_implementation_pair.py`,
    `test_experimental_implementation.py` and `test_skill_audit.py` ran
    489 passed / 3 skipped -- the whole suite agreed that a shipped file the
    spec requires had simply stopped existing. A requirement no test
    exercises is indistinguishable from a requirement nobody kept, which is
    the defect this repository cares most about, and it landed on the very
    file this change created to close a structural gap.

    The assertions are deliberately about the OBLIGATIONS, not the prose:
    the declared filename, the create-on-absent behaviour, and the refusal a
    reader meets when the holder they hold is not this skill's own. Pinning
    sentences would redden on every honest edit; pinning the obligations
    reddens only when one stops being documented.
    """

    REFERENCES = SKILL_DIR / "references" / "usage.md"

    def test_the_skill_ships_its_references_usage(self) -> None:
        self.assertTrue(
            self.REFERENCES.is_file(),
            f"{self.REFERENCES.relative_to(FORGE)} is required by this "
            "skill's own spec and is not on disk; its twin has carried one "
            "since before this skill existed",
        )

    def test_the_shipped_usage_names_every_holder_obligation(self) -> None:
        text = self.REFERENCES.read_text(encoding="utf-8")
        for obligation in (
                "Experimental_AGREED.md",
                "HOLDER_UNDECLARED",
        ):
            with self.subTest(obligation=obligation):
                self.assertIn(
                    obligation, text,
                    f"{obligation!r} is an obligation of this skill's own "
                    "declared holder and is undocumented in the file that "
                    "exists to document it",
                )

    def test_the_shipped_usage_never_names_the_sibling_holder_as_this_skill_s(
            self) -> None:
        """The whole point of the declared name is that this skill stops
        landing on `AGREED.md`. A `usage.md` that still calls that file this
        skill's own would re-teach the collision the change removed.

        Measured while writing this: the attribution can sit on the line
        BEFORE the filename, because prose wraps. A per-line check reddened
        on "a deliberately distinct name from the sibling's / own
        `AGREED.md`" -- correct prose, wrong assertion. The window below is
        the fix; the first draft of this test was the defect.
        """
        text = self.REFERENCES.read_text(encoding="utf-8")
        bare = re.compile(r"(?<!Experimental_)AGREED\.md")
        for match in bare.finditer(text):
            window = text[max(0, match.start() - 240):match.end() + 240]
            self.assertTrue(
                any(word in window for word in
                    ("proposal-implementation", "sibling", "twin")),
                "a bare `AGREED.md` mention must say whose it is; nothing "
                f"attributes the one at offset {match.start()}",
            )



class SettleDoneUnwitnessedSiblingTests(unittest.TestCase):
    """The recorded closing act for a witness-less agreement, under this
    profile's own launcher and holder (`Experimental_AGREED.md`).

    The shared engine's logic is covered by the proposal skill's
    `SettleDoneUnwitnessedTests`; this class proves the act lands in this
    skill's holder, reads back under `witness.decided`, and that a decision
    logged against one skill's holder never names a same-text line in the
    sibling's holder (the ledger match is keyed by holder path).
    """

    def _box(self):
        box = (FORGE / "implementations"
               / f"_exp_settle_unwitnessed_{os.getpid()}")
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        for directory in ("src/Method", "tests", "Method"):
            (box / directory).mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        return box

    def _settle(self, box, *extra):
        env = dict(os.environ)
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(PROFILE_FILE)
        return subprocess.run(
            [sys.executable, str(LAUNCHER), "settle", "--target", str(box),
             "--name", "Method", "--session", "s9",
             "--text", "a deferred item", *extra],
            capture_output=True, text=True, cwd=FORGE, env=env)

    def test_the_act_lands_in_this_skills_holder_and_reads_back(self):
        engine = HolderCollisionTests._load_engine(self)
        box = self._box()
        holder = box / "Method" / engine.HOLDER_FILENAME
        holder.write_text("# Agreed\n\n## Ladder\n\n- [ ] a deferred item\n",
                          encoding="utf-8")
        proc = self._settle(box, "--done", "--unwitnessed", "--reason",
                            "Deferred to the next revision.")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["holder"],
                         f"Method/{engine.HOLDER_FILENAME}")
        self.assertIn("- [x] a deferred item\n",
                      holder.read_text(encoding="utf-8"))
        state = engine.agreements_state(box, "Method")
        self.assertEqual(state["status"], "settled")
        self.assertEqual([d["reason"] for d in state["witness"]["decided"]],
                         ["Deferred to the next revision."])

    def test_a_decision_on_one_holder_never_names_the_siblings_line(self):
        engine = HolderCollisionTests._load_engine(self)
        box = self._box()
        (box / "Method" / engine.HOLDER_FILENAME).write_text(
            "# Agreed\n\n## Ladder\n\n- [x] a deferred item\n", encoding="utf-8")
        ledger = box / "Method" / ".implementation" / "position.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({
            "kind": "settle", "session": "s1", "text": "a deferred item",
            "done": True, "unwitnessed": True, "reason": "elsewhere",
            "holder": "Method/AGREED.md", "at": "2026-10-11T00:00:00Z"}) + "\n",
            encoding="utf-8")
        witness = engine.agreements_state(box, "Method")["witness"]
        self.assertNotIn("decided", witness)
        self.assertEqual(witness["handTicked"], ["a deferred item"])


CONVENTION_FILE = FORGE / "skills" / "_core" / "conventions" / "experiments.json"


class SharedExperimentConventionTests(unittest.TestCase):
    """A7 (`cross-skill-consistency`): ONE experiment convention, read by
    both experimental skills from `skills/_core/conventions/experiments.json`.

    The canonical form is the one `experimental-deliberation` produces and
    validates: an experiment declares `[exp:<id>]` in its own heading, and
    its block runs to the next heading of the same or a higher level.
    Before 0.14.0 this skill located experiments only by a bare `## N`
    heading, so a document written the deliberation's way read as declaring
    no experiment at all; documents had to carry both forms. The legacy
    `## N` form (with or without a nested `[exp:<id>]` heading) still reads
    -- managed revisions are immutable -- and inside one legacy block both
    ids name the same experiment.
    """

    CANONICAL = (
        "# Experiments\n\n"
        "## Experiment [exp:E1] — first sweep\n\n"
        "Sustains claim C1 [tests:E1], citing [claims:9].\n\n"
        "### Protocol\n\nFive seeds.\n\n"
        "## Experiment [exp:E2] — second sweep\n\n"
        "Sustains claim C2 [tests:E2].\n\n"
        "## Reporting\n\nTables.\n"
    )

    LEGACY_DUAL = (
        "# Experiments\n\n"
        "## 1\n\n### Experiment [exp:E1] — first sweep\n\nOld text one.\n\n"
        "## 2\n\n### Experiment [exp:E2] — second sweep\n\nOld text two.\n"
    )

    LEGACY_BARE = "## 1\n\nOld text one.\n\n## 2\n\nOld text two.\n"

    def _tmp_dir(self, prefix: str) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _engine(self, doc0_text: str | None = None, doc1_text: str | None = None):
        module, _ = _engine_with_documents(_real_profile()["documents"])
        doc0_dir = self._tmp_dir("convention-doc0-")
        doc1_dir = self._tmp_dir("convention-doc1-")
        if doc0_text is not None:
            (doc0_dir / "e1.md").write_text(doc0_text, encoding="utf-8")
        if doc1_text is not None:
            (doc1_dir / "p1.md").write_text(doc1_text, encoding="utf-8")
        saved = {key: os.environ.get(key)
                 for key in ("IMPLEMENTATION_PROPOSALS", "IMPLEMENTATION_PROPOSALS_1")}
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(doc0_dir)
        os.environ["IMPLEMENTATION_PROPOSALS_1"] = str(doc1_dir)

        def _restore():
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(_restore)
        return module

    def _compose(self, module, remedy_block: str, locus: str, entry: str) -> dict:
        box = FORGE / "implementations" / f"_convention_{os.getpid()}_{id(self)}_{next(_counter)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        finding = {"id": "f1", "document": "experiments", "experiments": [locus],
                   "remedy_experiments": [locus], "remedy": "rewrite it",
                   "remedy_block": remedy_block}
        (box / "tests" / "findings.py").write_text(
            f"FINDINGS = [{finding!r}]\n", encoding="utf-8")
        return module.cmd_compose(argparse.Namespace(
            target=str(box), finding="f1", entry_text=entry))

    # -- the canonical form, with no `## N` heading anywhere -------------

    def test_a_canonical_document_declares_its_experiments(self):
        module = self._engine()
        locator = module.document_block_locator(0)
        self.assertEqual(locator["pattern"].findall(self.CANONICAL), ["E1", "E2"])

    def test_a_canonical_locus_is_not_unknown_to_the_compatibility_audit(self):
        module = self._engine(self.CANONICAL, "$$a = b \\tag{9}$$\n")
        finding = {"id": "f1", "document": "experiments", "experiments": ["E2"],
                   "remedy_experiments": ["E2"], "uses": [], "introduces": []}
        result = module.remedy_compatibility(
            [finding], "e1.md", {"experiments": self.CANONICAL,
                                 "proposal": "$$a = b \\tag{9}$$\n"})
        self.assertEqual(result["unknownExperiments"], [], result)

    def test_a_canonical_document_still_crosses_into_the_proposal(self):
        module = self._engine(self.CANONICAL, "$$a = b \\tag{9}$$ $$c \\tag{4}$$\n")
        self.assertEqual(module.crossing_state(0, "e1.md"),
                         {"crossed": ["9"], "declared": ["4", "9"],
                          "absent": [], "untested": ["4"]})

    def test_compose_replaces_one_canonical_block_and_keeps_its_neighbours(self):
        module = self._engine()
        remedy = "## Experiment [exp:E1] — first sweep\n\nNew text one.\n"
        composed = self._compose(module, remedy, "E1", self.CANONICAL)
        self.assertEqual(composed["experiment"], "E1")
        text = composed["replacementText"]
        self.assertIn("New text one.", text)
        # The nested `### Protocol` belonged to E1's block and went with it;
        # E2 and the same-level `## Reporting` are untouched.
        self.assertNotIn("Five seeds.", text)
        self.assertIn("## Experiment [exp:E2] — second sweep\n\nSustains claim C2", text)
        self.assertTrue(text.endswith("## Reporting\n\nTables.\n"), text)

    def test_canonical_prose_citations_are_counted(self):
        pattern = re.compile(_real_profile()["findings"]["citation_pattern"])
        found = [next(g for g in m.groups() if g)
                 for m in pattern.finditer("As (Exp. E1) and (Experiment. run-2.b) show.")]
        self.assertEqual(found, ["E1", "run-2.b"])

    # -- the legacy forms keep reading -----------------------------------

    def test_legacy_prose_citations_still_count(self):
        pattern = re.compile(_real_profile()["findings"]["citation_pattern"])
        found = [next(g for g in m.groups() if g)
                 for m in pattern.finditer("Exp. 3, Exps. (4), Experiment 5, Experimentos (6)")]
        self.assertEqual(found, ["3", "4", "5", "6"])

    def test_the_legacy_bare_heading_still_declares(self):
        module = self._engine()
        self.assertEqual(
            module.document_block_locator(0)["pattern"].findall(self.LEGACY_BARE),
            ["1", "2"])

    def test_the_legacy_dual_form_declares_both_ids(self):
        module = self._engine()
        self.assertEqual(
            module.document_block_locator(0)["pattern"].findall(self.LEGACY_DUAL),
            ["1", "E1", "2", "E2"])

    def test_a_legacy_remedy_carrying_both_ids_composes_as_one_experiment(self):
        module = self._engine()
        remedy = "## 1\n\n### Experiment [exp:E1] — first sweep\n\nNew text one."
        composed = self._compose(module, remedy, "1", self.LEGACY_DUAL)
        self.assertEqual(
            composed["replacementText"],
            "# Experiments\n\n" + remedy + "\n## 2\n\n"
            "### Experiment [exp:E2] — second sweep\n\nOld text two.\n")

    def test_a_canonical_id_reaches_its_legacy_block(self):
        module = self._engine()
        remedy = "### Experiment [exp:E2] — second sweep\n\nNew text two.\n"
        composed = self._compose(module, remedy, "E2", self.LEGACY_DUAL)
        self.assertEqual(
            composed["replacementText"],
            "# Experiments\n\n## 1\n\n### Experiment [exp:E1] — first sweep\n\n"
            "Old text one.\n\n" + remedy)

    def test_a_legacy_bare_remedy_composes_exactly_as_before(self):
        module = self._engine()
        composed = self._compose(module, "## 2\n\nNew text two.\n", "2",
                                 self.LEGACY_BARE)
        self.assertEqual(composed["replacementText"],
                         "## 1\n\nOld text one.\n\n## 2\n\nNew text two.\n")

    def test_two_separate_experiments_in_one_remedy_stay_ambiguous(self):
        module = self._engine()
        remedy = ("## Experiment [exp:E1] — a\n\none\n\n"
                  "## Experiment [exp:E2] — b\n\ntwo\n")
        with self.assertRaises(module.Refused) as caught:
            self._compose(module, remedy, "E1", self.CANONICAL)
        self.assertEqual(caught.exception.code, "AMBIGUOUS_REMEDY_TAG")

    def test_one_id_declared_by_two_blocks_of_a_remedy_stays_ambiguous(self):
        module = self._engine()
        remedy = ("## 1\n\n### Experiment [exp:E1] — a\n\none\n\n"
                  "## Experiment [exp:E1] — again\n\ntwo\n")
        with self.assertRaises(module.Refused) as caught:
            self._compose(module, remedy, "1", self.LEGACY_DUAL)
        self.assertEqual(caught.exception.code, "AMBIGUOUS_REMEDY_TAG")

    def test_without_block_aliases_several_ids_stay_ambiguous(self):
        """Aliasing is the document's own declaration, off by default: the
        same legacy remedy refuses under a locator that does not opt in."""
        documents = copy.deepcopy(_real_profile()["documents"])
        del documents[0]["block_locator"]["block_aliases"]
        module, tmp_dir = _engine_with_documents(documents)
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        remedy = "## 1\n\n### Experiment [exp:E1] — first sweep\n\nNew text one."
        with self.assertRaises(module.Refused) as caught:
            self._compose(module, remedy, "1", self.LEGACY_DUAL)
        self.assertEqual(caught.exception.code, "AMBIGUOUS_REMEDY_TAG")

    def test_a_non_boolean_block_aliases_is_refused_by_the_resolver(self):
        profile = copy.deepcopy(dict(_real_profile()))
        profile["documents"][0]["block_locator"]["block_aliases"] = "yes"
        tmp_dir = self._tmp_dir("convention-aliases-")
        profile_file = tmp_dir / "impl_profile.py"
        profile_file.write_text(
            "from pathlib import Path\n" f"PROFILE = {_to_source(profile)}\n",
            encoding="utf-8")
        with self.assertRaises(RuntimeError) as ctx:
            _resolve_with(profile_file)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_BLOCK_LOCATOR",
                      str(ctx.exception))
        self.assertIn("block_aliases", str(ctx.exception))

    # -- one shared file drives both readers -----------------------------

    def _relocated_profile(self, convention: dict):
        """This skill's real profile file, placed in a scratch tree whose
        `_core/conventions/experiments.json` says something else."""
        root = self._tmp_dir("convention-tree-")
        skill = root / "skills" / "experimental-implementation"
        skill.mkdir(parents=True)
        shutil.copy(PROFILE_FILE, skill / "impl_profile.py")
        conventions = root / "skills" / "_core" / "conventions"
        conventions.mkdir(parents=True)
        (conventions / "experiments.json").write_text(
            json.dumps(convention), encoding="utf-8")
        # B1: the profile also reads the shared section-label convention.
        shutil.copy(CONVENTION_FILE.parent / "sections.json",
                    conventions / "sections.json")
        return _load_module(skill / "impl_profile.py", "relocated_profile").PROFILE

    def test_the_profile_reads_the_shared_file(self):
        convention = json.loads(CONVENTION_FILE.read_text(encoding="utf-8"))
        convention["declares"] = "trial"
        convention["proseReference"] = "\\(Trial\\s+({identifier})\\)"
        profile = self._relocated_profile(convention)
        locator = re.compile(profile["documents"][0]["block_locator"]["pattern"])
        self.assertEqual(locator.findall("## Trial [trial:T7]\n## X [exp:E1]\n"), ["T7"])
        prose = re.compile(profile["findings"]["citation_pattern"])
        self.assertEqual([next(g for g in m.groups() if g)
                          for m in prose.finditer("see (Trial T7)")], ["T7"])

    def test_both_languages_load_the_same_convention(self):
        """The deliberation's TypeScript reader and this profile read the
        identical values: declaration, citation and prose patterns."""
        harness = (
            "import path from 'node:path';\n"
            "import { pathToFileURL } from 'node:url';\n"
            f"const piRoot = {json.dumps(str(FORGE))};\n"
            "const { createJiti } = await import(pathToFileURL(path.join(piRoot, "
            "'node_modules/jiti/lib/jiti.mjs')).href);\n"
            "const jiti = createJiti(import.meta.url);\n"
            "const m = await jiti.import(path.join(piRoot, "
            "'skills/experimental-deliberation/reference-experimental.ts'));\n"
            "console.log(JSON.stringify(m.EXPERIMENT_CONVENTION));\n")
        scratch = self._tmp_dir("convention-node-")
        (scratch / "harness.mjs").write_text(harness, encoding="utf-8")
        env = dict(os.environ)
        env["DELIBERATION_DOMAIN_PROFILE"] = str(
            FORGE / "skills" / "experimental-deliberation" / "profile.ts")
        proc = subprocess.run(["node", str(scratch / "harness.mjs")], env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        from_ts = json.loads(proc.stdout.strip().splitlines()[-1])
        profile_module = _load_module(PROFILE_FILE, "convention_probe")
        self.assertEqual(from_ts, profile_module.EXPERIMENT_CONVENTION)
        self.assertEqual(from_ts, json.loads(CONVENTION_FILE.read_text(encoding="utf-8")))


class PerLineageImplementationBindingTests(unittest.TestCase):
    """A8 (`cross-skill-consistency`): `proposal-implementation` and this
    skill share one engine and, on one target, one `src/<Package>/__init__.py`
    -- so one `__implementation__`. Its `revision` held a single name, which
    each skill read as a revision of its OWN document 0: bound to the
    proposal, this skill's `verify` discovered nothing (`fidelity: unknown`);
    bound to the experiments document, the sibling's did the same. Keyed by
    document label, each skill reads its own lineage; a bare string keeps
    meaning this skill's document 0, exactly as before."""

    PROPOSAL = "$$a = b \\tag{1}$$\n"
    EXPERIMENTS = "## Experiment [exp:E1] — sweep\n\nBody.\n"

    def _engine(self):
        engine = HolderCollisionTests._load_engine(self)
        doc0 = Path(tempfile.mkdtemp(prefix="lineage-doc0-"))
        doc1 = Path(tempfile.mkdtemp(prefix="lineage-doc1-"))
        for directory in (doc0, doc1):
            self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        (doc0 / "experiments-x-v01.md").write_text(self.EXPERIMENTS, encoding="utf-8")
        (doc1 / "r01.md").write_text(self.PROPOSAL, encoding="utf-8")
        saved = {key: os.environ.get(key)
                 for key in ("IMPLEMENTATION_PROPOSALS", "IMPLEMENTATION_PROPOSALS_1")}
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(doc0)
        os.environ["IMPLEMENTATION_PROPOSALS_1"] = str(doc1)

        def _restore():
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(_restore)
        return engine

    def _box(self, revision) -> Path:
        box = FORGE / "implementations" / f"_lineage_{os.getpid()}_{id(self)}_{next(_counter)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "tests").mkdir()
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method" / "__init__.py").write_text(
            f"__implementation__ = {{'revision': {revision!r}, "
            "'premises': {'metric': 'm'}}\n", encoding="utf-8")
        return box

    def _fidelity(self, engine, box) -> dict:
        return engine.cmd_verify(argparse.Namespace(
            target=str(box), name="Method", revision=None))["fidelity"]

    def test_a_keyed_binding_reads_this_skills_own_lineage(self):
        engine = self._engine()
        box = self._box({"proposal": "r01.md", "experiments": "experiments-x-v01.md"})
        fidelity = self._fidelity(engine, box)
        self.assertEqual(fidelity["latestRevision"], "experiments-x-v01.md")
        self.assertEqual(fidelity["benchmark"]["revision"], "experiments-x-v01.md")
        self.assertFalse(fidelity["benchmark"]["staleRevision"])
        self.assertNotEqual(fidelity["status"], "unknown")

    def test_the_siblings_lineage_alone_is_never_read_as_this_one(self):
        """Measured before 0.14.0 with the bare string `r01.md`: this skill
        searched `experiments/` for a family named by a proposal file."""
        engine = self._engine()
        box = self._box({"proposal": "r01.md"})
        resolved = engine.resolve_implementation_declaration(box, "Method")
        self.assertEqual(resolved["contract"]["revision"], "")
        self.assertIsNone(self._fidelity(engine, box)["benchmark"]["revision"] or None)

    def test_a_bare_string_still_means_this_skills_document_zero(self):
        engine = self._engine()
        box = self._box("experiments-x-v01.md")
        fidelity = self._fidelity(engine, box)
        self.assertEqual(fidelity["latestRevision"], "experiments-x-v01.md")
        self.assertEqual(fidelity["benchmark"]["revision"], "experiments-x-v01.md")

    def test_the_siblings_module_does_not_drift_this_skills_headline(self):
        """X16: the proposal-bound module read stale in this skill's whole-tree
        `staleModules` while `fidelityByDocument` judged it `ok` under its own
        label. It is reported in `otherLineageModules` instead."""
        engine = self._engine()
        box = self._box({"proposal": "r01.md", "experiments": "experiments-x-v01.md"})
        (box / "src" / "Method" / "sweep.py").write_text(
            "__provenance__ = {'revision': 'experiments-x-v01.md', 'sections': ['E1'], "
            "'experiments': ['E1'], 'invariants': []}\n", encoding="utf-8")
        (box / "src" / "Method" / "estimator.py").write_text(
            "__provenance__ = {'revision': 'r01.md', 'sections': ['1'], 'invariants': []}\n",
            encoding="utf-8")
        fidelity = self._fidelity(engine, box)
        self.assertEqual(fidelity["staleModules"], [])
        self.assertEqual(fidelity["otherLineageModules"],
                         [{"module": "src/Method/estimator.py", "label": "proposal",
                           "revision": "r01.md"}])
        self.assertEqual({entry["label"]: entry["conditions"]["staleModules"]
                          for entry in fidelity["fidelityByDocument"]},
                         {"experiments": [], "proposal": []})
        self.assertEqual(fidelity["status"], "ok", fidelity)

    def test_the_scaffold_template_names_this_skills_own_document(self):
        """The template's comment used to name `proposals/` under both
        skills; it now names this skill's own document directory and label."""
        engine = HolderCollisionTests._load_engine(self)
        template = engine._DEFAULT_PACKAGE_DECLARATIONS
        self.assertIn("# experiments/, asked for by the flow", template)
        self.assertIn('"revision": {"experiments": "<filename>"', template)
        self.assertNotIn("proposals/", template)


if __name__ == "__main__":
    unittest.main()


class ExperimentSectionsTests(unittest.TestCase):
    """B1 (`cross-skill-consistency`), the experimental side: per-section
    drift in `verify` speaks in the experiment ids the shared convention
    declares (`[exp:<id>]` in a heading), and still reads the legacy `## N`
    form. Before 0.14.0 neither form produced a section: the canonical
    heading carries no leading number, and the legacy `## N` stands alone on
    its line, which the old reader never matched."""

    CANONICAL = SharedExperimentConventionTests.CANONICAL
    LEGACY_DUAL = SharedExperimentConventionTests.LEGACY_DUAL

    def _engine(self):
        module, _ = _engine_with_documents(_real_profile()["documents"])
        return module

    def test_canonical_experiment_headings_are_sections(self):
        engine = self._engine()
        self.assertEqual(sorted(engine.revision_sections(self.CANONICAL)), ["E1", "E2"])
        moved = engine.changed_sections(
            self.CANONICAL, self.CANONICAL.replace("Five seeds", "Ten seeds"))
        self.assertEqual(moved, ["E1"])

    def test_legacy_blocks_read_both_ids(self):
        engine = self._engine()
        self.assertEqual(sorted(engine.revision_sections(self.LEGACY_DUAL)),
                         ["1", "2", "E1", "E2"])
        moved = engine.changed_sections(
            self.LEGACY_DUAL, self.LEGACY_DUAL.replace("Old text two", "New"))
        self.assertEqual(moved, ["2", "E2"])

    def test_a_malformed_section_heading_is_refused_by_the_resolver(self):
        real = dict(_real_profile()["documents"][0]["section_heading"])
        for grammar in ({**real, "marker": r"\[exp:[A-Z0-9]+\]"},
                        {**real, "marker": r"(a)(b)"},
                        {**real, "label": r"(unclosed"},
                        {"closer": real["closer"]},
                        "not a mapping"):
            with self.subTest(grammar=grammar):
                profile = copy.deepcopy(dict(_real_profile()))
                profile["documents"][0]["section_heading"] = grammar
                tmp_dir = Path(tempfile.mkdtemp(prefix="section-heading-"))
                self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
                profile_file = tmp_dir / "impl_profile.py"
                profile_file.write_text(
                    "from pathlib import Path\n" f"PROFILE = {_to_source(profile)}\n",
                    encoding="utf-8")
                with self.assertRaises(RuntimeError) as ctx:
                    _resolve_with(profile_file)
                self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_SECTION_HEADING",
                              str(ctx.exception))

    def test_both_implementation_profiles_hand_over_the_one_convention(self):
        convention = {key: value for key, value in json.loads(
            (FORGE / "skills/_core/conventions/sections.json").read_text(
                encoding="utf-8")).items() if not key.startswith("$")}
        sibling = _load_module(
            FORGE / "skills/proposal-implementation/impl_profile.py",
            "proposal_impl_profile_sections").PROFILE
        self.assertEqual(sibling["documents"][0]["section_heading"], convention)
        mine = dict(_real_profile()["documents"][0]["section_heading"])
        mine.pop("marker")
        self.assertEqual(mine, convention)
