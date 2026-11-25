"""The section contracts of the observational and measurement studies line.

`sections-observational-measurement/` holds the contracts a workspace of that
line receives at `sections/`, beside the shared back matter
`sections/10-back-matter.md`, as the review line does with `sections-review/`
(paper-type-lines S8, T8-O1; decisions E4 and E7 of L66, accepted in L67).
The sections carry generic IMRaD names so the STROBE, STARD 2015 and COSMIN
`default` targets resolve; the methods and results blocks are bound to the
study facts and declarations of T7; every contract states that the assistant
never generates measurements or data and that ethics, consent, data collection
and the choice of primary outcome stay human.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from papersmith.core import init as init_module, manifest
from skills._core.checklists import engine

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "sections-observational-measurement"
BACK_MATTER = ROOT / "sections" / "10-back-matter.md"
KIND = "observational-measurement"

sys.path.insert(0, str(ROOT / "skills" / "paper-writing" / "scripts"))
import paper_contract  # noqa: E402
import paper_graph  # noqa: E402
import paper_vocabulary  # noqa: E402

FILES = ["01-title-and-keywords.md", "02-abstract.md", "03-introduction.md", "04-methods.md",
         "05-results.md", "06-discussion.md", "07-limitations.md", "08-conclusions.md"]
SECTIONS = ["title-and-keywords", "abstract", "introduction", "methods", "results", "discussion",
            "limitations", "conclusions"]

#: Block -> (required facts, required declarations) for the blocks S8 binds to the study records.
STUDY_BINDINGS = {
    "methods.m-variables-outcomes": (["outcomes"], []),
    "methods.m-study-size": (["sample"], []),
    "methods.m-statistical-methods": (["analysis-plan"], []),
    "methods.m-protocol-registration": (["protocol"], ["study-registration"]),
    "methods.m-ethics": ([], ["ethics-approval"]),
    "results.r-participant-flow": (["participant-flow"], []),
    "results.r-main-results": (["outcomes"], []),
}
VARIANT_BLOCKS = {
    "methods.m-reference-standard": "diagnostic-validation",
    "methods.m-measurement-properties": "measurement-instrument",
    "results.r-diagnostic-accuracy": "diagnostic-validation",
    "results.r-measurement-properties": "measurement-instrument",
}
GUIDELINES = ("strobe", "stard-2015", "cosmin")
NO_DATA_RULE = "The assistant never generates measurements or data"
HUMAN_RULE = "ethics, consent, data collection and the choice of primary outcome stay human"


def header_of(path: Path):
    header, _body = paper_contract.parse(path.read_bytes())
    return header


def body_of(path: Path) -> str:
    return paper_contract.parse(path.read_bytes())[1].decode("utf-8")


class CorpusCase(unittest.TestCase):
    """A directory named `sections/` holding the line's contracts and the shared
    back matter: the layout a workspace of the line receives."""

    def corpus_root(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        sections = root / "sections"
        sections.mkdir()
        for name in FILES:
            shutil.copyfile(CONTRACTS / name, sections / name)
        shutil.copyfile(BACK_MATTER, sections / BACK_MATTER.name)
        return root


class ContractShapeTests(CorpusCase):
    def test_the_line_ships_eight_imrad_contracts_in_order_before_the_shared_back_matter(self) -> None:
        self.assertTrue(CONTRACTS.is_dir(), CONTRACTS)
        self.assertEqual(sorted(p.name for p in CONTRACTS.iterdir()), FILES)
        headers = [header_of(CONTRACTS / name) for name in FILES]
        self.assertEqual([h.section for h in headers], SECTIONS)
        positions = [h.position for h in headers]
        self.assertEqual(positions, sorted(set(positions)))
        self.assertLess(positions[-1], header_of(BACK_MATTER).position)

    def test_every_contract_parses_and_the_corpus_assembles_with_the_back_matter(self) -> None:
        root = self.corpus_root()
        corpus = paper_graph.assemble_corpus(root / "sections")
        self.assertEqual(sorted(corpus.sections), sorted(SECTIONS + ["back-matter"]))
        edges = paper_graph.collect_edges(corpus)
        self.assertEqual(edges.dangling, [])
        order = paper_graph.derive_order(corpus, edges)
        self.assertEqual(sorted(order), sorted(corpus.blocks))
        self.assertTrue(paper_graph.derive_waves(corpus, edges))
        for qualified in list(STUDY_BINDINGS) + list(VARIANT_BLOCKS) + [
                "methods.m-design-setting", "methods.m-participants", "methods.m-data-sources",
                "methods.m-bias", "results.r-descriptive", "results.r-other-analyses"]:
            with self.subTest(block=qualified):
                self.assertIn(qualified, corpus.blocks)

    def test_every_referenced_fact_and_declaration_exists(self) -> None:
        for name in FILES:
            for block in header_of(CONTRACTS / name).blocks:
                for entry in block["requires_facts"] + block["produces_facts"]:
                    self.assertIn(entry["value"], paper_vocabulary.FACTS, (name, block["id"]))
                for entry in block["requires_declarations"]:
                    self.assertIn(entry["value"], paper_vocabulary.DECLARATIONS, (name, block["id"]))

    def test_the_methods_and_results_blocks_bind_the_study_facts_and_declarations(self) -> None:
        corpus = paper_graph.assemble_corpus(self.corpus_root() / "sections")
        for qualified, (facts, declarations) in STUDY_BINDINGS.items():
            with self.subTest(block=qualified):
                record = corpus.blocks[qualified]
                self.assertEqual(list(record.requires_facts), facts)
                self.assertEqual(list(record.requires_declarations), declarations)
                self.assertFalse(record.optional)

    def test_the_variant_blocks_are_optional_and_name_the_variant_they_serve(self) -> None:
        corpus = paper_graph.assemble_corpus(self.corpus_root() / "sections")
        for qualified, variant in VARIANT_BLOCKS.items():
            with self.subTest(block=qualified):
                self.assertTrue(corpus.blocks[qualified].optional)
                section, block = qualified.split(".")
                path = CONTRACTS / FILES[SECTIONS.index(section)]
                rule = body_of(path).split(f"\n## Block `{block}`", 1)[1].split("\n## ", 1)[0]
                self.assertIn(f"`{variant}`", rule)

    def test_the_results_separate_confirmatory_from_exploratory_analyses(self) -> None:
        text = body_of(CONTRACTS / "05-results.md")
        main = text.split("\n## Block `r-main-results`", 1)[1].split("\n## ", 1)[0]
        self.assertIn("confirmatory", main)
        self.assertIn("analysis/log.jsonl", main)
        other = text.split("\n## Block `r-other-analyses`", 1)[1].split("\n## ", 1)[0]
        self.assertIn("exploratory", other)
        flow = text.split("\n## Block `r-participant-flow`", 1)[1].split("\n## ", 1)[0]
        self.assertIn("paper/Figures/participant-flow.svg", flow)


class HouseStyleTests(unittest.TestCase):
    def test_every_contract_states_the_human_boundaries_in_its_house_style(self) -> None:
        from skills._core.command_center import state_extractor
        for name in FILES:
            with self.subTest(contract=name):
                text = body_of(CONTRACTS / name)
                self.assertEqual(text.count("\n## LIA house style\n"), 1)
                self.assertLess(text.index("\n## LIA house style\n"), text.index("\n## Disqualifiers\n"))
                style = text.split("\n## LIA house style\n", 1)[1].split("\n## Disqualifiers\n", 1)[0]
                flat = " ".join(style.split())
                self.assertIn(NO_DATA_RULE, flat)
                self.assertIn(HUMAN_RULE, flat)
                low, high = state_extractor._extent(text)
                self.assertIsNotNone(low)
                self.assertLess(low, high)

    def test_the_contracts_carry_no_review_or_experimental_line_rule(self) -> None:
        for name in FILES:
            with self.subTest(contract=name):
                text = (CONTRACTS / name).read_text(encoding="utf-8")
                for foreign in ("A029", "review/prisma.json", "Results/discussion.json", "G-NOVELTY"):
                    self.assertNotIn(foreign, text)


class GuidelineTargetTests(CorpusCase):
    def test_strobe_stard_and_cosmin_targets_resolve_to_these_sections(self) -> None:
        sections = engine.contract_sections(self.corpus_root())
        for gid in GUIDELINES:
            guideline = engine.load_guideline(gid)
            for item in guideline["items"]:
                targets = item["targets"].get(KIND, item["targets"].get("default"))
                scopes = [scope for rule in item.get("evidence", []) for scope in rule.get("in", [])]
                for target in list(targets) + scopes:
                    with self.subTest(guideline=gid, item=item["number"], target=target):
                        section, _, block = target.partition(".")
                        self.assertIn(section, sections)
                        if block:
                            self.assertIn(block, sections[section])


@unittest.skipUnless(KIND in manifest.LINES, f"the {KIND} kind is not registered in manifest.LINES yet")
class WorkspaceTests(unittest.TestCase):
    def test_a_workspace_of_the_line_receives_the_contracts_and_paper_writing_accepts_them(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        workspace = Path(holder.name).resolve() / "ws"
        init_module.initialize(workspace, tools=("claude",), run_npm=False, run_env=False, kind=KIND)
        served = sorted(p.name for p in (workspace / "sections").glob("*.md"))
        self.assertEqual(served, sorted(FILES + [BACK_MATTER.name]))
        for name in FILES:
            self.assertEqual((workspace / "sections" / name).read_bytes(), (CONTRACTS / name).read_bytes())
        self.assertFalse((workspace / CONTRACTS.name).exists())
        cli = workspace / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
        for argv in (["contract"], ["scaffold"], ["status"]):
            with self.subTest(verb=argv[0]):
                completed = subprocess.run([sys.executable, str(cli), *argv], cwd=workspace,
                                           capture_output=True, text=True, timeout=180)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["status"], "ok", (argv, completed.stdout[-800:], completed.stderr[-800:]))


if __name__ == "__main__":
    unittest.main()
