"""``smith gpu [<dir>]`` -- this machine's GPU, what blocks it, and the fix.

A read-only report from the kit's shared probe
(``skills/_core/gpu/gpu_probe.py``): vendor, AMD gfx target, VRAM/GTT, whether
this process can open the GPU nodes, the render-group state, the Vulkan
devices llama.cpp lists and the PyTorch backend of the workspace interpreter
(or ``--python``), then one exact remedy command per blocker. Works outside a
workspace too: the probe then comes from the kit and torch from this
interpreter.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from ..errors import UserError
from .exit_codes import SUCCESS

PROBE = Path("skills") / "_core" / "gpu" / "gpu_probe.py"
_MODULE = "papersmith_gpu_probe"


def load_probe(root: Path | None = None):
    """The probe module from the workspace, else the kit, else this checkout."""
    if _MODULE in sys.modules:
        return sys.modules[_MODULE]
    candidates: list[Path] = []
    if root is not None:
        candidates.append(root / PROBE)
    try:
        from ..kit import resolve_kit_root

        candidates.append(resolve_kit_root() / PROBE)
    except Exception:
        pass
    candidates.append(Path(__file__).resolve().parents[3] / PROBE)
    for script in candidates:
        if script.is_file():
            spec = importlib.util.spec_from_file_location(_MODULE, script)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[_MODULE] = module
                spec.loader.exec_module(module)
                return module
    raise UserError(f"could not locate the GPU probe ({PROBE.as_posix()}); run `smith upgrade`")


def _interpreter(root: Path, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if (root / ".papersmith").is_dir():
        try:
            from .ui import workspace_interpreter

            return workspace_interpreter(root)
        except Exception:
            return None
    return None


def run_cli(args) -> int:
    root = Path(args.directory).expanduser().resolve()
    probe = load_probe(root if (root / PROBE).is_file() else None)
    python = _interpreter(root, args.python) or sys.executable
    report = probe.probe(python=python)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(probe.render_text(report))
    return SUCCESS


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "gpu", help="report this machine's GPU, what blocks it and the exact fix (read-only)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--python", default=None, metavar="<interpreter>",
                        help="interpreter whose PyTorch to probe (default: the workspace's)")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.set_defaults(handler=run_cli)
