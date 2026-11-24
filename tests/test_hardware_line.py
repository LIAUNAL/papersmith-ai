"""The hardware line (paper-type-lines S8, T8-H1; decisions F1-F8 of L78, accepted in L79).

The second empirical line is a `manifest.LINES` entry plus its files: section
contracts in `sections-hardware/` following the HardwareX article template
(their ids are the targets of the `hardwarex` checklist), the flow template
`paper-flow-hardware.md.tpl`, the line skill `skills/hardware/` and the
catalogue flip of the `hardware` type, which has no variants and so names its
checklist on the family. The line shares the measurement core
(`skills/_core/measurement/measure_cli.py`) with lab-simulation, which this
unit registers beside it (its files belong to its own unit). An experimental,
review or observational workspace never receives the line's files.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from papersmith import render
from papersmith.cli import main
from papersmith.core import init as init_module, manifest
from papersmith.kit import resolve_and_validate
from skills._core.checklists import engine
from skills._core.paper_types import decision, registry
from tests.test_observational_line import OPTION_RE, required_options_of, usage_of

ROOT = Path(__file__).resolve().parents[1]
KIND = "hardware"
CONTRACTS = ROOT / "sections-hardware"
BACK_MATTER = ROOT / "sections" / "10-back-matter.md"
LINE_SKILL = "skills/hardware/"
SKILL_PATH = ROOT / LINE_SKILL / "SKILL.md"
FLOW_HEADING = "## Paper construction flow (hardware line)"
EXPERIMENTAL_ONLY = sorted(p.name for p in (ROOT / "sections").glob("*.md")
                           if f"sections/{p.name}" != "sections/10-back-matter.md")
SENSOR_IDEA = ("We built a low-cost soil moisture sensor on a microcontroller with an open bill of materials. "
               "The prototype device is calibrated and compared against a reference instrument in the field.")

FILES = ["00-title-and-keywords.md", "01-abstract.md", "02-specifications-table.md", "03-hardware-in-context.md",
         "04-hardware-description.md", "05-design-files.md", "06-bill-of-materials.md",
         "07-build-instructions.md", "08-operation-instructions.md", "09-validation-characterization.md"]
SECTIONS = ["title-and-keywords", "abstract", "specifications-table", "hardware-in-context",
            "hardware-description", "design-files", "bill-of-materials", "build-instructions",
            "operation-instructions", "validation-characterization"]
#: Block -> (required facts, required declarations, optional) for the blocks bound to the study records.
STUDY_BINDINGS = {
    "specifications-table.spec-table": (["protocol"], ["repository-url"], False),
    "design-files.df-summary-table": ([], ["repository-url"], False),
    "validation-characterization.vc-protocol": (["protocol", "outcomes"], [], False),
    "validation-characterization.vc-user-validation": (["sample"], ["ethics-approval", "study-registration"], True),
}
#: Block -> what its rule must name: the measurement core's record and the status verb that reads it.
MEASUREMENT_BINDINGS = {
    "vc-calibration": ("study/instruments.json", "measure_cli.py instrument status"),
    "vc-uncertainty": ("study/uncertainty/", "measure_cli.py uncertainty status"),
    "vc-agreement": ("study/agreement.json", "measure_cli.py agreement status"),
}
NO_DATA_RULE = "The assistant never generates measurements or data"
HUMAN_RULE = "ethics, consent, data collection and the choice of primary outcome stay human"

#: The CLIs the flow and the line skill name, and where their verbs live.
CLIS = {
    "measure_cli.py": ROOT / "skills/_core/measurement/measure_cli.py",
    "study_cli.py": ROOT / "skills/_core/empirical/study_cli.py",
    "analysis_cli.py": ROOT / "skills/_core/empirical/analysis_cli.py",
    "flow_cli.py": ROOT / "skills/_core/participant_flow/flow_cli.py",
    "checklist_cli.py": ROOT / "skills/_core/checklists/checklist_cli.py",
    "datasets_cli.py": ROOT / "skills/datasets/scripts/datasets_cli.py",
    "paper_cli.py": ROOT / "skills/paper-writing/scripts/paper_cli.py",
    "paper_type_cli.py": ROOT / "skills/_core/paper_types/paper_type_cli.py",
}

sys.path.insert(0, str(ROOT / "skills" / "paper-writing" / "scripts"))
import paper_contract  # noqa: E402
import paper_graph  # noqa: E402
import paper_vocabulary  # noqa: E402


def verbs_of(script: Path, *verbs: str) -> set[str]:
    """The subcommands a CLI's (or a subcommand's) usage line accepts: its last choice set,
    since argparse prints the positionals after the options (``measure_cli.py instrument``
    has an option with choices, ``--distribution {normal,rectangular}``, before them)."""
    choices = re.findall(r"\{([a-z_,-]+)\}", usage_of(script, *verbs))
    return set(choices[-1].split(",")) if choices else set()


def flow_text() -> str:
    return render.render_package_template(manifest.LINES[KIND].flow_template, {})


def skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def header_of(path: Path):
    return paper_contract.parse(path.read_bytes())[0]


def body_of(path: Path) -> str:
    return paper_contract.parse(path.read_bytes())[1].decode("utf-8")


def block_rule(section_file: str, block: str) -> str:
    return body_of(CONTRACTS / section_file).split(f"\n## Block `{block}`", 1)[1].split("\n## ", 1)[0]


def cli_spans(text: str) -> list[str]:
    """Every command a text names: its bash lines and the inline spans that call a CLI."""
    fenced = re.findall(r"```bash\n(.*?)```", text, flags=re.S)
    lines = [line.strip() for block in fenced for line in block.splitlines()
             if line.strip() and not line.strip().startswith("#")]
    prose = " ".join(re.sub(r"```.*?```", "", text, flags=re.S).split())
    spans = [span.replace("\\|", "|") for span in re.findall(r"`([^`]+)`", prose)]
    return lines + [span for span in spans if re.search(r"(?:_cli\.py|^python -m) ", span)]


class CommandCheck(unittest.TestCase):
    def check_command(self, command: str) -> None:
        """The CLI exists, every verb it names exists, every option it gives is accepted and
        every option the verb requires is given."""
        tokens = re.findall(r"<[^>]*>|\S+", command)
        at = next(i for i, token in enumerate(tokens) if token.endswith("_cli.py"))
        name = Path(tokens[at]).name
        self.assertIn(name, CLIS, f"unknown CLI {name}")
        script, rest, chain = CLIS[name], tokens[at + 1:], []
        if rest[:2] == ["--root", "."]:
            rest = rest[2:]
        for token in rest:
            choices = verbs_of(script, *chain)
            if token.startswith(("-", "<", ".")) or not choices:
                break
            self.assertIn(token, choices)
            chain.append(token)
        self.assertTrue(chain, "names no subcommand")
        own = tokens[:tokens.index("--")] if "--" in tokens else tokens
        given = {token.split("=", 1)[0] for token in own}
        self.assertLessEqual(required_options_of(script, *chain), given)
        accepted = set(OPTION_RE.findall(usage_of(script) + usage_of(script, *chain)))
        self.assertLessEqual({token for token in given if OPTION_RE.fullmatch(token)}, accepted)


class LineCase(unittest.TestCase):
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

    @staticmethod
    def smith(*argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()


class TableEntryTests(LineCase):
    def test_both_measurement_lines_are_table_entries(self) -> None:
        for kind in ("hardware", "lab-simulation"):
            with self.subTest(kind=kind):
                line = manifest.LINES[kind]
                self.assertEqual(line.sections_dir, f"sections-{kind}/")
                self.assertEqual(line.only_prefixes, (f"sections-{kind}/", f"skills/{kind}/"))
                self.assertEqual(line.shared_sections, ("sections/10-back-matter.md",))
                self.assertEqual(line.flow_template, f"paper-flow-{kind}.md.tpl")
                self.assertEqual(line.topology, "empirical")
                self.assertTrue(line.empirical)
                self.assertTrue(line.label and line.summary)
                self.assertIn(f"sections-{kind}", manifest.KIT_ENTRIES)
        self.assertEqual(manifest.PAPER_KINDS, ("experimental", "review", "observational-measurement", "hardware",
                                                "lab-simulation", "data-resource", "experiment-intervention"))
        self.assertEqual(registry.LINES, tuple(manifest.LINES))

    def test_no_other_line_receives_the_line_files(self) -> None:
        kit = resolve_and_validate()
        for other in ("experimental", "review", "observational-measurement"):
            with self.subTest(line=other):
                layout = manifest.kit_layout(kit, other)
                self.assertFalse([p for p in layout if p.startswith(LINE_SKILL)])
                self.assertFalse([s for s in layout.values() if s.startswith("sections-hardware/")])

    def test_the_line_layout_serves_its_contracts_and_its_skill(self) -> None:
        layout = manifest.kit_layout(resolve_and_validate(), KIND)
        self.assertEqual(layout["skills/hardware/SKILL.md"], "skills/hardware/SKILL.md")
        self.assertEqual(layout["sections/10-back-matter.md"], "sections/10-back-matter.md")
        for other in ("skills/systematic-review/", "skills/observational-measurement/", "skills/lab-simulation/"):
            self.assertFalse([p for p in layout if p.startswith(other)], other)
        for name in EXPERIMENTAL_ONLY:
            self.assertNotIn(f"sections/{name}", layout)
        for name in FILES:
            self.assertEqual(layout[f"sections/{name}"], f"sections-hardware/{name}")


class InitTests(LineCase):
    def test_init_records_the_kind_its_folders_skill_and_command(self) -> None:
        workspace = self.init(KIND)
        self.assertEqual(self.config(workspace)["paper_kind"], KIND)
        for folder in ("protocol", "study", "analysis", "datasets", "paper", "sota-pool"):
            self.assertTrue((workspace / folder).is_dir(), folder)
        for folder in ("proposals", "experiments", "implementations", "kaggle-inbox", "review"):
            self.assertFalse((workspace / folder).exists(), folder)
        self.assertTrue((workspace / LINE_SKILL / "SKILL.md").is_file())
        self.assertTrue((workspace / ".claude" / "commands" / "hardware.md").is_file())
        for other in ("systematic-review", "observational-measurement", "lab-simulation"):
            self.assertFalse((workspace / "skills" / other).exists(), other)
        self.assertFalse((workspace / "sections-hardware").exists())
        self.assertEqual(sorted(p.name for p in (workspace / "sections").glob("*.md")),
                         sorted(FILES + ["10-back-matter.md"]))
        for name in FILES:
            self.assertEqual((workspace / "sections" / name).read_bytes(), (CONTRACTS / name).read_bytes())

    def test_every_harness_entrypoint_carries_the_line_flow(self) -> None:
        workspace = self.init(KIND)
        for entry in ("CLAUDE.md", "OPENCODE.md", ".pi/APPEND_SYSTEM.md", ".agents/AGENTS.md"):
            text = (workspace / entry).read_text(encoding="utf-8")
            self.assertIn(FLOW_HEADING, text, entry)
            for gate in ("G-SPEC", "G-CALIBRATION", "G-AGREEMENT"):
                self.assertIn(gate, text, entry)
            self.assertNotIn("**Proof of concept and experiments**", text, entry)

    def test_other_lines_never_get_the_line_skill(self) -> None:
        for kind in (None, "review", "observational-measurement"):
            with self.subTest(kind=kind):
                workspace = self.init(kind)
                self.assertFalse((workspace / "skills" / "hardware").exists())
                self.assertFalse((workspace / ".claude" / "commands" / "hardware.md").exists())
                self.assertNotIn(FLOW_HEADING, (workspace / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_the_cli_accepts_the_kind_and_prints_its_label(self) -> None:
        workspace = self.new_tmp() / "ws"
        code, out, err = self.smith("init", str(workspace), "--kind", KIND, "--tools", "claude", "--no-npm",
                                    "--no-env", "--no-progress")
        self.assertEqual(code, 0, err)
        self.assertIn(f"Paper line: {KIND} ({manifest.LINES[KIND].label}", out)

    def test_a_fresh_workspace_reports_no_drift(self) -> None:
        code, out, _ = self.smith("status", str(self.init(KIND)))
        self.assertEqual(code, 0)
        self.assertIn("Framework drift: none", out)

    def test_paper_writing_accepts_the_served_contracts(self) -> None:
        workspace = self.init(KIND)
        cli = workspace / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
        for verb in ("contract", "scaffold", "status"):
            with self.subTest(verb=verb):
                done = subprocess.run([sys.executable, str(cli), verb], cwd=workspace, capture_output=True,
                                      text=True, timeout=180)
                payload = json.loads(done.stdout)
                self.assertEqual(payload["status"], "ok", (verb, done.stdout[-800:], done.stderr[-800:]))


class KindSetTests(LineCase):
    def test_experimental_to_the_line_and_back(self) -> None:
        workspace = self.init()
        decision.record_acceptance(workspace, SENSOR_IDEA, by="Ana")
        decision.record_scores(workspace, SENSOR_IDEA)
        code, out, err = self.smith("kind", "set", KIND, "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertIn(f"Paper line: experimental -> {KIND}", out)
        self.assertTrue((workspace / LINE_SKILL / "SKILL.md").is_file())
        self.assertIn(FLOW_HEADING, (workspace / "CLAUDE.md").read_text(encoding="utf-8"))
        code, status_out, _ = self.smith("status", str(workspace))
        self.assertEqual(code, 0)
        self.assertIn("Framework drift: none", status_out)
        code, _, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertFalse((workspace / "skills" / "hardware").exists())
        names = sorted(p.name for p in (workspace / "sections").glob("*.md"))
        for name in EXPERIMENTAL_ONLY:
            self.assertIn(name, names)


class CatalogueTests(unittest.TestCase):
    def test_both_types_are_available_on_their_own_line(self) -> None:
        for kind in ("hardware", "lab-simulation"):
            with self.subTest(kind=kind):
                item = registry.get(kind)
                self.assertEqual((item["status"], item["line"]), ("available", kind))
                self.assertEqual(registry.by_line(kind)["id"], kind)

    def test_each_type_names_its_checklist(self) -> None:
        hardware = registry.get("hardware")
        self.assertEqual(hardware.get("variants", []), [])
        self.assertEqual(hardware["checklist"], "hardwarex")
        self.assertEqual(registry.checklist_for(hardware, None), "hardwarex")
        lab = registry.get("lab-simulation")
        self.assertNotIn("checklist", lab)
        for variant in lab["variants"]:
            with self.subTest(variant=variant["id"]):
                self.assertEqual(variant["checklist"], "gum-reporting")
                self.assertEqual(registry.checklist_for(lab, variant["id"]), "gum-reporting")
        self.assertIsNone(registry.checklist_for(lab, None))
        self.assertEqual(registry.checklist_for(registry.get("observational-measurement"), "observational"), "strobe")
        self.assertIsNone(registry.checklist_for(registry.get("review"), None))

    def test_the_validator_checks_a_family_checklist(self) -> None:
        document = json.loads(registry.CATALOGUE.read_text(encoding="utf-8"))

        def changed(type_id: str, **fields) -> dict:
            out = copy.deepcopy(document)
            next(t for t in out["types"] if t["id"] == type_id).update(fields)
            return out

        registry.validate(changed("hardware", checklist=None))
        registry.validate(changed("hardware", checklist="gum-reporting"))
        for type_id, fields, message in (
                ("hardware", {"checklist": "no-such-guideline"}, "checklist"),
                ("hardware", {"checklist": 3}, "checklist"),
                ("lab-simulation", {"checklist": "gum-reporting"}, "variants")):
            with self.subTest(type=type_id, fields=fields), self.assertRaisesRegex(registry.RegistryError, message):
                registry.validate(changed(type_id, **fields))


class CorpusCase(unittest.TestCase):
    """A `sections/` directory holding the line's contracts and the shared back matter."""

    def corpus_root(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / "sections").mkdir()
        for name in FILES:
            shutil.copyfile(CONTRACTS / name, root / "sections" / name)
        shutil.copyfile(BACK_MATTER, root / "sections" / BACK_MATTER.name)
        return root


