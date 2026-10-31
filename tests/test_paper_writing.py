"""paper-writing: scaffold, block grammar, substitution engine.

Stdlib-only `unittest`. Every fixture lives under a `TemporaryDirectory`; the
real `paper/` at the forge root is never touched by this suite outside the
one CLI subprocess test, which scaffolds under the already-gitignored
`.scratch/` tree and cleans up after itself. Every
`paper_scaffold.resolve_paper_dir` call below passes an injected
`forge_root` for exactly this reason.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import dataclasses
import hashlib
import importlib
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
SECTIONS_DIR = FORGE_ROOT / "sections"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_scaffold  # noqa: E402
import paper_block  # noqa: E402
import paper_cli  # noqa: E402
import paper_contract  # noqa: E402
import paper_vocabulary  # noqa: E402
import paper_bindings  # noqa: E402
import paper_audit  # noqa: E402
import paper_write  # noqa: E402
import paper_style  # noqa: E402
import paper_leak  # noqa: E402
import paper_coupling_evidence  # noqa: E402
import paper_verify  # noqa: E402
import paper_objective  # noqa: E402
import paper_graph  # noqa: E402
import paper_obligation  # noqa: E402
import paper_readiness  # noqa: E402
import paper_declarations  # noqa: E402
import paper_region  # noqa: E402
import paper_guidance  # noqa: E402
import paper_source_span  # noqa: E402
import paper_marker  # noqa: E402
import paper_grounding  # noqa: E402 -- the-block-asserts-only-what-its-section-carries: per-sentence support reconciliation against the bound section's own bytes
import paper_figure  # noqa: E402 -- the-figure-nobody-looked-at, Phase 4: the repair-budget ledger `--visual-report`'s join must leave untouched

sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402
import impl_layout  # noqa: E402

# `the-figure-nobody-looked-at`, Phase 4: `figure-review`'s own rasterizer/
# measurement modules, imported here ONLY for this end-to-end TEST join --
# `paper_cli.py` itself never imports `figure-review` (design.md: "Never an
# edge: paper-writing --X--> figure-review"; the join is `--visual-report
# <path>`, never an import, in either direction).
sys.path.insert(0, str(FORGE_ROOT / "skills" / "figure-review" / "scripts"))
import raster as figure_review_raster  # noqa: E402
import findings as figure_review_findings  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "figure"))
import figure_dimensions  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "tests"))
from paper_mutation import _run_against_mutant  # noqa: E402
# `the-figure-nobody-looked-at`, Phase 4: reuses the stub `latexmk`
# `tests/test_paper_figure.py` already installs for its own repair-budget
# ledger tests -- the same shape `tests/test_implementation_domain_
# mutation.py` already establishes for cross-test-file reuse, never a
# second copy of the same stub source that could drift from the original.
from test_paper_figure import _install_stub_latexmk  # noqa: E402

CLI = SKILL_SCRIPTS / "paper_cli.py"
CORE_IMPLEMENTATION = FORGE_ROOT / "skills" / "_core" / "implementation"


#: Guarded, module-scoped `subprocess.Popen` monitor
#: (`writing-orchestration` spec, `Requirement: No Live Agent Invocation In
#: Tests`). Installed at IMPORT time, before any test in this module (or,
#: under `python -m unittest discover`, any test collected alongside it)
#: runs -- passive observation only, never blocking, so it cannot break an
#: unrelated suite's own legitimate subprocess use (`git`, `sys.executable`
#: running this skill's own CLI, etc). `paper-writing` never ships a code
#: path that spawns an agent binary (`design.md`, Decision D2: "No
#: agent-invoking code path exists"), so the list this accumulates is
#: asserted empty by `ZZLiveAgentGuardTests` below.
_AGENT_BINARY_NAMES = ("claude", "gemini", "codex", "pi", "claude-code")
_live_agent_launches: list[list[str]] = []
_real_popen_init = subprocess.Popen.__init__


def _guarded_popen_init(self, args, *a, **kw):
    argv = args if isinstance(args, (list, tuple)) else [args]
    head = Path(str(argv[0])).name if argv else ""
    if head in _AGENT_BINARY_NAMES:
        _live_agent_launches.append([str(x) for x in argv])
    return _real_popen_init(self, args, *a, **kw)


subprocess.Popen.__init__ = _guarded_popen_init


def _marker_pair(block_id: str, body: bytes) -> bytes:
    """Build a well-formed begin/end pair with the correct digest for
    `body`. Test-only fixture construction — production code never builds a
    pair this way; `open` (a later work unit) is what installs an empty one.
    """
    digest = hashlib.sha256(body).hexdigest()
    return (
        f"%% paper-writing block {block_id} begin sha256={digest}\n".encode("ascii")
        + body
        + f"%% paper-writing block {block_id} end\n".encode("ascii")
    )


def _write_fixture(paper_dir: Path, main_tex: bytes) -> None:
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "main.tex").write_bytes(main_tex)


def _settle_separation_round(
    paper_dir: Path, base: Path, fact_id: str, lineage: str, block: str, sections,
) -> dict:
    """`the-whole-cut-is-argued-before-any-section-is-claimed`, owner
    amendment (design.md Decision I): a test-only shortcut that directly
    RECORDS an already-settled (score 0) `separation` round naming exactly
    `(block, fact_id)` with `sections`, scored against the document
    `fact_id`'s own source root resolves to RIGHT NOW -- bypassing
    `compute_separation`'s own scoring pipeline, which Phases 1-4's own
    suite already proves independently (`test_paper_separation.py`,
    `SeparateVerbEndToEndTests`, `SeparationRoundPersistenceTests`). Used
    only to license a fixture's `bind_section`/`cmd_bind` call under the
    NEW precondition this owner amendment adds; every fixture below still
    proves `bind_section` itself, never re-proves `separate`."""
    root = paper_declarations.FACT_SOURCE_ROOT[fact_id]
    status = paper_declarations.source_root_status(base, root)
    if root.kind is paper_declarations.SourceRootKind.INGESTED:
        revision_path = paper_declarations.resolve_ingested_document(status["path"], lineage)
    else:
        marker = paper_declarations.read_revisions_marker(status["path"])
        revision_path = paper_declarations.resolve_lineage(status["path"], lineage, marker)
    digest = hashlib.sha256(revision_path.read_bytes()).hexdigest()
    return paper_declarations.record_separation_round(
        paper_dir, root.name, lineage, revision_path.name, digest,
        [{"block": block, "fact": fact_id, "sections": list(sections)}], 0,
    )


class ScaffoldTests(unittest.TestCase):
    """`paper-scaffold` spec: create/re-enter `paper/` idempotently."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()

    def test_first_run_creates_the_tree(self) -> None:
        paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        result = paper_scaffold.scaffold(paper_dir)

        self.assertTrue((paper_dir / "main.tex").is_file())
        self.assertTrue((paper_dir / "refs.bib").is_file())
        self.assertTrue((paper_dir / "Figures").is_dir())
        self.assertTrue((paper_dir / ".gitkeep").is_file())
        self.assertEqual(
            sorted(result["created"]),
            sorted(["main.tex", "refs.bib", "Figures", ".gitkeep"]),
        )

    def test_second_run_leaves_hand_edited_bytes_identical(self) -> None:
        paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(paper_dir)
        (paper_dir / "main.tex").write_bytes(b"\\documentclass{article}\n% hand-edited\n")
        before = {
            str(p.relative_to(paper_dir)): p.read_bytes()
            for p in sorted(paper_dir.rglob("*")) if p.is_file()
        }

        result = paper_scaffold.scaffold(paper_dir)

        after = {
            str(p.relative_to(paper_dir)): p.read_bytes()
            for p in sorted(paper_dir.rglob("*")) if p.is_file()
        }
        self.assertEqual(before, after)
        self.assertEqual(result["created"], [])

    def test_paper_as_a_file_refuses_and_writes_nothing(self) -> None:
        paper_dir = self.forge_root / "paper"
        paper_dir.write_bytes(b"not a directory")

        with self.assertRaises(Refused) as ctx:
            paper_scaffold.scaffold(paper_dir)

        self.assertEqual(ctx.exception.code, "PAPER_NOT_A_DIRECTORY")
        self.assertEqual(paper_dir.read_bytes(), b"not a directory")

    def test_figures_as_a_file_refuses_and_writes_nothing_else(self) -> None:
        paper_dir = self.forge_root / "paper"
        paper_dir.mkdir()
        (paper_dir / "Figures").write_bytes(b"not a directory")

        with self.assertRaises(Refused) as ctx:
            paper_scaffold.scaffold(paper_dir)

        self.assertEqual(ctx.exception.code, "SCAFFOLD_ENTRY_WRONG_TYPE")
        self.assertIn("Figures", ctx.exception.detail)
        self.assertFalse((paper_dir / "main.tex").exists())
        self.assertFalse((paper_dir / "refs.bib").exists())
        self.assertFalse((paper_dir / ".gitkeep").exists())
        # The wrong-typed entry itself is untouched, not replaced.
        self.assertEqual((paper_dir / "Figures").read_bytes(), b"not a directory")

    def test_paper_outside_repository_refuses(self) -> None:
        outside = Path(self._tmp.name) / "elsewhere"

        with self.assertRaises(Refused) as ctx:
            paper_scaffold.resolve_paper_dir(str(outside), forge_root=self.forge_root)

        self.assertEqual(ctx.exception.code, "PAPER_OUTSIDE_REPOSITORY")

    def test_cli_scaffold_verb_runs_and_emits_json(self) -> None:
        # Real FORGE_ROOT (the CLI's own default), scaffolded under the
        # already-gitignored `.scratch/` tree and removed afterward —
        # the one place in this test class allowed to touch the real repo.
        test_root = FORGE_ROOT / ".scratch" / f".paper-writing-cli-test-{os.getpid()}"
        self.addCleanup(shutil.rmtree, test_root, ignore_errors=True)
        paper_dir = test_root / "paper"

        proc = subprocess.run(
            [sys.executable, str(CLI), "scaffold", "--paper", str(paper_dir)],
            capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue((paper_dir / "main.tex").is_file())

    def test_cli_scaffold_outside_repository_refuses_with_exit_2(self) -> None:
        outside = Path(tempfile.gettempdir()) / f"paper-writing-outside-test-{os.getpid()}"
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)

        proc = subprocess.run(
            [sys.executable, str(CLI), "scaffold", "--paper", str(outside)],
            capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(proc.returncode, 2, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "PAPER_OUTSIDE_REPOSITORY")
        self.assertFalse(outside.exists())


class BlockCoreTests(unittest.TestCase):
    """`block-substitution`: marker grammar, pairing, substitute, hand-edit
    detection and `--adopt`. Exercises `paper_block.py` directly — CLI
    wiring for `open`/`status`/`substitute` is a later work unit."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    def _fixture(self) -> bytes:
        return (
            b"\\documentclass{article}\n\\begin{document}\n\n"
            + _marker_pair("abstract", b"One paragraph abstract.\n")
            + b"\nSome prose between blocks.\n\n"
            + _marker_pair("intro", b"Introduction body.\n")
            + b"\n\\end{document}\n"
        )

    def test_well_formed_pair_parses_via_status(self) -> None:
        data = self._fixture()
        result = paper_block.status(data)

        ids = {b["id"]: b for b in result["blocks"]}
        self.assertEqual(set(ids), {"abstract", "intro"})
        self.assertEqual(ids["abstract"]["digest"], hashlib.sha256(b"One paragraph abstract.\n").hexdigest())
        start, end = ids["intro"]["region"]
        self.assertEqual(data[start:end], _marker_pair("intro", b"Introduction body.\n"))

    def test_malformed_marker_line_refuses_naming_the_line(self) -> None:
        data = b"%% paper-writing block intro begin\nbody\n%% paper-writing block intro end\n"

        with self.assertRaises(Refused) as ctx:
            paper_block.status(data)

        self.assertEqual(ctx.exception.code, "MARKER_MALFORMED")
        self.assertIn("intro begin", ctx.exception.detail)

    def test_duplicated_id_refuses(self) -> None:
        data = _marker_pair("intro", b"first\n") + _marker_pair("intro", b"second\n")

        with self.assertRaises(Refused) as ctx:
            paper_block.status(data)

        self.assertEqual(ctx.exception.code, "BLOCK_DUPLICATED")

    def test_unpaired_begin_refuses(self) -> None:
        data = b"%% paper-writing block a begin sha256=" + b"0" * 64 + b"\nbody\n"

        with self.assertRaises(Refused) as ctx:
            paper_block.status(data)

        self.assertEqual(ctx.exception.code, "BLOCK_UNPAIRED")

    def test_nested_begin_refuses(self) -> None:
        digest_a = hashlib.sha256(b"").hexdigest()
        data = (
            f"%% paper-writing block a begin sha256={digest_a}\n".encode("ascii")
            + _marker_pair("b", b"nested body\n")
            + b"%% paper-writing block a end\n"
        )

        with self.assertRaises(Refused) as ctx:
            paper_block.status(data)

        self.assertEqual(ctx.exception.code, "BLOCK_NESTED")

    def test_region_excludes_the_preceding_newline(self) -> None:
        preamble = b"preamble line\n"
        data = preamble + _marker_pair("a", b"body\n")
        parsed = paper_block.parse(data)
        begin, _end = parsed.pairs["a"]
        marker_lead = b"%% paper-writing block a begin"

        self.assertEqual(begin["start"], len(preamble))
        self.assertEqual(data[begin["start"]:begin["start"] + len(marker_lead)], marker_lead)

    def test_substitute_on_absent_block_refuses_and_creates_nothing(self) -> None:
        fixture = self._fixture()
        _write_fixture(self.paper_dir, fixture)

        with self.assertRaises(Refused) as ctx:
            paper_block.substitute(self.paper_dir, "results", new_body=b"New results.\n")

        self.assertEqual(ctx.exception.code, "BLOCK_ABSENT")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), fixture)
        self.assertFalse((self.paper_dir / ".paper-writing").exists())

    def test_body_carrying_a_marker_line_refuses(self) -> None:
        fixture = self._fixture()
        _write_fixture(self.paper_dir, fixture)
        bad_body = b"Some text.\n%% paper-writing block sneaky begin sha256=" + b"0" * 64 + b"\n"

        with self.assertRaises(Refused) as ctx:
            paper_block.substitute(self.paper_dir, "intro", new_body=bad_body)

        self.assertEqual(ctx.exception.code, "CONTENT_CARRIES_MARKER")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), fixture)

    def test_hand_edited_body_refuses_naming_both_digests(self) -> None:
        fixture = self._fixture()
        _write_fixture(self.paper_dir, fixture)
        tampered = fixture.replace(b"Introduction body.\n", b"Hand-edited body.\n", 1)
        (self.paper_dir / "main.tex").write_bytes(tampered)
        expected_digest = hashlib.sha256(b"Introduction body.\n").hexdigest()
        found_digest = hashlib.sha256(b"Hand-edited body.\n").hexdigest()

        with self.assertRaises(Refused) as ctx:
            paper_block.substitute(self.paper_dir, "intro", new_body=b"Whatever.\n")

        self.assertEqual(ctx.exception.code, "BLOCK_HAND_EDITED")
        self.assertIn(expected_digest, ctx.exception.detail)
        self.assertIn(found_digest, ctx.exception.detail)
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), tampered)

    def test_adopt_updates_digest_without_touching_body_and_clears_the_refusal(self) -> None:
        fixture = self._fixture()
        _write_fixture(self.paper_dir, fixture)
        tampered = fixture.replace(b"Introduction body.\n", b"Hand-edited body.\n", 1)
        (self.paper_dir / "main.tex").write_bytes(tampered)

        paper_block.substitute(self.paper_dir, "intro", adopt=True)

        post_adopt = (self.paper_dir / "main.tex").read_bytes()
        self.assertIn(b"Hand-edited body.\n", post_adopt)
        parsed = paper_block.parse(post_adopt)
        begin, end = parsed.pairs["intro"]
        on_disk_body = post_adopt[begin["end"]:end["start"]]
        self.assertEqual(on_disk_body, b"Hand-edited body.\n")
        self.assertEqual(begin["digest"], hashlib.sha256(b"Hand-edited body.\n").hexdigest())

        # A later substitute() no longer refuses BLOCK_HAND_EDITED.
        paper_block.substitute(self.paper_dir, "intro", new_body=b"Rewritten after adopt.\n")
        final = (self.paper_dir / "main.tex").read_bytes()
        self.assertIn(b"Rewritten after adopt.\n", final)

    def test_adopt_on_matching_digest_refuses_nothing_to_adopt(self) -> None:
        fixture = self._fixture()
        _write_fixture(self.paper_dir, fixture)

        with self.assertRaises(Refused) as ctx:
            paper_block.substitute(self.paper_dir, "intro", adopt=True)

        self.assertEqual(ctx.exception.code, "NOTHING_TO_ADOPT")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), fixture)


class InvariantTests(unittest.TestCase):
    """Byte-identity invariant: three conjuncts, so a no-op write cannot
    pass trivially, plus the guard that refuses before any write."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    def _fixture(self) -> bytes:
        return (
            b"Preamble.\n\n"
            + _marker_pair("a", b"Body A.\n")
            + b"\nMiddle prose, untouched.\n\n"
            + _marker_pair("b", b"Body B.\n")
            + b"\nTail.\n"
        )

    def test_only_the_named_block_changes_three_conjuncts(self) -> None:
        pre = self._fixture()
        _write_fixture(self.paper_dir, pre)

        paper_block.substitute(self.paper_dir, "a", new_body=b"New body for a.\n")

        # Independent re-read: a fresh `read_bytes()`, not the in-memory
        # candidate this call already held — comparing a value against
        # itself would prove nothing.
        post = (self.paper_dir / "main.tex").read_bytes()

        # Conjunct 1: everything outside block `a`'s region is identical.
        self.assertEqual(paper_block.project(post), paper_block.project(pre))
        # Conjunct 2: something on disk actually changed (rules out a
        # no-op `substitute` silently reporting success).
        self.assertNotEqual(post, pre)
        # Conjunct 3: the substituted block's body is exactly the new body
        # (rules out a change landing at the wrong offset that still
        # happens to leave the outside-region projection equal).
        parsed = paper_block.parse(post)
        begin, end = parsed.pairs["a"]
        self.assertEqual(post[begin["end"]:end["start"]], b"New body for a.\n")
        # Block `b`'s own body and digest are untouched.
        begin_b, end_b = parsed.pairs["b"]
        self.assertEqual(post[begin_b["end"]:end_b["start"]], b"Body B.\n")
        self.assertEqual(begin_b["digest"], hashlib.sha256(b"Body B.\n").hexdigest())

    def test_violating_candidate_refuses_before_any_write(self) -> None:
        pre = self._fixture()
        parsed = paper_block.parse(pre)
        candidate, _written = paper_block.build_candidate(pre, parsed, "a", b"New body.\n", adopt=False)
        # Corrupt one byte outside the target block's region — exactly the
        # violation `identity_invariant` exists to catch before a write.
        corrupted = bytearray(candidate)
        corrupted[0:1] = b"X"
        corrupted = bytes(corrupted)

        with self.assertRaises(Refused) as ctx:
            paper_block.identity_invariant(pre, corrupted)

        self.assertEqual(ctx.exception.code, "SUBSTITUTION_NOT_LOCAL")
        # `identity_invariant` never opens a file — the refusal above is
        # itself the proof no write was attempted for this candidate.

    def test_tex_moved_refuses_when_disk_changes_between_read_and_write(self) -> None:
        pre = self._fixture()
        _write_fixture(self.paper_dir, pre)
        real_read_bytes = Path.read_bytes
        calls = {"n": 0}

        def flaky_read_bytes(self_path):
            calls["n"] += 1
            if calls["n"] == 2:
                # Simulate a second session's edit landing between this
                # call's own initial read and its CAS re-read.
                (self.paper_dir / "main.tex").write_bytes(pre + b"% intruder\n")
            return real_read_bytes(self_path)

        with unittest.mock.patch.object(Path, "read_bytes", flaky_read_bytes):
            with self.assertRaises(Refused) as ctx:
                paper_block.substitute(self.paper_dir, "a", new_body=b"New body.\n")

        self.assertEqual(ctx.exception.code, "TEX_MOVED")


class PreImageTests(unittest.TestCase):
    """The one-deep pre-image: the only recovery path once bytes reach
    disk, and its depth limit proven rather than merely stated."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    def _fixture(self) -> bytes:
        return _marker_pair("a", b"Body A.\n")

    def _prev_path(self) -> Path:
        return self.paper_dir / ".paper-writing" / "main.tex.prev"

    def test_pre_image_holds_the_exact_pre_write_bytes(self) -> None:
        pre = self._fixture()
        _write_fixture(self.paper_dir, pre)

        paper_block.substitute(self.paper_dir, "a", new_body=b"First rewrite.\n")

        self.assertEqual(self._prev_path().read_bytes(), pre)

    def test_only_the_immediately_prior_state_is_recoverable(self) -> None:
        first = self._fixture()
        _write_fixture(self.paper_dir, first)

        paper_block.substitute(self.paper_dir, "a", new_body=b"First rewrite.\n")
        second = (self.paper_dir / "main.tex").read_bytes()
        self.assertEqual(self._prev_path().read_bytes(), first)

        paper_block.substitute(self.paper_dir, "a", new_body=b"Second rewrite.\n")

        # After the second write, the pre-image holds only what preceded
        # THAT write — the state before the first write is gone from this
        # mechanism, and nothing else (main.tex is untracked) retains it.
        self.assertEqual(self._prev_path().read_bytes(), second)
        self.assertNotEqual(self._prev_path().read_bytes(), first)

    def test_pre_image_is_written_before_main_tex_is_replaced(self) -> None:
        pre = self._fixture()
        _write_fixture(self.paper_dir, pre)
        real_replace = os.replace
        calls = {"n": 0}

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] == 2:
                # The second `os.replace` this call makes is main.tex's own
                # (the first is the pre-image's) — simulate a crash right
                # there, after the pre-image landed and before main.tex did.
                raise OSError("simulated crash between pre-image and main.tex")
            return real_replace(src, dst)

        with unittest.mock.patch("paper_block.os.replace", flaky_replace):
            with self.assertRaises(OSError):
                paper_block.substitute(self.paper_dir, "a", new_body=b"Rewrite.\n")

        # The pre-image landed; main.tex was never touched — the crash left
        # pre-image == main.tex, the harmless case design step 9 declares.
        self.assertEqual(self._prev_path().read_bytes(), pre)
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), pre)


class CRLFTests(unittest.TestCase):
    """Binary I/O only: a CRLF fixture built in code, never committed, and
    a control assertion proving a text-mode open would have corrupted it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    def test_crlf_block_round_trips_untouched_and_text_mode_would_corrupt_it(self) -> None:
        preamble = b"\\documentclass{article}\r\n\\begin{document}\r\n"
        body = b"Mid-paragraph CRLF body.\r\n"
        tail = b"\r\nTrailing prose with CRLF.\r\n\\end{document}\r\n"
        pre = preamble + _marker_pair("mid", body) + tail
        _write_fixture(self.paper_dir, pre)

        paper_block.substitute(self.paper_dir, "mid", new_body=b"Replacement body.\r\n")
        post = (self.paper_dir / "main.tex").read_bytes()

        # Every CRLF outside the substituted region survives byte for byte.
        self.assertTrue(post.startswith(preamble))
        self.assertTrue(post.endswith(tail))
        self.assertEqual(post.count(b"\r\n"), preamble.count(b"\r\n") + 1 + tail.count(b"\r\n"))

        # Control: a text-mode, universal-newlines open of the SAME bytes
        # flattens every CRLF to LF — proving that had production code used
        # text mode instead of binary, this test's own byte-identity
        # assertion above would have failed. Demonstrated on the file this
        # engine actually wrote, not a separate hand-built buffer.
        tex_path = self.paper_dir / "main.tex"
        with open(tex_path, "r", newline=None) as handle:
            text_mode_bytes = handle.read().encode("utf-8")
        self.assertNotEqual(text_mode_bytes, post)
        self.assertIn(b"\r\n", post)
        self.assertNotIn(b"\r\n", text_mode_bytes)


class TexUndecodableTests(unittest.TestCase):
    """block-substitution spec: a `main.tex` that cannot even be decoded to
    locate marker lines refuses rather than being reasoned about as source."""

    def test_undecodable_bytes_refuse_tex_undecodable(self) -> None:
        data = b"\xff\xfe not valid utf-8 \x80\x81"

        with self.assertRaises(Refused) as ctx:
            paper_block.parse(data)

        self.assertEqual(ctx.exception.code, "TEX_UNDECODABLE")


class BlockIdShapeTests(unittest.TestCase):
    """design step 1: `--block <id>` shape, checked before it is ever used
    to look anything up."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    def test_malformed_block_id_refuses_on_substitute(self) -> None:
        _write_fixture(self.paper_dir, _marker_pair("a", b"body\n"))

        with self.assertRaises(Refused) as ctx:
            paper_block.substitute(self.paper_dir, "not a valid id!", new_body=b"x\n")

        self.assertEqual(ctx.exception.code, "BLOCK_ID_MALFORMED")

    def test_malformed_block_id_refuses_on_open(self) -> None:
        _write_fixture(self.paper_dir, b"")

        with self.assertRaises(Refused) as ctx:
            paper_block.open_block(self.paper_dir, "bad id", at_end=True)

        self.assertEqual(ctx.exception.code, "BLOCK_ID_MALFORMED")


class ResolveMainTexTests(unittest.TestCase):
    """`open`, `status`, `substitute` never create `paper/` themselves —
    only `scaffold` does — so each refuses cleanly when it is missing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    def test_substitute_on_absent_paper_dir_refuses_paper_absent(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_block.substitute(self.paper_dir, "a", new_body=b"x\n")

        self.assertEqual(ctx.exception.code, "PAPER_ABSENT")

    def test_substitute_when_paper_is_a_file_refuses_paper_not_a_directory(self) -> None:
        self.paper_dir.parent.mkdir(parents=True, exist_ok=True)
        self.paper_dir.write_bytes(b"not a directory")

        with self.assertRaises(Refused) as ctx:
            paper_block.substitute(self.paper_dir, "a", new_body=b"x\n")

        self.assertEqual(ctx.exception.code, "PAPER_NOT_A_DIRECTORY")

    def test_status_on_missing_main_tex_refuses_paper_absent(self) -> None:
        self.paper_dir.mkdir(parents=True)

        with self.assertRaises(Refused) as ctx:
            paper_block.read_status(self.paper_dir)

        self.assertEqual(ctx.exception.code, "PAPER_ABSENT")


class OpenBlockTests(unittest.TestCase):
    """block-substitution spec: `open` installs an empty pair, never
    content."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    def _fixture(self) -> bytes:
        return (
            b"\\documentclass{article}\n\\begin{document}\n\n"
            + _marker_pair("a", b"Body A.\n")
            + b"\n\\end{document}\n"
        )

    def test_open_after_anchor_inserts_empty_pair_and_leaves_prefix_unchanged(self) -> None:
        fixture = self._fixture()
        _write_fixture(self.paper_dir, fixture)
        anchor_end = fixture.index(b"%% paper-writing block a end") + len(
            b"%% paper-writing block a end\n"
        )

        paper_block.open_block(self.paper_dir, "b", after="a")

        post = (self.paper_dir / "main.tex").read_bytes()
        self.assertEqual(post[:anchor_end], fixture[:anchor_end])
        empty_digest = hashlib.sha256(b"").hexdigest()
        self.assertIn(
            f"%% paper-writing block b begin sha256={empty_digest}\n"
            "%% paper-writing block b end\n".encode("ascii"),
            post,
        )
        parsed = paper_block.parse(post)
        self.assertEqual(set(parsed.order), {"a", "b"})

    def test_open_on_existing_id_refuses_block_duplicated(self) -> None:
        fixture = self._fixture()
        _write_fixture(self.paper_dir, fixture)

        with self.assertRaises(Refused) as ctx:
            paper_block.open_block(self.paper_dir, "a", at_end=True)

        self.assertEqual(ctx.exception.code, "BLOCK_DUPLICATED")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), fixture)

    def test_open_after_missing_anchor_refuses_anchor_absent(self) -> None:
        fixture = self._fixture()
        _write_fixture(self.paper_dir, fixture)

        with self.assertRaises(Refused) as ctx:
            paper_block.open_block(self.paper_dir, "b", after="missing")

        self.assertEqual(ctx.exception.code, "ANCHOR_ABSENT")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), fixture)

    def test_open_at_end_never_inserts_a_blank_line(self) -> None:
        fixture = (b"Preamble line.\n" + _marker_pair("a", b"Body.\n")).rstrip(b"\n")
        _write_fixture(self.paper_dir, fixture)

        paper_block.open_block(self.paper_dir, "b", at_end=True)

        post = (self.paper_dir / "main.tex").read_bytes()
        added = post[len(fixture):]
        # Exactly one newline completes the unterminated last line — never a
        # blank line, which would be two in a row.
        self.assertTrue(added.startswith(b"\n%% paper-writing block b begin"))
        self.assertFalse(added.startswith(b"\n\n"))


class CLIWiringTests(unittest.TestCase):
    """CLI wiring for `open`, `status`, `substitute` — exercised as real
    subprocesses against `paper_cli.py`. `paper_cli.py` always resolves
    `--paper` against the REAL repository root (there is no injection point
    through the CLI, unlike `paper_scaffold.resolve_paper_dir`'s own
    `forge_root` kwarg), so — like
    `ScaffoldTests.test_cli_scaffold_verb_runs_and_emits_json` — every
    fixture here lives under the already-gitignored `.scratch/` tree
    and is removed afterward, never under a system temp directory outside
    the repository, which `PAPER_OUTSIDE_REPOSITORY` would correctly refuse."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        test_root = FORGE_ROOT / ".scratch" / f".paper-writing-cli-wiring-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, test_root, ignore_errors=True)
        self.paper_dir = test_root / "paper"

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            capture_output=True, text=True, timeout=30,
        )

    def _scaffold(self) -> None:
        proc = self._run("scaffold", "--paper", str(self.paper_dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_status_reports_the_block_table_without_writing(self) -> None:
        self._scaffold()
        (self.paper_dir / "main.tex").write_bytes(_marker_pair("intro", b"Intro body.\n"))
        before = (self.paper_dir / "main.tex").read_bytes()

        proc = self._run("status", "--paper", str(self.paper_dir))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ok")
        ids = {b["id"] for b in payload["blocks"]}
        self.assertEqual(ids, {"intro"})
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), before)

    def test_open_then_substitute_round_trip(self) -> None:
        self._scaffold()

        proc = self._run("open", "--paper", str(self.paper_dir), "--block", "intro", "--at-end")
        self.assertEqual(proc.returncode, 0, proc.stderr)

        body_path = Path(self._tmp.name) / "body.txt"
        body_path.write_bytes(b"New introduction.\n")
        proc = self._run(
            "substitute", "--paper", str(self.paper_dir),
            "--block", "intro", "--body", str(body_path),
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["rendering"], "unproven")
        final = (self.paper_dir / "main.tex").read_bytes()
        self.assertIn(b"New introduction.\n", final)

    def test_substitute_body_from_stdin_dash(self) -> None:
        self._scaffold()
        self._run("open", "--paper", str(self.paper_dir), "--block", "intro", "--at-end")

        proc = subprocess.run(
            [sys.executable, str(CLI), "substitute", "--paper", str(self.paper_dir),
             "--block", "intro", "--body", "-"],
            input="From stdin.\n", capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        final = (self.paper_dir / "main.tex").read_bytes()
        self.assertIn(b"From stdin.\n", final)

    def test_substitute_with_neither_body_nor_adopt_refuses_substitute_mode_required(self) -> None:
        self._scaffold()
        self._run("open", "--paper", str(self.paper_dir), "--block", "intro", "--at-end")

        proc = self._run("substitute", "--paper", str(self.paper_dir), "--block", "intro")

        self.assertEqual(proc.returncode, 2, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "SUBSTITUTE_MODE_REQUIRED")

    def test_substitute_with_body_and_adopt_together_refuses_adopt_body_conflict(self) -> None:
        self._scaffold()
        self._run("open", "--paper", str(self.paper_dir), "--block", "intro", "--at-end")
        body_path = Path(self._tmp.name) / "body.txt"
        body_path.write_bytes(b"x\n")

        proc = self._run(
            "substitute", "--paper", str(self.paper_dir), "--block", "intro",
            "--body", str(body_path), "--adopt",
        )

        self.assertEqual(proc.returncode, 2, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "ADOPT_BODY_CONFLICT")

    def test_open_with_neither_position_refuses_open_position_required(self) -> None:
        self._scaffold()

        proc = self._run("open", "--paper", str(self.paper_dir), "--block", "intro")

        self.assertEqual(proc.returncode, 2, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "OPEN_POSITION_REQUIRED")

    def test_open_with_both_positions_refuses_open_position_conflict(self) -> None:
        self._scaffold()

        proc = self._run(
            "open", "--paper", str(self.paper_dir), "--block", "intro",
            "--after", "nope", "--at-end",
        )

        self.assertEqual(proc.returncode, 2, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "OPEN_POSITION_CONFLICT")

    def test_observe_validates_an_insumos_observer_report_and_writes_nothing(self) -> None:
        """`observe` wires `paper_declarations.validate_observation_report`
        to a real CLI caller -- the same shuttle shape `write --draft
        <path>` already establishes for the redactor's account."""
        self._scaffold()
        report_path = self.paper_dir.parent / "observation_report.json"
        report_path.write_text(json.dumps({
            "formulation": {"satisfied": True, "evidence": [["proposals/x.md", "the model is..."]]},
            "implementation": {"satisfied": True, "evidence": [["repo/code.py", "q1"]]},
            "results": {"satisfied": True, "evidence": [["repo/results.json", "q2"]]},
        }), encoding="utf-8")
        before = report_path.read_bytes()

        proc = self._run("observe", "--report", str(report_path))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["validated"])
        self.assertEqual(payload["satisfied"], ["formulation", "implementation", "results"])
        self.assertEqual(report_path.read_bytes(), before)

    def test_observe_refuses_an_id_outside_the_observable_facts(self) -> None:
        self._scaffold()
        report_path = self.paper_dir.parent / "observation_report.json"
        report_path.write_text(json.dumps({
            "contributions": {"satisfied": True, "evidence": [["x", "y"]]},
        }), encoding="utf-8")

        proc = self._run("observe", "--report", str(report_path))

        self.assertEqual(proc.returncode, 2, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "NOT_AN_OBSERVABLE_FACT")

    def test_observe_refuses_conflated_implementation_and_results_evidence(self) -> None:
        self._scaffold()
        report_path = self.paper_dir.parent / "observation_report.json"
        report_path.write_text(json.dumps({
            "implementation": {"satisfied": True, "evidence": [["repo/code.py", "q1"]]},
            "results": {"satisfied": True, "evidence": [["repo/code.py", "q2"]]},
        }), encoding="utf-8")

        proc = self._run("observe", "--report", str(report_path))

        self.assertEqual(proc.returncode, 2, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "EVIDENCE_CONFLATED")


class FigureVerbFrontDoorTests(unittest.TestCase):
    """`figure`: the verb-level front door, added because the guard
    (`test_paper_contract.VerbFrontDoorCoverageTests`) measured `figure` as
    the one shipped verb with no front-door test in any of the six
    `paper-writing` suites -- the FUNCTION level (`paper_figure.
    optimize_figure` etc.) was covered, the VERB was not. Both tests drive
    the real argparse dispatch (`paper_cli.main([...])`), the same shape
    the other wiring tests here use, never `paper_figure.*` directly.
    `figure optimize --file` alone is a DRY RUN by construction: no
    manifest, no `paper/`, nothing written, so a fixture beyond the tex
    source is unnecessary. `figure audit --file` additionally needs a
    manifest and the shipped sections corpus read -- never written."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_figure_optimize_dry_run_returns_the_envelope_and_writes_nothing(self) -> None:
        """`figure optimize --file <path>` runs the whole pure pipeline
        (libraries pruned, styles factored) on the candidate text, reports
        it in the public envelope, and writes nothing -- the source file is
        untouched and no ledger/output file appears. A provably-unused
        detectable library (`calc`) proves the pipeline ran rather than
        echoing the input back."""
        tex = self.tmp / "front-door-figure.tex"
        tex.write_text(
            "\\documentclass[tikz,border=2pt]{standalone}\n"
            "\\usetikzlibrary{calc}\n"
            "\\begin{document}\n"
            "\\begin{tikzpicture}\n"
            "\\node[draw] (a) {A};\n"
            "\\end{tikzpicture}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        before_listing = sorted(p.name for p in self.tmp.iterdir())
        before_bytes = tex.read_bytes()

        with contextlib.redirect_stdout(io.StringIO()) as buf:
            exit_code = paper_cli.main(["figure", "optimize", "--file", str(tex)])
        payload = json.loads(buf.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["command"], "figure")
        self.assertEqual(payload["figureId"], "front-door-figure")
        self.assertIn("\\begin{document}", payload["text"])
        self.assertNotIn("\\usetikzlibrary", payload["text"], "the unused 'calc' library is pruned")
        self.assertTrue(
            any("calc" in change for change in payload["changes"]),
            f"the dry-run report names the prune: {payload['changes']}",
        )
        self.assertEqual(tex.read_bytes(), before_bytes, "a dry run never rewrites the source")
        self.assertEqual(
            sorted(p.name for p in self.tmp.iterdir()), before_listing,
            "a dry run plants no ledger, manifest, or output file",
        )

    def test_figure_audit_returns_the_unmeasured_verdict_through_the_front_door(self) -> None:
        """`figure audit --file --manifest` with a manifest declaring no
        components is deterministic without any prose coupling: the verdict
        is `unmeasured` (`NO_COMPONENTS_DECLARED`), and `status: ok` -- a
        content finding is a verdict, never a refusal. `--section
        introduction` resolves against the shipped sections corpus, which
        is only read."""
        tex = self.tmp / "audited.tex"
        tex.write_text(
            "\\documentclass[tikz,border=2pt]{standalone}\n"
            "\\begin{document}\n"
            "\\begin{tikzpicture}\n"
            "\\node (a) {A};\n"
            "\\end{tikzpicture}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        manifest = self.tmp / "audited.diagram.json"
        manifest.write_text(json.dumps({"components": []}), encoding="utf-8")

        with contextlib.redirect_stdout(io.StringIO()) as buf:
            exit_code = paper_cli.main([
                "figure", "audit", "--file", str(tex), "--manifest", str(manifest),
                "--section", "introduction",
            ])
        payload = json.loads(buf.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["command"], "figure")
        self.assertEqual(payload["figureId"], "audited")
        self.assertEqual(payload["verdict"], "unmeasured")
        self.assertEqual(payload["unmeasured_reason"], "NO_COMPONENTS_DECLARED")
        self.assertEqual(payload["evidence"]["section"], "introduction.md")

    def test_figure_audit_with_block_whose_contract_declares_components_from_returns_the_envelope(self) -> None:
        """`figure audit --block` against the shipped `rw-synthesis-artefact`
        block (whose `figure.components_from` names `contributions`) must
        return the documented pass/fail/unmeasured envelope, never raise --
        the merge added `sections_dir` to `_resolve_expected_components` but
        this fork call site still passed two positional arguments, so the
        verb tracebacked with `TypeError: ... missing 1 required positional
        argument: 'fact_id'` and exit 1 whenever a block's contract declared
        `components_from` (except Refused does not catch TypeError). A
        content finding stays a verdict: on a clean checkout `contributions`
        has no declared/written producer, so the resolution refuses
        `COMPONENTS_FACT_UNRESOLVED` and the envelope reports `unmeasured`;
        if a real `paper/` ever carries the producer, the same call still
        returns a verdict, which is what this regression locks."""
        tex = self.tmp / "audited-components-from.tex"
        tex.write_text(
            "\\documentclass[tikz,border=2pt]{standalone}\n"
            "\\begin{document}\n"
            "\\begin{tikzpicture}\n"
            "\\node (a) {A};\n"
            "\\end{tikzpicture}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        manifest = self.tmp / "audited-components-from.diagram.json"
        manifest.write_text(json.dumps({"components": ["A"]}), encoding="utf-8")

        with contextlib.redirect_stdout(io.StringIO()) as buf:
            exit_code = paper_cli.main([
                "figure", "audit", "--file", str(tex), "--manifest", str(manifest),
                "--section", "related-work", "--block", "rw-synthesis-artefact",
            ])
        payload = json.loads(buf.getvalue())

        self.assertEqual(exit_code, 0, "the components_from branch never raises through the front door")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["command"], "figure")
        self.assertEqual(payload["figureId"], "audited-components-from")
        self.assertIn(payload["verdict"], ("pass", "fail", "unmeasured"))
        self.assertEqual(payload["evidence"]["section"], "related-work.md")
        if payload["verdict"] == "unmeasured":
            self.assertEqual(
                payload["unmeasured_reason"], "COMPONENTS_FACT_UNRESOLVED",
                "the components_from branch ran: only 'contributions' having no written "
                "producer excuses the check, never the contract declining the comparison",
            )

    def test_figure_audit_unreadable_source_refuses_with_diagram_source_absent(self) -> None:
        """`figure audit` with a source it cannot read refuses through the
        front door instead of tracebacking: a manifest that is not valid
        JSON and a tex that does not decode as UTF-8 both refuse with the
        same `DIAGRAM_SOURCE_ABSENT` the absent-pair guard already uses
        (`status: refused`, exit 2) -- never a `JSONDecodeError` /
        `UnicodeDecodeError` crash with exit 1, because an unreadable
        invocation reuses the code the repo already names for it."""
        tex = self.tmp / "audited.tex"
        tex.write_text(
            "\\documentclass[tikz,border=2pt]{standalone}\n"
            "\\begin{document}\n"
            "\\begin{tikzpicture}\n"
            "\\node (a) {A};\n"
            "\\end{tikzpicture}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        malformed_manifest = self.tmp / "malformed.diagram.json"
        malformed_manifest.write_text("not json{", encoding="utf-8")
        valid_manifest = self.tmp / "valid.diagram.json"
        valid_manifest.write_text(json.dumps({"components": []}), encoding="utf-8")
        undecodable_tex = self.tmp / "undecodable.tex"
        undecodable_tex.write_bytes(
            b"\\documentclass[tikz,border=2pt]{standalone}\n"
            b"\\begin{document}\n"
            b"\\begin{tikzpicture}\n"
            b"\\node (a) {\xff};\n"
            b"\\end{tikzpicture}\n"
            b"\\end{document}\n"
        )

        for label, tex_path, manifest_path in [
            ("malformed manifest", tex, malformed_manifest),
            ("undecodable tex", undecodable_tex, valid_manifest),
        ]:
            with self.subTest(label=label):
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    exit_code = paper_cli.main([
                        "figure", "audit", "--file", str(tex_path),
                        "--manifest", str(manifest_path),
                        "--section", "introduction",
                    ])
                payload = json.loads(buf.getvalue())

                self.assertEqual(exit_code, 2)
                self.assertEqual(payload["status"], "refused")
                self.assertEqual(payload["code"], "DIAGRAM_SOURCE_ABSENT")


class FigureAuditVisualReportJoinTests(unittest.TestCase):
    """`the-figure-nobody-looked-at`, Phase 4, tasks 4.1-4.4: `figure
    audit` gains `--visual-report <path>`, resolved through the same
    `_resolve_repo_path` `--draft`/`--audit`/`--transcript` already reuse
    (design.md, Decision 5) -- never a derived scratch location, and
    never an import of `figure-review` in either direction. Fixtures live
    under the already-gitignored `.scratch/` tree: `_resolve_repo_path`
    has no injectable `forge_root` (unlike `paper_scaffold.resolve_paper_
    dir`), so every path this class supplies must resolve inside the
    REAL repository root (`.gitignore`'s own comment on why `.scratch/`
    exists for exactly this)."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".figure-audit-visual-report-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.test_root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.tex = self.test_root / "audited.tex"
        self.tex.write_text(
            "\\documentclass[tikz,border=2pt]{standalone}\n"
            "\\begin{document}\n"
            "\\begin{tikzpicture}\n"
            "\\node (a) {A};\n"
            "\\end{tikzpicture}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        self.manifest = self.test_root / "audited.diagram.json"
        self.manifest.write_text(json.dumps({"components": []}), encoding="utf-8")

    def _run(self, visual_report: Path | None = None, **extra_args: str) -> tuple:
        args = [
            "figure", "audit", "--file", str(self.tex), "--manifest", str(self.manifest),
            "--section", "introduction",
        ]
        for flag, value in extra_args.items():
            args += [f"--{flag}", value]
        if visual_report is not None:
            args += ["--visual-report", str(visual_report)]
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            exit_code = paper_cli.main(args)
        return exit_code, json.loads(buf.getvalue())

    def test_a_caller_supplied_visual_report_is_read_and_threaded_verbatim(self) -> None:
        # Task 4.2 -- lock 3's schema-level guarantee (task 3.1), confirmed
        # through the CLI front door rather than only `audit_semantics`
        # directly.
        visual = figure_dimensions.default_visual()
        visual["dimensions"]["overlap"] = {"verdict": "pass", "reason": None, "collisions": []}
        report_path = self.test_root / "visual-report.json"
        report_path.write_text(json.dumps(visual), encoding="utf-8")

        exit_code, payload = self._run(report_path)

        self.assertEqual(exit_code, 0, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["visual"], visual)

    def test_omitting_visual_report_defaults_to_every_dimension_unmeasured(self) -> None:
        # The `None` branch task 4.2 adds: no `--visual-report` at all
        # still threads through to `audit_semantics(visual=None)`, which
        # defaults (Commit 3, unchanged by this phase).
        exit_code, payload = self._run(None)

        self.assertEqual(exit_code, 0, payload)
        self.assertEqual(payload["visual"], figure_dimensions.default_visual())

    def test_an_absent_visual_report_refuses_diagram_source_absent(self) -> None:
        report_path = self.test_root / "does-not-exist.json"

        exit_code, payload = self._run(report_path)

        self.assertEqual(exit_code, 2, payload)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "DIAGRAM_SOURCE_ABSENT")

    def test_an_unparseable_visual_report_refuses_diagram_source_absent(self) -> None:
        report_path = self.test_root / "malformed.json"
        report_path.write_text("not json{", encoding="utf-8")

        exit_code, payload = self._run(report_path)

        self.assertEqual(exit_code, 2, payload)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "DIAGRAM_SOURCE_ABSENT")

    def test_a_visual_report_outside_the_repository_refuses(self) -> None:
        # Threat Matrix, "Path containment of the caller-supplied
        # operand": `../../tmp/x.json`-shaped in spirit -- any path
        # `_resolve_repo_path` cannot make relative to `FORGE_ROOT`.
        outside = (
            Path(tempfile.gettempdir())
            / f"figure-audit-visual-report-outside-{os.getpid()}.json"
        )
        outside.write_text(json.dumps(figure_dimensions.default_visual()), encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)

        exit_code, payload = self._run(outside)

        self.assertEqual(exit_code, 2, payload)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "PAPER_OUTSIDE_REPOSITORY")

    def test_a_symlink_escaping_the_repository_tree_refuses(self) -> None:
        # Threat Matrix, same row: a symlink INSIDE the repo whose target
        # resolves outside it -- `_resolve_repo_path`'s `Path(raw).
        # resolve()` follows the symlink before the containment check, so
        # this is not distinguishable from the plain outside-path case
        # above at the code level, and this test proves that directly.
        outside = (
            Path(tempfile.gettempdir())
            / f"figure-audit-visual-report-symlink-target-{os.getpid()}.json"
        )
        outside.write_text(json.dumps(figure_dimensions.default_visual()), encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        symlink_path = self.test_root / "visual-report-symlink.json"
        symlink_path.symlink_to(outside)

        exit_code, payload = self._run(symlink_path)

        self.assertEqual(exit_code, 2, payload)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "PAPER_OUTSIDE_REPOSITORY")

    def test_a_visual_failure_alongside_a_semantic_pass_leaves_the_cli_verdict_at_pass(self) -> None:
        # Lock 4, CLI-level confirmation of task 3.4's schema-level
        # isolation (`VisualVerdictIsolationTests` in
        # `tests/test_paper_figure_audit.py`). A custom one-block, one-
        # section corpus under `.scratch/` (never the shipped `sections/`
        # tree) whose prose deliberately agrees with the manifest, so the
        # semantic verdict is a real, reached `pass` rather than an
        # `unmeasured` that would make this assertion vacuous.
        self.manifest.write_text(json.dumps({"components": ["alpha"]}), encoding="utf-8")
        sections_dir = self.test_root / "sections"
        sections_dir.mkdir()
        header = {
            "section": "join-demo", "position": 1,
            "blocks": [{
                "id": "only", "requires_facts": [], "requires_declarations": [], "citations": "none",
            }],
        }
        (sections_dir / "01-join-demo.md").write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8")
            + b"\n---\n\nThe pipeline is described here: alpha.\n"
        )
        visual = figure_dimensions.default_visual()
        visual["dimensions"]["overlap"] = {
            "verdict": "fail", "reason": None,
            "collisions": [{"pixel": [[0, 0], [1, 1]], "point": [[0.0, 0.0], [0.48, 0.48]]}],
        }
        report_path = self.test_root / "visual-report.json"
        report_path.write_text(json.dumps(visual), encoding="utf-8")

        exit_code, payload = self._run(
            report_path, sections=str(sections_dir), section="join-demo",
        )

        self.assertEqual(exit_code, 0, payload)
        # The semantic half reached a real `pass` (components=["alpha"]
        # matches the prose), independently of the visual `fail` above --
        # the mutation this lock must survive is letting `visual` set this
        # value.
        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual(payload["visual"]["dimensions"]["overlap"]["verdict"], "fail")


class VisualPassRepairBudgetLedgerIsolationTests(unittest.TestCase):
    """Lock 5 (design.md lock table), task 4.5, full end-to-end
    confirmation in BOTH directions: a full successful visual pass
    (`raster` -> `measure` -> `figure audit --visual-report`) and a fully
    failing rasterizer chain each leave `render`'s repair-budget ledger
    byte-identical and its `attemptsUsed` count unchanged (`figure-raster`
    spec, `Requirement: Consumes an Already-Compiled PDF, Compiles
    Nothing`). The mutation this lock must survive: a single `_write_
    ledger` call added anywhere on the visual path -- proven caught, by
    hand, during implementation (see apply-progress); `figure-review`'s
    own scripts already prove they contain no such call
    (`RepairBudgetIsolationTests`, `tests/test_figure_review.py`)."""

    #: A syntactically minimal, real, decodable 8-bit RGBA 1x1 PNG (the
    #: same bytes `tests/test_cli_paper_e2e.py` already uses for its own
    #: stubbed figure file) -- sufficient for `png_read.py` to decode and
    #: `geometry.py` to measure; this class proves LEDGER isolation, not
    #: geometry, so no committed capture is needed here.
    _FAKE_PNG = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".figure-audit-ledger-isolation-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.paper_dir = self.test_root / "paper"
        self.figure_id = "ledger-isolation"
        figures_dir = self.paper_dir / "Figures"
        figures_dir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        (figures_dir / f"{self.figure_id}.tex").write_text("% node: box\n", encoding="utf-8")
        (figures_dir / f"{self.figure_id}.diagram.json").write_text(
            json.dumps({"components": ["box"]}), encoding="utf-8",
        )
        self.bin_dir = self.test_root / "latexmk-bin"
        _install_stub_latexmk(self.bin_dir)
        os.environ["STUB_RECORD_PATH"] = str(self.test_root / "record.jsonl")
        self.addCleanup(os.environ.pop, "STUB_RECORD_PATH", None)
        self.addCleanup(os.environ.pop, "STUB_MODE", None)

        # An "existing repair ledger": two ordinary repairable failures,
        # well under `REPAIR_BUDGET` -- `render`'s own `_write_ledger`
        # call, never anything this phase adds.
        os.environ["STUB_MODE"] = "failure_error"
        for _ in range(2):
            paper_figure.render(self.paper_dir, self.figure_id, path=str(self.bin_dir))
        # A clean compile leaves a compiled `<id>.pdf` beside that ledger
        # WITHOUT growing it -- `render`'s success path returns early,
        # before `_write_ledger` is ever reached (`paper_figure.py`).
        os.environ["STUB_MODE"] = "success"
        paper_figure.render(self.paper_dir, self.figure_id, path=str(self.bin_dir))

        self.paths = paper_figure.figure_paths(self.paper_dir, self.figure_id)
        self.assertTrue(self.paths["ledger"].is_file(), "setup must leave an existing ledger")
        self.ledger_before = self.paths["ledger"].read_bytes()
        self.attempts_before = json.loads(self.ledger_before)["attempts"]
        self.assertEqual(len(self.attempts_before), 2)

    def _visual_report_via_a_real_raster_and_measure_pass(self) -> Path:
        """Runs `figure-review`'s own `raster` then `measure` over an
        injected `PATH` stub -- never a real rasterizer, the same tier
        the skill's own suite uses -- and writes the resulting plain-data
        `visual-report.json` under this test's own `.scratch/` tree."""
        stub_body = (
            "import sys\nfrom pathlib import Path\n\n"
            "argv = sys.argv\n"
            "prefix = argv[-1]\n"
            f"Path(prefix + '-1.png').write_bytes(bytes.fromhex({self._FAKE_PNG.hex()!r}))\n"
        )
        raster_bin = self.test_root / "raster-bin"
        raster_bin.mkdir()
        stub_path = raster_bin / "pdftoppm"
        stub_path.write_text(f"#!{sys.executable}\n{stub_body}", encoding="utf-8")
        stub_path.chmod(0o755)

        raster_result = figure_review_raster.rasterize(
            self.paths["pdf"], self.test_root / "raster-scratch", path=str(raster_bin),
        )
        visual = figure_review_findings.measure_figure(Path(raster_result["png"]), raster_result)
        report_path = self.test_root / "visual-report.json"
        report_path.write_text(json.dumps(visual), encoding="utf-8")
        return report_path

    def test_a_full_successful_visual_pass_leaves_the_ledger_byte_identical(self) -> None:
        report_path = self._visual_report_via_a_real_raster_and_measure_pass()

        with contextlib.redirect_stdout(io.StringIO()) as buf:
            exit_code = paper_cli.main([
                "figure", "audit", "--paper", str(self.paper_dir), "--figure-id", self.figure_id,
                "--section", "introduction", "--visual-report", str(report_path),
            ])
        payload = json.loads(buf.getvalue())

        self.assertEqual(exit_code, 0, payload)
        self.assertIn("visual", payload)
        # `--figure-id` mode also persists the report to `figure_audit.json`
        # in the id's own scratch dir (`paper_cli.py`); the persisted
        # artifact carries the same join, not only the stdout payload.
        persisted = json.loads((self.paths["scratch"] / "figure_audit.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["visual"], payload["visual"])

        ledger_after = self.paths["ledger"].read_bytes()
        self.assertEqual(ledger_after, self.ledger_before)
        self.assertEqual(json.loads(ledger_after)["attempts"], self.attempts_before)

    def test_a_fully_failing_rasterizer_chain_also_leaves_the_ledger_byte_identical(self) -> None:
        # `out_dir` is deliberately THIS id's own real scratch directory
        # (`self.paths["scratch"]`, the same one `figure_paths` derives
        # `paths["ledger"]` from: `scratch_dir / "ledger.json"`) -- never a
        # throwaway path -- so a mutation that plants a ledger write on
        # this failure branch would land on the exact file this test's
        # own assertions read, making the mutation observable here rather
        # than merely absent from an unrelated directory.
        with self.assertRaises(Refused) as ctx:
            figure_review_raster.rasterize(
                self.paths["pdf"], self.paths["scratch"], path="",
            )
        self.assertEqual(ctx.exception.code, "RASTER_TOOLCHAIN_ABSENT")

        ledger_after = self.paths["ledger"].read_bytes()
        self.assertEqual(ledger_after, self.ledger_before)
        self.assertEqual(json.loads(ledger_after)["attempts"], self.attempts_before)


class MutationProofTests(unittest.TestCase):
    """Independent byte-identity verification, executed rather than
    asserted in prose. Each mutation below runs against a real subprocess
    and the corresponding guard test's own exit code is read, not guessed
    at.

    Every assertion below is two-part on purpose. `MUTANT_IMPORTED_OK` in
    stdout proves the mutant module actually loaded and `unittest` actually
    ran the named test against it; without that check, a subprocess that
    crashed on import (before the named test ever ran) and a subprocess
    where the guard genuinely failed are the same non-zero exit code, and
    this harness would be proving nothing about the mutation at all — the
    exact failure mode measured once already (`@dataclass` field-type
    resolution needs the mutant registered in `sys.modules` under its own
    `__name__`, not only under `'paper_block'`).
    """

    def _assert_guard_failed_under_mutation(self, proc: subprocess.CompletedProcess) -> None:
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_m1_region_start_one_byte_earlier_fails_the_byte_identity_test(self) -> None:
        # Mutates the WRITE path (`build_candidate`'s own slicing), not the
        # independent verification (`project()`, left untouched). A shift
        # applied symmetrically inside `project()` alone is invisible by
        # construction -- both sides of the comparison would be blind to the
        # exact same swallowed byte, and this was measured, not assumed: an
        # earlier version of this test mutated `project()`'s region list
        # instead and passed green with no guard ever firing. Shifting the
        # boundary actually used to slice `pre` when building the candidate
        # drops one real byte from what reaches disk, which the UNMUTATED,
        # independently re-parsing `project()` then genuinely disagrees
        # about.
        proc = _run_against_mutant(
            'candidate = pre[:begin["start"]] + new_begin_line + written_body + pre[end["start"]:]',
            'candidate = pre[:begin["start"] - 1] + new_begin_line + written_body + pre[end["start"]:]',
            "tests.test_paper_writing.InvariantTests.test_only_the_named_block_changes_three_conjuncts",
        )

        self._assert_guard_failed_under_mutation(proc)

    def test_m2_text_mode_open_against_crlf_fixture_fails_the_byte_identity_test(self) -> None:
        # `newline=None` universal-newlines mode, opened via the builtin
        # `open()` -- matching the CRLFTests fixture's own control assertion
        # exactly, so this exercises the real CRLF-flattening semantics the
        # spec's M2 names, not an unrelated crash from a keyword argument
        # `Path.read_text()` does not accept on this interpreter.
        #
        # For THIS fixture specifically, the guard that actually fires first
        # is `BLOCK_HAND_EDITED`, not `SUBSTITUTION_NOT_LOCAL`: the target
        # block's own body also carries CRLF, so flattening corrupts its
        # on-disk digest before the in-memory byte-identity check ever runs.
        # A fixture whose block body carried no CRLF would instead reach
        # `identity_invariant` and fail there -- both are real guards inside
        # the same safety net (design.md, "Guards that protect but are not
        # net layers"), and either one refusing is the property this test
        # proves: text-mode corruption never reaches disk.
        proc = _run_against_mutant(
            'pre = tex_path.read_bytes()\n    pre_digest = hashlib.sha256(pre).hexdigest()\n\n'
            '    parsed = parse(pre)\n    candidate, written_body = build_candidate(',
            'with open(tex_path, "r", newline=None) as _h:\n'
            '        pre = _h.read().encode("utf-8")\n'
            '    pre_digest = hashlib.sha256(pre).hexdigest()\n\n'
            '    parsed = parse(pre)\n    candidate, written_body = build_candidate(',
            "tests.test_paper_writing.CRLFTests"
            ".test_crlf_block_round_trips_untouched_and_text_mode_would_corrupt_it",
        )

        self._assert_guard_failed_under_mutation(proc)

    def test_m3_skipped_digest_comparison_fails_the_hand_edit_guard(self) -> None:
        proc = _run_against_mutant(
            'if on_disk_digest != begin["digest"]:',
            "if False:",
            "tests.test_paper_writing.BlockCoreTests.test_hand_edited_body_refuses_naming_both_digests",
        )

        self._assert_guard_failed_under_mutation(proc)


# =====================================================================
# the-writer-may-assert-only-what-it-was-given -- Work Unit 1
# =====================================================================


class ModeWideningTests(unittest.TestCase):
    """`section-contract` spec delta: `mode` joins `_TOP_LEVEL_OPTIONAL`/
    `_BLOCK_OPTIONAL`."""

    def _header(self, *, section_mode=None, block_mode=None) -> dict:
        header = {
            "section": "demo", "position": 1,
            "blocks": [{
                "id": "b1", "requires_facts": [], "requires_declarations": [],
                "citations": "none",
            }],
        }
        if section_mode is not None:
            header["mode"] = section_mode
        if block_mode is not None:
            header["blocks"][0]["mode"] = block_mode
        return header

    def _mode_obj(self, value: str) -> dict:
        return {"value": value, "source": {"file": "demo.md", "quote": "some prose"}}

    def test_a_valid_mode_value_parses(self) -> None:
        header = paper_contract.parse_header(self._header(block_mode=self._mode_obj("transposition")))
        self.assertEqual(header.blocks[0]["mode"]["value"], "transposition")

    def test_an_invalid_mode_value_refuses_unknown_mode(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(block_mode=self._mode_obj("exposition")))
        self.assertEqual(ctx.exception.code, "UNKNOWN_MODE")
        self.assertIn("exposition", ctx.exception.detail)

    def test_a_block_inherits_the_section_level_mode(self) -> None:
        header = paper_contract.parse_header(self._header(section_mode=self._mode_obj("argument")))
        resolved = paper_contract.resolve_mode(header, header.blocks[0])
        self.assertEqual(resolved["value"], "argument")

    def test_a_blocks_own_mode_overrides_the_section_level_default(self) -> None:
        header = paper_contract.parse_header(self._header(
            section_mode=self._mode_obj("argument"), block_mode=self._mode_obj("transposition"),
        ))
        resolved = paper_contract.resolve_mode(header, header.blocks[0])
        self.assertEqual(resolved["value"], "transposition")

    def test_neither_level_declaring_mode_resolves_to_none(self) -> None:
        header = paper_contract.parse_header(self._header())
        self.assertIsNone(paper_contract.resolve_mode(header, header.blocks[0]))

    #: `Headers Written Before mode Existed`: an absent `mode` at both
    #: levels is schema-valid, never a violation -- `write`'s own
    #: readiness stage is what refuses on it
    #: (`WritingPipelineTests.test_no_mode_resolved_refuses_mode_absent`),
    #: never this reader. All ten shipped contracts now carry a quotable
    #: mode-bearing sentence: `02-experimental-setup.md`,
    #: `04-limitations.md` and `05-related-work.md` initially shipped with
    #: none declared, and a later corrective batch authored the missing
    #: sentence for each. The synthetic, no-real-file-required case (neither
    #: level declaring `mode` still parses and resolves to `None`) is
    #: covered above by `test_neither_level_declaring_mode_resolves_to_none`
    #: and, for the corpus-walk's own None-skipping branch, by
    #: `test_paper_contract.ModeTranscriptionTests.
    #: test_undeclared_sections_are_absent_not_silently_passing`.

    def test_shipped_contracts_declaring_mode_resolve_it_at_every_block(self) -> None:
        for path in sorted(SECTIONS_DIR.glob("*.md")):
            header, _body = paper_contract.parse(path.read_bytes())
            self.assertIsNotNone(header.mode, path.name)
            self.assertIn(header.mode["value"], paper_vocabulary.MODES, path.name)
            self.assertEqual(header.mode["source"]["file"], f"sections/{path.name}")
            for block in header.blocks:
                resolved = paper_contract.resolve_mode(header, block)
                self.assertIsNotNone(resolved, (path.name, block["id"]))


class ModeVocabularyConstantsTests(unittest.TestCase):
    """`transposition-fidelity` spec, `Requirement: Only A Transposition-Mode
    Block Is Checked...` (design.md, Decision D; tasks.md 2.5-2.6): `MODES`
    stops being a bare literal tuple and is composed from two named
    constants, so no string literal for a mode needs to be spelled again in
    `paper_write.py`/`paper_leak.py`."""

    def test_named_mode_constants_hold_their_string_values(self) -> None:
        self.assertEqual(paper_vocabulary.MODE_TRANSPOSITION, "transposition")
        self.assertEqual(paper_vocabulary.MODE_ARGUMENT, "argument")

    def test_modes_is_composed_from_the_named_constants(self) -> None:
        self.assertEqual(
            paper_vocabulary.MODES,
            (paper_vocabulary.MODE_TRANSPOSITION, paper_vocabulary.MODE_ARGUMENT),
        )


class RequirementEntryShapeTests(unittest.TestCase):
    """`the-requirement-names-the-sentence-that-demands-it` — Work Units U1
    and U3. `section-contract` spec delta, `Requirement: Front Matter
    Schema`; `requirement-transcription` spec, `Requirement: Transcribed
    Requirement Entries Only`. U3 (design.md D3) removes bare-string
    acceptance and makes a non-null `source` unconditional — every test
    here proves the SHAPE layer alone, with no quote ever checked against
    a body at this layer (design.md D2: "`paper_contract` validates shape
    only"); the corpus-wide quote gate is `RequirementTranscriptionGateTests`,
    below."""

    def _header(self, *, fact=None, declaration=None) -> dict:
        block = {
            "id": "b1",
            "requires_facts": [fact] if fact is not None else [],
            "requires_declarations": [declaration] if declaration is not None else [],
            "citations": "none",
        }
        return {"section": "demo", "position": 1, "blocks": [block]}

    def _rich(self, value: str, *, file: str = "demo.md", quote: str = "some prose") -> dict:
        return {"value": value, "source": {"file": file, "quote": quote}}

    def test_a_bare_fact_string_now_refuses_malformed_header(self) -> None:
        """U3 (design.md D3): bare-string acceptance is removed. This is
        the decisive proof the half-migrated state is structurally
        UNREPRESENTABLE, not merely detected — a fixture (or a shipped
        contract) rebuilt with a bare string now refuses at parse, before
        the corpus-wide quote gate (`paper_graph.assemble_corpus`) ever
        gets a chance to run."""
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(fact="contributions"))
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")

    def test_a_bare_declaration_string_now_refuses_malformed_header(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(declaration="author-roles"))
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")

    def test_reparsing_a_rich_entrys_own_output_is_a_fixed_point(self) -> None:
        """U3's parser output always carries a dict with a populated,
        validated `source` (design.md, "Round-trip holds throughout"):
        feeding that output back in as the raw entry MUST normalize to
        the identical shape."""
        once = paper_contract.parse_header(
            self._header(fact=self._rich("contributions", file="06-introduction.md", quote="Prose."))
        )
        normalized_entry = once.blocks[0]["requires_facts"][0]
        twice = paper_contract.parse_header(self._header(fact=normalized_entry))
        self.assertEqual(twice.blocks[0]["requires_facts"], once.blocks[0]["requires_facts"])

    def test_a_rich_fact_entry_parses_and_carries_its_source(self) -> None:
        header = paper_contract.parse_header(
            self._header(fact=self._rich("contributions", file="06-introduction.md", quote="Prose."))
        )
        self.assertEqual(
            header.blocks[0]["requires_facts"],
            [{"value": "contributions", "source": {"file": "06-introduction.md", "quote": "Prose."}}],
        )

    def test_a_rich_entry_with_an_explicit_null_source_now_refuses(self) -> None:
        """U1/U2's `source: null` round-trip convention was how an
        untranscribed bare entry re-serialized. U3 (design.md D3) makes a
        non-null `source` unconditional, so an explicit `null` now refuses
        exactly like an absent key — never a silently-accepted value."""
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(fact={"value": "contributions", "source": None}))
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("source", ctx.exception.detail)

    def test_a_rich_entry_missing_source_refuses_malformed_header_naming_source(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(fact={"value": "contributions"}))
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("source", ctx.exception.detail)

    def test_a_rich_entry_with_an_unknown_key_refuses_malformed_header_naming_it(self) -> None:
        broken = dict(self._rich("contributions"), extra_key="nope")
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(fact=broken))
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("extra_key", ctx.exception.detail)

    def test_a_rich_entry_with_a_non_string_value_refuses_malformed_header(self) -> None:
        """Mirrors `_validate_mode_object`'s own `mode.value` check."""
        broken = dict(self._rich("contributions"), value=42)
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(fact=broken))
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")

    def test_a_rich_entry_with_a_non_object_source_refuses_malformed_header(self) -> None:
        broken = dict(self._rich("contributions"), source="not-an-object")
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(fact=broken))
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")

    def test_a_bare_unknown_fact_string_refuses_malformed_header_not_unknown_fact(self) -> None:
        """U3: the shape check (entry must be an object) runs before
        vocabulary validation, so a bare string — known or unknown fact —
        always refuses `MALFORMED_HEADER` first."""
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(fact="not-a-real-fact"))
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")

    def test_an_unknown_rich_facts_value_still_refuses_unknown_fact(self) -> None:
        """Task 1.11: `UNKNOWN_FACT` keeps firing, now reading
        `entry["value"]` rather than a bare string."""
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(fact=self._rich("not-a-real-fact")))
        self.assertEqual(ctx.exception.code, "UNKNOWN_FACT")

    def test_a_bare_unknown_declaration_string_refuses_malformed_header_not_unknown_declaration(
        self,
    ) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(declaration="not-a-real-declaration"))
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")

    def test_an_unknown_rich_declarations_value_still_refuses_unknown_declaration(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(
                self._header(declaration=self._rich("not-a-real-declaration"))
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_DECLARATION")

    def test_requirement_values_derives_the_plain_tuple_in_declaration_order(self) -> None:
        entries = [
            self._rich("contributions", file="demo.md", quote="Prose."),
            self._rich("dataset", file="06-introduction.md", quote="Prose."),
        ]
        self.assertEqual(paper_contract.requirement_values(entries), ("contributions", "dataset"))

    def test_block_record_derives_plain_tuples_from_the_real_shipped_corpus(self) -> None:
        """`requirement-transcription` spec, `Requirement: Derived Plain
        Tuple For Downstream Consumers`: `BlockRecord.requires_facts` /
        `.requires_declarations` stay plain tuples of ids over the real
        corpus, with no rich shape leaking through — proven against
        `sections/*.md` as shipped today, every entry now fully
        transcribed (U3's operator ruling applied)."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        for record in corpus.blocks.values():
            for value in record.requires_facts:
                self.assertIsInstance(value, str)
            for value in record.requires_declarations:
                self.assertIsInstance(value, str)


#: The legitimate derivation points a parsed block's `["requires_facts"]` /
#: `["requires_declarations"]` may be subscripted as a direct argument to —
#: `requirement_values` (design.md D1) and, since `the-requirement-names-
#: the-section-that-feeds-it`, `requirement_documents` (its own mirror,
#: `paper_graph.BlockRecord.source_bindings`'s sole construction site).
_REQUIREMENT_SUBSCRIPT_ALLOWED_FUNCS = ("requirement_values", "requirement_documents")


def _requirement_subscript_violations(root: Path) -> dict:
    """AST scan (design.md D1): no module OTHER than `paper_contract.py`
    may subscript `["requires_facts"]` / `["requires_declarations"]` on a
    parsed block dict except as a direct argument to
    `paper_contract.requirement_values(...)` or `paper_contract.
    requirement_documents(...)` — the two legitimate derivation points.
    `paper_contract.py` is exempt: it is where the dict is BUILT
    (`_parse_block`'s own `raw["requires_facts"]`), never read back through
    the accessors it defines.

    Every `ast.Subscript` node whose slice is a string constant equal to
    one of the two target keys is a candidate; it is excluded only when it
    sits (anywhere in its own subtree) inside the argument list of a call
    whose `func` is an `ast.Attribute` named one of
    `_REQUIREMENT_SUBSCRIPT_ALLOWED_FUNCS` — the exact shape every real
    call site (`paper_graph.py`, `paper_cli.py`) uses:
    `paper_contract.requirement_values(raw_block["requires_facts"])`.
    """
    target_keys = {"requires_facts", "requires_declarations"}
    violations: dict = {}
    for path in sorted(root.glob("*.py")):
        if path.name == "paper_contract.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed_ids: set = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _REQUIREMENT_SUBSCRIPT_ALLOWED_FUNCS
            ):
                for arg in node.args:
                    for sub in ast.walk(arg):
                        allowed_ids.add(id(sub))
        found: list = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            key_node = node.slice
            if isinstance(key_node, ast.Constant) and key_node.value in target_keys:
                if id(node) not in allowed_ids:
                    found.append(key_node.value)
        if found:
            violations[path.name] = found
    return violations


class RequirementSubscriptSingleDerivationTests(unittest.TestCase):
    """design.md D1: "A second path is made unreachable by an AST test
    over `scripts/*.py`: no module outside `paper_contract` may subscript
    `["requires_facts"]` / `["requires_declarations"]` on a parsed block
    dict except through" `requirement_values`. Two representations can
    drift only if a second construction path exists; this guard makes
    that path structurally unreachable rather than merely convention."""

    def test_no_shipped_script_outside_paper_contract_subscripts_the_two_keys_directly(
        self,
    ) -> None:
        self.assertEqual(_requirement_subscript_violations(SKILL_SCRIPTS), {})

    def test_a_planted_direct_subscript_is_caught(self) -> None:
        """Mutation proof: a synthetic module reading
        `block["requires_facts"]` OUTSIDE a `requirement_values(...)` call
        is exactly the second derivation path this guard exists to make
        unreachable. Planted in a temp directory rather than the shipped
        tree, since mutating the REAL construction sites would break
        every other test in this suite that assembles the corpus."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / "evil.py").write_text(
                'def f(block):\n    return tuple(block["requires_facts"])\n',
                encoding="utf-8",
            )
            violations = _requirement_subscript_violations(tmp_dir)
        self.assertIn("evil.py", violations)
        self.assertIn("requires_facts", violations["evil.py"])

    def test_a_direct_argument_to_requirement_values_is_not_flagged(self) -> None:
        """The two REAL call sites this accessor exists for
        (`paper_graph.py`'s `BlockRecord` construction, `paper_cli.py`'s
        `BlockContract` construction) both subscript the raw dict AS the
        argument to `paper_contract.requirement_values(...)` — proving the
        scanner recognizes that shape as the single legitimate derivation
        point, not a false positive the shipped-tree test above would
        otherwise silently hide."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / "good.py").write_text(
                "import paper_contract\n\n\n"
                "def f(block):\n"
                '    return paper_contract.requirement_values(block["requires_facts"])\n',
                encoding="utf-8",
            )
            violations = _requirement_subscript_violations(tmp_dir)
        self.assertEqual(violations, {})

    def test_paper_contract_py_itself_is_exempt_from_the_scan(self) -> None:
        """`paper_contract.py` DOES subscript both keys directly today
        (`_parse_block`'s own `raw["requires_facts"]` /
        `raw["requires_declarations"]`) — proving the exemption is real,
        not vacuous: a scan that failed to exempt it would fail on the
        shipped tree for the wrong reason."""
        contract_source = (SKILL_SCRIPTS / "paper_contract.py").read_text(encoding="utf-8")
        self.assertIn('raw["requires_facts"]', contract_source)
        violations = _requirement_subscript_violations(SKILL_SCRIPTS)
        self.assertNotIn("paper_contract.py", violations)


class RequirementTranscriptionGateTests(unittest.TestCase):
    """`the-requirement-names-the-sentence-that-demands-it` — Work Unit U3.
    `requirement-transcription` spec, `Requirement: Transcribed
    Requirement Entries Only`: `paper_graph._verify_requirement_
    transcription`, wired unconditionally into `assemble_corpus`. Mirrors
    `_verify_after_transcription`'s own self-file / cross-file / refusal
    tests (design.md, Testing Strategy)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def _write(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def test_an_unbacked_quote_refuses_span_not_in_source(self) -> None:
        self._write(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [{
                        "value": "dataset",
                        "source": {"file": "sections/01-a.md", "quote": "Never written anywhere."},
                    }],
                    "requires_declarations": [], "citations": "none",
                }],
            },
            "Prose that never mentions the dataset at all.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SPAN_NOT_IN_SOURCE")
        self.assertIn("a.only", ctx.exception.detail)

    def test_a_cross_file_quote_verifies(self) -> None:
        """Mirrors the shipped `abstract.slot-2` / `06-introduction.md`
        precedent: `source.file` names a DIFFERENT contract than the one
        declaring the entry, and the quote is checked against THAT file's
        own body, not the declaring block's."""
        self._write(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [{
                        "value": "dataset",
                        "source": {
                            "file": "sections/02-b.md",
                            "quote": "The dataset lives over here instead.",
                        },
                    }],
                    "requires_declarations": [], "citations": "none",
                }],
            },
            "Prose that never mentions the dataset.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )
        self._write(
            "02-b.md",
            {"section": "b", "position": 2, "blocks": [
                {"id": "only", "requires_facts": [], "requires_declarations": [], "citations": "none"},
            ]},
            "The dataset lives over here instead.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertIn("a.only", corpus.blocks)

    def test_a_typod_cross_file_quote_refuses(self) -> None:
        self._write(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [{
                        "value": "dataset",
                        "source": {
                            "file": "sections/02-b.md",
                            "quote": "The dataset lives ovar here instead.",
                        },
                    }],
                    "requires_declarations": [], "citations": "none",
                }],
            },
            "Prose that never mentions the dataset.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )
        self._write(
            "02-b.md",
            {"section": "b", "position": 2, "blocks": [
                {"id": "only", "requires_facts": [], "requires_declarations": [], "citations": "none"},
            ]},
            "The dataset lives over here instead.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SPAN_NOT_IN_SOURCE")

    def test_a_produces_facts_entry_verifies(self) -> None:
        """`fact-production` spec, `Requirement: Transcribed produces_facts
        Entries Only`: the block-level half of the widened tuple
        (design.md, Decision B: 'adding one member to its own tuple')."""
        self._write(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [], "requires_declarations": [], "citations": "none",
                    "produces_facts": [{
                        "value": "gap",
                        "source": {"file": "sections/01-a.md", "quote": "The gap itself, written here."},
                    }],
                }],
            },
            "The gap itself, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.blocks["a.only"].produces_facts, ("gap",))

    def test_an_unbacked_produces_facts_quote_refuses_span_not_in_source(self) -> None:
        self._write(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [], "requires_declarations": [], "citations": "none",
                    "produces_facts": [{
                        "value": "gap",
                        "source": {"file": "sections/01-a.md", "quote": "Never written anywhere."},
                    }],
                }],
            },
            "Prose that never mentions the gap at all.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SPAN_NOT_IN_SOURCE")
        self.assertIn("a.only", ctx.exception.detail)

    def test_an_unbacked_section_level_produces_facts_quote_refuses_span_not_in_source(self) -> None:
        """The section-level half of `produces_facts` (`ContractHeader.
        produces_facts`, design.md Decision B: 'the section-level list the
        same way') — walked separately from the block-level tuple, the same
        shape `_verify_mode_transcription` already walks `header.mode`
        apart from block `mode` entries."""
        self._write(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "produces_facts": [{
                    "value": "limitations",
                    "source": {"file": "sections/01-a.md", "quote": "Never written anywhere."},
                }],
                "blocks": [{
                    "id": "only",
                    "requires_facts": [], "requires_declarations": [], "citations": "none",
                }],
            },
            "Prose that never mentions the limits at all.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SPAN_NOT_IN_SOURCE")
        self.assertIn("a", ctx.exception.detail)


class SourceBindingsFieldTests(unittest.TestCase):
    """`the-requirement-names-the-section-that-feeds-it`, U1 (design.md,
    Interfaces): `BlockRecord.source_bindings` is a tuple of `(fact_id,
    lineage, section_title)` triples, derived from `paper_contract.
    requirement_documents` at `assemble_corpus` time -- inert at this
    phase, since resolution against real disk (`SOURCE_LINEAGE_UNRESOLVED`,
    `SECTION_NOT_IN_SOURCE`, etc.) is U2/U3's own concern."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def _write(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def test_a_document_bound_entry_populates_source_bindings(self) -> None:
        self._write(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [{
                        "value": "formulation",
                        "source": {
                            "file": "sections/01-a.md",
                            "quote": "The formulation, written here.",
                        },
                        "document": {
                            "lineage": "lumen-thesis", "section": "3. Something",
                        },
                    }],
                    "requires_declarations": [], "citations": "none",
                }],
            },
            "The formulation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing -- U1 is inert

        self.assertEqual(
            corpus.blocks["a.only"].source_bindings,
            (("formulation", "lumen-thesis", "3. Something"),),
        )

    def test_an_unbound_entry_leaves_source_bindings_empty(self) -> None:
        self._write(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [{
                        "value": "formulation",
                        "source": {
                            "file": "sections/01-a.md",
                            "quote": "The formulation, written here.",
                        },
                    }],
                    "requires_declarations": [], "citations": "none",
                }],
            },
            "The formulation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(corpus.blocks["a.only"].source_bindings, ())


class PaperMarkerSealTests(unittest.TestCase):
    """`specs/source-declaration-authoring/spec.md`, `Requirement: A
    Declaration Is Sealed Against An Unaware Edit, At Exactly Its Real
    Strength` -- the shared seal convention itself (design.md Decision B),
    independent of either marker's own grammar."""

    def test_identical_input_produces_an_identical_digest_across_two_calls(self) -> None:
        """Canonicalization stability: `sort_keys=True` is load-bearing, the
        same reason `paper_region.serialize_body` documents its own."""
        obj = {"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}

        first = paper_marker.computed_seal(obj)
        second = paper_marker.computed_seal(dict(obj))

        self.assertEqual(first, second)

    def test_the_digest_excludes_the_seal_key_itself_from_its_own_input(self) -> None:
        obj = {"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}
        seal = paper_marker.computed_seal(obj)
        with_seal = {**obj, paper_marker.SEAL_KEY: seal}

        self.assertEqual(paper_marker.computed_seal(with_seal), seal)

    def test_canonical_bytes_ignores_key_order(self) -> None:
        first = {"b": 1, "a": 2}
        second = {"a": 2, "b": 1}

        self.assertEqual(paper_marker.canonical_bytes(first), paper_marker.canonical_bytes(second))

    def test_is_sealed_true_iff_the_seal_key_is_present(self) -> None:
        self.assertFalse(paper_marker.is_sealed({"revisions": {}}))
        self.assertTrue(paper_marker.is_sealed({"revisions": {}, paper_marker.SEAL_KEY: "x"}))

    def test_seal_shape_error_none_when_absent(self) -> None:
        self.assertIsNone(paper_marker.seal_shape_error({"revisions": {}}))

    def test_seal_shape_error_none_when_a_valid_64_hex_string(self) -> None:
        obj = {"revisions": {}, paper_marker.SEAL_KEY: "a" * 64}

        self.assertIsNone(paper_marker.seal_shape_error(obj))

    def test_seal_shape_error_detail_when_wrong_length(self) -> None:
        obj = {"revisions": {}, paper_marker.SEAL_KEY: "a" * 63}

        detail = paper_marker.seal_shape_error(obj)

        self.assertIsNotNone(detail)
        self.assertIn(paper_marker.SEAL_KEY, detail)

    def test_seal_shape_error_detail_when_wrong_charset(self) -> None:
        obj = {"revisions": {}, paper_marker.SEAL_KEY: "g" * 64}

        self.assertIsNotNone(paper_marker.seal_shape_error(obj))

    def test_seal_shape_error_detail_when_not_a_string(self) -> None:
        obj = {"revisions": {}, paper_marker.SEAL_KEY: 12345}

        self.assertIsNotNone(paper_marker.seal_shape_error(obj))

    def test_write_sealed_sets_a_seal_matching_computed_seal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".paper-writing.json"
            obj = {"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}

            written = paper_marker.write(path, obj, sealed=True)

            self.assertEqual(written[paper_marker.SEAL_KEY], paper_marker.computed_seal(obj))
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk, written)

    def test_write_unsealed_carries_no_seal_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".paper-writing.json"
            obj = {"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}

            written = paper_marker.write(path, obj, sealed=False)

            self.assertNotIn(paper_marker.SEAL_KEY, written)
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn(paper_marker.SEAL_KEY, on_disk)

    def test_the_module_docstring_quotes_seal_strength_verbatim(self) -> None:
        source = (SKILL_SCRIPTS / "paper_marker.py").read_text(encoding="utf-8")

        self.assertIn(paper_marker.SEAL_STRENGTH, source)


class SealStrengthFourSurfaceTests(unittest.TestCase):
    """`specs/source-declaration-authoring/spec.md`, `Requirement: A
    Declaration Is Sealed Against An Unaware Edit, At Exactly Its Real
    Strength` (design.md Decision G); tasks.md 5.1/5.5/5.6. One test derives
    its expectation from `paper_marker.SEAL_STRENGTH` itself and asserts its
    byte-identical presence in every surface the requirement names — so
    weakening the claim in any one of them is a red test, never a review
    miss caught only by a human reading four separate files.

    `references/usage.md` is NOT a fifth surface here: `paper-writing` has
    no such file and never has (confirmed via `git ls-files`/`fd -H -I`,
    unlike four sibling skills the design's own precedent generalizes
    from — `2026-09-20-the-whole-cut-is-argued-before-any-section-is-
    claimed`'s own archive-report already ruled this for this exact skill).
    `SKILL.md` is `paper-writing`'s only documentation surface, so it alone
    stands in for design.md's "and `references/usage.md`" clause."""

    def test_seal_strength_appears_byte_identically_in_all_four_surfaces(self) -> None:
        strength = paper_marker.SEAL_STRENGTH

        # (a) the shared module's own docstring.
        marker_source = (SKILL_SCRIPTS / "paper_marker.py").read_text(encoding="utf-8")
        self.assertIn(strength, marker_source, "paper_marker.py module docstring")

        # (b) SOURCE_DECLARATION_HAND_EDITED's own refusal detail, reached
        # through the real reader every gating verb goes through — never a
        # separately hand-copied literal.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obj = {
                "revisions": {"revision_prefix": "r", "ordinal_digits": 2},
                paper_marker.SEAL_KEY: "a" * 64,
            }
            (root / ".paper-writing.json").write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaises(Refused) as ctx:
                paper_declarations.read_revisions_marker(root)
            self.assertEqual(ctx.exception.code, "SOURCE_DECLARATION_HAND_EDITED")
            self.assertIn(strength, ctx.exception.detail, "SOURCE_DECLARATION_HAND_EDITED detail")

        # (c) GUIDANCE_DECLARATION_HAND_EDITED's own refusal detail, reached
        # through `_classify` — the same shared reader `read_registry`/
        # `classify_source_md` already go through.
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "some-folder"
            folder.mkdir()
            obj = {"class": "evidence", paper_marker.SEAL_KEY: "a" * 64}
            (folder / ".paper-writing.json").write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaises(Refused) as ctx:
                paper_guidance.read_registry(folder.parent)
            self.assertEqual(ctx.exception.code, "GUIDANCE_DECLARATION_HAND_EDITED")
            self.assertIn(
                strength, ctx.exception.detail, "GUIDANCE_DECLARATION_HAND_EDITED detail",
            )

        # (d) `SKILL.md` -- this skill's only documentation surface.
        skill_md = (SKILL_SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(strength, skill_md, "SKILL.md")

    def test_mutation_weakening_seal_strength_reddens_the_four_surface_test(self) -> None:
        """tasks.md 5.6: weakening `SEAL_STRENGTH` to drop "not
        tamper-proofing" must turn the four-surface test red -- proving
        strengthening (or otherwise drifting) the claim anywhere is a red
        test, never a review miss a human has to notice by eye."""
        proc = _run_against_mutant(
            '"This seal detects an unaware edit. It is self-consistency, not "',
            '"This seal detects an unaware edit. It is self-consistency, "',
            "tests.test_paper_writing.SealStrengthFourSurfaceTests"
            ".test_seal_strength_appears_byte_identically_in_all_four_surfaces",
            source_path=SKILL_SCRIPTS / "paper_marker.py",
        )
        self.assertIn("MUTANT_IMPORTED_OK", proc.stdout + proc.stderr, proc.stdout + proc.stderr)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class SourceRevisionsMarkerGrammarTests(unittest.TestCase):
    """`source-section-binding` spec, `Requirement: The Marker Grammar Is
    Validated, And Disjoint From guidance/'s`: `paper_declarations.
    read_revisions_marker` -- UTF-8 JSON, exactly one top-level key
    (`revisions`), an object holding exactly `revision_prefix` (string) and
    `ordinal_digits` (integer), both required, no other key admitted at
    either level. `seal_sha256` MAY additionally be present at the top
    level (design.md Decision A/C) -- checked by this class too, once
    `paper_marker.py` exists to check it against."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _marker(self, text: str) -> None:
        (self.root / ".paper-writing.json").write_text(text, encoding="utf-8")

    def _assert_guard_failed_under_mutation(self, proc: subprocess.CompletedProcess) -> None:
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_an_absent_marker_reads_as_none(self) -> None:
        self.assertIsNone(paper_declarations.read_revisions_marker(self.root))

    def test_a_valid_marker_parses(self) -> None:
        self._marker('{"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}')

        marker = paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(
            marker, {"revision_prefix": "r", "ordinal_digits": 2, "sealed": False},
        )

    def test_an_unsealed_marker_accepts_exactly_as_before_sealing_existed(self) -> None:
        """`specs/source-declaration-authoring/spec.md`, `Requirement:
        Absence Is A Reported State...`, scenario `An unsealed marker on an
        existing checkout reports, not refuses`."""
        self._marker('{"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}')

        marker = paper_declarations.read_revisions_marker(self.root)

        self.assertFalse(marker["sealed"])

    def test_a_valid_sealed_marker_parses(self) -> None:
        obj = {"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}
        obj[paper_marker.SEAL_KEY] = paper_marker.computed_seal(obj)
        self._marker(json.dumps(obj))

        marker = paper_declarations.read_revisions_marker(self.root)

        self.assertTrue(marker["sealed"])
        self.assertEqual(marker["revision_prefix"], "r")
        self.assertEqual(marker["ordinal_digits"], 2)

    def test_a_malformed_seal_shape_refuses_as_malformed_not_hand_edited(self) -> None:
        self._marker(
            json.dumps({
                "revisions": {"revision_prefix": "r", "ordinal_digits": 2},
                paper_marker.SEAL_KEY: "not-a-hex-digest",
            })
        )

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn(paper_marker.SEAL_KEY, ctx.exception.detail)

    def test_a_mismatched_seal_refuses_hand_edited_naming_both_digests(self) -> None:
        obj = {"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}
        obj[paper_marker.SEAL_KEY] = "a" * 64  # never the real computed seal
        self._marker(json.dumps(obj))

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "SOURCE_DECLARATION_HAND_EDITED")
        self.assertIn("a" * 64, ctx.exception.detail)
        self.assertIn(paper_marker.computed_seal(obj), ctx.exception.detail)
        self.assertIn(paper_marker.SEAL_STRENGTH, ctx.exception.detail)

    def test_a_non_json_marker_refuses_malformed_source_marker(self) -> None:
        self._marker("{not valid json")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")

    def test_a_non_object_marker_refuses(self) -> None:
        self._marker("[1, 2, 3]")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")

    def test_a_non_utf8_marker_refuses(self) -> None:
        (self.root / ".paper-writing.json").write_bytes(b"\xff\xfe\x00\x01")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")

    def test_a_marker_missing_the_top_level_key_refuses_naming_revisions(self) -> None:
        self._marker('{"other": true}')

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn("revisions", ctx.exception.detail)

    def test_a_marker_with_an_unknown_top_level_key_refuses(self) -> None:
        self._marker(
            '{"revisions": {"revision_prefix": "r", "ordinal_digits": 2}, "extra": 1}'
        )

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn("extra", ctx.exception.detail)

    def test_a_marker_missing_revision_prefix_refuses_naming_it(self) -> None:
        self._marker('{"revisions": {"ordinal_digits": 2}}')

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn("revision_prefix", ctx.exception.detail)

    def test_a_marker_missing_ordinal_digits_refuses_naming_it(self) -> None:
        self._marker('{"revisions": {"revision_prefix": "r"}}')

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn("ordinal_digits", ctx.exception.detail)

    def test_a_marker_with_an_unknown_nested_key_refuses(self) -> None:
        self._marker(
            '{"revisions": {"revision_prefix": "r", "ordinal_digits": 2, "sixth": 1}}'
        )

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn("sixth", ctx.exception.detail)

    def test_a_marker_with_a_wrong_typed_ordinal_digits_refuses_naming_it(self) -> None:
        self._marker('{"revisions": {"revision_prefix": "r", "ordinal_digits": "2"}}')

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn("ordinal_digits", ctx.exception.detail)

    def test_a_marker_with_a_wrong_typed_revision_prefix_refuses_naming_it(self) -> None:
        self._marker('{"revisions": {"revision_prefix": 7, "ordinal_digits": 2}}')

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn("revision_prefix", ctx.exception.detail)

    def test_a_guidance_shaped_marker_refuses_naming_revisions_as_missing(self) -> None:
        """`Requirement: The Marker Grammar Is Validated, And Disjoint From
        guidance/'s`: `guidance/`'s own `{"class": "style-reference"}`
        shape MUST NOT be silently accepted by the source-root reader."""
        self._marker('{"class": "style-reference"}')

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_revisions_marker(self.root)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn("revisions", ctx.exception.detail)

    def test_mutation_a_sixth_key_in_the_marker_breaks_the_unknown_key_guard(self) -> None:
        proc = _run_against_mutant(
            'unknown = [key for key in obj if key != _SOURCE_MARKER_TOP_KEY]\n'
            '    if unknown:\n'
            '        raise Refused(\n'
            '            "MALFORMED_SOURCE_MARKER", f"{marker_path}: carries unknown key '
            '{unknown[0]!r}"\n'
            '        )\n',
            "",
            "tests.test_paper_writing.SourceRevisionsMarkerGrammarTests"
            ".test_a_marker_with_an_unknown_top_level_key_refuses",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_wrong_typed_ordinal_digits_breaks_the_type_guard(self) -> None:
        proc = _run_against_mutant(
            'if not isinstance(ordinal_digits, int) or isinstance(ordinal_digits, bool):',
            "if False:",
            "tests.test_paper_writing.SourceRevisionsMarkerGrammarTests"
            ".test_a_marker_with_a_wrong_typed_ordinal_digits_refuses_naming_it",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        self._assert_guard_failed_under_mutation(proc)


class SourceRootStatusTests(unittest.TestCase):
    """`source-section-binding` spec, `Requirement: A Document-Rooted
    Source With No Marker Refuses` / design.md Decision B: a root is
    document-rooted iff it resolves to a directory under the source base
    holding at least one `*.md` file -- a property computed on disk, never
    keyed by a fact id. U2b correctness repair to `Requirement: An
    Unmeasured Root Is Reported, Never Silently Passed`
    (`the-requirement-names-the-section-that-feeds-it`): a
    `SourceRootKind.REPOSITORY` root is unmeasured BY KIND, never by the
    document-rooted predicate above."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_an_absent_root_is_unmeasured(self) -> None:
        status = paper_declarations.source_root_status(
            self.base, paper_declarations.SourceRoot("does-not-exist", paper_declarations.SourceRootKind.PROSE)
        )

        self.assertEqual(status["state"], "unmeasured")
        self.assertIsNone(status["path"])

    def test_a_root_holding_only_a_gitkeep_is_unmeasured(self) -> None:
        root = self.base / "experiments"
        root.mkdir()
        (root / ".gitkeep").write_text("", encoding="utf-8")

        status = paper_declarations.source_root_status(
            self.base, paper_declarations.SourceRoot("experiments", paper_declarations.SourceRootKind.PROSE)
        )

        self.assertEqual(status["state"], "unmeasured")
        self.assertIsNotNone(status["reason"])

    def test_a_root_holding_a_markdown_document_is_document_rooted(self) -> None:
        root = self.base / "proposals"
        root.mkdir()
        (root / "lumen-thesis-r21.md").write_text("# Title\n", encoding="utf-8")

        status = paper_declarations.source_root_status(
            self.base, paper_declarations.SourceRoot("proposals", paper_declarations.SourceRootKind.PROSE)
        )

        self.assertEqual(status["state"], "document-rooted")
        self.assertEqual(status["path"], root)
        self.assertEqual(status["documents"], 1)
        self.assertIsNone(status["reason"])

    def test_a_repository_kind_root_is_unmeasured_even_when_populated_with_markdown(
        self,
    ) -> None:
        """The exact defect this unit repairs: a REPOSITORY-kind root
        holding real `*.md` files (a target repo's `README.md`, `AGREED.md`,
        ...) must NEVER read as document-rooted -- the has-at-least-one-
        `*.md` predicate above is for PROSE roots only, and must never even
        run for a REPOSITORY root."""
        root = self.base / "implementation"
        root.mkdir()
        (root / "README.md").write_text("# Not prose\n", encoding="utf-8")

        status = paper_declarations.source_root_status(
            self.base,
            paper_declarations.SourceRoot("implementation", paper_declarations.SourceRootKind.REPOSITORY),
        )

        self.assertEqual(status["state"], "unmeasured")
        self.assertIn("not read as prose", status["reason"])
        self.assertNotIn("is not a directory under", status["reason"])

    def test_a_repository_kind_root_is_unmeasured_when_wholly_absent(self) -> None:
        """Same outcome, same reason SHAPE, whether or not the directory
        exists at all -- kind decides this, never disk presence."""
        status = paper_declarations.source_root_status(
            self.base,
            paper_declarations.SourceRoot("implementation", paper_declarations.SourceRootKind.REPOSITORY),
        )

        self.assertEqual(status["state"], "unmeasured")
        self.assertIn("not read as prose", status["reason"])

    def test_the_repository_root_names_the_forges_own_canonical_workspace(self) -> None:
        """Ties this skill's idea of the implementation root to
        `impl_layout.WORKSPACE` directly -- never a re-spelled string --
        so a future rename on either side goes red instead of silent."""
        status = paper_declarations.source_root_status(
            self.base,
            paper_declarations.SourceRoot("implementation", paper_declarations.SourceRootKind.REPOSITORY),
        )

        self.assertEqual(status["path"], impl_layout.WORKSPACE)


class IngestedSourceRootTests(unittest.TestCase):
    """U2c (`the-requirement-names-the-section-that-feeds-it`): an
    `INGESTED`-kind root resolves through `guidance/`'s own per-folder
    classification (`paper_guidance.read_registry`, reused verbatim), never
    through a folder name literal -- `dataset`'s new root is the concrete
    consumer this family exists for."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # `.resolve()`: `paper_guidance.resolve_guidance_dir` resolves
        # `forge_root` before composing `guidance/` under it, and on macOS
        # `tempfile`'s own `/var/folders/...` is itself a symlink into
        # `/private/var/folders/...` -- comparing against an unresolved
        # `self.base` would spuriously fail on that symlink alone.
        self.base = Path(self._tmp.name).resolve()
        self.guidance = self.base / "guidance"
        self.root = paper_declarations.SourceRoot(
            "evidence", paper_declarations.SourceRootKind.INGESTED
        )

    def _classify(self, folder: str, klass: str) -> Path:
        target = self.guidance / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / ".paper-writing.json").write_text(json.dumps({"class": klass}), encoding="utf-8")
        return target

    def _ingest(self, folder: Path, paper_id: str) -> None:
        paper_dir = folder / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / f"{paper_id}.md").write_text("# Title\n", encoding="utf-8")

    def test_no_guidance_directory_at_all_is_unmeasured(self) -> None:
        status = paper_declarations.source_root_status(self.base, self.root)

        self.assertEqual(status["state"], "unmeasured")
        self.assertIsNone(status["path"])

    def test_a_guidance_tree_with_no_evidence_classed_folder_is_unmeasured(self) -> None:
        self._classify("paper-guide", "style-reference")

        status = paper_declarations.source_root_status(self.base, self.root)

        self.assertEqual(status["state"], "unmeasured")

    def test_an_evidence_folder_with_no_ingested_paper_yet_is_unmeasured(self) -> None:
        """A paper that has not ingested its evidence document yet is a
        paper at an earlier stage, never a fault -- the same reading
        `experiments/` holding only `.gitkeep` already gets."""
        self._classify("source-manuscript", "evidence")

        status = paper_declarations.source_root_status(self.base, self.root)

        self.assertEqual(status["state"], "unmeasured")

    def test_exactly_one_evidence_folder_holding_an_ingested_paper_is_document_rooted(
        self,
    ) -> None:
        folder = self._classify("source-manuscript", "evidence")
        self._ingest(folder, "a-fixture-paper-id")

        status = paper_declarations.source_root_status(self.base, self.root)

        self.assertEqual(status["state"], "document-rooted")
        self.assertEqual(status["path"], folder)
        self.assertEqual(status["documents"], 1)

    def test_two_evidence_folders_combine_distinct_documents(self) -> None:
        first = self._classify("source-manuscript", "evidence")
        second = self._classify("second-paper", "evidence")
        self._ingest(first, "first-id")
        self._ingest(second, "second-id")

        status = paper_declarations.source_root_status(self.base, self.root)

        self.assertEqual(status["state"], "document-rooted")
        self.assertEqual(status["documents"], 2)
        self.assertEqual(status["paths"], [second, first])
        self.assertIsNone(status["path"])
        for folder, lineage in ((first, "first-id"), (second, "second-id")):
            self.assertEqual(
                paper_declarations.resolve_ingested_document(status["paths"], lineage),
                folder / lineage / f"{lineage}.md",
            )
        candidates = paper_declarations.describe_binding_candidates(status, self.root)
        self.assertEqual(set(candidates), {"first-id", "second-id"})

    def test_two_folders_classed_evidence_refuses_ambiguous(self) -> None:
        for name in ("source-manuscript", "second-paper"):
            self._ingest(self._classify(name, "evidence"), "same-id")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.source_root_status(self.base, self.root)

        self.assertEqual(ctx.exception.code, "EVIDENCE_ROOT_AMBIGUOUS")
        self.assertIn("source-manuscript", ctx.exception.detail)
        self.assertIn("second-paper", ctx.exception.detail)

    def test_no_folder_name_literal_governs_which_folder_is_the_root(self) -> None:
        """Generality: `rg` under `scripts/` for this fixture's own folder
        name finds nothing -- the folder is discovered by classification,
        never spelled anywhere in the engine."""
        source = (SKILL_SCRIPTS / "paper_declarations.py").read_text(encoding="utf-8")
        self.assertNotIn("source-manuscript", source)

    def test_mutation_skipping_the_ambiguity_count_lets_the_first_match_win(self) -> None:
        proc = _run_against_mutant(
            "        if len(folders) > 1:",
            "        if False:",
            "tests.test_paper_writing.IngestedSourceRootTests"
            ".test_two_folders_classed_evidence_refuses_ambiguous",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class ResolveIngestedDocumentTests(unittest.TestCase):
    """`paper_declarations.resolve_ingested_document`: identity resolution
    for an `INGESTED`-kind root -- the lineage IS the document, never a
    max-ordinal search (design.md, structural consequence: a published
    paper gets no `r22`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.guidance = Path(self._tmp.name) / "guidance"
        self.evidence_dir = self.guidance / "source-manuscript"
        self.evidence_dir.mkdir(parents=True)

    def _ingest(self, paper_id: str) -> Path:
        paper_dir = self.evidence_dir / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        markdown = paper_dir / f"{paper_id}.md"
        markdown.write_text("# Title\n", encoding="utf-8")
        return markdown

    def test_resolves_the_exact_matching_folder(self) -> None:
        markdown = self._ingest("a-fixture-paper-id")

        resolved = paper_declarations.resolve_ingested_document(
            self.evidence_dir, "a-fixture-paper-id"
        )

        self.assertEqual(resolved, markdown)

    def test_single_root_list_preserves_missing_lineage_message(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.resolve_ingested_document([self.evidence_dir], "missing")
        self.assertEqual(ctx.exception.code, "SOURCE_LINEAGE_UNRESOLVED")
        self.assertEqual(ctx.exception.detail,
                         f"lineage 'missing' resolved to 0 ingested document(s) under "
                         f"{self.evidence_dir} (expected exactly one)")

    def test_a_lineage_naming_no_ingested_paper_refuses(self) -> None:
        self._ingest("a-fixture-paper-id")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.resolve_ingested_document(self.evidence_dir, "another-paper-id")

        self.assertEqual(ctx.exception.code, "SOURCE_LINEAGE_UNRESOLVED")
        self.assertIn("another-paper-id", ctx.exception.detail)

    def test_more_than_one_matching_candidate_refuses(self) -> None:
        """Structurally unreachable via two real directories sharing one
        name, but checked explicitly rather than assumed -- proven here by
        stubbing `paper_guidance.ingested_papers` to return a duplicate."""
        markdown = self._ingest("a-fixture-paper-id")
        duplicate = [
            {"folder": "a-fixture-paper-id", "markdown": str(markdown)},
            {"folder": "a-fixture-paper-id", "markdown": str(markdown)},
        ]
        with unittest.mock.patch.object(
            paper_guidance, "ingested_papers", return_value={"source-manuscript": duplicate}
        ):
            with self.assertRaises(Refused) as ctx:
                paper_declarations.resolve_ingested_document(
                    self.evidence_dir, "a-fixture-paper-id"
                )

        self.assertEqual(ctx.exception.code, "SOURCE_LINEAGE_UNRESOLVED")

    def test_mutation_accepting_any_candidate_count_lets_a_zero_match_pass(self) -> None:
        proc = _run_against_mutant(
            "    if len(candidates) != 1:",
            "    if False:",
            "tests.test_paper_writing.ResolveIngestedDocumentTests"
            ".test_a_lineage_naming_no_ingested_paper_refuses",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class SourceLineageResolutionTests(unittest.TestCase):
    """`source-section-binding` spec, `Requirement: Lineage Resolves To The
    Current Revision On Disk` / design.md Decision D: highest ordinal wins,
    gap-tolerant; a tie between two spellings of one ordinal refuses."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.marker = {"revision_prefix": "r", "ordinal_digits": 2}

    def _revision(self, name: str) -> None:
        (self.root / name).write_text("# placeholder\n", encoding="utf-8")

    def _assert_guard_failed_under_mutation(self, proc: subprocess.CompletedProcess) -> None:
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_resolves_to_the_highest_ordinal(self) -> None:
        for ordinal in (14, 15, 21):
            self._revision(f"lumen-thesis-r{ordinal:02d}.md")

        resolved = paper_declarations.resolve_lineage(self.root, "lumen-thesis", self.marker)

        self.assertEqual(resolved.name, "lumen-thesis-r21.md")

    def test_gaps_between_ordinals_are_irrelevant(self) -> None:
        for ordinal in (1, 21):
            self._revision(f"lumen-thesis-r{ordinal:02d}.md")

        resolved = paper_declarations.resolve_lineage(self.root, "lumen-thesis", self.marker)

        self.assertEqual(resolved.name, "lumen-thesis-r21.md")

    def test_a_foreign_lineage_with_zero_candidates_refuses(self) -> None:
        self._revision("other-concept-r21.md")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.resolve_lineage(self.root, "lumen-thesis", self.marker)

        self.assertEqual(ctx.exception.code, "SOURCE_LINEAGE_UNRESOLVED")
        self.assertIn("lumen-thesis", ctx.exception.detail)

    def test_a_tie_between_two_spellings_of_one_ordinal_refuses_naming_both(self) -> None:
        self._revision("lumen-thesis-r21.md")
        self._revision("lumen-thesis-r021.md")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.resolve_lineage(self.root, "lumen-thesis", self.marker)

        self.assertEqual(ctx.exception.code, "SOURCE_LINEAGE_UNRESOLVED")
        self.assertIn("lumen-thesis-r21.md", ctx.exception.detail)
        self.assertIn("lumen-thesis-r021.md", ctx.exception.detail)

    def test_the_markers_own_declared_prefix_and_digits_drive_resolution_never_a_literal(
        self,
    ) -> None:
        self._revision("lineage-v007.md")
        marker = {"revision_prefix": "v", "ordinal_digits": 3}

        resolved = paper_declarations.resolve_lineage(self.root, "lineage", marker)

        self.assertEqual(resolved.name, "lineage-v007.md")

    def test_no_revision_pattern_literal_governs_resolution(self) -> None:
        """design.md Decision A / success criterion 5: the regex is
        composed only from the marker's own declared values -- `rg` under
        `scripts/` for a bare `-r\\d` style literal finds nothing."""
        source = (SKILL_SCRIPTS / "paper_declarations.py").read_text(encoding="utf-8")
        self.assertNotIn('"-r"', source)
        self.assertNotIn("'-r'", source)

    def test_mutation_picking_the_first_match_instead_of_the_max_ordinal_breaks_the_guard(
        self,
    ) -> None:
        proc = _run_against_mutant(
            "    max_ordinal = max(ordinal for ordinal, _path in candidates)",
            "    max_ordinal = candidates[0][0]",
            "tests.test_paper_writing.SourceLineageResolutionTests"
            ".test_resolves_to_the_highest_ordinal",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_allowing_a_tie_to_pass_breaks_the_tie_guard(self) -> None:
        proc = _run_against_mutant(
            "    if len(winners) > 1:",
            "    if False:",
            "tests.test_paper_writing.SourceLineageResolutionTests"
            ".test_a_tie_between_two_spellings_of_one_ordinal_refuses_naming_both",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        self._assert_guard_failed_under_mutation(proc)


class SourceSectionBindingCorpusTests(unittest.TestCase):
    """`source-section-binding` spec: the corpus-level checks
    `paper_graph._verify_source_section_bindings` performs, wired into
    `assemble_corpus` -- `SOURCE_REVISIONS_UNDECLARED`, `SECTION_NOT_IN_
    SOURCE`, `SECTION_TITLE_AMBIGUOUS`, the unmeasured-root report, the
    injectable `source_base`, and the free version bump."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.sections_dir = self.base / "sections"
        self.sections_dir.mkdir()

    def _write_section(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def _unbound_header(self, fact: str = "formulation") -> dict:
        """A bindable `requires_facts` entry with NO `document` half --
        `source-section-binding` spec, `Requirement: A Bindable Fact With
        No Binding Refuses` (U3: the obligation is unconditional)."""
        return {
            "section": "a", "position": 1,
            "blocks": [{
                "id": "only",
                "requires_facts": [{
                    "value": fact,
                    "source": {
                        "file": "sections/01-a.md",
                        "quote": "The formulation, written here.",
                    },
                }],
                "requires_declarations": [], "citations": "none",
            }],
        }

    def _bound_header(self, section_title: str, *, lineage: str = "lumen-thesis") -> dict:
        return {
            "section": "a", "position": 1,
            "blocks": [{
                "id": "only",
                "requires_facts": [{
                    "value": "formulation",
                    "source": {
                        "file": "sections/01-a.md",
                        "quote": "The formulation, written here.",
                    },
                    "document": {"lineage": lineage, "section": section_title},
                }],
                "requires_declarations": [], "citations": "none",
            }],
        }

    _BODY = (
        "The formulation, written here.\n\n"
        "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
    )

    def _marker(self, root: Path, prefix: str = "r", digits: int = 2) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": prefix, "ordinal_digits": digits}}),
            encoding="utf-8",
        )

    def _assert_guard_failed_under_mutation(self, proc: subprocess.CompletedProcess) -> None:
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_a_document_rooted_root_with_no_marker_refuses_source_revisions_undeclared(
        self,
    ) -> None:
        self._write_section("01-a.md", self._bound_header("3. Something"), self._BODY)
        proposals = self.base / "proposals"
        proposals.mkdir()
        (proposals / "lumen-thesis-r21.md").write_text("# 3. Something\n", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SOURCE_REVISIONS_UNDECLARED")
        self.assertIn("proposals", ctx.exception.detail)

    def test_deleting_the_marker_never_degrades_to_unmeasured(self) -> None:
        self._write_section("01-a.md", self._bound_header("3. Something"), self._BODY)
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text("# 3. Something\n", encoding="utf-8")

        paper_graph.assemble_corpus(self.sections_dir)  # raises nothing -- resolves cleanly

        (proposals / ".paper-writing.json").unlink()

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SOURCE_REVISIONS_UNDECLARED")

    def test_an_unbound_entry_under_an_empty_root_reports_unmeasured_not_undeclared(self) -> None:
        """`experiments/` holding only `.gitkeep` (design.md Decision B):
        never `SOURCE_REVISIONS_UNDECLARED`, since the root is not
        document-rooted at all -- there is nothing to have declared a
        marker for."""
        self._write_section(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [{
                        "value": "experimental-design",
                        "source": {
                            "file": "sections/01-a.md",
                            "quote": "The design, written here.",
                        },
                    }],
                    "requires_declarations": [], "citations": "none",
                }],
            },
            "The design, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )
        experiments = self.base / "experiments"
        experiments.mkdir()
        (experiments / ".gitkeep").write_text("", encoding="utf-8")

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.source_roots["experiments"]["state"], "unmeasured")

    def test_a_resolved_binding_parses_with_no_refusal(self) -> None:
        self._write_section("01-a.md", self._bound_header("3. Something"), self._BODY)
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n\n# 5. Closing\n", encoding="utf-8",
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertIn("a.only", corpus.blocks)

    def test_an_absent_title_refuses_section_not_in_source(self) -> None:
        self._write_section("01-a.md", self._bound_header("9. Missing"), self._BODY)
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n", encoding="utf-8",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SECTION_NOT_IN_SOURCE")
        self.assertIn("a.only", ctx.exception.detail)
        self.assertIn("9. Missing", ctx.exception.detail)

    def test_an_ambiguous_title_refuses_section_title_ambiguous(self) -> None:
        self._write_section("01-a.md", self._bound_header("3. Something"), self._BODY)
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 3. Something\n\n# 3. Something\n", encoding="utf-8",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SECTION_TITLE_AMBIGUOUS")
        self.assertIn("a.only", ctx.exception.detail)

    def test_a_lineage_that_does_not_resolve_refuses_source_lineage_unresolved(self) -> None:
        self._write_section("01-a.md", self._bound_header("3. Something"), self._BODY)
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "other-concept-r21.md").write_text("# 3. Something\n", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SOURCE_LINEAGE_UNRESOLVED")

    def test_a_malformed_marker_refuses_malformed_source_marker(self) -> None:
        self._write_section("01-a.md", self._bound_header("3. Something"), self._BODY)
        proposals = self.base / "proposals"
        proposals.mkdir()
        (proposals / "lumen-thesis-r21.md").write_text("# 3. Something\n", encoding="utf-8")
        (proposals / ".paper-writing.json").write_text('{"class": "style-reference"}', encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")

    def test_a_minimal_fixture_with_no_source_roots_at_all_stays_green(self) -> None:
        """design.md Decision C, direct mitigation for the proposal's top
        risk: every EXISTING minimal fixture (no `proposals/`/`experiments/`
        at all under the source base) must keep assembling with zero
        edits -- every root simply reports unmeasured."""
        self._write_section(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [], "requires_declarations": [], "citations": "none",
                }],
            },
            "Prose.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.source_roots["proposals"]["state"], "unmeasured")

    def test_source_base_defaults_to_sections_dir_parent(self) -> None:
        self._write_section("01-a.md", self._bound_header("3. Something"), self._BODY)
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text("# 3. Something\n", encoding="utf-8")

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # no source_base passed

        self.assertIn("a.only", corpus.blocks)

    def test_source_base_is_injectable(self) -> None:
        self._write_section("01-a.md", self._bound_header("3. Something"), self._BODY)
        other_base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other_base, ignore_errors=True)
        proposals = other_base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text("# 3. Something\n", encoding="utf-8")

        corpus = paper_graph.assemble_corpus(self.sections_dir, source_base=other_base)

        self.assertIn("a.only", corpus.blocks)

    def test_publishing_a_survived_revision_costs_no_edit(self) -> None:
        """Success criterion 4: a new revision whose bound section title
        survives resolves with no edit to any binding, and the corpus
        assembles byte-identically untouched."""
        self._write_section("01-a.md", self._bound_header("3. Something"), self._BODY)
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n", encoding="utf-8",
        )

        first = paper_graph.assemble_corpus(self.sections_dir)
        self.assertIn("a.only", first.blocks)

        (proposals / "lumen-thesis-r22.md").write_text(
            "# 1. Intro\n\n# 3. Something\n\n# 7. New appendix\n", encoding="utf-8",
        )

        second = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing -- no edit made

        self.assertIn("a.only", second.blocks)

    def test_publishing_a_revision_that_drops_the_bound_title_refuses_by_name(self) -> None:
        self._write_section("01-a.md", self._bound_header("3. Something"), self._BODY)
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n", encoding="utf-8",
        )
        paper_graph.assemble_corpus(self.sections_dir)  # raises nothing at r21

        (proposals / "lumen-thesis-r22.md").write_text(
            "# 1. Intro\n\n# 3.1 Something Split\n\n# 3.2 Something Else\n", encoding="utf-8",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SECTION_NOT_IN_SOURCE")

    def test_a_repository_kind_fact_never_binds_even_against_a_populated_namesake_directory(
        self,
    ) -> None:
        """The corpus-level acceptance case for the U2b correctness repair:
        `implementation` binds to a REPOSITORY-kind root, so a `document`
        half naming it must resolve with NO refusal at all --
        `corpus.source_roots["implementation"]` stays `unmeasured` even
        though the directory exists and holds `*.md` files that would
        otherwise satisfy the document-rooted predicate and (wrongly)
        demand section resolution."""
        self._write_section(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [{
                        "value": "implementation",
                        "source": {
                            "file": "sections/01-a.md",
                            "quote": "The implementation, written here.",
                        },
                        "document": {"lineage": "does-not-matter", "section": "Nonexistent"},
                    }],
                    "requires_declarations": [], "citations": "none",
                }],
            },
            "The implementation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )
        implementation = self.base / "implementation"
        implementation.mkdir()
        (implementation / "README.md").write_text("# A target repo, not prose\n", encoding="utf-8")

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.source_roots["implementation"]["state"], "unmeasured")

    def test_mutation_treating_a_repository_root_as_prose_lets_it_bind(self) -> None:
        """Mutate the kind guard itself away: `SourceRootKind.REPOSITORY`
        roots fall through to the document-rooted predicate, and the
        populated `implementation/README.md` fixture above wrongly
        resolves as document-rooted -- proving the guard, not merely its
        presence."""
        proc = _run_against_mutant(
            "    if root.kind is SourceRootKind.REPOSITORY:",
            "    if False:",
            "tests.test_paper_writing.SourceSectionBindingCorpusTests"
            ".test_a_repository_kind_fact_never_binds_even_against_a_populated_namesake_directory",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_wiring_the_guard_only_behind_a_condition_is_caught(self) -> None:
        """Static proof the call is a direct statement of `assemble_corpus`'s
        own body, mirroring `RequirementTranscriptionMutationTests`'s own
        `test_the_call_is_a_direct_statement_never_guarded`."""
        source = (SKILL_SCRIPTS / "paper_graph.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        assemble = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "assemble_corpus"
        )
        direct_call_names = {
            stmt.value.func.id
            for stmt in assemble.body
            if isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
        }
        self.assertIn("_verify_source_section_bindings", direct_call_names)

    def test_mutation_removing_the_verifier_call_flips_section_existence_from_green_to_red(
        self,
    ) -> None:
        proc = _run_against_mutant(
            "    _verify_source_section_bindings(\n"
            "        corpus, enforce_bindings=enforce_bindings, enforce_for_block=enforce_for_block,\n"
            "    )\n",
            "",
            "tests.test_paper_writing.SourceSectionBindingCorpusTests"
            ".test_an_absent_title_refuses_section_not_in_source",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_a_bindable_fact_with_no_document_half_reports_undecided_at_read_time(
        self,
    ) -> None:
        """U3b correctness repair: a bindable fact whose source root is
        MEASURED but carries no `document` half is `undecided` -- reported
        in `Corpus.undecided_bindings`, the read-time counterpart
        `source_roots` already established for an unmeasured root, never
        raised. A read-only verb (plain `assemble_corpus`, the default
        `enforce_bindings=False`) MUST succeed; `SECTION_BINDING_ABSENT`
        moved to `write`'s own gate (`SourceSectionBindingWriteGateTests
        .test_write_refuses_section_binding_absent`) -- this is the exact
        assembly-time refusal U3 shipped, now proven ABSENT here so
        nothing forces an agent to invent a binding just to keep the
        corpus assemblable."""
        self._write_section("01-a.md", self._unbound_header("formulation"), self._BODY)
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text("# 3. Something\n", encoding="utf-8")

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(
            corpus.undecided_bindings["a.only"]["formulation"]["state"], "undecided",
        )
        self.assertEqual(corpus.undecided_bindings["a.only"]["formulation"]["root"], "proposals")

    def test_a_bindable_fact_under_an_unmeasured_root_carries_no_obligation(self) -> None:
        """An unmeasured root is a normal state of a paper at an earlier
        stage, never a fault: `SECTION_BINDING_ABSENT` MUST NOT fire for a
        bindable fact whose own root is not yet document-rooted."""
        self._write_section(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [{
                        "value": "experimental-design",
                        "source": {
                            "file": "sections/01-a.md",
                            "quote": "The design, written here.",
                        },
                    }],
                    "requires_declarations": [], "citations": "none",
                }],
            },
            "The design, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )
        experiments = self.base / "experiments"
        experiments.mkdir()
        (experiments / ".gitkeep").write_text("", encoding="utf-8")

        paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

    def test_a_bindable_fact_under_a_repository_root_carries_no_obligation(self) -> None:
        """A `REPOSITORY`-kind root is always `unmeasured` BY KIND -- an
        `implementation`-bound entry with no `document` half must never be
        obligated, however populated the namesake directory is."""
        self._write_section(
            "01-a.md",
            {
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [{
                        "value": "implementation",
                        "source": {
                            "file": "sections/01-a.md",
                            "quote": "The implementation, written here.",
                        },
                    }],
                    "requires_declarations": [], "citations": "none",
                }],
            },
            "The implementation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        )
        implementation = self.base / "implementation"
        implementation.mkdir()
        (implementation / "README.md").write_text("# A target repo\n", encoding="utf-8")

        paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

    def test_mutation_removing_the_absence_check_lets_an_unbound_fact_pass(self) -> None:
        """U3b: the obligation itself moved to `write`'s own gate, so the
        mutation this guard must survive is proven there too, through the
        REAL `cmd_write` root (`SourceSectionBindingWriteGateTests
        .test_write_refuses_section_binding_absent`) -- mutating away
        `_compute_undecided_bindings`'s own absence check must fail that
        write-gate test, never merely the read-only assembly this class
        already proves stays green on an unbound fact."""
        proc = _run_against_mutant(
            "            if fact_id not in bound_fact_ids:\n",
            "            if False:\n",
            "tests.test_paper_writing.SourceSectionBindingWriteGateTests"
            ".test_write_refuses_section_binding_absent",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_a_binding_naming_two_sections_resolves_both(self) -> None:
        """U2d: a binding may name more than one section of the same
        lineage -- both must resolve for the corpus to assemble cleanly."""
        self._write_section(
            "01-a.md", self._bound_header(["1. Intro", "3. Something"]), self._BODY,
        )
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n", encoding="utf-8",
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertIn("a.only", corpus.blocks)

    def test_a_binding_naming_two_sections_where_one_is_missing_names_that_title(self) -> None:
        """The refusal must name WHICH title failed, never just the block
        -- the other, resolvable title must not mask it."""
        self._write_section(
            "01-a.md", self._bound_header(["1. Intro", "9. Missing"]), self._BODY,
        )
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n", encoding="utf-8",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SECTION_NOT_IN_SOURCE")
        self.assertIn("a.only", ctx.exception.detail)
        self.assertIn("9. Missing", ctx.exception.detail)
        self.assertNotIn("1. Intro", ctx.exception.detail)


class RecordedSourceBindingCorpusTests(unittest.TestCase):
    """`the-requirement-names-the-section-that-feeds-it`, U3e ruling
    (design.md Decision J): the corpus reads a `source-section-binding`
    from `paper/` (`paper_declarations.read_bindings`, recorded by
    `bind`), never only from a contract header's own `document` half.
    Both sources may contribute; when both name the SAME (block, fact)
    they must agree exactly, or the corpus refuses `SOURCE_BINDING_
    CONFLICT` naming both — never a precedence rule that silently prefers
    one."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.sections_dir = self.base / "sections"
        self.sections_dir.mkdir()
        self.paper_dir = self.base / "paper"
        paper_scaffold.scaffold(self.paper_dir)

    def _write_section(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def _header(self, *, document=None) -> dict:
        entry = {
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
        }
        if document is not None:
            entry["document"] = document
        return {
            "section": "a", "position": 1,
            "blocks": [{
                "id": "only", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }],
        }

    _BODY = (
        "The formulation, written here.\n\n"
        "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
    )

    def _marker(self, root: Path, prefix: str = "r", digits: int = 2) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": prefix, "ordinal_digits": digits}}),
            encoding="utf-8",
        )

    def test_a_binding_recorded_via_bind_resolves_with_no_header_binding(self) -> None:
        self._write_section("01-a.md", self._header(), self._BODY)
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text("# 3. Something\n", encoding="utf-8")
        _settle_separation_round(
            self.paper_dir, self.base, "formulation", "lumen-thesis", "a.only",
            ("3. Something",),
        )
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis", "3. Something",
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertIn(
            ("formulation", "lumen-thesis", "3. Something"), corpus.blocks["a.only"].source_bindings,
        )
        self.assertNotIn("a.only", corpus.undecided_bindings)

    def test_a_recorded_binding_agreeing_with_the_header_is_not_a_conflict(self) -> None:
        self._write_section(
            "01-a.md",
            self._header(document={"lineage": "lumen-thesis", "section": "3. Something"}),
            self._BODY,
        )
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text("# 3. Something\n", encoding="utf-8")
        _settle_separation_round(
            self.paper_dir, self.base, "formulation", "lumen-thesis", "a.only",
            ("3. Something",),
        )
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis", "3. Something",
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(
            corpus.blocks["a.only"].source_bindings, (("formulation", "lumen-thesis", "3. Something"),),
        )

    def test_a_recorded_binding_disagreeing_with_the_header_refuses(self) -> None:
        self._write_section(
            "01-a.md",
            self._header(document={"lineage": "lumen-thesis", "section": "3. Something"}),
            self._BODY,
        )
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n", encoding="utf-8",
        )
        _settle_separation_round(
            self.paper_dir, self.base, "formulation", "lumen-thesis", "a.only", ("1. Intro",),
        )
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis", "1. Intro",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SOURCE_BINDING_CONFLICT")
        self.assertIn("a.only", ctx.exception.detail)
        self.assertIn("3. Something", ctx.exception.detail)
        self.assertIn("1. Intro", ctx.exception.detail)

    def test_mutation_collapsing_the_conflict_check_lets_disagreement_pass(self) -> None:
        proc = _run_against_mutant(
            "            if sorted(by_fact[fact_id]) != sorted(recorded_titles):\n",
            "            if False:\n",
            "tests.test_paper_writing.RecordedSourceBindingCorpusTests"
            ".test_a_recorded_binding_disagreeing_with_the_header_refuses",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class SecondProseRootGeneralityTests(unittest.TestCase):
    """U3c (design.md's own stated risk, discharged): every check
    `SourceSectionBindingCorpusTests` above proves against `proposals` --
    the only `PROSE`-kind root actually populated on this checkout -- is
    proven again here against `experiments`, the SECOND `PROSE`-kind root
    already declared in `FACT_SOURCE_ROOT` (holding only `.gitkeep` on
    this checkout). The full path -- marker read, lineage resolved to a
    current revision, section existence and ambiguity per title, the
    `undecided`/`write` tier boundary -- is driven through an invented
    lineage (`field-log`) and invented section titles that name nothing
    any shipped contract binds to, at a marker width (3 digits) that is
    NOT the live root's own (2)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.sections_dir = self.base / "sections"
        self.sections_dir.mkdir()

    def _write_section(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def _bound_header(self, section_title, *, lineage: str = "field-log") -> dict:
        return {
            "section": "a", "position": 1,
            "blocks": [{
                "id": "only",
                "requires_facts": [{
                    "value": "experimental-design",
                    "source": {"file": "sections/01-a.md", "quote": "The design, written here."},
                    "document": {"lineage": lineage, "section": section_title},
                }],
                "requires_declarations": [], "citations": "none",
            }],
        }

    def _unbound_header(self) -> dict:
        return {
            "section": "a", "position": 1,
            "blocks": [{
                "id": "only",
                "requires_facts": [{
                    "value": "experimental-design",
                    "source": {"file": "sections/01-a.md", "quote": "The design, written here."},
                }],
                "requires_declarations": [], "citations": "none",
            }],
        }

    _BODY = (
        "The design, written here.\n\n"
        "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
    )

    def _marker(self, root: Path, *, prefix: str = "v", digits: int = 3) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": prefix, "ordinal_digits": digits}}),
            encoding="utf-8",
        )

    def test_the_markers_own_declared_width_governs_resolution_not_the_live_roots_default(
        self,
    ) -> None:
        """This root's marker declares `ordinal_digits: 3` -- the live
        `proposals/.paper-writing.json` declares 2. `field-log-v05.md` (a
        two-digit ordinal) MUST be excluded under this root's own declared
        width, leaving exactly one candidate; nothing here silently
        depends on a two-digit default."""
        self._write_section("01-a.md", self._bound_header("1. Setup Notes"), self._BODY)
        experiments = self.base / "experiments"
        self._marker(experiments, prefix="v", digits=3)
        (experiments / "field-log-v05.md").write_text("# 0. Decoy\n", encoding="utf-8")
        (experiments / "field-log-v005.md").write_text("# 1. Setup Notes\n", encoding="utf-8")

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertIn("a.only", corpus.blocks)

    def test_mutation_hardcoding_the_live_roots_default_width_breaks_this_roots_resolution(
        self,
    ) -> None:
        proc = _run_against_mutant(
            '    digits = marker["ordinal_digits"]',
            "    digits = 2",
            "tests.test_paper_writing.SecondProseRootGeneralityTests"
            ".test_the_markers_own_declared_width_governs_resolution_not_the_live_roots_default",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_lineage_resolves_to_the_highest_ordinal_and_a_further_revision_moves_it_free(
        self,
    ) -> None:
        """The change's own headline property -- 'a version bump costs
        nothing' -- proven on a root other than the one it was developed
        against: the highest-ordinal revision wins with gaps between
        ordinals, and publishing a further revision moves resolution with
        no edit to the binding above."""
        self._write_section("01-a.md", self._bound_header("1. Setup Notes"), self._BODY)
        experiments = self.base / "experiments"
        self._marker(experiments)
        (experiments / "field-log-v005.md").write_text("# 0. Draft Notes\n", encoding="utf-8")
        (experiments / "field-log-v012.md").write_text("# 0. Draft Notes\n", encoding="utf-8")
        (experiments / "field-log-v020.md").write_text("# 1. Setup Notes\n", encoding="utf-8")

        first = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing -- picks v020
        self.assertIn("a.only", first.blocks)

        (experiments / "field-log-v031.md").write_text("# 1. Setup Notes\n", encoding="utf-8")

        second = paper_graph.assemble_corpus(self.sections_dir)  # no edit to the binding
        self.assertIn("a.only", second.blocks)

    def test_mutation_picking_the_lowest_ordinal_breaks_this_roots_resolution(self) -> None:
        proc = _run_against_mutant(
            "    max_ordinal = max(ordinal for ordinal, _path in candidates)",
            "    max_ordinal = min(ordinal for ordinal, _path in candidates)",
            "tests.test_paper_writing.SecondProseRootGeneralityTests"
            ".test_lineage_resolves_to_the_highest_ordinal_and_a_further_revision_moves_it_free",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_a_binding_naming_two_sections_resolves_both_on_this_root(self) -> None:
        self._write_section(
            "01-a.md", self._bound_header(["1. Setup Notes", "2. Session Records"]), self._BODY,
        )
        experiments = self.base / "experiments"
        self._marker(experiments)
        (experiments / "field-log-v005.md").write_text(
            "# 1. Setup Notes\n\n# 2. Session Records\n", encoding="utf-8",
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertIn("a.only", corpus.blocks)

    def test_one_missing_title_among_several_names_only_that_title_on_this_root(self) -> None:
        self._write_section(
            "01-a.md", self._bound_header(["1. Setup Notes", "9. Missing Log"]), self._BODY,
        )
        experiments = self.base / "experiments"
        self._marker(experiments)
        (experiments / "field-log-v005.md").write_text("# 1. Setup Notes\n", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SECTION_NOT_IN_SOURCE")
        self.assertIn("9. Missing Log", ctx.exception.detail)
        self.assertNotIn("1. Setup Notes", ctx.exception.detail)

    def test_mutation_collapsing_the_title_list_masks_the_missing_sibling_on_this_root(
        self,
    ) -> None:
        proc = _run_against_mutant(
            "        titles = section if isinstance(section, list) else (section,)",
            "        titles = (section[0] if isinstance(section, list) else section,)",
            "tests.test_paper_writing.SecondProseRootGeneralityTests"
            ".test_one_missing_title_among_several_names_only_that_title_on_this_root",
            source_path=SKILL_SCRIPTS / "paper_contract.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_an_ambiguous_title_refuses_section_title_ambiguous_on_this_root(self) -> None:
        self._write_section("01-a.md", self._bound_header("1. Setup Notes"), self._BODY)
        experiments = self.base / "experiments"
        self._marker(experiments)
        (experiments / "field-log-v005.md").write_text(
            "# 1. Setup Notes\n\n# 1. Setup Notes\n", encoding="utf-8",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SECTION_TITLE_AMBIGUOUS")

    def test_second_root_reports_unmeasured_then_refuses_once_it_holds_undeclared_documents(
        self,
    ) -> None:
        """Both `source-section-binding` states, proven distinguishable on
        `experiments` exactly as they already are on `proposals`: an
        absent root is `unmeasured` and a bound entry over it raises
        nothing; the SAME root, once it holds a document but no marker,
        refuses `SOURCE_REVISIONS_UNDECLARED` -- never a silent
        `unmeasured` report."""
        self._write_section("01-a.md", self._bound_header("1. Setup Notes"), self._BODY)

        first = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing -- root absent
        self.assertEqual(first.source_roots["experiments"]["state"], "unmeasured")

        experiments = self.base / "experiments"
        experiments.mkdir()
        (experiments / "field-log-v005.md").write_text("# 1. Setup Notes\n", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SOURCE_REVISIONS_UNDECLARED")
        self.assertIn("experiments", ctx.exception.detail)

    def test_mutation_removing_the_undeclared_guard_breaks_on_this_root(self) -> None:
        proc = _run_against_mutant(
            "        if marker is None:",
            "        if False:",
            "tests.test_paper_writing.SecondProseRootGeneralityTests"
            ".test_second_root_reports_unmeasured_then_refuses_once_it_holds_undeclared_documents",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_an_unbound_entry_under_this_root_reports_undecided_at_read_time(self) -> None:
        self._write_section("01-a.md", self._unbound_header(), self._BODY)
        experiments = self.base / "experiments"
        experiments.mkdir()
        (experiments / "field-log-v005.md").write_text("# 0. Draft Notes\n", encoding="utf-8")

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(
            corpus.undecided_bindings["a.only"]["experimental-design"]["state"], "undecided",
        )
        self.assertEqual(
            corpus.undecided_bindings["a.only"]["experimental-design"]["root"], "experiments",
        )


class SecondProseRootWriteGateTests(unittest.TestCase):
    """U3c: the `write`-only tier boundary (`source-section-binding` spec,
    `Requirement: A Bindable Fact With No Binding Is Undecided, And
    Refuses Only At write`) proven through the REAL `cmd_write` root
    against `experiments`, mirroring `SourceSectionBindingWriteGateTests
    .test_write_refuses_section_binding_absent` on a root that is not
    `proposals`."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-second-root-write-gate-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)

    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="a", block="only",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=None,
        )

    def test_write_refuses_section_binding_absent_on_a_second_root(self) -> None:
        (self.sections_dir / "01-a.md").write_text(
            "---\n" + json.dumps({
                "section": "a", "position": 1,
                "blocks": [{
                    "id": "only",
                    "requires_facts": [{
                        "value": "experimental-design",
                        "source": {
                            "file": "sections/01-a.md",
                            "quote": "The design, written here.",
                        },
                    }],
                    "requires_declarations": [], "citations": "none",
                }],
            }) + "\n---\n\nThe design, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        experiments = self.test_root / "experiments"
        experiments.mkdir()
        (experiments / "field-log-v005.md").write_text("# 0. Draft Notes\n", encoding="utf-8")

        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        before = tex_path.read_bytes()

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self._args())

        self.assertEqual(ctx.exception.code, "SECTION_BINDING_ABSENT")
        self.assertFalse((self.test_root / "draft.json").exists())
        self.assertFalse((self.test_root / "audit.json").exists())
        self.assertEqual(tex_path.read_bytes(), before)

    def test_mutation_removing_the_absence_check_lets_this_root_pass_write(self) -> None:
        proc = _run_against_mutant(
            "            if fact_id not in bound_fact_ids:\n",
            "            if False:\n",
            "tests.test_paper_writing.SecondProseRootWriteGateTests"
            ".test_write_refuses_section_binding_absent_on_a_second_root",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class IngestedSourceSectionBindingCorpusTests(unittest.TestCase):
    """U2c corpus-level acceptance: a `dataset`-bound entry resolves
    through the evidence-classed `guidance/` root, identity not
    max-ordinal -- the owner's ruling holds at the full `assemble_corpus`
    boundary, not merely at the unit level."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.sections_dir = self.base / "sections"
        self.sections_dir.mkdir()
        self.guidance = self.base / "guidance"

    def _write_section(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def _dataset_header(self, section_title: str, *, lineage: str) -> dict:
        return {
            "section": "a", "position": 1,
            "blocks": [{
                "id": "only",
                "requires_facts": [{
                    "value": "dataset",
                    "source": {
                        "file": "sections/01-a.md",
                        "quote": "The dataset, written here.",
                    },
                    "document": {"lineage": lineage, "section": section_title},
                }],
                "requires_declarations": [], "citations": "none",
            }],
        }

    _BODY = (
        "The dataset, written here.\n\n"
        "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
    )

    def _classify(self, folder: str, klass: str) -> Path:
        target = self.guidance / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / ".paper-writing.json").write_text(json.dumps({"class": klass}), encoding="utf-8")
        return target

    def _ingest(self, folder: Path, paper_id: str, body: str) -> None:
        paper_dir = folder / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / f"{paper_id}.md").write_text(body, encoding="utf-8")

    def test_a_dataset_binding_resolves_against_the_ingested_evidence_document(self) -> None:
        self._write_section(
            "01-a.md", self._dataset_header("3. Something", lineage="a-fixture-paper-id"),
            self._BODY,
        )
        evidence = self._classify("source-manuscript", "evidence")
        self._ingest(evidence, "a-fixture-paper-id", "# 1. Intro\n\n# 3. Something\n")

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertIn("a.only", corpus.blocks)

    def test_a_lineage_naming_no_ingested_paper_refuses_source_lineage_unresolved(self) -> None:
        """Corpus-level wiring proof, distinct from `ResolveIngestedDocument
        Tests`'s own unit test: `_verify_source_section_bindings`'s
        `INGESTED` branch is only reached once a real `dataset` binding
        exists, unlike the unconditionally-computed `source_roots` report
        (`EVIDENCE_ROOT_AMBIGUOUS`/`unmeasured` are already unit-covered by
        `IngestedSourceRootTests` and need no corpus-level duplicate)."""
        self._write_section(
            "01-a.md", self._dataset_header("3. Something", lineage="wrong-id"), self._BODY,
        )
        evidence = self._classify("source-manuscript", "evidence")
        self._ingest(evidence, "a-fixture-paper-id", "# 1. Intro\n\n# 3. Something\n")

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "SOURCE_LINEAGE_UNRESOLVED")

    def test_mutation_resolving_an_ingested_root_by_max_ordinal_breaks_the_guard(self) -> None:
        """The task's own required mutation: dispatch the `INGESTED`
        branch through the PROSE (marker + max-ordinal) route instead --
        `guidance/source-manuscript/` carries only the CLASSIFICATION marker
        (`{"class": "evidence"}`), which the PROSE-kind revision-marker
        reader refuses as malformed (missing `revisions`), proving the
        kind dispatch itself is load-bearing."""
        self._write_section(
            "01-a.md", self._dataset_header("3. Something", lineage="a-fixture-paper-id"),
            self._BODY,
        )
        evidence = self._classify("source-manuscript", "evidence")
        self._ingest(evidence, "a-fixture-paper-id", "# 1. Intro\n\n# 3. Something\n")

        proc = _run_against_mutant(
            "    if root.kind is paper_declarations.SourceRootKind.INGESTED:",
            "    if False:",
            "tests.test_paper_writing.IngestedSourceSectionBindingCorpusTests"
            ".test_a_dataset_binding_resolves_against_the_ingested_evidence_document",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class RequirementTranscriptionMutationTests(unittest.TestCase):
    """Mutation proof the gate is load-bearing (design.md, Testing
    Strategy, 'Mutation — unconditional': 'the `assemble_corpus` call line
    removed... the unbacked test goes green → red') and the static proof
    the wiring is unconditional — a direct statement inside
    `assemble_corpus`, never behind `if`/`try`."""

    def test_removing_the_verifier_call_flips_the_gate_test_from_green_to_red(self) -> None:
        proc = _run_against_mutant(
            "    _verify_requirement_transcription(corpus, bodies)\n",
            "",
            "tests.test_paper_writing.RequirementTranscriptionGateTests"
            ".test_an_unbacked_quote_refuses_span_not_in_source",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_narrowing_the_block_level_tuple_flips_the_produces_facts_test_from_green_to_red(
        self,
    ) -> None:
        """`fact-production` spec, `Requirement: Transcribed produces_facts
        Entries Only`; design.md Decision B: 'adding one member to its own
        tuple' — proves that member is load-bearing, not decorative."""
        proc = _run_against_mutant(
            '    for field in ("requires_facts", "requires_declarations", "produces_facts"):\n',
            '    for field in ("requires_facts", "requires_declarations"):\n',
            "tests.test_paper_writing.RequirementTranscriptionGateTests"
            ".test_an_unbacked_produces_facts_quote_refuses_span_not_in_source",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_removing_the_section_level_walk_flips_its_own_test_from_green_to_red(self) -> None:
        """The section-level half (`header.produces_facts`, walked apart
        from the block-level tuple the same way `_verify_mode_transcription`
        already walks `header.mode` apart from block `mode` entries) is its
        own load-bearing statement, not a no-op that happens to pass because
        the block-level tuple already covers it."""
        proc = _run_against_mutant(
            "        for entry in header.produces_facts:\n"
            "            source = entry[\"source\"]\n",
            "        for entry in []:\n"
            "            source = entry[\"source\"]\n",
            "tests.test_paper_writing.RequirementTranscriptionGateTests"
            ".test_an_unbacked_section_level_produces_facts_quote_refuses_span_not_in_source",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_the_call_is_a_direct_statement_never_guarded(self) -> None:
        source = (SKILL_SCRIPTS / "paper_graph.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        assemble = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "assemble_corpus"
        )
        direct_call_names = {
            stmt.value.func.id
            for stmt in assemble.body
            if isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
        }
        self.assertIn(
            "_verify_requirement_transcription", direct_call_names,
            "the verifier call must be a direct statement of assemble_corpus's own "
            "body, never nested inside an 'if' or 'try'",
        )


def _produces_facts_section(
    section: str, block_id: str, *, requires=(), produces=(), file: str,
) -> dict:
    """A minimal, partition-honoring, single-block header naming `file` as
    the self-source for every rich entry it declares — the shared shape
    `FactSelfReferenceTests` / `FactRouteExclusivityTests` /
    `FactProducerDuplicationTests` below all build on, one block per
    concern under test."""
    return {
        "section": section, "position": 1,
        "blocks": [{
            "id": block_id,
            "requires_facts": [
                {"value": v, "source": {"file": file, "quote": f"This block requires the {v}."}}
                for v in requires
            ],
            "requires_declarations": [], "citations": "none",
            "produces_facts": [
                {"value": v, "source": {"file": file, "quote": f"This block produces the {v}."}}
                for v in produces
            ],
        }],
    }


def _produces_facts_body(*, requires=(), produces=(), chain_rows=()) -> str:
    """`chain_rows`: `[(holder_qualified_id, dependency_qualified_id), ...]`
    -- `contract-input-partition` spec, `Requirement: A Produced-Fact
    Dependency Is An Internal-Chain Row`. Every caller whose fixture puts a
    genuinely SEPARATE producer block behind a `requires_facts` entry must
    pass the row naming that producer, or `paper_graph._verify_producer_
    chain_rows` refuses `PRODUCER_CHAIN_ABSENT` -- empty (the default)
    reproduces the prior `None.` body byte for byte, for every caller whose
    `requires`/`produces` never cross two different blocks."""
    sentences = "\n\n".join(
        [f"This block requires the {v}." for v in requires]
        + [f"This block produces the {v}." for v in produces]
    ) or "Prose."
    if chain_rows:
        table_rows = "\n".join(f"| `{holder}` | `{dependency}` |" for holder, dependency in chain_rows)
        internal_chain = f"### Internal chain\n\n| Block | Depends on |\n|---|---|\n{table_rows}\n"
    else:
        internal_chain = "### Internal chain\n\nNone.\n"
    return sentences + "\n\n### External inputs\n\nNone.\n\n" + internal_chain


class FactSelfReferenceTests(unittest.TestCase):
    """`fact-production` spec, `Requirement: A Block MUST NOT Require What
    It Produces`; design.md, File Changes ('self-reference... checks')."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def _write(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def test_a_block_requiring_and_producing_the_same_fact_refuses(self) -> None:
        header = _produces_facts_section(
            "related-work", "rw-closing", requires=["gap"], produces=["gap"],
            file="sections/01-a.md",
        )
        self._write("01-a.md", header, _produces_facts_body(requires=["gap"], produces=["gap"]))

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "FACT_SELF_REQUIRED")
        self.assertIn("related-work.rw-closing", ctx.exception.detail)
        self.assertIn("gap", ctx.exception.detail)

    def test_the_corrected_shape_parses_clean(self) -> None:
        """`related-work.rw-closing` producing `gap` and no longer
        requiring it (the corpus-edit unit 2 will make real) is exactly the
        shape this check must NOT refuse."""
        header = _produces_facts_section(
            "related-work", "rw-closing", requires=[], produces=["gap"],
            file="sections/01-a.md",
        )
        self._write("01-a.md", header, _produces_facts_body(produces=["gap"]))

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.blocks["related-work.rw-closing"].produces_facts, ("gap",))

    def test_removing_the_check_flips_the_refusal_test_from_green_to_red(self) -> None:
        proc = _run_against_mutant(
            "    _verify_self_reference(corpus)\n",
            "",
            "tests.test_paper_writing.FactSelfReferenceTests"
            ".test_a_block_requiring_and_producing_the_same_fact_refuses",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class FactRouteExclusivityTests(unittest.TestCase):
    """`fact-production` spec is silent on the exact name; design.md,
    Refusal Codes #4 ('a `produces_facts` entry names a declarable
    fact'); `tasks.md` unit 0.4 finalizes `FACT_ROUTE_AMBIGUOUS`. A
    `produces_facts` entry naming a fact in `paper_declarations.
    OBSERVABLE_FACTS ∪ STRUCTURAL_FACTS` refuses — those facts are only
    ever declared or structurally resolved, never written by a block."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def _write(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def test_a_produces_facts_entry_naming_an_observable_fact_refuses(self) -> None:
        header = _produces_facts_section(
            "a", "only", produces=["dataset"], file="sections/01-a.md",
        )
        self._write("01-a.md", header, _produces_facts_body(produces=["dataset"]))

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "FACT_ROUTE_AMBIGUOUS")
        self.assertIn("dataset", ctx.exception.detail)

    def test_a_produces_facts_entry_naming_the_structural_fact_refuses(self) -> None:
        header = _produces_facts_section(
            "a", "only", produces=["skeleton"], file="sections/01-a.md",
        )
        self._write("01-a.md", header, _produces_facts_body(produces=["skeleton"]))

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "FACT_ROUTE_AMBIGUOUS")
        self.assertIn("skeleton", ctx.exception.detail)

    def test_a_produces_facts_entry_naming_a_derived_fact_is_unaffected(self) -> None:
        header = _produces_facts_section(
            "a", "only", produces=["limitations"], file="sections/01-a.md",
        )
        self._write("01-a.md", header, _produces_facts_body(produces=["limitations"]))

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.blocks["a.only"].produces_facts, ("limitations",))

    def test_removing_the_check_flips_the_refusal_test_from_green_to_red(self) -> None:
        proc = _run_against_mutant(
            "    _verify_route_exclusivity(declarations)\n",
            "",
            "tests.test_paper_writing.FactRouteExclusivityTests"
            ".test_a_produces_facts_entry_naming_an_observable_fact_refuses",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class FactProducerDuplicationTests(unittest.TestCase):
    """`fact-production` spec, `Requirement: Every Producer Is Either Sole
    Or Corroborated`; `coupling-verification` spec, Coupling 3. Two
    uncorroborated producers of one fact refuse `FACT_PRODUCER_DUPLICATE`;
    the one corroborated pair an existing coupling-verification check names
    (`gap`, `paper_verify.CHECKS`) is legal — checked structurally (is the
    fact id itself a member of the existing coupling roster?), never by a
    hand-listed exception list of fact ids (design.md, Decision F)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def _write(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def test_two_uncorroborated_producers_of_one_fact_refuse(self) -> None:
        """`limitations` has no coupling-verification check named after it
        (`"limitations" not in paper_verify.CHECKS`) — an uncorroborated
        duplicate."""
        self.assertNotIn("limitations", paper_verify.CHECKS)
        header_a = _produces_facts_section(
            "a", "only", produces=["limitations"], file="sections/01-a.md",
        )
        header_b = _produces_facts_section(
            "b", "only", produces=["limitations"], file="sections/02-b.md",
        )
        self._write("01-a.md", header_a, _produces_facts_body(produces=["limitations"]))
        self._write("02-b.md", header_b, _produces_facts_body(produces=["limitations"]))

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "FACT_PRODUCER_DUPLICATE")
        self.assertIn("limitations", ctx.exception.detail)
        self.assertIn("a.only", ctx.exception.detail)
        self.assertIn("b.only", ctx.exception.detail)

    def test_the_corroborated_pair_of_gap_producers_is_legal(self) -> None:
        """`gap` has an existing coupling-verification check named after it
        (`"gap" in paper_verify.CHECKS`, Coupling 3) — the one corroborated
        duplicate `fact-production`'s carve-out allows."""
        self.assertIn("gap", paper_verify.CHECKS)
        header_a = _produces_facts_section(
            "related-work", "rw-closing", produces=["gap"], file="sections/01-a.md",
        )
        header_b = _produces_facts_section(
            "introduction", "block-3", produces=["gap"], file="sections/02-b.md",
        )
        self._write("01-a.md", header_a, _produces_facts_body(produces=["gap"]))
        self._write("02-b.md", header_b, _produces_facts_body(produces=["gap"]))

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.blocks["related-work.rw-closing"].produces_facts, ("gap",))
        self.assertEqual(corpus.blocks["introduction.block-3"].produces_facts, ("gap",))

    def test_three_producers_of_the_corroborated_fact_still_refuse(self) -> None:
        """Corroboration legalizes exactly the PAIR — a third producer of
        `gap` is still a duplicate, never silently absorbed."""
        header_a = _produces_facts_section(
            "related-work", "rw-closing", produces=["gap"], file="sections/01-a.md",
        )
        header_b = _produces_facts_section(
            "introduction", "block-3", produces=["gap"], file="sections/02-b.md",
        )
        header_c = _produces_facts_section(
            "c", "only", produces=["gap"], file="sections/03-c.md",
        )
        self._write("01-a.md", header_a, _produces_facts_body(produces=["gap"]))
        self._write("02-b.md", header_b, _produces_facts_body(produces=["gap"]))
        self._write("03-c.md", header_c, _produces_facts_body(produces=["gap"]))

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "FACT_PRODUCER_DUPLICATE")

    def test_removing_the_check_flips_the_refusal_test_from_green_to_red(self) -> None:
        proc = _run_against_mutant(
            "    _verify_producer_duplication(declarations)\n",
            "",
            "tests.test_paper_writing.FactProducerDuplicationTests"
            ".test_two_uncorroborated_producers_of_one_fact_refuse",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_removing_the_corroboration_carve_out_flips_the_legal_pair_test_from_green_to_red(
        self,
    ) -> None:
        """Proves the carve-out is a real branch, not vacuous: without it,
        `gap`'s own corroborated pair would refuse too."""
        proc = _run_against_mutant(
            'len(producer_ids) == 2 and fact_id in paper_verify.CHECKS',
            "False",
            "tests.test_paper_writing.FactProducerDuplicationTests"
            ".test_the_corroborated_pair_of_gap_producers_is_legal",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class FactTotalityTests(unittest.TestCase):
    """`fact-production` spec, `Requirement: Every Producer Is Either Sole
    Or Corroborated`; design.md, Decision D ('Totality is relative to
    consumption'); tasks.md 2.6. Consumption-relative: a fact SOME BLOCK
    REQUIRES (excluding the structural `skeleton` fact) must resolve
    through `paper_declarations.FACT_SOURCE_ROOT` (the five observable
    facts) or a block's `produces_facts`, else refuses
    `FACT_PRODUCER_ABSENT` naming the fact; a produced-class fact nobody
    requires needs no producer at all — an unconditional totality
    invariant is precisely what broke every raw-header fixture in the
    previous change."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def _write(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def test_a_required_fact_with_no_producer_anywhere_refuses(self) -> None:
        header = _produces_facts_section(
            "a", "only", requires=["limitations"], file="sections/01-a.md",
        )
        self._write("01-a.md", header, _produces_facts_body(requires=["limitations"]))

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "FACT_PRODUCER_ABSENT")
        self.assertIn("limitations", ctx.exception.detail)

    def test_a_required_observable_fact_needs_no_block_producer(self) -> None:
        """`dataset` resolves externally (`FACT_SOURCE_ROOT`) — requiring
        it with no `produces_facts` anywhere must not refuse."""
        header = _produces_facts_section(
            "a", "only", requires=["dataset"], file="sections/01-a.md",
        )
        self._write("01-a.md", header, _produces_facts_body(requires=["dataset"]))

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.blocks["a.only"].requires_facts, ("dataset",))

    def test_a_required_fact_with_a_producer_elsewhere_is_accepted(self) -> None:
        header_a = _produces_facts_section(
            "a", "only", requires=["limitations"], file="sections/01-a.md",
        )
        header_a["blocks"][0]["after"] = [
            {
                "target": "b.only",
                "source": {
                    "file": "sections/01-a.md",
                    "quote": "This block requires the limitations.",
                },
            }
        ]
        header_b = _produces_facts_section(
            "b", "only", produces=["limitations"], file="sections/02-b.md",
        )
        self._write(
            "01-a.md", header_a,
            _produces_facts_body(requires=["limitations"], chain_rows=[("a.only", "b.only")]),
        )
        self._write("02-b.md", header_b, _produces_facts_body(produces=["limitations"]))

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.blocks["a.only"].requires_facts, ("limitations",))

    def test_an_unrequired_produced_fact_needs_no_producer_check(self) -> None:
        """Decision D: a produced-class fact nobody requires is simply
        absent from this paper, legally — `produces_facts` alone, with no
        consumer anywhere, must not refuse."""
        header = _produces_facts_section(
            "a", "only", produces=["limitations"], file="sections/01-a.md",
        )
        self._write("01-a.md", header, _produces_facts_body(produces=["limitations"]))

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.blocks["a.only"].produces_facts, ("limitations",))

    def test_removing_the_check_flips_the_refusal_test_from_green_to_red(self) -> None:
        proc = _run_against_mutant(
            "    _verify_fact_totality(corpus, declarations)\n",
            "",
            "tests.test_paper_writing.FactTotalityTests"
            ".test_a_required_fact_with_no_producer_anywhere_refuses",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class ProducerReachabilityTests(unittest.TestCase):
    """`contract-input-partition` spec, `Requirement: A Produced-Fact
    Dependency Is An Internal-Chain Row`; design.md, Decision C ('Ordering
    is VERIFIED, never derived'); tasks.md 2.7. Every one of a produced
    fact's producer(s) must reach the requiring consumer in the
    `after`-edge graph (`collect_edges`/`_build_graph` — the SAME graph
    `derive_order`/`derive_waves` consume); an indirect, transitively
    backed chain is legal, a required DIRECT edge is not."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def _write(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def test_a_consumer_reachable_from_its_producer_is_accepted(self) -> None:
        header_a = _produces_facts_section(
            "a", "only", produces=["limitations"], file="sections/01-a.md",
        )
        header_b = _produces_facts_section(
            "b", "only", requires=["limitations"], file="sections/02-b.md",
        )
        header_b["blocks"][0]["after"] = [
            {
                "target": "a.only",
                "source": {
                    "file": "sections/02-b.md",
                    "quote": "This block requires the limitations.",
                },
            }
        ]
        self._write("01-a.md", header_a, _produces_facts_body(produces=["limitations"]))
        self._write(
            "02-b.md", header_b,
            _produces_facts_body(requires=["limitations"], chain_rows=[("b.only", "a.only")]),
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.blocks["b.only"].requires_facts, ("limitations",))

    def test_a_consumer_not_reachable_from_its_producer_refuses(self) -> None:
        """Same shape as the accepted case above, minus the `after` edge —
        the producer never reaches the consumer."""
        header_a = _produces_facts_section(
            "a", "only", produces=["limitations"], file="sections/01-a.md",
        )
        header_b = _produces_facts_section(
            "b", "only", requires=["limitations"], file="sections/02-b.md",
        )
        self._write("01-a.md", header_a, _produces_facts_body(produces=["limitations"]))
        self._write("02-b.md", header_b, _produces_facts_body(requires=["limitations"]))

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "PRODUCER_CHAIN_ABSENT")
        self.assertIn("b.only", ctx.exception.detail)
        self.assertIn("limitations", ctx.exception.detail)

    def test_unreachable_refuses_at_the_reachability_layer_in_isolation(self) -> None:
        """Unit 4 CRITICAL closure: once `_verify_producer_chain_rows`
        exists, a row can never be present without its backing edge also
        making the consumer trivially (single-hop) reachable -- so on any
        input that reaches `_verify_producer_reachability` at all, the row
        check would independently refuse the SAME totally-unreachable
        input too (mutating out reachability's own call no longer flips
        `test_a_consumer_not_reachable_from_its_producer_refuses`, since
        the row check backstops it). This isolates the reachability
        function itself, on a hand-built `Corpus` with no `after` edges
        anywhere, so its own guard stays independently mutation-provable
        regardless of that overlap."""
        record = paper_graph.BlockRecord(
            section="a", block_id="only", qualified_id="a.only", block_index=0,
            position=1, requires_facts=(), requires_declarations=(),
            citations="none", optional=False, produces_facts=("limitations",),
        )
        consumer = paper_graph.BlockRecord(
            section="b", block_id="only", qualified_id="b.only", block_index=0,
            position=2, requires_facts=("limitations",), requires_declarations=(),
            citations="none", optional=False, produces_facts=(),
        )
        corpus = paper_graph.Corpus(
            sections={
                "a": paper_contract.ContractHeader(section="a", position=1, after=[], blocks=[]),
                "b": paper_contract.ContractHeader(section="b", position=2, after=[], blocks=[]),
            },
            blocks={"a.only": record, "b.only": consumer},
            order_by_section={"a": ["a.only"], "b": ["b.only"]},
        )
        declarations = [("limitations", "a.only")]

        with self.assertRaises(Refused) as ctx:
            paper_graph._verify_producer_reachability(corpus, declarations)

        self.assertEqual(ctx.exception.code, "PRODUCER_CHAIN_ABSENT")
        self.assertIn("a.only", ctx.exception.detail)

    def test_transitive_reachability_through_an_intermediate_block_is_accepted(self) -> None:
        """Design.md Decision C: an indirect chain is legal at the
        REACHABILITY layer — the producer need not directly precede the
        consumer in the `after`-edge graph, only reach it. Calls
        `_verify_producer_reachability` directly against a hand-built
        `Corpus` (this file's own direct-`BlockRecord` construction
        precedent, matching `test_paper_decisions.py`'s), rather than
        through `assemble_corpus`: the full pipeline also runs
        `_verify_producer_chain_rows` (Unit 4, CRITICAL closure —
        `contract-input-partition` spec's added row-presence requirement),
        which DOES demand a direct row backed by a direct edge for every
        produced-fact dependency — an orthogonal, stricter DOCUMENTATION
        discipline this test does not exercise, and one a transitively-
        reached-only chain with no row never satisfies (see
        `ProducerChainRowsTests` for that discipline's own coverage)."""
        def _record(section: str, block_id: str, position: int, *, requires=(), produces=()):
            return paper_graph.BlockRecord(
                section=section, block_id=block_id, qualified_id=f"{section}.{block_id}",
                block_index=0, position=position, requires_facts=tuple(requires),
                requires_declarations=(), citations="none", optional=False,
                produces_facts=tuple(produces),
            )

        source = {"file": "sections/x.md", "quote": "x"}
        corpus = paper_graph.Corpus(
            sections={
                "a": paper_contract.ContractHeader(section="a", position=1, after=[], blocks=[]),
                "mid": paper_contract.ContractHeader(
                    section="mid", position=2, after=[],
                    blocks=[{"id": "only", "after": [{"target": "a.only", "source": source}]}],
                ),
                "c": paper_contract.ContractHeader(
                    section="c", position=3, after=[],
                    blocks=[{"id": "only", "after": [{"target": "mid.only", "source": source}]}],
                ),
            },
            blocks={
                "a.only": _record("a", "only", 1, produces=["limitations"]),
                "mid.only": _record("mid", "only", 2),
                "c.only": _record("c", "only", 3, requires=["limitations"]),
            },
            order_by_section={"a": ["a.only"], "mid": ["mid.only"], "c": ["c.only"]},
        )
        declarations = [("limitations", "a.only")]

        paper_graph._verify_producer_reachability(corpus, declarations)  # raises nothing

        self.assertEqual(corpus.blocks["c.only"].requires_facts, ("limitations",))

    def test_removing_the_check_flips_the_refusal_test_from_green_to_red(self) -> None:
        """Mutates the `_reaches(...)` CONDITION inside the function body,
        not the `assemble_corpus` call site: targets the isolated
        `test_unreachable_refuses_at_the_reachability_layer_in_isolation`
        above, which calls `_verify_producer_reachability` directly and so
        is blind to a call-site mutation. `test_a_consumer_not_reachable_
        from_its_producer_refuses` (through the full `assemble_corpus`
        pipeline) is no longer usable as the target here: `_verify_
        producer_chain_rows` (Unit 4 CRITICAL closure) independently
        refuses the same totally-unreachable input even with this
        function's own guard defeated, since a row can never exist without
        its backing edge also making the consumer reachable."""
        proc = _run_against_mutant(
            "                if not _reaches(successors, producer_id, qualified_id):\n",
            "                if False and not _reaches(successors, producer_id, qualified_id):\n",
            "tests.test_paper_writing.ProducerReachabilityTests"
            ".test_unreachable_refuses_at_the_reachability_layer_in_isolation",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_a_cyclic_corpus_still_surfaces_order_cycle_at_derive_order(self) -> None:
        """tasks.md 2.8: reachability (cycle-tolerant by construction, a
        visited set never unbounded recursion) must not hang and must not
        misreport a cycle as `PRODUCER_CHAIN_ABSENT` here — the cycle
        itself only ever surfaces at `derive_order`/`derive_waves`."""
        header_a = _produces_facts_section(
            "a", "cyc-a", produces=["limitations"], file="sections/01-a.md",
        )
        header_a["blocks"][0]["after"] = [
            {
                "target": "b.cyc-b",
                "source": {"file": "sections/01-a.md", "quote": "This block produces the limitations."},
            }
        ]
        header_b = _produces_facts_section(
            "b", "cyc-b", requires=["limitations"], file="sections/02-b.md",
        )
        header_b["blocks"][0]["after"] = [
            {
                "target": "a.cyc-a",
                "source": {"file": "sections/02-b.md", "quote": "This block requires the limitations."},
            }
        ]
        self._write("01-a.md", header_a, _produces_facts_body(produces=["limitations"]))
        self._write(
            "02-b.md", header_b,
            _produces_facts_body(requires=["limitations"], chain_rows=[("b.cyc-b", "a.cyc-a")]),
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing here

        edges = paper_graph.collect_edges(corpus)
        with self.assertRaises(Refused) as ctx:
            paper_graph.derive_order(corpus, edges)
        self.assertEqual(ctx.exception.code, "ORDER_CYCLE")


class ProducerChainRowsTests(unittest.TestCase):
    """`contract-input-partition` spec, `Requirement: A Produced-Fact
    Dependency Is An Internal-Chain Row` (`sdd-verify` FAIL, CRITICAL,
    `a-fact-is-declared-or-it-is-produced` Unit 4): `_verify_producer_
    reachability` alone proved a producer reaches its consumer somewhere in
    the `after`-edge graph, but never checked that the consumer's OWN
    `### Internal chain` table actually SAYS so in prose — a real `after`
    edge with the row absent assembled clean before this unit, the exact
    defect class this whole change exists to close. `_verify_producer_
    chain_rows` is the mirror `_verify_internal_chain` was always missing:
    that function proves ROW -> edge; this proves EDGE (fact-requirement) ->
    row."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def _write(self, filename: str, header: dict, body: str) -> None:
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def _write_pair(self, *, chain_rows=()) -> None:
        """A producer (`a.only`) and a consumer (`b.only`) joined by a REAL,
        DIRECT `after` edge -- reachability always holds here. `chain_rows`
        controls only whether the consumer's own `### Internal chain` table
        names the producer."""
        header_a = _produces_facts_section(
            "a", "only", produces=["limitations"], file="sections/01-a.md",
        )
        header_b = _produces_facts_section(
            "b", "only", requires=["limitations"], file="sections/02-b.md",
        )
        header_b["blocks"][0]["after"] = [
            {
                "target": "a.only",
                "source": {
                    "file": "sections/02-b.md",
                    "quote": "This block requires the limitations.",
                },
            }
        ]
        self._write("01-a.md", header_a, _produces_facts_body(produces=["limitations"]))
        self._write(
            "02-b.md", header_b,
            _produces_facts_body(requires=["limitations"], chain_rows=chain_rows),
        )

    def test_a_direct_edge_with_the_row_present_is_accepted(self) -> None:
        """`contract-input-partition` spec, `Scenario: A producer->consumer
        row is accepted`."""
        self._write_pair(chain_rows=[("b.only", "a.only")])

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # raises nothing

        self.assertEqual(corpus.blocks["b.only"].requires_facts, ("limitations",))

    def test_a_direct_edge_with_the_row_absent_refuses(self) -> None:
        """The decisive case: a REAL `after` edge reaches the consumer from
        its producer (`_verify_producer_reachability` alone would accept
        this corpus with no refusal), yet no `### Internal chain` row names
        the producer -- `contract-input-partition` spec, `Scenario: A
        missing producer row refuses`. This is the exact shape that
        assembled CLEAN before this unit: `_verify_producer_reachability`
        was satisfied by the edge alone, and nothing else ever read the
        row."""
        self._write_pair(chain_rows=())

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "PRODUCER_CHAIN_ABSENT")
        self.assertIn("b.only", ctx.exception.detail)
        self.assertIn("limitations", ctx.exception.detail)
        self.assertIn("a.only", ctx.exception.detail)

    def test_mutation_removing_the_row_after_it_existed_is_caught(self) -> None:
        """`contract-input-partition` spec, `Scenario: Mutation — removing
        the row after it existed is caught`: the row set is read live off
        the current prose body on every assembly, never cached from a prior
        pass, even though `requires_facts` for the fact never changes."""
        self._write_pair(chain_rows=[("b.only", "a.only")])
        paper_graph.assemble_corpus(self.sections_dir)  # raises nothing, row present

        self._write_pair(chain_rows=())  # same requires_facts, row deleted

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "PRODUCER_CHAIN_ABSENT")

    def test_a_self_producing_block_needs_no_row_on_itself(self) -> None:
        """`FACT_SELF_REQUIRED` (`_verify_self_reference`, run earlier in
        `assemble_corpus`) already refuses a block that both requires and
        produces the same fact, so `_verify_producer_chain_rows` can never
        reach that shape through the real pipeline — this calls it
        directly, on a hand-built `Corpus` bypassing that earlier check, to
        prove its own `producer_id == qualified_id` skip (mirroring `_
        verify_producer_reachability`'s identical skip) never asks a
        producer to carry a row naming itself, rather than merely being
        unreachable by construction."""
        record = paper_graph.BlockRecord(
            section="a", block_id="only", qualified_id="a.only", block_index=0,
            position=1, requires_facts=("limitations",), requires_declarations=(),
            citations="none", optional=False, produces_facts=("limitations",),
        )
        corpus = paper_graph.Corpus(
            sections={"a": paper_contract.ContractHeader(section="a", position=1, after=[], blocks=[])},
            blocks={"a.only": record},
            order_by_section={"a": ["a.only"]},
        )
        declarations = [("limitations", "a.only")]

        paper_graph._verify_producer_chain_rows(corpus, declarations, {"a": b"Prose.\n"})  # raises nothing

    def test_removing_the_check_flips_the_refusal_test_from_green_to_red(self) -> None:
        proc = _run_against_mutant(
            "    _verify_producer_chain_rows(corpus, declarations, section_bodies)\n",
            "",
            "tests.test_paper_writing.ProducerChainRowsTests"
            ".test_a_direct_edge_with_the_row_absent_refuses",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class MethodsProducesContributionsMutationTests(unittest.TestCase):
    """`the-methods-section-produces-the-contributions`, tasks.md Phase 4
    (4.1-4.3): mutation proofs against a COPY of the real, shipped
    `sections/` tree (`SECTIONS_DIR` itself is never written to — copied
    fresh per test, then mutated). Each test proves the specific guard this
    change relies on can actually FIRE (MAINTENANCE pattern 2: a guard
    that merely exists is not the same as one that is reachable), then
    confirms the real, unmutated shipped corpus still assembles clean —
    proving the shipped edit, not the mutation, is what ships."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        shutil.copytree(SECTIONS_DIR, self.sections_dir)

    def _mutate(self, filename: str, old: str, new: str) -> None:
        path = self.sections_dir / filename
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"{filename}: anchor text not found -- fixture drifted")
        self.assertEqual(text.count(old), 1, f"{filename}: anchor text is not unique in this file")
        path.write_text(text.replace(old, new), encoding="utf-8")

    def test_deleting_block_4b_new_row_refuses_producer_chain_absent(self) -> None:
        """Task 4.1: `introduction.block-4b`'s own new `### Internal chain`
        row is the only prose evidence that `mm-proposal` must precede it.
        Deleting the row while its `after` edge and `requires_facts` entry
        stay intact refuses `PRODUCER_CHAIN_ABSENT` -- the edge alone still
        makes `block-4b` reachable from `mm-proposal`, so only the row
        check (the documentation-direction mirror `_verify_producer_
        chain_rows` adds) catches this."""
        self._mutate(
            "06-introduction.md",
            "| `introduction.block-4b` — the list of contributions, inherited rather than "
            "drafted | `materials-and-methods.mm-proposal` — the section that defines and "
            "names each contribution |\n",
            "",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)
        self.assertEqual(ctx.exception.code, "PRODUCER_CHAIN_ABSENT")
        self.assertIn("introduction.block-4b", ctx.exception.detail)
        self.assertIn("materials-and-methods.mm-proposal", ctx.exception.detail)

        paper_graph.assemble_corpus(SECTIONS_DIR)  # the real, unmutated corpus: raises nothing

    def test_deleting_a_retargeted_after_edge_refuses_chain_row_unbacked(self) -> None:
        """Task 4.2: one of the six retargeted consumers
        (`experimental-setup.es-assessment`) still carries its `### Internal
        chain` row naming `mm-proposal`, but its backing `after` edge is
        deleted -- refuses `CHAIN_ROW_UNBACKED`, the row -> edge mirror of
        4.1's edge -> row check."""
        self._mutate(
            "02-experimental-setup.md",
            '        {\n'
            '          "target": "materials-and-methods.mm-proposal",\n'
            '          "source": {\n'
            '            "file": "sections/02-experimental-setup.md",\n'
            '            "quote": "Which property each contribution claims — if it was '
            'promised, this is where its instrument is named"\n'
            '          }\n'
            '        },\n',
            "",
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)
        self.assertEqual(ctx.exception.code, "CHAIN_ROW_UNBACKED")
        self.assertIn("experimental-setup.es-assessment", ctx.exception.detail)
        self.assertIn("materials-and-methods.mm-proposal", ctx.exception.detail)

        paper_graph.assemble_corpus(SECTIONS_DIR)  # the real, unmutated corpus: raises nothing

    def test_reviving_block_4b_as_a_second_producer_refuses_duplicate(self) -> None:
        """Task 4.3 (`fact-production` spec, 'Reviving the old producer
        duplicates it'): restoring `block-4b`'s dropped `produces_facts:
        contributions` entry alongside `mm-proposal`'s own (which stays)
        refuses `FACT_PRODUCER_DUPLICATE` -- `_verify_producer_duplication`
        runs before `_verify_self_reference` in `assemble_corpus`, so this
        is reached even though `block-4b` also still requires the fact it
        would now also produce."""
        self._mutate(
            "06-introduction.md",
            '"requires_declarations": [],\n'
            '      "citations": "none",\n'
            '      "after": [\n'
            '        {\n'
            '          "target": "materials-and-methods.mm-proposal",',
            '"requires_declarations": [],\n'
            '      "citations": "none",\n'
            '      "produces_facts": [\n'
            '        {\n'
            '          "value": "contributions",\n'
            '          "source": {\n'
            '            "file": "sections/06-introduction.md",\n'
            '            "quote": "It is inherited, never a drafting target."\n'
            '          }\n'
            '        }\n'
            '      ],\n'
            '      "after": [\n'
            '        {\n'
            '          "target": "materials-and-methods.mm-proposal",',
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)
        self.assertEqual(ctx.exception.code, "FACT_PRODUCER_DUPLICATE")
        self.assertIn("contributions", ctx.exception.detail)

        paper_graph.assemble_corpus(SECTIONS_DIR)  # the real, unmutated corpus: raises nothing


class ComponentsCheckSelfReferenceFalsifierTests(unittest.TestCase):
    """`design.md` D2, falsifier (1) (tasks.md 4.4): after the move,
    `materials-and-methods.mm-proposal` is `contributions`' sole producer
    AND the one block whose own diagram checks against it -- an intra-block
    check, never cross-section corroboration. Calls `paper_cli._resolve_
    expected_components` directly against the REAL shipped `sections/`
    (never mutated) with a synthetic rendered `main.tex` standing in for
    `mm-proposal`'s own body (the real `paper/main.tex` carries it empty
    today -- design.md's own measured note), proving the resolved roster is
    read from THIS block's own rendered text, and that altering one item
    changes what `paper_obligation.check_components` accepts."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    def _write_roster(self, *items: str) -> None:
        body = b"Prose stating the proposal.\n\n\\begin{itemize}\n"
        for item in items:
            body += f"\\item {item}\n".encode("utf-8")
        body += b"\\end{itemize}\n\nClosing prose.\n"
        main_tex = _marker_pair("materials-and-methods.mm-proposal", body)
        _write_fixture(self.paper_dir, main_tex)

    def test_the_resolved_roster_is_read_from_mm_proposals_own_body(self) -> None:
        self._write_roster("Adaptive Caching", "Robust Fallback")

        items = paper_cli._resolve_expected_components(self.paper_dir, SECTIONS_DIR, "contributions")

        self.assertEqual(items, ["Adaptive Caching", "Robust Fallback"])

    def test_mutating_one_roster_item_turns_a_passing_diagram_into_a_mismatch(self) -> None:
        figure = {"ordered": True}
        manifest = ["Adaptive Caching", "Robust Fallback"]  # the diagram's own declared labels

        self._write_roster("Adaptive Caching", "Robust Fallback")
        matching = paper_cli._resolve_expected_components(self.paper_dir, SECTIONS_DIR, "contributions")
        paper_obligation.check_components(figure, manifest, matching)  # raises nothing

        self._write_roster("Adaptive Caching", "Mutated Fallback")
        mutated = paper_cli._resolve_expected_components(self.paper_dir, SECTIONS_DIR, "contributions")

        self.assertNotEqual(matching, mutated)
        with self.assertRaises(Refused) as ctx:
            paper_obligation.check_components(figure, manifest, mutated)
        self.assertEqual(ctx.exception.code, "COMPONENT_MISMATCH")


class WaveOrderingPropertyTests(unittest.TestCase):
    """`design.md` Testing Strategy, Property row (tasks.md 4.5): every
    block's `after` dependency lands in a strictly earlier wave than the
    block itself, checked as a PROPERTY over the real shipped corpus's full
    edge set -- no wave count or shape is asserted here (pattern 7 of
    `MAINTENANCE-seven-ways-to-fail-green.md`; the exact,
    re-measured shape is asserted, dated, only in `SKILL.md`)."""

    def test_every_after_dependency_resolves_to_a_strictly_earlier_wave(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        edge_set = paper_graph.collect_edges(corpus)
        waves = paper_graph.derive_waves(corpus, edge_set)

        wave_of = {}
        for wave_index, qualified_ids in enumerate(waves):
            for qualified_id in qualified_ids:
                wave_of[qualified_id] = wave_index

        self.assertEqual(
            set(wave_of), set(corpus.blocks), "every block must land in exactly one wave",
        )

        checked = 0
        for before, after, _source in edge_set.edges:
            self.assertLess(
                wave_of[before], wave_of[after],
                f"{before} must resolve to a strictly earlier wave than {after}",
            )
            checked += 1
        self.assertGreater(checked, 0, "no `after` edges were checked -- the corpus carries none")


class ProducerMoveIntegrationTests(unittest.TestCase):
    """tasks.md 4.6: `assemble_corpus` + `derive_order` succeed against the
    real shipped corpus, acyclic, with `materials-and-methods.mm-proposal`
    as `contributions`' sole producer."""

    def test_the_shipped_corpus_assembles_acyclic_with_mm_proposal_the_sole_producer(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)  # raises nothing

        producers = paper_graph.producers_by_fact(corpus)
        self.assertEqual(producers["contributions"], ("materials-and-methods.mm-proposal",))

        edge_set = paper_graph.collect_edges(corpus)
        order = paper_graph.derive_order(corpus, edge_set)  # raises ORDER_CYCLE if cyclic

        self.assertEqual(set(order), set(corpus.blocks))
        self.assertLess(
            order.index("materials-and-methods.mm-proposal"),
            order.index("introduction.block-4b"),
            "the producer must be written before its consumer",
        )


class RequirementCorpusEqualityGoldenTests(unittest.TestCase):
    """`design.md`, Testing Strategy, 'Corpus — equality': `{qid:
    record.requires_facts}` / `.requires_declarations` over the shipped
    corpus, snapshotted as a frozen golden literal — U3's operator ruling
    (`unanchored-requirements.md`) appears here as an explicit, itemized
    diff against the pre-ruling (post-U2) derived value set, and nowhere
    else.

    `the-methods-section-produces-the-contributions` re-measured and
    re-recorded exactly one entry: `introduction.block-4b` gained
    `contributions` (`materials-and-methods.mm-proposal` is now its sole
    producer, and `block-4b` requires the fact it used to produce),
    appended last so the tuple order matches the header's own
    `requires_facts` declaration order."""

    #: `experimental-setup.es-assessment`'s pre-ruling `requires_facts`
    #: value set, and `title-and-keywords.keywords`'s — the exact two
    #: blocks the ruling touched (`unanchored-requirements.md`, rows 3
    #: and 4: both ruled "A — spurious").
    _PRE_RULING_FACTS = {
        "experimental-setup.es-assessment": (
            "dataset", "contributions", "experimental-design", "gap",
        ),
        "title-and-keywords.keywords": ("contributions",),
    }

    #: The full post-U3 snapshot, `{qualified_id: requires_facts}`,
    #: measured directly against the shipped corpus once U3's code and
    #: ruling both landed — the golden this test compares against.
    _GOLDEN_FACTS = {
        "abstract.slot-1": ("dataset",),
        "abstract.slot-2": ("contributions",),
        "abstract.slot-3": ("contributions",),
        "abstract.slot-4": ("contributions", "results"),
        "abstract.slot-5": ("experimental-design",),
        "abstract.slot-6": ("results",),
        "abstract.slot-7": ("results",),
        "back-matter.bm-acknowledgments": (),
        "back-matter.bm-appendices": (),
        "back-matter.bm-author-contributions": (),
        "back-matter.bm-conflicts-of-interest": (),
        "back-matter.bm-data-availability": (),
        "back-matter.bm-funding": (),
        "conclusions.concl-block-1": ("contributions",),
        "conclusions.concl-block-2": ("results",),
        "conclusions.concl-block-3": (),
        "conclusions.concl-block-4": ("limitations",),
        "experimental-setup.es-assessment": ("contributions", "experimental-design", "gap"),
        "experimental-setup.es-dataset": ("dataset",),
        "experimental-setup.es-preamble": (),
        "experimental-setup.es-training-details": ("implementation",),
        "introduction.block-1": ("dataset",),
        "introduction.block-2": ("contributions",),
        "introduction.block-3": ("problem-statement",),
        "introduction.block-4a": ("contributions",),
        "introduction.block-4b": ("results", "contributions"),
        "introduction.block-5": ("experimental-design", "results"),
        "introduction.block-6": ("skeleton",),
        "limitations.lim-closing": (),
        "limitations.lim-failure-mode": ("results",),
        "limitations.lim-opening-concession": ("results",),
        "limitations.lim-proposal-items": ("contributions",),
        "limitations.lim-validation-items": ("experimental-design",),
        "materials-and-methods.mm-borrowed-machinery": ("formulation",),
        "materials-and-methods.mm-dataset": ("dataset",),
        "materials-and-methods.mm-preamble": (),
        "materials-and-methods.mm-proposal": ("formulation",),
        "related-work.rw-closing": (),
        "related-work.rw-panorama": ("problem-statement",),
        "related-work.rw-preamble": ("problem-statement",),
        "related-work.rw-problem-blocks": ("problem-statement",),
        "related-work.rw-synthesis-artefact": ("contributions",),
        "results-and-discussion.rd-contribution-blocks": ("contributions", "results"),
        "results-and-discussion.rd-cost": ("results", "implementation"),
        "results-and-discussion.rd-general-task": ("results",),
        "title-and-keywords.keywords": (),
        "title-and-keywords.title": ("contributions",),
    }

    def test_the_shipped_corpus_matches_the_golden_modulo_the_dp_ruling(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        current_facts = {qid: record.requires_facts for qid, record in corpus.blocks.items()}

        self.assertEqual(
            current_facts, self._GOLDEN_FACTS,
            "the shipped corpus's derived requires_facts drifted from the frozen "
            "golden -- if this is an intentional change, it must be re-measured "
            "and re-recorded, never hand-patched to make the assertion pass",
        )

        for qid, pre_ruling in self._PRE_RULING_FACTS.items():
            self.assertNotEqual(
                current_facts[qid], pre_ruling,
                f"{qid}: the operator ruling was supposed to change this block's "
                "requires_facts and the golden shows it unchanged",
            )


class ContractHeaderTests(unittest.TestCase):
    """`a-diagram-that-compiles-or-says-why`, `section-contract` spec
    delta: `figure` joins `_BLOCK_OPTIONAL`, five subkeys required and
    `components_from` optional (tasks.md 3.1/3.2/3.6; `components_from`
    widened to optional by this change's own corrective amendment —
    verify FAIL, CRITICAL finding on `es-assessment`)."""

    _FIGURE = {
        "components_from": "contributions", "ordered": True,
        "excludes": ["dataset", "baseline"], "caption_enumerates": True,
        "caption_decodes": True, "mandatory": True,
    }

    def _header(self, figure=None) -> dict:
        block = {
            "id": "b1",
            "requires_facts": [
                {
                    "value": "contributions",
                    "source": {"file": "sections/00-demo.md", "quote": "The contributions."},
                }
            ],
            "requires_declarations": [],
            "citations": "none",
        }
        if figure is not None:
            block["figure"] = figure
        return {"section": "demo", "position": 1, "blocks": [block]}

    def test_a_valid_figure_object_parses(self) -> None:
        header = paper_contract.parse_header(self._header(figure=self._FIGURE))
        self.assertEqual(header.blocks[0]["figure"], self._FIGURE)

    def test_no_figure_key_resolves_to_none(self) -> None:
        header = paper_contract.parse_header(self._header())
        self.assertIsNone(header.blocks[0]["figure"])

    def test_a_figure_object_missing_a_subkey_refuses_malformed_figure_obligation(self) -> None:
        broken = {k: v for k, v in self._FIGURE.items() if k != "caption_decodes"}
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(figure=broken))
        self.assertEqual(ctx.exception.code, "MALFORMED_FIGURE_OBLIGATION")
        self.assertIn("caption_decodes", ctx.exception.detail)

    def test_a_figure_object_with_an_unknown_key_refuses_malformed_figure_obligation(self) -> None:
        broken = dict(self._FIGURE, extra_key="nope")
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(figure=broken))
        self.assertEqual(ctx.exception.code, "MALFORMED_FIGURE_OBLIGATION")

    def test_an_unknown_components_from_fact_refuses_unknown_fact(self) -> None:
        broken = dict(self._FIGURE, components_from="not-a-real-fact")
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(figure=broken))
        self.assertEqual(ctx.exception.code, "UNKNOWN_FACT")

    def test_a_non_boolean_ordered_refuses_malformed_figure_obligation(self) -> None:
        broken = dict(self._FIGURE, ordered="yes")
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(figure=broken))
        self.assertEqual(ctx.exception.code, "MALFORMED_FIGURE_OBLIGATION")

    def test_a_non_string_excludes_entry_refuses_malformed_figure_obligation(self) -> None:
        broken = dict(self._FIGURE, excludes=[1, 2])
        with self.assertRaises(Refused) as ctx:
            paper_contract.parse_header(self._header(figure=broken))
        self.assertEqual(ctx.exception.code, "MALFORMED_FIGURE_OBLIGATION")

    def test_a_figure_object_without_components_from_parses(self) -> None:
        """Corrective amendment: `components_from` is optional — a block
        whose diagram is a composite crossing over several categories of
        content, none of which alone is the full expected list (section
        02's closing diagram), declares no `components_from` at all rather
        than being wired to one fact's partial value."""
        without_components_from = {k: v for k, v in self._FIGURE.items() if k != "components_from"}
        header = paper_contract.parse_header(self._header(figure=without_components_from))
        self.assertIsNone(header.blocks[0]["figure"]["components_from"])

    def test_an_explicit_null_components_from_also_resolves_to_none(self) -> None:
        """Same `raw.get(...) is not None` round-trip convention `mode`
        already uses: this parser's own output re-serializes with an
        explicit `"components_from": null`, and re-parsing that MUST mean
        the same thing as the key being absent."""
        with_null = dict(self._FIGURE, components_from=None)
        header = paper_contract.parse_header(self._header(figure=with_null))
        self.assertIsNone(header.blocks[0]["figure"]["components_from"])


def _derive_figure_holders(sections_dir: Path = SECTIONS_DIR) -> list:
    """`[(filename, block_id), ...]` for EVERY block in `sections_dir` that
    declares a `figure:` obligation -- DERIVED by parsing every real
    `sections/*.md` file's own header, never a fixed list of ids typed by
    hand.

    W3 (`a-diagram-that-compiles-or-says-why`'s corrective re-verify,
    WARNING): this class used to hard-code a `_HOLDERS = {...}` dict of
    exactly three known ids. A hand-typed list like that is complete by
    coincidence, not by construction -- it can never notice a NEW
    figure-declaring block added later, because nothing forces whoever adds
    one to also remember to update a dict elsewhere in a different file.
    Module-level (not a class attribute) so a mutated COPY of the corpus
    can also be scanned from `tests/test_paper_figure.py`'s own mutation
    proof, without needing to instantiate this TestCase.

    W3's OWN re-verify (latent WARNING, cousin of the same finding class):
    the first version of this derivation replaced the hand-typed dict with
    a FRESH `dict[str, str]` keyed by `path.name`, assigned INSIDE the loop
    over that file's own blocks -- `holders[path.name] = block["id"]`. A
    second figure-declaring block in the same file silently overwrote the
    first, reopening the exact collapse this function exists to close.
    Nothing in the real corpus exercised it (each of the three real
    figure-declaring contracts holds exactly one such block), so it was
    unreachable, not absent. A list of `(filename, block_id)` pairs cannot
    collapse the same way -- proven by
    `FigureHolderDerivationDoesNotCollapseTests`, which builds a synthetic
    contract with two figure-declaring blocks in one file and confirms both
    survive."""
    holders: list = []
    for path in sorted(sections_dir.glob("*.md")):
        header, _body = paper_contract.parse(path.read_bytes())
        for block in header.blocks:
            if block["figure"] is not None:
                holders.append((path.name, block["id"]))
    return holders


def _assert_proof_classified_blocks_carry_their_derivation(
    sections_dir: Path, holders: list, realism_proof: dict,
) -> None:
    """For every derived `(filename, block_id)` classified `"proof:..."` in
    `realism_proof`, the REAL, on-disk header at `sections_dir` MUST
    currently declare a non-null `figure.components_from` for that block --
    read fresh from disk every call, never assumed from yesterday's shape.

    W3: a `"proof:..."` entry asserts a named test proves this block's
    Components Check is load-bearing; that claim is only true while the
    contract still names a fact for it. `components_from` moved from
    required to optional to close the original CRITICAL (a check silently
    wired to nothing); the cheapest way to reopen the identical hole is for
    a future edit to drop the field from a `"proof:..."`-classified block
    without also reclassifying its entry to `"exempt:<reason>"`. Raises
    `AssertionError` (not a `self.assert*` call) so this same function is
    callable, and its failure observable, from OUTSIDE a `TestCase` --
    `tests/test_paper_figure.py`'s own mutation proof calls this directly
    against a mutated copy and asserts it raises."""
    for filename, block_id in holders:
        entry = realism_proof.get(block_id)
        if entry is None or not entry.startswith("proof:"):
            continue
        header, _body = paper_contract.parse((sections_dir / filename).read_bytes())
        block = next(b for b in header.blocks if b["id"] == block_id)
        figure = block["figure"]
        if figure is None or figure["components_from"] is None:
            raise AssertionError(
                f"{filename}: {block_id} is classified {entry!r} (a load-bearing Components "
                "Check proof), but its real figure.components_from is now None -- either "
                "restore the field or reclassify this entry to 'exempt:<reason>'"
            )


class FigureHolderDerivationDoesNotCollapseTests(unittest.TestCase):
    """`a-diagram-that-compiles-or-says-why`'s re-verify, WARNING (latent):
    `_derive_figure_holders` built its `dict[str, str]` return by assigning
    `holders[path.name] = block["id"]` INSIDE the loop over that file's own
    blocks -- exactly the shape it exists to close (a second figure-
    declaring block in the same contract silently overwrites the first, and
    that block then drops out of every anti-drift check reading this map).
    No real `sections/*.md` file currently holds two such blocks, so this
    was unreachable through the corpus; it is reachable through a
    synthetic contract that names it directly."""

    _FIGURE = {
        "ordered": False, "excludes": [], "caption_enumerates": False,
        "caption_decodes": False, "mandatory": False,
    }

    def _two_figure_block_header(self) -> dict:
        block = {
            "id": None, "requires_facts": [], "requires_declarations": [], "citations": "none",
            "figure": dict(self._FIGURE),
        }
        first = dict(block, id="fig-a")
        second = dict(block, id="fig-b")
        return {"section": "demo", "position": 1, "blocks": [first, second]}

    def test_two_figure_declaring_blocks_in_one_file_both_survive_derivation(self) -> None:
        header_dict = self._two_figure_block_header()
        # Round-trips through the real parser first, matching every other
        # fixture in this module -- a malformed synthetic header would prove
        # nothing about the real collapse.
        paper_contract.parse_header(header_dict)

        file_bytes = b"---\n" + json.dumps(header_dict).encode("utf-8") + b"\n---\nbody\n"
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp) / "sections"
            sections_dir.mkdir()
            (sections_dir / "two-figures.md").write_bytes(file_bytes)

            holders = _derive_figure_holders(sections_dir)

        holder_block_ids = [block_id for filename, block_id in holders if filename == "two-figures.md"]
        self.assertIn(
            "fig-a", holder_block_ids,
            "fig-a dropped out of the derivation -- the second block overwrote it",
        )
        self.assertIn(
            "fig-b", holder_block_ids,
            "fig-b dropped out of the derivation -- a same-filename collapse lost a block",
        )


class FigureObligationTranscriptionTests(unittest.TestCase):
    """design.md, `Open Questions`: "a test asserts each `excludes` entry and
    the `components_from` fact name occur in the holder contract's prose,
    whitespace-normalised." Scoped to the PROSE below the header fence, not
    the JSON header itself -- a components_from/excludes value that only
    ever appeared inside the machine-written header would prove nothing
    about a human having stated it (design.md's own narrower-than-the-
    sibling's scoping note)."""

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.split())

    def test_every_excludes_entry_and_components_from_occur_in_the_holders_own_prose(self) -> None:
        for filename, block_id in _derive_figure_holders():
            path = SECTIONS_DIR / filename
            header, body = paper_contract.parse(path.read_bytes())
            block = next(b for b in header.blocks if b["id"] == block_id)
            figure = block["figure"]
            self.assertIsNotNone(figure, f"{filename}: {block_id} declares no figure")
            prose = self._normalize(body.decode("utf-8"))
            if figure["components_from"] is not None:
                self.assertIn(
                    self._normalize(figure["components_from"]), prose,
                    f"{filename}: components_from {figure['components_from']!r} not found in prose",
                )
            for excluded in figure["excludes"]:
                self.assertIn(
                    self._normalize(excluded), prose,
                    f"{filename}: excludes entry {excluded!r} not found in prose",
                )

    #: Fixing the CLASS, not just the instance (`a-diagram-that-compiles-
    #: or-says-why`, corrective verify FAIL): a transcription lock that
    #: only checks a word's presence in prose licenses any value that
    #: happens to share that word — measured directly: `components_from:
    #: "dataset"` passed the substring check above while inverting
    #: `paper_obligation.check_components` for `es-assessment` (a
    #: prose-compliant diagram refused, a degenerate one passed). Every
    #: block that declares `figure:` MUST ALSO be named here against either
    #: an EXECUTED realism proof living in `tests/test_paper_figure.py`
    #: (`"proof:<TestClass>.<test_method>"`, resolved against that file's
    #: own AST below so a stale reference fails loudly, not silently) or an
    #: explicit, human-readable exemption reason (`"exempt:<reason>"`) for
    #: a block whose obligation is conditional and never mechanically
    #: checked at all (section 05's table-or-diagram choice; and now
    #: `es-assessment`, whose composite crossing means it correctly
    #: declares no `components_from` at all — see the corrective fix
    #: below).
    _COMPONENTS_REALISM_PROOF = {
        "mm-proposal": "proof:ObligationTests.test_matching_ordered_components_pass",
        "es-assessment": (
            "exempt:components_from removed entirely (corrective fix, verify FAIL CRITICAL): "
            "the closing diagram is a composite crossing over six categories of content that no "
            "single fact's value can equal, so no Components Check is wired to it at all -- there "
            "is no longer a possible verdict to invert. See test_paper_figure.py, "
            "Section02ComponentsCheckOmittedTests and CLIWiringTests."
            "test_real_section_02_es_assessment_no_longer_inverts_the_components_check"
        ),
        "rw-synthesis-artefact": (
            "exempt:mandatory=false, and a table choice leaves no <id>.tex — no component check "
            "is ever reachable for this block (design.md, 'The 05 conditional, expressed in data "
            "rather than a new key'; ObligationTests."
            "test_a_table_choice_for_block_05_carries_no_diagram_obligation)"
        ),
    }

    def test_every_figure_declaring_block_names_a_realism_proof_or_an_exemption(self) -> None:
        figure_test_source = (FORGE_ROOT / "tests" / "test_paper_figure.py").read_text(encoding="utf-8")
        tree = ast.parse(figure_test_source)
        methods_by_class: dict[str, set] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods_by_class[node.name] = {
                    child.name for child in node.body if isinstance(child, ast.FunctionDef)
                }

        for filename, block_id in _derive_figure_holders():
            self.assertIn(
                block_id, self._COMPONENTS_REALISM_PROOF,
                f"{filename}: {block_id} declares figure: but names no realism proof or exemption",
            )
            entry = self._COMPONENTS_REALISM_PROOF[block_id]
            if entry.startswith("proof:"):
                class_name, _, method_name = entry[len("proof:"):].partition(".")
                self.assertIn(
                    class_name, methods_by_class,
                    f"{block_id}: proof names class {class_name!r}, absent from test_paper_figure.py",
                )
                self.assertIn(
                    method_name, methods_by_class[class_name],
                    f"{block_id}: proof names {class_name}.{method_name}, no such test method",
                )
            else:
                self.assertTrue(
                    entry.startswith("exempt:") and len(entry) > len("exempt:"),
                    f"{block_id}: exemption entry must state a non-empty reason: {entry!r}",
                )

    def test_every_proof_classified_block_currently_carries_the_derivation_it_claims(self) -> None:
        """W3 (`a-diagram-that-compiles-or-says-why`'s corrective re-verify,
        WARNING): `components_from` moved from required to optional to
        close the original CRITICAL. Optionality is itself the cheapest way
        to reopen the identical hole by silent omission -- nothing before
        this test locked the REAL, on-disk `mm-proposal` header to keep
        declaring `components_from`; a future edit could drop it and every
        existing test would stay green, because the one existing
        transcription-lock test
        (`test_every_figure_declaring_block_names_a_realism_proof_or_an_
        exemption`) only checks that a NAMED test method still exists in
        `test_paper_figure.py`, never that the real header still matches
        the classification. Proven load-bearing, not merely asserted, by
        `tests/test_paper_figure.py`'s own
        `ComponentsFromDerivationGuardTests` -- it calls the exact function
        this test calls, against a mutated copy of this real file, and
        confirms the guard raises."""
        holders = _derive_figure_holders(SECTIONS_DIR)
        try:
            _assert_proof_classified_blocks_carry_their_derivation(
                SECTIONS_DIR, holders, self._COMPONENTS_REALISM_PROOF,
            )
        except AssertionError as exc:
            self.fail(str(exc))


class RedactorInputContractTests(unittest.TestCase):
    """`evidence-bound-drafting` spec, `Requirement: Redactor Input
    Contract`."""

    def test_empty_style_set_is_a_valid_input(self) -> None:
        redactor_input = paper_bindings.RedactorInput(
            contract_prose="Some contract prose.", evidence_set=(), mode="transposition", style_set=(),
        )
        self.assertEqual(redactor_input.style_set, ())
        self.assertEqual(redactor_input.contract_prose, "Some contract prose.")

    def test_the_shape_carries_exactly_five_fields(self) -> None:
        """`design.md` D3: the field count is the shape's only enforcement
        -- `RedactorInput` has no production constructor, so a fifth field
        appended without this assertion could silently drift unnoticed."""
        self.assertEqual(len(dataclasses.fields(paper_bindings.RedactorInput)), 5)

    def test_source_sections_round_trips_as_a_keyword(self) -> None:
        section = {
            "fact": "formulation", "lineage": "widget-cascade", "title": "3. Something",
            "path": "proposals/widget-cascade-r21.md", "byte_start": 0, "byte_end": 10,
            "text": "Some text.",
        }
        redactor_input = paper_bindings.RedactorInput(
            contract_prose="Some contract prose.", evidence_set=(), mode="transposition",
            style_set=(), source_sections=(section,),
        )
        self.assertEqual(redactor_input.source_sections, (section,))


class BindingMapTests(unittest.TestCase):
    """`evidence-bound-drafting` spec, `Requirement: Binding Map
    Production`, `Requirement: Draft-Versus-Map Reconciliation`,
    `Requirement: Binding Resolution`."""

    def test_every_binding_entry_names_one_of_the_three_kinds(self) -> None:
        for raw, expected in (
            ("evidence:E1", ("evidence", "E1")),
            ("fact:results", ("fact", "results")),
            ("structural", ("structural", None)),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(paper_bindings.parse_binding(raw), expected)

    def test_an_unbound_sentence_refuses(self) -> None:
        latex = "First sentence. Second sentence."
        bindings = [{"sentence": "First sentence.", "binding": "structural"}]
        with self.assertRaises(Refused) as ctx:
            paper_bindings.reconcile(latex, bindings)
        self.assertEqual(ctx.exception.code, "UNBOUND_SENTENCE")
        self.assertIn("Second sentence.", ctx.exception.detail)

    def test_an_orphaned_binding_refuses(self) -> None:
        latex = "Only sentence here."
        bindings = [
            {"sentence": "Only sentence here.", "binding": "structural"},
            {"sentence": "Nothing drafted matches this.", "binding": "structural"},
        ]
        with self.assertRaises(Refused) as ctx:
            paper_bindings.reconcile(latex, bindings)
        self.assertEqual(ctx.exception.code, "BINDING_ORPHANED")
        self.assertIn("Nothing drafted matches this.", ctx.exception.detail)

    def test_an_unknown_evidence_id_refuses(self) -> None:
        bindings = [paper_bindings.Binding(sentence="s", kind="evidence", ref="E9")]
        with self.assertRaises(Refused) as ctx:
            paper_bindings.resolve_bindings(bindings, evidence_ids=set(), licensed_facts=set())
        self.assertEqual(ctx.exception.code, "EVIDENCE_ID_UNKNOWN")
        self.assertIn("E9", ctx.exception.detail)

    def test_an_unlicensed_fact_id_refuses(self) -> None:
        bindings = [paper_bindings.Binding(sentence="s", kind="fact", ref="results")]
        with self.assertRaises(Refused) as ctx:
            paper_bindings.resolve_bindings(bindings, evidence_ids=set(), licensed_facts=set())
        self.assertEqual(ctx.exception.code, "FACT_NOT_LICENSED")
        self.assertIn("results", ctx.exception.detail)

    def test_licensed_ids_resolve_without_refusing(self) -> None:
        bindings = [
            paper_bindings.Binding(sentence="s1", kind="evidence", ref="E1"),
            paper_bindings.Binding(sentence="s2", kind="fact", ref="results"),
        ]
        paper_bindings.resolve_bindings(bindings, evidence_ids={"E1"}, licensed_facts={"results"})


class StructuralTypingTests(unittest.TestCase):
    """`evidence-bound-drafting` spec, `Requirement: Structural Sentences
    Are Typed` (`design.md`, Decision D3)."""

    def test_a_numeral_inside_a_structural_sentence_refuses(self) -> None:
        bindings = [paper_bindings.Binding(sentence="We report 42% accuracy.", kind="structural", ref=None)]
        with self.assertRaises(Refused) as ctx:
            paper_bindings.type_structural(bindings, contract_prose="")
        self.assertEqual(ctx.exception.code, "STRUCTURAL_CARRIES_CLAIM")

    def test_a_plain_structural_sentence_passes(self) -> None:
        bindings = [
            paper_bindings.Binding(sentence="This paragraph closes the section.", kind="structural", ref=None)
        ]
        paper_bindings.type_structural(bindings, contract_prose="")

    def test_a_cite_command_inside_structural_refuses(self) -> None:
        bindings = [
            paper_bindings.Binding(
                sentence="See the prior work \\cite{smith2020}.", kind="structural", ref=None
            )
        ]
        with self.assertRaises(Refused) as ctx:
            paper_bindings.type_structural(bindings, contract_prose="")
        self.assertEqual(ctx.exception.code, "STRUCTURAL_CARRIES_CLAIM")

    def test_a_comparative_inside_structural_refuses(self) -> None:
        bindings = [
            paper_bindings.Binding(
                sentence="This method is faster than the baseline.", kind="structural", ref=None
            )
        ]
        with self.assertRaises(Refused) as ctx:
            paper_bindings.type_structural(bindings, contract_prose="")
        self.assertEqual(ctx.exception.code, "STRUCTURAL_CARRIES_CLAIM")

    def test_a_named_external_object_absent_from_contract_prose_refuses(self) -> None:
        bindings = [
            paper_bindings.Binding(
                sentence="This closes the discussion of Transformer.", kind="structural", ref=None
            )
        ]
        with self.assertRaises(Refused) as ctx:
            paper_bindings.type_structural(bindings, contract_prose="No mention of that architecture here.")
        self.assertEqual(ctx.exception.code, "STRUCTURAL_CARRIES_CLAIM")

    def test_a_named_object_present_verbatim_in_contract_prose_passes(self) -> None:
        bindings = [
            paper_bindings.Binding(
                sentence="This closes the discussion of Transformer.", kind="structural", ref=None
            )
        ]
        paper_bindings.type_structural(bindings, contract_prose="This section discusses Transformer at length.")

    def test_a_numeral_inside_a_display_math_fence_does_not_refuse(self) -> None:
        """`evidence-bound-drafting` spec, Scenario "A numeral inside a
        display-math fence does not refuse": a structural sentence whose
        only numeral sits inside a `$$...$$` display fence must not trigger
        `STRUCTURAL_CARRIES_CLAIM` -- `paper_bindings._strip_math` carries
        the identical `$$` defect `paper_style.strip_math` does, and the two
        implementations must not drift apart (design.md, Decision A)."""
        bindings = [
            paper_bindings.Binding(
                sentence="This paragraph closes the section. $$ 42 $$", kind="structural", ref=None
            )
        ]
        paper_bindings.type_structural(bindings, contract_prose="")


class ModeAdmissibilityTests(unittest.TestCase):
    """`evidence-bound-drafting` spec, `Requirement: Mode-Admissible
    Bindings`."""

    def test_transposition_rejects_a_discovery_binding(self) -> None:
        bindings = [paper_bindings.Binding(sentence="s", kind="evidence", ref="D1")]
        evidence_by_id = {"D1": {"id": "D1", "regime": "discovery"}}
        with self.assertRaises(Refused) as ctx:
            paper_bindings.check_mode_admissibility(bindings, "transposition", evidence_by_id)
        self.assertEqual(ctx.exception.code, "MODE_VIOLATION")
        self.assertIn("D1", ctx.exception.detail)

    def test_argument_admits_the_same_discovery_binding(self) -> None:
        bindings = [paper_bindings.Binding(sentence="s", kind="evidence", ref="D1")]
        evidence_by_id = {"D1": {"id": "D1", "regime": "discovery"}}
        paper_bindings.check_mode_admissibility(bindings, "argument", evidence_by_id)

    def test_both_modes_admit_resolution_class_evidence(self) -> None:
        bindings = [paper_bindings.Binding(sentence="s", kind="evidence", ref="R1")]
        evidence_by_id = {"R1": {"id": "R1", "regime": "resolution"}}
        paper_bindings.check_mode_admissibility(bindings, "transposition", evidence_by_id)
        paper_bindings.check_mode_admissibility(bindings, "argument", evidence_by_id)

    def test_both_modes_admit_none_regime_evidence(self) -> None:
        # `none` (no external source at all) is strictly more restrictive
        # than `resolution`, so a mode admitting `resolution` must admit
        # `none` too -- a block declaring `citations: "none"` inherits that
        # same regime on its own evidence records.
        bindings = [paper_bindings.Binding(sentence="s", kind="evidence", ref="N1")]
        evidence_by_id = {"N1": {"id": "N1", "regime": "none"}}
        paper_bindings.check_mode_admissibility(bindings, "transposition", evidence_by_id)
        paper_bindings.check_mode_admissibility(bindings, "argument", evidence_by_id)


class CorpusModeCitationsAdmissibilityTests(unittest.TestCase):
    """Derived guard over the real `sections/*.md` corpus, not a
    hand-listed set of block ids or a golden count standing in for
    enforcement: an evidence record's `regime` is inherited from its own
    block's `citations` field (`paper_cli._resolve_regime` ->
    `paper_validate.read_citations_regime`, fallback `"none"`), so every
    block whose contract declares a `citations` regime its own resolved
    `mode` does not admit would produce evidence its own section refuses
    at `write` time. Both sides of the comparison -- which blocks exist,
    each one's resolved mode, each one's declared citations regime -- are
    derived by parsing the corpus itself in this same test, never asserted
    or hand-listed."""

    def _violations(self) -> list[tuple[str, str, str, str]]:
        violations: list[tuple[str, str, str, str]] = []
        for path in sorted(SECTIONS_DIR.glob("*.md")):
            header, _body = paper_contract.parse(path.read_bytes())
            for block in header.blocks:
                mode_obj = paper_contract.resolve_mode(header, block)
                if mode_obj is None:
                    # No mode resolves for this block -- out of scope for
                    # this guard; `write`'s own readiness stage refuses
                    # `MODE_ABSENT` for it, a separate concern.
                    continue
                mode = mode_obj["value"]
                citations = block["citations"]
                admitted = paper_bindings._MODE_ADMITTED_EVIDENCE_REGIMES[mode]
                if citations not in admitted:
                    violations.append((path.name, block["id"], mode, citations))
        return violations

    def test_every_block_own_resolved_mode_admits_its_own_citations_regime(self) -> None:
        violations = self._violations()
        self.assertEqual(
            violations, [],
            f"block(s) whose resolved mode refuses their own declared citations "
            f"regime (section file, block id, mode, citations): {violations}",
        )

    def test_m4_dropping_none_from_transposition_fails_the_corpus_guard(self) -> None:
        # Load-bearing proof, executed rather than asserted: revert
        # `transposition`'s admitted set to the shipped defect (`none`
        # removed) in a real subprocess against a real mutant module, and
        # confirm the corpus guard above genuinely goes red naming real
        # blocks -- not merely that some test somewhere would notice.
        proc = _run_against_mutant(
            '"transposition": frozenset({"none", "resolution"}),',
            '"transposition": frozenset({"resolution"}),',
            "tests.test_paper_writing.CorpusModeCitationsAdmissibilityTests"
            ".test_every_block_own_resolved_mode_admits_its_own_citations_regime",
            source_path=SKILL_SCRIPTS / "paper_bindings.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)
        # The failure names real corpus blocks, not an empty or generic
        # message -- proving the guard fires on the actual violation shape.
        self.assertIn("08-abstract.md", output, output)
        self.assertIn("transposition", output, output)


#: Maps the number words `SKILL.md` prose is free to use for this count
#: (including the historical "none") to an integer, so the check below
#: reads *whatever the prose currently claims* rather than a hand-picked
#: expectation, and still catches the count going stale in either
#: direction.
_MODE_COUNT_WORDS = {
    "none": 0, "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_SKILL_MD_MODE_COUNT_RE = re.compile(
    r"(\w+) of the (\w+) shipped contracts carry `mode`"
)


class SkillMdModeCountAccuracyTests(unittest.TestCase):
    """`M17`: `SKILL.md`'s `### \\`mode\\`: how a block is licensed to argue`
    section states how many of the shipped `sections/*.md` contracts
    already declare `mode`. That count is prose sitting beside data that
    can be read directly -- the defect class this guard exists for is the
    prose going stale while the corpus moves on, exactly as it did when
    coverage went from 0/10 to 10/10 across `d99ee93`/`9986e11` and the
    sentence was never revisited. Both sides are derived here: the corpus
    side by parsing every `sections/*.md` header for a section-level
    `mode`, the prose side by regexing the live `SKILL.md` text -- neither
    is hand-listed or hardcoded to today's value.
    """

    SKILL_MD = (
        FORGE_ROOT / "skills" / "paper-writing" / "SKILL.md"
    )

    def _real_corpus_count(self) -> tuple[int, int]:
        paths = sorted(SECTIONS_DIR.glob("*.md"))
        with_mode = 0
        for path in paths:
            header, _body = paper_contract.parse(path.read_bytes())
            if header.mode is not None:
                with_mode += 1
        return with_mode, len(paths)

    def _claimed_count(self) -> tuple[int, int]:
        text = self.SKILL_MD.read_text(encoding="utf-8")
        match = _SKILL_MD_MODE_COUNT_RE.search(text)
        self.assertIsNotNone(
            match,
            "SKILL.md no longer states a '<n> of the <n> shipped contracts "
            "carry `mode`' sentence -- update this test's regex to match "
            "wherever that claim now lives before trusting it again.",
        )
        claimed_raw, total_raw = match.group(1), match.group(2)
        for raw in (claimed_raw, total_raw):
            self.assertIn(
                raw.lower(), _MODE_COUNT_WORDS,
                f"unrecognized count word {raw!r} in SKILL.md's mode-count "
                f"sentence -- extend _MODE_COUNT_WORDS to read it.",
            )
        return _MODE_COUNT_WORDS[claimed_raw.lower()], _MODE_COUNT_WORDS[total_raw.lower()]

    def test_skill_md_mode_count_matches_the_real_corpus(self) -> None:
        real_with_mode, real_total = self._real_corpus_count()
        claimed_with_mode, claimed_total = self._claimed_count()
        self.assertEqual(
            (claimed_with_mode, claimed_total), (real_with_mode, real_total),
            f"SKILL.md claims {claimed_with_mode} of {claimed_total} shipped "
            f"contracts carry `mode`, but sections/*.md actually shows "
            f"{real_with_mode} of {real_total} -- the prose drifted from "
            f"the corpus it describes.",
        )

    def test_no_documented_section_value_is_a_contract_filename_stem(self) -> None:
        """`--section` names the section id a contract DECLARES in its own
        header, never the `sections/*.md` filename stem. Both are plausible
        to a reader and only one resolves: `paper_contract.resolve_section_
        file` matches `header.section`, so a stem refuses `SECTION_UNKNOWN`.

        This guard exists because the drift already shipped and survived: the
        resolver was fixed while SIX user-facing sites kept documenting the
        stem -- two worked examples in `SKILL.md` and three `--help` strings
        -- so an operator hitting `SECTION_UNKNOWN` and consulting `--help`
        was handed the wrong answer again. A grep found those six; a grep is
        a list, and a list ages the day someone writes the seventh
        (`MAINTENANCE-seven-ways-to-fail-green.md`, 6: the fix is
        not touching the N sites, it is having something DERIVED find them).

        Both sides are derived, nothing hand-listed: the forbidden spellings
        are the real filename stems read off `sections/`, and the haystack is
        the live `SKILL.md` plus the live `--help` strings pulled out of the
        built parser. Renaming a contract file moves this guard with it.
        """
        stems = {path.stem for path in sorted(SECTIONS_DIR.glob("*.md"))}
        self.assertTrue(stems, "no shipped contracts found to derive stems from")

        surfaces = {"SKILL.md": self.SKILL_MD.read_text(encoding="utf-8")}
        parser = paper_cli.build_parser()
        for action in parser._actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            for verb, subparser in action.choices.items():
                for option in subparser._actions:
                    if "--section" in option.option_strings and option.help:
                        surfaces[f"{verb} --section help"] = option.help

        for where, text in sorted(surfaces.items()):
            for stem in sorted(stems):
                self.assertNotIn(
                    f"--section {stem}", text,
                    f"{where} documents `--section {stem}`, a contract "
                    f"FILENAME stem; `--section` takes the declared section "
                    f"id and a stem refuses SECTION_UNKNOWN",
                )
            self.assertNotIn(
                "--section <stem>", text,
                f"{where} calls `--section` a stem; it is the declared "
                f"section id",
            )
            self.assertNotIn(
                "sections/<id>.md stem", text,
                f"{where} describes `--section` as a filename stem; it is "
                f"the section id the contract's own header declares",
            )


_SAMPLE_DISQUALIFIER = "A symbol used without being declared."


def _contract_body(bullets: list) -> str:
    lines = ["# Demo Contract", "", "Some prose.", "", "## Disqualifiers"]
    lines += [f"- {bullet}" for bullet in bullets]
    return "\n".join(lines) + "\n"


class ContractAuditTests(unittest.TestCase):
    """`contract-audit` spec."""

    def test_bullet_text_reaches_the_audit_unchanged(self) -> None:
        bullets = paper_audit.extract_disqualifiers(_contract_body([_SAMPLE_DISQUALIFIER]))
        self.assertEqual(bullets, [_SAMPLE_DISQUALIFIER])

    def test_a_firing_disqualifier_quotes_its_span(self) -> None:
        body = _contract_body([_SAMPLE_DISQUALIFIER])
        draft = "A symbol X appears with no declaration."
        verdicts = [
            {"bullet": _SAMPLE_DISQUALIFIER, "verdict": "fires",
             "span": "symbol X appears with no declaration"}
        ]
        result = paper_audit.audit(body, draft, verdicts)
        self.assertTrue(result["blocks"])
        self.assertEqual(result["fired"][0]["span"], "symbol X appears with no declaration")

    def test_clear_and_firing_coexist_in_one_run(self) -> None:
        second = "A dataset described here and left unreferenced."
        body = _contract_body([_SAMPLE_DISQUALIFIER, second])
        draft = "A symbol X appears with no declaration."
        verdicts = [
            {"bullet": _SAMPLE_DISQUALIFIER, "verdict": "fires",
             "span": "symbol X appears with no declaration"},
            {"bullet": second, "verdict": "clear"},
        ]
        result = paper_audit.audit(body, draft, verdicts)
        by_bullet = {entry["bullet"]: entry["verdict"] for entry in result["verdicts"]}
        self.assertEqual(by_bullet[_SAMPLE_DISQUALIFIER], "fires")
        self.assertEqual(by_bullet[second], "clear")

    def test_an_all_undecidable_audit_does_not_block(self) -> None:
        second = "A dataset described here and left unreferenced."
        body = _contract_body([_SAMPLE_DISQUALIFIER, second])
        verdicts = [
            {"bullet": _SAMPLE_DISQUALIFIER, "verdict": "undecidable"},
            {"bullet": second, "verdict": "undecidable"},
        ]
        result = paper_audit.audit(body, "draft text", verdicts)
        self.assertFalse(result["blocks"])
        self.assertEqual({entry["verdict"] for entry in result["verdicts"]}, {"undecidable"})

    def test_one_firing_bullet_blocks_regardless_of_undecidables(self) -> None:
        second, third = "second bullet text.", "third bullet text."
        body = _contract_body([_SAMPLE_DISQUALIFIER, second, third])
        draft = "The offending clause appears here."
        verdicts = [
            {"bullet": _SAMPLE_DISQUALIFIER, "verdict": "fires",
             "span": "The offending clause appears here"},
            {"bullet": second, "verdict": "undecidable"},
            {"bullet": third, "verdict": "undecidable"},
        ]
        result = paper_audit.audit(body, draft, verdicts)
        self.assertTrue(result["blocks"])
        self.assertEqual(result["fired"][0]["bullet"], _SAMPLE_DISQUALIFIER)

    def test_a_fires_verdict_with_no_span_downgrades_to_undecidable(self) -> None:
        body = _contract_body([_SAMPLE_DISQUALIFIER])
        verdicts = [{"bullet": _SAMPLE_DISQUALIFIER, "verdict": "fires", "span": ""}]
        result = paper_audit.audit(body, "draft text", verdicts)
        self.assertFalse(result["blocks"])
        self.assertEqual(result["verdicts"][0]["verdict"], "undecidable")

    def test_a_fires_verdict_whose_span_is_not_in_the_draft_downgrades(self) -> None:
        body = _contract_body([_SAMPLE_DISQUALIFIER])
        verdicts = [{"bullet": _SAMPLE_DISQUALIFIER, "verdict": "fires", "span": "not present anywhere"}]
        result = paper_audit.audit(body, "draft text entirely unrelated", verdicts)
        self.assertFalse(result["blocks"])
        self.assertEqual(result["verdicts"][0]["verdict"], "undecidable")

    def test_a_contract_missing_the_heading_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_audit.extract_disqualifiers(
                "# Demo\n\nNo disqualifiers section here.\n", source_name="demo.md"
            )
        self.assertEqual(ctx.exception.code, "DISQUALIFIERS_ABSENT")
        self.assertIn("demo.md", ctx.exception.detail)

    def test_all_ten_shipped_contracts_carry_the_heading(self) -> None:
        for path in sorted(SECTIONS_DIR.glob("*.md")):
            _header, body = paper_contract.parse(path.read_bytes())
            bullets = paper_audit.extract_disqualifiers(body.decode("utf-8"), source_name=path.name)
            self.assertGreater(len(bullets), 0, path.name)

    def test_a_verdict_naming_an_unknown_bullet_refuses(self) -> None:
        verdicts = [{"bullet": "not a real bullet", "verdict": "clear"}]
        with self.assertRaises(Refused) as ctx:
            paper_audit.reconcile_verdicts([_SAMPLE_DISQUALIFIER], verdicts, "draft")
        self.assertEqual(ctx.exception.code, "VERDICT_BULLET_UNKNOWN")

    def test_a_missing_verdict_for_a_real_bullet_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_audit.reconcile_verdicts([_SAMPLE_DISQUALIFIER], [], "draft")
        self.assertEqual(ctx.exception.code, "VERDICT_MISSING")

    def test_a_wrapped_bullet_is_joined_with_one_space(self) -> None:
        body = (
            "# Demo Contract\n\n## Disqualifiers\n"
            "- An equation displayed and numbered that no sentence ever references, defines no\n"
            "  contribution, and is not the general combination.\n"
        )
        bullets = paper_audit.extract_disqualifiers(body)
        self.assertEqual(
            bullets,
            [
                "An equation displayed and numbered that no sentence ever references, defines no "
                "contribution, and is not the general combination."
            ],
        )

    def test_a_nested_bullet_stays_its_own_bullet(self) -> None:
        body = (
            "# Demo Contract\n\n## Disqualifiers\n"
            "- A top-level bullet.\n"
            "  - A nested bullet indented under it.\n"
        )
        bullets = paper_audit.extract_disqualifiers(body)
        self.assertEqual(
            bullets, ["A top-level bullet.", "A nested bullet indented under it."]
        )

    def test_all_shipped_disqualifier_bullets_are_extracted_whole(self) -> None:
        """Two properties, both derived from each contract's own bytes --
        never a frozen count. A count would go red the day someone adds or
        removes a disqualifier, which breaks nothing in production and is
        exactly the "test that ratifies a decision instead of verifying a
        property" pattern `MAINTENANCE-seven-ways-to-fail-green.md`
        (7) names. These two stay true at 178 bullets, at 179, or at 200,
        and still redden if the reader ever truncates, merges or splits one.

        1. Every bullet arrives WHOLE. A wrapped bullet cut at its line
           break loses its ending, and each shipped bullet is a sentence, so
           a bullet not ending in `.` is a bullet the reader truncated.
        2. Per contract, the number of bullets extracted equals the number
           of `- ` lines under that contract's own `## Disqualifiers`
           heading -- derived by counting them here, so a reader that
           swallowed one into another (or split one in two) fails even
           though every surviving bullet still ends in `.`.
        """
        for path in sorted(SECTIONS_DIR.glob("*.md")):
            _header, body = paper_contract.parse(path.read_bytes())
            text = body.decode("utf-8")
            bullets = paper_audit.extract_disqualifiers(text, source_name=path.name)
            for bullet in bullets:
                self.assertTrue(bullet.endswith("."), f"{path.name}: {bullet!r}")

            lines = text.splitlines()
            start = next(
                index for index, line in enumerate(lines)
                if line.strip() == "## Disqualifiers"
            )
            markers = 0
            for line in lines[start + 1:]:
                stripped = line.strip()
                if stripped.startswith("## "):
                    break
                if stripped.startswith("- ") or stripped.startswith("* "):
                    markers += 1
            self.assertEqual(len(bullets), markers, path.name)


def _write_contract(
    *, block_id="mm-proposal", citations_regime="resolution", mode="transposition",
    requires_facts=(), evidence_set=(), style_set=(), source_sections=(),
    disqualifiers=(_SAMPLE_DISQUALIFIER,),
) -> "paper_write.BlockContract":
    return paper_write.BlockContract(
        block_id=block_id,
        contract_prose=_contract_body(list(disqualifiers)),
        contract_source="demo.md",
        citations_regime=citations_regime,
        mode=mode,
        requires_facts=tuple(requires_facts),
        evidence_set=tuple(evidence_set),
        style_set=tuple(style_set),
        source_sections=tuple(source_sections),
    )


_CLEAN_DRAFT = {
    "latex": "This paragraph closes the section.",
    "bindings": [{"sentence": "This paragraph closes the section.", "binding": "structural"}],
}
_CLEAN_AUDIT = {"verdicts": [{"bullet": _SAMPLE_DISQUALIFIER, "verdict": "clear"}]}
_FIRING_AUDIT = {
    "verdicts": [
        {"bullet": _SAMPLE_DISQUALIFIER, "verdict": "fires", "span": "This paragraph closes the section"}
    ]
}


class WritingPipelineTests(unittest.TestCase):
    """`writing-orchestration` spec. This is one of the two decisive proofs
    for this change (per the orchestrator's launch context): the claim
    "an assertion outside the evidence set never reaches main.tex" is
    exercised here end to end, not merely asserted."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        _write_fixture(self.paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))

    def test_a_clean_pipeline_writes_the_block(self) -> None:
        contract = _write_contract(citations_regime="none", evidence_set=())
        result = paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        final = (self.paper_dir / "main.tex").read_bytes()
        self.assertIn(b"This paragraph closes the section.", final)

    def test_a_styled_draft_lifting_the_sample_refuses_style_overlap(self) -> None:
        """`design.md`'s own Data Flow: `paper_leak.tripwire (styled only)
        -> paper_write ledger` runs inside the real pipeline, not only in a
        standalone proof harness -- `write_block` itself refuses when a
        styled draft shares eight or more normalized tokens with a
        recorded sample, and `main.tex` never changes."""
        sample = {
            "reference": "paperA",
            "span": "The quick brown fox jumps over the lazy dog again today.",
        }
        contract = _write_contract(citations_regime="none", evidence_set=(), style_set=(sample,))
        lifted_draft = {
            "latex": (
                "This closes the section. "
                "The quick brown fox jumps over the lazy dog again today."
            ),
            "bindings": [
                {"sentence": "This closes the section.", "binding": "structural"},
                {
                    "sentence": "The quick brown fox jumps over the lazy dog again today.",
                    "binding": "structural",
                },
            ],
        }
        pre = (self.paper_dir / "main.tex").read_bytes()

        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(self.paper_dir, contract, lifted_draft, _CLEAN_AUDIT)

        self.assertEqual(ctx.exception.code, "STYLE_OVERLAP")
        self.assertIn("paperA", ctx.exception.detail)
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), pre)

    def test_a_styled_draft_with_no_lifted_run_still_writes(self) -> None:
        sample = {
            "reference": "paperA",
            "span": "one two three four five six seven eight nine ten",
        }
        contract = _write_contract(citations_regime="none", evidence_set=(), style_set=(sample,))
        result = paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")

    def test_no_mode_resolved_refuses_mode_absent(self) -> None:
        contract = _write_contract(citations_regime="none", mode=None)
        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(ctx.exception.code, "MODE_ABSENT")

    def test_a_citing_block_with_no_evidence_set_refuses_evidence_set_required(self) -> None:
        contract = _write_contract(citations_regime="resolution", evidence_set=())
        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(ctx.exception.code, "EVIDENCE_SET_REQUIRED")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), _marker_pair("mm-proposal", b"Old body.\n"))

    def test_a_none_regime_block_with_no_evidence_writes_with_no_refusal(self) -> None:
        contract = _write_contract(citations_regime="none", evidence_set=())
        result = paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")

    def test_an_assertion_outside_the_evidence_set_never_reaches_main_tex(self) -> None:
        """The decisive proof: give the writer an evidence set, then draft a
        binding naming an id outside it -- and confirm main.tex never
        changes."""
        contract = _write_contract(
            citations_regime="resolution", evidence_set=({"id": "E1", "regime": "resolution"},),
        )
        draft = {
            "latex": "This closes on the recorded evidence. This asserts an outside claim.",
            "bindings": [
                {"sentence": "This closes on the recorded evidence.", "binding": "evidence:E1"},
                {"sentence": "This asserts an outside claim.", "binding": "evidence:E9"},
            ],
        }
        pre = (self.paper_dir / "main.tex").read_bytes()
        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(self.paper_dir, contract, draft, _CLEAN_AUDIT)
        self.assertEqual(ctx.exception.code, "EVIDENCE_ID_UNKNOWN")
        self.assertIn("E9", ctx.exception.detail)
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), pre)

    def test_a_failing_evidence_audit_stops_before_contract_audit_runs(self) -> None:
        contract = _write_contract(citations_regime="none", evidence_set=())
        bad_draft = {
            "latex": "First sentence. Second sentence.",
            "bindings": [{"sentence": "First sentence.", "binding": "structural"}],
        }
        with unittest.mock.patch("paper_audit.audit") as mocked_audit:
            with self.assertRaises(Refused) as ctx:
                paper_write.write_block(self.paper_dir, contract, bad_draft, _CLEAN_AUDIT)
        self.assertEqual(ctx.exception.code, "UNBOUND_SENTENCE")
        mocked_audit.assert_not_called()
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), _marker_pair("mm-proposal", b"Old body.\n"))

    def test_one_bounded_redraft_reports_fired_bullets_as_feedback(self) -> None:
        contract = _write_contract(citations_regime="none", evidence_set=())
        result = paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _FIRING_AUDIT)
        self.assertEqual(result["status"], "audit-fired")
        self.assertEqual(result["attempt"], 1)
        self.assertEqual(result["fired"][0]["bullet"], _SAMPLE_DISQUALIFIER)
        self.assertEqual(result["fired"][0]["span"], "This paragraph closes the section")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), _marker_pair("mm-proposal", b"Old body.\n"))

    def test_the_second_attempt_is_audited_with_the_same_inputs(self) -> None:
        contract = _write_contract(citations_regime="none", evidence_set=())
        paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _FIRING_AUDIT)
        # Same contract/evidence/mode -- the ledger recognizes this as
        # attempt 2 against the SAME key, exactly what "the re-draft's
        # input includes ... the same contract, evidence set, and mode as
        # the first attempt" requires.
        key_before = paper_write._attempt_key(contract)
        ledger = paper_write._read_ledger(self.paper_dir, "mm-proposal")
        self.assertEqual(ledger["key"], key_before)
        self.assertEqual(ledger["attempts"], 1)

    def test_two_failing_audits_leave_main_tex_unchanged_and_refuse_audit_exhausted(self) -> None:
        contract = _write_contract(citations_regime="none", evidence_set=())
        pre = (self.paper_dir / "main.tex").read_bytes()
        paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _FIRING_AUDIT)
        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _FIRING_AUDIT)
        self.assertEqual(ctx.exception.code, "AUDIT_EXHAUSTED")
        self.assertIn(_SAMPLE_DISQUALIFIER, ctx.exception.detail)
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), pre)

    def test_a_changed_input_starts_a_fresh_attempt_budget(self) -> None:
        contract = _write_contract(citations_regime="none", evidence_set=())
        paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _FIRING_AUDIT)
        different_contract = _write_contract(citations_regime="none", evidence_set=(), mode="argument")
        result = paper_write.write_block(self.paper_dir, different_contract, _CLEAN_DRAFT, _FIRING_AUDIT)
        self.assertEqual(result["status"], "audit-fired")
        self.assertEqual(result["attempt"], 1)

    def test_a_real_write_with_no_style_set_reports_the_style_channel_unmeasured(self) -> None:
        """Ruling 2's own guarantee ('never a silent pass') has no real
        caller unless a genuine `write_block` invocation surfaces it. This
        drives the pipeline end to end -- not `style_channel_report` in
        isolation -- with an empty `style_set`, the only value Work Unit 1
        alone ever produces, and asserts the returned envelope itself
        reports `unmeasured` rather than omitting the field entirely."""
        contract = _write_contract(citations_regime="none", evidence_set=(), style_set=())
        result = paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["styleChannel"], {"status": "unmeasured"})

    def test_a_real_write_with_a_style_set_reports_the_style_channel_measured(self) -> None:
        sample = {
            "reference": "paperA",
            "span": "one two three four five six seven eight nine ten",
        }
        contract = _write_contract(citations_regime="none", evidence_set=(), style_set=(sample,))
        result = paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["styleChannel"]["status"], "measured")

    def test_a_real_write_with_no_source_sections_reports_source_fidelity_unmeasured(self) -> None:
        """`transposition-fidelity` spec, `Requirement: A Block With No
        Measured Bound Section Reports Unmeasured, Never Refused`, scenario
        "A block with no bound section reports unmeasured" (tasks.md 1.9):
        WU1's own scope, wiring and the `unmeasured` report only -- no
        verdict logic (`check_source_section_verbatim`) exists yet, that
        is WU2's."""
        contract = _write_contract(citations_regime="none", evidence_set=(), source_sections=())
        result = paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["sourceFidelity"], {"status": "unmeasured"})

    def test_a_real_write_with_a_bound_section_reports_source_fidelity_measured(self) -> None:
        """The reachable non-empty branch, proven minimally: WU1 adds no
        check and no refusal (tasks.md, orchestrator instruction), so only
        the `status` differentiates "a bound section reached the pipeline"
        from `unmeasured` -- the per-section floor/threshold/longest_run
        shape is WU2's own scope (`check_source_section_verbatim`,
        tasks.md 2.11)."""
        section = {
            "fact": "formulation", "lineage": "lumen-thesis", "title": "1. Intro",
            "path": "irrelevant.md", "byte_start": 0, "byte_end": 10, "text": "# 1. Intro",
        }
        contract = _write_contract(citations_regime="none", evidence_set=(), source_sections=(section,))
        result = paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["sourceFidelity"]["status"], "measured")


class StyleChannelReportingTests(unittest.TestCase):
    """Ruling 2 (orchestrator, this change): an all-`noEquivalent` style set
    reports `unmeasured`, it does not pass."""

    def test_empty_style_set_reports_unmeasured(self) -> None:
        result = paper_write.style_channel_report([], None, None)
        self.assertEqual(result["status"], "unmeasured")

    def test_nonempty_style_set_reports_measured(self) -> None:
        recorded = [{"reference": "paperA", "span": "x"}]
        result = paper_write.style_channel_report(recorded, {"pass": True}, {"pass": True})
        self.assertEqual(result["status"], "measured")


#: Invented, content-free filler words -- no digits, no number words
#: (`paper_vocabulary.NUMBER_WORDS`), no comparatives
#: (`paper_vocabulary.COMPARATIVES`) -- so a run built from them can be
#: embedded inside a single `structural`-typed draft sentence in the
#: `write_block` integration tests below without tripping `paper_bindings.
#: type_structural`'s numeral/comparative checks the way a digit-suffixed
#: token (`"clause1"`) would.
_FILLER_WORDS: tuple[str, ...] = (
    "willow", "cedar", "maple", "birch", "juniper", "cypress", "fern", "moss",
    "lichen", "reed", "rush", "sedge", "clover", "thistle", "nettle",
    "bramble", "hazel", "alder", "beech", "linden", "poplar", "sycamore",
    "hemlock", "larch", "holly", "fennel", "sorrel", "mallow", "chicory",
    "plantain", "bracken", "heather", "gorse", "bilberry", "hawthorn",
    "blackthorn", "rowan", "hornbeam", "whitebeam", "sallow", "osier",
    "spindle", "buckthorn", "dogwood",
)


def _n_token_run(n: int) -> str:
    """A run of exactly `n` distinct, invented filler words -- calibrates
    `source_section_floor`/`check_source_section_verbatim` against an exact
    known run length, never borrowed from any real document."""
    if n > len(_FILLER_WORDS):
        raise ValueError(f"_FILLER_WORDS only holds {len(_FILLER_WORDS)} words; need {n}")
    return " ".join(_FILLER_WORDS[:n])


class SourceSectionVerbatimWriteGateTests(unittest.TestCase):
    """`transposition-fidelity` spec, `Requirement: The Guard Fires Inside
    write, Before Substitution, Never Only From A Read-Only Verb` +
    `Requirement: Only A Transposition-Mode Block Is Checked...` (design.md,
    Decisions C/D; tasks.md 2.7-2.11). WU1 wired the plumbing and the
    `unmeasured` report only (`WritingPipelineTests` above); this class
    proves the real verdict logic reaches an actual `write_block` call.
    Every draft below is deliberately a single grammatical sentence (one
    capitalised word, at the very start, and no digits, number words or
    comparatives) so it clears `paper_bindings.type_structural`'s own
    checks and the ONLY refusal in play is the one under test."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        _write_fixture(self.paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))

    def _bound_section(self, text: str) -> dict:
        return {
            "fact": "formulation", "lineage": "widget-study-r4",
            "title": "2. Widget Calibration", "path": "irrelevant.md",
            "byte_start": 0, "byte_end": len(text), "text": text,
        }

    def _structural_draft(self, sentence: str) -> dict:
        return {"latex": sentence, "bindings": [{"sentence": sentence, "binding": "structural"}]}

    def test_a_verbatim_paste_refuses_before_substitute_and_main_tex_stays_unchanged(self) -> None:
        run = _n_token_run(17)
        section = self._bound_section(f"Some framing text about the section itself. {run} Trailing text.")
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="transposition", source_sections=(section,),
        )
        draft = self._structural_draft(f"This passage states directly that {run} without changing anything.")
        pre = (self.paper_dir / "main.tex").read_bytes()

        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(self.paper_dir, contract, draft, _CLEAN_AUDIT)

        self.assertEqual(ctx.exception.code, "SOURCE_SECTION_VERBATIM")
        self.assertIn("mm-proposal", ctx.exception.detail)
        self.assertIn("formulation", ctx.exception.detail)
        self.assertIn("widget-study-r4", ctx.exception.detail)
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), pre)

    def test_a_transposed_draft_in_its_own_register_writes(self) -> None:
        section = self._bound_section(
            "The widget calibration procedure requires careful measurement "
            "of every dial before the run starts."
        )
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="transposition", source_sections=(section,),
        )
        draft = self._structural_draft(
            "Calibrating the widget takes patience, attention, and a steady hand."
        )
        result = paper_write.write_block(self.paper_dir, contract, draft, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")

    def test_a_refusal_here_writes_nothing_to_the_attempt_ledger(self) -> None:
        run = _n_token_run(17)
        section = self._bound_section(f"Framing text. {run} Trailing text.")
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="transposition", source_sections=(section,),
        )
        draft = self._structural_draft(f"This passage states directly that {run} without changing anything.")
        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(self.paper_dir, contract, draft, _CLEAN_AUDIT)
        self.assertEqual(ctx.exception.code, "SOURCE_SECTION_VERBATIM")
        self.assertIsNone(paper_write._read_ledger(self.paper_dir, "mm-proposal"))

    def test_an_argument_mode_block_with_the_identical_binding_is_never_checked(self) -> None:
        run = _n_token_run(17)
        section = self._bound_section(f"Framing text. {run} Trailing text.")
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="argument", source_sections=(section,),
        )
        draft = self._structural_draft(f"This passage states directly that {run} without changing anything.")
        result = paper_write.write_block(self.paper_dir, contract, draft, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")

    def test_a_passing_block_reports_per_section_floor_threshold_and_longest_run(self) -> None:
        run = _n_token_run(16)
        section = self._bound_section(f"Framing text. {run} Trailing text.")
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="transposition", source_sections=(section,),
        )
        draft = self._structural_draft(f"This passage states directly that {run} without changing anything.")
        result = paper_write.write_block(self.paper_dir, contract, draft, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        entry = result["sourceFidelity"]["sections"][0]
        self.assertEqual(entry["lineage"], "widget-study-r4")
        self.assertEqual(entry["title"], "2. Widget Calibration")
        self.assertEqual(entry["threshold"], 16)
        self.assertEqual(entry["longest_run"], 16)
        self.assertIn("floor", entry)

    def test_a_contract_licensed_high_floor_is_visible_not_silent(self) -> None:
        """Scenario "A contract-licensed high floor is visible, not silent":
        a block whose own contract prose shares a forty-token run with its
        bound section makes the guard inert for that run, and the envelope
        reports a floor of forty and a threshold of forty."""
        run = _n_token_run(40)
        section = self._bound_section(f"Section framing text. {run} Section trailing text.")
        bullet = f"A bullet stating that {run} plainly."
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="transposition",
            source_sections=(section,), disqualifiers=(bullet,),
        )
        draft = self._structural_draft(f"This passage states directly that {run} without changing anything.")
        audit_account = {"verdicts": [{"bullet": bullet, "verdict": "clear"}]}
        result = paper_write.write_block(self.paper_dir, contract, draft, audit_account)
        self.assertEqual(result["status"], "written")
        entry = result["sourceFidelity"]["sections"][0]
        self.assertEqual(entry["floor"], 40)
        self.assertEqual(entry["threshold"], 40)

    def test_a_draft_failing_both_checks_names_style_overlap_first(self) -> None:
        """`transposition-fidelity` spec, Scenario "A verbatim source-section
        paste is a distinct refusal from a style leak": `write` runs the
        style tripwire BEFORE this capability's own stage (design.md, Data
        Flow), so a draft failing both always names `STYLE_OVERLAP`
        deterministically -- never computed by widening either check's own
        function or sample set."""
        style_run = _n_token_run(9)
        section_run = " ".join(_FILLER_WORDS[9:26])
        style_sample = {"reference": "paperA", "span": style_run}
        section = self._bound_section(f"Framing text. {section_run} Trailing text.")
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="transposition",
            source_sections=(section,), style_set=(style_sample,),
        )
        draft = self._structural_draft(
            f"This passage restates that {style_run} and separately that {section_run} plainly."
        )
        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(self.paper_dir, contract, draft, _CLEAN_AUDIT)
        self.assertEqual(ctx.exception.code, "STYLE_OVERLAP")


class SourceSectionVerbatimMutationProofTests(unittest.TestCase):
    """`transposition-fidelity` spec, the five mutation scenarios
    (tasks.md 2.14-2.18) -- each a mutation a weaker lock survives
    (design.md, Testing Strategy: "Mutation per claim")."""

    def _assert_guard_failed_under_mutation(self, proc: subprocess.CompletedProcess) -> None:
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_the_backstop_alone_fails_the_licensed_floor_guard(self) -> None:
        """Scenario "Mutation -- the backstop alone is not enough without
        the floor": `max(floor, SOURCE_RUN_BACKSTOP)` mutated to
        `SOURCE_RUN_BACKSTOP` alone must make the contract-licensed
        forty-token-run test go red -- it now wrongly refuses under the
        sixteen-token backstop alone."""
        proc = _run_against_mutant(
            "        threshold = max(floor, SOURCE_RUN_BACKSTOP)",
            "        threshold = SOURCE_RUN_BACKSTOP",
            "tests.test_paper_writing.SourceSectionVerbatimTests"
            ".test_a_contract_licensed_forty_token_floor_makes_the_guard_inert",
            source_path=SKILL_SCRIPTS / "paper_leak.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_the_floor_alone_fails_the_six_token_idiom_guard(self) -> None:
        """Scenario "Mutation -- the floor alone is not enough without the
        backstop": `max(floor, SOURCE_RUN_BACKSTOP)` mutated to `floor`
        alone must make the near-zero-floor six-token-idiom test go red --
        it now wrongly refuses a six-token idiom that shares nothing with
        the contract prose."""
        proc = _run_against_mutant(
            "        threshold = max(floor, SOURCE_RUN_BACKSTOP)",
            "        threshold = floor",
            "tests.test_paper_writing.SourceSectionVerbatimTests"
            ".test_a_six_token_idiom_does_not_refuse_under_the_real_backstop",
            source_path=SKILL_SCRIPTS / "paper_leak.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_raising_the_effective_minimum_fails_the_reachability_guard(self) -> None:
        """Scenario "Mutation -- the refusal is reachable at all": raising
        the check's own effective minimum far above any real draft length
        must make the verbatim-paste `write` test go red, proving
        `SOURCE_SECTION_VERBATIM` is reachable under an unmutated
        implementation, not merely asserted never to fire."""
        proc = _run_against_mutant(
            "            min_tokens=threshold + 1,",
            "            min_tokens=10_000,",
            "tests.test_paper_writing.SourceSectionVerbatimWriteGateTests"
            ".test_a_verbatim_paste_refuses_before_substitute_and_main_tex_stays_unchanged",
            source_path=SKILL_SCRIPTS / "paper_leak.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_skipping_the_stage_in_write_block_fails_the_direct_write_guard(self) -> None:
        """Scenario "Mutation -- wiring the guard only into a read-only verb
        is caught": with `write_block` itself made to skip the new stage
        (the shape a guard wired only onto a read-only verb would produce),
        the direct-`write` verbatim-paste test must fail -- proving the
        guard is wired to the enforcing verb, not merely a reachable
        function."""
        proc = _run_against_mutant(
            "    if contract.mode == paper_vocabulary.MODE_TRANSPOSITION and contract.source_sections:",
            "    if False and contract.mode == paper_vocabulary.MODE_TRANSPOSITION "
            "and contract.source_sections:",
            "tests.test_paper_writing.SourceSectionVerbatimWriteGateTests"
            ".test_a_verbatim_paste_refuses_before_substitute_and_main_tex_stays_unchanged",
            source_path=SKILL_SCRIPTS / "paper_write.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_mode_check_flipped_fails_the_transposition_guard(self) -> None:
        """Scenario "Mutation -- mode is derived, not assumed", transposition
        half: the stage guard's own condition mutated from
        `MODE_TRANSPOSITION` to `MODE_ARGUMENT` must make the
        transposition-mode verbatim-paste test go red -- the transposition
        block that should be checked is no longer checked."""
        proc = _run_against_mutant(
            "    if contract.mode == paper_vocabulary.MODE_TRANSPOSITION and contract.source_sections:",
            "    if contract.mode == paper_vocabulary.MODE_ARGUMENT and contract.source_sections:",
            "tests.test_paper_writing.SourceSectionVerbatimWriteGateTests"
            ".test_a_verbatim_paste_refuses_before_substitute_and_main_tex_stays_unchanged",
            source_path=SKILL_SCRIPTS / "paper_write.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_mode_check_flipped_fails_the_argument_exemption_guard(self) -> None:
        """Scenario "Mutation -- mode is derived, not assumed", argument
        half: the SAME mutation must also make the argument-mode exemption
        test go red -- the argument block that should be exempt is now
        wrongly checked."""
        proc = _run_against_mutant(
            "    if contract.mode == paper_vocabulary.MODE_TRANSPOSITION and contract.source_sections:",
            "    if contract.mode == paper_vocabulary.MODE_ARGUMENT and contract.source_sections:",
            "tests.test_paper_writing.SourceSectionVerbatimWriteGateTests"
            ".test_an_argument_mode_block_with_the_identical_binding_is_never_checked",
            source_path=SKILL_SCRIPTS / "paper_write.py",
        )
        self._assert_guard_failed_under_mutation(proc)


# =====================================================================
# Ruling 1 -- the no-subprocess seam, with exactly one named exception
# =====================================================================

#: The one file this skill will ever let import `subprocess`, for
#: `latexmk` (`a-diagram-that-compiles-or-says-why`, not yet landed; the
#: orchestrator's Ruling 1 for this change). Named here, not empty, so this
#: scan already tolerates it the moment that sibling's file appears on
#: disk. Pinned to `len(...) == 1` below: a SECOND name requires
#: hand-editing that literal in a diff someone reads.
SUBPROCESS_EXCEPTIONS: tuple = ("paper_latex.py",)


def _forbidden_process_names_in(source_path: Path) -> list:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    found: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "multiprocessing"):
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module in ("subprocess", "multiprocessing"):
            found.append(node.module)
        elif (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "os"):
            if node.attr in ("system", "popen") or node.attr.startswith("exec"):
                found.append(f"os.{node.attr}")
    return found


def scan_forbidden_process_imports(scripts_dir: Path) -> dict:
    """`design.md`, Decision D2 / Threat Matrix "Process integration":
    forbids `subprocess`, `os.system`, `os.popen`, `os.exec*`,
    `multiprocessing` across every `scripts/*.py` except
    `SUBPROCESS_EXCEPTIONS`."""
    violations: dict = {}
    for path in sorted(scripts_dir.glob("*.py")):
        if path.name in SUBPROCESS_EXCEPTIONS:
            continue
        found = _forbidden_process_names_in(path)
        if found:
            violations[path.name] = found
    return violations


class NoSubprocessScanTests(unittest.TestCase):

    def test_exception_list_has_exactly_one_entry(self) -> None:
        self.assertEqual(len(SUBPROCESS_EXCEPTIONS), 1)
        self.assertEqual(SUBPROCESS_EXCEPTIONS, ("paper_latex.py",))

    def test_no_shipped_script_imports_a_forbidden_process_primitive(self) -> None:
        self.assertEqual(scan_forbidden_process_imports(SKILL_SCRIPTS), {})

    def test_a_planted_subprocess_import_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / "evil.py").write_text("import subprocess\n", encoding="utf-8")
            violations = scan_forbidden_process_imports(tmp_dir)
        self.assertIn("evil.py", violations)
        self.assertIn("subprocess", violations["evil.py"])

    def test_the_exception_named_file_is_tolerated_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / "paper_latex.py").write_text("import subprocess\n", encoding="utf-8")
            violations = scan_forbidden_process_imports(tmp_dir)
        self.assertEqual(violations, {})


class ModuleCompletenessTests(unittest.TestCase):
    """tasks.md 1.12 -- the highest-value task in this change: `{stems of
    scripts/*.py}` must equal `paper_cli.py`'s own module-level import set,
    so a module nobody imports cannot ship unclassified. RED was proven by
    hand during implementation: a sixth, unimported module planted under
    `scripts/` made this equality fail; removed once proven, since a
    permanent planted file would corrupt this skill's own roster for every
    other suite that scans `scripts/*.py`."""

    def test_every_script_on_disk_is_imported_at_module_level_by_paper_cli(self) -> None:
        on_disk = {path.stem for path in SKILL_SCRIPTS.glob("*.py")}
        imported = {module.stem for module in paper_cli_imported_modules()} | {"paper_cli"}
        self.assertEqual(on_disk, imported)


# =====================================================================
# the-couplings-hold-or-they-do-not
# =====================================================================

#: The three canonical, declared contribution names -- shared by every
#: fixture below so a single ordered comparison exercises coupling 1,
#: coupling 4's methods-diagram reuse, and the chain's own closure check
#: against the same document-bound set.
_COUPLING_CONTRIBUTIONS = ["Adaptive Caching", "Async Prefetch", "Bounded Retry"]

#: The section corpus this capability's own fixture installs -- five files,
#: eight blocks, covering the fact every check derives its block set from
#: (`contributions`, `problem-statement`, `gap`, `limitations`). No
#: `figure:` obligation anywhere: this fixture is deliberately independent
#: of `a-diagram-that-compiles-or-says-why`.
def _coupling_requirement(fact: str, filename: str) -> dict:
    """One rich `requires_facts` entry for the coupling fixture, sourced at
    the same file declaring it — `_write_coupling_sections` appends this
    exact sentence to that file's own prose body, so `quote_in_body`
    verifies it for real rather than needing a fabricated anchor."""
    return {
        "value": fact,
        "source": {
            "file": f"sections/{filename}",
            "quote": f"This block requires the {fact}.",
        },
    }


def _coupling_production(fact: str, filename: str) -> dict:
    """One rich `produces_facts` entry, the `_coupling_requirement`
    counterpart (`a-fact-is-declared-or-it-is-produced`, `fact-production`
    spec). `00-produced-facts.md`'s own three blocks produce `contributions`
    /`problem-statement`/`limitations`; `gap` is produced instead by
    `intro-gap` and `related-work-gap` themselves (its two CORROBORATED
    producers, `paper_verify.CHECKS`'s own carve-out) — every one of the
    four facts resolves to a producer and `FACT_PRODUCER_ABSENT` never
    fires here."""
    return {
        "value": fact,
        "source": {
            "file": f"sections/{filename}",
            "quote": f"This block produces the {fact}.",
        },
    }


def _coupling_after(fact: str, filename: str) -> list:
    """The `after` edge every requiring block in this fixture carries to
    its fact's producer in `00-produced-facts.md`, position 0 — always
    the earliest section, so this edge alone backs reachability for
    every consumer (`fact-production` spec, `Requirement: Every Producer
    Is Either Sole Or Corroborated`; design.md, Decision C). Reuses the
    SAME `requires_facts` quote already anchored in `filename`'s own
    prose — no second sentence needed."""
    return [{
        "target": f"produced-facts.pf-{fact}",
        "source": {
            "file": f"sections/{filename}",
            "quote": f"This block requires the {fact}.",
        },
    }]


_COUPLING_SECTIONS = {
    "00-produced-facts.md": {
        "section": "produced-facts", "position": 0,
        "blocks": [
            {"id": f"pf-{fact}",
             "requires_facts": [], "requires_declarations": [], "citations": "none",
             "produces_facts": [_coupling_production(fact, "00-produced-facts.md")]}
            for fact in ("contributions", "problem-statement", "limitations")
        ],
    },
    "01-introduction.md": {
        "section": "introduction", "position": 1,
        "blocks": [
            {"id": "intro-contrib",
             "requires_facts": [_coupling_requirement("contributions", "01-introduction.md")],
             "requires_declarations": [], "citations": "none",
             "after": _coupling_after("contributions", "01-introduction.md")},
            # `gap`'s two CORROBORATED producers (`a-fact-is-declared-or-
            # it-is-produced`, design.md Decision F: `gap` is the one fact
            # `paper_verify.CHECKS` corroborates, so exactly two producers
            # are legal) -- `intro-gap` is one of them, never a consumer,
            # matching the real corpus's own `introduction.block-3` shape.
            {"id": "intro-gap",
             "requires_facts": [], "requires_declarations": [], "citations": "none",
             "produces_facts": [_coupling_production("gap", "01-introduction.md")]},
        ],
    },
    "02-methods.md": {
        "section": "methods", "position": 2,
        "blocks": [
            {"id": "methods-contrib",
             "requires_facts": [_coupling_requirement("contributions", "02-methods.md")],
             "requires_declarations": [], "citations": "none",
             "after": _coupling_after("contributions", "02-methods.md")},
            {"id": "methods-chain",
             "requires_facts": [_coupling_requirement("problem-statement", "02-methods.md")],
             "requires_declarations": [], "citations": "none",
             "after": _coupling_after("problem-statement", "02-methods.md")},
        ],
    },
    "03-related-work.md": {
        "section": "related-work", "position": 3,
        "blocks": [
            # `gap`'s other corroborated producer -- matches the real
            # corpus's own `related-work.rw-closing` shape.
            {"id": "related-work-gap",
             "requires_facts": [], "requires_declarations": [], "citations": "none",
             "produces_facts": [_coupling_production("gap", "03-related-work.md")]},
        ],
    },
    "04-abstract.md": {
        "section": "abstract", "position": 4,
        "blocks": [
            {"id": "abstract-contrib",
             "requires_facts": [_coupling_requirement("contributions", "04-abstract.md")],
             "requires_declarations": [], "citations": "none",
             "after": _coupling_after("contributions", "04-abstract.md")},
        ],
    },
    "05-conclusions.md": {
        "section": "conclusions", "position": 5,
        "blocks": [
            {"id": "conclusions-contrib",
             "requires_facts": [_coupling_requirement("contributions", "05-conclusions.md")],
             "requires_declarations": [], "citations": "none",
             "after": _coupling_after("contributions", "05-conclusions.md")},
            {"id": "conclusions-future",
             "requires_facts": [_coupling_requirement("limitations", "05-conclusions.md")],
             "requires_declarations": [], "citations": "discovery",
             "after": _coupling_after("limitations", "05-conclusions.md")},
        ],
    },
}

#: Every fact this fixture's blocks require, in file declaration order —
#: `_write_coupling_sections` appends one `This block requires the
#: <fact>.` sentence per fact to that file's own prose, matching
#: `_coupling_requirement`'s quote exactly. `00-produced-facts.md`'s own
#: blocks require nothing, so they contribute no entry here.
_COUPLING_FACTS_BY_FILE = {
    name: [entry["requires_facts"][0]["value"] for entry in header["blocks"] if entry["requires_facts"]]
    for name, header in _COUPLING_SECTIONS.items()
}

#: The `produces_facts` mirror of `_COUPLING_FACTS_BY_FILE` — only
#: `00-produced-facts.md` carries any.
_COUPLING_PRODUCES_BY_FILE = {
    name: [
        entry["produces_facts"][0]["value"]
        for entry in header["blocks"] if entry.get("produces_facts")
    ]
    for name, header in _COUPLING_SECTIONS.items()
}

#: Every block's body bytes in the fully-declared green fixture -- literal
#: enough that each check's own mechanical extraction (first-occurrence
#: order, role-prefixed chain lines, `\\item`/`Closing:` gap shape,
#: `\\cite{}`) is exercised against real bytes, never a hand-built
#: `Evidence` alone. Order inside `intro-contrib`/`methods-contrib`/
#: `abstract-contrib`/`conclusions-contrib` matches `_COUPLING_CONTRIBUTIONS`
#: exactly, so the unmutated tree is reachable-green on coupling 1.
_COUPLING_BODIES = {
    "intro-contrib": (
        b"This work makes three contributions: Adaptive Caching improves "
        b"hit rates, Async Prefetch reduces stalls, and Bounded Retry "
        b"avoids cascading failures.\n"
    ),
    "intro-gap": (
        b"\\item first study\n\\item second study\n"
        b"Closing: nobody has studied the combination.\n"
    ),
    "methods-contrib": (
        b"Section 3 implements Adaptive Caching first, then Async "
        b"Prefetch, and finally Bounded Retry.\n"
    ),
    "methods-chain": (
        b"Problem: Bounded Retry addresses cascading failures under load.\n"
        b"Contribution: Bounded Retry limits retries safely.\n"
        b"Property: Bounded Retry is measured by retry count.\n"
        b"Instrument: Bounded Retry is captured by the profiler.\n"
        b"Evidence: Bounded Retry reduces failures after deployment.\n"
    ),
    "related-work-gap": (
        b"\\item first study\n\\item second study\n"
        b"Closing: nobody has studied the combination.\n"
    ),
    "abstract-contrib": (
        b"In brief: Adaptive Caching, Async Prefetch, and Bounded Retry "
        b"together cut overhead.\n"
    ),
    "conclusions-contrib": (
        b"We summarize Adaptive Caching, Async Prefetch, and Bounded Retry "
        b"as the paper's contributions.\n"
    ),
    "conclusions-future": (
        b"Future work should extend Bounded Retry \\cite{future2027}.\n"
    ),
}

#: Blocks whose `substitute` call also records provenance -- both point at
#: the SAME contract file (`02-methods.md`), so `contract-currency`'s own
#: "one edit flags a whole section" requirement is directly exercisable: a
#: one-byte edit to that one file must stale BOTH blocks, not only one.
_COUPLING_PROVENANCE_BLOCKS = ("methods-contrib", "methods-chain")


#: `contract-input-partition` spec, `Requirement: A Produced-Fact Dependency
#: Is An Internal-Chain Row`: the three facts `00-produced-facts.md`
#: produces for a SEPARATE consumer to require -- `gap` is excluded, its two
#: corroborated producers (`intro-gap`/`related-work-gap`) never require it
#: themselves, so no row is ever needed for it in this fixture.
_COUPLING_PRODUCED_FACTS = frozenset({"contributions", "problem-statement", "limitations"})


def _coupling_internal_chain_rows(section_id: str, header: dict) -> list:
    """Every `(holder, dependency)` internal-chain row this fixture's own
    producer/consumer edges need -- one row per block requiring a fact
    `00-produced-facts.md` produces, naming that fact's producer block
    directly, so `paper_graph._verify_producer_chain_rows` finds it."""
    rows = []
    for block in header["blocks"]:
        for entry in block.get("requires_facts", []):
            fact = entry["value"]
            if fact in _COUPLING_PRODUCED_FACTS:
                rows.append((f"{section_id}.{block['id']}", f"produced-facts.pf-{fact}"))
    return rows


def _write_coupling_sections(sections_dir: Path) -> None:
    """`contract-input-partition` spec, `Requirement: Two-Heading
    Partition`: every assembled contract must carry `### External inputs`
    and `### Internal chain`, or `paper_graph.assemble_corpus` refuses
    `INPUT_PARTITION_ABSENT` -- this fixture's own concern
    (`the-couplings-hold-or-they-do-not`) is unrelated to that partition, so
    `### External inputs` is added empty, never populated with invented
    content. `### Internal chain` carries a real row for every block
    requiring a fact `00-produced-facts.md` produces (`fact-production`
    spec; `contract-input-partition` spec's own added row-presence
    requirement) -- `None.` only for a file with no such block."""
    sections_dir.mkdir(parents=True, exist_ok=True)
    for name, header in _COUPLING_SECTIONS.items():
        anchors = "".join(
            f" This block requires the {fact}." for fact in _COUPLING_FACTS_BY_FILE[name]
        ) + "".join(
            f" This block produces the {fact}." for fact in _COUPLING_PRODUCES_BY_FILE[name]
        )
        rows = _coupling_internal_chain_rows(header["section"], header)
        if rows:
            table_rows = "\n".join(f"| `{holder}` | `{dependency}` |" for holder, dependency in rows)
            internal_chain = f"### Internal chain\n\n| Block | Depends on |\n|---|---|\n{table_rows}\n"
        else:
            internal_chain = "### Internal chain\n\nNone.\n"
        text = (
            "---\n" + json.dumps(header, indent=2) + "\n---\n\nProse." + anchors + "\n\n"
            "### External inputs\n\nNone.\n\n" + internal_chain
        )
        (sections_dir / name).write_text(text, encoding="utf-8")


def _coupling_record(**overrides) -> dict:
    """The fully-declared green `paper/couplings.json` record. `overrides`
    replaces whole top-level keys (never deep-merged) -- a mutation test
    that wants "the same record, minus one field" builds that dict itself
    from this function's own return value, which is the point: no hidden
    default is mutated in place."""
    record = {
        "facts": {
            "contributions": list(_COUPLING_CONTRIBUTIONS),
            "limitations": ["lim-overhead"],
        },
        "chain": {"links": [{"word": "Bounded Retry"}]},
        "artefacts": {
            "setup_cells": ["cell-alpha", "cell-beta"],
            "results_artefacts": ["cell-alpha"],
        },
        "future_work": {
            "directions": [
                {"id": "extend-retry", "limitation": "lim-overhead", "cite_key": "future2027"},
            ],
        },
        "blocks": {block_id: True for block_id in _COUPLING_BODIES},
    }
    record.update(overrides)
    return record


def _build_coupling_paper(
    paper_dir: Path, sections_dir: Path, *,
    bodies: dict | None = None, record: dict | None = None,
    provenance_blocks=_COUPLING_PROVENANCE_BLOCKS, write_refs_bib: bool = True,
) -> None:
    """Builds a real, on-disk fixture tree through the SAME production
    calls an operator would use (`scaffold`, `open`, `substitute
    --contract`) -- never a hand-assembled `main.tex`, so every marker
    digest and every provenance `contract_sha256` is genuine rather than
    computed by this helper a second, possibly-drifting way."""
    _write_coupling_sections(sections_dir)
    paper_scaffold.scaffold(paper_dir)
    bodies = _COUPLING_BODIES if bodies is None else bodies
    for block_id, body in bodies.items():
        paper_block.open_block(paper_dir, block_id, at_end=True)
        contract = sections_dir / "02-methods.md" if block_id in provenance_blocks else None
        paper_block.substitute(paper_dir, block_id, new_body=body, contract=contract)
    if write_refs_bib:
        (paper_dir / "refs.bib").write_text(
            "@article{future2027,\n  title={Future Work},\n  year={2027}\n}\n",
            encoding="utf-8",
        )
    record = _coupling_record() if record is None else record
    (paper_dir / "couplings.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


class EvidenceTests(unittest.TestCase):
    """`paper_coupling_evidence.py`: the record grammar, and M6."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.sections_dir = Path(self._tmp.name) / "sections"

    def test_gather_reads_the_declared_record_and_the_provenance_region(self) -> None:
        _build_coupling_paper(self.paper_dir, self.sections_dir)

        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

        self.assertEqual(evidence.record["facts"]["contributions"], _COUPLING_CONTRIBUTIONS)
        self.assertIsNotNone(evidence.provenance)
        self.assertEqual(
            {entry["block"] for entry in evidence.provenance["body"]["records"]},
            set(_COUPLING_PROVENANCE_BLOCKS),
        )
        self.assertEqual(evidence.block_bodies["intro-contrib"], _COUPLING_BODIES["intro-contrib"])
        self.assertEqual(
            evidence.blocks_by_fact["contributions"][0],
            ("abstract-contrib", "conclusions-contrib", "intro-contrib", "methods-contrib"),
        )

    def test_gather_without_provenance_reports_it_absent(self) -> None:
        _build_coupling_paper(self.paper_dir, self.sections_dir, provenance_blocks=())

        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

        self.assertIsNone(evidence.provenance)
        self.assertEqual(evidence.contract_drift, {})

    def test_mutation_6_absent_declaration_record_refuses_and_writes_nothing(self) -> None:
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        (self.paper_dir / "couplings.json").unlink()
        before = (self.paper_dir / "main.tex").read_bytes()

        with self.assertRaises(Refused) as ctx:
            paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

        self.assertEqual(ctx.exception.code, "DECLARATION_RECORD_ABSENT")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), before)

    def test_mutation_6_empty_declaration_record_refuses(self) -> None:
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        (self.paper_dir / "couplings.json").write_text("{}", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

        self.assertEqual(ctx.exception.code, "DECLARATION_RECORD_ABSENT")

    def test_headerless_sections_report_unreadable_never_refuse(self) -> None:
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        (self.sections_dir / "01-introduction.md").write_text("no front matter here\n", encoding="utf-8")

        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

        self.assertEqual(
            evidence.blocks_by_fact["contributions"], ((), "SECTION_CONTRACTS_UNREADABLE"),
        )

    def test_no_block_requires_an_unused_fact(self) -> None:
        _build_coupling_paper(self.paper_dir, self.sections_dir)

        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

        self.assertEqual(evidence.blocks_by_fact["dataset"], ((), "NO_BLOCK_REQUIRES_FACT"))


class ReportShapeTests(unittest.TestCase):
    """`paper_verify.py`'s report: the closed roster is one declaration,
    proven both directions, and `unmeasured` is never counted in `holds`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.sections_dir = Path(self._tmp.name) / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        self.evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

    def test_report_carries_exactly_one_object_per_check_both_directions(self) -> None:
        report = paper_verify.run(self.evidence)

        reported = [entry["check"] for entry in report["checks"]]
        self.assertEqual(reported, list(paper_verify.CHECKS))
        self.assertEqual(set(reported), set(paper_verify.CHECKS))

    def test_buckets_sum_to_the_roster_length_and_unmeasured_excluded_from_holds(self) -> None:
        report = paper_verify.run(self.evidence)

        self.assertEqual(report["holds"] + report["fails"] + report["unmeasured"], len(paper_verify.CHECKS))
        unmeasured_checks = [entry["check"] for entry in report["checks"] if entry["verdict"] == "unmeasured"]
        self.assertNotIn("holds", [entry["verdict"] for entry in report["checks"] if entry["check"] in unmeasured_checks])

    def test_every_unmeasured_reason_used_is_in_the_closed_roster(self) -> None:
        report = paper_verify.run(self.evidence)

        for entry in report["checks"]:
            if entry["verdict"] == "unmeasured":
                self.assertIn(entry["unmeasured_reason"], paper_verify.UNMEASURED_REASONS)
            else:
                self.assertIsNone(entry["unmeasured_reason"])

    def test_gap_check_is_unconditionally_unmeasured_and_all_declared_sides_carry_the_limit(self) -> None:
        report = paper_verify.run(self.evidence)
        by_check = {entry["check"]: entry for entry in report["checks"]}

        self.assertEqual(by_check["gap"]["verdict"], "unmeasured")
        self.assertEqual(by_check["gap"]["unmeasured_reason"], "ASSISTED_READING_REQUIRED")

    def test_two_declared_sides_limit_is_derived_never_hand_listed(self) -> None:
        # None of the seven checks' baseline `sides` are ALL declared
        # (`skill-audit`'s own shape prefers a derived side wherever one is
        # possible), so this is a report-level property of `_entry` itself,
        # proven directly -- never a hand-list of which check ever reaches
        # it, matching design.md's own "a test derives that condition from
        # the report rather than a hand-list".
        all_declared = paper_verify._entry(
            "contribution-list", classification="mechanical", verdict="pass",
            sides=[
                {"name": "a", "source": "declared", "origin": "x"},
                {"name": "b", "source": "declared", "origin": "y"},
            ],
            evidence={}, limits=[], unmeasured_reason=None,
        )
        self.assertIn("TWO_DECLARED_SIDES", all_declared["limits"])

        mixed = paper_verify._entry(
            "contribution-list", classification="mechanical", verdict="pass",
            sides=[
                {"name": "a", "source": "declared", "origin": "x"},
                {"name": "b", "source": "derived", "origin": "y"},
            ],
            evidence={}, limits=[], unmeasured_reason=None,
        )
        self.assertNotIn("TWO_DECLARED_SIDES", mixed["limits"])

        # And the real report: no check's baseline sides are all declared.
        report = paper_verify.run(self.evidence)
        for entry in report["checks"]:
            if entry["sides"] and all(side["source"] == "declared" for side in entry["sides"]):
                self.assertIn("TWO_DECLARED_SIDES", entry["limits"])


class ReadOnlyTests(unittest.TestCase):
    """The three-way proof `verify` never writes: the AST lock, an executed
    content manifest, and M8 -- the manifest test itself, mutated."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.sections_dir = Path(self._tmp.name) / "sections"

    def _forbidden_write_calls(self, source_path: Path) -> list:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        forbidden_names = {
            "write_bytes", "write_text", "mkdir", "unlink", "replace", "rename",
        }
        forbidden_modules = {"shutil", "tempfile"}
        hits: list = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_modules:
                        hits.append(f"import {alias.name}")
            if isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                hits.append(node.attr)
            if isinstance(node, ast.Attribute) and node.attr in ("substitute", "open_block"):
                if isinstance(node.value, ast.Name) and node.value.id == "paper_block":
                    hits.append(f"paper_block.{node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                # A bare `open(...)` call -- this module never opens a file
                # directly (Path.read_bytes/read_text are used instead), so
                # any occurrence at all is worth naming.
                hits.append("open(...)")
        return hits

    def test_ast_lock_finds_no_write_operation_in_either_module(self) -> None:
        for name in ("paper_coupling_evidence.py", "paper_verify.py"):
            with self.subTest(module=name):
                self.assertEqual(self._forbidden_write_calls(SKILL_SCRIPTS / name), [])

    #: The only imports `paper_verify.py` has ever needed -- a closed
    #: ALLOWlist, not a hand-picked list of banned function names. The
    #: distinction matters: a denylist of forbidden calls is complete only
    #: by whoever remembered to add to it (this build's own repeated
    #: objection); a default-deny allowlist forecloses the ENTIRE universe
    #: of disk/network/process-capable stdlib modules in one shot --
    #: `pathlib`, `os`, `io`, `shutil`, `tempfile`, `sqlite3`, `socket`,
    #: `subprocess`, `ctypes`, and everything else never named here -- by
    #: construction, not by enumeration. Growing this set is a deliberate,
    #: visible test edit; nothing shrinks it silently.
    _PAPER_VERIFY_ALLOWED_IMPORTS = frozenset({"re"})
    _PAPER_VERIFY_ALLOWED_IMPORT_FROM_MODULES = frozenset({"__future__"})

    def _forbidden_reads(self, source_path: Path) -> list:
        """The read-side half of the disk-access lock. Two constructions,
        neither a hand-picked list of banned function names:

        1. A default-deny IMPORT allowlist (`_PAPER_VERIFY_ALLOWED_IMPORTS`
           / `_..._IMPORT_FROM_MODULES`, above). Any import beyond `re`
           (and `__future__`) is forbidden outright, and so is routing
           around the allowlist via dynamic import (`__import__(...)`,
           `importlib.import_module(...)`).
        2. Every `Evidence` field actually typed `Path`, read live off
           `paper_coupling_evidence.Evidence`'s own dataclass fields via
           `dataclasses.fields` -- never hand-typed here. Today that is
           `paper_dir`/`sections_dir`, kept on the object, per that
           dataclass's own docstring, only so `verify`'s report can name
           where evidence came from -- never so a check could re-open a
           file `gather()` already read. Touching either attribute at all,
           from any expression, is forbidden: a pure check has no
           legitimate reason to reach for either one.

        This is meaningful only for `paper_verify.py` -- `paper_coupling_
        evidence.py`'s entire job is reading, so this exact check would
        flag its own legitimate imports and parameters
        (`test_the_read_lock_would_flag_coupling_evidence_if_misapplied`,
        below proves it, rather than leaving the asymmetry asserted only in
        prose).
        """
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        path_field_names = {
            f.name for f in dataclasses.fields(paper_coupling_evidence.Evidence)
            if f.type == "Path"
        }
        hits: list = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name not in self._PAPER_VERIFY_ALLOWED_IMPORTS:
                        hits.append(f"import {alias.name}")
            if isinstance(node, ast.ImportFrom):
                if node.module not in self._PAPER_VERIFY_ALLOWED_IMPORT_FROM_MODULES:
                    hits.append(f"from {node.module} import ...")
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "__import__":
                    hits.append("__import__(...)")
                if isinstance(func, ast.Attribute) and func.attr == "import_module":
                    hits.append("importlib.import_module(...)")
            if isinstance(node, ast.Attribute) and node.attr in path_field_names:
                hits.append(f"evidence.{node.attr}")
        return hits

    def test_ast_lock_finds_no_disk_read_in_paper_verify(self) -> None:
        self.assertEqual(self._forbidden_reads(SKILL_SCRIPTS / "paper_verify.py"), [])

    def test_the_read_lock_would_flag_coupling_evidence_if_misapplied(self) -> None:
        # Proof the scoping to paper_verify.py alone is doing real work,
        # not silently vacuous: paper_coupling_evidence.py's own legitimate
        # `json`/`sys`/`pathlib` imports and its own `paper_dir`/
        # `sections_dir` parameters would trip this exact lock if it were
        # ever pointed at the reader by mistake -- the two files are
        # asymmetric by measurement, never by omission.
        hits = self._forbidden_reads(SKILL_SCRIPTS / "paper_coupling_evidence.py")
        self.assertTrue(hits, "expected the read lock to flag the reader's own legitimate imports")

    def test_coupling_evidence_legitimate_reads_still_pass(self) -> None:
        # A lock that forbade reads everywhere would break the reader whose
        # entire job is reading -- confirm `gather()` still performs its
        # real disk reads end to end, unaffected by the lock above (which
        # is never applied to this module).
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)
        self.assertEqual(evidence.paper_dir, self.paper_dir)
        self.assertEqual(evidence.sections_dir, self.sections_dir)
        self.assertTrue(evidence.main_tex_bytes)
        self.assertTrue(evidence.record)

    def test_content_manifest_unchanged_by_a_real_verify_run(self) -> None:
        _build_coupling_paper(self.paper_dir, self.sections_dir)

        def _manifest() -> dict:
            return {
                str(path.relative_to(self.paper_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(self.paper_dir.rglob("*")) if path.is_file()
            }

        before = _manifest()
        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)
        paper_verify.run(evidence)
        after = _manifest()

        self.assertEqual(before, after)

    def test_mutation_8_a_write_in_paper_verify_fails_the_manifest_guard(self) -> None:
        proc = _run_against_mutant(
            "def run(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:",
            'def run(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:\n'
            '    import pathlib as _pl\n'
            '    _pl.Path(evidence.paper_dir, "main.tex").write_bytes(b"x")',
            "tests.test_paper_writing.ReadOnlyTests.test_content_manifest_unchanged_by_a_real_verify_run",
            source_path=SKILL_SCRIPTS / "paper_verify.py",
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("MUTANT_IMPORTED_OK", proc.stdout)


class CouplingOneTests(unittest.TestCase):
    """Coupling 1 (`coupling-verification` spec, `Requirement: Coupling 1
    — Contribution List Identity`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.sections_dir = Path(self._tmp.name) / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        self.evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

    def test_unmutated_fixture_holds(self) -> None:
        result = paper_verify.check_contribution_list(self.evidence)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["evidence"]["mismatched_blocks"], [])
        self.assertEqual(result["evidence"]["absent_from_bytes"], [])

    def test_mutation_1_reordered_names_in_one_block_fails(self) -> None:
        reordered = (
            b"In brief: Async Prefetch, Adaptive Caching, and Bounded Retry "
            b"together cut overhead.\n"
        )
        mutated = dataclasses.replace(
            self.evidence,
            block_bodies={**self.evidence.block_bodies, "abstract-contrib": reordered},
        )

        result = paper_verify.check_contribution_list(mutated)

        self.assertEqual(result["verdict"], "fail")
        self.assertIn("abstract-contrib", result["evidence"]["mismatched_blocks"])

    def test_declared_name_absent_from_block_bytes_fails_distinctly(self) -> None:
        missing_name = b"In brief: Adaptive Caching and Async Prefetch cut overhead.\n"
        mutated = dataclasses.replace(
            self.evidence,
            block_bodies={**self.evidence.block_bodies, "abstract-contrib": missing_name},
        )

        result = paper_verify.check_contribution_list(mutated)

        self.assertEqual(result["verdict"], "fail")
        # The evidence payload names this as an absent-name finding
        # distinctly from a plain order mismatch, even though a block
        # missing a name can never equal the full declared order either
        # (spec, `Requirement: Declared-Name Literal Presence Limit`):
        # both reasons are reported, neither one hides the other.
        self.assertIn(
            {"block": "abstract-contrib", "name": "Bounded Retry"},
            result["evidence"]["absent_from_bytes"],
        )

    def test_an_undeclared_block_reports_unmeasured_not_pass(self) -> None:
        record = _coupling_record()
        del record["blocks"]["abstract-contrib"]
        mutated = dataclasses.replace(self.evidence, record=record)

        result = paper_verify.check_contribution_list(mutated)

        self.assertEqual(result["verdict"], "unmeasured")
        self.assertEqual(result["unmeasured_reason"], "BLOCK_NOT_DECLARED")


class CouplingTwoTests(unittest.TestCase):
    """Coupling 2 (`coupling-verification` spec, `Requirement: Coupling 2
    — Chain Word Identity`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.sections_dir = Path(self._tmp.name) / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        self.evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

    def test_unmutated_fixture_holds(self) -> None:
        result = paper_verify.check_chain(self.evidence)
        self.assertEqual(result["verdict"], "pass")

    def test_mutation_2_synonym_at_one_link_fails(self) -> None:
        # "Elastic Backoff" is not a substring of "Bounded Retry" -- a
        # synonym, never a paraphrase that would still pass a substring
        # check by accident.
        synonym_body = (
            b"Problem: Bounded Retry addresses cascading failures under load.\n"
            b"Contribution: Elastic Backoff limits retries safely.\n"
            b"Property: Bounded Retry is measured by retry count.\n"
            b"Instrument: Bounded Retry is captured by the profiler.\n"
            b"Evidence: Bounded Retry reduces failures after deployment.\n"
        )
        mutated = dataclasses.replace(
            self.evidence,
            block_bodies={**self.evidence.block_bodies, "methods-chain": synonym_body},
        )

        result = paper_verify.check_chain(mutated)

        self.assertEqual(result["verdict"], "fail")
        self.assertFalse(result["evidence"]["links"][0]["roles_present"]["contribution"])

    def test_closure_against_an_undeclared_word_fails(self) -> None:
        record = _coupling_record()
        record["chain"] = {"links": [{"word": "Not A Contribution"}]}
        mutated = dataclasses.replace(self.evidence, record=record)

        result = paper_verify.check_chain(mutated)

        self.assertEqual(result["verdict"], "fail")
        self.assertFalse(result["evidence"]["links"][0]["closure"])


class CitationTests(unittest.TestCase):
    """Check A (`citation-integrity` spec)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.sections_dir = Path(self._tmp.name) / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        self.evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

    def test_unmutated_fixture_holds_with_no_dangling_or_orphan(self) -> None:
        result = paper_verify.check_citations(self.evidence)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["evidence"]["dangling"], [])
        self.assertEqual(result["evidence"]["orphans"], [])

    def test_mutation_3a_dangling_cite_fails_naming_it(self) -> None:
        mutated = dataclasses.replace(
            self.evidence,
            main_tex_bytes=self.evidence.main_tex_bytes + b"\\cite{ghost}\n",
        )

        result = paper_verify.check_citations(mutated)

        self.assertEqual(result["verdict"], "fail")
        self.assertIn("ghost", result["evidence"]["dangling"])
        # M3a alone must not move the orphan-entry direction.
        self.assertEqual(result["evidence"]["orphans"], [])

    def test_mutation_3b_orphan_entry_is_listed_not_failing(self) -> None:
        mutated = dataclasses.replace(
            self.evidence,
            refs_bib_bytes=self.evidence.refs_bib_bytes
            + b"@article{orphan2028,\n  title={Nobody Cites This},\n  year={2028}\n}\n",
        )

        result = paper_verify.check_citations(mutated)

        # M3b alone must not move the dangling-cite direction.
        self.assertEqual(result["evidence"]["dangling"], [])
        self.assertIn("orphan2028", result["evidence"]["orphans"])
        self.assertEqual(result["verdict"], "pass")


class GapTests(unittest.TestCase):
    """Coupling 3 (`coupling-verification` spec, `Requirement: Coupling 3
    — The Gap Is Assisted`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.sections_dir = Path(self._tmp.name) / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        self.evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

    def test_unmutated_fixture_is_unconditionally_unmeasured_with_clean_mechanical_subchecks(self) -> None:
        result = paper_verify.check_gap(self.evidence)

        self.assertEqual(result["verdict"], "unmeasured")
        self.assertEqual(result["unmeasured_reason"], "ASSISTED_READING_REQUIRED")
        mechanical = result["evidence"]["mechanical"]
        self.assertTrue(mechanical["both_closings_present"])
        self.assertTrue(mechanical["fronts_equal"])
        self.assertTrue(mechanical["front_counts_equal"])
        self.assertEqual(result["evidence"]["depth_reading"], "unmeasured")

    def test_both_full_texts_and_front_lists_are_published(self) -> None:
        result = paper_verify.check_gap(self.evidence)

        self.assertEqual(
            result["evidence"]["closings"]["intro-gap"], "nobody has studied the combination.",
        )
        self.assertEqual(result["evidence"]["fronts"]["intro-gap"], ["first study", "second study"])

    def test_a_missing_closing_is_a_mechanical_fact_never_a_gate(self) -> None:
        no_closing = b"\\item first study\n\\item second study\n"
        mutated = dataclasses.replace(
            self.evidence,
            block_bodies={**self.evidence.block_bodies, "intro-gap": no_closing},
        )

        result = paper_verify.check_gap(mutated)

        # Still unconditionally unmeasured -- a mechanical failure never
        # promotes or demotes the top-level verdict.
        self.assertEqual(result["verdict"], "unmeasured")
        self.assertFalse(result["evidence"]["mechanical"]["both_closings_present"])

    def test_unequal_front_counts_report_mechanical_fail_still_unmeasured(self) -> None:
        three_items = (
            b"\\item first study\n\\item second study\n\\item third study\n"
            b"Closing: nobody has studied the combination.\n"
        )
        mutated = dataclasses.replace(
            self.evidence,
            block_bodies={**self.evidence.block_bodies, "related-work-gap": three_items},
        )

        result = paper_verify.check_gap(mutated)

        self.assertEqual(result["verdict"], "unmeasured")
        self.assertFalse(result["evidence"]["mechanical"]["front_counts_equal"])
        self.assertFalse(result["evidence"]["mechanical"]["fronts_equal"])


class RealCorpusGapPairingTests(unittest.TestCase):
    """`a-fact-is-declared-or-it-is-produced`, design.md Decision F / tasks.md
    Unit 3, 3.7: against the REAL shipped corpus, `check_gap`'s pair is the
    two PRODUCERS of `gap` -- `related-work.rw-closing` and `introduction.
    block-3` -- never `experimental-setup.es-assessment`, which requires
    `gap` in its own `requires_facts` for an unrelated reason and must never
    be read as this coupling's counterpart (`coupling-verification` spec,
    `Requirement: Coupling 3 — The Gap Is Assisted`, 'Pairing resolves to
    the two corroborated producers of gap')."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        (self.paper_dir / "couplings.json").write_text(
            json.dumps({"blocks": {"placeholder": True}}), encoding="utf-8",
        )

    def test_producers_by_fact_resolves_gaps_two_producers_from_the_real_corpus(self) -> None:
        evidence = paper_coupling_evidence.gather(self.paper_dir, SECTIONS_DIR)

        block_ids, reason = evidence.producers_by_fact["gap"]

        self.assertIsNone(reason)
        self.assertEqual(set(block_ids), {"rw-closing", "block-3"})

    def test_the_published_pair_is_the_two_producers_never_es_assessment(self) -> None:
        evidence = paper_coupling_evidence.gather(self.paper_dir, SECTIONS_DIR)

        result = paper_verify.check_gap(evidence)

        published_ids = set(result["evidence"]["closings"])
        self.assertEqual(published_ids, {"rw-closing", "block-3"})
        self.assertNotIn("es-assessment", published_ids)

    def test_mutation_reverting_to_consumer_scan_pairing_is_caught(self) -> None:
        """tasks.md 3.8: revert `check_gap` to `evidence.blocks_by_fact`
        (the consumer-scan mapping) and confirm the real-corpus pairing
        proof above fails, since the real corpus's ONLY `requires_facts`
        consumer of `gap` is `experimental-setup.es-assessment` alone --
        never the two producers."""
        proc = _run_against_mutant(
            'block_ids, reason = evidence.producers_by_fact.get('
            '"gap", ((), "SECTION_CONTRACTS_UNREADABLE"))',
            'block_ids, reason = evidence.blocks_by_fact.get('
            '"gap", ((), "SECTION_CONTRACTS_UNREADABLE"))',
            "tests.test_paper_writing.RealCorpusGapPairingTests"
            ".test_the_published_pair_is_the_two_producers_never_es_assessment",
            source_path=SKILL_SCRIPTS / "paper_verify.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class CheckGapProducerPairingRegressionTests(unittest.TestCase):
    """tasks.md 3.9: `check_chain`/`check_contribution_list`/`check_future_
    work` must keep reading `evidence.blocks_by_fact` -- the consumer-scan
    mapping `check_chain`'s own `zip(block_ids, links)` depends on for
    link/block alignment (design.md, Decision F) -- and must never be
    repointed at the new `producers_by_fact` mapping only `check_gap`
    reads."""

    def test_the_three_untouched_checks_still_read_blocks_by_fact_only(self) -> None:
        for fn in (
            paper_verify.check_chain,
            paper_verify.check_contribution_list,
            paper_verify.check_future_work,
        ):
            with self.subTest(check=fn.__name__):
                source = inspect.getsource(fn)
                self.assertIn("evidence.blocks_by_fact", source)
                self.assertNotIn("producers_by_fact", source)

    def test_check_gap_reads_producers_by_fact_not_blocks_by_fact(self) -> None:
        source = inspect.getsource(paper_verify.check_gap)
        self.assertIn("evidence.producers_by_fact", source)
        self.assertNotIn("evidence.blocks_by_fact", source)


class ArtefactsTests(unittest.TestCase):
    """Coupling 4 (`coupling-verification` spec, `Requirement: Coupling 4
    — Diagram Cell Disjointness`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.sections_dir = Path(self._tmp.name) / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        self.evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

    def test_unmutated_fixture_holds(self) -> None:
        result = paper_verify.check_artefacts(self.evidence)
        self.assertEqual(result["verdict"], "pass")

    def test_mutation_4a_undeclared_results_cell_fails(self) -> None:
        record = _coupling_record()
        record["artefacts"]["results_artefacts"] = ["cell-alpha", "cell-nowhere"]
        mutated = dataclasses.replace(self.evidence, record=record)

        result = paper_verify.check_artefacts(mutated)

        self.assertEqual(result["verdict"], "fail")
        self.assertIn("cell-nowhere", result["evidence"]["undeclared_results"])

    def test_mutation_4b_a_contribution_added_to_setup_cells_fails_on_intersection(self) -> None:
        record = _coupling_record()
        record["artefacts"]["setup_cells"] = ["cell-alpha", "cell-beta", "Adaptive Caching"]
        mutated = dataclasses.replace(self.evidence, record=record)

        result = paper_verify.check_artefacts(mutated)

        self.assertEqual(result["verdict"], "fail")
        self.assertIn("Adaptive Caching", result["evidence"]["shared_with_methods"])

    def test_artefacts_inherits_contribution_lists_own_unmeasured_status(self) -> None:
        record = _coupling_record()
        del record["blocks"]["abstract-contrib"]
        mutated = dataclasses.replace(self.evidence, record=record)

        result = paper_verify.check_artefacts(mutated)

        self.assertEqual(result["verdict"], "unmeasured")
        self.assertEqual(result["unmeasured_reason"], "BLOCK_NOT_DECLARED")


class FutureWorkTests(unittest.TestCase):
    """Coupling 5 (`coupling-verification` spec, `Requirement: Coupling 5
    — Future Work ⊆ Limitations`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.sections_dir = Path(self._tmp.name) / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        self.evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

    def test_unmutated_fixture_holds_and_publishes_out_of_reach_subparts(self) -> None:
        result = paper_verify.check_future_work(self.evidence)

        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["evidence"]["relevance"], "out-of-reach")
        self.assertEqual(result["evidence"]["specificity"], "out-of-reach")

    def test_mutation_5_a_direction_answering_no_declared_limitation_fails_totality(self) -> None:
        record = _coupling_record()
        record["future_work"]["directions"] = [
            {"id": "extend-retry", "limitation": "lim-nowhere", "cite_key": "future2027"},
        ]
        mutated = dataclasses.replace(self.evidence, record=record)

        result = paper_verify.check_future_work(mutated)

        self.assertEqual(result["verdict"], "fail")
        self.assertIn("extend-retry", result["evidence"]["unanswered"])

    def test_a_direction_whose_cite_key_never_occurs_in_the_block_fails(self) -> None:
        record = _coupling_record()
        record["future_work"]["directions"] = [
            {"id": "extend-retry", "limitation": "lim-overhead", "cite_key": "nevercited2029"},
        ]
        mutated = dataclasses.replace(self.evidence, record=record)

        result = paper_verify.check_future_work(mutated)

        self.assertEqual(result["verdict"], "fail")
        self.assertIn("extend-retry", result["evidence"]["missing_cite"])


class ContractCurrencyTests(unittest.TestCase):
    """Check B (`contract-currency` spec)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.sections_dir = Path(self._tmp.name) / "sections"

    def test_unmutated_fixture_holds_with_provenance_present(self) -> None:
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

        result = paper_verify.check_contract_currency(evidence)

        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["classification"], "out-of-reach today")

    def test_mutation_7_absent_provenance_region_reports_unmeasured_never_zero_stale(self) -> None:
        _build_coupling_paper(self.paper_dir, self.sections_dir, provenance_blocks=())
        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

        result = paper_verify.check_contract_currency(evidence)

        self.assertEqual(result["verdict"], "unmeasured")
        self.assertEqual(result["unmeasured_reason"], "CONTRACT_RECORD_ABSENT")
        # Run continues -- every OTHER check still reports a real verdict.
        report = paper_verify.run(evidence)
        by_check = {entry["check"]: entry for entry in report["checks"]}
        self.assertEqual(by_check["contribution-list"]["verdict"], "pass")

    def test_one_byte_edit_to_the_shared_contract_file_flags_both_recorded_blocks_stale(self) -> None:
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        contract_path = self.sections_dir / "02-methods.md"
        contract_path.write_text(contract_path.read_text(encoding="utf-8") + "\nOne more line.\n", encoding="utf-8")
        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

        result = paper_verify.check_contract_currency(evidence)

        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(
            sorted(result["evidence"]["stale_blocks"]),
            sorted(_COUPLING_PROVENANCE_BLOCKS),
        )


class CouplingVerifyCLITests(unittest.TestCase):
    """`verify` wired into `paper_cli.py` (`block-substitution` spec,
    `Requirement: verify Verb Is Registered And Read-Only`). Real
    subprocess calls against the real `paper_cli.py` resolve `--paper`/
    `--sections` against the REAL repository root
    (`paper_scaffold.FORGE_ROOT`), so -- the same convention
    `ScaffoldTests.test_cli_scaffold_verb_runs_and_emits_json` already
    established -- this fixture lives under the already-gitignored
    `.scratch/` tree, never an arbitrary tempdir outside it."""

    def setUp(self) -> None:
        test_root = FORGE_ROOT / ".scratch" / f".paper-writing-verify-cli-test-{os.getpid()}"
        self.addCleanup(shutil.rmtree, test_root, ignore_errors=True)
        self.paper_dir = test_root / "paper"
        self.sections_dir = test_root / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)

    def test_a_full_run_leaves_main_tex_untouched_and_exits_zero(self) -> None:
        before = (self.paper_dir / "main.tex").read_bytes()

        proc = subprocess.run(
            [
                sys.executable, str(CLI), "verify",
                "--paper", str(self.paper_dir), "--sections", str(self.sections_dir),
            ],
            capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), before)
        by_check = {entry["check"]: entry for entry in payload["checks"]}
        self.assertEqual(by_check["contribution-list"]["verdict"], "pass")
        self.assertEqual(by_check["gap"]["verdict"], "unmeasured")

    def test_a_refusal_path_also_writes_nothing_and_exits_two(self) -> None:
        (self.paper_dir / "couplings.json").unlink()
        before = (self.paper_dir / "main.tex").read_bytes()

        proc = subprocess.run(
            [
                sys.executable, str(CLI), "verify",
                "--paper", str(self.paper_dir), "--sections", str(self.sections_dir),
            ],
            capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(proc.returncode, 2, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "DECLARATION_RECORD_ABSENT")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), before)

    def test_mutation_9_the_roster_walk_reaches_paper_verify_by_source_not_import(self) -> None:
        """M9 (design.md; tasks.md 3.9) proves the roster walk reaches
        `paper_verify.py` -- this skill's THIRD imported module, beyond
        `paper_coupling_evidence.py` -- without M9, widening the walk to a
        new module is an untested claim.

        `_run_against_mutant` (used for M8, above) cannot prove this: it
        loads the mutant through `sys.modules`, but
        `reachable_paper_refusal_codes()` never imports the modules it
        scans -- it reads each one's own bytes directly from
        `SKILL_SCRIPTS / f"{name}.py"` (`paper_cli_imported_modules()`,
        `tests/test_paper_writing.py`), a fixed real path a `sys.modules`
        substitution cannot redirect. So this is proven by hand, on the
        real file, the same way `ModuleCompletenessTests`'s own docstring
        already documents for its own precedent case: a throwaway
        `Refused` was inserted into `paper_verify.py`, `RefusalRosterTests
        .test_every_reachable_refusal_is_classified` was run and observed
        to fail naming the new code, the insertion was removed, and the
        suite was confirmed green again -- verified during this change's
        own implementation, not re-run automatically on every CI pass
        (planting it permanently would corrupt this skill's own roster for
        every other suite scanning `scripts/*.py`, `ModuleCompletenessTests`'
        own reasoning, reused verbatim here).

        This test instead asserts the STATIC precondition M9 depends on:
        `paper_verify.py` is a member of the whole-module scan set at all,
        so a `Refused` added anywhere in it is picked up by construction.
        """
        self.assertIn(SKILL_SCRIPTS / "paper_verify.py", paper_cli_imported_modules())


class CouplingFixtureLeakTests(unittest.TestCase):
    """The forge leak guard, extended to this capability's own fixture
    tree -- `shipped_documents()` never reaches `tests/`, so nothing else
    in this suite scans it (design.md, `What Breaks`: "the fixture tree...
    must carry no target vocabulary")."""

    def test_the_fixture_bodies_and_record_carry_no_forge_vocabulary(self) -> None:
        sys.path.insert(0, str(FORGE_ROOT / "tests"))
        import forge_vocabulary  # noqa: E402

        texts = [json.dumps(_COUPLING_SECTIONS)] + [
            body.decode("utf-8") for body in _COUPLING_BODIES.values()
        ] + [json.dumps(_coupling_record())]
        leaking = {name: forge_vocabulary.leaks_in(text) for name, text in
                   zip(list(_COUPLING_BODIES) + ["sections", "record"], texts)
                   if forge_vocabulary.leaks_in(text)}
        self.assertEqual(leaking, {})


class ZZLiveAgentGuardTests(unittest.TestCase):
    """`writing-orchestration` spec, `Requirement: No Live Agent Invocation
    In Tests`. Named `ZZ...` so it sorts alphabetically last among this
    module's own test classes (`unittest.TestLoader` iterates `dir(module)`,
    which is sorted) -- every subprocess-launching test class defined above
    (`ScaffoldTests`, `CLIWiringTests`, `MutationProofTests`,
    `WriterMutationProofTests`, `ReadOnlyTests`, `CouplingVerifyCLITests`)
    has therefore already run by the time this assertion executes. The monitor itself (top of this file) is installed
    at import time, so it also covers any subprocess launched by another
    test module collected alongside this one under `python -m unittest
    discover`, for as long as this module stays imported."""

    def test_no_agent_binary_launched_by_any_subprocess_this_run_has_made_so_far(self) -> None:
        self.assertEqual(_live_agent_launches, [])


# =====================================================================
# the-writer-may-assert-only-what-it-was-given -- Work Unit 2
# =====================================================================


class StyleChannelTests(unittest.TestCase):
    """`style-channel` spec."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.guidance_dir = Path(self._tmp.name) / "guidance"

    def _make_reference(self, name: str) -> Path:
        folder = self.guidance_dir / name
        folder.mkdir(parents=True)
        (folder / ".paper-writing.json").write_text(
            json.dumps({"class": "style-reference"}), encoding="utf-8"
        )
        return folder

    def test_a_style_reference_resolves_its_equivalent_block(self) -> None:
        folder = self._make_reference("paperA")
        md = folder / "paperA.md"
        md.write_text("Intro text. The equivalent block reads exactly like this, whole.\n", encoding="utf-8")
        proposals = [{
            "reference": "paperA", "source_md": str(md),
            "span": "The equivalent block reads exactly like this, whole.",
        }]
        recorded, no_equivalent = paper_style.resolve_style_set(self.guidance_dir, proposals)
        self.assertEqual(no_equivalent, [])
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["reference"], "paperA")

    def test_a_resolved_block_is_passed_intact_never_truncated(self) -> None:
        folder = self._make_reference("paperA")
        whole = "Sentence one. Sentence two. Sentence three."
        md = folder / "paperA.md"
        md.write_text(whole, encoding="utf-8")
        proposals = [{"reference": "paperA", "source_md": str(md), "span": whole}]
        recorded, _no_equivalent = paper_style.resolve_style_set(self.guidance_dir, proposals)
        self.assertEqual(recorded[0]["span"], whole)

    def test_r_contains_exactly_the_shown_samples(self) -> None:
        folder_a = self._make_reference("paperA")
        folder_b = self._make_reference("paperB")
        md_a = folder_a / "paperA.md"
        md_a.write_text("Block A body.", encoding="utf-8")
        md_b = folder_b / "paperB.md"
        md_b.write_text("Block B body.", encoding="utf-8")
        proposals = [
            {"reference": "paperA", "source_md": str(md_a), "span": "Block A body."},
            {"reference": "paperB", "source_md": str(md_b), "span": "Block B body."},
        ]
        recorded, no_equivalent = paper_style.resolve_style_set(self.guidance_dir, proposals)
        self.assertEqual(no_equivalent, [])
        self.assertEqual({entry["reference"] for entry in recorded}, {"paperA", "paperB"})
        self.assertEqual({entry["span"] for entry in recorded}, {"Block A body.", "Block B body."})

    def test_a_proposed_span_not_byte_present_refuses_span_not_in_source(self) -> None:
        folder = self._make_reference("paperA")
        md = folder / "paperA.md"
        md.write_text("Real content only.", encoding="utf-8")
        proposals = [{"reference": "paperA", "source_md": str(md), "span": "Fabricated content."}]
        with self.assertRaises(Refused) as ctx:
            paper_style.resolve_style_set(self.guidance_dir, proposals)
        self.assertEqual(ctx.exception.code, "SPAN_NOT_IN_SOURCE")

    def test_no_equivalent_degrades_to_the_empty_style_set(self) -> None:
        self._make_reference("paperA")
        recorded, no_equivalent = paper_style.resolve_style_set(
            self.guidance_dir, [{"reference": "paperA", "noEquivalent": True}],
        )
        self.assertEqual(recorded, [])
        self.assertEqual(no_equivalent, ["paperA"])

    def test_zero_style_references_is_the_empty_style_set(self) -> None:
        recorded, no_equivalent = paper_style.resolve_style_set(self.guidance_dir, [])
        self.assertEqual(recorded, [])
        self.assertEqual(no_equivalent, [])


class StyleLeakDetectionTests(unittest.TestCase):
    """`style-leak-detection` spec. This is the second of the two decisive
    proofs for this change: write one block three times -- two unstyled,
    one styled -- and check both inequalities for real."""

    def test_register_distance_rises_with_style_reported_with_its_control(self) -> None:
        unstyled_a = "The system computes the objective. It reports the result plainly."
        unstyled_b = "The method evaluates the loss. It states the outcome directly."
        styled = (
            "Verily, the apparatus doth compute yon objective most curiously! Behold, it "
            "proclaimeth the result unto thee, exceedingly and most plainly indeed, forsooth!"
        )
        result = paper_leak.register_distance_holds(styled, unstyled_a, unstyled_b)
        self.assertIn("d_S_AB", result)
        self.assertIn("d_AB", result)
        self.assertGreater(result["d_S_AB"], result["d_AB"])
        self.assertTrue(result["pass"], result)

    def test_dropping_the_ab_control_fails_construction(self) -> None:
        with self.assertRaises(TypeError):
            paper_leak.register_distance_holds("styled text", "unstyled a text")

    def test_overlap_stays_at_the_chance_floor_passes(self) -> None:
        samples = [{"reference": "paperA", "span": "the quick brown fox jumps over the lazy dog today"}]
        unstyled_a = "an unrelated sentence about something else entirely today"
        unstyled_b = "a different unrelated sentence about another topic today"
        styled = "yet another styled sentence sharing almost nothing with the sample"
        result = paper_leak.relative_overlap_holds(styled, unstyled_a, unstyled_b, samples)
        self.assertTrue(result["pass"], result)

    def test_styled_overlap_exceeding_both_baselines_fails(self) -> None:
        samples = [{"reference": "paperA", "span": "the quick brown fox jumps over the lazy dog today"}]
        unstyled_a = "completely unrelated text about nothing shared here at all"
        unstyled_b = "another unrelated sentence sharing nothing with the sample text"
        styled = "the quick brown fox jumps over the lazy dog today, verbatim and whole"
        result = paper_leak.relative_overlap_holds(styled, unstyled_a, unstyled_b, samples)
        self.assertFalse(result["pass"], result)
        self.assertGreater(result["overlap_S"], max(result["overlap_A"], result["overlap_B"]))

    def test_relative_overlap_holds_signature_carries_no_threshold(self) -> None:
        sig = inspect.signature(paper_leak.relative_overlap_holds)
        self.assertEqual(list(sig.parameters), ["styled", "unstyled_a", "unstyled_b", "samples"])
        for name in sig.parameters:
            self.assertNotIn("threshold", name.lower())
            self.assertNotIn("min_token", name.lower())

    def test_a_near_verbatim_lifted_sentence_refuses_style_overlap(self) -> None:
        samples = [{"reference": "paperA", "span": "one two three four five six seven eight nine"}]
        styled = "prefix text one two three four five six seven eight nine suffix text"
        with self.assertRaises(Refused) as ctx:
            paper_leak.check_tripwire(styled, samples)
        self.assertEqual(ctx.exception.code, "STYLE_OVERLAP")
        self.assertIn("paperA", ctx.exception.detail)

    def test_shared_math_notation_does_not_trip_the_tripwire(self) -> None:
        shared_math = r"\(\alpha \beta \gamma \delta \epsilon \zeta \eta \theta \iota\)"
        samples = [{"reference": "paperA", "span": f"Some prose. {shared_math} More prose."}]
        styled = f"Different prose entirely. {shared_math} Also different."
        hits = paper_leak.tripwire_spans(styled, samples)
        self.assertEqual(hits, [])

    def test_a_dollar_dollar_display_fence_is_excluded_body_and_all(self) -> None:
        """`style-leak-detection` spec, Scenario "A `$$` display fence is
        excluded, body and all": a sample in `R` and a styled draft `S`
        share the identical equation body between `$$` fences and nothing
        else -- normalization must exclude the fenced body in both, not
        merely its delimiters, so no tokens from inside it ever reach the
        tripwire (design.md, Decision A)."""
        equation_body = "alpha x plus beta x squared plus gamma x cubed minus delta"
        styled = f"Prefix prose shared with nothing else. $$ {equation_body} $$ Suffix unique to styled."
        sample_span = f"Different prefix prose entirely. $$ {equation_body} $$ Suffix unique to sample."
        samples = [{"reference": "sample", "span": sample_span}]
        hits = paper_leak.tripwire_spans(styled, samples)
        self.assertEqual(hits, [], hits)

    def test_mutation_dropping_the_dollar_dollar_alternative_fails_the_display_fence_guard(self) -> None:
        """`style-leak-detection` spec, Scenario "Mutation -- dropping the
        display-fence alternative is caught": with the `$$...$$` alternative
        removed from `paper_style._MATH_DISPLAY_RE`, the display-fence test
        above must go red, proving the exclusion is load-bearing rather than
        merely present."""
        proc = _run_against_mutant(
            r'r"\$\$.*?\$\$|',
            'r"',
            "tests.test_paper_writing.StyleLeakDetectionTests"
            ".test_a_dollar_dollar_display_fence_is_excluded_body_and_all",
            source_path=SKILL_SCRIPTS / "paper_style.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_overlap_ignores_text_in_the_reference_file_outside_r(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ref_file = Path(tmp) / "reference.md"
            ref_file.write_text(
                "Recorded content only here today. UNRECORDED SECRET one two three four "
                "five six seven eight",
                encoding="utf-8",
            )
            samples = [{
                "reference": "paperA", "source_md": str(ref_file),
                "span": "Recorded content only here today.",
            }]
            styled = "UNRECORDED SECRET one two three four five six seven eight"
            self.assertEqual(paper_leak.overlap_against_set(styled, samples), 0)
            self.assertEqual(paper_leak.tripwire_spans(styled, samples), [])


class SourceSectionVerbatimTests(unittest.TestCase):
    """`transposition-fidelity` spec. `check_source_section_verbatim` is a
    SIBLING of `check_tripwire` (`Requirement: The Verbatim Check Is A
    Sibling, Never An Extension Of The Style Tripwire`) -- its own refusal
    code, its own self-calibrated threshold, reusing `overlap_against_set`/
    `tripwire_spans` verbatim rather than re-implementing the overlap/
    hit-scan machinery (design.md, Decision B/C; tasks.md 2.1-2.4)."""

    def test_source_run_backstop_is_sixteen(self) -> None:
        self.assertEqual(paper_leak.SOURCE_RUN_BACKSTOP, 16)

    def test_source_section_floor_reuses_overlap_against_set_verbatim(self) -> None:
        shared_run = _n_token_run(9)
        contract_prose = f"Unrelated framing prose. {shared_run} More unrelated prose."
        section_text = f"Different framing sentence. {shared_run} Different trailing sentence."
        self.assertEqual(
            paper_leak.source_section_floor(contract_prose, section_text),
            paper_leak.overlap_against_set(contract_prose, [{"span": section_text}]),
        )
        self.assertEqual(paper_leak.source_section_floor(contract_prose, section_text), 9)

    def test_a_verbatim_paste_beyond_the_backstop_refuses(self) -> None:
        """Scenario "A draft pasting its bound section verbatim refuses":
        the contract prose shares almost nothing with the section (the
        floor stays under the backstop), so the threshold is the
        sixteen-token backstop; the draft reproduces a seventeen-token run
        from the section, one token past it."""
        section_text = (
            "Some opening sentence about the widget calibration procedure. "
            f"{_n_token_run(17)} A closing sentence about something else."
        )
        contract_prose = "The block's own contract prose shares almost nothing with this section."
        section = {
            "fact": "formulation", "lineage": "widget-study-r4",
            "title": "2. Widget Calibration", "text": section_text,
        }
        draft_latex = f"Opening sentence of the draft. {_n_token_run(17)} Closing sentence of the draft."

        with self.assertRaises(Refused) as ctx:
            paper_leak.check_source_section_verbatim(draft_latex, contract_prose, [section])

        self.assertEqual(ctx.exception.code, "SOURCE_SECTION_VERBATIM")
        self.assertIn("formulation", ctx.exception.detail)
        self.assertIn("widget-study-r4", ctx.exception.detail)
        self.assertIn("2. Widget Calibration", ctx.exception.detail)
        self.assertIn("willow", ctx.exception.detail)

    def test_the_detail_message_names_all_five_fields_at_once(self) -> None:
        """Item 6, `limpieza-de-pendientes-chicos`: the detail string names
        FIVE fields -- `block_id`, the run length, the bound fact, the
        lineage and the section title -- but no single scenario had ever
        asserted all five together; `test_a_verbatim_paste_refuses_before_
        substitute_and_main_tex_stays_unchanged` (above, through
        `write_block`) checks block/fact/lineage and never title or
        length, `test_a_verbatim_paste_beyond_the_backstop_refuses` (above,
        calling this function directly with no `block_id`) checks fact/
        lineage/title and never block or length -- either alone would
        still pass a change that silently dropped one of the two fields
        neither covers. This scenario supplies `block_id` explicitly and
        checks all five in the same assertion set."""
        section_text = (
            "Some opening sentence about the widget calibration procedure. "
            f"{_n_token_run(17)} A closing sentence about something else."
        )
        contract_prose = "The block's own contract prose shares almost nothing with this section."
        section = {
            "fact": "formulation", "lineage": "widget-study-r4",
            "title": "2. Widget Calibration", "text": section_text,
        }
        draft_latex = f"Opening sentence of the draft. {_n_token_run(17)} Closing sentence of the draft."

        with self.assertRaises(Refused) as ctx:
            paper_leak.check_source_section_verbatim(
                draft_latex, contract_prose, [section], block_id="mm-proposal",
            )

        self.assertEqual(ctx.exception.code, "SOURCE_SECTION_VERBATIM")
        self.assertIn("mm-proposal", ctx.exception.detail)
        self.assertIn("17", ctx.exception.detail)
        self.assertIn("formulation", ctx.exception.detail)
        self.assertIn("widget-study-r4", ctx.exception.detail)
        self.assertIn("2. Widget Calibration", ctx.exception.detail)

    def test_the_same_claim_in_different_words_passes(self) -> None:
        """Scenario "The same claim in the paper's own register passes": no
        normalized run longer than a handful of tokens is shared."""
        section_text = (
            "The widget calibration procedure requires careful measurement "
            "of every dial before the run starts."
        )
        contract_prose = "Unrelated contract prose sharing nothing with the section."
        section = {
            "fact": "formulation", "lineage": "widget-study-r4",
            "title": "2. Widget Calibration", "text": section_text,
        }
        draft_latex = "Calibrating the widget takes patience, attention, and a steady hand."
        report = paper_leak.check_source_section_verbatim(draft_latex, contract_prose, [section])
        self.assertEqual(report["sections"][0]["title"], "2. Widget Calibration")

    def test_a_run_equal_to_the_threshold_passes(self) -> None:
        """The strict-inequality half of `Requirement: The Threshold
        Self-Calibrates...`: a run of EXACTLY sixteen tokens (the backstop,
        against a near-zero floor) must pass, never refuse."""
        run = _n_token_run(16)
        section_text = f"Framing prose. {run} Trailing prose."
        contract_prose = "The contract prose shares nothing at all with this section."
        section = {
            "fact": "formulation", "lineage": "widget-study-r4",
            "title": "2. Widget Calibration", "text": section_text,
        }
        draft_latex = f"Draft framing. {run} Draft trailing."
        report = paper_leak.check_source_section_verbatim(draft_latex, contract_prose, [section])
        entry = report["sections"][0]
        self.assertEqual(entry["threshold"], 16)
        self.assertEqual(entry["longest_run"], 16)

    def test_a_contract_licensed_forty_token_floor_makes_the_guard_inert(self) -> None:
        """Scenario "A contract-licensed long run is not refused": the
        block's own contract prose already carries the same forty-token run
        from its bound section, so the floor is forty, above the backstop,
        and reproducing that same run passes -- equal to, never strictly
        above, its own threshold. The inertness is visible through the
        reported floor (`Requirement: The Floor And Threshold Are Reported,
        Never Inferred Silently`)."""
        run = _n_token_run(40)
        section_text = f"Section framing. {run} Section trailing."
        contract_prose = f"Contract framing sentence. {run} Contract trailing sentence."
        section = {
            "fact": "formulation", "lineage": "widget-study-r4",
            "title": "2. Widget Calibration", "text": section_text,
        }
        draft_latex = f"Draft framing sentence. {run} Draft trailing sentence."
        report = paper_leak.check_source_section_verbatim(draft_latex, contract_prose, [section])
        entry = report["sections"][0]
        self.assertEqual(entry["floor"], 40)
        self.assertEqual(entry["threshold"], 40)
        self.assertEqual(entry["longest_run"], 40)

    def test_a_six_token_idiom_does_not_refuse_under_the_real_backstop(self) -> None:
        """The scenario mutation 2.15 falsifies: a block whose contract
        prose shares near nothing with its section (floor near zero)
        drafts a six-token idiom that also appears in the section -- under
        the REAL `max(floor, SOURCE_RUN_BACKSTOP)` threshold this must NOT
        refuse; the backstop alone is what protects it."""
        idiom = _n_token_run(6)
        section_text = f"Framing text. {idiom} Trailing text of the section."
        contract_prose = "Contract prose sharing almost nothing with this section at all."
        section = {
            "fact": "formulation", "lineage": "widget-study-r4",
            "title": "2. Widget Calibration", "text": section_text,
        }
        draft_latex = f"Draft prose. {idiom} Draft closing prose."
        report = paper_leak.check_source_section_verbatim(draft_latex, contract_prose, [section])
        self.assertEqual(report["sections"][0]["threshold"], 16)


def _every_strip_math_callable() -> list[tuple[str, object]]:
    """Every callable literally named `strip_math` or `_strip_math` in any
    module under `scripts/`, discovered by introspection -- never a
    hand-maintained list of exactly the two implementations known today
    (`style-leak-detection` spec, Requirement: The Eight-Token Tripwire,
    Scenario "Mutation -- a third normalizer is caught by the derived
    sweep, never a hand-edited list"). Reusing `SKILL_SCRIPTS`, already
    on `sys.path` at module import time, so a mutation test that pre-seeds
    `sys.modules` for exactly one module still resolves this sweep to the
    mutant for that module and to the real file for every sibling."""
    found: list[tuple[str, object]] = []
    for path in sorted(SKILL_SCRIPTS.glob("*.py")):
        module = importlib.import_module(path.stem)
        for candidate_name in ("strip_math", "_strip_math"):
            candidate = getattr(module, candidate_name, None)
            if callable(candidate):
                found.append((f"{path.stem}.{candidate_name}", candidate))
    return found


class MathFenceExclusionSweepTests(unittest.TestCase):
    """`style-leak-detection` spec, Requirement: The Eight-Token Tripwire --
    the DERIVED cross-module sweep proving every `strip_math`/`_strip_math`
    callable under `scripts/` excludes a `$$...$$` fence identically
    (design.md, Decision A: "The class, not the instance")."""

    _EQUATION_BODY = "alpha x plus beta x squared plus gamma x cubed minus delta"

    def test_every_strip_math_callable_excludes_a_dollar_dollar_fence(self) -> None:
        callables = _every_strip_math_callable()
        self.assertGreaterEqual(
            len(callables), 2,
            "expected at least paper_style.strip_math and paper_bindings._strip_math",
        )
        text = f"Prefix prose. $$ {self._EQUATION_BODY} $$ Suffix prose."
        for label, fn in callables:
            stripped = fn(text)
            stripped_words = set(re.findall(r"[a-zA-Z0-9']+", stripped))
            for token in self._EQUATION_BODY.split():
                self.assertNotIn(
                    token, stripped_words,
                    f"{label} left the whole word {token!r} from inside a $$ fence in its stripped output",
                )

    def test_mutation_dropping_the_alternative_in_paper_bindings_fails_the_derived_sweep(self) -> None:
        """`style-leak-detection` spec, Scenario "Mutation -- a third
        normalizer is caught by the derived sweep, never a hand-edited
        list": with the `$$...$$` alternative removed from ONLY
        `paper_bindings._strip_math`, the sweep test above must go red --
        proving membership in the sweep is computed from every callable
        actually found, not merely from a pair of names somebody remembered
        to list."""
        proc = _run_against_mutant(
            r'r"\$\$.*?\$\$|',
            'r"',
            "tests.test_paper_writing.MathFenceExclusionSweepTests"
            ".test_every_strip_math_callable_excludes_a_dollar_dollar_fence",
            source_path=SKILL_SCRIPTS / "paper_bindings.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class ThreeDraftProofSetTests(unittest.TestCase):
    """`style-leak-detection` spec, `Requirement: Three-Draft Proof Set`,
    scenario "A, B, and S share every input but the style channel" --
    flagged CRITICAL UNTESTED by this change's own corrective verify. The
    scenario describes the orchestrating agent's live shuttle procedure
    (three separate redactor calls), which this suite may never spawn
    (Decision D2). What IS achievable, and was missing, is the
    CLI-observable half: that `write_block`, given three contracts sharing
    identical contract prose, evidence set and mode and differing ONLY in
    `style_set`, treats every non-style field identically -- proven against
    the exact mechanism the pipeline itself uses to recognize "the same
    attempt" (`_attempt_key`), and end to end through three real
    `write_block` calls."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base_dir = Path(self._tmp.name)

    def _fresh_paper_dir(self, name: str) -> Path:
        paper_dir = self.base_dir / name
        _write_fixture(paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))
        return paper_dir

    def test_attempt_key_is_identical_across_a_b_and_s(self) -> None:
        """The A/B/S split changes only `style_set`. `_attempt_key` --
        which the one-bounded-re-draft ledger uses to decide whether two
        submissions are "the same attempt" -- reads contract, evidence and
        mode alone, so it must hash identically for all three regardless of
        style."""
        contract_a = _write_contract(citations_regime="none", evidence_set=(), style_set=())
        contract_b = _write_contract(citations_regime="none", evidence_set=(), style_set=())
        contract_s = _write_contract(
            citations_regime="none", evidence_set=(),
            style_set=({"reference": "paperA", "span": "one two three four five six"},),
        )
        key_a = paper_write._attempt_key(contract_a)
        key_b = paper_write._attempt_key(contract_b)
        key_s = paper_write._attempt_key(contract_s)
        self.assertEqual(key_a, key_b)
        self.assertEqual(key_a, key_s)

    def test_a_and_b_and_s_produce_identical_outcomes_but_for_the_style_channel(self) -> None:
        """Three real `write_block` calls, one shared contract shape,
        differing only in `style_set`, each against its own fresh fixture
        (so all three independently reach `substitute`). A and B use the
        SAME draft -- non-style-field identity is exactly what is under
        test, not incidental wording variance a live redactor would
        introduce. S uses a differently-worded but content-equivalent draft
        that shares no eight-token run with its one recorded sample, so the
        tripwire stays silent and S reaches `written` too."""
        contract_a = _write_contract(citations_regime="none", evidence_set=(), style_set=())
        contract_b = _write_contract(citations_regime="none", evidence_set=(), style_set=())
        contract_s = _write_contract(
            citations_regime="none", evidence_set=(),
            style_set=({"reference": "paperA", "span": "one two three four five six"},),
        )
        self.assertEqual(contract_a.contract_prose, contract_b.contract_prose)
        self.assertEqual(contract_a.contract_prose, contract_s.contract_prose)
        self.assertEqual(contract_a.mode, contract_s.mode)
        self.assertEqual(contract_a.evidence_set, contract_s.evidence_set)

        result_a = paper_write.write_block(
            self._fresh_paper_dir("a"), contract_a, _CLEAN_DRAFT, _CLEAN_AUDIT,
        )
        result_b = paper_write.write_block(
            self._fresh_paper_dir("b"), contract_b, _CLEAN_DRAFT, _CLEAN_AUDIT,
        )
        styled_draft = {
            "latex": "This paragraph closes the whole demonstration.",
            "bindings": [
                {"sentence": "This paragraph closes the whole demonstration.", "binding": "structural"},
            ],
        }
        result_s = paper_write.write_block(
            self._fresh_paper_dir("s"), contract_s, styled_draft, _CLEAN_AUDIT,
        )

        for result in (result_a, result_b, result_s):
            self.assertEqual(result["status"], "written")
            self.assertEqual(result["verdicts"], result_a["verdicts"])

        self.assertEqual(result_a["styleChannel"], {"status": "unmeasured"})
        self.assertEqual(result_b["styleChannel"], {"status": "unmeasured"})
        self.assertEqual(result_s["styleChannel"]["status"], "measured")

    def test_mutation_8_style_leaking_into_the_attempt_key_fails_the_identity_guard(self) -> None:
        """Falsifies the guard above: if `_attempt_key` were changed to
        fold `style_set` into its payload, A and S would no longer hash
        identically, and `test_attempt_key_is_identical_across_a_b_and_s`
        must go red -- proving that test can actually fail, not just that
        it currently passes."""
        proc = _run_against_mutant(
            '            "mode": contract.mode,\n        },',
            '            "mode": contract.mode,\n'
            '            "style": [dict(entry) for entry in contract.style_set],\n'
            '        },',
            "tests.test_paper_writing.ThreeDraftProofSetTests"
            ".test_attempt_key_is_identical_across_a_b_and_s",
            source_path=SKILL_SCRIPTS / "paper_write.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class WriterMutationProofTests(unittest.TestCase):
    """`tasks.md` 1.11/2.3/2.5 -- the seven mutations named in the
    proposal, executed for real against the five new modules, mirroring
    `MutationProofTests` above."""

    def _assert_guard_failed_under_mutation(self, proc: subprocess.CompletedProcess) -> None:
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_1_dropped_reconciliation_fails_the_unbound_sentence_guard(self) -> None:
        proc = _run_against_mutant(
            "if sentence not in by_sentence:",
            "if False:",
            "tests.test_paper_writing.BindingMapTests.test_an_unbound_sentence_refuses",
            source_path=SKILL_SCRIPTS / "paper_bindings.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_2_never_firing_fails_the_one_firing_bullet_blocks_guard(self) -> None:
        proc = _run_against_mutant(
            'fired = [entry for entry in reconciled if entry["verdict"] == "fires"]',
            "fired = []",
            "tests.test_paper_writing.ContractAuditTests"
            ".test_one_firing_bullet_blocks_regardless_of_undecidables",
            source_path=SKILL_SCRIPTS / "paper_audit.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_3_substituting_on_exhausted_audit_fails_the_exhaustion_guard(self) -> None:
        proc = _run_against_mutant(
            "if attempt >= 2:",
            "if attempt >= 99:",
            "tests.test_paper_writing.WritingPipelineTests"
            ".test_two_failing_audits_leave_main_tex_unchanged_and_refuse_audit_exhausted",
            source_path=SKILL_SCRIPTS / "paper_write.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_4_a_hardcoded_bullet_fails_the_verbatim_extraction_guard(self) -> None:
        proc = _run_against_mutant(
            "    return bullets",
            '    bullets.append("HARDCODED BULLET THAT WAS NEVER IN THE CONTRACT")\n    return bullets',
            "tests.test_paper_writing.ContractAuditTests.test_bullet_text_reaches_the_audit_unchanged",
            source_path=SKILL_SCRIPTS / "paper_audit.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_5_absent_heading_as_zero_disqualifiers_fails_the_guard(self) -> None:
        proc = _run_against_mutant(
            "        raise Refused(\n"
            '            "DISQUALIFIERS_ABSENT", f"{source_name}: no \'## Disqualifiers\' heading"\n'
            "        )",
            "        return []",
            "tests.test_paper_writing.ContractAuditTests.test_a_contract_missing_the_heading_refuses",
            source_path=SKILL_SCRIPTS / "paper_audit.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_6_optional_ab_control_fails_the_typeerror_guard(self) -> None:
        proc = _run_against_mutant(
            "def register_distance_holds(styled: str, unstyled_a: str, unstyled_b: str) -> dict:",
            'def register_distance_holds(styled: str, unstyled_a: str, unstyled_b: str = "") -> dict:',
            "tests.test_paper_writing.StyleLeakDetectionTests.test_dropping_the_ab_control_fails_construction",
            source_path=SKILL_SCRIPTS / "paper_leak.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_7_reading_the_reference_file_fails_the_recorded_set_guard(self) -> None:
        proc = _run_against_mutant(
            'return max(_longest_run(tokens, paper_style.normalize_tokens(sample["span"])) '
            "for sample in samples)",
            "return max(_longest_run(tokens, paper_style.normalize_tokens("
            'Path(sample["source_md"]).read_text(encoding="utf-8"))) for sample in samples)',
            "tests.test_paper_writing.StyleLeakDetectionTests"
            ".test_overlap_ignores_text_in_the_reference_file_outside_r",
            source_path=SKILL_SCRIPTS / "paper_leak.py",
        )
        self._assert_guard_failed_under_mutation(proc)


REFUSAL_CONSTRUCTORS = ("Refused",)
REFUSAL_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")


def _refusal_code_argument(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _refusal_sites(node, owner: str) -> list[tuple[str, str | None]]:
    """Every refusal constructed anywhere under `node`, as `(owner, code)` —
    the same shape `test_proposal_implementation.py` uses for its own
    roster, scoped here to `paper_cli.py` and whatever it imports
    (`paper_cli_imported_modules()`)."""
    sites: list[tuple[str, str | None]] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sites += _refusal_sites(child, child.name)
            continue
        if (isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                and child.func.id in REFUSAL_CONSTRUCTORS):
            sites.append(
                (owner, _refusal_code_argument(child.args[0]) if child.args else None))
        sites += _refusal_sites(child, owner)
    return sites


def _module_code_constants(tree) -> set[str]:
    constants = set()
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)) or statement.value is None:
            continue
        for node in ast.walk(statement.value):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and REFUSAL_CODE_RE.match(node.value)):
                constants.add(node.value)
    return constants


def _codes_from_sites(sites, constants: set[str]) -> set[str]:
    codes = {code for _, code in sites if code is not None}
    if any(code is None for _, code in sites):
        codes |= constants
    return codes


def paper_cli_imported_modules() -> list[Path]:
    """Every module `paper_cli.py` imports at module level via a plain
    `import X` (never `from X import Y`, which is how it reaches
    `impl_refusals.Refused` and contributes no roster entry of its own by
    design), resolved to a `.py` file inside this skill's own scripts
    directory.

    Derived from `paper_cli.py`'s own imports rather than a hand-listed
    tuple or a directory scan. A hand-listed tuple goes stale silently the
    moment a new script is added and wired in -- measured: this skill's own
    `paper_contract.py` and `paper_graph.py` were added and every refusal in
    them went unrostered with no test going red, because nothing re-derived
    the tuple. A directory scan is the OTHER wrong shape: it would claim a
    sibling change's own modules the moment they land beside these, which is
    exactly the whole-directory-scan pattern `skills/_core/` is
    forbidden from reproducing (measured elsewhere in this repository, where
    a different skill's roster derivation does scan a whole directory and is
    the reason nothing of this skill's may live under `_core/`). Importing
    is the correct reachability boundary either way: a module the front door
    never imports raises nothing a user can reach through it.
    """
    tree = ast.parse(CLI.read_text(encoding="utf-8"))
    modules = []
    for node in tree.body:
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            candidate = SKILL_SCRIPTS / f"{alias.name}.py"
            if candidate.is_file():
                modules.append(candidate)
    return modules


def unreadable_paper_refusal_sites() -> set[tuple[str, str]]:
    sites = set()
    for source in (CLI, *paper_cli_imported_modules()):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        sites |= {(source.name, owner)
                  for owner, code in _refusal_sites(tree, "<module>")
                  if code is None}
    return sites


def reachable_paper_refusal_codes() -> set[str]:
    """Every refusal code a `paper_cli.py` command can raise, derived from
    source — never hand-listed. The same shape as
    `test_proposal_implementation.reachable_refusal_codes`: a closure from
    `paper_cli.py`'s `cmd_*` roots (following calls into helpers defined in
    `paper_cli.py` itself), UNIONED with a whole-module scan of every module
    `paper_cli.py` itself imports (`paper_cli_imported_modules()` above) —
    this skill's own helper modules, playing the role
    `_core/implementation/*.py` plays for the sibling skill, and widening by
    itself the moment a verb is actually wired rather than needing a second,
    hand-maintained tuple kept in sync with the first. `impl_refusals.py`
    contributes nothing: it raises no `Refused` of its own (design.md's `Own
    modules; import only Refused` decision) — the whole point of that choice
    being that this skill's roster and the sibling skill's roster never
    share an entry neither owns.
    """
    tree = ast.parse(CLI.read_text(encoding="utf-8"))
    definitions = {node.name: node for node in tree.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    # `main` is a root beside every `cmd_*` verb, never called by one and
    # never calling one back: it is the CLI's own front door
    # (`_require_supported_python`, item 4, `limpieza-de-pendientes-
    # chicos`) and raises a refusal of its own before any command is even
    # dispatched. Omitting it would leave that refusal permanently
    # "reachable per a human reading `main()`" but invisible to this walk.
    roots = ["main"] + [f"cmd_{command}" for command in paper_cli.COMMANDS]
    for root in roots:
        if root not in definitions:
            raise AssertionError(f"paper_cli.py defines no {root}")
    constants = _module_code_constants(tree)
    codes: set[str] = set()
    seen: set[str] = set()
    frontier = list(roots)
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        definition = definitions[name]
        codes |= _codes_from_sites(_refusal_sites(definition, name), constants)
        frontier += [node.id for node in ast.walk(definition)
                     if isinstance(node, ast.Name)
                     and isinstance(node.ctx, ast.Load)
                     and node.id in definitions]
    for source in paper_cli_imported_modules():
        module = ast.parse(source.read_text(encoding="utf-8"))
        codes |= _codes_from_sites(_refusal_sites(module, "<module>"),
                                    _module_code_constants(module))
    return codes


class RefusalRosterTests(unittest.TestCase):
    """Every refusal reachable from a `paper_cli.py` command is classified,
    and nothing is classified that no command can reach — the lock
    `GatingRefusalRosterTests` holds `implementation_cli.py` to, derived
    rather than hand-listed so a new `Refused` anywhere in `paper_cli.py` or
    any module it imports goes red here until somebody classifies it."""

    def test_every_reachable_refusal_is_classified(self) -> None:
        missing = sorted(reachable_paper_refusal_codes() - set(paper_cli.REFUSAL_CLASSIFICATION))
        self.assertEqual(
            missing, [],
            "these codes are reachable and the roster classifies none of them; a "
            "refusal nobody decided about is the defect this roster exists to make "
            "impossible")

    def test_the_roster_classifies_nothing_unreachable(self) -> None:
        extra = sorted(set(paper_cli.REFUSAL_CLASSIFICATION) - reachable_paper_refusal_codes())
        self.assertEqual(
            extra, [],
            "the roster classifies these and no command can reach them")

    def test_every_classification_is_invocation_defect_or_work_state(self) -> None:
        allowed = {paper_cli.INVOCATION_DEFECT, paper_cli.WORK_STATE}
        bad = {code: cls for code, cls in paper_cli.REFUSAL_CLASSIFICATION.items()
               if cls not in allowed}
        self.assertEqual(bad, {})

    def test_the_derivation_has_no_unreadable_sites(self) -> None:
        """No refusal in `paper_cli.py` or any module it imports raises a
        code this walk cannot read as a string literal — asserted rather
        than assumed, so a future dynamic code site is looked at by a human
        instead of silently widening to a module's constants."""
        self.assertEqual(unreadable_paper_refusal_sites(), set())

    def test_the_derivation_finds_the_measured_count(self) -> None:
        """Sanity check on the derivation itself: a change that adds,
        removes or renames a refusal anywhere reachable should move this
        number, never a typo in the walk above. Moved from 21 to 30 when
        `the-contract-is-data-not-code` appended `contract`/`readiness`/
        `order` and `paper_cli.py` started importing `paper_vocabulary.py`,
        `paper_contract.py` and `paper_graph.py` — 3 (`UNKNOWN_FACT`,
        `UNKNOWN_DECLARATION`, `UNKNOWN_CITATIONS_REGIME`) + 4
        (`MALFORMED_HEADER`, `HEADER_PRESENT`, `BODY_MUTATED`,
        `SECTIONS_OUTSIDE_REPOSITORY`) + 2 (`ID_COLLISION`, `ORDER_CYCLE`).
        Moved from 30 to 36 in Slice A of `the-paper-carries-its-own-decisions`,
        which imports `paper_region.py` (`REGION_MALFORMED`,
        `REGION_DUPLICATED`, `REGION_UNPAIRED`) and `paper_guidance.py`
        (`GUIDANCE_OUTSIDE_REPOSITORY`, `UNKNOWN_GUIDANCE_CLASS`,
        `MALFORMED_GUIDANCE_MARKER`) at module level ahead of either
        module's own verb wiring (tasks.md, 1.10) — six new codes, reachable
        and classified the moment the import lands. Moved from 36 to 41 in
        Slice B, which wires `declare`: `DECLARATION_FIXED` and
        `DECLARATIONS_HAND_EDITED` from `paper_declarations.py`, plus
        `DECLARE_MODE_REQUIRED`, `DECLARE_MODE_CONFLICT`,
        `DECLARE_VALUE_REQUIRED` from `cmd_declare`'s own mode selection in
        this file — `UNKNOWN_DECLARATION`/`UNKNOWN_FACT` are reused
        verbatim from Phase 2 and add nothing new to the set. Moved from 41
        to 43 in Slice C1, which adds `CONTRACT_UNREADABLE` (raised
        directly inside `paper_block.substitute`, already-imported) and
        `PROVENANCE_HAND_EDITED` (from the newly-imported
        `paper_provenance.py`). Moved from 43 to 45 in Slice C2, which adds
        `NOT_AN_OBSERVABLE_FACT` and `EVIDENCE_CONFLATED` from
        `paper_declarations.validate_observation_report` -- reachable
        through the whole-module scan even though no `cmd_*` root calls it
        directly, the same shape that already applies to every other
        module-level refusal here. `plan`'s own wiring adds no new code:
        every refusal `compute_plan`/`cmd_plan` can raise was already
        classified by an earlier slice. `paper_objective.py` raises none of
        its own, matching `paper_readiness.py`'s own precedent. Moved from
        45 to 54 in WU1 of `no-claim-without-a-source-that-holds-it`, which
        adds `UNKNOWN_VERDICT` (`paper_vocabulary.py`, already-imported
        module) and wires `resolve` -- `paper_cli.py` starts importing
        `paper_evidence.py` (`SPAN_NOT_IN_SOURCE`, `VERDICT_SPAN_REQUIRED`)
        and `paper_resolve.py` (`PAPERSMITH_CONFIG_UNREADABLE`,
        `UNKNOWN_ROLE`, `DISCOVERY_UNAVAILABLE`, `RESOLVER_ROLE_EMPTY`,
        `RESOLVER_UNREACHABLE`, `IDENTIFIER_UNRESOLVED`) -- 1 + 2 + 6 = 9
        new codes. Moved from 54 to 57 in WU2, which wires `bib build`:
        `paper_bib.py` adds `ENTRY_UNSOURCED`, `CITE_WITHOUT_ENTRY`,
        `ENTRY_WITHOUT_CITE`. Moved from 57 to 65 in WU3, which wires
        `validate`: `paper_validate.py` adds `EVIDENCE_EXHAUSTED`,
        `CITATION_MULTI_CLAIM_SENTENCE`, `CITATION_NOUN_PHRASE`,
        `CITATION_NOT_AT_SENTENCE_END`, `CITATION_DETACHED_FROM_OBJECT`,
        `CITATION_UNDER_NONE_REGIME`, `CONTRACT_HEADER_ABSENT`, plus
        `cmd_validate`'s own `VALIDATE_VERDICT_REQUIRED` in this file -- 7 + 1
        = 8 new codes. Moved from 65 to 79 in `the-writer-may-assert-only-
        what-it-was-given`: `paper_contract.py`'s `mode` widening adds
        `UNKNOWN_MODE` (1); WU1 wires `write` and starts importing
        `paper_bindings.py` (`UNBOUND_SENTENCE`, `BINDING_ORPHANED`,
        `EVIDENCE_ID_UNKNOWN`, `FACT_NOT_LICENSED`,
        `STRUCTURAL_CARRIES_CLAIM`, `MODE_VIOLATION` -- 6),
        `paper_audit.py` (`DISQUALIFIERS_ABSENT`, `VERDICT_MISSING`,
        `VERDICT_BULLET_UNKNOWN` -- 3) and `paper_write.py`
        (`MODE_ABSENT`, `EVIDENCE_SET_REQUIRED`, `AUDIT_EXHAUSTED` -- 3);
        WU2 starts importing `paper_leak.py` (`STYLE_OVERLAP` -- 1) and
        `paper_style.py` (raises none of its own, reusing
        `SPAN_NOT_IN_SOURCE`) -- 1 + 6 + 3 + 3 + 1 = 14 new codes. Moved
        from 79 to 93 in `a-diagram-that-compiles-or-says-why`: `paper_cli.py`
        starts importing `paper_latex.py` (raises none of its own -- every
        one of its refusals is reused/named by `paper_figure.py`'s own
        call sites), `paper_figure.py` (`DIAGRAM_SOURCE_ABSENT`,
        `LATEX_TOOLCHAIN_ABSENT`, `LATEX_PACKAGE_ABSENT`,
        `REPAIR_BUDGET_SPENT`, `DIAGRAM_PLOTS_DATA`, `MANIFEST_SOURCE_MISMATCH`,
        `LATEX_LOG_ABSENT`, `LATEX_OUTCOME_UNEXPLAINED` -- 8) and
        `paper_obligation.py` (`COMPONENT_MISMATCH`, `EXCLUDED_COMPONENT`,
        `SHARED_COMPONENT`, `CAPTION_INCOMPLETE`, `MANDATORY_DIAGRAM_ABSENT`
        -- 5), and `paper_contract.py`'s own `_parse_figure` adds
        `MALFORMED_FIGURE_OBLIGATION` (1) to an already-imported module --
        8 + 5 + 1 = 14 new codes. Moved from 93 to 94 in
        `the-couplings-hold-or-they-do-not`: `paper_cli.py` starts importing
        `paper_coupling_evidence.py` (`DECLARATION_RECORD_ABSENT` -- 1) and
        `paper_verify.py` (raises no `Refused` of its own), both ahead of
        `verify`'s own wiring -- the same shape `paper_region.py`/
        `paper_obligation.py` already established, forced this time by
        `ModuleCompletenessTests` rather than chosen: that test holds every
        on-disk script to being imported by `paper_cli.py` the moment it
        exists, so the import could not wait for Work Unit 3 the way
        tasks.md's own 3.7 originally phrased it. Moved from 94 to 96 in
        `a-diagram-that-compiles-or-says-why`'s own corrective amendment
        (verify FAIL, CRITICAL): `_resolve_expected_components`, a new
        helper inside `paper_cli.py` itself, raises `COMPONENTS_FACT_
        UNRESOLVED` and `COMPONENTS_FACT_NOT_A_LIST` -- reachable the
        moment `_check_obligations` calls it, no new module import needed
        since both live in the already-scanned `paper_cli.py`. Moved from
        96 to 95 in the zero-production-caller corrective: `paper_contract.
        install_header` (`HEADER_PRESENT`, `BODY_MUTATED`) is deleted --
        its one-shot migration over the ten shipped contracts already ran
        and nothing promises a "create a new section contract" workflow
        anywhere in SKILL.md, a spec, or a registered agent -- and `observe`
        is wired as `validate_observation_report`'s real caller, adding
        `OBSERVATION_REPORT_UNREADABLE` (this file's own shuttle-file read,
        the same shape `CONTRACT_UNREADABLE` already establishes). Net
        -2 + 1 = -1. `classify_guidance_child` (`paper_evidence.py`) is also
        deleted in the same corrective but raises no `Refused` of its own,
        so it moves this count by zero. Moved from 95 to 96 in the K4
        corrective (`resolve_sections_dir` never checked the resolved
        `--sections` path actually existed, so `contract`/`readiness`/
        `order`/`plan` silently read a typo'd path as a real empty corpus):
        `paper_contract.resolve_sections_dir` gains one new raise site for
        `SECTION_CONTRACTS_UNREADABLE` -- reusing, not inventing, the code
        `paper_verify.UNMEASURED_REASONS` and `paper_coupling_evidence.
        _blocks_by_fact` already carry for "the corpus itself could not be
        read", so the set gains a member without gaining a second name for
        the same condition. Moved from 96 to 97 in `the-phases-are-derived-
        not-remembered`, unit 1: `paper_graph.py` gains
        `_verify_input_partition`, called from `assemble_corpus` (an
        already-imported module), refusing `INPUT_PARTITION_ABSENT` when a
        contract's prose body is missing `### External inputs` or
        `### Internal chain` -- reachable through the whole-module scan the
        moment the new raise site lands, no new import needed. Moved from 97
        to 101 in the same change's unit 4 (`internal-chain-edges`, tasks
        4.1-4.13 / 4.8b-4.8i): `paper_graph.py` gains `_verify_internal_
        chain` (`CHAIN_ROW_UNRESOLVED`, `CHAIN_ROW_UNBACKED` -- every
        `### Internal chain` row transcribes to a real, backed `after`
        edge) and `_verify_block_subunits` (`BLOCK_SUBUNIT_UNDECLARED`,
        `UNIT_HEADING_AMBIGUOUS` -- the PROSE -> HEADER direction no
        existing check covered, the guard the block-4 split proved
        missing), both called from `assemble_corpus` -- an already-imported
        module, so all four land reachable together the moment their raise
        sites exist, measured as one +4 move rather than the tasks
        artifact's own three smaller increments forecast in isolation.
        Moved from 101 to 103 in unit 6 (`readiness` gains a basis; `phases`
        owns "what can I write now", tasks.md 6.1-6.16): `cmd_readiness`
        gains `READINESS_BASIS_REQUIRED` (neither `--paper` nor any
        `--fact`/`--declaration` flag given) and the new `cmd_phases` root
        gains `PHASE_NOT_READY` (a wave before the requested `--phase` is
        still incomplete) -- both raised directly inside `paper_cli.py`,
        reachable the instant their `cmd_*` roots exist, no new import
        needed. This is the measured +2, not the tasks artifact's own
        forecast (99 to 101), which predates unit 4's own measured +4 (97
        to 101, not the three separate +1/+1/+2 moves 4.8f/4.10 forecast in
        isolation) and was never corrected forward. Moved from 103 to 106 in
        unit 7 (`skeleton` + disk inference + `ingested_papers`, tasks.md
        7.1-7.16): the new `cmd_skeleton` root raises `SKELETON_ANSWER_
        REQUIRED` (either flag missing) and `SKELETON_ALREADY_DECIDED` (the
        given flags contradict what disk already records); `paper_
        declarations.infer_dataset_placement` (already-imported module)
        raises `DATASET_PLACEMENT_CONFLICT` -- reachable the instant its
        raise site exists, no new import needed. This is the measured +3,
        not the tasks artifact's own forecast (101 to 104), which predates
        this same drift already flagged for units 4/6 above and was never
        corrected forward either. Moved from 106 to 107 in unit 8
        (`packet` + `segment_markdown`, tasks.md 8.1-8.15): `paper_
        guidance.read_markdown_outline` (already-imported module) gains
        `GUIDANCE_MARKDOWN_UNREADABLE`, reachable the instant that raise
        site exists -- no new import needed. `cmd_packet`/`assemble_
        packet` and `cmd_write`'s own new `assemble_packet` call raise no
        code of their own; this is the measured +1, matching the tasks
        artifact's own forecast (104 to 105) in shape though not in the
        absolute numbers either endpoint names, since both predate unit
        7's own measured +3 (103 to 106, not the tasks artifact's stale
        101-to-104) that was never corrected forward. Moved from 107 to 108 in
        `a-declined-fact-has-somewhere-to-live`: `paper_declarations.py` (an
        already-imported module) gains `decline_fact`, which raises
        `DECLINE_REASON_REQUIRED` when `--reason` is empty or all whitespace
        -- reachable the instant that raise site exists, no new import
        needed; `DECLARATION_FIXED` is reused verbatim for both a decline-
        over-resolved and a resolve-over-declined conflict, adding no second
        code for either condition. Moved from 108 to 111 in that same
        change's `condition-that-expires` extension (a decline must carry a
        disk condition the skill re-evaluates on every read, so it can go
        stale rather than stand forever on a human's memory): `paper_
        vocabulary.py` (already-imported) gains `validate_condition_type`,
        raising `UNKNOWN_CONDITION_TYPE` for a `condition["type"]` outside
        the one-member closed vocabulary `("directory-empty-except",)`;
        `paper_declarations.decline_fact`'s own new `_validate_condition_
        shape` helper raises `CONDITION_REQUIRED` (`--condition` omitted)
        and `CONDITION_MALFORMED` (not a JSON object, a missing/wrong-typed
        required field, or a `path` resolving outside `paper_dir.parent`) --
        three new codes, reachable the instant their raise sites exist, no
        new import needed since `paper_vocabulary.py` and `paper_
        declarations.py` were already scanned. Measured directly against
        `reachable_paper_refusal_codes()` rather than forecast, per this
        file's own repeated warning that the forecast arithmetic has
        drifted stale before. Moved from 118 to 119 in
        `no-citation-before-its-paper-is-ingested`, item 2: `paper_bib.py`
        (already-imported) gains `_require_ingested`, raising
        `ENTRY_NOT_INGESTED` when a resolved citation was never ingested --
        one new code, reachable the instant that raise site exists, no new
        import needed. Moved from 119 to 122 in that same change's item 3:
        this file's own new `_guard_section_citations_ready`, called from
        `cmd_write`, raises `CITATION_FOLDER_ABSENT`, `CITATION_NOT_
        INGESTED` and `CITATION_FOLDER_UNCLASSIFIED` -- three new codes,
        reachable the instant `cmd_write` calls it, no new import needed.
        Measured directly against `reachable_paper_refusal_codes()`, never
        forecast. Moved from 122 to 127 in `the-pdf-arrives-or-the-
        operator-is-told`, item 1: `paper_cli.py` starts importing
        `paper_full_text.py`, which fills the `full-text` role
        `papersmith.yaml` and `paper_resolve.ROLES` both already declared
        -- `METADATA_NOT_CACHED`, `FULL_TEXT_URL_ABSENT`, `RESOLVER_ROLE_
        EMPTY` (reused, not counted twice), `CITE_KEY_MALFORMED`, and
        `FULL_TEXT_NOT_A_PDF`/`FULL_TEXT_FILE_PRESENT` -- five new codes,
        reachable the instant the new `cmd_full_text` root and its import
        land; `RESOLVER_UNREACHABLE`/`IDENTIFIER_UNRESOLVED` (via the new
        `paper_resolve.fetch_bytes`) and `GUIDANCE_OUTSIDE_REPOSITORY` (via
        `resolve_destination`'s own containment guard) are reused verbatim
        from WU1/Slice A, adding nothing new to the set. Item 2's own
        distinct-source-count minimum (`paper_validate.claim_coverage`)
        adds no new code at all: it changes what `EVIDENCE_EXHAUSTED`'s
        detail says and what `finalize_block` returns, never what it can
        raise. Measured directly against `reachable_paper_refusal_codes()`,
        never forecast. Moved from 127 to 130 in
        `a-fact-is-declared-or-it-is-produced`, unit 1: `paper_graph.py`
        gains three new raise sites, reachable the instant `produces_facts`
        entries exist anywhere in the parsed corpus (today: nowhere, since
        this unit touches no `sections/*.md` file) --
        `FACT_SELF_REQUIRED` (a block requiring what it produces),
        `FACT_ROUTE_AMBIGUOUS` (a `produces_facts` entry naming a
        declarable fact), and `FACT_PRODUCER_DUPLICATE` (an uncorroborated
        duplicate producer; a corroborated pair, e.g. `gap` via Coupling 3,
        is legal and raises nothing). `paper_contract.py`'s own grammar
        widening adds no new code: `MALFORMED_HEADER`/`UNKNOWN_FACT` are
        reused verbatim, the identical `requires_facts` schema check.
        Measured directly against `reachable_paper_refusal_codes()`, never
        forecast. Moved from 130 to 132 in the same change's unit 2:
        `paper_graph.py` gains two new raise sites, called from
        `assemble_corpus` (an already-imported module) --
        `FACT_PRODUCER_ABSENT` (a fact some block requires, excluding
        `skeleton`, resolves via neither `FACT_SOURCE_ROOT` nor any
        block's `produces_facts`) and `PRODUCER_CHAIN_ABSENT` (a producer
        does not reach one of its consumers in the `after`-edge graph).
        Both are reachable the instant their raise sites exist -- no new
        import needed, since the corpus edits landing in the same commit
        (`sections/*.md`) are exactly what makes each condition
        exercisable against the real, shipped corpus. Measured directly
        against `reachable_paper_refusal_codes()`, never forecast. Moved
        from 132 to 133 in the same change's unit 3: `paper_declarations.py`
        gains one new raise site, `_refuse_if_produced` (shared by
        `set_fact`/`decline_fact`) -- `PRODUCED_FACT_UNDECLARABLE` (`declare
        --fact`/`--decline` targets a fact a corpus block produces).
        Reachable the instant `paper_cli.cmd_declare` resolves a non-empty
        `produced_by` tuple for the given fact id, which the shipped corpus
        already does for four facts. Measured directly against
        `reachable_paper_refusal_codes()`, never forecast. Moved from 133
        to 138 in U1+U2 of `the-requirement-names-the-section-that-feeds-
        it`: `paper_graph.py` gains `_verify_source_section_bindings`,
        called from `assemble_corpus` (an already-imported module) --
        `SOURCE_REVISIONS_UNDECLARED` (a document-rooted root carries no
        marker), `SOURCE_LINEAGE_UNRESOLVED` (a lineage resolves to zero or
        more than one revision), `SECTION_NOT_IN_SOURCE` and `SECTION_
        TITLE_AMBIGUOUS` (a bound title matches zero or more than one
        heading) -- four new raise sites. `paper_declarations.py` (already
        imported) gains `read_revisions_marker`'s own `MALFORMED_SOURCE_
        MARKER` -- one more. `paper_contract.py`'s own `document` grammar
        widening adds no new code: `MALFORMED_HEADER` is reused verbatim,
        the identical shape `after`/`mode`/`figure` already use. All five
        are reachable the instant their raise sites exist, no new import
        needed, since every one of these three modules was already
        imported by `paper_cli.py`. `SECTION_BINDING_ABSENT` (the sixth
        code this change ships) is U3-only and moves this count again only
        once that unit's write-gate wiring lands. Measured directly
        against `reachable_paper_refusal_codes()`, never forecast.

        Moved from 138 to 139 in U2c: the owner's ruling that `dataset` is
        sourced from the ingested EVIDENCE document, never `proposals/`'s
        mathematics lineage, adds a third `SourceRootKind` (`INGESTED`) and
        one new raise site, `paper_declarations._ingested_root_status`'s
        own `EVIDENCE_ROOT_AMBIGUOUS` (more than one `guidance/` folder
        classed `'evidence'`) -- reachable the instant that raise site
        exists, no new import needed, since `paper_declarations.py` was
        already imported by `paper_cli.py`.

        Moved from 139 to 140 in U3: `SECTION_BINDING_ABSENT`'s own raise
        site now exists, unconditionally, in `paper_graph._verify_source_
        section_bindings` -- the sixth code this change ships, landing with
        the write-gate wiring rather than staying inert (design.md, Refusal
        Codes table).

        Moved from 140 to 144 in U3e (design.md Decision J): the new `bind`
        verb (`cmd_bind`, a new root in `paper_cli.COMMANDS`) records a
        binding through `paper_declarations.bind_section`/`reopen_binding`
        -- `BINDING_FACT_NOT_BINDABLE`, `BINDING_LINEAGE_REQUIRED`,
        `BINDING_SECTIONS_REQUIRED` (three new raise sites; `UNKNOWN_FACT`
        is reused verbatim, adding nothing new). `paper_graph.py` (already
        imported) gains one more: `_reconcile_source_bindings`'s own
        `SOURCE_BINDING_CONFLICT`, when a header-declared binding and a
        RECORDED one disagree for the same (block, fact). Four new codes
        total, reachable the instant their raise sites exist -- `cmd_bind`
        as a new root, the other three via modules `paper_cli.py` already
        imports.

        Moved from 144 to 149 in `the-whole-cut-is-argued-before-any-
        section-is-claimed`, U2: the new `separate` verb (`cmd_separate`, a
        new root in `paper_cli.COMMANDS`) lands five new raise sites, all in
        this file -- `SEPARATION_REPORT_UNREADABLE` (the proposal's own
        shape stage), `SEPARATION_SECTION_UNCLAIMABLE`, `SEPARATION_
        SECTION_OVERLAP`, `SEPARATION_SECTION_ORPHANED`, `SEPARATION_
        NOTATION_GAP` (the fixed-precedence structural dispatch).
        `UNKNOWN_FACT`, `BINDING_FACT_NOT_BINDABLE`, `SECTION_NOT_IN_
        SOURCE` and `SECTION_TITLE_AMBIGUOUS` are reused verbatim, adding
        nothing new -- `separate` resolves every title through the SAME
        `paper_graph.resolve_section_index` extraction `bind` already
        reaches. Measured directly against `reachable_paper_refusal_
        codes()`, never forecast.

        Moved from 149 to 151 in U3/U4 of the same change: the round
        record's own concession pipeline (`_check_separation_concession`,
        this file) adds two new raise sites -- `SEPARATION_ROUND_ABSENT`
        (`concedes_to_round` names no recorded round) and `SEPARATION_
        CONCESSION_REGRESSED` (the conceding cut's recomputed total is
        strictly worse than the round it abandons).

        Moved from 151 to 152 in U6 of the same change (the owner
        amendment, design.md Decisions I/J): `paper_declarations.py`
        (already imported) gains one new raise site, `_binding_separation_
        report`'s own `BINDING_UNARGUED` -- `bind`'s own precondition, for
        a measured, document-rooted fact, that a settled `separate` round
        licenses this exact `(block, fact)` claim with this exact title
        set (`settled_round_licensing`). Reachable the instant `cmd_bind`
        (already a root) records through `bind_section`; no new import
        needed. Measured directly against `reachable_paper_refusal_
        codes()`, never forecast.

        Moved from 152 to 153 in WU2 of `the-tripwire-reaches-the-section-
        that-feeds-it`: `paper_leak.py` (already imported, `# for the
        roster derivation`) gains one new raise site,
        `check_source_section_verbatim`'s own `SOURCE_SECTION_VERBATIM` --
        a transposition-mode block's draft pasting a run from its own bound
        source section beyond the self-calibrated `max(floor,
        SOURCE_RUN_BACKSTOP)` threshold. Reachable through the
        whole-module scan the moment the new raise site lands in an
        already-imported module; no new import needed. Measured directly
        against `reachable_paper_refusal_codes()`, never forecast.

        Moved from 153 to 154 in item 4 of `limpieza-de-pendientes-chicos`:
        `main` itself gains one raise site, `_require_supported_python`'s
        own `PYTHON_VERSION_UNSUPPORTED` -- the CLI's declared Python
        floor, refused by name ahead of every command rather than a bare
        traceback. Reachable only once `main` joins `cmd_*` as a root this
        walk follows (above); no new import needed. Measured directly
        against `reachable_paper_refusal_codes()`, never forecast.

        Moved from 154 to 157 in S2 of `the-skill-writes-the-declaration-
        it-demands`: `paper_declarations.py` (already imported) gains three
        new raise sites -- `declare_revisions`'s own `SOURCE_ROOT_
        UNDECLARABLE` (a `--root` naming a non-`PROSE`-kind root) and
        `SOURCE_DECLARATION_UNMATCHED` (a declared prefix/width matching
        zero `*.md`, or the root not being a directory at all), and
        `read_revisions_marker`'s own `SOURCE_DECLARATION_HAND_EDITED` (a
        sealed marker's recorded seal not matching the computed one). `mark`
        joins `cmd_*` as a new root (`cmd_mark` -> `cmd_mark_revisions`);
        `paper_marker.py` is imported too (`ModuleCompletenessTests`) but
        contributes nothing of its own -- it raises no `Refused`
        (design.md Decision B). Measured directly against `reachable_
        paper_refusal_codes()`, never forecast; S3/S4 move this again.

        Moved from 157 to 159 in S3 of `the-skill-writes-the-declaration-
        it-demands`: `paper_guidance.py` (already imported) gains two new
        raise sites -- `declare_class`'s own `GUIDANCE_FOLDER_ABSENT` (a
        `--folder` naming no directory directly under `guidance/`) and
        `_classify`'s own `GUIDANCE_DECLARATION_HAND_EDITED` (a sealed class
        marker's recorded seal not matching the computed one). `mark class`
        joins `cmd_mark`'s own dispatch (`cmd_mark` -> `cmd_mark_class`),
        never a new top-level root, so the top-level verb-roster count this
        skill's own `test_skill_audit.py` probe measures is unmoved by S3.
        S4 (`source_revisions_undeclared_detail`) adds no new code: both
        raise sites reuse `SOURCE_REVISIONS_UNDECLARED` verbatim through one
        shared builder. Measured directly against `reachable_paper_refusal_
        codes()`, never forecast.

        159 -> 161: `SECTION_UNKNOWN` and `BLOCK_UNDECLARED`. Both replace a
        crash, never a behaviour that used to be allowed -- `packet`, `write`
        and `place` composed the contract filename from the section id and
        then did a bare `next()` over the header's blocks, so a typo'd
        `--section`/`--block` and EVERY shipped contract alike died with a
        traceback and exit 1 instead of this skill's refusal envelope.

        161 -> 165 in `the-block-asserts-only-what-its-section-carries`:
        `paper_grounding.py` (newly imported, `# for the roster derivation`)
        gains four raise sites -- `reconcile_support`'s own
        `GROUNDING_ACCOUNT_ABSENT`, `GROUNDING_SENTENCE_UNKNOWN`,
        `GROUNDING_VERDICT_MISSING` and `SECTION_UNSUPPORTED_CLAIM`, the
        fourth sibling in `write_block`'s judge chain that reconciles a
        per-sentence support account against a transposition block's own
        bound source section bytes. Reachable through the whole-module scan
        the moment the new import lands; `cmd_write`'s own `--grounding`
        wiring reaches the same module through `write_block`, contributing
        no code of its own. Measured directly against `reachable_paper_
        refusal_codes()`, EXECUTED after all of this change's engine code
        landed, never forecast.

        165 -> 167 in `model-output-validation` (Issue #71):
        `cmd_write` and `write_block` validate draft and audit account
        JSON envelopes before indexing fields, adding `DRAFT_UNREADABLE`
        and `AUDIT_UNREADABLE` (both invocation defects)."""
        self.assertEqual(len(reachable_paper_refusal_codes()), 167)


class ObjectiveNorthTests(unittest.TestCase):
    """`paper_objective.OBJECTIVE_FLOW` is the north `tests/test_agents.py`
    reads to gate every paper-writing agent's frontmatter (`stage_conditions()`
    there) -- but that file only ever reads a stage's `behindWhen` to find the
    ONE stage a person's word closes (`UNMEASURABLE`). Nothing anywhere checks
    a MEASURABLE `behindWhen` -- one that names a fact a run can check, not a
    human's future call -- against what `paper_cli.py` actually ships today.
    A stage whose own verbs are already live in the CLI's parser roster,
    while its `behindWhen` still says the capability "does not exist yet", is
    exactly the drift an agent reads and then refuses to run a shipped verb
    over.

    `STAGE_VERBS` is not invented: every verb named for a stage below is
    quoted, together with the one-line help `paper_cli.py`'s own
    `build_parser()` gives it, in this same table this class's docstring and
    D3's own defect report both drew from `paper_cli.py --help`. A stage
    absent from this table is simply not covered by this guard -- it is not
    a claim that stage's own `behindWhen` is trustworthy.
    """

    #: A `behindWhen` phrase asserting the stage's capability is flatly
    #: unbuilt -- as opposed to `write`'s legitimate "not yet fed in
    #: automatically", which names a missing AUTOMATION, not a missing verb,
    #: and must never trip this pattern.
    ABSENT_CLAIM = re.compile(
        r"\bno verb\b|\bhas no\b[^.]*\btoolchain\b|\bdoes not exist yet\b",
        re.IGNORECASE,
    )

    # stage -> the paper_cli.py verb(s) whose presence in its OWN parser
    # roster falsifies a behindWhen claiming that stage's capability is
    # unbuilt. Each verb is the one paper_cli.py --help names for exactly
    # this stage's `establishes` text:
    #   cite    -> resolve ("resolve one identifier's metadata through a
    #              named connector"), bib ("refs.bib management -- never
    #              hand-typed"), validate ("the single gate: submit one
    #              judged verdict ... write on success")
    #   render  -> render ("compile one diagram id standalone ... via
    #              latexmk"), place ("place an already-measured figure's
    #              PDF")
    #   verify  -> verify ("read-only report over the couplings, citation
    #              integrity and contract currency")
    STAGE_VERBS = {
        "scaffold": ("scaffold",),
        "plan": ("plan",),
        "declare": ("declare",),
        "cite": ("resolve", "bib", "validate"),
        "write": ("write",),
        "render": ("render", "place"),
        "verify": ("verify",),
    }

    def shipped_verbs(self) -> set[str]:
        """The verb roster `paper_cli.py`'s own `build_parser()` accepts --
        the same names `--help` prints, read from the live parser rather than
        grepped, so a renamed or removed verb changes this set too."""
        parser = paper_cli.build_parser()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                return set(action.choices.keys())
        raise AssertionError("paper_cli.py's parser declares no subcommands "
                              "-- build_parser()'s shape moved")

    def test_a_measurable_behindwhen_never_claims_a_shipped_verb_is_absent(self) -> None:
        """Cross `OBJECTIVE_FLOW` against the CLI it describes.

        For every stage this class has a verb mapping for: if its own
        `behindWhen` claims the capability does not exist (`ABSENT_CLAIM`),
        every verb `STAGE_VERBS` names for that stage must be MISSING from
        `paper_cli.py`'s actual roster -- otherwise the claim is false today,
        not merely destined to become false later.
        """
        shipped = self.shipped_verbs()
        stages = {stage["stage"]: stage["behindWhen"]
                  for stage in paper_objective.OBJECTIVE_FLOW["stages"]}
        for stage, verbs in self.STAGE_VERBS.items():
            self.assertIn(
                stage, stages,
                f"OBJECTIVE_FLOW no longer declares a {stage!r} stage -- "
                f"update STAGE_VERBS or this test, never assume it still "
                f"applies")
            when = stages[stage]
            if not self.ABSENT_CLAIM.search(when):
                continue
            shipped_for_stage = sorted(set(verbs) & shipped)
            self.assertFalse(
                shipped_for_stage,
                f"{stage!r}'s behindWhen claims its capability does not "
                f"exist ({when!r}), but paper_cli.py's own parser roster "
                f"already ships {shipped_for_stage!r} for it -- the north "
                f"is stale, not the CLI")


def _write_optional_contribution_section(sections_dir: Path, *, optional: bool) -> None:
    """One block, `res-contrib`, requiring the `contributions` fact --
    minimal enough that `check_contribution_list`'s derived block set for
    this corpus is exactly this one block, so "entirely optional-and-
    unopened" is trivially the whole set (`optional-block-semantics` spec,
    tasks.md Work Unit 3, 3.6/3.7). A second file supplies `contributions`'
    own producer (`a-fact-is-declared-or-it-is-produced`, `fact-production`
    spec, `Requirement: Every Producer Is Either Sole Or Corroborated`) --
    non-optional and never itself required, so it neither enters
    `check_contribution_list`'s own derived block set nor `optional_ids`."""
    sections_dir.mkdir(parents=True, exist_ok=True)
    source_header = {
        "section": "front-matter", "position": 0,
        "blocks": [
            {
                "id": "contrib-source",
                "requires_facts": [], "requires_declarations": [], "citations": "none",
                "produces_facts": [
                    {
                        "value": "contributions",
                        "source": {
                            "file": "sections/00-front-matter.md",
                            "quote": "This block produces the contributions.",
                        },
                    }
                ],
            },
        ],
    }
    source_text = (
        "---\n" + json.dumps(source_header, indent=2) + "\n---\n\nProse. This block produces the "
        "contributions.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
    )
    (sections_dir / "00-front-matter.md").write_text(source_text, encoding="utf-8")

    header = {
        "section": "results", "position": 1,
        "blocks": [
            {
                "id": "res-contrib",
                "requires_facts": [
                    {
                        "value": "contributions",
                        "source": {
                            "file": "sections/01-results.md",
                            "quote": "This block requires the contributions.",
                        },
                    }
                ],
                "requires_declarations": [], "citations": "none", "optional": optional,
                "after": [
                    {
                        "target": "front-matter.contrib-source",
                        "source": {
                            "file": "sections/01-results.md",
                            "quote": "This block requires the contributions.",
                        },
                    }
                ],
            },
        ],
    }
    text = (
        "---\n" + json.dumps(header, indent=2) + "\n---\n\nProse. This block requires the "
        "contributions.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\n"
        "| Block | Depends on |\n|---|---|\n"
        "| `results.res-contrib` | `front-matter.contrib-source` |\n"
    )
    (sections_dir / "01-results.md").write_text(text, encoding="utf-8")


class OptionalVerifyTests(unittest.TestCase):
    """`optional-block-semantics` spec, `Requirement: Verify Excuses An
    Unopened Optional Block` (tasks.md, Work Unit 3, 3.5-3.7). Calls each
    check function directly with an explicit `optional_block_ids` set built
    from a real corpus read -- the wiring of that set into `run()`'s only
    real caller today (`paper_cli.cmd_verify`) is deferred: it needs
    `paper_graph.assemble_corpus`, and neither `paper_cli.py` nor
    `paper_coupling_evidence.py` is in this unit's allowed edit roots. See
    this unit's own notes for exactly why."""

    def _build(self, *, optional: bool, opened: bool):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        paper_dir = Path(tmp.name) / "paper"
        sections_dir = Path(tmp.name) / "sections"
        _write_optional_contribution_section(sections_dir, optional=optional)
        paper_scaffold.scaffold(paper_dir)
        if opened:
            paper_block.open_block(paper_dir, "res-contrib", at_end=True)
        (paper_dir / "couplings.json").write_text(
            json.dumps({"blocks": {"res-contrib": True}, "facts": {"contributions": []}}),
            encoding="utf-8",
        )
        corpus = paper_graph.assemble_corpus(sections_dir)
        optional_ids = frozenset(b.block_id for b in corpus.blocks.values() if b.optional)
        evidence = paper_coupling_evidence.gather(paper_dir, sections_dir)
        return evidence, optional_ids

    def test_unopened_optional_block_reports_unmeasured_optional_block_absent(self) -> None:
        evidence, optional_ids = self._build(optional=True, opened=False)

        entry = paper_verify.check_contribution_list(evidence, optional_block_ids=optional_ids)

        self.assertEqual(entry["verdict"], "unmeasured")
        self.assertEqual(entry["unmeasured_reason"], "OPTIONAL_BLOCK_ABSENT")

    def test_unopened_non_optional_block_never_reports_optional_block_absent(self) -> None:
        evidence, optional_ids = self._build(optional=False, opened=False)

        entry = paper_verify.check_contribution_list(evidence, optional_block_ids=optional_ids)

        self.assertNotEqual(entry["unmeasured_reason"], "OPTIONAL_BLOCK_ABSENT")

    def test_opened_optional_block_is_checked_exactly_like_a_non_optional_opened_block(self) -> None:
        optional_evidence, optional_ids = self._build(optional=True, opened=True)
        plain_evidence, plain_ids = self._build(optional=False, opened=True)

        optional_entry = paper_verify.check_contribution_list(optional_evidence, optional_block_ids=optional_ids)
        plain_entry = paper_verify.check_contribution_list(plain_evidence, optional_block_ids=plain_ids)

        self.assertNotEqual(optional_entry["unmeasured_reason"], "OPTIONAL_BLOCK_ABSENT")
        self.assertEqual(optional_entry["verdict"], plain_entry["verdict"])
        self.assertEqual(optional_entry["unmeasured_reason"], plain_entry["unmeasured_reason"])

    def test_run_default_optional_block_ids_never_changes_behavior(self) -> None:
        """`run()`'s new keyword-only parameter defaults to an empty
        `frozenset()` -- calling it exactly as every existing caller does
        today must report byte-identical results."""
        evidence, _optional_ids = self._build(optional=True, opened=False)

        report = paper_verify.run(evidence)

        by_check = {entry["check"]: entry for entry in report["checks"]}
        self.assertNotEqual(by_check["contribution-list"]["unmeasured_reason"], "OPTIONAL_BLOCK_ABSENT")


class OptionalReadinessTests(unittest.TestCase):
    """`optional-block-semantics` spec, `Requirement: Readiness Reports The
    Optional Flag` (tasks.md, Work Unit 3, 3.1/3.3) and the `not-applicable`
    status half of `Requirement: ...` D6 describes (3.2/3.4) -- the basis
    dispatch itself (`--paper`, `READINESS_BASIS_REQUIRED`) is Work Unit 6's
    job; this class proves the pure function `compute_block_readiness`/
    `compute_readiness` grew, called directly with explicit `opened`/`basis`
    values, never through an invented CLI flag."""

    def test_optional_flag_is_read_verbatim_over_the_shipped_corpus(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)

        report = paper_readiness.compute_readiness(corpus, satisfied_facts=set(), satisfied_declarations=set())

        by_block = {entry["block"]: entry for entry in report}
        self.assertTrue(by_block["materials-and-methods.mm-dataset"]["optional"])
        self.assertFalse(by_block["experimental-setup.es-assessment"]["optional"])

    def test_optional_unopened_block_is_not_applicable_under_declaration_backed_basis(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        block = corpus.blocks["materials-and-methods.mm-dataset"]

        declaration_backed = paper_readiness.compute_block_readiness(
            block, satisfied_facts=set(), satisfied_declarations=set(),
            opened=False, basis="declaration-backed",
        )
        flags_only = paper_readiness.compute_block_readiness(
            block, satisfied_facts=set(), satisfied_declarations=set(),
        )

        self.assertEqual(declaration_backed["status"], "not-applicable")
        self.assertIn(flags_only["status"], ("writable", "blocked"))
        self.assertNotEqual(flags_only["status"], "not-applicable")

    def test_optional_opened_block_is_never_not_applicable(self) -> None:
        """`not-applicable` gates on ABSENCE, never on the `optional`
        declaration alone -- the same discriminating principle
        `optional-block-semantics`'s `paper_verify` requirement states
        explicitly, proven here on the readiness side too."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        block = corpus.blocks["materials-and-methods.mm-dataset"]

        opened_and_backed = paper_readiness.compute_block_readiness(
            block, satisfied_facts=set(), satisfied_declarations=set(),
            opened=True, basis="declaration-backed",
        )

        self.assertNotEqual(opened_and_backed["status"], "not-applicable")

    def test_a_non_optional_block_is_never_not_applicable_even_when_unopened(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        block = corpus.blocks["experimental-setup.es-assessment"]

        report = paper_readiness.compute_block_readiness(
            block, satisfied_facts=set(), satisfied_declarations=set(),
            opened=False, basis="declaration-backed",
        )

        self.assertNotEqual(report["status"], "not-applicable")


class OptionalVerifyWiringTests(unittest.TestCase):
    """tasks.md Work Unit 9b: the wiring Work Unit 3 built and proved but
    could not perform itself (`OptionalVerifyTests`, above, calls
    `paper_verify.check_contribution_list` directly with a hand-supplied
    `optional_block_ids`). This class exercises `paper_cli.cmd_verify`
    itself -- the defect this unit closes lived entirely in that function's
    own body, which never resolved or passed `optional_block_ids` at all.

    `cmd_verify` resolves `--paper`/`--sections` against the REAL
    repository root (`paper_scaffold.FORGE_ROOT`), so -- the same
    convention `CouplingVerifyCLITests` already established -- this
    fixture lives under the already-gitignored `.scratch/` tree,
    never an arbitrary tempdir outside it.
    """

    def setUp(self) -> None:
        test_root = FORGE_ROOT / ".scratch" / f".paper-writing-9b-verify-wiring-{os.getpid()}"
        self.addCleanup(shutil.rmtree, test_root, ignore_errors=True)
        self.paper_dir = test_root / "paper"
        self.sections_dir = test_root / "sections"
        _write_optional_contribution_section(self.sections_dir, optional=True)
        paper_scaffold.scaffold(self.paper_dir)
        # `res-contrib` is declared but never opened: absent from `main.tex`.
        # `contributions` is non-empty on purpose (unlike `OptionalVerifyTests`'
        # own `_build`, whose empty list would report `BLOCK_NOT_DECLARED`
        # either way and hide the exact difference this unit proves) --
        # with the wire absent, this specific record instead reaches the
        # order-comparison branch and reports `fail`.
        (self.paper_dir / "couplings.json").write_text(
            json.dumps({"blocks": {"res-contrib": True}, "facts": {"contributions": ["Foo"]}}),
            encoding="utf-8",
        )
        self.args = argparse.Namespace(paper=str(self.paper_dir), sections=str(self.sections_dir))

    def test_resolve_optional_block_ids_measures_the_shipped_corpus(self) -> None:
        """Measured directly against the real, shipped `sections/` tree --
        never forecast. `paper_readiness`'s own shipped-corpus test
        (`OptionalReadinessTests.test_optional_flag_is_read_verbatim_over_
        the_shipped_corpus`) checks two individual blocks; this asserts the
        WHOLE derived set `cmd_verify` would thread through `verify` today."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        expected = frozenset(b.block_id for b in corpus.blocks.values() if b.optional)

        self.assertEqual(paper_cli._resolve_optional_block_ids(SECTIONS_DIR), expected)
        # None of the four facts `verify`'s own checks read (`contributions`,
        # `problem-statement`, `gap`, `limitations`) map to an ENTIRELY
        # optional block set on the real shipped corpus today -- every one
        # of them is also required by at least one non-optional block --
        # so `OPTIONAL_BLOCK_ABSENT` cannot be observed through the real
        # `verify` verb against the unmodified `sections/` tree. Measured,
        # not assumed: this is why the load-bearing proof below builds its
        # own minimal fixture, the same way `WaveTests`/`SkeletonPathContain
        # mentTests` already do for their own units, rather than forcing a
        # false positive out of data this unit's scope may not edit.
        by_fact = {}
        for record in corpus.blocks.values():
            for fact in ("contributions", "problem-statement", "gap", "limitations"):
                if fact in record.requires_facts:
                    by_fact.setdefault(fact, []).append(record.optional)
        for fact, flags in by_fact.items():
            self.assertFalse(all(flags), f"{fact!r} unexpectedly maps to an all-optional block set")

    def test_cmd_verify_reports_optional_block_absent_for_an_unopened_optional_block(self) -> None:
        report = paper_cli.cmd_verify(self.args)

        by_check = {entry["check"]: entry for entry in report["checks"]}
        self.assertEqual(by_check["contribution-list"]["verdict"], "unmeasured")
        self.assertEqual(by_check["contribution-list"]["unmeasured_reason"], "OPTIONAL_BLOCK_ABSENT")

    def test_mutation_the_wire_is_load_bearing_not_merely_present(self) -> None:
        """RED-first mutation, run against the exact defect Work Unit 3's
        own notes name: `cmd_verify` never resolving or passing
        `optional_block_ids` at all (its shipped body called
        `paper_verify.run(evidence)` with no keyword). Patching
        `_resolve_optional_block_ids` to always return an empty set
        reproduces that exact shipped defect; against the SAME fixture the
        previous test proves `pass`es today, the coupling stops reporting
        `unmeasured` altogether and reports `fail` instead -- proving the
        parameter changes real behavior, not merely that it is accepted."""
        with unittest.mock.patch.object(paper_cli, "_resolve_optional_block_ids", return_value=frozenset()):
            unwired_report = paper_cli.cmd_verify(self.args)
        wired_report = paper_cli.cmd_verify(self.args)

        unwired_entry = {e["check"]: e for e in unwired_report["checks"]}["contribution-list"]
        wired_entry = {e["check"]: e for e in wired_report["checks"]}["contribution-list"]

        self.assertEqual(wired_entry["unmeasured_reason"], "OPTIONAL_BLOCK_ABSENT")
        self.assertNotEqual(unwired_entry["verdict"], "unmeasured")
        self.assertEqual(unwired_entry["verdict"], "fail")

    def test_paper_verify_import_allowlist_is_unchanged_and_still_green(self) -> None:
        """9b.4: the resolution belongs one level up in `cmd_verify`
        precisely because `paper_verify.py`'s own AST-enforced import lock
        (`ReadOnlyTests`, above) forbids it from reading `sections_dir`
        itself -- confirm that lock is UNCHANGED: still exactly `{"re"}`
        for real imports (`__future__` is the one `ImportFrom` the same
        lock already exempts), never widened to make this unit's own fix
        easier. `ReadOnlyTests` itself, run as part of this same suite,
        is the load-bearing proof; this is a direct, local confirmation."""
        tree = ast.parse((SKILL_SCRIPTS / "paper_verify.py").read_text(encoding="utf-8"))
        real_imports = set()
        import_from_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                real_imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                import_from_modules.add(node.module)
        self.assertEqual(real_imports, {"re"})
        self.assertEqual(import_from_modules, {"__future__"})

    def test_verify_writes_nothing_including_this_units_own_refusal_paths(self) -> None:
        """9b.5: the before/after content manifest, over this unit's own
        fixture -- `verify` must write nothing under every input, including
        every refusal path, exactly as it did before this unit existed."""

        def _manifest() -> dict:
            return {
                str(path.relative_to(self.paper_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(self.paper_dir.rglob("*")) if path.is_file()
            }

        paper_cli.cmd_verify(self.args)
        before = _manifest()

        (self.paper_dir / "couplings.json").unlink()
        with self.assertRaises(Refused):
            paper_cli.cmd_verify(self.args)
        after = _manifest()

        # `couplings.json` was removed by this test itself, above, as the
        # refusal trigger -- everything else must still match byte for byte.
        before.pop("couplings.json", None)
        after.pop("couplings.json", None)
        self.assertEqual(before, after)


# =====================================================================
# `derive_waves` -- Work Unit 5
# =====================================================================

#: `writing-phases` spec / tasks.md Work Unit 5. Every fixture below is
#: SYNTHETIC -- never the live `sections/` tree, whose shape keeps moving
#: under later units. Mirrors `test_paper_contract.py`'s own
#: `_write_section`/`_block`/`_quote_source` shape (`### Internal chain`
#: stays "None": transcribing a chain PROSE row into a graph edge is unit
#: 4's concern, already covered there -- this unit only exercises
#: header-level `after` edges over `_build_graph`/`derive_waves`).
_WAVE_BODY = "Prose.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"


def _wave_section(section: str, position: int, block_id: str, *, after=None) -> dict:
    header = {
        "section": section,
        "position": position,
        "blocks": [
            {"id": block_id, "requires_facts": [], "requires_declarations": [], "citations": "none"},
        ],
    }
    if after is not None:
        header["after"] = after
    return header


def _write_wave_section(sections_dir: Path, filename: str, header: dict) -> None:
    sections_dir.mkdir(parents=True, exist_ok=True)
    text = "---\n" + json.dumps(header, indent=2) + "\n---\n\n" + _WAVE_BODY
    (sections_dir / filename).write_text(text, encoding="utf-8")


def _wave_after(target: str, source_file: str) -> dict:
    return {"target": target, "source": {"file": source_file, "quote": "Prose."}}


class WaveTests(unittest.TestCase):
    """`writing-phases` spec, `Requirement: Wave Grouping Is Frontier-
    Based` (tasks.md Work Unit 5, 5.1-5.10). `derive_waves` groups
    `derive_order`'s own graph into Kahn frontiers instead of flattening
    them -- design.md D2's five invariants, each proved independently."""

    def test_zero_edge_corpus_is_one_wave(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp) / "sections"
            _write_wave_section(sections_dir, "01-a.md", _wave_section("a", 1, "only"))
            _write_wave_section(sections_dir, "02-b.md", _wave_section("b", 2, "only"))
            _write_wave_section(sections_dir, "03-c.md", _wave_section("c", 3, "only"))

            corpus = paper_graph.assemble_corpus(sections_dir)
            edges = paper_graph.collect_edges(corpus)
            waves = paper_graph.derive_waves(corpus, edges)

            self.assertEqual(len(waves), 1)
            self.assertEqual(set(waves[0]), {"a.only", "b.only", "c.only"})

    def test_a_pure_chain_produces_n_waves_matching_chain_length(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp) / "sections"
            _write_wave_section(sections_dir, "01-a.md", _wave_section("a", 1, "only"))
            _write_wave_section(
                sections_dir, "02-b.md",
                _wave_section("b", 2, "only", after=[_wave_after("a", "sections/02-b.md")]),
            )
            _write_wave_section(
                sections_dir, "03-c.md",
                _wave_section("c", 3, "only", after=[_wave_after("b", "sections/03-c.md")]),
            )
            _write_wave_section(
                sections_dir, "04-d.md",
                _wave_section("d", 4, "only", after=[_wave_after("c", "sections/04-d.md")]),
            )

            corpus = paper_graph.assemble_corpus(sections_dir)
            edges = paper_graph.collect_edges(corpus)
            waves = paper_graph.derive_waves(corpus, edges)

            self.assertEqual(
                waves,
                [["a.only"], ["b.only"], ["c.only"], ["d.only"]],
            )

    def test_invariant_1_waves_partition_the_same_node_set_derive_order_returns(self) -> None:
        """Diamond fixture: a; b after a; c after a; d after b and c."""
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp) / "sections"
            _write_wave_section(sections_dir, "01-a.md", _wave_section("a", 1, "only"))
            _write_wave_section(
                sections_dir, "02-b.md",
                _wave_section("b", 2, "only", after=[_wave_after("a", "sections/02-b.md")]),
            )
            _write_wave_section(
                sections_dir, "03-c.md",
                _wave_section("c", 3, "only", after=[_wave_after("a", "sections/03-c.md")]),
            )
            _write_wave_section(
                sections_dir, "04-d.md",
                _wave_section("d", 4, "only", after=[
                    _wave_after("b", "sections/04-d.md"), _wave_after("c", "sections/04-d.md"),
                ]),
            )

            corpus = paper_graph.assemble_corpus(sections_dir)
            edges = paper_graph.collect_edges(corpus)
            order = paper_graph.derive_order(corpus, edges)
            waves = paper_graph.derive_waves(corpus, edges)

            from itertools import chain
            flattened_set = set(chain.from_iterable(waves))
            self.assertEqual(flattened_set, set(order))
            self.assertEqual(flattened_set, set(corpus.blocks))
            # No block omitted or duplicated across waves.
            self.assertEqual(sum(len(wave) for wave in waves), len(corpus.blocks))
            self.assertEqual(
                waves,
                [["a.only"], ["b.only", "c.only"], ["d.only"]],
            )

    def test_invariant_2_every_edge_crosses_a_wave_boundary(self) -> None:
        """Diamond fixture again, read generically: for every collected
        edge `(before, after)`, `wave_of(before) < wave_of(after)` --
        this is the exact test `_run_against_mutant` below targets."""
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp) / "sections"
            _write_wave_section(sections_dir, "01-a.md", _wave_section("a", 1, "only"))
            _write_wave_section(
                sections_dir, "02-b.md",
                _wave_section("b", 2, "only", after=[_wave_after("a", "sections/02-b.md")]),
            )
            _write_wave_section(
                sections_dir, "03-c.md",
                _wave_section("c", 3, "only", after=[_wave_after("a", "sections/03-c.md")]),
            )
            _write_wave_section(
                sections_dir, "04-d.md",
                _wave_section("d", 4, "only", after=[
                    _wave_after("b", "sections/04-d.md"), _wave_after("c", "sections/04-d.md"),
                ]),
            )

            corpus = paper_graph.assemble_corpus(sections_dir)
            edges = paper_graph.collect_edges(corpus)
            waves = paper_graph.derive_waves(corpus, edges)

            wave_of = {qid: index for index, wave in enumerate(waves) for qid in wave}
            for before, after, _source in edges.edges:
                self.assertLess(
                    wave_of[before], wave_of[after],
                    f"{before} (wave {wave_of[before]}) does not strictly precede "
                    f"{after} (wave {wave_of[after]})",
                )

    def test_invariant_3_wave_membership_is_independent_of_dict_iteration_order(self) -> None:
        """Waves are sorted by `_sort_key`, never by dict/filename
        iteration -- feed `collect_edges`' own edge list back in reversed
        order and confirm the waves (as sets, and as sorted lists) are
        unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp) / "sections"
            _write_wave_section(sections_dir, "01-a.md", _wave_section("a", 1, "only"))
            _write_wave_section(
                sections_dir, "02-b.md",
                _wave_section("b", 2, "only", after=[_wave_after("a", "sections/02-b.md")]),
            )
            _write_wave_section(
                sections_dir, "03-c.md",
                _wave_section("c", 3, "only", after=[_wave_after("a", "sections/03-c.md")]),
            )

            corpus = paper_graph.assemble_corpus(sections_dir)
            edges = paper_graph.collect_edges(corpus)
            waves_forward = paper_graph.derive_waves(corpus, edges)

            perturbed = paper_graph.EdgeSet(
                edges=list(reversed(edges.edges)), dangling=list(edges.dangling),
            )
            waves_perturbed = paper_graph.derive_waves(corpus, perturbed)

            self.assertEqual(waves_forward, waves_perturbed)

    def test_invariant_4_a_cycle_refuses_order_cycle_with_derive_orders_own_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp) / "sections"
            _write_wave_section(
                sections_dir, "01-a.md",
                _wave_section("a", 1, "x", after=[_wave_after("b.y", "sections/01-a.md")]),
            )
            _write_wave_section(
                sections_dir, "02-b.md",
                _wave_section("b", 2, "y", after=[_wave_after("a.x", "sections/02-b.md")]),
            )

            corpus = paper_graph.assemble_corpus(sections_dir)
            edges = paper_graph.collect_edges(corpus)

            with self.assertRaises(Refused) as order_ctx:
                paper_graph.derive_order(corpus, edges)
            with self.assertRaises(Refused) as waves_ctx:
                paper_graph.derive_waves(corpus, edges)

            self.assertEqual(waves_ctx.exception.code, "ORDER_CYCLE")
            self.assertEqual(waves_ctx.exception.detail, order_ctx.exception.detail)
            self.assertIn("a.x", waves_ctx.exception.detail)
            self.assertIn("b.y", waves_ctx.exception.detail)

    def test_invariant_5_flattened_waves_are_not_asserted_equal_to_derive_orders_sequence(self) -> None:
        """The rejected false lock, documented as a negative test
        (design.md D2, invariant 5): `derive_order`'s min-heap can pop a
        node from a LATER frontier ahead of a still-unpopped node from an
        EARLIER one, when the later node's `_sort_key` outranks it --
        legitimate interleaving, not a bug. Fixture: `alpha1` (position 1)
        and `alpha2` (position 10) are both wave 1 (no dependencies); `beta`
        (position 2) depends only on `alpha1`. `derive_order`'s heap pops
        `alpha1`, immediately frees `beta` (position 2), and pops IT before
        `alpha2` (position 10) -- but wave-grouping keeps `alpha2` in wave 1
        (it was ready from the start) and `beta` in wave 2 (it only became
        ready once wave 1 finished), so the two orders diverge."""
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp) / "sections"
            _write_wave_section(sections_dir, "01-alpha1.md", _wave_section("alpha1", 1, "only"))
            _write_wave_section(
                sections_dir, "02-beta.md",
                _wave_section("beta", 2, "only", after=[_wave_after("alpha1", "sections/02-beta.md")]),
            )
            _write_wave_section(sections_dir, "10-alpha2.md", _wave_section("alpha2", 10, "only"))

            corpus = paper_graph.assemble_corpus(sections_dir)
            edges = paper_graph.collect_edges(corpus)
            order = paper_graph.derive_order(corpus, edges)
            waves = paper_graph.derive_waves(corpus, edges)

            from itertools import chain
            flattened = list(chain.from_iterable(waves))

            # The false lock this test documents as REJECTED:
            self.assertNotEqual(
                flattened, order,
                "flattened waves equalled derive_order's own sequence on a "
                "genuinely multi-frontier fixture -- this fixture no longer "
                "demonstrates legitimate interleaving; strengthen it rather "
                "than assert sequence equality (design.md D2, invariant 5)",
            )
            # What IS true instead: same node set, waves respect dependency order.
            self.assertEqual(set(flattened), set(order))
            self.assertEqual(waves, [["alpha1.only", "alpha2.only"], ["beta.only"]])
            self.assertEqual(order, ["alpha1.only", "beta.only", "alpha2.only"])

    def test_the_real_shipped_corpus_decomposes_with_the_preamble_strictly_after_the_proposal(self) -> None:
        """Regression, not a fixture: `materials-and-methods.mm-proposal`
        must land strictly earlier than `materials-and-methods.mm-preamble`
        -- the single clearest evidence this change works (the preamble no
        longer shares a wave with the block it must name). Wave COUNT and
        exact per-wave sizes are measured, reported below, and deliberately
        NOT hard-asserted here: later units still change this corpus."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        edges = paper_graph.collect_edges(corpus)
        order = paper_graph.derive_order(corpus, edges)
        waves = paper_graph.derive_waves(corpus, edges)

        from itertools import chain
        flattened_set = set(chain.from_iterable(waves))
        self.assertEqual(flattened_set, set(order))
        self.assertEqual(flattened_set, set(corpus.blocks))
        self.assertEqual(sum(len(wave) for wave in waves), len(corpus.blocks))

        wave_of = {qid: index for index, wave in enumerate(waves) for qid in wave}
        for before, after, _source in edges.edges:
            self.assertLess(wave_of[before], wave_of[after])

        self.assertLess(
            wave_of["materials-and-methods.mm-proposal"],
            wave_of["materials-and-methods.mm-preamble"],
        )


class WaveMutationProofTests(unittest.TestCase):
    """tasks.md 5.6 / design.md's own mutation table, item 4: `derive_waves`
    appending a newly-ready successor to the CURRENT wave instead of the
    NEXT one must fail `WaveTests.test_invariant_2_every_edge_crosses_a_
    wave_boundary` -- a passing assertion beside an unexercised guard is
    not a mutation that ran."""

    def test_mutation_appending_to_the_current_wave_fails_the_boundary_invariant(self) -> None:
        proc = _run_against_mutant(
            "                if remaining_indegree[successor] == 0:\n"
            "                    next_frontier.append(successor)",
            "                if remaining_indegree[successor] == 0:\n"
            "                    waves[-1].append(successor)",
            "tests.test_paper_writing.WaveTests"
            ".test_invariant_2_every_edge_crosses_a_wave_boundary",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class ReadinessBasisTests(unittest.TestCase):
    """`writing-readiness` spec, `Requirement: Readiness Resolves Declared
    State From The Paper Directory` / `Requirement: A Bare Readiness Call
    Refuses Rather Than Guessing A Basis` / `Requirement: Optional Flag
    Surfaces In Readiness Reports` (tasks.md 6.4-6.7). `cmd_readiness`
    never opened `main.tex` before this unit -- `paper_cli.compute_
    readiness_report` is the basis dispatch, kept separate from argparse
    resolution (the same shape `compute_plan` keeps from `cmd_plan`) and
    exercised directly here."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()
        def _req(fact: str) -> dict:
            return {
                "value": fact,
                "source": {
                    "file": "sections/01-readiness-basis.md",
                    "quote": f"This block requires the {fact}.",
                },
            }

        header = json.dumps({
            "section": "readiness-basis",
            "position": 1,
            "blocks": [
                {
                    "id": "needs-formulation", "requires_facts": [_req("formulation")],
                    "requires_declarations": [], "citations": "none",
                },
                {
                    "id": "needs-both",
                    "requires_facts": [_req("formulation"), _req("dataset")],
                    "requires_declarations": [], "citations": "none",
                },
            ],
        })
        (self.sections_dir / "01-readiness-basis.md").write_text(
            f"---\n{header}\n---\n\nProse. This block requires the formulation. "
            "This block requires the dataset.\n\n### External inputs\n\nNone.\n\n"
            "### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )

    def _status_of(self, report: dict, block_id: str) -> str:
        block = next(b for b in report["blocks"] if b["block"] == block_id)
        return block["status"]

    def test_declared_fact_alone_reports_writable_with_no_flags_repeated(self) -> None:
        """tasks.md 6.5 / spec scenario 'Readiness changes after declare,
        with no flags repeated'."""
        paper_declarations.set_fact(
            self.paper_dir, "formulation", "the delta on the borrowed machinery",
        )

        report = paper_cli.compute_readiness_report(self.sections_dir, paper_dir=self.paper_dir)

        self.assertEqual(report["basis"], "declaration-backed")
        self.assertEqual(
            self._status_of(report, "readiness-basis.needs-formulation"), "writable",
        )

    def test_explicit_flag_adds_to_the_recorded_state(self) -> None:
        """tasks.md 6.6 / spec scenario 'Explicit flags still add to the
        recorded state'."""
        paper_declarations.set_fact(self.paper_dir, "formulation", "the delta")

        report = paper_cli.compute_readiness_report(
            self.sections_dir, paper_dir=self.paper_dir, flag_facts=frozenset({"dataset"}),
        )

        self.assertEqual(self._status_of(report, "readiness-basis.needs-both"), "writable")
        self.assertEqual(report.get("supposed"), ["dataset"])

    def test_neither_paper_nor_flags_refuses_readiness_basis_required(self) -> None:
        """tasks.md 6.7 / spec `Requirement: A Bare Readiness Call Refuses
        Rather Than Guessing A Basis`."""
        with self.assertRaises(Refused) as ctx:
            paper_cli.compute_readiness_report(self.sections_dir)
        self.assertEqual(ctx.exception.code, "READINESS_BASIS_REQUIRED")

    def test_flags_only_with_no_paper_preserves_the_hypothetical_what_if(self) -> None:
        """Regression: the pre-existing flags-only path must keep behaving
        exactly as it did before this unit -- basis `"supposed-only"`, no
        disk read at all, no `"supposed"` labelling (that only applies on
        top of a real declaration-backed read)."""
        report = paper_cli.compute_readiness_report(
            self.sections_dir, flag_facts=frozenset({"formulation", "dataset"}),
        )
        self.assertEqual(report["basis"], "supposed-only")
        self.assertEqual(self._status_of(report, "readiness-basis.needs-both"), "writable")
        self.assertNotIn("supposed", report)

    def test_optional_unopened_block_reports_not_applicable_under_declaration_backed_basis(
        self,
    ) -> None:
        """The `opened_blocks` half of 6.4's own wiring: an optional block
        absent from `main.tex` reports `not-applicable` once `readiness
        --paper` resolves openness from disk, never merely `blocked`
        (design.md D6; `optional-block-semantics` spec)."""
        header = json.dumps({
            "section": "optional-basis",
            "position": 2,
            "blocks": [
                {
                    "id": "maybe",
                    "requires_facts": [
                        {
                            "value": "dataset",
                            "source": {
                                "file": "sections/02-optional-basis.md",
                                "quote": "This block requires the dataset.",
                            },
                        }
                    ],
                    "requires_declarations": [], "optional": True, "citations": "none",
                },
            ],
        })
        (self.sections_dir / "02-optional-basis.md").write_text(
            f"---\n{header}\n---\n\nProse. This block requires the dataset."
            "\n\n### External inputs\n\nNone.\n\n"
            "### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )

        report = paper_cli.compute_readiness_report(self.sections_dir, paper_dir=self.paper_dir)

        self.assertEqual(self._status_of(report, "optional-basis.maybe"), "not-applicable")


class ReadinessProducedFactsTests(unittest.TestCase):
    """`a-fact-is-declared-or-it-is-produced`, tasks.md Unit 3, 3.1/3.4:
    `compute_block_readiness`/`compute_readiness` gain `produced_by` and
    `blocked_on_produced`; `compute_readiness_report`/`compute_phases`
    resolve it from the assembled corpus and derive a produced fact's
    satisfaction from its producer's own written status -- never from the
    `declarations` region (`paper-declarations` spec's carve-out) and never
    from a `declare` call, which this fixture never makes."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

        header = json.dumps({
            "section": "produced-readiness",
            "position": 1,
            "blocks": [
                {
                    "id": "producer", "requires_facts": [], "requires_declarations": [],
                    "citations": "none",
                    "produces_facts": [{
                        "value": "limitations",
                        "source": {
                            "file": "sections/01-produced-readiness.md",
                            "quote": "This block produces the limitations.",
                        },
                    }],
                },
                {
                    "id": "consumer",
                    "requires_facts": [{
                        "value": "limitations",
                        "source": {
                            "file": "sections/01-produced-readiness.md",
                            "quote": "This block requires the limitations.",
                        },
                    }],
                    "requires_declarations": [], "citations": "none",
                    "after": [{
                        "target": "produced-readiness.producer",
                        "source": {
                            "file": "sections/01-produced-readiness.md",
                            "quote": "This block requires the limitations.",
                        },
                    }],
                },
            ],
        })
        (self.sections_dir / "01-produced-readiness.md").write_text(
            f"---\n{header}\n---\n\nProse. This block produces the limitations. "
            "This block requires the limitations.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\n"
            "| Block | Depends on |\n|---|---|\n"
            "| `produced-readiness.consumer` | `produced-readiness.producer` |\n",
            encoding="utf-8",
        )

    def _readiness_block(self, block_id: str) -> dict:
        report = paper_cli.compute_readiness_report(self.sections_dir, paper_dir=self.paper_dir)
        return next(b for b in report["blocks"] if b["block"] == block_id)

    def _phases_block(self, block_id: str) -> dict:
        phases = paper_cli.compute_phases(self.paper_dir, self.sections_dir)
        for wave in phases["waves"]:
            for block in wave["blocks"]:
                if block["block"] == block_id:
                    return block
        raise AssertionError(f"{block_id!r} not found in any wave")

    def test_consumer_is_blocked_naming_the_producer_before_it_is_written(self) -> None:
        block = self._readiness_block("produced-readiness.consumer")

        self.assertEqual(block["status"], "blocked")
        self.assertEqual(block["missing_facts"], ["limitations"])
        self.assertEqual(
            block["blocked_on_produced"],
            [{"fact": "limitations", "producers": ["produced-readiness.producer"]}],
        )

    def test_consumer_becomes_writable_once_the_producer_is_opened_with_no_declare_call(
        self,
    ) -> None:
        """Spec scenario 'A produced fact becomes satisfied once its
        producer is written' -- no `declarations` region entry for
        `limitations` is ever created, and readiness still flips."""
        paper_block.open_block(self.paper_dir, "produced-readiness.producer", at_end=True)

        block = self._readiness_block("produced-readiness.consumer")

        self.assertEqual(block["status"], "writable")
        self.assertEqual(block["missing_facts"], [])
        self.assertNotIn("blocked_on_produced", block)
        satisfied_facts, _declarations = paper_declarations.read_satisfied(self.paper_dir)
        self.assertNotIn("limitations", satisfied_facts)

    def test_phases_agrees_the_consumer_is_writable_once_the_producer_is_opened(self) -> None:
        paper_block.open_block(self.paper_dir, "produced-readiness.producer", at_end=True)

        block = self._phases_block("produced-readiness.consumer")

        self.assertEqual(block["status"], "writable")
        self.assertEqual(block["blocked_on_produced"], [])

    def test_phases_agrees_the_consumer_is_blocked_before_the_producer_is_opened(self) -> None:
        block = self._phases_block("produced-readiness.consumer")

        self.assertEqual(block["status"], "blocked")
        self.assertEqual(block["missing_facts"], ["limitations"])

    def test_phases_carries_blocked_on_produced_wave_verify_finding_warning_1(self) -> None:
        """`sdd-verify` FAIL, WARNING 1: `cmd_phases`'s wave-block dict
        literal enumerated a fixed key set that never forwarded `blocked_
        on_produced`, even though `compute_phases` already resolves it
        through the SAME `paper_readiness.compute_readiness` call `cmd_
        readiness` uses — an operator following `SKILL.md`'s own "what can
        I write now" verb never saw which block to WRITE. No test asserted
        its presence in `phases` output in either direction before this
        one."""
        block = self._phases_block("produced-readiness.consumer")

        self.assertEqual(
            block["blocked_on_produced"],
            [{"fact": "limitations", "producers": ["produced-readiness.producer"]}],
        )


class ReadinessPhasesEndToEndTests(unittest.TestCase):
    """`writing-readiness` spec + `writing-phases` spec, driven through the
    real CLI end to end (tasks.md 6.8: 'a real `declare` write, then
    `readiness --paper` re-read shows the changed answer with no flags
    repeated') -- the single regression that proves the seam closed:
    recording a fact with `declare` must be SEEN by `readiness --paper`
    and by `phases`, not only by `plan`. `paper_cli.py` always resolves
    `--paper`/`--sections` against the real repository root, so this lives
    under the already-gitignored `.scratch/` tree, the same shape
    `CLIWiringTests` already establishes."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-phases-e2e-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, test_root, ignore_errors=True)
        self.paper_dir = test_root / "paper"
        self.sections_dir = test_root / "sections"
        self.sections_dir.mkdir(parents=True)

        header = json.dumps({
            "section": "e2e",
            "position": 1,
            "blocks": [
                {
                    "id": "needs-formulation",
                    "requires_facts": [
                        {
                            "value": "formulation",
                            "source": {
                                "file": "sections/01-e2e.md",
                                "quote": "This block requires the formulation.",
                            },
                        }
                    ],
                    "requires_declarations": [], "citations": "none",
                },
            ],
        })
        (self.sections_dir / "01-e2e.md").write_text(
            f"---\n{header}\n---\n\nProse. This block requires the formulation."
            "\n\n### External inputs\n\nNone.\n\n"
            "### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )

    def _run(self, *args: str):
        proc = subprocess.run(
            [sys.executable, str(CLI), *args],
            capture_output=True, text=True, timeout=30,
        )
        return proc.returncode, json.loads(proc.stdout), proc.stderr

    def _readiness_status(self) -> str:
        code, payload, stderr = self._run(
            "readiness", "--paper", str(self.paper_dir), "--sections", str(self.sections_dir),
        )
        self.assertEqual(code, 0, stderr or payload)
        self.assertEqual(payload["basis"], "declaration-backed")
        block = next(b for b in payload["blocks"] if b["block"] == "e2e.needs-formulation")
        return block["status"]

    def test_declare_then_readiness_paper_sees_it_with_no_flags_repeated(self) -> None:
        code, payload, stderr = self._run("scaffold", "--paper", str(self.paper_dir))
        self.assertEqual(code, 0, stderr or payload)

        self.assertEqual(
            self._readiness_status(), "blocked",
            "sanity check before declaring: the fact is not yet recorded",
        )

        code, payload, stderr = self._run(
            "declare", "--paper", str(self.paper_dir),
            "--fact", "formulation", "--value", "lumen-thesis-r21.md",
        )
        self.assertEqual(code, 0, stderr or payload)

        self.assertEqual(
            self._readiness_status(), "writable",
            "declare must be seen by readiness --paper with no flag repeated -- "
            "the regression `cmd_readiness` never opening main.tex left this "
            "structurally blind",
        )

    def test_phases_also_sees_the_same_declare(self) -> None:
        code, payload, stderr = self._run("scaffold", "--paper", str(self.paper_dir))
        self.assertEqual(code, 0, stderr or payload)
        code, payload, stderr = self._run(
            "declare", "--paper", str(self.paper_dir),
            "--fact", "formulation", "--value", "lumen-thesis-r21.md",
        )
        self.assertEqual(code, 0, stderr or payload)

        code, payload, stderr = self._run(
            "phases", "--paper", str(self.paper_dir), "--sections", str(self.sections_dir),
        )
        self.assertEqual(code, 0, stderr or payload)
        self.assertIn("formulation", payload["declared"]["facts"])
        block = next(
            b for wave in payload["waves"] for b in wave["blocks"]
            if b["block"] == "e2e.needs-formulation"
        )
        self.assertEqual(block["status"], "writable")

    def test_bare_readiness_call_refuses_readiness_basis_required(self) -> None:
        code, payload, stderr = self._run("scaffold", "--paper", str(self.paper_dir))
        self.assertEqual(code, 0, stderr or payload)

        code, payload, stderr = self._run("readiness", "--sections", str(self.sections_dir))

        self.assertEqual(code, 2, stderr or payload)
        self.assertEqual(payload["code"], "READINESS_BASIS_REQUIRED")


class PhasesTests(unittest.TestCase):
    """`writing-phases` spec, `Requirement: Phase N Is Gated On Phase N-1`
    (tasks.md 6.9-6.12); Open Question 2 (design.md), resolved: an
    `unprovenanced` block still counts as WRITTEN for this gate --
    provenance currency stays `plan`'s own separately-reported concern."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def _two_wave_corpus(self, *, second_optional_extra: bool = False) -> None:
        blocks_a = [
            {"id": "a", "requires_facts": [], "requires_declarations": [], "citations": "none"},
        ]
        if second_optional_extra:
            blocks_a.append({
                "id": "opt", "requires_facts": [], "requires_declarations": [],
                "citations": "none", "optional": True,
            })
        (self.sections_dir / "01-a.md").write_text(
            "---\n" + json.dumps({"section": "phase-a", "position": 1, "blocks": blocks_a})
            + "\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        (self.sections_dir / "02-b.md").write_text(
            "---\n" + json.dumps({
                "section": "phase-b", "position": 2,
                "blocks": [
                    {"id": "b", "requires_facts": [], "requires_declarations": [], "citations": "none"},
                ],
                "after": [
                    {"target": "phase-a.a", "source": {"file": "sections/02-b.md", "quote": "Prose."}},
                ],
            })
            + "\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n"
            "### Internal chain\n\n`phase-b.b` — `phase-a.a`\n",
            encoding="utf-8",
        )

    def test_phase_2_refuses_phase_not_ready_while_wave_1_is_incomplete(self) -> None:
        """tasks.md 6.10."""
        self._two_wave_corpus()

        with self.assertRaises(Refused) as ctx:
            paper_cli.compute_phases(self.paper_dir, self.sections_dir, phase=2)

        self.assertEqual(ctx.exception.code, "PHASE_NOT_READY")
        self.assertIn("phase-a.a", ctx.exception.detail)

    def test_phase_2_proceeds_once_wave_1_is_written(self) -> None:
        """tasks.md 6.11."""
        self._two_wave_corpus()
        paper_block.open_block(self.paper_dir, "phase-a.a", at_end=True)

        report = paper_cli.compute_phases(self.paper_dir, self.sections_dir, phase=2)

        self.assertEqual(len(report["waves"]), 2)
        self.assertEqual(report["waves"][0]["status"], "complete")
        self.assertEqual(report["waves"][1]["status"], "open")

    def test_an_unwritten_optional_block_never_gates_the_next_wave(self) -> None:
        """tasks.md 6.12."""
        self._two_wave_corpus(second_optional_extra=True)
        paper_block.open_block(self.paper_dir, "phase-a.a", at_end=True)

        report = paper_cli.compute_phases(self.paper_dir, self.sections_dir, phase=2)

        self.assertEqual(report["waves"][0]["status"], "complete")
        opt_entry = next(
            b for b in report["waves"][0]["blocks"] if b["block"] == "phase-a.opt"
        )
        self.assertFalse(opt_entry["opened"])

    def test_an_unprovenanced_block_still_counts_as_written_for_the_gate(self) -> None:
        """Open Question 2 (design.md), resolved at task 6.2: `phases`' own
        gate reads OPENNESS alone (`paper_block.status`), never provenance
        state -- opening `phase-a.a` with `open_block` and never
        substituting it (so it stays `unprovenanced`) is still enough to
        satisfy the wave-1 gate for wave 2."""
        self._two_wave_corpus()
        paper_block.open_block(self.paper_dir, "phase-a.a", at_end=True)

        report = paper_cli.compute_phases(self.paper_dir, self.sections_dir, phase=2)

        block_a = next(b for b in report["waves"][0]["blocks"] if b["block"] == "phase-a.a")
        self.assertEqual(block_a["provenance"], "unprovenanced")
        self.assertEqual(report["waves"][0]["status"], "complete")

    def test_phases_with_no_flag_reports_every_wave_the_full_plan(self) -> None:
        """tasks.md 6.13: the full wave plan, unfiltered -- what the
        operator approves once before writing starts
        (`specs/writing-phases/spec.md`, `Requirement: The Operator
        Approves The Phase Plan Before Writing Starts`)."""
        self._two_wave_corpus()

        report = paper_cli.compute_phases(self.paper_dir, self.sections_dir)

        self.assertEqual(len(report["waves"]), 2)
        self.assertEqual(
            {b["block"] for b in report["waves"][0]["blocks"]}, {"phase-a.a"},
        )
        self.assertEqual(
            {b["block"] for b in report["waves"][1]["blocks"]}, {"phase-b.b"},
        )


class WriteGateTests(unittest.TestCase):
    """`writing-phases` spec, `Requirement: Phase N Is Gated On Phase N-1`
    -- its own scenarios name `write`, not `phases` (tasks.md 6b.1-6b.5).
    Unit 6 wired `PHASE_NOT_READY` onto the read-only `phases` verb alone;
    `cmd_write` never consulted `derive_waves` at all, so nothing stopped
    a later wave being written before an earlier one existed -- the gate
    reported, it never gated. Unit 6's own Notes flagged that no test
    anywhere bound `PHASE_NOT_READY` to `write`; this class closes exactly
    that gap by exercising the REAL `cmd_write` root directly, never
    `paper_write.write_block` alone.

    Runs under a real `paper_dir`/`sections_dir` rooted under `FORGE_ROOT`
    -- `paper_scaffold.resolve_paper_dir`'s own containment requirement,
    the same already-gitignored `.scratch/` convention
    `test_cli_scaffold_verb_runs_and_emits_json` above uses -- because
    `cmd_write` resolves both through the real, non-injectable
    `FORGE_ROOT` default, unlike `compute_phases`, which `PhasesTests`
    above calls directly with an injected `forge_root`.

    `--draft`/`--audit` deliberately name files that are NEVER created:
    the phase gate must refuse (or, once open, the pipeline must fail on
    a DIFFERENT, unrelated error) before either path is ever opened --
    which side of that line execution reached is exactly what each test
    below proves.
    """

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-write-gate-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)

        blocks_a = [
            {"id": "a", "requires_facts": [], "requires_declarations": [], "citations": "none"},
        ]
        (self.sections_dir / "01-a.md").write_text(
            "---\n" + json.dumps({"section": "phase-a", "position": 1, "blocks": blocks_a})
            + "\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        (self.sections_dir / "02-b.md").write_text(
            "---\n" + json.dumps({
                "section": "phase-b", "position": 2,
                "blocks": [
                    {"id": "b", "requires_facts": [], "requires_declarations": [], "citations": "none"},
                ],
                "after": [
                    {"target": "phase-a.a", "source": {"file": "sections/02-b.md", "quote": "Prose."}},
                ],
            })
            + "\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n"
            "### Internal chain\n\n`phase-b.b` — `phase-a.a`\n",
            encoding="utf-8",
        )

        self.args = argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="phase-b", block="b",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=None,
        )

    def test_write_on_a_wave_2_block_refuses_phase_not_ready_while_wave_1_is_unwritten(self) -> None:
        """tasks.md 6b.3, RED-first: written before `cmd_write` consulted
        `derive_waves` at all, this failed against that `cmd_write` with
        `FileNotFoundError` on `draft.json` instead of `Refused` -- proof
        the gate was never reached on the real write path."""
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self.args)

        self.assertEqual(ctx.exception.code, "PHASE_NOT_READY")
        self.assertIn("phase-a.a", ctx.exception.detail)
        self.assertFalse((self.test_root / "draft.json").exists())
        self.assertFalse((self.test_root / "audit.json").exists())

    def test_write_on_the_same_block_proceeds_once_wave_1_is_written(self) -> None:
        """tasks.md 6b.4: a gate that never opens is as wrong as one that
        never closes. Opening `phase-a.a` clears the gate; `cmd_write`
        then runs PAST it and fails on the very next real stage instead
        -- the draft file this test deliberately never creates --
        `Refused('DRAFT_UNREADABLE')`, never `Refused('PHASE_NOT_READY')`."""
        paper_block.open_block(self.paper_dir, "phase-a.a", at_end=True)

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self.args)
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")


class WriteGateMutationProofTests(unittest.TestCase):
    """tasks.md 6b.5: the gate must be load-bearing on the real write
    path, not merely present beside it. Removing `cmd_write`'s own call
    to `_resolve_write_gate` must fail `WriteGateTests.test_write_on_a_
    wave_2_block_refuses_phase_not_ready_while_wave_1_is_unwritten` -- a
    passing test beside an unexercised guard is not a mutation that ran.
    """

    def test_mutation_removing_the_gate_call_fails_the_write_path_refusal(self) -> None:
        proc = _run_against_mutant(
            '    corpus = _resolve_write_gate(paper_dir, sections_dir, qualified_id)\n',
            "",
            "tests.test_paper_writing.WriteGateTests"
            ".test_write_on_a_wave_2_block_refuses_phase_not_ready_while_wave_1_is_unwritten",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class SourceSectionBindingWriteGateTests(unittest.TestCase):
    """`writing-orchestration` spec, `Requirement: Section Binding
    Resolution Gates write, Not Only A Read-Only Verb` (U3): every refusal
    `source-section-binding` raises during corpus assembly MUST stop
    `write` before the readiness stage, exercised through the REAL
    `cmd_write` root directly -- never `paper_graph.assemble_corpus` called
    in isolation, and never only the read-only `phases` verb. `write`
    reaches `assemble_corpus` through `_resolve_write_gate`'s own first
    statement, the SAME choke point `WriteGateTests` above already proves
    load-bearing for `PHASE_NOT_READY` -- this class proves the identical
    choke point also carries all six `source-section-binding` codes, plus
    `EVIDENCE_ROOT_AMBIGUOUS` (U2c), never reachable only from `phases`.

    Runs under a real `paper_dir`/`sections_dir` rooted under `FORGE_ROOT`
    -- `cmd_write` resolves both through the real, non-injectable
    `FORGE_ROOT` default, the same containment `WriteGateTests` above
    requires. `--draft`/`--audit` name files that are NEVER created: every
    refusal below MUST fire before either path is ever opened.
    """

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-binding-write-gate-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)

    def _write_bound_section(self, entry: dict) -> None:
        blocks = [{
            "id": "only", "requires_facts": [entry],
            "requires_declarations": [], "citations": "none",
        }]
        (self.sections_dir / "01-a.md").write_text(
            "---\n" + json.dumps({"section": "a", "position": 1, "blocks": blocks})
            + "\n---\n\nThe formulation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )

    def _marker(self, root: Path, prefix: str = "r", digits: int = 2) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": prefix, "ordinal_digits": digits}}),
            encoding="utf-8",
        )

    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="a", block="only",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=None,
        )

    def _assert_refuses_before_drafting(self, code: str) -> None:
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        before = tex_path.read_bytes()

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self._args())

        self.assertEqual(ctx.exception.code, code)
        self.assertFalse((self.test_root / "draft.json").exists())
        self.assertFalse((self.test_root / "audit.json").exists())
        self.assertEqual(tex_path.read_bytes(), before)

    def test_write_refuses_section_not_in_source(self) -> None:
        self._write_bound_section({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
            "document": {"lineage": "lumen-thesis", "section": "9. Missing"},
        })
        proposals = self.test_root / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")

        self._assert_refuses_before_drafting("SECTION_NOT_IN_SOURCE")

    def test_write_refuses_section_title_ambiguous(self) -> None:
        self._write_bound_section({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
            "document": {"lineage": "lumen-thesis", "section": "1. Intro"},
        })
        proposals = self.test_root / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 1. Intro\n", encoding="utf-8",
        )

        self._assert_refuses_before_drafting("SECTION_TITLE_AMBIGUOUS")

    def test_write_refuses_section_binding_absent(self) -> None:
        self._write_bound_section({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
        })
        proposals = self.test_root / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")

        self._assert_refuses_before_drafting("SECTION_BINDING_ABSENT")

    def test_section_binding_absent_names_the_block_fact_root_and_candidates(self) -> None:
        """U3e ruling: the refusal IS the question. A person reading it
        must be able to answer it without opening anything -- the block,
        the fact, the root, the resolved current revision (highest
        ordinal wins over an older one), and the section titles that
        revision actually carries RIGHT NOW, read from disk at refusal
        time, never cached or hand-listed."""
        self._write_bound_section({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
        })
        proposals = self.test_root / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r20.md").write_text("# Old\n", encoding="utf-8")
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n", encoding="utf-8",
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self._args())

        self.assertEqual(ctx.exception.code, "SECTION_BINDING_ABSENT")
        detail = ctx.exception.detail
        self.assertIn("a.only", detail)
        self.assertIn("formulation", detail)
        self.assertIn("proposals", detail)
        self.assertIn("lumen-thesis-r21.md", detail)
        self.assertNotIn("lumen-thesis-r20.md", detail)
        self.assertIn("1. Intro", detail)
        self.assertIn("3. Something", detail)
        self.assertIn("bind", detail)

    def test_write_refuses_source_lineage_unresolved(self) -> None:
        self._write_bound_section({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
            "document": {"lineage": "lumen-thesis", "section": "1. Intro"},
        })
        proposals = self.test_root / "proposals"
        self._marker(proposals)
        (proposals / "other-concept-r21.md").write_text("# 1. Intro\n", encoding="utf-8")

        self._assert_refuses_before_drafting("SOURCE_LINEAGE_UNRESOLVED")

    def test_write_refuses_source_revisions_undeclared(self) -> None:
        """The marker codes reach `write` through the SAME corpus assembly
        as the binding codes -- invoked directly via `write`, never only
        via `phases`."""
        self._write_bound_section({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
            "document": {"lineage": "lumen-thesis", "section": "1. Intro"},
        })
        proposals = self.test_root / "proposals"
        proposals.mkdir()
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")

        self._assert_refuses_before_drafting("SOURCE_REVISIONS_UNDECLARED")

    def test_write_refuses_malformed_source_marker(self) -> None:
        self._write_bound_section({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
            "document": {"lineage": "lumen-thesis", "section": "1. Intro"},
        })
        proposals = self.test_root / "proposals"
        proposals.mkdir()
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")
        (proposals / ".paper-writing.json").write_text(
            json.dumps({"class": "style-reference"}), encoding="utf-8",
        )

        self._assert_refuses_before_drafting("MALFORMED_SOURCE_MARKER")

    def test_write_refuses_evidence_root_ambiguous(self) -> None:
        """U2c's own amendment: `EVIDENCE_ROOT_AMBIGUOUS` is computed
        unconditionally for every root in `Corpus.source_roots`, the same
        corpus assembly the six named codes above reach `write` through --
        never reachable only from the read-only `phases` verb."""
        self._write_bound_section({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
            "document": {"lineage": "lumen-thesis", "section": "1. Intro"},
        })
        proposals = self.test_root / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")
        guidance = self.test_root / "guidance"
        for name in ("evidence-a", "evidence-b"):
            folder = guidance / name
            folder.mkdir(parents=True)
            (folder / ".paper-writing.json").write_text(
                json.dumps({"class": "evidence"}), encoding="utf-8",
            )
            paper = folder / "duplicate-id"
            paper.mkdir()
            (paper / "duplicate-id.md").write_text("# Dataset\n", encoding="utf-8")

        self._assert_refuses_before_drafting("EVIDENCE_ROOT_AMBIGUOUS")

    def test_write_refuses_source_declaration_hand_edited(self) -> None:
        """`specs/source-declaration-authoring/spec.md`, `Requirement:
        Absence Is A Reported State; A Broken Seal Refuses Where The Marker
        Is Read` -- the seal is verified inside `read_revisions_marker`,
        reached here through `write`'s own corpus-assembly gate, never only
        through the read-only `plan`/`phases` verbs (design.md Decision C,
        invariant 4)."""
        self._write_bound_section({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
            "document": {"lineage": "lumen-thesis", "section": "1. Intro"},
        })
        proposals = self.test_root / "proposals"
        proposals.mkdir(parents=True)
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")
        obj = {"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}
        obj[paper_marker.SEAL_KEY] = "a" * 64  # never the real computed seal
        (proposals / ".paper-writing.json").write_text(json.dumps(obj), encoding="utf-8")

        self._assert_refuses_before_drafting("SOURCE_DECLARATION_HAND_EDITED")

    def test_deleting_an_already_declared_marker_still_refuses_undeclared(self) -> None:
        """`source-section-binding` spec, scenario `Deleting the marker
        does not degrade to unmeasured`: a document-rooted root that WAS
        declared and had that declaration deleted refuses
        `SOURCE_REVISIONS_UNDECLARED` again, never a silent `unmeasured`
        report -- reserved for a root that is not document-rooted at all."""
        self._write_bound_section({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
            "document": {"lineage": "lumen-thesis", "section": "1. Intro"},
        })
        proposals = self.test_root / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")
        corpus = paper_graph.assemble_corpus(self.sections_dir)
        self.assertEqual(corpus.source_roots["proposals"]["state"], "document-rooted")

        (proposals / ".paper-writing.json").unlink()

        self._assert_refuses_before_drafting("SOURCE_REVISIONS_UNDECLARED")


class SourceSectionBindingWriteGateScopeTests(unittest.TestCase):
    """U4 correctness repair (gate-fix-design.md, measured 2026-09-21
    against `introduction.block-6`): `SECTION_BINDING_ABSENT` is scoped to
    the block `write` actually names, never the whole corpus. The old
    corpus-wide raise (`_verify_source_section_bindings`, U3) refused
    writing ANY block whenever ANY other block anywhere in the corpus
    carried an undecided binding -- including a block that will never be
    written at all. A block requiring no bindable fact (`skeleton`, a
    `paper_declarations.STRUCTURAL_FACTS` entry -- never a key of
    `FACT_SOURCE_ROOT`) can never invent an answer for one, so it must
    never be gated on an unrelated SIBLING's own undecided binding; a
    block whose OWN bindable fact is unbound must still refuse in full --
    the scope narrows WHICH block can raise, never removes the obligation
    for the block actually being written.
    """

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-binding-scope-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)

        # `a.structural` requires ONLY `skeleton` -- STRUCTURAL, never a
        # key of `FACT_SOURCE_ROOT`, so it can never carry a binding at
        # all and can never appear in `Corpus.undecided_bindings`.
        self._write_section(
            "01-a.md", "a", "structural",
            {
                "value": "skeleton",
                "source": {"file": "sections/01-a.md", "quote": "The skeleton, written here."},
            },
        )
        # `b.bound`, a SIBLING in a DIFFERENT section: its own `formulation`
        # fact is bindable and its root (`proposals`) is measured below,
        # but it carries no `document` half -- exactly the entry the OLD
        # corpus-wide gate would raise `SECTION_BINDING_ABSENT` for on
        # behalf of ANY block written, `a.structural` included.
        self._write_section(
            "02-b.md", "b", "bound",
            {
                "value": "formulation",
                "source": {"file": "sections/02-b.md", "quote": "The formulation, written here."},
            },
        )

        proposals = self.test_root / "proposals"
        proposals.mkdir()
        (proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}),
            encoding="utf-8",
        )
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")

    def _write_section(self, filename: str, section: str, block_id: str, fact_entry: dict) -> None:
        blocks = [{
            "id": block_id, "requires_facts": [fact_entry],
            "requires_declarations": [], "citations": "none",
        }]
        (self.sections_dir / filename).write_text(
            "---\n" + json.dumps({"section": section, "position": 1, "blocks": blocks})
            + "\n---\n\n" + fact_entry["source"]["quote"] + "\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )

    def _args(self, section: str, block: str) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section=section, block=block,
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=None,
        )

    def test_a_block_with_no_bindable_fact_is_not_gated_on_a_siblings_undecided_binding(
        self,
    ) -> None:
        """The regression under repair, reproducing the measured
        `introduction.block-6` defect: `a.structural` requires only
        `skeleton`, which can never carry a binding, so it must proceed
        past the binding gate even though `b.bound`'s own `formulation`
        fact sits measured and unbound in the SAME corpus. `--draft`/
        `--audit` name files that are never created, so the next failure
        past the gate is that bare, downstream open (`FileNotFoundError`)
        or an unrelated `Refused` -- never `SECTION_BINDING_ABSENT`."""
        with self.assertRaises((Refused, FileNotFoundError)) as ctx:
            paper_cli.cmd_write(self._args("a", "structural"))
        if isinstance(ctx.exception, Refused):
            self.assertNotEqual(ctx.exception.code, "SECTION_BINDING_ABSENT")

    def test_a_block_with_its_own_unbound_fact_still_refuses_section_binding_absent(
        self,
    ) -> None:
        """The scope narrows WHICH block can raise, never removes the
        obligation for the block actually being written: `b.bound` names
        its OWN unbound `formulation` fact and must still refuse in full,
        with the detail naming `b.bound` itself."""
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self._args("b", "bound"))
        self.assertEqual(ctx.exception.code, "SECTION_BINDING_ABSENT")
        self.assertIn("b.bound", ctx.exception.detail)
        self.assertIn("formulation", ctx.exception.detail)

    def test_undecided_bindings_still_reports_the_sibling_even_when_the_gate_did_not_raise(
        self,
    ) -> None:
        """`Corpus.undecided_bindings` is a corpus-wide REPORT
        (`_compute_undecided_bindings`, untouched by this repair); scoping
        the RAISE to the block actually being written must never shrink
        it -- `b.bound`'s entry survives even when `enforce_for_block`
        names the unrelated `a.structural` and the gate raises nothing."""
        corpus = paper_graph.assemble_corpus(
            self.sections_dir, paper_dir=self.paper_dir,
            enforce_bindings=True, enforce_for_block="a.structural",
        )  # raises nothing -- "a.structural" carries no undecided entry
        self.assertEqual(
            corpus.undecided_bindings["b.bound"]["formulation"]["state"], "undecided",
        )
        self.assertEqual(corpus.undecided_bindings["b.bound"]["formulation"]["root"], "proposals")

    def test_the_read_time_report_agrees_with_the_real_gate_for_every_block(self) -> None:
        """The whole point of `_write_gate_state`: an operator must be able
        to see, WITHOUT spending a redactor and a contract-auditor run,
        whether `write` will refuse this block. That is only worth anything
        if the report and the gate agree, so this derives BOTH sides from
        the same fixture corpus and compares them block by block -- never a
        hand-listed expectation, which would pass while the two drift.

        `_resolve_write_gate` is the real thing `write` runs. A gate code it
        raises must show up as `state: blocked` carrying that same code; a
        block it lets through must report `clear`. `PHASE_NOT_READY` is
        excluded from the comparison on purpose: it is a wave-ordering
        refusal, not one of the two gates this report covers, and it is
        already the one refusal `phases` has always surfaced itself.
        """
        corpus = paper_graph.assemble_corpus(self.sections_dir, paper_dir=self.paper_dir)
        guidance_dir = self.test_root / "guidance"
        self.assertTrue(corpus.blocks, "fixture corpus parsed no blocks to compare")

        for qualified_id in sorted(corpus.blocks):
            report = paper_cli._write_gate_state(corpus, guidance_dir, qualified_id)
            try:
                paper_cli._resolve_write_gate(self.paper_dir, self.sections_dir, qualified_id)
            except Refused as refusal:
                if refusal.code == "PHASE_NOT_READY":
                    continue
                self.assertEqual(
                    report["state"], "blocked",
                    f"{qualified_id}: the gate raises {refusal.code} but the "
                    f"read-time report calls it clear",
                )
                self.assertIn(
                    refusal.code, [entry["code"] for entry in report["blockers"]],
                    f"{qualified_id}: the gate raises {refusal.code}, absent "
                    f"from the report's own blockers {report['blockers']}",
                )
            else:
                self.assertEqual(
                    report["state"], "clear",
                    f"{qualified_id}: the gate raises nothing but the "
                    f"read-time report calls it {report['blockers']}",
                )

    def test_the_sibling_with_its_own_unbound_fact_is_reported_blocked(self) -> None:
        """The concrete half of the agreement above: `b.bound` carries its
        OWN undecided binding, so the report must name it -- and
        `a.structural`, which can never carry one, must stay clear. Without
        this pair the agreement test above would still pass over a corpus
        where every block happened to fall on the same side."""
        corpus = paper_graph.assemble_corpus(self.sections_dir, paper_dir=self.paper_dir)
        guidance_dir = self.test_root / "guidance"

        blocked = paper_cli._write_gate_state(corpus, guidance_dir, "b.bound")
        self.assertEqual(blocked["state"], "blocked")
        self.assertEqual(
            [entry["code"] for entry in blocked["blockers"]], ["SECTION_BINDING_ABSENT"],
        )
        self.assertIn("formulation", blocked["blockers"][0]["detail"])

        clear = paper_cli._write_gate_state(corpus, guidance_dir, "a.structural")
        self.assertEqual(clear, {"state": "clear", "blockers": []})


class SourceRevisionsUndeclaredByteIdentityTests(unittest.TestCase):
    """`source-section-binding` spec, `Requirement: A Document-Rooted
    Source With No Marker Refuses`, scenario `Both raise sites produce
    byte-identical detail`; design.md Decision H: `_resolve_bind_document`
    (reached through `bind`) and `paper_graph.resolve_section_index`
    (reached through `write`) call the SAME shared builder, so drift
    between them is structural rather than asserted."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-undeclared-byte-identity-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        blocks = [{
            "id": "only", "requires_facts": [{
                "value": "formulation",
                "source": {"file": "sections/a.md", "quote": "The formulation, written here."},
                "document": {"lineage": "lumen-thesis", "section": "1. Intro"},
            }],
            "requires_declarations": [], "citations": "none",
        }]
        (self.sections_dir / "a.md").write_text(
            "---\n" + json.dumps({"section": "a", "position": 1, "blocks": blocks})
            + "\n---\n\nThe formulation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        proposals = self.test_root / "proposals"
        proposals.mkdir()
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")

    def _write_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="a", block="only",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=None,
        )

    def _bind_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            block="a.only", fact="formulation", lineage="lumen-thesis",
            section=["1. Intro"], reopen=False,
        )

    def test_bind_and_write_produce_byte_identical_detail(self) -> None:
        with self.assertRaises(Refused) as write_ctx:
            paper_cli.cmd_write(self._write_args())
        self.assertEqual(write_ctx.exception.code, "SOURCE_REVISIONS_UNDECLARED")

        with self.assertRaises(Refused) as bind_ctx:
            paper_cli.cmd_bind(self._bind_args())
        self.assertEqual(bind_ctx.exception.code, "SOURCE_REVISIONS_UNDECLARED")

        self.assertEqual(write_ctx.exception.detail, bind_ctx.exception.detail)


class SourceRevisionsUndeclaredMutationProofTests(unittest.TestCase):
    def test_mutation_inlining_the_bind_side_literal_breaks_byte_identity(self) -> None:
        """tasks.md 4.7: inlining a literal message at ONE of the two raise
        sites (here, `_resolve_bind_document`) must fail the byte-identity
        test above -- proving the two sites share a builder rather than
        merely a copied string."""
        proc = _run_against_mutant(
            'raise Refused(\n'
            '            "SOURCE_REVISIONS_UNDECLARED",\n'
            '            source_revisions_undeclared_detail(status, root),\n'
            '        )',
            'raise Refused(\n'
            '            "SOURCE_REVISIONS_UNDECLARED",\n'
            '            f"{root.name!r} is document-rooted but carries no marker at all",\n'
            '        )',
            "tests.test_paper_writing.SourceRevisionsUndeclaredByteIdentityTests"
            ".test_bind_and_write_produce_byte_identical_detail",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class BindCliEndToEndTests(unittest.TestCase):
    """`the-requirement-names-the-section-that-feeds-it`, U3e ruling: the
    full worked session a `SECTION_BINDING_ABSENT` refusal exists to
    enable -- `write` refuses, `bind` answers it (never a hand edit to
    `sections/*.md`), `write` reaches the readiness stage. Rooted under
    `FORGE_ROOT/.scratch/`, the same containment
    `SourceSectionBindingWriteGateTests` already requires -- `cmd_bind`
    and `cmd_write` both resolve `--paper`/`--sections` against the real,
    non-injectable `FORGE_ROOT` default."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-bind-cli-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        blocks = [{
            "id": "only",
            "requires_facts": [{
                "value": "formulation",
                "source": {"file": "sections/a.md", "quote": "The formulation, written here."},
            }],
            "requires_declarations": [], "citations": "none",
        }]
        # `cmd_write` resolves a block's own contract file as literally
        # `sections/<section-id>.md` (`section_path = sections_dir /
        # f"{args.section}.md"`) -- unlike `assemble_corpus`'s own `*.md`
        # glob, which is filename-agnostic. Named `a.md` here, matching
        # `args.section="a"`, so this fixture is the first to exercise
        # `cmd_write` past its own binding gate.
        (self.sections_dir / "a.md").write_text(
            "---\n" + json.dumps({"section": "a", "position": 1, "blocks": blocks})
            + "\n---\n\nThe formulation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        proposals = self.test_root / "proposals"
        proposals.mkdir()
        (proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}),
            encoding="utf-8",
        )
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n", encoding="utf-8",
        )

    def _write_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="a", block="only",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=None,
        )

    def _bind_args(self, **overrides) -> argparse.Namespace:
        base = dict(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            block="a.only", fact="formulation",
            lineage="lumen-thesis", section=["3. Something"], reopen=False,
        )
        base.update(overrides)
        return argparse.Namespace(**base)

    def _settle(self, block: str, sections) -> dict:
        """Owner amendment (design.md Decision I): `bind` now demands a
        settled `separate` round before it will record — this fixture's own
        `test_root` IS `bind`'s own `source_base` (`sections_dir.parent`),
        so this settles against the SAME document `cmd_bind` resolves."""
        return _settle_separation_round(
            self.paper_dir, self.test_root, "formulation", "lumen-thesis", block, sections,
        )

    def test_the_full_session_refusal_bind_then_write_succeeds(self) -> None:
        # 1. `write` refuses -- the block's own bindable fact carries no
        #    binding yet.
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self._write_args())
        self.assertEqual(ctx.exception.code, "SECTION_BINDING_ABSENT")

        # 1b. Owner amendment (Decision I): `bind` also refuses until the
        #     whole cut has been argued -- a settled `separate` round
        #     naming this exact (block, fact) with this exact title set.
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_bind(self._bind_args())
        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")
        self._settle("a.only", ["3. Something"])

        # 2. `bind` answers it -- an operator using the skill, never a
        #    hand edit to `sections/a.md`.
        result = paper_cli.cmd_bind(self._bind_args())
        self.assertEqual(result["block"], "a.only")
        self.assertEqual(result["fact"], "formulation")
        self.assertEqual(result["lineage"], "lumen-thesis")

        # 3. `write` no longer refuses `SECTION_BINDING_ABSENT` -- it
        #    proceeds past the binding gate, all the way to trying to open
        #    `--draft` (this fixture names a `draft.json` that is never
        #    created, so the next failure is that bare, downstream open,
        #    never the binding gate).
        with self.assertRaises((Refused, FileNotFoundError)) as ctx:
            paper_cli.cmd_write(self._write_args())
        if isinstance(ctx.exception, Refused):
            self.assertNotEqual(ctx.exception.code, "SECTION_BINDING_ABSENT")

        # `sections/a.md` is never touched by any of this.
        prose = (self.sections_dir / "a.md").read_text(encoding="utf-8")
        self.assertNotIn('"document"', prose)

    def test_bind_refuses_an_empty_section_list(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_bind(self._bind_args(section=[]))
        self.assertEqual(ctx.exception.code, "BINDING_SECTIONS_REQUIRED")

    def test_bind_refuses_a_missing_lineage(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_bind(self._bind_args(lineage=None))
        self.assertEqual(ctx.exception.code, "BINDING_LINEAGE_REQUIRED")

    def test_reopen_then_bind_a_different_section_through_the_cli(self) -> None:
        self._settle("a.only", ["3. Something"])
        paper_cli.cmd_bind(self._bind_args())

        paper_cli.cmd_bind(self._bind_args(reopen=True, lineage=None, section=None))

        # Owner amendment (Decision I): rebinding to a DIFFERENT title set
        # for the SAME (block, fact) needs its OWN settled round naming
        # that exact scope -- the round settling "3. Something" above does
        # not license "1. Intro".
        self._settle("a.only", ["1. Intro"])
        result = paper_cli.cmd_bind(self._bind_args(section=["1. Intro"]))

        self.assertEqual(result["sections"], ["1. Intro"])


class SourceSectionBindingWriteGateMutationProofTests(unittest.TestCase):
    """The load-bearing proof (tasks.md 4.9): wiring the guard only into
    the read-only `phases` verb and leaving `write` unguarded must fail
    both the binding-code family and the marker-code family above.
    `_resolve_write_gate`'s own first statement is `cmd_write`'s ONLY path
    to `paper_graph.assemble_corpus` (`assemble_packet`, called later in
    `cmd_write`, never assembles a corpus at all) -- removing that one
    call reproduces exactly the mutation this task describes: the guard
    stays wired into `phases` (`compute_phases` calls `assemble_corpus`
    independently) while `write` no longer does."""

    def test_mutation_removing_the_gate_call_fails_section_not_in_source(self) -> None:
        proc = _run_against_mutant(
            '    corpus = _resolve_write_gate(paper_dir, sections_dir, qualified_id)\n',
            "",
            "tests.test_paper_writing.SourceSectionBindingWriteGateTests"
            ".test_write_refuses_section_not_in_source",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_removing_the_gate_call_fails_source_revisions_undeclared(self) -> None:
        proc = _run_against_mutant(
            '    corpus = _resolve_write_gate(paper_dir, sections_dir, qualified_id)\n',
            "",
            "tests.test_paper_writing.SourceSectionBindingWriteGateTests"
            ".test_write_refuses_source_revisions_undeclared",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_the_seal_comparison_is_reachable_through_write_not_only_plan(self) -> None:
        """tasks.md 2.19 (the non-negotiable constraint): replacing the
        seal-comparison line inside `read_revisions_marker` with a constant
        `True` MUST be caught by a test driven through `write`, a gating
        verb -- never only through the read-only `plan`. This mutation runs
        against `paper_declarations.py`, not `paper_cli.py`: `write` still
        reaches `read_revisions_marker` unchanged, but the reader itself no
        longer detects the mismatch."""
        proc = _run_against_mutant(
            "        if recorded != computed:",
            "        if False:",
            "tests.test_paper_writing.SourceSectionBindingWriteGateTests"
            ".test_write_refuses_source_declaration_hand_edited",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_removing_the_gate_call_fails_section_binding_absent(self) -> None:
        proc = _run_against_mutant(
            '    corpus = _resolve_write_gate(paper_dir, sections_dir, qualified_id)\n',
            "",
            "tests.test_paper_writing.SourceSectionBindingWriteGateTests"
            ".test_write_refuses_section_binding_absent",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_reverting_the_refusal_detail_to_bare_fails_the_candidates_test(self) -> None:
        """U3e ruling: "the refusal IS the question" -- reverting
        `SECTION_BINDING_ABSENT`'s own detail to the bare U3 message
        (naming only the block, fact and root, none of the candidates
        `_describe_binding_absent` derives from disk) must fail
        `test_section_binding_absent_names_the_block_fact_root_and_
        candidates`, proving that test load-bearing on the improved
        message, not merely on the refusal code."""
        proc = _run_against_mutant(
            '                    _describe_binding_absent(corpus, enforce_for_block, fact_id, info),\n'
            '                )',
            "                    f\"{enforce_for_block}: {fact_id!r} is bindable and its source \"\n"
            "                    f\"root {info['root']!r} is measured, but carries no 'document' \"\n"
            "                    \"binding\",\n"
            "                )",
            "tests.test_paper_writing.SourceSectionBindingWriteGateTests"
            ".test_section_binding_absent_names_the_block_fact_root_and_candidates",
            source_path=SKILL_SCRIPTS / "paper_graph.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class ReadinessPhasesReadOnlyTests(unittest.TestCase):
    """tasks.md 6.14: `phases` and `readiness` write nothing under every
    input, including every refusal path -- the same before/after content
    manifest `ReadOnlyTests.test_content_manifest_unchanged_by_a_real_
    verify_run` already established for `verify`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()
        header = json.dumps({
            "section": "ro", "position": 1,
            "blocks": [
                {
                    "id": "a",
                    "requires_facts": [
                        {
                            "value": "formulation",
                            "source": {
                                "file": "sections/01-ro.md",
                                "quote": "This block requires the formulation.",
                            },
                        }
                    ],
                    "requires_declarations": [], "citations": "none",
                },
            ],
        })
        (self.sections_dir / "01-ro.md").write_text(
            f"---\n{header}\n---\n\nProse. This block requires the formulation."
            "\n\n### External inputs\n\nNone.\n\n"
            "### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )

    def _manifest(self) -> dict:
        return {
            str(path.relative_to(self.paper_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.paper_dir.rglob("*")) if path.is_file()
        }

    def test_readiness_writes_nothing_including_when_it_refuses(self) -> None:
        paper_declarations.set_fact(self.paper_dir, "formulation", "x")
        before = self._manifest()

        paper_cli.compute_readiness_report(self.sections_dir, paper_dir=self.paper_dir)
        with self.assertRaises(Refused):
            paper_cli.compute_readiness_report(self.sections_dir)  # READINESS_BASIS_REQUIRED

        after = self._manifest()
        self.assertEqual(before, after)

    def test_phases_writes_nothing_including_when_it_refuses(self) -> None:
        paper_declarations.set_fact(self.paper_dir, "formulation", "x")
        before = self._manifest()

        paper_cli.compute_phases(self.paper_dir, self.sections_dir)
        with self.assertRaises(Refused):
            # One wave only ("ro.a"), unopened -- phase=2 demands wave 1
            # complete before a (non-existent) wave 2, so this refuses
            # PHASE_NOT_READY without writing anything either.
            paper_cli.compute_phases(self.paper_dir, self.sections_dir, phase=2)

        after = self._manifest()
        self.assertEqual(before, after)

    def test_mutation_a_write_inside_compute_phases_fails_the_manifest_guard(self) -> None:
        proc = _run_against_mutant(
            # Anchored on `compute_phases`'s first two BODY statements, not
            # on its `def` line and not on its docstring. The `def` line was
            # the original anchor and silently unmatched the day the
            # signature went multi-line to take `guidance_dir`; anchoring on
            # the docstring opener instead injects the write INSIDE the
            # docstring, where it is a string literal that never runs and
            # the mutation passes green. The first body statement alone is
            # not unique in this file (a sibling assembles the same corpus
            # at a deeper indent), so the `edge_set` line disambiguates.
            "    corpus = paper_graph.assemble_corpus(sections_dir, paper_dir=paper_dir)\n"
            "    edge_set = paper_graph.collect_edges(corpus)",
            "    tex = paper_dir / 'main.tex'\n"
            "    tex.write_bytes(tex.read_bytes() + b'x')\n"
            "    corpus = paper_graph.assemble_corpus(sections_dir, paper_dir=paper_dir)\n"
            "    edge_set = paper_graph.collect_edges(corpus)",
            "tests.test_paper_writing.ReadinessPhasesReadOnlyTests"
            ".test_phases_writes_nothing_including_when_it_refuses",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


def _write_skeleton_corpus(sections_dir: Path) -> None:
    """`the-phases-are-derived-not-remembered`, unit 7 (tasks.md 7.8-7.14):
    a real, normalized four-section corpus naming both dataset blocks
    (`paper_declarations.MM_DATASET_ID`/`ES_DATASET_ID`, literal) and one
    related-work block, no `after` edges -- `derive_order` over this corpus
    is therefore pure `(position, block_index, qualified_id)`:
    `materials-and-methods.mm-preamble`, `materials-and-methods.mm-dataset`,
    `experimental-setup.es-dataset`, `related-work.rw-a`, `conclusions.c-a`.
    """
    (sections_dir / "01-materials-and-methods.md").write_text(
        "---\n" + json.dumps({
            "section": "materials-and-methods", "position": 1,
            "blocks": [
                {
                    "id": "mm-preamble", "requires_facts": [], "requires_declarations": [],
                    "citations": "none",
                },
                {
                    "id": "mm-dataset", "requires_facts": [
                        {
                            "value": "dataset",
                            "source": {
                                "file": "sections/01-materials-and-methods.md",
                                "quote": "The dataset enters through this block.",
                            },
                        },
                    ], "requires_declarations": [],
                    "citations": "none", "optional": True,
                },
            ],
        })
        + "\n---\n\nProse. The dataset enters through this block."
        "\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        encoding="utf-8",
    )
    (sections_dir / "02-experimental-setup.md").write_text(
        "---\n" + json.dumps({
            "section": "experimental-setup", "position": 2,
            "blocks": [
                {
                    "id": "es-dataset", "requires_facts": [
                        {
                            "value": "dataset",
                            "source": {
                                "file": "sections/02-experimental-setup.md",
                                "quote": "The dataset enters through this block.",
                            },
                        },
                    ], "requires_declarations": [],
                    "citations": "none", "optional": True,
                },
            ],
        })
        + "\n---\n\nProse. The dataset enters through this block."
        "\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        encoding="utf-8",
    )
    (sections_dir / "03-related-work.md").write_text(
        "---\n" + json.dumps({
            "section": "related-work", "position": 3,
            "blocks": [
                {
                    "id": "rw-a", "requires_facts": [], "requires_declarations": [],
                    "citations": "none", "optional": True,
                },
            ],
        })
        + "\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        encoding="utf-8",
    )
    (sections_dir / "04-conclusions.md").write_text(
        "---\n" + json.dumps({
            "section": "conclusions", "position": 4,
            "blocks": [
                {"id": "c-a", "requires_facts": [], "requires_declarations": [], "citations": "none"},
            ],
        })
        + "\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
        encoding="utf-8",
    )


class SkeletonTests(unittest.TestCase):
    """`specs/skeleton-startup/spec.md`; design.md D4 (tasks.md 7.8-7.12)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()
        _write_skeleton_corpus(self.sections_dir)

    def _build(self, *, related_work=None, dataset_in=None) -> dict:
        return paper_cli.build_skeleton(
            self.paper_dir, self.sections_dir, related_work=related_work, dataset_in=dataset_in,
        )

    def _opened_ids(self) -> set:
        return {block["id"] for block in paper_block.read_status(self.paper_dir)["blocks"]}

    def test_fresh_paper_opens_the_chosen_dataset_block_and_leaves_the_other_unopened(self) -> None:
        """tasks.md 7.9; `specs/skeleton-startup/spec.md`, `Scenario: The
        skeleton opens the chosen dataset block only`."""
        result = self._build(related_work="yes", dataset_in="experimental-setup")

        opened = self._opened_ids()
        self.assertIn("experimental-setup.es-dataset", opened)
        self.assertNotIn("materials-and-methods.mm-dataset", opened)
        self.assertIn("related-work.rw-a", opened)
        self.assertIn("materials-and-methods.mm-preamble", opened)
        self.assertIn("conclusions.c-a", opened)
        self.assertEqual(result["datasetPlacement"], "experimental-setup")
        self.assertTrue(result["relatedWork"])

    def test_related_work_no_leaves_every_rw_block_unopened(self) -> None:
        result = self._build(related_work="no", dataset_in="materials")

        opened = self._opened_ids()
        self.assertNotIn("related-work.rw-a", opened)
        self.assertIn("materials-and-methods.mm-dataset", opened)
        self.assertNotIn("experimental-setup.es-dataset", opened)
        self.assertFalse(result["relatedWork"])
        self.assertEqual(result["datasetPlacement"], "materials-and-methods")

    def test_an_existing_skeleton_is_never_re_asked_and_is_idempotent(self) -> None:
        """tasks.md 7.10: a fresh call with the SAME answers, once the
        skeleton already exists, opens nothing new."""
        self._build(related_work="yes", dataset_in="experimental-setup")
        before = self._opened_ids()

        result = self._build(related_work="yes", dataset_in="experimental-setup")

        self.assertEqual(result["opened"], [])
        self.assertEqual(self._opened_ids(), before)

    def test_dataset_flag_contradicting_disk_state_refuses_skeleton_already_decided(self) -> None:
        """tasks.md 7.11."""
        self._build(related_work="yes", dataset_in="experimental-setup")

        with self.assertRaises(Refused) as ctx:
            self._build(related_work="yes", dataset_in="materials")

        self.assertEqual(ctx.exception.code, "SKELETON_ALREADY_DECIDED")
        self.assertIn("experimental-setup", ctx.exception.detail)
        self.assertIn("materials-and-methods", ctx.exception.detail)

    def test_related_work_flag_contradicting_disk_state_refuses_skeleton_already_decided(self) -> None:
        """tasks.md 7.11, the other decision."""
        self._build(related_work="yes", dataset_in="experimental-setup")

        with self.assertRaises(Refused) as ctx:
            self._build(related_work="no", dataset_in="experimental-setup")

        self.assertEqual(ctx.exception.code, "SKELETON_ALREADY_DECIDED")

    def test_a_missing_dataset_flag_refuses_skeleton_answer_required(self) -> None:
        """tasks.md 7.12."""
        with self.assertRaises(Refused) as ctx:
            self._build(related_work="yes", dataset_in=None)

        self.assertEqual(ctx.exception.code, "SKELETON_ANSWER_REQUIRED")
        self.assertIn("--dataset-in", ctx.exception.detail)
        self.assertEqual(self._opened_ids(), set())

    def test_a_missing_related_work_flag_refuses_skeleton_answer_required(self) -> None:
        """tasks.md 7.12, the other flag."""
        with self.assertRaises(Refused) as ctx:
            self._build(related_work=None, dataset_in="materials")

        self.assertEqual(ctx.exception.code, "SKELETON_ANSWER_REQUIRED")
        self.assertIn("--related-work", ctx.exception.detail)


class SkeletonWriteAmplificationTests(unittest.TestCase):
    """Threat Matrix, `Write amplification into main.tex`: only `skeleton`
    writes, only through `paper_block.open_block` (design.md; tasks.md
    7.13). Proven by reproducing `cmd_skeleton`'s own output independently
    -- replaying `open_block` alone, in the identical `derive_order` order,
    against a second, freshly scaffolded `paper_dir` -- so a mutation that
    writes even one byte directly to `main.tex`, bypassing `open_block`,
    diverges from that independent replay."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()
        _write_skeleton_corpus(self.sections_dir)

    def _run_skeleton(self, forge_root: Path) -> Path:
        paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=forge_root)
        paper_scaffold.scaffold(paper_dir)
        paper_cli.build_skeleton(
            paper_dir, self.sections_dir, related_work="yes", dataset_in="experimental-setup",
        )
        return paper_dir

    def test_skeleton_output_matches_replaying_open_block_alone(self) -> None:
        produced_root = Path(self._tmp.name) / "produced"
        produced_root.mkdir()
        produced_dir = self._run_skeleton(produced_root)
        produced_bytes = paper_block.resolve_main_tex(produced_dir).read_bytes()

        replay_root = Path(self._tmp.name) / "replay"
        replay_root.mkdir()
        replay_dir = paper_scaffold.resolve_paper_dir(None, forge_root=replay_root)
        paper_scaffold.scaffold(replay_dir)
        corpus = paper_graph.assemble_corpus(self.sections_dir)
        edge_set = paper_graph.collect_edges(corpus)
        order = paper_graph.derive_order(corpus, edge_set)
        for qualified_id in order:
            if qualified_id == "materials-and-methods.mm-dataset":
                continue
            paper_block.open_block(replay_dir, qualified_id, at_end=True)
        expected_bytes = paper_block.resolve_main_tex(replay_dir).read_bytes()

        self.assertEqual(produced_bytes, expected_bytes)

    def test_mutation_writing_a_raw_byte_directly_fails_the_replay_check(self) -> None:
        proc = _run_against_mutant(
            '    return {\n'
            '        "relatedWork": related_work_flag,\n'
            '        "datasetPlacement": requested_placement,\n'
            '        "opened": opened,\n'
            '    }',
            '    tex_path = paper_block.resolve_main_tex(paper_dir)\n'
            '    tex_path.write_bytes(tex_path.read_bytes() + b"\\n%% extra\\n")\n'
            '    return {\n'
            '        "relatedWork": related_work_flag,\n'
            '        "datasetPlacement": requested_placement,\n'
            '        "opened": opened,\n'
            '    }',
            "tests.test_paper_writing.SkeletonWriteAmplificationTests"
            ".test_skeleton_output_matches_replaying_open_block_alone",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class SkeletonPathContainmentTests(unittest.TestCase):
    """Threat Matrix, `Path containment`: `skeleton` reuses `paper_
    scaffold.resolve_paper_dir` / `paper_contract.resolve_sections_dir`
    verbatim -- never a new containment check (design.md; tasks.md 7.14).
    Runs under the real, non-injectable `FORGE_ROOT` default, the same
    `.scratch/` convention `WriteGateTests` uses, because `cmd_
    skeleton` resolves both `--paper`/`--sections` through it."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-skeleton-containment-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        _write_skeleton_corpus(self.sections_dir)

    def _manifest(self) -> dict:
        return {
            str(path.relative_to(self.paper_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.paper_dir.rglob("*")) if path.is_file()
        }

    def test_paper_outside_repository_refuses_and_writes_nothing(self) -> None:
        before = self._manifest()
        outside = Path(tempfile.gettempdir()) / f"paper-writing-skeleton-outside-{os.getpid()}"
        args = argparse.Namespace(
            paper=str(outside), sections=str(self.sections_dir),
            related_work="yes", dataset_in="materials",
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_skeleton(args)

        self.assertEqual(ctx.exception.code, "PAPER_OUTSIDE_REPOSITORY")
        self.assertFalse(outside.exists())
        self.assertEqual(self._manifest(), before)

    def test_sections_outside_repository_refuses_and_writes_nothing(self) -> None:
        before = self._manifest()
        outside = Path(tempfile.gettempdir()) / f"paper-writing-skeleton-outside-sections-{os.getpid()}"
        args = argparse.Namespace(
            paper=str(self.paper_dir), sections=str(outside),
            related_work="yes", dataset_in="materials",
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_skeleton(args)

        self.assertEqual(ctx.exception.code, "SECTIONS_OUTSIDE_REPOSITORY")
        self.assertFalse(outside.exists())
        self.assertEqual(self._manifest(), before)


def _write_guidance_style_reference(guidance_dir: Path, root: str, papers: dict) -> None:
    """Test fixture (unit 8): classifies `guidance_dir/<root>` `style-
    reference` and ingests one `.md` per `{folder: body}` entry in
    `papers`, two levels deep -- exactly the shape `paper_guidance.
    ingested_papers` walks (design.md D4/D5)."""
    root_dir = guidance_dir / root
    root_dir.mkdir(parents=True, exist_ok=True)
    (root_dir / ".paper-writing.json").write_text(
        json.dumps({"class": "style-reference"}), encoding="utf-8",
    )
    for folder, body in papers.items():
        paper_dir = root_dir / folder
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / f"{folder}.md").write_text(body, encoding="utf-8")


def _write_packet_section(sections_dir: Path, stem: str, section: str, block_id: str, prose: str) -> None:
    """Test fixture (unit 8): the smallest `sections/<stem>.md` contract
    `paper_contract.parse` accepts, carrying one block -- a mode-less
    block never enters `assemble_packet`'s own transposition-mode branch
    (`the-redactor-receives-the-section-it-must-transpose`, design.md D5),
    so `paper_graph.assemble_corpus` is never called for it and no
    `### External inputs`/`### Internal chain` sections are required here."""
    header = json.dumps({
        "section": section, "position": 1,
        "blocks": [
            {"id": block_id, "requires_facts": [], "requires_declarations": [], "citations": "none"},
        ],
    })
    (sections_dir / f"{stem}.md").write_text(f"---\n{header}\n---\n\n{prose}\n", encoding="utf-8")


#: Reused across every fixture in this section that needs `paper_contract.
#: parse`'s own `mode.source.quote` transcription check to hold verbatim
#: (`the-redactor-receives-the-section-it-must-transpose`, design.md).
_TRANSPOSITION_QUOTE = (
    "This synthetic fixture block restates its own formulation for testing purposes only."
)


def _write_transposition_section(
    sections_dir: Path, stem: str, section: str, block_id: str,
    *, mode: str | None = "transposition", document: dict | None = None, with_fact: bool = True,
) -> None:
    """Test fixture (`the-redactor-receives-the-section-it-must-transpose`,
    design.md D1/D2/D5): a `sections/<stem>.md` contract carrying one
    block whose own `requires_facts` entry names the synthetic
    `formulation` fact, optionally bound to a `document` triple --
    `mode=None` omits the header's own `mode` key entirely (`paper_
    contract.resolve_mode` then reports `None`). Carries the full
    `## Disqualifiers` / `### External inputs` / `### Internal chain`
    partition every real `assemble_corpus`/`write_block` call needs, so
    the SAME fixture serves a bare `assemble_packet` call (Phase 0/1/4)
    and a full `cmd_write` pipeline run (Phase 3/5) alike."""
    header: dict = {
        "section": section, "position": 1,
        "blocks": [{
            "id": block_id, "requires_facts": [], "requires_declarations": [], "citations": "none",
        }],
    }
    if with_fact:
        fact_entry = {
            "value": "formulation", "source": {"file": f"sections/{stem}.md", "quote": _TRANSPOSITION_QUOTE},
        }
        if document is not None:
            fact_entry["document"] = document
        header["blocks"][0]["requires_facts"] = [fact_entry]
    if mode is not None:
        header["mode"] = {"value": mode, "source": {"file": f"sections/{stem}.md", "quote": _TRANSPOSITION_QUOTE}}
    body = (
        f"{_TRANSPOSITION_QUOTE}\n\n"
        "## Disqualifiers\n\n- A symbol used without being declared.\n\n"
        "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
    )
    (sections_dir / f"{stem}.md").write_text(
        "---\n" + json.dumps(header) + "\n---\n\n" + body, encoding="utf-8",
    )


class SegmentMarkdownTests(unittest.TestCase):
    """`paper_guidance.segment_markdown`/`read_markdown_outline` (tasks.md
    8.2-8.5; `redactor-packet` spec, design.md Decision D5)."""

    def test_no_headings_reports_the_reason_not_a_silent_empty_list(self) -> None:
        result = paper_guidance.segment_markdown("Just a paragraph, no heading anywhere.\n")
        self.assertEqual(result, {"headings": [], "reason": "NO_HEADINGS"})

    def test_a_deeper_level_appendix_is_not_swallowed_by_its_shallower_predecessor(self) -> None:
        """tasks.md 8.3, RED-first: `## Section Two` is followed by `#
        Appendix` (SHALLOWER, level 1), which itself nests `### Appendix
        Detail` (DEEPER, level 3) as the document's own LAST heading. A
        same-level-only rule finds no further level-2 heading after
        `Section Two` and extends its span all the way to EOF, swallowing
        both the Appendix and its own nested Detail; the fixed `level <=
        own` rule stops `Section Two` exactly where `# Appendix` begins.
        `SegmentMarkdownMutationProofTests` below re-introduces the
        same-level-only rule and confirms this exact assertion goes red
        without the fix -- this is not merely a one-time dev-loop RED,
        it is design.md's own mutation 8, permanently re-run."""
        body = (
            "## Section Two\n"
            "content of section 2\n"
            "# Appendix\n"
            "appendix intro\n"
            "### Appendix Detail\n"
            "detail content to end of file\n"
        )
        result = paper_guidance.segment_markdown(body)
        by_title = {heading["title"]: heading for heading in result["headings"]}
        data = body.encode("utf-8")

        self.assertEqual(set(by_title), {"Section Two", "Appendix", "Appendix Detail"})
        appendix_start = by_title["Appendix"]["byte_start"]
        self.assertEqual(by_title["Section Two"]["byte_end"], appendix_start)
        section_two_slice = data[by_title["Section Two"]["byte_start"]:by_title["Section Two"]["byte_end"]]
        self.assertNotIn(b"Appendix", section_two_slice)
        # The deepest, last heading in the whole document always ends at EOF.
        self.assertEqual(by_title["Appendix Detail"]["byte_end"], len(data))

    def test_unreadable_markdown_refuses_guidance_markdown_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "bad.md"
            bad_path.write_bytes(b"\xff\xfe# Not valid UTF-8\n")
            with self.assertRaises(Refused) as ctx:
                paper_guidance.read_markdown_outline(bad_path)
            self.assertEqual(ctx.exception.code, "GUIDANCE_MARKDOWN_UNREADABLE")


class SegmentMarkdownMutationProofTests(unittest.TestCase):
    """tasks.md 8.3; design.md mutation 8: `segment_markdown` ending a
    section at the next SAME-level heading (rather than `level <= own`)
    must fail `SegmentMarkdownTests.test_a_deeper_level_appendix_is_not_
    swallowed_by_its_shallower_predecessor` -- a passing assertion beside
    an unexercised rule is not a mutation that ran."""

    def test_mutation_same_level_only_fails_the_appendix_guard(self) -> None:
        proc = _run_against_mutant(
            'if later["level"] <= heading["level"]:',
            'if later["level"] == heading["level"]:',
            "tests.test_paper_writing.SegmentMarkdownTests"
            ".test_a_deeper_level_appendix_is_not_swallowed_by_its_shallower_predecessor",
            source_path=SKILL_SCRIPTS / "paper_guidance.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class PacketAssemblyTests(unittest.TestCase):
    """`paper_cli.assemble_packet`/`cmd_packet` (tasks.md 8.6; `redactor-
    packet` spec, `Requirement: The Packet Carries Contract Prose Plus
    Same-Section Style Extracts`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.sections_dir = self.tmp_path / "sections"
        self.sections_dir.mkdir()
        self.guidance_dir = self.tmp_path / "guidance"
        _write_packet_section(self.sections_dir, "01-intro", "intro", "a", "Our own contract prose.")

    def test_packet_assembles_contract_prose_and_reference_outlines(self) -> None:
        _write_guidance_style_reference(self.guidance_dir, "reference-papers", {
            "paper-one": "# Introduction\n\nReference sentence one.\n\n## Methods\n\nReference sentence two.\n",
            "paper-two": "# Overview\n\nA different reference paper's own sentence.\n",
        })

        packet = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")

        self.assertEqual(packet["block"], "a")
        self.assertEqual(packet["section"], "intro")
        self.assertIn("Our own contract prose.", packet["contract"])
        self.assertEqual({ref["folder"] for ref in packet["references"]}, {"paper-one", "paper-two"})
        for ref in packet["references"]:
            self.assertEqual(ref["root"], "reference-papers")
            self.assertIn("headings", ref)
            self.assertNotIn("span", ref)
            self.assertNotIn("text", ref)
            for heading in ref["headings"]:
                self.assertEqual(set(heading), {"title", "level", "byte_start", "byte_end"})

    def test_a_non_style_reference_root_contributes_nothing(self) -> None:
        _write_guidance_style_reference(self.guidance_dir, "evidence-root", {"paper-one": "# X\n\nBody.\n"})
        (self.guidance_dir / "evidence-root" / ".paper-writing.json").write_text(
            json.dumps({"class": "evidence"}), encoding="utf-8",
        )

        packet = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")

        self.assertEqual(packet["references"], [])

    def test_an_unclassified_root_contributes_nothing_either(self) -> None:
        (self.guidance_dir / "unclassified-root" / "paper-one").mkdir(parents=True)
        (self.guidance_dir / "unclassified-root" / "paper-one" / "paper-one.md").write_text(
            "# X\n\nBody.\n", encoding="utf-8",
        )

        packet = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")

        self.assertEqual(packet["references"], [])

    def test_a_headingless_reference_reports_no_headings_reason(self) -> None:
        _write_guidance_style_reference(self.guidance_dir, "reference-papers", {
            "paper-one": "Just a paragraph, no heading anywhere.\n",
        })

        packet = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")

        self.assertEqual(len(packet["references"]), 1)
        self.assertEqual(packet["references"][0]["headings"], [])
        self.assertEqual(packet["references"][0]["reason"], "NO_HEADINGS")

    def test_an_unreadable_ingested_paper_refuses_guidance_markdown_unreadable(self) -> None:
        _write_guidance_style_reference(self.guidance_dir, "reference-papers", {"paper-one": "# X\n\nBody.\n"})
        bad_md = self.guidance_dir / "reference-papers" / "paper-one" / "paper-one.md"
        bad_md.write_bytes(b"\xff\xfe# Not valid UTF-8\n")

        with self.assertRaises(Refused) as ctx:
            paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")

        self.assertEqual(ctx.exception.code, "GUIDANCE_MARKDOWN_UNREADABLE")


class PacketLeakGuardTests(unittest.TestCase):
    """tasks.md 8.7; design.md mutation 7: the packet is structurally
    incapable of carrying reference prose -- proved by mutation, not
    merely asserted (design.md, D5: "Rejected alternative -- the packet
    inlines each extracted section's text -- puts an unaudited copy of
    reference prose in a file the redactor can read without ever passing
    residency verification or the eight-token tripwire")."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.sections_dir = self.tmp_path / "sections"
        self.sections_dir.mkdir()
        self.guidance_dir = self.tmp_path / "guidance"
        _write_packet_section(self.sections_dir, "01-intro", "intro", "a", "Our own contract prose.")
        _write_guidance_style_reference(self.guidance_dir, "reference-papers", {
            "paper-one": "# Introduction\n\nA reference sentence naming a specific unpublished finding.\n",
        })

    def test_no_reference_byte_in_the_payload(self) -> None:
        packet = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")
        payload = json.dumps(packet)
        self.assertNotIn("unpublished finding", payload)
        self.assertNotIn("A reference sentence", payload)

    def test_mutation_inlining_span_text_fails_the_no_reference_byte_guard(self) -> None:
        proc = _run_against_mutant(
            '            references.append({\n'
            '                "root": root,\n'
            '                "folder": paper["folder"],\n'
            '                "markdown": paper["markdown"],\n'
            '                **outline,\n'
            '            })\n',
            '            leaked = Path(paper["markdown"]).read_text(encoding="utf-8")\n'
            '            references.append({\n'
            '                "root": root,\n'
            '                "folder": paper["folder"],\n'
            '                "markdown": paper["markdown"],\n'
            '                "excerpt": leaked,\n'
            '                **outline,\n'
            '            })\n',
            "tests.test_paper_writing.PacketLeakGuardTests.test_no_reference_byte_in_the_payload",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class PacketStyleResolutionIntegrationTests(unittest.TestCase):
    """tasks.md 8.8-8.11: packet's outline feeds the (simulated) style-
    sampler, whose account is resolved through the EXISTING `paper_style.
    resolve_style_set` call path -- no second resolution path (design.md,
    D5's own diagram: packet -> style-sampler -> resolve_style_set -> R ->
    write -> check_tripwire)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.sections_dir = self.tmp_path / "sections"
        self.sections_dir.mkdir()
        self.guidance_dir = self.tmp_path / "guidance"
        _write_packet_section(self.sections_dir, "01-intro", "intro", "a", "Our own contract prose.")

    def test_two_reference_packet_resolves_into_r_exactly(self) -> None:
        """tasks.md 8.10: `R` read back after assembly contains exactly
        the two extracts a two-reference packet resolved."""
        _write_guidance_style_reference(self.guidance_dir, "root-a", {
            "paper-a": "# Intro\n\nSentence one from paper A, whole and unexcerpted.\n",
        })
        _write_guidance_style_reference(self.guidance_dir, "root-b", {
            "paper-b": "# Intro\n\nSentence two from paper B, whole and unexcerpted.\n",
        })

        packet = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")
        self.assertEqual({ref["root"] for ref in packet["references"]}, {"root-a", "root-b"})

        # The (simulated) style-sampler reads the outline above, resolves
        # the equivalent heading itself, and reports the span verbatim.
        proposals = [
            {
                "reference": "root-a",
                "source_md": str(self.guidance_dir / "root-a" / "paper-a" / "paper-a.md"),
                "span": "Sentence one from paper A, whole and unexcerpted.",
            },
            {
                "reference": "root-b",
                "source_md": str(self.guidance_dir / "root-b" / "paper-b" / "paper-b.md"),
                "span": "Sentence two from paper B, whole and unexcerpted.",
            },
        ]
        recorded, no_equivalent = paper_style.resolve_style_set(self.guidance_dir, proposals)

        self.assertEqual(no_equivalent, [])
        self.assertEqual({entry["reference"] for entry in recorded}, {"root-a", "root-b"})
        self.assertEqual(
            {entry["span"] for entry in recorded},
            {
                "Sentence one from paper A, whole and unexcerpted.",
                "Sentence two from paper B, whole and unexcerpted.",
            },
        )

    def test_a_no_equivalent_entry_contributes_nothing_and_does_not_refuse(self) -> None:
        """tasks.md 8.8: a `noEquivalent` style-reference entry contributes
        nothing; assembly (of `R`) does not refuse on its account."""
        _write_guidance_style_reference(self.guidance_dir, "root-a", {
            "paper-a": "# Intro\n\nSentence from paper A.\n",
        })
        _write_guidance_style_reference(self.guidance_dir, "root-b", {
            "paper-b": "# Intro\n\nSentence from paper B.\n",
        })

        packet = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")
        self.assertEqual({ref["root"] for ref in packet["references"]}, {"root-a", "root-b"})

        proposals = [
            {"reference": "root-a", "noEquivalent": True},
            {
                "reference": "root-b",
                "source_md": str(self.guidance_dir / "root-b" / "paper-b" / "paper-b.md"),
                "span": "Sentence from paper B.",
            },
        ]
        recorded, no_equivalent = paper_style.resolve_style_set(self.guidance_dir, proposals)

        self.assertEqual(no_equivalent, ["root-a"])
        self.assertEqual([entry["reference"] for entry in recorded], ["root-b"])

    def test_leak_tripwire_runs_clean_against_packet_informed_r(self) -> None:
        """tasks.md 8.11: the existing `STYLE_OVERLAP` tripwire runs against
        a packet's own extracts, using exactly `R`; confirm no violation
        attributable to material outside `R`."""
        _write_guidance_style_reference(self.guidance_dir, "root-a", {
            "paper-a": "# Intro\n\nA reference sentence with its own distinct register and words.\n",
        })
        paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")
        proposals = [{
            "reference": "root-a",
            "source_md": str(self.guidance_dir / "root-a" / "paper-a" / "paper-a.md"),
            "span": "A reference sentence with its own distinct register and words.",
        }]
        recorded, _no_equivalent = paper_style.resolve_style_set(self.guidance_dir, proposals)

        styled_draft = "A completely unrelated styled sentence about our own results."
        paper_leak.check_tripwire(styled_draft, recorded)  # must not raise

    def test_leak_tripwire_refuses_material_lifted_from_r(self) -> None:
        """The complementary half: a styled draft that lifts at least
        eight normalized tokens verbatim from a recorded sample refuses
        `STYLE_OVERLAP` -- confirming the tripwire is actually wired
        against `R`, not vacuously passing."""
        _write_guidance_style_reference(self.guidance_dir, "root-a", {
            "paper-a": "# Intro\n\nEight distinct normalized tokens appear verbatim right here today.\n",
        })
        proposals = [{
            "reference": "root-a",
            "source_md": str(self.guidance_dir / "root-a" / "paper-a" / "paper-a.md"),
            "span": "Eight distinct normalized tokens appear verbatim right here today.",
        }]
        recorded, _no_equivalent = paper_style.resolve_style_set(self.guidance_dir, proposals)

        styled_draft = "Eight distinct normalized tokens appear verbatim right here today."
        with self.assertRaises(Refused) as ctx:
            paper_leak.check_tripwire(styled_draft, recorded)
        self.assertEqual(ctx.exception.code, "STYLE_OVERLAP")


class PacketWriteGateTests(unittest.TestCase):
    """`writing-orchestration` spec, `Requirement: Packet Assembly
    Precedes Draft` (tasks.md 8.12): `cmd_write` assembles this block's
    packet before `--draft`/`--audit` are ever opened -- a broken style-
    reference guidance corpus is caught here, before any judge-cycle
    attempt is spent, rather than surfacing only later inside `resolve_
    style_set`. Runs under the real, non-injectable `FORGE_ROOT` default,
    the same `.scratch/` convention `WriteGateTests` uses."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-packet-write-gate-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        blocks_a = [
            {"id": "a", "requires_facts": [], "requires_declarations": [], "citations": "none"},
        ]
        (self.sections_dir / "01-a.md").write_text(
            "---\n" + json.dumps({"section": "phase-a", "position": 1, "blocks": blocks_a})
            + "\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        self.guidance_dir = self.test_root / "guidance"
        _write_guidance_style_reference(self.guidance_dir, "reference-papers", {"paper-one": "# X\n\nBody.\n"})

        self.args = argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="phase-a", block="a",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=str(self.guidance_dir), transcript=None, grounding=None,
        )

    def test_an_unreadable_style_reference_paper_refuses_before_draft_is_opened(self) -> None:
        bad_md = self.guidance_dir / "reference-papers" / "paper-one" / "paper-one.md"
        bad_md.write_bytes(b"\xff\xfe# Not valid UTF-8\n")

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self.args)

        self.assertEqual(ctx.exception.code, "GUIDANCE_MARKDOWN_UNREADABLE")
        self.assertFalse((self.test_root / "draft.json").exists())
        self.assertFalse((self.test_root / "audit.json").exists())

    def test_a_readable_corpus_proceeds_past_the_packet_gate(self) -> None:
        """A packet that assembles cleanly is not itself the failure --
        `cmd_write` proceeds past the gate and fails on the very next real
        stage instead, the draft file this test deliberately never
        creates, never `Refused('GUIDANCE_MARKDOWN_UNREADABLE')`."""
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self.args)
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")


class PacketWriteGateMutationProofTests(unittest.TestCase):
    """tasks.md 8.12: the packet gate must be load-bearing on the real
    write path, not merely present beside it. Removing `cmd_write`'s own
    call to `assemble_packet` must fail `PacketWriteGateTests.test_an_
    unreadable_style_reference_paper_refuses_before_draft_is_opened` -- a
    passing test beside an unexercised guard is not a mutation that ran.
    """

    def test_mutation_removing_the_packet_assembly_call_fails_the_gate(self) -> None:
        proc = _run_against_mutant(
            "    assemble_packet(\n"
            "        sections_dir, guidance_dir, args.section, args.block, corpus=corpus, paper_dir=paper_dir,\n"
            "    )\n",
            "",
            "tests.test_paper_writing.PacketWriteGateTests"
            ".test_an_unreadable_style_reference_paper_refuses_before_draft_is_opened",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


# =====================================================================
# the-redactor-receives-the-section-it-must-transpose -- WU3/WU4/WU5
# =====================================================================


class PacketCorpusReuseTests(unittest.TestCase):
    """`design.md` D2, Phase 3 (WU3, tasks 3.4/3.6): `assemble_packet`
    never assembles a corpus it was handed, and never derives a paper
    root it was not given -- proven against a REAL `bind`-recorded
    binding, so only the SUPPLIED root (never the derived default) can
    possibly resolve it."""

    def setUp(self) -> None:
        # `cmd_bind`/`cmd_write` both resolve `--paper`/`--sections` through
        # the real, non-injectable `FORGE_ROOT` default (the same
        # containment `BindCliEndToEndTests` requires), so this fixture
        # lives under the already-gitignored `.scratch/` tree.
        self.tmp_path = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-packet-corpus-reuse-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.tmp_path, ignore_errors=True)
        self.tmp_path.mkdir(parents=True)
        self.sections_dir = self.tmp_path / "sections"
        self.sections_dir.mkdir()
        self.guidance_dir = self.tmp_path / "guidance"
        # `document=None`: the header itself declares NO binding, so the
        # fixture's binding exists ONLY where `bind` records it below --
        # a header-declared binding would resolve identically no matter
        # which `paper_dir` is supplied, which would prove nothing.
        _write_transposition_section(self.sections_dir, "01-a", "a", "only", document=None)
        proposals = self.tmp_path / "proposals"
        proposals.mkdir()
        (proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}), encoding="utf-8",
        )
        (proposals / "widget-cascade-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n\nResolved section body text for this fixture only.\n",
            encoding="utf-8",
        )
        # A DIFFERENT root from `sections_dir.parent / "paper"` (`paper_
        # graph.assemble_corpus`'s own default) -- the SUPPLIED root this
        # whole class proves `assemble_packet` actually uses.
        self.custom_paper_dir = self.tmp_path / "custom-paper"
        paper_scaffold.scaffold(self.custom_paper_dir)
        # The DERIVED default -- scaffolded too, but never bound, so a
        # silent fallback to it would show `unbound`, never `resolved`.
        self.default_paper_dir = self.tmp_path / "paper"
        paper_scaffold.scaffold(self.default_paper_dir)

        _settle_separation_round(
            self.custom_paper_dir, self.tmp_path, "formulation", "widget-cascade", "a.only",
            ["3. Something"],
        )
        paper_cli.cmd_bind(argparse.Namespace(
            paper=str(self.custom_paper_dir), sections=str(self.sections_dir),
            block="a.only", fact="formulation", lineage="widget-cascade",
            section=["3. Something"], reopen=False,
        ))

    def test_a_corpus_assembled_under_the_supplied_paper_dir_is_reused_verbatim(self) -> None:
        corpus = paper_cli._resolve_write_gate(self.custom_paper_dir, self.sections_dir, "a.only")

        with unittest.mock.patch.object(
            paper_graph, "assemble_corpus", wraps=paper_graph.assemble_corpus,
        ) as spy:
            packet = paper_cli.assemble_packet(
                self.sections_dir, self.guidance_dir, "a", "only",
                corpus=corpus, paper_dir=self.custom_paper_dir,
            )

        spy.assert_not_called()
        self.assertEqual(packet["source_sections_state"]["state"], "resolved")
        self.assertEqual(len(packet["source_sections"]), 1)

    def test_no_corpus_resolves_against_the_supplied_root_never_the_derived_default(self) -> None:
        under_custom = paper_cli.assemble_packet(
            self.sections_dir, self.guidance_dir, "a", "only", paper_dir=self.custom_paper_dir,
        )
        under_default = paper_cli.assemble_packet(
            self.sections_dir, self.guidance_dir, "a", "only", paper_dir=self.default_paper_dir,
        )

        self.assertEqual(under_custom["source_sections_state"]["state"], "resolved")
        self.assertEqual(under_default["source_sections_state"]["state"], "unbound")

    def test_cmd_write_resolves_source_sections_consistently_with_assemble_packet(self) -> None:
        """Task 3.6: `cmd_write`'s own `assemble_packet` call (now given
        `corpus=corpus, paper_dir=paper_dir`) and `BlockContract.source_
        sections` (`paper_cli.py:2260`) must resolve against the SAME
        corpus -- never a second, independently-assembled one."""
        draft = {
            "latex": "This closes the block.",
            "bindings": [{"sentence": "This closes the block.", "binding": "structural"}],
        }
        audit = {"verdicts": [{"bullet": "A symbol used without being declared.", "verdict": "clear"}]}
        (self.tmp_path / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
        (self.tmp_path / "audit.json").write_text(json.dumps(audit), encoding="utf-8")

        with unittest.mock.patch.object(
            paper_source_span, "resolve_bound_sections", wraps=paper_source_span.resolve_bound_sections,
        ) as spy:
            args = argparse.Namespace(
                paper=str(self.custom_paper_dir), sections=str(self.sections_dir),
                section="a", block="only",
                draft=str(self.tmp_path / "draft.json"),
                audit=str(self.tmp_path / "audit.json"),
                evidence=None, style=None, guidance=str(self.guidance_dir), transcript=None, grounding=None,
            )
            with self.assertRaises(Refused) as ctx:
                paper_cli.cmd_write(args)

        # No open block marker exists for "only" in this fixture's `main.tex`
        # -- `substitute` refuses `BLOCK_ABSENT` at the very end of the
        # pipeline, proving every earlier stage (including BOTH `resolve_
        # bound_sections` calls) already cleared.
        self.assertEqual(ctx.exception.code, "BLOCK_ABSENT")
        self.assertEqual(spy.call_count, 2)
        corpora = {id(call.args[0]) for call in spy.call_args_list}
        self.assertEqual(len(corpora), 1)
        qualified_ids = {call.args[1] for call in spy.call_args_list}
        self.assertEqual(qualified_ids, {"a.only"})


class PacketCorpusContaminationTests(unittest.TestCase):
    """`design.md` D2 category B/D, Phase 4 (WU4, tasks 4.1-4.3):
    seventeen shipped codes are newly reachable from `packet` for a
    `transposition` block -- proved by a test, not merely documented as
    reachable."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.sections_dir = self.tmp_path / "sections"
        self.sections_dir.mkdir()
        self.guidance_dir = self.tmp_path / "guidance"
        self.paper_dir = self.tmp_path / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        _write_transposition_section(
            self.sections_dir, "01-a", "a", "only",
            document={"lineage": "widget-cascade", "section": "3. Something"},
        )
        proposals = self.tmp_path / "proposals"
        proposals.mkdir()
        (proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}), encoding="utf-8",
        )
        (proposals / "widget-cascade-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n\nResolved section body text for this fixture only.\n",
            encoding="utf-8",
        )

    def test_a_hand_edited_declarations_region_blocks_the_packet(self) -> None:
        """Task 4.1: at least one of the 17 category-B codes -- here
        `DECLARATIONS_HAND_EDITED` -- is reachable from `packet`, not
        merely documented as reachable."""
        paper_declarations.set_declaration(self.paper_dir, "author-roles", "Alice: writing")
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        pre = tex_path.read_bytes()
        record = paper_region.read_region(pre, "declarations")
        corrupted = (
            pre[: record["begin_start"]]
            + pre[record["begin_start"]:record["end_end"]].replace(b"Alice", b"Alicf", 1)
            + pre[record["end_end"]:]
        )
        tex_path.write_bytes(corrupted)

        with self.assertRaises(Refused) as ctx:
            paper_cli.assemble_packet(
                self.sections_dir, self.guidance_dir, "a", "only", paper_dir=self.paper_dir,
            )
        self.assertEqual(ctx.exception.code, "DECLARATIONS_HAND_EDITED")

    def test_an_unrelated_malformed_section_blocks_a_transposition_packet(self) -> None:
        (self.sections_dir / "02-b.md").write_bytes(b"---\nnot valid json\n---\n\nBroken.\n")

        with self.assertRaises(Refused) as ctx:
            paper_cli.assemble_packet(
                self.sections_dir, self.guidance_dir, "a", "only", paper_dir=self.paper_dir,
            )
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")

    def test_the_same_corrupted_sibling_does_not_block_an_argument_mode_packet(self) -> None:
        # Named "00-c" (sorts BEFORE the corrupted "02-b" below) so `paper_
        # contract.resolve_section_path`'s own pre-existing, mode-blind
        # scan-every-file lookup for THIS section resolves before ever
        # reaching the corrupted sibling -- this test is about `assemble_
        # packet`'s NEW mode gate (skipping `assemble_corpus` entirely for
        # an `argument`-mode block), never about that unrelated, already-
        # shipped lookup order.
        _write_transposition_section(
            self.sections_dir, "00-c", "c", "only", mode="argument",
            document={"lineage": "widget-cascade", "section": "3. Something"},
        )
        (self.sections_dir / "02-b.md").write_bytes(b"---\nnot valid json\n---\n\nBroken.\n")

        packet = paper_cli.assemble_packet(
            self.sections_dir, self.guidance_dir, "c", "only", paper_dir=self.paper_dir,
        )
        self.assertEqual(packet["source_sections_state"]["state"], "not-applicable")


class SourceSectionVerbatimFalsifierTests(unittest.TestCase):
    """`design.md` D6, Phase 5 (WU5, tasks 5.1-5.4): `SOURCE_RUN_BACKSTOP`
    holds unchanged, and THIS is the falsifier that makes it a MEASURED
    claim -- driven through the REAL `cmd_packet` -> `cmd_write` path end
    to end, never a hand-built `BlockContract`."""

    def setUp(self) -> None:
        # `cmd_packet`/`cmd_write` both resolve `--paper`/`--sections`
        # through the real, non-injectable `FORGE_ROOT` default, the same
        # containment `BindCliEndToEndTests` requires.
        self.tmp_path = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-verbatim-falsifier-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.tmp_path, ignore_errors=True)
        self.tmp_path.mkdir(parents=True)
        self.sections_dir = self.tmp_path / "sections"
        self.sections_dir.mkdir()
        self.guidance_dir = self.tmp_path / "guidance"
        self.paper_dir = self.tmp_path / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        # The manuscript carries the QUALIFIED id (`<section>.<block>`), which is
        # what `skeleton`/`open` write and what `cmd_write` now substitutes against.
        (self.paper_dir / "main.tex").write_bytes(_marker_pair("a.only", b"Old body.\n"))
        self._section_text = (
            "This synthetic fixture section restates a long distinctive and entirely invented "
            "sentence describing a formulation transposed from its own bound source document "
            "for testing purposes only."
        )
        # A single-word heading title -- `resolve_bound_sections`' own span
        # includes the heading LINE itself (`paper_guidance.segment_
        # markdown`'s `byte_start` starts at the `#` marker, not the body
        # beneath it), and its only capitalized token then sits at index 0
        # of the pasted sentence, where `paper_bindings.type_structural`'s
        # named-external-object check never looks (`index == 0: continue`).
        # A multi-word title would otherwise flag its OWN second word as a
        # named external object, a `paper_bindings` concern unrelated to
        # the D6 falsifier this fixture exists to prove.
        _write_transposition_section(
            self.sections_dir, "01-a", "a", "only",
            document={"lineage": "widget-cascade", "section": "Formulation"},
        )
        proposals = self.tmp_path / "proposals"
        proposals.mkdir()
        (proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}), encoding="utf-8",
        )
        (proposals / "widget-cascade-r21.md").write_text(
            f"# Intro\n\n# Formulation\n\n{self._section_text}\n", encoding="utf-8",
        )

    def _packet(self) -> dict:
        args = argparse.Namespace(
            section="a", block="only", sections=str(self.sections_dir),
            guidance=str(self.guidance_dir), paper=str(self.paper_dir),
        )
        return paper_cli.cmd_packet(args)

    def _write_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="a", block="only",
            draft=str(self.tmp_path / "draft.json"),
            audit=str(self.tmp_path / "audit.json"),
            evidence=None, style=None, guidance=str(self.guidance_dir), transcript=None, grounding=None,
        )

    def test_the_fixture_packet_resolves_the_bound_section(self) -> None:
        """Task 5.2: the packet resolves through the real `cmd_packet`
        path, not a hand-built corpus."""
        packet = self._packet()
        self.assertEqual(packet["source_sections_state"]["state"], "resolved")
        self.assertEqual(len(packet["source_sections"]), 1)
        self.assertIn(self._section_text, packet["source_sections"][0]["text"])

    def test_a_verbatim_paste_of_the_fixture_bound_section_refuses(self) -> None:
        """Task 5.3: D6's own required falsifier."""
        packet = self._packet()
        bound_text = packet["source_sections"][0]["text"]
        # Segmented the SAME way `write`'s own `paper_bindings.reconcile`
        # will segment it -- robust to whatever the resolved span's own
        # sentence boundaries turn out to be, never assumed to be one.
        sentences = paper_bindings.segment_sentences(bound_text)
        self.assertTrue(sentences, "the resolved span segmented into zero sentences")

        draft = {
            "latex": bound_text,
            "bindings": [{"sentence": sentence, "binding": "structural"} for sentence in sentences],
        }
        audit = {"verdicts": [{"bullet": "A symbol used without being declared.", "verdict": "clear"}]}
        (self.tmp_path / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
        (self.tmp_path / "audit.json").write_text(json.dumps(audit), encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self._write_args())

        self.assertEqual(ctx.exception.code, "SOURCE_SECTION_VERBATIM")
        # `main.tex` never changes on a refused write.
        self.assertEqual(
            (self.paper_dir / "main.tex").read_bytes(), _marker_pair("a.only", b"Old body.\n"),
        )

    def test_a_genuinely_restated_draft_under_threshold_still_writes(self) -> None:
        """Task 5.4: the companion case -- a genuinely restated draft,
        run length under threshold, passes and `write` succeeds; the
        guard is not simply always-refuse."""
        packet = self._packet()
        self.assertEqual(len(packet["source_sections"]), 1)  # sanity: the section did resolve

        draft = {
            "latex": "This closes the block with its own distinct restatement.",
            "bindings": [{
                "sentence": "This closes the block with its own distinct restatement.",
                "binding": "structural",
            }],
        }
        audit = {"verdicts": [{"bullet": "A symbol used without being declared.", "verdict": "clear"}]}
        (self.tmp_path / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
        (self.tmp_path / "audit.json").write_text(json.dumps(audit), encoding="utf-8")

        result = paper_cli.cmd_write(self._write_args())

        self.assertEqual(result["status"], "written")


class CitationReadinessGateTests(unittest.TestCase):
    """`no-citation-before-its-paper-is-ingested`, item 3: `write` refuses
    while a citing block's own section citation folder
    (`guidance/<section-id>/`) is not fully ready -- PDFs downloaded,
    ingested, and the folder classified. Runs under the real,
    non-injectable `FORGE_ROOT` default, the same `.scratch/`
    convention `WriteGateTests`/`PacketWriteGateTests` use.

    RED-first: before `_guard_section_citations_ready` existed, every
    refusal test below instead failed on `draft.json`
    (`FileNotFoundError`) -- proof the guard was never consulted on the
    real `cmd_write` path."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-citation-gate-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        blocks = [
            {"id": "cited", "requires_facts": [], "requires_declarations": [], "citations": "resolution"},
            {"id": "uncited", "requires_facts": [], "requires_declarations": [], "citations": "none"},
        ]
        (self.sections_dir / "01-a.md").write_text(
            "---\n" + json.dumps({"section": "cited-section", "position": 1, "blocks": blocks})
            + "\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        self.guidance_dir = self.test_root / "guidance"

        self.args = argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="cited-section", block="cited",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=str(self.guidance_dir), transcript=None, grounding=None,
        )

    def test_no_guidance_folder_at_all_refuses_citation_folder_absent(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self.args)
        self.assertEqual(ctx.exception.code, "CITATION_FOLDER_ABSENT")
        self.assertIn("cited-section", ctx.exception.detail)
        self.assertFalse((self.test_root / "draft.json").exists())
        self.assertFalse((self.test_root / "audit.json").exists())

    def test_an_un_ingested_loose_pdf_refuses_citation_not_ingested_naming_it(self) -> None:
        """The decisive proof for item 3: a section folder holding a loose,
        un-ingested PDF refuses `write` by name, before `draft.json` is
        ever opened."""
        section_dir = self.guidance_dir / "cited-section"
        section_dir.mkdir(parents=True)
        (section_dir / "smith2024.pdf").write_bytes(b"%PDF-1.4 fake")

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self.args)
        self.assertEqual(ctx.exception.code, "CITATION_NOT_INGESTED")
        self.assertIn("smith2024.pdf", ctx.exception.detail)
        self.assertFalse((self.test_root / "draft.json").exists())

    def test_an_ingested_but_unclassified_folder_refuses_citation_folder_unclassified(self) -> None:
        paper_dir = self.guidance_dir / "cited-section" / "smith2024"
        paper_dir.mkdir(parents=True)
        (paper_dir / "smith2024.md").write_text("# Smith 2024\n", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self.args)
        self.assertEqual(ctx.exception.code, "CITATION_FOLDER_UNCLASSIFIED")

    def test_a_fully_ready_section_proceeds_past_the_citation_gate(self) -> None:
        """A ready citation folder is not itself the failure -- `cmd_write`
        proceeds past this gate and fails on the very next real stage
        instead, the draft file this test deliberately never creates,
        never `Refused` from the citation gate."""
        paper_dir = self.guidance_dir / "cited-section" / "smith2024"
        paper_dir.mkdir(parents=True)
        (paper_dir / "smith2024.md").write_text("# Smith 2024\n", encoding="utf-8")
        (self.guidance_dir / "cited-section" / ".paper-writing.json").write_text(
            json.dumps({"class": "evidence"}), encoding="utf-8",
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self.args)
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")

    def test_a_none_regime_block_is_never_gated_even_with_no_guidance_folder_at_all(self) -> None:
        """A guard that blocks everything is as wrong as one that blocks
        nothing: the `uncited` block's own contract declares `"citations":
        "none"`, so it is written with no citations to gate at all, even
        though `guidance/cited-section/` still does not exist."""
        args = argparse.Namespace(**{**vars(self.args), "block": "uncited"})
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(args)
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")


class CitationReadinessGateMutationProofTests(unittest.TestCase):
    """The decisive mutation proof for item 3: removing `cmd_write`'s own
    call to `_guard_section_citations_ready` must fail
    `CitationReadinessGateTests.test_an_un_ingested_loose_pdf_refuses_
    citation_not_ingested_naming_it` -- a passing test beside an
    unexercised guard is not a mutation that ran."""

    def test_mutation_removing_the_citation_gate_call_fails_the_refusal(self) -> None:
        proc = _run_against_mutant(
            "    _guard_section_citations_ready(guidance_dir, header.section, block[\"citations\"])\n",
            "",
            "tests.test_paper_writing.CitationReadinessGateTests"
            ".test_an_un_ingested_loose_pdf_refuses_citation_not_ingested_naming_it",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_a_none_regime_gate_that_never_returns_early_fails_the_uncited_proof(self) -> None:
        """The other half of the same decisive proof: a gate that forgot
        `none`-regime blocks entirely (checked EVERY regime) must fail
        `CitationReadinessGateTests.test_a_none_regime_block_is_never_
        gated_even_with_no_guidance_folder_at_all` -- a guard that blocks
        everything is as wrong as one that blocks nothing, and this proves
        the negative test actually exercises the early return."""
        proc = _run_against_mutant(
            '    if regime == "none":\n        return\n',
            "",
            "tests.test_paper_writing.CitationReadinessGateTests"
            ".test_a_none_regime_block_is_never_gated_even_with_no_guidance_folder_at_all",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class PacketReadOnlyTests(unittest.TestCase):
    """tasks.md 8.14: `packet` writes nothing under every input, including
    every refusal path -- the same before/after content manifest
    `ReadinessPhasesReadOnlyTests` already established for `phases`/
    `readiness`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.sections_dir = self.tmp_path / "sections"
        self.sections_dir.mkdir()
        self.guidance_dir = self.tmp_path / "guidance"
        _write_packet_section(self.sections_dir, "01-intro", "intro", "a", "Our own contract prose.")
        _write_guidance_style_reference(self.guidance_dir, "reference-papers", {
            "paper-one": "# Introduction\n\nA reference sentence.\n",
        })
        self.broken_guidance_dir = self.tmp_path / "guidance-broken"
        _write_guidance_style_reference(self.broken_guidance_dir, "reference-papers", {
            "paper-one": "# X\n\nBody.\n",
        })
        (self.broken_guidance_dir / "reference-papers" / "paper-one" / "paper-one.md").write_bytes(
            b"\xff\xfe# Not valid UTF-8\n",
        )

    def _manifest(self) -> dict:
        return {
            str(path.relative_to(self.tmp_path)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.tmp_path.rglob("*")) if path.is_file()
        }

    def test_packet_writes_nothing_including_when_it_refuses(self) -> None:
        before = self._manifest()

        paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")
        with self.assertRaises(Refused):
            paper_cli.assemble_packet(self.sections_dir, self.broken_guidance_dir, "intro", "a")

        after = self._manifest()
        self.assertEqual(before, after)

    def test_mutation_a_write_inside_assemble_packet_fails_the_manifest_guard(self) -> None:
        proc = _run_against_mutant(
            "def assemble_packet(\n"
            "    sections_dir: Path, guidance_dir: Path, section: str, block_id: str,\n"
            "    *, corpus=None, paper_dir: Path | None = None,\n"
            ") -> dict:\n",
            "def assemble_packet(\n"
            "    sections_dir: Path, guidance_dir: Path, section: str, block_id: str,\n"
            "    *, corpus=None, paper_dir: Path | None = None,\n"
            ") -> dict:\n"
            "    marker = sections_dir / '01-intro.md'\n"
            "    marker.write_bytes(marker.read_bytes() + b'x')\n",
            "tests.test_paper_writing.PacketReadOnlyTests"
            ".test_packet_writes_nothing_including_when_it_refuses",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class PacketPathContainmentTests(unittest.TestCase):
    """Threat Matrix, `Path containment`: `packet` reuses `paper_contract.
    resolve_sections_dir` / `paper_guidance.resolve_guidance_dir`
    verbatim -- never a new containment check (design.md; tasks.md 8.6).
    Runs under the real, non-injectable `FORGE_ROOT` default, the same
    `.scratch/` convention `SkeletonPathContainmentTests` uses."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-packet-containment-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        _write_packet_section(self.sections_dir, "01-intro", "intro", "a", "Prose.")
        self.guidance_dir = self.test_root / "guidance"

    def test_sections_outside_repository_refuses_and_writes_nothing(self) -> None:
        outside = Path(tempfile.gettempdir()) / f"paper-writing-packet-outside-sections-{os.getpid()}"
        args = argparse.Namespace(
            section="intro", block="a", sections=str(outside), guidance=str(self.guidance_dir), paper=None,
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_packet(args)

        self.assertEqual(ctx.exception.code, "SECTIONS_OUTSIDE_REPOSITORY")
        self.assertFalse(outside.exists())

    def test_guidance_outside_repository_refuses_and_writes_nothing(self) -> None:
        outside = Path(tempfile.gettempdir()) / f"paper-writing-packet-outside-guidance-{os.getpid()}"
        args = argparse.Namespace(
            section="intro", block="a", sections=str(self.sections_dir), guidance=str(outside), paper=None,
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_packet(args)

        self.assertEqual(ctx.exception.code, "GUIDANCE_OUTSIDE_REPOSITORY")
        self.assertFalse(outside.exists())


class PacketPaperFlagTests(unittest.TestCase):
    """`the-redactor-receives-the-section-it-must-transpose`, design.md D1
    category C, Phase 3 (WU3, tasks 3.1-3.3): `cmd_packet` now resolves
    `--paper` through `paper_scaffold.resolve_paper_dir`, the SAME
    containment boundary `write`/`place` already enforce."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-packet-paper-flag-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        _write_packet_section(self.sections_dir, "01-intro", "intro", "a", "Prose.")
        self.guidance_dir = self.test_root / "guidance"

    def test_paper_outside_repository_refuses(self) -> None:
        outside = Path(tempfile.gettempdir()) / f"paper-writing-packet-outside-paper-{os.getpid()}"
        args = argparse.Namespace(
            section="intro", block="a", sections=str(self.sections_dir),
            guidance=str(self.guidance_dir), paper=str(outside),
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_packet(args)

        self.assertEqual(ctx.exception.code, "PAPER_OUTSIDE_REPOSITORY")

    def test_a_real_paper_root_reaches_assemble_packet(self) -> None:
        paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(paper_dir)
        args = argparse.Namespace(
            section="intro", block="a", sections=str(self.sections_dir),
            guidance=str(self.guidance_dir), paper=str(paper_dir),
        )

        packet = paper_cli.cmd_packet(args)

        self.assertEqual(packet["block"], "a")
        self.assertIn("source_sections_state", packet)


class PacketShippedCorpusTests(unittest.TestCase):
    """`packet` against the contracts this repository actually ships.

    Every packet fixture in this file writes `sections/01-intro.md` with a
    header declaring `section: "intro"`, and then asked for `"01-intro"` --
    the FILE STEM. That is the only shape under which composing
    `sections_dir / f"{section}.md"` works, and it is a shape the shipped
    corpus never has: all ten contracts are `NN-<section>.md`. So `packet`
    could not open a single real contract, died with a `FileNotFoundError`
    traceback and exit 1 rather than this skill's refusal envelope, and the
    whole packet suite stayed green because it only ever exercised the
    implementation's own shortcut.

    This case is derived from the corpus on disk rather than listing
    anything, so a future rename cannot re-break it in silence: it walks
    every section every contract declares and every block inside it.
    """

    def test_packet_resolves_every_block_of_every_shipped_section(self) -> None:
        sections_dir = FORGE_ROOT / "sections"
        guidance_dir = FORGE_ROOT / "guidance"
        pairs = []
        for path in sorted(sections_dir.glob("*.md")):
            header, _ = paper_contract.parse(path.read_bytes())
            for block in header.blocks:
                pairs.append((header.section, block["id"]))

        self.assertGreaterEqual(
            len(pairs), 10,
            "no section/block pair parsed out of the shipped corpus -- every "
            "assertion below would be passing over an empty set")

        for section, block_id in pairs:
            with self.subTest(section=section, block=block_id):
                packet = paper_cli.assemble_packet(
                    sections_dir, guidance_dir, section, block_id)
                self.assertEqual(packet["section"], section)
                self.assertEqual(packet["block"], block_id)
                self.assertTrue(
                    packet["contract"],
                    "the packet's whole purpose is carrying contract prose")

    def test_an_undeclared_section_refuses_and_names_what_is_declared(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_cli.assemble_packet(
                FORGE_ROOT / "sections", FORGE_ROOT / "guidance",
                "experimental-setup.md", "es-dataset")
        self.assertEqual(ctx.exception.code, "SECTION_UNKNOWN")
        self.assertIn("experimental-setup", ctx.exception.detail)

    def test_an_undeclared_block_refuses_and_names_what_is_declared(self) -> None:
        """A bare `next()` raised `StopIteration` here -- a crash, and one a
        static roster scan cannot see, since it only ever reads a literal
        refusal code."""
        with self.assertRaises(Refused) as ctx:
            paper_cli.assemble_packet(
                FORGE_ROOT / "sections", FORGE_ROOT / "guidance",
                "experimental-setup", "no-such-block")
        self.assertEqual(ctx.exception.code, "BLOCK_UNDECLARED")
        self.assertIn("es-dataset", ctx.exception.detail)


class SectionPathCorruptSiblingTests(unittest.TestCase):
    """A sibling this lookup was not asked about cannot decide it.

    `resolve_section_path` reads EVERY `sections/*.md` to find one, so a
    corrupted contract sorting alphabetically first used to refuse every
    lookup behind it -- including a section whose own file is perfectly well
    formed. Reproduced with a minimal fixture by the verify phase of
    `the-redactor-receives-the-section-it-must-transpose`, whose own
    corpus-contamination test had to order its fixture filenames around it.

    The defect is deferred, never swallowed: a corrupt sibling that did not
    hold the answer is irrelevant, and `contract`/`plan` still refuse on it
    through the corpus reader, whose job that is.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()
        # Sorts FIRST, and its header is not JSON.
        (self.sections_dir / "00-corrupt.md").write_text(
            "---\n{ not json at all\n---\n\nProse.\n", encoding="utf-8")
        _write_packet_section(
            self.sections_dir, "01-intro", "intro", "a", "Our own contract prose.")

    def test_a_corrupt_sibling_sorting_first_does_not_block_a_well_formed_section(self) -> None:
        resolved = paper_contract.resolve_section_path(self.sections_dir, "intro")
        self.assertEqual(resolved.name, "01-intro.md")

    def test_a_genuinely_absent_section_names_the_unreadable_files_too(self) -> None:
        """'It is not there' and 'one file could not be read' must never
        look the same from the refusal -- otherwise the deferral above
        becomes a way to hide a corpus defect."""
        with self.assertRaises(Refused) as ctx:
            paper_contract.resolve_section_path(self.sections_dir, "no-such-section")
        self.assertEqual(ctx.exception.code, "SECTION_UNKNOWN")
        self.assertIn("intro", ctx.exception.detail)
        self.assertIn("00-corrupt.md", ctx.exception.detail)
        self.assertIn("MALFORMED_HEADER", ctx.exception.detail)

    def test_the_corpus_reader_still_refuses_on_the_same_corrupt_file(self) -> None:
        """The deferral is scoped to this one lookup. The verb whose job is
        reading the whole corpus must still say the file is broken."""
        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)
        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")


# =====================================================================
# the-redactor-receives-the-section-it-must-transpose -- WU0/WU1
# =====================================================================


class AssemblePacketCorpusParamsTests(unittest.TestCase):
    """`design.md` D2/D3(interface), Phase 0 (WU0): `assemble_packet`
    gains keyword-only `corpus`/`paper_dir`, defaulted, and never
    re-assembles a corpus it was handed."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.sections_dir = self.tmp_path / "sections"
        self.sections_dir.mkdir()
        self.guidance_dir = self.tmp_path / "guidance"

    def test_no_corpus_or_paper_dir_leaves_the_four_original_keys_unchanged(self) -> None:
        """Task 0.1: called with no `corpus`/`paper_dir`, the widened
        signature changes nothing an existing caller reads."""
        _write_packet_section(self.sections_dir, "01-intro", "intro", "a", "Our own contract prose.")

        packet = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "intro", "a")

        self.assertEqual(packet["block"], "a")
        self.assertEqual(packet["section"], "intro")
        self.assertIn("Our own contract prose.", packet["contract"])
        self.assertEqual(packet["references"], [])

    def test_a_supplied_corpus_is_never_re_assembled(self) -> None:
        """Task 0.2: a `transposition`-mode block, handed a pre-built
        corpus, must never call `paper_graph.assemble_corpus` a second
        time -- spied, not merely inferred from the returned envelope."""
        _write_transposition_section(self.sections_dir, "02-b", "b", "only", with_fact=False)
        corpus = paper_graph.assemble_corpus(self.sections_dir)

        with unittest.mock.patch.object(
            paper_graph, "assemble_corpus", wraps=paper_graph.assemble_corpus,
        ) as spy:
            paper_cli.assemble_packet(
                self.sections_dir, self.guidance_dir, "b", "only", corpus=corpus,
            )

        spy.assert_not_called()


class PacketSourceSectionsStateTests(unittest.TestCase):
    """`design.md` D1/D2/D4/D5, Phase 1 (WU1): the closed `source_sections_
    state` vocabulary, and the mode gate that decides whether a corpus is
    even assembled. `redactor-packet` spec, scenarios "A transposition
    block with a resolved binding...", "...reports unbound...", "No paper
    root reachable reports unmeasured...", "An argument-mode block
    reports not-applicable..."."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.sections_dir = self.tmp_path / "sections"
        self.sections_dir.mkdir()
        self.guidance_dir = self.tmp_path / "guidance"

    def _scaffold_source(self) -> None:
        proposals = self.tmp_path / "proposals"
        proposals.mkdir()
        (proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}), encoding="utf-8",
        )
        (proposals / "widget-cascade-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n\nResolved section body text for this synthetic fixture only.\n",
            encoding="utf-8",
        )

    def test_a_resolvable_binding_reports_resolved(self) -> None:
        self._scaffold_source()
        _write_transposition_section(
            self.sections_dir, "01-a", "a", "only",
            document={"lineage": "widget-cascade", "section": "3. Something"},
        )
        paper_dir = self.tmp_path / "paper"
        paper_scaffold.scaffold(paper_dir)

        packet = paper_cli.assemble_packet(
            self.sections_dir, self.guidance_dir, "a", "only", paper_dir=paper_dir,
        )

        self.assertEqual(len(packet["source_sections"]), 1)
        section = packet["source_sections"][0]
        self.assertEqual(section["fact"], "formulation")
        self.assertEqual(section["lineage"], "widget-cascade")
        self.assertEqual(section["title"], "3. Something")
        self.assertIn("Resolved section body text", section["text"])
        self.assertEqual(
            packet["source_sections_state"],
            {"state": "resolved", "reason": None, "unresolved": []},
        )

    def test_no_triple_declared_at_all_reports_unbound_never_a_refusal(self) -> None:
        _write_transposition_section(self.sections_dir, "01-a", "a", "only", with_fact=False)
        paper_dir = self.tmp_path / "paper"
        paper_scaffold.scaffold(paper_dir)

        packet = paper_cli.assemble_packet(
            self.sections_dir, self.guidance_dir, "a", "only", paper_dir=paper_dir,
        )

        self.assertEqual(packet["source_sections"], ())
        state = packet["source_sections_state"]
        self.assertEqual(state["state"], "unbound")
        self.assertIsNotNone(state["reason"])
        self.assertEqual(state["unresolved"], [])

    def test_a_declared_triple_with_no_paper_root_reports_unmeasured(self) -> None:
        """Constraint 4: distinct from the `unbound` envelope above even
        though both report an empty `source_sections`."""
        self._scaffold_source()
        _write_transposition_section(
            self.sections_dir, "01-a", "a", "only",
            document={"lineage": "widget-cascade", "section": "3. Something"},
        )

        packet = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "a", "only")

        self.assertEqual(packet["source_sections"], ())
        state = packet["source_sections_state"]
        self.assertEqual(state["state"], "unmeasured")
        self.assertIsNotNone(state["reason"])
        self.assertEqual(
            state["unresolved"],
            [{"fact": "formulation", "lineage": "widget-cascade", "title": "3. Something"}],
        )
        self.assertNotEqual(state["state"], "unbound")
        self.assertNotEqual(
            state, {"state": "unbound", "reason": state["reason"], "unresolved": []},
        )

    def test_an_argument_mode_block_reports_not_applicable_and_stays_byte_identical(self) -> None:
        self._scaffold_source()
        _write_transposition_section(
            self.sections_dir, "01-a", "a", "only", mode="argument",
            document={"lineage": "widget-cascade", "section": "3. Something"},
        )
        paper_dir = self.tmp_path / "paper"
        paper_scaffold.scaffold(paper_dir)

        with_root = paper_cli.assemble_packet(
            self.sections_dir, self.guidance_dir, "a", "only", paper_dir=paper_dir,
        )
        baseline = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "a", "only")

        state = with_root["source_sections_state"]
        self.assertEqual(state["state"], "not-applicable")
        self.assertIsNotNone(state["reason"])
        self.assertEqual(with_root["source_sections"], ())
        for key in ("block", "section", "contract", "references"):
            self.assertEqual(with_root[key], baseline[key])

    def test_no_mode_declared_reports_unmeasured_naming_the_absent_mode(self) -> None:
        _write_transposition_section(
            self.sections_dir, "01-a", "a", "only", mode=None,
            document={"lineage": "widget-cascade", "section": "3. Something"},
        )

        packet = paper_cli.assemble_packet(self.sections_dir, self.guidance_dir, "a", "only")

        state = packet["source_sections_state"]
        self.assertEqual(state["state"], "unmeasured")
        self.assertIsNotNone(state["reason"])
        self.assertIn("mode", state["reason"].lower())
        self.assertEqual(packet["source_sections"], ())

    def test_mutation_the_no_paper_root_branch_is_reachable_not_decorative(self) -> None:
        """Task 1.7: break the `unmeasured`-because-no-paper-root branch's
        own `state`/`reason` assignment and confirm the pinning test above
        goes RED -- proving that branch is reachable, not decorative."""
        proc = _run_against_mutant(
            '            return (), {\n'
            '                "state": "unmeasured",\n'
            '                "reason": (\n'
            '                    f"{qualified_id}: no paper root supplied; pass --paper <dir> (or "\n'
            '                    "ensure paper/main.tex is reachable) so its bound sections can be "\n'
            '                    "resolved"\n'
            '                ),\n'
            '                "unresolved": [\n'
            '                    {"fact": fact, "lineage": lineage, "title": title}\n'
            '                    for fact, lineage, title in header_triples\n'
            '                ],\n'
            '            }\n',
            '            return (), {"state": "resolved", "reason": None, "unresolved": []}\n',
            "tests.test_paper_writing.PacketSourceSectionsStateTests"
            ".test_a_declared_triple_with_no_paper_root_reports_unmeasured",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class SeparationProposalShapeTests(unittest.TestCase):
    """`the-whole-cut-is-argued-before-any-section-is-claimed`, U2, task
    2.1-2.4: `paper_cli._read_separation_proposal`'s own shape stage --
    pure JSON/key-set validation, no corpus needed at all (design.md,
    Interfaces / Contracts: key set exactly `{lineage, assignments}` plus
    the optional `concedes_to_round`; each assignment exactly `{block,
    fact, sections}`; `sections` a list of unique non-empty strings; a
    duplicate `(block, fact)` pair; facts resolving through more than one
    source root)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def _write(self, obj) -> Path:
        path = self.base / "proposal.json"
        path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
        return path

    def test_a_well_shaped_proposal_parses(self) -> None:
        path = self._write({
            "lineage": "field-survey",
            "assignments": [
                {"block": "overview.block-a", "fact": "formulation",
                 "sections": ["1. Background on widget metrics"]},
                {"block": "methods.block-b", "fact": "formulation",
                 "sections": ["2. Alignment estimators"]},
                {"block": "methods.block-c", "fact": "formulation",
                 "sections": ["2. Alignment estimators"]},
            ],
        })
        result = paper_cli._read_separation_proposal(path)
        self.assertEqual(result["lineage"], "field-survey")
        self.assertEqual(len(result["assignments"]), 3)
        self.assertEqual(result["root"].name, "proposals")

    def test_an_unknown_top_level_key_refuses_naming_it(self) -> None:
        path = self._write({"lineage": "field-survey", "assignments": [], "author": "someone"})

        with self.assertRaises(Refused) as ctx:
            paper_cli._read_separation_proposal(path)

        self.assertEqual(ctx.exception.code, "SEPARATION_REPORT_UNREADABLE")
        self.assertIn("author", ctx.exception.detail)

    def test_a_duplicate_block_fact_pair_refuses_naming_it(self) -> None:
        path = self._write({
            "lineage": "field-survey",
            "assignments": [
                {"block": "methods.block-b", "fact": "formulation", "sections": ["A"]},
                {"block": "methods.block-b", "fact": "formulation", "sections": ["B"]},
            ],
        })

        with self.assertRaises(Refused) as ctx:
            paper_cli._read_separation_proposal(path)

        self.assertEqual(ctx.exception.code, "SEPARATION_REPORT_UNREADABLE")
        self.assertIn("methods.block-b", ctx.exception.detail)

    def test_a_proposal_spanning_two_source_roots_refuses_naming_both(self) -> None:
        path = self._write({
            "lineage": "field-survey",
            "assignments": [
                {"block": "overview.block-a", "fact": "formulation", "sections": ["A"]},
                {"block": "overview.block-d", "fact": "experimental-design", "sections": ["B"]},
            ],
        })

        with self.assertRaises(Refused) as ctx:
            paper_cli._read_separation_proposal(path)

        self.assertEqual(ctx.exception.code, "SEPARATION_REPORT_UNREADABLE")
        self.assertIn("proposals", ctx.exception.detail)
        self.assertIn("experiments", ctx.exception.detail)

    def test_a_wrong_shaped_assignment_refuses(self) -> None:
        path = self._write({
            "lineage": "field-survey",
            "assignments": [{"block": "overview.block-a", "fact": "formulation"}],
        })

        with self.assertRaises(Refused) as ctx:
            paper_cli._read_separation_proposal(path)

        self.assertEqual(ctx.exception.code, "SEPARATION_REPORT_UNREADABLE")

    def test_sections_must_be_a_list_of_unique_non_empty_strings(self) -> None:
        path = self._write({
            "lineage": "field-survey",
            "assignments": [
                {"block": "overview.block-a", "fact": "formulation", "sections": "A"},
            ],
        })

        with self.assertRaises(Refused) as ctx:
            paper_cli._read_separation_proposal(path)

        self.assertEqual(ctx.exception.code, "SEPARATION_REPORT_UNREADABLE")

    def test_duplicate_titles_inside_one_assignment_refuse(self) -> None:
        path = self._write({
            "lineage": "field-survey",
            "assignments": [
                {"block": "overview.block-a", "fact": "formulation", "sections": ["A", "A"]},
            ],
        })

        with self.assertRaises(Refused) as ctx:
            paper_cli._read_separation_proposal(path)

        self.assertEqual(ctx.exception.code, "SEPARATION_REPORT_UNREADABLE")

    def test_a_non_json_file_refuses(self) -> None:
        path = self._write("not json at all")

        with self.assertRaises(Refused) as ctx:
            paper_cli._read_separation_proposal(path)

        self.assertEqual(ctx.exception.code, "SEPARATION_REPORT_UNREADABLE")

    def test_an_unknown_fact_refuses_unknown_fact(self) -> None:
        path = self._write({
            "lineage": "field-survey",
            "assignments": [
                {"block": "overview.block-a", "fact": "not-a-real-fact", "sections": ["A"]},
            ],
        })

        with self.assertRaises(Refused) as ctx:
            paper_cli._read_separation_proposal(path)

        self.assertEqual(ctx.exception.code, "UNKNOWN_FACT")

    def test_a_non_bindable_fact_refuses_binding_fact_not_bindable(self) -> None:
        path = self._write({
            "lineage": "field-survey",
            "assignments": [
                {"block": "overview.block-a", "fact": "contributions", "sections": ["A"]},
            ],
        })

        with self.assertRaises(Refused) as ctx:
            paper_cli._read_separation_proposal(path)

        self.assertEqual(ctx.exception.code, "BINDING_FACT_NOT_BINDABLE")

    def test_mutation_exact_key_set_weakened_to_a_subset_check(self) -> None:
        proc = _run_against_mutant(
            "unknown_keys = set(report) - _SEPARATION_TOP_KEYS",
            "unknown_keys = set()",
            "tests.test_paper_writing.SeparationProposalShapeTests"
            ".test_an_unknown_top_level_key_refuses_naming_it",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class _SeparationCorpusMixin:
    """Shared fixture for `separate`'s integration tests: a two-section,
    three-block corpus, every block `requires_facts: formulation` with NO
    `document` half (`separate` reads `requires_facts` values directly,
    never a recorded/declared binding), and a `proposals/` root carrying
    lineage `field-survey`'s marker and current revision -- the worked
    example's own invented vocabulary (design.md)."""

    _CLAIMABLE_DOC = (
        "# Field Survey of Widget Alignment\n\n"
        "## 1. Background on widget metrics\n\nBody.\n\n"
        "## 2. Alignment estimators\n\nBody.\n\n"
        "## 3. Proposed alignment objective\n\nBody.\n\n"
        "## 4. Calibration procedure\n\nBody.\n\n"
        "## 5. Open problems\n\nBody.\n"
    )

    _ROUND_1 = {
        "lineage": "field-survey",
        "assignments": [
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["1. Background on widget metrics"]},
            {"block": "methods.block-b", "fact": "formulation",
             "sections": ["2. Alignment estimators", "4. Calibration procedure"]},
            {"block": "methods.block-c", "fact": "formulation",
             "sections": ["2. Alignment estimators"]},
        ],
    }

    _BRANCH_A = {
        "lineage": "field-survey",
        "assignments": [
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["1. Background on widget metrics"]},
            {"block": "methods.block-b", "fact": "formulation",
             "sections": ["2. Alignment estimators", "3. Proposed alignment objective"]},
            {"block": "methods.block-c", "fact": "formulation",
             "sections": ["4. Calibration procedure", "5. Open problems"]},
        ],
    }

    #: The worked example's own "branch B", scoring 5 (`tests.test_paper_
    #: separation.ScoreCutTests.test_worked_example_branch_b_scores_5`):
    #: 1 overlap + 2 orphans + 2 gaps -- strictly WORSE than round 1's 4.
    _BRANCH_B = {
        "lineage": "field-survey",
        "assignments": [
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["2. Alignment estimators"]},
            {"block": "methods.block-b", "fact": "formulation",
             "sections": ["2. Alignment estimators", "5. Open problems"]},
            {"block": "methods.block-c", "fact": "formulation",
             "sections": ["1. Background on widget metrics"]},
        ],
    }

    #: Task 4.1/4.3: a cut structurally DIFFERENT from `_ROUND_1` (the two
    #: methods blocks' own claims are swapped, so canonicalization never
    #: treats it as a byte-identical replay) that recomputes to the exact
    #: SAME total, 4 -- one overlap on "2. Alignment estimators", the same
    #: two orphans, one gap now attributed to `block-c` instead of
    #: `block-b`. A concession naming this against round 1 is a TIE: not a
    #: regression, but still nonzero, so it must still reach the
    #: structural refusal next.
    _TIE_SWAP = {
        "lineage": "field-survey",
        "assignments": [
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["1. Background on widget metrics"]},
            {"block": "methods.block-b", "fact": "formulation",
             "sections": ["2. Alignment estimators"]},
            {"block": "methods.block-c", "fact": "formulation",
             "sections": ["2. Alignment estimators", "4. Calibration procedure"]},
        ],
    }

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.sections_dir = self.base / "sections"
        self.sections_dir.mkdir()
        self.paper_dir = self.base / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self._write_block_section("01-overview.md", "overview", [("block-a", "formulation")])
        self._write_block_section(
            "02-methods.md", "methods", [("block-b", "formulation"), ("block-c", "formulation")],
        )
        self.proposals = self.base / "proposals"
        self.proposals.mkdir()
        (self.proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}),
            encoding="utf-8",
        )
        (self.proposals / "field-survey-r07.md").write_text(self._CLAIMABLE_DOC, encoding="utf-8")

    def _write_block_section(self, filename: str, section_id: str, block_facts: list) -> None:
        blocks = []
        for block_id, fact in block_facts:
            blocks.append({
                "id": block_id,
                "requires_facts": [{
                    "value": fact,
                    "source": {"file": f"sections/{filename}", "quote": "Prose here."},
                }],
                "requires_declarations": [], "citations": "none",
            })
        header = {"section": section_id, "position": 1, "blocks": blocks}
        body = "Prose here.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
        (self.sections_dir / filename).write_bytes(
            b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n" + body.encode("utf-8")
        )

    def _proposal_path(self, obj) -> Path:
        path = self.base / "proposal.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def _compute(self, obj) -> dict:
        return paper_cli.compute_separation(
            self._proposal_path(obj), sections_dir=self.sections_dir, paper_dir=self.paper_dir,
            source_base=self.base,
        )

    def _read_rounds(self) -> tuple:
        return paper_declarations.read_separation_rounds(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
        )

    def _tamper_round_score(self, round_number: int, new_score: int) -> None:
        """Task 4.7: overwrites a recorded round's stored `score` field on
        disk, leaving its `assignments` byte-for-byte unchanged -- proving
        the concession check recomputes from `assignments`, never trusts
        the stored field. Rebuilt through the region's own `build_region_
        bytes`/`replace_or_append` (the SAME path `_write_declarations`
        uses), so the digest stays coherent and this is never mistaken
        for `DECLARATIONS_HAND_EDITED`."""
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        pre = tex_path.read_bytes()
        record = paper_region.read_region(pre, "declarations")
        body = record["body"]
        for entry in body["records"]:
            if entry["kind"] == "separation" and entry.get("round") == round_number:
                entry["score"] = new_score
        region_bytes, _digest = paper_region.build_region_bytes("declarations", body)
        candidate = paper_region.replace_or_append(
            pre, "declarations", region_bytes,
            {"begin_start": record["begin_start"], "end_end": record["end_end"]},
        )
        tex_path.write_bytes(candidate)

    def _run_separate_subprocess(self, proposal_obj, *, expect_ok: bool) -> dict:
        """Task 3.11/3.12: a genuinely SEPARATE CLI invocation -- a real
        subprocess, its own fresh Python process, no module-level state
        shared with this test process at all -- reading whatever an
        earlier, already-exited invocation left on disk."""
        proposal_path = self._proposal_path(proposal_obj)
        script_path = self.base / f"run_separate_{uuid.uuid4().hex}.py"
        script_path.write_text(
            "import json, sys\n"
            f"sys.path.insert(0, {str(SKILL_SCRIPTS)!r})\n"
            f"sys.path.insert(0, {str(CORE_IMPLEMENTATION)!r})\n"
            "from pathlib import Path\n"
            "import paper_cli\n"
            "from impl_refusals import Refused\n"
            "try:\n"
            "    result = paper_cli.compute_separation(\n"
            f"        Path({str(proposal_path)!r}), sections_dir=Path({str(self.sections_dir)!r}),\n"
            f"        paper_dir=Path({str(self.paper_dir)!r}), source_base=Path({str(self.base)!r}),\n"
            "    )\n"
            "    print(json.dumps({'ok': True, 'result': result}))\n"
            "except Refused as exc:\n"
            "    print(json.dumps({'ok': False, 'code': exc.code, 'detail': exc.detail}))\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(script_path)], capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["ok"], expect_ok, payload)
        return payload


class SeparationResolutionReuseTests(_SeparationCorpusMixin, unittest.TestCase):
    """Task 2.5/2.7/2.8: every title resolves through the SAME existence/
    ambiguity path `bind` already uses, before any scoring runs."""

    def test_an_unresolvable_title_refuses_before_scoring(self) -> None:
        proposal = {
            "lineage": "field-survey",
            "assignments": [
                {"block": "overview.block-a", "fact": "formulation",
                 "sections": ["9. Nothing like this exists"]},
                {"block": "methods.block-b", "fact": "formulation",
                 "sections": ["2. Alignment estimators"]},
            ],
        }

        with self.assertRaises(Refused) as ctx:
            self._compute(proposal)

        self.assertEqual(ctx.exception.code, "SECTION_NOT_IN_SOURCE")
        self.assertIn("9. Nothing like this exists", ctx.exception.detail)

    def test_an_ambiguous_title_refuses_before_scoring(self) -> None:
        (self.proposals / "field-survey-r07.md").write_text(
            self._CLAIMABLE_DOC.replace(
                "## 2. Alignment estimators\n\nBody.\n\n",
                "## 2. Alignment estimators\n\nBody.\n\n## 2. Alignment estimators\n\nBody.\n\n",
                1,
            ),
            encoding="utf-8",
        )

        with self.assertRaises(Refused) as ctx:
            self._compute(self._ROUND_1)

        self.assertEqual(ctx.exception.code, "SECTION_TITLE_AMBIGUOUS")
        self.assertIn("2. Alignment estimators", ctx.exception.detail)


class SeparationCorpusAnchoringTests(_SeparationCorpusMixin, unittest.TestCase):
    """Task 2.9/2.10: an assignment for a `(block, fact)` absent from the
    assembled corpus's `requires_facts` is reported, never deleted or
    invented, and contributes nothing to coverage."""

    def test_an_unanchored_assignment_is_reported_and_scores_nothing(self) -> None:
        proposal = {
            "lineage": "field-survey",
            "assignments": list(self._BRANCH_A["assignments"]) + [
                {"block": "no-such.block", "fact": "formulation",
                 "sections": ["1. Background on widget metrics"]},
            ],
        }

        result = self._compute(proposal)

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["unanchored"], [{"block": "no-such.block", "fact": "formulation"}])


class SeparationRefusalPrecedenceTests(_SeparationCorpusMixin, unittest.TestCase):
    """Task 2.11-2.14: fixed precedence `overlap -> orphan -> gap`, ONE
    refusal, and its detail names every present class plus all totals --
    two properties, two separately-checkable tests (design.md Decision E)."""

    def test_all_three_classes_present_raise_exactly_one_refusal(self) -> None:
        """Task 2.11's own explicit, separately-checkable property: never
        more than one code, even though round 1 carries defects in all
        three classes at once."""
        with self.assertRaises(Refused) as ctx:
            self._compute(self._ROUND_1)

        self.assertEqual(ctx.exception.code, "SEPARATION_SECTION_OVERLAP")

    def test_the_single_refusals_detail_names_every_class_and_every_total(self) -> None:
        """Task 2.12's own explicit, separately-checkable property: the
        SAME refusal from the test above also names every orphaned title,
        the gapped block and title, and all four counted totals -- not
        merely the overlapping title that decided which code fired. A test
        that only checked `.code` above would pass an implementation that
        silently dropped the orphan/gap detail from the message."""
        with self.assertRaises(Refused) as ctx:
            self._compute(self._ROUND_1)

        detail = ctx.exception.detail
        self.assertIn("2. Alignment estimators", detail)
        self.assertIn("3. Proposed alignment objective", detail)
        self.assertIn("5. Open problems", detail)
        self.assertIn("methods.block-b", detail)
        self.assertIn("total=4", detail)
        self.assertIn("orphan=2", detail)
        self.assertIn("overlap=1", detail)
        self.assertIn("gap=1", detail)

    def test_orphan_and_gap_with_no_overlap_raise_the_orphan_code(self) -> None:
        proposal = {
            "lineage": "field-survey",
            "assignments": [
                {"block": "methods.block-b", "fact": "formulation",
                 "sections": ["1. Background on widget metrics",
                              "3. Proposed alignment objective"]},
            ],
        }

        with self.assertRaises(Refused) as ctx:
            self._compute(proposal)

        self.assertEqual(ctx.exception.code, "SEPARATION_SECTION_ORPHANED")
        self.assertIn("2. Alignment estimators", ctx.exception.detail)

    def test_only_a_gap_raises_the_gap_code(self) -> None:
        proposal = {
            "lineage": "field-survey",
            "assignments": [
                {"block": "overview.block-a", "fact": "formulation",
                 "sections": ["1. Background on widget metrics",
                              "3. Proposed alignment objective"]},
                {"block": "methods.block-b", "fact": "formulation",
                 "sections": ["2. Alignment estimators"]},
                {"block": "methods.block-c", "fact": "formulation",
                 "sections": ["4. Calibration procedure", "5. Open problems"]},
            ],
        }

        with self.assertRaises(Refused) as ctx:
            self._compute(proposal)

        self.assertEqual(ctx.exception.code, "SEPARATION_NOTATION_GAP")

    def test_mutation_disabling_the_overlap_branch_reddens_round_1(self) -> None:
        """Reachability proof for `SEPARATION_SECTION_OVERLAP`'s own
        wiring, distinct from `paper_separation.score_cut`'s own overlap
        arithmetic (already proven in U1): if the dispatch never checked
        overlap first, round 1 would raise the orphan code instead."""
        proc = _run_against_mutant(
            '    if result["overlap"]:\n        raise Refused("SEPARATION_SECTION_OVERLAP", detail)',
            "    if False:\n        raise Refused(\"SEPARATION_SECTION_OVERLAP\", detail)",
            "tests.test_paper_writing.SeparationRefusalPrecedenceTests"
            ".test_all_three_classes_present_raise_exactly_one_refusal",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_disabling_the_orphan_branch_reddens_the_orphan_only_fixture(self) -> None:
        """Reachability proof for `SEPARATION_SECTION_ORPHANED`'s own
        wiring: disabling it falls through to the gap code instead, on a
        fixture carrying both defects."""
        proc = _run_against_mutant(
            '    if result["orphan"]:\n        raise Refused("SEPARATION_SECTION_ORPHANED", detail)',
            "    if False:\n        raise Refused(\"SEPARATION_SECTION_ORPHANED\", detail)",
            "tests.test_paper_writing.SeparationRefusalPrecedenceTests"
            ".test_orphan_and_gap_with_no_overlap_raise_the_orphan_code",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_relabeling_the_gap_code_reddens_the_gap_only_fixture(self) -> None:
        """Reachability proof for `SEPARATION_NOTATION_GAP` itself: the
        gap-only fixture must see THIS code, not a copy-pasted sibling."""
        proc = _run_against_mutant(
            'raise Refused("SEPARATION_NOTATION_GAP", detail)',
            'raise Refused("SEPARATION_SECTION_ORPHANED", detail)',
            "tests.test_paper_writing.SeparationRefusalPrecedenceTests"
            ".test_only_a_gap_raises_the_gap_code",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class SeparationUnclaimableTests(_SeparationCorpusMixin, unittest.TestCase):
    """Task 2.15/2.16: a title resolving to a real heading outside the
    claimable set, or an unmeasured claimable set, both refuse
    `SEPARATION_SECTION_UNCLAIMABLE` -- never a silent pass."""

    def test_naming_the_documents_own_title_refuses_unclaimable(self) -> None:
        proposal = {
            "lineage": "field-survey",
            "assignments": [
                {"block": "overview.block-a", "fact": "formulation",
                 "sections": ["Field Survey of Widget Alignment"]},
            ],
        }

        with self.assertRaises(Refused) as ctx:
            self._compute(proposal)

        self.assertEqual(ctx.exception.code, "SEPARATION_SECTION_UNCLAIMABLE")
        self.assertIn("Field Survey of Widget Alignment", ctx.exception.detail)

    def test_an_unmeasured_claimable_set_refuses_unclaimable_naming_the_reason(self) -> None:
        """A headingless resolved revision reports `unmeasured` BEFORE any
        per-title existence check runs -- naming ANY title against it
        refuses `SEPARATION_SECTION_UNCLAIMABLE`, never `SECTION_NOT_IN_
        SOURCE`, because there is no claimable set at all to resolve a
        title's existence against in the first place."""
        (self.proposals / "field-survey-r07.md").write_text(
            "Just prose, no headings anywhere.\n", encoding="utf-8",
        )
        proposal = {
            "lineage": "field-survey",
            "assignments": [
                {"block": "overview.block-a", "fact": "formulation", "sections": ["Anything"]},
            ],
        }

        with self.assertRaises(Refused) as ctx:
            self._compute(proposal)

        self.assertEqual(ctx.exception.code, "SEPARATION_SECTION_UNCLAIMABLE")
        self.assertIn("NO_HEADINGS", ctx.exception.detail)

    def test_mutation_disabling_the_claimability_check_reddens_the_own_title_fixture(self) -> None:
        """Reachability proof for `SEPARATION_SECTION_UNCLAIMABLE`'s own
        wiring in `compute_separation`, distinct from `paper_separation.
        claimable_sections`'s own derivation (already proven in U1): a
        title resolving to a real heading outside the claimable set must
        still be caught HERE, at the per-title loop, or it silently
        proceeds to scoring."""
        proc = _run_against_mutant(
            "            if title not in claimable_titles:",
            "            if False:",
            "tests.test_paper_writing.SeparationUnclaimableTests"
            ".test_naming_the_documents_own_title_refuses_unclaimable",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class SeparateVerbEndToEndTests(_SeparationCorpusMixin, unittest.TestCase):
    """Task 2.17/2.18: `separate` is a real, registered `paper_cli.py`
    verb, and a settled cut exits 0 naming the exact `bind` invocations --
    never recording any of them (Phase 3 lands persistence)."""

    def test_separate_is_a_registered_command(self) -> None:
        self.assertIn("separate", paper_cli.COMMANDS)
        self.assertIs(paper_cli._COMMANDS["separate"], paper_cli.cmd_separate)

    def test_a_settled_cut_exits_clean_naming_every_bind_invocation(self) -> None:
        result = self._compute(self._BRANCH_A)

        self.assertEqual(result["total"], 0)
        self.assertEqual(len(result["bind_invocations"]), 3)
        for invocation in result["bind_invocations"]:
            self.assertTrue(invocation.startswith("bind --block "))
        self.assertTrue(any("overview.block-a" in inv for inv in result["bind_invocations"]))

    def test_cmd_separate_resolves_real_paths_and_refuses_containment(self) -> None:
        outside = Path(tempfile.gettempdir()) / f"paper-writing-separate-outside-{os.getpid()}"
        args = argparse.Namespace(paper=None, sections=None, proposal=str(outside))

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_separate(args)

        self.assertEqual(ctx.exception.code, "PAPER_OUTSIDE_REPOSITORY")


class SeparationRoundPersistenceTests(_SeparationCorpusMixin, unittest.TestCase):
    """Task 3.6/3.7/3.9: `separate` records EVERY structurally-valid
    round, whatever its score, BEFORE the structural refusal fires -- and
    `concedes_to_round` naming an unrecorded round refuses
    `SEPARATION_ROUND_ABSENT`, recording nothing."""

    def test_a_round_scoring_nonzero_is_recorded_before_the_structural_refusal(self) -> None:
        with self.assertRaises(Refused) as ctx:
            self._compute(self._ROUND_1)

        self.assertEqual(ctx.exception.code, "SEPARATION_SECTION_OVERLAP")
        self.assertIn("round-1", ctx.exception.detail)

        rounds = self._read_rounds()
        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0]["round"], 1)
        self.assertEqual(rounds[0]["score"], 4)

    def test_a_settled_cut_is_also_recorded(self) -> None:
        result = self._compute(self._BRANCH_A)

        self.assertEqual(result["round"], 1)
        rounds = self._read_rounds()
        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0]["score"], 0)

    def test_conceding_to_a_nonexistent_round_refuses_round_absent_and_records_nothing(self) -> None:
        proposal = dict(self._BRANCH_A)
        proposal["concedes_to_round"] = 7

        with self.assertRaises(Refused) as ctx:
            self._compute(proposal)

        self.assertEqual(ctx.exception.code, "SEPARATION_ROUND_ABSENT")
        self.assertIn("7", ctx.exception.detail)
        self.assertEqual(self._read_rounds(), ())

    def test_mutation_treating_a_missing_round_as_scoring_zero_reddens_round_absent(self) -> None:
        """Task 3.8: a missing round scoring 0 instead of refusing (the
        concede-to-nothing case silently survives) must redden the
        `SEPARATION_ROUND_ABSENT` fixture above."""
        proc = _run_against_mutant(
            "    conceded_round = _find_separation_round(paper_dir, root_name, lineage, revision, concedes_to_round)\n"
            "    if conceded_round is None:\n"
            "        raise Refused(\n"
            '            "SEPARATION_ROUND_ABSENT",\n'
            '            f"concedes_to_round={concedes_to_round} names no recorded round for "\n'
            '            f"(root={root_name!r}, lineage={lineage!r}, revision={revision!r})",\n'
            "        )\n",
            "    conceded_round = _find_separation_round(paper_dir, root_name, lineage, revision, concedes_to_round)\n"
            "    if conceded_round is None:\n"
            '        conceded_round = {"assignments": []}\n',
            "tests.test_paper_writing.SeparationRoundPersistenceTests"
            ".test_conceding_to_a_nonexistent_round_refuses_round_absent_and_records_nothing",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_round_two_is_checkable_with_no_process_state(self) -> None:
        """Task 3.11/3.12: two genuinely separate CLI invocations, real
        subprocesses -- the first has exited entirely before the second
        starts -- the second reads round 1 back from disk alone and
        scores the concession correctly."""
        self._run_separate_subprocess(self._ROUND_1, expect_ok=False)

        conceding = dict(self._BRANCH_A)
        conceding["concedes_to_round"] = 1
        second = self._run_separate_subprocess(conceding, expect_ok=True)

        self.assertEqual(second["result"]["total"], 0)


class SeparationConcessionTests(_SeparationCorpusMixin, unittest.TestCase):
    """Task 4.1/4.6/4.7-4.10 (design.md Decision D/E, `source-separation-
    review` spec, `Requirement: A Concession Is Verified By Recomputing
    Both Cuts From Disk, Before The Structural Refusal`): `concedes_to_
    round` recomputes BOTH totals from disk, every time -- an equal or
    lower total is accepted, a strictly higher one refuses, and the
    stored `score` field is never trusted."""

    def _concede(self, cut: dict, round_number: int) -> dict:
        proposal = dict(cut)
        proposal["concedes_to_round"] = round_number
        return proposal

    def test_a_concession_that_reaches_zero_is_accepted(self) -> None:
        try:
            self._compute(self._ROUND_1)  # records round 1, scoring 4, and refuses
        except Refused:
            pass  # round 1's own refusal is already asserted by SeparationRoundPersistenceTests

        result = self._compute(self._concede(self._BRANCH_A, 1))

        self.assertEqual(result["total"], 0)

    def test_a_concession_that_scores_worse_refuses_naming_both_totals(self) -> None:
        try:
            self._compute(self._ROUND_1)
        except Refused:
            pass  # round 1 records and refuses on structure; expected

        with self.assertRaises(Refused) as ctx:
            self._compute(self._concede(self._BRANCH_B, 1))

        self.assertEqual(ctx.exception.code, "SEPARATION_CONCESSION_REGRESSED")
        self.assertIn("4", ctx.exception.detail)
        self.assertIn("5", ctx.exception.detail)
        # A regressed concession is never recorded (task 3.9/4.10): only
        # round 1 exists afterward.
        self.assertEqual(len(self._read_rounds()), 1)

    def test_an_equal_total_concession_is_accepted_but_still_hits_structural_refusal(self) -> None:
        """Task 4.1's own third case: a TIE is not a regression, yet the
        cut is still nonzero, so it must still reach the structural
        refusal next -- exactly the pass-through 4.3 proves."""
        try:
            self._compute(self._ROUND_1)
        except Refused:
            pass

        with self.assertRaises(Refused) as ctx:
            self._compute(self._concede(self._TIE_SWAP, 1))

        self.assertNotEqual(ctx.exception.code, "SEPARATION_CONCESSION_REGRESSED")
        self.assertEqual(ctx.exception.code, "SEPARATION_SECTION_OVERLAP")
        self.assertEqual(len(self._read_rounds()), 2)

    def test_mutation_off_by_one_weakening_survives_a_four_to_five_jump(self) -> None:
        """Task 4.6: `submitted > prior` weakened to `submitted > prior +
        1` must still catch a jump from 4 to 5 -- a lock that only catches
        a LARGE jump is not the lock this requirement demands."""
        proc = _run_against_mutant(
            'if result["total"] > conceded_result["total"]:',
            'if result["total"] > conceded_result["total"] + 1:',
            "tests.test_paper_writing.SeparationConcessionTests"
            ".test_a_concession_that_scores_worse_refuses_naming_both_totals",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_a_tampered_stored_score_does_not_change_the_refusal(self) -> None:
        """Task 4.7/4.8: round 1's stored `score` overwritten to 0 on
        disk, its `assignments` unchanged -- a conceding cut scoring 5
        still refuses, naming 4 (recomputed from `assignments`) and 5,
        never the tampered 0."""
        try:
            self._compute(self._ROUND_1)
        except Refused:
            pass
        self._tamper_round_score(1, 0)
        tampered = self._read_rounds()
        self.assertEqual(tampered[0]["score"], 0)

        with self.assertRaises(Refused) as ctx:
            self._compute(self._concede(self._BRANCH_B, 1))

        self.assertEqual(ctx.exception.code, "SEPARATION_CONCESSION_REGRESSED")
        self.assertIn("4", ctx.exception.detail)
        self.assertIn("5", ctx.exception.detail)
        self.assertNotIn("scores 0", ctx.exception.detail)

    def test_mutation_reading_the_stored_score_instead_of_recomputing(self) -> None:
        """Task 4.9: the comparison mutated to trust the stored `score`
        field (freshly tampered to 0 by 4.7's own fixture, real score 4)
        instead of recomputing from `assignments` -- the message no
        longer names 4, so the fixture above goes red."""
        proc = _run_against_mutant(
            "    conceded_claims, _unanchored = _claims_by_block(conceded_round[\"assignments\"], corpus)\n"
            '    conceded_result = paper_separation.score_cut(claimable["titles"], conceded_claims)\n',
            "    conceded_claims, _unanchored = _claims_by_block(conceded_round[\"assignments\"], corpus)\n"
            '    conceded_result = {"total": conceded_round["score"]}\n',
            "tests.test_paper_writing.SeparationConcessionTests"
            ".test_a_tampered_stored_score_does_not_change_the_refusal",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_a_regressed_concession_resubmitted_identically_refuses_with_no_round_growth(self) -> None:
        """Task 4.10: extends 3.9's own round-count assertions to a
        REFUSED resubmission -- a regressed concession is never recorded,
        so resubmitting it identically must refuse the same way with no
        growth in round count."""
        try:
            self._compute(self._ROUND_1)
        except Refused:
            pass

        branch_b = self._concede(self._BRANCH_B, 1)

        for _ in range(2):
            with self.assertRaises(Refused) as ctx:
                self._compute(branch_b)
            self.assertEqual(ctx.exception.code, "SEPARATION_CONCESSION_REGRESSED")

        self.assertEqual(len(self._read_rounds()), 1)


class SeparationConcessionOrderingTests(_SeparationCorpusMixin, unittest.TestCase):
    """Task 4.3/4.4/4.5 (design.md Decision E): the concession check runs
    BEFORE the structural refusal. Reversed, `SEPARATION_CONCESSION_
    REGRESSED` becomes a refusal that cannot fire -- only a score-0 cut
    could ever reach it."""

    def test_the_concession_check_passes_a_nonregressed_cut_through_to_the_structural_refusal(
        self,
    ) -> None:
        try:
            self._compute(self._ROUND_1)
        except Refused:
            pass

        with self.assertRaises(Refused) as ctx:
            self._compute(self._concede(self._TIE_SWAP, 1))

        # If the concession check MASKED the structural refusal (ran
        # after it, or swallowed a nonregressed tie into a bare success),
        # this would never raise a structural code at all.
        self.assertEqual(ctx.exception.code, "SEPARATION_SECTION_OVERLAP")

    def _concede(self, cut: dict, round_number: int) -> dict:
        proposal = dict(cut)
        proposal["concedes_to_round"] = round_number
        return proposal

    def test_mutation_running_the_structural_refusal_first_makes_the_concession_check_unreachable(
        self,
    ) -> None:
        """Task 4.4's own load-bearing proof: swap the call order so the
        structural refusal runs BEFORE the concession check -- the
        `SEPARATION_CONCESSION_REGRESSED` fixture from `SeparationConcessionTests`
        becomes structurally unreachable, since `_raise_separation_refusal`
        always raises first for any nonzero total, and a branch-B-style
        cut (total 5) never reaches the concession check at all."""
        proc = _run_against_mutant(
            '    _check_separation_concession(\n'
            '        paper_dir, root.name, lineage, revision, concedes_to_round, result, claimable, corpus,\n'
            '    )\n'
            '    recorded_round = paper_declarations.record_separation_round(\n'
            '        paper_dir, root.name, lineage, revision, document_digest, assignments, result["total"],\n'
            '    )\n'
            '    if result["total"] == 0:\n'
            '        return {\n'
            '            "total": 0, "unanchored": unanchored,\n'
            '            "bind_invocations": [_bind_invocation(entry, lineage) for entry in assignments],\n'
            '            "round": recorded_round["round"], "round_id": recorded_round["id"],\n'
            '        }\n'
            '    _raise_separation_refusal(result, recorded_round["id"])\n',
            '    recorded_round = paper_declarations.record_separation_round(\n'
            '        paper_dir, root.name, lineage, revision, document_digest, assignments, result["total"],\n'
            '    )\n'
            '    if result["total"] == 0:\n'
            '        return {\n'
            '            "total": 0, "unanchored": unanchored,\n'
            '            "bind_invocations": [_bind_invocation(entry, lineage) for entry in assignments],\n'
            '            "round": recorded_round["round"], "round_id": recorded_round["id"],\n'
            '        }\n'
            '    _raise_separation_refusal(result, recorded_round["id"])\n'
            '    _check_separation_concession(\n'
            '        paper_dir, root.name, lineage, revision, concedes_to_round, result, claimable, corpus,\n'
            '    )\n',
            "tests.test_paper_writing.SeparationConcessionTests"
            ".test_a_concession_that_scores_worse_refuses_naming_both_totals",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


def _record_kinds_reachable_from(root_name: str) -> set:
    """`declarations`-region record KINDS (`_set_record`'s own `kind=`
    keyword argument) reachable from `root_name`'s own call graph, across
    BOTH `paper_cli.py` and `paper_declarations.py` -- the two modules the
    writer path actually spans (task 3.13, Decision F/G's AST proof).
    Never a hand-listed set: a future call from `cmd_separate` into a
    THIRD kind lands here the moment the AST sees it, the identical shape
    `reachable_paper_refusal_codes` above already uses for refusal codes,
    applied to record kinds instead."""
    definitions: dict = {}
    for path in (SKILL_SCRIPTS / "paper_cli.py", SKILL_SCRIPTS / "paper_declarations.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                definitions[node.name] = node

    def _callee_name(func):
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None

    kinds: set = set()
    seen: set = set()
    frontier = [root_name]
    while frontier:
        name = frontier.pop()
        if name in seen or name not in definitions:
            continue
        seen.add(name)
        for call in ast.walk(definitions[name]):
            if not isinstance(call, ast.Call):
                continue
            callee = _callee_name(call.func)
            if callee is None:
                continue
            if callee == "_set_record":
                for kw in call.keywords:
                    if kw.arg == "kind" and isinstance(kw.value, ast.Constant):
                        kinds.add(kw.value.value)
            if callee in definitions:
                frontier.append(callee)
    return kinds


class SeparateNeverRecordsABindingASTTests(unittest.TestCase):
    """Task 3.13/3.14 (design.md Decision F/G): the set of `declarations`-
    region record kinds reachable from `cmd_separate`'s own call graph is
    EXACTLY `{"separation"}` -- `separate` never records a `binding`
    under any outcome, derived from source rather than asserted by hand."""

    def test_cmd_separate_reaches_only_the_separation_kind(self) -> None:
        self.assertEqual(_record_kinds_reachable_from("cmd_separate"), {"separation"})

    def test_cmd_bind_reaches_the_binding_kind_as_a_sanity_check_on_the_walk_itself(self) -> None:
        """The derivation itself is exercised against a KNOWN positive:
        `cmd_bind`'s own call graph must still show `binding`, or this
        walk would trivially pass by never finding anything at all."""
        self.assertEqual(_record_kinds_reachable_from("cmd_bind"), {"binding"})


class SeparateNeverRecordsABindingEndToEndTests(unittest.TestCase):
    """Task 3.16/3.17 (Decision G): a settled `separate` cut exits 0,
    names the exact `bind` invocation for its one assignment, and records
    no `binding` -- `write` still refuses `SECTION_BINDING_ABSENT` until
    an operator actually runs `bind`. Rooted under
    `FORGE_ROOT/.scratch/`, the same containment `BindCliEndToEndTests`
    already requires."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-separate-e2e-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        blocks = [{
            "id": "only",
            "requires_facts": [{
                "value": "formulation",
                "source": {"file": "sections/a.md", "quote": "The formulation, written here."},
            }],
            "requires_declarations": [], "citations": "none",
        }]
        (self.sections_dir / "a.md").write_text(
            "---\n" + json.dumps({"section": "a", "position": 1, "blocks": blocks})
            + "\n---\n\nThe formulation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        self.proposals = self.test_root / "proposals"
        self.proposals.mkdir()
        (self.proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}),
            encoding="utf-8",
        )
        (self.proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n", encoding="utf-8",
        )

    def _write_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="a", block="only",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=None,
        )

    def _proposal_path(self, obj) -> Path:
        path = self.test_root / "proposal.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def _settled_proposal(self) -> dict:
        return {
            "lineage": "lumen-thesis",
            "assignments": [
                {"block": "a.only", "fact": "formulation",
                 "sections": ["1. Intro", "3. Something"]},
            ],
        }

    def test_a_settled_separation_records_no_binding_and_write_still_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self._write_args())
        self.assertEqual(ctx.exception.code, "SECTION_BINDING_ABSENT")

        result = paper_cli.compute_separation(
            self._proposal_path(self._settled_proposal()),
            sections_dir=self.sections_dir, paper_dir=self.paper_dir, source_base=self.test_root,
        )

        self.assertEqual(result["total"], 0)
        self.assertEqual(len(result["bind_invocations"]), 1)
        self.assertIn("a.only", result["bind_invocations"][0])

        self.assertEqual(paper_declarations.read_bindings(self.paper_dir), {})

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self._write_args())
        self.assertEqual(ctx.exception.code, "SECTION_BINDING_ABSENT")

    def test_mutation_recording_a_binding_kind_reddens_the_settled_e2e_test(self) -> None:
        """Task 3.15's own runtime reachability proof, alongside the AST
        proof above: if the round writer persisted `kind='binding'`
        instead of `kind='separation'`, this e2e's own assertions must
        fail -- either `write` proceeds past its gate, or `read_bindings`
        chokes on a `binding`-kind record with no `block`/`fact` of its
        own, since a settled separation carries no such fields."""
        proc = _run_against_mutant(
            'kind="separation", id_=id_, value_field="revision", value=revision, clock=clock,',
            'kind="binding", id_=id_, value_field="revision", value=revision, clock=clock,',
            "tests.test_paper_writing.SeparateNeverRecordsABindingEndToEndTests"
            ".test_a_settled_separation_records_no_binding_and_write_still_refuses",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class WriteGateReturnsCorpusTests(unittest.TestCase):
    """`transposition-fidelity` spec's own prerequisite plumbing (design.md
    Decision E, tasks.md 1.2-1.3): `_resolve_write_gate` already builds the
    `Corpus` its own `assemble_corpus(..., enforce_bindings=True)` call
    returns, and until now discarded it. `cmd_write` cannot fill
    `BlockContract.source_sections` from a corpus it was never handed back."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-write-gate-return-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        blocks = [
            {"id": "a", "requires_facts": [], "requires_declarations": [], "citations": "none"},
        ]
        (self.sections_dir / "01-a.md").write_text(
            "---\n" + json.dumps({"section": "phase-a", "position": 1, "blocks": blocks})
            + "\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )

    def test_resolve_write_gate_returns_the_assembled_corpus(self) -> None:
        corpus = paper_cli._resolve_write_gate(self.paper_dir, self.sections_dir, "phase-a.a")

        self.assertIsInstance(corpus, paper_graph.Corpus)
        self.assertIn("phase-a.a", corpus.blocks)

    def test_resolve_write_gate_returns_the_corpus_off_the_early_return_branch_too(self) -> None:
        """A `qualified_id` the corpus's own waves do not contain (a
        typo'd `--section`/`--block`, never declared anywhere) takes the
        EARLY `return` inside `_resolve_write_gate` -- design.md Decision
        E's own return value must hold on that branch too, not only the
        gated one."""
        corpus = paper_cli._resolve_write_gate(self.paper_dir, self.sections_dir, "no-such.block")

        self.assertIsInstance(corpus, paper_graph.Corpus)


class ResolveBoundSectionsTests(unittest.TestCase):
    """`transposition-fidelity` spec's own prerequisite plumbing (design.md
    Decision E, tasks.md 1.4-1.5): `paper_source_span.resolve_bound_
    sections` turns a block's own `(fact, lineage, title)` triples into
    the bound section's own bytes, via the landed `paper_graph.resolve_
    section_index` -- never a second, independent resolution."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-resolve-bound-sections-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        self.proposals = self.test_root / "proposals"
        self.proposals.mkdir()
        (self.proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}),
            encoding="utf-8",
        )
        (self.proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\nOpening prose.\n\n# 3. Something\n\nThe body of the third heading.\n",
            encoding="utf-8",
        )

    def _corpus(self, entry: dict) -> "paper_graph.Corpus":
        blocks = [{
            "id": "only", "requires_facts": [entry],
            "requires_declarations": [], "citations": "none",
        }]
        (self.sections_dir / "01-a.md").write_text(
            "---\n" + json.dumps({"section": "a", "position": 1, "blocks": blocks})
            + "\n---\n\nThe formulation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        return paper_graph.assemble_corpus(self.sections_dir, paper_dir=self.paper_dir)

    def test_a_bound_section_resolves_its_own_span(self) -> None:
        corpus = self._corpus({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
            "document": {"lineage": "lumen-thesis", "section": "3. Something"},
        })

        resolved = paper_source_span.resolve_bound_sections(corpus, "a.only")

        self.assertEqual(len(resolved), 1)
        entry = resolved[0]
        self.assertEqual(entry["fact"], "formulation")
        self.assertEqual(entry["lineage"], "lumen-thesis")
        self.assertEqual(entry["title"], "3. Something")
        self.assertEqual(entry["path"], str(self.proposals / "lumen-thesis-r21.md"))
        self.assertIn("The body of the third heading.", entry["text"])
        self.assertNotIn("Opening prose.", entry["text"])
        body_bytes = (self.proposals / "lumen-thesis-r21.md").read_bytes()
        self.assertEqual(
            body_bytes[entry["byte_start"]:entry["byte_end"]].decode("utf-8"), entry["text"],
        )

    def test_a_block_with_no_document_binding_resolves_nothing(self) -> None:
        corpus = self._corpus({
            "value": "formulation",
            "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
        })

        resolved = paper_source_span.resolve_bound_sections(corpus, "a.only")

        self.assertEqual(resolved, ())


class CmdWriteSourceSectionsWiringTests(unittest.TestCase):
    """`transposition-fidelity` spec's own prerequisite plumbing (design.md
    Decision E, tasks.md 1.8, 1.10): `cmd_write` must actually pass the
    resolved bound sections into `BlockContract.source_sections`, never
    merely resolve them and discard the result -- the exact defect this
    change closes in `_resolve_write_gate` itself. Mocks `paper_write.
    write_block` (never `paper_source_span.resolve_bound_sections`), so
    the REAL corpus, REAL resolution and REAL CLI wiring all run; only the
    drafting pipeline past that point is stubbed out."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-cmd-write-source-sections-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        blocks = [{
            "id": "only",
            "requires_facts": [{
                "value": "formulation",
                "source": {"file": "sections/a.md", "quote": "The formulation, written here."},
                "document": {"lineage": "lumen-thesis", "section": "3. Something"},
            }],
            "requires_declarations": [], "citations": "none",
        }]
        # `cmd_write` resolves a block's own contract file as literally
        # `sections/<section-id>.md` (`section_path = sections_dir /
        # f"{args.section}.md"`), unlike `assemble_corpus`'s own `*.md`
        # glob -- named `a.md` here, matching `args.section="a"`, the same
        # precedent `BindCliEndToEndTests` above already established.
        (self.sections_dir / "a.md").write_text(
            "---\n" + json.dumps({"section": "a", "position": 1, "blocks": blocks})
            + "\n---\n\nThe formulation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        self.proposals = self.test_root / "proposals"
        self.proposals.mkdir()
        (self.proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}),
            encoding="utf-8",
        )
        (self.proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\nOpening prose.\n\n# 3. Something\n\nThe body of the third heading.\n",
            encoding="utf-8",
        )
        (self.test_root / "draft.json").write_text(
            json.dumps({"latex": "Draft body.", "bindings": []}), encoding="utf-8",
        )
        (self.test_root / "audit.json").write_text(json.dumps({"verdicts": []}), encoding="utf-8")

    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="a", block="only",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=None,
        )

    def test_cmd_write_fills_source_sections_from_the_resolved_corpus(self) -> None:
        with unittest.mock.patch("paper_write.write_block") as mocked_write_block:
            mocked_write_block.return_value = {"status": "written"}
            paper_cli.cmd_write(self._args())

        contract = mocked_write_block.call_args[0][1]
        self.assertEqual(len(contract.source_sections), 1)
        section = contract.source_sections[0]
        self.assertEqual(section["fact"], "formulation")
        self.assertEqual(section["lineage"], "lumen-thesis")
        self.assertEqual(section["title"], "3. Something")
        self.assertIn("The body of the third heading.", section["text"])


class CmdWriteSourceSectionsWiringMutationProofTests(unittest.TestCase):
    """tasks.md 1.10: forcing `cmd_write` to always pass
    `source_sections=()` regardless of what `resolve_bound_sections`
    resolved must fail `CmdWriteSourceSectionsWiringTests.test_cmd_write_
    fills_source_sections_from_the_resolved_corpus` -- proving the
    resolved bindings actually have to arrive at `BlockContract` for
    anything to change. Re-used, not duplicated, by WU2's own 'the
    resolved bindings really arrive' mutation once the verdict logic
    exists (design.md, Testing Strategy table)."""

    def test_mutation_forcing_empty_source_sections_fails_the_wiring_test(self) -> None:
        proc = _run_against_mutant(
            "        source_sections=paper_source_span.resolve_bound_sections(corpus, qualified_id),\n",
            "        source_sections=(),\n",
            "tests.test_paper_writing.CmdWriteSourceSectionsWiringTests"
            ".test_cmd_write_fills_source_sections_from_the_resolved_corpus",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class BlockContractSourceSectionsDefaultTests(unittest.TestCase):
    """tasks.md 1.7: `BlockContract.source_sections` is defaulted, the same
    `produces_facts`/`source_bindings` precedent, so every existing
    `BlockContract(...)` construction site in this suite stays green with
    no change of its own."""

    def test_source_sections_defaults_to_an_empty_tuple(self) -> None:
        contract = _write_contract(citations_regime="none")

        self.assertEqual(contract.source_sections, ())


class PythonFloorGuardTests(unittest.TestCase):
    """Item 4, `limpieza-de-pendientes-chicos`: this skill claimed
    stdlib-only and gave no floor anywhere -- a user on an older
    interpreter got whatever bare traceback the first unavailable feature
    happened to raise, naming a module they never asked about. `main`'s
    own front door now refuses `PYTHON_VERSION_UNSUPPORTED` by name before
    any command runs.

    `SKILL_PYTHON_FLOOR = (3, 7)` is MEASURED, not picked: every one of the
    31 shipped `paper_*.py` modules (and the shared `impl_refusals.py`)
    opens with `from __future__ import annotations` (PEP 563, 3.7+), the
    highest-versioned feature any of them use -- no walrus operator, no
    `match`/`case`, no PEP 604 `X | Y` outside an annotation, no dict-union
    `|`, no `str.removeprefix`/`removesuffix`, scanned for across every
    shipped script and found nowhere.

    A pre-3.7 interpreter cannot even PARSE `paper_cli.py` to reach this
    check (`from __future__ import annotations` is itself the 3.7+ syntax
    feature), so the comparison can only be proven by telling a real,
    fully-capable interpreter that it is older -- `sys.version_info`
    patched for the duration of one call, restored immediately after.
    """

    def test_an_interpreter_at_the_floor_is_accepted(self) -> None:
        with unittest.mock.patch.object(
            paper_cli.sys, "version_info", paper_cli.SKILL_PYTHON_FLOOR,
        ):
            paper_cli._require_supported_python()  # must not raise

    def test_an_interpreter_above_the_floor_is_accepted(self) -> None:
        above = (paper_cli.SKILL_PYTHON_FLOOR[0], paper_cli.SKILL_PYTHON_FLOOR[1] + 5)
        with unittest.mock.patch.object(paper_cli.sys, "version_info", above):
            paper_cli._require_supported_python()  # must not raise

    def test_an_interpreter_below_the_floor_refuses_by_name(self) -> None:
        below = (paper_cli.SKILL_PYTHON_FLOOR[0], paper_cli.SKILL_PYTHON_FLOOR[1] - 1)
        with unittest.mock.patch.object(paper_cli.sys, "version_info", below):
            with self.assertRaises(paper_cli.Refused) as ctx:
                paper_cli._require_supported_python()
        self.assertEqual(ctx.exception.code, "PYTHON_VERSION_UNSUPPORTED")
        self.assertIn("3.6", ctx.exception.detail)
        self.assertIn("3.7", ctx.exception.detail)

    def test_main_itself_refuses_before_dispatching_any_command(self) -> None:
        """The check runs inside `main()`, ahead of argument parsing and
        every `cmd_*` dispatch -- proven by an invocation (`status` with no
        `--paper`) that would otherwise run to a different, unrelated
        refusal or a real read, never reaching this one unless the version
        check truly sits first."""
        below = (paper_cli.SKILL_PYTHON_FLOOR[0], paper_cli.SKILL_PYTHON_FLOOR[1] - 1)
        with unittest.mock.patch.object(paper_cli.sys, "version_info", below):
            exit_code = paper_cli.main(["status"])
        self.assertEqual(exit_code, 2)


class PythonFloorGuardMutationTests(unittest.TestCase):
    """RED-first proof the comparison is load-bearing: disabling it must
    fail `PythonFloorGuardTests.test_an_interpreter_below_the_floor_
    refuses_by_name` -- a passing test beside an unexercised guard is not a
    mutation that ran."""

    def test_mutation_disabling_the_comparison_fails_the_refusal_test(self) -> None:
        proc = _run_against_mutant(
            "    if current < SKILL_PYTHON_FLOOR:\n",
            "    if False:\n",
            "tests.test_paper_writing.PythonFloorGuardTests"
            ".test_an_interpreter_below_the_floor_refuses_by_name",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class MarkRevisionsCliWholeLoopTests(unittest.TestCase):
    """`specs/source-declaration-authoring/spec.md`, Acceptance Criteria:
    "Both marker kinds gain a writer reachable only by using the skill" --
    the whole loop `SOURCE_REVISIONS_UNDECLARED` exists to enable: `write`
    refuses, `mark revisions` (a REAL CLI invocation, never a direct Python
    call -- the CLI wiring itself is what this test proves) answers it,
    `write` proceeds past that gate (tasks.md 2.23)."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-mark-revisions-loop-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        blocks = [{
            "id": "only",
            "requires_facts": [{
                "value": "formulation",
                "source": {"file": "sections/01-a.md", "quote": "The formulation, written here."},
                "document": {"lineage": "lumen-thesis", "section": "1. Intro"},
            }],
            "requires_declarations": [], "citations": "none",
        }]
        (self.sections_dir / "01-a.md").write_text(
            "---\n" + json.dumps({"section": "a", "position": 1, "blocks": blocks})
            + "\n---\n\nThe formulation, written here.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        self.proposals = self.test_root / "proposals"
        self.proposals.mkdir()
        (self.proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")

    def _write_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="a", block="only",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=None,
        )

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        """The SAME confirmed CLI-shelling shape `_cli_shelling_run_helper_
        names` recognizes elsewhere in this file (`test_paper_contract.
        VerbFrontDoorCoverageTests`'s own AST scan) -- `mark revisions`'s
        CLI wiring is a front door, proven through a REAL subprocess, never
        a direct Python call to `paper_declarations.declare_revisions`."""
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            capture_output=True, text=True, timeout=30,
        )

    def test_write_refuses_then_mark_revisions_then_write_proceeds(self) -> None:
        # 1. `write` refuses -- `proposals/` is document-rooted, no marker.
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self._write_args())
        self.assertEqual(ctx.exception.code, "SOURCE_REVISIONS_UNDECLARED")

        # 2. `mark revisions` answers it -- a REAL subprocess CLI
        #    invocation, never a direct call to `paper_declarations.
        #    declare_revisions`, so the CLI wiring itself (the argparse
        #    subparser, `cmd_mark`, `cmd_mark_revisions`) is what is proven.
        proc = self._run(
            "mark", "revisions", "--paper", str(self.paper_dir), "--root", "proposals",
            "--revision-prefix", "r", "--ordinal-digits", "2",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["root"], "proposals")
        self.assertEqual(payload["matched"], ["lumen-thesis-r21.md"])
        self.assertEqual(payload["unmatched"], [])
        self.assertTrue(payload["sealed"])
        self.assertTrue((self.proposals / ".paper-writing.json").is_file())

        # 3. `write` no longer refuses `SOURCE_REVISIONS_UNDECLARED` -- it
        #    proceeds past the marker gate, all the way to trying to open
        #    the never-created `--draft`.
        with self.assertRaises((Refused, FileNotFoundError)) as ctx:
            paper_cli.cmd_write(self._write_args())
        if isinstance(ctx.exception, Refused):
            self.assertNotEqual(ctx.exception.code, "SOURCE_REVISIONS_UNDECLARED")

        # `sections/01-a.md` is never touched by any of this.
        prose = (self.sections_dir / "01-a.md").read_text(encoding="utf-8")
        self.assertNotIn("seal_sha256", prose)

    def test_mark_revisions_refuses_a_declared_width_matching_nothing_on_disk(self) -> None:
        proc = self._run(
            "mark", "revisions", "--paper", str(self.paper_dir), "--root", "proposals",
            "--revision-prefix", "v", "--ordinal-digits", "3",
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "SOURCE_DECLARATION_UNMATCHED")
        self.assertIn("v", payload["detail"])
        self.assertIn("3", payload["detail"])
        self.assertIn("lumen-thesis-r21.md", payload["detail"])
        self.assertFalse((self.proposals / ".paper-writing.json").exists())

    def test_mark_revisions_refuses_a_non_declarable_root(self) -> None:
        proc = self._run(
            "mark", "revisions", "--paper", str(self.paper_dir), "--root", "implementation",
            "--revision-prefix", "r", "--ordinal-digits", "2",
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "SOURCE_ROOT_UNDECLARABLE")
        self.assertIn("proposals", payload["detail"])
        self.assertIn("experiments", payload["detail"])

    def test_mark_revisions_unsealed_writes_no_seal_key(self) -> None:
        proc = self._run(
            "mark", "revisions", "--paper", str(self.paper_dir), "--root", "proposals",
            "--revision-prefix", "r", "--ordinal-digits", "2", "--unsealed",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["sealed"])
        on_disk = json.loads((self.proposals / ".paper-writing.json").read_text(encoding="utf-8"))
        self.assertNotIn(paper_marker.SEAL_KEY, on_disk)

    def test_re_recording_a_hand_edited_marker_always_succeeds(self) -> None:
        """`specs/source-declaration-authoring/spec.md`, `Requirement:
        Re-Recording Always Succeeds; There Is No Stuck State` -- no
        `--reopen`/`--adopt`, and a hand-edited sealed marker is cleared by
        re-running the verb, never by hand-editing the file."""
        marker_path = self.proposals / ".paper-writing.json"
        marker_path.write_text(
            json.dumps({
                "revisions": {"revision_prefix": "r", "ordinal_digits": 2},
                paper_marker.SEAL_KEY: "a" * 64,
            }),
            encoding="utf-8",
        )

        proc = self._run(
            "mark", "revisions", "--paper", str(self.paper_dir), "--root", "proposals",
            "--revision-prefix", "r", "--ordinal-digits", "2",
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        on_disk = json.loads(marker_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk[paper_marker.SEAL_KEY], paper_marker.computed_seal(on_disk))


class PlanSourceRootsTests(unittest.TestCase):
    """`specs/source-declaration-authoring/spec.md`, `Requirement: The
    Position Report Names Every Declarable Root's And Every Guidance
    Folder's Declaration State`: `compute_plan`'s own return value carries
    a `sourceRoots` key -- asserted here by CALLING `compute_plan` and
    reading what it returns, never by asserting a field exists on `Corpus`
    alone (the exact failure mode of the archived predecessor's
    false-ticked `tasks.md` item 2.14, which claimed `Corpus.source_roots`
    was already "echoed by every corpus-reading verb" while, measured by
    running `plan`, `phases`, and `contract`, none of the three rendered it
    at all)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.guidance_dir = self.forge_root / "guidance"

    def test_compute_plan_carries_a_sourceRoots_entry_per_root(self) -> None:
        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        self.assertIn("sourceRoots", report)
        expected_names = {root.name for root in paper_declarations.FACT_SOURCE_ROOT.values()}
        self.assertEqual(set(report["sourceRoots"]), expected_names)
        for entry in report["sourceRoots"].values():
            self.assertEqual(set(entry), {"state", "documents", "reason", "declaration"})

    def test_a_prose_root_with_no_marker_reports_undeclared(self) -> None:
        proposals = self.forge_root / "proposals"
        proposals.mkdir()
        (proposals / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")

        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        self.assertEqual(report["sourceRoots"]["proposals"]["declaration"], "undeclared")

    def test_a_malformed_marker_refuses_through_the_position_verb(self) -> None:
        """`specs/source-declaration-authoring/spec.md`, `Requirement: Absence
        Is A Reported State; A Broken Seal Refuses Where The Marker Is Read`,
        scenario `A malformed marker still refuses through the position verb`.

        Absence and malformation are different outcomes and must stay
        different: an unfilled root REPORTS `undeclared` and `plan` succeeds,
        while a marker that does not parse REFUSES and `plan` does not return
        a report at all. Collapsing the two would let a broken declaration
        read as an unfilled one, and the operator would see a root waiting to
        be declared rather than one whose declaration is unreadable.

        The verify pass that closed this change flagged this scenario as
        behaviourally correct but carried by NO test -- the exact shape that
        let this change's own predecessor ship a ticked task whose work was
        half done. Asserted here by calling the reporting verb and reading
        what it does, never by asserting the reader alone refuses.
        """
        proposals = self.forge_root / "proposals"
        proposals.mkdir()
        (proposals / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        (proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r",
                                      "ordinal_digits": "two"}}),
            encoding="utf-8")

        with self.assertRaises(Refused) as caught:
            paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        self.assertEqual(caught.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn("ordinal_digits", caught.exception.detail)

    def test_a_prose_root_with_a_valid_unsealed_marker_reports_declared_unsealed(self) -> None:
        """S2 widens the three-value vocabulary `declared` split into
        `declared-sealed`/`declared-unsealed` (design.md Decision C/I;
        `specs/source-declaration-authoring/spec.md`, `Requirement: Absence
        Is A Reported State; A Broken Seal Refuses Where The Marker Is
        Read`) -- a marker written before sealing existed carries no
        `seal_sha256` key and reports `declared-unsealed`, never a
        refusal."""
        proposals = self.forge_root / "proposals"
        proposals.mkdir()
        (proposals / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        (proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}),
            encoding="utf-8",
        )

        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        self.assertEqual(report["sourceRoots"]["proposals"]["declaration"], "declared-unsealed")

    def test_a_prose_root_with_a_valid_sealed_marker_reports_declared_sealed(self) -> None:
        proposals = self.forge_root / "proposals"
        proposals.mkdir()
        (proposals / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        obj = {"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}
        obj[paper_marker.SEAL_KEY] = paper_marker.computed_seal(obj)
        (proposals / ".paper-writing.json").write_text(json.dumps(obj), encoding="utf-8")

        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        self.assertEqual(report["sourceRoots"]["proposals"]["declaration"], "declared-sealed")

    def test_a_non_prose_root_reports_n_a_by_kind(self) -> None:
        implementation_kind = paper_declarations.FACT_SOURCE_ROOT["implementation"].kind
        self.assertEqual(implementation_kind, paper_declarations.SourceRootKind.REPOSITORY)

        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        self.assertEqual(report["sourceRoots"]["implementation"]["declaration"], "n/a")

    def test_a_sixth_prose_root_widens_the_report_with_zero_engine_edit(self) -> None:
        sixth = paper_declarations.SourceRoot(
            "invented-sixth-prose-root", paper_declarations.SourceRootKind.PROSE,
        )
        with unittest.mock.patch.dict(
            paper_declarations.FACT_SOURCE_ROOT, {"invented-sixth-fact": sixth},
        ):
            report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        self.assertIn(sixth.name, report["sourceRoots"])
        self.assertEqual(report["sourceRoots"][sixth.name]["declaration"], "undeclared")


class WriteBlockConsumesEvidenceAuditBindingsTests(unittest.TestCase):
    """`the-block-asserts-only-what-its-section-carries`, Phase 0, tasks
    0.2/0.3 (design.md D4 `[re-measured]`): `_stage_evidence_audit` already
    returns `list[Binding]` (`paper_write.py:121`, `return bindings` at
    `:129`) and has exactly one caller, where the value used to be dropped
    on the floor as a bare statement. This asserts the CALL SITE actually
    assigns the return value rather than merely running the call for its
    side effects -- the shape that lets a later stage (this phase's own
    subject derivation) use the bindings `_stage_evidence_audit` already
    produces instead of segmenting the draft a second time (D4's own
    rejected alternative)."""

    def test_the_call_site_assigns_the_return_value_not_a_bare_statement(self) -> None:
        source = (SKILL_SCRIPTS / "paper_write.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        write_block = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "write_block"
        )

        def calls_stage_evidence_audit(node) -> bool:
            return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_stage_evidence_audit")

        bare_statement_calls = [
            stmt for stmt in write_block.body
            if isinstance(stmt, ast.Expr) and calls_stage_evidence_audit(stmt.value)
        ]
        assigned_calls = [
            stmt for stmt in write_block.body
            if isinstance(stmt, ast.Assign) and calls_stage_evidence_audit(stmt.value)
        ]
        self.assertEqual(
            bare_statement_calls, [],
            "_stage_evidence_audit's return value is dropped as a bare statement",
        )
        self.assertEqual(
            len(assigned_calls), 1,
            "write_block must call _stage_evidence_audit exactly once, assigning "
            "its return value to a name a later stage can use",
        )

    def test_a_fixture_with_a_bound_sentence_still_writes_after_the_fix(self) -> None:
        """Runtime companion, task 0.3's own fixture requirement: a real
        `write_block` call, with a fixture carrying at least one `fact:`-
        bound sentence, still reaches `"status": "written"` once the call
        site keeps the bindings rather than dropping them -- the fix
        changes no observable behaviour for a block this phase does not
        yet gate on subjects (no `source_sections` bound)."""
        with tempfile.TemporaryDirectory() as tmp:
            paper_dir = Path(tmp) / "paper"
            _write_fixture(paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))
            contract = _write_contract(
                citations_regime="none", evidence_set=(),
                requires_facts=("calibration-regime",),
            )
            draft = {
                "latex": "The device holds calibration steady across trials.",
                "bindings": [
                    {
                        "sentence": "The device holds calibration steady across trials.",
                        "binding": "fact:calibration-regime",
                    }
                ],
            }
            result = paper_write.write_block(paper_dir, contract, draft, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")


class WriteBlockGroundingAccountKeywordTests(unittest.TestCase):
    """Task 0.4: `grounding_account` is a keyword-only, defaulted parameter
    -- the same `source_sections: tuple = ()` precedent `BlockContract`
    already sets -- so every existing positional `write_block(paper_dir,
    contract, draft, audit_account)` call site in this suite stays green,
    unchanged."""

    def test_grounding_account_is_keyword_only_and_defaults_to_none(self) -> None:
        signature = inspect.signature(paper_write.write_block)
        parameter = signature.parameters["grounding_account"]
        self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(parameter.default)

    def test_every_existing_positional_call_site_stays_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper_dir = Path(tmp) / "paper"
            _write_fixture(paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))
            contract = _write_contract(citations_regime="none", evidence_set=())
            result = paper_write.write_block(paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")


def _fact_binding(sentence: str, fact: str) -> "paper_bindings.Binding":
    return paper_bindings.Binding(sentence=sentence, kind="fact", ref=fact, raw=f"fact:{fact}")


def _evidence_binding(sentence: str, evidence_id: str) -> "paper_bindings.Binding":
    return paper_bindings.Binding(sentence=sentence, kind="evidence", ref=evidence_id, raw=f"evidence:{evidence_id}")


def _structural_binding(sentence: str) -> "paper_bindings.Binding":
    return paper_bindings.Binding(sentence=sentence, kind="structural", ref=None, raw="structural")


def _bound_section(
    *, fact="invented-calibration-fact", lineage="invented-study-r1",
    title="Invented Calibration Section", text="Invented section body text.",
) -> dict:
    return {
        "fact": fact, "lineage": lineage, "title": title,
        "path": "/invented/path.md", "byte_start": 0, "byte_end": len(text),
        "text": text,
    }


class SubjectsForTests(unittest.TestCase):
    """`transposition-grounding` spec, `Requirement: The Subject Set Is An
    Intersection Derived From Bytes, Never A List` (tasks.md 0.5/0.6;
    design.md D3). Invented fixture names only -- never a real paper's
    block id, section title, document filename, or lineage literal."""

    def test_a_licensed_fact_with_a_bound_section_is_a_subject(self) -> None:
        section = _bound_section(fact="invented-calibration-fact")
        binding = _fact_binding("The device holds calibration steady.", "invented-calibration-fact")
        subjects = paper_grounding.subjects_for([binding], (section,))
        self.assertEqual(subjects, [binding])

    def test_an_evidence_bound_sentence_is_never_a_subject(self) -> None:
        section = _bound_section(fact="invented-calibration-fact")
        binding = _evidence_binding("This cites an external record.", "E1")
        subjects = paper_grounding.subjects_for([binding], (section,))
        self.assertEqual(subjects, [])

    def test_a_structural_sentence_is_never_a_subject(self) -> None:
        section = _bound_section(fact="invented-calibration-fact")
        binding = _structural_binding("This paragraph closes the section.")
        subjects = paper_grounding.subjects_for([binding], (section,))
        self.assertEqual(subjects, [])

    def test_a_fact_bound_sentence_whose_fact_has_no_bound_section_is_never_a_subject(self) -> None:
        section = _bound_section(fact="invented-calibration-fact")
        binding = _fact_binding("An unrelated fact claim.", "invented-unrelated-fact")
        subjects = paper_grounding.subjects_for([binding], (section,))
        self.assertEqual(subjects, [])

    def test_an_empty_source_sections_tuple_yields_no_subjects(self) -> None:
        binding = _fact_binding("The device holds calibration steady.", "invented-calibration-fact")
        subjects = paper_grounding.subjects_for([binding], ())
        self.assertEqual(subjects, [])


class ArgumentModeBlockHasNoSubjectsTests(unittest.TestCase):
    """`transposition-grounding` spec, Scenario "An argument-mode block has
    no subjects" (tasks.md 0.7): an `argument`-mode block never reaches
    subject derivation at all -- the grounding stage must not even import
    `paper_grounding`, let alone call `subjects_for`, for a non-
    transposition block."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        _write_fixture(self.paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))

    def test_argument_mode_never_calls_subjects_for(self) -> None:
        section = _bound_section(fact="invented-calibration-fact")
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="argument",
            requires_facts=("invented-calibration-fact",), source_sections=(section,),
        )
        draft = {
            "latex": "The device holds calibration steady across trials.",
            "bindings": [
                {
                    "sentence": "The device holds calibration steady across trials.",
                    "binding": "fact:invented-calibration-fact",
                }
            ],
        }
        with unittest.mock.patch.object(paper_grounding, "subjects_for") as mocked:
            result = paper_write.write_block(self.paper_dir, contract, draft, _CLEAN_AUDIT)
        mocked.assert_not_called()
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["sourceGrounding"], {"status": "unmeasured", "subjects": 0})


class InterimSourceGroundingEnvelopeTests(unittest.TestCase):
    """`transposition-grounding` spec, `Requirement: A Block With No Decided
    Subject Reports Unmeasured, Never A Silent Pass`, the `subjects == 0`
    half (tasks.md 0.8/0.9): the `write` envelope gains a `sourceGrounding`
    key beside `sourceFidelity`, reporting `{"status": "unmeasured",
    "subjects": 0}` for a block with an empty subject set."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        _write_fixture(self.paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))

    def test_no_source_sections_reports_unmeasured_zero_subjects(self) -> None:
        contract = _write_contract(citations_regime="none", evidence_set=(), source_sections=())
        result = paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["sourceGrounding"], {"status": "unmeasured", "subjects": 0})

    def test_a_bound_section_with_no_fact_bound_sentence_reports_unmeasured_zero_subjects(self) -> None:
        section = _bound_section(fact="invented-calibration-fact")
        contract = _write_contract(
            citations_regime="none", evidence_set=(), source_sections=(section,),
        )
        result = paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["sourceGrounding"], {"status": "unmeasured", "subjects": 0})


def _grounding_account(entries: list) -> dict:
    return {"support": entries}


class ReconcileSupportBurdenOfProofTests(unittest.TestCase):
    """`the-block-asserts-only-what-its-section-carries`, Phase 1, task 1.1
    -- THE LOAD-BEARING PROPERTY of the whole change, its own task, written
    RED first (design.md D1): an ungrounded `supported` verdict for a
    subject sentence must NOT let that sentence pass as `supported`. Copy
    `contract-audit`'s asymmetry naively and an ungrounded `supported`
    waves everything past -- the guard becomes ceremonial. (`transposition-
    grounding` spec, `Requirement: The Permissive Verdict Carries The
    Burden Of Proof`, Scenario "A supported verdict with an absent span
    downgrades".)"""

    def test_a_supported_verdict_with_an_empty_span_never_passes_as_supported(self) -> None:
        section = _bound_section(
            fact="invented-calibration-fact", text="The calibration constant stays fixed across trials.",
        )
        subject = _fact_binding("Calibration is held constant across every trial.", "invented-calibration-fact")
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "invented-calibration-fact",
                "verdict": "supported", "span": "",
            }
        ])

        reconciled = paper_grounding.reconcile_support(
            [subject], account, (section,), block_id="mm-proposal",
        )

        self.assertEqual(len(reconciled), 1)
        self.assertNotEqual(reconciled[0]["verdict"], "supported")
        self.assertEqual(reconciled[0]["verdict"], "undecidable")
        self.assertEqual(reconciled[0]["span"], "")
        self.assertTrue(reconciled[0]["downgraded"])


class ReconcileSupportTests(unittest.TestCase):
    """`transposition-grounding` spec: `reconcile_support`'s full both-
    direction reconciliation (design.md D1/D3/D7; tasks.md 1.2-1.11)."""

    def test_a_different_facts_section_also_downgrades(self) -> None:
        """Scenario "A supported verdict grounded in a different fact's
        section downgrades" (tasks.md 1.3)."""
        own_section = _bound_section(
            fact="calibration-regime", lineage="widget-study-r4",
            title="Own Section", text="The own section carries nothing about the midpoint.",
        )
        other_section = _bound_section(
            fact="other-fact", lineage="widget-study-r4",
            title="Other Section", text="The midpoint constant is fixed across every trial.",
        )
        subject = _fact_binding("The constant sits at the midpoint across trials.", "calibration-regime")
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "calibration-regime",
                "verdict": "supported", "span": "midpoint constant is fixed across every trial",
            }
        ])

        reconciled = paper_grounding.reconcile_support(
            [subject], account, (own_section, other_section), block_id="mm-proposal",
        )

        self.assertEqual(reconciled[0]["verdict"], "undecidable")
        self.assertEqual(reconciled[0]["span"], "")
        self.assertTrue(reconciled[0]["downgraded"])

    def test_a_byte_present_span_in_its_own_section_passes(self) -> None:
        """Scenario "A supported verdict with a byte-present span passes"
        (tasks.md 1.4)."""
        section = _bound_section(
            fact="calibration-regime", text="The constant is fixed at the interval's midpoint.",
        )
        subject = _fact_binding("Calibration fixes that constant at the midpoint.", "calibration-regime")
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "calibration-regime",
                "verdict": "supported", "span": "fixed at the interval's midpoint",
            }
        ])

        reconciled = paper_grounding.reconcile_support(
            [subject], account, (section,), block_id="mm-proposal",
        )

        self.assertEqual(reconciled[0]["verdict"], "supported")
        self.assertEqual(reconciled[0]["span"], "fixed at the interval's midpoint")
        self.assertFalse(reconciled[0]["downgraded"])

    def test_unsupported_refuses_naming_all_five_fields(self) -> None:
        """Scenario "An unsupported claim is refused with full
        identification" (tasks.md 1.5)."""
        section = _bound_section(
            fact="calibration-regime", lineage="widget-study-r4",
            title="2. Widget Calibration", text="The constant never changes across trials.",
        )
        subject = _fact_binding("Calibration was repeated after every third trial.", "calibration-regime")
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "calibration-regime",
                "verdict": "unsupported",
            }
        ])

        with self.assertRaises(Refused) as ctx:
            paper_grounding.reconcile_support([subject], account, (section,), block_id="mm-proposal")

        self.assertEqual(ctx.exception.code, "SECTION_UNSUPPORTED_CLAIM")
        self.assertIn("mm-proposal", ctx.exception.detail)
        self.assertIn("calibration-regime", ctx.exception.detail)
        self.assertIn("widget-study-r4", ctx.exception.detail)
        self.assertIn("2. Widget Calibration", ctx.exception.detail)
        self.assertIn(subject.sentence, ctx.exception.detail)

    def test_an_account_entry_naming_an_unsegmented_sentence_refuses(self) -> None:
        """Scenario "An account entry naming an unsegmented sentence
        refuses" (tasks.md 1.6, first direction)."""
        section = _bound_section(fact="calibration-regime")
        subject = _fact_binding("The real subject sentence.", "calibration-regime")
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "calibration-regime",
                "verdict": "supported", "span": "Invented section body text.",
            },
            {
                "sentence": "A sentence write never segmented as this fact's subject.",
                "fact": "calibration-regime", "verdict": "clear",
            },
        ])

        with self.assertRaises(Refused) as ctx:
            paper_grounding.reconcile_support([subject], account, (section,), block_id="mm-proposal")

        self.assertEqual(ctx.exception.code, "GROUNDING_SENTENCE_UNKNOWN")
        self.assertIn("A sentence write never segmented as this fact's subject.", ctx.exception.detail)

    def test_a_subject_with_no_account_entry_refuses_verdict_missing(self) -> None:
        """Scenario "A subject sentence absent from the account refuses"
        (tasks.md 1.6, second direction)."""
        section = _bound_section(fact="calibration-regime")
        subject = _fact_binding("This subject sentence has no verdict at all.", "calibration-regime")

        with self.assertRaises(Refused) as ctx:
            paper_grounding.reconcile_support(
                [subject], _grounding_account([]), (section,), block_id="mm-proposal",
            )

        self.assertEqual(ctx.exception.code, "GROUNDING_VERDICT_MISSING")
        self.assertIn("mm-proposal", ctx.exception.detail)
        self.assertIn(subject.sentence, ctx.exception.detail)

    def test_no_account_with_subjects_refuses_account_absent_never_verdict_missing(self) -> None:
        """Scenario "No account, subjects exist" (tasks.md 1.7): the
        absence must never fall through to `GROUNDING_VERDICT_MISSING` on
        the first subject (design.md D7's own rejected alternative)."""
        section = _bound_section(fact="calibration-regime")
        subject = _fact_binding("A subject sentence.", "calibration-regime")

        with self.assertRaises(Refused) as ctx:
            paper_grounding.reconcile_support([subject], None, (section,), block_id="mm-proposal")

        self.assertEqual(ctx.exception.code, "GROUNDING_ACCOUNT_ABSENT")
        self.assertIn("mm-proposal", ctx.exception.detail)
        self.assertIn("1", ctx.exception.detail)
        self.assertNotEqual(ctx.exception.code, "GROUNDING_VERDICT_MISSING")

    def test_no_account_and_no_subjects_raises_nothing(self) -> None:
        """Scenario "No account, no subjects" (tasks.md 1.7)."""
        reconciled = paper_grounding.reconcile_support([], None, (), block_id="mm-proposal")
        self.assertEqual(reconciled, [])


class SourceGroundingReportTests(unittest.TestCase):
    """`transposition-grounding` spec, `Requirement: Undecidable Never
    Blocks Alone...` + `Requirement: A Block With No Decided Subject
    Reports Unmeasured...` (design.md D8; tasks.md 1.8-1.11)."""

    def test_downgraded_and_agent_returned_undecidable_never_merge(self) -> None:
        """Task 1.9, its own task per design.md D2: one subject returned
        `undecidable` directly, a second `supported` with an absent span;
        the report counts the first as `undecidable` and exactly the
        second as `downgraded` -- the two counts never merge. (Scenario "A
        downgrade is never counted as an agent-returned undecidable".)"""
        section = _bound_section(fact="calibration-regime")
        honest = _fact_binding("An honestly abstained subject sentence.", "calibration-regime")
        minted = _fact_binding("A subject sentence with a minted, absent span.", "calibration-regime")
        account = _grounding_account([
            {"sentence": honest.sentence, "fact": "calibration-regime", "verdict": "undecidable"},
            {
                "sentence": minted.sentence, "fact": "calibration-regime",
                "verdict": "supported", "span": "",
            },
        ])

        reconciled = paper_grounding.reconcile_support(
            [honest, minted], account, (section,), block_id="mm-proposal",
        )
        report = paper_grounding.source_grounding_report([honest, minted], reconciled)

        self.assertEqual(report["undecidable"], 1)
        self.assertEqual(report["downgraded"], 1)
        self.assertEqual(report["subjects"], 2)

    def test_an_all_undecidable_or_downgraded_account_does_not_block(self) -> None:
        """Scenario "An all-undecidable-or-downgraded account does not
        block" (tasks.md 1.10)."""
        section = _bound_section(fact="calibration-regime")
        returned = _fact_binding("Returned undecidable directly.", "calibration-regime")
        downgraded_subject = _fact_binding("Downgraded by an absent span.", "calibration-regime")
        account = _grounding_account([
            {"sentence": returned.sentence, "fact": "calibration-regime", "verdict": "undecidable"},
            {
                "sentence": downgraded_subject.sentence, "fact": "calibration-regime",
                "verdict": "supported", "span": "not present anywhere",
            },
        ])

        reconciled = paper_grounding.reconcile_support(
            [returned, downgraded_subject], account, (section,), block_id="mm-proposal",
        )
        report = paper_grounding.source_grounding_report([returned, downgraded_subject], reconciled)

        self.assertGreater(report["undecidable"], 0)
        self.assertGreater(report["downgraded"], 0)
        self.assertNotEqual(report["status"], "refused")

    def test_subjects_exist_but_none_decided_reports_unmeasured_nonzero(self) -> None:
        """Scenario "Subjects exist but none decided reports unmeasured
        with a nonzero count" (tasks.md 1.11)."""
        section = _bound_section(fact="calibration-regime")
        subject = _fact_binding("A subject sentence returned undecidable.", "calibration-regime")
        account = _grounding_account([
            {"sentence": subject.sentence, "fact": "calibration-regime", "verdict": "undecidable"},
        ])

        reconciled = paper_grounding.reconcile_support(
            [subject], account, (section,), block_id="mm-proposal",
        )
        report = paper_grounding.source_grounding_report([subject], reconciled)

        self.assertEqual(report["status"], "unmeasured")
        self.assertEqual(report["subjects"], 1)
        self.assertGreater(report["subjects"], 0)

    def test_a_decided_subject_reports_measured(self) -> None:
        section = _bound_section(fact="calibration-regime", text="The constant holds across trials.")
        subject = _fact_binding("The constant holds steady across trials.", "calibration-regime")
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "calibration-regime",
                "verdict": "supported", "span": "constant holds across trials",
            },
        ])

        reconciled = paper_grounding.reconcile_support(
            [subject], account, (section,), block_id="mm-proposal",
        )
        report = paper_grounding.source_grounding_report([subject], reconciled)

        self.assertEqual(report["status"], "measured")
        self.assertEqual(report["decided"], 1)


class WriteBlockGroundingWiringTests(unittest.TestCase):
    """`transposition-grounding` spec, `Requirement: The Guard Fires After
    The Verbatim Check And Before Substitution` (tasks.md 1.12/1.14); full
    guard wired into `write_block`, replacing Phase 0's interim
    unconditional-`unmeasured` report."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        _write_fixture(self.paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))

    def test_an_unsupported_claim_refuses_through_a_real_write_call(self) -> None:
        """Scenario "An unsupported claim is refused by an actual write
        invocation" -- never a read-only verb; `main.tex` stays unchanged."""
        section = _bound_section(
            fact="calibration-regime", text="The constant never changes across trials.",
        )
        contract = _write_contract(
            citations_regime="none", evidence_set=(), requires_facts=("calibration-regime",),
            source_sections=(section,),
        )
        draft = {
            "latex": "Calibration was repeated after every third trial.",
            "bindings": [
                {
                    "sentence": "Calibration was repeated after every third trial.",
                    "binding": "fact:calibration-regime",
                }
            ],
        }
        grounding_account = _grounding_account([
            {
                "sentence": "Calibration was repeated after every third trial.",
                "fact": "calibration-regime", "verdict": "unsupported",
            }
        ])
        pre = (self.paper_dir / "main.tex").read_bytes()

        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(
                self.paper_dir, contract, draft, _CLEAN_AUDIT, grounding_account=grounding_account,
            )

        self.assertEqual(ctx.exception.code, "SECTION_UNSUPPORTED_CLAIM")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), pre)

    def test_a_supported_claim_writes_with_the_span_reported(self) -> None:
        section = _bound_section(
            fact="calibration-regime", text="The constant is fixed at the interval's midpoint.",
        )
        contract = _write_contract(
            citations_regime="none", evidence_set=(), requires_facts=("calibration-regime",),
            source_sections=(section,),
        )
        draft = {
            "latex": "Calibration fixes that constant at the midpoint.",
            "bindings": [
                {
                    "sentence": "Calibration fixes that constant at the midpoint.",
                    "binding": "fact:calibration-regime",
                }
            ],
        }
        grounding_account = _grounding_account([
            {
                "sentence": "Calibration fixes that constant at the midpoint.",
                "fact": "calibration-regime", "verdict": "supported",
                "span": "fixed at the interval's midpoint",
            }
        ])

        result = paper_write.write_block(
            self.paper_dir, contract, draft, _CLEAN_AUDIT, grounding_account=grounding_account,
        )

        self.assertEqual(result["status"], "written")
        self.assertEqual(result["sourceGrounding"]["status"], "measured")
        self.assertEqual(result["sourceGrounding"]["decided"], 1)

    def test_a_draft_failing_both_checks_names_the_verbatim_refusal(self) -> None:
        """Scenario "A draft failing both checks names the verbatim
        refusal" (tasks.md 1.14): copying is decided before meaning."""
        run = _n_token_run(17)
        section_text = f"Some opening sentence. {run} A closing sentence about something else."
        section = _bound_section(
            fact="calibration-regime", lineage="widget-study-r4",
            title="2. Widget Calibration", text=section_text,
        )
        contract = _write_contract(
            citations_regime="none", evidence_set=(), requires_facts=("calibration-regime",),
            source_sections=(section,),
        )
        draft_latex = f"Opening sentence of the draft. {run} Closing sentence of the draft."
        draft = {
            "latex": draft_latex,
            "bindings": [{"sentence": draft_latex, "binding": "fact:calibration-regime"}],
        }
        grounding_account = _grounding_account([
            {"sentence": draft_latex, "fact": "calibration-regime", "verdict": "unsupported"},
        ])

        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(
                self.paper_dir, contract, draft, _CLEAN_AUDIT, grounding_account=grounding_account,
            )

        self.assertEqual(ctx.exception.code, "SOURCE_SECTION_VERBATIM")


class GroundingThresholdObligationTests(unittest.TestCase):
    """The D2 obligation, carried by the machine instead of by prose.

    `the-block-asserts-only-what-its-section-carries` deliberately shipped no
    ratio threshold over `downgraded`/`decided`, and said so as a ruling with
    a written falsifier rather than inventing a number. The reason is a
    precondition, not an opinion: no real `document`-rooted binding exists
    anywhere on disk, so there is nothing to calibrate against, and any number
    would be chosen and then read six months later as measured.

    That obligation lived only in `SKILL.md` and an archive report. A document
    does not execute, so it cannot notice the day its precondition changes --
    the failure this repository records as "prose that outlives its mechanism".

    This test is the tripwire that closes that gap. While no binding is
    recorded it passes, and it is passing for a stated reason rather than
    vacuously. The moment somebody runs `bind` for real, it goes RED and names
    what is now owed: run the falsifier, and either discharge the ruling with
    measured counts or replace it with the blocking rule it asks for.

    The falsifier itself, verbatim from `SKILL.md`: over ten or more recorded
    real `write` runs against genuine document-rooted bindings, if any block
    reaches `written` with `downgraded > 0`, or with `subjects > 0` and
    `decided == 0`, the no-ratio-threshold ruling is wrong and a blocking rule
    over these counts must be added.
    """

    #: The falsifier's own number, quoted from `SKILL.md`: "over ten or more
    #: recorded real `write` runs". Named here so the count that decides
    #: whether there is anything to judge is not buried in a comparison.
    FALSIFIER_MINIMUM = 10

    @staticmethod
    def recorded_runs(paper_dir: Path) -> list:
        """Every run `write` recorded, oldest first.

        An absent ledger is zero runs, not an error: before the first write
        there is nothing to have recorded. A malformed line is skipped rather
        than raising, because one bad line must not make the other nine
        unreadable — the same fail-closed direction `forge_section_ids`
        already takes, where an unreadable input grants nothing instead of
        taking the whole check down.
        """
        path = paper_dir / ".paper-writing" / "grounding-runs.jsonl"
        if not path.is_file():
            return []
        runs = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                runs.append(json.loads(line))
            except ValueError:
                continue
        return runs

    @classmethod
    def falsifier_hits(cls, runs) -> list:
        """The runs that trip the falsifier, each named with the count that
        tripped it.

        Verbatim from `SKILL.md`: a block reaching `written` with
        `downgraded > 0`, or with `subjects > 0` and `decided == 0`. Both
        shapes are kept as written rather than collapsed into one predicate —
        they are two different ways for the ruling to be wrong, and a reader
        deciding what rule to add needs to know which one fired.
        """
        hits = []
        for run in runs:
            block = run.get("block_id", "<unnamed>")
            subjects = run.get("subjects", 0)
            decided = run.get("decided", 0)
            downgraded = run.get("downgraded", 0)
            if isinstance(downgraded, int) and downgraded > 0:
                hits.append(f"{block}: downgraded={downgraded}")
            elif (isinstance(subjects, int) and subjects > 0
                    and isinstance(decided, int) and decided == 0):
                hits.append(f"{block}: subjects={subjects} decided=0")
        return hits

    def test_the_falsifier_runs_once_there_is_something_to_run_it_on(self) -> None:
        """The D2 obligation, judged against recorded runs rather than
        announced forever.

        This failed the moment ANY document-rooted binding existed, and kept
        failing until somebody discharged the ruling by hand. That made the
        suite permanently red, and a permanently red test is not a signal —
        in this repository three legitimate failures were dismissed as
        environmental for a whole session for exactly that reason.

        The repository already has the right shape for "cannot judge yet",
        and uses it a few files over: announce the silence, do not fail. So
        below the falsifier's own minimum this SKIPS and says how far off it
        is. At or above it, the falsifier is applied to the counts the runs
        recorded, and either names what fired or asks for the discharge the
        obligation actually specifies.

        It never passes silently. Silence here means there is nothing to say
        yet; it never means the ruling was checked.
        """
        runs = self.recorded_runs(FORGE_ROOT / "paper")
        if len(runs) < self.FALSIFIER_MINIMUM:
            self.skipTest(
                f"{len(runs)} recorded `write` run(s); the falsifier needs "
                f"{self.FALSIFIER_MINIMUM}. Nothing to judge yet, and this is "
                "announced silence rather than a pass — the no-ratio-threshold "
                "ruling stays unchecked, not confirmed")
        hits = self.falsifier_hits(runs)
        self.assertEqual(
            hits, [],
            "the falsifier fired over {n} recorded runs, so the "
            "no-ratio-threshold ruling is WRONG and a blocking rule over "
            "these counts must be added: {hits}".format(
                n=len(runs), hits="; ".join(hits)))
        self.fail(
            f"the falsifier ran over {len(runs)} recorded runs and nothing "
            "fired, so the ruling held. That is not a pass: the obligation "
            "asks for the measured counts to be recorded in the doctrine and "
            "THIS TEST DELETED. Do NOT simply re-pin it.")

    def test_a_downgraded_run_is_named_as_the_shape_that_fired(self) -> None:
        """Positive control for the first shape. Without it, a predicate that
        stopped matching would read exactly like a ruling that held."""
        self.assertEqual(self.falsifier_hits([
            {"block_id": "a", "status": "measured", "subjects": 3, "decided": 3,
             "downgraded": 1}]), ["a: downgraded=1"])

    def test_subjects_with_nothing_decided_is_the_other_shape(self) -> None:
        """Positive control for the second, and they must stay
        distinguishable: a reader deciding what rule to add needs to know
        which one fired."""
        self.assertEqual(self.falsifier_hits([
            {"block_id": "b", "status": "unmeasured", "subjects": 4,
             "decided": 0, "downgraded": 0}]), ["b: subjects=4 decided=0"])

    def test_a_clean_run_and_an_empty_block_fire_nothing(self) -> None:
        """The negative control. A predicate that fired on everything would
        satisfy both controls above and be just as broken."""
        self.assertEqual(self.falsifier_hits([
            {"block_id": "c", "status": "measured", "subjects": 2, "decided": 2,
             "downgraded": 0},
            {"block_id": "d", "status": "unmeasured", "subjects": 0}]), [])

    def test_an_absent_or_malformed_ledger_reads_as_the_runs_it_has(self) -> None:
        """An absent ledger is zero runs, not a crash; one unreadable line
        costs its own line and not the other nine."""
        box = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        self.assertEqual(self.recorded_runs(box), [])
        store = box / ".paper-writing"
        store.mkdir()
        (store / "grounding-runs.jsonl").write_text(
            '{"block_id": "a", "subjects": 1, "decided": 1}\n'
            'not json at all\n\n'
            '{"block_id": "b", "subjects": 2, "decided": 2}\n', encoding="utf-8")
        self.assertEqual(
            [r["block_id"] for r in self.recorded_runs(box)], ["a", "b"])

    def test_the_falsifier_is_still_shipped_where_a_reader_will_find_it(self) -> None:
        """The tripwire above is worthless if the obligation it points at has
        been quietly edited out of the shipped doctrine."""
        skill_md = (SKILL_SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Falsifier:", skill_md)
        self.assertIn("downgraded > 0", skill_md)
        self.assertIn("decided == 0", skill_md)


class GroundingHeadingIsNotSupportTests(unittest.TestCase):
    """A section's own HEADING cannot ground a claim about its body.

    `resolve_bound_sections` slices from the heading's first byte, so
    `section["text"]` opens with the heading itself. That is correct for
    `SOURCE_SECTION_VERBATIM` -- pasting a source's heading into a draft is
    copying it -- and wrong here: a `supported` verdict quoting only the
    TITLE was byte-present in the full slice and survived reconciliation,
    licensing a sentence the body never supports.

    The verify phase of `the-block-asserts-only-what-its-section-carries`
    reproduced this by direct execution and recorded it as a WARNING; none
    of that change's own 39 grounding tests exercised it. These do.
    """

    HEADED = "# 3. Calibration Protocol\n\nThe constant is re-derived per trial.\n"

    def test_a_span_quoting_only_the_heading_is_downgraded_never_supported(self) -> None:
        section = _bound_section(fact="invented-calibration-fact", text=self.HEADED)
        subject = _fact_binding("Calibration runs once per study.", "invented-calibration-fact")
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "invented-calibration-fact",
                "verdict": "supported", "span": "3. Calibration Protocol",
            }
        ])

        reconciled = paper_grounding.reconcile_support(
            [subject], account, (section,), block_id="mm-proposal",
        )

        self.assertEqual(reconciled[0]["verdict"], "undecidable")
        self.assertEqual(reconciled[0]["span"], "")
        self.assertTrue(
            reconciled[0]["downgraded"],
            "a heading names what a section is about; it asserts nothing, so it "
            "cannot ground a claim -- and the downgrade must be counted as one",
        )

    def test_a_span_quoting_the_body_still_survives(self) -> None:
        """The other half, without which the check above could be a blanket
        that downgrades everything and nothing would say so."""
        section = _bound_section(fact="invented-calibration-fact", text=self.HEADED)
        subject = _fact_binding("The constant is re-derived for every trial.", "invented-calibration-fact")
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "invented-calibration-fact",
                "verdict": "supported", "span": "The constant is re-derived per trial.",
            }
        ])

        reconciled = paper_grounding.reconcile_support(
            [subject], account, (section,), block_id="mm-proposal",
        )

        self.assertEqual(reconciled[0]["verdict"], "supported")
        self.assertFalse(reconciled[0]["downgraded"])

    def test_a_section_that_is_only_a_heading_grounds_nothing(self) -> None:
        """The degenerate case, failing in the safe direction: a section
        carrying no body at all has nothing that can support anything."""
        section = _bound_section(fact="invented-calibration-fact", text="# 3. Calibration Protocol")
        subject = _fact_binding("Calibration runs once per study.", "invented-calibration-fact")
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "invented-calibration-fact",
                "verdict": "supported", "span": "3. Calibration Protocol",
            }
        ])

        reconciled = paper_grounding.reconcile_support(
            [subject], account, (section,), block_id="mm-proposal",
        )

        self.assertEqual(reconciled[0]["verdict"], "undecidable")
        self.assertTrue(reconciled[0]["downgraded"])

    def test_an_unheaded_section_is_read_whole(self) -> None:
        """Not every bound section starts with a heading; one that does not
        must keep every byte it has available as support."""
        section = _bound_section(
            fact="invented-calibration-fact", text="The constant is re-derived per trial.",
        )
        subject = _fact_binding("The constant is re-derived for every trial.", "invented-calibration-fact")
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "invented-calibration-fact",
                "verdict": "supported", "span": "The constant is re-derived per trial.",
            }
        ])

        reconciled = paper_grounding.reconcile_support(
            [subject], account, (section,), block_id="mm-proposal",
        )

        self.assertEqual(reconciled[0]["verdict"], "supported")


class GroundingScopeBoundaryTests(unittest.TestCase):
    """`transposition-grounding` spec, `Requirement: A Sibling Check, Never
    An Extension Of The Verbatim Or Leak Checks` (tasks.md 1.13, its own
    task). An `evidence:`-bound sentence and an `argument`-mode block NEVER
    reach reconciliation, even when a grounding account names them --
    proven by a LOCK, not by the absence of a failure."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        _write_fixture(self.paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))

    def test_an_account_entry_naming_a_non_subject_sentence_is_ignored(self) -> None:
        """A grounding account naming an `evidence:`-bound sentence (never
        a subject) must not raise `GROUNDING_SENTENCE_UNKNOWN` -- the entry
        is simply irrelevant to reconciliation, which is scoped to
        subjects' own facts alone."""
        section = _bound_section(fact="calibration-regime", text="The constant holds across trials.")
        subject = _fact_binding("The constant holds steady across trials.", "calibration-regime")
        non_subject_entry = {
            "sentence": "This cites an external record, never a subject.",
            "fact": "an-unrelated-non-subject-fact", "verdict": "unsupported",
        }
        account = _grounding_account([
            {
                "sentence": subject.sentence, "fact": "calibration-regime",
                "verdict": "supported", "span": "constant holds across trials",
            },
            non_subject_entry,
        ])

        reconciled = paper_grounding.reconcile_support(
            [subject], account, (section,), block_id="mm-proposal",
        )

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["verdict"], "supported")

    def test_an_evidence_bound_sentence_never_reaches_reconciliation_through_write(self) -> None:
        section = _bound_section(fact="calibration-regime", text="The constant holds across trials.")
        contract = _write_contract(
            citations_regime="resolution", evidence_set=({"id": "E1", "regime": "resolution"},),
            requires_facts=("calibration-regime",), source_sections=(section,),
        )
        draft = {
            "latex": (
                "The constant holds steady across trials. "
                "This closes on the recorded evidence."
            ),
            "bindings": [
                {
                    "sentence": "The constant holds steady across trials.",
                    "binding": "fact:calibration-regime",
                },
                {
                    "sentence": "This closes on the recorded evidence.",
                    "binding": "evidence:E1",
                },
            ],
        }
        grounding_account = _grounding_account([
            {
                "sentence": "The constant holds steady across trials.",
                "fact": "calibration-regime", "verdict": "supported",
                "span": "constant holds across trials",
            },
            {
                # An over-eager account also judging the evidence-bound
                # sentence, which is never a subject and must be ignored.
                "sentence": "This closes on the recorded evidence.",
                "fact": "E1", "verdict": "unsupported",
            },
        ])

        result = paper_write.write_block(
            self.paper_dir, contract, draft, _CLEAN_AUDIT, grounding_account=grounding_account,
        )

        self.assertEqual(result["status"], "written")

    def test_an_argument_mode_block_never_reaches_reconciliation_through_write(self) -> None:
        section = _bound_section(fact="calibration-regime", text="The constant holds across trials.")
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="argument",
            requires_facts=("calibration-regime",), source_sections=(section,),
        )
        draft = {
            "latex": "The constant holds steady across trials.",
            "bindings": [
                {
                    "sentence": "The constant holds steady across trials.",
                    "binding": "fact:calibration-regime",
                }
            ],
        }
        # An account claiming `unsupported` would refuse `SECTION_
        # UNSUPPORTED_CLAIM` were this block ever reconciled -- it is not,
        # even though a caller (mistakenly) supplied one.
        grounding_account = _grounding_account([
            {
                "sentence": "The constant holds steady across trials.",
                "fact": "calibration-regime", "verdict": "unsupported",
            }
        ])

        result = paper_write.write_block(
            self.paper_dir, contract, draft, _CLEAN_AUDIT, grounding_account=grounding_account,
        )

        self.assertEqual(result["status"], "written")
        self.assertEqual(result["sourceGrounding"], {"status": "unmeasured", "subjects": 0})


def _read_grounding_run_lines(paper_dir: Path) -> list:
    """Test-only helper: parses `paper/.paper-writing/grounding-runs.jsonl`
    one line at a time, the same convention `EvidenceRecordStoreTests`
    (`tests/test_paper_evidence.py`) uses for its own JSONL store, oldest
    first. Reads bytes actually on disk rather than trusting any in-process
    return value, since the property under test is what got WRITTEN."""
    path = paper_dir / ".paper-writing" / "grounding-runs.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class GroundingRunLedgerTests(unittest.TestCase):
    """The falsifier `GroundingThresholdObligationTests` names (`SKILL.md`,
    "over ten or more recorded real `write` runs...") has nothing to
    accumulate against today: `write_block` computes `sourceGrounding` and
    then drops it. This is the missing recorder -- one JSON line per
    completed `write` run, appended to `paper/.paper-writing/grounding-
    runs.jsonl`, never rewritten.

    Deliberately does NOT touch `GroundingThresholdObligationTests` itself,
    and does not fabricate a document-rooted binding: these fixtures are
    the same invented, non-document-rooted shapes every sibling grounding
    test in this file already uses, so `paper_declarations.read_bindings`
    on the real `paper/` tree is untouched and that tripwire stays red for
    the same reason it already is.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    def test_a_measured_transposition_run_leaves_one_line_carrying_its_counts(self) -> None:
        _write_fixture(self.paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))
        section = _bound_section(fact="calibration-regime", text="The constant holds across trials.")
        contract = _write_contract(
            citations_regime="resolution", evidence_set=({"id": "E1", "regime": "resolution"},),
            requires_facts=("calibration-regime",), source_sections=(section,),
        )
        draft = {
            "latex": "The constant holds steady across trials.",
            "bindings": [
                {
                    "sentence": "The constant holds steady across trials.",
                    "binding": "fact:calibration-regime",
                },
            ],
        }
        grounding_account = _grounding_account([
            {
                "sentence": "The constant holds steady across trials.",
                "fact": "calibration-regime", "verdict": "supported",
                "span": "constant holds across trials",
            },
        ])

        result = paper_write.write_block(
            self.paper_dir, contract, draft, _CLEAN_AUDIT, grounding_account=grounding_account,
        )

        self.assertEqual(result["status"], "written")
        expected_report = result["sourceGrounding"]
        self.assertEqual(
            expected_report,
            {"status": "measured", "subjects": 1, "decided": 1, "undecidable": 0, "downgraded": 0},
        )
        lines = _read_grounding_run_lines(self.paper_dir)
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line["block_id"], "mm-proposal")
        for key, value in expected_report.items():
            self.assertEqual(line[key], value)

    def test_a_run_whose_substitution_fails_leaves_no_line_at_all(self) -> None:
        """The ledger counts blocks that REACHED `written`, so the append
        belongs after the substitution and nowhere else.

        Without this test that ordering is prose: moving the append above
        `paper_block.substitute` was measured to change nothing any test
        observes, because no other case here ever lets the substitution
        fail. And the ordering is not cosmetic -- a line written before a
        substitution that then raises records a run that never happened,
        inflating the very denominator the falsifier discharges the D2
        obligation by counting. Overcounting is the worse direction: it
        would let ten apparent runs discharge a ruling that fewer real
        runs were ever measured against.
        """
        _write_fixture(self.paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))
        section = _bound_section(fact="invented-calibration-fact")
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="argument",
            requires_facts=("invented-calibration-fact",), source_sections=(section,),
        )
        draft = {
            "latex": "The device holds calibration steady across trials.",
            "bindings": [
                {
                    "sentence": "The device holds calibration steady across trials.",
                    "binding": "fact:invented-calibration-fact",
                }
            ],
        }

        def _refuse(*args, **kwargs):
            raise RuntimeError("substitution refused by this test")

        with unittest.mock.patch.object(paper_block, "substitute", _refuse):
            with self.assertRaisesRegex(
                    RuntimeError, "substitution refused by this test"):
                paper_write.write_block(
                    self.paper_dir, contract, draft, _CLEAN_AUDIT)

        self.assertEqual(
            _read_grounding_run_lines(self.paper_dir), [],
            "the substitution raised, so no block reached `written` -- a "
            "ledger line here would count a run that never happened")

    def test_an_argument_mode_unmeasured_run_also_leaves_a_line(self) -> None:
        """The one a careless implementation drops: an `argument`-mode
        block never imports `paper_grounding` and reports the interim
        `{"status": "unmeasured", "subjects": 0}` envelope, but it is still
        a real completed `write` run and still owed a place in the "ten or
        more" denominator the falsifier counts against."""
        _write_fixture(self.paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))
        section = _bound_section(fact="invented-calibration-fact")
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="argument",
            requires_facts=("invented-calibration-fact",), source_sections=(section,),
        )
        draft = {
            "latex": "The device holds calibration steady across trials.",
            "bindings": [
                {
                    "sentence": "The device holds calibration steady across trials.",
                    "binding": "fact:invented-calibration-fact",
                }
            ],
        }

        result = paper_write.write_block(self.paper_dir, contract, draft, _CLEAN_AUDIT)

        self.assertEqual(result["status"], "written")
        self.assertEqual(result["sourceGrounding"], {"status": "unmeasured", "subjects": 0})
        lines = _read_grounding_run_lines(self.paper_dir)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["block_id"], "mm-proposal")
        self.assertEqual(lines[0]["status"], "unmeasured")
        self.assertEqual(lines[0]["subjects"], 0)

    def test_a_second_run_appends_and_the_first_line_survives_byte_identical(self) -> None:
        main_tex = _marker_pair("mm-proposal", b"Old body one.\n") + _marker_pair(
            "mm-second", b"Old body two.\n",
        )
        _write_fixture(self.paper_dir, main_tex)
        contract_a = _write_contract(
            block_id="mm-proposal", citations_regime="none", evidence_set=(), mode="argument",
        )
        contract_b = _write_contract(
            block_id="mm-second", citations_regime="none", evidence_set=(), mode="argument",
        )

        paper_write.write_block(self.paper_dir, contract_a, _CLEAN_DRAFT, _CLEAN_AUDIT)
        path = self.paper_dir / ".paper-writing" / "grounding-runs.jsonl"
        first_line_bytes = path.read_bytes()
        self.assertEqual(len(_read_grounding_run_lines(self.paper_dir)), 1)

        paper_write.write_block(self.paper_dir, contract_b, _CLEAN_DRAFT, _CLEAN_AUDIT)

        raw = path.read_bytes()
        self.assertTrue(raw.startswith(first_line_bytes))
        lines = _read_grounding_run_lines(self.paper_dir)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["block_id"], "mm-proposal")
        self.assertEqual(lines[1]["block_id"], "mm-second")

    def test_the_line_is_valid_json_with_timestamp_block_id_and_counts(self) -> None:
        from datetime import datetime as _datetime  # noqa: PLC0415

        _write_fixture(self.paper_dir, _marker_pair("mm-proposal", b"Old body.\n"))
        contract = _write_contract(
            citations_regime="none", evidence_set=(), mode="argument",
        )

        paper_write.write_block(self.paper_dir, contract, _CLEAN_DRAFT, _CLEAN_AUDIT)

        path = self.paper_dir / ".paper-writing" / "grounding-runs.jsonl"
        raw_lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(raw_lines), 1)
        line = json.loads(raw_lines[0])  # raises if not valid JSON
        self.assertIsInstance(line["timestamp"], str)
        _datetime.fromisoformat(line["timestamp"])  # raises if not a real timestamp
        self.assertEqual(line["block_id"], "mm-proposal")
        self.assertEqual(line["status"], "unmeasured")
        self.assertEqual(line["subjects"], 0)


class CmdWriteGroundingWiringTests(unittest.TestCase):
    """`the-block-asserts-only-what-its-section-carries`, Phase 2, task
    2.8: `cmd_write` reads `--grounding`, resolves it through
    `_resolve_repo_path` when supplied, loads its JSON, and threads it to
    `write_block(..., grounding_account=...)`. Mocks `paper_write.
    write_block` (never `paper_source_span.resolve_bound_sections`), the
    same shape `CmdWriteSourceSectionsWiringTests` already establishes."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-cmd-write-grounding-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)
        blocks = [{
            "id": "only", "requires_facts": [], "requires_declarations": [], "citations": "none",
        }]
        (self.sections_dir / "a.md").write_text(
            "---\n" + json.dumps({"section": "a", "position": 1, "blocks": blocks})
            + "\n---\n\nSome contract prose.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        (self.test_root / "draft.json").write_text(
            json.dumps({"latex": "Draft body.", "bindings": []}), encoding="utf-8",
        )
        (self.test_root / "audit.json").write_text(json.dumps({"verdicts": []}), encoding="utf-8")
        self.grounding_payload = {
            "support": [{"sentence": "Draft body.", "fact": "invented-fact", "verdict": "supported"}]
        }
        (self.test_root / "grounding.json").write_text(
            json.dumps(self.grounding_payload), encoding="utf-8",
        )

    def _args(self, *, grounding=None) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="a", block="only",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=grounding,
        )

    def test_cmd_write_threads_grounding_account_to_write_block(self) -> None:
        with unittest.mock.patch("paper_write.write_block") as mocked_write_block:
            mocked_write_block.return_value = {"status": "written"}
            paper_cli.cmd_write(self._args(grounding=str(self.test_root / "grounding.json")))

        self.assertEqual(mocked_write_block.call_args.kwargs["grounding_account"], self.grounding_payload)

    def test_cmd_write_omitting_grounding_passes_none(self) -> None:
        with unittest.mock.patch("paper_write.write_block") as mocked_write_block:
            mocked_write_block.return_value = {"status": "written"}
            paper_cli.cmd_write(self._args(grounding=None))

        self.assertIsNone(mocked_write_block.call_args.kwargs["grounding_account"])

    def test_a_grounding_path_outside_the_repository_refuses(self) -> None:
        outside = Path(tempfile.gettempdir()) / f"paper-writing-grounding-outside-{os.getpid()}.json"
        outside.write_text(json.dumps({"support": []}), encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_write(self._args(grounding=str(outside)))

        self.assertEqual(ctx.exception.code, "PAPER_OUTSIDE_REPOSITORY")


class RefusalConstructorLiteralArgumentTests(unittest.TestCase):
    """`the-block-asserts-only-what-its-section-carries`, task 2.9
    (design.md Sec 1): every `Refused(...)` first argument this change adds
    is a string literal, in `paper_grounding.py` and this phase's
    `paper_write.py`/`paper_cli.py` diffs -- a non-literal makes the site
    `code is None` to `reachable_paper_refusal_codes`'s own static walk
    (`_refusal_code_argument` reads only `ast.Constant`), silently widening
    the module's whole constant set into the roster."""

    def test_no_new_raise_site_re_raises_a_caught_refusals_own_code(self) -> None:
        for path in (
            SKILL_SCRIPTS / "paper_grounding.py",
            SKILL_SCRIPTS / "paper_write.py",
            CLI,
        ):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "raise Refused(exc.code", source,
                f"{path.name} re-raises a caught refusal's own runtime code, which is "
                "invisible to the roster derivation's static walk",
            )

    def test_every_refused_call_in_paper_grounding_takes_a_string_literal_code(self) -> None:
        tree = ast.parse((SKILL_SCRIPTS / "paper_grounding.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "Refused"):
                first = node.args[0]
                self.assertIsInstance(first, ast.Constant, ast.dump(node))
                self.assertIsInstance(first.value, str, ast.dump(node))


class GroundingMutationProofTests(unittest.TestCase):
    """`the-block-asserts-only-what-its-section-carries`, Phase 3, tasks
    3.1-3.4: one mutant per refusal code, proving reachability the way
    this repository requires it proven -- by breaking the guard and
    watching the mapped scenario go red, never by reading the source and
    asserting it looks right. Every anchor below sits on its own line in
    `paper_grounding.py`, none shared with another (tasks.md 3.4)."""

    def _assert_guard_failed_under_mutation(self, proc: subprocess.CompletedProcess) -> None:
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_1_treating_an_absent_account_as_empty_fails_the_account_absent_guard(self) -> None:
        """Scenario "Mutation -- the absent-account refusal is reachable"
        (tasks.md 3.1)."""
        proc = _run_against_mutant(
            "    if account is None:",
            "    if False:",
            "tests.test_paper_writing.ReconcileSupportTests"
            ".test_no_account_with_subjects_refuses_account_absent_never_verdict_missing",
            source_path=SKILL_SCRIPTS / "paper_grounding.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_2a_disabling_the_unknown_sentence_check_fails_its_own_scenario(self) -> None:
        """Scenario "Mutation -- each direction is independently reachable"
        (tasks.md 3.2), the `GROUNDING_SENTENCE_UNKNOWN` direction."""
        proc = _run_against_mutant(
            '        if entry["sentence"] not in subject_sentences:',
            "        if False:",
            "tests.test_paper_writing.ReconcileSupportTests"
            ".test_an_account_entry_naming_an_unsegmented_sentence_refuses",
            source_path=SKILL_SCRIPTS / "paper_grounding.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_2b_disabling_the_missing_verdict_check_fails_its_own_scenario(self) -> None:
        """Scenario "Mutation -- each direction is independently reachable"
        (tasks.md 3.2), the `GROUNDING_VERDICT_MISSING` direction -- a
        DIFFERENT anchor line from 2a's, so each mutant reddens only its
        own scenario, never the other."""
        proc = _run_against_mutant(
            "        if entry is None:",
            "        if False:",
            "tests.test_paper_writing.ReconcileSupportTests"
            ".test_a_subject_with_no_account_entry_refuses_verdict_missing",
            source_path=SKILL_SCRIPTS / "paper_grounding.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_3_removing_the_byte_presence_re_read_fails_the_downgrade_guard(self) -> None:
        """Scenario "Mutation -- the downgrade is caught only by span
        reconciliation" (tasks.md 3.3) -- THE load-bearing property (design.md
        D1): with the byte-presence re-read removed, any span is accepted
        without ever being checked against the section's own bytes, and an
        ungrounded `supported` verdict wrongly survives."""
        proc = _run_against_mutant(
            'byte_present_own = bool(span) and any(span in _body_of(section) for section in own_sections)',
            "byte_present_own = True",
            "tests.test_paper_writing.ReconcileSupportBurdenOfProofTests"
            ".test_a_supported_verdict_with_an_empty_span_never_passes_as_supported",
            source_path=SKILL_SCRIPTS / "paper_grounding.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_mutation_4_disabling_the_unsupported_branch_fails_its_own_scenario(self) -> None:
        """Scenario "Mutation -- the unsupported refusal is reachable"
        (tasks.md 3.4)."""
        proc = _run_against_mutant(
            '        if verdict == "unsupported":',
            "        if False:",
            "tests.test_paper_writing.ReconcileSupportTests"
            ".test_unsupported_refuses_naming_all_five_fields",
            source_path=SKILL_SCRIPTS / "paper_grounding.py",
        )
        self._assert_guard_failed_under_mutation(proc)

    def test_the_four_anchors_sit_on_four_distinct_lines(self) -> None:
        """tasks.md 3.4's own design constraint on the module: no two of
        the four refusals' guard conditions may share a source line, or
        `_run_against_mutant`'s exactly-once anchor requirement could never
        be satisfied for both at once."""
        source = (SKILL_SCRIPTS / "paper_grounding.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        anchors = [
            "if account is None:",
            'if entry["sentence"] not in subject_sentences:',
            "if entry is None:",
            'if verdict == "unsupported":',
            'byte_present_own = bool(span) and any(span in _body_of(section) for section in own_sections)',
        ]
        anchor_lines = set()
        for anchor in anchors:
            matches = [index for index, line in enumerate(lines) if anchor in line]
            self.assertEqual(len(matches), 1, f"{anchor!r} must occur exactly once")
            anchor_lines.add(matches[0])
        self.assertEqual(len(anchor_lines), len(anchors), "two anchors share the same source line")


class WriteSubstitutesTheQualifiedBlockTests(unittest.TestCase):
    """`write` must reach `substitute` against the id the manuscript
    actually carries. `skeleton`/`open` write the QUALIFIED id
    (`<section>.<block>`) into `main.tex` -- what `status` lists -- while
    `cmd_write` built its `BlockContract` with the BARE `args.block`, so
    `paper_block.substitute` looked for a block no real manuscript has and
    refused `BLOCK_ABSENT` for every one of them.

    RED-first: against the pre-fix `cmd_write` this class fails with
    `Refused('BLOCK_ABSENT')` instead of writing. Every other `cmd_write`
    test in this file stops at a GATE (a refusal, or a deliberately absent
    draft file) and so never reached the substitution at all -- which is
    exactly how the defect shipped.
    """

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / ".scratch"
            / f".paper-writing-qualified-id-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)

        header = {
            "section": "mm", "position": 1,
            "mode": {"value": "transposition",
                     "source": {"file": "sections/01-mm.md", "quote": "Prose."}},
            "blocks": [
                {"id": "only", "requires_facts": [], "requires_declarations": [],
                 "citations": "none"},
            ],
        }
        (self.sections_dir / "01-mm.md").write_text(
            "---\n" + json.dumps(header) + "\n---\n\nProse.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n\n"
            "## Disqualifiers\n\n- A symbol used without being declared.\n",
            encoding="utf-8",
        )

        self.qualified_id = "mm.only"
        paper_block.open_block(self.paper_dir, self.qualified_id, at_end=True)

        self.sentence = "This paragraph closes the section."
        (self.test_root / "draft.json").write_text(
            json.dumps({"latex": self.sentence,
                        "bindings": [{"sentence": self.sentence, "binding": "structural"}]}),
            encoding="utf-8",
        )
        (self.test_root / "audit.json").write_text(
            json.dumps({"verdicts": [
                {"bullet": "A symbol used without being declared.", "verdict": "clear"},
            ]}),
            encoding="utf-8",
        )

        self.args = argparse.Namespace(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            section="mm", block="only",
            draft=str(self.test_root / "draft.json"),
            audit=str(self.test_root / "audit.json"),
            evidence=None, style=None, guidance=None, transcript=None, grounding=None,
        )

    def test_write_substitutes_the_block_the_manuscript_carries(self) -> None:
        result = paper_cli.cmd_write(self.args)

        self.assertEqual(result["status"], "written")
        self.assertEqual(result["block"], self.qualified_id)

    def test_the_written_bytes_land_inside_that_qualified_block(self) -> None:
        paper_cli.cmd_write(self.args)

        tex = (self.paper_dir / "main.tex").read_text(encoding="utf-8")
        self.assertIn(self.sentence, tex)
        begin = tex.index(f"%% paper-writing block {self.qualified_id} begin")
        end = tex.index(f"%% paper-writing block {self.qualified_id} end")
        self.assertLess(begin, tex.index(self.sentence))
        self.assertLess(tex.index(self.sentence), end)


class WriteQualifiedIdMutationProofTests(unittest.TestCase):
    """The qualified id must be load-bearing, not merely present: reverting
    `cmd_write`'s `block_id` to the bare `args.block` must turn the write
    path red again."""

    def test_mutation_back_to_the_bare_block_id_fails_the_write(self) -> None:
        proc = _run_against_mutant(
            "        block_id=qualified_id,\n",
            "        block_id=args.block,\n",
            "tests.test_paper_writing.WriteSubstitutesTheQualifiedBlockTests"
            ".test_write_substitutes_the_block_the_manuscript_carries",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)



class ModelOutputEnvelopeValidationTests(unittest.TestCase):
    """Issue #71: Validate generated JSON envelopes before indexing model output."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="paper-envelope-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_strip_markdown_fences_handles_fences_and_raw_json(self) -> None:
        raw = '{"latex": "abc", "bindings": []}'
        self.assertEqual(paper_cli._strip_markdown_fences(raw), raw)

        fenced = '```json\n{"latex": "abc", "bindings": []}\n```'
        self.assertEqual(paper_cli._strip_markdown_fences(fenced), raw)

        fenced_no_lang = '```\n{"latex": "abc", "bindings": []}\n```'
        self.assertEqual(paper_cli._strip_markdown_fences(fenced_no_lang), raw)

    def test_draft_envelope_valid_and_fenced_loads(self) -> None:
        p = self.tmp / "draft.json"
        p.write_text('```json\n{"latex": "Hello world", "bindings": []}\n```', encoding="utf-8")
        loaded = paper_cli._load_draft_envelope(p)
        self.assertEqual(loaded["latex"], "Hello world")
        self.assertEqual(loaded["bindings"], [])

    def test_draft_envelope_malformed_json_refuses(self) -> None:
        p = self.tmp / "draft.json"
        p.write_text('not json at all', encoding="utf-8")
        with self.assertRaises(Refused) as ctx:
            paper_cli._load_draft_envelope(p)
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")
        self.assertIn("invalid JSON", ctx.exception.detail)

    def test_draft_envelope_non_dict_refuses(self) -> None:
        p = self.tmp / "draft.json"
        p.write_text('[1, 2, 3]', encoding="utf-8")
        with self.assertRaises(Refused) as ctx:
            paper_cli._load_draft_envelope(p)
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")
        self.assertIn("must be a JSON object", ctx.exception.detail)

    def test_draft_envelope_missing_or_invalid_latex_refuses(self) -> None:
        p = self.tmp / "draft.json"
        p.write_text('{"bindings": []}', encoding="utf-8")
        with self.assertRaises(Refused) as ctx:
            paper_cli._load_draft_envelope(p)
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")
        self.assertIn("missing or non-string 'latex'", ctx.exception.detail)

        p.write_text('{"latex": 123, "bindings": []}', encoding="utf-8")
        with self.assertRaises(Refused) as ctx:
            paper_cli._load_draft_envelope(p)
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")
        self.assertIn("missing or non-string 'latex'", ctx.exception.detail)

    def test_draft_envelope_missing_or_invalid_bindings_refuses(self) -> None:
        p = self.tmp / "draft.json"
        p.write_text('{"latex": "ok"}', encoding="utf-8")
        with self.assertRaises(Refused) as ctx:
            paper_cli._load_draft_envelope(p)
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")
        self.assertIn("missing or non-list 'bindings'", ctx.exception.detail)

        p.write_text('{"latex": "ok", "bindings": "not a list"}', encoding="utf-8")
        with self.assertRaises(Refused) as ctx:
            paper_cli._load_draft_envelope(p)
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")
        self.assertIn("missing or non-list 'bindings'", ctx.exception.detail)

    def test_audit_envelope_valid_and_fenced_loads(self) -> None:
        p = self.tmp / "audit.json"
        p.write_text('```json\n{"verdicts": []}\n```', encoding="utf-8")
        loaded = paper_cli._load_audit_envelope(p)
        self.assertEqual(loaded["verdicts"], [])

    def test_audit_envelope_malformed_and_missing_keys_refuses(self) -> None:
        p = self.tmp / "audit.json"
        p.write_text('{"wrong": 1}', encoding="utf-8")
        with self.assertRaises(Refused) as ctx:
            paper_cli._load_audit_envelope(p)
        self.assertEqual(ctx.exception.code, "AUDIT_UNREADABLE")
        self.assertIn("missing or non-list 'verdicts'", ctx.exception.detail)

    def test_write_block_defensive_checks_refuse_bad_inputs(self) -> None:
        contract = unittest.mock.MagicMock()
        contract.mode = "argument"
        contract.citations_regime = "none"
        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(Path("/dummy"), contract, "not a dict", {})
        self.assertEqual(ctx.exception.code, "DRAFT_UNREADABLE")

        with self.assertRaises(Refused) as ctx:
            paper_write.write_block(Path("/dummy"), contract, {"latex": "ok", "bindings": []}, "not a dict")
        self.assertEqual(ctx.exception.code, "AUDIT_UNREADABLE")


if __name__ == "__main__":
    unittest.main()
