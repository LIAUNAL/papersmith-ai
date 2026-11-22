"""`smith kind set`: move a workspace to the line of its agreed paper type.

The operator agrees a paper type after plausibility (`/paper-type`). When that
type's line (`experimental`, `review`) differs from the workspace's, this
command records the agreement, writes the new `paper_kind` and lets `upgrade`
apply the line's kit layout and harness flow text. The other line's files are
removed only when unedited (their hash matches the stored manifest); an edited
one stays and is reported as stranded, because it is the operator's work.

A paper that has started (a managed proposal revision or `paper/main.tex`)
refuses to move unless `--force`: its proposals and sections were written for
the line it is on.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ..errors import PapersmithError, UserError
from ..kit import resolve_and_validate_origin
from . import fs, manifest, upgrade as upgrade_module
from .exit_codes import SUCCESS

#: The workspace's copy of the paper-type catalogue and the module that
#: records the agreement (paper-type-lines S2-S3). ``kind set`` reuses both so
#: there is one catalogue and one writer of ``.papersmith/paper_type.json``.
CATALOGUE = Path("skills") / "_core" / "paper_types" / "paper_types.json"
DECISION_MODULE = "skills._core.paper_types.paper_type_cli"
CONFIG = Path(".papersmith") / "config.json"


def _line_of(root: Path, type_id: str) -> str:
    """The workspace line of ``type_id``, refusing unknown and planned types."""
    text = fs.read_text(root / CATALOGUE)
    if text is None:
        raise UserError(f"{CATALOGUE} not found in {root}: run `smith upgrade` to refresh the workspace kit")
    try:
        types = json.loads(text).get("types", [])
    except (ValueError, AttributeError):
        raise UserError(f"{root / CATALOGUE} is not a readable paper-type catalogue") from None
    item = next((entry for entry in types if isinstance(entry, dict) and entry.get("id") == type_id), None)
    if item is None:
        known = ", ".join(str(entry.get("id")) for entry in types if isinstance(entry, dict))
        raise UserError(f"TYPE_UNKNOWN: no paper type {type_id!r}; expected one of {known}")
    line = item.get("line")
    if line is None:
        raise UserError(f"paper type {type_id!r} has no flow in smith yet; agree it with /paper-type "
                        "and the workspace keeps its line until one exists")
    if line not in manifest.PAPER_KINDS:
        raise UserError(f"paper type {type_id!r} names an unknown line {line!r}")
    return line


def started_markers(root: Path) -> list[str]:
    """The files that show the paper has started on its current line."""
    markers = sorted(path.relative_to(root).as_posix()
                     for path in (root / "proposals").glob("*-r*.md") if fs.is_regular_file(path))
    if fs.is_regular_file(root / "paper" / "main.tex"):
        markers.append("paper/main.tex")
    return markers


def _agree(root: Path, type_id: str, by: str) -> dict:
    """Record the agreement through the workspace's own paper-type CLI."""
    argv = [sys.executable, "-B", "-m", DECISION_MODULE, "agree", "--root", str(root),
            "--type", type_id, "--by", by, "--rationale", "smith kind set"]
    completed = subprocess.run(argv, cwd=str(root), capture_output=True, text=True, check=False)
    try:
        reply = json.loads(completed.stdout or "{}")
    except ValueError:
        reply = {}
    if completed.returncode != 0 or not reply.get("ok"):
        code = reply.get("error") or "AGREE_FAILED"
        message = reply.get("message") or completed.stderr.strip() or "the agreement was not recorded"
        raise UserError(f"{code}: {message}")
    return reply


def _remove_unedited(root: Path, paths: list[str], baseline: dict) -> tuple[list[str], list[str]]:
    """Delete the old line's files whose bytes are the framework's; keep the rest."""
    removed: list[str] = []
    stranded: list[str] = []
    for relpath in paths:
        target = root / relpath
        if not fs.exists(target) or manifest.is_preserved(relpath):
            continue
        recorded = baseline.get(relpath)
        current = manifest.sha256_if_readable(target)
        if not isinstance(recorded, str) or current is None or current != recorded:
            stranded.append(relpath)
            continue
        try:
            target.unlink()
        except OSError:
            stranded.append(relpath)
            continue
        removed.append(relpath)
        parent = target.parent
        while parent != root and parent.name != "sections":
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    return removed, stranded


