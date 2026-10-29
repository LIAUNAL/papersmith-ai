"""Focused unit tests for the paper-ingestion helpers (routing, config, references).

These cover the deterministic, pure logic authored in ``extract_pdf.py`` —
reference stripping, config loading, and loose-PDF discovery — without invoking
the heavy Marker/torch/surya stack (whose end-to-end behaviour is validated by
a real ingestion run, not a unit test).

Run with the skill's venv:
    skills/paper-ingestion/.venv/bin/python -m unittest tests.test_extract_pdf
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "skills/paper-ingestion/scripts/extract_pdf.py"
SPEC = importlib.util.spec_from_file_location("extract_pdf", SCRIPT)
assert SPEC and SPEC.loader
EXTRACTOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EXTRACTOR
SPEC.loader.exec_module(EXTRACTOR)



class ObjectiveFlowTests(unittest.TestCase):
    """The north: why this skill was invoked and where it has to arrive."""

    SKILL_MD = (Path(EXTRACTOR.__file__).resolve().parent.parent / "SKILL.md")
    STAGES = ["filed", "extracted", "readable"]

    def test_the_one_refusal_path_carries_it(self) -> None:
        """A blocked session is exactly the one that has lost the purpose, and
        this skill has a single place a refusal reaches a reader -- so there is
        no excuse for it to arrive without the north."""
        source = Path(EXTRACTOR.__file__).read_text(encoding="utf-8")
        self.assertEqual(source.count('print(f"Configuration error:'), 1,
                         "a second refusal path appeared and carries nothing")
        self.assertIn('"objective": OBJECTIVE_FLOW', source)

    def test_it_is_declared_ordered_and_closes_every_stage(self) -> None:
        flow = EXTRACTOR.OBJECTIVE_FLOW
        self.assertEqual([s["stage"] for s in flow["stages"]], self.STAGES)
        for stage in flow["stages"]:
            self.assertTrue(stage["establishes"] and stage["behindWhen"])

    def test_arrival_is_a_readable_artefact_and_not_a_processed_pdf(self) -> None:
        """This skill's whole reason to exist: a PDF is already on disk and
        already unusable as evidence."""
        self.assertIn("cite", EXTRACTOR.OBJECTIVE_FLOW["arrival"])

    def test_the_empty_human_stops_list_is_present_rather_than_omitted(self) -> None:
        """Ingestion asks nobody, and the list says so by being empty. A reader
        meeting a missing key would have to guess whether that meant none or
        meant nobody wrote it down."""
        self.assertIn("humanStops", EXTRACTOR.OBJECTIVE_FLOW)
        self.assertEqual(EXTRACTOR.OBJECTIVE_FLOW["humanStops"], [])

    def test_the_doctrine_states_the_same_stages(self) -> None:
        skill = self.SKILL_MD.read_text(encoding="utf-8")
        start = skill.index("## The objective flow")
        table = skill[start:skill.index("**Arrival:**", start)]
        rows = [line for line in table.splitlines() if line.startswith("| `")]
        self.assertEqual([line.split("`")[1] for line in rows], self.STAGES)


class StripReferencesTests(unittest.TestCase):
    def test_cuts_from_a_references_heading_to_the_end(self) -> None:
        text = "# Paper\n\nBody text.\n\n## References\n\n[1] Foo et al.\n[2] Bar.\n"
        out = EXTRACTOR.strip_references(text)
        self.assertIn("Body text.", out)
        self.assertNotIn("Foo et al.", out)
        self.assertNotIn("References", out)

    def test_handles_numbered_spanish_and_marker_decorated_headings(self) -> None:
        headings = (
            "## 7. References",
            "# Bibliography",
            "## Referencias",
            "### Bibliografía",
            "#### **References**",                              # Marker bold
            '## <span id="page-18-0"></span>**References**',    # Marker anchor + bold
        )
        for heading in headings:
            text = f"Body.\n\n{heading}\n\n[1] cite.\n"
            self.assertNotIn("cite", EXTRACTOR.strip_references(text), heading)

    def test_cuts_at_the_last_heading_when_referenced_mid_body(self) -> None:
        text = "Body mentions the References section.\n\n## References\n\n[1] cite.\n"
        out = EXTRACTOR.strip_references(text)
        self.assertIn("Body mentions the References section.", out)
        self.assertNotIn("[1] cite", out)

    def test_an_appendix_after_the_references_survives(self) -> None:
        """References are not always last, and cutting to the end of the
        document takes the appendix with them.

        Measured on this operator's own corpus: of 17 ingested papers
        carrying a references heading, FIVE place supplementary material
        after it, and cutting to the end removed between 52% and 74% of
        each file -- `A UDA generalization bound`, `A1 Derivation of
        UW-SO`, `B DATASET DETAILS`, `B. Details on Neural Networks
        RAINCOAT Algorithm`, `A.1 RELATED WORK (CONTINUED)`. That is
        citable science, not trailing bibliography.
        """
        text = (
            "# Paper\n\nBody text.\n\n"
            "# References\n\n[1] Foo et al.\n[2] Bar.\n\n"
            "# Appendix A\n\nThe derivation that matters.\n"
        )
        out = EXTRACTOR.strip_references(text)
        self.assertIn("Body text.", out)
        self.assertNotIn("Foo et al.", out)
        self.assertIn("Appendix A", out)
        self.assertIn("The derivation that matters.", out)

    def test_the_appendix_survives_at_any_heading_depth(self) -> None:
        """The depth of the heading that follows cannot be the test.

        Stopping at the next heading of the same-or-shallower level reads
        like the principled rule and fails on real input: measured in
        `he2023.md`, references sit at `# References` and the appendix
        opens at `## A. Further Information ...` -- DEEPER. Marker infers
        heading levels from font size, so depth is not a reliable signal
        about structure. The cut therefore ends at the next heading of any
        level that is not itself a references heading.
        """
        for appendix in ("# Appendix", "## Appendix", "#### Appendix"):
            with self.subTest(appendix=appendix):
                text = (
                    f"Body.\n\n# References\n\n[1] cite.\n\n"
                    f"{appendix}\n\nKept.\n"
                )
                out = EXTRACTOR.strip_references(text)
                self.assertNotIn("[1] cite", out)
                self.assertIn("Kept.", out)

    def test_consecutive_references_headings_are_all_cut(self) -> None:
        """A two-column render can emit the heading twice. Stopping at the
        first following heading must not leave the second block behind."""
        text = (
            "Body.\n\n## References\n\n[1] one.\n\n"
            "## REFERENCES\n\n[2] two.\n\n# Appendix\n\nKept.\n"
        )
        out = EXTRACTOR.strip_references(text)
        self.assertNotIn("[1] one", out)
        self.assertNotIn("[2] two", out)
        self.assertIn("Kept.", out)

    def test_references_last_still_cuts_to_the_end(self) -> None:
        """The case that already worked must keep working: with nothing
        after them, the references run to the end of the file and the whole
        tail goes."""
        text = "# Paper\n\nBody.\n\n## References\n\n[1] cite.\n[2] more.\n"
        out = EXTRACTOR.strip_references(text)
        self.assertIn("Body.", out)
        self.assertNotIn("cite", out)
        self.assertNotIn("more", out)

    def test_every_references_section_is_cut_not_only_the_last(self) -> None:
        """A paper can carry more than one bibliography.

        Measured on a real corpus: eight ingested papers place a
        `References` section in the body AND another later, typically
        beside supplementary material. Anchoring the cut on the LAST one
        removed the trailing block and left the body's real bibliography
        sitting in the document -- the opposite of the intent, and invisible
        because the file did get smaller.
        """
        text = (
            "Body.\n\n## References\n\n[1] first list.\n\n"
            "## Associated Data\n\nKept one.\n\n"
            "## References\n\n[2] second list.\n\n"
            "## Supplementary Materials\n\nKept two.\n"
        )
        out = EXTRACTOR.strip_references(text)
        self.assertNotIn("first list", out)
        self.assertNotIn("second list", out)
        self.assertIn("Kept one.", out)
        self.assertIn("Kept two.", out)

    def test_stripping_twice_changes_nothing_the_second_time(self) -> None:
        """Idempotence is the property that catches a partial cut.

        A pass that removes one bibliography and leaves another looks like
        success -- the file shrank -- and only a second pass reveals it by
        shrinking again. Asserting the second pass is a no-op turns that
        into a test instead of something someone has to notice.
        """
        text = (
            "Body.\n\n## References\n\n[1] a.\n\n"
            "## Appendix\n\nKept.\n\n## Bibliography\n\n[2] b.\n"
        )
        once = EXTRACTOR.strip_references(text)
        self.assertEqual(
            EXTRACTOR.strip_references(once), once,
            "a second pass still found something to remove, so the first "
            "pass left a references section behind")

    def test_text_without_a_references_heading_is_unchanged(self) -> None:
        text = "# Paper\n\nAll body, no bibliography.\n"
        self.assertEqual(EXTRACTOR.strip_references(text), text)


class LoadConfigTests(unittest.TestCase):
    """A malformed or missing configuration is reported, never silently
    downgraded to "nothing to ingest" — that reads exactly like a healthy
    no-op run and hides the real problem."""

    def _config(self, tmp: str, body: str) -> Path:
        path = Path(tmp) / "papersmith.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_reads_paper_ingestion_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(
                tmp, "paper_ingestion:\n  engine: marker\n  mode: fast\n  strip_references: true\n"
            )
            cfg = EXTRACTOR.load_config(path)
            self.assertEqual(cfg["engine"], "marker")
            self.assertEqual(cfg["mode"], "fast")
            self.assertTrue(cfg["strip_references"])

    def test_missing_file_is_a_config_error(self) -> None:
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.load_config(Path("/no/such/papersmith.yaml"))

    def test_file_without_block_is_a_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "other_section:\n  key: value\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_unparseable_yaml_is_a_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion:\n  mode: [unclosed\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_scalar_block_is_a_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion: marker\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_unknown_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion:\n  mode: turbo\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_unknown_engine_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion:\n  engine: nougat\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_source_roots_must_be_a_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion:\n  source_roots: guidance/papers\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_strip_references_must_be_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion:\n  strip_references: sometimes\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_the_repository_configuration_is_valid(self) -> None:
        cfg = EXTRACTOR.load_config(REPOSITORY_ROOT / "papersmith.yaml")
        self.assertIsInstance(cfg["source_roots"], list)


class _BaseFixture(unittest.TestCase):
    """A `source_base` with topic folders under it, and `REPO_ROOT` pointed at it.

    The script resolves every configured path against `REPO_ROOT`, so a test that
    does not move it would read the real repository and pass or fail for reasons
    that have nothing to do with the fixture.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Resolved: on macOS the temporary directory is reached through a symlink,
        # and the script resolves every path it returns. An unresolved fixture would
        # compare two spellings of the same folder and fail for nothing.
        self.repo = Path(self._tmp.name).resolve()
        self.base = self.repo / "guidance"
        self.base.mkdir()
        self._real_root = EXTRACTOR.REPO_ROOT
        EXTRACTOR.REPO_ROOT = self.repo
        self.addCleanup(lambda: setattr(EXTRACTOR, "REPO_ROOT", self._real_root))
        self.cfg = {"source_base": "guidance"}

    def topic(self, name: str, *pdfs: str) -> Path:
        folder = self.base / name
        folder.mkdir(exist_ok=True)
        for pdf in pdfs:
            (folder / pdf).write_bytes(b"%PDF")
        return folder


