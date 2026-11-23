"""The observational-measurement line (paper-type-lines S8, T8-O2 and T8-O3).

The first empirical line is a `manifest.LINES` entry plus its files: section
contracts in `sections-observational-measurement/`, the flow template
`paper-flow-observational-measurement.md.tpl`, the line skill
`skills/observational-measurement/` and the catalogue flip of the
`observational-measurement` type, whose variants each name their reporting
checklist. An experimental or review workspace never receives the line's files.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from papersmith import render
from papersmith.cli import main
from papersmith.core import init as init_module, kind as kind_module, manifest
from papersmith.kit import resolve_and_validate
from skills._core.paper_types import decision, registry

ROOT = Path(__file__).resolve().parents[1]
KIND = "observational-measurement"
SECTIONS_DIR = ROOT / "sections-observational-measurement"
LINE_SKILL = "skills/observational-measurement/"
FLOW_HEADING = "## Paper construction flow (observational and measurement line)"
EXPERIMENTAL_ONLY = sorted(p.name for p in (ROOT / "sections").glob("*.md")
                           if f"sections/{p.name}" != "sections/10-back-matter.md")
SURVEY_IDEA = ("We surveyed 368 rural young people in three municipalities with a structured questionnaire. "
               "A cross-sectional observational study estimates the prevalence of migration intentions.")
#: The CLIs the flow names, and where their verbs live.
CLIS = {
    "study_cli.py": ROOT / "skills/_core/empirical/study_cli.py",
    "analysis_cli.py": ROOT / "skills/_core/empirical/analysis_cli.py",
    "flow_cli.py": ROOT / "skills/_core/participant_flow/flow_cli.py",
    "checklist_cli.py": ROOT / "skills/_core/checklists/checklist_cli.py",
    "datasets_cli.py": ROOT / "skills/datasets/scripts/datasets_cli.py",
    "paper_cli.py": ROOT / "skills/paper-writing/scripts/paper_cli.py",
}


def flow_text() -> str:
    return render.render_package_template(manifest.LINES[KIND].flow_template, {})


def verbs_of(script: Path) -> set[str]:
    """The subcommands a CLI's own argparse usage line accepts."""
    done = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True,
                          cwd=str(ROOT), check=False)
    choices = re.search(r"\{([a-z_,-]+)\}", done.stdout)
    return set(choices.group(1).split(",")) if choices else set()


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
        self.assertEqual(line.sections_dir, "sections-observational-measurement/")
        self.assertEqual(line.only_prefixes, ("sections-observational-measurement/", LINE_SKILL))
        self.assertEqual(line.shared_sections, ("sections/10-back-matter.md",))
        self.assertEqual(line.flow_template, "paper-flow-observational-measurement.md.tpl")
        self.assertEqual(line.topology, "empirical")
        self.assertTrue(line.empirical)
        self.assertIn(line.topology, init_module.TOPOLOGIES)
        self.assertIn(KIND, manifest.PAPER_KINDS)
        self.assertIn("sections-observational-measurement", manifest.KIT_ENTRIES)
        self.assertEqual(registry.LINES, tuple(manifest.LINES))

    def test_no_other_line_receives_the_line_files(self) -> None:
        kit = resolve_and_validate()
        for other in ("experimental", "review"):
            with self.subTest(line=other):
                layout = manifest.kit_layout(kit, other)
                self.assertFalse([p for p in layout if p.startswith(LINE_SKILL)])
                self.assertFalse([s for s in layout.values()
                                  if s.startswith("sections-observational-measurement/")])

    def test_the_line_layout_serves_its_contracts_and_its_skill(self) -> None:
        kit = resolve_and_validate()
        layout = manifest.kit_layout(kit, KIND)
        self.assertEqual(layout["skills/observational-measurement/SKILL.md"],
                         "skills/observational-measurement/SKILL.md")
        self.assertEqual(layout["sections/10-back-matter.md"], "sections/10-back-matter.md")
        self.assertFalse([p for p in layout if p.startswith("skills/systematic-review/")])
        for name in EXPERIMENTAL_ONLY:
            self.assertNotIn(f"sections/{name}", layout)
        for path in sorted(SECTIONS_DIR.glob("*.md")):
            self.assertEqual(layout[f"sections/{path.name}"], f"sections-observational-measurement/{path.name}")