def set_kind(workspace: str | Path, type_id: str, *, by: str, force: bool = False) -> dict:
    root = Path(workspace).expanduser().resolve()
    stored = manifest.load_manifest(root)
    if stored is None:
        raise UserError(f"not a papersmith workspace: missing {root / '.papersmith/manifest.json'}")
    by = str(by or "").strip()
    if not by:
        raise UserError("name the operator who agreed the paper type with --by")
    line = _line_of(root, type_id)
    previous = manifest.paper_kind(root)
    if line != previous and not force:
        markers = started_markers(root)
        if markers:
            raise UserError(f"the paper has started on the {previous} line ({', '.join(markers)}); "
                            "moving it would leave its proposals and sections behind. "
                            "Re-run with --force to move it anyway")
    agreement = _agree(root, type_id, by)
    result = {"workspace": str(root), "type": type_id, "agreed_by": by, "from": previous, "to": line,
              "moved": False, "removed": [], "stranded": [], "upgrade": None,
              "agreed_variant": agreement.get("agreed_variant")}
    if line == previous:
        return result

    kit_root, _ = resolve_and_validate_origin()
    leaving = sorted(set(manifest.kit_layout(kit_root, previous)) - set(manifest.kit_layout(kit_root, line)))
    config_path = root / CONFIG
    original = fs.read_text(config_path)
    config = json.loads(original) if original else {}
    config["paper_kind"] = line
    if not fs.write_text(config_path, json.dumps(config, indent=2, sort_keys=False) + "\n"):
        raise UserError(f"could not write {config_path}")
    try:
        report = upgrade_module.upgrade(root)
    except PapersmithError:
        # ``upgrade`` refuses before its first write (dirty kit, downgrade), so
        # restoring the line leaves the workspace exactly as it was.
        fs.write_text(config_path, original or "")
        raise
    removed, stranded = _remove_unedited(root, leaving, stored["files"])
    if any(not relpath.startswith(upgrade_module.SECTION_CONTRACTS) for relpath in removed):
        # A removed skill still had rendered commands; a second pass renders
        # without it and sweeps them as orphans.
        report = upgrade_module.upgrade(root)
    result.update({"moved": True, "removed": removed, "stranded": stranded, "upgrade": report})
    return result


def register(subparsers) -> None:
    parser = subparsers.add_parser("kind", help="move a workspace to the line of its agreed paper type")
    parser.add_argument("action", choices=("set",), help="set: record the type and apply its line")
    parser.add_argument("type", metavar="<type>", help="a paper type id of the catalogue (applied-ai, review, ...)")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.add_argument("--by", default="", help="the operator who agreed the type")
    parser.add_argument("--force", action="store_true",
                        help="move even when a proposal revision or paper/main.tex exists")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    result = set_kind(args.directory, args.type, by=args.by, force=args.force)
    variant = f", variant {result['agreed_variant']}" if result["agreed_variant"] else ""
    print(f"Paper type agreed: {result['type']}{variant} (by {result['agreed_by']})")
    if not result["moved"]:
        print(f"The workspace already follows the {result['to']} line; nothing moved.")
        return SUCCESS
    print(f"Paper line: {result['from']} -> {result['to']}")
    report = result["upgrade"]
    print(f"Framework version: {report['version']}; changed files: {len(report['changed_files'])}")
    for relpath in result["removed"]:
        print(f"Removed (unedited): {relpath}")
    for relpath in result["stranded"]:
        print(f"Stranded (edited, kept): {relpath}")
    for relpath in report["kept_edited"]:
        print(f"Kept edited contract: {relpath}")
    for relpath in report["unsynchronized"]:
        print(f"Warning: could not write '{relpath}'; it stays reported as drift")
    return SUCCESS
