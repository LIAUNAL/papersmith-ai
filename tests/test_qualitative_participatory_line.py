"""The qualitative-participatory line (paper-type-lines S8, T8-L6; decisions K1-K8 of L112, accepted in L113).

The sixth empirical line, and the last type of the catalogue to get a flow, is a
`manifest.LINES` entry plus its files: IMRaD section contracts in
`sections-qualitative-participatory/` shaped by SRQR (their ids are the targets
of the `srqr`, `coreq` and `accord` checklists), with optional blocks for the
consensus-foresight and experience-report variants, the flow template
`paper-flow-qualitative-participatory.md.tpl`, the line skill
`skills/qualitative-participatory/` and the catalogue flip of the
`qualitative-participatory` type, whose variants choose the checklist:
qualitative-mixed -> `srqr` (COREQ the alternative), consensus-foresight ->
`accord`, experience-report -> none. The assistant never generates data, never
writes or edits a transcript, never invents or polishes a quote and never
enters a rating; ethics, consent, data collection and the analytic sign-off
stay human. No other line receives its files.
"""

from __future__ import annotations

import contextlib
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
from papersmith.core import init as init_module, kind as kind_module, manifest
from papersmith.kit import resolve_and_validate
from skills._core.checklists import engine
from skills._core.paper_types import decision, registry
from tests.test_observational_line import OPTION_RE, required_options_of, usage_of, verbs_of

ROOT = Path(__file__).resolve().parents[1]
KIND = "qualitative-participatory"
CONTRACTS = ROOT / "sections-qualitative-participatory"
BACK_MATTER = ROOT / "sections" / "10-back-matter.md"
LINE_SKILL = "skills/qualitative-participatory/"
SKILL_PATH = ROOT / LINE_SKILL / "SKILL.md"
FLOW_HEADING = "## Paper construction flow (qualitative-participatory line)"
EXPERIMENTAL_ONLY = sorted(p.name for p in (ROOT / "sections").glob("*.md")
                           if f"sections/{p.name}" != "sections/10-back-matter.md")
OTHER_LINES = ("experimental", "review", "observational-measurement", "hardware", "lab-simulation", "data-resource",
               "experiment-intervention")
OTHER_SKILLS = ("systematic-review", "observational-measurement", "hardware", "lab-simulation", "data-resource",
                "experiment-intervention")
CASE_IDEA = ("A case study of the panela value chain with semi-structured interviews and focus groups with "
             "producers; a thematic analysis of the interviews describes how the cooperative organises sales.")

FILES = ["01-title-and-keywords.md", "02-abstract.md", "03-introduction.md", "04-methods.md",
         "05-results.md", "06-discussion.md", "07-limitations.md", "08-conclusions.md"]
SECTIONS = ["title-and-keywords", "abstract", "introduction", "methods", "results", "discussion",
            "limitations", "conclusions"]
