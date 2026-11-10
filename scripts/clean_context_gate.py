#!/usr/bin/env python3
"""Run the declared gate twice under different personal contexts, and refuse to
call the two results equal unless they are.

**Why a differential, and not a flag.** The first version of this control pointed
`ENGRAM_BIN` at a nonexistent path and unset `ENGRAM_URL`, then re-ran the gate
and required "the same result as with the provider present". It could not fail:
nothing in the tracked tree reads either variable, and the gate spawns no agent,
so both runs were identical by construction. A control that cannot fail is worse
than no control, because it is read as evidence.

**What this does instead.** The declared gate runs under two `HOME`s that differ
only in the personal agent context they contain:

* an **empty** home — a bare `mktemp -d`;
* a **decoy** home — the same, populated with the shapes a developer's machine
  carries: `.pi/agent/settings.json`, `.pi/agent/mcp.json`, `.agents/skills/`,
  `.claude/skills/`, `.config/opencode/`, `.engram/`.

If any part of the gate reads the operator's personal context, the two runs
differ, and this script exits non-zero naming the difference. If none does, the
two runs agree and the property holds.

**Both homes are synthetic, which is the point.** Comparing "the operator's real
home" against "an empty one" would be trivially green on CI, where the home is
already bare. A decoy is present on every machine, so the control fires
everywhere: a test that reads `~/.pi` or `~/.agents` fails here on a laptop and
on a runner alike.

**Cost.** The declared gate runs twice. That is the price of a control that can
fail, and it is paid deliberately.

Usage:
    python3 scripts/clean_context_gate.py                # the whole declared gate
    python3 scripts/clean_context_gate.py --half node     # just the Node half
    python3 scripts/clean_context_gate.py --half python   # just the Python half
    python3 scripts/clean_context_gate.py --keep          # keep the temp homes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

FORGE = Path(__file__).resolve().parent.parent

#: Personal agent context, as files. Each entry is what a developer's machine
#: carries and what a verification path must therefore be able to ignore. They
#: are deliberately plausible rather than empty: an empty decoy would prove only
#: that the gate does not read a directory that does not exist.
DECOY_FILES: dict[str, str] = {
    ".pi/agent/settings.json": json.dumps(
        {"defaultModel": "decoy-model", "packages": ["npm:gentle-engram"]}, indent=2),
    ".pi/agent/mcp.json": json.dumps(
        {"mcpServers": {"engram": {"command": "engram", "args": ["mcp"]}}}, indent=2),
    ".pi/agent/gentle-ai/persona.json": json.dumps({"mode": "decoy"}, indent=2),
    ".agents/skills/decoy-skill/SKILL.md": (
        "---\nname: decoy-skill\ndescription: A personal skill that no test may read.\n---\n\n"
        "If a test's outcome changes because this file exists, the verification "
        "path depends on the operator's personal context.\n"),
    ".claude/skills/decoy-skill/SKILL.md": "---\nname: decoy-skill\n---\n\nPersonal skill.\n",
    ".config/opencode/skills/decoy-skill/SKILL.md": "---\nname: decoy-skill\n---\n\nPersonal.\n",
    ".engram/config.json": json.dumps({"data_dir": "/decoy/.engram"}, indent=2),
    ".gemini/skills/decoy-skill/SKILL.md": "---\nname: decoy-skill\n---\n\nPersonal.\n",
    # Valid-looking literature-connector keys in the store `smith keys` writes
    # (`skills/_core/api_keys.py`), private as that store requires: a run that
    # reads them sends a decoy key and diverges from the empty-HOME run.
    ".config/papersmith/keys/asta": "decoy-asta-key-0000000000\n",
    ".config/papersmith/keys/openalex": "decoy-openalex-key-000000\n",
}

#: Decoys that must be private (mode 0600 in a 0700 directory) to be usable.
PRIVATE_DECOYS = (".config/papersmith/keys/asta", ".config/papersmith/keys/openalex")

#: A failing test, in either half's vocabulary. pytest reports `FAILED path::test`
#: and `ERROR path`; `node --test` reports TAP `not ok N - name`. Collected as a
#: set, because two runs that fail the same tests in a different order have not
#: disagreed about anything that matters.
PYTEST_FAILURE = re.compile(r"(?m)^(FAILED|ERROR) (\S+)")
#: pytest reports a subtest failure on its own line, and `^(FAILED|ERROR)` does not
#: match it. Measured the hard way: without this pattern a run reported three
#: failing tests where pytest counted six, so two runs differing only in a
#: subfailure were called equal -- an under-observing control.
PYTEST_SUBFAILURE = re.compile(r"(?m)^SUBFAILED\(([^)]*)\) (\S+)")
#: What `node --test` ACTUALLY prints for a failing test, measured rather than
#: assumed: with stdout redirected to a file -- the condition `run_gate` creates --
#: it prints `\u2716 a suite that fails (0.955203ms)`, never TAP's `not ok N - ...`.
#: The previous pattern matched a shape this repository's own Node never emits, so
#: the Node half compared exit codes alone and its inversion control proved a
#: reader on a line no run produces. The trailing duration is optional because the
#: summary block repeats the name without it in some versions.
NODE_FAILURE = re.compile(r"(?m)^\u2716 (.+?)(?:\s+\([\d.]+ms\))?$")
#: Kept for a run that emits TAP (a different reporter, or a future default).
TAP_FAILURE = re.compile(r"(?m)^not ok \d+ - (.+?)\s*$")

#: Exit codes that mean a stage could not LAUNCH, rather than failed a test: the
#: shell's "not executable" and "not found". A gate that never ran is not evidence
#: of anything, so the control refuses to call such a run "identical" -- before
#: this, a missing interpreter made both halves exit 127 with no failure lines,
#: and the step printed OK while the declared gate could not run at all.
UNRUNNABLE_EXIT_CODES = (126, 127)
UNRUNNABLE_OUTPUT = re.compile(
    r"(?m)^(?:/bin/)?sh: .*(?:No such file or directory|not found)$")


def declared_gate() -> list[list[str]]:
    """The gate's stages, read from `package.json` rather than restated here.

    A restated command string has to be edited alongside the defect it was meant
    to catch, which is the silence `tests/test_forge_gate.py` exists to close.
    """
    scripts = json.loads((FORGE / "package.json").read_text(encoding="utf-8"))["scripts"]
    stages = [stage.strip() for stage in scripts["test:all"].split("&&")]
    return [stage.split() for stage in stages]


def half_stages(half: str) -> list[list[str]]:
    stages = declared_gate()
    if half == "all":
        return stages
    keep = "test:node" if half == "node" else "test:py"
    selected = []
    for stage in stages:
        delegated = re.fullmatch(r"npm (?:run )?(\S+)", " ".join(stage))
        if delegated and delegated.group(1) == keep:
            selected.append(stage)
    if not selected:
        raise SystemExit(f"the declared gate delegates to {keep} nowhere: {stages}")
    return selected


def build_decoy_home(root: Path) -> Path:
    home = root / "decoy-home"
    for relative, content in DECOY_FILES.items():
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if relative in PRIVATE_DECOYS and os.name != "nt":
            path.parent.chmod(0o700)
            path.chmod(0o600)
    return home


def build_empty_home(root: Path) -> Path:
    home = root / "empty-home"
    home.mkdir(parents=True, exist_ok=True)
    return home


def run_gate(home: Path, stages: list[list[str]], log: Path) -> tuple[int, str]:
    """Run every stage under `home`, in order, stopping at the first failure --
    the same `&&` semantics the declared gate itself has."""
    environment = dict(os.environ, HOME=str(home))
    environment.pop("XDG_CONFIG_HOME", None)
    lines = [f"# HOME={home}"]
    code = 0
    with log.open("w", encoding="utf-8") as handle:
        for stage in stages:
            handle.write(f"# $ {' '.join(stage)}\n")
            handle.flush()
            done = subprocess.run(stage, cwd=str(FORGE), env=environment,
                                  stdout=handle, stderr=subprocess.STDOUT, text=True)
            lines.append(f"# $ {' '.join(stage)} -> exit {done.returncode}")
            code = done.returncode
            if code != 0:
                break
    return code, "\n".join(lines)


def failure_signature(log_text: str) -> list[str]:
    """The set of tests that failed, in either half's vocabulary.

    Derived from the output rather than from a count: two runs that both fail
    three tests, but not the same three, have disagreed, and a count would call
    them equal.
    """
    found = {f"{kind} {target}" for kind, target in PYTEST_FAILURE.findall(log_text)}
    found |= {f"SUBFAILED {subject} {test}" for subject, test in PYTEST_SUBFAILURE.findall(log_text)}
    # The summary block's own header (`x failing tests:`) is not a test name; it
    # would otherwise be reported as a failing test that never existed.
    found |= {f"node {name}" for name in NODE_FAILURE.findall(log_text)
              if not name.endswith(":")}
    found |= {f"not ok {name}" for name in TAP_FAILURE.findall(log_text)}
    return sorted(found)


#: The most lines of a failing run's own explanation the report repeats.
DETAIL_LINES = 40


def summary_name(line: str) -> str | None:
    """The failure a pytest short-summary line reports, spelled as
    `failure_signature` spells it, or None for any other line."""
    match = PYTEST_FAILURE.match(line)
    if match:
        return f"{match[1]} {match[2]}"
    match = PYTEST_SUBFAILURE.match(line)
    if match:
        return f"SUBFAILED {match[1]} {match[2]}"
    return None


def failure_details(log_text: str, first: frozenset[str] = frozenset()) -> list[str]:
    """What the failing tests said: pytest's short-summary entries that carry a
    message (``FAILED x - AssertionError: ...``, a subtest's ``SUBFAILED(...)
    x - ...``) and its ``E`` assertion lines, at most ``DETAIL_LINES`` of them.
    The log itself lives in a temporary home that is removed, so without these
    a CI-only failure names a test and never says why it failed.

    The entries of the failures in `first` (spelled as `failure_signature`
    spells them) lead, whole: on CI pytest prints a multi-line message in full,
    its later lines unprefixed. The rest keep their log order. While `main` is
    red, both homes fail other tests whose lines come first in the log and
    would otherwise spend the cap before the failure that differs."""
    leading: list[str] = []
    rest: list[str] = []
    continuing = False
    for line in (raw.rstrip() for raw in log_text.splitlines()):
        name = summary_name(line)
        if name is not None:
            continuing = name in first and " - " in line
            if " - " in line:
                (leading if continuing else rest).append(line)
        elif line.startswith("E   "):
            continuing = False
            rest.append(line)
        elif continuing and line and not line.startswith(("=", "_")):
            leading.append(line)
        else:
            continuing = False
    return (leading + rest)[:DETAIL_LINES]


def print_failure_details(home: str, log_text: str, first: frozenset[str] = frozenset()) -> None:
    """Print `failure_details` of one home's run, under that home's name.

    Called for every home whose run failed, whether or not the two homes
    agree: a test that fails under one home only is the failure this control
    exists for, and naming it without what it said leaves it unexplained.
    `first` holds the failures only this home had."""
    details = failure_details(log_text, first)
    if details:
        print(f"\n[clean-context] what the failing tests said under the {home} home:")
        for line in details:
            print(f"  {line}")


def gate_could_not_run(log_text: str, code: int) -> bool:
    """Whether a stage failed to launch, rather than failed a test.

    Both are non-zero exits and only one of them is a test result. A differential
    over a gate that never started proves nothing about personal context, and
    reporting it as agreement is a false green.
    """
    if code in UNRUNNABLE_EXIT_CODES:
        return True
    return bool(UNRUNNABLE_OUTPUT.search(log_text))


def compare(left: dict, right: dict) -> list[str]:
    """Every way two runs disagree, as human-readable lines. Empty means equal.

    Takes dicts (`{"home", "code", "failures"}`) rather than reading files, so
    the inversion control below drives this exact function against a planted
    disagreement instead of re-implementing the comparison.
    """
    differences = []
    if left["code"] != right["code"]:
        differences.append(
            f"exit code differs: {left['home']} -> {left['code']}, "
            f"{right['home']} -> {right['code']}")
    if left.get("unrunnable") or right.get("unrunnable"):
        differences.append(
            "the declared gate could not run in this environment "
            f"(empty: {left.get('unrunnable')}, decoy: {right.get('unrunnable')}). "
            "Two runs of a gate that never started agree about nothing, so this "
            "is a failure of the control rather than a clean result")
    only_left = sorted(set(left["failures"]) - set(right["failures"]))
    only_right = sorted(set(right["failures"]) - set(left["failures"]))
    for name in only_left:
        differences.append(f"fails only under {left['home']}: {name}")
    for name in only_right:
        differences.append(f"fails only under {right['home']}: {name}")
    return differences


def baseline_failures(empty: dict) -> list[str]:
    """Why the empty-home run does not stand as a clean pass of the gate itself.

    `compare` only reports disagreement, so a suite that fails the same way
    under both homes is "equal" there. That is right for the comparator and
    wrong for a step that replaces a plain run of the suite: the empty home is
    the machine with no personal context, which is the one CI must be green on.
    """
    if empty["code"] == 0:
        return []
    named = "; ".join(empty["failures"]) or "no failing test was named"
    return [f"the gate fails under the {empty['home']} home (exit {empty['code']}): {named}"]


def remove_tree(root: Path) -> None:
    """Remove the temporary homes, and say so if anything is left behind.

    A gate run can leave a read-only file under HOME, which `rmtree` cannot
    remove without write permission on its directory; `ignore_errors` hid that.
    """
    shutil.rmtree(root, ignore_errors=True)
    if not root.exists():
        return
    for path in [root, *root.rglob("*")]:
        if not path.is_symlink():
            path.chmod(0o700 if path.is_dir() else 0o600)
    shutil.rmtree(root, ignore_errors=True)
    if root.exists():
        print(f"[clean-context] warning: could not remove {root}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--half", choices=("all", "node", "python"), default="all")
    parser.add_argument("--keep", action="store_true",
                        help="keep the temporary homes and logs for inspection")
    args = parser.parse_args(argv)

    stages = half_stages(args.half)
    # A cancelled CI job sends SIGTERM; without a handler the `finally` below
    # never runs and the temporary homes stay on the runner.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    root = Path(tempfile.mkdtemp(prefix="clean-context-gate-"))
    try:
        empty = build_empty_home(root)
        decoy = build_decoy_home(root)
        print(f"[clean-context] gate: {' && '.join(' '.join(s) for s in stages)}")
        print(f"[clean-context] homes: {empty} (empty) vs {decoy} (decoy)")

        empty_code, empty_note = run_gate(empty, stages, root / "empty.log")
        decoy_code, decoy_note = run_gate(decoy, stages, root / "decoy.log")
        logs = {home: (root / f"{home}.log").read_text("utf-8") for home in ("empty", "decoy")}
        empty_result = {"home": "empty", "code": empty_code,
                        "failures": failure_signature(logs["empty"]),
                        "unrunnable": gate_could_not_run(logs["empty"], empty_code)}
        decoy_result = {"home": "decoy", "code": decoy_code,
                        "failures": failure_signature(logs["decoy"]),
                        "unrunnable": gate_could_not_run(logs["decoy"], decoy_code)}

        print(empty_note)
        print(decoy_note)
        for result in (empty_result, decoy_result):
            state = "COULD NOT RUN" if result["unrunnable"] else f"exit {result['code']}"
            print(f"[clean-context] {result['home']}: {state}, "
                  f"{len(result['failures'])} failing test(s)")

        differences = compare(empty_result, decoy_result)
        if differences:
            print("\n[clean-context] FAIL: the gate's result depends on the "
                  "personal context it ran under, so it does not verify a machine "
                  "that has none:")
            for line in differences:
                print(f"  {line}")
            for result, other in ((empty_result, decoy_result), (decoy_result, empty_result)):
                if result["code"] != 0:
                    only_here = frozenset(result["failures"]) - frozenset(other["failures"])
                    print_failure_details(result["home"], logs[result["home"]], only_here)
            return 1

        failures = baseline_failures(empty_result)
        if failures:
            print("\n[clean-context] FAIL: the gate does not pass on a machine "
                  "with no personal context:")
            for line in failures:
                print(f"  {line}")
            print_failure_details("empty", logs["empty"])
            return 1

        print("\n[clean-context] OK: the gate's result is identical under an "
              "empty home and under one carrying personal agent context. The "
              "verification path does not read the operator's context.")
        return 0
    finally:
        if args.keep:
            print(f"[clean-context] kept: {root}")
        else:
            remove_tree(root)


if __name__ == "__main__":
    sys.exit(main())
