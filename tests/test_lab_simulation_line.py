"""The lab-simulation line's own files (paper-type-lines S8, T8-L1).

A lab-simulation workspace receives the contracts of `sections-lab-simulation/`
at `sections/`, beside the shared back matter, the flow template
`paper-flow-lab-simulation.md.tpl` and the thin line skill
`skills/lab-simulation/`. Decisions F3-F5 of L78, accepted in L79: the line
reuses the study-protocol deliberation (primary observable, replicates or
parameter grid as the sample size, analysis plan) with its lock, adds
G-CALIBRATION against known values and the uncertainty budget of the
measurement core, reports on the `gum-reporting` checklist and writes IMRaD
contracts with sample or model, calibration and uncertainty blocks. The
assistant never generates measurements or data, and the choice of the primary
observable stays human.

The command checks reuse the helpers of `tests/test_observational_line.py`.
The workspace part runs only once the kind is registered in
`papersmith.core.manifest.LINES` (the hardware writer registers both lines).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith import render
from papersmith.core import init as init_module, manifest
from skills._core.checklists import engine
from skills._core.paper_types import registry
from tests import test_observational_line as observational

ROOT = Path(__file__).resolve().parents[1]
KIND = "lab-simulation"
CONTRACTS = ROOT / "sections-lab-simulation"
BACK_MATTER = ROOT / "sections" / "10-back-matter.md"
FLOW_TEMPLATE = "paper-flow-lab-simulation.md.tpl"
FLOW_HEADING = "## Paper construction flow (lab and simulation line)"
LINE_SKILL = ROOT / "skills" / "lab-simulation" / "SKILL.md"
GUIDELINE = "gum-reporting"

sys.path.insert(0, str(ROOT / "skills" / "paper-writing" / "scripts"))
import paper_contract  # noqa: E402
import paper_graph  # noqa: E402
import paper_vocabulary  # noqa: E402

FILES = ["01-title-and-keywords.md", "02-abstract.md", "03-introduction.md", "04-methods.md",
         "05-results.md", "06-discussion.md", "07-limitations.md", "08-conclusions.md"]
SECTIONS = ["title-and-keywords", "abstract", "introduction", "methods", "results", "discussion",
            "limitations", "conclusions"]

#: Block -> (required facts, required declarations) for the blocks bound to the study records (F3).
STUDY_BINDINGS = {
    "methods.m-protocol": (["protocol"], []),
    "methods.m-observables": (["outcomes"], []),
    "methods.m-replicates-grid": (["sample"], []),
    "methods.m-analysis": (["analysis-plan"], []),
    "results.r-observables": (["outcomes"], []),
}
VARIANT_BLOCKS = {
    "methods.m-sample-matrix": "materials",
    "methods.m-model-definition": "modelling-simulation",
    "results.r-sample-characterization": "materials",
    "results.r-model-verification": "modelling-simulation",
}
#: The blocks every workspace of the line writes, whatever its variant.
CORE_BLOCKS = ("methods.m-design", "methods.m-calibration", "methods.m-uncertainty", "results.r-calibration",
               "results.r-uncertainty-budgets", "results.r-parameter-sweeps")
NO_DATA_RULE = "The assistant never generates measurements or data"
HUMAN_RULE = "the choice of the primary observable stay human"
#: Uncertainty vocabulary of GUM clause 7 the methods' uncertainty block names (paraphrased).
GUM_TERMS = ("type A", "type B", "sensitivity coefficient", "combined standard uncertainty",
             "effective degrees of freedom", "Welch-Satterthwaite", "expanded uncertainty", "coverage factor")
#: The measurement-core CLI joins the CLIs the observational helpers already know.
CLIS = {**observational.CLIS, "measure_cli.py": ROOT / "skills/_core/measurement/measure_cli.py"}


def verbs_of(script: Path, *verbs: str) -> set[str]:
    """`observational.verbs_of` minus the choices of an option (`--distribution {normal,rectangular}`), which
    the shared helper would read as the subcommands when they precede them in the usage line."""
    usage = re.sub(r"--[a-z][a-z-]* \{[^}]*\}", "", observational.usage_of(script, *verbs))
    choices = re.search(r"\{([a-z_,-]+)\}", usage)
    return set(choices.group(1).split(",")) if choices else set()


def shared_helpers(**patches):
    """The observational line's command checks, run on this line's text with the measurement CLI known."""
    return mock.patch.multiple(observational, CLIS=CLIS, verbs_of=verbs_of, **patches)


def header_of(path: Path):
    return paper_contract.parse(path.read_bytes())[0]


def body_of(path: Path) -> str:
    return paper_contract.parse(path.read_bytes())[1].decode("utf-8")


def block_rule(section: str, block: str) -> str:
    """The prose of one block of a contract: from its heading to the next `## ` heading."""
    text = body_of(CONTRACTS / FILES[SECTIONS.index(section)])
    return " ".join(text.split(f"\n## Block `{block}`", 1)[1].split("\n## ", 1)[0].split())


def flow_text() -> str:
    return render.render_package_template(FLOW_TEMPLATE, {})


def skill_text() -> str:
    return LINE_SKILL.read_text(encoding="utf-8")


class CorpusCase(unittest.TestCase):
    """A directory named `sections/` holding the line's contracts and the shared back matter."""

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
        corpus = paper_graph.assemble_corpus(self.corpus_root() / "sections")
        self.assertEqual(sorted(corpus.sections), sorted(SECTIONS + ["back-matter"]))
        edges = paper_graph.collect_edges(corpus)
        self.assertEqual(edges.dangling, [])
        self.assertEqual(sorted(paper_graph.derive_order(corpus, edges)), sorted(corpus.blocks))
        self.assertTrue(paper_graph.derive_waves(corpus, edges))
        for qualified in list(STUDY_BINDINGS) + list(VARIANT_BLOCKS) + list(CORE_BLOCKS):
            with self.subTest(block=qualified):
                self.assertIn(qualified, corpus.blocks)

    def test_every_referenced_fact_and_declaration_exists(self) -> None:
        for name in FILES:
            for block in header_of(CONTRACTS / name).blocks:
                for entry in block["requires_facts"] + block["produces_facts"]:
                    self.assertIn(entry["value"], paper_vocabulary.FACTS, (name, block["id"]))
                for entry in block["requires_declarations"]:
                    self.assertIn(entry["value"], paper_vocabulary.DECLARATIONS, (name, block["id"]))

    def test_the_methods_and_results_blocks_bind_the_study_facts(self) -> None:
        corpus = paper_graph.assemble_corpus(self.corpus_root() / "sections")
        for qualified, (facts, declarations) in STUDY_BINDINGS.items():
            with self.subTest(block=qualified):
                record = corpus.blocks[qualified]
                self.assertEqual(list(record.requires_facts), facts)
                self.assertEqual(list(record.requires_declarations), declarations)
                self.assertFalse(record.optional)
        for qualified in CORE_BLOCKS:
            with self.subTest(block=qualified):
                self.assertFalse(corpus.blocks[qualified].optional)

    def test_the_variant_blocks_are_optional_and_name_the_variant_they_serve(self) -> None:
        corpus = paper_graph.assemble_corpus(self.corpus_root() / "sections")
        for qualified, variant in VARIANT_BLOCKS.items():
            with self.subTest(block=qualified):
                self.assertTrue(corpus.blocks[qualified].optional)
                self.assertIn(f"`{variant}`", block_rule(*qualified.split(".")))

    def test_the_variant_blocks_say_what_each_variant_describes(self) -> None:
        sample = block_rule("methods", "m-sample-matrix")
        for term in ("synthesis", "deposition", "processing", "characterization"):
            self.assertIn(term, sample)
        model = block_rule("methods", "m-model-definition")
        for term in ("solver", "parameters", "convergence"):
            self.assertIn(term, model)

    def test_the_calibration_and_uncertainty_blocks_read_the_measurement_core(self) -> None:
        calibration = block_rule("methods", "m-calibration")
        self.assertIn("study/instruments.json", calibration)
        self.assertIn("known value", calibration)
        uncertainty = block_rule("methods", "m-uncertainty")
        for term in GUM_TERMS:
            self.assertIn(term, uncertainty, term)
        self.assertIn("study/uncertainty/", uncertainty)

    def test_the_results_report_expanded_uncertainties_and_label_the_sweeps(self) -> None:
        observables = block_rule("results", "r-observables")
        for term in ("study/uncertainty/", "expanded uncertainty", "coverage factor", "confirmatory",
                     "analysis/log.jsonl"):
            self.assertIn(term, observables, term)
        self.assertIn("known value", block_rule("results", "r-calibration"))
        self.assertIn("effective degrees of freedom", block_rule("results", "r-uncertainty-budgets"))
        sweeps = block_rule("results", "r-parameter-sweeps")
        for term in ("confirmatory", "exploratory", "analysis/log.jsonl"):
            self.assertIn(term, sweeps, term)


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

    def test_the_contracts_carry_no_other_line_rule(self) -> None:
        for name in FILES:
            with self.subTest(contract=name):
                text = (CONTRACTS / name).read_text(encoding="utf-8")
                for foreign in ("A029", "review/prisma.json", "Results/discussion.json", "G-NOVELTY",
                                "study/flow.json", "participant-flow", "STROBE"):
                    self.assertNotIn(foreign, text)