class ContractTests(CorpusCase):
    def test_the_line_ships_the_hardwarex_sections_in_order_before_the_back_matter(self) -> None:
        self.assertEqual(sorted(p.name for p in CONTRACTS.iterdir()), FILES)
        headers = [header_of(CONTRACTS / name) for name in FILES]
        self.assertEqual([h.section for h in headers], SECTIONS)
        positions = [h.position for h in headers]
        self.assertEqual(positions, sorted(set(positions)))
        self.assertLess(positions[-1], header_of(BACK_MATTER).position)

    def test_the_corpus_assembles_with_the_back_matter(self) -> None:
        corpus = paper_graph.assemble_corpus(self.corpus_root() / "sections")
        self.assertEqual(sorted(corpus.sections), sorted(SECTIONS + ["back-matter"]))
        edges = paper_graph.collect_edges(corpus)
        self.assertEqual(edges.dangling, [])
        self.assertEqual(sorted(paper_graph.derive_order(corpus, edges)), sorted(corpus.blocks))
        self.assertTrue(paper_graph.derive_waves(corpus, edges))
        for qualified in list(STUDY_BINDINGS) + [f"validation-characterization.{b}" for b in MEASUREMENT_BINDINGS]:
            self.assertIn(qualified, corpus.blocks)

    def test_every_referenced_fact_and_declaration_exists(self) -> None:
        for name in FILES:
            for block in header_of(CONTRACTS / name).blocks:
                for entry in block["requires_facts"] + block["produces_facts"]:
                    self.assertIn(entry["value"], paper_vocabulary.FACTS, (name, block["id"]))
                for entry in block["requires_declarations"]:
                    self.assertIn(entry["value"], paper_vocabulary.DECLARATIONS, (name, block["id"]))

    def test_the_blocks_bind_the_study_facts_and_declarations(self) -> None:
        corpus = paper_graph.assemble_corpus(self.corpus_root() / "sections")
        for qualified, (facts, declarations, optional) in STUDY_BINDINGS.items():
            with self.subTest(block=qualified):
                record = corpus.blocks[qualified]
                self.assertEqual(list(record.requires_facts), facts)
                self.assertEqual(list(record.requires_declarations), declarations)
                self.assertEqual(record.optional, optional)

    def test_the_validation_blocks_read_the_measurement_core(self) -> None:
        for block, needles in MEASUREMENT_BINDINGS.items():
            rule = " ".join(block_rule("09-validation-characterization.md", block).split())
            for needle in needles:
                with self.subTest(block=block, needle=needle):
                    self.assertIn(needle, rule)
        people = " ".join(block_rule("09-validation-characterization.md", "vc-user-validation").split())
        for needle in ("study_cli.py status --root .", "/study-protocol-deliberation", "optional"):
            self.assertIn(needle, people)

    def test_every_contract_states_the_human_boundaries(self) -> None:
        from skills._core.command_center import state_extractor
        for name in FILES:
            with self.subTest(contract=name):
                text = body_of(CONTRACTS / name)
                self.assertEqual(text.count("\n## LIA house style\n"), 1)
                style = " ".join(text.split("\n## LIA house style\n", 1)[1].split("\n## Disqualifiers\n", 1)[0]
                                 .split())
                self.assertIn(NO_DATA_RULE, style)
                self.assertIn(HUMAN_RULE, style)
                low, high = state_extractor._extent(text)
                self.assertIsNotNone(low)
                self.assertLess(low, high)
                for foreign in ("A029", "review/prisma.json", "Results/discussion.json", "G-NOVELTY"):
                    self.assertNotIn(foreign, text)

    def test_the_hardwarex_targets_resolve_to_these_sections(self) -> None:
        sections = engine.contract_sections(self.corpus_root())
        guideline = engine.load_guideline("hardwarex")
        for item in guideline["items"]:
            targets = item["targets"].get(KIND, item["targets"].get("default"))
            for target in targets:
                with self.subTest(item=item["number"], target=target):
                    section, _, block = target.partition(".")
                    self.assertIn(section, sections)
                    if block:
                        self.assertIn(block, sections[section])


