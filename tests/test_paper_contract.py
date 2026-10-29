"""the-contract-is-data-not-code: vocabulary, header schema, insertion into the
ten shipped contracts, block graph, readiness and order.

Stdlib-only `unittest`, the same shape `tests/test_paper_writing.py` already
uses for this skill: every fixture lives under a `TemporaryDirectory`, and the
only calls touching the real repository are the ones that MUST — reading the
ten shipped `sections/*.md` files and their `git show HEAD:` digests, and the
insertion + mutation subprocesses, each of which restores or never writes to
the real tree outside what the work unit itself is proving.

One class per concern, no class name reused — `design.md`, `Testing Strategy`.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
SECTIONS_DIR = FORGE_ROOT / "sections"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_vocabulary  # noqa: E402
import paper_contract  # noqa: E402
import paper_graph  # noqa: E402
import paper_readiness  # noqa: E402
import paper_cli  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

# The forge's vocabulary floor, defined in one place beside the suites --
# the same import shape `tests/test_skill_audit.py` and
# `tests/test_proposal_implementation.py` already use.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import forge_vocabulary  # noqa: E402
from paper_mutation import _run_against_mutant  # noqa: E402


def _assert_mutant_test_failed(case: unittest.TestCase, proc) -> None:
    """Shared two-part assertion every `_run_against_mutant` proof in this
    suite uses: `MUTANT_IMPORTED_OK` proves the mutant module actually
    loaded and `unittest` actually ran the named test against it, and a
    non-zero exit proves the guard genuinely failed rather than the
    process crashing on import before the test ever ran. A local copy --
    `tests/test_paper_decisions.py` keeps its own -- since these are two
    independent suites on purpose (design.md, `File Changes`)."""
    output = proc.stdout + proc.stderr
    case.assertIn("MUTANT_IMPORTED_OK", output, output)
    case.assertNotEqual(proc.returncode, 0, output)


def _header_bytes(header: dict) -> bytes:
    return b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\n"


def _minimal_header(**overrides) -> dict:
    header = {
        "section": "example",
        "position": 1,
        "blocks": [
            {
                "id": "only-block",
                "requires_facts": [],
                "requires_declarations": [],
                "citations": "none",
            }
        ],
    }
    header.update(overrides)
    return header


class VocabularyTests(unittest.TestCase):
    """`section-contract` spec: the three closed vocabularies, each derived
    from one declaration so an unclassified value goes red rather than
    silent."""

    def test_a_listed_fact_parses(self) -> None:
        paper_vocabulary.validate_fact("results")  # raises nothing

    def test_every_declared_fact_id_is_accepted(self) -> None:
        for fact in paper_vocabulary.FACTS:
            paper_vocabulary.validate_fact(fact)  # raises nothing

    def test_an_unlisted_fact_refuses_unknown_fact(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_vocabulary.validate_fact("discussion")

        self.assertEqual(ctx.exception.code, "UNKNOWN_FACT")
        self.assertIn("discussion", ctx.exception.detail)

    def test_a_listed_declaration_parses(self) -> None:
        paper_vocabulary.validate_declaration("author-roles")  # raises nothing

    def test_every_declared_declaration_id_is_accepted(self) -> None:
        for declaration in paper_vocabulary.DECLARATIONS:
            paper_vocabulary.validate_declaration(declaration)  # raises nothing

    def test_an_unlisted_declaration_refuses_unknown_declaration(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_vocabulary.validate_declaration("reviewer-name")

        self.assertEqual(ctx.exception.code, "UNKNOWN_DECLARATION")
        self.assertIn("reviewer-name", ctx.exception.detail)

    def test_a_valid_citations_regime_parses(self) -> None:
        paper_vocabulary.validate_citations("discovery")  # raises nothing

    def test_every_declared_citations_regime_is_accepted(self) -> None:
        for regime in paper_vocabulary.CITATIONS_REGIMES:
            paper_vocabulary.validate_citations(regime)  # raises nothing

    def test_an_invalid_citations_regime_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_vocabulary.validate_citations("maybe")

        self.assertEqual(ctx.exception.code, "UNKNOWN_CITATIONS_REGIME")
        self.assertIn("maybe", ctx.exception.detail)

    def test_the_three_vocabularies_are_closed_tuples_with_no_overlap(self) -> None:
        # Own decision (design.md, `paper_vocabulary.py`): "three closed
        # tuples, no I/O, no state" -- proven here rather than merely
        # documented.
        self.assertIsInstance(paper_vocabulary.FACTS, tuple)
        self.assertIsInstance(paper_vocabulary.DECLARATIONS, tuple)
        self.assertIsInstance(paper_vocabulary.CITATIONS_REGIMES, tuple)
        self.assertEqual(len(paper_vocabulary.FACTS), 10)
        self.assertEqual(len(paper_vocabulary.DECLARATIONS), 6)
        self.assertEqual(len(paper_vocabulary.CITATIONS_REGIMES), 3)
        self.assertEqual(
            set(paper_vocabulary.FACTS) & set(paper_vocabulary.DECLARATIONS), set()
        )


class SchemaTests(unittest.TestCase):
    """`section-contract` spec: the front-matter schema, `MALFORMED_HEADER`,
    and the `--sections` repository boundary."""

    def test_valid_header_parses_with_no_refusal(self) -> None:
        rich_entry = {
            "value": "results",
            "source": {"file": "results.md", "quote": "The results themselves."},
        }
        header = _minimal_header(
            blocks=[
                {
                    "id": "results-block",
                    "requires_facts": [rich_entry],
                    "requires_declarations": [],
                    "citations": "discovery",
                }
            ]
        )
        parsed, body = paper_contract.parse(_header_bytes(header) + b"Prose.\n")

        self.assertEqual(parsed.section, "example")
        self.assertEqual(parsed.position, 1)
        self.assertEqual(len(parsed.blocks), 1)
        self.assertEqual(parsed.blocks[0]["id"], "results-block")
        self.assertEqual(
            parsed.blocks[0]["requires_facts"],
            [rich_entry],
            "U3: bare-string acceptance is gone; a rich entry parses to its own "
            "shape unchanged -- this is a shape-only check, the corpus-wide quote "
            "gate lives in paper_graph.assemble_corpus",
        )
        self.assertEqual(body, b"Prose.\n")

    def test_header_missing_position_refuses_naming_position(self) -> None:
        header = _minimal_header()
        del header["position"]

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("position", ctx.exception.detail)

    def test_header_missing_section_refuses_naming_section(self) -> None:
        header = _minimal_header()
        del header["section"]

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("section", ctx.exception.detail)

    def test_header_missing_blocks_refuses_naming_blocks(self) -> None:
        header = _minimal_header()
        del header["blocks"]

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("blocks", ctx.exception.detail)

    def test_header_with_unknown_top_level_key_refuses(self) -> None:
        header = _minimal_header(reviewer="someone")

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("reviewer", ctx.exception.detail)

    def test_block_missing_requires_facts_refuses_naming_it(self) -> None:
        header = _minimal_header(
            blocks=[{"id": "b", "requires_declarations": [], "citations": "none"}]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("requires_facts", ctx.exception.detail)

    def test_block_with_unknown_key_refuses(self) -> None:
        header = _minimal_header(
            blocks=[
                {
                    "id": "b",
                    "requires_facts": [],
                    "requires_declarations": [],
                    "citations": "none",
                    "reviewer": "someone",
                }
            ]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("reviewer", ctx.exception.detail)

    def test_block_declaring_an_unknown_fact_refuses_unknown_fact(self) -> None:
        header = _minimal_header(
            blocks=[
                {
                    "id": "b",
                    "requires_facts": [
                        {
                            "value": "discussion",
                            "source": {"file": "b.md", "quote": "The discussion."},
                        }
                    ],
                    "requires_declarations": [],
                    "citations": "none",
                }
            ]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "UNKNOWN_FACT")
        self.assertIn("discussion", ctx.exception.detail)

    def test_block_declaring_an_unknown_declaration_refuses_unknown_declaration(self) -> None:
        header = _minimal_header(
            blocks=[
                {
                    "id": "b",
                    "requires_facts": [],
                    "requires_declarations": [
                        {
                            "value": "reviewer-name",
                            "source": {"file": "b.md", "quote": "The reviewer name."},
                        }
                    ],
                    "citations": "none",
                }
            ]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "UNKNOWN_DECLARATION")
        self.assertIn("reviewer-name", ctx.exception.detail)

    def test_block_declaring_an_invalid_citations_regime_refuses(self) -> None:
        header = _minimal_header(
            blocks=[
                {
                    "id": "b",
                    "requires_facts": [],
                    "requires_declarations": [],
                    "citations": "maybe",
                }
            ]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "UNKNOWN_CITATIONS_REGIME")
        self.assertIn("maybe", ctx.exception.detail)

    def test_malformed_json_returns_nothing_not_merely_raises(self) -> None:
        data = b"---\n{not valid json\n---\nProse.\n"
        sentinel = object()
        result = sentinel

        with self.assertRaises(Refused) as ctx:
            result = paper_contract.parse(data)

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        # The call site never received a value -- `result` still holds the
        # sentinel it was seeded with, not a partial parse.
        self.assertIs(result, sentinel)

    def test_missing_opening_fence_refuses_malformed_header(self) -> None:
        data = b"No fence at all.\n"

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(data)

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")

    def test_unclosed_fence_refuses_malformed_header(self) -> None:
        data = b"---\n" + json.dumps(_minimal_header()).encode("utf-8") + b"\nProse with no closing fence.\n"

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(data)

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")

    def test_body_below_the_header_is_passed_through_unread(self) -> None:
        header = _minimal_header()
        body = b"Arbitrary prose.\n\nMore prose, %% not a marker, just text.\n"

        _parsed, returned_body = paper_contract.parse(_header_bytes(header) + body)

        self.assertEqual(returned_body, body)

    def test_sections_outside_repository_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            forge_root = Path(tmp) / "repo"
            forge_root.mkdir()
            outside = Path(tmp) / "elsewhere"

            with self.assertRaises(Refused) as ctx:
                paper_contract.resolve_sections_dir(str(outside), forge_root=forge_root)

            self.assertEqual(ctx.exception.code, "SECTIONS_OUTSIDE_REPOSITORY")

    def test_sections_dir_defaults_to_sections_under_the_forge_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            forge_root = Path(tmp) / "repo"
            forge_root.mkdir()

            resolved = paper_contract.resolve_sections_dir(None, forge_root=forge_root)

            self.assertEqual(resolved, (forge_root / "sections").resolve())

    def test_sections_dir_that_does_not_exist_refuses_section_contracts_unreadable(self) -> None:
        """K4 corrective: an in-repository but non-existent `--sections`
        path (a typo, most often) previously resolved silently and every
        downstream verb read it as a real empty corpus -- `{"blocks": [],
        "danglingEdges": []}` reported as clean `ok`, indistinguishable from
        a genuinely empty corpus. Reuses `SECTION_CONTRACTS_UNREADABLE`
        (`paper_verify.UNMEASURED_REASONS`) rather than inventing a new
        code -- the same vocabulary that already names "the corpus itself
        could not be read" everywhere else in this skill."""
        with tempfile.TemporaryDirectory() as tmp:
            forge_root = Path(tmp) / "repo"
            forge_root.mkdir()
            missing = forge_root / "no_existe_xyz"

            with self.assertRaises(Refused) as ctx:
                paper_contract.resolve_sections_dir(str(missing), forge_root=forge_root)

            self.assertEqual(ctx.exception.code, "SECTION_CONTRACTS_UNREADABLE")
            self.assertIn(str(missing), ctx.exception.detail)

    def test_sections_dir_that_is_a_file_refuses_section_contracts_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            forge_root = Path(tmp) / "repo"
            forge_root.mkdir()
            not_a_dir = forge_root / "sections-but-a-file"
            not_a_dir.write_text("not a directory\n", encoding="utf-8")

            with self.assertRaises(Refused) as ctx:
                paper_contract.resolve_sections_dir(str(not_a_dir), forge_root=forge_root)

            self.assertEqual(ctx.exception.code, "SECTION_CONTRACTS_UNREADABLE")


