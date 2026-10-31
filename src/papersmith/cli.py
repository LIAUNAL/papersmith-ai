"""papersmith command-line interface.

Subcommands register themselves here as they land; every handler returns the
process exit code and raises ``PapersmithError`` for typed failures.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .bridges import deliberation as deliberation_command
from .bridges import implementation as implementation_command
from .bridges import audit as audit_command
from .bridges import remote as remote_command
from .core import atlas as atlas_command
from .core import colab as colab_command
from .core import doctor as doctor_command
from .core import env as env_command
from .core import executor as executor_command
from .core import init as init_command
from .core import ingest as ingest_command
from .core import novelty as novelty_command
from .core import status as status_command
from .core import target as target_command
from .core import team as team_command
from .core import ui as ui_command
from .core import upgrade as upgrade_command
from .errors import PapersmithError
from .mcp import cli as mcp_command


def build_parser(prog: str = "smith") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="CLI workspace orchestrator for the papersmith-ai framework: "
        "initialize, upgrade, and run decoupled paper research workspaces.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for register in _REGISTRY:
        register(sub)
    return parser


_REGISTRY: list = [
    init_command.register,
    env_command.register,
    upgrade_command.register,
    status_command.register,
    ingest_command.register,
    deliberation_command.register,
    implementation_command.register,
    executor_command.register,
    remote_command.register,
    target_command.register,
    audit_command.register,
    doctor_command.register,
    novelty_command.register,
    ui_command.register,
    atlas_command.register,
    mcp_command.register,
    team_command.register,
    colab_command.register,
]


def command(register):
    """Decorator: register a subcommand's parser builder."""
    _REGISTRY.append(register)
    return register


def parse_argv(parser: argparse.ArgumentParser, argv: list[str] | None):
    """Parse ``argv`` letting the chosen subcommand interleave its positionals
    with its optionals (``smith run smoke --dry-run <dir>``).

    Native argparse only mixes the two freely from 3.13 on; on 3.11/3.12 a
    trailing positional after the optionals is rejected as unrecognized, which
    the CI matrix caught. ``parse_intermixed_args`` is the documented API for
    this order and is applied to the chosen subcommand only -- the top parser
    carries subparsers, which ``parse_intermixed_args`` refuses.
    """
    actual = sys.argv[1:] if argv is None else list(argv)
    subparsers = next(
        (action for action in parser._actions
         if isinstance(action, argparse._SubParsersAction)),
        None,
    )
    if subparsers is not None and actual and actual[0] in subparsers.choices:
        name = actual[0]
        chosen = subparsers.choices[name]
        try:
            namespace = chosen.parse_intermixed_args(actual[1:])
        except TypeError:
            # `parse_intermixed_args` refuses parsers that carry their own
            # subparsers (`target set <name> <dir>`) or a REMAINDER. Those
            # commands never needed the interleave fix; their plain parse is
            # the parser's own contract.
            namespace = chosen.parse_args(actual[1:])
        setattr(namespace, subparsers.dest, name)
        return namespace
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # `smith` is the canonical command name; the `papersmith` entry point stays
    # installed as a compatibility alias but reports itself as `smith`.
    prog = "smith"
    parser = build_parser(prog=prog)
    args = parse_argv(parser, argv)
    setattr(args, "_prog", prog)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    try:
        return handler(args)
    except PapersmithError as exc:
        print(f"{prog}: error: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print(f"{prog}: interrupted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
