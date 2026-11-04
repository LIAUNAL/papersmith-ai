"""The command center's state extractor is read-only and honest.

Every fixture here is a hand-built workspace holding exactly the bytes the
assertion is about, so a failure names the input rather than a fixture
generator.
"""

from __future__ import annotations

import fnmatch
import json
import re
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import state_extractor

try:
    import yaml  # noqa: F401  (PyYAML is a kit dependency)

    HAS_YAML = True
except ModuleNotFoundError:  # pragma: no cover - kit venv installs PyYAML
    HAS_YAML = False


def _contract(section: str, position: int, blocks: list[dict]) -> str:
    meta = {"section": section, "position": position, "mode": {"value": "argument"}, "blocks": blocks}
    return "---\n" + json.dumps(meta, indent=2) + "\n---\n\n# " + section + "\n\n**Extent** 100–250 words · one subsection\n"


class ReadOnlyObserverTests(unittest.TestCase):
    """Deriving state must not write into the workspace it observes.

    The extractor loads the workspace's own `paper_declarations` module, and an
    unsuppressed import leaves `__pycache__` behind. Measured before this lock:
    the first derivation created 12 paths inside the paper folder, falsifying
    three shipped read-only claims at once. The workspace's own `.gitignore`
    hides `__pycache__`, so nothing else would ever have seen it.
    """

    def new_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / "sections").mkdir(parents=True)
        scripts = root / "skills" / "paper-writing" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "paper_declarations.py").write_text(
            "FACT_SOURCE_ROOT = {'a-fact': 'a reason'}\n", encoding="utf-8")
        return root

    def file_set(self, root: Path) -> list[str]:
        return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())

    def test_deriving_state_writes_nothing_into_the_workspace(self) -> None:
        root = self.new_workspace()
        before = self.file_set(root)

        state = state_extractor.get_workspace_state(root)

        assert self.file_set(root) == before, (
            "deriving state wrote into the workspace it only observes. An "
            "unsuppressed module import leaves `__pycache__` behind, which the "
            "workspace's own .gitignore hides from every other gate")
        assert state["gates"], "the payload lost its gates"

    def test_the_loader_still_reaches_the_workspace_declaration(self) -> None:
        """Non-vacuity: the suppression must not silently break the load it
        wraps, which would look identical from the outside."""
        root = self.new_workspace()

        facts = state_extractor._external_fact_ids(str(root))

        assert "a-fact" in facts, sorted(facts)