class DocumentBindingSchemaTests(unittest.TestCase):
    """`section-contract` spec, `Requirement: Front Matter Schema` (MODIFIED
    by `the-requirement-names-the-section-that-feeds-it`): a `requires_facts`
    entry MAY additionally carry `document: {lineage, section}` -- the
    source document's lineage and the exact title of the section within it
    that feeds this entry (`source-section-binding` capability). Shape-only
    here -- resolution against real disk (marker, lineage, section
    existence/ambiguity) is `paper_graph._verify_source_section_bindings`'s
    concern, tested in `test_paper_writing.py`, the same split
    `ProducesFactsSchemaTests` already draws for `produces_facts`."""

    def test_a_document_binding_parses(self) -> None:
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
            "document": {
                "lineage": "lumen-thesis",
                "section": "3. Formulación del método y su fundamento teórico",
            },
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        parsed, _body = paper_contract.parse(_header_bytes(header) + b"Prose.\n")

        self.assertEqual(parsed.blocks[0]["requires_facts"], [entry])

    def test_a_requirement_entry_with_no_document_half_parses_unchanged(self) -> None:
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        parsed, _body = paper_contract.parse(_header_bytes(header) + b"Prose.\n")

        self.assertEqual(parsed.blocks[0]["requires_facts"], [entry])
        self.assertNotIn("document", parsed.blocks[0]["requires_facts"][0])

    def test_a_document_binding_missing_section_refuses_naming_section(self) -> None:
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
            "document": {"lineage": "lumen-thesis"},
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("section", ctx.exception.detail)

    def test_a_document_binding_missing_lineage_refuses_naming_lineage(self) -> None:
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
            "document": {"section": "3. Something"},
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("lineage", ctx.exception.detail)

    def test_a_document_binding_with_null_lineage_refuses_naming_lineage(self) -> None:
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
            "document": {"lineage": None, "section": "3. Something"},
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("lineage", ctx.exception.detail)

    def test_a_document_binding_with_unknown_key_refuses_naming_it(self) -> None:
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
            "document": {
                "lineage": "lumen-thesis", "section": "3. Something", "revision": "r21",
            },
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("revision", ctx.exception.detail)

    def test_a_document_binding_on_a_declaration_entry_refuses_naming_document(self) -> None:
        entry = {
            "value": "author-roles",
            "source": {"file": "b.md", "quote": "Author roles."},
            "document": {"lineage": "lumen-thesis", "section": "3. Something"},
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [], "requires_declarations": [entry],
                "citations": "none",
            }]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("document", ctx.exception.detail)

    def test_a_document_binding_on_a_produces_facts_entry_refuses_naming_document(self) -> None:
        """`document` is scoped to `requires_facts` only (design.md, File
        Changes): `produces_facts` shares `_normalize_requirement_entry`'s
        machinery but is never called with `allow_document=True`."""
        entry = {
            "value": "gap",
            "source": {"file": "b.md", "quote": "The gap."},
            "document": {"lineage": "lumen-thesis", "section": "3. Something"},
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [], "requires_declarations": [],
                "citations": "none", "produces_facts": [entry],
            }]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("document", ctx.exception.detail)

    def test_requirement_documents_derives_bindable_triples_in_order(self) -> None:
        bound = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "x"},
            "document": {"lineage": "lumen-thesis", "section": "3. Something"},
        }
        unbound = {"value": "dataset", "source": {"file": "b.md", "quote": "y"}}

        self.assertEqual(
            paper_contract.requirement_documents([bound, unbound]),
            (("formulation", "lumen-thesis", "3. Something"),),
        )

    def test_requirement_documents_is_empty_when_no_entry_carries_one(self) -> None:
        unbound = {"value": "dataset", "source": {"file": "b.md", "quote": "y"}}

        self.assertEqual(paper_contract.requirement_documents([unbound]), ())

    def test_a_document_binding_with_a_list_of_sections_parses(self) -> None:
        """`the-requirement-names-the-section-that-feeds-it` (U2d): a block
        may borrow from more than one section of the same lineage --
        `document.section` MAY be a non-empty list of unique titles, never
        forcing every binding into a list."""
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
            "document": {
                "lineage": "lumen-thesis",
                "section": ["1. Fundamentos", "2. Estimación de la entropía"],
            },
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        parsed, _body = paper_contract.parse(_header_bytes(header) + b"Prose.\n")

        self.assertEqual(parsed.blocks[0]["requires_facts"], [entry])

    def test_a_document_binding_with_an_empty_section_list_refuses(self) -> None:
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
            "document": {"lineage": "lumen-thesis", "section": []},
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("section", ctx.exception.detail)

    def test_a_document_binding_with_a_repeated_section_title_refuses(self) -> None:
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
            "document": {
                "lineage": "lumen-thesis",
                "section": ["3. Something", "3. Something"],
            },
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("section", ctx.exception.detail)

    def test_a_document_binding_with_a_non_string_section_list_entry_refuses(self) -> None:
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
            "document": {"lineage": "lumen-thesis", "section": ["3. Something", 7]},
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("section", ctx.exception.detail)

    def test_a_document_binding_with_a_non_list_non_string_section_refuses(self) -> None:
        entry = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "The formulation."},
            "document": {"lineage": "lumen-thesis", "section": {"nested": True}},
        }
        header = _minimal_header(
            blocks=[{
                "id": "b", "requires_facts": [entry],
                "requires_declarations": [], "citations": "none",
            }]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("section", ctx.exception.detail)

    def test_requirement_documents_derives_one_triple_per_section_title_in_order(self) -> None:
        bound = {
            "value": "formulation",
            "source": {"file": "b.md", "quote": "x"},
            "document": {
                "lineage": "lumen-thesis",
                "section": ["1. First", "2. Second", "3. Third"],
            },
        }

        self.assertEqual(
            paper_contract.requirement_documents([bound]),
            (
                ("formulation", "lumen-thesis", "1. First"),
                ("formulation", "lumen-thesis", "2. Second"),
                ("formulation", "lumen-thesis", "3. Third"),
            ),
        )

    def test_mutation_collapsing_the_section_list_to_its_first_title_is_caught(self) -> None:
        """A weaker `requirement_documents` that only expands the FIRST
        title of a list would silently drop every other section a binding
        names -- this mutation proves the multi-title expansion is real,
        not merely a shape that happens to round-trip a single-entry list."""
        proc = _run_against_mutant(
            "        titles = section if isinstance(section, list) else (section,)\n",
            "        titles = (section[0],) if isinstance(section, list) else (section,)\n",
            "tests.test_paper_contract.DocumentBindingSchemaTests"
            ".test_requirement_documents_derives_one_triple_per_section_title_in_order",
            source_path=SKILL_SCRIPTS / "paper_contract.py",
        )
        _assert_mutant_test_failed(self, proc)


class ProducesFactsSchemaTests(unittest.TestCase):
    """`fact-production` spec, `Requirement: produces_facts Field Grammar`:
    a block (and, symmetrically, a section) MAY declare `produces_facts`,
    parsed through the identical `_normalize_requirement_entry` shape
    `requires_facts` already uses (design.md, Decision B). Shape-only here —
    the corpus-wide quote-transcription gate lives in
    `paper_graph.assemble_corpus` (`tests/test_paper_writing.py`), the same
    split `SchemaTests.test_valid_header_parses_with_no_refusal` already
    documents for `requires_facts`."""

    def test_a_valid_produces_facts_entry_parses(self) -> None:
        rich_entry = {
            "value": "gap",
            "source": {"file": "related-work.md", "quote": "The gap itself."},
        }
        header = _minimal_header(
            blocks=[
                {
                    "id": "rw-closing",
                    "requires_facts": [],
                    "requires_declarations": [],
                    "citations": "none",
                    "produces_facts": [rich_entry],
                }
            ]
        )
        parsed, _body = paper_contract.parse(_header_bytes(header) + b"Prose.\n")

        self.assertEqual(parsed.blocks[0]["produces_facts"], [rich_entry])

    def test_produces_facts_defaults_to_an_empty_list_when_absent(self) -> None:
        header = _minimal_header()
        parsed, _body = paper_contract.parse(_header_bytes(header) + b"Prose.\n")

        self.assertEqual(parsed.blocks[0]["produces_facts"], [])
        self.assertEqual(
            parsed.produces_facts, [],
            "the section-level field must default the same way `after` does, "
            "so every existing fixture and construction site stays green",
        )

    def test_a_valid_section_level_produces_facts_entry_parses(self) -> None:
        rich_entry = {
            "value": "limitations",
            "source": {"file": "limitations.md", "quote": "The limits themselves."},
        }
        header = _minimal_header(produces_facts=[rich_entry])
        parsed, _body = paper_contract.parse(_header_bytes(header) + b"Prose.\n")

        self.assertEqual(parsed.produces_facts, [rich_entry])

    def test_produces_facts_entry_missing_source_refuses_malformed_header(self) -> None:
        header = _minimal_header(
            blocks=[
                {
                    "id": "b",
                    "requires_facts": [],
                    "requires_declarations": [],
                    "citations": "none",
                    "produces_facts": [{"value": "gap"}],
                }
            ]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("source", ctx.exception.detail)

    def test_produces_facts_entry_with_null_source_refuses_malformed_header(self) -> None:
        header = _minimal_header(
            blocks=[
                {
                    "id": "b",
                    "requires_facts": [],
                    "requires_declarations": [],
                    "citations": "none",
                    "produces_facts": [{"value": "gap", "source": None}],
                }
            ]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("source", ctx.exception.detail)

    def test_block_declaring_produces_facts_with_an_unknown_fact_refuses_unknown_fact(self) -> None:
        header = _minimal_header(
            blocks=[
                {
                    "id": "b",
                    "requires_facts": [],
                    "requires_declarations": [],
                    "citations": "none",
                    "produces_facts": [
                        {
                            "value": "discussion",
                            "source": {"file": "b.md", "quote": "The discussion."},
                        }
                    ],
                }
            ]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "UNKNOWN_FACT")
        self.assertIn("discussion", ctx.exception.detail)

    def test_produces_facts_that_is_not_a_list_refuses_malformed_header(self) -> None:
        header = _minimal_header(
            blocks=[
                {
                    "id": "b",
                    "requires_facts": [],
                    "requires_declarations": [],
                    "citations": "none",
                    "produces_facts": "gap",
                }
            ]
        )

        with self.assertRaises(Refused) as ctx:
            paper_contract.parse(_header_bytes(header))

        self.assertEqual(ctx.exception.code, "MALFORMED_HEADER")
        self.assertIn("produces_facts", ctx.exception.detail)


#: The ten shipped contracts' body digests as committed at HEAD **before**
#: this change (578d117f9008062c08bc3a4bd93f2e7245b4ce9b), when every file
#: was headerless prose end to end. Captured once, by running
#: `git show HEAD:sections/<file> | sha256sum` against that commit -- not
#: re-derived from `HEAD` at test time, which would read the AFTER state
#: post-insertion and make the comparison prove nothing (`HEAD` moves the
#: moment this change is committed; a literal baseline does not). This is
#: the acceptance evidence `specs/section-contract`'s
#: `Requirement: Byte-Clean Header Insertion` asks for, held here so the
#: proof stays meaningful for every run after this change lands, not only
#: the one that performed the insertion.
#:
#: `02-experimental-setup.md`, `04-limitations.md` and `05-related-work.md`
#: later received one operator-authored sentence each (the missing
#: `mode`-bearing sentence a corrective batch added), a legitimate,
#: intentional prose edit -- their three digests below were re-captured
#: after that edit and no longer equal the header-migration-era value.
#: `08-abstract.md` received one further operator-authored sentence (a
#: `mode.source.quote` unambiguous to a human reader, repointing `mode`
#: away from the pre-existing "whole argument at one-fiftieth scale"
#: sentence, which stays in the body as ordinary prose) -- its digest below
#: was re-captured after that edit too.
#:
#: All ten digests below were re-captured again for `the-phases-are-derived-
#: not-remembered`, unit 1: every contract's flat `## Inputs` table was
#: restructured into `### External inputs` / `### Internal chain` /
#: `### Structural decisions` (`contract-input-partition` spec) -- a
#: legitimate, intentional prose restructuring, never a meaning change. No
#: sentence any `after`/`mode` quote depends on was touched; `GraphTests`
#: and `ModeTranscriptionTests` above hold that lock independently.
#:
#: Eight of the ten digests below were re-captured a second time for unit
#: 1b: unit 1 wrote a positive "None -- nothing here is derived from a
#: sibling block's own prose" assertion into every `### Internal chain`
#: heading, and six of those eight assertions were false, each contradicted
#: by prose already sitting in the same file. Unit 1b replaces the false
#: "None" with real, quote-backed rows in `01`, `02`, `03`, `05`, `09`,
#: `10`, and rewrites the two genuinely-empty "None" assertions in `04` and
#: `07` into a checkable measurement statement. `06` and `08` are untouched
#: by unit 1b and keep their unit-1 digest.
#:
#: `06-introduction.md`'s digest was re-captured a further time for unit 4
#: (`internal-chain-edges`): task 4.8g rewrites the `## Block 4` heading
#: itself, from `## Block 4 -- Proposal and contributions` to
#: `` ## Block 4 -- Proposal and contributions (`block-4a`, `block-4b`) ``,
#: an explicit-grouping fix for the residue `BLOCK_SUBUNIT_UNDECLARED`'s
#: own extended check (`_verify_block_subunits`, `UNIT_HEADING_AMBIGUOUS`
#: branch) would otherwise flag -- a genuine PROSE change, unlike every
#: other unit-4 edit (all fourteen `after` entries live in the HEADER,
#: below the closing fence's own JSON, and move no body digest). No other
#: file's digest moves in unit 4.
#:
#: `06-introduction.md`'s digest was re-captured once more when the operator
#: allowed paragraph 4a to cite the prior work the proposal extends: the
#: block 4 citation rule, the density rule and the matching disqualifier
#: now carve out that single 4a citation; from 4b onward nothing is cited.
#:
#: `02-experimental-setup.md`'s digest was re-captured a further time for
#: `the-requirement-names-the-sentence-that-demands-it`, Work Unit U3: the
#: operator's ruling on `es-assessment`'s `experimental-design` and `gap`
#: requirements was "B — the contract never wrote it down" for both
#: (`unanchored-requirements.md`), and U3's own launch prompt explicitly
#: authorizes adding two `### External inputs` rows naming those facts so
#: the requirement entries have something real to anchor to — a genuine,
#: ruling-sanctioned PROSE change, the only one this file has had since
#: header insertion.
#:
#: `02`, `03`, `05`, `06`, `07`, `09` were re-captured a further time in
#: `a-fact-is-declared-or-it-is-produced` unit 2: `gap`, `contributions`,
#: `problem-statement` and `limitations` became produced-class facts, so
#: every consumer row naming one of them moved from `### External inputs`
#: to `### Internal chain`, pointing at its producer — a genuine,
#: task-2.5-sanctioned PROSE change (row moves and one `after`-edge note in
#: `06`'s own `### Structural decisions`), never a meaning change to any
#: quote an `after`/`requires_facts`/`produces_facts` entry depends on.
#: `04` and `10` and `01` are untouched by unit 2 and keep their prior
#: digest. `08` was re-captured a further time in
#: `a-fact-is-declared-or-it-is-produced` UNIT 4 (`sdd-verify` FAIL,
#: CRITICAL): `abstract.slot-2` requires `contributions` but carried no
#: `### Internal chain` row naming its producer, `introduction.block-4b` —
#: `paper_graph._verify_producer_chain_rows`'s own new check (the
#: `contract-input-partition` spec's added row-presence requirement) refused
#: `PRODUCER_CHAIN_ABSENT` against the real corpus until one row (and the
#: `after` edge it names) was added — a genuine, ruling-sanctioned PROSE
#: change, never a meaning change to any quote an existing `after`/
#: `requires_facts`/`produces_facts` entry depends on.
#:
#: `01`, `02`, `03`, `05`, `06`, `07`, `08`, `09` were re-captured a further
#: time in `the-methods-section-produces-the-contributions`:
#: `materials-and-methods.mm-proposal` became `contributions`' sole
#: producer (`01` gains the fact's `produces_facts` entry, an ordered
#: `\item` roster mandate before the closing pointer, and inverted
#: naming-authority prose; `06`'s `block-4b` drops the fact and gains
#: `requires_facts` + an `after` edge + an eighth `### Internal chain` row,
#: with its own naming-authority prose inverted); `02`, `03`, `05`, `07`,
#: `08` each retarget one existing `after` edge and row from
#: `introduction.block-4b` to `materials-and-methods.mm-proposal`, reusing
#: every `source.quote` verbatim (`05` also states its `components_from`
#: referent moved). `09`'s digest also moves: its row-only retarget (no
#: `after` edge, since `_position_derived_edges` already orders M&M before
#: title) still changes one body byte span, the row's own dependency cell.
#: `06`'s digest moves a further time within this same change: its
#: `### Structural decisions` bullet arguing `block-4a`/`block-4b` must
#: stay separate ids cited a cycle rationale ("block 2 depends on 4b, and
#: 4a depends on block 2") the move itself falsifies -- block 2 now
#: depends on `mm-proposal`, never on `block-4b` -- so the stale claim was
#: corrected in place (MAINTENANCE pattern 3), never a meaning change to
#: any quote an entry depends on. `04` and `10` are untouched and keep
#: their prior digest.
#:
#: `06`'s digest is re-captured once more: the introduction stopped
#: taking `formulation` as an external input. The formulation reaches
#: the introduction already transposed, through the three written
#: `materials-and-methods` blocks, so `block-4a`'s middle source line
#: was retargeted from "the mathematical formulation" to the methods
#: section, `block-4b`'s own `formulation` row was dropped as carried
#: by the `contributions` it already requires, the now-false
#: `### External inputs` row for the formulation was removed, and
#: `block-4a` gained the `### Internal chain` row its new produced-fact
#: requirement owes `mm-proposal`. Measured cause: `proposals/
#: research-concept-r21.md` carries exactly five claimable sections and
#: the two methods blocks already claim all five, so `score_cut` can
#: never settle a cut that also hands one to an introduction block --
#: `SECTION_BINDING_ABSENT` on 4a/4b had no legal exit. `01`'s own
#: mismatch is NOT re-captured here: it predates this change and
#: belongs to an edit this author did not make.
#:
#: `04` and `08` re-captured: the three remaining consumers of `formulation`
#: -- `lim-proposal-items`, `abstract.slot-3`, `abstract.slot-4` -- moved to
#: requiring `contributions`, for the same measured cause that moved
#: `introduction.block-4a`/`4b`: the five claimable sections of
#: `research-concept-r21.md` are already split whole between the two Methods
#: blocks, so `score_cut` cannot settle any new cut and `bind` refused
#: `BINDING_UNARGUED` forever. The formulation reaches both sections already
#: transposed, through the written Methods blocks. In each file: the
#: now-false external-inputs row was removed, the sentence backing the
#: citation was authored, and the edge was added plus its `### Internal
#: chain` row (`04` gets its first table; before it said "None").
#: `01` re-captured now (R3-stale-section-digest): the guard WAS live -- red
#: before this change -- over the new prose at :281-291 and :406-410; the
#: old digest came from an uncommitted edit.
#: `01`-`09` re-captured (lia-writing-guide): each contract gained a
#: `## LIA house style` section before `## Inputs` (or before
#: `## Cross-cutting conventions` in `06` and `08`), measured over the
#: group's ten Q1 method articles (2025-2026); `01` changed the equation
#: numbering rule and `09` the title range to 10-13 words; `01` and `03`
#: added notation and reporting disqualifiers.
PRE_MIGRATION_BODY_DIGESTS: dict[str, str] = {
    "01-materials-and-methods.md": "4a4d5078955ba64d77e9b45b1f4d116bf072ac011069e2ad57e100d77927405e"[:64],
    "02-experimental-setup.md": "8974689bc11ce955e707b14502aeaf974be7d69959df28f82e9f016cca1d8ce5"[:64],
    "03-results-and-discussion.md": "1f232a64dd277d10da2e47ed3436acb58137f77ac2f5de32cc22da8e8cf974b1"[:64],
    "04-limitations.md": "9175dfeb1d8375439aa9430027464bafe4ddfa477e25efa5d9192b7e74212ed4"[:64],
    "05-related-work.md": "0b8a99da1b91307b3e2e1a654ca161d02ac251635fec99a23edc4407b70d4323"[:64],
    "06-introduction.md": "fdbc7fbbb5c5cd33d076f7e31ed1359916328ed8a384f62b45015ace471964ce"[:64],
    "07-conclusions.md": "5b400628d6d7f783172a0546cb3fa92b973d471b34001f58fb8ff9277d25aeec"[:64],
    "08-abstract.md": "e5e2d180ad612c99c2f779d669956405c56f9744645ca9e229a57c1bc605ba94"[:64],
    "09-title-and-keywords.md": "0fb1238c2b4cc956f127ef75a81bb476ec1e6117c0c0baee472e5e433e17096a"[:64],
    "10-back-matter.md": "b1cd44fe7c00d8eca92d979be5780a97a6cd815faba9ab3890442f2286316cbb"[:64],
}


class ShippedHeaderDigestTests(unittest.TestCase):
    """`section-contract` spec: Byte-Clean Header Insertion. The mechanism
    that performed the insertion (`paper_contract.install_header`) has since
    been deleted (zero-production-caller corrective: its one-shot migration
    over the ten shipped contracts already completed, and nothing promises
    an ongoing "create a new section contract" workflow anywhere in
    `SKILL.md`, a published spec, or a registered agent). This test stands
    alone as the regression check on the corpus's own result, against the
    digests this change's own author captured from `git show HEAD:` at the
    commit before the insertion ran (`PRE_MIGRATION_BODY_DIGESTS` above) --
    `HEAD` itself is never read here, precisely because by the time this
    suite runs again `HEAD` already carries the header and comparing
    against it would prove only that the file equals itself."""

    def test_the_ten_shipped_contracts_carry_headers_matching_the_pre_migration_body_digests(self) -> None:
        for name, expected_digest in PRE_MIGRATION_BODY_DIGESTS.items():
            path = SECTIONS_DIR / name
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"---\n"), f"{name}: no header installed")
            header, body = paper_contract.parse(data)
            self.assertEqual(
                hashlib.sha256(body).hexdigest(), expected_digest,
                f"{name}: body below the header does not match its pre-migration digest",
            )
            self.assertEqual(header.section, name[3:-3])


class IntroductionCitationRegimeTests(unittest.TestCase):
    """Block 4a may cite the prior work the proposal extends, so it runs
    under the resolution regime; from 4b to the end of the introduction
    nothing is cited."""

    def test_only_block_4a_of_block_4_onward_may_cite(self) -> None:
        header, _ = paper_contract.parse((SECTIONS_DIR / "06-introduction.md").read_bytes())
        regimes = {block["id"]: block["citations"] for block in header.blocks}
        self.assertEqual(regimes["block-4a"], "resolution")
        for block_id in ("block-4b", "block-5", "block-6"):
            self.assertEqual(regimes[block_id], "none", block_id)

#: `contract-input-partition` spec, `Requirement: Two-Heading Partition`:
#: EVERY assembled contract, including a synthetic fixture, must carry both
#: headings or `paper_graph.assemble_corpus` refuses `INPUT_PARTITION_ABSENT`
#: -- this is the shared default body every `_write_section` caller below
#: gets unless it passes its own `body=`, so a fixture built only to
#: exercise an unrelated concern (id collisions, `after` resolution, order,
#: readiness) does not also have to spell out an empty partition by hand.
_DEFAULT_PARTITIONED_BODY = (
    b"Prose.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
)


def _write_section(
    directory: Path, filename: str, header: dict, body: bytes = _DEFAULT_PARTITIONED_BODY,
) -> None:
    (directory / filename).write_bytes(_header_bytes(header) + body)


def _block(block_id: str, *, facts=(), declarations=(), citations="none", after=None) -> dict:
    entry = {
        "id": block_id,
        "requires_facts": list(facts),
        "requires_declarations": list(declarations),
        "citations": citations,
    }
    if after is not None:
        entry["after"] = after
    return entry


def _quote_source(file: str, quote: str) -> dict:
    return {"file": file, "quote": quote}


def _fact_entry(value: str, file: str, *, quote: str | None = None) -> dict:
    """A rich `requires_facts`/`requires_declarations` entry, self-sourced
    at `file` by default with the same `This block requires the <value>.`
    sentence `_write_section`'s caller is expected to append to that file's
    own body -- U3 (design.md D3) removed bare-string acceptance, so every
    `_block(facts=[...])` caller below now builds this shape instead."""
    return {
        "value": value,
        "source": _quote_source(file, quote or f"This block requires the {value}."),
    }


def _quote_in_body(file_path: Path, quote: str) -> bool:
    """Thin pass-through to the PRODUCTION lock, `paper_contract.quote_in_body`
    -- kept here, rather than deleted, only because most of this file's
    callers pass a file PATH while the production function (called from
    both `paper_contract.parse` and `paper_graph.assemble_corpus`, which
    read bodies off two different disk shapes) takes body BYTES directly.
    No algorithm lives in this file any more: a second copy of the
    whitespace-collapse/emphasis-strip logic, next to the one now load-
    bearing in production, is exactly the "two enforcement paths that can
    disagree" risk this corrective was written to close (defect 1). Note
    this now runs `paper_contract.parse` on `file_path`, which since this
    same corrective also refuses `SPAN_NOT_IN_SOURCE` if THAT file's own
    `mode` transcription is dishonest -- never an issue for the real,
    honestly-transcribed corpus this helper is used against."""
    _header, body = paper_contract.parse(file_path.read_bytes())
    return paper_contract.quote_in_body(body, quote)


class GraphTests(unittest.TestCase):
    """`section-contract` spec: flat id namespace, `after` transcription and
    resolution, the exactly-two literal cross-section edges, and the
    position-derived third edge the orchestrator settled at apply time
    (`specs/section-contract/spec.md`'s Implementation note)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    # --- flat id namespace -------------------------------------------------

    def test_a_block_id_colliding_with_a_section_id_refuses_id_collision(self) -> None:
        _write_section(self.sections_dir, "01-a.md", {
            "section": "a", "position": 1, "blocks": [_block("only")],
        })
        _write_section(self.sections_dir, "02-b.md", {
            "section": "b", "position": 2, "blocks": [_block("a")],  # collides with section "a"
        })

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "ID_COLLISION")
        self.assertIn("a", ctx.exception.detail)

    def test_disjoint_ids_across_sections_assemble_cleanly(self) -> None:
        _write_section(self.sections_dir, "01-a.md", {
            "section": "a", "position": 1, "blocks": [_block("only")],
        })
        _write_section(self.sections_dir, "02-b.md", {
            "section": "b", "position": 2, "blocks": [_block("only")],  # same raw id, different section: fine
        })

        corpus = paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(set(corpus.blocks), {"a.only", "b.only"})

    # --- after: section target expands to every block ----------------------

    def test_after_naming_a_section_expands_to_every_block_of_it(self) -> None:
        _write_section(self.sections_dir, "01-a.md", {
            "section": "a", "position": 1,
            "blocks": [_block("first"), _block("second")],
        })
        _write_section(self.sections_dir, "02-b.md", {
            "section": "b", "position": 2,
            "after": [{"target": "a", "source": _quote_source("sections/01-a.md", "Prose.")}],
            "blocks": [_block("only")],
        })

        corpus = paper_graph.assemble_corpus(self.sections_dir)
        edge_set = paper_graph.collect_edges(corpus)

        pairs = {(before, after) for before, after, _source in edge_set.edges}
        self.assertIn(("a.first", "b.only"), pairs)
        self.assertIn(("a.second", "b.only"), pairs)

    # --- after: an absent target is reported, never refused ----------------

    def test_dangling_after_target_is_reported_never_refused(self) -> None:
        _write_section(self.sections_dir, "01-a.md", {
            "section": "a", "position": 1,
            "after": [{"target": "nonexistent", "source": _quote_source("sections/01-a.md", "x")}],
            "blocks": [_block("only")],
        })

        corpus = paper_graph.assemble_corpus(self.sections_dir)
        edge_set = paper_graph.collect_edges(corpus)  # must not raise

        self.assertIn("nonexistent", edge_set.dangling)

    # --- transcription lock: real corpus ------------------------------------

    def _real_corpus(self):
        return paper_graph.assemble_corpus(SECTIONS_DIR)

    def test_the_real_corpus_assembles_cleanly_under_the_production_transcription_lock(self) -> None:
        """This corrective's own requirement: moving the transcription lock
        off the test suite and into `paper_contract.parse` (`mode`) and
        `paper_graph.assemble_corpus` (`after`) must refuse NONE of the ten
        shipped contracts or their real `after` edges -- both checks run as
        a side effect of the one call below (`assemble_corpus` parses every
        file, which enforces `mode`; it then enforces `after` itself). A
        refusal here would mean the operator's own prose is wrong, to be
        reported back, never patched around by loosening this check."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)  # must not raise
        self.assertEqual(len(corpus.sections), 10, "expected exactly the ten shipped sections")

    def test_every_transcribed_afters_quote_is_a_substring_of_its_named_file(self) -> None:
        # Reads the parsed BODY only, via `paper_contract.parse`'s own
        # header/body split -- never the raw file text. A whole-file read is
        # vacuous for any edge whose `source.file` is the SAME file as the
        # header that transcribes it (`introduction.block-3` -> `related-
        # work`, sourced in its own `06-introduction.md`): that header's own
        # JSON always re-serializes `quote` verbatim, so a substring check
        # against the raw bytes finds it there regardless of what the prose
        # says. Checking the body only closes that hole -- proven by
        # `test_a_fabricated_quote_on_a_self_referential_edge_fails_the_lock`
        # below, which replays this exact check with a prose-absent quote on
        # that exact edge and confirms it now fails.
        corpus = self._real_corpus()

        checked = 0
        for section_id, header in corpus.sections.items():
            entries = list(header.after)
            for raw_block in header.blocks:
                entries += raw_block["after"]
            for entry in entries:
                source = entry["source"]
                self.assertTrue(
                    _quote_in_body(FORGE_ROOT / source["file"], source["quote"]),
                    f"{section_id}: quote not found verbatim (whitespace-collapsed) in "
                    f"{source['file']}'s prose body",
                )
                checked += 1

        self.assertGreater(checked, 0, "no transcribed after entries were found to check")

    def test_a_fabricated_quote_on_a_self_referential_edge_fails_the_lock(self) -> None:
        """Reproduces the verifier's own falsification exactly, on a temp
        copy -- never the tracked file. `introduction.block-3`'s `after`
        names `related-work`, sourced in `06-introduction.md`, the SAME file
        as its own holder section: self-sourced, the one shape (of the two
        shipped literal edges) that made the OLD, whole-file-reading lock
        vacuous, because that file's header always re-serializes whatever
        `quote` it holds. Substitute a prose-absent quote into ONLY the
        header field (the body is untouched) and confirm: the OLD shape
        (raw-whole-file substring) still reports it found -- the exact hole
        -- while the body-only check above correctly reports it absent.
        A fix proven only by "the old test still passes" would prove
        nothing, since that test passed while broken."""
        real_path = SECTIONS_DIR / "06-introduction.md"
        header, body = paper_contract.parse(real_path.read_bytes())
        self.assertEqual(header.section, "introduction")

        fabricated_quote = "Purple elephants never write in Related Work order at all."
        body_text = " ".join(body.decode("utf-8").split())
        self.assertNotIn(
            fabricated_quote, body_text,
            "fixture assumption: the fabrication is absent from the real prose",
        )

        def _tamper(raw_block: dict) -> dict:
            if raw_block["id"] != "block-3":
                return raw_block
            tampered = dict(raw_block)
            tampered["after"] = [
                {**entry, "source": {**entry["source"], "quote": fabricated_quote}}
                for entry in raw_block["after"]
            ]
            return tampered

        tampered_header = {
            "section": header.section,
            "position": header.position,
            "after": header.after,
            "blocks": [_tamper(raw_block) for raw_block in header.blocks],
        }
        tampered_bytes = _header_bytes(tampered_header) + body

        # OLD lock shape: raw-whole-file substring check. It finds the
        # fabrication -- not in the prose, but in the header's own JSON,
        # which the tamper just wrote into that same file. This is exactly
        # the vacuity `verify-report.md`'s Finding W1 proved.
        raw_text = " ".join(tampered_bytes.decode("utf-8").split())
        self.assertIn(
            fabricated_quote, raw_text,
            "fixture assumption: the tampered header still re-serializes the fabrication verbatim",
        )

        # NEW lock shape (this corrective's fix, defect 1): drive the REAL
        # production entrypoint, `paper_graph.assemble_corpus`, on a temp
        # copy of the WHOLE shipped corpus (never the tracked file) with
        # only `06-introduction.md` swapped for the tampered bytes -- the
        # rest of the corpus stays real so `related-work`, this edge's own
        # `target`, still resolves exactly as it does in the real
        # repository. A single-file fixture would make that target
        # dangling and this corrective's own narrowing (dangling targets
        # are not quote-checked) would silently skip the exact case this
        # test exists to prove.
        with tempfile.TemporaryDirectory() as tmp:
            temp_sections = Path(tmp) / "sections"
            temp_sections.mkdir()
            for path in SECTIONS_DIR.glob("*.md"):
                (temp_sections / path.name).write_bytes(path.read_bytes())
            (temp_sections / "06-introduction.md").write_bytes(tampered_bytes)

            with self.assertRaises(Refused) as ctx:
                paper_graph.assemble_corpus(temp_sections)

        self.assertEqual(ctx.exception.code, "SPAN_NOT_IN_SOURCE")
        self.assertIn("06-introduction.md", ctx.exception.detail)
        self.assertIn("Purple elephants", ctx.exception.detail)

    # --- exactly two literal cross-section edges, derived not hand-listed --

    def test_the_shipped_corpus_has_exactly_two_literal_cross_section_after_edges(self) -> None:
        corpus = self._real_corpus()

        cross_section = set()
        for section_id, header in corpus.sections.items():
            for entry in header.after:
                if entry["target"] != section_id and entry["target"] in corpus.sections:
                    cross_section.add((section_id, entry["target"]))
            for raw_block in header.blocks:
                for entry in raw_block["after"]:
                    if entry["target"] != section_id and entry["target"] in corpus.sections:
                        cross_section.add((f"{section_id}.{raw_block['id']}", entry["target"]))

        self.assertEqual(
            cross_section,
            {("abstract", "conclusions"), ("introduction.block-3", "related-work")},
        )

    # --- the position-derived third edge (orchestrator settlement) ---------

    def test_title_and_keywords_position_derived_edge_targets_exactly_the_seven_body_sections(self) -> None:
        corpus = self._real_corpus()

        body_sections = {
            sid for sid, header in corpus.sections.items()
            if corpus.sections["abstract"].position < header.position < corpus.sections["back-matter"].position
        }

        self.assertEqual(
            body_sections,
            {
                "introduction", "related-work", "materials-and-methods",
                "experimental-setup", "results-and-discussion", "limitations",
                "conclusions",
            },
        )

        edge_set = paper_graph.collect_edges(corpus)
        pairs = {(before, after) for before, after, _source in edge_set.edges}
        tk_blocks = corpus.order_by_section["title-and-keywords"]
        for section_id in body_sections:
            for target_qualified in corpus.order_by_section[section_id]:
                for tk_qualified in tk_blocks:
                    self.assertIn((target_qualified, tk_qualified), pairs)

    def test_position_derived_edge_is_computed_from_looked_up_positions_not_a_hardcoded_integer(self) -> None:
        # Re-derive the same corpus with abstract's position changed (still
        # a valid, internally consistent renumbering) and confirm the body
        # set moves with it -- proof the computation reads `position` via
        # section id lookups rather than a baked-in `2`/`10` pair.
        with tempfile.TemporaryDirectory() as tmp:
            alt_dir = Path(tmp) / "sections"
            alt_dir.mkdir()
            _write_section(alt_dir, "01-title-and-keywords.md", {
                "section": "title-and-keywords", "position": 1, "blocks": [_block("only")],
            })
            _write_section(alt_dir, "02-abstract.md", {
                "section": "abstract", "position": 3, "blocks": [_block("only")],  # moved from 2 to 3
            })
            _write_section(alt_dir, "03-middle.md", {
                "section": "middle", "position": 4, "blocks": [_block("only")],
            })
            _write_section(alt_dir, "04-back-matter.md", {
                "section": "back-matter", "position": 5, "blocks": [_block("only")],
            })

            corpus = paper_graph.assemble_corpus(alt_dir)
            edge_set = paper_graph.collect_edges(corpus)
            pairs = {(before, after) for before, after, _source in edge_set.edges}

            self.assertIn(("middle.only", "title-and-keywords.only"), pairs)


class ModeTranscriptionTests(unittest.TestCase):
    """`section-contract` spec, `Requirement: Closed Mode Vocabulary And
    Transcription`: a `mode` MUST be admitted only where the contract's own
    prose states it, "mirroring the transcription discipline already
    required of `after` edges" -- the discipline `GraphTests` above already
    proves for `after` via `_quote_in_body` (body-only, never the raw
    file). Before this corrective, `test_paper_writing.py`'s
    `test_shipped_contracts_declaring_mode_resolve_it_at_every_block`
    checked `mode`'s SHAPE and `source["file"]`, but never `source["quote"]`
    against real prose -- this class closes that gap, the CRITICAL a
    corrective re-verify found."""

    def _real_corpus(self):
        return paper_graph.assemble_corpus(SECTIONS_DIR)

    def _declared_modes(self, corpus=None):
        """Derived from the corpus, never a hand-listed set of section ids:
        every section's own `header.mode` (all ten shipped sections declare
        one as of the `02`/`04`/`05` corrective) plus every block's own
        `mode` (none in the shipped corpus today, but the walk is generic --
        a future block-level declaration is picked up without touching this
        test). `corpus` defaults to the real shipped one; a caller may pass a
        synthetic corpus to exercise the None-skipping branch without
        depending on any real section ever leaving `mode` undeclared."""
        corpus = corpus if corpus is not None else self._real_corpus()
        entries = []
        for section_id, header in corpus.sections.items():
            if header.mode is not None:
                entries.append((section_id, header.mode))
            for raw_block in header.blocks:
                block_mode = raw_block.get("mode")
                if block_mode is not None:
                    entries.append((f"{section_id}.{raw_block['id']}", block_mode))
        return entries

    def test_every_declared_modes_quote_is_a_substring_of_its_named_file(self) -> None:
        entries = self._declared_modes()

        for owner, mode in entries:
            source = mode["source"]
            self.assertTrue(
                _quote_in_body(FORGE_ROOT / source["file"], source["quote"]),
                f"{owner}: mode quote not found verbatim (whitespace-collapsed, "
                f"markdown-emphasis-stripped) in {source['file']}'s prose body",
            )

        # Golden count, not a hand-listed set of section ids: the walk above
        # is generic over the whole corpus; this pins it to the ten modes
        # this build has actually declared, one per shipped section -- the
        # same "exactly N, derived not hand-listed" style `GraphTests`
        # already uses for the two literal cross-section `after` edges.
        # Grew from seven to ten when `02-experimental-setup.md`,
        # `04-limitations.md` and `05-related-work.md` each received their
        # operator-authored mode-bearing sentence; the count is read off the
        # real corpus walk above, never edited by hand to match.
        self.assertEqual(len(entries), 10, "expected exactly the ten declared modes")

    def test_undeclared_sections_are_absent_not_silently_passing(self) -> None:
        """Every shipped section now declares a `mode`
        (`test_every_declared_modes_quote_is_a_substring_of_its_named_file`'s
        golden count of ten), so this class exercises the None-skipping
        branch of the walk on a synthetic corpus instead of leaning on a
        real section that happens to leave `mode` undeclared -- the walk
        must still skip an undeclared section entirely rather than ever
        counting the absence as a checked-and-passed entry."""
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp)
            declared_header = {
                "section": "with-mode", "position": 1,
                "mode": {
                    "value": "argument",
                    "source": {"file": "with-mode.md", "quote": "This section argues."},
                },
                "blocks": [{
                    "id": "b1", "requires_facts": [], "requires_declarations": [],
                    "citations": "none",
                }],
            }
            undeclared_header = {
                "section": "without-mode", "position": 2,
                "blocks": [{
                    "id": "b2", "requires_facts": [], "requires_declarations": [],
                    "citations": "none",
                }],
            }
            partition = b"\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
            (sections_dir / "with-mode.md").write_bytes(
                b"---\n" + json.dumps(declared_header).encode("utf-8")
                + b"\n---\nThis section argues." + partition
            )
            (sections_dir / "without-mode.md").write_bytes(
                b"---\n" + json.dumps(undeclared_header).encode("utf-8")
                + b"\n---\nNo mode sentence here." + partition
            )

            corpus = paper_graph.assemble_corpus(sections_dir)
            self.assertIsNone(corpus.sections["without-mode"].mode)

            owners = {owner for owner, _mode in self._declared_modes(corpus=corpus)}
            self.assertIn("with-mode", owners)
            self.assertNotIn("without-mode", owners)

    def test_a_fabricated_mode_quote_on_a_self_sourced_entry_fails_the_lock(self) -> None:
        """Same falsification `GraphTests` already runs for `after`
        (`test_a_fabricated_quote_on_a_self_referential_edge_fails_the_lock`),
        replayed for `mode` -- the exact CRITICAL this corrective closes.
        `introduction`'s own `mode` is self-sourced (`source.file` is
        `06-introduction.md`, the same file as the header holding it): the
        one shape that makes a whole-file raw substring check vacuous, since
        that file's header JSON always re-serializes whatever `quote` the
        `mode` entry holds, verbatim."""
        real_path = SECTIONS_DIR / "06-introduction.md"
        header, body = paper_contract.parse(real_path.read_bytes())
        self.assertEqual(header.section, "introduction")
        self.assertIsNotNone(header.mode)
        self.assertEqual(header.mode["source"]["file"], "sections/06-introduction.md")

        fabricated_quote = "Purple elephants narrate every argumentative function in reverse."
        body_text = " ".join(body.decode("utf-8").split())
        self.assertNotIn(
            fabricated_quote, body_text,
            "fixture assumption: the fabrication is absent from the real prose",
        )

        tampered_header = {
            "section": header.section,
            "position": header.position,
            "after": header.after,
            "mode": {
                "value": header.mode["value"],
                "source": {**header.mode["source"], "quote": fabricated_quote},
            },
            "blocks": [dict(raw_block) for raw_block in header.blocks],
        }
        tampered_bytes = _header_bytes(tampered_header) + body

        with tempfile.TemporaryDirectory() as tmp:
            tampered_path = Path(tmp) / "06-introduction.md"
            tampered_path.write_bytes(tampered_bytes)

            # OLD lock shape: raw-whole-file substring check. It finds the
            # fabrication -- not in the prose, but in the header's own JSON,
            # which the tamper just wrote into that same file.
            raw_text = " ".join(tampered_path.read_text(encoding="utf-8").split())
            self.assertIn(
                fabricated_quote, raw_text,
                "fixture assumption: the tampered header still re-serializes the fabrication verbatim",
            )

            # NEW lock shape (this corrective's fix, defect 1): the REAL
            # production entrypoint -- `paper_contract.parse` itself, not a
            # test-only helper reporting a bare `False` -- refuses on its
            # own, before this header is ever handed back to any caller
            # (`paper_graph.assemble_corpus`, `write`, `render`, `place`,
            # every CLI verb that reads a section contract).
            with self.assertRaises(Refused) as ctx:
                paper_contract.parse(tampered_path.read_bytes())

        self.assertEqual(ctx.exception.code, "SPAN_NOT_IN_SOURCE")
        self.assertIn("introduction", ctx.exception.detail)
        self.assertIn("Purple elephants", ctx.exception.detail)

    def test_a_paraphrased_quote_and_an_unrelated_sentence_both_still_fail(self) -> None:
        """The trap named in this corrective's own brief: normalizing
        markdown emphasis (`**bold**`/`*italic*`) must never become a fuzzy
        or similarity match. Feed the lock a genuine paraphrase of
        `06-introduction.md`'s own prose (same meaning, different words) and
        a genuinely unrelated sentence, and confirm both still fail -- proof
        the normalization only strips literal `*` characters, never blurs
        word content."""
        real_path = SECTIONS_DIR / "06-introduction.md"

        paraphrase = "Six persuasive roles, always in the same sequence, spread over 7 to 13 paragraphs."
        unrelated = "The dataset was collected across three clinical sites over eighteen months."

        self.assertFalse(_quote_in_body(real_path, paraphrase), "a paraphrase must not pass the lock")
        self.assertFalse(_quote_in_body(real_path, unrelated), "an unrelated sentence must not pass the lock")

    def test_the_shipped_introduction_mode_quote_passes_only_once_emphasis_is_stripped(self) -> None:
        """Direct proof of the fix, isolated from the corpus walk above:
        `06-introduction.md`'s real, unedited `mode.source.quote` is an
        honest, word-for-word transcription of the real prose -- the ONLY
        reason the old whitespace-collapse-only lock rejected it is that the
        prose wraps two of those words in `**bold**` markup, decoration a
        JSON quote field was never meant to have to spell out."""
        real_path = SECTIONS_DIR / "06-introduction.md"
        header, _body = paper_contract.parse(real_path.read_bytes())
        quote = header.mode["source"]["quote"]

        self.assertTrue(_quote_in_body(real_path, quote))


