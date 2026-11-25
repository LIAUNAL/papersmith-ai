"""``smith idea [VERB] [ROOT]``: the optional idea-shaping phase before ``/plausibility``.

Every argument is forwarded to the engine's own CLI,
``skills/_core/idea/idea_cli.py`` (one parser, so ``smith idea --help`` and
``smith idea VERB --help`` print the engine's help for every verb and
option). Plain ``smith idea`` runs ``start``: the six questions, one at a
time. The engine is loaded from the workspace's kit copy when it has one,
else from the kit smith runs from, like ``smith novelty`` loads its gate.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

from ..errors import UserError

ENGINE = Path("skills") / "_core" / "idea" / "idea_cli.py"
MODULE = "skills._core.idea.idea_cli"
HELP = ("optional idea shaping before /plausibility: sources (bank MCP), profile, experience, interests, "
        "topics and a gated draft (`smith idea --help` lists the verbs)")


def _root_guess(argv: list[str]) -> Path:
    """The workspace the arguments name (``--root DIR`` or a ROOT holding
    ``.papersmith/``), else the current directory; only to pick the engine."""
    for index, token in enumerate(argv):
        if token == "--root" and index + 1 < len(argv):
            return Path(argv[index + 1]).expanduser()
        if token.startswith("--root="):
            return Path(token.split("=", 1)[1]).expanduser()
    for token in reversed(argv):
        if not token.startswith("-") and (Path(token).expanduser() / ".papersmith").is_dir():
            return Path(token).expanduser()
    return Path.cwd()


def _candidates(root: Path) -> list[Path]:
    found = [root / ENGINE]
    try:
        from ..kit import resolve_kit_root
        found.append(resolve_kit_root() / ENGINE)
    except Exception:  # noqa: BLE001 - a broken kit falls back to the checkout
        pass
    found.append(Path(__file__).resolve().parents[3] / ENGINE)
    return found


def load_engine(argv: list[str]) -> Any:
    """The engine's ``idea_cli`` module (imported as ``skills._core.idea.idea_cli``
    from the first tree that ships it)."""
    if MODULE in sys.modules:
        return sys.modules[MODULE]
    for script in _candidates(_root_guess(argv)):
        if script.is_file():
            base = str(script.resolve().parents[3])
            if base not in sys.path:
                sys.path.insert(0, base)
            try:
                return importlib.import_module(MODULE)
            except ImportError:
                continue
    raise UserError(f"could not locate the idea-shaping engine ({ENGINE.as_posix()}); "
                    "run `smith upgrade` to refresh the workspace kit")


def run(args: argparse.Namespace) -> int:
    argv = list(getattr(args, "idea_argv", []) or [])
    engine = load_engine(argv)
    return int(engine.main(argv, prog=f"{getattr(args, '_prog', 'smith')} idea"))


class _ForwardParser(argparse.ArgumentParser):
    """Takes every argument verbatim (options included, before or after the
    verb) and leaves parsing and help to the engine's parser."""

    def parse_known_args(self, args=None, namespace=None):  # type: ignore[override]
        namespace = namespace if namespace is not None else argparse.Namespace()
        namespace.idea_argv = list(sys.argv[2:] if args is None else args)
        namespace.handler = run
        return namespace, []

    def parse_args(self, args=None, namespace=None):  # type: ignore[override]
        return self.parse_known_args(args, namespace)[0]

    def parse_intermixed_args(self, args=None, namespace=None):  # type: ignore[override]
        return self.parse_known_args(args, namespace)[0]


def register(subparsers) -> None:
    parser = subparsers.add_parser("idea", help=HELP, description=HELP, add_help=False)
    parser.__class__ = _ForwardParser
