"""`figure-semantics` compares a figure's components against the manuscript.

A section contract (`sections/*.md`) is the plan for a section, not its
prose: a paper-specific component such as "Circular Data Re-Uploading
(CDRU)" is named in the manuscript block that realises the section, never in
the contract. Both callers of `paper_figure_audit.audit_semantics` — the
aggregate `verify` check (`paper_coupling_evidence._figure_semantics`) and
the standalone `figure audit --section` verb — therefore have to hand the
auditor the contract body PLUS the section's manuscript blocks from
`paper/main.tex`, or every such component reports `unmatched_nodes` even
when the manuscript names it verbatim.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_block  # noqa: E402
import paper_cli  # noqa: E402
import paper_coupling_evidence  # noqa: E402
import paper_scaffold  # noqa: E402

COMPONENT = "Circular Data Re-Uploading (CDRU)"
OTHER_COMPONENT = "Hybrid Quantum Readout"
FIGURE_ID = "methods-figure"

#: The manuscript prose realising the methods section: the component sits in
#: a `\subsection` title, the way a real paper names a method it introduces.
MANUSCRIPT_BODY = (
    "\\subsection{Circular Data Re-Uploading (CDRU)}\n"
    "The encoder re-uploads each sample once per layer.\n"
)


class ManuscriptProseFixture(unittest.TestCase):
    """A scaffolded paper with a `methods` section contract that declares a
    `figure:` obligation and one figure whose manifest lists `components`."""

    def setUp(self) -> None:
        # `figure audit --sections` resolves inside the repository root, so
        # the fixture lives under `.scratch/` rather than the system tmpdir.
        scratch = FORGE_ROOT / ".scratch"
        scratch.mkdir(exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=scratch, prefix=".figure-semantics-prose-")
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.paper_dir = root / "paper"
        self.sections_dir = root / "sections"
        self.sections_dir.mkdir(parents=True)
        paper_scaffold.scaffold(self.paper_dir)
        self._write_contract("The contract describes the plan, not the prose.")

    def _write_contract(self, body: str) -> None:
        header = {
            "section": "methods", "position": 1,
            "blocks": [{
                "id": "diagram", "requires_facts": [], "requires_declarations": [],
                "citations": "none",
                "figure": {
                    "ordered": True, "excludes": [], "caption_enumerates": False,
                    "caption_decodes": False, "mandatory": False,
                },
            }],
        }
        self.sections_dir.joinpath("01-methods.md").write_text(
            "---\n" + json.dumps(header, indent=2) + "\n---\n\n" + body + "\n",
            encoding="utf-8",
        )

    def _write_manuscript_block(self, block_id: str, body: str) -> None:
        paper_block.open_block(self.paper_dir, block_id, at_end=True)
        paper_block.substitute(self.paper_dir, block_id, new_body=body.encode("utf-8"))
        (self.paper_dir / "couplings.json").write_text(
            json.dumps({"blocks": {block_id: {}}}), encoding="utf-8",
        )

    def _write_figure(self, components: list) -> None:
        figures = self.paper_dir / "Figures"
        figures.mkdir(parents=True, exist_ok=True)
        figures.joinpath(f"{FIGURE_ID}.tex").write_text(
            "\n".join(f"% node: {component}" for component in components) + "\n",
            encoding="utf-8",
        )
        figures.joinpath(f"{FIGURE_ID}.diagram.json").write_text(
            json.dumps({
                "components": components, "encodings": [],
                "caption": "Figure: " + ", ".join(components) + ".",
            }),
            encoding="utf-8",
        )

    def _aggregate_report(self) -> dict:
        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)
        return evidence.figure_semantics["figures"][FIGURE_ID]

    def _audit_report(self) -> dict:
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            exit_code = paper_cli.main([
                "figure", "audit", "--paper", str(self.paper_dir),
                "--figure-id", FIGURE_ID, "--section", "methods",
                "--sections", str(self.sections_dir),
            ])
        payload = json.loads(buf.getvalue())
        self.assertEqual(exit_code, 0, payload)
        return payload


class ComponentNamedOnlyInTheManuscriptTests(ManuscriptProseFixture):
    def setUp(self) -> None:
        super().setUp()
        self._write_manuscript_block("methods.body", MANUSCRIPT_BODY)
        self._write_figure([COMPONENT])

    def test_the_aggregate_check_matches_a_component_the_manuscript_names(self) -> None:
        report = self._aggregate_report()

        self.assertEqual(report["unmatched_nodes"], [])
        self.assertEqual(report["verdict"], "pass")

    def test_figure_audit_section_matches_a_component_the_manuscript_names(self) -> None:
        report = self._audit_report()

        self.assertEqual(report["unmatched_nodes"], [])
        self.assertEqual(report["verdict"], "pass")

    def test_a_block_of_another_section_does_not_supply_the_prose(self) -> None:
        # Same words, but under a different section id: only the figure's own
        # section(s) contribute manuscript prose.
        self._write_figure([OTHER_COMPONENT])
        self._write_manuscript_block("results.body", f"\\subsection{{{OTHER_COMPONENT}}}\n")

        self.assertEqual(self._aggregate_report()["unmatched_nodes"], [OTHER_COMPONENT])
        self.assertEqual(self._audit_report()["unmatched_nodes"], [OTHER_COMPONENT])


class ComponentNamedNowhereTests(ManuscriptProseFixture):
    def setUp(self) -> None:
        super().setUp()
        self._write_manuscript_block("methods.body", MANUSCRIPT_BODY)
        self._write_figure([COMPONENT, OTHER_COMPONENT])

    def test_the_aggregate_check_still_reports_the_unnamed_component(self) -> None:
        report = self._aggregate_report()

        self.assertEqual(report["unmatched_nodes"], [OTHER_COMPONENT])
        self.assertEqual(report["verdict"], "fail")

    def test_figure_audit_section_still_reports_the_unnamed_component(self) -> None:
        report = self._audit_report()

        self.assertEqual(report["unmatched_nodes"], [OTHER_COMPONENT])
        self.assertEqual(report["verdict"], "fail")


class NoManuscriptTests(ManuscriptProseFixture):
    def setUp(self) -> None:
        super().setUp()
        self.paper_dir.joinpath("main.tex").unlink()

    def test_the_aggregate_check_falls_back_to_the_contract_text(self) -> None:
        self._write_contract(f"The figure shows {COMPONENT}.")
        self._write_figure([COMPONENT])

        report = paper_coupling_evidence._figure_semantics(
            self.paper_dir, self.sections_dir,
        )["figures"][FIGURE_ID]

        self.assertEqual(report["unmatched_nodes"], [])

    def test_the_aggregate_check_reports_a_component_the_contract_does_not_name(self) -> None:
        self._write_figure([COMPONENT])

        report = paper_coupling_evidence._figure_semantics(
            self.paper_dir, self.sections_dir,
        )["figures"][FIGURE_ID]

        self.assertEqual(report["unmatched_nodes"], [COMPONENT])
        self.assertEqual(report["verdict"], "fail")

    def test_figure_audit_section_uses_the_contract_text_alone(self) -> None:
        self._write_contract(f"The figure shows {COMPONENT}.")
        self._write_figure([COMPONENT, OTHER_COMPONENT])

        report = self._audit_report()

        self.assertEqual(report["unmatched_nodes"], [OTHER_COMPONENT])

    def test_an_unparseable_manuscript_also_falls_back_to_the_contract_text(self) -> None:
        self.paper_dir.joinpath("main.tex").write_text(
            "%% paper-writing block methods.body begin sha256=nothex\n", encoding="utf-8",
        )
        self._write_contract(f"The figure shows {COMPONENT}.")
        self._write_figure([COMPONENT])

        self.assertEqual(self._audit_report()["unmatched_nodes"], [])


if __name__ == "__main__":
    unittest.main()