class EmphasisStripTests(unittest.TestCase):
    """Defect 2: the emphasis strip must be PAIR-aware, never a bare-
    character removal. Two properties, each its own test rather than one
    combined assertion, so either can fail independently and name exactly
    which property broke."""

    def test_a_bold_pair_still_matches_once_stripped(self) -> None:
        """The property the strip exists for in the first place: a
        `**bold**` pair must still match a quote written without the
        markup -- this is why `06-introduction.md` needed no prose edit
        when its own mode quote was first transcribed."""
        body = b"This sentence carries **bold words** inside it.\n"
        self.assertTrue(paper_contract.quote_in_body(body, "bold words"))

    def test_an_unpaired_asterisk_inside_a_word_does_not_falsely_match(self) -> None:
        """The exact hole named in this corrective's brief: `func*tions`
        (one bare `*`, no closing partner anywhere in the text) must NOT
        match a quote written `functions` -- a single stray delimiter is
        not a pair, so nothing strips it, and the literal `*` survives
        into the comparison, correctly breaking the match."""
        body = b"This sentence carries func*tions inside it.\n"
        self.assertFalse(paper_contract.quote_in_body(body, "functions"))


class InputPartitionTests(unittest.TestCase):
    """`contract-input-partition` spec, `Requirement: Two-Heading
    Partition`: every contract's prose MUST carry `### External inputs` and
    `### Internal chain`, or `_verify_input_partition` (called from
    `paper_graph.assemble_corpus`) refuses `INPUT_PARTITION_ABSENT` naming
    whichever is missing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    _PARTITIONED_BODY = (
        b"# Example\n\n"
        b"### External inputs\n\n"
        b"| Input | Unblocks |\n|---|---|\n"
        b"| The **dataset** | `example.only` |\n\n"
        b"### Internal chain\n\n"
        b"None -- `example.only` depends only on external facts.\n"
    )

    def test_a_partitioned_contract_parses_with_no_refusal(self) -> None:
        _write_section(
            self.sections_dir, "01-example.md",
            {"section": "example", "position": 1, "blocks": [_block("only")]},
            body=self._PARTITIONED_BODY,
        )

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # must not raise

        self.assertIn("example.only", corpus.blocks)

    def test_a_flat_unpartitioned_contract_refuses_naming_internal_chain(self) -> None:
        """`contract-input-partition` spec's own scenario: a flat `## Inputs`
        table missing BOTH headings refuses naming `### Internal chain`
        specifically -- the more actionable half, since that is the
        dependency data this change exists to make explicit."""
        body = (
            b"# Example\n\n"
            b"## Inputs\n\n"
            b"| What | Depends on |\n|---|---|\n| Everything | the dataset |\n"
        )
        _write_section(
            self.sections_dir, "01-example.md",
            {"section": "example", "position": 1, "blocks": [_block("only")]},
            body=body,
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "INPUT_PARTITION_ABSENT")
        self.assertIn("### Internal chain", ctx.exception.detail)

    def test_missing_only_internal_chain_refuses_naming_it(self) -> None:
        body = (
            b"### External inputs\n\n"
            b"| Input | Unblocks |\n|---|---|\n| The **dataset** | `example.only` |\n"
        )
        _write_section(
            self.sections_dir, "01-example.md",
            {"section": "example", "position": 1, "blocks": [_block("only")]},
            body=body,
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "INPUT_PARTITION_ABSENT")
        self.assertIn("### Internal chain", ctx.exception.detail)

    def test_missing_only_external_inputs_refuses_naming_it(self) -> None:
        body = b"### Internal chain\n\nNone -- `example.only` depends only on external facts.\n"
        _write_section(
            self.sections_dir, "01-example.md",
            {"section": "example", "position": 1, "blocks": [_block("only")]},
            body=body,
        )

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "INPUT_PARTITION_ABSENT")
        self.assertIn("### External inputs", ctx.exception.detail)

    def test_the_real_corpus_partitions_cleanly(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)  # must not raise
        self.assertEqual(len(corpus.sections), 10)

    def test_mutation_deleting_internal_chain_from_a_normalized_fixture_fires_live(self) -> None:
        """Task 1.4: the guard must fire against a LIVE re-parse of the
        mutated file, never a cached result from the first, passing parse --
        proven by re-parsing the SAME directory twice, the second time after
        the heading has been deleted underneath it."""
        header = {"section": "example", "position": 1, "blocks": [_block("only")]}
        _write_section(self.sections_dir, "01-example.md", header, body=self._PARTITIONED_BODY)

        paper_graph.assemble_corpus(self.sections_dir)  # first, live parse: no refusal

        mutated_body = (
            b"### External inputs\n\n"
            b"| Input | Unblocks |\n|---|---|\n| The **dataset** | `example.only` |\n"
        )
        _write_section(self.sections_dir, "01-example.md", header, body=mutated_body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)  # second, live parse: refuses

        self.assertEqual(ctx.exception.code, "INPUT_PARTITION_ABSENT")
        self.assertIn("### Internal chain", ctx.exception.detail)

    def test_corpus_wide_content_smoke_check_via_the_cli(self) -> None:
        """Task 1.21: `paper_cli.py contract` over the whole shipped corpus
        reports zero `INPUT_PARTITION_ABSENT` refusals now that all ten
        contracts carry the two-heading partition -- chain-row backing
        itself (`CHAIN_ROW_UNRESOLVED`/`CHAIN_ROW_UNBACKED`) is unit 4's own
        concern, not this unit's."""
        proc = subprocess.run(
            [sys.executable, str(SKILL_SCRIPTS / "paper_cli.py"), "contract"],
            capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(len(payload["sections"]), 10)

    def test_introduction_block_4_is_two_blocks_not_one_composite(self) -> None:
        """`introduction.block-4` is TWO blocks, not one node with glosses.
        The contract's own extent line says so -- "Two physical paragraphs,
        120-180 words in total" -- and it names them `Paragraph 4a - the
        prose` and `Paragraph 4b - the list`.

        Collapsing them manufactures a cycle the writing order does not
        have: block 2 depends on 4b (each contribution read backwards as
        the deficiency it resolves) while 4a depends on block 2 (the
        purpose clause mirrors its specific problems). Those parts fall on
        OPPOSITE sides of block 2, so one node cannot express them --
        settled decision 5's union rule has no answer here, and the split
        is at the contract's block inventory, never at the graph."""
        _header, body = paper_contract.parse((SECTIONS_DIR / "06-introduction.md").read_bytes())
        text = body.decode("utf-8")

        self.assertIn("Two physical paragraphs", text)
        self.assertIn("Paragraph 4a", text)
        self.assertIn("Paragraph 4b", text)

        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        self.assertIn("introduction.block-4a", corpus.blocks)
        self.assertIn("introduction.block-4b", corpus.blocks)
        self.assertNotIn(
            "introduction.block-4", corpus.blocks,
            "the collapsed id must be gone -- leaving it would let a chain row "
            "resolve to a node whose parts straddle block 2",
        )

        # 4a carries only the contributions the methods section produces;
        # the results complete 4b's list, never 4a's prose. Getting this
        # backwards would hold the whole presenting paragraph hostage to a
        # measurement it never needed. Neither block requires `formulation`
        # any more: the formulation reaches the introduction already
        # transposed, through `materials-and-methods.mm-proposal`, so
        # requiring the document-rooted fact here demanded a source-section
        # binding against a proposals/ revision whose claimable sections the
        # two methods blocks already hold in full -- a cut no further
        # assignment can settle, and therefore a gate with no legal exit.
        self.assertEqual(corpus.blocks["introduction.block-4a"].requires_facts, ("contributions",))
        self.assertEqual(
            corpus.blocks["introduction.block-4b"].requires_facts,
            ("results", "contributions"),
        )

    def test_the_internal_chain_of_the_introduction_is_acyclic(self) -> None:
        """`the-methods-section-produces-the-contributions` re-measured this
        test: `block-2` now depends on `materials-and-methods.mm-proposal`
        (`contributions`' sole producer, moved from `introduction.block-4b`)
        and `block-4b` gained its own fifth row depending on that same
        producer (`_verify_producer_chain_rows`'s own row-presence
        requirement). Re-measured again when `block-4a` stopped requiring
        the document-rooted `formulation` and started requiring the
        `contributions` that same producer emits: 4a owes that producer its
        own row too, so there are now SIX normalized chain rows whose
        SUBJECT starts with `introduction.` -- 4b -> mm-proposal,
        4b -> 2 -> mm-proposal, 4a -> 2, 4a -> 4b, 4a -> mm-proposal and
        3 -> 2 -- still a DAG, still the regression for the cycle the
        collapsed `block-4` produced."""
        _header, body = paper_contract.parse((SECTIONS_DIR / "06-introduction.md").read_bytes())
        text = body.decode("utf-8")
        chain = text.split("### Internal chain", 1)[1].split("###", 1)[0]

        rows = [line for line in chain.splitlines() if line.startswith("| `introduction.")]
        self.assertEqual(len(rows), 6, chain)

        def ends(row: str) -> tuple:
            subject, dependency = row.split("|")[1], row.split("|")[2]
            return (subject.split("`")[1], dependency.split("`")[1])

        edges = {ends(row) for row in rows}
        self.assertEqual(
            edges,
            {
                ("introduction.block-2", "materials-and-methods.mm-proposal"),
                ("introduction.block-3", "introduction.block-2"),
                ("introduction.block-4a", "introduction.block-2"),
                ("introduction.block-4a", "introduction.block-4b"),
                ("introduction.block-4a", "materials-and-methods.mm-proposal"),
                ("introduction.block-4b", "materials-and-methods.mm-proposal"),
            },
        )
        # No pair appears in both directions -- that is what the collapsed
        # id produced and what this split exists to remove.
        for subject, dependency in edges:
            self.assertNotIn((dependency, subject), edges, f"{subject} <-> {dependency}")


class InternalChainTests(unittest.TestCase):
    """`internal-chain-edges` spec, both Requirements; `contract-input-
    partition` spec, `Requirement: Internal-Chain Rows Name Qualified Block
    Ids`. `_verify_internal_chain` (called from `paper_graph.assemble_corpus`,
    right after `_verify_after_transcription`) refuses `CHAIN_ROW_UNRESOLVED`
    when a row's leading token is not a key of `corpus.blocks`, and
    `CHAIN_ROW_UNBACKED` when it is a key but no `after` edge backs the
    pair."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def _body(self, chain_table: bytes) -> bytes:
        return (
            b"# Example\n\nProse.\n\n### External inputs\n\nNone.\n\n"
            b"### Internal chain\n\n| Block | Depends on |\n|---|---|\n"
            + chain_table
        )

    def test_a_row_naming_a_qualified_id_maps_and_a_backed_row_is_accepted(self) -> None:
        """`internal-chain-edges` spec's own "A backed row is accepted"
        scenario, and `contract-input-partition`'s "A row naming a
        qualified id maps"."""
        header = {
            "section": "example", "position": 1,
            "blocks": [
                _block("first"),
                _block("second", after=[
                    {"target": "example.first",
                     "source": _quote_source("sections/01-example.md", "Prose.")},
                ]),
            ],
        }
        body = self._body(b"| `example.second` | `example.first` |\n")
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # must not raise

        self.assertIn("example.second", corpus.blocks)

    def test_a_row_naming_only_a_paraphrase_refuses_chain_row_unresolved(self) -> None:
        """`contract-input-partition` spec's own scenario: a row naming no
        qualified block id anywhere refuses `CHAIN_ROW_UNRESOLVED` naming
        that row's text."""
        header = {"section": "example", "position": 1, "blocks": [_block("only")]}
        body = self._body(
            b"| depends on: the announcement of the count | plain prose, no id |\n"
        )
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "CHAIN_ROW_UNRESOLVED")
        self.assertIn("the announcement of the count", ctx.exception.detail)

    def test_mutation_editing_a_mapping_row_to_drop_its_qualified_id_refuses_live(self) -> None:
        """Task 4.3: a previously-mapping row edited to drop its qualified
        id must refuse on a LIVE re-parse, never reuse a stale mapping."""
        header = {
            "section": "example", "position": 1,
            "blocks": [
                _block("first"),
                _block("second", after=[
                    {"target": "example.first",
                     "source": _quote_source("sections/01-example.md", "Prose.")},
                ]),
            ],
        }
        good_body = self._body(b"| `example.second` | `example.first` |\n")
        _write_section(self.sections_dir, "01-example.md", header, body=good_body)

        paper_graph.assemble_corpus(self.sections_dir)  # first, live parse: no refusal

        mutated_body = self._body(b"| `example.second` | the first block, dropped id |\n")
        _write_section(self.sections_dir, "01-example.md", header, body=mutated_body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)  # second, live parse: refuses

        self.assertEqual(ctx.exception.code, "CHAIN_ROW_UNRESOLVED")

    def test_a_row_naming_a_real_block_with_no_backing_edge_refuses_chain_row_unbacked(self) -> None:
        """`internal-chain-edges` spec's own "An unbacked row refuses"
        scenario: both cells resolve to real ids, but the header carries no
        matching `after` edge -- refuses `CHAIN_ROW_UNBACKED` naming the
        holder and the missing dependency."""
        header = {
            "section": "example", "position": 1,
            "blocks": [_block("first"), _block("second")],  # no `after` at all
        }
        body = self._body(b"| `example.second` | `example.first` |\n")
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "CHAIN_ROW_UNBACKED")
        self.assertIn("example.second", ctx.exception.detail)
        self.assertIn("example.first", ctx.exception.detail)

    def test_mutation_deleting_the_backing_after_entry_refuses_live(self) -> None:
        """`internal-chain-edges` spec's own "Mutation -- deleting a backing
        edge is caught" scenario: the check reads the LIVE edge set, never
        a cached result from the row's earlier presence."""
        first_backed = _block("second", after=[
            {"target": "example.first",
             "source": _quote_source("sections/01-example.md", "Prose.")},
        ])
        header = {"section": "example", "position": 1, "blocks": [_block("first"), first_backed]}
        body = self._body(b"| `example.second` | `example.first` |\n")
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        paper_graph.assemble_corpus(self.sections_dir)  # first, live parse: no refusal

        unbacked_header = {
            "section": "example", "position": 1,
            "blocks": [_block("first"), _block("second")],  # `after` entry removed
        }
        _write_section(self.sections_dir, "01-example.md", unbacked_header, body=body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)  # second, live parse: refuses

        self.assertEqual(ctx.exception.code, "CHAIN_ROW_UNBACKED")

    def test_corpus_wide_one_missing_edge_among_many_stops_the_run(self) -> None:
        """`internal-chain-edges` spec's own "One missing edge among many
        stops the run" scenario: nine of ten named dependencies backed,
        one not -- the run refuses on the one gap, and no order/readiness
        report is produced from the incomplete graph."""
        blocks = [_block("root")]
        for index in range(1, 10):
            backed = index != 9  # the 9th dependency (index 9) is left unbacked
            after = None
            if backed:
                after = [{
                    "target": f"example.b{index - 1}" if index > 1 else "example.root",
                    "source": _quote_source("sections/01-example.md", "Prose."),
                }]
            blocks.append(_block(f"b{index}", after=after))
        header = {"section": "example", "position": 1, "blocks": blocks}

        rows = []
        for index in range(1, 10):
            dependency = f"example.b{index - 1}" if index > 1 else "example.root"
            rows.append(f"| `example.b{index}` | `{dependency}` |\n".encode("utf-8"))
        body = self._body(b"".join(rows))
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "CHAIN_ROW_UNBACKED")
        self.assertIn("example.b9", ctx.exception.detail)

    def test_the_real_corpus_transcribes_every_internal_chain_row_with_no_refusal(self) -> None:
        """Task 4.11: `specs/section-contract/spec.md`'s shipped scenarios
        ("every edge quote-backed", "no row left unmapped") hold against
        the real corpus."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)  # must not raise
        self.assertEqual(len(corpus.sections), 10)

    def test_the_introductions_three_chain_rows_become_three_after_edges(self) -> None:
        """`the-methods-section-produces-the-contributions` re-measured this
        acid test: `block-2` <- `block-4b` retargets to `block-2` <-
        `materials-and-methods.mm-proposal` (`contributions`' sole producer
        moved there), `block-4b` gains its own new edge to that same
        producer, and `block-4a` <- `block-2` / `block-4a` <- `block-4b`
        stay exactly as before. Must not cycle."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        edge_set = paper_graph.collect_edges(corpus)
        pairs = {(before, after) for before, after, _source in edge_set.edges}

        self.assertIn(("materials-and-methods.mm-proposal", "introduction.block-2"), pairs)
        self.assertIn(("materials-and-methods.mm-proposal", "introduction.block-4b"), pairs)
        self.assertIn(("introduction.block-2", "introduction.block-4a"), pairs)
        self.assertIn(("introduction.block-4b", "introduction.block-4a"), pairs)

        order = paper_graph.derive_order(corpus, edge_set)  # must not raise ORDER_CYCLE
        index = {qid: i for i, qid in enumerate(order)}
        self.assertLess(index["materials-and-methods.mm-proposal"], index["introduction.block-2"])
        self.assertLess(index["materials-and-methods.mm-proposal"], index["introduction.block-4b"])
        self.assertLess(index["introduction.block-2"], index["introduction.block-4a"])
        self.assertLess(index["introduction.block-4b"], index["introduction.block-4a"])

    def test_related_works_closing_depends_on_problem_blocks_intra_node(self) -> None:
        """The acid test: `05`'s single row is `rw-closing` after
        `rw-problem-blocks` -- never a self-edge on the shared
        `rw-problem-blocks` id, which would be an `ORDER_CYCLE`."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        edge_set = paper_graph.collect_edges(corpus)
        pairs = {(before, after) for before, after, _source in edge_set.edges}

        self.assertIn(("related-work.rw-problem-blocks", "related-work.rw-closing"), pairs)
        self.assertNotIn(
            ("related-work.rw-problem-blocks", "related-work.rw-problem-blocks"), pairs,
        )

    def test_mm_preambles_internal_chain_becomes_a_real_edge(self) -> None:
        """Task 4.9: `mm-preamble`'s internal chain becomes a real edge --
        only edge existence is asserted here, never placement (unit 5's
        own concern)."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        edge_set = paper_graph.collect_edges(corpus)
        pairs = {(before, after) for before, after, _source in edge_set.edges}

        self.assertIn(
            ("materials-and-methods.mm-proposal", "materials-and-methods.mm-preamble"), pairs,
        )