class FlowTextTests(CommandCheck):
    def test_the_flow_names_its_steps_gates_and_records(self) -> None:
        self.assertTrue(flow_text().startswith(FLOW_HEADING))
        text = " ".join(flow_text().split())
        for snippet in ("/plausibility", "/paper-type", "/study-protocol-deliberation", "study_cli.py protocol approve",
                        "G-SPEC", "measure_cli.py instrument add", "measure_cli.py data register",
                        "measure_cli.py uncertainty compute", "G-CALIBRATION", "measure_cli.py agreement compute",
                        "G-AGREEMENT", "study_cli.py ethics record", "--not-applicable", "repository-url",
                        "/paper-writing", "--guideline hardwarex", "--guideline gum-reporting",
                        "measurement-science", "/figure-review", "smith audit ."):
            self.assertIn(snippet, text, snippet)

    def test_the_flow_states_what_stays_human(self) -> None:
        text = " ".join(flow_text().split())
        self.assertIn("never generates measurements or data", text)
        tail = text.split("never generates measurements or data", 1)[1]
        for record in ("ethics", "consent", "data collection", "primary outcome"):
            self.assertIn(record, tail)

    def test_every_cli_command_the_flow_names_exists(self) -> None:
        commands = [c for c in cli_spans(flow_text()) if "_cli.py " in c]
        self.assertGreaterEqual(len(commands), 10)
        for command in commands:
            with self.subTest(command=command):
                self.check_command(command)

    def test_every_path_and_slash_command_the_flow_names_exists(self) -> None:
        for path in re.findall(r"`(skills/[A-Za-z0-9_./-]+\.(?:py|md))", flow_text()):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)
        for name in sorted(set(re.findall(r"`/([a-z][a-z-]*)", flow_text()))):
            with self.subTest(command=name):
                self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file(), name)


