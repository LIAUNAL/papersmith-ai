"""A block that requires a declaration can carry the declared value.

`bm-funding`, `bm-code-availability` and `bm-ai-use-declaration` must print
tokens no `fact:` or `structural` sentence may carry: the grant code, the
funder, the repository URL and its commit, the framework release and the
tool names. `declaration:<id>` binds such a sentence to the value the
operator recorded with `declare --declaration <id>` (licensed by the block's
own `requires_declarations`), or to the packet's `ai_usage` record
(`declaration:ai-usage`, licensed for the blocks whose packet carries it).
`write` then checks the sentence against that value: it must carry at least
one of the value's components verbatim, and every numeral and every named
object it prints must come from the value.

Every test drives `paper_cli.py write` as a subprocess and asserts its JSON,
its exit code and the bytes of `main.tex`. The fixture paper lives under the
gitignored `.scratch/` because `--paper` must resolve inside the repository;
it is removed after each test.
"""
from __future__ import annotations

import json
import os
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
import paper_block  # noqa: E402
import paper_declarations  # noqa: E402
import paper_scaffold  # noqa: E402

GRANT_TITLE = (
    "Aprendizaje de máquina cuántico (Convocatoria Conjunta UCaldas–UNAL Manizales 2024)"
)
GRANT_CODE = "Hermes 62836; QUIPU 202010045932"
REPOSITORY_URL = "https://github.com/example/qml-eeg; commit 06faa71; checked 2026-11-13"
FRAMEWORK_VERSION = "0.76.1"

PROSE = (
    "# Back Matter\n\n"
    "The grant-title and grant-code — the funding project's registered title, funder, and code.\n\n"
    "The repository-url — the code repository and its commit.\n\n"
    "The AI-use declaration names the AI tools from the record.\n\n"
    "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n\n"
    "## Disqualifiers\n\n- A grant code reproduced from memory.\n"
)
DISQUALIFIER = "A grant code reproduced from memory."


def _requirement(value: str, quote: str) -> dict:
    return {"value": value, "source": {"file": "sections/10-back-matter.md", "quote": quote}}


HEADER = {
    "section": "back-matter",
    "position": 10,
    "mode": {"value": "transposition",
             "source": {"file": "sections/10-back-matter.md", "quote": "The repository-url"}},
    "blocks": [
        {"id": "bm-funding", "requires_facts": [],
         "requires_declarations": [
             _requirement("grant-title", "The grant-title and grant-code"),
             _requirement("grant-code", "The grant-title and grant-code"),
         ],
         "citations": "none"},
        {"id": "bm-code-availability", "requires_facts": [],
         "requires_declarations": [_requirement("repository-url", "The repository-url")],
         "citations": "none"},
        {"id": "bm-conflicts-of-interest", "requires_facts": [], "requires_declarations": [],
         "citations": "none"},
        {"id": "bm-ai-use-declaration", "requires_facts": [], "requires_declarations": [],
         "citations": "none"},
    ],
}