class StateExtractorTests(unittest.TestCase):
    def new_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / "sections").mkdir(parents=True)
        (root / "paper").mkdir()
        return root

    def test_payload_always_carries_the_contract_keys(self) -> None:
        root = self.new_workspace()
        state = state_extractor.get_workspace_state(root)

        assert set(state) == {
            "generated_at", "workspace", "paper_metadata", "sections",
            "gates", "pipeline_stages", "pipeline_chain", "gate_links",
            "experiments", "figures", "inbox", "totals",
        }
        assert [gate["id"] for gate in state["gates"]] == [
            "writing-readiness", "coupling-verification",
            "grounding-style-leak", "diagram-raster",
        ]
        assert [stage["id"] for stage in state["pipeline_stages"]] == [
            "harness", "plausibility", "ingestion", "proposal",
            "experimental-deliberation", "implementation",
            "experimental-implementation", "credentials", "remote",
            "scaffolding", "declarations", "writing", "figures", "paper", "audit",
        ]

    def test_a_missing_workspace_is_empty_not_an_error(self) -> None:
        root = self.new_workspace() / "does-not-exist"
        state = state_extractor.get_workspace_state(root)

        assert state["workspace"]["root"] == str(root)
        # The ten section slots are always present so the matrix renders; none
        # of them has a contract yet.
        assert len(state["sections"]) == 10
        assert all(section["status"] == "SCAFFOLDED" for section in state["sections"])
        assert state["totals"]["sections"] == 10
        assert state["totals"]["blocks_total"] == 0
        assert state["gates"][0]["state"] == "BLOCKED"

    def test_contract_without_a_draft_is_contracted(self) -> None:
        root = self.new_workspace()
        (root / "sections" / "01-materials-and-methods.md").write_text(
            _contract("materials-and-methods", 5, [
                {"id": "mm-preamble", "requires_facts": [], "requires_declarations": [], "citations": "none"},
                {"id": "mm-proposal", "requires_facts": [{"value": "formulation"}],
                 "requires_declarations": [], "produces_facts": [{"value": "contributions"}]},
            ]),
            encoding="utf-8",
        )
        state = state_extractor.get_workspace_state(root)

        section = state["sections"][0]
        assert section["status"] == "CONTRACTED"
        assert section["blocks_total"] == 2
        assert section["blocks_written"] == 0
        assert section["extent"] == {"min_words": 100, "max_words": 250}
        assert section["facts"]["demands"] == ["formulation"]
        assert section["facts"]["produces"] == ["contributions"]

    def test_word_count_and_drafting_come_from_block_markers(self) -> None:
        root = self.new_workspace()
        (root / "sections" / "01-materials-and-methods.md").write_text(
            _contract("materials-and-methods", 5, [
                {"id": "mm-preamble", "requires_facts": [], "requires_declarations": [], "citations": "none"},
                {"id": "mm-proposal", "requires_facts": [], "requires_declarations": [], "citations": "none"},
            ]),
            encoding="utf-8",
        )
        (root / "paper" / "main.tex").write_text(
            "\\documentclass{article}\n"
            "%% paper-writing block materials-and-methods.mm-preamble begin sha256=" + "a" * 64 + "\n"
            "one two three four five\n"
            "%% paper-writing block materials-and-methods.mm-preamble end\n"
            "%% paper-writing block materials-and-methods.mm-proposal begin sha256=" + "b" * 64 + "\n"
            "%% paper-writing block materials-and-methods.mm-proposal end\n",
            encoding="utf-8",
        )
        state = state_extractor.get_workspace_state(root)

        section = state["sections"][0]
        assert section["blocks_written"] == 1
        assert section["word_count"] == 5
        assert section["status"] == "DRAFTING"

    def test_unresolved_citation_placeholder_blocks_the_grounding_gate(self) -> None:
        root = self.new_workspace()
        (root / "sections" / "01-materials-and-methods.md").write_text(
            _contract("materials-and-methods", 5, [
                {"id": "mm-proposal", "requires_facts": [], "requires_declarations": [], "citations": "none"},
            ]),
            encoding="utf-8",
        )
        (root / "paper" / "main.tex").write_text(
            "%% paper-writing block materials-and-methods.mm-proposal begin sha256=" + "a" * 64 + "\n"
            "We build on \\cite{unknown-key}.\n"
            "%% paper-writing block materials-and-methods.mm-proposal end\n",
            encoding="utf-8",
        )
        state = state_extractor.get_workspace_state(root)

        gate = next(g for g in state["gates"] if g["id"] == "grounding-style-leak")
        assert gate["state"] == "BLOCKED"
        assert gate["parts"]["placeholder_citations"] == 1
        assert state["sections"][0]["status"] == "DRAFTING"

    def test_a_sealed_paper_reports_sealed(self) -> None:
        root = self.new_workspace()
        (root / "sections" / "01-materials-and-methods.md").write_text(
            _contract("materials-and-methods", 5, [
                {"id": "mm-proposal", "requires_facts": [], "requires_declarations": [], "citations": "none"},
            ]),
            encoding="utf-8",
        )
        (root / "paper" / "main.tex").write_text(
            "%% paper-writing block materials-and-methods.mm-proposal begin sha256=" + "a" * 64 + "\n"
            "A fully written paragraph.\n"
            "%% paper-writing block materials-and-methods.mm-proposal end\n",
            encoding="utf-8",
        )
        (root / "paper" / "verdict.json").write_text("{}", encoding="utf-8")
        state = state_extractor.get_workspace_state(root)

        assert state["sections"][0]["status"] == "SEALED"

    def test_coupling_gate_blocks_a_demand_without_a_producer(self) -> None:
        root = self.new_workspace()
        (root / "sections" / "01-materials-and-methods.md").write_text(
            _contract("materials-and-methods", 5, [
                {"id": "mm-proposal", "requires_facts": [{"value": "no-such-fact"}],
                 "requires_declarations": [], "citations": "none"},
            ]),
            encoding="utf-8",
        )
        state = state_extractor.get_workspace_state(root)

        gate = next(g for g in state["gates"] if g["id"] == "coupling-verification")
        assert gate["state"] == "BLOCKED"
        assert gate["parts"]["unmatched"] == ["no-such-fact"]

    def test_external_and_structural_facts_clear_the_coupling_gate(self) -> None:
        """A demanded fact is resolved by its external `FACT_SOURCE_ROOT` route
        (`formulation`) or by skeleton-startup (`skeleton`), so neither may
        block the gate. Only a fact with no route at all blocks it."""
        root = self.new_workspace()
        (root / "sections" / "01-materials-and-methods.md").write_text(
            _contract("materials-and-methods", 5, [
                {"id": "mm-a", "requires_facts": [{"value": "formulation"}],
                 "requires_declarations": [], "citations": "none"},
                {"id": "mm-b", "requires_facts": [{"value": "skeleton"}],
                 "requires_declarations": [], "citations": "none"},
            ]),
            encoding="utf-8",
        )
        state = state_extractor.get_workspace_state(root)

        gate = next(g for g in state["gates"] if g["id"] == "coupling-verification")
        assert gate["state"] == "PASSED"
        assert gate["parts"]["unmatched"] == []
        assert "formulation" in gate["parts"]["external"]

    def test_a_produced_fact_clears_the_coupling_gate(self) -> None:
        root = self.new_workspace()
        (root / "sections" / "01-materials-and-methods.md").write_text(
            _contract("materials-and-methods", 5, [
                {"id": "mm-a", "requires_facts": [], "requires_declarations": [],
                 "produces_facts": [{"value": "formulation"}], "citations": "none"},
            ]),
            encoding="utf-8",
        )
        (root / "sections" / "02-experimental-setup.md").write_text(
            _contract("experimental-setup", 6, [
                {"id": "es-a", "requires_facts": [{"value": "formulation"}],
                 "requires_declarations": [], "citations": "none"},
            ]),
            encoding="utf-8",
        )
        state = state_extractor.get_workspace_state(root)

        gate = next(g for g in state["gates"] if g["id"] == "coupling-verification")
        assert gate["state"] == "PASSED"

    def test_paper_metadata_prefers_the_workspace_yaml(self) -> None:
        root = self.new_workspace()
        (root / "papersmith.yaml").write_text(
            'version: "1"\nname: "my-paper"\ntitle: "A Real Title"\n'
            'topic: "graphs"\nvenue_target: "NeurIPS"\nauthors:\n  - "A. Author"\n',
            encoding="utf-8",
        )
        (root / ".papersmith").mkdir()
        (root / ".papersmith" / "config.json").write_text(
            json.dumps({"project_name": "fallback", "active_tools": ["claude"],
                        "execution_engine": {"active_compute_target": "local-workstation"}}),
            encoding="utf-8",
        )
        state = state_extractor.get_workspace_state(root)

        metadata = state["paper_metadata"]
        assert metadata["name"] == "my-paper"
        assert metadata["title"] == "A Real Title"
        assert metadata["topic"] == "graphs"
        assert metadata["authors"] == ["A. Author"]
        assert metadata["tools"] == ["claude"]
        assert metadata["compute_target"] == "local-workstation"

    def test_non_dict_workspace_config_degrades_without_raising(self) -> None:
        """A `.papersmith/config.json` that is valid JSON but not an object
        must not abort `/api/state`; the metadata degrades to workspace defaults."""
        root = self.new_workspace()
        (root / ".papersmith").mkdir()
        (root / ".papersmith" / "config.json").write_text("[1, 2, 3]", encoding="utf-8")

        state = state_extractor.get_workspace_state(root)

        assert state["paper_metadata"]["name"] == root.name
        assert set(state) >= {"paper_metadata", "sections", "gates", "pipeline_stages"}

    def test_a_partial_scaffold_blocks_writing_readiness(self) -> None:
        """One contract present is not a complete scaffold: the ten canonical
        slots are always reported, so the nine missing ones block readiness."""
        root = self.new_workspace()
        (root / "sections" / "01-materials-and-methods.md").write_text(
            _contract("materials-and-methods", 5, [
                {"id": "mm-proposal", "requires_facts": [],
                 "requires_declarations": [], "citations": "none"},
            ]),
            encoding="utf-8",
        )

        state = state_extractor.get_workspace_state(root)

        assert len(state["sections"]) == 10
        gate = next(g for g in state["gates"] if g["id"] == "writing-readiness")
        assert gate["state"] == "BLOCKED"
        assert gate["parts"] == {"contracts_total": 10, "contracts_ok": 1}

    def test_the_repository_contracts_parse(self) -> None:
        """The ten real contracts in this repository must all parse."""
        repository = Path(__file__).resolve().parent.parent
        state = state_extractor.get_workspace_state(repository)

        assert len(state["sections"]) == 10
        assert all(section["has_contract"] for section in state["sections"])
        assert all(section["blocks_total"] > 0 for section in state["sections"])
        assert state["totals"]["blocks_total"] > 0

    @unittest.skipUnless(HAS_YAML, "PyYAML is required for YAML frontmatter")
    def test_a_scalar_mode_contract_degrades_without_raising(self) -> None:
        """A scalar frontmatter field where a mapping is expected (`mode:
        argument`) degrades exactly that field to `None` instead of aborting
        `get_workspace_state` and blanking the whole `/api/state` payload."""
        root = self.new_workspace()
        (root / "sections" / "01-materials-and-methods.md").write_text(
            "---\n"
            "section: materials-and-methods\n"
            "position: 5\n"
            "mode: argument\n"
            "blocks:\n"
            "  - id: mm-proposal\n"
            "    requires_facts: []\n"
            "    requires_declarations: []\n"
            "    citations: none\n"
            "---\n\n"
            "# materials-and-methods\n\n"
            "**Extent** 100–250 words\n",
            encoding="utf-8",
        )
        state = state_extractor.get_workspace_state(root)

        section = state["sections"][0]
        assert section["has_contract"] is True
        assert section["mode"] is None
        assert section["section"] == "materials-and-methods"



