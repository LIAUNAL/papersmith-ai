"""The review line: `smith init --kind review` beside the unchanged experimental line.

A review workspace (PRISMA 2020 systematic review) receives the review section
contracts at `sections/`, the review flow in its harness entrypoints and the
`review/` records folder; an experimental workspace receives exactly what it
received before the review line existed.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from papersmith.cli import main
from papersmith.core import init as init_module, manifest, upgrade as upgrade_module
from papersmith.errors import UserError
from papersmith.kit import resolve_and_validate

ROOT = Path(__file__).resolve().parents[1]
REVIEW_SECTIONS = sorted(p.name for p in (ROOT / "sections-review").glob("*.md"))
EXPERIMENTAL_SECTIONS = sorted(p.name for p in (ROOT / "sections").glob("*.md"))


class ReviewLineCase(unittest.TestCase):
    def new_tmp(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def init(self, kind: str | None = None) -> Path:
        workspace = self.new_tmp() / "ws"
        kwargs = {} if kind is None else {"kind": kind}
        init_module.initialize(workspace, tools=("claude", "opencode", "pi", "antigravity"),
                               run_npm=False, run_env=False, **kwargs)
        return workspace

    @staticmethod
    def config(workspace: Path) -> dict:
        return json.loads((workspace / ".papersmith" / "config.json").read_text(encoding="utf-8"))


class ExperimentalLineUnchangedTests(ReviewLineCase):
    def test_default_init_gets_no_review_file_and_records_no_kind(self) -> None:
        workspace = self.init()
        self.assertNotIn("paper_kind", self.config(workspace))
        self.assertEqual(sorted(p.name for p in (workspace / "sections").glob("*.md")), EXPERIMENTAL_SECTIONS)
        self.assertFalse((workspace / "sections-review").exists())
        self.assertFalse((workspace / "skills" / "systematic-review").exists())
        self.assertFalse((workspace / ".claude" / "commands" / "systematic-review.md").exists())
        self.assertFalse((workspace / "review").exists())
        for folder in ("proposals", "experiments", "implementations", "kaggle-inbox"):
            self.assertTrue((workspace / folder).is_dir(), folder)
        claude = (workspace / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("**Proof of concept and experiments**", claude)
        self.assertNotIn("review line", claude)

    def test_explicit_experimental_kind_is_the_default(self) -> None:
        default, explicit = self.init(), self.init("experimental")
        self.assertEqual(self.config(default).keys(), self.config(explicit).keys())
        self.assertEqual(sorted(p.relative_to(default).as_posix() for p in default.rglob("*") if p.is_file()),
                         sorted(p.relative_to(explicit).as_posix() for p in explicit.rglob("*") if p.is_file()))

    def test_experimental_layout_is_the_kit_without_review_only_paths(self) -> None:
        kit = resolve_and_validate()
        layout = manifest.kit_layout(kit, "experimental")
        self.assertTrue(all(source == target for target, source in layout.items()))
        expected = {p for p in manifest.kit_files(kit) if not p.startswith(manifest.REVIEW_ONLY_PREFIXES)}
        self.assertEqual(set(layout), expected)


class ReviewInitTests(ReviewLineCase):
    def test_review_init_records_the_kind_and_the_review_layout(self) -> None:
        workspace = self.init("review")
        self.assertEqual(self.config(workspace)["paper_kind"], "review")
        self.assertEqual(sorted(p.name for p in (workspace / "sections").glob("*.md")),
                         sorted(REVIEW_SECTIONS + [Path(p).name for p in manifest.REVIEW_SHARED_SECTIONS]))
        for name in REVIEW_SECTIONS:
            self.assertEqual((workspace / "sections" / name).read_bytes(),
                             (ROOT / "sections-review" / name).read_bytes())
        self.assertFalse((workspace / "sections-review").exists())
        self.assertTrue((workspace / "review" / ".gitkeep").is_file())
        self.assertTrue((workspace / "skills" / "systematic-review" / "scripts" / "review_cli.py").is_file())
        self.assertTrue((workspace / ".claude" / "commands" / "systematic-review.md").is_file())
        for folder in ("proposals", "experiments", "implementations", "kaggle-inbox"):
            self.assertFalse((workspace / folder).exists(), folder)

    def test_every_harness_entrypoint_carries_the_review_flow(self) -> None:
        workspace = self.init("review")
        for entry in ("CLAUDE.md", "OPENCODE.md", ".pi/APPEND_SYSTEM.md", ".agents/AGENTS.md"):
            text = (workspace / entry).read_text(encoding="utf-8")
            self.assertIn("## Paper construction flow (review line)", text, entry)
            self.assertIn("PRISMA 2020", text, entry)
            self.assertNotIn("**Proof of concept and experiments**", text, entry)

    def test_cli_flag_and_its_refusal(self) -> None:
        workspace = self.new_tmp() / "ws"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["init", str(workspace), "--kind", "review", "--tools", "claude", "--no-npm",
                         "--no-env", "--no-progress"])
        self.assertEqual(code, 0)
        self.assertIn("Paper line: review", out.getvalue())
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(io.StringIO()):
            main(["init", str(self.new_tmp() / "other"), "--kind", "survey"])
        self.assertEqual(ctx.exception.code, 2)
        with self.assertRaises(UserError):
            init_module.initialize(self.new_tmp() / "api", kind="survey", run_npm=False, run_env=False)

    def test_an_unknown_recorded_kind_refuses(self) -> None:
        workspace = self.init("review")
        path = workspace / ".papersmith" / "config.json"
        data = self.config(workspace)
        data["paper_kind"] = "survey"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(UserError):
            manifest.paper_kind(workspace)


class ReviewUpgradeAndDriftTests(ReviewLineCase):
    def test_upgrade_keeps_the_review_layout_and_repairs_a_review_contract(self) -> None:
        workspace = self.init("review")
        (workspace / "sections" / "05-methods.md").unlink()
        result = upgrade_module.upgrade(workspace)
        self.assertIn("sections/05-methods.md", result["changed_files"])
        self.assertEqual((workspace / "sections" / "05-methods.md").read_bytes(),
                         (ROOT / "sections-review" / "05-methods.md").read_bytes())
        names = sorted(p.name for p in (workspace / "sections").glob("*.md"))
        for name in EXPERIMENTAL_SECTIONS:
            if f"sections/{name}" not in manifest.REVIEW_SHARED_SECTIONS:
                self.assertNotIn(name, names)
        self.assertFalse((workspace / "sections-review").exists())

    def test_a_fresh_review_workspace_reports_no_drift(self) -> None:
        workspace = self.init("review")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["status", str(workspace)])
        self.assertEqual(code, 0)
        self.assertIn("Framework drift: none", out.getvalue())


class ReviewContractsTests(ReviewLineCase):
    def test_the_paper_writing_engine_accepts_the_review_corpus(self) -> None:
        workspace = self.init("review")
        cli = workspace / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
        for argv in (["contract"], ["scaffold"], ["phases"]):
            completed = subprocess.run([sys.executable, str(cli), *argv], cwd=workspace,
                                       capture_output=True, text=True, timeout=120)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "ok", (argv, completed.stdout, completed.stderr))
        blocks = {block["block"] for wave in payload["waves"] for block in wave["blocks"]}
        for block in ("methods.m-search-strategy", "methods.m-selection-process", "results.r-study-selection",
                      "results.r-thematic-synthesis", "abstract.abs-other", "back-matter.bm-funding"):
            self.assertIn(block, blocks)

    def test_the_prisma_checklist_reads_the_written_blocks_and_the_registration(self) -> None:
        workspace = self.init("review")
        paper = workspace / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
        review = workspace / "skills" / "systematic-review" / "scripts" / "review_cli.py"

        def run(cli, *argv, stdin=None):
            completed = subprocess.run([sys.executable, str(cli), *argv], cwd=workspace, input=stdin,
                                       capture_output=True, text=True, timeout=120)
            return json.loads(completed.stdout)

        def item(number):
            return run(review, "checklist")["items"][number - 1]

        self.assertEqual(run(paper, "scaffold")["status"], "ok")
        self.assertIn("text:methods.m-eligibility", item(5)["missing"])
        run(paper, "open", "--block", "methods.m-eligibility", "--at-end")
        self.assertIn("text:methods.m-eligibility", item(5)["missing"])  # opened but empty
        body = workspace / "body.tex"
        body.write_text("Studies were eligible when they evaluated a method on real data.\n", encoding="utf-8")
        self.assertEqual(run(paper, "substitute", "--block", "methods.m-eligibility", "--body", str(body))["status"], "ok")
        self.assertEqual(item(5)["missing"], ["record:protocol"])
        self.assertIn("declaration:review-registration", item(24)["missing"])
        run(paper, "declare", "--declaration", "review-registration", "--value", "OSF 10.17605/OSF.IO/ABCDE")
        self.assertNotIn("declaration:review-registration", item(24)["missing"])

    def test_review_registration_is_a_declaration(self) -> None:
        sys.path.insert(0, str(ROOT / "skills" / "paper-writing" / "scripts"))
        try:
            import paper_vocabulary
        finally:
            sys.path.pop(0)
        paper_vocabulary.validate_declaration("review-registration")
        self.assertNotIn("review-registration", paper_vocabulary.FACTS)



def review_body(name: str) -> str:
    return (ROOT / "sections-review" / name).read_text(encoding="utf-8").split("\n---\n", 1)[1]


class ReviewWritingRulesTests(unittest.TestCase):
    """The review contracts carry their own house style, measured on the group's review A029."""

    def test_the_review_sections_follow_the_groups_review_structure(self) -> None:
        names = [json.loads((ROOT / "sections-review" / name).read_text(encoding="utf-8")
                            .split("---\n", 2)[1])["section"] for name in REVIEW_SECTIONS]
        self.assertEqual(names, ["title-and-keywords", "abstract", "introduction", "background", "methods",
                                 "results", "discussion", "limitations", "conclusions"])

    def test_every_review_contract_carries_its_house_style_before_its_disqualifiers_and_an_extent(self) -> None:
        from skills._core.command_center import state_extractor
        for name in REVIEW_SECTIONS:
            with self.subTest(contract=name):
                text = review_body(name)
                self.assertEqual(text.count("\n## LIA house style\n"), 1)
                self.assertLess(text.index("\n## LIA house style\n"), text.index("\n## Disqualifiers\n"))
                self.assertIn("Measured on the group's MDPI review A029", text)
                low, high = state_extractor._extent(text)
                self.assertIsNotNone(low)
                self.assertLess(low, high)

    def test_the_results_are_a_comparative_synthesis(self) -> None:
        text = review_body("06-results.md")
        self.assertIn("compares at least two studies along one dimension", text)
        self.assertIn("A comparison table per theme", text)
        disqualifiers = text.split("\n## Disqualifiers\n", 1)[1]
        for rule in ("A citation as the subject of a sentence: *The paper by [n]*",
                     "Three or more consecutive sentences about one study.",
                     "A sub-theme without its closing synthesis sentence",
                     "An included study cited nowhere in the results."):
            with self.subTest(rule=rule):
                self.assertIn(rule, disqualifiers)

    def test_the_methods_refuse_example_keywords_for_a_search_strategy(self) -> None:
        disqualifiers = review_body("05-methods.md").split("\n## Disqualifiers\n", 1)[1]
        self.assertIn("A search strategy given as example keywords (*terms such as*)", disqualifiers)

    def test_the_background_names_the_problem_classes_the_results_use(self) -> None:
        self.assertIn("same names", review_body("04-background.md"))
        header = json.loads((ROOT / "sections-review" / "06-results.md").read_text(encoding="utf-8").split("---\n", 2)[1])
        synthesis = next(b for b in header["blocks"] if b["id"] == "r-thematic-synthesis")
        self.assertIn("background.bg-open-problems", [edge["target"] for edge in synthesis["after"]])

    def test_the_experimental_contracts_carry_no_review_rule(self) -> None:
        for name in EXPERIMENTAL_SECTIONS:
            with self.subTest(contract=name):
                text = (ROOT / "sections" / name).read_text(encoding="utf-8")
                self.assertNotIn("A029", text)
                self.assertNotIn("comparative synthesis", text)


if __name__ == "__main__":
    unittest.main()
