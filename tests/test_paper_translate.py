"""`paper_cli.py translate ...`: the Spanish translation of the finished English paper.

Spec: odd/tasks/manuscript-translation-es.md, T2 (S2, S3, S5, S6) and its
"Contract shared by the CLI and the dashboard". Every verb runs through the
real front door as a subprocess, on a scratch workspace under the
already-gitignored `.scratch/` (`--paper` must resolve inside the repository
root), built from the four-block fixture in `tests/fixtures/paper_translate/`.
Each refusal also proves it wrote nothing, and no verb ever changes
`paper/main.tex`.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
CLI = SCRIPTS / "paper_cli.py"
FIXTURES = FORGE_ROOT / "tests" / "fixtures" / "paper_translate"
BLOCKS = ("intro", "methods", "eq", "results")
PROSE_BLOCKS = ("intro", "methods", "results")

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
import paper_block  # noqa: E402
import paper_cli  # noqa: E402
import paper_language  # noqa: E402

_COUNTER = [0]

STATUS_KEYS = {"ok", "lang", "blocks", "counts", "built", "main_tex", "pdf", "audit"}
#: Additive to the contract: the fragments outside every block.
STATUS_FRAGMENT_KEYS = {"fragments", "fragment_counts"}
FRAGMENTS = json.loads((FIXTURES / "fragments.json").read_text(encoding="utf-8"))
#: (kind, English) of every fragment the fixture skeleton holds, in id order per kind.
FRAGMENT_ORDER = (("title", "Spectral Graph Decoding of EEG"), ("section", "Introduction"),
                  ("section", "Methods"), ("subsection", "Setup"), ("subsection", "Experimental setup"),
                  ("section", "Results"), ("caption", "Accuracy over 3 folds (\\%)."))
AUDIT_KEYS = {"ok", "lang", "generated_at", "notice", "document", "blocks", "cross_block_redundancy", "fidelity"}
ENVELOPE = {"status", "command"}


def block_bytes(block_id: str, body: str) -> str:
    if body and not body.endswith("\n"):
        body += "\n"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (f"%% paper-writing block {block_id} begin sha256={digest}\n{body}"
            f"%% paper-writing block {block_id} end")


def tree_hash(root: Path) -> dict:
    if not root.exists():
        return {}
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class TranslateCase(unittest.TestCase):

    def setUp(self) -> None:
        _COUNTER[0] += 1
        self.root = FORGE_ROOT / ".scratch" / f".paper-translate-test-{os.getpid()}-{_COUNTER[0]}"
        shutil.rmtree(self.root, ignore_errors=True)
        self.paper = self.root / "paper"
        self.paper.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.bodies = {name: (FIXTURES / "en" / f"{name}.tex").read_text(encoding="utf-8") for name in BLOCKS}
        self.write_main()

    # --- helpers -----------------------------------------------------------

    def write_main(self, *, skeleton: str | None = None) -> None:
        text = skeleton if skeleton is not None else (FIXTURES / "skeleton.tex").read_text(encoding="utf-8")
        for name, body in self.bodies.items():
            text = text.replace("{{" + name + "}}", block_bytes(name, body))
        (self.paper / "main.tex").write_text(text, encoding="utf-8")

    def spanish(self, name: str, text: str | None = None) -> Path:
        path = self.root / f"{name}.es.tex"
        path.write_text(text if text is not None else (FIXTURES / "es" / f"{name}.tex").read_text(encoding="utf-8"),
                        encoding="utf-8")
        return path

    def run_cli(self, verb: str, *args: str, lang: str = "es") -> tuple[int, dict]:
        completed = subprocess.run(
            [sys.executable, str(CLI), "translate", verb, "--lang", lang, "--paper", str(self.paper), *args],
            cwd=FORGE_ROOT, capture_output=True, text=True, timeout=60)
        return completed.returncode, json.loads(completed.stdout)

    def ok(self, verb: str, *args: str) -> dict:
        code, out = self.run_cli(verb, *args)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["ok"], out)
        return out

    def refused(self, verb: str, code_name: str, *args: str, lang: str = "es") -> dict:
        before = tree_hash(self.paper)
        code, out = self.run_cli(verb, *args, lang=lang)
        self.assertEqual(code, 2, out)
        self.assertEqual(out["code"], code_name, out)
        self.assertEqual((out["ok"], out["error"]), (False, code_name), out)
        self.assertTrue(out["message"])
        self.assertEqual(tree_hash(self.paper), before, "a refusal wrote to disk")
        return out

    def store(self, name: str, text: str | None = None) -> dict:
        return self.ok("store", "--block", name, "--file", str(self.spanish(name, text)))

    def store_fragment(self, fragment_id: str, text: str) -> dict:
        path = self.root / f"{fragment_id}.es.txt"
        path.write_text(text, encoding="utf-8")
        return self.ok("store", "--fragment", fragment_id, "--file", str(path))

    def fragments(self) -> dict:
        """{English text: fragment id} as `plan` lists them."""
        return {f["english"]: f["id"] for f in self.ok("plan")["fragments"]}

    def store_fragments(self) -> None:
        for english, fragment_id in self.fragments().items():
            self.store_fragment(fragment_id, FRAGMENTS[english])

    def store_all(self) -> None:
        self.ok("plan")
        for name in PROSE_BLOCKS:
            self.store(name)
        self.store_fragments()

    def translation(self) -> dict:
        return json.loads((self.paper / "translations" / "es" / "translation.json").read_text(encoding="utf-8"))

    def main_sha(self) -> str:
        return hashlib.sha256((self.paper / "main.tex").read_bytes()).hexdigest()


class PlanTests(TranslateCase):

    def test_plan_writes_the_state_and_lists_every_block(self) -> None:
        out = self.ok("plan")
        self.assertEqual([b["id"] for b in out["blocks"]], list(BLOCKS))
        states = {b["id"]: b["state"] for b in out["blocks"]}
        # A block with no prose (an equation) has nothing to translate: it is carried over.
        self.assertEqual(states, {"intro": "missing", "methods": "missing", "eq": "current", "results": "missing"})
        self.assertTrue(all(b["source"] == "paper/main.tex" and b["excerpt"] for b in out["blocks"]))
        record = self.translation()
        self.assertEqual((record["schema"], record["language"]), (1, "es"))
        self.assertEqual(record["source_main_sha256"], self.main_sha())
        self.assertEqual(set(record["blocks"]), set(BLOCKS))
        self.assertIn("EEG", record["glossary"])
        self.assertIn("GraphNet", record["glossary"])
        self.assertTrue((self.paper / "translations" / "es" / "blocks" / "eq.tex").is_file())

    def test_plan_inventories_every_fragment_outside_the_blocks(self) -> None:
        out = self.ok("plan")
        listed = [(f["kind"], f["english"]) for f in out["fragments"]]
        self.assertEqual(sorted(listed), sorted(FRAGMENT_ORDER))
        record = self.translation()["fragments"]
        counters: dict = {}
        for kind, english in FRAGMENT_ORDER:
            counters[kind] = counters.get(kind, 0) + 1
            sha = hashlib.sha256(english.encode("utf-8")).hexdigest()
            fragment_id = f"{kind}-{counters[kind]}-{sha[:8]}"
            self.assertIn(fragment_id, record)
            entry = record[fragment_id]
            self.assertEqual((entry["kind"], entry["english"], entry["source_sha"], entry["state"]),
                             (kind, english, sha, "missing"))
        self.assertTrue(all(f["state"] == "missing" for f in out["fragments"]))

    def test_plan_keeps_terms_the_user_adds(self) -> None:
        self.ok("plan", "--term", "spectral graph model")
        self.ok("plan")
        self.assertIn("spectral graph model", self.translation()["glossary"])

    def test_plan_never_changes_main_tex(self) -> None:
        before = self.main_sha()
        self.ok("plan")
        self.assertEqual(self.main_sha(), before)

    def test_plan_refuses_a_language_other_than_spanish(self) -> None:
        self.refused("plan", "TRANSLATION_LANGUAGE_UNSUPPORTED", lang="fr")

    def test_plan_refuses_without_main_tex(self) -> None:
        (self.paper / "main.tex").unlink()
        self.refused("plan", "PAPER_ABSENT")

    def test_plan_refuses_a_paper_with_no_block(self) -> None:
        (self.paper / "main.tex").write_text("\\documentclass{article}\n\\begin{document}\nHi.\n\\end{document}\n",
                                             encoding="utf-8")
        self.refused("plan", "TRANSLATION_NO_BLOCKS")

    def test_plan_refuses_placeholder_text_in_the_english(self) -> None:
        self.bodies["results"] = "The model reaches TODO accuracy.\n"
        self.write_main()
        out = self.refused("plan", "TRANSLATION_SOURCE_PLACEHOLDER")
        self.assertIn("TODO", out["message"])

    def test_plan_refuses_an_empty_english_block(self) -> None:
        self.bodies["results"] = ""
        self.write_main()
        out = self.refused("plan", "TRANSLATION_SOURCE_INCOMPLETE")
        self.assertIn("results", out["message"])


class StoreTests(TranslateCase):

    def setUp(self) -> None:
        super().setUp()
        self.ok("plan")

    def test_store_writes_the_block_and_records_its_source_digest(self) -> None:
        out = self.store("intro")
        self.assertEqual((out["id"], out["state"]), ("intro", "current"))
        written = (self.paper / "translations" / "es" / "blocks" / "intro.tex").read_text(encoding="utf-8")
        self.assertEqual(written, (FIXTURES / "es" / "intro.tex").read_text(encoding="utf-8"))
        record = self.translation()["blocks"]["intro"]
        english = paper_block.parse((self.paper / "main.tex").read_bytes()).pairs["intro"][0]["digest"]
        self.assertEqual((record["source_digest"], record["state"]), (english, "current"))
        self.assertEqual(set(record["audit"]), {"index", "style_score", "flow_score", "redundancy_score",
                                                "verdict", "findings"})

    def test_store_refuses_before_plan(self) -> None:
        shutil.rmtree(self.paper / "translations")
        self.refused("store", "TRANSLATION_NOT_PLANNED", "--block", "intro", "--file", str(self.spanish("intro")))

    def test_store_refuses_an_unknown_block(self) -> None:
        self.refused("store", "BLOCK_ABSENT", "--block", "nope", "--file", str(self.spanish("intro")))

    def test_store_refuses_a_missing_file(self) -> None:
        self.refused("store", "TARGET_UNREADABLE", "--block", "intro", "--file", str(self.root / "absent.tex"))

    def test_store_refuses_empty_text(self) -> None:
        self.refused("store", "TRANSLATION_EMPTY", "--block", "intro", "--file", str(self.spanish("intro", "  \n")))

    def test_store_refuses_placeholder_text(self) -> None:
        text = (FIXTURES / "es" / "results.tex").read_text(encoding="utf-8").replace("como muestra", "TBD como muestra")
        self.refused("store", "TRANSLATION_PLACEHOLDER_TEXT", "--block", "results",
                     "--file", str(self.spanish("results", text)))

    def test_store_refuses_text_that_is_not_spanish(self) -> None:
        self.refused("store", "TRANSLATION_NOT_SPANISH", "--block", "intro",
                     "--file", str(self.spanish("intro", self.bodies["intro"])))

    def test_store_refuses_a_marker_line(self) -> None:
        text = (FIXTURES / "es" / "methods.tex").read_text(encoding="utf-8") + "%% paper-writing block x end\n"
        self.refused("store", "CONTENT_CARRIES_MARKER", "--block", "methods", "--file", str(self.spanish("methods", text)))

    def test_store_refuses_every_fidelity_difference_and_lists_them(self) -> None:
        text = ((FIXTURES / "es" / "methods.tex").read_text(encoding="utf-8")
                .replace("64 canales", "65 canales").replace("\\citep{lee2021}", ""))
        out = self.refused("store", "TRANSLATION_FIDELITY", "--block", "methods",
                           "--file", str(self.spanish("methods", text)))
        self.assertIn("lee2021", out["message"])
        self.assertIn("65", out["message"])

    def test_store_writes_a_fragment(self) -> None:
        fragment_id = self.fragments()["Introduction"]
        out = self.store_fragment(fragment_id, "Introducción\n")
        self.assertEqual((out["id"], out["state"]), (fragment_id, "current"))
        entry = self.translation()["fragments"][fragment_id]
        self.assertEqual((entry["spanish"], entry["state"]), ("Introducción", "current"))
        states = {f["id"]: f["state"] for f in self.ok("status")["fragments"]}
        self.assertEqual(states[fragment_id], "current")

    def store_fragment_refused(self, fragment_id: str, text: str, code_name: str) -> dict:
        path = self.root / "fragment.es.txt"
        path.write_text(text, encoding="utf-8")
        return self.refused("store", code_name, "--fragment", fragment_id, "--file", str(path))

    def test_store_refuses_an_unknown_fragment(self) -> None:
        self.store_fragment_refused("section-9-00000000", "Introducción", "TRANSLATION_FRAGMENT_UNKNOWN")

    def test_store_refuses_a_fragment_left_in_english(self) -> None:
        self.store_fragment_refused(self.fragments()["Introduction"], "Introduction", "TRANSLATION_NOT_SPANISH")

    def test_store_refuses_an_empty_or_placeholder_fragment(self) -> None:
        fragment_id = self.fragments()["Methods"]
        self.store_fragment_refused(fragment_id, " \n", "TRANSLATION_EMPTY")
        self.store_fragment_refused(fragment_id, "Métodos TODO", "TRANSLATION_PLACEHOLDER_TEXT")

    def test_store_refuses_a_fragment_that_changes_a_fact(self) -> None:
        out = self.store_fragment_refused(self.fragments()["Accuracy over 3 folds (\\%)."],
                                          "Exactitud en 4 particiones (\\%).", "TRANSLATION_FIDELITY")
        self.assertIn("4", out["message"])

    def test_store_takes_exactly_one_of_block_and_fragment(self) -> None:
        path = self.spanish("intro")
        for extra in ((), ("--block", "intro", "--fragment", self.fragments()["Methods"])):
            completed = subprocess.run(
                [sys.executable, str(CLI), "translate", "store", "--lang", "es", "--paper", str(self.paper),
                 "--file", str(path), *extra], cwd=FORGE_ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("one of the arguments --block --fragment is required"
                          if not extra else "not allowed with argument", completed.stderr)

    def test_a_changed_english_fragment_makes_its_translation_stale(self) -> None:
        fragment_id = self.fragments()["Results"]
        self.store_fragment(fragment_id, "Resultados")
        skeleton = (FIXTURES / "skeleton.tex").read_text(encoding="utf-8").replace(
            "\\section{Results}", "\\section{Results and Discussion}")
        self.write_main(skeleton=skeleton)
        status = self.ok("status")
        stale = [f for f in status["fragments"] if f["state"] == "stale"]
        self.assertEqual([f["kind"] for f in stale], ["section"])
        self.assertTrue(stale[0]["id"].startswith("section-3-"))
        self.assertNotEqual(stale[0]["id"], fragment_id)
        self.assertEqual(status["fragment_counts"]["stale"], 1)

    def test_a_changed_english_block_makes_its_translation_stale(self) -> None:
        self.store("intro")
        self.bodies["intro"] = self.bodies["intro"].replace("3 experiments", "three experiments")
        self.write_main()
        status = self.ok("status")
        self.assertEqual({b["id"]: b["state"] for b in status["blocks"]}["intro"], "stale")


class BuildTests(TranslateCase):

    def test_build_refuses_while_a_block_is_missing_or_stale(self) -> None:
        self.ok("plan")
        self.store("intro")
        out = self.refused("build", "TRANSLATION_INCOMPLETE")
        self.assertIn("methods", out["message"])
        self.store("methods")
        self.store("results")
        self.bodies["intro"] = self.bodies["intro"].replace("3 experiments", "three experiments")
        self.write_main()
        out = self.refused("build", "TRANSLATION_INCOMPLETE")
        self.assertIn("intro", out["message"])

    def test_build_refuses_while_a_fragment_is_missing_or_stale(self) -> None:
        self.ok("plan")
        for name in PROSE_BLOCKS:
            self.store(name)
        out = self.refused("build", "TRANSLATION_INCOMPLETE")
        self.assertIn("section-1-", out["message"])
        self.store_fragments()
        self.ok("build")
        skeleton = (FIXTURES / "skeleton.tex").read_text(encoding="utf-8").replace(
            "\\section{Results}", "\\section{Results and Discussion}")
        self.write_main(skeleton=skeleton)
        out = self.refused("build", "TRANSLATION_INCOMPLETE")
        self.assertIn("section-3-", out["message"])
        self.assertIn("stale", out["message"])

    def test_build_refuses_before_plan(self) -> None:
        self.refused("build", "TRANSLATION_NOT_PLANNED")

    def test_build_writes_the_spanish_main_and_never_touches_the_english(self) -> None:
        self.store_all()
        before = self.main_sha()
        out = self.ok("build")
        self.assertEqual(self.main_sha(), before)
        self.assertEqual(out["main_tex"], "paper/translations/es/main.tex")
        built = (self.paper / "translations" / "es" / "main.tex").read_text(encoding="utf-8")
        self.assertNotIn("%% paper-writing block", built)
        self.assertEqual(paper_block.parse(built.encode("utf-8")).pairs, {})
        english_digest = paper_block.parse((self.paper / "main.tex").read_bytes()).pairs["intro"][0]["digest"]
        self.assertIn(f"%% paper-writing translation intro source {english_digest} begin", built)
        self.assertIn("%% paper-writing translation intro end", built)
        self.assertIn("La decodificación de electroencefalografía", built)
        self.assertNotIn("Electroencephalography (EEG) decoding", built)
        self.assertEqual(paper_language.declared_language(built), "spanish")
        self.assertIn("y = W x + b", built)
        self.assertIn("\\title{Decodificación espectral de grafos para EEG}", built)
        self.assertIn("\\section{Introducción}", built)
        self.assertIn("\\subsection[Configuración]{Configuración experimental}", built)
        self.assertIn("\\caption{Exactitud en 3 particiones (\\%).}", built)
        self.assertNotIn("\\section{Introduction}", built)
        self.assertNotIn("untranslated_headings", out)
        # A commented heading is not prose and stays as written.
        self.assertIn("% \\section{A commented heading is not a fragment}", built)

    def test_build_declares_spanish_when_the_preamble_has_no_babel(self) -> None:
        skeleton = (FIXTURES / "skeleton.tex").read_text(encoding="utf-8").replace("\\usepackage[english]{babel}\n", "")
        self.write_main(skeleton=skeleton)
        self.store_all()
        self.ok("build")
        built = (self.paper / "translations" / "es" / "main.tex").read_text(encoding="utf-8")
        self.assertEqual(paper_language.declared_language(built), "spanish")


class AuditAndStatusTests(TranslateCase):

    def test_audit_refuses_with_nothing_stored(self) -> None:
        self.ok("plan")
        shutil.rmtree(self.paper / "translations" / "es" / "blocks")
        self.refused("audit", "TRANSLATION_NOTHING_STORED")

    def test_audit_has_exactly_the_contract_shape_and_writes_it(self) -> None:
        self.store_all()
        out = self.ok("audit")
        self.assertEqual(set(out), AUDIT_KEYS | ENVELOPE)
        saved = json.loads((self.paper / "translations" / "es" / "audit.json").read_text(encoding="utf-8"))
        self.assertEqual(set(saved), AUDIT_KEYS)
        self.assertEqual(saved, {k: v for k, v in out.items() if k not in ENVELOPE})
        self.assertEqual(set(out["document"]), {"index", "style_score", "flow_score", "redundancy_score", "verdict"})
        self.assertEqual({b["id"] for b in out["blocks"]}, set(BLOCKS))
        for block in out["blocks"]:
            self.assertEqual(set(block), {"id", "index", "style_score", "flow_score", "redundancy_score",
                                          "verdict", "findings"})
        self.assertEqual({f["id"]: f["ok"] for f in out["fidelity"]}, {name: True for name in BLOCKS})
        self.assertTrue(all(set(f) == {"id", "ok", "differences"} for f in out["fidelity"]))
        self.assertIn("not an authorship", out["notice"])

    def test_status_has_exactly_the_contract_shape_through_the_whole_flow(self) -> None:
        out = self.ok("status")
        self.assertEqual(set(out), STATUS_KEYS | STATUS_FRAGMENT_KEYS | ENVELOPE)
        self.assertEqual(out["counts"], {"total": 4, "current": 0, "stale": 0, "missing": 4})
        self.assertEqual(out["fragment_counts"], {"total": 7, "current": 0, "stale": 0, "missing": 7})
        self.assertTrue(all(set(f) == {"id", "kind", "state"} for f in out["fragments"]))
        self.assertEqual((out["built"], out["main_tex"], out["pdf"], out["audit"]), (False, None, None, None))
        self.store_all()
        self.ok("build")
        self.ok("audit")
        out = self.ok("status")
        self.assertEqual(out["counts"], {"total": 4, "current": 4, "stale": 0, "missing": 0})
        self.assertEqual(out["fragment_counts"], {"total": 7, "current": 7, "stale": 0, "missing": 0})
        self.assertTrue(all(set(b) == {"id", "state", "source_digest", "stored_at"} for b in out["blocks"]))
        self.assertEqual((out["built"], out["main_tex"], out["pdf"]), (True, "paper/translations/es/main.tex", None))
        self.assertEqual(set(out["audit"]), {"generated_at", "index", "verdict"})
        (self.paper / "translations" / "es" / "main.pdf").write_bytes(b"%PDF-1.4\n")
        self.assertEqual(self.ok("status")["pdf"], "paper/translations/es/main.pdf")

    def test_every_new_refusal_is_classified(self) -> None:
        for code in ("TRANSLATION_LANGUAGE_UNSUPPORTED", "TRANSLATION_NO_BLOCKS", "TRANSLATION_SOURCE_PLACEHOLDER",
                     "TRANSLATION_SOURCE_INCOMPLETE", "TRANSLATION_NOT_PLANNED", "TRANSLATION_EMPTY",
                     "TRANSLATION_PLACEHOLDER_TEXT", "TRANSLATION_NOT_SPANISH", "TRANSLATION_FIDELITY",
                     "TRANSLATION_INCOMPLETE", "TRANSLATION_NOTHING_STORED", "TRANSLATION_FRAGMENT_UNKNOWN"):
            self.assertIn(code, paper_cli.REFUSAL_CLASSIFICATION)


if __name__ == "__main__":
    unittest.main()
