"""`smith kind set` and the protection of edited section contracts (paper-type-lines S5).

`smith upgrade` used to overwrite any `sections/` contract whose bytes differed
from the kit, including the ones an operator had edited. It now keeps an edited
contract (its bytes differ from the manifest baseline) and reports it, unless
`--force`. `smith kind set <type> --by <name>` records the agreed paper type,
moves the workspace to the type's line through `upgrade`, removes the other
line's files only when unedited and reports the edited ones as stranded.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from papersmith.cli import main
from papersmith.core import init as init_module, manifest, upgrade as upgrade_module
from skills._core.paper_types import decision

ROOT = Path(__file__).resolve().parents[1]
REVIEW_SECTIONS = sorted(p.name for p in (ROOT / "sections-review").glob("*.md"))
EXPERIMENTAL_ONLY = sorted(p.name for p in (ROOT / "sections").glob("*.md")
                           if f"sections/{p.name}" not in manifest.REVIEW_SHARED_SECTIONS)
REVIEW_IDEA = ("A systematic review and meta-analysis of graph neural networks for drug discovery, "
               "following PRISMA with screening and risk of bias.")


class KindCase(unittest.TestCase):
    def new_tmp(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def init(self, kind: str | None = None, *, scored: bool = True) -> Path:
        workspace = self.new_tmp() / "ws"
        kwargs = {} if kind is None else {"kind": kind}
        init_module.initialize(workspace, tools=("claude", "opencode", "pi", "antigravity"),
                               run_npm=False, run_env=False, **kwargs)
        if scored:
            decision.record_acceptance(workspace, REVIEW_IDEA, by="Ana")
            decision.record_scores(workspace, REVIEW_IDEA)
        return workspace

    @staticmethod
    def config(workspace: Path) -> dict:
        return json.loads((workspace / ".papersmith" / "config.json").read_text(encoding="utf-8"))

    @staticmethod
    def paper_type(workspace: Path) -> dict:
        return json.loads((workspace / ".papersmith" / "paper_type.json").read_text(encoding="utf-8"))

    @staticmethod
    def smith(*argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def sections(self, workspace: Path) -> list[str]:
        return sorted(p.name for p in (workspace / "sections").glob("*.md"))


class UpgradeKeepsEditedContractsTests(KindCase):
    def test_upgrade_keeps_an_edited_contract_and_reports_it(self) -> None:
        workspace = self.init(scored=False)
        contract = workspace / "sections" / "04-limitations.md"
        contract.write_text("# Limitations\n\nOur own house rules.\n", encoding="utf-8")
        result = upgrade_module.upgrade(workspace)
        self.assertEqual(contract.read_text(encoding="utf-8"), "# Limitations\n\nOur own house rules.\n")
        self.assertIn("sections/04-limitations.md", result["kept_edited"])
        self.assertNotIn("sections/04-limitations.md", result["changed_files"])
        # The edit stays detectable: a second run keeps it as well.
        again = upgrade_module.upgrade(workspace)
        self.assertIn("sections/04-limitations.md", again["kept_edited"])
        self.assertEqual(contract.read_text(encoding="utf-8"), "# Limitations\n\nOur own house rules.\n")

    def test_the_cli_names_the_kept_contract(self) -> None:
        workspace = self.init(scored=False)
        (workspace / "sections" / "04-limitations.md").write_text("edited\n", encoding="utf-8")
        code, out, _ = self.smith("upgrade", str(workspace))
        self.assertEqual(code, 0)
        self.assertIn("Kept edited contract: sections/04-limitations.md", out)

    def test_force_overwrites_an_edited_contract(self) -> None:
        workspace = self.init(scored=False)
        contract = workspace / "sections" / "04-limitations.md"
        contract.write_text("edited\n", encoding="utf-8")
        result = upgrade_module.upgrade(workspace, force=True)
        self.assertEqual(contract.read_bytes(), (ROOT / "sections" / "04-limitations.md").read_bytes())
        self.assertEqual(result["kept_edited"], [])

    def test_an_unedited_stale_contract_is_still_refreshed(self) -> None:
        # The previous behaviour holds for a copy the framework wrote: an older
        # kit's bytes, recorded as the baseline, are replaced by the current kit.
        workspace = self.init(scored=False)
        contract = workspace / "sections" / "04-limitations.md"
        contract.write_text("an older release's contract\n", encoding="utf-8")
        stored = manifest.load_manifest(workspace)
        files = dict(stored["files"])
        files["sections/04-limitations.md"] = manifest.sha256_file(contract)
        manifest.write_manifest(workspace, stored["version"], files, kind="workspace")
        result = upgrade_module.upgrade(workspace)
        self.assertIn("sections/04-limitations.md", result["changed_files"])
        self.assertEqual(contract.read_bytes(), (ROOT / "sections" / "04-limitations.md").read_bytes())

    def test_an_edited_contract_recorded_unsynchronized_is_kept(self) -> None:
        # An edit unreadable during one upgrade is recorded as unsynchronized;
        # the next upgrade still keeps it (it differs from the kit).
        workspace = self.init(scored=False)
        contract = workspace / "sections" / "04-limitations.md"
        contract.write_text("op edit\n", encoding="utf-8")
        stored = manifest.load_manifest(workspace)
        files = dict(stored["files"])
        files["sections/04-limitations.md"] = "unsynchronized"
        manifest.write_manifest(workspace, stored["version"], files, kind="workspace")
        result = upgrade_module.upgrade(workspace)
        self.assertEqual(contract.read_text(encoding="utf-8"), "op edit\n")
        self.assertIn("sections/04-limitations.md", result["kept_edited"])

    def test_a_deleted_contract_is_still_repaired(self) -> None:
        workspace = self.init(scored=False)
        (workspace / "sections" / "04-limitations.md").unlink()
        result = upgrade_module.upgrade(workspace)
        self.assertIn("sections/04-limitations.md", result["changed_files"])
        self.assertEqual((workspace / "sections" / "04-limitations.md").read_bytes(),
                         (ROOT / "sections" / "04-limitations.md").read_bytes())


class KindSetTests(KindCase):
    def test_experimental_to_review_moves_the_layout_and_records_the_type(self) -> None:
        workspace = self.init()
        code, out, err = self.smith("kind", "set", "review", "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.config(workspace)["paper_kind"], "review")
        names = self.sections(workspace)
        for name in REVIEW_SECTIONS:
            self.assertIn(name, names)
        for name in EXPERIMENTAL_ONLY:
            self.assertNotIn(name, names)
        self.assertIn("10-back-matter.md", names)
        record = self.paper_type(workspace)
        self.assertEqual(record["agreed"], "review")
        self.assertEqual(record["agreed_by"], "Ana")
        for entry in ("CLAUDE.md", "OPENCODE.md", ".pi/APPEND_SYSTEM.md", ".agents/AGENTS.md"):
            self.assertIn("## Paper construction flow (review line)",
                          (workspace / entry).read_text(encoding="utf-8"), entry)
        self.assertIn("Paper line: experimental -> review", out)
        code, status_out, _ = self.smith("status", str(workspace))
        self.assertEqual(code, 0)
        self.assertIn("Framework drift: none", status_out)

    def test_an_edited_contract_of_the_old_line_is_kept_and_reported_stranded(self) -> None:
        workspace = self.init()
        edited = workspace / "sections" / "01-materials-and-methods.md"
        edited.write_text("our methods contract\n", encoding="utf-8")
        code, out, err = self.smith("kind", "set", "review", "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertEqual(edited.read_text(encoding="utf-8"), "our methods contract\n")
        self.assertIn("Stranded (edited, kept): sections/01-materials-and-methods.md", out)
        self.assertFalse((workspace / "sections" / "02-experimental-setup.md").exists())

    def test_review_back_to_experimental_removes_the_review_files(self) -> None:
        workspace = self.init("review")
        self.assertTrue((workspace / "skills" / "systematic-review" / "SKILL.md").exists())
        code, _, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.config(workspace)["paper_kind"], "experimental")
        names = self.sections(workspace)
        for name in EXPERIMENTAL_ONLY:
            self.assertIn(name, names)
        for name in REVIEW_SECTIONS:
            self.assertNotIn(name, names)
        self.assertFalse((workspace / "skills" / "systematic-review").exists())
        self.assertFalse((workspace / ".claude" / "commands" / "systematic-review.md").exists())
        code, status_out, _ = self.smith("status", str(workspace))
        self.assertEqual(code, 0)
        self.assertIn("Framework drift: none", status_out)

    def test_an_upgrade_refusal_leaves_the_records_untouched(self) -> None:
        workspace = self.init()
        (workspace / ".papersmith" / "version").write_text("99.0.0\n", encoding="utf-8")
        state = workspace / ".papersmith"
        before = {p.name: p.read_bytes() for p in state.iterdir() if p.is_file()}
        code, _, err = self.smith("kind", "set", "review", "--by", "Ana", str(workspace))
        self.assertNotEqual(code, 0)
        self.assertIn("backwards", err)
        self.assertEqual(before, {p.name: p.read_bytes() for p in state.iterdir() if p.is_file()})
        self.assertIn("01-materials-and-methods.md", self.sections(workspace))

    def test_an_unreadable_config_refuses_before_the_agreement(self) -> None:
        workspace = self.init()
        (workspace / ".papersmith" / "config.json").write_text("{not json", encoding="utf-8")
        code, _, err = self.smith("kind", "set", "review", "--by", "Ana", str(workspace))
        self.assertNotEqual(code, 0)
        self.assertIn("config.json", err)
        self.assertIsNone(self.paper_type(workspace)["agreed"])
        self.assertEqual((workspace / ".papersmith" / "config.json").read_text(encoding="utf-8"), "{not json")

    def test_a_skill_with_an_edited_file_stays_whole(self) -> None:
        workspace = self.init("review")
        edited = workspace / "skills" / "systematic-review" / "scripts" / "review_cli.py"
        edited.write_text(edited.read_text(encoding="utf-8") + "\n# our change\n", encoding="utf-8")
        code, out, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertTrue((workspace / "skills" / "systematic-review" / "SKILL.md").exists())
        self.assertIn("Stranded (edited, kept): skills/systematic-review/SKILL.md", out)
        self.assertIn("Stranded (edited, kept): skills/systematic-review/scripts/review_cli.py", out)

    def test_the_new_line_gets_its_folders_and_the_summary_counts_both_passes(self) -> None:
        workspace = self.init()
        code, _, err = self.smith("kind", "set", "review", "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertTrue((workspace / "review" / ".gitkeep").exists())
        workspace = self.init("review")
        code, out, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        for folder in ("proposals", "experiments", "implementations", "kaggle-inbox"):
            self.assertTrue((workspace / folder / ".gitkeep").exists(), folder)
        self.assertNotIn("changed files: 0", out)

    def test_the_same_line_records_the_type_and_moves_nothing(self) -> None:
        workspace = self.init()
        before = manifest.load_manifest(workspace)["files"]
        code, out, err = self.smith("kind", "set", "applied-ai", "--by", "Ana", str(workspace))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.paper_type(workspace)["agreed"], "applied-ai")
        self.assertIn("already follows the experimental line", out)
        self.assertEqual(manifest.load_manifest(workspace)["files"], before)

    def test_a_started_manuscript_refuses_unless_forced(self) -> None:
        for marker in ("paper/main.tex", "proposals/idea-r1.md"):
            with self.subTest(marker=marker):
                workspace = self.init()
                (workspace / marker).parent.mkdir(parents=True, exist_ok=True)
                (workspace / marker).write_text("started\n", encoding="utf-8")
                code, _, err = self.smith("kind", "set", "review", "--by", "Ana", str(workspace))
                self.assertNotEqual(code, 0)
                self.assertIn(marker, err)
                self.assertNotIn("paper_kind", self.config(workspace))
                self.assertIsNone(self.paper_type(workspace)["agreed"])
                code, _, err = self.smith("kind", "set", "review", "--by", "Ana", "--force", str(workspace))
                self.assertEqual(code, 0, err)
                self.assertEqual(self.config(workspace)["paper_kind"], "review")

    def test_refusals_write_nothing(self) -> None:
        cases = (
            (("qualitative-participatory", "--by", "Ana"), "has no flow in smith yet"),
            (("no-such-type", "--by", "Ana"), "TYPE_UNKNOWN"),
            (("review",), "--by"),
        )
        for argv, expected in cases:
            with self.subTest(argv=argv):
                workspace = self.init()
                code, _, err = self.smith("kind", "set", *argv, str(workspace))
                self.assertNotEqual(code, 0)
                self.assertIn(expected, err)
                self.assertNotIn("paper_kind", self.config(workspace))
                self.assertIsNone(self.paper_type(workspace)["agreed"])

    def test_an_unscored_idea_refuses_before_any_move(self) -> None:
        workspace = self.init(scored=False)
        code, _, err = self.smith("kind", "set", "review", "--by", "Ana", str(workspace))
        self.assertNotEqual(code, 0)
        self.assertIn("SCORES_ABSENT", err)
        self.assertNotIn("paper_kind", self.config(workspace))
        self.assertIn("01-materials-and-methods.md", self.sections(workspace))


if __name__ == "__main__":
    unittest.main()
