"""Regenerate the SOTA atlas page: the "Regenerar grafo" action.

The one writer in the command center, and it writes exactly one file:
``sota-pool/atlas.html``. It never lays anything out itself; it runs the
workspace's own plausibility scripts, in the order the skill documents:

1. ``skills/plausibility/scripts/check_atlas.py sota-pool/atlas.json``
   (``--pool sota-pool/candidates.json`` when the pool exists), and stops on
   any violation so a failing atlas never replaces a good page;
2. ``skills/plausibility/scripts/render_atlas.py sota-pool/atlas.json --out
   sota-pool/atlas.html``.

Both scripts are stdlib-only and run as child processes of the current
interpreter, from fixed workspace paths that never come from request input.

Run standalone from a workspace root::

    python -m skills._core.command_center.atlas_build [--root .] [--json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPTS = ("skills", "plausibility", "scripts")
TIMEOUT_SECONDS = 120
MAX_VIOLATIONS = 50
TEXT_MAX = 300


def _result(ok: bool, stage: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"ok": ok, "stage": stage, "detail": detail[:TEXT_MAX], **extra}


def _run(argv: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=str(root), capture_output=True, text=True,
                          timeout=TIMEOUT_SECONDS, check=False)


def _counts(atlas_json: Path) -> dict[str, int]:
    try:
        data = json.loads(atlas_json.read_text(encoding="utf-8"))
        systems = data["systems"]
        planets = sum(len(s.get("planets") or []) for s in systems)
        return {"systems": len(systems), "planets": planets, "links": len(data["links"])}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"systems": 0, "planets": 0, "links": 0}


def build(root: Path | str) -> dict[str, Any]:
    """Check, then render. ``stage`` names where it stopped:

    ``absent`` (no atlas.json), ``scripts`` (a plausibility script is missing),
    ``check`` (the checker refused), ``render`` (the renderer refused) or
    ``rendered`` (the page was written).
    """
    root = Path(root).expanduser().resolve()
    pool = root / "sota-pool"
    atlas_json = pool / "atlas.json"
    if not atlas_json.is_file():
        return _result(False, "absent", "sota-pool/atlas.json not found: run the "
                       "plausibility skill first")
    scripts = root.joinpath(*SCRIPTS)
    checker, renderer = scripts / "check_atlas.py", scripts / "render_atlas.py"
    missing = [p.name for p in (checker, renderer) if not p.is_file()]
    if missing:
        return _result(False, "scripts", "missing " + ", ".join(missing)
                       + " in skills/plausibility/scripts")

    check_argv = [sys.executable, str(checker), "sota-pool/atlas.json"]
    if (pool / "candidates.json").is_file():
        check_argv += ["--pool", "sota-pool/candidates.json"]
    try:
        checked = _run(check_argv, root)
        if checked.returncode != 0:
            lines = [l for l in (checked.stdout + checked.stderr).splitlines() if l.strip()]
            return _result(False, "check", lines[0] if lines else "check_atlas.py refused",
                           violations=[l[:TEXT_MAX] for l in lines[:MAX_VIOLATIONS]],
                           violation_count=len(lines))
        rendered = _run([sys.executable, str(renderer), "sota-pool/atlas.json",
                         "--out", "sota-pool/atlas.html"], root)
    except subprocess.TimeoutExpired:
        return _result(False, "timeout", f"the rebuild exceeded {TIMEOUT_SECONDS}s")
    except OSError as error:
        return _result(False, "scripts", f"could not start the scripts: {error}")
    if rendered.returncode != 0:
        lines = [l for l in (rendered.stdout + rendered.stderr).splitlines() if l.strip()]
        return _result(False, "render", lines[0] if lines else "render_atlas.py refused")
    if (root / "paper" / "refs.bib").is_file() or (pool / "atlas.manuscript.json").is_file():
        try:
            from . import atlas_manuscript
            atlas_manuscript.sync_constellation_citations(root)
        except Exception:
            pass
    return _result(True, "rendered", checked.stdout.strip() or "atlas rendered",
                   **_counts(atlas_json))


def describe(result: dict[str, Any]) -> str:
    """One human line for a build result."""
    if result["ok"]:
        return (f"atlas rebuilt: {result['systems']} systems, {result['planets']} planets, "
                f"{result['links']} links -> sota-pool/atlas.html")
    return f"atlas not rebuilt ({result['stage']}): {result['detail']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skills._core.command_center.atlas_build",
                                     description="Check and re-render sota-pool/atlas.html.")
    parser.add_argument("--root", default=".", help="workspace root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    result = build(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["ok"]:
        print(describe(result))
    else:
        print(describe(result), file=sys.stderr)
        for line in result.get("violations", [])[1:]:
            print(f"  {line}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
