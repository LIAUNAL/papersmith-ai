"""The idea brief (``skills/_core/idea/brief.py``): ``.papersmith/idea_brief.json``,
schema 1, one step recorded at a time, atomic writes, refusals with a code.
The experience and interests steps are also driven through ``idea_cli``."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from skills._core.idea import brief, idea_cli

SCHEMA_KEYS = {"schema", "updated_at", "bank", "profile", "experience", "interests", "topics", "chosen", "draft",
               "history"}


def cli(*argv: str) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = idea_cli.main(list(argv))
    return code, json.loads(out.getvalue())


class BriefTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / ".papersmith").mkdir()

    def test_an_absent_brief_loads_empty_with_every_schema_key(self) -> None:
        loaded = brief.load(self.root)
        self.assertEqual(set(loaded), SCHEMA_KEYS)
        self.assertEqual(loaded["schema"], 1)
        self.assertEqual(loaded["bank"]["choice"], None)
        self.assertEqual(loaded["draft"], {"text": "", "source_topics": [], "approved": False, "approved_at": None,
                                           "gate": {"ok": False, "score": None, "missing": []}})
        self.assertFalse(brief.path(self.root).exists(), "loading never writes")

    def test_record_merges_a_step_and_appends_history(self) -> None:
        brief.record(self.root, "experience", {"level": "Early career", "methods": "GNN, transformers, GNN"})
        result = brief.record(self.root, "experience", {"time": "6 months"})
        self.assertEqual(result["experience"], {"level": "early-career", "methods": ["GNN", "transformers"],
                                                "resources": [], "time": "6 months"})
        self.assertEqual([event["step"] for event in result["history"]], ["experience", "experience"])
        on_disk = json.loads((self.root / ".papersmith" / "idea_brief.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk, result)
        self.assertEqual([p.name for p in (self.root / ".papersmith").iterdir()], ["idea_brief.json"],
                         "the atomic write leaves no temporary file")

    def test_a_replaced_step_drops_the_previous_fields(self) -> None:
        brief.record(self.root, "profile", {"orcid": "0000-0002-1825-0097", "source": "openalex"})
        result = brief.record(self.root, "profile", {"source": "none", "reason": "offline"})
        self.assertIsNone(result["profile"]["orcid"])
        self.assertEqual(result["profile"]["reason"], "offline")

    def test_an_unknown_level_or_step_is_refused_with_its_code(self) -> None:
        with self.assertRaises(brief.IdeaError) as ctx:
            brief.record(self.root, "experience", {"level": "guru"})
        self.assertEqual(ctx.exception.code, "LEVEL_UNKNOWN")
        with self.assertRaises(brief.IdeaError) as ctx:
            brief.record(self.root, "mood", {})
        self.assertEqual(ctx.exception.code, "STEP_UNKNOWN")
        self.assertFalse(brief.path(self.root).exists(), "a refusal writes nothing")

    def test_a_corrupt_brief_refuses_instead_of_being_overwritten(self) -> None:
        target = brief.path(self.root)
        target.write_text("{not json", encoding="utf-8")
        with self.assertRaises(brief.IdeaError) as ctx:
            brief.record(self.root, "interests", {"keywords": "eeg"})
        self.assertEqual(ctx.exception.code, "BRIEF_UNREADABLE")
        self.assertEqual(target.read_text(encoding="utf-8"), "{not json")

    def test_experience_and_interests_verbs_record_their_steps(self) -> None:
        code, body = cli("experience", str(self.root), "--level", "student", "--methods", "EEG, SVM",
                         "--resources", "a public EEG dataset", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(body["experience"]["methods"], ["EEG", "SVM"])
        code, body = cli("interests", "--root", str(self.root), "--keywords", "eeg; domain shift",
                         "--domain", "clinical neurology", "--admired", "10.1000/x", "--json")
        self.assertEqual((code, body["ok"]), (0, True))
        self.assertEqual(body["interests"], {"keywords": ["eeg", "domain shift"], "domain": "clinical neurology",
                                             "admired_paper": "10.1000/x"})
        self.assertEqual(brief.load(self.root)["experience"]["level"], "student")

    def test_a_verb_outside_a_workspace_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            code, body = cli("show", other, "--json")
        self.assertEqual(code, 1)
        self.assertEqual(body["error"], "NOT_A_WORKSPACE")


if __name__ == "__main__":
    unittest.main()