class GuidelineTargetTests(CorpusCase):
    def test_gum_reporting_names_the_line_and_its_targets_resolve(self) -> None:
        guideline = engine.load_guideline(GUIDELINE)
        self.assertIn(KIND, guideline["lines"])
        sections = engine.contract_sections(self.corpus_root())
        for item in guideline["items"]:
            targets = item["targets"].get(KIND, item["targets"].get("default"))
            scopes = [scope for rule in item.get("evidence", []) for scope in rule.get("in", [])]
            for target in list(targets) + scopes:
                with self.subTest(item=item["number"], target=target):
                    section, _, block = target.partition(".")
                    self.assertIn(section, sections)
                    if block:
                        self.assertIn(block, sections[section])


class FlowTextTests(unittest.TestCase):
    def test_the_flow_names_its_stages_gates_and_records(self) -> None:
        self.assertTrue(flow_text().startswith(FLOW_HEADING))
        text = " ".join(flow_text().split())
        for snippet in ("smith init --kind lab-simulation", "smith kind set lab-simulation",
                        "/study-protocol-deliberation", "study_cli.py protocol approve", "--by",
                        "G-STUDY-PROTOCOL", "measure_cli.py data register", "measure_cli.py instrument add",
                        "G-CALIBRATION", "measure_cli.py uncertainty compute", "analysis_cli.py run",
                        "analysis_cli.py record", "analysis_cli.py status", "repository-url", "/paper-writing",
                        "paper_cli.py observe", "checklist_cli.py check --guideline gum-reporting",
                        "measurement-science", "paper_cli.py review", "/figure-review", "smith audit .",
                        "materials", "modelling-simulation"):
            self.assertIn(snippet, text, snippet)

    def test_the_flow_follows_the_catalogue_stages_in_order(self) -> None:
        text = " ".join(flow_text().split()).lower()
        stages = [stage.lower() for stage in registry.get(KIND)["stages"]]
        self.assertEqual(len(stages), 6)
        positions = [text.find(stage) for stage in stages]
        self.assertNotIn(-1, positions, dict(zip(stages, positions)))
        self.assertEqual(positions, sorted(positions))

    def test_the_flow_states_what_stays_human(self) -> None:
        text = " ".join(flow_text().split())
        self.assertIn("never generates measurements or data", text)
        tail = text.split("never generates measurements or data", 1)[1]
        for record in ("primary observable", "parameter grid", "calibration", "sign"):
            self.assertIn(record, tail)

    def test_every_cli_verb_and_path_the_flow_names_exists(self) -> None:
        with shared_helpers(flow_text=flow_text):
            observational.FlowTextTests.test_every_cli_verb_the_flow_names_exists(self)
            observational.FlowTextTests.test_every_path_the_flow_names_exists(self)

    def test_every_cli_command_of_the_flow_exists_with_its_required_options(self) -> None:
        """The flow's complete commands (each `python skills/...` span) walk the same check as the skill's."""
        flow = flow_text()
        spans = [" ".join(span.split()) for span in re.findall(r"`(python\s[^`]+)`", flow)]
        self.assertGreaterEqual(len(spans), 6)
        commands = "\n".join(spans)
        with shared_helpers(SKILL_TEXT=f"```bash\n{commands}\n```\n"):
            observational.SkillCommandTests.test_every_cli_command_the_skill_names_exists_with_its_required_options(
                self)