class _Paper(unittest.TestCase):
    """A scaffolded paper with the four back-matter blocks open and empty."""

    record = {"grant-title": GRANT_TITLE, "grant-code": GRANT_CODE,
              "repository-url": REPOSITORY_URL}

    def setUp(self) -> None:
        self.root = (FORGE_ROOT / ".scratch"
                     / f".declaration-binding-test-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper = self.root / "paper"
        paper_scaffold.scaffold(self.paper)
        sections = self.root / "sections"
        sections.mkdir()
        (sections / "10-back-matter.md").write_text(
            "---\n" + json.dumps(HEADER) + "\n---\n" + PROSE, encoding="utf-8")
        for block in HEADER["blocks"]:
            paper_block.open_block(self.paper, f"back-matter.{block['id']}", at_end=True)
        for declaration_id, value in self.record.items():
            paper_declarations.set_declaration(self.paper, declaration_id, value)
        (self.root / ".papersmith").mkdir()
        (self.root / ".papersmith" / "version").write_text(FRAMEWORK_VERSION + "\n", encoding="utf-8")
        (self.root / "audit.json").write_text(
            json.dumps({"verdicts": [{"bullet": DISQUALIFIER, "verdict": "clear"}]}), encoding="utf-8")
        # No harness session store outside this scratch home is ever read.
        self.home = Path(tempfile.mkdtemp(prefix="declaration-binding-home-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def write(self, block: str, entries: list[tuple[str, str]]) -> tuple[int, dict, bytes, bytes]:
        latex = " ".join(sentence for sentence, _binding in entries)
        draft = self.root / f"draft-{uuid.uuid4().hex[:6]}.json"
        draft.write_text(json.dumps({
            "latex": latex,
            "bindings": [{"sentence": s, "binding": b} for s, b in entries],
        }), encoding="utf-8")
        before = (self.paper / "main.tex").read_bytes()
        env = {key: value for key, value in os.environ.items()
               if key not in ("CLAUDE_CONFIG_DIR", "PI_CODING_AGENT_DIR", "XDG_DATA_HOME")}
        env["HOME"] = str(self.home)
        proc = subprocess.run(
            [sys.executable, str(CLI), "write", "--paper", str(self.paper),
             "--sections", str(self.root / "sections"), "--section", "back-matter",
             "--block", block, "--draft", str(draft), "--audit", str(self.root / "audit.json")],
            capture_output=True, text=True, cwd=FORGE_ROOT, env=env, timeout=120,
        )
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            payload = {"stdout": proc.stdout, "stderr": proc.stderr}
        return proc.returncode, payload, before, (self.paper / "main.tex").read_bytes()

    def assertRefused(self, outcome, code: str, *needles: str) -> None:
        returncode, payload, before, after = outcome
        self.assertEqual(payload.get("code"), code, payload)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(returncode, 2)
        for needle in needles:
            self.assertIn(needle, payload["detail"])
        self.assertEqual(after, before, "a refused write leaves main.tex byte-identical")

    def assertWritten(self, outcome, block: str, *sentences: str) -> None:
        returncode, payload, _before, after = outcome
        self.assertEqual(payload.get("status"), "written", payload)
        self.assertEqual(payload["block"], f"back-matter.{block}")
        self.assertEqual(returncode, 0)
        tex = after.decode("utf-8")
        begin = tex.index(f"%% paper-writing block back-matter.{block} begin")
        end = tex.index(f"%% paper-writing block back-matter.{block} end")
        for sentence in sentences:
            self.assertIn(sentence, tex[begin:end])


class ReportedReproductionTests(_Paper):
    """The report's reproduction: the grant code bound `fact:` or `structural`
    refuses -- both unchanged by the new kind."""

    SENTENCE = "This work was funded under grant Hermes 62836."

    def test_the_grant_code_bound_fact_still_refuses_fact_not_licensed(self) -> None:
        self.assertRefused(self.write("bm-funding", [(self.SENTENCE, "fact:grant-code")]),
                           "FACT_NOT_LICENSED", "grant-code")

    def test_the_grant_code_bound_structural_still_refuses_structural_carries_claim(self) -> None:
        self.assertRefused(self.write("bm-funding", [(self.SENTENCE, "structural")]),
                           "STRUCTURAL_CARRIES_CLAIM")

    def test_the_grant_code_bound_declaration_is_written(self) -> None:
        self.assertWritten(self.write("bm-funding", [(self.SENTENCE, "declaration:grant-code")]),
                           "bm-funding", self.SENTENCE)


class DeclarationBindingRuleTests(_Paper):
    def test_a_licensed_recorded_declaration_carried_verbatim_is_written(self) -> None:
        sentence = ("The code is available at \\url{https://github.com/example/qml-eeg}, "
                    "commit 06faa71, accessed on 2026-11-13.")
        self.assertWritten(
            self.write("bm-code-availability", [(sentence, "declaration:repository-url")]),
            "bm-code-availability", sentence)

    def test_a_recorded_iso_date_may_be_printed_with_its_month_name(self) -> None:
        sentence = ("The code is available at \\url{https://github.com/example/qml-eeg} "
                    "(commit 06faa71, accessed 13 November 2026).")
        self.assertWritten(
            self.write("bm-code-availability", [(sentence, "declaration:repository-url")]),
            "bm-code-availability", sentence)

    def test_an_id_outside_requires_declarations_refuses_declaration_not_licensed(self) -> None:
        sentence = "The code is available at \\url{https://github.com/example/qml-eeg}."
        self.assertRefused(self.write("bm-funding", [(sentence, "declaration:repository-url")]),
                           "DECLARATION_NOT_LICENSED", "repository-url", "requires_declarations")

    def test_an_unknown_declaration_id_refuses_declaration_not_licensed(self) -> None:
        sentence = "This work was funded under grant Hermes 62836."
        self.assertRefused(self.write("bm-funding", [(sentence, "declaration:grant-number")]),
                           "DECLARATION_NOT_LICENSED", "grant-number")

    def test_a_licensed_declaration_with_no_recorded_value_refuses_declaration_undeclared(self) -> None:
        paper_declarations.reopen(self.paper, "grant-code")
        sentence = "This work was funded under grant Hermes 62836."
        self.assertRefused(self.write("bm-funding", [(sentence, "declaration:grant-code")]),
                           "DECLARATION_UNDECLARED", "grant-code", "declare --declaration grant-code")

    def test_a_sentence_carrying_none_of_the_value_refuses_declaration_value_absent(self) -> None:
        sentence = "This work received institutional funding."
        self.assertRefused(self.write("bm-funding", [(sentence, "declaration:grant-code")]),
                           "DECLARATION_VALUE_ABSENT", "grant-code")

    def test_a_numeral_the_value_does_not_hold_refuses_declaration_carries_claim(self) -> None:
        sentence = "This work was funded under grants Hermes 62836 and Hermes 99999."
        self.assertRefused(self.write("bm-funding", [(sentence, "declaration:grant-code")]),
                           "DECLARATION_CARRIES_CLAIM", "99999")

    def test_a_named_object_the_value_does_not_hold_refuses_declaration_carries_claim(self) -> None:
        sentence = "This work was funded by Minciencias under grant Hermes 62836."
        self.assertRefused(self.write("bm-funding", [(sentence, "declaration:grant-code")]),
                           "DECLARATION_CARRIES_CLAIM", "Minciencias")

    def test_a_comparative_the_value_does_not_hold_refuses_declaration_carries_claim(self) -> None:
        sentence = "This work was funded under grant Hermes 62836, which made the method better than every prior approach."
        self.assertRefused(self.write("bm-funding", [(sentence, "declaration:grant-code")]),
                           "DECLARATION_CARRIES_CLAIM", "better")

    def test_one_sentence_may_carry_several_licensed_declarations(self) -> None:
        sentence = ("This work was funded by the project ``Aprendizaje de m\\'aquina cu\\'antico'' "
                    "(Convocatoria Conjunta UCaldas--UNAL Manizales 2024) under grants "
                    "Hermes 62836 and QUIPU 202010045932.")
        self.assertWritten(
            self.write("bm-funding", [(sentence, "declaration:grant-title,grant-code")]),
            "bm-funding", sentence)

    def test_a_bold_label_opening_the_declaration_is_not_a_named_object(self) -> None:
        sentence = "\\textbf{Funding.} This work was funded under grant QUIPU 202010045932."
        self.assertWritten(self.write("bm-funding", [(sentence, "declaration:grant-code")]),
                           "bm-funding", sentence)

    def test_each_of_several_declarations_must_be_carried(self) -> None:
        sentence = "This work was funded under grants Hermes 62836 and QUIPU 202010045932."
        self.assertRefused(
            self.write("bm-funding", [(sentence, "declaration:grant-title,grant-code")]),
            "DECLARATION_VALUE_ABSENT", "grant-title")


class AiUsageDeclarationTests(_Paper):
    SENTENCE = ("During the preparation of this work the authors used AI agents orchestrated by "
                "the papersmith framework (version 0.76.1, "
                "\\url{https://github.com/LIAUNAL/papersmith-ai}).")

    def test_the_ai_use_declaration_carries_the_framework_release_from_the_record(self) -> None:
        self.assertWritten(
            self.write("bm-ai-use-declaration", [(self.SENTENCE, "declaration:ai-usage")]),
            "bm-ai-use-declaration", self.SENTENCE)

    def test_a_release_the_record_does_not_hold_refuses(self) -> None:
        sentence = self.SENTENCE.replace("0.76.1", "0.58.2")
        self.assertRefused(
            self.write("bm-ai-use-declaration", [(sentence, "declaration:ai-usage")]),
            "DECLARATION_CARRIES_CLAIM", "58")

    def test_the_ai_usage_record_is_not_licensed_outside_its_blocks(self) -> None:
        self.assertRefused(self.write("bm-funding", [(self.SENTENCE, "declaration:ai-usage")]),
                           "DECLARATION_NOT_LICENSED", "ai-usage")


class PriorBindingKindsTests(_Paper):
    """`structural` and `evidence:` behave exactly as before."""

    def test_a_structural_sentence_asserting_nothing_is_still_written(self) -> None:
        sentence = "The authors declare no conflict of interest."
        self.assertWritten(self.write("bm-conflicts-of-interest", [(sentence, "structural")]),
                           "bm-conflicts-of-interest", sentence)

    def test_an_unknown_evidence_id_still_refuses_evidence_id_unknown(self) -> None:
        sentence = "The authors declare no conflict of interest."
        self.assertRefused(self.write("bm-conflicts-of-interest", [(sentence, "evidence:E9")]),
                           "EVIDENCE_ID_UNKNOWN", "E9")


if __name__ == "__main__":
    unittest.main()
