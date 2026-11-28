"""Block markers on contract disqualifiers (odd/tasks/efficiency-stage-b.md,
S7): "agrega las marcas por bloque".

A `## Disqualifiers` bullet may open with a machine-readable marker naming
the block(s) it is judged on, `[block: <id>]` or `[block: <id>, <id>]`. The
contract judge rules on every unmarked bullet (section-wide, so an older or
customized contract behaves exactly as today) and on the marked bullets of
the block being written; `VERDICT_MISSING` still forces a verdict on every
applicable bullet, and a verdict on a bullet marked for another block
refuses `VERDICT_BULLET_UNKNOWN`. A marker that does not parse, or names a
block the contract does not declare, never removes a rule: that bullet is
judged on every block.

The marker is part of the bullet's verbatim text (the `contract-audit`
spec: "the exact bullet text is what the audit evaluates against, byte for
byte"), so the judge sees it and quotes it back unchanged.

The CLI tests drive `paper_cli.py write` as a subprocess and assert its
JSON, exit code, `main.tex` bytes and attempt ledger on disk. The fixture
paper lives under the gitignored `.scratch/` because `--paper` must resolve
inside the repository; it is removed after each test.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
CLI = SKILL_SCRIPTS / "paper_cli.py"
sys.path.insert(0, str(SKILL_SCRIPTS))
sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
import paper_audit  # noqa: E402
import paper_block  # noqa: E402
import paper_contract  # noqa: E402
import paper_scaffold  # noqa: E402
from impl_refusals import Refused  # noqa: E402

BLOCK = "bm-conflicts-of-interest"
OTHER_BLOCK = "bm-funding"
QUALIFIED = f"back-matter.{BLOCK}"

SECTION_WIDE = "A sentence that names a grant from memory."
OWN = f"[block: {BLOCK}] A conflicts statement that hedges."
OTHER = f"[block: {OTHER_BLOCK}] A funding statement without its grant code."
MULTI = f"[block: {OTHER_BLOCK}, {BLOCK}] A statement that thanks a person."
UNDECLARED = "[block: bm-nonexistent] A rule whose marker names no declared block."
MALFORMED = "[block bm-funding] A rule whose marker does not parse."
MARKED_BULLETS = (SECTION_WIDE, OWN, OTHER, MULTI, UNDECLARED, MALFORMED)
APPLICABLE = [SECTION_WIDE, OWN, MULTI, UNDECLARED, MALFORMED]

UNMARKED_BULLETS = (SECTION_WIDE, "Block 2 without its closing statement of conflicts.")

HEADER = {
    "section": "back-matter",
    "position": 10,
    "mode": {"value": "transposition",
             "source": {"file": "sections/10-back-matter.md", "quote": "The conflicts block"}},
    "blocks": [
        {"id": OTHER_BLOCK, "requires_facts": [], "requires_declarations": [],
         "citations": "none", "optional": True},
        {"id": BLOCK, "requires_facts": [], "requires_declarations": [], "citations": "none"},
    ],
}

SENTENCE = "The authors declare no conflict of interest."
CLEAN = [(SENTENCE, "structural")]


def _prose(bullets) -> str:
    return (
        "# Back Matter\n\n"
        "The conflicts block states that the authors declare no conflict of interest.\n\n"
        "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n\n"
        "## Disqualifiers\n\n" + "".join(f"- {bullet}\n" for bullet in bullets)
    )


def _clear(bullets) -> list:
    return [{"bullet": bullet, "verdict": "clear"} for bullet in bullets]


class _Paper(unittest.TestCase):
    """A scaffolded paper with one back-matter block open and empty."""

    bullets: tuple = MARKED_BULLETS

    def setUp(self) -> None:
        self.root = (FORGE_ROOT / ".scratch"
                     / f".block-marker-test-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper = self.root / "paper"
        paper_scaffold.scaffold(self.paper)
        self.sections = self.root / "sections"
        self.sections.mkdir()
        self.prose = _prose(self.bullets)
        (self.sections / "10-back-matter.md").write_text(
            "---\n" + json.dumps(HEADER) + "\n---\n" + self.prose, encoding="utf-8")
        paper_block.open_block(self.paper, QUALIFIED, at_end=True)
        self.home = Path(tempfile.mkdtemp(prefix="block-marker-home-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    @property
    def ledger(self) -> Path:
        return self.paper / ".paper-writing" / "attempts" / f"{QUALIFIED}.json"

    def _file(self, prefix: str, payload) -> Path:
        path = self.root / f"{prefix}-{uuid.uuid4().hex[:6]}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def run_write(self, verdicts=None, *, precheck: bool = False):
        draft = self._file("draft", {
            "latex": SENTENCE, "bindings": [{"sentence": s, "binding": b} for s, b in CLEAN]})
        argv = [sys.executable, str(CLI), "write", "--paper", str(self.paper),
                "--sections", str(self.sections), "--section", "back-matter",
                "--block", BLOCK, "--draft", str(draft)]
        if precheck:
            argv.append("--precheck")
        if verdicts is not None:
            argv += ["--audit", str(self._file("audit", {"verdicts": verdicts}))]
        before = (self.paper / "main.tex").read_bytes()
        env = {key: value for key, value in os.environ.items()
               if key not in ("CLAUDE_CONFIG_DIR", "PI_CODING_AGENT_DIR", "XDG_DATA_HOME")}
        env["HOME"] = str(self.home)
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=FORGE_ROOT, env=env,
                              timeout=120)
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            payload = {"stdout": proc.stdout, "stderr": proc.stderr}
        return proc.returncode, payload, before, (self.paper / "main.tex").read_bytes()

    def assertRefused(self, outcome, code: str, *needles: str) -> dict:
        returncode, payload, before, after = outcome
        self.assertEqual(payload.get("code"), code, payload)
        self.assertEqual(returncode, 2)
        for needle in needles:
            self.assertIn(needle, payload["detail"])
        self.assertEqual(after, before, "a refused write leaves main.tex byte-identical")
        self.assertFalse(self.ledger.exists(), "an incomplete account spends no attempt")
        return payload


class UnmarkedContractTests(_Paper):
    """A contract with no marker behaves exactly as today."""

    bullets = UNMARKED_BULLETS

    def test_the_precheck_lists_every_bullet_verbatim_in_contract_order(self) -> None:
        returncode, payload, _before, _after = self.run_write(precheck=True)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["disqualifiers"], list(UNMARKED_BULLETS))
        self.assertEqual(payload["disqualifiers"],
                         paper_audit.extract_disqualifiers(self.prose))

    def test_a_missing_verdict_on_any_bullet_still_refuses_verdict_missing(self) -> None:
        self.assertRefused(self.run_write(_clear(UNMARKED_BULLETS[:1])),
                           "VERDICT_MISSING", UNMARKED_BULLETS[1])

    def test_the_attempt_ledger_key_is_unchanged(self) -> None:
        fires = [{"bullet": SECTION_WIDE, "verdict": "fires", "span": "declare no conflict"},
                 {"bullet": UNMARKED_BULLETS[1], "verdict": "clear"}]
        returncode, payload, _before, _after = self.run_write(fires)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["status"], "audit-fired")
        expected = hashlib.sha256(json.dumps(
            {"contract": self.prose, "evidence": [], "mode": "transposition"},
            sort_keys=True).encode("utf-8")).hexdigest()
        ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
        self.assertEqual(ledger["key"], expected)

    def test_a_clear_account_on_every_bullet_writes_the_block(self) -> None:
        returncode, payload, before, after = self.run_write(_clear(UNMARKED_BULLETS))
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["status"], "written")
        self.assertNotEqual(after, before)


class MarkedContractTests(_Paper):
    """Marked bullets are judged only on the block they name."""

    def test_the_precheck_lists_exactly_the_applicable_bullets(self) -> None:
        returncode, payload, before, after = self.run_write(precheck=True)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["disqualifiers"], APPLICABLE)
        self.assertNotIn(OTHER, payload["disqualifiers"])
        self.assertEqual(payload["unresolvedMarkers"], [UNDECLARED, MALFORMED])
        self.assertEqual(after, before)
        self.assertFalse(self.ledger.exists())

    def test_a_clear_account_on_the_applicable_bullets_writes_the_block(self) -> None:
        returncode, payload, before, after = self.run_write(_clear(APPLICABLE))
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["status"], "written")
        self.assertNotEqual(after, before)

    def test_a_missing_verdict_on_a_bullet_marked_for_this_block_refuses(self) -> None:
        account = _clear([bullet for bullet in APPLICABLE if bullet != OWN])
        self.assertRefused(self.run_write(account), "VERDICT_MISSING", OWN)

    def test_a_missing_verdict_on_a_multi_block_bullet_refuses(self) -> None:
        account = _clear([bullet for bullet in APPLICABLE if bullet != MULTI])
        self.assertRefused(self.run_write(account), "VERDICT_MISSING", MULTI)

    def test_a_missing_verdict_on_an_unresolved_marker_refuses(self) -> None:
        for bullet in (UNDECLARED, MALFORMED):
            with self.subTest(bullet=bullet):
                account = _clear([entry for entry in APPLICABLE if entry != bullet])
                self.assertRefused(self.run_write(account), "VERDICT_MISSING", bullet)

    def test_a_verdict_on_a_bullet_marked_for_another_block_refuses(self) -> None:
        self.assertRefused(self.run_write(_clear(APPLICABLE + [OTHER])),
                           "VERDICT_BULLET_UNKNOWN", OTHER, QUALIFIED)

    def test_the_fired_bullet_is_reported_with_its_marker_verbatim(self) -> None:
        account = _clear([bullet for bullet in APPLICABLE if bullet != OWN])
        account.append({"bullet": OWN, "verdict": "fires", "span": "declare no conflict"})
        returncode, payload, _before, _after = self.run_write(account)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["status"], "audit-fired")
        self.assertEqual(payload["fired"], [{"bullet": OWN, "span": "declare no conflict"}])


class UnresolvedMarkersFailTowardJudgingTests(_Paper):
    """A marker that names an undeclared id, misses its space, names the
    qualified id or capitalizes `Block` never removes its rule: the bullet
    is judged on every block and reported as unresolved."""

    BAD = (
        f"[block: {OTHER_BLOCK}, bm-nonexistent] A rule with one undeclared id.",
        f"[block:{OTHER_BLOCK}] A rule whose marker misses its space.",
        f"[block: back-matter.{OTHER_BLOCK}] A rule whose marker names the qualified id.",
        f"[Block: {OTHER_BLOCK}] A rule whose marker is capitalized.",
    )
    bullets = (SECTION_WIDE, *BAD)

    def test_each_bad_marker_is_judged_and_reported_unresolved(self) -> None:
        returncode, payload, _before, _after = self.run_write(precheck=True)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["disqualifiers"], list(self.bullets))
        self.assertEqual(payload["unresolvedMarkers"], list(self.BAD))

    def test_omitting_a_verdict_on_any_bad_marker_refuses_verdict_missing(self) -> None:
        for bullet in self.BAD:
            with self.subTest(bullet=bullet):
                account = _clear([entry for entry in self.bullets if entry != bullet])
                self.assertRefused(self.run_write(account), "VERDICT_MISSING", bullet)


class MarkerIsPartOfTheBulletTests(_Paper):
    def test_quoting_a_marked_bullet_without_its_marker_refuses(self) -> None:
        stripped = paper_audit.bullet_rule(OWN)
        account = _clear([bullet for bullet in APPLICABLE if bullet != OWN] + [stripped])
        self.assertRefused(self.run_write(account), "VERDICT_BULLET_UNKNOWN", stripped)


class MarkerParsingTests(unittest.TestCase):
    """The module surface the CLI and the shipped-contract check share."""

    def test_a_single_and_a_multi_block_marker_parse(self) -> None:
        self.assertEqual(paper_audit.bullet_blocks(OWN), (BLOCK,))
        self.assertEqual(paper_audit.bullet_blocks(MULTI), (OTHER_BLOCK, BLOCK))

    def test_an_unmarked_or_malformed_bullet_names_no_block(self) -> None:
        for bullet in (SECTION_WIDE, MALFORMED, "[block: ] Empty.", "Text [block: a] later."):
            with self.subTest(bullet=bullet):
                self.assertIsNone(paper_audit.bullet_blocks(bullet))

    def test_the_rule_text_drops_only_the_marker(self) -> None:
        self.assertEqual(paper_audit.bullet_rule(OWN), "A conflicts statement that hedges.")
        self.assertEqual(paper_audit.bullet_rule(SECTION_WIDE), SECTION_WIDE)

    def test_without_declared_blocks_every_marker_is_inert(self) -> None:
        self.assertEqual(
            paper_audit.applicable_disqualifiers(list(MARKED_BULLETS), BLOCK),
            list(MARKED_BULLETS))

    def test_a_qualified_block_id_selects_like_a_bare_one(self) -> None:
        declared = (OTHER_BLOCK, BLOCK)
        self.assertEqual(
            paper_audit.applicable_disqualifiers(list(MARKED_BULLETS), QUALIFIED, declared),
            APPLICABLE)
        self.assertEqual(
            paper_audit.applicable_disqualifiers(list(MARKED_BULLETS), BLOCK, declared),
            APPLICABLE)

    def test_audit_without_a_block_judges_every_bullet_as_today(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_audit.audit(_prose(MARKED_BULLETS), SENTENCE, _clear(APPLICABLE))
        self.assertEqual(ctx.exception.code, "VERDICT_MISSING")
        self.assertIn(OTHER, ctx.exception.detail)

    def test_a_marked_row_count_bullet_keeps_its_deterministic_check(self) -> None:
        marked = f"[block: rw-synthesis-artefact] {paper_audit.ROW_COUNT_BULLET}"
        table = "\\begin{tabular}{ll}A & B \\\\ \\midrule W1 & x \\\\ P & y \\\\ \\end{tabular}"
        result = paper_audit.audit(
            _prose([marked]), table, _clear([marked]),
            block_id="related-work.rw-synthesis-artefact",
            declared_blocks=("rw-synthesis-artefact",))
        self.assertEqual(result["verdicts"][0]["verdict"], "undecidable")
        self.assertIn("1 works", result["verdicts"][0]["deterministic"])


class ShippedMarkerTests(unittest.TestCase):
    """Every marker in a shipped contract names a block that contract
    declares, so no shipped rule is silently judged on no block."""

    def test_every_shipped_marker_names_a_declared_block(self) -> None:
        roots = [FORGE_ROOT / "sections", *sorted(FORGE_ROOT.glob("sections-*"))]
        for root in roots:
            for path in sorted(root.glob("*.md")):
                header, body = paper_contract.parse(path.read_bytes())
                declared = {block["id"] for block in header.blocks}
                bullets = paper_audit.extract_disqualifiers(body.decode("utf-8"),
                                                            source_name=path.name)
                for bullet in bullets:
                    with self.subTest(contract=f"{root.name}/{path.name}", bullet=bullet):
                        if bullet.startswith("[block"):
                            blocks = paper_audit.bullet_blocks(bullet)
                            self.assertIsNotNone(blocks, "the marker does not parse")
                            self.assertTrue(set(blocks) <= declared,
                                            f"undeclared block in {blocks}; declared {declared}")
                self.assertEqual(
                    paper_audit.unresolved_markers(bullets, tuple(declared)), [],
                    f"{root.name}/{path.name}")

    def _shipped_marked(self):
        roots = [FORGE_ROOT / "sections", *sorted(FORGE_ROOT.glob("sections-*"))]
        for root in roots:
            for path in sorted(root.glob("*.md")):
                _header, body = paper_contract.parse(path.read_bytes())
                for bullet in paper_audit.extract_disqualifiers(body.decode("utf-8")):
                    yield f"{root.name}/{path.name}", bullet, paper_audit.bullet_blocks(bullet)

    def test_a_marked_bullet_about_the_title_and_the_keywords_names_both(self) -> None:
        found = 0
        for where, bullet, blocks in self._shipped_marked():
            lowered = bullet.lower()
            if blocks and "title" in lowered and "keyword" in lowered:
                found += 1
                with self.subTest(contract=where, bullet=bullet):
                    self.assertTrue({"title", "keywords"} <= set(blocks), blocks)
        self.assertGreater(found, 0)

    def test_every_marked_synthesis_table_bullet_names_the_problem_blocks(self) -> None:
        # Contract 05 allows one artefact per problem block, placed at its close.
        found = 0
        for where, bullet, blocks in self._shipped_marked():
            if where == "sections/05-related-work.md" and blocks and (
                    "synthesis table" in bullet or "synthesis-table" in bullet):
                found += 1
                with self.subTest(bullet=bullet):
                    self.assertIn("rw-problem-blocks", blocks)
        self.assertGreaterEqual(found, 4)

    def test_the_unmotivated_contribution_rule_names_block_2(self) -> None:
        matches = [blocks for where, bullet, blocks in self._shipped_marked()
                   if where == "sections/06-introduction.md"
                   and "A contribution motivated by no problem in block 2." in bullet]
        self.assertEqual(len(matches), 1)
        self.assertIn("block-2", matches[0] or ())

    def test_the_spanish_copies_carry_every_marker_byte_identical(self) -> None:
        """The dashboard's Spanish copy of a contract translates the rule,
        never its marker: bullet N of the copy opens with exactly the marker
        bullet N of the contract opens with, or with none."""
        copies = FORGE_ROOT / "skills" / "_core" / "command_center" / "static" / "i18n" / "es" / "sections"
        marker = re.compile(r"^\[block: [^\]]*\] ")
        for path in sorted((FORGE_ROOT / "sections").glob("*.md")):
            english = paper_audit.extract_disqualifiers(path.read_text(encoding="utf-8"))
            spanish = paper_audit.extract_disqualifiers(
                (copies / path.name).read_text(encoding="utf-8").replace(
                    "## Descalificadores", "## Disqualifiers"))
            with self.subTest(contract=path.name):
                self.assertEqual(len(spanish), len(english))
                for source, copy in zip(english, spanish):
                    found = marker.match(source)
                    self.assertEqual(marker.match(copy) and marker.match(copy).group(0),
                                     found and found.group(0), copy)


if __name__ == "__main__":
    unittest.main()
