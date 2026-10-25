"""Shared pytest fixtures.

The papersmith CLI uses a src-layout; expose ``src/`` so tests import the
package without an install step. The repository root is exposed too: the Paper
Command Center ships as ``skills/_core/command_center/`` (a kit tree member
that must stay importable standalone from a workspace root), not as a
``papersmith`` submodule.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The suite initializes and upgrades workspaces from this checkout, which is
# usually carrying uncommitted edits, and from throwaway kits outside git. Both
# refuse by design without an explicit override (`--allow-dirty-kit`); this is
# that override for the test process and the CLI children it spawns. The tests
# that pin the refusal itself (tests/test_kit_provenance.py) remove it first.
import os  # noqa: E402

os.environ.setdefault("PAPERSMITH_ALLOW_DIRTY_KIT", "1")


# --- Process-state isolation (X8b) -----------------------------------------
#
# The suite runs as one process, so anything a test leaves in `os.environ`,
# the working directory, or the cached `impl_domain_profile` module is read by
# every test after it. Measured: importing a skill's `materialize.py` inside
# one class `setdefault`s IMPLEMENTATION_DOMAIN_PROFILE to that skill's
# profile for the rest of the run, and a later test that hands `os.environ`
# to the OTHER skill's launcher then reads the wrong holder -- green alone,
# red in the change-selected tier. Listing the offending tests does not
# scale; restoring the state after every test and every module does.
#
# Two scopes, because unittest's `setUpClass`/`setUpModule` run inside
# class- and module-scoped fixtures, outside any function fixture: the
# function scope undoes what a test body or its `setUp` left behind, the
# module scope undoes what a class or module setup left behind. A restore
# only runs when something changed, and comparing about a hundred short
# strings costs microseconds per test.

import pytest  # noqa: E402

#: Cached modules whose import resolves process-wide state from the
#: environment: the implementation engine's profile is resolved once, at
#: import, from IMPLEMENTATION_DOMAIN_PROFILE.
_STATEFUL_MODULES = ("impl_domain_profile",)


def _snapshot() -> tuple[dict, str, dict]:
    return (dict(os.environ), os.getcwd(),
            {name: sys.modules.get(name) for name in _STATEFUL_MODULES})


def _restore_environ(saved: dict) -> None:
    current = os.environ
    if current == saved:
        return
    for key in [key for key in current if key not in saved]:
        del current[key]
    for key, value in saved.items():
        if current.get(key) != value:
            current[key] = value


def _restore(snapshot: tuple[dict, str, dict], *, modules: bool) -> None:
    environ, cwd, cached = snapshot
    _restore_environ(environ)
    if os.getcwd() != cwd:
        os.chdir(cwd)
    if modules:
        for name, module in cached.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


@pytest.fixture(autouse=True, scope="module")
def _isolate_module_process_state():
    snapshot = _snapshot()
    yield
    _restore(snapshot, modules=True)


@pytest.fixture(autouse=True)
def _isolate_test_process_state():
    snapshot = _snapshot()
    yield
    # Environment and cwd only: a cached profile module set up by a class
    # fixture stays for the rest of that class, and the module scope above
    # drops it before the next file.
    _restore(snapshot, modules=False)


# --- Run registry for the orphan sweep (#60) --------------------------------
#
# Several suites write fixtures into the live `implementations/`, named after
# the pid of the process that made them. `orphan_sweep` removes one a killed
# run left behind only when that pid is recorded here as a test run (and is
# dead); an operator's own repository never is. Every pytest process,
# including each xdist worker, records itself before any test runs.
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))
try:
    import orphan_sweep  # noqa: E402
except ImportError:
    # A conftest copied into a scratch suite (test_process_state_isolation)
    # travels without its siblings; an unrecorded run only means its own
    # orphans are never swept.
    orphan_sweep = None
if orphan_sweep is not None:
    orphan_sweep.register_run()
