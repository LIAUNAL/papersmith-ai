"""`paper_tikz.py` — the pure TikZ optimization transforms, and
`paper_figure.optimize_figure()`'s compile-validated commit pipeline.

Three tiers, matching `test_paper_figure.py`'s own convention:

* pure transforms (no disk at all) — the library map, the `\\tikzset`
  factoring rules, idempotency, and the `% node:` marker contract;
* the pipeline with an INJECTED compile (monkeypatched `paper_latex.compile`,
  hermetic, no toolchain) — commit-only-on-success and the rollback;
* one real-toolchain case that refuses `LATEX_TOOLCHAIN_ABSENT` when no
  `latexmk` exists rather than skipping into a vacuous pass.
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_figure  # noqa: E402
import paper_latex  # noqa: E402
import paper_tikz  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: A figure the optimizer has real work to do on: two libraries it can prove
#: unused (`shapes.geometric`, `calc`), one it can detect as missing
#: (`positioning`, triggered by `below=of`), and the same non-positional
#: option list on two sites — while `beta`'s copy carries `below=of a`, so it
#: must NOT join the factored style. `gamma` sits clear of `alpha` with an
#: `at` outside its option list, so the list still matches `alpha`'s and the
#: rendered audit finds no text overlap.
BLOATED = r"""\documentclass[tikz,border=2pt]{standalone}
\usepackage{tikz}
\usetikzlibrary{shapes.geometric,calc}
\begin{document}
\begin{tikzpicture}
% node: alpha
\node[draw, rounded corners, fill=blue!10] (a) {Alpha};
% node: beta
\node[draw, rounded corners, fill=blue!10, below=of a] (b) {Beta};
% node: gamma
\node[draw, rounded corners, fill=blue!10] (c) at (2.5,0) {Gamma};
\draw[->] (a) -- (b);
\draw[->] (b) -- (c);
\end{tikzpicture}
\end{document}
"""

#: Already optimal: only the library it uses, no repeated non-positional
#: option list (the two nodes differ precisely by their positional key).
OPTIMAL = r"""\documentclass[tikz,border=2pt]{standalone}
\usepackage{tikz}
\usetikzlibrary{positioning}
\begin{document}
\begin{tikzpicture}
% node: alpha
\node[draw] (a) {Alpha};
% node: beta
\node[draw, below=of a] (b) {Beta};
\draw[->] (a) -- (b);
\end{tikzpicture}
\end{document}
"""

#: The trap: `below=of` appears ONLY inside a comment. A detector that ran on
#: the raw source would add `positioning` for a construct nobody draws.
COMMENT_ONLY_TRIGGER = r"""\documentclass[tikz,border=2pt]{standalone}
\begin{document}
\begin{tikzpicture}
% node: alpha
\node[draw] (a) {Alpha};
% a ghost we never draw: \node[below=of a] (ghost) {Ghost};
\end{tikzpicture}
\end{document}
"""


class OptimizerLibraryTests(unittest.TestCase):
    """`scan_libraries`/`detect_required_libraries`/`merge_libraries`."""

    def test_positioning_is_detected_from_relative_placement(self) -> None:
        self.assertIn("positioning", paper_tikz.detect_required_libraries(BLOATED))

    def test_calc_is_detected_from_coordinate_math(self) -> None:
        source = "\\draw ($ (a)!0.5!(b) $) -- (c);"
        self.assertIn("calc", paper_tikz.detect_required_libraries(source))

    def test_arrows_meta_is_detected_from_a_tipped_arrowhead(self) -> None:
        source = "\\draw[-{Stealth}] (a) -- (b);"
        self.assertIn("arrows.meta", paper_tikz.detect_required_libraries(source))

    def test_a_plain_arrow_never_pulls_in_arrows_meta(self) -> None:
        # `->` is base TikZ; demanding arrows.meta for it would add a library
        # every ordinary diagram would then carry for nothing.
        self.assertNotIn("arrows.meta", paper_tikz.detect_required_libraries("\\draw[->] (a) -- (b);"))

    def test_a_trigger_inside_a_comment_never_adds_a_library(self) -> None:
        self.assertNotIn(
            "positioning", paper_tikz.detect_required_libraries(COMMENT_ONLY_TRIGGER),
        )

    def test_merging_into_an_existing_declaration_deduplicates(self) -> None:
        merged = paper_tikz.merge_libraries(OPTIMAL, {"calc", "positioning"})
        self.assertEqual(merged.count("\\usetikzlibrary"), 1)
        self.assertEqual(paper_tikz.scan_libraries(merged), {"positioning", "calc"})

    def test_a_library_this_module_cannot_detect_is_never_pruned(self) -> None:
        source = "\\documentclass[tikz,border=2pt]{standalone}\n\\usetikzlibrary{intersections}\n"
        result = paper_tikz.optimize(source)
        self.assertIn("intersections", paper_tikz.scan_libraries(result.text))

    def test_an_added_library_lands_in_the_preamble(self) -> None:
        # Found by smoke-testing the real CLI, not by the unit tests: an
        # inserted `\usetikzlibrary` AFTER `\begin{document}` still compiles
        # in the simple case, which is exactly why the misplacement would
        # survive until a preamble-time library was involved.
        source = "\\documentclass[tikz,border=2pt]{standalone}\n\\begin{document}\n\\end{document}\n"
        merged = paper_tikz.merge_libraries(source, {"calc"})
        self.assertLess(merged.index("\\usetikzlibrary"), merged.index("\\begin{document}"))

    def test_a_factored_style_lands_in_the_preamble_with_no_library_line(self) -> None:
        source = (
            "\\documentclass[tikz,border=2pt]{standalone}\n"
            "\\begin{document}\n"
            "\\node[draw] (a) {A};\n"
            "\\node[draw] (b) {B};\n"
            "\\end{document}\n"
        )
        rewritten, styles = paper_tikz.factor_styles(source)
        self.assertEqual(len(styles), 1)
        self.assertLess(rewritten.index("\\tikzset"), rewritten.index("\\begin{document}"))

    def test_removing_a_library_leaves_no_blank_line_behind(self) -> None:
        source = (
            "\\documentclass[tikz,border=2pt]{standalone}\n"
            "\\usetikzlibrary{calc}\n"
            "\\begin{document}\n\\end{document}\n"
        )
        result = paper_tikz.optimize(source)
        self.assertNotIn("\\usetikzlibrary", result.text)
        self.assertNotIn("\n\n\n", result.text)

    def test_an_undetectable_library_name_is_reported_as_removed_only_when_proven(self) -> None:
        result = paper_tikz.optimize(BLOATED)
        self.assertEqual(set(result.libraries_removed), {"shapes.geometric", "calc"})
        self.assertEqual(set(result.libraries_added), {"positioning"})


class OptimizerStyleTests(unittest.TestCase):
    """`factor_styles` — the conservative factoring rules."""

    def test_two_identical_non_positional_lists_factor_into_one_style(self) -> None:
        # Two groups in BLOATED: the `alpha`/`gamma` node option list, and
        # the `->` arrow option list shared by the two `\draw` paths.
        rewritten, styles = paper_tikz.factor_styles(BLOATED)
        self.assertEqual(len(styles), 2)
        self.assertTrue(all(name.startswith("ps-") for name in styles))
        self.assertEqual(rewritten.count("\\tikzset"), 1)
        for name in styles:
            self.assertIn(f"[{name}]", rewritten)

    def test_an_option_naming_a_coordinate_is_never_factored(self) -> None:
        # `fit=(a)(b)` bakes in two specific nodes; a shared style that
        # carried it would attach every site to those two.
        source = (
            "\\node[fit=(a)(b)] (g) {};\n"
            "\\node[fit=(a)(b)] (h) {};\n"
        )
        _, styles = paper_tikz.factor_styles(source)
        self.assertEqual(styles, ())

    def test_a_list_differing_only_by_a_positional_key_is_never_factored(self) -> None:
        # `beta` carries `below=of a`; `alpha`/`gamma` do not. `beta`'s own
        # list must survive verbatim or the diagram would move, so
        # `rounded corners` survives exactly twice: once in `beta`'s inline
        # list, once in the one `\tikzset` definition.
        rewritten, styles = paper_tikz.factor_styles(BLOATED)
        self.assertEqual(len(styles), 2)
        self.assertIn("below=of a", rewritten)
        self.assertEqual(rewritten.count("rounded corners"), 2)
        self.assertIn("\\node[draw, rounded corners, fill=blue!10, below=of a] (b)", rewritten)

    def test_a_site_already_carrying_a_generated_style_is_left_alone(self) -> None:
        once, styles = paper_tikz.factor_styles(BLOATED)
        twice, second_styles = paper_tikz.factor_styles(once)
        self.assertNotEqual(styles, ())
        self.assertEqual(second_styles, ())
        self.assertEqual(twice, once)

    def test_nothing_to_factor_reports_nothing(self) -> None:
        rewritten, styles = paper_tikz.factor_styles(OPTIMAL)
        self.assertEqual(styles, ())
        self.assertEqual(rewritten, OPTIMAL)


class OptimizerIdempotencyTests(unittest.TestCase):
    """`optimize(optimize(x).text).text == optimize(x).text`, both fixtures."""

    def test_bloated_source_reaches_a_fixed_point(self) -> None:
        once = paper_tikz.optimize(BLOATED)
        twice = paper_tikz.optimize(once.text)
        self.assertEqual(twice.text, once.text)
        self.assertEqual(twice.styles_factored, ())
        self.assertEqual(twice.libraries_added, ())
        self.assertEqual(twice.libraries_removed, ())

    def test_already_optimal_source_is_byte_identical(self) -> None:
        result = paper_tikz.optimize(OPTIMAL)
        self.assertEqual(result.text, OPTIMAL)
        self.assertEqual(result.changes, ())


class OptimizerMarkerSafetyTests(unittest.TestCase):
    """`% node:` markers are the manifest contract, never comment litter."""

    def _markers(self, tex: str) -> list:
        """The skill's own marker grammar, read through its own regex —
        never a second copy of `%\\s*node:\\s*(\\S+)` that could drift."""
        return sorted(paper_figure._NODE_MARKER_RE.findall(tex))

    def test_markers_survive_a_default_optimize(self) -> None:
        marker_text = BLOATED
        result = paper_tikz.optimize(marker_text)
        self.assertEqual(self._markers(result.text), ["alpha", "beta", "gamma"])

    def test_markers_survive_even_when_comments_are_stripped(self) -> None:
        result = paper_tikz.optimize(BLOATED, strip_comments=True)
        self.assertEqual(self._markers(result.text), ["alpha", "beta", "gamma"])

    def test_ordinary_comments_are_only_stripped_when_asked(self) -> None:
        with_comments = paper_tikz.optimize(BLOATED)
        self.assertIn("% a ghost we never draw", paper_tikz.optimize(COMMENT_ONLY_TRIGGER).text)
        stripped = paper_tikz.optimize(COMMENT_ONLY_TRIGGER, strip_comments=True)
        self.assertNotIn("a ghost we never draw", stripped.text)
        self.assertIn("% node: alpha", stripped.text)
        self.assertIsNotNone(with_comments)

    def test_the_manifest_cross_check_still_passes_on_the_optimized_source(self) -> None:
        manifest = {"components": ["alpha", "beta", "gamma"]}
        result = paper_tikz.optimize(BLOATED)
        paper_figure.cross_check_manifest(manifest, result.text)


class OptimizerHeaderTests(unittest.TestCase):
    """`normalize_header` — insert when absent, never silently re-author."""

    def test_a_headerless_source_gains_the_standalone_header(self) -> None:
        result = paper_tikz.optimize("\\begin{document}\n\\end{document}\n")
        self.assertIn(paper_tikz.STANDALONE_HEADER, result.text)

    def test_an_authors_document_class_is_never_swapped(self) -> None:
        source = "\\documentclass{article}\n\\begin{document}\n\\end{document}\n"
        result = paper_tikz.optimize(source)
        self.assertIn("\\documentclass{article}", result.text)
        self.assertTrue(any("not 'standalone'" in warning for warning in result.warnings))

    def test_a_standalone_header_without_a_border_is_warned_not_rewritten(self) -> None:
        source = "\\documentclass[tikz]{standalone}\n\\begin{document}\n\\end{document}\n"
        result = paper_tikz.optimize(source)
        self.assertIn("\\documentclass[tikz]{standalone}", result.text)
        self.assertTrue(any("border" in warning for warning in result.warnings))


class OptimizerGuardTests(unittest.TestCase):
    """Static guards report; they never claim a ceiling nobody measured."""

    def test_a_self_recursive_macro_is_reported(self) -> None:
        warnings = paper_tikz.scan_memory_guards("\\def\\loop{\\loop}\n")
        self.assertTrue(any("expands to itself" in warning for warning in warnings))

    def test_a_clean_source_reports_no_guard(self) -> None:
        self.assertEqual(paper_tikz.scan_memory_guards(OPTIMAL), ())

    def test_the_guard_sets_no_hard_limit_and_records_what_is_unproven(self) -> None:
        # Honesty lock, at the level the invariant actually holds: the module
        # must be STRUCTURALLY unable to set a limit — no `os` (so it cannot
        # write an environment variable) and no route to the compiler at all
        # — and it must record the M1 result including the part that stayed
        # unproven. Grepping for the bare strings `main_memory=` or
        # `--cnf-line` would have forbidden the very documentation that makes
        # the measurement inheritable, which is the opposite of the point.
        source = Path(str(paper_tikz.__file__)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertEqual(imported & {"os", "subprocess", "multiprocessing"}, set())
        self.assertNotIn("paper_latex", imported)
        self.assertIn("UNPROVEN", source)
        self.assertIn("M1", source)


class OptimizerNoSubprocessTests(unittest.TestCase):
    """`paper_tikz.py` is pure: no process primitive, ever."""

    def test_the_module_imports_no_forbidden_process_primitive(self) -> None:
        tree = ast.parse(Path(str(paper_tikz.__file__)).read_text(encoding="utf-8"))
        found: list = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("subprocess", "multiprocessing"):
                        found.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module in ("subprocess", "multiprocessing"):
                found.append(node.module)
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and (node.attr in ("system", "popen") or node.attr.startswith("exec"))
            ):
                found.append(f"os.{node.attr}")
        self.assertEqual(found, [])


class OptimizerPipelineTests(unittest.TestCase):
    """`paper_figure.optimize_figure` — guards, compile, atomic commit.

    The compile is INJECTED (monkeypatched `paper_latex.compile`), so this
    class is hermetic and never needs a toolchain; the real-toolchain case
    lives in `OptimizerRealToolchainTests` below.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.figures = self.paper_dir / "Figures"
        self.figures.mkdir(parents=True)
        self.figure_id = "bloated"
        self.tex_path = self.figures / f"{self.figure_id}.tex"
        self.tex_path.write_text(BLOATED, encoding="utf-8")
        (self.figures / f"{self.figure_id}.diagram.json").write_text(
            json.dumps({"components": ["alpha", "beta", "gamma"], "encodings": [], "caption": "Figure."}),
            encoding="utf-8",
        )
        self._original = paper_latex.compile

    def tearDown(self) -> None:
        paper_latex.compile = self._original

    def _inject(self, verdict: str):
        calls: list = []

        def fake_compile(figure_dir, figure_id, scratch_dir, *, path=None, timeout=300):
            calls.append({"figure_dir": figure_dir, "figure_id": figure_id, "scratch_dir": scratch_dir})
            scratch_dir.mkdir(parents=True, exist_ok=True)
            return paper_latex.CompileResult(
                exit_code=0 if verdict == "success" else 1,
                pdf_written=verdict == "success",
                log_path=scratch_dir / f"{figure_id}.log",
                diagnostics=() if verdict == "success" else (paper_latex.Diagnostic("error", 3, "boom"),),
                verdict=verdict,
            )

        paper_latex.compile = fake_compile
        return calls

    def test_a_successful_compile_commits_the_candidate(self) -> None:
        self._inject("success")
        result = paper_figure.optimize_figure(self.paper_dir, self.figure_id)
        self.assertEqual(result["verdict"], "committed")
        self.assertIn("\\tikzset", self.tex_path.read_text(encoding="utf-8"))

    def test_a_failing_compile_rolls_back_and_leaves_the_source_byte_identical(self) -> None:
        # A repairable compile failure is the loop's ordinary cost, not a
        # guard blocking anything (`paper_figure.render`'s own reading): the
        # call succeeds and reports the rollback, and the original bytes are
        # untouched. Never a new refusal code.
        self._inject("failure")
        result = paper_figure.optimize_figure(self.paper_dir, self.figure_id)
        self.assertEqual(result["verdict"], "rolled_back")
        self.assertEqual(result["diagnostics"], ["boom"])
        self.assertEqual(self.tex_path.read_text(encoding="utf-8"), BLOATED)

    def test_no_compile_still_runs_stop_a_and_the_manifest_cross_check(self) -> None:
        # A candidate that would fail stop A must be discarded with the
        # original byte-identical, even when the caller skipped compiling.
        self.tex_path.write_text(BLOATED + "\\begin{axis}\\end{axis}\n", encoding="utf-8")
        before = self.tex_path.read_text(encoding="utf-8")
        with self.assertRaises(Refused) as caught:
            paper_figure.optimize_figure(self.paper_dir, self.figure_id, compile_candidate=False)
        self.assertEqual(caught.exception.code, "DIAGRAM_PLOTS_DATA")
        self.assertEqual(self.tex_path.read_text(encoding="utf-8"), before)

    def test_a_marker_dropping_candidate_is_refused_before_any_write(self) -> None:
        bad = BLOATED.replace("% node: gamma", "% removed")
        self.tex_path.write_text(bad, encoding="utf-8")
        (self.figures / f"{self.figure_id}.diagram.json").write_text(
            json.dumps({"components": ["alpha", "beta", "gamma"], "encodings": [], "caption": "Figure."}),
            encoding="utf-8",
        )
        with self.assertRaises(Refused) as caught:
            paper_figure.optimize_figure(self.paper_dir, self.figure_id, compile_candidate=False)
        self.assertEqual(caught.exception.code, "MANIFEST_SOURCE_MISMATCH")
        self.assertEqual(self.tex_path.read_text(encoding="utf-8"), bad)

    def test_an_absent_source_refuses_with_the_reused_code(self) -> None:
        with self.assertRaises(Refused) as caught:
            paper_figure.optimize_figure(self.paper_dir, "no-such-figure")
        self.assertEqual(caught.exception.code, "DIAGRAM_SOURCE_ABSENT")

    def test_dry_run_writes_nothing(self) -> None:
        result = paper_figure.render_optimized_text(self.tex_path)
        self.assertIn("\\tikzset", result["text"])
        self.assertEqual(self.tex_path.read_text(encoding="utf-8"), BLOATED)

    def test_the_candidate_is_written_under_the_real_figure_id(self) -> None:
        calls = self._inject("success")
        paper_figure.optimize_figure(self.paper_dir, self.figure_id)
        self.assertEqual([call["figure_id"] for call in calls], [self.figure_id])


