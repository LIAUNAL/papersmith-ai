"""The papersmith exit-code contract.

==================  =================  ===========================================
Code                Name               Meaning
==================  =================  ===========================================
0                   SUCCESS            Operation completed without errors.
1                   USER_ERROR         Missing argument, invalid directory, or
                                       corrupted configuration.
2                   SOURCE_ERROR       Missing kit source files or unresolvable
                                       PAPERSMITH_KIT_ROOT.
3                   DRIFT_ERROR        Drift detected during lint/generator check
                                       or checksum mismatch.
4                   EXECUTION_ERROR    Invariant test failure, remote run crash,
                                       build error, or a ``fail`` row in
                                       ``smith doctor``.
==================  =================  ===========================================
"""

from __future__ import annotations

SUCCESS = 0
USER_ERROR = 1
SOURCE_ERROR = 2
DRIFT_ERROR = 3
EXECUTION_ERROR = 4


def map_child_rc(rc: int) -> int:
    """Map a skill-script exit code onto the papersmith contract.

    Skill scripts use ``2`` for argparse usage errors and domain refusals
    (for example ``implementation_cli``'s ``Refused`` envelope), so both
    surface as USER_ERROR; any other nonzero exit is an execution failure.
    """
    if rc == 0:
        return SUCCESS
    if rc == 2:
        return USER_ERROR
    return EXECUTION_ERROR