class InitTests(LineCase):
    def test_init_records_the_kind_its_folders_skill_and_command(self) -> None:
        workspace = self.init(KIND)
        self.assertEqual(self.config(workspace)["paper_kind"], KIND)
        for folder in ("protocol", "study", "analysis", "datasets", "paper", "sota-pool"):
            self.assertTrue((workspace / folder).is_dir(), folder)
        for folder in ("proposals", "experiments", "implementations", "kaggle-inbox", "review"):
            self.assertFalse((workspace / folder).exists(), folder)
        self.assertTrue((workspace / LINE_SKILL / "SKILL.md").is_file())
        self.assertTrue((workspace / ".claude" / "commands" / "observational-measurement.md").is_file())
        self.assertFalse((workspace / "skills" / "systematic-review").exists())
        self.assertFalse((workspace / "sections-observational-measurement").exists())
        names = sorted(p.name for p in (workspace / "sections").glob("*.md"))
        self.assertIn("10-back-matter.md", names)
        for name in EXPERIMENTAL_ONLY:
            self.assertNotIn(name, names)
        for path in sorted(SECTIONS_DIR.glob("*.md")):
            self.assertEqual((workspace / "sections" / path.name).read_bytes(), path.read_bytes())

    def test_every_harness_entrypoint_carries_the_line_flow(self) -> None:
        workspace = self.init(KIND)
        for entry in ("CLAUDE.md", "OPENCODE.md", ".pi/APPEND_SYSTEM.md", ".agents/AGENTS.md"):
            text = (workspace / entry).read_text(encoding="utf-8")
            self.assertIn(FLOW_HEADING, text, entry)
            self.assertIn("G-STUDY-PROTOCOL", text, entry)
            self.assertNotIn("**Proof of concept and experiments**", text, entry)

    def test_experimental_and_review_workspaces_never_get_the_line_skill(self) -> None:
        for kind in (None, "review"):
            with self.subTest(kind=kind):
                workspace = self.init(kind)
                self.assertFalse((workspace / "skills" / "observational-measurement").exists())
                self.assertFalse((workspace / ".claude" / "commands" / "observational-measurement.md").exists())
                self.assertNotIn(FLOW_HEADING, (workspace / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_the_cli_accepts_the_kind_and_prints_its_label(self) -> None:
        workspace = self.new_tmp() / "ws"
        code, out, err = self.smith("init", str(workspace), "--kind", KIND, "--tools", "claude", "--no-npm",
                                    "--no-env", "--no-progress")
        self.assertEqual(code, 0, err)
        self.assertIn(f"Paper line: {KIND} ({manifest.LINES[KIND].label}", out)

    def test_a_fresh_workspace_reports_no_drift(self) -> None:
        workspace = self.init(KIND)
        code, out, _ = self.smith("status", str(workspace))
        self.assertEqual(code, 0)
        self.assertIn("Framework drift: none", out)


class FlowTextTests(unittest.TestCase):
    def test_the_flow_names_its_steps_gates_and_records(self) -> None:
        self.assertTrue(flow_text().startswith(FLOW_HEADING))
        text = " ".join(flow_text().split())
        for snippet in ("/study-protocol-deliberation", "study_cli.py protocol approve", "G-STUDY-PROTOCOL",
                        "study_cli.py ethics record", "study_cli.py registration record", "--not-applicable",
                        "datasets_cli.py --root . own", "dictionary init", "dictionary check", " qc ",
                        "deidentify", "analysis_cli.py run", "analysis_cli.py record", "analysis_cli.py status",
                        "flow_cli.py template strobe", "stard-2015", "flow_cli.py check", "flow_cli.py render",
                        "flow_cli.py signoff", "/paper-writing", "--protocol", "--flow", "study-registration",
                        "ethics-approval", "checklist_cli.py check --guideline", "empirical-study",
                        "strobe", "cosmin", "/figure-review", "smith audit ."):
            self.assertIn(snippet, text, snippet)

    def test_the_flow_states_what_stays_human(self) -> None:
        text = " ".join(flow_text().split())
        self.assertIn("never generates measurements or data", text)
        for record in ("ethics", "consent", "data collection", "sign-offs", "primary outcome"):
            self.assertIn(record, text.split("never generates measurements or data", 1)[1])

    def test_every_cli_verb_the_flow_names_exists(self) -> None:
        text = " ".join(flow_text().split())
        named = re.findall(r"\b(\w+_cli\.py)(?: --root \.)? ([a-z][a-z-]*)", text)
        self.assertTrue(named)
        verbs = {name: verbs_of(path) for name, path in CLIS.items()}
        for name, verb in named:
            with self.subTest(cli=name, verb=verb):
                self.assertIn(name, CLIS, f"the flow names an unknown CLI {name}")
                self.assertIn(verb, verbs[name])

    def test_every_path_the_flow_names_exists(self) -> None:
        for path in re.findall(r"`(skills/[A-Za-z0-9_./-]+\.(?:py|md))", flow_text()):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)


class CatalogueTests(unittest.TestCase):
    def test_the_type_is_available_on_its_line(self) -> None:
        item = registry.get(KIND)
        self.assertEqual((item["status"], item["line"]), ("available", KIND))
        self.assertEqual(registry.by_line(KIND)["id"], KIND)

    def test_each_variant_names_its_checklist(self) -> None:
        variants = {v["id"]: v for v in registry.get(KIND)["variants"]}
        self.assertEqual({key: v.get("checklist") for key, v in variants.items()},
                         {"observational": "strobe", "diagnostic-validation": "stard-2015",
                          "measurement-instrument": "cosmin"})
        for variant in variants.values():
            self.assertTrue((registry.GUIDELINES / f"{variant['checklist']}.json").is_file())
            self.assertIsNone(variant.get("flow_template"))

    def test_the_validator_checks_checklist_and_flow_template(self) -> None:
        document = json.loads(registry.CATALOGUE.read_text(encoding="utf-8"))

        def with_variant(**fields) -> dict:
            changed = copy.deepcopy(document)
            family = next(t for t in changed["types"] if t["id"] == KIND)
            family["variants"][0].update(fields)
            return changed

        registry.validate(with_variant(checklist=None, flow_template=None))
        registry.validate(with_variant(flow_template="paper-flow-observational-measurement.md.tpl"))
        for fields, message in (({"checklist": "no-such-guideline"}, "checklist"),
                                ({"checklist": 3}, "checklist"),
                                ({"flow_template": "flow.txt"}, "flow_template"),
                                ({"flow_template": ""}, "flow_template")):
            with self.subTest(fields=fields), self.assertRaisesRegex(registry.RegistryError, message):
                registry.validate(with_variant(**fields))


class KindSetTests(LineCase):
    def scored(self, workspace: Path) -> Path:
        decision.record_acceptance(workspace, SURVEY_IDEA, by="Ana")
        decision.record_scores(workspace, SURVEY_IDEA)
        return workspace

    def test_experimental_to_the_line_and_back(self) -> None:
        workspace = self.scored(self.init())
        code, out, err = self.smith("kind", "set", KIND, "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertIn(f"Paper line: experimental -> {KIND}", out)
        self.assertEqual(self.config(workspace)["paper_kind"], KIND)
        self.assertTrue((workspace / LINE_SKILL / "SKILL.md").is_file())
        self.assertTrue((workspace / "study").is_dir())
        self.assertIn(FLOW_HEADING, (workspace / "CLAUDE.md").read_text(encoding="utf-8"))
        names = sorted(p.name for p in (workspace / "sections").glob("*.md"))
        for name in EXPERIMENTAL_ONLY:
            self.assertNotIn(name, names)
        code, status_out, _ = self.smith("status", str(workspace))
        self.assertIn("Framework drift: none", status_out)

        code, _, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertFalse((workspace / "skills" / "observational-measurement").exists())
        self.assertFalse((workspace / ".claude" / "commands" / "observational-measurement.md").exists())
        names = sorted(p.name for p in (workspace / "sections").glob("*.md"))
        for name in EXPERIMENTAL_ONLY:
            self.assertIn(name, names)

    def test_a_protocol_revision_shows_the_study_started(self) -> None:
        workspace = self.scored(self.init(KIND))
        (workspace / "protocol" / "study-protocol-rural-v01.md").write_text("draft\n", encoding="utf-8")
        self.assertEqual(kind_module.started_markers(workspace), ["protocol/study-protocol-rural-v01.md"])
        code, _, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", str(workspace))
        self.assertNotEqual(code, 0)
        self.assertIn("--force", err)
        self.assertEqual(self.config(workspace)["paper_kind"], KIND)


if __name__ == "__main__":
    unittest.main()
