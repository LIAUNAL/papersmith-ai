"""paper-writing: region grammar, guidance registry, declarations,
provenance — the paper's own decisions.

A second, independent suite from `tests/test_paper_writing.py` on purpose
(design.md, `File Changes`: "a second class of the same name loses tests
silently"). Stdlib-only `unittest`, same fixture discipline: every fixture
lives under a `TemporaryDirectory`, and every `paper_scaffold.resolve_paper_dir`
/ `paper_guidance.resolve_guidance_dir` call passes an injected `forge_root`
so the real repository tree is never touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
CLI = SKILL_SCRIPTS / "paper_cli.py"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_block  # noqa: E402
import paper_region  # noqa: E402
import paper_guidance  # noqa: E402
import paper_scaffold  # noqa: E402
import paper_vocabulary  # noqa: E402
import paper_graph  # noqa: E402
import paper_declarations  # noqa: E402
import paper_marker  # noqa: E402
import paper_provenance  # noqa: E402
import paper_couplings  # noqa: E402
import paper_coupling_evidence  # noqa: E402
import paper_cli  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "tests"))
from paper_mutation import _run_against_mutant  # noqa: E402

AGENTS_DIR = FORGE_ROOT / ".claude" / "agents"


def _assert_guard_failed_under_mutation(case: unittest.TestCase, proc) -> None:
    """Shared two-part assertion every mutation-proof test in this suite
    uses: `MUTANT_IMPORTED_OK` proves the mutant module actually loaded and
    `unittest` actually ran the named test against it, and a non-zero exit
    proves the guard genuinely failed rather than the process crashing on
    import before the test ever ran."""
    output = proc.stdout + proc.stderr
    case.assertIn("MUTANT_IMPORTED_OK", output, output)
    case.assertNotEqual(proc.returncode, 0, output)


def _marker_pair(block_id: str, body: bytes) -> bytes:
    digest = hashlib.sha256(body).hexdigest()
    return (
        f"%% paper-writing block {block_id} begin sha256={digest}\n".encode("ascii")
        + body
        + f"%% paper-writing block {block_id} end\n".encode("ascii")
    )


class DisjointGrammarTests(unittest.TestCase):
    """`design.md`, `Two grammars coexist by mutual non-prefix, pinned in
    both directions`. Five checks, four derived from
    `paper_block.MARKER_PREFIX` and `paper_region.KINDS` rather than
    written out by hand."""

    def test_marker_prefix_has_exactly_three_tokens(self) -> None:
        self.assertEqual(
            len(paper_block.MARKER_PREFIX.split()), 3,
            "a narrowing of MARKER_PREFIX to 'block' status alone (dropping "
            "a token) changes the slot this test derives everything else "
            "from",
        )

    def test_marker_prefix_slot_two_is_block(self) -> None:
        self.assertEqual(paper_block.MARKER_PREFIX.split()[2], b"block")

    def test_block_is_not_a_region_kind_and_no_kind_prefixes_another(self) -> None:
        block_token = paper_block.MARKER_PREFIX.split()[2]
        encoded_kinds = [kind.encode("ascii") for kind in paper_region.KINDS]
        self.assertNotIn(block_token, encoded_kinds)
        candidates = encoded_kinds + [block_token]
        for i, left in enumerate(candidates):
            for j, right in enumerate(candidates):
                if i == j:
                    continue
                self.assertFalse(
                    right.startswith(left),
                    f"{right!r} is a prefix of {left!r}; the two grammars would "
                    "collide under Phase 1's own startswith() check",
                )

    def test_marker_prefix_is_pinned_exactly(self) -> None:
        self.assertEqual(
            paper_block.MARKER_PREFIX, b"%% paper-writing block",
            "MARKER_PREFIX is pinned exactly, trailing space included, "
            "deliberately brittle: a legitimate Phase 1 edit to this "
            "constant is EXPECTED to redden this test, on purpose -- it "
            "is not a bug in this test and must not be loosened to admit "
            "the change silently. A narrowing to 'b\"%% paper-writing "
            "block \"' (trailing space) would split identically and "
            "silently disarm Phase 1's own MARKER_MALFORMED detection.",
        )

    def test_regions_only_file_reports_zero_blocks_and_two_regions(self) -> None:
        declarations_bytes, _digest = paper_region.build_region_bytes(
            "declarations", {"generation": 0, "records": []}
        )
        provenance_bytes, _digest2 = paper_region.build_region_bytes(
            "provenance", {"records": []}
        )
        data = declarations_bytes + provenance_bytes

        result = paper_block.status(data)
        self.assertEqual(result["blocks"], [])

        self.assertIsNotNone(paper_region.find_region(data, "declarations"))
        self.assertIsNotNone(paper_region.find_region(data, "provenance"))

    def test_one_block_plus_both_regions_are_seen_by_their_own_parser_only(self) -> None:
        body = b"prose\n"
        data = _marker_pair("intro", body)
        declarations_bytes, _digest = paper_region.build_region_bytes(
            "declarations", {"generation": 0, "records": []}
        )
        provenance_bytes, _digest2 = paper_region.build_region_bytes(
            "provenance", {"records": []}
        )
        data = data + declarations_bytes + provenance_bytes

        result = paper_block.status(data)
        self.assertEqual(len(result["blocks"]), 1)
        self.assertEqual(result["blocks"][0]["id"], "intro")

        self.assertIsNotNone(paper_region.find_region(data, "declarations"))
        self.assertIsNotNone(paper_region.find_region(data, "provenance"))


class RegionGrammarMutationTests(unittest.TestCase):
    """Mutation 1 (design.md): renaming our sentinel's slot 2 to `block`
    proves `DisjointGrammarTests`'s behavioural scenario can fire."""

    def test_mutation_1_renaming_the_sentinel_to_block_breaks_the_regions_only_scenario(
        self,
    ) -> None:
        proc = _run_against_mutant(
            'begin_line = f"%% paper-writing {kind} begin sha256={digest}\\n".encode("ascii")',
            'begin_line = f"%% paper-writing block begin sha256={digest}\\n".encode("ascii")',
            "tests.test_paper_decisions.DisjointGrammarTests"
            ".test_regions_only_file_reports_zero_blocks_and_two_regions",
            source_path=SKILL_SCRIPTS / "paper_region.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class RegionParsingTests(unittest.TestCase):
    """Grammar-level refusals: `REGION_MALFORMED`, `REGION_DUPLICATED`,
    `REGION_UNPAIRED`, and the round-trip through `serialize_body` /
    `deserialize_body` / digesting."""

    def test_absent_region_returns_none(self) -> None:
        self.assertIsNone(paper_region.find_region(b"nothing here\n", "declarations"))
        self.assertIsNone(paper_region.read_region(b"nothing here\n", "declarations"))

    def test_malformed_marker_line_refuses(self) -> None:
        data = b"%% paper-writing declarations begins sha256=deadbeef\n"
        with self.assertRaises(Refused) as ctx:
            paper_region.find_region(data, "declarations")
        self.assertEqual(ctx.exception.code, "REGION_MALFORMED")

    def test_duplicated_begin_marker_refuses(self) -> None:
        region_bytes, _digest = paper_region.build_region_bytes(
            "declarations", {"generation": 0, "records": []}
        )
        begin_line = region_bytes.splitlines(keepends=True)[0]
        data = begin_line + region_bytes
        with self.assertRaises(Refused) as ctx:
            paper_region.find_region(data, "declarations")
        self.assertEqual(ctx.exception.code, "REGION_DUPLICATED")

    def test_unpaired_begin_marker_refuses(self) -> None:
        region_bytes, digest = paper_region.build_region_bytes(
            "declarations", {"generation": 0, "records": []}
        )
        begin_only = region_bytes.split(b"%% paper-writing declarations end\n")[0]
        with self.assertRaises(Refused) as ctx:
            paper_region.find_region(begin_only, "declarations")
        self.assertEqual(ctx.exception.code, "REGION_UNPAIRED")

    def test_round_trip_preserves_body_and_verifies_digest(self) -> None:
        body_obj = {"generation": 3, "records": [{"kind": "declaration", "id": "x"}]}
        region_bytes, digest = paper_region.build_region_bytes("declarations", body_obj)
        record = paper_region.read_region(region_bytes, "declarations")
        self.assertEqual(record["body"], body_obj)
        self.assertEqual(record["digest"], digest)
        self.assertEqual(paper_region.current_digest(record["body_bytes"]), digest)

    def test_canonical_serialization_is_key_order_independent(self) -> None:
        first = paper_region.serialize_body({"b": 1, "a": 2})
        second = paper_region.serialize_body({"a": 2, "b": 1})
        self.assertEqual(first, second)

    def test_replace_or_append_appends_when_absent(self) -> None:
        region_bytes, _digest = paper_region.build_region_bytes(
            "declarations", {"generation": 0, "records": []}
        )
        result = paper_region.replace_or_append(b"prose\n", "declarations", region_bytes, None)
        self.assertTrue(result.startswith(b"prose\n"))
        self.assertTrue(result.endswith(region_bytes))

    def test_replace_or_append_replaces_existing_span_exactly(self) -> None:
        first_bytes, _digest = paper_region.build_region_bytes(
            "declarations", {"generation": 0, "records": []}
        )
        data = b"before\n" + first_bytes + b"after\n"
        existing = paper_region.find_region(data, "declarations")
        second_bytes, _digest2 = paper_region.build_region_bytes(
            "declarations", {"generation": 1, "records": []}
        )
        replaced = paper_region.replace_or_append(data, "declarations", second_bytes, existing)
        self.assertEqual(replaced, b"before\n" + second_bytes + b"after\n")


class GuidanceRegistryTests(unittest.TestCase):
    """`specs/guidance-registry/spec.md`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.guidance_dir = self.forge_root / "guidance"

    def _write_marker(self, folder: str, obj) -> None:
        target = self.guidance_dir / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / ".paper-writing.json").write_text(json.dumps(obj), encoding="utf-8")

    def test_fresh_clone_reports_every_folder_unclassified_refuses_nothing(self) -> None:
        for folder in ("paper-guide", "reference-papers", "style-reference-notes"):
            (self.guidance_dir / folder).mkdir(parents=True)

        registry = paper_guidance.read_registry(self.guidance_dir)

        self.assertEqual(
            registry,
            {
                "paper-guide": "unclassified",
                "reference-papers": "unclassified",
                "style-reference-notes": "unclassified",
            },
        )

    def test_folder_named_like_a_class_stays_unclassified(self) -> None:
        (self.guidance_dir / "style-reference-notes").mkdir(parents=True)

        registry = paper_guidance.read_registry(self.guidance_dir)

        self.assertEqual(registry["style-reference-notes"], "unclassified")

    def test_valid_marker_classifies_its_folder(self) -> None:
        self._write_marker("prior-papers", {"class": "evidence"})

        registry = paper_guidance.read_registry(self.guidance_dir)

        self.assertEqual(registry["prior-papers"], "evidence")

    def test_out_of_vocabulary_class_refuses(self) -> None:
        self._write_marker("prior-papers", {"class": "reference-material"})

        with self.assertRaises(Refused) as ctx:
            paper_guidance.read_registry(self.guidance_dir)
        self.assertEqual(ctx.exception.code, "UNKNOWN_GUIDANCE_CLASS")
        self.assertIn("reference-material", ctx.exception.detail)
        self.assertIn("prior-papers", ctx.exception.detail)

    def test_marker_with_extra_key_refuses_malformed(self) -> None:
        self._write_marker("prior-papers", {"class": "evidence", "extra": True})

        with self.assertRaises(Refused) as ctx:
            paper_guidance.read_registry(self.guidance_dir)
        self.assertEqual(ctx.exception.code, "MALFORMED_GUIDANCE_MARKER")

    def test_a_source_root_shaped_marker_refuses_as_an_unknown_key(self) -> None:
        """`the-requirement-names-the-section-that-feeds-it`,
        `source-section-binding` spec, `Requirement: The Marker Grammar Is
        Validated, And Disjoint From guidance/'s`: `guidance/`'s own
        reader (`_MARKER_ALLOWED_KEYS = ("class",)`) MUST NOT silently
        accept a source-root-shaped marker (`{"revisions": {...}}`) --
        regression proof only, no production edit expected here, since
        `_MARKER_ALLOWED_KEYS` already excludes `revisions`."""
        self._write_marker(
            "prior-papers",
            {"revisions": {"revision_prefix": "r", "ordinal_digits": 2}},
        )

        with self.assertRaises(Refused) as ctx:
            paper_guidance.read_registry(self.guidance_dir)

        self.assertEqual(ctx.exception.code, "MALFORMED_GUIDANCE_MARKER")
        self.assertIn("revisions", ctx.exception.detail)

    def test_marker_that_is_not_an_object_refuses_malformed(self) -> None:
        target = self.guidance_dir / "prior-papers"
        target.mkdir(parents=True)
        (target / ".paper-writing.json").write_text("[1, 2]", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_guidance.read_registry(self.guidance_dir)
        self.assertEqual(ctx.exception.code, "MALFORMED_GUIDANCE_MARKER")

    def test_guidance_outside_repository_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_guidance.resolve_guidance_dir("../", forge_root=self.forge_root)
        self.assertEqual(ctx.exception.code, "GUIDANCE_OUTSIDE_REPOSITORY")

    def test_two_arbitrarily_named_folders_each_classify_from_their_own_marker(self) -> None:
        self._write_marker("first-unused-name", {"class": "style-reference"})
        self._write_marker("second-unused-name", {"class": "evidence"})

        registry = paper_guidance.read_registry(self.guidance_dir)

        self.assertEqual(registry["first-unused-name"], "style-reference")
        self.assertEqual(registry["second-unused-name"], "evidence")

    def test_registry_reads_no_hardcoded_folder_name(self) -> None:
        """The registry's own source names no specific `guidance/<folder>`
        anywhere (`specs/guidance-registry/spec.md`, `Requirement: The
        Registry Reads No Hardcoded Folder Path`)."""
        source = (SKILL_SCRIPTS / "paper_guidance.py").read_text(encoding="utf-8")
        for hardcoded in ("paper-guide", "reference-papers"):
            self.assertNotIn(hardcoded, source)

    def test_marker_allowed_keys_is_derived_from_paper_marker_seal_key(self) -> None:
        """tasks.md 3.1: `_MARKER_ALLOWED_KEYS` is `("class",
        paper_marker.SEAL_KEY)` -- never a second, re-spelled literal."""
        self.assertEqual(
            paper_guidance._MARKER_ALLOWED_KEYS, ("class", paper_marker.SEAL_KEY),
        )

    def test_a_valid_sealed_marker_classifies_its_folder(self) -> None:
        """`specs/guidance-registry/spec.md`, scenario `A valid sealed
        marker classifies its folder`."""
        obj = {"class": "evidence"}
        obj[paper_marker.SEAL_KEY] = paper_marker.computed_seal(obj)
        self._write_marker("prior-papers", obj)

        registry = paper_guidance.read_registry(self.guidance_dir)

        self.assertEqual(registry["prior-papers"], "evidence")

    def test_a_malformed_seal_shape_refuses_as_malformed_not_hand_edited(self) -> None:
        self._write_marker(
            "prior-papers", {"class": "evidence", paper_marker.SEAL_KEY: "not-a-hex-digest"},
        )

        with self.assertRaises(Refused) as ctx:
            paper_guidance.read_registry(self.guidance_dir)

        self.assertEqual(ctx.exception.code, "MALFORMED_GUIDANCE_MARKER")
        self.assertIn(paper_marker.SEAL_KEY, ctx.exception.detail)

    def test_a_mismatched_seal_refuses_hand_edited_naming_both_digests(self) -> None:
        obj = {"class": "evidence", paper_marker.SEAL_KEY: "a" * 64}
        self._write_marker("prior-papers", obj)

        with self.assertRaises(Refused) as ctx:
            paper_guidance.read_registry(self.guidance_dir)

        self.assertEqual(ctx.exception.code, "GUIDANCE_DECLARATION_HAND_EDITED")
        self.assertIn("a" * 64, ctx.exception.detail)
        self.assertIn(paper_marker.computed_seal(obj), ctx.exception.detail)
        self.assertIn(paper_marker.SEAL_STRENGTH, ctx.exception.detail)

    def test_declaration_state_reports_undeclared_unsealed_sealed(self) -> None:
        """tasks.md 5.15: `paper_guidance.declaration_state` reports the
        SAME three reachable values `paper_declarations.declaration_state`
        reports for a `PROSE` root -- `'n/a'` never applies here, since
        every LISTED `guidance/` folder is classifiable."""
        absent = self.guidance_dir / "absent-folder"
        absent.mkdir(parents=True)
        self.assertEqual(paper_guidance.declaration_state(absent), "undeclared")

        self._write_marker("unsealed-folder", {"class": "evidence"})
        self.assertEqual(
            paper_guidance.declaration_state(self.guidance_dir / "unsealed-folder"),
            "declared-unsealed",
        )

        obj = {"class": "style-reference"}
        obj[paper_marker.SEAL_KEY] = paper_marker.computed_seal(obj)
        self._write_marker("sealed-folder", obj)
        self.assertEqual(
            paper_guidance.declaration_state(self.guidance_dir / "sealed-folder"),
            "declared-sealed",
        )

    def test_declaration_state_propagates_hand_edited_refusal(self) -> None:
        """`declaration_state` reuses `_classify`'s own seal-verification
        path (`_read_marker`), so a mismatched seal refuses identically
        through either caller -- never a second, drifting notion of
        whether a folder's own marker is good."""
        obj = {"class": "evidence", paper_marker.SEAL_KEY: "a" * 64}
        self._write_marker("hand-edited-folder", obj)

        with self.assertRaises(Refused) as ctx:
            paper_guidance.declaration_state(self.guidance_dir / "hand-edited-folder")
        self.assertEqual(ctx.exception.code, "GUIDANCE_DECLARATION_HAND_EDITED")


class GuidanceRegistryMutationTests(unittest.TestCase):
    """Mutation 4 (design.md): defaulting an unclassified folder to
    `style-reference` proves the fresh-clone scenario can fire."""

    def test_mutation_4_defaulting_unclassified_to_style_reference_breaks_the_fresh_clone_scenario(
        self,
    ) -> None:
        proc = _run_against_mutant(
            'return "unclassified"',
            'return "style-reference"',
            "tests.test_paper_decisions.GuidanceRegistryTests"
            ".test_fresh_clone_reports_every_folder_unclassified_refuses_nothing",
            source_path=SKILL_SCRIPTS / "paper_guidance.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_declaration_state_sealed_branch_is_reachable(self) -> None:
        """tasks.md 5.15: collapsing `declaration_state`'s sealed/unsealed
        ternary to always report `declared-unsealed` must turn the sealed
        assertion red -- proving the sealed branch is actually reached
        through the real function, not merely present in source."""
        proc = _run_against_mutant(
            'return "declared-sealed" if result["sealed"] else "declared-unsealed"',
            'return "declared-unsealed"',
            "tests.test_paper_decisions.GuidanceRegistryTests"
            ".test_declaration_state_reports_undeclared_unsealed_sealed",
            source_path=SKILL_SCRIPTS / "paper_guidance.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class SourceMdClassificationTests(unittest.TestCase):
    """`the-skill-stops-trusting-memory`, item 2/3: `paper_guidance.
    classify_source_md` -- the pure lookup `validate --source-md`'s guard is
    built on."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.guidance_dir = self.forge_root / "guidance"

    def _write_marker(self, folder: str, cls: str) -> Path:
        target = self.guidance_dir / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / ".paper-writing.json").write_text(json.dumps({"class": cls}), encoding="utf-8")
        return target

    def test_a_path_under_a_style_reference_folder_classifies_style_reference(self) -> None:
        folder = self._write_marker("reference-papers", "style-reference")
        paper_dir = folder / "paper1" / "paper1.md"
        paper_dir.parent.mkdir(parents=True)
        paper_dir.write_text("body", encoding="utf-8")

        self.assertEqual(
            paper_guidance.classify_source_md(paper_dir, self.guidance_dir), "style-reference",
        )

    def test_a_path_under_an_evidence_folder_classifies_evidence(self) -> None:
        folder = self._write_marker("source-manuscript", "evidence")
        paper_dir = folder / "paper1" / "paper1.md"
        paper_dir.parent.mkdir(parents=True)
        paper_dir.write_text("body", encoding="utf-8")

        self.assertEqual(paper_guidance.classify_source_md(paper_dir, self.guidance_dir), "evidence")

    def test_a_path_under_an_unmarked_folder_classifies_unclassified(self) -> None:
        target = self.guidance_dir / "area-benchmark" / "paper1"
        target.mkdir(parents=True)
        md_path = target / "paper1.md"
        md_path.write_text("body", encoding="utf-8")

        self.assertEqual(
            paper_guidance.classify_source_md(md_path, self.guidance_dir), "unclassified",
        )

    def test_a_path_outside_guidance_entirely_classifies_none(self) -> None:
        outside = Path(self._tmp.name) / "elsewhere" / "paper1.md"
        outside.parent.mkdir(parents=True)
        outside.write_text("body", encoding="utf-8")

        self.assertIsNone(paper_guidance.classify_source_md(outside, self.guidance_dir))


class ValidateSourceMdGuardTests(unittest.TestCase):
    """`the-skill-stops-trusting-memory`, item 2/3: `validate --source-md`
    refuses a `style-reference`-classed source and accepts an
    `evidence`-classed one -- the exact scenario measured before this
    change: `validate --block X --quote "<a sentence lifted from a
    style-reference paper>" --source-md guidance/reference-papers/<paper>/
    <paper>.md --verdict holds` used to return `satisfied`.

    Runs under the real, non-injectable `FORGE_ROOT` default, the same
    `implementations/` convention `SkeletonPathContainmentTests`
    (`tests/test_paper_writing.py`) uses, because `cmd_validate` resolves
    both `--paper`/`--guidance` through it."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / "implementations"
            / f".paper-writing-validate-source-md-guard-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.guidance_dir = self.test_root / "guidance"

    def _write_marker(self, folder: str, cls: str) -> Path:
        target = self.guidance_dir / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / ".paper-writing.json").write_text(json.dumps({"class": cls}), encoding="utf-8")
        return target

    def _write_source(self, folder: Path, text: str) -> Path:
        paper_dir = folder / "paper1"
        paper_dir.mkdir(parents=True, exist_ok=True)
        md_path = paper_dir / "paper1.md"
        md_path.write_text(text, encoding="utf-8")
        return md_path

    def _args(self, *, source_md: Path, quote: str) -> argparse.Namespace:
        return argparse.Namespace(
            paper=str(self.paper_dir), block="intro.b1", claim="c1", quote=quote,
            source_md=str(source_md), verdict="holds", reason=None, cite_key=None,
            identifier=None, resolver=None, metadata_digest=None, regime="none",
            section_md=None, round=None, guidance=str(self.guidance_dir), body=None,
            sentence=None,
            # `min_sources=1`: this class's own proof is the guidance-
            # classification guard (style-reference/evidence/unclassified),
            # orthogonal to `the-pdf-arrives-or-the-operator-is-told`'s own
            # distinct-source-count minimum -- pinned to 1 so a single
            # submitted record still reads `satisfied`, exactly as before
            # that feature existed.
            min_sources=1,
        )

    def test_a_quote_from_a_style_reference_source_refuses(self) -> None:
        folder = self._write_marker("reference-papers", "style-reference")
        source_md = self._write_source(folder, "An Explainable Framework Integrating Local")

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_validate(self._args(
                source_md=source_md, quote="An Explainable Framework Integrating Local",
            ))

        self.assertEqual(ctx.exception.code, "SOURCE_STYLE_REFERENCE")
        self.assertIn(str(source_md), ctx.exception.detail)

    def test_a_quote_from_an_evidence_source_is_accepted(self) -> None:
        folder = self._write_marker("source-manuscript", "evidence")
        source_md = self._write_source(folder, "scientific data")

        result = paper_cli.cmd_validate(self._args(source_md=source_md, quote="scientific data"))

        self.assertEqual(result["status"], "satisfied")

    def test_a_quote_from_an_unclassified_source_refuses(self) -> None:
        target = self.guidance_dir / "area-benchmark" / "paper1"
        target.mkdir(parents=True)
        source_md = target / "paper1.md"
        source_md.write_text("hello world quote", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_validate(self._args(source_md=source_md, quote="hello world quote"))

        self.assertEqual(ctx.exception.code, "SOURCE_NOT_EVIDENCE")

    def test_a_quote_from_outside_guidance_entirely_is_unaffected_by_this_guard(self) -> None:
        """`classify_source_md` returns `None` for a path outside
        `guidance_dir` altogether -- this guard must not refuse THAT case;
        whatever else may apply to it is out of this gate's scope."""
        outside_dir = self.test_root / "elsewhere"
        outside_dir.mkdir()
        source_md = outside_dir / "paper1.md"
        source_md.write_text("free text", encoding="utf-8")

        result = paper_cli.cmd_validate(self._args(source_md=source_md, quote="free text"))

        self.assertEqual(result["status"], "satisfied")

    def test_no_claim_given_never_reaches_the_guard_and_writes_nothing(self) -> None:
        """The guard lives inside `_build_evidence_record`, called only
        when `--claim` is given -- a bare `validate --block` (status
        check) never touches `guidance_dir` classification at all."""
        args = self._args(source_md=Path("unused.md"), quote="unused")
        args.claim = None

        result = paper_cli.cmd_validate(args)

        self.assertEqual(result["status"], "satisfied")
        self.assertEqual(result["unsupported"], [])

    def test_a_quote_from_a_hand_edited_sealed_evidence_source_refuses(self) -> None:
        """`specs/guidance-registry/spec.md`, scenario `A mismatched seal
        refuses, with no adopt escape` -- reached through `validate
        --source-md`, a gating verb, never only through `plan` (design.md
        Decision C, invariant 4)."""
        folder = self.guidance_dir / "source-manuscript"
        folder.mkdir(parents=True)
        obj = {"class": "evidence", paper_marker.SEAL_KEY: "a" * 64}
        (folder / ".paper-writing.json").write_text(json.dumps(obj), encoding="utf-8")
        source_md = self._write_source(folder, "scientific data")

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_validate(self._args(source_md=source_md, quote="scientific data"))

        self.assertEqual(ctx.exception.code, "GUIDANCE_DECLARATION_HAND_EDITED")


class ValidateSourceMdGuardMutationTests(unittest.TestCase):
    """Proves both new refusal branches are load-bearing, not dead code."""

    def _write_marker(self, guidance_dir: Path, folder: str, cls: str) -> Path:
        target = guidance_dir / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / ".paper-writing.json").write_text(json.dumps({"class": cls}), encoding="utf-8")
        return target

    def test_mutation_dropping_the_style_reference_branch_breaks_the_guard(self) -> None:
        proc = _run_against_mutant(
            'if source_class == "style-reference":\n'
            '        raise Refused(\n'
            '            "SOURCE_STYLE_REFERENCE",\n'
            '            f"{source_md} resolves inside a guidance folder classed '
            "'style-reference'; \"\n"
            '            "style-reference feeds style only, never a quote submitted as evidence",\n'
            '        )',
            'if False:\n'
            '        raise Refused("SOURCE_STYLE_REFERENCE", "unreachable")',
            "tests.test_paper_decisions.ValidateSourceMdGuardTests"
            ".test_a_quote_from_a_style_reference_source_refuses",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_dropping_the_not_evidence_branch_breaks_the_guard(self) -> None:
        proc = _run_against_mutant(
            'if source_class != "evidence":\n'
            '        raise Refused(\n'
            '            "SOURCE_NOT_EVIDENCE",\n'
            '            f"{source_md} resolves inside a guidance folder classed {source_class!r}, "\n'
            '            "not \'evidence\'; classify the folder before quoting it as evidence",\n'
            '        )',
            'if False:\n'
            '        raise Refused("SOURCE_NOT_EVIDENCE", "unreachable")',
            "tests.test_paper_decisions.ValidateSourceMdGuardTests"
            ".test_a_quote_from_an_unclassified_source_refuses",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_the_class_marker_seal_comparison_is_reachable_through_validate_not_only_plan(
        self,
    ) -> None:
        """tasks.md 3.10 (the non-negotiable constraint): replacing the
        seal-comparison line inside `_classify` with a constant `True`
        (i.e. never mismatched) MUST be caught by a test driven through
        `validate --source-md`, a gating verb -- never only through the
        read-only `plan`. This mutation runs against `paper_guidance.py`,
        not `paper_cli.py`: `validate` still reaches `_classify`
        unchanged, but the reader itself no longer detects the mismatch."""
        proc = _run_against_mutant(
            "        if recorded != computed:",
            "        if False:",
            "tests.test_paper_decisions.ValidateSourceMdGuardTests"
            ".test_a_quote_from_a_hand_edited_sealed_evidence_source_refuses",
            source_path=SKILL_SCRIPTS / "paper_guidance.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class GuidanceIngestedPapersTests(unittest.TestCase):
    """`the-phases-are-derived-not-remembered`, design.md D4; tasks.md
    7.6-7.7. `read_registry` only enumerates ONE level under `guidance/`;
    `ingested_papers` walks the real two-level shape
    (`guidance/<root>/<paper>/<paper>.md`) with `Path.iterdir()`, which is
    gitignore-blind BY CONSTRUCTION -- never `fd`/`rg`, which honour
    `.gitignore` and would report a populated-but-ignored tree empty."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.guidance_dir = self.forge_root / "guidance"

    def _write_paper(self, root: str, folder: str, *, extra_files: tuple = ()) -> None:
        paper_dir = self.guidance_dir / root / folder
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / f"{folder}.md").write_text("# Title\n", encoding="utf-8")
        for name in extra_files:
            (paper_dir / name).write_bytes(b"")

    def test_a_gitignored_populated_tree_reports_as_populated_not_empty(self) -> None:
        """tasks.md 7.7: mirrors the real repository's own `.gitignore`
        shape (`guidance/*/*`) so the fixture is not merely synthetic in
        spirit -- an actual ignore pattern matching every path this walk
        must still find. `Path.iterdir()` never consults `.gitignore` at
        all, so this is true regardless; the point of the fixture is to
        make that explicit rather than assumed."""
        self._write_paper("source-manuscript", "q77213-004-11029-2", extra_files=("_page_0_Picture_2.jpeg",))
        self._write_paper("paper-guide", "brainsci-16-00363")
        self._write_paper("paper-guide", "Li_2026_Prog._Biomed._Eng._8_022013")
        (self.guidance_dir / "area-benchmark").mkdir()
        (self.guidance_dir / ".gitignore").write_text(
            "guidance/*/*\n!guidance/*/.gitkeep\n", encoding="utf-8",
        )

        registry = paper_guidance.ingested_papers(self.guidance_dir)

        self.assertEqual(
            {folder["folder"] for folder in registry["source-manuscript"]}, {"q77213-004-11029-2"},
        )
        self.assertEqual(
            {folder["folder"] for folder in registry["paper-guide"]},
            {"brainsci-16-00363", "Li_2026_Prog._Biomed._Eng._8_022013"},
        )
        self.assertEqual(registry["area-benchmark"], [])
        total_papers = sum(len(papers) for papers in registry.values())
        self.assertEqual(total_papers, 3)

    def test_a_paper_folder_missing_its_own_named_markdown_is_not_reported(self) -> None:
        (self.guidance_dir / "reference-papers" / "not-a-paper").mkdir(parents=True)

        registry = paper_guidance.ingested_papers(self.guidance_dir)

        self.assertEqual(registry["reference-papers"], [])

    def test_a_non_existent_guidance_dir_reports_an_empty_registry(self) -> None:
        registry = paper_guidance.ingested_papers(self.forge_root / "no-such-guidance")
        self.assertEqual(registry, {})

    def test_against_the_real_shipped_guidance_tree(self) -> None:
        """The PROPERTY, not this checkout's own particular counts (U3d
        left this test pinned to one root's own paper count and to a
        whole-corpus total, measured against ONE machine's ambient,
        gitignored content on ONE day -- `git ls-files guidance/` shows
        only five `.gitkeep` files travel, so a fresh clone reports every
        root empty and every one of those counts was false on that
        checkout; never repeated by name in this docstring, the same
        reason `ForgeVocabularyDerivedGuardTests` scans this suite's own
        commentary). The ROOT FOLDERS themselves ARE tracked
        (`guidance/<root>/.gitkeep`), so which roots exist is read off
        disk here too, never hand-listed.

        The property this test exists to hold: `ingested_papers` must
        report the SAME papers a gitignore-blind walk (`Path.iterdir()`,
        never `fd`/`rg`) finds on THIS disk right now -- independently
        re-derived here, against the real, checked-out tree, so a
        regression that silently traded `Path.iterdir()` for gitignore-
        aware tooling would still be caught: it would report empty (or
        undercounted) roots while this test's OWN gitignore-blind count
        disagrees. True on every checkout, whether the gitignored
        `guidance/*/*` content is fully populated or (a fresh clone)
        entirely absent beyond its own tracked `.gitkeep`."""
        real_guidance_dir = paper_guidance.resolve_guidance_dir(
            None, forge_root=FORGE_ROOT,
        )
        registry = paper_guidance.ingested_papers(real_guidance_dir)

        expected_roots = {
            entry.name for entry in real_guidance_dir.iterdir() if entry.is_dir()
        }
        self.assertEqual(set(registry), expected_roots)
        for root_name, papers in registry.items():
            root_dir = real_guidance_dir / root_name
            expected = sorted(
                entry.name for entry in root_dir.iterdir()
                if entry.is_dir() and (entry / f"{entry.name}.md").is_file()
            )
            self.assertEqual(
                sorted(paper["folder"] for paper in papers), expected,
                f"{root_name!r}: ingested_papers must match a gitignore-blind walk taken now",
            )


class SectionCitationStatusTests(unittest.TestCase):
    """`no-citation-before-its-paper-is-ingested`, item 1:
    `paper_guidance.section_citation_status`/`section_citation_folders` --
    the discovery half of the per-section citation-folder capability.
    A folder is a section's own citation folder exactly when its name
    equals a section id, and that id is always DERIVED from the parsed
    corpus, never a hand-listed tuple -- exercised below against a section
    id no production section contract has ever declared, which a
    hand-listed tuple could not have found."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.guidance_dir = self.forge_root / "guidance"

    def test_a_section_with_no_folder_yet_reports_absent_with_no_classification(self) -> None:
        status = paper_guidance.section_citation_status(self.guidance_dir, "introduction")
        self.assertEqual(
            status,
            {"section": "introduction", "exists": False, "classification": None,
             "ingested": [], "pending_pdfs": []},
        )

    def test_a_freshly_created_folder_reports_unclassified_and_empty(self) -> None:
        (self.guidance_dir / "introduction").mkdir(parents=True)
        status = paper_guidance.section_citation_status(self.guidance_dir, "introduction")
        self.assertTrue(status["exists"])
        self.assertEqual(status["classification"], "unclassified")
        self.assertEqual(status["ingested"], [])
        self.assertEqual(status["pending_pdfs"], [])

    def test_a_loose_pdf_is_reported_pending_until_ingestion_moves_it(self) -> None:
        section_dir = self.guidance_dir / "introduction"
        section_dir.mkdir(parents=True)
        (section_dir / "smith2024.pdf").write_bytes(b"%PDF-1.4 fake")

        status = paper_guidance.section_citation_status(self.guidance_dir, "introduction")
        self.assertEqual(status["pending_pdfs"], ["smith2024.pdf"])
        self.assertEqual(status["ingested"], [])

        # paper-ingestion's own contract: ingestion MOVES the PDF into
        # <paper>/<paper>.pdf and writes <paper>/<paper>.md alongside it.
        (section_dir / "smith2024.pdf").unlink()
        paper_dir = section_dir / "smith2024"
        paper_dir.mkdir()
        (paper_dir / "smith2024.pdf").write_bytes(b"%PDF-1.4 fake")
        (paper_dir / "smith2024.md").write_text("# Smith 2024\n", encoding="utf-8")

        after = paper_guidance.section_citation_status(self.guidance_dir, "introduction")
        self.assertEqual(after["pending_pdfs"], [])
        self.assertEqual([p["folder"] for p in after["ingested"]], ["smith2024"])

    def test_a_classified_folder_reports_its_own_class(self) -> None:
        section_dir = self.guidance_dir / "introduction"
        section_dir.mkdir(parents=True)
        (section_dir / ".paper-writing.json").write_text(
            json.dumps({"class": "evidence"}), encoding="utf-8",
        )
        status = paper_guidance.section_citation_status(self.guidance_dir, "introduction")
        self.assertEqual(status["classification"], "evidence")

    def test_folders_are_discovered_from_a_section_id_never_hardcoded(self) -> None:
        """Never assumed: a made-up section id this repository's own
        contracts have never declared, `unlikely-future-section`, is
        discovered from a real parsed corpus exactly like any other id --
        proof that nothing in this path enumerates section ids from a
        literal tuple."""
        sections_dir = self.forge_root / "sections"
        sections_dir.mkdir()
        header = json.dumps({
            "section": "unlikely-future-section", "position": 1,
            "blocks": [
                {"id": "only", "requires_facts": [], "requires_declarations": [], "citations": "none"},
            ],
        })
        (sections_dir / "99-unlikely.md").write_text(
            f"---\n{header}\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n"
            "### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        (self.guidance_dir / "unlikely-future-section").mkdir(parents=True)

        corpus = paper_graph.assemble_corpus(sections_dir)
        self.assertIn("unlikely-future-section", corpus.sections)

        folders = paper_guidance.section_citation_folders(self.guidance_dir, corpus.sections)
        self.assertTrue(folders["unlikely-future-section"]["exists"])
        self.assertEqual(folders["unlikely-future-section"]["classification"], "unclassified")

    def test_a_section_id_the_registry_has_never_seen_is_untouched_by_this_walk(self) -> None:
        """ADDITIVE, never destructive: an unrelated function-named folder
        sitting beside a section folder keeps reporting through
        `read_registry` exactly as before -- this walk never mutates or
        reclassifies it."""
        (self.guidance_dir / "reference-papers").mkdir(parents=True)
        (self.guidance_dir / "reference-papers" / ".paper-writing.json").write_text(
            json.dumps({"class": "style-reference"}), encoding="utf-8",
        )
        (self.guidance_dir / "introduction").mkdir(parents=True)

        paper_guidance.section_citation_folders(self.guidance_dir, {"introduction"})

        registry = paper_guidance.read_registry(self.guidance_dir)
        self.assertEqual(registry["reference-papers"], "style-reference")


class SectionCitationStatusMutationTests(unittest.TestCase):
    """The decisive proof for item 1: a hand-listed tuple of section ids
    standing in for the corpus-derived set must fail
    `SectionCitationStatusTests.test_folders_are_discovered_from_a_section_
    id_never_hardcoded` -- exactly the failure mode the launch context
    names ("one went stale silently... the day the skill grew past its
    first three verbs")."""

    def test_mutation_a_hardcoded_tuple_in_place_of_sorted_section_ids_fails_the_discovery_proof(
        self,
    ) -> None:
        proc = _run_against_mutant(
            "    return {\n"
            "        section_id: section_citation_status(guidance_dir, section_id)\n"
            "        for section_id in sorted(section_ids)\n"
            "    }",
            "    return {\n"
            "        section_id: section_citation_status(guidance_dir, section_id)\n"
            '        for section_id in ("introduction", "related-work", "materials-and-methods")\n'
            "    }",
            "tests.test_paper_decisions.SectionCitationStatusTests"
            ".test_folders_are_discovered_from_a_section_id_never_hardcoded",
            source_path=SKILL_SCRIPTS / "paper_guidance.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


_FIXED_CLOCK = "2024-01-01T00:00:00+00:00"


def _block_record(
    qualified_id: str, *, requires_facts=(), requires_declarations=(), optional=False,
    section="synthetic",
):
    """A minimal, real `paper_graph.BlockRecord` — `affected_blocks` only
    ever reads `.requires_facts`/`.requires_declarations`, so the other
    fields are filled with harmless placeholders rather than driven through
    a full `assemble_corpus` disk fixture. `section` defaults to the same
    placeholder every existing caller already relies on; a caller that
    needs `dataset_placement_candidates` to group by a REAL section name
    (it reads `.section`, never `qualified_id`'s own dotted prefix) passes
    one explicitly."""
    return paper_graph.BlockRecord(
        section=section,
        block_id=qualified_id.split(".")[-1],
        qualified_id=qualified_id,
        block_index=0,
        position=1,
        requires_facts=tuple(requires_facts),
        requires_declarations=tuple(requires_declarations),
        citations="none",
        optional=optional,
    )


class DeclarationsTests(unittest.TestCase):
    """`specs/paper-declarations/spec.md`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)

    def _clock(self) -> str:
        return _FIXED_CLOCK

    def test_recording_a_fact_as_a_declaration_refuses_unknown_declaration(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.set_declaration(
                self.paper_dir, "contributions", "x", clock=self._clock
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_DECLARATION")
        self.assertIn("contributions", ctx.exception.detail)

    def test_recording_a_declaration_as_a_fact_refuses_unknown_fact(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.set_fact(
                self.paper_dir, "repository-url", "x", clock=self._clock
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_FACT")
        self.assertIn("repository-url", ctx.exception.detail)

    def test_the_partition_is_pairwise_disjoint_and_covers_every_fact(self) -> None:
        self.assertEqual(len(paper_declarations.OBSERVABLE_FACTS), 5)
        self.assertEqual(len(paper_declarations.DERIVED_FACTS), 4)
        self.assertEqual(len(paper_declarations.STRUCTURAL_FACTS), 1)
        union = (
            set(paper_declarations.OBSERVABLE_FACTS)
            | set(paper_declarations.DERIVED_FACTS)
            | set(paper_declarations.STRUCTURAL_FACTS)
        )
        self.assertEqual(union, set(paper_vocabulary.FACTS))
        self.assertTrue(
            set(paper_declarations.OBSERVABLE_FACTS).isdisjoint(paper_declarations.DERIVED_FACTS)
        )
        self.assertTrue(
            set(paper_declarations.OBSERVABLE_FACTS).isdisjoint(paper_declarations.STRUCTURAL_FACTS)
        )
        self.assertTrue(
            set(paper_declarations.DERIVED_FACTS).isdisjoint(paper_declarations.STRUCTURAL_FACTS)
        )

    def test_facts_and_declarations_vocabularies_are_pinned_and_disjoint(self) -> None:
        self.assertEqual(len(paper_vocabulary.FACTS), 10)
        self.assertEqual(len(paper_vocabulary.DECLARATIONS), 6)
        self.assertTrue(set(paper_vocabulary.FACTS).isdisjoint(paper_vocabulary.DECLARATIONS))

    def test_a_fixed_entry_refuses_a_plain_overwrite(self) -> None:
        paper_declarations.set_declaration(
            self.paper_dir, "author-roles", "Alice: writing", clock=self._clock
        )

        with self.assertRaises(Refused) as ctx:
            paper_declarations.set_declaration(
                self.paper_dir, "author-roles", "Bob: writing", clock=self._clock
            )
        self.assertEqual(ctx.exception.code, "DECLARATION_FIXED")

    def test_reopen_then_declare_admits_a_new_value(self) -> None:
        paper_declarations.set_declaration(
            self.paper_dir, "author-roles", "Alice: writing", clock=self._clock
        )
        paper_declarations.reopen(self.paper_dir, "author-roles", clock=self._clock)

        result = paper_declarations.set_declaration(
            self.paper_dir, "author-roles", "Bob: writing", clock=self._clock
        )

        self.assertEqual(result["value"], "Bob: writing")
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        record = paper_region.read_region(tex_path.read_bytes(), "declarations")
        entry = next(r for r in record["body"]["records"] if r["id"] == "author-roles")
        self.assertEqual(entry["value"], "Bob: writing")
        self.assertTrue(entry["fixed"])

    def test_reopen_narrows_to_exactly_the_naming_blocks(self) -> None:
        corpus = paper_graph.Corpus(
            sections={},
            blocks={
                "a.one": _block_record("a.one", requires_declarations=["repository-url"]),
                "a.two": _block_record("a.two", requires_declarations=["repository-url"]),
                "a.three": _block_record("a.three", requires_declarations=["grant-title"]),
            },
            order_by_section={},
        )

        affected = paper_declarations.affected_blocks(corpus, "repository-url")

        self.assertEqual(affected, {"a.one", "a.two"})

    def test_declarations_hand_edited_refuses_and_writes_nothing(self) -> None:
        paper_declarations.set_declaration(
            self.paper_dir, "author-roles", "Alice: writing", clock=self._clock
        )
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        pre = tex_path.read_bytes()
        record = paper_region.read_region(pre, "declarations")
        # Corrupt exactly one byte of the region's body -- a hand edit that
        # does not touch the marker lines at all.
        corrupted = (
            pre[: record["begin_start"]]
            + pre[record["begin_start"]:record["end_end"]].replace(b"Alice", b"Alicf", 1)
            + pre[record["end_end"]:]
        )
        tex_path.write_bytes(corrupted)

        with self.assertRaises(Refused) as ctx:
            paper_declarations.set_declaration(
                self.paper_dir, "grant-title", "A Title", clock=self._clock
            )
        self.assertEqual(ctx.exception.code, "DECLARATIONS_HAND_EDITED")

        self.assertEqual(tex_path.read_bytes(), corrupted, "a refused write must leave disk untouched")


class BindingRecordTests(unittest.TestCase):
    """`the-requirement-names-the-section-that-feeds-it`, U3e ruling
    (design.md Decision J): the verb that RECORDS a `source-section-
    binding` -- `bind_section` -- and its own read (`read_bindings`) and
    reopen (`reopen_binding`) counterparts, all through the SAME
    `declarations` region `set_fact`/`set_declaration` already write, a
    THIRD record kind (`binding`) never sharing `fact`'s or
    `declaration`'s own field name."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)

    def _clock(self) -> str:
        return _FIXED_CLOCK

    def test_a_recorded_binding_is_read_back(self) -> None:
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis",
            ("1. Fundamentos",), clock=self._clock,
        )

        bindings = paper_declarations.read_bindings(self.paper_dir)

        self.assertEqual(
            bindings["a.only"]["formulation"],
            {"lineage": "lumen-thesis", "sections": ("1. Fundamentos",)},
        )

    def test_a_single_string_section_is_accepted_and_read_back_as_a_tuple(self) -> None:
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis",
            "1. Fundamentos", clock=self._clock,
        )

        bindings = paper_declarations.read_bindings(self.paper_dir)

        self.assertEqual(bindings["a.only"]["formulation"]["sections"], ("1. Fundamentos",))

    def test_two_facts_on_the_same_block_are_recorded_independently(self) -> None:
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis",
            ("1. Fundamentos",), clock=self._clock,
        )
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "dataset", "q77213-004-11029-2",
            ("Dataset",), clock=self._clock,
        )

        bindings = paper_declarations.read_bindings(self.paper_dir)

        self.assertEqual(set(bindings["a.only"]), {"formulation", "dataset"})

    def test_the_same_fact_bound_on_two_blocks_is_recorded_independently(self) -> None:
        """The worked example this whole change exists for:
        `mm-borrowed-machinery` and `mm-proposal` both require
        `formulation` but bind different sections."""
        paper_declarations.bind_section(
            self.paper_dir, "materials-and-methods.mm-borrowed-machinery", "formulation",
            "lumen-thesis", ("1. Fundamentos",), clock=self._clock,
        )
        paper_declarations.bind_section(
            self.paper_dir, "materials-and-methods.mm-proposal", "formulation",
            "lumen-thesis", ("3. Formulacion",), clock=self._clock,
        )

        bindings = paper_declarations.read_bindings(self.paper_dir)

        self.assertEqual(
            bindings["materials-and-methods.mm-borrowed-machinery"]["formulation"]["sections"],
            ("1. Fundamentos",),
        )
        self.assertEqual(
            bindings["materials-and-methods.mm-proposal"]["formulation"]["sections"],
            ("3. Formulacion",),
        )

    def test_an_empty_sections_tuple_refuses_binding_sections_required(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.bind_section(
                self.paper_dir, "a.only", "formulation", "lumen-thesis", (), clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "BINDING_SECTIONS_REQUIRED")

    def test_an_empty_lineage_refuses_binding_lineage_required(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.bind_section(
                self.paper_dir, "a.only", "formulation", "", ("1. Intro",), clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "BINDING_LINEAGE_REQUIRED")

    def test_binding_a_produced_fact_refuses_unknown_fact(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.bind_section(
                self.paper_dir, "a.only", "not-a-fact", "lumen-thesis", ("1. Intro",),
                clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_FACT")

    def test_binding_a_non_bindable_fact_refuses_fact_not_bindable(self) -> None:
        """`gap` is a produced fact -- absent from `FACT_SOURCE_ROOT` by
        construction, so it can never be document-bound (`source-section-
        binding` spec, `Requirement: Bindable Facts Are Derived, Never
        Listed`)."""
        with self.assertRaises(Refused) as ctx:
            paper_declarations.bind_section(
                self.paper_dir, "a.only", "gap", "lumen-thesis", ("1. Intro",), clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "BINDING_FACT_NOT_BINDABLE")
        self.assertIn("gap", ctx.exception.detail)

    def test_rebinding_the_same_block_and_fact_without_reopen_refuses(self) -> None:
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis",
            ("1. Fundamentos",), clock=self._clock,
        )

        with self.assertRaises(Refused) as ctx:
            paper_declarations.bind_section(
                self.paper_dir, "a.only", "formulation", "lumen-thesis",
                ("3. Formulacion",), clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "DECLARATION_FIXED")

    def test_reopen_then_bind_admits_a_new_lineage(self) -> None:
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis",
            ("1. Fundamentos",), clock=self._clock,
        )
        paper_declarations.reopen_binding(self.paper_dir, "a.only", "formulation", clock=self._clock)

        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis",
            ("3. Formulacion",), clock=self._clock,
        )

        bindings = paper_declarations.read_bindings(self.paper_dir)
        self.assertEqual(bindings["a.only"]["formulation"]["sections"], ("3. Formulacion",))

    def test_reopening_a_never_bound_pair_is_harmless(self) -> None:
        result = paper_declarations.reopen_binding(
            self.paper_dir, "a.never", "formulation", clock=self._clock,
        )
        self.assertEqual(result["block"], "a.never")
        self.assertEqual(result["fact"], "formulation")

    def test_reopening_one_pair_leaves_a_sibling_binding_untouched(self) -> None:
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis",
            ("1. Fundamentos",), clock=self._clock,
        )
        paper_declarations.bind_section(
            self.paper_dir, "a.other", "formulation", "lumen-thesis",
            ("1. Fundamentos",), clock=self._clock,
        )

        paper_declarations.reopen_binding(self.paper_dir, "a.only", "formulation", clock=self._clock)

        bindings = paper_declarations.read_bindings(self.paper_dir)
        self.assertNotIn("a.only", bindings)
        self.assertEqual(bindings["a.other"]["formulation"]["sections"], ("1. Fundamentos",))

    def test_read_bindings_reports_empty_before_paper_is_scaffolded(self) -> None:
        """A corpus must be assemblable, read-only, before `paper/` even
        exists -- the SAME tolerance `Corpus.undecided_bindings` already
        extends to a fact with no binding at all."""
        unscaffolded = self.forge_root / "no-such-paper"

        self.assertEqual(paper_declarations.read_bindings(unscaffolded), {})

    def test_a_hand_edited_declarations_region_still_refuses_a_new_binding(self) -> None:
        paper_declarations.bind_section(
            self.paper_dir, "a.only", "formulation", "lumen-thesis",
            ("1. Fundamentos",), clock=self._clock,
        )
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        pre = tex_path.read_bytes()
        record = paper_region.read_region(pre, "declarations")
        corrupted = (
            pre[: record["begin_start"]]
            + pre[record["begin_start"]:record["end_end"]].replace(b"lumen", b"lumin", 1)
            + pre[record["end_end"]:]
        )
        tex_path.write_bytes(corrupted)

        with self.assertRaises(Refused) as ctx:
            paper_declarations.bind_section(
                self.paper_dir, "a.other", "dataset", "q77213-004-11029-2", ("Dataset",),
                clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "DECLARATIONS_HAND_EDITED")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_bindings(self.paper_dir)
        self.assertEqual(ctx.exception.code, "DECLARATIONS_HAND_EDITED")


class SeparationRoundRecordTests(unittest.TestCase):
    """`the-whole-cut-is-argued-before-any-section-is-claimed`, U3
    (design.md Decision A): a FOURTH `declarations`-region record kind,
    `separation`, keyed by round -- `record_separation_round`/
    `read_separation_rounds`, through the SAME `_set_record`/`_find_
    record`/`_verify_not_hand_edited` path `binding` and `fact`/
    `declaration` already go through. All example names invented
    (design.md's own worked example: lineage `field-survey`, revision
    `field-survey-r07.md`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)

    def _clock(self) -> str:
        return _FIXED_CLOCK

    def _round_1_assignments(self) -> list:
        return [
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["1. Background on widget metrics"]},
        ]

    def test_the_id_shape_carries_root_lineage_revision_and_a_derived_round(self) -> None:
        result = paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, self._round_1_assignments(), 4, clock=self._clock,
        )

        self.assertEqual(
            result["id"], "separation::proposals::field-survey::field-survey-r07.md::round-1",
        )
        self.assertEqual(result["round"], 1)

    def test_a_recorded_round_is_read_back_by_root_lineage_and_revision(self) -> None:
        paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, self._round_1_assignments(), 4, clock=self._clock,
        )

        rounds = paper_declarations.read_separation_rounds(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
        )

        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0]["round"], 1)
        self.assertEqual(rounds[0]["score"], 4)
        self.assertEqual(rounds[0]["document_digest"], "deadbeef" * 8)
        self.assertEqual(rounds[0]["assignments"], self._round_1_assignments())

    def test_the_round_number_is_derived_never_a_caller_supplied_argument(self) -> None:
        """A caller cannot name its own round -- the function signature
        carries no `round`/`round_number` parameter at all, and a SECOND
        submission for the identical `(root, lineage, revision)` derives
        round 2 regardless of what the caller's own bookkeeping thinks the
        next number should be."""
        import inspect
        signature = inspect.signature(paper_declarations.record_separation_round)
        self.assertNotIn("round", signature.parameters)
        self.assertNotIn("round_number", signature.parameters)

        paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, self._round_1_assignments(), 4, clock=self._clock,
        )
        second = paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "cafebabe" * 8,
            [{"block": "overview.block-a", "fact": "formulation",
              "sections": ["1. Background on widget metrics", "2. Alignment estimators"]}],
            0, clock=self._clock,
        )

        self.assertEqual(second["round"], 2)
        self.assertIn("round-2", second["id"])

    def test_a_new_revision_restarts_numbering_at_round_one(self) -> None:
        """Decision A, refinement 1: the revision is part of the id, so a
        mid-negotiation publish restarts the count -- staleness is
        structurally impossible, never a code that has to catch it."""
        paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, self._round_1_assignments(), 4, clock=self._clock,
        )

        under_new_revision = paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r08.md",
            "cafebabe" * 8, self._round_1_assignments(), 4, clock=self._clock,
        )

        self.assertEqual(under_new_revision["round"], 1)
        self.assertIn("field-survey-r08.md", under_new_revision["id"])

    def test_rounds_are_append_only_no_reopen_function_exists(self) -> None:
        """Decision A, refinement 3: reopening a round would let an
        argument be rewritten after its successor was scored against it,
        so no such function exists at all -- not merely undocumented."""
        self.assertFalse(hasattr(paper_declarations, "reopen_separation"))

    def test_read_separation_rounds_reports_empty_before_paper_is_scaffolded(self) -> None:
        unscaffolded = self.forge_root / "no-such-paper"

        self.assertEqual(
            paper_declarations.read_separation_rounds(
                unscaffolded, "proposals", "field-survey", "field-survey-r07.md",
            ),
            (),
        )

    def test_two_different_lineages_under_the_same_root_stay_independent(self) -> None:
        paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, self._round_1_assignments(), 4, clock=self._clock,
        )
        paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "other-survey", "other-survey-r01.md",
            "cafebabe" * 8, self._round_1_assignments(), 4, clock=self._clock,
        )

        field_rounds = paper_declarations.read_separation_rounds(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
        )
        other_rounds = paper_declarations.read_separation_rounds(
            self.paper_dir, "proposals", "other-survey", "other-survey-r01.md",
        )

        self.assertEqual(len(field_rounds), 1)
        self.assertEqual(len(other_rounds), 1)

    def test_a_hand_edited_declarations_region_still_refuses_a_new_round(self) -> None:
        paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, self._round_1_assignments(), 4, clock=self._clock,
        )
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        pre = tex_path.read_bytes()
        record = paper_region.read_region(pre, "declarations")
        corrupted = (
            pre[: record["begin_start"]]
            + pre[record["begin_start"]:record["end_end"]].replace(b"field", b"filed", 1)
            + pre[record["end_end"]:]
        )
        tex_path.write_bytes(corrupted)

        with self.assertRaises(Refused) as ctx:
            paper_declarations.record_separation_round(
                self.paper_dir, "proposals", "field-survey", "field-survey-r08.md",
                "cafebabe" * 8, self._round_1_assignments(), 0, clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "DECLARATIONS_HAND_EDITED")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.read_separation_rounds(
                self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            )
        self.assertEqual(ctx.exception.code, "DECLARATIONS_HAND_EDITED")


class SeparationRoundReplayTests(unittest.TestCase):
    """Task 3.4/3.5: a byte-identical, canonicalized cut resubmitted
    against the latest recorded round for that id prefix records nothing
    new and returns that same round -- a retried invocation must not
    inflate the round count."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)

    def _clock(self) -> str:
        return _FIXED_CLOCK

    def test_an_identical_resubmission_records_nothing_new(self) -> None:
        assignments = [
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["1. Background on widget metrics"]},
        ]
        first = paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, assignments, 4, clock=self._clock,
        )

        second = paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, assignments, 4, clock=self._clock,
        )

        self.assertEqual(second["round"], first["round"])
        rounds = paper_declarations.read_separation_rounds(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
        )
        self.assertEqual(len(rounds), 1)

    def test_a_canonicalized_reordering_is_still_recognized_as_a_replay(self) -> None:
        """The same cut, its assignments and each assignment's own
        `sections` in a different order, is still the SAME cut -- never a
        spurious new round (`score_cut` itself treats both as sets)."""
        first_assignments = [
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["1. Background", "2. Estimators"]},
            {"block": "methods.block-b", "fact": "formulation", "sections": ["3. Objective"]},
        ]
        reordered_assignments = [
            {"block": "methods.block-b", "fact": "formulation", "sections": ["3. Objective"]},
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["2. Estimators", "1. Background"]},
        ]
        paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, first_assignments, 1, clock=self._clock,
        )

        paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, reordered_assignments, 1, clock=self._clock,
        )

        rounds = paper_declarations.read_separation_rounds(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
        )
        self.assertEqual(len(rounds), 1)

    def test_a_genuinely_different_cut_records_a_new_round(self) -> None:
        first_assignments = [
            {"block": "overview.block-a", "fact": "formulation", "sections": ["1. Background"]},
        ]
        second_assignments = [
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["1. Background", "2. Estimators"]},
        ]
        paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, first_assignments, 4, clock=self._clock,
        )

        second = paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", "field-survey-r07.md",
            "deadbeef" * 8, second_assignments, 0, clock=self._clock,
        )

        self.assertEqual(second["round"], 2)