class DiscoverSourceRootsTests(_BaseFixture):
    """Resolving what to scan — string paths, missing folders, nothing configured.

    These three moved here when discovery was split out of `find_loose_pdfs`, which
    now receives folders somebody else already validated. Their tests did not move
    with them and sat red for fifteen commits against the old address, while the
    function that took the behaviour over had no tests at all.
    """

    def test_an_explicit_root_given_as_a_string_is_resolved(self) -> None:
        self.topic("extra", "a.pdf")
        roots = EXTRACTOR.discover_source_roots({"source_roots": ["guidance/extra"]})
        self.assertEqual([r.name for r in roots], ["extra"])

    def test_a_nonexistent_explicit_root_is_skipped(self) -> None:
        self.assertEqual(
            EXTRACTOR.discover_source_roots({"source_roots": ["definitely/not/here"]}), [])

    def test_nothing_configured_fails_closed(self) -> None:
        """Discovering nothing in silence reads the same as "everything is already ingested"."""
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.discover_source_roots({})

    def test_a_base_that_is_not_a_folder_fails_closed(self) -> None:
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.discover_source_roots({"source_base": "no-such-folder"})

    def test_every_child_holding_a_loose_pdf_is_promoted(self) -> None:
        self.topic("datasets", "a.pdf")
        self.topic("new-topic", "b.pdf")
        ingested = self.topic("done")
        (ingested / "x").mkdir()
        (ingested / "x" / "x.pdf").write_bytes(b"%PDF")
        roots = EXTRACTOR.discover_source_roots(self.cfg)
        self.assertEqual(sorted(r.name for r in roots), ["datasets", "new-topic"])