class SkillTests(unittest.TestCase):
    def test_the_skill_names_the_line_and_its_variants(self) -> None:
        text = skill_text()
        self.assertTrue(text.startswith("---\nname: lab-simulation\n"))
        for snippet in ("materials", "modelling-simulation", "gum-reporting", "G-STUDY-PROTOCOL", "G-CALIBRATION",
                        "measurement-science", NO_DATA_RULE.lower().replace("the assistant ", "")):
            self.assertIn(snippet, text, snippet)
        self.assertFalse([p for p in LINE_SKILL.parent.rglob("*") if p.suffix == ".py"], "the line skill has no script")

    def test_every_cli_command_the_skill_names_exists_with_its_required_options(self) -> None:
        with shared_helpers(SKILL_TEXT=skill_text()):
            self.assertTrue([c for c in observational.skill_invocations() if "measure_cli.py " in c])
            observational.SkillCommandTests.test_every_cli_command_the_skill_names_exists_with_its_required_options(
                self)
            observational.SkillCommandTests.test_every_module_command_the_skill_names_runs(self)

    def test_every_slash_command_and_path_the_skill_names_exists(self) -> None:
        text = skill_text()
        slash = set(re.findall(r"`/([a-z][a-z-]*)", text))
        self.assertIn("lab-simulation", slash)
        for name in sorted(slash - {"lab-simulation"}):
            with self.subTest(command=name):
                self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file(), name)
        for path in re.findall(r"`(skills/[A-Za-z0-9_./-]+)`", text):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).exists(), path)


@unittest.skipUnless(KIND in manifest.LINES, f"the {KIND} kind is not registered in manifest.LINES yet")
class WorkspaceTests(unittest.TestCase):
    def test_the_table_entry_points_at_these_files(self) -> None:
        line = manifest.LINES[KIND]
        self.assertEqual(line.sections_dir, "sections-lab-simulation/")
        self.assertEqual(line.flow_template, FLOW_TEMPLATE)
        self.assertIn("skills/lab-simulation/", line.only_prefixes)

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
        self.assertTrue((workspace / "skills" / "lab-simulation" / "SKILL.md").is_file())
        self.assertIn(FLOW_HEADING, (workspace / "CLAUDE.md").read_text(encoding="utf-8"))
        cli = workspace / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
        for argv in (["contract"], ["scaffold"], ["status"]):
            with self.subTest(verb=argv[0]):
                completed = subprocess.run([sys.executable, str(cli), *argv], cwd=workspace,
                                           capture_output=True, text=True, timeout=180)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["status"], "ok", (argv, completed.stdout[-800:], completed.stderr[-800:]))


if __name__ == "__main__":
    unittest.main()