class BlockSubunitTests(unittest.TestCase):
    """tasks.md 4.8b-4.8i: `_verify_block_subunits` (called from
    `paper_graph.assemble_corpus`) is the PROSE -> HEADER direction no
    existing check covers -- a numbered heading naming a sub-unit the
    front matter never declared."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def test_the_real_corpus_reports_zero_false_positives(self) -> None:
        """Task 4.8d, measured direction 1: the real corpus -- six
        unit-headings carry `###` children, five of them prose notes with
        no unit word, and only `06`'s `### Paragraph 4a`/`4b` match, both
        resolving to declared ids -- assembles with no refusal."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)  # must not raise
        self.assertIn("introduction.block-4a", corpus.blocks)
        self.assertIn("introduction.block-4b", corpus.blocks)

    def test_a_reintroduced_unit_word_child_with_no_matching_id_refuses(self) -> None:
        """Task 4.8d, measured direction 2: a fixture reintroducing
        `### Paragraph 5a` under `## Block 5` with no matching id refuses
        `BLOCK_SUBUNIT_UNDECLARED`."""
        header = {
            "section": "example", "position": 1,
            "blocks": [_block("block-5")],
        }
        body = (
            b"# Example\n\n## Block 5 -- Evaluation\n\n"
            b"### Paragraph 5a -- the setup.\n\nProse.\n\n"
            b"### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
        )
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "BLOCK_SUBUNIT_UNDECLARED")
        self.assertIn("Paragraph 5a", ctx.exception.detail)

    def test_mutation_collapsing_block_4a_4b_back_to_block_4_fires_the_guard(self) -> None:
        """Task 4.8e: RED-first mutation -- collapse `block-4a`/`block-4b`
        back to one `block-4` id in a fixture reproducing the real corpus's
        own heading shape, and confirm `BLOCK_SUBUNIT_UNDECLARED` fires --
        the guard must catch the EXACT anomaly that shipped unnoticed, not
        merely pass alongside it."""
        header = {
            "section": "example", "position": 1,
            "blocks": [_block("block-4")],  # collapsed: 4a/4b's split undone
        }
        body = (
            b"# Example\n\n## Block 4 -- Proposal and contributions\n\n"
            b"### Paragraph 4a -- the prose.\n\nProse.\n\n"
            b"### Paragraph 4b -- the list.\n\nProse.\n\n"
            b"### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
        )
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "BLOCK_SUBUNIT_UNDECLARED")

    def test_a_parent_heading_resolving_to_zero_ids_refuses(self) -> None:
        """A `## Block N` PARENT heading naming a number no declared id
        carries at all (not even a composite `Na`/`Nb` split -- that shape
        is `test_a_parent_heading_resolving_to_several_ids_...` below)
        refuses `BLOCK_SUBUNIT_UNDECLARED`."""
        header = {
            "section": "example", "position": 1,
            "blocks": [_block("block-1")],  # no id anywhere numbered "7"
        }
        body = (
            b"# Example\n\n## Block 7 -- Nothing declares this\n\nProse.\n\n"
            b"### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
        )
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "BLOCK_SUBUNIT_UNDECLARED")

    def test_a_parent_heading_resolving_to_a_composite_split_with_no_children_refuses(self) -> None:
        """Task 4.8g's own residue, reproduced directly: `## Block 4` with
        NO `###` children maps, under loose suffix matching, to BOTH
        `block-4a` and `block-4b` -- two ids, no explicit grouping in the
        heading text -- which this guard classifies `UNIT_HEADING_
        AMBIGUOUS`, the exact shape `06` carried before task 4.8g's fix
        named both ids in the heading itself."""
        header = {
            "section": "example", "position": 1,
            "blocks": [_block("block-4a"), _block("block-4b")],
        }
        body = (
            b"# Example\n\n## Block 4 -- Proposal and contributions\n\nProse.\n\n"
            b"### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
        )
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "UNIT_HEADING_AMBIGUOUS")

    def test_the_fixed_block_4_heading_names_both_ids_and_refuses_nothing(self) -> None:
        """Task 4.8g's own fix, reproduced directly: naming BOTH resolved
        ids in the parent heading itself is an explicit grouping, not
        ambiguous -- the real `06-introduction.md` heading shape today."""
        header = {
            "section": "example", "position": 1,
            "blocks": [_block("block-4a"), _block("block-4b")],
        }
        body = (
            b"# Example\n\n## Block 4 -- Proposal and contributions "
            b"(`block-4a`, `block-4b`)\n\nProse.\n\n"
            b"### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
        )
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        corpus = paper_graph.assemble_corpus(self.sections_dir)  # must not raise
        self.assertIn("example.block-4a", corpus.blocks)

    def test_a_parent_heading_resolving_to_several_ids_with_no_grouping_refuses_ambiguous(self) -> None:
        """Task 4.8h: a `##` PARENT heading resolving to more than one
        declared id, without naming every one of them in the heading text
        itself, refuses the new `UNIT_HEADING_AMBIGUOUS`."""
        header = {
            "section": "example", "position": 1,
            "blocks": [_block("block-4a"), _block("block-4b")],
        }
        body = (
            b"# Example\n\n## Block 4 -- Proposal and contributions, split in two\n\n"
            b"Prose.\n\n### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n"
        )
        _write_section(self.sections_dir, "01-example.md", header, body=body)

        with self.assertRaises(Refused) as ctx:
            paper_graph.assemble_corpus(self.sections_dir)

        self.assertEqual(ctx.exception.code, "UNIT_HEADING_AMBIGUOUS")

    def test_content_named_contracts_never_enter_either_branch(self) -> None:
        """Task 4.8i, measured direction: the check stays SILENT on the four
        content-named contracts (`03`, `04`, `09`, `10`) -- asserted
        against the real corpus, not merely a fixture, since those files'
        own numbered-LOOKING content (none, in fact) must never misfire."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)  # must not raise
        for section_id in ("results-and-discussion", "limitations",
                            "title-and-keywords", "back-matter"):
            self.assertFalse(
                paper_graph._section_uses_numbered_ids(corpus, section_id),
                f"{section_id}: expected content-named ids, no numbered convention",
            )

    def test_semantically_named_numbered_headings_never_misfire(self) -> None:
        """Correction to 4.8i's own stated gate (heading-pattern-based): `01`
        and `02` (and `05`) use `## Slot|Subsection|Block N` HEADINGS with
        semantically-named ids (`mm-dataset`, `es-assessment`) that carry no
        numeric suffix at all -- a naive heading-pattern gate would misfire
        `BLOCK_SUBUNIT_UNDECLARED` on `01`'s own `## Slot 1 -- The dataset`.
        Measured directly: the real corpus assembles cleanly, and `01`,
        `02`, `05` are confirmed NOT to use the numbered-id convention this
        check actually requires."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)  # must not raise
        for section_id in ("materials-and-methods", "experimental-setup", "related-work"):
            self.assertFalse(
                paper_graph._section_uses_numbered_ids(corpus, section_id),
                f"{section_id}: uses numbered HEADINGS but content-named ids",
            )