class FindLoosePdfsTests(_BaseFixture):
    def test_returns_only_loose_pdfs_not_already_ingested_ones(self) -> None:
        root = self.topic("papers", "b.pdf", "a.pdf")
        ingested = root / "c"
        ingested.mkdir()
        (ingested / "c.pdf").write_bytes(b"%PDF-c")
        (root / "note.txt").write_text("ignore", encoding="utf-8")
        self.assertEqual([p.name for p in EXTRACTOR.find_loose_pdfs([root])],
                         ["a.pdf", "b.pdf"])

    def test_an_uppercase_extension_is_still_a_pdf(self) -> None:
        root = self.topic("papers", "SHOUTY.PDF")
        self.assertEqual([p.name for p in EXTRACTOR.find_loose_pdfs([root])],
                         ["SHOUTY.PDF"])

    def test_a_directory_named_like_a_pdf_is_not_a_paper(self) -> None:
        root = self.topic("papers")
        (root / "trap.pdf").mkdir()
        self.assertEqual(EXTRACTOR.find_loose_pdfs([root]), [])


class UnfiledPdfsTests(_BaseFixture):
    """The PDF dropped into the base itself, beside the folders and in none of them.

    It is the worst pair: pending and invisible. Discovery only promotes
    CHILDREN of the base, so nobody finds it and the run reports that everything
    is ingested — the exact silence `source_base` fails closed against.
    """

    def test_a_pdf_beside_the_topic_folders_is_reported(self) -> None:
        self.topic("datasets", "inside.pdf")
        (self.base / "dropped.pdf").write_bytes(b"%PDF")
        self.assertEqual([p.name for p in EXTRACTOR.unfiled_pdfs(self.cfg)],
                         ["dropped.pdf"])

    def test_it_is_never_ingested_where_it_lies(self) -> None:
        """Converting it there would turn it into a topic of its own, and the next
        run would read it as an already-ingested folder and leave it there forever."""
        (self.base / "dropped.pdf").write_bytes(b"%PDF")
        roots = EXTRACTOR.discover_source_roots({**self.cfg, "source_roots": []})
        self.assertEqual(EXTRACTOR.find_loose_pdfs(roots), [])

    def test_a_pdf_inside_a_topic_is_not_unfiled(self) -> None:
        """The other pole: without it, a check that flagged everything would tell nothing apart."""
        self.topic("datasets", "inside.pdf")
        self.assertEqual(EXTRACTOR.unfiled_pdfs(self.cfg), [])

    def test_the_options_are_read_from_the_tree(self) -> None:
        self.topic("datasets")
        self.topic("reference-papers")
        (self.base / ".hidden").mkdir()
        self.assertEqual(EXTRACTOR.filing_options(self.cfg),
                         ["datasets", "reference-papers"])


