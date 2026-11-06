"""no-claim-without-a-source-that-holds-it: WU1 (the evidence channel) and
WU2 (the bibliography that was never typed).

Same shape `tests/test_paper_contract.py` and `tests/test_paper_writing.py`
already use: every fixture lives under a `TemporaryDirectory`, `setUp`
installs a raising `OPENER` module-wide so an accidental live network call
fails loudly instead of passing slowly, and the mutation tests reuse
`_run_against_mutant` from `tests/paper_mutation.py`.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
SECTIONS_DIR = FORGE_ROOT / "sections"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_cli  # noqa: E402
import paper_bib  # noqa: E402
import paper_evidence  # noqa: E402
import paper_full_text  # noqa: E402
import paper_resolve  # noqa: E402
import paper_scaffold  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_mutation import _run_against_mutant  # noqa: E402


class _RaisingOpener:
    """The module-level `OPENER` seam (`design.md`, Decision 3, Test seam):
    every request this fakes raises `URLError` with no socket ever touched,
    proving the offline refusal path with zero live network access."""

    def open(self, request, timeout=None):  # noqa: A003 -- mirrors OpenerDirector.open
        raise urllib.error.URLError("test seam: network is not reachable")


class _AnsweringOpener:
    """Returns a fixed byte payload for any request -- used to prove the
    guard is NOT firing when the transport genuinely answers."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def open(self, request, timeout=None):
        return _FakeResponse(self._payload)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _NotFoundOpener:
    def open(self, request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)


def _config(resolution=("openalex",), discovery=(), contact="") -> dict:
    return {
        "paper_writing": {
            "contact": contact,
            "roles": {
                "discovery": list(discovery),
                "resolution": list(resolution),
                "full-text": [],
            },
        }
    }


class VerdictConstructionTests(unittest.TestCase):
    """design.md Decision 2: `Verdict` has no public string-taking
    constructor; `.holds`/`.does_not_hold` require a real span
    positionally, and only `.insufficient` can be built without one."""

    def test_holds_requires_a_span_positionally(self) -> None:
        with self.assertRaises(TypeError):
            paper_evidence.Verdict.holds()  # type: ignore[call-arg]

    def test_does_not_hold_requires_a_span_positionally(self) -> None:
        with self.assertRaises(TypeError):
            paper_evidence.Verdict.does_not_hold()  # type: ignore[call-arg]

    def test_no_public_string_taking_constructor_exists(self) -> None:
        with self.assertRaises(TypeError):
            paper_evidence.Verdict(value="holds", span=None, reason=None)

    def test_holds_with_none_span_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_evidence.Verdict.holds(None)
        self.assertEqual(ctx.exception.code, "VERDICT_SPAN_REQUIRED")

    def test_insufficient_needs_no_span(self) -> None:
        verdict = paper_evidence.Verdict.insufficient("no source located")
        self.assertEqual(verdict.value, "insufficient")
        self.assertIsNone(verdict.span)


class EvidenceSpanTests(unittest.TestCase):
    """`EvidenceSpan.locate` byte-searches the ingested `.md`; a quote not
    literally present refuses `SPAN_NOT_IN_SOURCE` rather than becoming a
    span (`evidence-set`, Requirement: A Spanless Record Is Insufficient By
    Construction)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_locate_finds_the_verbatim_quote(self) -> None:
        source = self.root / "ingested.md"
        source.write_text("The estimator converges under bounded variance.\n", encoding="utf-8")
        span = paper_evidence.EvidenceSpan.locate(source, "converges under bounded variance")
        self.assertEqual(span.byte_start, source.read_bytes().find(b"converges under bounded variance"))
        self.assertEqual(span.byte_end - span.byte_start, len("converges under bounded variance"))
        self.assertTrue(span.file_sha256)

    def test_a_paraphrase_refuses_span_not_in_source(self) -> None:
        source = self.root / "ingested.md"
        source.write_text("The estimator converges under bounded variance.\n", encoding="utf-8")
        with self.assertRaises(Refused) as ctx:
            paper_evidence.EvidenceSpan.locate(source, "the estimator always converges")
        self.assertEqual(ctx.exception.code, "SPAN_NOT_IN_SOURCE")

    def test_a_span_authored_to_look_right_but_not_byte_identical_refuses(self) -> None:
        # One character off from a real sentence in the source -- looks
        # right to a human skim, is not byte-identical (design.md, Decision
        # 7b: "a fixture and a span authored together still have to agree
        # byte-for-byte or SPAN_NOT_IN_SOURCE fires").
        source = self.root / "ingested.md"
        source.write_text("The dataset contains 4,096 labeled examples.\n", encoding="utf-8")
        near_miss = "The dataset contains 4,095 labeled examples."
        self.assertNotIn(near_miss, source.read_text(encoding="utf-8"))
        with self.assertRaises(Refused) as ctx:
            paper_evidence.EvidenceSpan.locate(source, near_miss)
        self.assertEqual(ctx.exception.code, "SPAN_NOT_IN_SOURCE")

    def test_empty_quote_refuses(self) -> None:
        source = self.root / "ingested.md"
        source.write_text("non-empty content\n", encoding="utf-8")
        with self.assertRaises(Refused) as ctx:
            paper_evidence.EvidenceSpan.locate(source, "")
        self.assertEqual(ctx.exception.code, "SPAN_NOT_IN_SOURCE")

    def test_domain_independent_fixture_a_pre_existing_repository_document(self) -> None:
        # design.md, Decision 7c / Testing Strategy leg 3: one fixture
        # nobody wrote for this test -- a verbatim excerpt of a repository
        # document that predates the validator. README.md is prose about
        # this repository's own tooling, not a science paper: it proves
        # independence of AUTHORSHIP (this quote was not shaped to pass),
        # never independence of DOMAIN. That limit is stated here, not
        # silently assumed.
        #
        # The quote moved once, when the README was rewritten to document
        # nine skills instead of five and its opening paragraph went with
        # it. The replacement is deliberately taken from a section that
        # rewrite did NOT touch: a line authored for this test, or authored
        # in the same pass that fixed it, would still be verbatim and would
        # no longer be independent of authorship, which is the whole of
        # what this fixture proves.
        #
        # It moved a second time when the README was translated to English:
        # the same table row, translated in that pass, not written for this
        # test.
        readme = FORGE_ROOT / "README.md"
        self.assertTrue(readme.is_file(), "README.md must exist for this fixture to mean anything")
        quote = "**Guide papers** — the methodological / style references."
        span = paper_evidence.EvidenceSpan.locate(readme, quote)
        self.assertEqual(span.quote, quote)


class AdversarialPairingTests(unittest.TestCase):
    """design.md, Testing Strategy leg 1: the SAME bytes must be able to
    produce `holds` for one claim and `does-not-hold` for another -- proving
    the mechanism does not silently collapse every verdict to one pole. An
    author who shaped the source to satisfy the matcher would make the
    `does-not-hold` claim pass too; it does not, because the verdict is the
    caller's own judgment against a real, located span, never derived from
    the quote's mere presence."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.source = Path(self._tmp.name) / "ingested.md"
        self.source.write_text(
            "The proposed estimator achieves a 12% reduction in test error "
            "on the benchmark suite. The baseline model was not evaluated "
            "on out-of-distribution inputs in this study.\n",
            encoding="utf-8",
        )

    def test_claim_a_holds_from_its_own_verbatim_span(self) -> None:
        span = paper_evidence.EvidenceSpan.locate(
            self.source, "achieves a 12% reduction in test error"
        )
        verdict = paper_evidence.Verdict.holds(span)
        self.assertEqual(verdict.value, "holds")
        self.assertEqual(verdict.span.source_md, str(self.source))

    def test_claim_b_does_not_hold_from_a_real_but_unsupporting_span(self) -> None:
        # The claim under test: "the baseline WAS evaluated on
        # out-of-distribution inputs" -- the located span is real (it is in
        # the file, byte for byte) but it says the opposite, so the caller
        # (standing in for the agent's own judgment) records does-not-hold.
        span = paper_evidence.EvidenceSpan.locate(
            self.source, "was not evaluated on out-of-distribution inputs"
        )
        verdict = paper_evidence.Verdict.does_not_hold(span)
        self.assertEqual(verdict.value, "does-not-hold")
        self.assertIsNotNone(verdict.span)