class OrderTests(unittest.TestCase):
    """`writing-readiness` spec: the derived writing order, and its
    distinctness from both filename order and rendering (`position`)
    order."""

    def test_order_is_deterministic_across_repeated_derivations(self) -> None:
        corpus_1 = paper_graph.assemble_corpus(SECTIONS_DIR)
        edges_1 = paper_graph.collect_edges(corpus_1)
        order_1 = paper_graph.derive_order(corpus_1, edges_1)

        corpus_2 = paper_graph.assemble_corpus(SECTIONS_DIR)
        edges_2 = paper_graph.collect_edges(corpus_2)
        order_2 = paper_graph.derive_order(corpus_2, edges_2)

        self.assertEqual(order_1, order_2)

    def test_rendering_order_differs_from_filename_order(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        # Rendering order: by `position` -- introduction (3) before
        # related-work (4), even though the filenames sort the other way
        # (06-introduction.md > 05-related-work.md).
        self.assertLess(corpus.sections["introduction"].position, corpus.sections["related-work"].position)
        filenames = sorted(p.name for p in SECTIONS_DIR.glob("*.md"))
        intro_filename_index = filenames.index("06-introduction.md")
        rw_filename_index = filenames.index("05-related-work.md")
        self.assertGreater(intro_filename_index, rw_filename_index)  # filename order disagrees

    def test_related_work_precedes_introduction_block_3_and_follows_blocks_1_2_4(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        edges = paper_graph.collect_edges(corpus)
        order = paper_graph.derive_order(corpus, edges)
        index = {qid: i for i, qid in enumerate(order)}

        for rw_block in corpus.order_by_section["related-work"]:
            self.assertLess(index["introduction.block-1"], index[rw_block])
            self.assertLess(index["introduction.block-2"], index[rw_block])
            self.assertLess(index["introduction.block-4a"], index[rw_block])
            self.assertLess(index["introduction.block-4b"], index[rw_block])
            self.assertLess(index[rw_block], index["introduction.block-3"])

    def test_back_matter_renders_last_while_its_writing_order_place_is_graph_derived_not_fact_derived(self) -> None:
        """`writing-readiness` spec, Requirement: Derived Writing Order,
        Scenario "Position reports rendering order separately from writing
        order". Back matter is the discriminating case: every one of its
        blocks requires zero facts, so a writing-order deriver that (wrongly)
        used readiness/fact-satisfaction as its ordering signal would place
        every back-matter block FIRST, ahead of anything still waiting on a
        fact -- back matter renders LAST (the highest `position` in the
        shipped corpus). This test pins both halves down: `position` is read
        directly off the header as a value separate from the derived order
        (rendering order), and the derived order does not place a
        zero-missing-facts block ahead of fact-blocked ones (writing order is
        graph-derived, not readiness-derived) -- back matter carries no
        CROSS-SECTION `after` edge, transcribed or position-derived, so
        nothing in another section's graph names it either. Unit 4
        (`internal-chain-edges`) transcribes back matter's own INTRA-section
        row (`bm-acknowledgments` after `bm-funding`), which constrains only
        the write order WITHIN back matter, never its render position
        relative to any other section -- measured below rather than
        re-asserting the pre-unit-4 "no edge at all" claim, which this row
        makes false."""
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)

        # Rendering order: back matter's own `position` is the maximum among
        # every shipped section -- a fact read straight off the header,
        # computed nowhere near the graph.
        self.assertEqual(
            corpus.sections["back-matter"].position,
            max(header.position for header in corpus.sections.values()),
        )

        # Back matter carries no CROSS-SECTION `after` edge anywhere --
        # section-level or block-level -- so nothing transcribed constrains
        # its place relative to another section, and it is not
        # `title-and-keywords` (the one section that receives a
        # position-derived edge). Its OWN intra-section row
        # (`bm-acknowledgments` after `bm-funding`) is permitted: it
        # reorders nothing across section boundaries.
        bm_header = corpus.sections["back-matter"]
        self.assertEqual(bm_header.after, [])
        for raw_block in bm_header.blocks:
            for entry in raw_block["after"]:
                self.assertTrue(
                    entry["target"].startswith("back-matter."),
                    f"{raw_block['id']}: after-edge target {entry['target']!r} "
                    "crosses out of back-matter -- only an intra-section edge "
                    "is expected here",
                )

        # Readiness: every back-matter block requires zero facts, so a
        # (wrong) fact-only ordering signal would rank every one of them
        # ahead of any block still waiting on a fact.
        readiness = paper_readiness.compute_readiness(
            corpus, satisfied_facts=set(), satisfied_declarations=set()
        )
        bm_qualified_ids = {r["block"] for r in readiness if r["block"].startswith("back-matter.")}
        self.assertTrue(bm_qualified_ids, "fixture assumption: back matter ships at least one block")
        for entry in readiness:
            if entry["block"] in bm_qualified_ids:
                self.assertEqual(entry["missing_facts"], [])

        fact_blocked_qualified_ids = {r["block"] for r in readiness if r["missing_facts"]}
        self.assertTrue(
            fact_blocked_qualified_ids,
            "fixture assumption: at least one shipped block still needs a fact",
        )

        # Writing order: derived from the graph. If readiness/fact-count
        # decided placement, every zero-missing-facts back-matter block would
        # land before every still-fact-blocked block above. It does not --
        # the graph, not readiness, decides.
        edges = paper_graph.collect_edges(corpus)
        order = paper_graph.derive_order(corpus, edges)
        index = {qid: i for i, qid in enumerate(order)}

        for bm_qid in bm_qualified_ids:
            for fact_blocked_qid in fact_blocked_qualified_ids:
                self.assertGreater(
                    index[bm_qid], index[fact_blocked_qid],
                    f"{bm_qid} (zero missing facts) landed before {fact_blocked_qid} (still fact-blocked) "
                    "in the writing order -- readiness, not the graph, appears to be deciding placement",
                )

    def test_a_two_block_mutual_after_cycle_refuses_order_cycle_naming_both(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp) / "sections"
            sections_dir.mkdir()
            _write_section(sections_dir, "01-a.md", {
                "section": "a", "position": 1,
                "blocks": [_block(
                    "x", after=[{"target": "b.y", "source": _quote_source("sections/01-a.md", "Prose.")}]
                )],
            })
            _write_section(sections_dir, "02-b.md", {
                "section": "b", "position": 2,
                "blocks": [_block(
                    "y", after=[{"target": "a.x", "source": _quote_source("sections/02-b.md", "Prose.")}]
                )],
            })

            corpus = paper_graph.assemble_corpus(sections_dir)
            edges = paper_graph.collect_edges(corpus)

            with self.assertRaises(Refused) as ctx:
                paper_graph.derive_order(corpus, edges)

            self.assertEqual(ctx.exception.code, "ORDER_CYCLE")
            self.assertIn("a.x", ctx.exception.detail)
            self.assertIn("b.y", ctx.exception.detail)

    def test_acyclic_synthetic_corpus_orders_without_refusing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sections_dir = Path(tmp) / "sections"
            sections_dir.mkdir()
            _write_section(sections_dir, "01-a.md", {
                "section": "a", "position": 1, "blocks": [_block("only")],
            })
            _write_section(sections_dir, "02-b.md", {
                "section": "b", "position": 2,
                "after": [{"target": "a", "source": _quote_source("sections/01-a.md", "Prose.")}],
                "blocks": [_block("only")],
            })

            corpus = paper_graph.assemble_corpus(sections_dir)
            edges = paper_graph.collect_edges(corpus)
            order = paper_graph.derive_order(corpus, edges)

            self.assertLess(order.index("a.only"), order.index("b.only"))


class OrderCliFrontDoorTests(unittest.TestCase):
    """`order`: `paper_cli.cmd_order`, the CLI front door a real caller
    actually dispatches through -- never `paper_graph.derive_order` called
    directly, which is all `OrderTests` above (and `test_paper_writing.py`)
    do, 21 times combined. That coverage proves `derive_order`'s ALGORITHM
    holds; it never once proves `cmd_order`'s own WIRING holds -- reading
    `args.sections`, resolving it, assembling the corpus, collecting
    edges, and shaping the `{"order", "danglingEdges"}` envelope `main()`
    prints. This is the exact shape `cmd_write` shipped with zero direct
    coverage until a missing phase gate survived an entire unit undetected
    (`the-writer-may-assert-only-what-it-was-given`, item 1) -- the FUNCTION
    was covered, the VERB was not."""

    def test_cmd_order_returns_the_order_and_dangling_edges_envelope_over_the_real_corpus(
        self,
    ) -> None:
        result = paper_cli.cmd_order(argparse.Namespace(sections=None))

        self.assertEqual(set(result.keys()), {"order", "danglingEdges"})
        self.assertEqual(result["danglingEdges"], [])
        index = {qid: i for i, qid in enumerate(result["order"])}
        # The same acid-test assertions `InternalChainTests.test_the_
        # introductions_three_chain_rows_become_three_after_edges` makes
        # against `derive_order`'s own return value -- made here against
        # `cmd_order`'s envelope instead, never against `derive_order`'s.
        # Re-measured by `the-methods-section-produces-the-contributions`:
        # `materials-and-methods.mm-proposal` (`contributions`' sole
        # producer) now precedes both `block-2` and `block-4b` directly.
        self.assertLess(index["materials-and-methods.mm-proposal"], index["introduction.block-2"])
        self.assertLess(index["materials-and-methods.mm-proposal"], index["introduction.block-4b"])
        self.assertLess(index["introduction.block-2"], index["introduction.block-4a"])
        self.assertLess(index["introduction.block-4b"], index["introduction.block-4a"])

    def test_cmd_order_propagates_a_cycle_refusal_from_a_fixture_corpus(self) -> None:
        """`cmd_order` must not swallow or reshape `derive_order`'s own
        refusal -- proven against a real `--sections` override, the
        argument name `cmd_order` actually reads off `args`. Lives under
        `implementations/` (gitignored scratch, containment-eligible),
        never a bare system tempdir: `resolve_sections_dir` refuses an
        out-of-repository `--sections` with `SECTIONS_OUTSIDE_REPOSITORY`
        before `assemble_corpus` ever runs, which would hide the very
        `ORDER_CYCLE` propagation this test exists to prove."""
        test_root = (
            FORGE_ROOT / "implementations"
            / f".paper-writing-order-cli-cycle-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, test_root, ignore_errors=True)
        sections_dir = test_root / "sections"
        sections_dir.mkdir(parents=True)
        _write_section(sections_dir, "01-a.md", {
            "section": "a", "position": 1,
            "blocks": [_block(
                "x", after=[{"target": "b.y", "source": _quote_source("sections/01-a.md", "Prose.")}]
            )],
        })
        _write_section(sections_dir, "02-b.md", {
            "section": "b", "position": 2,
            "blocks": [_block(
                "y", after=[{"target": "a.x", "source": _quote_source("sections/02-b.md", "Prose.")}]
            )],
        })

        with self.assertRaises(Refused) as ctx:
            paper_cli.cmd_order(argparse.Namespace(sections=str(sections_dir)))

        self.assertEqual(ctx.exception.code, "ORDER_CYCLE")

    def test_mutation_swapping_cmd_orders_own_attribute_name_fails_its_front_door_test(
        self,
    ) -> None:
        """RED-first, deliberate mutation: `derive_order`'s 21 existing
        tests call it directly with a `corpus`/`edge_set` pair they built
        themselves -- none of them would ever notice `cmd_order` reading
        the wrong argparse attribute off `args`, because none of them go
        through `cmd_order` at all. Mutating `args.sections` to
        `args.section` inside `cmd_order` itself proves THIS test's own
        `Namespace(sections=...)` call is what catches it: `AttributeError`,
        surfaced through `_run_against_mutant` as a failing dotted test,
        never a clean run -- the exact defect shape a direct front-door
        test exists to make impossible."""
        proc = _run_against_mutant(
            'def cmd_order(args: argparse.Namespace) -> dict:\n'
            '    sections_dir = paper_contract.resolve_sections_dir(args.sections)',
            'def cmd_order(args: argparse.Namespace) -> dict:\n'
            '    sections_dir = paper_contract.resolve_sections_dir(args.section)',
            "tests.test_paper_contract.OrderCliFrontDoorTests."
            "test_cmd_order_returns_the_order_and_dangling_edges_envelope_over_the_real_corpus",
            source_path=SKILL_SCRIPTS / "paper_cli.py",
        )
        _assert_mutant_test_failed(self, proc)


def _shipped_paper_cli_verbs() -> set[str]:
    """The verb roster `paper_cli.py`'s own `build_parser()` accepts --
    read from the live parser, never grepped or hand-listed, the same
    derivation `test_paper_writing.ObjectiveNorthTests.shipped_verbs`
    already uses for the identical reason: a renamed, removed, or freshly
    -added verb changes this set with zero edits here. This branch's own
    working tree is shared with other concurrent agent sessions on other
    branches; this function reads whatever `paper_cli.py` actually
    contains at call time on THIS branch's checkout, never a cached or
    hand-counted figure, which is exactly what let a mid-session sighting
    of an unrelated branch's own in-flight verbs (`reuse`, `exhaustion` --
    never part of this branch's history) get caught and corrected rather
    than silently pinned as if they were this branch's own gap."""
    parser = paper_cli.build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices.keys())
    raise AssertionError(
        "paper_cli.py's parser declares no subcommands -- build_parser()'s shape moved"
    )


#: The six `paper-writing` suites this task's own Verification section
#: names and counts (695 tests, six `python -m unittest` targets) -- the
#: scan scope for "does a verb have a front-door test", fixed to exactly
#: that roster rather than globbed, because a 7th `test_paper_*.py` file
#: can appear mid-session from unrelated concurrent work (`tests/
#: test_paper_lifecycle.py` did, while this item was in flight) without
#: that work's suite being part of what this task's baseline counts.
_PAPER_CLI_SUITE_FILES = (
    "test_paper_writing.py",
    "test_paper_citation.py",
    "test_paper_evidence.py",
    "test_paper_figure.py",
    "test_paper_contract.py",
    "test_paper_decisions.py",
)


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _cli_shelling_run_helper_names(tree: ast.Module) -> set[str]:
    """Every `_run` helper anywhere in this ONE module CONFIRMED, by
    walking its own body, to shell out to `paper_cli.py` as `subprocess.
    run([sys.executable, ...])` -- never assumed from the name alone, so a
    future `_run` meaning something unrelated is never read as front-door
    evidence. All four `_run` helpers across the six suites match this
    shape today (`test_paper_figure.CLIWiringTests._run`, `test_paper_
    writing.CLIWiringTests._run`, `test_paper_writing.<E2E>._run`, `test_
    paper_decisions.<E2E>._run`)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_run":
            dumped = ast.dump(node)
            if "subprocess" in dumped and "executable" in dumped:
                names.add(node.name)
    return names


def _front_door_verbs_in_file(path: Path) -> set[str]:
    """Every verb ONE test file exercises through a front door this
    repository's own tests already recognize as one: `paper_cli.cmd_<verb>
    (...)` (`test_paper_decisions.CouplingsCliTests`'s own docstring calls
    this exactly "the ... front door"), `paper_cli.main([<verb>, ...])`
    (the real argparse dispatch), a confirmed CLI-shelling `self._run(
    <verb>, ...)` helper, or a raw `subprocess.run([..., <a path ending in
    paper_cli.py>, <verb>, ...])` call with no `_run` wrapper.

    AST-based, never a flat-text grep: this repository's own calls wrap
    across lines (`subprocess.run(\\n    [sys.executable, str(CLI), *args]`
    is the shipped shape in every `_run` helper), and a flat-text search
    for `subprocess.run([sys.executable` reads a real call as an absence
    that is not there -- the same SEARCH TRAP this change's own brief
    warns about for contract prose, equally real for source text.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    run_like = _cli_shelling_run_helper_names(tree)
    verbs: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr.startswith("cmd_"):
            verbs.add(func.attr[len("cmd_"):])
            continue
        if (isinstance(func, ast.Attribute) and func.attr == "main") or (
            isinstance(func, ast.Name) and func.id == "main"
        ):
            if node.args and isinstance(node.args[0], (ast.List, ast.Tuple)) and node.args[0].elts:
                verb = _string_constant(node.args[0].elts[0])
                if verb:
                    verbs.add(verb)
            continue
        if isinstance(func, ast.Attribute) and func.attr in run_like:
            if node.args:
                verb = _string_constant(node.args[0])
                if verb:
                    verbs.add(verb)
            continue
        if (
            isinstance(func, ast.Attribute) and func.attr == "run"
            and isinstance(func.value, ast.Name) and func.value.id == "subprocess"
        ):
            if node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
                elts = node.args[0].elts
                cli_index = None
                for i, elt in enumerate(elts):
                    try:
                        rendered = ast.unparse(elt)
                    except Exception:
                        continue
                    if "paper_cli.py" in rendered:
                        cli_index = i
                        break
                if cli_index is not None and cli_index + 1 < len(elts):
                    verb = _string_constant(elts[cli_index + 1])
                    if verb:
                        verbs.add(verb)
    return verbs


#: Verbs `_front_door_verbs_in_file` measures as uncovered across the six
#: `paper-writing` suites, pinned explicitly and dated -- the way `paper_
#: cli.REFUSAL_CLASSIFICATION` pins every reachable code by name rather
#: than leaving an unclassified one to read as covered by omission. A verb
#: leaves this set only by gaining a real front-door test in one of the
#: six suites; a verb enters it only by a deliberate, measured edit here.
#:
#: - `bib` (2026-09-19, measured on this branch, base `7b91bc5`, 22 shipped
#:   verbs): `paper_bib.build_refs_bib` and `cmd_bib`'s own `reciprocal`
#:   check are exercised directly (`test_paper_evidence.py`, `test_paper_
#:   writing.py`), but nothing calls `paper_cli.cmd_bib`, `paper_cli.main(
#:   ["bib", "build", ...])`, or shells out to `paper_cli.py bib build` in
#:   any of the six suites -- out of this item's scope (tests only;
#:   `scripts/*.py` belongs to another agent).
_KNOWN_UNCOVERED_PAPER_CLI_VERBS = frozenset({"bib"})


class VerbFrontDoorCoverageTests(unittest.TestCase):
    """Item 1's general guard: `cmd_order` shipped with zero direct tests
    while `derive_order` carried 21 across two suites -- the FUNCTION was
    covered, the VERB was not, the exact shape `cmd_write` shipped with
    until a missing phase gate survived an entire unit undetected. This
    class holds every CURRENT and FUTURE `paper_cli.py` verb to the same
    bar, derived from `build_parser()` itself, never a hand-listed tuple:
    `COMMANDS` already drifted from this module's own docstring once (the
    docstring's own prose enumeration never mentions `couplings`, though
    `build_parser()` and `COMMANDS` both ship it) -- a second hand-kept
    roster here would be exactly that failure mode again."""

    def _tested_verbs(self) -> set[str]:
        tested: set[str] = set()
        for name in _PAPER_CLI_SUITE_FILES:
            tested |= _front_door_verbs_in_file(FORGE_ROOT / "tests" / name)
        return tested

    def test_every_shipped_verb_has_a_front_door_test_or_a_pinned_gap(self) -> None:
        shipped = _shipped_paper_cli_verbs()
        uncovered = shipped - self._tested_verbs()
        unpinned = sorted(uncovered - _KNOWN_UNCOVERED_PAPER_CLI_VERBS)
        self.assertEqual(
            unpinned, [],
            f"{unpinned} ship in paper_cli.py's own parser roster with no front-door "
            "test in any of the six suites and no pinned, dated entry in "
            "_KNOWN_UNCOVERED_PAPER_CLI_VERBS explaining why -- either add a direct "
            "test or pin the gap deliberately, the way REFUSAL_CLASSIFICATION pins "
            "its own")

    def test_the_pinned_gap_list_carries_nothing_already_covered(self) -> None:
        shipped = _shipped_paper_cli_verbs()
        uncovered = shipped - self._tested_verbs()
        stale = sorted(_KNOWN_UNCOVERED_PAPER_CLI_VERBS - uncovered)
        self.assertEqual(
            stale, [],
            f"{stale} are pinned as uncovered gaps but a front-door test for them "
            "exists in the six suites now -- shrink the backlog instead of leaving "
            "a stale pin standing")

    def test_the_pinned_gap_list_names_only_verbs_paper_cli_still_ships(self) -> None:
        shipped = _shipped_paper_cli_verbs()
        stray = sorted(_KNOWN_UNCOVERED_PAPER_CLI_VERBS - shipped)
        self.assertEqual(
            stray, [],
            f"{stray} are pinned as uncovered verbs but paper_cli.py ships no such "
            "verb -- a removed verb's pin must be removed with it")

    def test_the_ast_scanner_recognizes_a_synthetic_front_door_call_and_nothing_else(
        self,
    ) -> None:
        """Prove the scanner is not a rubber stamp: a synthetic file
        calling `paper_cli.cmd_scaffold(...)` is read as covering
        `scaffold` and nothing else; one calling nothing paper_cli-shaped
        covers nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            covering = Path(tmp) / "covering.py"
            covering.write_text(
                "import paper_cli\n\n\ndef test_x():\n    paper_cli.cmd_scaffold(object())\n",
                encoding="utf-8",
            )
            self.assertEqual(_front_door_verbs_in_file(covering), {"scaffold"})

            empty = Path(tmp) / "empty.py"
            empty.write_text("def test_y():\n    pass\n", encoding="utf-8")
            self.assertEqual(_front_door_verbs_in_file(empty), set())

    def test_the_guard_itself_goes_red_when_a_real_gap_is_unpinned(self) -> None:
        """RED-first proof for this guard's OWN logic (never `_run_
        against_mutant`, which mutates `scripts/*.py` -- this guard's own
        defect surface is the pin list and the AST scanner, both living in
        this test file, not in any mutable script). Reproduce the exact
        completeness check with `bib` deliberately dropped from the pinned
        set and confirm it reports `bib` as an unpinned gap -- proof this
        guard genuinely distinguishes a pinned gap from an unpinned one,
        rather than always reporting `[]` regardless of input."""
        shipped = _shipped_paper_cli_verbs()
        uncovered = shipped - self._tested_verbs()
        self.assertIn("bib", uncovered, "bib is expected to still be a real, measured gap")

        reduced_pins = _KNOWN_UNCOVERED_PAPER_CLI_VERBS - {"bib"}
        unpinned = sorted(uncovered - reduced_pins)
        self.assertIn("bib", unpinned)


class ReadinessTests(unittest.TestCase):
    """`writing-readiness` spec: per-block `writable`/`blocked`, and the
    case a facts-only check gets wrong."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sections_dir = Path(self._tmp.name) / "sections"
        self.sections_dir.mkdir()

    def test_a_block_with_every_requirement_satisfied_is_writable(self) -> None:
        _write_section(self.sections_dir, "01-a.md", {
            "section": "a", "position": 1,
            "blocks": [_block("only", facts=[_fact_entry("dataset", "sections/01-a.md")])],
        }, body=b"Prose. This block requires the dataset.\n\n"
                b"### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n")
        corpus = paper_graph.assemble_corpus(self.sections_dir)

        report = paper_readiness.compute_readiness(corpus, satisfied_facts={"dataset"}, satisfied_declarations=set())

        entry = next(r for r in report if r["block"] == "a.only")
        self.assertEqual(entry["status"], "writable")
        self.assertEqual(entry["missing_facts"], [])
        self.assertEqual(entry["missing_declarations"], [])

    def test_a_block_blocked_only_by_a_declaration_is_not_writable(self) -> None:
        _write_section(self.sections_dir, "01-a.md", {
            "section": "a", "position": 1,
            "blocks": [_block(
                "only",
                facts=[_fact_entry("dataset", "sections/01-a.md")],
                declarations=[_fact_entry("repository-url", "sections/01-a.md")],
            )],
        }, body=b"Prose. This block requires the dataset. "
                b"This block requires the repository-url.\n\n"
                b"### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n")
        corpus = paper_graph.assemble_corpus(self.sections_dir)

        report = paper_readiness.compute_readiness(
            corpus, satisfied_facts={"dataset"}, satisfied_declarations=set()
        )

        entry = next(r for r in report if r["block"] == "a.only")
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["missing_facts"], [])
        self.assertEqual(entry["missing_declarations"], ["repository-url"])

    def test_back_matter_reports_zero_missing_facts_and_its_declarations_missing(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)

        report = paper_readiness.compute_readiness(corpus, satisfied_facts=set(), satisfied_declarations=set())

        bm_entries = [r for r in report if r["block"].startswith("back-matter.")]
        self.assertGreater(len(bm_entries), 0)
        for entry in bm_entries:
            self.assertEqual(entry["missing_facts"], [])
            if entry["missing_declarations"]:
                self.assertEqual(entry["status"], "blocked")


def _reader_source_digest() -> str:
    """sha256 over every `.py` file the reader ships, concatenated in a
    fixed order. Asserted equal before and after a mutation subprocess run
    (design.md's Mutation A: "digest-asserting the reader's own source is
    unchanged before and after") -- a mutation that patched the reader's own
    disk copy instead of exercising it through a fixture would move this."""
    hasher = hashlib.sha256()
    for name in ("paper_vocabulary.py", "paper_contract.py", "paper_graph.py",
                 "paper_readiness.py", "paper_cli.py"):
        hasher.update((SKILL_SCRIPTS / name).read_bytes())
    return hasher.hexdigest()


def _section_graph_shape(corpus, section_id: str) -> tuple:
    """The graph-shape axis `writing-readiness`'s Mutation A anti-vacuity
    check uses: whether `section_id` carries BOTH a section-level and a
    block-level `after`, and whether any of its `after` entries targets a
    section or block positioned EARLIER than the holder itself. Derived
    from the corpus, never hand-asserted."""
    header = corpus.sections[section_id]
    has_section_after = bool(header.after)
    has_block_after = any(block["after"] for block in header.blocks)
    has_both = has_section_after and has_block_after

    def target_position(target_id):
        if target_id in corpus.sections:
            return corpus.sections[target_id].position
        if target_id in corpus.blocks:
            return corpus.blocks[target_id].position
        return None

    entries = list(header.after)
    for block in header.blocks:
        entries += block["after"]

    has_earlier_target = any(
        (pos := target_position(entry["target"])) is not None and pos < header.position
        for entry in entries
    )

    return (has_both, has_earlier_target)


class MutationTests(unittest.TestCase):
    """`writing-readiness` spec: the two executed mutations that prove the
    reader generalizes with zero code changes -- Requirement: Eleventh
    Contract Enters With No Code Change, and Requirement: A Fact Outside
    the Ten Refuses."""

    def test_mutation_a_the_eleventh_contract_is_novel_and_reads_correctly(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)

        used_fact_shapes = {frozenset(block.requires_facts) for block in corpus.blocks.values()}
        used_graph_shapes = {_section_graph_shape(corpus, sid) for sid in corpus.sections}

        eleventh_facts = frozenset({"skeleton", "gap"})
        # Both a section-level and a block-level `after`, at least one
        # targeting an EARLIER section -- `(False, True)` alone stopped
        # being novel once `a-fact-is-declared-or-it-is-produced` unit 2
        # gave several real sections a backward producer-reachability edge.
        eleventh_graph_shape = (True, True)

        self.assertNotIn(
            eleventh_facts, used_fact_shapes,
            "the fixture's fact combination is already shipped -- it proves round-tripping, not generality",
        )
        self.assertNotIn(
            eleventh_graph_shape, used_graph_shapes,
            "the fixture's graph shape is already shipped -- it proves round-tripping, not generality",
        )

        test_root = FORGE_ROOT / "implementations" / f".paper-contract-mutation-a-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, test_root, ignore_errors=True)
        temp_sections = test_root / "sections"
        temp_sections.mkdir(parents=True)
        for path in SECTIONS_DIR.glob("*.md"):
            (temp_sections / path.name).write_bytes(path.read_bytes())

        eleventh_body = (
            b"This appendix is written after the title is fixed, because its examples quote it. "
            b"This appendix also follows the abstract, because it elaborates a claim made there. "
            b"This block requires the skeleton. This block requires the gap.\n\n"
            b"### External inputs\n\nNone.\n\n### Internal chain\n\n"
            b"| Block | Depends on |\n|---|---|\n"
            b"| `supplementary-notes.only` \xe2\x80\x94 requires the gap | "
            b"`related-work.rw-closing` \xe2\x80\x94 the joint gap, one of its two corroborated producers |\n"
            b"| `supplementary-notes.only` \xe2\x80\x94 requires the gap | "
            b"`introduction.block-3` \xe2\x80\x94 the joint gap, its other corroborated producer |\n"
        )
        _write_section(
            temp_sections, "11-supplementary-notes.md",
            {
                "section": "supplementary-notes", "position": 11,
                # Section-level AND block-level `after`, both targeting an
                # earlier section -- `_section_graph_shape`'s (True, True)
                # shape, novel against the shipped corpus even after
                # `a-fact-is-declared-or-it-is-produced` unit 2 introduced
                # several (False, True) sections (a producer-reachability
                # edge to an earlier-positioned section, e.g.
                # `experimental-setup` -> `introduction.block-3`).
                "after": [{
                    "target": "abstract",
                    "source": {
                        "file": "sections/11-supplementary-notes.md",
                        "quote": "This appendix also follows the abstract, because it elaborates a claim made there.",
                    },
                }],
                "blocks": [_block(
                    "only", facts=[
                        _fact_entry("skeleton", "sections/11-supplementary-notes.md"),
                        _fact_entry("gap", "sections/11-supplementary-notes.md"),
                    ],
                    after=[
                        {
                            "target": "title-and-keywords",
                            "source": {
                                "file": "sections/11-supplementary-notes.md",
                                "quote": "This appendix is written after the title is fixed, because its examples quote it.",
                            },
                        },
                        # `contract-input-partition` spec, `Requirement: A
                        # Produced-Fact Dependency Is An Internal-Chain
                        # Row`: `gap`'s two corroborated producers
                        # (`related-work.rw-closing`, `introduction.block-3`)
                        # both need a direct edge here, backing the two
                        # rows this fixture's own `### Internal chain` adds
                        # below -- reusing the same requires_facts quote,
                        # the same pattern the real corpus's own added
                        # edges (tasks.md 2.4) use.
                        {
                            "target": "related-work.rw-closing",
                            "source": {
                                "file": "sections/11-supplementary-notes.md",
                                "quote": "This block requires the gap.",
                            },
                        },
                        {
                            "target": "introduction.block-3",
                            "source": {
                                "file": "sections/11-supplementary-notes.md",
                                "quote": "This block requires the gap.",
                            },
                        },
                    ],
                )],
            },
            body=eleventh_body,
        )

        pre_digest = _reader_source_digest()
        proc = subprocess.run(
            [sys.executable, str(SKILL_SCRIPTS / "paper_cli.py"), "readiness",
             "--sections", str(temp_sections), "--fact", "skeleton", "--fact", "gap"],
            capture_output=True, text=True, timeout=30,
        )
        post_digest = _reader_source_digest()

        self.assertEqual(pre_digest, post_digest, "the reader's own source changed during the mutation run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        entry = next(b for b in payload["blocks"] if b["block"] == "supplementary-notes.only")
        self.assertEqual(entry["status"], "writable")

    def test_mutation_b_a_fact_outside_the_vocabulary_refuses_on_execution(self) -> None:
        test_root = FORGE_ROOT / "implementations" / f".paper-contract-mutation-b-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, test_root, ignore_errors=True)
        sections_dir = test_root / "sections"
        sections_dir.mkdir(parents=True)
        _write_section(sections_dir, "01-bad.md", {
            "section": "bad", "position": 1,
            "blocks": [_block("only", facts=[{"value": "discussion", "source": None}])],
        })

        proc = subprocess.run(
            [sys.executable, str(SKILL_SCRIPTS / "paper_cli.py"), "readiness", "--sections", str(sections_dir)],
            capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(proc.returncode, 2, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "UNKNOWN_FACT")
        self.assertIn("discussion", payload["detail"])


class VocabularyLeakTests(unittest.TestCase):
    """Forge leak guard: `FORGE_VOCABULARY_FLOOR` must never appear in any
    file this skill ships. `transfer` sits on it and `09-title-and-
    keywords.md`'s own prose uses it ("the work does not transfer beyond
    it") -- that sentence lives in `sections/`, which `shipped_documents()`
    never reaches, but nothing newly written under
    `skills/paper-writing/` may quote it (design.md, `What
    Breaks`)."""

    def test_no_shipped_paper_writing_document_leaks_the_forge_vocabulary_floor(self) -> None:
        skill_root = FORGE_ROOT / "skills" / "paper-writing"
        documents = forge_vocabulary.shipped_documents(skill_root)
        self.assertGreater(len(documents), 0, "no shipped documents found under paper-writing -- scan is broken")

        leaking = {}
        for document in documents:
            text = document.read_text(encoding="utf-8")
            if document.suffix == ".py":
                text = forge_vocabulary.scannable_suite_text(text)
            hits = forge_vocabulary.leaks_in(text)
            if hits:
                leaking[str(document.relative_to(FORGE_ROOT))] = hits

        self.assertEqual(leaking, {})


class DatasetForkAndProposalFactsTests(unittest.TestCase):
    """`the-phases-are-derived-not-remembered`, Phase 2: `es-dataset` is the
    missing branch of the dataset-placement fork (mirroring `mm-dataset`),
    every `rw-*` block is `optional: true` (Open Question 1, block-level,
    no schema change), and `mm-proposal` depends only on `formulation` --
    `implementation` was an over-demand `01-materials-and-methods.md`'s own
    Inputs table never made (it names `implementation` only for the narrow
    "correct reading of an ambiguous equation" role)."""

    def test_es_dataset_mirrors_mm_dataset(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        es_dataset = corpus.blocks["experimental-setup.es-dataset"]
        mm_dataset = corpus.blocks["materials-and-methods.mm-dataset"]
        self.assertTrue(es_dataset.optional)
        self.assertEqual(es_dataset.requires_facts, ("dataset",))
        self.assertEqual(es_dataset.optional, mm_dataset.optional)
        self.assertEqual(es_dataset.requires_facts, mm_dataset.requires_facts)

    def test_every_related_work_block_is_optional(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        rw_blocks = corpus.order_by_section["related-work"]
        self.assertEqual(len(rw_blocks), 5)
        for qualified_id in rw_blocks:
            self.assertTrue(corpus.blocks[qualified_id].optional, qualified_id)

    def test_mm_proposal_depends_only_on_the_formulation(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS_DIR)
        mm_proposal = corpus.blocks["materials-and-methods.mm-proposal"]
        self.assertEqual(mm_proposal.requires_facts, ("formulation",))
        self.assertNotIn("implementation", mm_proposal.requires_facts)


if __name__ == "__main__":
    unittest.main()