class FileIntoTests(_BaseFixture):
    def test_filing_moves_it_into_an_existing_topic(self) -> None:
        self.topic("datasets")
        pdf = self.base / "dropped.pdf"
        pdf.write_bytes(b"%PDF")
        landed = EXTRACTOR.file_into(pdf, "datasets", self.cfg)
        self.assertEqual(landed, self.base / "datasets" / "dropped.pdf")
        self.assertFalse(pdf.exists())
        # And now ordinary discovery sees it, which is the point of filing.
        self.assertEqual([p.name for p in
                          EXTRACTOR.find_loose_pdfs(EXTRACTOR.discover_source_roots(self.cfg))],
                         ["dropped.pdf"])

    def test_a_new_topic_is_created(self) -> None:
        pdf = self.base / "dropped.pdf"
        pdf.write_bytes(b"%PDF")
        landed = EXTRACTOR.file_into(pdf, "brand-new", self.cfg)
        self.assertTrue(landed.is_file())

    def test_it_never_displaces_a_paper_already_there(self) -> None:
        """Two different papers under one name: moving would destroy the first."""
        self.topic("datasets", "dropped.pdf")
        pdf = self.base / "dropped.pdf"
        pdf.write_bytes(b"%PDF-other")
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.file_into(pdf, "datasets", self.cfg)
        self.assertTrue(pdf.exists(), "the original must stay where it was")

    def test_a_topic_that_escapes_the_base_is_refused(self) -> None:
        pdf = self.base / "dropped.pdf"
        pdf.write_bytes(b"%PDF")
        for folder in ("../outside", "nested/topic", ".hidden", ""):
            with self.assertRaises(EXTRACTOR.ConfigError, msg=folder):
                EXTRACTOR.file_into(pdf, folder, self.cfg)

    def test_only_a_pdf_sitting_in_the_base_can_be_filed(self) -> None:
        """A PDF already in a topic is not an unfiled pending one, and moving it
        would reorganize someone's library without being asked."""
        inside = self.topic("datasets", "inside.pdf") / "inside.pdf"
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.file_into(inside, "reference-papers", self.cfg)