class EvidenceRecordStoreTests(unittest.TestCase):
    """`evidence-set`, Requirement: The Claim<->Source Record Shape, and the
    JSONL store at `paper/.paper-writing/evidence/<block-id>.jsonl`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.paper_dir.mkdir()
        self.source = Path(self._tmp.name) / "quote.md"
        self.source.write_text("Training used 30 random seeds per configuration.\n", encoding="utf-8")

    def test_a_complete_record_round_trips_through_the_store(self) -> None:
        span = paper_evidence.EvidenceSpan.locate(self.source, "30 random seeds per configuration")
        verdict = paper_evidence.Verdict.holds(span)
        record = paper_evidence.EvidenceRecord.from_verdict(
            block_id="results.main-claim", regime="discovery", claim="30 seeds were used",
            cite_key="smith2024", identifier="10.1/example", resolver="openalex",
            metadata_digest="abc123", verdict=verdict, round=1,
        )
        paper_evidence.append_record(self.paper_dir, record)
        stored = paper_evidence.read_records(self.paper_dir, "results.main-claim")
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["verdict"], "holds")
        self.assertEqual(stored[0]["quote"], "30 random seeds per configuration")
        self.assertTrue(stored[0]["locator"]["file_sha256"])
        self.assertEqual(stored[0]["claim"], "30 seeds were used")

    def test_a_spanless_record_carries_empty_span_fields(self) -> None:
        verdict = paper_evidence.Verdict.insufficient("no candidate source found")
        record = paper_evidence.EvidenceRecord.from_verdict(
            block_id="results.main-claim", regime="none", claim="unsupported claim",
            cite_key="", identifier="", resolver="", metadata_digest="",
            verdict=verdict, round=1,
        )
        self.assertEqual(record.source_md, "")
        self.assertEqual(record.quote, "")
        self.assertEqual(record.locator, {})

    def test_reading_an_unwritten_block_returns_empty(self) -> None:
        self.assertEqual(paper_evidence.read_records(self.paper_dir, "never-written"), [])

    def test_multiple_appends_accumulate_in_order(self) -> None:
        for round_number in (1, 2):
            verdict = paper_evidence.Verdict.insufficient(f"round {round_number}")
            record = paper_evidence.EvidenceRecord.from_verdict(
                block_id="b", regime="none", claim="c", cite_key="", identifier="",
                resolver="", metadata_digest="", verdict=verdict, round=round_number,
            )
            paper_evidence.append_record(self.paper_dir, record)
        stored = paper_evidence.read_records(self.paper_dir, "b")
        self.assertEqual([r["round"] for r in stored], [1, 2])


class ManifestProducerTests(unittest.TestCase):
    """`evidence-set`, Requirement: Evidence Folders Carry a Producer-
    Written Manifest -- `append_record` marks the guidance folder its span's
    source sits under, the real production caller of `write_evidence_manifest`
    (never a second, test-only write path)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.paper_dir = self.root / "paper"
        self.paper_dir.mkdir()
        self.guidance_dir = self.root / "guidance"
        self.folder = self.guidance_dir / "06-introduction"
        self.folder.mkdir(parents=True)
        self.source = self.folder / "paper1.md"
        self.source.write_text("A verbatim sentence about the field.\n", encoding="utf-8")

    def test_appending_a_record_with_a_real_span_marks_its_guidance_folder(self) -> None:
        span = paper_evidence.EvidenceSpan.locate(self.source, "verbatim sentence about the field")
        verdict = paper_evidence.Verdict.holds(span)
        record = paper_evidence.EvidenceRecord.from_verdict(
            block_id="intro.claim", regime="discovery", claim="claim text", cite_key="paper1",
            identifier="10.1/x", resolver="openalex", metadata_digest="d", verdict=verdict, round=1,
        )
        paper_evidence.append_record(self.paper_dir, record, guidance_dir=self.guidance_dir)
        manifest_path = self.folder / ".papersmith-evidence.json"
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["kind"], "evidence")
        self.assertEqual(manifest["section"], "06-introduction")
        self.assertIn("paper1", manifest["blocks"])

    def test_an_insufficient_record_marks_nothing(self) -> None:
        verdict = paper_evidence.Verdict.insufficient("nothing located")
        record = paper_evidence.EvidenceRecord.from_verdict(
            block_id="intro.claim", regime="discovery", claim="claim text", cite_key="paper1",
            identifier="", resolver="", metadata_digest="", verdict=verdict, round=1,
        )
        paper_evidence.append_record(self.paper_dir, record, guidance_dir=self.guidance_dir)
        self.assertFalse((self.folder / ".papersmith-evidence.json").exists())

    def test_a_source_outside_guidance_dir_marks_nothing_and_never_refuses(self) -> None:
        outside = self.root / "elsewhere.md"
        outside.write_text("some text\n", encoding="utf-8")
        span = paper_evidence.EvidenceSpan.locate(outside, "some text")
        verdict = paper_evidence.Verdict.holds(span)
        record = paper_evidence.EvidenceRecord.from_verdict(
            block_id="b", regime="none", claim="c", cite_key="k", identifier="",
            resolver="", metadata_digest="", verdict=verdict, round=1,
        )
        result = paper_evidence.append_record(self.paper_dir, record, guidance_dir=self.guidance_dir)
        self.assertNotIn("manifest", result)


class ConfigParsingTests(unittest.TestCase):
    """`paper_resolve.parse_yaml_subset` -- the constrained reader that
    keeps `paper-writing` stdlib-only end to end."""

    def test_round_trips_roles_and_contact(self) -> None:
        text = (
            "paper_ingestion:\n"
            "  engine: marker  # a trailing comment\n"
            "  source_roots: []\n"
            "\n"
            "paper_writing:\n"
            "  contact: \"a@b.example\"\n"
            "  roles:\n"
            "    discovery: []\n"
            "    resolution:\n"
            "      - openalex\n"
            "      - crossref\n"
            "    full-text: []\n"
        )
        parsed = paper_resolve.parse_yaml_subset(text)
        self.assertEqual(parsed["paper_writing"]["contact"], "a@b.example")
        self.assertEqual(parsed["paper_writing"]["roles"]["resolution"], ["openalex", "crossref"])
        self.assertEqual(parsed["paper_ingestion"]["engine"], "marker")

    def test_malformed_line_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            paper_resolve.parse_yaml_subset("not a mapping line at all")

    def test_load_config_refuses_papersmith_config_unreadable_for_a_missing_file(self) -> None:
        missing = Path(tempfile.mkdtemp()) / "nope.yaml"
        with self.assertRaises(Refused) as ctx:
            paper_resolve.load_config(missing)
        self.assertEqual(ctx.exception.code, "PAPERSMITH_CONFIG_UNREADABLE")

    def test_the_real_papersmith_yaml_declares_the_resolution_role(self) -> None:
        config = paper_resolve.load_config()
        self.assertIn("openalex", config["paper_writing"]["roles"]["resolution"])


