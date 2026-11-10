"""`smith` is the only command the package installs, and the name it reports."""

from __future__ import annotations

import sys

import pytest

from papersmith import cli


@pytest.mark.parametrize("argv0", ["/usr/bin/smith", "python"])
def test_version_reports_smith_for_every_entry_point(monkeypatch, capsys, argv0):
    monkeypatch.setattr(sys, "argv", [argv0, "--version"])
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("smith ")


def test_help_usage_names_smith(capsys):
    assert cli.main([]) == 1
    assert capsys.readouterr().out.startswith("usage: smith ")


def test_only_smith_is_installed():
    """The `papersmith` alias kept since 0.19.0 is gone: `smith` is the one
    console script. `smith upgrade` repoints workspace MCP entries that still
    launch the old name (see tests/test_migration_legacy_command.py)."""
    import tomllib
    from pathlib import Path

    scripts = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    )["project"]["scripts"]
    assert scripts == {"smith": "papersmith.cli:main"}