class BindingLicenseTests(unittest.TestCase):
    """`the-whole-cut-is-argued-before-any-section-is-claimed`, owner
    amendment (design.md Decisions I/J): `settled_round_licensing`'s four
    checks and `bind_section`'s own `BINDING_UNARGUED` guard, gated on
    them -- a binding for a MEASURED, document-rooted fact is refused
    unless a settled `separate` round licenses this EXACT `(block, fact)`
    claim with this EXACT title set, against the document resolved and
    digested RIGHT NOW. All example names invented, matching this file's
    own worked example (lineage `field-survey`, revision
    `field-survey-r07.md`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.proposals = self.forge_root / "proposals"
        self.proposals.mkdir()
        (self.proposals / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}),
            encoding="utf-8",
        )
        self.revision_path = self.proposals / "field-survey-r07.md"
        self.revision_path.write_text("# 1. Background\n\n# 2. Estimators\n", encoding="utf-8")

    def _clock(self) -> str:
        return _FIXED_CLOCK

    def _digest(self, path: Path | None = None) -> str:
        return hashlib.sha256((path or self.revision_path).read_bytes()).hexdigest()

    def _settle(
        self, *, block: str = "overview.block-a", fact: str = "formulation",
        sections=("1. Background", "2. Estimators"), revision: str | None = None,
        digest: str | None = None, score: int = 0,
    ) -> dict:
        revision = revision if revision is not None else self.revision_path.name
        digest = digest if digest is not None else self._digest()
        return paper_declarations.record_separation_round(
            self.paper_dir, "proposals", "field-survey", revision, digest,
            [{"block": block, "fact": fact, "sections": list(sections)}], score,
            clock=self._clock,
        )

    def _bind(
        self, *, block: str = "overview.block-a", fact: str = "formulation",
        lineage: str = "field-survey", sections=("1. Background", "2. Estimators"),
    ) -> dict:
        return paper_declarations.bind_section(
            self.paper_dir, block, fact, lineage, sections,
            source_base=self.forge_root, clock=self._clock,
        )

    # -- settled_round_licensing, the four checks, unit level (task 5.1) --

    def test_settled_round_licensing_licenses_when_all_four_checks_match(self) -> None:
        self._settle()

        result = paper_declarations.settled_round_licensing(
            self.paper_dir, "proposals", "field-survey", self.revision_path.name, self._digest(),
            "overview.block-a", "formulation", ("1. Background", "2. Estimators"),
        )

        self.assertEqual(result["state"], "licensed")
        self.assertEqual(result["round"], 1)
        self.assertIsNone(result["failed_check"])

    def test_check_1_identity_fails_with_no_round_recorded_at_all(self) -> None:
        result = paper_declarations.settled_round_licensing(
            self.paper_dir, "proposals", "field-survey", self.revision_path.name, self._digest(),
            "overview.block-a", "formulation", ("1. Background", "2. Estimators"),
        )

        self.assertEqual(result["state"], "refused")
        self.assertEqual(result["failed_check"], "identity")
        self.assertIn("no separation round is recorded", result["reason"])

    def test_check_1_identity_fails_when_only_an_older_revision_was_argued(self) -> None:
        self._settle(revision="field-survey-r06.md", digest="deadbeef" * 8)

        result = paper_declarations.settled_round_licensing(
            self.paper_dir, "proposals", "field-survey", self.revision_path.name, self._digest(),
            "overview.block-a", "formulation", ("1. Background", "2. Estimators"),
        )

        self.assertEqual(result["state"], "refused")
        self.assertEqual(result["failed_check"], "identity")
        self.assertIn("field-survey-r06.md", result["reason"])
        self.assertIn(self.revision_path.name, result["reason"])

    def test_check_2_digest_fails_on_a_digest_mismatch(self) -> None:
        self._settle(digest="deadbeef" * 8)

        result = paper_declarations.settled_round_licensing(
            self.paper_dir, "proposals", "field-survey", self.revision_path.name, self._digest(),
            "overview.block-a", "formulation", ("1. Background", "2. Estimators"),
        )

        self.assertEqual(result["state"], "refused")
        self.assertEqual(result["failed_check"], "digest")
        self.assertIn("deadbeef" * 8, result["reason"])

    def test_check_3_score_fails_when_no_round_settles_at_zero(self) -> None:
        self._settle(score=4)

        result = paper_declarations.settled_round_licensing(
            self.paper_dir, "proposals", "field-survey", self.revision_path.name, self._digest(),
            "overview.block-a", "formulation", ("1. Background", "2. Estimators"),
        )

        self.assertEqual(result["state"], "refused")
        self.assertEqual(result["failed_check"], "score")

    def test_check_4_scope_fails_on_a_title_set_mismatch(self) -> None:
        self._settle(sections=("1. Background",))

        result = paper_declarations.settled_round_licensing(
            self.paper_dir, "proposals", "field-survey", self.revision_path.name, self._digest(),
            "overview.block-a", "formulation", ("1. Background", "2. Estimators"),
        )

        self.assertEqual(result["state"], "refused")
        self.assertEqual(result["failed_check"], "scope")
        self.assertEqual(result["argued_sections"], ("1. Background",))

    # -- bind_section itself, gated on the same four checks -- the no-round
    #    fixture (task 5.3), happy path (5.7), scope mismatches (5.8/5.9) --

    def test_bind_with_no_settled_round_at_all_refuses_binding_unargued(self) -> None:
        with self.assertRaises(Refused) as ctx:
            self._bind()

        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")
        detail = ctx.exception.detail
        self.assertIn("overview.block-a", detail)
        self.assertIn("formulation", detail)
        self.assertIn("proposals", detail)
        self.assertIn(self.revision_path.name, detail)
        self.assertIn("failed_check='identity'", detail)
        self.assertIn("separate --proposal", detail)

    def test_a_settled_round_naming_the_exact_pair_and_titles_licenses_the_bind(self) -> None:
        self._settle()

        result = self._bind()

        self.assertEqual(result["block"], "overview.block-a")
        self.assertTrue(result["separation"].startswith("licensed(round="))

    def test_title_order_does_not_matter_set_equality_not_sequence(self) -> None:
        self._settle(sections=("1. Background", "2. Estimators"))

        result = self._bind(sections=("2. Estimators", "1. Background"))

        self.assertTrue(result["separation"].startswith("licensed(round="))

    def test_a_settled_round_naming_a_different_block_refuses(self) -> None:
        self._settle(block="overview.block-a")

        with self.assertRaises(Refused) as ctx:
            self._bind(block="overview.block-z")

        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")
        self.assertIn("overview.block-z", ctx.exception.detail)
        self.assertIn("no settled round names", ctx.exception.detail)

    def test_binding_a_subset_of_the_argued_titles_refuses(self) -> None:
        self._settle(sections=("1. Background", "2. Estimators"))

        with self.assertRaises(Refused) as ctx:
            self._bind(sections=("1. Background",))

        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")
        detail = ctx.exception.detail
        self.assertIn("1. Background", detail)
        self.assertIn("2. Estimators", detail)

    def test_binding_a_superset_of_the_argued_titles_refuses(self) -> None:
        self._settle(sections=("1. Background",))

        with self.assertRaises(Refused) as ctx:
            self._bind(sections=("1. Background", "2. Estimators"))

        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")

    def test_mutation_weakening_check_4_to_nonemptiness_reddens_the_subset_fixture(self) -> None:
        proc = _run_against_mutant(
            "            if recorded == argued:\n",
            "            if recorded:\n",
            "tests.test_paper_decisions.BindingLicenseTests"
            ".test_binding_a_subset_of_the_argued_titles_refuses",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_weakening_check_4_to_nonemptiness_reddens_the_superset_fixture(self) -> None:
        proc = _run_against_mutant(
            "            if recorded == argued:\n",
            "            if recorded:\n",
            "tests.test_paper_decisions.BindingLicenseTests"
            ".test_binding_a_superset_of_the_argued_titles_refuses",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_the_wrong_block_fixture_is_unaffected_by_the_check_4_weakening(self) -> None:
        """Documented, not silently assumed: a round naming a DIFFERENT
        block never reaches check 4's title comparison at all --
        `settled_round_licensing`'s inner loop only compares titles once
        `(block, fact)` already matched, so weakening THAT comparison
        cannot move this fixture. Proven directly rather than by mutation,
        since no mutation of check 4 alone could ever redden it."""
        self._settle(block="overview.block-a")

        with self.assertRaises(Refused) as ctx:
            self._bind(block="overview.block-z")

        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")

    # -- licence expiry, both root kinds (task 5.11/5.12), and the two
    #    mutations proving checks 1 and 2 are each independently load-
    #    bearing (task 5.13/5.14) --

    def test_a_new_revision_voids_the_licence_even_with_identical_bytes(self) -> None:
        """The revision is part of the licence's own identity (Decision A):
        `field-survey-r08.md` republishes the IDENTICAL bytes as r07 (a
        pure version bump, `test_publishing_a_survived_revision_costs_no_
        edit`'s own precedent), yet the licence still voids -- proving
        check 1 fires on the revision STRING alone, never merely as a
        side effect of the digest also changing."""
        self._settle()
        (self.proposals / "field-survey-r08.md").write_bytes(self.revision_path.read_bytes())

        with self.assertRaises(Refused) as ctx:
            self._bind()

        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")
        detail = ctx.exception.detail
        self.assertIn("failed_check='identity'", detail)
        self.assertIn("field-survey-r07.md", detail)
        self.assertIn("field-survey-r08.md", detail)

    def test_an_in_place_rewrite_voids_the_licence_even_at_the_same_revision(self) -> None:
        self._settle()
        self.revision_path.write_text(
            "# 1. Background\n\n# 2. Estimators\n\n# rewritten in place\n", encoding="utf-8",
        )

        with self.assertRaises(Refused) as ctx:
            self._bind()

        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")
        self.assertIn("failed_check='digest'", ctx.exception.detail)

    def test_an_ingested_documents_licence_expires_only_by_digest_never_by_revision(self) -> None:
        guidance = self.forge_root / "guidance"
        evidence = guidance / "source-manuscript"
        evidence.mkdir(parents=True)
        (evidence / ".paper-writing.json").write_text(
            json.dumps({"class": "evidence"}), encoding="utf-8",
        )
        paper_id = "a-fixture-paper-id"
        doc_dir = evidence / paper_id
        doc_dir.mkdir()
        doc_path = doc_dir / f"{paper_id}.md"
        doc_path.write_text("Just prose about the dataset.\n", encoding="utf-8")
        digest = hashlib.sha256(doc_path.read_bytes()).hexdigest()
        paper_declarations.record_separation_round(
            self.paper_dir, "evidence", paper_id, f"{paper_id}.md", digest,
            [{"block": "overview.block-a", "fact": "dataset", "sections": ["Dataset"]}], 0,
            clock=self._clock,
        )

        result = paper_declarations.bind_section(
            self.paper_dir, "overview.block-a", "dataset", paper_id, ("Dataset",),
            source_base=self.forge_root, clock=self._clock,
        )
        self.assertTrue(result["separation"].startswith("licensed(round="))
        paper_declarations.reopen_binding(self.paper_dir, "overview.block-a", "dataset")

        # Re-ingested with DIFFERENT content under the SAME identity -- the
        # revision string never changes at all (an ingested paper gets no
        # `r22`), so only the digest can void this licence.
        doc_path.write_text("Different prose entirely.\n", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.bind_section(
                self.paper_dir, "overview.block-a", "dataset", paper_id, ("Dataset",),
                source_base=self.forge_root, clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")
        self.assertIn("failed_check='digest'", ctx.exception.detail)
        self.assertIn(f"{paper_id}.md", ctx.exception.detail)

    def test_mutation_dropping_check_2_digest_reddens_the_in_place_rewrite_fixture(self) -> None:
        proc = _run_against_mutant(
            '    digest_current = [entry for entry in current if entry["document_digest"] == '
            'document_digest]\n',
            "    digest_current = current\n",
            "tests.test_paper_decisions.BindingLicenseTests"
            ".test_an_in_place_rewrite_voids_the_licence_even_at_the_same_revision",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_dropping_check_1_identity_reddens_the_new_revision_fixture(self) -> None:
        proc = _run_against_mutant(
            "    current = read_separation_rounds(paper_dir, root, lineage, revision)\n",
            "    current = _read_separation_rounds_any_revision(paper_dir, root, lineage)\n",
            "tests.test_paper_decisions.BindingLicenseTests"
            ".test_a_new_revision_voids_the_licence_even_with_identical_bytes",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    # -- the guard lives in `bind_section` itself (task 5.15/5.16) --

    def test_bind_section_called_directly_bypassing_the_cli_still_refuses(self) -> None:
        """The same direct-call shape every fixture in this class already
        uses: `bind_section` is called here with no `cmd_bind`/CLI layer
        anywhere in the call stack, and it still refuses on its own."""
        with self.assertRaises(Refused) as ctx:
            self._bind()

        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")

    def test_mutation_moving_the_guard_out_of_bind_section_reddens_the_direct_call_fixture(
        self,
    ) -> None:
        proc = _run_against_mutant(
            '    separation_report = _binding_separation_report(\n'
            '        paper_dir, qualified_block_id, fact_id, lineage, sections, source_base,\n'
            '    )\n',
            '    separation_report = "licensed(round=0)"  # mutated: guard moved elsewhere\n',
            "tests.test_paper_decisions.BindingLicenseTests"
            ".test_bind_section_called_directly_bypassing_the_cli_still_refuses",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    # -- an unmeasured root bypasses the precondition entirely (5.17), and
    #    `--reopen` is never blocked by it, in every state (5.18) --

    def test_an_unmeasured_root_bypasses_the_precondition_entirely(self) -> None:
        """No `experiments/` directory exists at all under `self.forge_root`
        -- `experimental-design`'s own root reports unmeasured, so the
        precondition never applies at all (`source-section-binding` spec,
        `Requirement: An Unmeasured Root Is Reported, Never Silently
        Passed`)."""
        result = paper_declarations.bind_section(
            self.paper_dir, "overview.block-a", "experimental-design", "field-log",
            ("1. Setup Notes",), source_base=self.forge_root, clock=self._clock,
        )

        self.assertTrue(result["separation"].startswith("unmeasured("))

    def test_reopen_succeeds_with_no_settled_round_at_all_on_a_measured_root(self) -> None:
        result = paper_declarations.reopen_binding(
            self.paper_dir, "overview.block-a", "formulation", clock=self._clock,
        )
        self.assertEqual(result["block"], "overview.block-a")

    def test_reopen_succeeds_with_no_settled_round_at_all_on_an_unmeasured_root(self) -> None:
        result = paper_declarations.reopen_binding(
            self.paper_dir, "overview.block-a", "experimental-design", clock=self._clock,
        )
        self.assertEqual(result["block"], "overview.block-a")

    # -- the shortcut-closed e2e (5.19/5.20), module level; the CLI-level
    #    counterpart lives in `test_paper_writing.BindCliEndToEndTests` --

    def test_the_shortcut_is_closed_bind_refuses_then_a_settled_separate_licenses_it(
        self,
    ) -> None:
        with self.assertRaises(Refused) as ctx:
            self._bind()
        self.assertEqual(ctx.exception.code, "BINDING_UNARGUED")

        self._settle()
        result = self._bind()
        self.assertTrue(result["separation"].startswith("licensed(round="))

        reopened = paper_declarations.reopen_binding(
            self.paper_dir, "overview.block-a", "formulation", clock=self._clock,
        )
        self.assertEqual(reopened["block"], "overview.block-a")


class DescribeBindingCandidatesTests(unittest.TestCase):
    """`the-requirement-names-the-section-that-feeds-it`, U3e: what `write`'s
    own improved `SECTION_BINDING_ABSENT` refusal shows an operator --
    every lineage a root carries RIGHT NOW, its own current revision (or,
    for an INGESTED root, its own paper), and the section titles read from
    it at call time. Nothing here is cached or hand-listed."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def _marker(self, root: Path, prefix: str = "r", digits: int = 2) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": prefix, "ordinal_digits": digits}}),
            encoding="utf-8",
        )

    def test_a_marked_root_reports_the_current_revision_per_lineage(self) -> None:
        proposals = self.base / "proposals"
        self._marker(proposals)
        (proposals / "lumen-thesis-r20.md").write_text("# Old\n", encoding="utf-8")
        (proposals / "lumen-thesis-r21.md").write_text(
            "# 1. Intro\n\n# 3. Something\n", encoding="utf-8",
        )
        (proposals / "other-thesis-r05.md").write_text("# Only heading\n", encoding="utf-8")
        status = paper_declarations.source_root_status(
            self.base, paper_declarations.SourceRoot("proposals", paper_declarations.SourceRootKind.PROSE),
        )

        candidates = paper_declarations.describe_binding_candidates(
            status, paper_declarations.SourceRoot("proposals", paper_declarations.SourceRootKind.PROSE),
        )

        self.assertEqual(
            candidates,
            {
                "lumen-thesis": {
                    "revision": "lumen-thesis-r21.md",
                    "sections": ["1. Intro", "3. Something"],
                },
                "other-thesis": {"revision": "other-thesis-r05.md", "sections": ["Only heading"]},
            },
        )

    def test_a_root_with_no_marker_yet_reports_every_file_by_its_own_stem(self) -> None:
        proposals = self.base / "proposals"
        proposals.mkdir()
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")
        status = paper_declarations.source_root_status(
            self.base, paper_declarations.SourceRoot("proposals", paper_declarations.SourceRootKind.PROSE),
        )

        candidates = paper_declarations.describe_binding_candidates(
            status, paper_declarations.SourceRoot("proposals", paper_declarations.SourceRootKind.PROSE),
        )

        self.assertEqual(
            candidates,
            {"lumen-thesis-r21": {"revision": "lumen-thesis-r21.md", "sections": ["1. Intro"]}},
        )

    def test_an_ingested_root_reports_every_paper_as_its_own_lineage(self) -> None:
        guidance = self.base / "guidance" / "source-manuscript"
        paper_dir = guidance / "q77213-004-11029-2"
        paper_dir.mkdir(parents=True)
        (paper_dir / "q77213-004-11029-2.md").write_text("# Dataset\n", encoding="utf-8")
        status = {"state": "document-rooted", "path": guidance, "documents": 1, "reason": None}

        candidates = paper_declarations.describe_binding_candidates(
            status, paper_declarations.SourceRoot("evidence", paper_declarations.SourceRootKind.INGESTED),
        )

        self.assertEqual(
            candidates,
            {"q77213-004-11029-2": {"revision": "q77213-004-11029-2.md", "sections": ["Dataset"]}},
        )

    def test_unmarked_candidates_lists_every_md_file_by_name_sorted(self) -> None:
        """tasks.md 4.1: the SAME derivation `describe_binding_candidates`'s
        own no-marker branch already computes, extracted into one lister
        both callers share -- one lister, two callers, provably the same
        list."""
        proposals = self.base / "proposals"
        proposals.mkdir()
        (proposals / "b-thesis.md").write_text("# 1\n", encoding="utf-8")
        (proposals / "a-thesis.md").write_text("# 1\n", encoding="utf-8")
        (proposals / "notes.txt").write_text("not markdown", encoding="utf-8")

        candidates = paper_declarations._unmarked_candidates(proposals)

        self.assertEqual(candidates, ["a-thesis.md", "b-thesis.md"])