#: Block -> (required facts, required declarations, optional) for the blocks every variant writes or the
#: blocks bound to the study records.
STUDY_BINDINGS = {
    "methods.m-approach-paradigm": ([], [], False),
    "methods.m-researcher-reflexivity": ([], [], False),
    "methods.m-context": ([], [], False),
    "methods.m-sampling": ([], [], False),
    "methods.m-ethics-consent": ([], ["ethics-approval"], False),
    "methods.m-data-collection": ([], [], False),
    "methods.m-units-of-study": ([], [], False),
    "methods.m-data-processing": ([], [], True),
    "methods.m-data-analysis": ([], [], False),
    "methods.m-trustworthiness": ([], [], False),
    "methods.m-protocol": (["protocol"], [], True),
    "results.r-synthesis": ([], [], False),
    "results.r-links-to-data": ([], [], True),
    "discussion.d-key-findings": (["contributions"], [], False),
    "discussion.d-integration": (["gap"], [], False),
    "discussion.d-implications": ([], [], False),
    "discussion.d-transferability": ([], [], False),
    "limitations.lim-reported": ([], [], False),
}
#: The optional blocks only one variant writes, and what each must name.
VARIANT_BLOCKS = {
    ("04-methods.md", "m-consensus-panel"): ("consensus-foresight", ("panel", "recruit", "expertise",
                                                                     "consensus_cli.py status --root .")),
    ("04-methods.md", "m-consensus-definition"): ("consensus-foresight", ("threshold", "pre-specified",
                                                                          "protocol", "consensus_cli.py status --root .")),
    ("04-methods.md", "m-consensus-rounds"): ("consensus-foresight", ("rounds", "questionnaire", "feedback")),
    ("05-results.md", "r-consensus-rounds"): ("consensus-foresight", ("consensus_cli.py round status --root .",
                                                                      "each round")),
    ("05-results.md", "r-consensus-dissent"): ("consensus-foresight", ("non-consensus", "dissent")),
    ("05-results.md", "r-consensus-micmac"): ("consensus-foresight", ("MICMAC",
                                                                      "consensus_cli.py micmac status --root .")),
    ("05-results.md", "r-consensus-scenarios"): ("consensus-foresight", ("MACTOR", "scenario", "narrative")),
    ("04-methods.md", "m-experience-setting"): ("experience-report", ("context", "setting")),
    ("04-methods.md", "m-experience-innovation"): ("experience-report", ("innovation", "programme")),
    ("05-results.md", "r-experience-what-was-done"): ("experience-report", ("what was done",)),
    ("06-discussion.md", "d-experience-lessons"): ("experience-report", ("what it taught",)),
    ("07-limitations.md", "lim-experience-limits"): ("experience-report", ("no effect", "evaluation")),
}
#: The optional blocks a `qualitative-mixed` paper must write.
MIXED_REQUIRED = {("04-methods.md", "m-data-processing"), ("05-results.md", "r-links-to-data")}
#: Block -> what its rule must name: the record it reads and the command that writes or reads it.
RECORD_BINDINGS = {
    ("04-methods.md", "m-data-processing"): ("qual_cli.py transcripts status --root .", "de-identified",
                                             "transcription", "never quotes a transcript"),
    ("04-methods.md", "m-data-analysis"): ("qual_cli.py codebook status --root .",
                                           "qual_cli.py themes status --root .", "sign-off", "codebook version"),
    ("04-methods.md", "m-protocol"): ("study_cli.py protocol status --root .", "amendment"),
    ("04-methods.md", "m-ethics-consent"): ("study/ethics.json", "consent", "not applicable"),
    ("04-methods.md", "m-sampling"): ("sufficiency", "qual_cli.py transcripts status --root ."),
    ("05-results.md", "r-links-to-data"): ("\\pquote{<code>}{<text>}", "verbatim",
                                           "qual_cli.py quotes check --root .", "paper_cli.py verify"),
    ("05-results.md", "r-synthesis"): ("themes", "signed off"),
}
NO_DATA_RULE = "The assistant never generates data"
NO_TRANSCRIPT_RULE = ("never writes or edits a transcript, never invents or polishes a quote and never enters "
                      "a rating")
HUMAN_RULE = "ethics, consent, data collection and the analytic sign-off stay human"
GUIDELINES = ("srqr", "coreq", "accord")
GATES = ("G-STUDY-PROTOCOL", "G-ETHICS", "G-TRANSCRIPTS", "G-ROUNDS", "G-ANALYSIS")

#: The CLIs the flow, the line skill and the contracts name, and where their verbs live.
CLIS = {
    "study_cli.py": ROOT / "skills/_core/empirical/study_cli.py",
    "qual_cli.py": ROOT / "skills/_core/qualitative/qual_cli.py",
    "consensus_cli.py": ROOT / "skills/_core/qualitative/consensus_cli.py",
    "checklist_cli.py": ROOT / "skills/_core/checklists/checklist_cli.py",
    "paper_cli.py": ROOT / "skills/paper-writing/scripts/paper_cli.py",
    "paper_type_cli.py": ROOT / "skills/_core/paper_types/paper_type_cli.py",
}

sys.path.insert(0, str(ROOT / "skills" / "paper-writing" / "scripts"))
import paper_contract  # noqa: E402
import paper_graph  # noqa: E402
import paper_vocabulary  # noqa: E402


def flow_text() -> str:
    return render.render_package_template(manifest.LINES[KIND].flow_template, {})


def skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def header_of(path: Path):
    return paper_contract.parse(path.read_bytes())[0]


def body_of(path: Path) -> str:
    return paper_contract.parse(path.read_bytes())[1].decode("utf-8")


