"""The paper lines as one data table (paper-type-lines S8, T8-G1).

`manifest.LINES` names every paper line a workspace can follow: its section
contracts, the kit paths only it receives, the contracts it shares with the
experimental line, its flow template, its research-state topology and its
`smith init` label. Everything that used to branch on `kind == "review"`
(schema, `kit_layout`, init, the harness flow text, `kind set`) reads the
table, so a later line is a table entry plus its files.

These tests prove it by injecting a temporary third line (`probe`) into the
table and a temporary flow template, without shipping a file for it.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith import generators, render, schema
from papersmith.cli import main
from papersmith.core import init as init_module, kind as kind_module, manifest
from papersmith.errors import UserError
from skills._core.paper_types import registry

PROBE = "probe"
PROBE_FLOW = "## Paper construction flow (probe line)\n\nProbe steps.\n"
PROBE_LINE = manifest.PaperLine(
    sections_dir="sections-probe/",
    only_prefixes=("sections-probe/", "skills/probe-line/"),
    shared_sections=("sections/10-back-matter.md",),
    flow_template="paper-flow-probe.md.tpl",
    topology="empirical",
    label="probe observational study",
    summary="a probe line",
    empirical=True,
)
KIT_FILES = {
    "skills/common/SKILL.md": "common",
    "skills/systematic-review/SKILL.md": "review skill",
    "skills/probe-line/SKILL.md": "probe skill",
    "sections/01-materials-and-methods.md": "experimental methods",
    "sections/10-back-matter.md": "back matter",
    "sections-review/05-methods.md": "review methods",
    "sections-probe/05-methods.md": "probe methods",
    ".claude/agents/helper.md": "agent",
}


class TableCase(unittest.TestCase):
    def new_tmp(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def inject_probe(self) -> Path:
        """Add the probe line to the table and serve its flow template."""
        patcher = mock.patch.dict(manifest.LINES, {PROBE: PROBE_LINE})
        patcher.start()
        self.addCleanup(patcher.stop)
        template = self.new_tmp() / PROBE_LINE.flow_template
        template.write_text(PROBE_FLOW, encoding="utf-8")
        real = render.package_template_path
        path_patcher = mock.patch.object(
            render, "package_template_path",
            side_effect=lambda name: template if name == PROBE_LINE.flow_template else real(name))
        path_patcher.start()
        self.addCleanup(path_patcher.stop)
        return template

    def kit(self) -> Path:
        kit = self.new_tmp() / "kit"
        for relpath, text in KIT_FILES.items():
            (kit / relpath).parent.mkdir(parents=True, exist_ok=True)
            (kit / relpath).write_text(text, encoding="utf-8")
        return kit

    def init(self, kind: str) -> Path:
        workspace = self.new_tmp() / "ws"
        init_module.initialize(workspace, tools=("claude", "opencode", "pi", "antigravity"),
                               run_npm=False, run_env=False, kind=kind)
        return workspace


class TableShapeTests(TableCase):
    def test_the_shipped_lines_and_their_derived_names(self) -> None:
        self.assertEqual(tuple(manifest.LINES), ("experimental", "review", "observational-measurement", "hardware", "lab-simulation"))
        self.assertEqual(manifest.PAPER_KINDS, ("experimental", "review", "observational-measurement", "hardware", "lab-simulation"))
        self.assertEqual(manifest.DEFAULT_PAPER_KIND, "experimental")
        review = manifest.LINES["review"]
        self.assertEqual(manifest.REVIEW_ONLY_PREFIXES, review.only_prefixes)
        self.assertEqual(manifest.REVIEW_ONLY_PREFIXES, ("sections-review/", "skills/systematic-review/"))
        self.assertEqual(manifest.REVIEW_SHARED_SECTIONS, ("sections/10-back-matter.md",))
        self.assertEqual(manifest.LINES["experimental"].flow_template, "paper-flow.md.tpl")
        self.assertEqual(review.flow_template, "paper-flow-review.md.tpl")
        self.assertIn("sections-review", manifest.KIT_ENTRIES)

    def test_the_workspace_registry_names_the_same_lines(self) -> None:
        self.assertEqual(registry.LINES, tuple(manifest.LINES))


class InjectedLineTests(TableCase):
    def test_kit_layout_serves_each_line_its_own_contracts(self) -> None:
        self.inject_probe()
        kit = self.kit()
        experimental = manifest.kit_layout(kit, "experimental")
        self.assertEqual(experimental, {path: path for path in (
            "skills/common/SKILL.md", "sections/01-materials-and-methods.md", "sections/10-back-matter.md",
            ".claude/agents/helper.md")})
        self.assertEqual(manifest.kit_layout(kit, "review"), {
            "skills/common/SKILL.md": "skills/common/SKILL.md",
            "skills/systematic-review/SKILL.md": "skills/systematic-review/SKILL.md",
            "sections/05-methods.md": "sections-review/05-methods.md",
            "sections/10-back-matter.md": "sections/10-back-matter.md",
            ".claude/agents/helper.md": ".claude/agents/helper.md",
        })
        self.assertEqual(manifest.kit_layout(kit, PROBE), {
            "skills/common/SKILL.md": "skills/common/SKILL.md",
            "skills/probe-line/SKILL.md": "skills/probe-line/SKILL.md",
            "sections/05-methods.md": "sections-probe/05-methods.md",
            "sections/10-back-matter.md": "sections/10-back-matter.md",
            ".claude/agents/helper.md": ".claude/agents/helper.md",
        })
        with self.assertRaisesRegex(UserError, "experimental, review, observational-measurement, hardware, lab-simulation, probe"):
            manifest.kit_layout(kit, "survey")

    def test_paper_kind_and_schema_accept_a_table_line(self) -> None:
        workspace = self.new_tmp()
        (workspace / ".papersmith").mkdir()
        (workspace / ".papersmith" / "config.json").write_text(json.dumps({"paper_kind": PROBE}), encoding="utf-8")
        with self.assertRaises(UserError):
            manifest.paper_kind(workspace)
        self.inject_probe()
        self.assertEqual(manifest.paper_kind(workspace), PROBE)
        config = json.loads((self.init("experimental") / ".papersmith" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(schema.validate_config_json({**config, "paper_kind": PROBE})["paper_kind"], PROBE)
        with self.assertRaisesRegex(UserError, "must be experimental, review, observational-measurement, hardware, lab-simulation or probe"):
            schema.validate_config_json({**config, "paper_kind": "survey"})

    def test_the_harness_flow_text_comes_from_the_line_template(self) -> None:
        self.inject_probe()
        workspace = self.new_tmp()
        rendered = generators.render_files(workspace, {"paper_kind": PROBE}, ("claude",))
        self.assertIn("## Paper construction flow (probe line)", rendered["CLAUDE.md"])
        self.assertNotIn("**Proof of concept and experiments**", rendered["CLAUDE.md"])

    def test_init_builds_the_line_topology_and_names_its_label(self) -> None:
        self.inject_probe()
        workspace = self.init(PROBE)
        config = json.loads((workspace / ".papersmith" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["paper_kind"], PROBE)
        for folder in ("protocol", "study", "analysis", "datasets", "paper", "sota-pool"):
            self.assertTrue((workspace / folder / ".gitkeep").is_file(), folder)
        for folder in ("proposals", "experiments", "implementations", "kaggle-inbox", "review"):
            self.assertFalse((workspace / folder).exists(), folder)
        self.assertFalse((workspace / "skills" / "systematic-review").exists())
        self.assertEqual(sorted(p.name for p in (workspace / "sections").glob("*.md")), ["10-back-matter.md"])
        self.assertIn("## Paper construction flow (probe line)", (workspace / "CLAUDE.md").read_text(encoding="utf-8"))

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["init", str(self.new_tmp() / "cli"), "--kind", PROBE, "--tools", "claude", "--no-npm",
                         "--no-env", "--no-progress"])
        self.assertEqual(code, 0)
        self.assertIn("Paper line: probe (probe observational study; see CLAUDE.md)", out.getvalue())
        self.assertNotIn("PRISMA", out.getvalue())

    def test_an_empirical_line_counts_its_protocol_and_lock_as_started(self) -> None:
        self.inject_probe()
        workspace = self.init(PROBE)
        (workspace / "protocol" / "study-protocol-cohort-v01.md").write_text("protocol", encoding="utf-8")
        (workspace / "study" / "protocol.lock.json").write_text("{}", encoding="utf-8")
        self.assertEqual(kind_module.started_markers(workspace),
                         ["protocol/study-protocol-cohort-v01.md", "study/protocol.lock.json"])
        self.assertEqual(kind_module.started_markers(workspace, "experimental"), [])
        with self.assertRaisesRegex(UserError, "started on the probe line .*study/protocol.lock.json"):
            kind_module.set_kind(workspace, "applied-ai", by="Ana")


class ShippedLinesUnchangedTests(TableCase):
    def test_review_init_still_names_prisma(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["init", str(self.new_tmp() / "cli"), "--kind", "review", "--tools", "claude", "--no-npm",
                         "--no-env", "--no-progress"])
        self.assertEqual(code, 0)
        self.assertIn("Paper line: review (PRISMA 2020 systematic review; see CLAUDE.md)", out.getvalue())

    def test_experimental_started_markers_ignore_protocol_files(self) -> None:
        workspace = self.new_tmp()
        (workspace / "protocol").mkdir()
        (workspace / "protocol" / "study-protocol-cohort-v01.md").write_text("protocol", encoding="utf-8")
        (workspace / "proposals").mkdir()
        (workspace / "proposals" / "research-concept-r01.md").write_text("proposal", encoding="utf-8")
        self.assertEqual(kind_module.started_markers(workspace), ["proposals/research-concept-r01.md"])


if __name__ == "__main__":
    unittest.main()