class SkillTests(CommandCheck):
    def test_the_skill_names_the_line(self) -> None:
        text = skill_text()
        self.assertTrue(text.startswith("---\nname: hardware\n"))
        self.assertFalse(list(SKILL_PATH.parent.glob("**/*.py")), "the line skill owns no script")
        flat = " ".join(text.split())
        self.assertIn("never generates", flat)
        for gate in ("G-SPEC", "G-CALIBRATION", "G-AGREEMENT"):
            self.assertIn(gate, flat)

    def test_every_cli_command_the_skill_names_exists_with_its_required_options(self) -> None:
        commands = [c for c in cli_spans(skill_text()) if "_cli.py " in c]
        self.assertGreaterEqual(len(commands), 10)
        for command in commands:
            with self.subTest(command=command):
                self.check_command(command)

    def test_every_module_command_the_skill_names_runs(self) -> None:
        commands = [c for c in cli_spans(skill_text()) if c.startswith("python -m ")]
        self.assertTrue(commands)
        for command in commands:
            with self.subTest(command=command):
                done = subprocess.run([sys.executable, *command.split()[1:]], capture_output=True, text=True,
                                      cwd=str(ROOT), check=False)
                self.assertEqual(done.returncode, 0, done.stderr)

    def test_every_slash_command_and_path_the_skill_names_exists(self) -> None:
        text = skill_text()
        slash = set(re.findall(r"`/([a-z][a-z-]*)", text))
        self.assertIn("hardware", slash)
        for name in sorted(slash):
            with self.subTest(command=name):
                self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file(), name)
        for path in re.findall(r"`(skills/[A-Za-z0-9_./-]+)`", text):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).exists(), path)


if __name__ == "__main__":
    unittest.main()
