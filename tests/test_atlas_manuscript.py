"""The manuscript layer of the SOTA atlas: which pool systems the paper cites.

``skills/_core/command_center/atlas_manuscript.py`` derives
``sota-pool/atlas.manuscript.json`` from ``sota-pool/atlas.json``,
``sota-pool/candidates.json``, ``paper/main.tex``, ``paper/refs.bib`` and the
per-block evidence stores, and never modifies ``atlas.json``. These tests run
on a copy of ``tests/fixtures/atlas_manuscript/`` and go through the module's
public functions, its command line, ``smith atlas cited`` and the dashboard
route.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from papersmith.cli import build_parser
from skills._core.command_center import atlas_manuscript, server

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "atlas_manuscript"
COMMAND_CENTER = REPO / "skills" / "_core" / "command_center"


def _routes(app) -> dict:
    return {(r.path, tuple(sorted(getattr(r, "methods", None) or ()))): r.endpoint
            for r in app.routes if hasattr(r, "path") and hasattr(r, "endpoint")}


def _route(app, path: str, method: str):
    for (route_path, methods), endpoint in _routes(app).items():
        if route_path == path and method in methods:
            return endpoint
    raise AssertionError(f"no {method} {path} route")


class _Workspace(unittest.TestCase):
    def workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        shutil.copytree(FIXTURE, root)
        return root


class CitedSystemsTests(_Workspace):
    def test_each_system_is_marked_cited_or_not_with_its_blocks_and_claims(self) -> None:
        root = self.workspace()
        joined = atlas_manuscript.cited_systems(root)
        by_id = {s["id"]: s for s in joined["systems"]}
        self.assertEqual(list(by_id), ["sys-a", "sys-b", "sys-c"])
        self.assertTrue(by_id["sys-a"]["cited"])
        self.assertEqual(by_id["sys-a"]["cite_keys"], ["alpha2024"])
        self.assertEqual(by_id["sys-a"]["blocks"], ["intro", "methods"])
        self.assertEqual(by_id["sys-a"]["claims"], [
            {"block": "intro", "cite_key": "alpha2024", "claim": "Attention pooling is common.",
             "verdict": "insufficient"},
            {"block": "methods", "cite_key": "alpha2024", "claim": "Attention weights each instance.",
             "verdict": "holds"},
        ])
        self.assertEqual(by_id["sys-b"]["cite_keys"], ["beta2023"])
        self.assertEqual(by_id["sys-b"]["blocks"], ["intro"])
        # delta2021 has evidence against sys-c, but the text never cites it.
        self.assertFalse(by_id["sys-c"]["cited"])
        self.assertEqual((by_id["sys-c"]["cite_keys"], by_id["sys-c"]["blocks"],
                          by_id["sys-c"]["claims"]), ([], [], []))
        self.assertEqual(joined["cite_source"], "main.tex")

    def test_a_cited_paper_absent_from_the_pool_is_an_extra_system(self) -> None:
        root = self.workspace()
        extra = atlas_manuscript.cited_systems(root)["extra_systems"]
        self.assertEqual(extra, [{
            "cite_key": "gamma2022", "identifier": "10.9999/extra", "resolver": "crossref",
            "title": "A Study Outside the Pool", "blocks": ["intro"],
            "claims": [{"block": "intro", "cite_key": "gamma2022", "claim": "A newer study agrees.",
                        "verdict": "holds"}],
        }])

    def test_without_main_tex_the_bibliography_names_the_cited_keys(self) -> None:
        root = self.workspace()
        (root / "paper" / "main.tex").unlink()
        joined = atlas_manuscript.cited_systems(root)
        self.assertEqual(joined["cite_source"], "refs.bib")
        self.assertEqual([s["id"] for s in joined["systems"] if s["cited"]], ["sys-a", "sys-b"])


_BIB_ONLY_REFS = """@article{alpha2024,
  title={Attention Pooling for Sets},
  eprint={2401.00001},
  archivePrefix={arXiv},
  year={2024}
}

@article{beta2023,
  title={Graph Priors},
  journal={Neural Journal},
  doi={10.1000/B},
  year={2023}
}