def block_rule(section_file: str, block: str) -> str:
    body = body_of(CONTRACTS / section_file)
    part = re.split(rf"\n## (?:Block|Slot) `{re.escape(block)}`", body, maxsplit=1)[1]
    return part.split("\n## ", 1)[0]


def disqualifiers_of(section_file: str) -> str:
    return body_of(CONTRACTS / section_file).split("\n## Disqualifiers\n", 1)[1].split("\n## ", 1)[0]


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
            self.assertIn(token, choices, command)
            chain.append(token)
        self.assertTrue(chain, f"names no subcommand: {command}")
        own = tokens[:tokens.index("--")] if "--" in tokens else tokens
        given = {token.split("=", 1)[0] for token in own}
        self.assertLessEqual(required_options_of(script, *chain), given, command)
        accepted = set(OPTION_RE.findall(usage_of(script) + usage_of(script, *chain)))
        self.assertLessEqual({token for token in given if OPTION_RE.fullmatch(token)}, accepted, command)


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
    def test_the_line_is_a_table_entry(self) -> None:
        line = manifest.LINES[KIND]
        self.assertEqual(line.sections_dir, "sections-qualitative-participatory/")
        self.assertEqual(line.only_prefixes, ("sections-qualitative-participatory/", LINE_SKILL))
        self.assertEqual(line.shared_sections, ("sections/10-back-matter.md",))
        self.assertEqual(line.flow_template, "paper-flow-qualitative-participatory.md.tpl")
        self.assertEqual(line.topology, "empirical")
        self.assertTrue(line.empirical)
        self.assertTrue(line.label and line.summary)
        self.assertIn("sections-qualitative-participatory", manifest.KIT_ENTRIES)
        self.assertEqual(manifest.PAPER_KINDS, OTHER_LINES + (KIND,))
        self.assertEqual(registry.LINES, tuple(manifest.LINES))

    def test_no_other_line_receives_the_line_files(self) -> None:
        kit = resolve_and_validate()
        for other in OTHER_LINES:
            with self.subTest(line=other):
                layout = manifest.kit_layout(kit, other)
                self.assertFalse([p for p in layout if p.startswith(LINE_SKILL)])
                self.assertFalse([s for s in layout.values() if s.startswith("sections-qualitative-participatory/")])

    def test_the_line_layout_serves_its_contracts_and_its_skill(self) -> None:
        layout = manifest.kit_layout(resolve_and_validate(), KIND)
        self.assertEqual(layout[f"{LINE_SKILL}SKILL.md"], f"{LINE_SKILL}SKILL.md")
        self.assertEqual(layout["sections/10-back-matter.md"], "sections/10-back-matter.md")
        for other in OTHER_SKILLS:
            self.assertFalse([p for p in layout if p.startswith(f"skills/{other}/")], other)
        for name in EXPERIMENTAL_ONLY:
            self.assertNotIn(f"sections/{name}", layout)
        for name in FILES:
            self.assertEqual(layout[f"sections/{name}"], f"sections-qualitative-participatory/{name}")