class SourceRevisionsUndeclaredDetailTests(unittest.TestCase):
    """`source-section-binding` spec, `Requirement: A Document-Rooted
    Source With No Marker Refuses`; design.md Decision H:
    `source_revisions_undeclared_detail` is the ONE detail text both
    `SOURCE_REVISIONS_UNDECLARED` raise sites use."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_names_the_root_the_marker_file_the_candidates_and_the_invocation(self) -> None:
        proposals = self.base / "proposals"
        proposals.mkdir()
        (proposals / "lumen-thesis-r21.md").write_text("# 1. Intro\n", encoding="utf-8")
        (proposals / "other-thesis-r05.md").write_text("# Only heading\n", encoding="utf-8")
        root = paper_declarations.SourceRoot("proposals", paper_declarations.SourceRootKind.PROSE)
        status = paper_declarations.source_root_status(self.base, root)

        detail = paper_declarations.source_revisions_undeclared_detail(status, root)

        self.assertIn("proposals", detail)
        self.assertIn(".paper-writing.json", detail)
        self.assertIn("lumen-thesis-r21.md", detail)
        self.assertIn("other-thesis-r05.md", detail)
        self.assertIn("mark revisions", detail)
        self.assertIn("--root proposals", detail)

    def test_reads_candidates_at_call_time_never_cached(self) -> None:
        proposals = self.base / "proposals"
        proposals.mkdir()
        root = paper_declarations.SourceRoot("proposals", paper_declarations.SourceRootKind.PROSE)
        status = paper_declarations.source_root_status(self.base, root)

        first = paper_declarations.source_revisions_undeclared_detail(status, root)
        self.assertNotIn("fresh-arrival-r01.md", first)

        (proposals / "fresh-arrival-r01.md").write_text("# 1\n", encoding="utf-8")
        second = paper_declarations.source_revisions_undeclared_detail(status, root)

        self.assertIn("fresh-arrival-r01.md", second)


class ProducedFactUndeclarableTests(unittest.TestCase):
    """`a-fact-is-declared-or-it-is-produced`, `paper-declarations` spec,
    `Requirement: declare Refuses A Produced Fact` (tasks.md Unit 3, 3.2):
    `set_fact`/`decline_fact` refuse `PRODUCED_FACT_UNDECLARABLE` when
    `produced_by` is non-empty, enforced IN THE MODULE so no caller can
    escape it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)

    def _clock(self) -> str:
        return _FIXED_CLOCK

    def test_setting_a_produced_fact_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.set_fact(
                self.paper_dir, "gap", "some value", clock=self._clock,
                produced_by=("related-work.rw-closing", "introduction.block-3"),
            )
        self.assertEqual(ctx.exception.code, "PRODUCED_FACT_UNDECLARABLE")
        self.assertIn("gap", ctx.exception.detail)
        self.assertIn("related-work.rw-closing", ctx.exception.detail)

    def test_declining_a_produced_fact_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "gap", "reason",
                {"type": "directory-empty-except", "path": "experiments"},
                clock=self._clock, produced_by=("related-work.rw-closing",),
            )
        self.assertEqual(ctx.exception.code, "PRODUCED_FACT_UNDECLARABLE")

    def test_setting_a_fact_with_no_producer_is_unaffected(self) -> None:
        """Spec scenario 'Declaring an external fact is unaffected':
        `formulation` resolves from `FACT_SOURCE_ROOT`, with no producing
        block -- `produced_by` defaults to `()`."""
        result = paper_declarations.set_fact(
            self.paper_dir, "formulation", "x", clock=self._clock,
        )
        self.assertEqual(result["resolution"], "x")

    def test_setting_a_produced_fact_writes_nothing(self) -> None:
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        pre = tex_path.read_bytes()
        with self.assertRaises(Refused):
            paper_declarations.set_fact(
                self.paper_dir, "gap", "some value", clock=self._clock,
                produced_by=("related-work.rw-closing",),
            )
        self.assertEqual(tex_path.read_bytes(), pre, "a refused declare must leave disk untouched")