class OptimizerRealToolchainTests(unittest.TestCase):
    """One real `latexmk` case. Absent toolchain REFUSES, never skips."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        self.figures = self.paper_dir / "Figures"
        self.figures.mkdir(parents=True)
        self.figure_id = "real"
        (self.figures / f"{self.figure_id}.tex").write_text(BLOATED, encoding="utf-8")
        (self.figures / f"{self.figure_id}.diagram.json").write_text(
            json.dumps({"components": ["alpha", "beta", "gamma"], "encodings": [], "caption": "Figure."}),
            encoding="utf-8",
        )

    def test_the_optimized_candidate_compiles_on_a_real_toolchain(self) -> None:
        try:
            paper_latex.discover_latexmk(None)
        except Refused as exc:
            # Plan §8: never a silent skip that reads as a pass. The refusal
            # IS the measured result on a machine without a TeX distribution.
            self.assertEqual(exc.code, "LATEX_TOOLCHAIN_ABSENT")
            return
        result = paper_figure.optimize_figure(self.paper_dir, self.figure_id)
        self.assertEqual(result["verdict"], "committed")
        self.assertTrue(result["compiled"], "the real latexmk must have been the validator")
        # And the committed source still renders end to end: `optimize`
        # commits the SOURCE, never a PDF -- `render` owns the PDF, so the
        # proof that compilation was preserved is that `render` still wins.
        rendered = paper_figure.render(self.paper_dir, self.figure_id)
        self.assertEqual(rendered["verdict"], "success")
        self.assertTrue(paper_figure.figure_paths(self.paper_dir, self.figure_id)["pdf"].is_file())


if __name__ == "__main__":
    unittest.main()