@article{kernels2021,
  title={Kernel Baselines},
  url={https://doi.org/10.1000/c},
  year={2021}
}

@article{reupload2019,
  title={Data re-uploading},
  journal={arXiv preprint arXiv:1905.13311},
  year={2019}
}

@article{amini2024adhdeepnet,
  title={{ADHDeepNet} From Raw {EEG} to Diagnosis: Improving {ADHD} Diagnosis},
  author={Amini, Ali},
  journal={Cognitive Computation},
  year={2024}
}

@article{schuld2021effect,
  title={Effect of data encoding on the expressive power},
  year={2021}
}

@article{twin2020,
  title={Twin Title},
  year={2020}
}

@article{lost2020,
  title={Nothing In The Pool},
  year={2020}
}

@article{versioned2024,
  title={ADHDeepNet From Raw EEG to Diagnosis: Improving ADHD Diagnosis},
  doi={10.5555/elsewhere},
  year={2024}
}
"""

_BIB_ONLY_TEX = (
    "\\documentclass{article}\n\\begin{document}\n"
    "\\cite{alpha2024,beta2023,kernels2021,reupload2019,amini2024adhdeepnet,"
    "schuld2021effect,twin2020,lost2020,versioned2024}\n\\end{document}\n")


def _planet(origin: str) -> dict:
    return {"id": "sun", "slot": "sun", "orbit": 0, "provenance": "stated", "label": "x",
            "detail": "d", "evidence": {"origin": origin, "quote": "q", "retrieved": "2026-01-02"}}


class BibliographyJoinTests(_Workspace):
    """A manuscript written without evidence records still joins its cite keys
    to atlas systems through the identifiers and titles of ``refs.bib``."""

    def bib_only_workspace(self) -> Path:
        root = self.workspace()
        shutil.rmtree(root / "paper" / ".paper-writing")
        (root / "paper" / "refs.bib").write_text(_BIB_ONLY_REFS, encoding="utf-8")
        (root / "paper" / "main.tex").write_text(_BIB_ONLY_TEX, encoding="utf-8")
        atlas = json.loads((root / "sota-pool" / "atlas.json").read_text("utf-8"))
        candidates = json.loads((root / "sota-pool" / "candidates.json").read_text("utf-8"))
        extra = [
            ("sys-d", "Re-uploading", "1905.13311", "arxiv", "Data re-uploading for a classifier"),
            ("sys-e", "adhdeepnet", "2509.08779", "arxiv",
             "ADHDeepNet From Raw EEG to Diagnosis: Improving ADHD Diagnosis"),
            ("sys-f", "Twin one", "10.2000/f", "crossref", "Twin Title"),
            ("sys-g", "Twin two", "10.2000/g", "crossref", "Twin title"),
            ("sys-h", "Encoding", "2008.08605", "arxiv",
             "The effect of data encoding on the expressive power"),
        ]
        for sid, title, identifier, resolver, paper_title in extra:
            atlas["systems"].append({"id": sid, "title": title, "planets": [_planet(identifier)]})
            candidates.append({"identifier": identifier, "resolver": resolver,
                               "title": paper_title, "abstract": "q"})
        (root / "sota-pool" / "atlas.json").write_text(json.dumps(atlas), encoding="utf-8")
        (root / "sota-pool" / "candidates.json").write_text(json.dumps(candidates),
                                                            encoding="utf-8")
        return root

    def test_bibliography_identifiers_join_cited_keys_without_evidence(self) -> None:
        joined = atlas_manuscript.cited_systems(self.bib_only_workspace())
        by_id = {s["id"]: s for s in joined["systems"]}
        expected = {
            "sys-a": [{"cite_key": "alpha2024", "via": "bib"}],
            "sys-b": [{"cite_key": "beta2023", "via": "bib"}],
            "sys-c": [{"cite_key": "kernels2021", "via": "bib"}],
            "sys-d": [{"cite_key": "reupload2019", "via": "bib"}],
            "sys-e": [{"cite_key": "amini2024adhdeepnet", "via": "title"}],
            "sys-f": [], "sys-g": [],
            # a leading article does not make two titles different
            "sys-h": [{"cite_key": "schuld2021effect", "via": "title"}],
        }
        self.assertEqual({sid: s["matches"] for sid, s in by_id.items()}, expected)
        for sid, matches in expected.items():
            self.assertEqual(by_id[sid]["cited"], bool(matches), sid)
            self.assertEqual(by_id[sid]["cite_keys"], [m["cite_key"] for m in matches], sid)
            self.assertEqual((by_id[sid]["blocks"], by_id[sid]["claims"]), ([], []), sid)

    def test_ambiguous_unknown_and_identified_elsewhere_keys_stay_extra(self) -> None:
        extra = atlas_manuscript.cited_systems(self.bib_only_workspace())["extra_systems"]
        self.assertEqual(
            [(e["cite_key"], e["identifier"], e["resolver"]) for e in extra],
            [("lost2020", None, None), ("twin2020", None, None),
             ("versioned2024", "10.5555/elsewhere", "crossref")])

    def test_evidence_identifiers_win_over_the_bibliography(self) -> None:
        joined = atlas_manuscript.cited_systems(self.workspace())
        by_id = {s["id"]: s for s in joined["systems"]}
        self.assertEqual(by_id["sys-a"]["matches"], [{"cite_key": "alpha2024", "via": "evidence"}])
        # beta2023 carries the DOI in both its evidence and its bib entry.
        self.assertEqual(by_id["sys-b"]["matches"], [{"cite_key": "beta2023", "via": "evidence"}])
        self.assertEqual(by_id["sys-c"]["matches"], [])

    def test_smith_atlas_cited_json_reports_the_bibliography_join(self) -> None:
        root = self.bib_only_workspace()
        CommandLineTests._with_kit(self, root)
        args = build_parser("smith").parse_args(["atlas", "cited", "--json", str(root)])
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = args.handler(args)
        self.assertEqual(code, 0, out.getvalue())
        summary = json.loads(out.getvalue())["summary"]
        self.assertEqual((summary["systems_total"], summary["cited_systems"],
                          summary["extra_cited"]), (8, 6, 3))


class OneLineBibliographyTests(_Workspace):
    def test_a_one_line_entry_reaches_the_atlas_join(self) -> None:
        root = self.workspace()
        systems = json.loads((root / "sota-pool" / "atlas.json").read_text(encoding="utf-8"))["systems"]
        pool = json.loads((root / "sota-pool" / "candidates.json").read_text(encoding="utf-8"))
        candidates = pool if isinstance(pool, list) else pool["candidates"]
        target = next(c for c in candidates if str(c.get("identifier", "")).startswith("10."))
        (root / "paper" / "main.tex").write_text("See \\cite{oneline2024}.\n", encoding="utf-8")
        (root / "paper" / "refs.bib").write_text(
            f"@article{{oneline2024, title={{Unrelated Words}}, doi={{{target['identifier']}}}, year={{2024}}}}\n",
            encoding="utf-8")
        for store in (root / "paper" / ".paper-writing" / "evidence").glob("*.jsonl"):
            store.unlink()

        joined = atlas_manuscript.cited_systems(root)

        self.assertTrue(systems)
        cited = [s for s in joined["systems"] if s["cited"]]
        self.assertEqual([s["cite_keys"] for s in cited], [["oneline2024"]])
        self.assertEqual(joined["extra_systems"], [])

    def test_bib_fields_keep_only_the_declared_fields(self) -> None:
        fields = atlas_manuscript._bib_fields(
            b"@string{jn = \"Neural Journal\"}\n"
            b"@article{a, title={A\n   Title}, journal=jn, abstract={Not kept}, year=2020}\n")
        self.assertEqual(fields, {"a": {"title": "A Title", "journal": "Neural Journal", "year": "2020"}})


class LayerTests(_Workspace):
    def test_build_writes_the_layer_and_leaves_atlas_json_byte_identical(self) -> None:
        root = self.workspace()
        atlas_json = root / "sota-pool" / "atlas.json"
        before = atlas_json.read_bytes()
        result = atlas_manuscript.write_layer(root)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["path"], "sota-pool/atlas.manuscript.json")
        self.assertEqual(atlas_json.read_bytes(), before)
        layer = json.loads((root / "sota-pool" / "atlas.manuscript.json").read_text("utf-8"))
        self.assertEqual(layer["schema"], atlas_manuscript.SCHEMA)
        self.assertEqual(layer["summary"], {
            "systems_total": 3, "cited_systems": 2, "uncited_systems": ["sys-c"],
            "extra_cited": 1, "cited_keys": 3,
        })
        self.assertEqual(result["summary"], layer["summary"])
        self.assertEqual(sorted(layer["generated_from"]),
                         ["atlas.json", "candidates.json", "evidence", "main.tex", "refs.bib"])
        self.assertTrue(all(isinstance(v, str) and len(v) == 64
                            for v in layer["generated_from"].values()))

    def test_a_rebuild_on_unchanged_inputs_is_byte_identical(self) -> None:
        root = self.workspace()
        atlas_manuscript.write_layer(root)
        first = (root / "sota-pool" / "atlas.manuscript.json").read_bytes()
        atlas_manuscript.write_layer(root)
        self.assertEqual((root / "sota-pool" / "atlas.manuscript.json").read_bytes(), first)

    def test_read_layer_reports_staleness_when_an_input_changes(self) -> None:
        root = self.workspace()
        self.assertEqual(atlas_manuscript.read_layer(root)["status"], "absent")
        atlas_manuscript.write_layer(root)
        fresh = atlas_manuscript.read_layer(root)
        self.assertEqual((fresh["status"], fresh["stale"]), ("ok", False))
        self.assertEqual(fresh["layer"]["summary"]["cited_systems"], 2)
        refs = root / "paper" / "refs.bib"
        refs.write_text(refs.read_text("utf-8") + "\n", encoding="utf-8")
        self.assertEqual(atlas_manuscript.read_layer(root)["stale"], True)

    def test_no_atlas_means_no_layer_is_written(self) -> None:
        root = self.workspace()
        (root / "sota-pool" / "atlas.json").unlink()
        result = atlas_manuscript.write_layer(root)
        self.assertEqual((result["ok"], result["status"]), (False, "absent"))
        self.assertFalse((root / "sota-pool" / "atlas.manuscript.json").exists())

    def test_refresh_turns_a_builder_error_into_a_warning(self) -> None:
        root = self.workspace()
        (root / "sota-pool" / "atlas.json").write_text("{not json", encoding="utf-8")
        result = atlas_manuscript.refresh(root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")
        self.assertIn("warning", result)
        self.assertFalse((root / "sota-pool" / "atlas.manuscript.json").exists())

    def test_refresh_is_silent_without_an_atlas(self) -> None:
        root = self.workspace()
        shutil.rmtree(root / "sota-pool")
        self.assertIsNone(atlas_manuscript.refresh(root))


class CommandLineTests(_Workspace):
    def test_module_entry_point_writes_and_reports_json(self) -> None:
        root = self.workspace()
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "skills._core.command_center.atlas_manuscript",
             "--root", str(root), "--json"],
            cwd=str(REPO), capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["ok"])
        self.assertTrue((root / "sota-pool" / "atlas.manuscript.json").is_file())

    def run_smith(self, *argv: str) -> tuple[int, str, str]:
        args = build_parser("smith").parse_args(list(argv))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = args.handler(args)
        return code, out.getvalue(), err.getvalue()

    def _with_kit(self, root: Path) -> None:
        center = root / "skills" / "_core" / "command_center"
        center.mkdir(parents=True)
        for name in ("__init__.py", "atlas_manuscript.py"):
            shutil.copy(COMMAND_CENTER / name, center / name)
        shutil.copytree(REPO / "skills" / "paper-writing" / "scripts",
                        root / "skills" / "paper-writing" / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "skills" / "_core" / "implementation",
                        root / "skills" / "_core" / "implementation",
                        ignore=shutil.ignore_patterns("__pycache__"))

    def test_smith_atlas_cited_writes_the_layer(self) -> None:
        root = self.workspace()
        self._with_kit(root)
        code, out, _err = self.run_smith("atlas", "cited", str(root))
        self.assertEqual(code, 0, out)
        self.assertIn("2/3 systems cited", out)
        self.assertTrue((root / "sota-pool" / "atlas.manuscript.json").is_file())

    def test_smith_atlas_cited_fails_closed_without_an_atlas(self) -> None:
        root = self.workspace()
        self._with_kit(root)
        (root / "sota-pool" / "atlas.json").unlink()
        code, _out, err = self.run_smith("atlas", "cited", "--json", str(root))
        self.assertEqual(code, 1)
        self.assertIn("atlas.json", err + _out)


class RouteTests(_Workspace):
    def test_get_api_atlas_manuscript_returns_the_layer(self) -> None:
        root = self.workspace()
        app = server.create_app(root, history_store=None)
        endpoint = _route(app, "/api/atlas/manuscript", "GET")
        absent = json.loads(bytes(endpoint().body))
        self.assertEqual(absent["status"], "absent")
        atlas_manuscript.write_layer(root)
        body = json.loads(bytes(endpoint().body))
        self.assertEqual((body["status"], body["stale"]), ("ok", False))
        self.assertEqual(body["layer"]["summary"]["uncited_systems"], ["sys-c"])


if __name__ == "__main__":
    unittest.main()
