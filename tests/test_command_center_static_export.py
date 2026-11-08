"""`smith ui --export-snapshot`: a read-only, static copy of the dashboard.

The snapshot is meant for a public GitHub Pages site, so these tests pin what
it must never carry (AI conversations, team accounts, credential status,
absolute paths) and that exporting writes nothing into the workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from papersmith.core import init as init_module
from papersmith.core import ui as ui_command
from skills._core.command_center import server, static_export

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "skills/_core/command_center/static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")


def _tree_digest(root: Path) -> dict[str, str]:
    digest = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            digest[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif path.is_dir():
            digest[str(path.relative_to(root)) + "/"] = "dir"
    return digest


def _seed_private_data(workspace: Path) -> None:
    """What a real workspace holds and a public snapshot must not."""
    papersmith = workspace / ".papersmith"
    (papersmith / "ai-history").mkdir(parents=True, exist_ok=True)
    (papersmith / "ai-history" / "session.md").write_text("private conversation", encoding="utf-8")
    (papersmith / "team.json").write_text(json.dumps({"members": [
        {"owner": "alice", "email": "alice@example.org", "kaggle_username": "alice-k"}]}),
        encoding="utf-8")
    (papersmith / "anotaciones_pdf.json").write_text(json.dumps(
        {"timestamp": "2026-01-01", "annotations": [{"text": "operator note"}], "applied": {}}),
        encoding="utf-8")


class SnapshotExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.holder = tempfile.TemporaryDirectory()
        base = Path(cls.holder.name).resolve()
        cls.workspace = base / "snapshot-ws"
        init_module.initialize(cls.workspace, run_npm=False, run_env=False)
        _seed_private_data(cls.workspace)
        cls.before = _tree_digest(cls.workspace)
        cls.out = base / "site"
        cls.report = static_export.export_snapshot(cls.workspace, cls.out)
        cls.after = _tree_digest(cls.workspace)
        cls.manifest = json.loads((cls.out / "snapshot" / "manifest.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.holder.cleanup()

    def entries(self) -> dict:
        return self.manifest["entries"]

    def test_the_manifest_holds_the_core_routes_in_both_languages(self) -> None:
        for route in ("/api/status", "/api/model", "/api/experiments", "/api/citations",
                      "/api/novelty/status", "/api/atlas/novelty/view", "/api/flow"):
            with self.subTest(route=route):
                self.assertIn(route, self.entries())
                self.assertIn(f"{route}?lang=es", self.entries())
        for key, entry in self.entries().items():
            with self.subTest(key=key):
                self.assertTrue((self.out / entry["file"]).is_file())
                self.assertTrue(entry["file"].startswith("snapshot/"))

    def test_the_spanish_answers_are_localized(self) -> None:
        en = json.loads((self.out / self.entries()["/api/status"]["file"]).read_text(encoding="utf-8"))
        es = json.loads((self.out / self.entries()["/api/status?lang=es"]["file"]).read_text(encoding="utf-8"))
        self.assertEqual(len(en["fases"]), len(es["fases"]))
        self.assertNotEqual(en["fases"], es["fases"])

    def test_the_request_key_drops_cache_busters_and_english(self) -> None:
        key = static_export.request_key
        self.assertEqual(key("/api/pdf", {"v": "doc", "t": "1"}), "/api/pdf")
        self.assertEqual(key("/api/pdf", {"venue": "a b", "lang": "en"}), "/api/pdf?venue=a%20b")
        self.assertEqual(key("/api/artifact", {"file": "sections/x.md"}),
                         "/api/artifact?path=sections%2Fx.md")
        self.assertEqual(key("/api/x", {"lang": "es", "fresh": "1", "b": "2"}), "/api/x?b=2&lang=es")

    def test_no_file_carries_the_workspace_or_home_path(self) -> None:
        needles = [str(self.workspace).encode(), str(Path.home()).encode()]
        for path in self.out.rglob("*"):
            if not path.is_file() or path.suffix in (".pdf", ".png", ".ico"):
                continue
            data = path.read_bytes()
            for needle in needles:
                with self.subTest(file=str(path.relative_to(self.out)), needle=needle):
                    self.assertNotIn(needle, data)

    def test_no_conversation_team_or_credential_data(self) -> None:
        forbidden = [b"private conversation", b"alice@example.org", b"alice-k", b"operator note",
                     b"token_path", b"kaggle_username", b"accounts_store_present"]
        for path in (self.out / "snapshot").rglob("*"):
            if not path.is_file():
                continue
            data = path.read_bytes()
            for needle in forbidden:
                with self.subTest(file=str(path.relative_to(self.out)), needle=needle):
                    self.assertNotIn(needle, data)

    def test_excluded_routes_are_absent(self) -> None:
        for key in self.entries():
            with self.subTest(key=key):
                self.assertFalse(key.startswith(("/api/ai-history", "/api/terminal", "/api/doctor")))
        annotations = json.loads((self.out / self.entries()["/api/pdf/annotations"]["file"]).read_text())
        self.assertEqual(annotations, {"timestamp": None, "annotations": [], "applied": {}})
        for excluded in ("/api/ai-history", "/api/doctor", "/api/terminal/*"):
            self.assertIn(excluded, self.report["excluded"])

    def test_artifacts_come_only_from_the_allow_list(self) -> None:
        artifacts = [key for key in self.entries() if key.startswith("/api/artifact")]
        self.assertTrue(artifacts, "the status artifacts and section files are exported")
        for key in artifacts:
            with self.subTest(key=key):
                self.assertNotIn("%2F.", key)
                self.assertFalse(key.split("path=", 1)[1].startswith("."))

    def test_the_workspace_is_byte_identical_after_the_export(self) -> None:
        self.assertEqual(self.before, self.after)

    def test_the_archive_sync_is_restored_after_the_export(self) -> None:
        self.assertEqual(server.ai_archive.sync_in_background.__name__, "sync_in_background")

    def test_the_page_loads_the_shim_after_i18n_and_carries_the_manifest(self) -> None:
        page = (self.out / "index.html").read_text(encoding="utf-8")
        order = re.findall(r'<script src="\./([^"?]+)', page)
        self.assertEqual(order.index("snapshot.js"), order.index("i18n.js") + 1)
        self.assertIn("window.PAPERSMITH_SNAPSHOT_MANIFEST", page)
        self.assertIn("window.PAPERSMITH_STATIC", page)
        self.assertLess(page.index("window.PAPERSMITH_SNAPSHOT_MANIFEST"), page.index('src="./snapshot.js'))
        self.assertNotIn('<script src="./cli-console.js', page)
        self.assertNotIn('<script src="./vendor/xterm.js', page)
        # The flow iframe in the markup points at its snapshot file.
        self.assertRegex(page, r'<iframe id="flowIframe"[^>]*src="snapshot/en/api/flow\.html"')
        markup = re.sub(r"<script\b.*?</script>", "", page, flags=re.S)
        self.assertNotRegex(markup, r'\s(?:src|href)="/api/')
        self.assertTrue((self.out / ".nojekyll").is_file())
        self.assertTrue((self.out / "snapshot.js").is_file())
        self.assertTrue((self.out / "vendor" / "pdf.min.js").is_file())

    def test_the_report_counts_what_was_written(self) -> None:
        self.assertEqual(self.report["routes"], len(self.entries()))
        self.assertGreater(self.report["files"], 0)
        self.assertGreater(self.report["bytes"], 0)

    def test_a_non_workspace_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(static_export.SnapshotError) as caught:
                static_export.export_snapshot(Path(raw), Path(raw) / "out")
            self.assertIn("papersmith.yaml", str(caught.exception))
            self.assertFalse((Path(raw) / "out").exists())

    def test_a_non_empty_destination_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            (out / "keep.txt").write_text("mine", encoding="utf-8")
            with self.assertRaises(static_export.SnapshotError):
                static_export.export_snapshot(self.workspace, out)
            self.assertEqual((out / "keep.txt").read_text(encoding="utf-8"), "mine")


class ExperimentScrubTests(unittest.TestCase):
    def test_team_accounts_and_credentials_are_dropped(self) -> None:
        view = {
            "products": [{"name": "p", "remote_workers": [{"worker": "alice"}],
                          "placement_plan": {"accounts": ["kaggle:alice"]},
                          "runs": {"latest": [{"worker": "alice", "submission_id": "alice/x", "state": "ok"}]},
                          "figures": [{"path": "implementations/p/fig.png"}]}],
            "remote_accounts": {"accounts_store_present": True},
            "remote_mcp": {"token_path": "/home/u/.kaggle/access_token"},
            "remote_colab": {"environment": {"user": "u"}},
            "remote_services": {"team": {"members": [{"email": "a@b.c"}]}},
            "local_environment": {"workspace": {"path": ".micromamba"}},
            "run_options": {"plan_picks": {"full": {"accounts": ["kaggle:alice"]}}},
            "flow": {"poc": 1},
        }
        scrubbed = static_export.scrub_experiments(view)
        text = json.dumps(scrubbed)
        for needle in ("alice", "token_path", "a@b.c", "remote_", "local_environment", "run_options"):
            self.assertNotIn(needle, text)
        self.assertEqual(scrubbed["flow"], {"poc": 1})
        self.assertEqual(scrubbed["products"][0]["figures"], [{"path": "implementations/p/fig.png"}])
        self.assertEqual(scrubbed["products"][0]["runs"]["latest"][0]["state"], "ok")


class PathScrubTests(unittest.TestCase):
    def test_this_and_other_machines_home_paths_are_scrubbed(self) -> None:
        root = Path("/srv/work/paper")
        text = (b'{"a": "/srv/work/paper/sections/x.md", "b": "/Users/teammate/Documents/data", '
                b'"c": "/home/other/.cache/x", "d": "https://example.org/home/page"}')
        scrubbed = static_export._scrub_text(text, static_export._path_replacements(root))
        self.assertEqual(scrubbed, b'{"a": "./sections/x.md", "b": "~/Documents/data", '
                                   b'"c": "~/.cache/x", "d": "https://example.org/home/page"}')

    def test_guidance_and_dot_folders_are_never_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            for rel in ("guidance/reference-papers/p.md", ".papersmith/team.json", "sections/a.md"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x", encoding="utf-8")
            allowed = [rel for rel in ("guidance/reference-papers/p.md", ".papersmith/team.json",
                                       "sections/a.md", "../etc/passwd")
                       if static_export._allowed_artifact(root, rel)]
        self.assertEqual(allowed, ["sections/a.md"])


class ShippedPageTests(unittest.TestCase):
    def test_the_shipped_page_loads_the_inert_shim_right_after_i18n(self) -> None:
        order = re.findall(r'<script src="\./([^"?]+)', PAGE[:PAGE.index("</head>")])
        self.assertEqual(order.index("snapshot.js"), order.index("i18n.js") + 1)
        shim = (STATIC / "snapshot.js").read_text(encoding="utf-8")
        # Without the export's manifest the shim returns before touching anything.
        head = shim[:shim.index("window.fetch =")]
        self.assertRegex(head, r"if \(!manifest[^\n]*\) return;")

    def test_pdf_url_and_the_graph_check_use_the_hooks_only_when_present(self) -> None:
        self.assertIn("window.psRewrite ? window.psRewrite(", PAGE)
        explorer = (STATIC / "paper-explorer-panel.js").read_text(encoding="utf-8")
        self.assertIn("window.psApiPath ? window.psApiPath(", explorer)


class CliTests(unittest.TestCase):
    def test_the_server_flag_runs_the_exporter(self) -> None:
        parser = server.build_parser()
        args = parser.parse_args(["--export-snapshot", "/tmp/x", "--snapshot-lang", "en"])
        self.assertEqual(args.export_snapshot, "/tmp/x")
        self.assertEqual(args.snapshot_lang, "en")

    def test_smith_ui_forwards_the_snapshot_flags_to_the_workspace_backend(self) -> None:
        argv = ui_command.build_server_argv(Path("/w"), "127.0.0.1", 8080, no_browser=True,
                                            export_snapshot="/tmp/site", snapshot_lang="en,es")
        self.assertIn("--export-snapshot", argv)
        self.assertEqual(argv[argv.index("--export-snapshot") + 1], "/tmp/site")
        self.assertEqual(argv[argv.index("--snapshot-lang") + 1], "en,es")

    def test_smith_ui_spawns_the_backend_for_a_snapshot(self) -> None:
        captured: list[list[str]] = []
        original = ui_command._run_child
        ui_command._run_child = lambda argv, workspace: captured.append(argv) or 0
        self.addCleanup(setattr, ui_command, "_run_child", original)
        backend = ui_command.require_runnable_backend
        ui_command.require_runnable_backend = lambda workspace, interpreter: interpreter
        self.addCleanup(setattr, ui_command, "require_runnable_backend", backend)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            entry = root / ui_command.COMMAND_CENTER_ENTRY
            entry.parent.mkdir(parents=True)
            entry.write_text("", encoding="utf-8")
            args = argparse.Namespace(directory=str(root), host="127.0.0.1", port=8080,
                                      no_browser=False, export_static=None,
                                      export_snapshot=str(root / "site"), snapshot_lang="en")
            self.assertEqual(ui_command.run_cli(args), 0)
        self.assertIn("--export-snapshot", captured[0])
        self.assertNotIn("--export-static", captured[0])

    def test_the_server_refuses_a_non_workspace_with_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            code = server.main(["--root", raw, "--export-snapshot", os.path.join(raw, "out")])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
