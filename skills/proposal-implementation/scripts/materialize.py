#!/usr/bin/env python3
"""Drop the materialization kit into a target repository.

The forge's own harness, never a step of Flow A: an agent fills the scaffold
gaps by reading step 5, and this plays that part so the suite can examine a
freshly scaffolded target. It fills exactly the gaps the skill reports,
parameterized by the scenario's name and seed, and writes no step-9 template —
those answer an object map that does not exist at scaffold time.

    python3 materialize.py <target> <Name> <seed> [kit-directory]

The kit defaults to the skill's own templates. The forge's harness passes a
neutral fixture kit instead: a paper forge must not carry one paper's content.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The one-way dependency this file's own docstring claims: the production
# engine never imports this script; this script imports the engine.
#
# Cut 1 (`the-engine-leaves-its-skill`): the engine now lives under
# `_core/implementation/engine/`, serves no domain of its own, and refuses
# to start without a profile -- this script is a second host reaching it,
# exactly the way the published launcher (`implementation_cli.py`, now a
# 22-line hand-over, never re-exporting the engine's own names) does.
_HERE = Path(__file__).resolve()
os.environ.setdefault("IMPLEMENTATION_DOMAIN_PROFILE",
                      str(_HERE.parents[1] / "impl_profile.py"))
sys.path.insert(0, str(_HERE.parents[2] / "_core" / "implementation" / "engine"))
from implementation_engine import (  # noqa: E402
    IGNORE_ENTRIES,
    authored_ignore_lines,
    SKILL_ROOT,
    authored_package_init,
    package_name,
    scaffold_destinations,
    scaffold_kit_source,
    scaffold_substitute_body,
    writable_at_scaffold_time,
)

DEFAULT_KIT = SKILL_ROOT / "assets" / "kit"


def main(target: str, name: str, seed: str, kit: str | None = None) -> int:
    KIT = Path(kit).resolve() if kit else DEFAULT_KIT
    root = Path(target).resolve()
    pkg = package_name(name)
    package_init = f"src/{pkg}/__init__.py"

    # design D9: `scaffold_destinations(name)` is the ONE list the writer and
    # the gap-reporter both read. This file used to re-implement the scaffold
    # stage imperatively at three separate sites -- the package init, the
    # benchmark package's declaration, and the report seal -- and a fourth
    # site added by a later movement would have had to remember to update
    # this file too. The loop below removes the duplication instead of
    # policing it: `MaterializeScaffoldAgreementTests` asserts the two lists
    # agree, and now that assertion is a tautology by construction.
    for destination in scaffold_destinations(name):
        full = root / destination
        full.parent.mkdir(parents=True, exist_ok=True)

        if destination == package_init:
            # The one scaffold destination with no kit source: `src/` has no
            # modules yet because step 9 has written none of them, so this
            # file is engine-authored rather than copied. Preserved
            # verbatim: `experimental-implementation` ships no scaffold kit (its
            # `assets/kit/` holds only `ps_figures.py`), and this is the one write
            # that never needs one.
            full.write_text(authored_package_init(name))
            continue

        # Kit sources resolve under the caller-supplied KIT, never under
        # SKILL_ROOT: `scaffold_kit_source` answers in terms of the skill's
        # OWN kit, and the fourth argument exists precisely so a neutral
        # fixture kit can stand in for it. Re-rooting every destination
        # under the passed KIT keeps that promise for the whole loop, not
        # just the sites this file used to special-case -- a paper forge
        # must not carry one paper's content into its own test suite.
        source = scaffold_kit_source(destination, name)
        relative = source.relative_to(SKILL_ROOT / "assets" / "kit")
        body = scaffold_substitute_body(
            (KIT / relative).read_text(encoding="utf-8"), name, seed)
        if destination.endswith(".py") and not writable_at_scaffold_time(body):
            # `conftest.py`, `sweep.py` and `admissibility.py` are not tests
            # and were never asked for, so a scaffold built from exactly
            # this list could not be collected without them; but
            # `test_invariants.py`/`test_synthetic.py`-shaped templates
            # still carry step 9's own tokens (`{{FUNCTION_NAME}}`,
            # `{{INVARIANT_ID}}`, `{{EXPECTATION}}`) at scaffold time, and
            # nothing here could have answered them yet. Left unwritten
            # rather than shipped unparsable.
            continue
        full.write_text(body, encoding="utf-8")

    pyproject = root / "pyproject.toml"
    text = pyproject.read_text() if pyproject.exists() else (
        "[build-system]\n"
        'requires = ["setuptools>=68"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        f'name = "{pkg.lower().replace("_", "-")}"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.9"\n'
        'dependencies = ["numpy>=1.24"]\n\n'
        "[tool.setuptools.packages.find]\n"
        'where = ["src"]\n'
    )
    if "[tool.pytest.ini_options]" not in text:
        # `["src"]`, the way `assets/pyproject.template.toml` and step 5 both
        # spell it. `tests` was listed here too and nothing announced the
        # difference: pytest's prepend import mode already puts a test file's own
        # directory on `sys.path`, so the flat `from sweep import ...` style the
        # kit uses resolves either way. Naming `tests` explicitly would make the
        # forge depend on a path where it depends on that behaviour.
        text += ('\n[tool.pytest.ini_options]\n'
                 'testpaths = ["tests"]\n'
                 'pythonpath = ["src"]\n')
    pyproject.write_text(text)

    # Merged into whatever the repository already has, never written over it —
    # a checkout that already ignores things has reasons this script cannot
    # read. It was the one gap the materializer left behind, which is why a test
    # fixture hand-patched it afterwards; a producer and a hand-patch writing
    # halves of the same file is how the two trees drifted with neither being
    # wrong on its own.
    ignore = root / ".gitignore"
    ignored = ignore.read_text() if ignore.exists() else ""
    missing = [entry for entry in IGNORE_ENTRIES
               if entry.rstrip("/") not in ignored]
    if missing:
        if ignored and not ignored.endswith("\n"):
            ignored += "\n"
        ignore.write_text(ignored + "".join(
            f"{entry}\n" for entry in authored_ignore_lines(root, missing)))

    print(f"materialized {pkg} into {root} (seed {seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:5]))