class RoleConnectorTests(unittest.TestCase):
    def test_an_empty_discovery_role_refuses_discovery_unavailable(self) -> None:
        config = _config(discovery=())
        with self.assertRaises(Refused) as ctx:
            paper_resolve.require_role_connectors(config, "discovery")
        self.assertEqual(ctx.exception.code, "DISCOVERY_UNAVAILABLE")

    def test_an_empty_resolution_role_refuses_resolver_role_empty(self) -> None:
        config = _config(resolution=())
        with self.assertRaises(Refused) as ctx:
            paper_resolve.require_role_connectors(config, "resolution")
        self.assertEqual(ctx.exception.code, "RESOLVER_ROLE_EMPTY")

    def test_an_unknown_role_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_resolve.connectors_for_role(_config(), "translation")
        self.assertEqual(ctx.exception.code, "UNKNOWN_ROLE")


class ResolverKeylessTests(unittest.TestCase):
    """literature-search, Requirement: Resolution Runs Through the CLI Over
    Stdlib `urllib` -- `mailto` from config, never hardcoded; no API key or
    secret anywhere on this path."""

    def test_mailto_sourced_from_config_contact(self) -> None:
        config = _config(contact="reader@example.org")
        url = paper_resolve._openalex_url("10.1000/example", config)
        self.assertIn("mailto=reader%40example.org", url)

    def test_no_contact_means_no_mailto_parameter(self) -> None:
        config = _config(contact="")
        url = paper_resolve._openalex_url("10.1000/example", config)
        self.assertNotIn("mailto", url)

    def test_resolution_source_holds_no_hardcoded_api_key(self) -> None:
        source = (SKILL_SCRIPTS / "paper_resolve.py").read_text(encoding="utf-8")
        self.assertNotIn("api_key", source.lower())
        self.assertNotIn("Bearer ", source)


class ResolverOfflineTests(unittest.TestCase):
    """`literature-search`, Requirement: Unreachable Connectors Refuse By
    Name -- proven with the raising `OPENER` seam, zero live network."""

    def setUp(self) -> None:
        self._real_opener = paper_resolve.OPENER
        self.addCleanup(self._restore_opener)

    def _restore_opener(self) -> None:
        paper_resolve.OPENER = self._real_opener

    def test_unreachable_resolver_refuses_with_the_named_code(self) -> None:
        paper_resolve.OPENER = _RaisingOpener()
        config = _config()
        with self.assertRaises(Refused) as ctx:
            paper_resolve.resolve_identifier(
                "10.1000/example", resolver="openalex", role="resolution", config=config,
            )
        self.assertEqual(ctx.exception.code, "RESOLVER_UNREACHABLE")

    def test_unreachable_resolver_cli_call_exits_non_zero(self) -> None:
        paper_resolve.OPENER = _RaisingOpener()
        exit_code = paper_cli.main(
            ["resolve", "--identifier", "10.1000/example", "--resolver", "openalex", "--role", "resolution"]
        )
        self.assertEqual(exit_code, 2)

    def test_a_none_regime_block_is_unaffected_by_every_connector_being_unreachable(self) -> None:
        # literature-search, Scenario: A none block is unaffected -- proven
        # here by showing the write path this change touches
        # (paper_scaffold/paper_block, unchanged by this work unit) never
        # even consults paper_resolve, so an unreachable OPENER cannot
        # possibly affect it.
        paper_resolve.OPENER = _RaisingOpener()
        with tempfile.TemporaryDirectory() as tmp:
            paper_dir = Path(tmp) / "paper"
            result = paper_scaffold.scaffold(paper_dir)
            self.assertIn("main.tex", result["created"])

    def test_a_not_found_identifier_refuses_identifier_unresolved(self) -> None:
        paper_resolve.OPENER = _NotFoundOpener()
        config = _config()
        with self.assertRaises(Refused) as ctx:
            paper_resolve.resolve_identifier(
                "10.1000/does-not-exist", resolver="openalex", role="resolution", config=config,
            )
        self.assertEqual(ctx.exception.code, "IDENTIFIER_UNRESOLVED")

    def test_a_reachable_resolver_returns_metadata_and_caches_it(self) -> None:
        payload = json.dumps({"title": "A Paper", "doi": "10.1/x", "publication_year": 2024}).encode()
        paper_resolve.OPENER = _AnsweringOpener(payload)
        config = _config()
        result = paper_resolve.resolve_identifier(
            "10.1/x", resolver="openalex", role="resolution", config=config,
        )
        self.assertEqual(result["title"], "A Paper")
        self.assertTrue(result["metadata_digest"])
        with tempfile.TemporaryDirectory() as tmp:
            paper_dir = Path(tmp) / "paper"
            paper_dir.mkdir()
            paper_resolve.cache_metadata(paper_dir, result)
            cached = paper_resolve.read_cached_metadata(paper_dir, result["metadata_digest"])
            self.assertEqual(cached["title"], "A Paper")