class PipelineFlowTests(unittest.TestCase):
    """The dashboard's flows are the architecture diagram's flows.

    The diagram (``docs/diagrams/papersmith-pi-flow.html``, built from
    ``docs/diagrams/papersmith-pi-flow.build.mjs``) numbers its lanes by the
    eleven dashboard phases; the board's tramos map onto them in order, Phase 5
    as five tramos (protocol, proof of concept, full experiments, credentials,
    remote run) and every other phase as one. The extractor used
    to ship six stages invented in this directory -- ``ingestion``,
    ``deliberation``, ``experiments``, ``drafting``, ``auditing``,
    ``publishing`` -- and nothing compared the two, so the board drew a project
    that was not the project. These lock the transcription and the honest half
    of it: a tramo with no artifact on disk lights up for nothing.
    """

    TRAMOS = [
        "harness", "plausibility", "ingestion", "proposal", "experimental-deliberation",
        "implementation", "experimental-implementation", "credentials",
        "remote", "scaffolding", "declarations", "writing", "figures", "paper",
    ]

    #: The diagram draws the audit lane beside the numbered phases as the
    #: transversal one, and the board follows: it is a stage so the four
    #: gates have somewhere to land, and no chain edge touches it.
    AUDIT = "audit"

    CHAIN = [
        ("plausibility", "ingestion", "top-5 to ingest"),
        ("ingestion", "proposal", "guidance/"),
        ("proposal", "experimental-deliberation", "rNN revision"),
        ("experimental-deliberation", "implementation", "protocol"),
        ("implementation", "experimental-implementation", "verified PoC (G-EXP-POC)"),
        ("experimental-implementation", "credentials", "job ready"),
        ("credentials", "remote", "accounts validated"),
        ("remote", "scaffolding", "findings approved (G-NOVELTY)"),
        ("scaffolding", "declarations", "section contracts"),
        ("declarations", "writing", "declarations"),
        ("writing", "figures", "sections"),
        ("figures", "paper", "anchors"),
    ]

    def new_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / "sections").mkdir(parents=True)
        (root / "paper").mkdir()
        return root

    @staticmethod
    def write(path: Path, text: str = "{}\n") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def active(self, root: Path) -> set[str]:
        return {
            stage["id"]
            for stage in state_extractor.get_workspace_state(root)["pipeline_stages"]
            if stage["active"]
        }

    def test_the_stages_are_the_diagrams_tramos_in_order(self) -> None:
        state = state_extractor.get_workspace_state(self.new_workspace())

        assert [stage["id"] for stage in state["pipeline_stages"]] == self.TRAMOS + [self.AUDIT]

    def test_the_audit_lane_lights_only_when_every_gate_passed(self) -> None:
        """The audit lane is the gates' outcome, not a fifth opinion about them."""
        root = self.new_workspace()
        stages = {
            stage["id"]: stage
            for stage in state_extractor.get_workspace_state(root)["pipeline_stages"]
        }

        assert stages[self.AUDIT]["active"] is False
        assert "gates passed" in stages[self.AUDIT]["detail"]

    def test_the_chain_is_the_diagrams_main_chain(self) -> None:
        state = state_extractor.get_workspace_state(self.new_workspace())
        ids = {stage["id"] for stage in state["pipeline_stages"]}

        chain = [(edge["from"], edge["to"], edge["label"]) for edge in state["pipeline_chain"]]

        assert chain == self.CHAIN
        assert all(source in ids and target in ids for source, target, _ in chain), (
            "the chain names a stage the stage list does not carry, so the "
            "drawing would drop the edge without saying so")

    #: The three agents that work inside the first tramo. The drawing fills its
    #: plausibility lane with them.
    PLAUSIBILITY_AGENTS = ["novelty-screener", "sota-grapher", "sota-scout"]

    def test_the_plausibility_tramo_lists_the_agents_that_work_in_it(self) -> None:
        root = self.new_workspace()
        for name in self.PLAUSIBILITY_AGENTS + ["redactor"]:
            self.write(root / ".claude" / "agents" / f"{name}.md",
                       f"---\nname: {name}\ntools: Read\n---\n")
        stages = {
            stage["id"]: stage
            for stage in state_extractor.get_workspace_state(root)["pipeline_stages"]
        }

        assert sorted(stages["plausibility"]["workers"]) == self.PLAUSIBILITY_AGENTS
        assert stages["writing"]["workers"] == ["redactor"]

    def test_every_shipped_agent_is_mapped_to_a_tramo(self) -> None:
        """An agent nobody maps is dropped from the board without a word.

        Measured on 2026-10-12: ``AGENT_STAGES`` carried 16 of the 19 shipped
        definitions and the three it was missing were exactly the plausibility
        ones, so the tramo the drawing fills with three agents showed none and
        nothing failed.
        """
        repo = Path(__file__).resolve().parents[1]
        shipped = {path.stem for path in (repo / ".claude" / "agents").glob("*.md")}

        assert shipped, "the repository must define agents"
        assert set(state_extractor.AGENT_STAGES) == shipped

    def test_every_gate_hangs_off_a_known_stage(self) -> None:
        state = state_extractor.get_workspace_state(self.new_workspace())
        ids = {stage["id"] for stage in state["pipeline_stages"]}
        links = state["gate_links"]

        assert set(links) == {gate["id"] for gate in state["gates"]}
        for gate_id, link in links.items():
            assert link["from"] in ids, (gate_id, link)
            assert link["label"], (gate_id, link)
            assert link["consumed_by"] in ids, (gate_id, link)
            assert link["consumed_by"] == self.AUDIT, (gate_id, link)

    def test_every_stage_still_follows_the_published_shape(self) -> None:
        """The node component reads these six keys; the catalogue changed, the
        contract did not."""
        for stage in state_extractor.get_workspace_state(self.new_workspace())["pipeline_stages"]:
            assert set(stage) == {"id", "title", "active", "progress", "detail", "workers"}, stage
            assert stage["title"]
            assert isinstance(stage["active"], bool)
            assert 0.0 <= stage["progress"] <= 1.0
            assert stage["detail"], f"{stage['id']} reported no detail"
            assert isinstance(stage["workers"], list)

    def test_an_empty_workspace_lights_no_tramo(self) -> None:
        """Nothing on disk is nothing reported: a board that guesses is worse
        than a board that is empty."""
        assert self.active(self.new_workspace()) == set()

    def test_a_scaffolds_placeholders_are_not_artifacts(self) -> None:
        """Every drop zone ships with a placeholder so the folder travels.

        Counting one lights its tramo with the only file the scaffold put
        there, which is how `remote` came up green on a workspace that had just
        been created and had never run anything.
        """
        root = self.new_workspace()
        self.write(root / "skills" / "remote-execution" / "scripts" / "remote_cli.py",
                   'INBOX_NAME = "kaggle-inbox"\n')
        for zone in ("implementations", "proposals", "experiments", "kaggle-inbox"):
            directory = root / zone
            directory.mkdir(parents=True, exist_ok=True)
            (directory / ".gitkeep").write_text("", encoding="utf-8")
            (directory / ".gitignore").write_text("*\n", encoding="utf-8")

        assert self.active(root) == set()

    def test_each_tramo_lights_up_from_its_own_artifact(self) -> None:
        def harness(root: Path) -> None:
            (root / ".pi").mkdir()

        def credentials(root: Path) -> None:
            self.write(root / "skills" / "accounts-owner" / "scripts" / "accounts_cli.py",
                       'STORE_NAME = "store"\nSTORE_FILE = "accounts.json"\n')
            self.write(root / "skills" / "accounts-owner" / "store" / "accounts.json",
                       '{"accounts": []}\n')

        def remote(root: Path) -> None:
            self.write(root / "skills" / "remote-execution" / "scripts" / "remote_cli.py",
                       'INBOX_NAME = "kaggle-inbox"\n')
            self.write(root / "kaggle-inbox" / "ledger.jsonl")

        def writing(root: Path) -> None:
            self.write(root / "sections" / "01-materials-and-methods.md",
                       _contract("materials-and-methods", 1, [{"id": "mm-preamble"}]))
            self.write(root / "paper" / "main.tex",
                       "\\documentclass{article}\n"
                       "%% paper-writing block materials-and-methods.mm-preamble begin sha256="
                       + "a" * 64 + "\n"
                       "one two three\n"
                       "%% paper-writing block materials-and-methods.mm-preamble end\n")

        cases = [
            ("harness", harness, {"harness"}),
            ("plausibility",
             lambda root: self.write(root / "sota-pool" / "atlas.json"), {"plausibility"}),
            ("ingestion",
             lambda root: self.write(root / "guidance" / "paper-guide" / "a.md", "# a\n"),
             {"ingestion"}),
            ("proposal",
             lambda root: self.write(root / "proposals" / "research-concept-r01.md", "# r\n"),
             {"proposal"}),
            # The proposal tramo's second artifact kind: the sky graph drawn
            # beside the revision. Either one lights the tramo on its own, and
            # a workspace holding only the graph is a real state -- the chain
            # runs after the publish.
            ("proposal",
             lambda root: self.write(root / "proposals" / "research-concept-r01.graph.html",
                                     "<html></html>\n"),
             {"proposal"}),
            ("implementation",
             lambda root: self.write(root / "implementations" / "repo" / "main.py", "x = 1\n"),
             {"implementation"}),
            ("experimental-deliberation",
             lambda root: self.write(root / ".experimental-deliberation" / "receipts" / "r.json"),
             {"experimental-deliberation"}),
            ("experimental-implementation",
             lambda root: self.write(root / "experiments" / "experiments-slug-v01.md", "# e\n"),
             {"experimental-implementation"}),
            ("credentials", credentials, {"credentials"}),
            ("remote", remote, {"remote"}),
            # A drafted block requires paper/main.tex to exist, so this case
            # legitimately lights the scaffolding tramo too.
            ("writing", writing, {"writing", "scaffolding"}),
            ("figures",
             lambda root: self.write(root / "paper" / "Figures" / "arch.pdf", "%PDF-1.7\n"),
             {"figures"}),
            ("scaffolding",
             lambda root: (root / "paper" / "main.tex").write_text(
                 "\\documentclass{article}\n", encoding="utf-8"),
             {"scaffolding"}),
            ("declarations",
             lambda root: (root / "paper" / "main.tex").write_text(
                 "\\documentclass{article}\n%% paper-writing declarations begin sha256="
                 + "b" * 64 + "\n%% paper-writing declarations end\n", encoding="utf-8"),
             {"scaffolding", "declarations"}),
            ("paper",
             lambda root: self.write(root / "paper" / "main.pdf", "%PDF-1.7\n"),
             {"paper"}),
        ]

        covered = set()
        for stage_id, setup, expected in cases:
            with self.subTest(stage=stage_id):
                root = self.new_workspace()
                setup(root)
                assert self.active(root) == expected
                covered.add(stage_id)

        assert covered == set(self.TRAMOS), (
            f"a tramo has no artifact case: {sorted(set(self.TRAMOS) - covered)}")

    def test_the_proposal_tramo_counts_its_revision_and_its_sky_separately(self) -> None:
        """A revision and the graph beside it are two artifacts, and the board
        says so.

        A proposal can be published without its graph -- that is the half-done
        state this signal exists to show -- so one file must not read as the
        same thing as two, and neither may be inferred from the other.
        """
        def revision(root: Path) -> None:
            self.write(root / "proposals" / "research-concept-r01.md", "# r\n")

        def sky(root: Path) -> None:
            self.write(root / "proposals" / "research-concept-r01.graph.html",
                       "<html></html>\n")

        def both(root: Path) -> None:
            revision(root)
            sky(root)

        def proposal_stage(setup) -> dict:
            root = self.new_workspace()
            setup(root)
            stages = state_extractor.get_workspace_state(root)["pipeline_stages"]
            return next(stage for stage in stages if stage["id"] == "proposal")

        alone = proposal_stage(revision)
        assert alone["active"] is True
        assert "1 proposal(s)" in alone["detail"], alone["detail"]
        assert "0 sky graph(s)" in alone["detail"], alone["detail"]
        assert alone["progress"] == 0.5, alone

        drawn = proposal_stage(sky)
        assert drawn["active"] is True
        assert "0 proposal(s)" in drawn["detail"], drawn["detail"]
        assert "1 sky graph(s)" in drawn["detail"], drawn["detail"]
        assert drawn["progress"] == 0.5, drawn

        complete = proposal_stage(both)
        assert complete["progress"] == 1.0, complete

        assert proposal_stage(lambda root: None)["detail"] == "no proposal revision"

    def test_the_glob_matches_the_artifact_the_skill_names(self) -> None:
        """The tramo's signal and the skill's own output name are one convention
        held in two files, and nothing else in the repository compares them.

        The path is written in the deliberation's instructions and the pattern
        is in the extractor, so a rename on either side would leave the graph
        sitting on disk while the tramo stays dark -- exactly the failure this
        signal exists to prevent.
        """
        skill = (Path(__file__).resolve().parent.parent
                 / "skills" / "proposal-deliberation" / "SKILL.md")
        named = re.findall(r"--out\s+proposals/(\S+)", skill.read_text(encoding="utf-8"))

        assert len(named) == 1, f"expected one artifact name under proposals/, got {named}"
        assert fnmatch.fnmatch(named[0], state_extractor.PROPOSAL_GRAPH_GLOB), (
            f"the skill writes proposals/{named[0]} and the extractor counts "
            f"{state_extractor.PROPOSAL_GRAPH_GLOB}, so the graph would be on "
            "disk and the tramo still dark")