class SingleTargetTests(unittest.TestCase):
    """An explicit ``<loose-pdf>`` argument is validated before the engine
    loads, so a mistyped path can never displace a file that is not a paper."""

    def test_accepts_a_loose_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "paper.pdf"
            pdf.write_bytes(b"%PDF-p")
            self.assertEqual(EXTRACTOR.resolve_single_target(str(pdf)), pdf.resolve())

    def test_rejects_a_missing_path(self) -> None:
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.resolve_single_target("/no/such/paper.pdf")

    def test_rejects_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.resolve_single_target(tmp)

    def test_rejects_a_non_pdf_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.txt"
            notes.write_text("research notes", encoding="utf-8")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.resolve_single_target(str(notes))

    def test_rejects_an_already_ingested_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "paper"
            folder.mkdir()
            pdf = folder / "paper.pdf"
            pdf.write_bytes(b"%PDF-p")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.resolve_single_target(str(pdf))

    def test_is_loose_recognises_the_ingested_layout(self) -> None:
        self.assertTrue(EXTRACTOR.is_loose(Path("/papers/foo.pdf")))
        self.assertFalse(EXTRACTOR.is_loose(Path("/papers/foo/foo.pdf")))


class ForceOcrTests(_BaseFixture):
    """Marker rebuilds a digital table from the PDF's own text layer
    (`tables_pdftext`) whenever one exists, in both modes. A poor text layer
    garbles those tables, and the only lever that skips the text layer is
    Marker's `force_ocr`. These tests check that the lever reaches the options
    handed to Marker -- they never load Marker itself."""

    def test_default_options_leave_the_text_layer_on(self) -> None:
        options = EXTRACTOR.marker_options(None, False)
        self.assertEqual(options, {"output_format": "markdown"})

    def test_force_ocr_reaches_the_marker_options(self) -> None:
        options = EXTRACTOR.marker_options("balanced", True)
        self.assertEqual(options, {"output_format": "markdown",
                                   "mode": "balanced", "force_ocr": True})

    def test_the_configuration_accepts_a_boolean_force_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "papersmith.yaml"
            path.write_text("paper_ingestion:\n  force_ocr: true\n", encoding="utf-8")
            self.assertTrue(EXTRACTOR.load_config(path)["force_ocr"])

    def test_a_non_boolean_force_ocr_is_a_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "papersmith.yaml"
            path.write_text("paper_ingestion:\n  force_ocr: sometimes\n", encoding="utf-8")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def _engine_arguments(self, argv: list[str], cfg: dict) -> tuple:
        """Run `main` up to the engine load and return (engine, mode, force_ocr, cache)."""
        self.topic("reference-papers", "paper.pdf")
        seen: list[tuple] = []

        def refuse(*args):
            seen.append(args)
            raise EXTRACTOR.EngineError("not loaded in a unit test")

        real_load, real_build = EXTRACTOR.load_config, EXTRACTOR.build_engine
        EXTRACTOR.load_config = lambda: {**self.cfg, **cfg}
        EXTRACTOR.build_engine = refuse
        real_argv = sys.argv
        sys.argv = ["extract_pdf.py", *argv]
        try:
            from contextlib import redirect_stderr, redirect_stdout
            import io
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(EXTRACTOR.main(), 2)
        finally:
            EXTRACTOR.load_config, EXTRACTOR.build_engine = real_load, real_build
            sys.argv = real_argv
        self.assertEqual(len(seen), 1)
        return seen[0]

    def _converter_arguments(self, argv: list[str], cfg: dict) -> tuple:
        """The (mode, force_ocr) pair handed to the engine."""
        arguments = self._engine_arguments(argv, cfg)
        return arguments[1], arguments[2]

    def test_the_flag_forces_ocr_for_this_run(self) -> None:
        self.assertEqual(self._converter_arguments(["--force-ocr"], {}), (None, True))

    def test_the_configuration_forces_ocr_when_no_flag_is_given(self) -> None:
        self.assertEqual(self._converter_arguments([], {"force_ocr": True, "mode": "fast"}),
                         ("fast", True))

    def test_without_either_the_text_layer_stays_on(self) -> None:
        self.assertEqual(self._converter_arguments([], {}), (None, False))