class ResolverMutationProofTests(unittest.TestCase):
    """m1 (design.md, Testing Strategy, Mutations table): the offline guard
    itself must be load-bearing, proven by disabling it and watching the
    corresponding refusal test fail."""

    def test_m1_unreachable_guard_disabled_fails_the_refusal_test(self) -> None:
        proc = _run_against_mutant(
            'raise Refused("RESOLVER_UNREACHABLE", str(exc))',
            'return {"identifier": identifier, "resolver": resolver, "metadata_digest": "",'
            ' "title": None, "doi": None, "year": None}',
            "tests.test_paper_evidence.ResolverOfflineTests.test_unreachable_resolver_refuses_with_the_named_code",
            source_path=SKILL_SCRIPTS / "paper_resolve.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class LiteratureSearchAbsenceTests(unittest.TestCase):
    """`literature-search`, three scenarios ("Discovery issues an open
    search", "Discovery candidate reaches resolution", "Consensus cannot
    supply a verdict") describe behaviour that is deliberately ABSENT from
    this CLI -- discovery runs entirely through the agent's own MCP servers,
    and there is no Consensus connector anywhere in this codebase
    (`design.md`, Decision 3; `paper_resolve.py` module docstring). Static
    inspection confirmed this in `verify-report.md`, but a comment cannot
    fail when the absence stops being true -- these tests can. Each
    assertion is derived from the running module or from every file the
    skill actually ships, not from a hand-maintained list, so a future
    change that wires discovery search, a Consensus connector, or a
    free-text query builder into this CLI trips one of these by name."""

    def test_no_skill_script_references_an_mcp_config(self) -> None:
        # "Discovery issues an open search" / "Discovery candidate reaches
        # resolution": discovery search runs through the agent's MCP, never
        # through this CLI. Scans every .py file this skill ships (derived
        # via glob, not a hand-picked file list) for a reference to the MCP
        # config this CLI is documented to never read.
        offenders = []
        for path in sorted(SKILL_SCRIPTS.glob("*.py")):
            lowered = path.read_text(encoding="utf-8").lower()
            if ".mcp.json" in lowered or "mcpservers" in lowered:
                offenders.append(path.name)
        self.assertEqual(offenders, [], f"MCP config referenced in: {offenders}")

    def test_no_free_text_query_construction_function_exists(self) -> None:
        # "Discovery issues an open search": a free-text query builder would
        # be the mechanism a discovery search needs; none exists here.
        # `resolve_identifier` is identifier-based only. Derived from the
        # module's own public surface via `inspect`, not a hardcoded name.
        # One named exception: `search_title` confirms a paper the manuscript
        # already cites and is accepted only on an exact title, so it finds no
        # new literature. Anything else with this shape is still discovery.
        confirmation_only = {"search_title"}
        offenders = []
        for name, func in inspect.getmembers(paper_resolve, inspect.isfunction):
            if func.__module__ != paper_resolve.__name__ or name in confirmation_only:
                continue  # imported from elsewhere (paper_scaffold, Refused)
            params = list(inspect.signature(func).parameters)
            name_is_suspect = "query" in name.lower() or "search" in name.lower()
            param_is_suspect = any("query" in p.lower() for p in params)
            if name_is_suspect or param_is_suspect:
                offenders.append(name)
        self.assertEqual(offenders, [], f"query-construction function(s): {offenders}")

    @staticmethod
    def _resolver_carrying_attributes(module) -> dict:
        """Every module-level attribute that could carry a resolver's name:
        any `tuple`/`list`/`set`/`frozenset`/`dict` bound directly on
        `module`'s own namespace (excluding dunder attributes such as
        `__annotations__`, which are about the module, not about it).
        `_ENDPOINT_BUILDERS` carries resolver names as dict KEYS, so
        membership (`in`) is checked the same way for every container here
        -- keys for a mapping, elements for the rest -- rather than reading
        one shape and assuming the others match it.

        Derived by walking the live module, exactly like
        `test_no_skill_script_references_an_mcp_config` (glob) and
        `test_no_free_text_query_construction_function_exists` (`inspect`)
        already derive their own surfaces in this same class -- so a fourth
        resolver-carrying attribute added tomorrow is picked up the moment
        it exists, never by someone remembering to extend a hand-typed list
        of three names."""
        return {
            name: value
            for name, value in vars(module).items()
            if not (name.startswith("__") and name.endswith("__"))
            and isinstance(value, (tuple, list, set, frozenset, dict))
        }

    def test_consensus_is_not_a_resolver(self) -> None:
        # "Consensus cannot supply a verdict": no Consensus connector exists
        # anywhere in this codebase. Checked against every container this
        # module's own namespace currently holds, derived at run time -- not
        # a hand-picked list of the three attributes that happen to be the
        # whole surface today.
        offenders = [
            name
            for name, value in self._resolver_carrying_attributes(paper_resolve).items()
            if "consensus" in value
        ]
        self.assertEqual(offenders, [], f"'consensus' appears in: {offenders}")

    def test_a_fourth_resolver_carrying_attribute_naming_consensus_is_caught(self) -> None:
        # Proof the derivation above is real, not cosmetic: a hand-listed
        # version naming only `RESOLVERS`/`ROLES`/`_ENDPOINT_BUILDERS` cannot
        # see an attribute it was never told about. This installs a fourth
        # one directly on the live module, confirms the derived check catches
        # a "consensus" entry inside it, then removes it and confirms the
        # module -- and the check -- are back to green.
        self.assertNotIn("_FULLTEXT_PROVIDERS", vars(paper_resolve))
        paper_resolve._FULLTEXT_PROVIDERS = ("openalex", "consensus")
        try:
            offenders = [
                name
                for name, value in self._resolver_carrying_attributes(paper_resolve).items()
                if "consensus" in value
            ]
            self.assertEqual(offenders, ["_FULLTEXT_PROVIDERS"], offenders)
        finally:
            del paper_resolve._FULLTEXT_PROVIDERS
        clean_offenders = [
            name
            for name, value in self._resolver_carrying_attributes(paper_resolve).items()
            if "consensus" in value
        ]
        self.assertEqual(clean_offenders, [])


def _cite_record(cite_key: str, *, resolver: str = "", metadata_digest: str = "", source_md: str = "") -> dict:
    return {
        "block_id": "b", "regime": "discovery", "claim": "c", "cite_key": cite_key,
        "identifier": "10.1/x", "resolver": resolver, "metadata_digest": metadata_digest,
        "source_md": source_md, "quote": "", "locator": {}, "verdict": "holds", "round": 1,
    }


class BibProducerTests(unittest.TestCase):
    """WU2: `sourced-bibliography`, Requirement: Every Entry Originates From
    Resolved Metadata. `entry_from_record` is the sole producer; every check
    here runs with the raising `OPENER` installed and no network access.

    `no-citation-before-its-paper-is-ingested`, item 2: resolved is no
    longer sufficient on its own -- `_ingested_source_md` below places a
    REAL ingested paper (`guidance/<root>/<paper>/<paper>.md`) for every
    fixture that must be accepted, the same two-level shape
    `paper_guidance.ingested_papers` walks; a record that must still be
    refused (never resolved at all) keeps `source_md=""` unchanged, since
    `ENTRY_UNSOURCED` fires first regardless.
    """

    def setUp(self) -> None:
        self._real_opener = paper_resolve.OPENER
        paper_resolve.OPENER = _RaisingOpener()
        self.addCleanup(self._restore_opener)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.paper_dir.mkdir()
        self.guidance_dir = Path(self._tmp.name) / "guidance"
        self.guidance_dir.mkdir()

    def _restore_opener(self) -> None:
        paper_resolve.OPENER = self._real_opener

    def _resolved_result(self, cite_key: str) -> dict:
        payload = json.dumps({"title": f"Paper {cite_key}", "doi": f"10.1/{cite_key}", "publication_year": 2024}).encode()
        digest = hashlib.sha256(payload).hexdigest()
        result = {
            "identifier": f"10.1/{cite_key}", "resolver": "openalex", "metadata_digest": digest,
            "title": f"Paper {cite_key}", "doi": f"10.1/{cite_key}", "year": 2024,
        }
        paper_resolve.cache_metadata(self.paper_dir, result)
        return result

    def _ingested_source_md(self, cite_key: str) -> str:
        """Places `guidance/citations/<cite_key>/<cite_key>.md` -- a REAL
        ingested paper, exactly the shape `paper_guidance.ingested_papers`
        walks -- and returns its path for `_cite_record`'s own `source_md`.
        """
        paper_dir = self.guidance_dir / "citations" / cite_key
        paper_dir.mkdir(parents=True, exist_ok=True)
        md_path = paper_dir / f"{cite_key}.md"
        md_path.write_text(f"# {cite_key}\n\nBody.\n", encoding="utf-8")
        return str(md_path)

    def test_a_hand_composed_entry_refuses_entry_unsourced_offline(self) -> None:
        # No cache, no resolver, no digest -- and the OPENER is a
        # _RaisingOpener the whole test class refuses to ever call. This
        # check needs no network (sourced-bibliography, Scenario: A
        # hand-typed entry is refused offline).
        with self.assertRaises(Refused) as ctx:
            paper_bib.entry_from_record(
                self.paper_dir, _cite_record("hand-typed"), guidance_dir=self.guidance_dir,
            )
        self.assertEqual(ctx.exception.code, "ENTRY_UNSOURCED")

    def test_a_digest_with_no_matching_cache_blob_refuses(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_bib.entry_from_record(
                self.paper_dir, _cite_record("ghost", resolver="openalex", metadata_digest="deadbeef"),
                guidance_dir=self.guidance_dir,
            )
        self.assertEqual(ctx.exception.code, "ENTRY_UNSOURCED")

    def test_a_resolved_entry_is_accepted(self) -> None:
        result = self._resolved_result("smith2024")
        record = _cite_record(
            "smith2024", resolver="openalex", metadata_digest=result["metadata_digest"],
            source_md=self._ingested_source_md("smith2024"),
        )
        entry = paper_bib.entry_from_record(self.paper_dir, record, guidance_dir=self.guidance_dir)
        self.assertEqual(entry["cite_key"], "smith2024")
        self.assertEqual(entry["title"], "Paper smith2024")

    def test_a_resolved_but_not_ingested_entry_refuses_entry_not_ingested(self) -> None:
        """The decisive proof for item 2: resolution alone is no longer
        enough. `metadata_digest`/`resolver` are both real and cached --
        exactly `test_a_resolved_entry_is_accepted`'s own fixture -- but
        `source_md` is empty, so no evidence span was ever located against
        an ingested paper."""
        result = self._resolved_result("unread2024")
        record = _cite_record(
            "unread2024", resolver="openalex", metadata_digest=result["metadata_digest"],
        )
        with self.assertRaises(Refused) as ctx:
            paper_bib.entry_from_record(self.paper_dir, record, guidance_dir=self.guidance_dir)
        self.assertEqual(ctx.exception.code, "ENTRY_NOT_INGESTED")
        self.assertIn("unread2024", ctx.exception.detail)

    def test_a_source_md_outside_guidance_refuses_entry_not_ingested(self) -> None:
        """A `source_md` naming a real file that simply does not sit under
        `guidance_dir` at all is not a free pass -- reliability requires
        the SAME ingested-paper shape, not merely "some file exists"."""
        result = self._resolved_result("elsewhere2024")
        outside = Path(self._tmp.name) / "elsewhere.md"
        outside.write_text("# Elsewhere\n", encoding="utf-8")
        record = _cite_record(
            "elsewhere2024", resolver="openalex", metadata_digest=result["metadata_digest"],
            source_md=str(outside),
        )
        with self.assertRaises(Refused) as ctx:
            paper_bib.entry_from_record(self.paper_dir, record, guidance_dir=self.guidance_dir)
        self.assertEqual(ctx.exception.code, "ENTRY_NOT_INGESTED")

    def test_build_refs_bib_rebuilds_whole_and_sorted(self) -> None:
        result_b = self._resolved_result("bkey")
        result_a = self._resolved_result("akey")
        records = [
            _cite_record(
                "bkey", resolver="openalex", metadata_digest=result_b["metadata_digest"],
                source_md=self._ingested_source_md("bkey"),
            ),
            _cite_record(
                "akey", resolver="openalex", metadata_digest=result_a["metadata_digest"],
                source_md=self._ingested_source_md("akey"),
            ),
        ]
        built = paper_bib.build_refs_bib(self.paper_dir, records, guidance_dir=self.guidance_dir)
        self.assertEqual(built["entries"], ["akey", "bkey"])
        text = (self.paper_dir / "refs.bib").read_text(encoding="utf-8")
        self.assertLess(text.index("akey"), text.index("bkey"))

    def test_provenance_never_reaches_the_rendered_page(self) -> None:
        """A `note` field PRINTS, and this one carried a bare `_`.

        RED-first, measured on a real 12-page build of this repository's own
        manuscript: the `plain` style rendered all eight references as
        "... resolver=openalex; metadata_digest=6f98...", and the bare `_`
        of `metadata_digest` is a math-mode character, so the emitted `.bbl`
        raised "Missing $ inserted" at every entry. The damage is not
        cosmetic: the error cascade left the `.aux` with zero `\\newlabel`
        and zero `\\bibcite`, so a single-pass compile resolved all 23
        `\\ref` to `??` and all 10 `\\cite` to `[?]`.

        Provenance still belongs in the file -- BibTeX ignores bytes between
        entries, so a leading `%` line keeps it readable and off the page.
        """
        result = self._resolved_result("akey")
        records = [_cite_record(
            "akey", resolver="openalex", metadata_digest=result["metadata_digest"],
            source_md=self._ingested_source_md("akey"),
        )]

        paper_bib.build_refs_bib(self.paper_dir, records, guidance_dir=self.guidance_dir)
        text = (self.paper_dir / "refs.bib").read_text(encoding="utf-8")

        self.assertNotIn("note = ", text)
        self.assertIn(
            f"% resolver=openalex; metadata_digest={result['metadata_digest']}", text,
        )
        for line in text.splitlines():
            if line.startswith("%"):
                continue
            self.assertNotIn(
                "_", line, f"a bare underscore reaches the typeset page: {line!r}",
            )

    def test_build_refs_bib_rebuilds_whole_never_appends(self) -> None:
        refs_path = self.paper_dir / "refs.bib"
        refs_path.write_text("@misc{stale,\n  title = {Should Be Gone},\n}\n", encoding="utf-8")
        result = self._resolved_result("fresh")
        record = _cite_record(
            "fresh", resolver="openalex", metadata_digest=result["metadata_digest"],
            source_md=self._ingested_source_md("fresh"),
        )
        paper_bib.build_refs_bib(self.paper_dir, [record], guidance_dir=self.guidance_dir)
        text = refs_path.read_text(encoding="utf-8")
        self.assertNotIn("stale", text)
        self.assertIn("fresh", text)

    def test_one_unsourced_record_refuses_the_whole_rebuild_before_any_byte_written(self) -> None:
        refs_path = self.paper_dir / "refs.bib"
        refs_path.write_text("@misc{untouched,\n}\n", encoding="utf-8")
        pre = refs_path.read_bytes()
        with self.assertRaises(Refused):
            paper_bib.build_refs_bib(
                self.paper_dir, [_cite_record("no-provenance")], guidance_dir=self.guidance_dir,
            )
        self.assertEqual(refs_path.read_bytes(), pre)

    def test_one_not_ingested_record_refuses_the_whole_rebuild_before_any_byte_written(self) -> None:
        """The same all-or-nothing property `test_one_unsourced_record_
        refuses_the_whole_rebuild_before_any_byte_written` proves for
        `ENTRY_UNSOURCED` also holds for `ENTRY_NOT_INGESTED`: one
        resolved-but-not-ingested record among several refuses the WHOLE
        rebuild, never a partial `refs.bib`."""
        refs_path = self.paper_dir / "refs.bib"
        refs_path.write_text("@misc{untouched,\n}\n", encoding="utf-8")
        pre = refs_path.read_bytes()
        ok_result = self._resolved_result("ready2024")
        ok_record = _cite_record(
            "ready2024", resolver="openalex", metadata_digest=ok_result["metadata_digest"],
            source_md=self._ingested_source_md("ready2024"),
        )
        not_ingested_result = self._resolved_result("notyet2024")
        not_ingested_record = _cite_record(
            "notyet2024", resolver="openalex", metadata_digest=not_ingested_result["metadata_digest"],
        )
        with self.assertRaises(Refused) as ctx:
            paper_bib.build_refs_bib(
                self.paper_dir, [ok_record, not_ingested_record], guidance_dir=self.guidance_dir,
            )
        self.assertEqual(ctx.exception.code, "ENTRY_NOT_INGESTED")
        self.assertEqual(refs_path.read_bytes(), pre)


class BibIngestionGateMutationTests(unittest.TestCase):
    """The decisive mutation proof for item 2: dropping `entry_from_record`'s
    own call to `_require_ingested` must fail
    `BibProducerTests.test_a_resolved_but_not_ingested_entry_refuses_
    entry_not_ingested` -- a passing test beside an unexercised guard is
    not a mutation that ran."""

    def test_mutation_removing_the_ingestion_check_fails_the_not_ingested_refusal(self) -> None:
        proc = _run_against_mutant(
            "    _require_ingested(record, guidance_dir)\n    return {",
            "    return {",
            "tests.test_paper_evidence.BibProducerTests"
            ".test_a_resolved_but_not_ingested_entry_refuses_entry_not_ingested",
            source_path=SKILL_SCRIPTS / "paper_bib.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class ReciprocalCheckTests(unittest.TestCase):
    """`sourced-bibliography`, Requirement: Reciprocal Citation/Entry
    Checks -- each direction fires independently, from two separate
    fixtures."""

    def test_cite_without_entry_fires_independently(self) -> None:
        main_tex = rb"\cite{missing-entry}"
        refs_bib = b""
        with self.assertRaises(Refused) as ctx:
            paper_bib.check_reciprocal(main_tex, refs_bib)
        self.assertEqual(ctx.exception.code, "CITE_WITHOUT_ENTRY")
        self.assertIn("missing-entry", ctx.exception.detail)

    def test_entry_without_cite_fires_independently(self) -> None:
        main_tex = b"no citations here"
        refs_bib = b"@misc{orphan-entry,\n  title = {X},\n}\n"
        with self.assertRaises(Refused) as ctx:
            paper_bib.check_reciprocal(main_tex, refs_bib)
        self.assertEqual(ctx.exception.code, "ENTRY_WITHOUT_CITE")
        self.assertIn("orphan-entry", ctx.exception.detail)

    def test_a_fully_reciprocal_bibliography_passes(self) -> None:
        main_tex = rb"\cite{a-key} and \cite{b-key}"
        refs_bib = b"@misc{a-key,\n}\n@misc{b-key,\n}\n"
        report = paper_bib.check_reciprocal(main_tex, refs_bib)
        self.assertEqual(report["cited"], ["a-key", "b-key"])
        self.assertEqual(report["entries"], ["a-key", "b-key"])


def _full_text_config(connectors=("openalex", "arxiv")) -> dict:
    return {
        "paper_writing": {
            "contact": "",
            "roles": {
                "discovery": [], "resolution": ["openalex", "crossref", "arxiv"],
                "full-text": list(connectors),
            },
        }
    }


class FullTextFetchTests(unittest.TestCase):
    """`the-pdf-arrives-or-the-operator-is-told`: fills the `full-text`
    role `papersmith.yaml` and `paper_resolve.ROLES` both already declared.
    Reachability is read off the cached metadata's own `full_text_url`,
    never re-guessed here -- every fixture below sets it directly rather
    than exercising `paper_resolve`'s parsers a second time (WU1's own
    `ResolverOfflineTests` already proves those)."""

    def setUp(self) -> None:
        self._real_opener = paper_resolve.OPENER
        self.addCleanup(self._restore_opener)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.paper_dir.mkdir()
        self.guidance_dir = Path(self._tmp.name) / "guidance"
        self.guidance_dir.mkdir()

    def _restore_opener(self) -> None:
        paper_resolve.OPENER = self._real_opener

    def _cache(self, *, identifier, resolver, title, full_text_url, digest=None) -> str:
        digest = digest or hashlib.sha256(identifier.encode()).hexdigest()
        result = {
            "identifier": identifier, "resolver": resolver, "metadata_digest": digest,
            "title": title, "doi": None, "year": None, "full_text_url": full_text_url,
        }
        paper_resolve.cache_metadata(self.paper_dir, result)
        return digest

    def test_a_record_with_no_full_text_url_is_reported_unobtainable_by_name(self) -> None:
        """The decisive proof for item 1: a record this connector cannot
        reach is refused BY NAME (identifier and title both appear in the
        detail), never silently skipped -- and nothing is written."""
        paper_resolve.OPENER = _RaisingOpener()  # proves zero network reached
        digest = self._cache(
            identifier="10.1/paywalled", resolver="crossref",
            title="A Paywalled Paper", full_text_url=None,
        )
        with self.assertRaises(Refused) as ctx:
            paper_full_text.fetch_full_text(
                self.paper_dir, self.guidance_dir, section_id="results",
                metadata_digest=digest, cite_key="paywalled2024", config=_full_text_config(),
            )
        self.assertEqual(ctx.exception.code, "FULL_TEXT_URL_ABSENT")
        self.assertIn("10.1/paywalled", ctx.exception.detail)
        self.assertIn("A Paywalled Paper", ctx.exception.detail)
        self.assertFalse((self.guidance_dir / "results").exists())

    def test_m_disabling_the_url_absent_guard_loses_the_named_report(self) -> None:
        proc = _run_against_mutant(
            "if not url:",
            "if False:",
            "tests.test_paper_evidence.FullTextFetchTests"
            ".test_a_record_with_no_full_text_url_is_reported_unobtainable_by_name",
            source_path=SKILL_SCRIPTS / "paper_full_text.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_an_empty_full_text_role_closes_the_path_entirely(self) -> None:
        digest = self._cache(
            identifier="10.1000/x", resolver="openalex", title="Some Paper",
            full_text_url="https://example.org/paper.pdf",
        )
        with self.assertRaises(Refused) as ctx:
            paper_full_text.fetch_full_text(
                self.paper_dir, self.guidance_dir, section_id="results",
                metadata_digest=digest, cite_key="somepaper2024", config=_config(),
            )
        self.assertEqual(ctx.exception.code, "RESOLVER_ROLE_EMPTY")
        self.assertFalse((self.guidance_dir / "results").exists())

    def test_a_reachable_pdf_lands_loose_directly_under_the_section_folder(self) -> None:
        payload = b"%PDF-1.4 fake pdf bytes\n"
        paper_resolve.OPENER = _AnsweringOpener(payload)
        digest = self._cache(
            identifier="2301.00001", resolver="arxiv", title="An Open Paper",
            full_text_url="https://arxiv.org/pdf/2301.00001",
        )
        result = paper_full_text.fetch_full_text(
            self.paper_dir, self.guidance_dir, section_id="results",
            metadata_digest=digest, cite_key="open2023", config=_full_text_config(),
        )
        destination = Path(result["path"])
        # `.resolve()` on both sides: on macOS, `/var` is itself a symlink
        # to `/private/var`, and `resolve_destination` returns the fully
        # resolved form while `self.guidance_dir` here does not.
        self.assertEqual(destination, (self.guidance_dir / "results" / "open2023.pdf").resolve())
        self.assertEqual(destination.read_bytes(), payload)
        # Loose, not nested: paper-ingestion's own "exactly one level down"
        # contract requires the file's parent to be the section folder
        # itself, never a subfolder of it.
        self.assertEqual(destination.parent, (self.guidance_dir / "results").resolve())

    def test_a_non_pdf_response_refuses_full_text_not_a_pdf(self) -> None:
        """`open_access.oa_url` sometimes lands on a repository splash page
        rather than raw PDF bytes -- a 200 response is not proof of a
        fetched PDF, only the bytes are."""
        paper_resolve.OPENER = _AnsweringOpener(b"<html>not a pdf</html>")
        digest = self._cache(
            identifier="2301.00002", resolver="arxiv", title="Mislabeled OA Link",
            full_text_url="https://arxiv.org/pdf/2301.00002",
        )
        with self.assertRaises(Refused) as ctx:
            paper_full_text.fetch_full_text(
                self.paper_dir, self.guidance_dir, section_id="results",
                metadata_digest=digest, cite_key="mislabeled2023", config=_full_text_config(),
            )
        self.assertEqual(ctx.exception.code, "FULL_TEXT_NOT_A_PDF")
        self.assertFalse((self.guidance_dir / "results" / "mislabeled2023.pdf").exists())

    def test_fetching_twice_never_overwrites_silently(self) -> None:
        paper_resolve.OPENER = _AnsweringOpener(b"%PDF-1.4 first\n")
        digest = self._cache(
            identifier="2301.00003", resolver="arxiv", title="Refetched Paper",
            full_text_url="https://arxiv.org/pdf/2301.00003",
        )
        paper_full_text.fetch_full_text(
            self.paper_dir, self.guidance_dir, section_id="results",
            metadata_digest=digest, cite_key="dup2023", config=_full_text_config(),
        )
        with self.assertRaises(Refused) as ctx:
            paper_full_text.fetch_full_text(
                self.paper_dir, self.guidance_dir, section_id="results",
                metadata_digest=digest, cite_key="dup2023", config=_full_text_config(),
            )
        self.assertEqual(ctx.exception.code, "FULL_TEXT_FILE_PRESENT")

    def test_a_cite_key_containing_a_path_separator_refuses_before_any_fetch(self) -> None:
        paper_resolve.OPENER = _RaisingOpener()  # proves the guard runs first
        digest = self._cache(
            identifier="2301.00004", resolver="arxiv", title="Traversal Attempt",
            full_text_url="https://arxiv.org/pdf/2301.00004",
        )
        with self.assertRaises(Refused) as ctx:
            paper_full_text.fetch_full_text(
                self.paper_dir, self.guidance_dir, section_id="results",
                metadata_digest=digest, cite_key="../escape", config=_full_text_config(),
            )
        self.assertEqual(ctx.exception.code, "CITE_KEY_MALFORMED")

    def test_a_digest_with_no_cached_metadata_refuses_metadata_not_cached(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_full_text.fetch_full_text(
                self.paper_dir, self.guidance_dir, section_id="results",
                metadata_digest="deadbeef", cite_key="ghost", config=_full_text_config(),
            )
        self.assertEqual(ctx.exception.code, "METADATA_NOT_CACHED")


class FullTextCLITests(unittest.TestCase):
    """`full_text` wired into `paper_cli.py` end to end, against the real
    `papersmith.yaml` this same change fills (`full-text: [openalex,
    arxiv]`) -- the same `implementations/` real-repo fixture pattern
    `tests/test_paper_citation.py::ValidateCLITests` already uses."""

    def setUp(self) -> None:
        self._real_opener = paper_resolve.OPENER
        self.addCleanup(self._restore_opener)
        self.root = FORGE_ROOT / "implementations" / f".paper-writing-full-text-cli-test-{os.getpid()}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.paper_dir.mkdir(parents=True)
        self.guidance_dir = self.root / "guidance"
        self.guidance_dir.mkdir(parents=True)

    def _restore_opener(self) -> None:
        paper_resolve.OPENER = self._real_opener

    def test_full_text_cli_fetches_and_places_the_pdf_loose(self) -> None:
        result = {
            "identifier": "2301.99999", "resolver": "arxiv", "metadata_digest": "cli-digest",
            "title": "CLI Paper", "doi": None, "year": None,
            "full_text_url": "https://arxiv.org/pdf/2301.99999",
        }
        paper_resolve.cache_metadata(self.paper_dir, result)
        paper_resolve.OPENER = _AnsweringOpener(b"%PDF-1.4 cli fetched\n")
        exit_code = paper_cli.main([
            "full_text", "--paper", str(self.paper_dir), "--guidance", str(self.guidance_dir),
            "--section", "results", "--metadata-digest", "cli-digest", "--cite-key", "clipaper2023",
        ])
        self.assertEqual(exit_code, 0)
        destination = self.guidance_dir / "results" / "clipaper2023.pdf"
        self.assertTrue(destination.is_file())
        self.assertEqual(destination.read_bytes(), b"%PDF-1.4 cli fetched\n")

    def test_full_text_cli_names_an_unobtainable_record_and_exits_non_zero(self) -> None:
        result = {
            "identifier": "10.1/cli-wall", "resolver": "crossref", "metadata_digest": "cli-wall-digest",
            "title": "CLI Walled Paper", "doi": None, "year": None, "full_text_url": None,
        }
        paper_resolve.cache_metadata(self.paper_dir, result)
        paper_resolve.OPENER = _RaisingOpener()
        exit_code = paper_cli.main([
            "full_text", "--paper", str(self.paper_dir), "--guidance", str(self.guidance_dir),
            "--section", "results", "--metadata-digest", "cli-wall-digest", "--cite-key", "clidenied",
        ])
        self.assertEqual(exit_code, 2)


class ResolvedMetadataCarriesAuthorsTests(unittest.TestCase):
    """A bibliography entry with no author is one bibtex cannot even sort
    ("Warning--to sort, need author or key") and no venue will accept.

    RED-first: measured against a real `refs.bib` this repository built,
    every one of its six entries was `@misc` with a title, a doi, a year and
    a provenance note -- and no author, because the three parsers discarded
    the authorships the connectors had already returned. The fix is in the
    PARSERS, not in the entry writer: an entry producer cannot emit what was
    never captured.
    """

    def test_openalex_captures_authorships_and_venue(self) -> None:
        raw = json.dumps({
            "title": "A Paper", "doi": "10.0/x", "publication_year": 2021,
            "open_access": {"is_oa": False},
            "authorships": [
                {"author": {"display_name": "Ada Lovelace"}},
                {"author": {"display_name": "Alan Turing"}},
            ],
            "primary_location": {"source": {"display_name": "Journal of Things"}},
        }).encode("utf-8")

        parsed = paper_resolve._parse_openalex(raw)

        self.assertEqual(parsed["authors"], ["Ada Lovelace", "Alan Turing"])
        self.assertEqual(parsed["venue"], "Journal of Things")

    def test_openalex_with_no_authorships_reports_an_empty_list(self) -> None:
        """Absent is absent: a record the connector returned without
        authorships parses to `[]`, never to an invented name."""
        raw = json.dumps({"title": "A Paper", "doi": "10.0/x", "publication_year": 2021}).encode("utf-8")

        parsed = paper_resolve._parse_openalex(raw)

        self.assertEqual(parsed["authors"], [])
        self.assertIsNone(parsed["venue"])

    def test_crossref_captures_given_and_family_names(self) -> None:
        raw = json.dumps({"message": {
            "title": ["A Paper"], "DOI": "10.0/x",
            "author": [{"given": "Ada", "family": "Lovelace"}],
            "container-title": ["Journal of Things"],
        }}).encode("utf-8")

        parsed = paper_resolve._parse_crossref(raw)

        self.assertEqual(parsed["authors"], ["Ada Lovelace"])
        self.assertEqual(parsed["venue"], "Journal of Things")

    def test_arxiv_captures_entry_author_names(self) -> None:
        raw = (
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            "<title>A Paper</title>"
            "<author><name>Ada Lovelace</name></author>"
            "<author><name>Alan Turing</name></author>"
            "</entry></feed>"
        ).encode("utf-8")

        parsed = paper_resolve._parse_arxiv(raw)

        self.assertEqual(parsed["authors"], ["Ada Lovelace", "Alan Turing"])
        self.assertEqual(parsed["venue"], "arXiv")

    def test_the_entry_text_emits_author_and_journal(self) -> None:
        text = paper_bib._entry_text({
            "cite_key": "lovelace2021", "title": "A Paper", "doi": "10.0/x", "year": 2021,
            "authors": ["Ada Lovelace", "Alan Turing"], "venue": "Journal of Things",
            "resolver": "openalex", "metadata_digest": "abc",
        })

        self.assertIn("author = {Ada Lovelace and Alan Turing},", text)
        self.assertIn("journal = {Journal of Things},", text)
        # The entry proper is the first line BibTeX reads: provenance rides
        # above it as a comment, which BibTeX skips along with every other
        # byte between entries.
        entry = [line for line in text.splitlines() if not line.startswith("%")]
        self.assertEqual(entry[0], "@article{lovelace2021,")

    def test_an_entry_with_no_venue_stays_misc_and_prints_no_journal(self) -> None:
        """`plain` ignores `journal` on a `@misc`, so an uncaptured venue
        must not silently turn the entry into an article with a blank one."""
        text = paper_bib._entry_text({
            "cite_key": "anon2021", "title": "A Paper", "doi": None, "year": 2021,
            "authors": [], "venue": None, "resolver": "openalex", "metadata_digest": "abc",
        })

        entry = [line for line in text.splitlines() if not line.startswith("%")]
        self.assertEqual(entry[0], "@misc{anon2021,")
        self.assertNotIn("journal = ", text)
        self.assertNotIn("author = ", text)

    def test_the_entry_text_escapes_latex_special_bytes(self) -> None:
        """R3-unescaped-upstream-fields-reach-bbl: an unescaped `&` in
        ordinary metadata breaks the compiled `.bbl`; all three fields
        must escape it.
        """
        text = paper_bib._entry_text({
            "cite_key": "amp2021", "title": "A & B Study", "doi": None, "year": 2021,
            "authors": ["Smith & Jones"], "venue": "Journal of A & B",
            "resolver": "openalex", "metadata_digest": "abc",
        })

        self.assertIn(r"author = {Smith \& Jones},", text)
        self.assertIn(r"title = {A \& B Study},", text)
        self.assertIn(r"journal = {Journal of A \& B},", text)
        self.assertNotIn("A & B", text)


class ResolvedAuthorsMutationProofTests(unittest.TestCase):
    """The capture must be load-bearing, not merely present: dropping the
    authorship walk from the OpenAlex parser must turn the capture test red."""

    def test_mutation_dropping_the_authorship_walk_fails_the_capture(self) -> None:
        proc = _run_against_mutant(
            '    for authorship in obj.get("authorships") or []:\n',
            "    for authorship in []:\n",
            "tests.test_paper_evidence.ResolvedMetadataCarriesAuthorsTests"
            ".test_openalex_captures_authorships_and_venue",
            source_path=SKILL_SCRIPTS / "paper_resolve.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class ResolvedMetadataCarriesAbstractTests(unittest.TestCase):
    """A scout that grades against abstracts needs them captured, not
    referenced: OpenAlex ships its abstract position-indexed and arXiv its
    summary multi-line, and neither survives a parser that ignores it.

    RED-first: the scout contract demands verbatim abstract quotes while the
    three parsers discarded them — the same class of defect the authorship
    capture above closed. The fix is in the PARSERS, not in the scout: an
    agent cannot quote what was never captured.
    """

    def test_openalex_deinverts_the_position_index_into_reading_order(self) -> None:
        raw = json.dumps({
            "title": "A Paper", "doi": "10.0/x", "publication_year": 2021,
            "abstract_inverted_index": {
                "We": [0], "study": [1], "things": [2], "deeply": [4],
                "very": [3],
            },
        }).encode("utf-8")

        parsed = paper_resolve._parse_openalex(raw)

        self.assertEqual(parsed["abstract"], "We study things very deeply")

    def test_openalex_without_an_index_reports_none_never_a_guess(self) -> None:
        """Absent or malformed is absent: a record without an index parses to
        `None`, and one with non-integer positions does too — joining either
        would mint word salad the scout would then cite as evidence."""
        bare = json.dumps({"title": "A Paper"}).encode("utf-8")
        self.assertIsNone(paper_resolve._parse_openalex(bare)["abstract"])

        broken = json.dumps({
            "title": "A Paper",
            "abstract_inverted_index": {"We": ["zero"]},
        }).encode("utf-8")
        self.assertIsNone(paper_resolve._parse_openalex(broken)["abstract"])

    def test_arxiv_collapses_its_multiline_summary_to_one_line(self) -> None:
        raw = (
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            "<title>A Paper</title>"
            "<summary>We study things.\n  Very deeply.</summary>"
            "</entry></feed>"
        ).encode("utf-8")

        parsed = paper_resolve._parse_arxiv(raw)

        self.assertEqual(parsed["abstract"], "We study things. Very deeply.")

    def test_arxiv_without_a_summary_reports_none(self) -> None:
        raw = (
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            "<title>A Paper</title>"
            "</entry></feed>"
        ).encode("utf-8")

        self.assertIsNone(paper_resolve._parse_arxiv(raw)["abstract"])

    def test_crossref_reports_none_rather_than_jats(self) -> None:
        """Crossref abstracts arrive as publisher JATS, not plain text.
        Capturing them raw would hand the scout tags to quote; `None` names
        the limit instead."""
        raw = json.dumps({"message": {
            "title": ["A Paper"], "DOI": "10.0/x",
            "abstract": "<jats:p>We study things.</jats:p>",
        }}).encode("utf-8")

        self.assertIsNone(paper_resolve._parse_crossref(raw)["abstract"])


class ResolvedAbstractMutationProofTests(unittest.TestCase):
    """The de-inversion must be load-bearing, not merely present: dropping
    the positional sort must scramble the sentence and turn the capture red."""

    def test_mutation_dropping_the_sort_fails_the_capture(self) -> None:
        proc = _run_against_mutant(
            "    ordered.sort()\n",
            "    pass  # MUTANT: wire order kept\n",
            "tests.test_paper_evidence.ResolvedMetadataCarriesAbstractTests"
            ".test_openalex_deinverts_the_position_index_into_reading_order",
            source_path=SKILL_SCRIPTS / "paper_resolve.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)



if __name__ == "__main__":
    unittest.main()
