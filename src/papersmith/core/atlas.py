"""``smith atlas build|cited|summary``: the workspace's SOTA atlas actions.

``smith atlas summary`` writes the manuscript summary graph
(``.papersmith/manuscript_graph.json``) through
``skills/_core/command_center/manuscript_graph.py``, the same way.

``smith atlas cited`` writes the manuscript layer
(``sota-pool/atlas.manuscript.json``: which atlas systems the paper cites)
through ``skills/_core/command_center/atlas_manuscript.py``, the same way.

``smith atlas build`` regenerates the SOTA atlas page.

The same action as the dashboard's "Regenerar grafo" button. The rebuild lives
in the workspace's command center (``skills/_core/command_center/atlas_build.py``)
and runs the workspace's own plausibility checker and renderer; this command
only resolves the workspace and runs that module from its root. Both are
stdlib-only, so the current interpreter is enough.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..errors import UserError
from . import fs

#: The workspace module that performs the rebuild.
ATLAS_BUILD_MODULE = "skills._core.command_center.atlas_build"
ATLAS_BUILD_ENTRY = Path("skills") / "_core" / "command_center" / "atlas_build.py"
#: The workspace module that writes the manuscript layer.
ATLAS_MANUSCRIPT_MODULE = "skills._core.command_center.atlas_manuscript"
ATLAS_MANUSCRIPT_ENTRY = Path("skills") / "_core" / "command_center" / "atlas_manuscript.py"
#: The workspace module that writes the manuscript summary graph.
MANUSCRIPT_GRAPH_MODULE = "skills._core.command_center.manuscript_graph"
MANUSCRIPT_GRAPH_ENTRY = Path("skills") / "_core" / "command_center" / "manuscript_graph.py"
#: The workspace module that builds the 3D novelty solar constellation.
NOVELTY_GRAPH_MODULE = "skills._core.command_center.novelty_graph"
NOVELTY_GRAPH_ENTRY = Path("skills") / "_core" / "command_center" / "novelty_graph.py"


def _run_module(args, module: str, entry: Path) -> int:
    workspace = Path(args.directory).expanduser().resolve()
    if not fs.is_dir(workspace):
        raise UserError(f"not a directory: {workspace}")
    if not fs.is_regular_file(workspace / entry):
        raise UserError(f"{entry} not found in {workspace}: "
                        "run `smith upgrade` to refresh the workspace kit")
    argv = [sys.executable, "-B", "-m", module, "--root", str(workspace)]
    if args.json:
        argv.append("--json")
    if getattr(args, "sync", False):
        argv.append("--sync")
    completed = subprocess.run(argv, cwd=str(workspace), capture_output=True, text=True,
                               check=False)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return 0 if completed.returncode == 0 else 1


def run_build(args) -> int:
    return _run_module(args, ATLAS_BUILD_MODULE, ATLAS_BUILD_ENTRY)


def run_cited(args) -> int:
    return _run_module(args, ATLAS_MANUSCRIPT_MODULE, ATLAS_MANUSCRIPT_ENTRY)


def run_summary(args) -> int:
    return _run_module(args, MANUSCRIPT_GRAPH_MODULE, MANUSCRIPT_GRAPH_ENTRY)


def run_novelty(args) -> int:
    return _run_module(args, NOVELTY_GRAPH_MODULE, NOVELTY_GRAPH_ENTRY)


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "atlas",
        help="SOTA atlas actions (the dashboard's graph buttons, from the terminal)",
        description="SOTA atlas actions shared with the Paper Command Center.",
    )
    actions = parser.add_subparsers(dest="atlas_action", metavar="<action>")
    actions.required = True
    build = actions.add_parser(
        "build",
        help="check sota-pool/atlas.json and re-render sota-pool/atlas.html",
        description=("Run the workspace's plausibility checker on sota-pool/atlas.json "
                     "(with --pool sota-pool/candidates.json when it exists) and, only "
                     "when it is green, re-render sota-pool/atlas.html. Exit 0 when the "
                     "page was written, 1 otherwise."),
    )
    build.add_argument("--json", action="store_true", help="print the result as JSON")
    build.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    build.set_defaults(handler=run_build)
    cited = actions.add_parser(
        "cited",
        help="write sota-pool/atlas.manuscript.json: the atlas systems the paper cites",
        description=("Join sota-pool/atlas.json and candidates.json with paper/main.tex, "
                     "paper/refs.bib and the per-block evidence records, and write "
                     "sota-pool/atlas.manuscript.json (each system cited or not, with its "
                     "citing blocks and claims, plus cited papers outside the pool). "
                     "Never modifies atlas.json. Exit 0 when the layer was written, 1 "
                     "otherwise."),
    )
    cited.add_argument("--json", action="store_true", help="print the result as JSON")
    cited.add_argument("--sync", action="store_true", help="synchronize the 3D constellation with all citations")
    cited.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    cited.set_defaults(handler=run_cited)
    summary = actions.add_parser(
        "summary",
        help="write .papersmith/manuscript_graph.json: the manuscript summary graph",
        description=("Read the topic, problem, pillars, hypotheses, cited SOTA, base and "
                     "novelty mathematics, experiments, findings and conclusions from the "
                     "artifacts each phase wrote, and write .papersmith/manuscript_graph.json "
                     "(typed nodes and edges; a missing source is a node marked missing with "
                     "the phase that fills it). Exit 0 when the graph was written, 1 otherwise."),
    )
    summary.add_argument("--json", action="store_true", help="print the result as JSON")
    summary.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    summary.set_defaults(handler=run_summary)
    novelty = actions.add_parser(
        "novelty",
        help="render .papersmith/novelty_graph.html: 3D novelty solar constellation",
        description=("Read .papersmith/novelty_graph.json and proposals, build the 3D novelty "
                     "solar constellation with one solar system per contribution node, and "
                     "render .papersmith/novelty_graph.html. Exit 0 when the page was written, "
                     "1 otherwise."),
    )
    novelty.add_argument("--json", action="store_true", help="print the constellation JSON")
    novelty.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    novelty.set_defaults(handler=run_novelty)


__all__ = ["register", "run_build", "run_cited", "run_summary", "run_novelty",
           "MANUSCRIPT_GRAPH_MODULE", "MANUSCRIPT_GRAPH_ENTRY", "ATLAS_BUILD_MODULE", "ATLAS_BUILD_ENTRY",
           "ATLAS_MANUSCRIPT_MODULE", "ATLAS_MANUSCRIPT_ENTRY", "NOVELTY_GRAPH_MODULE", "NOVELTY_GRAPH_ENTRY"]