class InitTests(LineCase):
    def test_init_records_the_kind_its_folders_skill_and_command(self) -> None:
        workspace = self.init(KIND)
        self.assertEqual(self.config(workspace)["paper_kind"], KIND)
        for folder in ("protocol", "study", "analysis", "datasets", "paper", "sota-pool"):
            self.assertTrue((workspace / folder).is_dir(), folder)
        for folder in ("proposals", "experiments", "implementations", "kaggle-inbox", "review"):
            self.assertFalse((workspace / folder).exists(), folder)
        self.assertTrue((workspace / LINE_SKILL / "SKILL.md").is_file())
        self.assertTrue((workspace / ".claude" / "commands" / "qualitative-participatory.md").is_file())
        for other in OTHER_SKILLS:
            self.assertFalse((workspace / "skills" / other).exists(), other)
        self.assertFalse((workspace / "sections-qualitative-participatory").exists())
        self.assertEqual(sorted(p.name for p in (workspace / "sections").glob("*.md")),
                         sorted(FILES + ["10-back-matter.md"]))
        for name in FILES:
            self.assertEqual((workspace / "sections" / name).read_bytes(), (CONTRACTS / name).read_bytes())

    def test_every_harness_entrypoint_carries_the_line_flow(self) -> None:
        workspace = self.init(KIND)
        for entry in ("CLAUDE.md", "OPENCODE.md", ".pi/APPEND_SYSTEM.md", ".agents/AGENTS.md"):
            text = (workspace / entry).read_text(encoding="utf-8")
            self.assertIn(FLOW_HEADING, text, entry)
            for gate in GATES:
                self.assertIn(gate, text, entry)
            self.assertNotIn("**Proof of concept and experiments**", text, entry)

    def test_other_lines_never_get_the_line_skill(self) -> None:
        for kind in (None, "review", "experiment-intervention"):
            with self.subTest(kind=kind):
                workspace = self.init(kind)
                self.assertFalse((workspace / "skills" / "qualitative-participatory").exists())
                self.assertFalse((workspace / ".claude" / "commands" / "qualitative-participatory.md").exists())
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
    def scored(self, kind: str | None = None) -> Path:
        workspace = self.init(kind)
        decision.record_acceptance(workspace, CASE_IDEA, by="Ana")
        decision.record_scores(workspace, CASE_IDEA)
        return workspace

    def test_experimental_to_the_line_and_back(self) -> None:
        workspace = self.scored()
        code, out, err = self.smith("kind", "set", KIND, "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertIn(f"Paper line: experimental -> {KIND}", out)
        self.assertTrue((workspace / LINE_SKILL / "SKILL.md").is_file())
        self.assertIn(FLOW_HEADING, (workspace / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertEqual(sorted(p.name for p in (workspace / "sections").glob("*.md")),
                         sorted(FILES + ["10-back-matter.md"]))
        code, status_out, _ = self.smith("status", str(workspace))
        self.assertEqual(code, 0)
        self.assertIn("Framework drift: none", status_out)
        code, _, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertFalse((workspace / "skills" / "qualitative-participatory").exists())
        names = sorted(p.name for p in (workspace / "sections").glob("*.md"))
        for name in EXPERIMENTAL_ONLY:
            self.assertIn(name, names)

    def test_leaving_the_line_is_refused_once_a_protocol_revision_exists(self) -> None:
        workspace = self.scored(KIND)
        revision = workspace / "protocol" / "study-protocol-panela-v01.md"
        revision.parent.mkdir(parents=True, exist_ok=True)
        revision.write_text("draft\n", encoding="utf-8")
        self.assertEqual(kind_module.started_markers(workspace), ["protocol/study-protocol-panela-v01.md"])
        before = self.config(workspace)
        code, out, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", str(workspace))
        self.assertNotEqual(code, 0)
        self.assertIn("protocol/study-protocol-panela-v01.md", err)
        self.assertIn("--force", err)
        self.assertNotIn("Paper line:", out)
        self.assertEqual(self.config(workspace), before)
        self.assertTrue((workspace / LINE_SKILL / "SKILL.md").is_file())
        self.assertEqual(revision.read_text(encoding="utf-8"), "draft\n")

    def test_the_protocol_lock_alone_refuses_leaving_and_force_moves_it(self) -> None:
        workspace = self.scored(KIND)
        lock = workspace / "study" / "protocol.lock.json"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("{}\n", encoding="utf-8")
        self.assertEqual(kind_module.started_markers(workspace), ["study/protocol.lock.json"])
        code, _, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", str(workspace))
        self.assertNotEqual(code, 0)
        self.assertIn("study/protocol.lock.json", err)
        self.assertIn("--force", err)
        self.assertEqual(self.config(workspace)["paper_kind"], KIND)
        self.assertTrue((workspace / LINE_SKILL / "SKILL.md").is_file())

        code, out, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", "--force", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertIn(f"Paper line: {KIND} -> experimental", out)
        self.assertEqual(self.config(workspace)["paper_kind"], "experimental")
        self.assertFalse((workspace / "skills" / "qualitative-participatory").exists())
        self.assertEqual(lock.read_text(encoding="utf-8"), "{}\n")


class CatalogueTests(unittest.TestCase):
    def test_the_type_is_available_and_its_variants_choose_the_checklist(self) -> None:
        item = registry.get(KIND)
        self.assertEqual((item["status"], item["line"]), ("available", KIND))
        self.assertEqual(registry.by_line(KIND)["id"], KIND)
        self.assertNotIn("checklist", item)
        variants = {v["id"]: v for v in item["variants"]}
        self.assertEqual(sorted(variants), ["consensus-foresight", "experience-report", "qualitative-mixed"])
        self.assertEqual(registry.checklist_for(item, "qualitative-mixed"), "srqr")
        self.assertEqual(registry.checklist_for(item, "consensus-foresight"), "accord")
        self.assertIsNone(registry.checklist_for(item, "experience-report"))
        self.assertIsNone(registry.checklist_for(item, None))
        for variant in variants.values():
            self.assertIsNone(variant["flow_template"])

    def test_no_catalogue_type_is_planned_any_more(self) -> None:
        self.assertEqual([t["id"] for t in registry.load() if t["status"] == "planned"], [])
        self.assertEqual({t["line"] for t in registry.available()}, set(manifest.PAPER_KINDS))


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
    def test_the_line_ships_eight_imrad_contracts_in_order_before_the_back_matter(self) -> None:
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

    def test_the_methods_follow_srqr(self) -> None:
        methods = [block["id"] for block in header_of(CONTRACTS / "04-methods.md").blocks]
        srqr = ["m-approach-paradigm", "m-researcher-reflexivity", "m-context", "m-sampling", "m-ethics-consent",
                "m-data-collection", "m-units-of-study", "m-data-processing", "m-data-analysis",
                "m-trustworthiness"]
        self.assertEqual([block for block in methods if block in srqr], srqr)

    def test_the_variant_blocks_are_optional_and_name_their_variant(self) -> None:
        corpus = paper_graph.assemble_corpus(self.corpus_root() / "sections")
        for (name, block), (variant, needles) in VARIANT_BLOCKS.items():
            with self.subTest(block=block):
                qualified = f"{SECTIONS[FILES.index(name)]}.{block}"
                self.assertTrue(corpus.blocks[qualified].optional)
                rule = " ".join(block_rule(name, block).split())
                self.assertIn(f"`{variant}`", rule)
                for needle in needles:
                    self.assertIn(needle, rule)
                self.assertIn(f"`{block}`", disqualifiers_of(name))

    def test_a_qualitative_mixed_paper_must_write_its_transcript_blocks(self) -> None:
        for name, block in MIXED_REQUIRED:
            with self.subTest(block=block):
                rule = " ".join(block_rule(name, block).split())
                self.assertIn("`qualitative-mixed`", rule)
                self.assertIn("required there", rule)
                self.assertIn(f"`{block}`", disqualifiers_of(name))

    def test_the_blocks_read_the_line_records(self) -> None:
        for (name, block), needles in RECORD_BINDINGS.items():
            rule = " ".join(block_rule(name, block).split())
            for needle in needles:
                with self.subTest(block=block, needle=needle):
                    self.assertIn(needle, rule)

    def test_an_experience_report_claims_no_effect(self) -> None:
        disqualifiers = " ".join(disqualifiers_of("06-discussion.md").split())
        self.assertIn("experience report", disqualifiers)
        self.assertIn("effect", disqualifiers)

    def test_every_contract_states_the_human_boundaries(self) -> None:
        from skills._core.command_center import state_extractor
        for name in FILES:
            with self.subTest(contract=name):
                text = body_of(CONTRACTS / name)
                self.assertEqual(text.count("\n## LIA house style\n"), 1)
                style = " ".join(text.split("\n## LIA house style\n", 1)[1].split("\n## Disqualifiers\n", 1)[0]
                                 .split())
                for rule in (NO_DATA_RULE, NO_TRANSCRIPT_RULE, HUMAN_RULE):
                    self.assertIn(rule, style)
                low, high = state_extractor._extent(text)
                self.assertIsNotNone(low)
                self.assertLess(low, high)
                for foreign in ("A029", "review/prisma.json", "Results/discussion.json", "G-NOVELTY",
                                "study/instruments.json", "study/allocation.json", "datasets_cli.py --root . deposit"):
                    self.assertNotIn(foreign, text)

    def test_the_srqr_coreq_and_accord_targets_resolve_to_these_sections(self) -> None:
        sections = engine.contract_sections(self.corpus_root())
        for gid in GUIDELINES:
            guideline = engine.load_guideline(gid)
            self.assertEqual(guideline["lines"], [KIND])
            for item in guideline["items"]:
                targets = item["targets"].get(KIND, item["targets"].get("default"))
                scopes = [scope for rule in item.get("evidence", []) for scope in rule.get("in", [])]
                for target in list(targets) + scopes:
                    with self.subTest(guideline=gid, item=item["number"], target=target):
                        section, _, block = target.partition(".")
                        self.assertIn(section, sections)
                        if block:
                            self.assertIn(block, sections[section])


class FlowTextTests(CommandCheck):
    def test_the_flow_names_its_steps_gates_and_records(self) -> None:
        self.assertTrue(flow_text().startswith(FLOW_HEADING))
        text = " ".join(flow_text().split())
        for snippet in ("/plausibility", "/paper-type", "/study-protocol-deliberation", "study_cli.py protocol approve",
                        "study_cli.py ethics record", "--not-applicable", "qual_cli.py transcripts add",
                        "qual_cli.py transcripts status", "consensus_cli.py panel add", "consensus_cli.py plan record",
                        "consensus_cli.py round record", "qual_cli.py codebook record", "qual_cli.py themes signoff",
                        "consensus_cli.py round status", "consensus_cli.py micmac compute", "qual_cli.py quotes check",
                        "\\pquote", "/paper-writing", "--guideline srqr", "--guideline coreq", "--guideline accord",
                        "qualitative-study", "paper_cli.py verify", "/figure-review", "smith audit .",
                        "Integration with prior work", "optional for an experience report", *GATES):
            self.assertIn(snippet, text, snippet)

    def test_the_flow_states_what_stays_human(self) -> None:
        text = " ".join(flow_text().split())
        self.assertIn(NO_DATA_RULE, text)
        self.assertIn(NO_TRANSCRIPT_RULE, text)
        self.assertIn(HUMAN_RULE, text)

    def test_every_cli_command_the_flow_names_exists(self) -> None:
        commands = [c for c in cli_spans(flow_text()) if "_cli.py " in c]
        self.assertGreaterEqual(len(commands), 18)
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


class ContractCommandTests(CommandCheck):
    """The section contracts direct the writer to CLI commands; each one must exist as written."""

    #: The study CLIs a contract may name; a span naming one of them is checked against its `--help`.
    STUDY_CLIS = ("study_cli.py", "qual_cli.py", "consensus_cli.py", "checklist_cli.py", "datasets_cli.py",
                  "analysis_cli.py", "flow_cli.py")

    def test_every_study_cli_command_the_contracts_name_exists(self) -> None:
        named = rf"(?:^|/)(?:{'|'.join(map(re.escape, self.STUDY_CLIS))}) \S"
        commands = []
        for name in FILES:
            body = body_of(CONTRACTS / name)
            found = [command for command in cli_spans(body) if re.search(named, command)]
            # Every mention of a study CLI is a backticked command the check below can read.
            mentions = re.findall(rf"(?:{'|'.join(map(re.escape, self.STUDY_CLIS))})\s", body)
            self.assertEqual(len(found), len(mentions), f"{name}: a study CLI named outside a command span")
            commands += [(name, command) for command in found]
        self.assertGreaterEqual(len(commands), 10)
        for name, command in commands:
            with self.subTest(contract=name, command=command):
                self.check_command(command)


class SkillTests(CommandCheck):
    def test_the_skill_names_the_line(self) -> None:
        text = skill_text()
        self.assertTrue(text.startswith("---\nname: qualitative-participatory\n"))
        self.assertFalse(list(SKILL_PATH.parent.glob("**/*.py")), "the line skill owns no script")
        flat = " ".join(text.split())
        self.assertIn(NO_TRANSCRIPT_RULE, flat)
        self.assertIn(HUMAN_RULE, flat)
        for gate in GATES:
            self.assertIn(gate, flat)
        for guideline in GUIDELINES:
            self.assertIn(guideline, flat)
        self.assertIn("qualitative-study", flat)

    def test_every_cli_command_the_skill_names_exists_with_its_required_options(self) -> None:
        commands = [c for c in cli_spans(skill_text()) if "_cli.py " in c]
        self.assertGreaterEqual(len(commands), 18)
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
        self.assertIn("qualitative-participatory", slash)
        for name in sorted(slash):
            with self.subTest(command=name):
                self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file(), name)
        for path in re.findall(r"`(skills/[A-Za-z0-9_./-]+)`", text):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).exists(), path)


if __name__ == "__main__":
    unittest.main()