class DeclareCliProducedFactTests(unittest.TestCase):
    """`paper_cli.cmd_declare` resolves `produced_by` from the assembled
    corpus (tasks.md, Unit 3, 3.4) -- the CLI front door for `PRODUCED_
    FACT_UNDECLARABLE`."""

    def setUp(self) -> None:
        # `cmd_declare` resolves `--paper`/`--sections` against the REAL
        # repository root (`paper_scaffold.resolve_paper_dir(args.paper)`,
        # no `forge_root` override) -- the same containment reason
        # `CouplingsCliTests` above roots its own fixture under
        # `implementations/` (gitignored) rather than an unrelated
        # `tempfile.TemporaryDirectory`.
        self.test_root = (
            FORGE_ROOT / "implementations"
            / f".paper-writing-declare-cli-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir()
        header = json.dumps({
            "section": "declare-cli", "position": 1,
            "blocks": [{
                "id": "producer", "requires_facts": [], "requires_declarations": [],
                "citations": "none",
                "produces_facts": [{
                    "value": "limitations",
                    "source": {
                        "file": "sections/01-declare-cli.md",
                        "quote": "This block produces the limitations.",
                    },
                }],
            }],
        })
        (self.sections_dir / "01-declare-cli.md").write_text(
            f"---\n{header}\n---\n\nProse. This block produces the limitations.\n\n"
            "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )

    def _args(self, **overrides) -> argparse.Namespace:
        base = dict(
            paper=str(self.paper_dir), sections=str(self.sections_dir),
            declaration=None, fact=None, reopen=None, value=None,
            decline=None, reason=None, condition=None,
        )
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_declaring_a_produced_fact_through_the_cli_refuses(self) -> None:
        args = self._args(fact="limitations", value="x")

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_declare(args)

        self.assertEqual(ctx.exception.code, "PRODUCED_FACT_UNDECLARABLE")
        self.assertIn("limitations", ctx.exception.detail)
        self.assertIn("declare-cli.producer", ctx.exception.detail)

    def test_declaring_an_unproduced_fact_through_the_cli_is_unaffected(self) -> None:
        args = self._args(fact="formulation", value="x")

        result = paper_cli.cmd_declare(args)

        self.assertEqual(result["resolution"], "x")

    def test_declining_a_produced_fact_through_the_cli_refuses(self) -> None:
        args = self._args(
            decline="limitations", reason="no protocol yet",
            condition=json.dumps({"type": "directory-empty-except", "path": "experiments"}),
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_declare(args)

        self.assertEqual(ctx.exception.code, "PRODUCED_FACT_UNDECLARABLE")


class DeclinedFactTests(unittest.TestCase):
    """`a-declined-fact-has-somewhere-to-live`: a fact the operator has
    DECLINED — decided it does not enter the paper for now — is distinct
    from a fact simply not yet measured. Stored through the exact same
    `declarations` region, `set_fact`/`reopen`'s exact same private
    readers/writers, never a second store.

    A decline's `condition` is mandatory (`condition-that-expires`
    extension): a JSON object the skill re-evaluates fresh from disk on
    every `read_declined` call, resolved relative to `paper_dir.parent`
    (the fixture's own `forge_root`). `self.CONDITION` names
    `self.forge_root / "experiments"`, a path that does not exist under
    this fixture by default — `_evaluate_condition` reports a non-existent
    path as holding, matching `decline_fact`'s own docstring ("does not
    exist" is a holding case for `directory-empty-except`)."""

    CONDITION = {"type": "directory-empty-except", "path": "experiments", "ignore": [".gitkeep"]}

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)

    def _clock(self) -> str:
        return _FIXED_CLOCK

    def test_declining_an_unknown_id_refuses_unknown_fact(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "repository-url", "not a fact", self.CONDITION, clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_FACT")
        self.assertIn("repository-url", ctx.exception.detail)

    def test_declining_with_none_reason_refuses_decline_reason_required(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", None, self.CONDITION, clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "DECLINE_REASON_REQUIRED")

    def test_declining_with_empty_reason_refuses_decline_reason_required(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", "", self.CONDITION, clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "DECLINE_REASON_REQUIRED")

    def test_declining_with_whitespace_only_reason_refuses_decline_reason_required(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", "   ", self.CONDITION, clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "DECLINE_REASON_REQUIRED")

    def test_declining_with_no_condition_refuses_condition_required(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", "no protocol exists yet", None,
                clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "CONDITION_REQUIRED")

    def test_declining_with_a_non_object_condition_refuses_condition_malformed(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", "no protocol exists yet", "not an object",
                clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "CONDITION_MALFORMED")

    def test_declining_with_a_condition_missing_type_refuses_unknown_condition_type(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", "no protocol exists yet",
                {"path": "experiments"}, clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_CONDITION_TYPE")

    def test_declining_with_an_unknown_condition_type_refuses_unknown_condition_type(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", "no protocol exists yet",
                {"type": "file-exists", "path": "x"}, clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_CONDITION_TYPE")

    def test_declining_with_a_condition_missing_path_refuses_condition_malformed(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", "no protocol exists yet",
                {"type": "directory-empty-except"}, clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "CONDITION_MALFORMED")

    def test_declining_with_a_non_list_ignore_refuses_condition_malformed(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", "no protocol exists yet",
                {"type": "directory-empty-except", "path": "experiments", "ignore": "x"},
                clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "CONDITION_MALFORMED")

    def test_declining_with_a_path_outside_the_root_refuses_condition_malformed(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", "no protocol exists yet",
                {"type": "directory-empty-except", "path": "../outside"}, clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "CONDITION_MALFORMED")

    def test_declining_a_fact_is_reflected_in_read_declined(self) -> None:
        paper_declarations.decline_fact(
            self.paper_dir, "experimental-design", "no protocol exists yet", self.CONDITION,
            clock=self._clock,
        )

        declined = paper_declarations.read_declined(self.paper_dir)

        self.assertEqual(set(declined), {"experimental-design"})
        entry = declined["experimental-design"]
        self.assertEqual(entry["reason"], "no protocol exists yet")
        self.assertEqual(entry["condition"], self.CONDITION)
        self.assertTrue(entry["holds"])

    def test_a_declined_fact_is_not_in_read_satisfied(self) -> None:
        paper_declarations.decline_fact(
            self.paper_dir, "experimental-design", "no protocol exists yet", self.CONDITION,
            clock=self._clock,
        )

        satisfied_facts, _satisfied_declarations = paper_declarations.read_satisfied(self.paper_dir)

        self.assertNotIn("experimental-design", satisfied_facts)

    def test_declining_an_already_resolved_fact_refuses_declaration_fixed(self) -> None:
        paper_declarations.set_fact(
            self.paper_dir, "experimental-design", "protocol X", clock=self._clock,
        )

        with self.assertRaises(Refused) as ctx:
            paper_declarations.decline_fact(
                self.paper_dir, "experimental-design", "changed my mind", self.CONDITION,
                clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "DECLARATION_FIXED")

    def test_resolving_an_already_declined_fact_refuses_declaration_fixed(self) -> None:
        paper_declarations.decline_fact(
            self.paper_dir, "experimental-design", "no protocol exists yet", self.CONDITION,
            clock=self._clock,
        )

        with self.assertRaises(Refused) as ctx:
            paper_declarations.set_fact(
                self.paper_dir, "experimental-design", "protocol X", clock=self._clock,
            )
        self.assertEqual(ctx.exception.code, "DECLARATION_FIXED")

    def test_reopen_then_resolve_round_trips_a_declined_fact(self) -> None:
        paper_declarations.decline_fact(
            self.paper_dir, "experimental-design", "no protocol exists yet", self.CONDITION,
            clock=self._clock,
        )

        paper_declarations.reopen(self.paper_dir, "experimental-design", clock=self._clock)

        self.assertNotIn(
            "experimental-design", paper_declarations.read_declined(self.paper_dir),
        )

        result = paper_declarations.set_fact(
            self.paper_dir, "experimental-design", "protocol X", clock=self._clock,
        )
        self.assertEqual(result["resolution"], "protocol X")
        satisfied_facts, _ = paper_declarations.read_satisfied(self.paper_dir)
        self.assertIn("experimental-design", satisfied_facts)

    def test_read_fact_returns_none_for_a_currently_declined_fact(self) -> None:
        paper_declarations.decline_fact(
            self.paper_dir, "experimental-design", "no protocol exists yet", self.CONDITION,
            clock=self._clock,
        )

        self.assertIsNone(paper_declarations.read_fact(self.paper_dir, "experimental-design"))

    def test_a_lapsed_condition_is_reported_as_not_holding(self) -> None:
        paper_declarations.decline_fact(
            self.paper_dir, "experimental-design", "no protocol exists yet", self.CONDITION,
            clock=self._clock,
        )
        experiments_dir = self.forge_root / "experiments"
        experiments_dir.mkdir(parents=True, exist_ok=True)
        (experiments_dir / "protocol.md").write_text("a real protocol\n", encoding="utf-8")

        declined = paper_declarations.read_declined(self.paper_dir)

        entry = declined["experimental-design"]
        self.assertFalse(entry["holds"])
        self.assertIn("protocol.md", entry["detail"])


class DeclarationsMutationTests(unittest.TestCase):
    """Mutations 2, 5, 6 (design.md)."""

    def test_mutation_2_allowing_overwrite_of_a_fixed_entry_breaks_the_refusal_test(self) -> None:
        proc = _run_against_mutant(
            'if existing is not None and existing.get("fixed"):',
            "if False:",
            "tests.test_paper_decisions.DeclarationsTests.test_a_fixed_entry_refuses_a_plain_overwrite",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_5_over_invalidating_every_block_breaks_the_reopen_scope_test(self) -> None:
        proc = _run_against_mutant(
            "return {\n"
            "        qualified_id\n"
            "        for qualified_id, block in corpus.blocks.items()\n"
            "        if target_id in block.requires_facts or target_id in block.requires_declarations\n"
            "    }",
            "return set(corpus.blocks)",
            "tests.test_paper_decisions.DeclarationsTests.test_reopen_narrows_to_exactly_the_naming_blocks",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_6_swapping_the_declaration_validator_for_the_fact_one_breaks_the_vocabulary_guard(
        self,
    ) -> None:
        proc = _run_against_mutant(
            "paper_vocabulary.validate_declaration(declaration_id)",
            "paper_vocabulary.validate_fact(declaration_id)",
            "tests.test_paper_decisions.DeclarationsTests"
            ".test_recording_a_fact_as_a_declaration_refuses_unknown_declaration",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_8_a_declined_fact_counted_as_satisfied_breaks_the_read_satisfied_guard(
        self,
    ) -> None:
        proc = _run_against_mutant(
            'satisfied_facts = {\n'
            '        entry["id"] for entry in body["records"]\n'
            '        if entry["kind"] == "fact" and entry.get("fixed") and not entry.get("declined")\n'
            '    }',
            'satisfied_facts = {\n'
            '        entry["id"] for entry in body["records"]\n'
            '        if entry["kind"] == "fact" and entry.get("fixed")\n'
            '    }',
            "tests.test_paper_decisions.DeclinedFactTests"
            ".test_a_declined_fact_is_not_in_read_satisfied",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class SkeletonInferenceTests(unittest.TestCase):
    """`the-phases-are-derived-not-remembered`, design.md D4;
    `specs/skeleton-startup/spec.md`, `Requirement: Both Decisions Are
    Re-Derived From Disk, Never Recalled` (tasks.md 7.2-7.5)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.corpus = paper_graph.Corpus(
            sections={},
            blocks={
                "related-work.rw-a": _block_record(
                    "related-work.rw-a", section="related-work",
                ),
                "materials-and-methods.mm-dataset": _block_record(
                    "materials-and-methods.mm-dataset", section="materials-and-methods",
                    requires_facts=["dataset"], optional=True,
                ),
                "experimental-setup.es-dataset": _block_record(
                    "experimental-setup.es-dataset", section="experimental-setup",
                    requires_facts=["dataset"], optional=True,
                ),
            },
            order_by_section={
                "related-work": ["related-work.rw-a"],
                "materials-and-methods": ["materials-and-methods.mm-dataset"],
                "experimental-setup": ["experimental-setup.es-dataset"],
            },
        )

    def test_es_dataset_opened_alone_reports_experimental_setup_from_opened_ids(self) -> None:
        """tasks.md 7.3."""
        paper_block.open_block(self.paper_dir, "experimental-setup.es-dataset", at_end=True)

        decisions = paper_declarations.infer_skeleton_decisions(self.paper_dir, self.corpus)

        self.assertEqual(decisions["datasetPlacement"], "experimental-setup")
        self.assertFalse(decisions["relatedWork"])

    def test_both_dataset_blocks_opened_refuses_dataset_placement_conflict(self) -> None:
        """tasks.md 7.4."""
        paper_block.open_block(self.paper_dir, "materials-and-methods.mm-dataset", at_end=True)
        paper_block.open_block(self.paper_dir, "experimental-setup.es-dataset", at_end=True)

        with self.assertRaises(Refused) as ctx:
            paper_declarations.infer_skeleton_decisions(self.paper_dir, self.corpus)

        self.assertEqual(ctx.exception.code, "DATASET_PLACEMENT_CONFLICT")
        self.assertIn("materials-and-methods.mm-dataset", ctx.exception.detail)
        self.assertIn("experimental-setup.es-dataset", ctx.exception.detail)

    def test_related_work_opened_reports_present(self) -> None:
        paper_block.open_block(self.paper_dir, "related-work.rw-a", at_end=True)

        decisions = paper_declarations.infer_skeleton_decisions(self.paper_dir, self.corpus)

        self.assertTrue(decisions["relatedWork"])
        self.assertEqual(decisions["datasetPlacement"], "undecided")

    def test_a_fresh_process_infers_the_same_decision_from_disk_alone_even_when_the_skeleton_fact_disagrees(
        self,
    ) -> None:
        """`specs/skeleton-startup/spec.md`, `Scenario: A fresh process
        infers the same decision from disk alone` -- and tasks.md 7.5's own
        mutation target: the recorded `skeleton` STRUCTURAL_FACT is set to
        the OPPOSITE placement of what is actually opened on disk. If the
        inference ever read `read_fact(paper_dir, "skeleton")` instead of
        `paper_block.read_status`, it would report the fact's answer
        (`materials-and-methods`), not disk's (`experimental-setup`)."""
        paper_declarations.set_fact(self.paper_dir, "skeleton", "materials-and-methods.mm-dataset")
        paper_block.open_block(self.paper_dir, "experimental-setup.es-dataset", at_end=True)

        decisions = paper_declarations.infer_skeleton_decisions(self.paper_dir, self.corpus)

        self.assertEqual(decisions["datasetPlacement"], "experimental-setup")


class SkeletonInferenceMutationTests(unittest.TestCase):
    """tasks.md 7.5: the inference must read disk, and only disk."""

    def test_mutation_reading_the_skeleton_fact_instead_of_read_status_fails(self) -> None:
        proc = _run_against_mutant(
            '    status = paper_block.read_status(paper_dir)\n'
            '    opened_ids = {block["id"] for block in status["blocks"]} & set(corpus.blocks)',
            '    opened_ids = {read_fact(paper_dir, "skeleton")} & set(corpus.blocks)',
            "tests.test_paper_decisions.SkeletonInferenceTests"
            ".test_a_fresh_process_infers_the_same_decision_from_disk_alone_even_when_the_skeleton_fact_disagrees",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class DatasetPlacementCandidateDerivationTests(unittest.TestCase):
    """the-skill-stops-trusting-memory, item 1: `paper_declarations.
    MM_DATASET_ID`/`ES_DATASET_ID` are gone. `dataset_placement_candidates`
    derives the same two ids from the corpus's own `requires_facts`/
    `optional` shape instead -- SKILL.md:154-158, "block ids are shape
    only ... never validates an id against a list of what should exist"."""

    def test_against_the_real_shipped_corpus(self) -> None:
        """The real `sections/*.md` corpus is what motivated this change:
        `mm-dataset`/`es-dataset` both carry `requires_facts: ["dataset"]`
        and `optional: true` on disk (measured, not assumed)."""
        corpus = paper_graph.assemble_corpus(FORGE_ROOT / "sections")

        candidates = paper_declarations.dataset_placement_candidates(corpus)

        self.assertEqual(
            candidates,
            {
                "materials-and-methods": "materials-and-methods.mm-dataset",
                "experimental-setup": "experimental-setup.es-dataset",
            },
        )

    def test_a_corpus_with_no_candidate_at_all_refuses_absent(self) -> None:
        """Renaming `mm-dataset`'s `requires_facts` away from `dataset` (the
        exact scenario the task names: 'rename mm-dataset in its contract
        and infer_dataset_placement silently reports undecided forever')
        must now REFUSE, never silently degrade to `undecided`."""
        corpus = paper_graph.Corpus(
            sections={},
            blocks={
                "materials-and-methods.mm-preamble": _block_record(
                    "materials-and-methods.mm-preamble", section="materials-and-methods",
                ),
            },
            order_by_section={"materials-and-methods": ["materials-and-methods.mm-preamble"]},
        )

        with self.assertRaises(Refused) as ctx:
            paper_declarations.dataset_placement_candidates(corpus)

        self.assertEqual(ctx.exception.code, "DATASET_PLACEMENT_CANDIDATE_ABSENT")

    def test_a_section_with_two_candidates_refuses_ambiguous(self) -> None:
        corpus = paper_graph.Corpus(
            sections={},
            blocks={
                "materials-and-methods.mm-dataset": _block_record(
                    "materials-and-methods.mm-dataset", section="materials-and-methods",
                    requires_facts=["dataset"], optional=True,
                ),
                "materials-and-methods.mm-dataset-2": _block_record(
                    "materials-and-methods.mm-dataset-2", section="materials-and-methods",
                    requires_facts=["dataset"], optional=True,
                ),
            },
            order_by_section={
                "materials-and-methods": [
                    "materials-and-methods.mm-dataset", "materials-and-methods.mm-dataset-2",
                ],
            },
        )

        with self.assertRaises(Refused) as ctx:
            paper_declarations.dataset_placement_candidates(corpus)

        self.assertEqual(ctx.exception.code, "DATASET_PLACEMENT_CANDIDATE_AMBIGUOUS")
        self.assertIn("materials-and-methods.mm-dataset", ctx.exception.detail)
        self.assertIn("materials-and-methods.mm-dataset-2", ctx.exception.detail)

    def test_a_candidate_that_is_optional_but_does_not_require_dataset_is_not_a_candidate(
        self,
    ) -> None:
        """`optional` alone is not enough -- the block must also require the
        `dataset` fact. This is exactly the shape the OUT-OF-SCOPE
        `tests/test_paper_writing.py` fixture `_write_skeleton_corpus` used
        to carry (`optional: true`, no `requires_facts`) before this
        change; report note: that fixture needs `requires_facts:
        ["dataset"]` added to its `mm-dataset`/`es-dataset` blocks for
        `SkeletonTests` to keep passing under this derivation."""
        corpus = paper_graph.Corpus(
            sections={},
            blocks={
                "materials-and-methods.mm-dataset": _block_record(
                    "materials-and-methods.mm-dataset", section="materials-and-methods",
                    optional=True,
                ),
            },
            order_by_section={"materials-and-methods": ["materials-and-methods.mm-dataset"]},
        )

        with self.assertRaises(Refused) as ctx:
            paper_declarations.dataset_placement_candidates(corpus)

        self.assertEqual(ctx.exception.code, "DATASET_PLACEMENT_CANDIDATE_ABSENT")

    def test_mutation_dropping_the_optional_check_breaks_the_ambiguous_guard(self) -> None:
        """If `dataset_placement_candidates` ever stopped checking `block.
        optional` (matched on `requires_facts` alone), a section carrying a
        non-optional block that also requires `dataset` would silently
        become a second candidate, and the real shipped corpus -- which has
        several non-optional blocks requiring `dataset` alongside
        `mm-dataset`/`es-dataset`? No: measured, only the two optional ones
        require it. This mutation instead proves the REQUIRES_FACTS check
        is load-bearing: dropping it turns every optional block into a
        candidate, which the real corpus's `related-work`/other optional
        blocks (if any) would trip. To keep this hermetic, exercise it
        against a synthetic ambiguous fixture instead of relying on the
        real corpus's own shape drifting under test."""
        proc = _run_against_mutant(
            'if block.optional and "dataset" in block.requires_facts:',
            'if block.optional:',
            "tests.test_paper_decisions.DatasetPlacementCandidateDerivationTests"
            ".test_a_candidate_that_is_optional_but_does_not_require_dataset_is_not_a_candidate",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class SkeletonExcludedIdsDerivationTests(unittest.TestCase):
    """`paper_cli._skeleton_excluded_ids` no longer reads `paper_
    declarations.MM_DATASET_ID`/`ES_DATASET_ID` -- it derives the excluded
    candidate from the corpus via `dataset_placement_candidates`."""

    def _corpus(self) -> "paper_graph.Corpus":
        return paper_graph.Corpus(
            sections={},
            blocks={
                "related-work.rw-a": _block_record("related-work.rw-a", section="related-work"),
                "materials-and-methods.mm-dataset": _block_record(
                    "materials-and-methods.mm-dataset", section="materials-and-methods",
                    requires_facts=["dataset"], optional=True,
                ),
                "experimental-setup.es-dataset": _block_record(
                    "experimental-setup.es-dataset", section="experimental-setup",
                    requires_facts=["dataset"], optional=True,
                ),
            },
            order_by_section={
                "related-work": ["related-work.rw-a"],
                "materials-and-methods": ["materials-and-methods.mm-dataset"],
                "experimental-setup": ["experimental-setup.es-dataset"],
            },
        )

    def test_materials_choice_excludes_the_experimental_setup_candidate(self) -> None:
        excluded = paper_cli._skeleton_excluded_ids(
            self._corpus(), related_work=True, dataset_in="materials",
        )

        self.assertEqual(excluded, {"experimental-setup.es-dataset"})

    def test_experimental_setup_choice_excludes_the_materials_candidate(self) -> None:
        excluded = paper_cli._skeleton_excluded_ids(
            self._corpus(), related_work=True, dataset_in="experimental-setup",
        )

        self.assertEqual(excluded, {"materials-and-methods.mm-dataset"})

    def test_a_corpus_with_no_dataset_candidate_at_all_refuses(self) -> None:
        """`build_skeleton`/`_skeleton_excluded_ids` can no longer silently
        open every block when the corpus names no dataset-placement
        candidate at all -- it refuses, naming the absence, exactly like
        `dataset_placement_candidates` itself."""
        corpus = paper_graph.Corpus(
            sections={}, blocks={}, order_by_section={},
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli._skeleton_excluded_ids(corpus, related_work=True, dataset_in="materials")

        self.assertEqual(ctx.exception.code, "DATASET_PLACEMENT_CANDIDATE_ABSENT")


class ProvenanceTests(unittest.TestCase):
    """`specs/contract-provenance/spec.md` + the `block-substitution`
    delta (`specs/block-substitution/spec.md`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.contract_path = Path(self._tmp.name) / "sections" / "intro.md"
        self.contract_path.parent.mkdir(parents=True, exist_ok=True)
        self.contract_path.write_bytes(b"contract v1\n")

    def _clock(self) -> str:
        return _FIXED_CLOCK

    def _open_and_substitute(self, block_id, body, *, contract=None):
        paper_block.open_block(self.paper_dir, block_id, at_end=True)
        return paper_block.substitute(
            self.paper_dir, block_id, new_body=body, contract=contract, clock=self._clock,
        )

    def test_provenanced_write_persists_the_write_time_baseline(self) -> None:
        self._open_and_substitute("intro", b"hello\n", contract=self.contract_path)

        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        record = paper_provenance.read_provenance(tex_path.read_bytes())
        entry = next(r for r in record["body"]["records"] if r["block"] == "intro")
        expected_digest = hashlib.sha256(b"contract v1\n").hexdigest()
        self.assertEqual(entry["contract_sha256"], expected_digest)
        self.assertEqual(entry["generation"], 0)

    def test_provenanced_and_unprovenanced_writes_produce_identical_block_bytes(self) -> None:
        self._open_and_substitute("with-contract", b"same body\n", contract=self.contract_path)
        self._open_and_substitute("without-contract", b"same body\n")

        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        status = paper_block.status(tex_path.read_bytes())
        digest_a = next(b["digest"] for b in status["blocks"] if b["id"] == "with-contract")
        digest_b = next(b["digest"] for b in status["blocks"] if b["id"] == "without-contract")
        self.assertEqual(digest_a, digest_b)

        record = paper_provenance.read_provenance(tex_path.read_bytes())
        provenanced_ids = {r["block"] for r in record["body"]["records"]}
        self.assertIn("with-contract", provenanced_ids)
        self.assertNotIn("without-contract", provenanced_ids)

    def test_unreadable_contract_refuses_before_any_write(self) -> None:
        missing = Path(self._tmp.name) / "sections" / "missing.md"
        paper_block.open_block(self.paper_dir, "intro", at_end=True)
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        pre = tex_path.read_bytes()

        with self.assertRaises(Refused) as ctx:
            paper_block.substitute(self.paper_dir, "intro", new_body=b"x\n", contract=missing)
        self.assertEqual(ctx.exception.code, "CONTRACT_UNREADABLE")
        self.assertEqual(
            tex_path.read_bytes(), pre, "no block byte and no provenance record on refusal"
        )

    def test_hand_edited_block_still_refuses_even_with_contract(self) -> None:
        self._open_and_substitute("intro", b"hello\n", contract=self.contract_path)
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        corrupted = tex_path.read_bytes().replace(b"hello", b"hellx", 1)
        tex_path.write_bytes(corrupted)

        with self.assertRaises(Refused) as ctx:
            paper_block.substitute(
                self.paper_dir, "intro", new_body=b"new\n", contract=self.contract_path,
            )
        self.assertEqual(ctx.exception.code, "BLOCK_HAND_EDITED")

    def test_a_block_written_without_contract_is_unprovenanced(self) -> None:
        self._open_and_substitute("methods", b"body\n")
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        self.assertIsNone(
            paper_provenance.drift(tex_path.read_bytes(), "methods", self.contract_path)
        )

    def test_drift_is_reported_on_a_single_byte_edit_and_block_is_untouched(self) -> None:
        self._open_and_substitute("results", b"body\n", contract=self.contract_path)
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        before = tex_path.read_bytes()

        self.contract_path.write_bytes(b"contract v2\n")

        self.assertTrue(
            paper_provenance.drift(tex_path.read_bytes(), "results", self.contract_path)
        )
        self.assertEqual(tex_path.read_bytes(), before, "drift detection must never rewrite a block")

    def test_no_drift_when_the_contract_is_unchanged(self) -> None:
        self._open_and_substitute("results", b"body\n", contract=self.contract_path)
        tex_path = paper_block.resolve_main_tex(self.paper_dir)

        self.assertFalse(
            paper_provenance.drift(tex_path.read_bytes(), "results", self.contract_path)
        )

    def test_provenance_hand_edited_refuses_and_writes_nothing(self) -> None:
        self._open_and_substitute("intro", b"hello\n", contract=self.contract_path)
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        pre = tex_path.read_bytes()
        record = paper_provenance.read_provenance(pre)
        corrupted = (
            pre[: record["begin_start"]]
            + pre[record["begin_start"]:record["end_end"]].replace(b"contract", b"contrbct", 1)
            + pre[record["end_end"]:]
        )
        tex_path.write_bytes(corrupted)

        paper_block.open_block(self.paper_dir, "second", at_end=True)
        with self.assertRaises(Refused) as ctx:
            paper_block.substitute(
                self.paper_dir, "second", new_body=b"x\n", contract=self.contract_path,
            )
        self.assertEqual(ctx.exception.code, "PROVENANCE_HAND_EDITED")


class ProvenanceMutationTests(unittest.TestCase):
    """Mutation 3 (design.md): recomputing the baseline at read time makes
    drift structurally undetectable."""

    def test_mutation_3_recomputing_the_baseline_at_read_time_breaks_drift_detection(self) -> None:
        proc = _run_against_mutant(
            "return current_digest != entry[\"contract_sha256\"]",
            "return current_digest != current_digest",
            "tests.test_paper_decisions.ProvenanceTests"
            ".test_drift_is_reported_on_a_single_byte_edit_and_block_is_untouched",
            source_path=SKILL_SCRIPTS / "paper_provenance.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class ObservationReportTests(unittest.TestCase):
    """`design.md`, `A fact the agent may observe is a partition, not a
    guideline` — the schema `insumos-observer`'s report is checked against."""

    def test_an_id_outside_the_observable_facts_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.validate_observation_report(
                {"contributions": {"satisfied": True, "evidence": [["x", "y"]]}}
            )
        self.assertEqual(ctx.exception.code, "NOT_AN_OBSERVABLE_FACT")
        self.assertIn("contributions", ctx.exception.detail)

    def test_implementation_and_results_sharing_one_evidence_path_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.validate_observation_report({
                "implementation": {"satisfied": True, "evidence": [["repo/code.py", "q1"]]},
                "results": {"satisfied": True, "evidence": [["repo/code.py", "q2"]]},
            })
        self.assertEqual(ctx.exception.code, "EVIDENCE_CONFLATED")

    def test_distinct_evidence_paths_are_accepted(self) -> None:
        paper_declarations.validate_observation_report({
            "implementation": {"satisfied": True, "evidence": [["repo/code.py", "q1"]]},
            "results": {"satisfied": True, "evidence": [["repo/results.json", "q2"]]},
            "formulation": {"satisfied": False, "evidence": []},
        })  # raises nothing


class ObservationReportMutationTests(unittest.TestCase):
    """Mutation 7 (design.md): accepting one evidence path for both facts
    breaks the conflation guard."""

    def test_mutation_7_accepting_one_shared_path_breaks_the_conflation_guard(self) -> None:
        proc = _run_against_mutant(
            "overlap = implementation_paths & results_paths",
            "overlap = set()",
            "tests.test_paper_decisions.ObservationReportTests"
            ".test_implementation_and_results_sharing_one_evidence_path_refuses",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class PlanTests(unittest.TestCase):
    """`specs/contract-provenance/spec.md`, `Requirement: plan Aggregates
    Registry, Declarations, and Provenance`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.guidance_dir = self.forge_root / "guidance"
        self.contract_path = Path(self._tmp.name) / "sections" / "intro.md"
        self.contract_path.parent.mkdir(parents=True, exist_ok=True)
        self.contract_path.write_bytes(b"contract v1\n")

    def _clock(self) -> str:
        return _FIXED_CLOCK

    def test_plan_aggregates_all_three_concerns_and_writes_nothing(self) -> None:
        classified = self.guidance_dir / "classified-folder"
        classified.mkdir(parents=True)
        (classified / ".paper-writing.json").write_text(
            json.dumps({"class": "evidence"}), encoding="utf-8",
        )
        (self.guidance_dir / "unclassified-folder").mkdir(parents=True)

        paper_declarations.set_declaration(
            self.paper_dir, "author-roles", "Alice", clock=self._clock,
        )

        paper_block.open_block(self.paper_dir, "current", at_end=True)
        paper_block.substitute(
            self.paper_dir, "current", new_body=b"x\n", contract=self.contract_path,
            clock=self._clock,
        )
        paper_block.open_block(self.paper_dir, "bare", at_end=True)
        paper_block.substitute(self.paper_dir, "bare", new_body=b"y\n")

        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        before = tex_path.read_bytes()

        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        self.assertEqual(
            report["guidance"],
            {
                "classified-folder": {"class": "evidence", "declaration": "declared-unsealed"},
                "unclassified-folder": {"class": "unclassified", "declaration": "undeclared"},
            },
        )
        recorded = next(
            r for r in report["declarations"]["records"] if r["id"] == "author-roles"
        )
        self.assertEqual(recorded["value"], "Alice")
        provenance_by_block = {p["block"]: p["state"] for p in report["provenance"]}
        self.assertEqual(provenance_by_block, {"current": "current", "bare": "unprovenanced"})

        self.assertEqual(tex_path.read_bytes(), before, "plan must never write")

    def test_plan_reports_drift_after_a_contract_edit(self) -> None:
        paper_block.open_block(self.paper_dir, "results", at_end=True)
        paper_block.substitute(
            self.paper_dir, "results", new_body=b"x\n", contract=self.contract_path,
            clock=self._clock,
        )
        self.contract_path.write_bytes(b"contract v2\n")

        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        provenance_by_block = {p["block"]: p["state"] for p in report["provenance"]}
        self.assertEqual(provenance_by_block["results"], "drifted")

    def test_one_contract_edit_flags_every_block_sharing_that_contract(self) -> None:
        """`specs/contract-provenance/spec.md`, `Requirement: Whole-File
        Hashing Over-Reports by Design`, `One edit flags every block of the
        section` — two blocks provenanced against the SAME contract file;
        editing one byte of it must drift BOTH, even though only one of the
        two ever reads the other's own guidance text. Under-reporting (a
        real drift going unreported for either block) is the failure this
        guards against; over-reporting both is the accepted, deliberate
        direction the spec names."""
        paper_block.open_block(self.paper_dir, "results-a", at_end=True)
        paper_block.substitute(
            self.paper_dir, "results-a", new_body=b"a\n", contract=self.contract_path,
            clock=self._clock,
        )
        paper_block.open_block(self.paper_dir, "results-b", at_end=True)
        paper_block.substitute(
            self.paper_dir, "results-b", new_body=b"b\n", contract=self.contract_path,
            clock=self._clock,
        )

        self.contract_path.write_bytes(b"contract v2\n")

        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        provenance_by_block = {p["block"]: p["state"] for p in report["provenance"]}
        self.assertEqual(provenance_by_block["results-a"], "drifted")
        self.assertEqual(provenance_by_block["results-b"], "drifted")

    def test_a_bare_call_with_no_sections_dir_reports_no_section_guidance_key(self) -> None:
        """The two pre-existing `compute_plan` callers that never built a
        section corpus keep getting exactly the same three keys back —
        `sectionGuidance` is additive, never a required key."""
        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)
        self.assertNotIn("sectionGuidance", report)

    def test_plan_reports_every_corpus_sections_own_citation_status(self) -> None:
        """item 1: given a real `sections_dir`, `plan` reports one
        `sectionGuidance` entry per section id the corpus declares —
        derived from the corpus, never a hand-listed tuple — additive to
        `guidance`'s own function-named-folder registry."""
        sections_dir = Path(self._tmp.name) / "real-sections"
        sections_dir.mkdir()
        header = json.dumps({
            "section": "introduction", "position": 1,
            "blocks": [
                {"id": "only", "requires_facts": [], "requires_declarations": [], "citations": "none"},
            ],
        })
        (sections_dir / "01-intro.md").write_text(
            f"---\n{header}\n---\n\nProse.\n\n### External inputs\n\nNone.\n\n"
            "### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        (self.guidance_dir / "introduction").mkdir(parents=True)
        (self.guidance_dir / "reference-papers").mkdir(parents=True)

        report = paper_cli.compute_plan(
            self.paper_dir, guidance_dir=self.guidance_dir, sections_dir=sections_dir,
        )

        self.assertIn("sectionGuidance", report)
        self.assertEqual(set(report["sectionGuidance"]), {"introduction"})
        self.assertTrue(report["sectionGuidance"]["introduction"]["exists"])
        # `guidance`'s own function-named-folder registry is untouched.
        self.assertEqual(
            report["guidance"]["reference-papers"],
            {"class": "unclassified", "declaration": "undeclared"},
        )

    def test_guidance_entries_widen_to_class_and_declaration_object(self) -> None:
        """`specs/source-declaration-authoring/spec.md`, `Requirement: The
        Position Report Names Every Declarable Root's And Every Guidance
        Folder's Declaration State`: `guidance`'s bare class string widens
        to `{"class": ..., "declaration": ...}` -- an unsealed classified
        folder reports `declared-unsealed`, an unmarked one reports
        `undeclared`, never a dropped `class` value."""
        classified = self.guidance_dir / "classified-folder"
        classified.mkdir(parents=True)
        (classified / ".paper-writing.json").write_text(
            json.dumps({"class": "evidence"}), encoding="utf-8",
        )
        (self.guidance_dir / "unclassified-folder").mkdir(parents=True)

        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        self.assertEqual(
            report["guidance"],
            {
                "classified-folder": {"class": "evidence", "declaration": "declared-unsealed"},
                "unclassified-folder": {"class": "unclassified", "declaration": "undeclared"},
            },
        )

    def test_guidance_declaration_widens_to_declared_sealed_one_vocabulary_with_sourceroots(
        self,
    ) -> None:
        """tasks.md 5.15 (surfaced by the S3+S4 apply report, measured true
        by running `plan`): `guidance` and `sourceRoots` MUST report the
        SAME four-value declaration vocabulary for the identical concept --
        design.md Decision I's own worked `plan` example shows a
        `guidance` folder reporting `declared-sealed`, and
        `specs/source-declaration-authoring/spec.md`'s own scenario
        `guidance's report widens without dropping its class` requires
        exactly that. Proven by calling `compute_plan` (the same function
        the `plan` verb runs) and reading its actual output for BOTH a
        sealed and an unsealed folder in one call -- never by asserting a
        field merely exists."""
        sealed_folder = self.guidance_dir / "sealed-folder"
        sealed_folder.mkdir(parents=True)
        sealed_obj = {"class": "style-reference"}
        sealed_obj[paper_marker.SEAL_KEY] = paper_marker.computed_seal(sealed_obj)
        (sealed_folder / ".paper-writing.json").write_text(
            json.dumps(sealed_obj), encoding="utf-8",
        )
        unsealed_folder = self.guidance_dir / "unsealed-folder"
        unsealed_folder.mkdir(parents=True)
        (unsealed_folder / ".paper-writing.json").write_text(
            json.dumps({"class": "evidence"}), encoding="utf-8",
        )

        report = paper_cli.compute_plan(self.paper_dir, guidance_dir=self.guidance_dir)

        self.assertEqual(
            report["guidance"]["sealed-folder"],
            {"class": "style-reference", "declaration": "declared-sealed"},
        )
        self.assertEqual(
            report["guidance"]["unsealed-folder"],
            {"class": "evidence", "declaration": "declared-unsealed"},
        )


class InsumosObserverThreatMatrixTests(unittest.TestCase):
    """Threat matrix (design.md): process integration. `insumos-observer`'s
    frontmatter `tools` contains none of Write, Edit, Bash — the capability
    layer that survives non-compliance even if its own body were ever
    edited to suggest otherwise."""

    def test_frontmatter_tools_contains_none_of_write_edit_bash(self) -> None:
        path = AGENTS_DIR / "insumos-observer.md"
        text = path.read_text(encoding="utf-8")
        header = text.split("---\n", 2)[1]
        tools_line = next(line for line in header.splitlines() if line.startswith("tools:"))
        tools = {tool.strip() for tool in tools_line.split(":", 1)[1].split(",")}
        self.assertTrue(tools, "insumos-observer.md declares no tools at all")
        self.assertTrue(
            tools.isdisjoint({"Write", "Edit", "Bash"}),
            f"insumos-observer.md grants {tools & {'Write', 'Edit', 'Bash'}}, "
            "which lets it write a record or invoke declare directly",
        )


class ReopenInvalidatesProvenanceEndToEndTests(unittest.TestCase):
    """`specs/paper-declarations/spec.md`, `Requirement: Reopening
    Invalidates Exactly the Blocks That Named It` — driven through the real
    CLI end to end (`subprocess`, real `main.tex` on disk), the same shape
    the verify FAIL's own manual reproduction used to disprove this
    requirement.

    This is deliberately NOT a test against `paper_declarations.affected_blocks`
    or `paper_cli.compute_plan` called directly with a synthetic corpus —
    that is exactly the shape
    (`DeclarationsTests.test_reopen_narrows_to_exactly_the_naming_blocks`)
    that shipped green while the actual `declare --reopen` -> `plan` chain
    gave zero signal, because nothing outside that one test ever called
    `affected_blocks`. This test drives `scaffold` -> `declare` -> `open`
    -> `substitute --contract` -> `plan` -> `declare --reopen` -> `plan`
    as five real subprocess invocations of `paper_cli.py` and asserts the
    block's reported state changes from `current` to `drifted`.
    """

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / "implementations"
            / f".paper-writing-cli-reopen-test-{os.getpid()}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        self.sections_dir = self.test_root / "sections"
        self.sections_dir.mkdir(parents=True)

        header = json.dumps({
            "section": "reopen-e2e",
            "position": 1,
            "blocks": [
                {
                    "id": "needs-repo-url",
                    "requires_facts": [],
                    "requires_declarations": [
                        {
                            "value": "repository-url",
                            "source": {
                                "file": "sections/reopen-e2e.md",
                                "quote": "This block requires the repository-url.",
                            },
                        }
                    ],
                    "citations": "none",
                }
            ],
        })
        self.contract_path = self.sections_dir / "reopen-e2e.md"
        self.contract_path.write_text(
            f"---\n{header}\n---\n\nProse body, never read for meaning. "
            "This block requires the repository-url.\n\n"
            "### External inputs\n\n### Internal chain\n",
            encoding="utf-8",
        )

    def _run(self, *args: str):
        proc = subprocess.run(
            [sys.executable, str(CLI), *args],
            capture_output=True, text=True, timeout=30,
        )
        return proc.returncode, json.loads(proc.stdout), proc.stderr

    def _plan_state_for(self, block_id: str) -> str:
        code, payload, stderr = self._run(
            "plan", "--paper", str(self.paper_dir), "--sections", str(self.sections_dir),
        )
        self.assertEqual(code, 0, stderr or payload)
        provenance_by_block = {p["block"]: p["state"] for p in payload["provenance"]}
        return provenance_by_block[block_id]

    def test_reopen_then_plan_stops_reporting_current(self) -> None:
        block_id = "reopen-e2e.needs-repo-url"

        code, payload, stderr = self._run("scaffold", "--paper", str(self.paper_dir))
        self.assertEqual(code, 0, stderr or payload)

        code, payload, stderr = self._run(
            "declare", "--paper", str(self.paper_dir),
            "--declaration", "repository-url", "--value", "https://example.org/repo",
        )
        self.assertEqual(code, 0, stderr or payload)

        code, payload, stderr = self._run(
            "open", "--paper", str(self.paper_dir),
            "--block", block_id, "--at-end",
        )
        self.assertEqual(code, 0, stderr or payload)

        body_path = self.test_root / "body.tex"
        body_path.write_text("some prose\n", encoding="utf-8")
        code, payload, stderr = self._run(
            "substitute", "--paper", str(self.paper_dir),
            "--block", block_id, "--body", str(body_path),
            "--contract", str(self.contract_path),
        )
        self.assertEqual(code, 0, stderr or payload)

        self.assertEqual(
            self._plan_state_for(block_id), "current",
            "sanity check before reopening: a freshly provenanced block "
            "against an unchanged contract must report current",
        )

        code, payload, stderr = self._run(
            "declare", "--paper", str(self.paper_dir), "--reopen", "repository-url",
        )
        self.assertEqual(code, 0, stderr or payload)

        self.assertEqual(
            self._plan_state_for(block_id), "drifted",
            "reopening 'repository-url' -- a declaration this exact block's "
            "own contract names in requires_declarations -- must stop plan "
            "from reporting the block current. This is the end-to-end "
            "chain the verify FAIL's manual reproduction ran to prove "
            "affected_blocks() had no real caller; a synthetic-corpus unit "
            "test on that helper alone is not sufficient evidence this "
            "requirement holds.",
        )


class ReadinessDeclinedFactsTests(unittest.TestCase):
    """`a-declined-fact-has-somewhere-to-live` + its `condition-that-expires`
    extension: the decisive proof that a decline actually changes what
    `readiness`/`phases` report, not merely what `declarations` stores --
    and that a LAPSED decline's condition is surfaced, never silently
    treated as still `declined` and never silently auto-unblocked. Same
    synthetic-contract fixture shape as `tests/test_paper_writing.py`'s
    `ReadinessBasisTests`. Three blocks:

    - `declined-only` requires ONLY the declined fact -> `"declined"` while
      the condition holds, `"blocked"` (with `stale_declines`) once it
      lapses.
    - `declined-plus-live` also requires a live (never declared) fact ->
      a decline must never mask a real gap, so this stays `"blocked"`
      regardless of the decline's own holds/stale state.
    - `declined-plus-declaration` also requires a never-declared
      declaration -> also stays `"blocked"` regardless.

    Driven through BOTH `compute_readiness_report` and `compute_phases`,
    which both compute from the same `paper_readiness.compute_readiness`
    call and must therefore agree.
    """

    REASON = "no experimental protocol exists yet in experiments/"
    CONDITION = {"type": "directory-empty-except", "path": "experiments", "ignore": [".gitkeep"]}

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
                    "file": "sections/01-declined-readiness.md",
                    "quote": f"This block requires the {fact}.",
                },
            }

        def _decl(name: str) -> dict:
            return {
                "value": name,
                "source": {
                    "file": "sections/01-declined-readiness.md",
                    "quote": f"This block requires the {name}.",
                },
            }

        header = json.dumps({
            "section": "declined-readiness",
            "position": 1,
            "blocks": [
                {
                    "id": "declined-only", "requires_facts": [_req("experimental-design")],
                    "requires_declarations": [], "citations": "none",
                },
                {
                    "id": "declined-plus-live",
                    "requires_facts": [_req("experimental-design"), _req("dataset")],
                    "requires_declarations": [], "citations": "none",
                },
                {
                    "id": "declined-plus-declaration",
                    "requires_facts": [_req("experimental-design")],
                    "requires_declarations": [_decl("repository-url")], "citations": "none",
                },
            ],
        })
        (self.sections_dir / "01-declined-readiness.md").write_text(
            f"---\n{header}\n---\n\nProse. This block requires the experimental-design. "
            "This block requires the dataset. This block requires the repository-url."
            "\n\n### External inputs\n\nNone.\n\n"
            "### Internal chain\n\nNone.\n",
            encoding="utf-8",
        )
        paper_declarations.decline_fact(
            self.paper_dir, "experimental-design", self.REASON, self.CONDITION,
        )

    def _lapse_the_condition(self) -> None:
        """Writes a real file into the condition's own named path, so
        `_evaluate_condition` reports the decline's condition as no longer
        holding -- the stale/lapsed state, never touched by `--reopen`."""
        experiments_dir = self.forge_root / "experiments"
        experiments_dir.mkdir(parents=True, exist_ok=True)
        (experiments_dir / "protocol.md").write_text("a real protocol\n", encoding="utf-8")

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

    # --- state 1: the condition holds -----------------------------------

    def test_readiness_reports_declined_only_block_as_declined(self) -> None:
        block = self._readiness_block("declined-readiness.declined-only")
        self.assertEqual(block["status"], "declined")
        self.assertEqual(
            block["declined_facts"],
            [{"fact": "experimental-design", "reason": self.REASON}],
        )
        self.assertEqual(block.get("stale_declines", []), [])

    def test_phases_agrees_declined_only_block_is_declined(self) -> None:
        block = self._phases_block("declined-readiness.declined-only")
        self.assertEqual(block["status"], "declined")
        self.assertEqual(
            block["declined_facts"],
            [{"fact": "experimental-design", "reason": self.REASON}],
        )
        self.assertEqual(block["stale_declines"], [])

    # --- state 2: the condition has lapsed (stale) ----------------------

    def test_readiness_reports_a_lapsed_decline_as_blocked_with_stale_declines(self) -> None:
        self._lapse_the_condition()

        block = self._readiness_block("declined-readiness.declined-only")

        self.assertEqual(
            block["status"], "blocked",
            "a lapsed decline must never still read as declined -- and must "
            "never be silently auto-unblocked into writable either",
        )
        self.assertEqual(block.get("declined_facts", []), [])
        self.assertEqual(len(block["stale_declines"]), 1)
        stale = block["stale_declines"][0]
        self.assertEqual(stale["fact"], "experimental-design")
        self.assertEqual(stale["reason"], self.REASON)
        self.assertEqual(stale["condition"], self.CONDITION)
        self.assertIn("protocol.md", stale["detail"])

    def test_phases_agrees_a_lapsed_decline_is_blocked_with_stale_declines(self) -> None:
        self._lapse_the_condition()

        block = self._phases_block("declined-readiness.declined-only")

        self.assertEqual(block["status"], "blocked")
        self.assertEqual(block["declined_facts"], [])
        self.assertEqual(len(block["stale_declines"]), 1)
        self.assertEqual(block["stale_declines"][0]["fact"], "experimental-design")
        self.assertIn("protocol.md", block["stale_declines"][0]["detail"])

    # --- state 3: mixed / regression -- a decline never masks a real gap,
    # re-verified against the v2 three-bucket logic under BOTH the holding
    # and the lapsed condition, so this cannot regress silently either way

    def test_readiness_reports_declined_plus_live_fact_as_blocked(self) -> None:
        block = self._readiness_block("declined-readiness.declined-plus-live")
        self.assertEqual(block["status"], "blocked")

    def test_readiness_reports_declined_plus_missing_declaration_as_blocked(self) -> None:
        block = self._readiness_block("declined-readiness.declined-plus-declaration")
        self.assertEqual(block["status"], "blocked")

    def test_phases_agrees_declined_plus_live_fact_is_blocked(self) -> None:
        block = self._phases_block("declined-readiness.declined-plus-live")
        self.assertEqual(block["status"], "blocked")

    def test_phases_agrees_declined_plus_missing_declaration_is_blocked(self) -> None:
        block = self._phases_block("declined-readiness.declined-plus-declaration")
        self.assertEqual(block["status"], "blocked")

    def test_readiness_reports_declined_plus_live_fact_as_blocked_even_once_lapsed(self) -> None:
        self._lapse_the_condition()
        block = self._readiness_block("declined-readiness.declined-plus-live")
        self.assertEqual(block["status"], "blocked")

    def test_readiness_reports_declined_plus_missing_declaration_as_blocked_even_once_lapsed(
        self,
    ) -> None:
        self._lapse_the_condition()
        block = self._readiness_block("declined-readiness.declined-plus-declaration")
        self.assertEqual(block["status"], "blocked")


class ReadinessDeclinedFactsMutationTests(unittest.TestCase):
    """The literal 'a mutation that drops the decline-awareness from the
    readiness computation must turn it red' requirement: forcing
    `compute_block_readiness` to always report `"blocked"` for a missing
    fact, even when every missing fact is declined and holding, must
    redden the decisive proof above -- and a mutation that stops
    `read_declined` from re-evaluating the condition at all (treating a
    decline as permanent) must redden the lapsed-case proof."""

    def test_mutation_9_always_blocked_breaks_the_declined_only_readiness_guard(self) -> None:
        proc = _run_against_mutant(
            'status = (\n'
            '            "declined" if (declined_missing and not stale_missing and not live_missing)\n'
            '            else "blocked"\n'
            '        )',
            'status = "blocked"',
            "tests.test_paper_decisions.ReadinessDeclinedFactsTests"
            ".test_readiness_reports_declined_only_block_as_declined",
            source_path=SKILL_SCRIPTS / "paper_readiness.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_10_never_re_evaluating_the_condition_breaks_the_lapsed_case_guard(
        self,
    ) -> None:
        proc = _run_against_mutant(
            'holds, detail = _evaluate_condition(root, entry["condition"])',
            'holds, detail = True, "always holds"',
            "tests.test_paper_decisions.ReadinessDeclinedFactsTests"
            ".test_readiness_reports_a_lapsed_decline_as_blocked_with_stale_declines",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class SourceAvailableTests(unittest.TestCase):
    """`the-skill-stops-trusting-memory`, item 5: `paper_declarations.
    source_available` -- gitignore-blind by construction, unlike `fd`/`rg`
    (both honor `.gitignore` by default, which is exactly what made an
    agent's shell exploration report a populated `implementations/<repo>/`
    and an 8-paper `guidance/` tree both ABSENT/EMPTY in the session that
    produced this fix)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_a_non_existent_root_is_not_available(self) -> None:
        self.assertFalse(paper_declarations.source_available(self.root / "does-not-exist"))

    def test_an_existing_but_empty_root_is_not_available(self) -> None:
        target = self.root / "empty"
        target.mkdir()
        self.assertFalse(paper_declarations.source_available(target))

    def test_a_populated_root_is_available(self) -> None:
        target = self.root / "populated"
        target.mkdir()
        (target / "file.txt").write_text("x", encoding="utf-8")
        self.assertTrue(paper_declarations.source_available(target))

    def test_a_root_hidden_from_git_by_gitignore_is_still_measured_available(self) -> None:
        """The exact defect: a `.gitignore` pattern that empties this tree
        for `fd`/`rg` must NOT empty it for this function -- it never
        shells out, by construction, not by discipline."""
        target = self.root / "gitignored"
        target.mkdir()
        (self.root / ".gitignore").write_text(f"{target.name}/*\n", encoding="utf-8")
        (target / "real-content.py").write_text("print(1)", encoding="utf-8")

        self.assertTrue(paper_declarations.source_available(target))


class BindableFactDerivationTests(unittest.TestCase):
    """`source-section-binding` spec, `Requirement: Bindable Facts Are
    Derived, Never Listed`: a fact is bindable iff it is a key of
    `FACT_SOURCE_ROOT` -- membership in the mapping is the sole test, never
    a hand-maintained list of fact ids anywhere under `scripts/`."""

    def test_a_document_rooted_fact_is_bindable(self) -> None:
        self.assertTrue(paper_declarations.is_bindable_fact("formulation"))

    def test_a_produced_fact_is_never_bindable(self) -> None:
        self.assertFalse(paper_declarations.is_bindable_fact("gap"))

    def test_the_structural_fact_is_never_bindable(self) -> None:
        self.assertFalse(paper_declarations.is_bindable_fact("skeleton"))

    def test_a_sixth_root_widens_bindability_with_zero_engine_edit(self) -> None:
        """The spec's own mutation scenario: extending `FACT_SOURCE_ROOT`
        with a sixth fact/root pair (via `patch.dict`, never a source
        edit) makes that sixth fact bindable, proving the test is
        membership in the mapping and not a second, hand-maintained list."""
        with unittest.mock.patch.dict(
            paper_declarations.FACT_SOURCE_ROOT, {"a-sixth-fact": "a-sixth-root"}
        ):
            self.assertTrue(paper_declarations.is_bindable_fact("a-sixth-fact"))


class SourceRootDeclaresItsKindTests(unittest.TestCase):
    """`the-requirement-names-the-section-that-feeds-it`, U2b correctness
    repair to `source-section-binding` spec's `Requirement: An Unmeasured
    Root Is Reported, Never Silently Passed`: a `FACT_SOURCE_ROOT` value
    is one `SourceRoot(name, kind)` record, never a bare string -- and
    `kind` carries no default, so a sixth fact/root pair that omits it
    fails immediately rather than silently defaulting to `PROSE` and
    becoming spuriously section-bindable."""

    def test_kind_carries_no_default_and_must_be_stated(self) -> None:
        with self.assertRaises(TypeError):
            paper_declarations.SourceRoot("a-sixth-root")  # type: ignore[call-arg]

    def test_every_shipped_root_states_its_kind(self) -> None:
        for fact_id, root in paper_declarations.FACT_SOURCE_ROOT.items():
            self.assertIsInstance(
                root, paper_declarations.SourceRoot, f"{fact_id!r} is not a SourceRoot record"
            )
            self.assertIn(root.kind, (paper_declarations.SourceRootKind.PROSE,
                                       paper_declarations.SourceRootKind.REPOSITORY,
                                       paper_declarations.SourceRootKind.INGESTED))

    def test_implementation_and_results_are_repository_kind_not_prose(self) -> None:
        """The exact defect: `implementation`/`results` are read by
        RUNNING a target repository, never by reading a document's
        headings -- so both must be `REPOSITORY`, never `PROSE`."""
        self.assertEqual(
            paper_declarations.FACT_SOURCE_ROOT["implementation"].kind,
            paper_declarations.SourceRootKind.REPOSITORY,
        )
        self.assertEqual(
            paper_declarations.FACT_SOURCE_ROOT["results"].kind,
            paper_declarations.SourceRootKind.REPOSITORY,
        )

    def test_formulation_and_experimental_design_stay_prose(self) -> None:
        for fact_id in ("formulation", "experimental-design"):
            self.assertEqual(
                paper_declarations.FACT_SOURCE_ROOT[fact_id].kind,
                paper_declarations.SourceRootKind.PROSE,
            )

    def test_dataset_is_ingested_kind_not_prose(self) -> None:
        """U2c ruling (`the-requirement-names-the-section-that-feeds-it`):
        `dataset` is sourced from the ingested evidence document, never
        from `proposals/`'s mathematics lineage -- a published paper gets
        no `r22`, so it cannot share `formulation`'s `PROSE` root."""
        self.assertEqual(
            paper_declarations.FACT_SOURCE_ROOT["dataset"].kind,
            paper_declarations.SourceRootKind.INGESTED,
        )

    def test_dataset_root_name_is_never_the_paper_specific_folder(self) -> None:
        """Generality: the `SourceRoot.name` for `dataset` is a generic
        vocabulary word this skill already uses (`paper_guidance.CLASSES`
        holds `'evidence'`), never this paper's own guidance folder name
        (asserted below, never repeated in this docstring -- the same
        reason `ForgeVocabularyDerivedGuardTests` scans this suite's own
        commentary) -- which root actually feeds it is DERIVED at
        resolution time, never named here."""
        self.assertNotEqual(paper_declarations.FACT_SOURCE_ROOT["dataset"].name, "data-paper")
        self.assertNotEqual(paper_declarations.FACT_SOURCE_ROOT["dataset"].name, "proposals")


class DeclarationStateTests(unittest.TestCase):
    """`specs/source-declaration-authoring/spec.md`, `Requirement: Absence
    Is A Reported State; A Broken Seal Refuses Where The Marker Is Read`
    -- S2's four-value vocabulary (`undeclared` | `declared-unsealed` |
    `declared-sealed` | `n/a`), now that `paper_marker.py` exists."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_a_non_prose_root_reports_n_a_by_kind_never_by_name(self) -> None:
        """Asserted against a fixture root whose `kind` is `REPOSITORY` --
        an invented name, never a shipped root's own name -- so this can
        never pass by coincidentally matching `FACT_SOURCE_ROOT`'s own
        `implementation`/`results` entries."""
        root = paper_declarations.SourceRoot(
            "invented-non-prose-root", paper_declarations.SourceRootKind.REPOSITORY,
        )
        status = paper_declarations.source_root_status(self.base, root)

        self.assertEqual(paper_declarations.declaration_state(status, root), "n/a")

    def test_a_prose_root_with_no_marker_is_undeclared(self) -> None:
        root = paper_declarations.SourceRoot(
            "invented-prose-root", paper_declarations.SourceRootKind.PROSE,
        )
        (self.base / root.name).mkdir()
        (self.base / root.name / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        status = paper_declarations.source_root_status(self.base, root)

        self.assertEqual(paper_declarations.declaration_state(status, root), "undeclared")

    def test_a_prose_root_with_a_valid_unsealed_marker_is_declared_unsealed(self) -> None:
        root = paper_declarations.SourceRoot(
            "invented-prose-root", paper_declarations.SourceRootKind.PROSE,
        )
        (self.base / root.name).mkdir()
        (self.base / root.name / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        (self.base / root.name / ".paper-writing.json").write_text(
            json.dumps({"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}),
            encoding="utf-8",
        )
        status = paper_declarations.source_root_status(self.base, root)

        self.assertEqual(paper_declarations.declaration_state(status, root), "declared-unsealed")

    def test_a_prose_root_with_a_valid_sealed_marker_is_declared_sealed(self) -> None:
        root = paper_declarations.SourceRoot(
            "invented-prose-root", paper_declarations.SourceRootKind.PROSE,
        )
        (self.base / root.name).mkdir()
        (self.base / root.name / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        obj = {"revisions": {"revision_prefix": "r", "ordinal_digits": 2}}
        obj[paper_marker.SEAL_KEY] = paper_marker.computed_seal(obj)
        (self.base / root.name / ".paper-writing.json").write_text(
            json.dumps(obj), encoding="utf-8",
        )
        status = paper_declarations.source_root_status(self.base, root)

        self.assertEqual(paper_declarations.declaration_state(status, root), "declared-sealed")

    def test_a_prose_root_with_a_hand_edited_sealed_marker_propagates_the_refusal(self) -> None:
        """`Requirement: Absence Is A Reported State; A Broken Seal Refuses
        Where The Marker Is Read` -- never a fifth, silently-swallowed
        declaration_state value."""
        root = paper_declarations.SourceRoot(
            "invented-prose-root", paper_declarations.SourceRootKind.PROSE,
        )
        (self.base / root.name).mkdir()
        (self.base / root.name / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        obj = {
            "revisions": {"revision_prefix": "r", "ordinal_digits": 2},
            paper_marker.SEAL_KEY: "a" * 64,
        }
        (self.base / root.name / ".paper-writing.json").write_text(
            json.dumps(obj), encoding="utf-8",
        )
        status = paper_declarations.source_root_status(self.base, root)

        with self.assertRaises(Refused) as ctx:
            paper_declarations.declaration_state(status, root)
        self.assertEqual(ctx.exception.code, "SOURCE_DECLARATION_HAND_EDITED")

    def test_a_prose_root_that_is_not_a_directory_at_all_is_undeclared(self) -> None:
        """A `PROSE` root whose directory does not exist yet
        (`status["path"]` is `None`) can carry no marker file at all --
        reported `undeclared`, never a crash on a `None` path."""
        root = paper_declarations.SourceRoot(
            "invented-absent-prose-root", paper_declarations.SourceRootKind.PROSE,
        )
        status = paper_declarations.source_root_status(self.base, root)

        self.assertIsNone(status["path"])
        self.assertEqual(paper_declarations.declaration_state(status, root), "undeclared")


class DeclarableSourceRootsTests(unittest.TestCase):
    """design.md Decision J; `specs/source-declaration-authoring/spec.md`,
    `Requirement: Which Roots And Folders Are Declarable Is Derived, Never
    Listed`."""

    def test_declarable_roots_are_exactly_the_prose_kind_roots(self) -> None:
        declarable = paper_declarations.declarable_source_roots()

        self.assertEqual(
            set(declarable),
            {
                root.name
                for root in paper_declarations.FACT_SOURCE_ROOT.values()
                if root.kind is paper_declarations.SourceRootKind.PROSE
            },
        )
        for root in declarable.values():
            self.assertEqual(root.kind, paper_declarations.SourceRootKind.PROSE)

    def test_a_sixth_prose_root_widens_declarability_with_zero_engine_edit(self) -> None:
        """The spec's own mutation scenario: extending `FACT_SOURCE_ROOT`
        with a sixth PROSE-kind fact/root pair (via `patch.dict`, never a
        source edit) makes that root declarable, proving the test is
        membership-by-kind in the mapping, never a hand-maintained list."""
        sixth = paper_declarations.SourceRoot(
            "invented-sixth-prose-root", paper_declarations.SourceRootKind.PROSE,
        )
        with unittest.mock.patch.dict(
            paper_declarations.FACT_SOURCE_ROOT, {"invented-sixth-fact": sixth},
        ):
            declarable = paper_declarations.declarable_source_roots()

            self.assertIn(sixth.name, declarable)
            self.assertEqual(declarable[sixth.name], sixth)


class DeclareRevisionsTests(unittest.TestCase):
    """`specs/source-declaration-authoring/spec.md`, `Requirement: A Source
    Root's Revision Rule Is Recorded And Validated Against Disk By Using
    The Skill`; design.md Decision F -- `declare_revisions`'s own engine,
    independent of the CLI wiring (`MarkRevisionsCliWholeLoopTests` in
    `test_paper_writing.py` proves that end of it)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.experiments = self.base / "experiments"
        self.experiments.mkdir()

    def _marker_path(self) -> Path:
        return self.experiments / ".paper-writing.json"

    def test_a_matching_declaration_is_recorded(self) -> None:
        (self.experiments / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        (self.experiments / "field-survey-r08.md").write_text("# 1\n", encoding="utf-8")

        result = paper_declarations.declare_revisions(self.base, "experiments", "r", 2)

        self.assertEqual(result["root"], "experiments")
        self.assertEqual(
            result["revisions"], {"revision_prefix": "r", "ordinal_digits": 2},
        )
        self.assertEqual(
            sorted(result["matched"]), ["field-survey-r07.md", "field-survey-r08.md"],
        )
        self.assertEqual(result["unmatched"], [])
        self.assertTrue(result["sealed"])
        self.assertTrue(self._marker_path().is_file())

    def test_a_declared_width_matching_nothing_refuses_at_write_time(self) -> None:
        (self.experiments / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        (self.experiments / "field-survey-r08.md").write_text("# 1\n", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.declare_revisions(self.base, "experiments", "v", 3)

        self.assertEqual(ctx.exception.code, "SOURCE_DECLARATION_UNMATCHED")
        self.assertIn("v", ctx.exception.detail)
        self.assertIn("3", ctx.exception.detail)
        self.assertIn("field-survey-r07.md", ctx.exception.detail)
        self.assertIn("field-survey-r08.md", ctx.exception.detail)
        self.assertFalse(self._marker_path().exists())

    def test_a_non_declarable_root_refuses_by_name(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.declare_revisions(self.base, "implementation", "r", 2)

        self.assertEqual(ctx.exception.code, "SOURCE_ROOT_UNDECLARABLE")
        self.assertIn("proposals", ctx.exception.detail)
        self.assertIn("experiments", ctx.exception.detail)
        self.assertIn("repository", ctx.exception.detail)

    def test_a_name_matching_no_known_root_at_all_also_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_declarations.declare_revisions(self.base, "invented-nowhere-root", "r", 2)

        self.assertEqual(ctx.exception.code, "SOURCE_ROOT_UNDECLARABLE")

    def test_ordinal_digits_below_one_refuses_malformed(self) -> None:
        (self.experiments / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_declarations.declare_revisions(self.base, "experiments", "r", 0)

        self.assertEqual(ctx.exception.code, "MALFORMED_SOURCE_MARKER")
        self.assertIn("ordinal_digits", ctx.exception.detail)
        self.assertFalse(self._marker_path().exists())

    def test_a_root_that_is_not_a_directory_folds_into_unmatched(self) -> None:
        """design.md Decision F.3: a root that is not a directory at all
        folds into the SAME `SOURCE_DECLARATION_UNMATCHED` code. Nothing
        creates the directory."""
        shutil.rmtree(self.experiments)

        with self.assertRaises(Refused) as ctx:
            paper_declarations.declare_revisions(self.base, "experiments", "r", 2)

        self.assertEqual(ctx.exception.code, "SOURCE_DECLARATION_UNMATCHED")
        self.assertFalse(self.experiments.exists())

    def test_declare_revisions_never_produces_a_marker_its_own_reader_refuses(self) -> None:
        """The round-trip guarantee (tasks.md 2.10): every accepted write
        is immediately re-readable through `read_revisions_marker`."""
        (self.experiments / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")

        paper_declarations.declare_revisions(self.base, "experiments", "r", 2)

        marker = paper_declarations.read_revisions_marker(self.experiments)
        self.assertEqual(marker["revision_prefix"], "r")
        self.assertEqual(marker["ordinal_digits"], 2)
        self.assertTrue(marker["sealed"])

    def test_unsealed_writes_no_seal_key_shape_identical_to_pre_seal_grammar(self) -> None:
        """tasks.md 2.12: the `--unsealed` marker's shape is IDENTICAL to
        what the pre-change grammar admits -- round-tripped here through a
        hand-built pre-seal validator, never through the sealed-aware
        reader alone."""
        (self.experiments / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")

        result = paper_declarations.declare_revisions(
            self.base, "experiments", "r", 2, sealed=False,
        )

        self.assertFalse(result["sealed"])
        on_disk = json.loads(self._marker_path().read_text(encoding="utf-8"))
        self.assertNotIn(paper_marker.SEAL_KEY, on_disk)
        # A hand-built pre-seal validator: exactly {"revisions": {...}},
        # exactly the two required nested keys -- the grammar an
        # unmodified older reader (one that has never heard of
        # `seal_sha256`) still accepts.
        self.assertEqual(set(on_disk), {"revisions"})
        self.assertEqual(set(on_disk["revisions"]), {"revision_prefix", "ordinal_digits"})

    def test_re_recording_always_succeeds_over_an_existing_sealed_marker(self) -> None:
        (self.experiments / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        paper_declarations.declare_revisions(self.base, "experiments", "r", 2)
        (self.experiments / "field-survey-r08.md").write_text("# 1\n", encoding="utf-8")

        result = paper_declarations.declare_revisions(self.base, "experiments", "r", 2)

        self.assertEqual(sorted(result["matched"]), ["field-survey-r07.md", "field-survey-r08.md"])

    def test_re_recording_over_a_hand_edited_marker_clears_the_defect(self) -> None:
        """No `--reopen`/`--adopt`: re-running the verb is the only exit
        from a hand-edited sealed marker (spec: "Re-Recording Always
        Succeeds; There Is No Stuck State")."""
        (self.experiments / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        obj = {
            "revisions": {"revision_prefix": "r", "ordinal_digits": 2},
            paper_marker.SEAL_KEY: "a" * 64,
        }
        self._marker_path().write_text(json.dumps(obj), encoding="utf-8")

        paper_declarations.declare_revisions(self.base, "experiments", "r", 2)

        marker = paper_declarations.read_revisions_marker(self.experiments)
        self.assertTrue(marker["sealed"])

    def test_mutation_the_zero_match_guard_is_reachable(self) -> None:
        (self.experiments / "field-survey-r07.md").write_text("# 1\n", encoding="utf-8")
        proc = _run_against_mutant(
            "    if not matched:",
            "    if False:",
            "tests.test_paper_decisions.DeclareRevisionsTests"
            ".test_a_declared_width_matching_nothing_refuses_at_write_time",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_the_declarable_membership_check_is_reachable(self) -> None:
        proc = _run_against_mutant(
            "    if root_name not in declarable:",
            "    if False:",
            "tests.test_paper_decisions.DeclareRevisionsTests"
            ".test_a_non_declarable_root_refuses_by_name",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class DeclareClassTests(unittest.TestCase):
    """`specs/guidance-registry/spec.md`; design.md Decision F (guidance
    half) -- `declare_class`'s own engine, the `guidance/` marker's
    sibling to `DeclareRevisionsTests` above, independent of the CLI
    wiring."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.guidance_dir = Path(self._tmp.name) / "guidance"
        self.guidance_dir.mkdir()

    def _marker_path(self, folder: str) -> Path:
        return self.guidance_dir / folder / ".paper-writing.json"

    def _mkfolder(self, name: str) -> None:
        (self.guidance_dir / name).mkdir(parents=True, exist_ok=True)

    def test_a_folder_is_classified_and_recorded(self) -> None:
        self._mkfolder("prior-papers")

        result = paper_guidance.declare_class(self.guidance_dir, "prior-papers", "evidence")

        self.assertEqual(result, {"folder": "prior-papers", "class": "evidence", "sealed": True})
        self.assertTrue(self._marker_path("prior-papers").is_file())

    def test_a_folder_absent_under_guidance_refuses_naming_every_folder_present(self) -> None:
        self._mkfolder("first-folder")
        self._mkfolder("second-folder")

        with self.assertRaises(Refused) as ctx:
            paper_guidance.declare_class(self.guidance_dir, "invented-nowhere-folder", "evidence")

        self.assertEqual(ctx.exception.code, "GUIDANCE_FOLDER_ABSENT")
        self.assertIn("first-folder", ctx.exception.detail)
        self.assertIn("second-folder", ctx.exception.detail)
        self.assertFalse((self.guidance_dir / "invented-nowhere-folder").exists())

    def test_a_class_outside_the_vocabulary_refuses(self) -> None:
        self._mkfolder("prior-papers")

        with self.assertRaises(Refused) as ctx:
            paper_guidance.declare_class(self.guidance_dir, "prior-papers", "reference-material")

        self.assertEqual(ctx.exception.code, "UNKNOWN_GUIDANCE_CLASS")
        self.assertIn("reference-material", ctx.exception.detail)
        self.assertFalse(self._marker_path("prior-papers").exists())

    def test_classing_a_second_evidence_folder_preserves_both_markers(self) -> None:
        self._mkfolder("first-evidence")
        self._mkfolder("second-evidence")
        paper_guidance.declare_class(self.guidance_dir, "first-evidence", "evidence")
        before = self._marker_path("first-evidence").read_bytes()

        paper_guidance.declare_class(self.guidance_dir, "second-evidence", "evidence")

        self.assertEqual(paper_guidance.read_registry(self.guidance_dir), {
            "first-evidence": "evidence", "second-evidence": "evidence",
        })
        self.assertEqual(self._marker_path("first-evidence").read_bytes(), before)

    def test_declare_class_never_produces_a_marker_its_own_reader_refuses(self) -> None:
        self._mkfolder("prior-papers")

        paper_guidance.declare_class(self.guidance_dir, "prior-papers", "style-reference")

        registry = paper_guidance.read_registry(self.guidance_dir)
        self.assertEqual(registry["prior-papers"], "style-reference")

    def test_unsealed_writes_no_seal_key_shape_identical_to_pre_seal_grammar(self) -> None:
        """tasks.md 3.7: mirrors 2.12 for the class marker -- the
        `--unsealed` marker's shape is IDENTICAL to what the pre-change
        grammar admits."""
        self._mkfolder("prior-papers")

        result = paper_guidance.declare_class(
            self.guidance_dir, "prior-papers", "evidence", sealed=False,
        )

        self.assertFalse(result["sealed"])
        on_disk = json.loads(self._marker_path("prior-papers").read_text(encoding="utf-8"))
        self.assertNotIn(paper_marker.SEAL_KEY, on_disk)
        self.assertEqual(set(on_disk), {"class"})

    def test_re_recording_always_succeeds_over_an_existing_sealed_marker(self) -> None:
        self._mkfolder("prior-papers")
        paper_guidance.declare_class(self.guidance_dir, "prior-papers", "evidence")

        result = paper_guidance.declare_class(self.guidance_dir, "prior-papers", "style-reference")

        self.assertEqual(result["class"], "style-reference")

    def test_re_recording_over_a_hand_edited_marker_clears_the_defect(self) -> None:
        """No `--reopen`/`--adopt`: re-running the verb is the only exit
        from a hand-edited sealed class marker (spec: "Re-Recording Always
        Succeeds; There Is No Stuck State", mirrored from the revisions
        marker's own requirement)."""
        self._mkfolder("prior-papers")
        obj = {"class": "evidence", paper_marker.SEAL_KEY: "a" * 64}
        self._marker_path("prior-papers").write_text(json.dumps(obj), encoding="utf-8")

        paper_guidance.declare_class(self.guidance_dir, "prior-papers", "evidence")

        registry = paper_guidance.read_registry(self.guidance_dir)
        self.assertEqual(registry["prior-papers"], "evidence")

    def test_an_evidence_folder_holding_zero_ingested_papers_is_not_refused(self) -> None:
        """design.md Decision F: deliberately not validated -- a class is
        a judgement about a folder, not a measurement of it."""
        self._mkfolder("empty-evidence")

        result = paper_guidance.declare_class(self.guidance_dir, "empty-evidence", "evidence")

        self.assertEqual(result["class"], "evidence")

    def test_re_marking_the_same_folder_evidence_again_is_never_self_ambiguous(self) -> None:
        """Re-recording the SAME folder's own class must never trip the
        ambiguity check against itself."""
        self._mkfolder("prior-papers")
        paper_guidance.declare_class(self.guidance_dir, "prior-papers", "evidence")

        result = paper_guidance.declare_class(self.guidance_dir, "prior-papers", "evidence")

        self.assertEqual(result["class"], "evidence")

    def test_mutation_the_folder_membership_check_is_reachable(self) -> None:
        proc = _run_against_mutant(
            "    if folder not in present:",
            "    if False:",
            "tests.test_paper_decisions.DeclareClassTests"
            ".test_a_folder_absent_under_guidance_refuses_naming_every_folder_present",
            source_path=SKILL_SCRIPTS / "paper_guidance.py",
        )
        _assert_guard_failed_under_mutation(self, proc)



class ReconcileObservationReportTests(unittest.TestCase):
    """`reconcile_observation_report`: the pure comparison `observe`'s new
    disk-truth gate is built on."""

    def test_an_unsatisfied_fact_with_no_evidence_while_its_root_is_available_disagrees(
        self,
    ) -> None:
        """`implementation` AND `results` both map to the `implementation`
        root (`.claude/agents/insumos-observer.md`); `results` is reported
        satisfied here precisely so only `implementation` disagrees."""
        report = {
            "implementation": {"satisfied": False, "evidence": []},
            "results": {"satisfied": True, "evidence": [["out.log", "q"]]},
        }
        measured = {"implementation": True}

        disagreements = paper_declarations.reconcile_observation_report(report, measured)

        self.assertEqual(len(disagreements), 1)
        self.assertEqual(disagreements[0]["fact"], "implementation")
        self.assertEqual(disagreements[0]["source"], "implementation")

    def test_an_unsatisfied_fact_agrees_when_its_root_is_measurably_unavailable(self) -> None:
        report = {
            "implementation": {"satisfied": False, "evidence": []},
            "results": {"satisfied": False, "evidence": []},
        }
        measured = {"implementation": False}

        self.assertEqual(paper_declarations.reconcile_observation_report(report, measured), [])

    def test_a_satisfied_fact_never_disagrees_regardless_of_measurement(self) -> None:
        report = {
            "implementation": {"satisfied": True, "evidence": [["a", "b"]]},
            "results": {"satisfied": True, "evidence": [["c", "d"]]},
        }
        measured = {"implementation": True}

        self.assertEqual(paper_declarations.reconcile_observation_report(report, measured), [])

    def test_an_unmeasured_root_is_never_reconciled_against(self) -> None:
        """`measured` naming nothing for a fact's own root means that root
        was never checked -- never treated as "measured unavailable"."""
        report = {"implementation": {"satisfied": False, "evidence": []}}

        self.assertEqual(paper_declarations.reconcile_observation_report(report, {}), [])

    def test_an_unsatisfied_fact_that_still_carries_evidence_never_disagrees(self) -> None:
        """`evidence` non-empty but `satisfied` false is a real, honest
        report shape (a partial finding the agent judged insufficient) --
        never flagged, since SOME evidence was actually found."""
        report = {
            "implementation": {"satisfied": False, "evidence": [["partial.py", "q"]]},
            "results": {"satisfied": True, "evidence": [["c", "d"]]},
        }
        measured = {"implementation": True}

        self.assertEqual(paper_declarations.reconcile_observation_report(report, measured), [])

    def test_every_fact_is_named_independently_never_averaged_into_one_verdict(self) -> None:
        report = {
            "formulation": {"satisfied": False, "evidence": []},
            "dataset": {"satisfied": True, "evidence": [["p", "q"]]},
        }
        measured = {"proposals": True}

        disagreements = paper_declarations.reconcile_observation_report(report, measured)

        self.assertEqual([d["fact"] for d in disagreements], ["formulation"])


class ReconcileObservationReportMutationTests(unittest.TestCase):
    def test_mutation_dropping_the_no_evidence_check_over_reports_disagreement(self) -> None:
        """Without the `not evidence` half, a fact reported SATISFIED (with
        real evidence) over an available root would also flag as a
        disagreement -- exactly backwards, since a satisfied report
        AGREES with an available source."""
        proc = _run_against_mutant(
            "if not satisfied and not evidence:",
            "if not satisfied:",
            "tests.test_paper_decisions.ReconcileObservationReportTests"
            ".test_an_unsatisfied_fact_that_still_carries_evidence_never_disagrees",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_treating_an_unmeasured_root_as_available_breaks_the_guard(self) -> None:
        proc = _run_against_mutant(
            "if root_name not in measured or not measured[root_name]:",
            "if not measured.get(root_name, True):",
            "tests.test_paper_decisions.ReconcileObservationReportTests"
            ".test_an_unmeasured_root_is_never_reconciled_against",
            source_path=SKILL_SCRIPTS / "paper_declarations.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class ObserveDiskReconciliationTests(unittest.TestCase):
    """`paper_cli.compute_observation`: `observe`'s own end-to-end
    disk-truth reconciliation, injected paths (no argparse defaulting)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.report_path = self.root / "report.json"

    def _write_report(self, obj) -> None:
        self.report_path.write_text(json.dumps(obj), encoding="utf-8")

    def test_the_measured_defect_scenario_now_refuses(self) -> None:
        """The exact scenario the task names: the orchestrator reported the
        implementation repository ABSENT when it was actually populated,
        four times, because `fd`/`rg` honor `.gitignore`."""
        self._write_report({
            "implementation": {"satisfied": False, "evidence": []},
            "results": {"satisfied": False, "evidence": []},
        })
        implementation_dir = self.root / "implementations" / "Domain_Adaptation"
        implementation_dir.mkdir(parents=True)
        (implementation_dir / "train.py").write_text("print(1)", encoding="utf-8")
        (self.root / ".gitignore").write_text("implementations/*\n", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_cli.compute_observation(
                self.report_path, implementation_dir=implementation_dir,
            )

        self.assertEqual(ctx.exception.code, "OBSERVATION_DISK_CONFLICT")
        self.assertIn("implementation", ctx.exception.detail)

    def test_an_honest_absent_report_over_an_empty_root_is_accepted(self) -> None:
        self._write_report({"implementation": {"satisfied": False, "evidence": []}})
        implementation_dir = self.root / "implementations" / "empty-repo"
        implementation_dir.mkdir(parents=True)

        result = paper_cli.compute_observation(self.report_path, implementation_dir=implementation_dir)

        self.assertEqual(result["measured"], {"implementation": False})
        self.assertEqual(result["satisfied"], [])

    def test_no_roots_given_performs_no_reconciliation_at_all(self) -> None:
        """Backward compatible: an `observe` call naming no root reconciles
        against nothing and behaves exactly as before this change."""
        self._write_report({"implementation": {"satisfied": False, "evidence": []}})

        result = paper_cli.compute_observation(self.report_path)

        self.assertEqual(result["measured"], {})

    def test_writes_nothing_including_on_a_disk_conflict_refusal(self) -> None:
        self._write_report({"implementation": {"satisfied": False, "evidence": []}})
        implementation_dir = self.root / "impl"
        implementation_dir.mkdir()
        (implementation_dir / "code.py").write_text("x", encoding="utf-8")
        before = sorted(str(p) for p in self.root.rglob("*"))

        with self.assertRaises(Refused):
            paper_cli.compute_observation(self.report_path, implementation_dir=implementation_dir)

        after = sorted(str(p) for p in self.root.rglob("*"))
        self.assertEqual(before, after)


class ObserveCliTests(unittest.TestCase):
    """`paper_cli.cmd_observe`: the CLI front door, real, non-injectable
    `FORGE_ROOT` defaults for `--proposals`/`--experiments`, path
    containment for all three flags -- same `implementations/` convention
    `SkeletonPathContainmentTests` (`tests/test_paper_writing.py`) uses."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / "implementations"
            / f".paper-writing-observe-cli-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.test_root.mkdir(parents=True)

    def _args(self, **overrides) -> argparse.Namespace:
        base = dict(report=None, proposals=None, experiments=None, implementation=None)
        base.update(overrides)
        return argparse.Namespace(**base)

    def _write_report(self, obj) -> Path:
        path = self.test_root / "report.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def test_an_implementation_path_outside_the_repository_refuses_containment(self) -> None:
        report_path = self._write_report({"implementation": {"satisfied": False, "evidence": []}})
        outside = Path(tempfile.gettempdir()) / f"paper-writing-observe-outside-{os.getpid()}"

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_observe(self._args(report=str(report_path), implementation=str(outside)))

        self.assertEqual(ctx.exception.code, "PAPER_OUTSIDE_REPOSITORY")

    def test_an_implementation_path_inside_the_repository_reconciles_against_it(self) -> None:
        report_path = self._write_report({"implementation": {"satisfied": False, "evidence": []}})
        implementation_dir = self.test_root / "impl"
        implementation_dir.mkdir()
        (implementation_dir / "main.py").write_text("x", encoding="utf-8")

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_observe(
                self._args(report=str(report_path), implementation=str(implementation_dir)),
            )

        self.assertEqual(ctx.exception.code, "OBSERVATION_DISK_CONFLICT")

    def test_omitting_implementation_skips_that_reconciliation(self) -> None:
        report_path = self._write_report({"implementation": {"satisfied": False, "evidence": []}})

        result = paper_cli.cmd_observe(self._args(report=str(report_path)))

        self.assertNotIn("implementation", result["measured"])


class CouplingsShapeValidationTests(unittest.TestCase):
    """`the-skill-stops-trusting-memory`, item 4: `paper_couplings.
    validate_couplings_shape` -- the floor every real `paper_verify.py`
    check reads, checked at WRITE time rather than surfacing later as a
    confusing `unmeasured`."""

    def test_a_non_object_record_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_couplings.validate_couplings_shape([1, 2, 3])
        self.assertEqual(ctx.exception.code, "COUPLINGS_RECORD_MALFORMED")

    def test_a_record_with_no_blocks_key_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_couplings.validate_couplings_shape({"facts": {}})
        self.assertEqual(ctx.exception.code, "COUPLINGS_RECORD_MALFORMED")

    def test_a_record_with_an_empty_blocks_object_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_couplings.validate_couplings_shape({"blocks": {}})
        self.assertEqual(ctx.exception.code, "COUPLINGS_RECORD_MALFORMED")

    def test_a_minimal_valid_record_is_accepted(self) -> None:
        paper_couplings.validate_couplings_shape({"blocks": {"a": {}}})

    def test_contributions_that_is_not_a_list_of_strings_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_couplings.validate_couplings_shape(
                {"blocks": {"a": {}}, "facts": {"contributions": "not-a-list"}}
            )
        self.assertEqual(ctx.exception.code, "COUPLINGS_RECORD_MALFORMED")

    def test_a_chain_link_missing_word_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_couplings.validate_couplings_shape(
                {"blocks": {"a": {}}, "chain": {"links": [{"not_word": "x"}]}}
            )
        self.assertEqual(ctx.exception.code, "COUPLINGS_RECORD_MALFORMED")

    def test_artefact_cells_that_are_not_strings_refuse(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_couplings.validate_couplings_shape(
                {"blocks": {"a": {}}, "artefacts": {"setup_cells": [1, 2]}}
            )
        self.assertEqual(ctx.exception.code, "COUPLINGS_RECORD_MALFORMED")

    def test_a_future_work_direction_missing_a_required_key_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_couplings.validate_couplings_shape(
                {
                    "blocks": {"a": {}},
                    "future_work": {"directions": [{"id": "d1", "limitation": "L1"}]},
                }
            )
        self.assertEqual(ctx.exception.code, "COUPLINGS_RECORD_MALFORMED")

    def test_a_fully_populated_record_is_accepted(self) -> None:
        paper_couplings.validate_couplings_shape({
            "blocks": {"a": {}, "b": {}},
            "facts": {"contributions": ["x", "y"], "limitations": ["L1"]},
            "chain": {"links": [{"word": "x"}]},
            "artefacts": {"setup_cells": ["c1"], "results_artefacts": ["c1"]},
            "future_work": {
                "directions": [{"id": "d1", "limitation": "L1", "cite_key": "smith2024"}],
            },
        })


class CouplingsProducerTests(unittest.TestCase):
    """`couplings` writes `paper/couplings.json` whole, atomically -- the
    producer `verify` never had. `DECLARATION_RECORD_ABSENT` refuses before
    this change; it must stop refusing once `couplings` has written a
    minimally valid record, with no other change to `verify` itself."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def test_write_couplings_creates_the_file_with_the_given_content(self) -> None:
        result = paper_couplings.write_couplings(self.paper_dir, {"blocks": {"intro.b1": {}}})

        path = self.paper_dir / paper_coupling_evidence.COUPLINGS_RECORD_NAME
        self.assertTrue(path.is_file())
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"blocks": {"intro.b1": {}}})
        self.assertEqual(result["blocks"], ["intro.b1"])

    def test_write_couplings_rejects_a_malformed_record_and_writes_nothing(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_couplings.write_couplings(self.paper_dir, {"blocks": {}})

        self.assertEqual(ctx.exception.code, "COUPLINGS_RECORD_MALFORMED")
        self.assertFalse((self.paper_dir / paper_coupling_evidence.COUPLINGS_RECORD_NAME).exists())

    def test_write_couplings_rebuilds_whole_never_merges_with_a_prior_write(self) -> None:
        paper_couplings.write_couplings(self.paper_dir, {"blocks": {"a": {}}, "facts": {"contributions": ["x"]}})

        paper_couplings.write_couplings(self.paper_dir, {"blocks": {"b": {}}})

        path = self.paper_dir / paper_coupling_evidence.COUPLINGS_RECORD_NAME
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"blocks": {"b": {}}})

    def test_verify_refuses_declaration_record_absent_before_couplings_runs(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)
        self.assertEqual(ctx.exception.code, "DECLARATION_RECORD_ABSENT")

    def test_verify_stops_refusing_declaration_record_absent_once_couplings_has_run(self) -> None:
        """The end-to-end proof item 4 exists for: `verify`, a shipped verb
        with seven checks, could not be run at all on a real paper before
        this change. It can now, with zero changes to `verify`/`paper_
        coupling_evidence.py` themselves."""
        paper_couplings.write_couplings(self.paper_dir, {"blocks": {"intro.b1": {}}})

        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

        self.assertEqual(evidence.record, {"blocks": {"intro.b1": {}}})


class CouplingsCliTests(unittest.TestCase):
    """`paper_cli.cmd_couplings`: the `--file <path|->` front door, and its
    own path-containment/JSON-readability refusals."""

    def setUp(self) -> None:
        self.test_root = (
            FORGE_ROOT / "implementations"
            / f".paper-writing-couplings-cli-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)

    def _write_input(self, text: str) -> Path:
        path = self.test_root / "couplings-input.json"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_valid_file_is_written_to_paper_couplings_json(self) -> None:
        input_path = self._write_input(json.dumps({"blocks": {"a": {}}}))
        args = argparse.Namespace(paper=str(self.paper_dir), file=str(input_path))

        result = paper_cli.cmd_couplings(args)

        self.assertEqual(result["blocks"], ["a"])
        written = self.paper_dir / paper_coupling_evidence.COUPLINGS_RECORD_NAME
        self.assertEqual(json.loads(written.read_text(encoding="utf-8")), {"blocks": {"a": {}}})

    def test_invalid_json_refuses_input_unreadable_and_writes_nothing(self) -> None:
        input_path = self._write_input("{not-json")
        args = argparse.Namespace(paper=str(self.paper_dir), file=str(input_path))

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_couplings(args)

        self.assertEqual(ctx.exception.code, "COUPLINGS_INPUT_UNREADABLE")
        self.assertFalse((self.paper_dir / paper_coupling_evidence.COUPLINGS_RECORD_NAME).exists())

    def test_a_missing_file_refuses_input_unreadable(self) -> None:
        args = argparse.Namespace(
            paper=str(self.paper_dir), file=str(self.test_root / "does-not-exist.json"),
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_couplings(args)

        self.assertEqual(ctx.exception.code, "COUPLINGS_INPUT_UNREADABLE")

    def test_a_file_outside_the_repository_refuses_path_containment(self) -> None:
        outside = Path(tempfile.gettempdir()) / f"paper-writing-couplings-outside-{os.getpid()}.json"
        outside.write_text(json.dumps({"blocks": {"a": {}}}), encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        args = argparse.Namespace(paper=str(self.paper_dir), file=str(outside))

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_couplings(args)

        self.assertEqual(ctx.exception.code, "PAPER_OUTSIDE_REPOSITORY")


class PlaceCliFrontDoorTests(unittest.TestCase):
    """`place`: `paper_cli.cmd_place`, the CLI front door -- `paper_figure.
    place_figure` itself carries three tests in `tests/test_paper_figure.py`
    (`PlacementVerbTests`), every one calling `place_figure` directly with
    positional arguments the test builds itself. None of them exercises
    `cmd_place`'s OWN wiring: `args.paper` -> `resolve_paper_dir`, then
    `args.figure_id`/`args.pdf`/`args.provenance` threaded into `place_
    figure`'s four positional parameters, in that order. The same
    thin-reference shape `order` shipped with before `OrderCliFrontDoorTests`
    (`tests/test_paper_contract.py`) -- the FUNCTION was covered, the VERB
    was not."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.test_root = (
            FORGE_ROOT / "implementations"
            / f".paper-writing-place-cli-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)
        self.paper_dir = self.test_root / "paper"
        paper_scaffold.scaffold(self.paper_dir)

    def _sources(self) -> tuple[Path, Path]:
        tmp_dir = Path(self._tmp.name)
        pdf_source = tmp_dir / "measured.pdf"
        pdf_source.write_bytes(b"%PDF-1.4 cli-front-door\n")
        provenance_source = tmp_dir / "provenance.json"
        provenance_source.write_text(json.dumps({"run": "campaign-cli-1"}), encoding="utf-8")
        return pdf_source, provenance_source

    def test_cmd_place_writes_the_pdf_and_returns_the_json_envelope(self) -> None:
        pdf_source, provenance_source = self._sources()
        args = argparse.Namespace(
            paper=str(self.paper_dir), figure_id="cli-fig",
            pdf=str(pdf_source), provenance=str(provenance_source),
        )

        result = paper_cli.cmd_place(args)

        self.assertEqual(result["figureId"], "cli-fig")
        self.assertEqual(Path(result["pdf"]).read_bytes(), b"%PDF-1.4 cli-front-door\n")
        self.assertEqual(
            json.loads(Path(result["provenance"]).read_text(encoding="utf-8"))["run"],
            "campaign-cli-1",
        )

    def test_cmd_place_propagates_diagram_source_absent_for_a_missing_pdf(self) -> None:
        _pdf_source, provenance_source = self._sources()
        args = argparse.Namespace(
            paper=str(self.paper_dir), figure_id="cli-fig",
            pdf=str(Path(self._tmp.name) / "does-not-exist.pdf"), provenance=str(provenance_source),
        )

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_place(args)

        self.assertEqual(ctx.exception.code, "DIAGRAM_SOURCE_ABSENT")

    def test_mutation_swapping_cmd_places_own_attribute_name_fails_its_front_door_test(
        self,
    ) -> None:
        """RED-first, deliberate mutation: `place_figure`'s three existing
        tests (`test_paper_figure.PlacementVerbTests`) call it directly
        with positional arguments they build themselves -- none of them
        would ever notice `cmd_place` reading the wrong argparse attribute
        off `args`, because none of them go through `cmd_place` at all.
        Mutating `args.figure_id` to `args.figureId` inside `cmd_place`
        itself proves THIS test's own `Namespace(figure_id=...)` call is
        what catches it: `AttributeError`, surfaced through `_run_against_
        mutant` as a failing dotted test, never a clean run."""
        proc = _run_against_mutant(
            "paper_dir, args.figure_id, Path(args.pdf), Path(args.provenance),",
            "paper_dir, args.figureId, Path(args.pdf), Path(args.provenance),",
            "tests.test_paper_decisions.PlaceCliFrontDoorTests"
            ".test_cmd_place_writes_the_pdf_and_returns_the_json_envelope",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


class CouplingsMutationTests(unittest.TestCase):
    """Proves the write-before-validate ordering and the malformed-shape
    guard are both load-bearing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)

    def test_mutation_skipping_validation_before_write_lets_a_malformed_record_through(
        self,
    ) -> None:
        proc = _run_against_mutant(
            "    validate_couplings_shape(record)\n"
            "    path = paper_dir / paper_coupling_evidence.COUPLINGS_RECORD_NAME",
            "    path = paper_dir / paper_coupling_evidence.COUPLINGS_RECORD_NAME",
            "tests.test_paper_decisions.CouplingsProducerTests"
            ".test_write_couplings_rejects_a_malformed_record_and_writes_nothing",
            source_path=SKILL_SCRIPTS / "paper_couplings.py",
        )
        _assert_guard_failed_under_mutation(self, proc)

    def test_mutation_accepting_an_empty_blocks_object_breaks_the_shape_guard(self) -> None:
        proc = _run_against_mutant(
            'if not isinstance(blocks, dict) or not blocks:',
            'if not isinstance(blocks, dict):',
            "tests.test_paper_decisions.CouplingsShapeValidationTests"
            ".test_a_record_with_an_empty_blocks_object_refuses",
            source_path=SKILL_SCRIPTS / "paper_couplings.py",
        )
        _assert_guard_failed_under_mutation(self, proc)


#: Item 2 (`every-verb-has-a-door-test`): the naming convention measured
#: over `paper_cli.REFUSAL_CLASSIFICATION`'s own live 127-code roster is
#: SUBJECT-FIRST -- the domain noun leads, the condition word trails
#: (`ANCHOR_ABSENT`, `CONTRACT_HEADER_ABSENT`, `BLOCK_HAND_EDITED`). This
#: is the pinned, dated, MEASURED minority that does not: every one of
#: these 18 codes was read off the live roster on 2026-09-19 (`paper_cli.
#: REFUSAL_CLASSIFICATION` held exactly 127 keys at the time), never
#: guessed from the code's name alone -- the same discipline `REFUSAL_
#: CLASSIFICATION` itself holds every reachable code to. `MALFORMED_
#: SOURCE_MARKER` was pinned separately on 2026-09-19, added by `the-
#: requirement-names-the-section-that-feeds-it` U1+U2 (roster moved 133 ->
#: 138) — design.md's own words: "qualifier-led, which the measured roster
#: admits for exactly this family: the three existing `MALFORMED_*` codes
#: are all shape checks, and so is this."
#:
#: - `CITE_WITHOUT_ENTRY`, `ENTRY_WITHOUT_CITE`: an opposite-direction PAIR
#:   naming the same relational condition (a `\\cite{}` key with no bib
#:   entry, and a bib entry with no `\\cite{}` key). Whichever side is
#:   read as "the subject", the other necessarily inverts -- there is no
#:   subject-first choice that holds for BOTH members of a `WITHOUT` pair
#:   at once, which is exactly why a mechanical rule cannot resolve this
#:   pair on its own (see the class docstring below).
#: - `EXCLUDED_COMPONENT`: the predicate `EXCLUDED` leads; `COMPONENT` (the
#:   subject) trails.
#: - `SHARED_COMPONENT`: the predicate `SHARED` leads; `COMPONENT` trails.
#: - `MALFORMED_FIGURE_OBLIGATION`, `MALFORMED_GUIDANCE_MARKER`,
#:   `MALFORMED_HEADER`, `MALFORMED_SOURCE_MARKER`: the predicate
#:   `MALFORMED` leads. Contrast the six OTHER shipped codes where
#:   `MALFORMED` correctly TRAILS a leading subject and need no pin:
#:   `MARKER_MALFORMED`, `REGION_MALFORMED`, `CONDITION_MALFORMED`,
#:   `COUPLINGS_RECORD_MALFORMED`, `CITE_KEY_MALFORMED`, `BLOCK_ID_
#:   MALFORMED` -- the same WORD is subject-first in six codes and
#:   predicate-first in these four, which is exactly why this guard pins
#:   CODE NAMES, never a word-anywhere-in-the-code rule.
#: - `NOT_AN_OBSERVABLE_FACT`: the negation `NOT` leads with no subject
#:   noun ahead of it at all (contrast the many codes where `NOT` trails
#:   the subject correctly, e.g. `ENTRY_NOT_INGESTED`, `PHASE_NOT_READY`).
#: - `NOTHING_TO_ADOPT`: the quantifier `NOTHING` leads an infinitive
#:   ("nothing to adopt"), naming no domain noun as its subject at all --
#:   the only shipped code shaped this way.
#: - `UNBOUND_SENTENCE`: the predicate `UNBOUND` leads; `SENTENCE` (the
#:   subject) trails.
#: - `UNKNOWN_CITATIONS_REGIME`, `UNKNOWN_CONDITION_TYPE`, `UNKNOWN_
#:   DECLARATION`, `UNKNOWN_FACT`, `UNKNOWN_GUIDANCE_CLASS`, `UNKNOWN_
#:   MODE`, `UNKNOWN_ROLE`, `UNKNOWN_VERDICT`: the predicate `UNKNOWN`
#:   leads in all eight -- NOT part of the task brief's own seed list, a
#:   gap this item's own re-measurement of the live roster found. Contrast
#:   `VERDICT_BULLET_UNKNOWN`, where `UNKNOWN` correctly TRAILS and needs
#:   no pin -- the same word, subject-first there, predicate-first here.
_SUBJECT_FIRST_EXCEPTIONS = frozenset({
    "CITE_WITHOUT_ENTRY", "ENTRY_WITHOUT_CITE",
    "EXCLUDED_COMPONENT", "SHARED_COMPONENT",
    "MALFORMED_FIGURE_OBLIGATION", "MALFORMED_GUIDANCE_MARKER", "MALFORMED_HEADER",
    "MALFORMED_SOURCE_MARKER",
    "NOT_AN_OBSERVABLE_FACT", "NOTHING_TO_ADOPT", "UNBOUND_SENTENCE",
    "UNKNOWN_CITATIONS_REGIME", "UNKNOWN_CONDITION_TYPE", "UNKNOWN_DECLARATION",
    "UNKNOWN_FACT", "UNKNOWN_GUIDANCE_CLASS", "UNKNOWN_MODE", "UNKNOWN_ROLE",
    "UNKNOWN_VERDICT",
})


def _leading_token(code: str) -> str:
    return code.split("_", 1)[0]


#: Derived from `_SUBJECT_FIRST_EXCEPTIONS` itself -- never a second,
#: independently hand-kept vocabulary -- by taking each pinned exception's
#: own leading token. `CITE`/`ENTRY` are dropped: both also lead perfectly
#: good subject-first codes elsewhere (`CITE_KEY_MALFORMED`, `ENTRY_NOT_
#: INGESTED`, `ENTRY_UNSOURCED`), so "first token is CITE/ENTRY" is not a
#: predicate signal at all -- only the specific `..._WITHOUT_..` PAIR is,
#: and a pair is not detectable from one token in isolation. This is the
#: mechanism `test_a_new_code_reusing_an_attested_leading_marker_is_caught_
#: unpinned` below proves fires.
_LEADING_PREDICATE_MARKERS = frozenset(
    _leading_token(code) for code in _SUBJECT_FIRST_EXCEPTIONS
) - {"CITE", "ENTRY"}


class RefusalCodeNamingConventionTests(unittest.TestCase):
    """Item 2 (`every-verb-has-a-door-test`): `sdd-spec` and `sdd-design`
    invented COMPETING names for the same five conditions when they ran in
    parallel (`CHAIN_ROW_UNRESOLVED` vs `UNMAPPED_CHAIN_ROW`, `PHASE_NOT_
    READY` vs `PHASE_GATED`, three more), reconciled by hand against the
    live roster's own measured convention: SUBJECT-FIRST, the domain noun
    leads and the condition word trails.

    BE HONEST about what this class can and cannot mechanically decide.
    Telling a subject from a predicate is a judgment about ENGLISH
    MEANING, not a syntactic property of an identifier -- no rule over the
    bare string `"UNKNOWN_MODE"` can derive that `UNKNOWN` is a predicate
    and `MODE` is its subject; that reading was made by a person (here,
    the agent doing this measurement) and then PINNED, exactly the way
    `paper_cli.REFUSAL_CLASSIFICATION` pins every code's invocation-defect/
    work-state reading rather than inferring it from the code's spelling.

    What IS mechanically checkable, and what this class actually checks:
    a code's LEADING token, compared against `_LEADING_PREDICATE_MARKERS`
    -- the leading tokens of every ALREADY-PINNED exception (`UNKNOWN`,
    `MALFORMED`, `NOT`, `EXCLUDED`, `SHARED`, `NOTHING`, `UNBOUND`). A code
    outside `_SUBJECT_FIRST_EXCEPTIONS` whose leading token reuses one of
    these markers is a NEW instance of an ALREADY-SEEN violating shape
    (e.g. a hypothetical `UNKNOWN_RESOLVER_ID` reusing the same `UNKNOWN`-
    leads pattern eight existing codes already use) -- that much a rule
    genuinely catches, proven by
    `test_a_new_code_reusing_an_attested_leading_marker_is_caught_unpinned`
    below by injecting exactly such a name and confirming it is reported.

    What this class CANNOT catch, and does not pretend to: a genuinely
    NOVEL leading word this roster has never used as a predicate before
    (nothing here would flag a hypothetical `ORPHANED_BLOCK` on its first
    appearance, since `ORPHANED` matches no attested marker yet -- only a
    human reading `REFUSAL_CLASSIFICATION`'s diff can catch that, the same
    way only a human decided `UNKNOWN_MODE` belongs on this pinned list in
    the first place). Nor can it resolve an opposite-direction PAIR like
    `CITE_WITHOUT_ENTRY`/`ENTRY_WITHOUT_CITE`, where neither member's
    leading token is inherently a predicate -- both are pinned by name,
    not caught by the marker rule at all. This class is a drift guard over
    an ALREADY-SEEN violating shape, never a general subject/predicate
    parser -- exactly the boundary the task brief asked to be honest
    about."""

    def test_the_pinned_exceptions_still_exist_in_the_live_roster(self) -> None:
        stray = sorted(_SUBJECT_FIRST_EXCEPTIONS - set(paper_cli.REFUSAL_CLASSIFICATION))
        self.assertEqual(
            stray, [],
            f"{stray} are pinned as naming exceptions but paper_cli.py's own "
            "REFUSAL_CLASSIFICATION no longer ships them -- a removed code's pin "
            "must be removed with it")

    def test_no_live_code_outside_the_pinned_exceptions_reuses_an_attested_leading_marker(
        self,
    ) -> None:
        codes = set(paper_cli.REFUSAL_CLASSIFICATION)
        violators = sorted(
            code for code in codes - _SUBJECT_FIRST_EXCEPTIONS
            if _leading_token(code) in _LEADING_PREDICATE_MARKERS
        )
        self.assertEqual(
            violators, [],
            f"{violators} lead with an already-attested predicate marker "
            f"({sorted(_LEADING_PREDICATE_MARKERS)}) and are not in "
            "_SUBJECT_FIRST_EXCEPTIONS -- either rename to subject-first, or pin "
            "the exception deliberately with a dated, measured reason, the way "
            "every existing entry there is pinned")

    def test_a_new_code_reusing_an_attested_leading_marker_is_caught_unpinned(self) -> None:
        """RED-first, synthetic injection: `paper_cli.REFUSAL_CLASSIFICATION`
        is never mutated for this (it is real production state another
        agent owns) -- instead, this reproduces
        `test_no_live_code_outside_the_pinned_exceptions_reuses_an_
        attested_leading_marker`'s own check against the live roster PLUS
        one synthetic, deliberately unpinned, `UNKNOWN`-leading code, and
        confirms that ONE code -- and only that one -- is reported."""
        codes = set(paper_cli.REFUSAL_CLASSIFICATION) | {"UNKNOWN_RESOLVER_ID_TEST_ONLY"}
        violators = sorted(
            code for code in codes - _SUBJECT_FIRST_EXCEPTIONS
            if _leading_token(code) in _LEADING_PREDICATE_MARKERS
        )
        self.assertEqual(violators, ["UNKNOWN_RESOLVER_ID_TEST_ONLY"])

    def test_the_marker_set_excludes_cite_and_entry_so_their_own_dominant_codes_pass(
        self,
    ) -> None:
        """Proof the `CITE`/`ENTRY` carve-out in `_LEADING_PREDICATE_
        MARKERS` is load-bearing: without it, `CITE_KEY_MALFORMED`, `ENTRY_
        NOT_INGESTED` and `ENTRY_UNSOURCED` -- three real, correctly
        subject-first shipped codes -- would be reported as violators
        purely for sharing a first word with the `..._WITHOUT_...` pair,
        which is exactly the false positive this carve-out exists to
        prevent."""
        self.assertNotIn("CITE", _LEADING_PREDICATE_MARKERS)
        self.assertNotIn("ENTRY", _LEADING_PREDICATE_MARKERS)
        for dominant_code in ("CITE_KEY_MALFORMED", "ENTRY_NOT_INGESTED", "ENTRY_UNSOURCED"):
            self.assertIn(dominant_code, paper_cli.REFUSAL_CLASSIFICATION)
            self.assertNotIn(_leading_token(dominant_code), _LEADING_PREDICATE_MARKERS)


if __name__ == "__main__":
    unittest.main()


class LifecycleCliFrontDoorTests(unittest.TestCase):
    """`reuse` and `exhaustion` exercised through `paper_cli`'s own command
    functions -- the door a caller actually goes through -- not through
    `paper_lifecycle`'s pure functions, which their own suite already covers.

    These exist because `VerbFrontDoorCoverageTests` went RED the moment
    these two verbs merged in from another branch: that guard derives the
    shipped verb list from `build_parser()` live, so it noticed two new
    doors nobody had knocked on without any human remembering to update a
    list. This is the guard working, and these are its answer.
    """

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="lifecycle-front-door-", dir=FORGE_ROOT))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper = self.root / "paper"
        self.paper.mkdir()
        (self.paper / "main.tex").write_bytes(b"")
        self.guidance = self.root / "guidance"
        self.guidance.mkdir()

    def _args(self, **extra) -> argparse.Namespace:
        base = {"paper": str(self.paper), "guidance": str(self.guidance),
                "min_sources": None}
        base.update(extra)
        return argparse.Namespace(**base)

    def test_reuse_returns_its_envelope_through_the_command_function(self) -> None:
        payload = paper_cli.cmd_reuse(self._args(block="intro.claim"))
        self.assertIsInstance(payload, dict)
        self.assertNotIn("status", payload,
                         "cmd_* returns the body; `main` adds `status` itself")

    def test_exhaustion_returns_its_envelope_through_the_command_function(self) -> None:
        payload = paper_cli.cmd_exhaustion(self._args())
        self.assertIsInstance(payload, dict)

    def test_both_refuse_outside_the_repository_before_reading_anything(self) -> None:
        """Path containment is the one guard that must fire before either
        report touches disk -- the same `PAPER_OUTSIDE_REPOSITORY` every
        other verb raises, reused, never a second code for one condition."""
        outside = argparse.Namespace(paper="/tmp/not-in-this-repo",
                                     guidance=str(self.guidance),
                                     min_sources=None, block="intro.claim")
        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_reuse(outside)
        self.assertEqual(ctx.exception.code, "PAPER_OUTSIDE_REPOSITORY")