class EngineSelectionTests(_BaseFixture):
    """Which engine a run asks for, and that the page cache follows the switches."""

    _engine_arguments = ForceOcrTests._engine_arguments

    def test_the_default_engine_routes_pages_and_caches_them(self) -> None:
        engine, _mode, _ocr, cache, _cpu = self._engine_arguments([], {})
        self.assertEqual(engine, "auto")
        self.assertEqual(cache, EXTRACTOR.REPO_ROOT / EXTRACTOR.CACHE_DIR)

    def test_the_configured_engine_is_used(self) -> None:
        self.assertEqual(self._engine_arguments([], {"engine": "marker"})[0], "marker")

    def test_the_flag_overrides_the_configured_engine(self) -> None:
        self.assertEqual(self._engine_arguments(["--engine", "pdfium"], {"engine": "docling"})[0], "pdfium")

    def test_no_cache_from_the_flag_or_the_configuration(self) -> None:
        self.assertIsNone(self._engine_arguments(["--no-cache"], {})[3])
        self.assertIsNone(self._engine_arguments([], {"cache": False})[3])

    def test_formulas_on_cpu_reaches_the_engine(self) -> None:
        self.assertFalse(self._engine_arguments([], {})[4])
        self.assertTrue(self._engine_arguments([], {"formulas_on_cpu": True})[4])

    def test_a_non_boolean_cache_is_a_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "papersmith.yaml"
            path.write_text("paper_ingestion:\n  cache: maybe\n", encoding="utf-8")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_marker_is_built_only_when_named_and_its_license_is_stated(self) -> None:
        import io
        from contextlib import redirect_stderr

        calls = []
        real = EXTRACTOR.build_converter
        EXTRACTOR.build_converter = lambda mode, force_ocr: calls.append((mode, force_ocr)) or "marker"
        try:
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(EXTRACTOR.build_engine("marker", "fast", False, None), "marker")
                routed = EXTRACTOR.build_engine("auto", None, False, None)
        finally:
            EXTRACTOR.build_converter = real
        self.assertEqual(calls, [("fast", False)])
        self.assertIn("USD 5M", err.getvalue())
        self.assertIsInstance(routed, EXTRACTOR.RoutedEngine)


if __name__ == "__main__":
    unittest.main()
