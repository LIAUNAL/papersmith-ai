#!/usr/bin/env python3
"""The CLI front door for forge-owned remote execution.

This module is the top of this skill's own dependency chain —
`remote_cli -> packer -> ledger -> adapter` — and it is deliberately the
ONLY module in that chain that names a command-line entry point, parses
`--target`/`--entrypoint`/`--worker` arguments, and decides what counts as
a submittable path in this forge's own repository layout. Everything below
it (`packer.py`, `ledger.py`, `adapter.py`) stays blind to both concerns:
they take paths, ids and dicts as arguments and never ask where an argument
came from or what kind of file it names.

`submit`, `status`, `poll`, `fetch` and `reconcile` are the five commands.
`status` reports the fold and calls no adapter at all — it never resolves
anything, only renders what the ledger already says. `poll` and `fetch`
call the adapter; `fetch` is the only command that ever writes an artifact
to disk, and it does so through a materialize-then-rename sequence so a
crash never leaves a false `returned` event behind (see `cmd_fetch`).
`reconcile` compares the ledger against `adapter.list_active()` in both
directions and reports the difference; it never auto-adopts a remote orphan
and never auto-resolves a local one — `--resolve` is the one human-invoked
exception, and even then it only ever appends `errored`, never `returned`
or `submitted`.

`submit`, `poll`, `fetch` and `reconcile` construct their adapter with a
credential PROVIDER, never a value and never a pre-built mapping this
module would have to assemble itself: `credentials.provider()` returns a
callable an adapter calls lazily, by worker id, the first time it actually
needs one. `--credential-dir` is an override only, for tests and
already-materialized credentials — the default is lazy materialization,
and no target configuration file is ever consulted for a credential path.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Sequence


def _load_sibling(module_name: str, filename: str):
    """Path-import a sibling module from this same directory, reusing an
    already-loaded copy under `module_name` when one exists.

    Same technique and same correctness reason as `packer.py`'s own
    `_load_sibling`: this skill's scripts are not a package, so a
    cross-module dependency goes by file path, and checking `sys.modules`
    first is what keeps `isinstance` checks against `ADAPTER.Adapter`
    working when this module and `packer.py` both load `adapter.py` — a
    second, separately exec'd copy would define a second, distinct
    `Adapter` class with the same name.
    """
    if module_name in sys.modules:
        return sys.modules[module_name]
    script = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


LEDGER = _load_sibling("remote_execution_ledger", "ledger.py")
ADAPTER = _load_sibling("remote_execution_adapter", "adapter.py")
PACKER = _load_sibling("remote_execution_packer", "packer.py")

# Loaded AFTER adapter.py above, for the same sys.modules-reuse reason
# documented next to PACKER's own load above: `credentials.py`'s own
# `ADAPTER.CredentialHandle` has to be the exact same class every other
# module in this chain already loaded, not a second, separately exec'd
# copy of the same name.
CREDENTIALS = _load_sibling("remote_execution_credentials", "credentials.py")

# Loaded the same way, for the same reason: `jobfolder.py`'s own `ADAPTER`
# (it calls `ADAPTER.resolve_metadata()`) has to be this exact module
# object too.
JOBFOLDER = _load_sibling("remote_execution_jobfolder", "jobfolder.py")

# `smoke record`'s verdict comes from the SAME predicate T10's `merge()`
# uses — never a second, independently written completeness check here.
SHARD_IO = _load_sibling("remote_execution_shard_io", "shard_io.py")

# What `generate-jobs` and `generate-job --dataset` derive from the target's
# and the workspace's own declarations (remote-preflight S2, S3).
JOB_PLAN = _load_sibling("remote_execution_job_plan", "job_plan.py")


def _load_source_digest() -> Callable[[Path, str], str]:
    """Path-import `source_digest()` from proposal-implementation's digest kit.

    A `submitted` event's `sourceDigest` has to be the SAME hash
    proposal-implementation's own admissibility and verify machinery already
    treats as canonical for a given source tree — a second, independently
    written hash here would be safe only until the day the two quietly
    drifted apart, at which point every submission this CLI records would
    carry a digest nothing else in the repository recognizes as current.

    `assets/kit/nb/report_digest.py` is the file this reaches for, not
    `implementation_cli.py`: it is the lightweight, stdlib-only half of the
    pair proposal-implementation's own test suite already holds to
    byte-for-byte parity with the CLI's copy (`ReportDigestJoinTests` in
    `tests/test_proposal_implementation.py`), and loading it costs nothing
    but `hashlib` and `pathlib` — not the whole argparse-driven
    proposal-implementation CLI, which this module never touches. This IS a
    dependency reaching outside this skill's own
    `remote_cli -> packer -> ledger -> adapter` chain, and this function is
    the one place in the whole skill that reaches for it — `fold()`'s own
    docstring (`ledger.py`) already anticipates exactly this: it says the
    real `source_digest()` "lives in proposal-implementation's own module"
    and must be supplied by a caller that already knows how to compute one.
    This function is that caller, called only when `submit` actually needs
    a digest, never at import time.
    """
    module_name = "remote_execution_source_digest_kit"
    if module_name in sys.modules:
        return sys.modules[module_name].source_digest
    script = (
        Path(__file__).resolve().parents[2]
        / "proposal-implementation"
        / "assets"
        / "kit"
        / "nb"
        / "report_digest.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise RemoteCLIError(
            f"the source-digest kit is not where this expects it: {script}. "
            "If it moved, this loader is the one place that has to follow it."
        )
    module = importlib.util.module_from_spec(spec)
    # Registered only once it has actually run. Publishing the module before
    # executing it is the usual shape, and it is wrong here: a failed exec
    # would leave an empty module under this name, and every later call would
    # take the cache branch above and raise AttributeError on a module that
    # never loaded — reporting a missing attribute instead of the real fault,
    # for the rest of the process. Registering after means a failure is
    # retryable and always reports itself.
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module.source_digest


class RemoteCLIError(Exception):
    """Something this CLI's own validation refused before doing any work."""


class PathGuardError(RemoteCLIError):
    """An entrypoint failed this forge's own file-kind policy for what may run remotely."""


class AuthorizationError(RemoteCLIError):
    """A non-rehearsal `submit` refused for lack of a matching `gate`
    transition record (design §4, domain launch-authorization) -- a
    SEPARATE and INDEPENDENT precondition from `ConsentError` below, never
    a payload this class shares with it.

    `campaign_consent_token()` binds *what* is launched and is computed
    entirely from this invocation's own argv -- which is exactly why it can
    never be an authorization: any caller who can run `submit` can also
    compute its own consent. This error exists for the other half:
    *someone with standing said yes, at this readiness, for this reason* --
    a fact that has to be recorded before, and independently of, the
    launching invocation, never derivable from it.
    """


class ReadinessError(AuthorizationError):
    """A non-rehearsal CAMPAIGN `submit` refused `CAMPAIGN_WORKERS_NOT_READY`
    (S2, parallel campaigns): the distribution assigns units to at least one
    worker with no passing rehearsal of its own at the job's current pin.
    Readiness is per worker (`rehearse-each-account`): a campaign `gate`
    record binds pin, entrypoint and units, never workers, so the accounts
    a campaign actually spends are checked here, once `packer.distribute()`
    has named them and before any `adapter.submit()`. `workers` holds the
    workers that still need a rehearsal, in distribution order.
    """

    def __init__(self, message: str, workers: Sequence[str]) -> None:
        super().__init__(message)
        self.workers = tuple(workers)


CAMPAIGN_WORKERS_NOT_READY = "CAMPAIGN_WORKERS_NOT_READY"
DUPLICATE_SUBMISSION_ID = "DUPLICATE_SUBMISSION_ID"
# A campaign share whose `submitted` event (which now records the share's
# units) would not fit one ledger line: refused BEFORE any submission, since
# a submission the ledger cannot record is the one outcome it exists to
# rule out.
LEDGER_EVENT_TOO_LARGE = "LEDGER_EVENT_TOO_LARGE"
# A continuation unit whose earlier output was produced on a worker other
# than the one this campaign places it on (kernel-carry S4): a private job's
# output is only verified to carry within its own account, so the campaign
# is refused before any submission. `--no-carry` starts such units fresh.
CARRY_WORKER_MISMATCH = "CARRY_WORKER_MISMATCH"

# Where `_carry_evidence()` notes, on its own copy of a `submitted` event,
# the local directory that submission's output was fetched to. Never written
# to the ledger: `carriedFrom` keeps only `submissionId` and `ref`.
_CARRY_ARTIFACT_KEY = "_carryArtifact"

# The longest submission id the size pre-check assumes a backend may answer
# with: generous next to every id shape shipped today (`<owner>/<slug>`,
# `colab:<owner>/psmith-...`), so the check never passes a share whose real
# event would then fail to append.
_SUBMISSION_ID_BUDGET_CHARS = 256


class DiagramValidationError(RemoteCLIError):
    """ANY `submit` (rehearsal or full) refused because the product holds an
    approval (`AGREED.md`, `Experimental_AGREED.md`) whose experiment diagram
    the operator has not validated -- in the dashboard ("Validar diagrama") or
    by approving it explicitly in the agent chat (`diagram_cli.py validate`) --
    or validated and then drew again. Both routes write the one record this
    reads (`skills/experiment-diagrams/scripts/diagram_cli.py`,
    `write_validation`)."""


class ConsentError(RemoteCLIError):
    """ANY `submit` refused for lack of, or a mismatch in, the consent
    token this invocation needs -- campaign, single send, and rehearsal
    alike (Finding 3; Decisions 4, 5; and this phase's own correction: the
    original gate fired only for campaign mode, which let a plain `submit`
    or `submit --smoke` reach `adapter.submit()` with nobody having been
    asked -- the exact launch the user's complaint named).

    Raised BEFORE `packer.select()`/`packer.plan()`/`packer.distribute()`
    runs -- no adapter health read, no plan, no quota spent, no ledger
    line appended -- for exactly the same "refuse while refusing still
    costs nothing" reason `_gate_job_folder_pin()` already refuses ahead
    of it.
    """


NOTEBOOKS_DIRNAME = "Notebooks"
NOTEBOOK_SUFFIX = ".ipynb"
LEDGER_DIRNAME = ".remote-execution"
LEDGER_FILENAME = "ledger.jsonl"
QUARANTINE_DIRNAME = "quarantine"

# A rehearsal's (`fetch --smoke`) landing directory -- distinct from
# QUARANTINE_DIRNAME above, which is for a REAL fetch judged not current.
# Before this existed, `fetch --smoke` landed wherever `--dest` said, the
# same tree a shard reader enumerates, and nothing ever quarantined it.
REHEARSAL_DIRNAME = "rehearsal"
PARTIAL_SUFFIX = ".partial"

# Where `fetch` KEEPS the bytes of a run that came back without a complete
# result -- failed, timed out, reclaimed, or still running: under
# `<product>/.remote-execution/partial/<submissionId>/<UTC stamp>/`, one
# directory per fetch, never overwritten and never deleted by this CLI.
# Outside `Results/shards/` for the same reason quarantine is: nothing that
# enumerates results can reach an incomplete one by accident. The operator
# (or a resume) reads it; `remaining --unit-field` counts the per-unit
# records it holds.
KEPT_PARTIAL_DIRNAME = "partial"

# The run states after which an incomplete fetch is RECORDED, as an
# `errored` event naming the kept bytes: the run is over, and it did not
# produce a complete result. `unknown` is the seam's state for a session
# the service no longer reports -- a reclaimed or vanished one.
_UNFINISHED_TERMINAL_STATES = ("failed", "unknown")
TOOLS_DIRNAME = "tools"
RUN_CONFIG_FILENAME = "run-config.json"

# `smoke.jsonl` — a DISTINCT file from `ledger.jsonl`, beside it in the
# same product's `.remote-execution/` directory, appended through the
# same `LEDGER.append()`. A fourth `kind` inside `ledger.jsonl` was
# rejected: `fold()` indexes `latest[entrypoint]`, so a smoke submission
# recorded there would silently reclassify a real run as superseded.
# `fold()` never reads this file, so that is structurally impossible. See
# `SKILL.md`'s "Smoke" section for the full rationale.
SMOKE_LEDGER_FILENAME = "smoke.jsonl"

# The `kind` a `smoke record` verdict carries inside `smoke.jsonl` (which
# also carries the ordinary `submitted` events a smoke SUBMISSION writes —
# see `cmd_submit`). Never folded, so free of the fourth-kind constraint.
SMOKE_RESULT_KIND = "smokeResult"


def _subcommand_option_strings(command: str) -> frozenset[str]:
    """The exact `--flag` strings `_build_parser()` declares for `command`'s
    own subparser — read from the parser itself, never a second,
    hand-maintained list a refusal message could drift from the CLI it
    describes (Finding 4 case C; Decision 13c).

    Built fresh from `_build_parser()` rather than cached: this only runs
    on `product_for()`'s own refusal path, never on a resolved call, so
    the cost of rebuilding the whole parser is paid at most once per
    refusal, never on the path that matters for speed.
    """
    parser = _build_parser()
    subparsers_action = next(
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    subparser = subparsers_action.choices[command]
    return frozenset(subparser._option_string_actions)


def product_for(
    target: Path,
    entrypoint: str | Path,
    explicit: str | None = None,
    *,
    command: str | None = None,
) -> str:
    """Resolve which product's ledger `entrypoint` belongs to — explicitly,
    never guessed. Replaces `name_for()`, reusing its same resolve-first
    discipline (resolve first, then read path components past `target`) so
    `status`, `fetch`'s quarantine path, and `reconcile`'s ledger selection
    keep calling the SAME derivation rather than each growing its own copy
    that could quietly disagree.

    `command` names the CALLING subcommand (`"submit"`, `"status"`,
    `"distribute"`, `"fetch"`, `"reconcile"`) and affects nothing but the
    wording of the refusal at the bottom of this function (Finding 4 case
    C). Only `submit` (and `generate-job`, which never calls this
    function) declares a `--product` override; `status`, `distribute`,
    `fetch` and `reconcile` do not. All five used to reach the SAME
    hand-written "no explicit --product" refusal regardless of which
    subcommand asked, which sent a `status` caller looking for a flag
    `status`'s own parser never accepts — a remedy that cannot be
    performed is worse than a refusal that names nothing, because it
    costs the caller the attempt. The remedy is now derived from
    `_build_parser()`'s own declared flags for `command`, never
    hand-written prose: `--product` is named only when `command`'s own
    subparser actually declares it. Omitted (`None`), the refusal never
    names `--product` either — the same conservative choice as a
    subcommand confirmed not to declare it, since an unknown caller's
    flags cannot be confirmed at all.

    Four steps, in this fixed order, mirroring the fold's own treatment of
    an unrecognized event `kind`: an ambiguous input is refused, not
    silently mapped to the least-wrong guess.

    1. `explicit` — a caller-supplied `--product` — wins outright, over
       both steps below, whatever the entrypoint's own shape says.
    2. Else, for the job-folder shape (`<target>/tools/<service>/
       <job-name>/*.ipynb`), the `product` field declared in that job's own
       `run-config.json`, read beside the entrypoint. Absent, unreadable,
       or missing that field falls through to step 3 rather than refusing
       immediately — a job-folder path is only refused once every earlier
       step has genuinely found nothing.
    3. Else, for the legacy shape (`<target>/<Name>/Notebooks/**.ipynb`),
       `<Name>` — the first path component past `target` — exactly as
       `name_for()` always derived it.
    4. Else: refused. `TOOLS_DIRNAME` ("tools") is a forge-layout constant,
       not a product, and this function never derives it as one — a
       job-folder path with no declared product is refused here rather
       than falling back to `parts[0]` the way the legacy shape does.

    Whatever step resolves a product, the result is validated the same way
    regardless of source: it must name an existing directory directly
    under `target`, and it must not be `TOOLS_DIRNAME` itself — an explicit
    `--product tools` or a `run-config.json` misdeclaring `"product":
    "tools"` is refused exactly like an unresolved one, because `tools` is
    forge layout, never a product this skill's ledger can shard by.

    This forge's real target has hosted more than one product at once;
    nothing in this skill is allowed to assume which one a caller means —
    a product is always read off a path, a flag, or a job's own recorded
    config, never typed in as a bare string by this function itself.
    """
    resolved = Path(entrypoint).resolve()
    try:
        relative = resolved.relative_to(target)
    except ValueError:
        raise RemoteCLIError(
            f"cannot resolve a product: {resolved} does not stay under "
            f"target {target} at all"
        ) from None
    if not relative.parts:
        raise RemoteCLIError(
            f"cannot resolve a product: {resolved} equals target {target} "
            "itself"
        )

    parts = relative.parts
    product = explicit

    if product is None and len(parts) == 4 and parts[0] == TOOLS_DIRNAME:
        run_config_path = resolved.parent / RUN_CONFIG_FILENAME
        if run_config_path.is_file():
            try:
                run_config = json.loads(
                    run_config_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                run_config = None
            declared = (
                run_config.get("product")
                if isinstance(run_config, dict)
                else None
            )
            if isinstance(declared, str) and declared:
                product = declared

    if product is None and len(parts) >= 3 and parts[1] == NOTEBOOKS_DIRNAME:
        product = parts[0]

    if product is None:
        can_override = (
            command is not None and "--product" in _subcommand_option_strings(command)
        )
        if can_override:
            # Only a subcommand whose OWN parser actually declares
            # `--product` (confirmed via `_subcommand_option_strings()`,
            # never assumed) gets a message naming it as a remedy.
            reason = (
                "no explicit --product, no product declared in its "
                "run-config.json, and the legacy <Name>/Notebooks/ shape "
                "does not apply"
            )
        else:
            # `command` names a subcommand that does not declare
            # `--product` (e.g. `status`), or `command` is unknown
            # (`None`) and therefore cannot be confirmed to declare it
            # either way. Either way, the message never names a flag the
            # caller cannot actually type: a remedy that cannot be
            # performed is worse than a refusal that names nothing.
            reason = (
                "no product declared in its run-config.json, and the "
                "legacy <Name>/Notebooks/ shape does not apply"
            )
        raise RemoteCLIError(f"cannot resolve a product for {resolved}: {reason}")

    if product == TOOLS_DIRNAME:
        raise RemoteCLIError(
            f"refusing product {product!r}: {TOOLS_DIRNAME!r} is a "
            "forge-layout constant, never a product"
        )

    product_dir = target / product
    if not product_dir.is_dir():
        raise RemoteCLIError(
            f"refusing product {product!r}: {product_dir} is not an "
            "existing directory"
        )

    return product


def _job_folder_staleness(resolved_entrypoint: Path) -> dict | None:
    """Route `resolved_entrypoint` through `jobfolder.read()` — the single
    staleness reader design #744 §4 mandates — whenever it sits beside a
    `run-config.json`, i.e. the job-folder shape. Every command that
    touches an already-generated job folder (`submit`, `status`, `fetch`,
    `reconcile`) calls this so staleness is reported alongside whatever
    else that command already reports, never recomputed a second way.

    Returns `None` for the legacy shape, which has no job folder and
    therefore nothing to report staleness about, and for a
    `run-config.json` `jobfolder.read()` cannot make sense of (missing a
    required field, invalid JSON) — the SAME "falls through cleanly"
    tolerance `product_for()`'s own narrower run-config lookup already
    applies one step up (see its docstring, step 2): a command already
    resilient to an incomplete run-config.json does not become stricter
    just because staleness reporting was added beside it.
    """
    job_dir = resolved_entrypoint.parent
    if not (job_dir / RUN_CONFIG_FILENAME).is_file():
        return None
    try:
        return dict(JOBFOLDER.read(job_dir).staleness)
    except JOBFOLDER.JobFolderError:
        return None


def _job_folder_commit(resolved_entrypoint: Path) -> str | None:
    """The pin a campaign consent token binds to (Decision 4's "commit-state
    threat-matrix case"): the job folder's OWN declared `commit`, read the
    SAME way `_gate_job_folder_pin()` reads it — through `JOBFOLDER.read()`,
    never a second, independent parse of `run-config.json`.

    `None` for the legacy shape (no job folder at all) and for a
    `run-config.json` `read()` cannot make sense of — the SAME two-path
    tolerance `_job_folder_staleness()` already applies one function up,
    for the same reason: a discriminator this narrow does not need to be
    stricter than the staleness reporter sitting right beside it.
    `campaign_consent_token()` hashes `None` exactly like any other value;
    it is part of the payload here, not a special case this function has
    to swallow.
    """
    job_dir = resolved_entrypoint.parent
    if not (job_dir / RUN_CONFIG_FILENAME).is_file():
        return None
    try:
        return JOBFOLDER.read(job_dir).run_config["commit"]
    except JOBFOLDER.JobFolderError:
        return None


def campaign_consent_token(
    *, pin_commit: str | None, relative_entrypoint: str | Path, units: Sequence[str],
    worker: str | None = None,
) -> str:
    """The ONE digest both `distribute` (which prints it) and `submit`
    (which verifies it) compute — a second, independently written hash
    here would be safe only until the day the two quietly drifted apart,
    at which point a legitimately-minted token would refuse and nobody
    could say why (Decision 4: "shared token-derivation function used by
    both distribute's print and submit's verify").

    `sha256(pin commit, relative entrypoint, ordered unit list[, worker])`.
    Every input in the payload is load-bearing:

    - `pin_commit` binds the token to the exact code a runner would
      clone. A job that re-pins to a different commit changes this value,
      and a token minted at the old pin no longer authorizes anything —
      self-expiring by construction, never by a staleness check this
      function would have to remember to run.
    - `relative_entrypoint` keeps a token minted for one product's
      campaign from ever authorizing a different one, even by accident —
      the cross-campaign case Decision 4 names explicitly.
    - `units`, hashed IN THE GIVEN ORDER, never sorted and never
      deduplicated: one approval covers the EXACT ordered unit list of
      that invocation (Decision 5). A unit added, removed, or reordered
      changes this payload and therefore the digest — there is no looser
      notion of "the same campaign" for this function to fall back to.
    - `worker`, present in the payload ONLY when the caller explicitly
      named one (`submit --worker <id>`, single-send, never `--unit`, never
      auto-selected) — see `_verify_launch_consent`'s own docstring for why
      an EXPLICIT worker must bind and an ABSENT one must not. Omitted
      entirely (not `null`, not an empty string) when no worker was named,
      so a campaign or auto-select derivation is byte-for-byte identical to
      before this parameter existed — this is what keeps
      `test_campaign_token_derivation_byte_identical_to_pre_change` true.

    Deliberately NOT a `--yes` boolean and deliberately not looked up
    anywhere but the arguments handed to it: this function reads no
    file, no environment variable, and no ledger line. Nothing it computes
    is ever written back to disk by this module — the whole reason a
    token is never persisted is that nothing downstream of this function
    ever tries to.
    """
    fields: dict[str, object] = {
        "pin": pin_commit,
        "entrypoint": str(relative_entrypoint),
        "units": list(units),
    }
    if worker is not None:
        fields["worker"] = worker
    payload = json.dumps(fields, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_launch_consent(
    *, consent: str | None, expected_consent: str, units: Sequence[str] | None,
    worker: str | None = None,
) -> None:
    """The ONE consent check every `submit` invocation goes through --
    campaign, single send, and rehearsal alike. Correction to Finding 3:
    the original gate fired only when `units` was truthy, which left a
    plain `submit` (no `--unit`, with or without `--smoke`) reaching
    `adapter.submit()` with NOBODY asked -- the exact launch the user's
    own complaint named. The fix is not a second case bolted onto the
    first; it is the same check, called unconditionally, for every mode,
    written as a structural invariant rather than a list of gated cases:
    nothing reaches `packer.select()`/`packer.plan()`/`packer.distribute()`
    -- and therefore never `adapter.submit()` -- without a token that
    matches what is being sent.

    `expected_consent` is always `campaign_consent_token()`'s own output
    -- ONE derivation, ONE shape, for BOTH campaign and single-send
    tokens: an empty ordered unit list is itself a legitimate input to
    that function, not a reason to invent a second one.

    CORRECTED (F2): the worker binds into that payload when, and only
    when, the caller explicitly named one with `--worker` at mint time.
    The prior rationale here claimed "the account is the caller's own
    explicit choice and does not need the token's protection to be
    honest" -- that was false the moment it was tested: three different
    real, named `--worker <account>` invocations on this machine all
    minted the IDENTICAL token, because none of them fed the worker into
    the digest at all. A token minted while approving one named account
    was therefore valid for launching on ANY account, which is exactly the
    cross-account authorization gap the token exists to close. With no
    `--worker` (campaign mode, or auto-select single-send), the account is
    chosen by `packer.select()`/`packer.distribute()` AFTER consent would
    be given, so binding it is still structurally impossible in
    advance -- that half of the old rationale survives; only the
    named-worker half was wrong.

    Missing consent for CAMPAIGN mode (`units` truthy) points the caller
    at `distribute --unit ...`, which mints and prints the token -- there
    is no other place a campaign token could come from.

    Missing consent for SINGLE-SEND mode (`units` empty, including a
    smoke rehearsal) has no equivalent minting command: there is no
    `distribute` step for one entrypoint. So THIS function prints the
    exact expected token itself, inside the refusal message. That is safe
    ONLY because the call that reaches this refusal never gets past it:
    no `packer.select()`/`packer.plan()`, no `adapter.submit()`, nothing
    launched. A token printed by a run that submitted nothing can never
    BE the approval it names -- only a second, deliberate invocation that
    copies it back into `--consent` is.
    """
    if consent is None:
        if units:
            raise ConsentError(
                "campaign submit refuses without --consent: run "
                "`distribute --unit ...` first, for this exact pin, "
                "entrypoint and ordered unit list, and pass back the "
                "token it prints. Nothing is launched without an "
                "explicit, per-campaign approval carried by this "
                "invocation's own argv."
            )
        account_note = (
            f" This token authorizes account {worker!r} only."
            if worker is not None
            else " This token names no single account -- it authorizes "
            "whichever account is chosen at launch time."
        )
        raise ConsentError(
            "submit refuses without --consent: nothing is launched "
            "without an explicit, per-launch approval carried by this "
            "invocation's own argv, and a single send has no "
            "`distribute` step to mint one ahead of time. This exact "
            "invocation submitted nothing -- no plan, no adapter call, "
            "no ledger line -- so printing the token it would need is "
            f"safe: re-run with --consent {expected_consent} to approve "
            "this exact pin and entrypoint." + account_note + " The token "
            "above is NOT itself the approval -- only a second, "
            "deliberate invocation that passes it back is."
        )
    if consent != expected_consent:
        raise ConsentError(
            "consent token does not match this invocation's pin, "
            "entrypoint, ordered unit list, or named worker: a token "
            "authorizes one exact launch only -- on the one account it "
            "named, when it named one -- and it stops authorizing the "
            "instant the pin, entrypoint, unit list, or worker moves -- "
            + (
                "mint a fresh one with `distribute --unit ...`"
                if units
                else "re-run with no --consent to see the token this "
                "exact invocation needs"
            )
        )


def _load_impl_position():
    """Path-import `_core/implementation/impl_position.py` -- the ONE fold
    of `.implementation/position.jsonl` `_verify_launch_authorization()`
    below is allowed to read.

    Same `sys.modules`-reuse technique as every other `_load_sibling` load
    in this module, extended one skill boundary further: `impl_position.py`
    lives outside this skill's own `remote_cli -> packer -> ledger ->
    adapter` chain, in neutral ground `proposal-implementation` already
    reaches into the same way (`implementation_cli.py`'s own `import
    impl_position`, after a `sys.path.insert` of this exact directory).
    Reusing an already-loaded copy under the SAME `sys.modules` key that
    caller uses is not merely an optimization here: `impl_position.py`
    defines no class either module would need `isinstance` for, but
    re-executing it under a second key would still leave two modules
    disagreeing about `sys.modules["impl_position"]`, which is the one
    piece of global state a caller elsewhere in the same process might
    already depend on.

    `_core/implementation/` is inserted onto `sys.path` before the exec,
    because `impl_position.py` itself does `from impl_refusals import
    Refused` with no path setup of its own -- it is written to be reached
    the way `implementation_cli.py` reaches it, and a spec-loaded exec
    still runs that same top-level import line, which needs
    `impl_refusals` importable at that moment.

    Loaded lazily, called only from inside `_verify_launch_authorization()`
    -- same discipline `_load_source_digest()` documents for its own
    cross-skill reach: every OTHER `submit` path (a rehearsal, a legacy
    entrypoint, campaign mode -- see that function's own docstring) never
    needs this module at all, so importing it at module load time would
    cost every caller a `sys.path` mutation and a file read they may never
    use.
    """
    module_name = "impl_position"
    if module_name in sys.modules:
        return sys.modules[module_name]
    core_dir = Path(__file__).resolve().parents[2] / "_core" / "implementation"
    if str(core_dir) not in sys.path:
        sys.path.insert(0, str(core_dir))
    script = core_dir / "impl_position.py"
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _verify_launch_authorization(
    *,
    smoke: bool,
    target: Path,
    product: str,
    pin_commit: str | None,
    relative_entrypoint: Path,
    units: Sequence[str] | None,
    worker: str | None,
) -> None:
    """The SECOND, independent precondition `cmd_submit` enforces (design
    §4.2) -- separate from `_verify_launch_consent()` above, never a second
    check bolted onto that one's payload.

    The finding this repairs: `_verify_launch_consent()` refuses every
    unauthorized launch correctly, but its refusal message prints back the
    exact token the caller passes in on the next call -- `campaign_consent_
    token()` is a sha256 over THIS INVOCATION'S OWN public argv, so any
    caller who can run `submit` can also compute it. Editing that payload
    to add readiness or a justification would not close that gap; it would
    only give the refusal one more field to print back, and it repeats the
    exact defect class already recorded at `_verify_launch_consent()`'s own
    docstring (F2): three named `--worker <account>` invocations once
    minted an identical token because a real field was left out of the
    digest. This function is deliberately NOT that kind of change: it reads
    a record written BEFORE and INDEPENDENTLY of this invocation, by a
    different act -- `implementation_cli gate`, run against a REHEARSAL
    that actually happened -- never anything this invocation's own argv
    could have produced.

    Readiness is the un-forgeable half: `gate` only ever appends its record
    after `remote_execution_jobs_state()['smokeReady']` reads `True` for
    that job at its CURRENT pin, and that fact can only become true by a
    rehearsal actually running and being recorded (`cmd_readiness`'s own
    three-fact bind) -- no caller can type it into existence. Justification
    is legible, not verified: this function checks only that one is present
    on the matching record, never who wrote it or whether a human read it.
    What is enforceable, and IS enforced here, is narrower and honest: the
    approval is a distinct recorded act, and re-running this exact launch
    command a second time can never substitute for it -- only a `gate`
    record, minted by a separate invocation of a separate command, can.

    Strengthened once more, additively (Slice 2B, design decision 3): the
    `gate` command that appends a matching record now also requires its own
    SEPARATE `--authorization` precondition -- a token minted by a prior
    `offer` publish, verified and consumed at gate time
    (`implementation_cli._verify_gate_authorization`). This function does
    not read that token, or any `authorization`/`authorization-consumed`
    event -- it still folds only `kind: "gate"` events, exactly as before,
    and it cannot tell a record written before that mechanism existed from
    one written after. That is deliberate, not an oversight: the
    strengthening is a property of how a `gate` record now comes to exist
    (the command that writes it refuses to run without a verified token),
    never a property this function itself checks. A `gate` record written
    before this mechanism existed therefore authorizes exactly as it always
    did here -- it is not migrated, and it is not invalidated.

    Scope, stated rather than left implicit:

    - `smoke=True` returns immediately. A rehearsal is never gated by this
      function -- gating it would deadlock the very mechanism that makes
      readiness measurable (`smokeReady` becomes `True` only once a
      rehearsal has run). `--smoke` still needs its own consent token
      (`_verify_launch_consent` above), so a rehearsal stays deliberate.
    - `pin_commit is None` returns immediately too: the legacy
      `<Name>/Notebooks/**.ipynb` shape has no job folder and therefore no
      `run-config.json` for `gate` to have read a commit from, and no
      `@rehearsal <jobName>` witness a position sequence could ever name
      for it -- the exact "nothing here promised a runner a commit"
      discriminator `_gate_job_folder_pin()`'s own docstring already uses,
      applied to the same reason.
    - Campaign mode (`units` truthy) is NOT exempt (design revision,
      `the-position-nobody-holds` PR8 -- corrected: the original pass here
      exempted it, reasoning that `gate`'s own CLI took no `--unit` flag to
      bind against. That reasoning inverted this change's whole purpose: the
      single send ended up authorized and the campaign -- the full-scale,
      multi-worker, hours-long launch this mechanism exists to gate -- did
      not. The premise was also simply wrong: `units`, at THIS call site, is
      the exact ordered list `cmd_submit`'s OWN caller passed via `--unit`,
      computed before `packer.distribute()` ever runs -- the same value
      `campaign_consent_token()` already binds, never the per-worker
      assignment `distribute()` computes later, which this function never
      sees at all. `gate` now takes the identical repeatable `--unit`, so a
      campaign authorization binds the same (pin, entrypoint, ordered unit
      list) `campaign_consent_token()` binds, with `worker` always absent --
      campaign mode never names one (`cmd_submit`'s own `--worker`/`--unit`
      mutual exclusivity above), the same reason `campaign_consent_token()`
      itself omits `worker` from its payload whenever the caller named none.

    For every other launch, this folds `<target>/<product>/.implementation/
    position.jsonl` and requires the NEWEST `gate` event whose `commit`,
    `entrypoint` and `units` match this invocation's own binding exactly,
    whose `worker` matches this invocation's own `worker` (which is why an
    auto-selected single-send launch -- no `--worker` named -- can never
    match a `gate` record: `gate`'s own `--worker` flag is required for that
    shape, so a record always names one account, and an invocation that has
    not yet chosen one has nothing to match against; a campaign launch's
    `worker` is structurally always `None`, and a campaign `gate` record's
    `worker` is `None` too, by the same mutual-exclusivity rule on both
    sides), and whose `justification` is non-blank. Fail-closed by design
    (§4.5): a product with no `.implementation/position.jsonl` at all folds
    to zero events and refuses exactly like one with events but no match,
    reproducing today's hole for NO target -- the one-time adoption cost
    this accepts on purpose, and the refusal below names the exact command
    that pays it.
    """
    if smoke:
        return
    if pin_commit is None:
        return

    impl_position = _load_impl_position()
    ledger_path = (
        Path(target).resolve() / product / ".implementation" / "position.jsonl"
    )
    events = impl_position.read_events(ledger_path)
    expected_units = list(units or ())
    expected_entrypoint = str(relative_entrypoint)

    for event in reversed(events):
        if event.get("kind") != "gate":
            continue
        if (
            event.get("commit") == pin_commit
            and event.get("entrypoint") == expected_entrypoint
            and list(event.get("units") or []) == expected_units
            and event.get("worker") == worker
            and str(event.get("justification") or "").strip()
        ):
            return

    # A campaign refusal must hand the caller a command shaped like the
    # record that could actually authorize it -- naming `--worker <account>`
    # here would send the caller toward a record `gate`'s own mutual
    # exclusivity refuses to write (a campaign record's `worker` is always
    # `None`), so the campaign branch names `--unit` instead, never a
    # worker flag.
    if units:
        worker_note = ""
        gate_flags = " ".join(f"--unit {unit!r}" for unit in expected_units)
    else:
        worker_note = (
            f" for worker {worker!r}" if worker is not None else " (no --worker named)"
        )
        gate_flags = f"--worker {worker!r}" if worker is not None else "--worker <account>"
    raise AuthorizationError(
        "submit refuses: no `gate` transition record authorizes this exact "
        f"launch (pin {pin_commit!r}, entrypoint {expected_entrypoint!r}, "
        f"units {expected_units!r}){worker_note}. Run `implementation_cli "
        f"gate --target <workspace-clone> --name {product} --job <jobName> "
        f"{gate_flags} --justification <text-or--> --revision "
        "<revision> --session <id>` first, at this exact pin, then re-run "
        "this exact submit invocation -- re-running submit itself is "
        "never the approval; only that separate, recorded act is."
    )


def _verify_campaign_readiness(
    *, job_dir: Path, workers: Sequence[str], pin_commit: str
) -> None:
    """Refuse `CAMPAIGN_WORKERS_NOT_READY` unless every worker the
    distribution assigns units to reads ready on `cmd_readiness()` (its own
    passing rehearsal at the job's current pin). S2, parallel campaigns:
    the campaign `gate` record binds pin, entrypoint and units but no
    worker, so which accounts a campaign spends is only known once
    `packer.distribute()` ran -- this is checked right then, before the
    first `adapter.submit()`, and names every worker that still needs a
    rehearsal rather than the first. A single send keeps its own check
    (the `gate` record names its worker); a rehearsal (`--smoke`) and the
    legacy no-job-folder shape are exempt, as they are from the gate.
    """
    not_ready: list[str] = []
    reasons: list[str] = []
    for worker in workers:
        if worker in not_ready:
            continue
        verdict = cmd_readiness(job_dir=job_dir, worker=worker)
        if not verdict["ready"]:
            not_ready.append(worker)
            reasons.append(f"{worker!r}: {verdict['reason']}")
    if not not_ready:
        return
    names = ", ".join(repr(worker) for worker in not_ready)
    raise ReadinessError(
        f"{CAMPAIGN_WORKERS_NOT_READY}: submit refuses: this campaign assigns "
        f"units to {len(not_ready)} worker(s) with no passing rehearsal of "
        f"their own at pin {pin_commit!r}: {names}. Readiness is per worker: "
        "rehearse each one (`submit --smoke --worker <worker> ...`, `fetch "
        "--smoke`, `smoke record --worker <worker>`), confirm `readiness "
        "--worker <worker>` reads ready, then re-run this exact submit. "
        "Nothing was submitted. Details -- " + "; ".join(reasons),
        not_ready,
    )


def _gate_job_folder_pin(
    resolved_entrypoint: Path, *, repo_credential_path: str | Path | None = None
) -> None:
    """Put a job-folder submission's own declared pin through the same
    pin conditions `generate-job` enforces — BEFORE the digest walk, the
    plan, `adapter.submit()` and `LEDGER.append()`.

    `cmd_submit` used to compute a staleness verdict and place it in its
    return value, after the ledger event had already been appended. By the
    time an operator could read it, the adapter had accepted the job, the
    quota was gone and the ledger recorded a submission. That is not a
    gate; it is a receipt with a warning printed on it. Refusing has to
    happen while refusing still costs nothing, which is why this sits
    immediately after `product_for()` and before anything is computed,
    uploaded or written.

    It calls `jobfolder.verify_pin_preconditions()` — the same one
    function, in the same `PIN_CONDITIONS` order — with the job folder's
    OWN declared pin, clone paths and remote, read back through
    `JOBFOLDER.read()`. Not the caller's arguments: what is being
    submitted is the job folder, and the job folder is what promised a
    runner a commit.

    **The discriminator is `run-config.json`'s presence, deliberately not
    `_job_folder_staleness()`.** That helper returns `None` on TWO paths,
    not one: the legacy shape, and a `run-config.json` `read()` cannot make
    sense of. Reusing it here would let a job folder skip every pin
    condition by being unreadable, which is the worse half of the defect
    class this whole change is about. So a `JobFolderError` from `read()`
    is NOT swallowed — the same restraint `cmd_smoke_record()` already
    applies, and for the same reason. A malformed job folder refusing at
    submit is a new refusal path, and it is the intended one.

    A legacy entrypoint skipping every pin condition is not a finding and
    is left exactly as it was: it has no declared pin, no declared clone
    paths and no declared remote, so there is nothing to check, and unlike
    a job folder it never promised a runner a commit.

    A rehearsal (`submit --smoke`) meets this gate too. A rehearsal dials
    out, uploads a staged copy and spends quota; exempting it would make
    the gate optional in the workflow that runs most often, and it would
    break the very binding `cmd_readiness` depends on — that the rehearsed
    bytes and the submitted bytes are the same bytes.

    Raises `JobFolderError`, unwrapped, so the message reaching stderr is
    byte-identical to the one generation would have printed.
    """
    job_dir = resolved_entrypoint.parent
    if not (job_dir / RUN_CONFIG_FILENAME).is_file():
        return

    job_folder = JOBFOLDER.read(job_dir)
    run_config = job_folder.run_config
    repo = run_config["repo"]
    JOBFOLDER.verify_pin_preconditions(
        target=_target_for_job_dir(job_folder.path),
        commit=run_config["commit"],
        clone_paths=run_config["clonePaths"],
        # Derived from the job folder's OWN config through the SAME
        # `declared_notebooks()` generation used, never re-spelled here.
        # A second spelling is how the two decision points would come to
        # disagree about which notebooks a job promised to run — the exact
        # drift `verify_pin_preconditions()` exists to make impossible for
        # every other condition.
        notebooks=JOBFOLDER.declared_notebooks(run_config),
        repo_url=repo["url"],
        repo_ref=repo["ref"],
        decision="submission",
        # S3: the submit-time probe meets the same credential-conditional
        # behavior generation's does; `None` (no flag) is unchanged.
        repo_credential_path=repo_credential_path,
        # A job that ships its code as a bundle never has the runner clone,
        # so the one network condition (`pin-published`) is skipped and
        # the bundle file itself is checked against its recorded sha256
        # instead, still before anything is uploaded.
        code_bundle="codeBundle" in run_config,
    )
    JOBFOLDER.verify_code_bundle(
        job_folder.path, run_config, target=_target_for_job_dir(job_folder.path)
    )


def guard_entrypoint(target: Path, entrypoint: Path) -> Path:
    """Refuse anything that is not a notebook living under one of exactly
    two admitted shapes.

    THIS function is the single place in the entire remote-execution skill
    that holds an opinion about what KIND of file may run remotely.
    Everything below it is deliberately blind to that question:
    `adapter.Job.entrypoint` is typed as a bare path with no extension or
    directory-containment check (see `adapter.py`'s own docstring on that
    field), the ledger's `submitted`/`returned`/`errored` events store
    `entrypoint` as an opaque string, and the fold indexes by that same
    string without ever asking what it points to. That narrowing is
    deliberate, not an oversight left for later: a future workload that is
    a plain script, not a notebook, becomes admissible by widening the
    checks below — and ONLY the checks below. Nowhere else in this skill
    needs to change: not `Job`, not the ledger's event schema, not the
    fold's indices, not any downstream consumer that reads `entrypoint`
    today. Reworking all of those for a second file kind is exactly the
    refactor this one guard exists to make unnecessary.

    This forge's own layout rule, not a universal one, and not something a
    second deployment of this skill against a differently-shaped repository
    should assume holds. Exactly two shapes are admitted, both under
    `<target>`:

    - the legacy shape, `<Name>/Notebooks/**.ipynb` — the resolved path's
      second component is `Notebooks` and it has at least three components
      past `target`
    - the job-folder shape, `tools/<service>/<job-name>/*.ipynb` — exactly
      four components past `target`, the first of which is
      `TOOLS_DIRNAME`. This depth is exact, not a minimum: a fifth
      component (one level deeper than a job folder ever legitimately
      goes) is refused exactly like a path with too few. A shallower
      `tools/<service>/*.ipynb` is refused the same way — there is no
      service-level entrypoint, only a job-level one.

    `TOOLS_DIRNAME` ("tools") is a forge-layout constant fixed by this
    skill's own directory convention, never a service name — it must never
    be treated as one, and it is why it never appears in this module's own
    no-service source scan.

    Both shapes require the resolved path to end `.ipynb`; anything else is
    refused, with a message naming both the path that was refused and
    which rule it failed.

    `Path.resolve()` runs FIRST, and both shape checks below run only
    against the RESOLVED path — never the literal argument this function
    received. This order is load-bearing, not cosmetic, for EITHER shape: a
    symlink sitting inside `Notebooks/` or inside a job folder can point
    anywhere else on disk, and a check made against the literal path would
    see only the symlink's own in-bounds location, never where it actually
    leads. Checking containment before resolving is the exact hole a
    documentation-like escape (this skill's own threat matrix) would walk
    straight through; resolving first and checking the resolved target is
    what closes it, on both shapes alike.

    One narrower case gets its OWN message before either shape check's
    generic refusal (Finding 4 case B): a path that is exactly the
    job-folder DIRECTORY itself — three components past `target`, first
    `TOOLS_DIRNAME`, and actually holding both `run-config.json` and
    `runner.ipynb` — is one level above the answer, not a path in the
    wrong location. The generic "does not stay under ... nor under ..."
    message reads as a location problem and sends the caller to
    regenerate a job that was already sound; this instead says a file was
    expected, not a directory, and names exactly where the notebook is.
    A directory merely SHAPED like a job folder by depth alone, holding
    neither file, is not this case and still falls through to the generic
    refusal below — as does a `.ipynb` FILE one level too shallow (no
    `<job-name>` component at all), which is a different defect entirely.
    """
    resolved = Path(entrypoint).resolve()

    try:
        relative = resolved.relative_to(target)
    except ValueError:
        raise PathGuardError(
            f"refusing {entrypoint}: resolved path {resolved} does not stay "
            f"under target {target} at all"
        ) from None

    parts = relative.parts
    legacy_shape = len(parts) >= 3 and parts[1] == NOTEBOOKS_DIRNAME
    job_folder_shape = len(parts) == 4 and parts[0] == TOOLS_DIRNAME

    if not (legacy_shape or job_folder_shape):
        job_folder_directory = (
            len(parts) == 3
            and parts[0] == TOOLS_DIRNAME
            and resolved.is_dir()
            and (resolved / RUN_CONFIG_FILENAME).is_file()
            and (resolved / JOBFOLDER.RUNNER_FILENAME).is_file()
        )
        if job_folder_directory:
            # Finding 4 case B: `--entrypoint` was handed the job folder
            # DIRECTORY itself, one level above the answer, not the
            # notebook FILE inside it. The generic shape-mismatch message
            # below reads as though the folder were in the wrong
            # location and sends the caller to regenerate a job that was
            # perfectly sound — this names what was wanted, what was
            # given, and exactly what to type instead.
            notebook = resolved / JOBFOLDER.RUNNER_FILENAME
            raise PathGuardError(
                f"refusing {entrypoint}: a file was expected, not a "
                f"directory — {resolved} is the job folder itself, one "
                f"level above the answer; the notebook is at {notebook} — "
                "pass that path to --entrypoint instead"
            )
        raise PathGuardError(
            f"refusing {entrypoint}: resolved path {resolved} does not stay "
            f"under <target>/<Name>/{NOTEBOOKS_DIRNAME}/ nor under "
            f"<target>/{TOOLS_DIRNAME}/<service>/<job-name>/"
        )

    if resolved.suffix != NOTEBOOK_SUFFIX:
        raise PathGuardError(
            f"refusing {entrypoint}: resolved path {resolved} does not end "
            f"in {NOTEBOOK_SUFFIX}"
        )

    return resolved


def _relative_entrypoint(target: Path, resolved_entrypoint: Path, product: str) -> Path:
    """Derive the path recorded as a `submitted` event's own `entrypoint`
    field, from the SAME resolved entrypoint and the SAME product
    `product_for()` already resolved — never a second, independent
    derivation of either.

    For the legacy shape, `product` IS the entrypoint's own first path
    component past `target` (`product_for()`'s step 3 derives it that
    way), so the path relative to the product directory is exactly
    `Notebooks/...` — byte-identical to what this replaces, which computed
    `resolved_entrypoint.relative_to(target / name)` with `name` derived
    inline as that same first component.

    For the job-folder shape, the product directory is NOT an ancestor of
    the entrypoint at all: a job lives under
    `<target>/tools/<service>/<job-name>/`, structurally separate from
    wherever its declared product's own directory happens to live —
    `product_for()`'s whole reason for reading `run-config.json` instead of
    guessing `parts[0]` is that these two locations are unrelated for this
    shape. "Relative to the product directory" therefore has no meaning
    here, so this falls back to relative-to-`target` instead
    (`tools/<service>/<job-name>/runner.ipynb`), which stays unique and
    unambiguous per job folder without asserting a containment
    relationship that does not hold for this shape.
    """
    try:
        return resolved_entrypoint.relative_to(target / product)
    except ValueError:
        return resolved_entrypoint.relative_to(target)


def _declared_session_limit(adapter: "ADAPTER.Adapter") -> int | None:
    """The adapter's declared continuous session limit, in seconds, or
    `None` when it declares none. Only a positive integer counts: anything
    else (an adapter predating the seam's default, a test double that is
    not an `Adapter`) is read as undeclared, never coerced into a number."""
    reader = getattr(adapter, "session_limit_seconds", None)
    if not callable(reader):
        return None
    limit = reader()
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        return None
    return limit


#: What a single send of a job declaring carry paths reports (session-chains).
NO_SHARE_CARRY_WARNING = (
    "this job declares carry paths but was sent without --unit, so no share was "
    "recorded: if its session is cut at the limit, `remaining` lists none of its units "
    "and no continuation carries its checkpoints. Send it as `submit --unit <id>` per "
    "unit (the ids its partial.json names)")


def _declared_carry_paths(resolved_entrypoint: Path) -> tuple[str, ...]:
    """The carry paths the job folder beside `resolved_entrypoint` declares
    in its `run-config.json` (`generate-job --carry-path`), or `()` when it
    declares none or is not a job folder at all (the legacy shape carries
    nothing). Read with the generator's own validator, so a hand-edited
    path that escapes the product folder refuses here too."""
    config_path = resolved_entrypoint.parent / RUN_CONFIG_FILENAME
    if not config_path.is_file():
        return ()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ()
    declared = config.get("carryPaths") if isinstance(config, dict) else None
    if not declared:
        return ()
    if not isinstance(declared, list):
        raise RemoteCLIError(
            f"{config_path}'s carryPaths must be a list of carry paths"
        )
    return JOBFOLDER.validate_carry_paths(declared)


def _declared_input_datasets(resolved_entrypoint: Path) -> tuple[str, ...]:
    """The public datasets the job folder beside `resolved_entrypoint`
    declares in its `run-config.json` (`generate-job --input-dataset`), or
    `()` when it declares none or is not a job folder (the legacy shape
    attaches nothing). Read with the generator's own validator, so a
    hand-edited ref refuses here, before anything is submitted
    (kernel-input-datasets S1)."""
    config_path = resolved_entrypoint.parent / RUN_CONFIG_FILENAME
    if not config_path.is_file():
        return ()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ()
    if not isinstance(config, dict) or "inputDatasets" not in config:
        return ()
    try:
        return JOBFOLDER.validate_input_datasets(config["inputDatasets"])
    except JOBFOLDER.JobFolderError as exc:
        raise RemoteCLIError(f"{config_path}: {exc}") from None


def _input_plan(
    adapter: "ADAPTER.Adapter", resolved_entrypoint: Path
) -> tuple[str | None, dict]:
    """What `submit` does with a job's declared input datasets
    (kernel-input-datasets S2, S3): `(None, {})` for a job declaring none
    -- it is submitted exactly as before -- else `("attached", {"inputRoot":
    <root>})` for a backend declaring `INPUT_DATASETS_ROOT`, which attaches
    the datasets to the push, or `("unsupported", {})` for one that does
    not, whose runner then exports every ref mapped to null."""
    if not _declared_input_datasets(resolved_entrypoint):
        return None, {}
    root = getattr(adapter, "INPUT_DATASETS_ROOT", None)
    if isinstance(root, str) and root:
        return "attached", {"inputRoot": root}
    return "unsupported", {}


def _carry_evidence(
    *,
    target: Path,
    product: str,
    relative_entrypoint: str,
    live_digest: str,
    ledger_lines: Sequence[str],
) -> dict[str, dict]:
    """Which units an earlier submission of this entrypoint left to be
    continued, and by which submission (kernel-carry S2) -- unit -> that
    submission's `submitted` event.

    The same evidence `remaining` reads, and only that: a settled
    submission at the CURRENT source digest whose `returned` result was
    not quarantined and carries a `partial.json` (the units it lists, or
    its whole share when it lists none), or whose `errored` event names
    bytes `fetch` kept under `.remote-execution/partial/` (its whole
    share). The LATEST settled submission carrying a unit decides: one
    that finished it, or that left nothing behind, clears what an earlier
    one left. A submission still in flight decides nothing.
    """
    product_root = (target / product / LEDGER_DIRNAME).resolve()
    quarantine = product_root / QUARANTINE_DIRNAME
    kept_root = product_root / KEPT_PARTIAL_DIRNAME
    evidence: dict[str, dict] = {}
    for submitted, terminal in LEDGER.submission_outcomes(ledger_lines):
        if str(submitted.get("entrypoint")) != relative_entrypoint:
            continue
        if submitted.get("sourceDigest") != live_digest:
            continue
        if terminal is None:
            continue
        share = [str(unit) for unit in submitted.get("units") or ()]
        artifact = terminal.get("artifactPath")
        resolved = Path(artifact).resolve() if artifact else None
        left: set[str] = set()
        if terminal.get("kind") == "returned" and resolved is not None:
            if not resolved.is_relative_to(quarantine):
                stopped, unfinished = SHARD_IO.partial_marker(resolved)
                if stopped:
                    left = set(share) if unfinished is None else set(share) & unfinished
        elif terminal.get("kind") == "errored" and resolved is not None:
            if resolved.is_relative_to(kept_root) and resolved.is_dir():
                left = set(share)
        if left:
            # One copy per submission, shared by its units, so a share can
            # still tell two units of one earlier submission apart by identity.
            submitted = {**submitted, _CARRY_ARTIFACT_KEY: str(resolved)}
        for unit in share:
            if unit in left:
                evidence[unit] = submitted
            else:
                evidence.pop(unit, None)
    return evidence


def _carry_affinity(evidence: Mapping[str, dict], units: Sequence[str]) -> dict[str, str]:
    """unit -> the worker whose earlier output it continues from, for the
    units of this campaign that have continuation evidence."""
    return {
        str(unit): str(evidence[str(unit)].get("worker"))
        for unit in units
        if str(unit) in evidence
    }


def _carry_source(adapter: "ADAPTER.Adapter", submission_id: str) -> dict | None:
    """The adapter's `carry_source()` answer, validated, or `None` when the
    backend carries nothing (an adapter predating the seam's default, a
    test double that is not an `Adapter`, or an answer that is not the
    `{"ref", "mount"}` pair of strings)."""
    reader = getattr(adapter, "carry_source", None)
    if not callable(reader):
        return None
    answer = reader(submission_id)
    if not isinstance(answer, Mapping):
        return None
    ref, mount = answer.get("ref"), answer.get("mount")
    if not isinstance(ref, str) or not ref or not isinstance(mount, str) or not mount:
        return None
    return {"submissionId": submission_id, "ref": ref, "mount": mount}


def _main_ledger_evidence(
    target: Path, product: str, relative_entrypoint: "str | Path", digest: str,
) -> dict[str, dict]:
    """`_carry_evidence()` over the MAIN ledger, whatever ledger this
    invocation records into: a rehearsal (`--smoke`) pushes the same kernel
    a real run does, so it must avoid the refs real continuations read."""
    return _carry_evidence(
        target=target, product=product,
        relative_entrypoint=str(relative_entrypoint), live_digest=digest,
        ledger_lines=_read_ledger_lines(_main_ledger_path(target, product)),
    )


def _carry_protected(adapter: "ADAPTER.Adapter", evidence: Mapping[str, dict]) -> list[str]:
    """Every ref some continuation still reads from: the `carry_source()`
    ref of each submission that left a unit to be continued, whether or not
    this campaign sends that unit (kernel-carry B1). Handed to every job as
    `run_config["carryProtected"]` so no push -- a fresh share's, another
    share's, a later fresh-only campaign's -- replaces an output a
    continuation is about to read. Sorted, so a job is deterministic; empty
    when nothing is pending or the backend carries nothing."""
    refs: set[str] = set()
    for submitted in evidence.values():
        source = _carry_source(adapter, str(submitted.get("submissionId")))
        if source is not None:
            refs.add(source["ref"])
    return sorted(refs)


def _in_flight_refs(
    adapter: "ADAPTER.Adapter",
    *,
    target: Path,
    product: str,
    relative_entrypoint: "str | Path",
    smoke: bool,
) -> set[str]:
    """The `carry_source()` refs of every submission of this entrypoint
    that is still in flight -- submitted, never settled -- in the main
    ledger, and in the rehearsal ledger too when this invocation is a
    rehearsal. A new push to one of them would replace a kernel that is
    still running, so they join the protected set whether or not the job
    declares carry paths. Any source digest counts: a kernel pushed from an
    older source is still running. A backend whose `carry_source` is the
    seam's default contributes nothing here."""
    paths = [_main_ledger_path(target, product)]
    if smoke:
        paths.append(_smoke_ledger_path(target, product))
    refs: set[str] = set()
    for path in paths:
        for submitted, terminal in LEDGER.submission_outcomes(_read_ledger_lines(path)):
            if terminal is not None:
                continue
            if str(submitted.get("entrypoint")) != str(relative_entrypoint):
                continue
            source = _carry_source(adapter, str(submitted.get("submissionId")))
            if source is not None:
                refs.add(source["ref"])
    return refs


def _protected_refs(
    adapter: "ADAPTER.Adapter",
    *,
    target: Path,
    product: str,
    resolved_entrypoint: Path,
    relative_entrypoint: "str | Path",
    digest: str,
    smoke: bool,
    evidence: Mapping[str, dict] | None = None,
) -> list[str]:
    """`run_config["carryProtected"]` for a job folder: the refs a push
    must avoid. Refs pending continuations read from (only for a job
    declaring carry paths) and refs of submissions still in flight (every
    job folder). Empty -- and then no key is written at all, so the job is
    byte-identical to before -- when neither exists, or for the legacy
    shape, which has no job folder to carry the key."""
    if not (resolved_entrypoint.parent / RUN_CONFIG_FILENAME).is_file():
        return []
    refs = _in_flight_refs(
        adapter, target=target, product=product,
        relative_entrypoint=relative_entrypoint, smoke=smoke,
    )
    if _declared_carry_paths(resolved_entrypoint):
        refs.update(_carry_protected(adapter, {
            **_main_ledger_evidence(target, product, relative_entrypoint, digest),
            **(evidence or {}),
        }))
    return sorted(refs)


def _plan_share_carry(
    *,
    adapter: "ADAPTER.Adapter",
    evidence: Mapping[str, dict],
    worker: str,
    share: Sequence[str],
    no_carry: bool,
) -> tuple[str, list[dict]] | None:
    """What one campaign share carries: `None` when no unit of it continues
    an earlier submission, else `(status, sources)` with `status` one of
    `attached` (sources are `{"submissionId", "ref", "mount"}` rows),
    `uploaded` (the backend uploads the earlier output from this machine,
    `Adapter.CARRY_UPLOAD`: sources are `{"submissionId", "ref", "upload"}`
    rows naming the local directory `fetch` left), `unsupported` (the
    backend can do neither; nothing is carried) or `fresh` (`--no-carry`).
    A source produced on another worker refuses `CARRY_WORKER_MISMATCH`
    (kernel-carry S4). An upload source always exists: the evidence that
    names it is read from inside it (`_carry_evidence()`)."""
    earlier: list[dict] = []
    seen: set[str] = set()
    for unit in share:
        submitted = evidence.get(str(unit))
        if submitted is None:
            continue
        submission_id = str(submitted.get("submissionId"))
        if submission_id in seen:
            continue
        seen.add(submission_id)
        earlier.append(submitted)
    if not earlier:
        return None
    if no_carry:
        return ("fresh", [])
    sources: list[dict] = []
    status = "attached"
    uploads = getattr(adapter, "CARRY_UPLOAD", False) is True
    for submitted in earlier:
        submission_id = str(submitted.get("submissionId"))
        source = _carry_source(adapter, submission_id)
        if source is None and uploads:
            status = "uploaded"
            source = {"submissionId": submission_id, "ref": submission_id,
                      "upload": str(submitted.get(_CARRY_ARTIFACT_KEY))}
        if source is None:
            return ("unsupported", [])
        sources.append(source)
    for submitted in earlier:
        produced_on = str(submitted.get("worker"))
        if produced_on != worker:
            continued = [
                str(unit) for unit in share
                if evidence.get(str(unit)) is submitted
            ]
            raise RemoteCLIError(
                f"{CARRY_WORKER_MISMATCH}: unit(s) {continued} continue from "
                f"submission {submitted.get('submissionId')!r}, whose output "
                f"was produced on worker {produced_on!r}, but this campaign "
                f"places them on worker {worker!r}; an earlier output is only "
                "carried within the account that produced it. Nothing was "
                f"submitted. Include worker {produced_on!r} in the pool "
                "(distribute places continuations there), or pass --no-carry "
                "to start these units fresh"
            )
    return (status, sources)


def cmd_submit(
    *,
    target: str | Path,
    entrypoint: str | Path,
    worker: str | None = None,
    requested: int,
    adapter: "ADAPTER.Adapter",
    source_digest: Callable[[Path, str], str] | None = None,
    product: str | None = None,
    smoke: bool = False,
    units: Sequence[str] | None = None,
    consent: str | None = None,
    repo_credential_path: str | Path | None = None,
    no_carry: bool = False,
) -> dict:
    """Guard, resolve a product, plan, submit, and record — the whole submit
    path, in this order.

    Carry (kernel-carry S2-S5), campaign mode only, and only for a job
    folder whose `run-config.json` declares `carryPaths`: a unit an
    earlier submission of this entrypoint left to be continued
    (`_carry_evidence()`, the evidence `remaining` reads) is placed on the
    worker that produced it (`packer.distribute(affinity=...)`), and its
    share's job is handed `run_config["carry"]` -- the earlier
    submission's `{"submissionId", "ref", "mount"}` from the adapter's
    `carry_source()` -- so the backend attaches the earlier output and the
    runner restores the declared paths before the entrypoint. The
    `submitted` event records `carriedFrom`, and each `submissions[]` row
    reports `carry`: `attached`, `unsupported` (a backend that mounts no
    earlier output; nothing is carried) or `fresh` (`no_carry`, the
    `--no-carry` flag). A continuation produced on another worker refuses
    `CARRY_WORKER_MISMATCH` before any submission. A job declaring no
    carry paths, a single send and the legacy shape behave exactly as
    before: no affinity, no `carry` key, no `carriedFrom`.

    `units` is `submit --unit`'s own campaign switch (Finding 2; Decisions
    6, 7) — repeatable, the exact same flag `cmd_distribute` already
    declares. `None` or empty keeps every existing caller on TODAY's
    single-worker path below, byte-identical: `packer.select()` (no
    `--worker`) or `packer.plan()` (a named `--worker`), one
    `adapter.submit()`, one ledger event. A non-empty `units` switches
    into CAMPAIGN mode instead: `packer.distribute()` replaces
    `select()`/`plan()` entirely, consuming the spread across every
    healthy account rather than stopping at the first one — the defect
    this phase closes (`cmd_distribute`'s own docstring: "nothing is
    recorded and nothing is handed to" the adapter). `worker` is refused
    together with `units`: campaign mode has no "which account" fork for a
    caller to override, the same reason `distribute()` itself takes no
    `worker` parameter.

    Guard order past the target resolution is unchanged either way:
    `guard_entrypoint()` → `product_for()` → `_gate_job_folder_pin()` →
    `_verify_diagrams_validated()` (the operator validated every approved
    experiment diagram in the dashboard) → the consent gate below → the digest, computed once and reused for
    every assignment in campaign mode — a single `distribute()` call
    already reads live health for every worker in one pass, so there is
    no per-assignment health re-read to stagger the digest around.

    `consent` gates EVERY mode this function has (Finding 3; Decisions 4,
    5 -- corrected: the original pass gated campaign mode only, which left
    a plain `submit` or `submit --smoke` reaching `adapter.submit()` with
    nobody asked, the exact launch the user's complaint named). Stated as
    the invariant it now is: nothing reaches
    `packer.select()`/`packer.plan()`/`packer.distribute()` -- and
    therefore never `adapter.submit()` -- without a `consent` token that
    matches `campaign_consent_token()`'s own output for THIS invocation's
    job folder pin (`_job_folder_commit()`, `None` for the legacy shape),
    relative entrypoint, and `units` in the exact order given (the empty
    tuple for a single send -- one derivation, one shape, never a second
    one invented for the non-campaign case). `_verify_launch_consent()`
    runs this check unconditionally, right after `_gate_job_folder_pin()`
    and before the digest is ever computed, so a refusal on any mode costs
    nothing: no digest walk, no plan, no adapter call, no ledger line.

    For a campaign, `distribute --unit ...` mints the token ahead of time
    and prints it -- the caller passes it back here. A single send has no
    equivalent minting command, so `submit` itself mints the expected
    token and prints it IN the refusal, which is safe only because the
    refusing call never gets past this gate: nothing was launched by the
    run that named the token. The worker is never part of what the token
    binds, in either mode: with no `--worker`, the account is chosen by
    `packer.select()` AFTER consent would be given, so binding it would
    make the token unmintable in advance; with `--worker` named, the
    account is the caller's own explicit, already-honest choice.

    Campaign mode issues one `adapter.submit()` and appends one ledger
    event per `packer.Distribution` assignment (Decision 6) — never one
    per unit, since a worker's whole assigned unit list travels inside
    that ONE job's opaque `run_config["units"]`, unread by this function.
    An assignment whose `units` came back empty (a healthy account with
    room but nothing left to hand it, `packer.Assignment`'s own documented
    case) submits nothing and is reported with `submissionId: None` —
    "had room, didn't need it" stays a fact about capacity, never a
    fabricated job. The returned mapping mirrors `packer.Distribution`
    field for field (Decision 7): `assignments[]`, `unplaced[]`, and
    `skipped[]` (worker → `Skip.reason`, unprefixed, exactly as
    `cmd_distribute` already renders it) — carried through unchanged, no
    new triage logic invented here.

    `smoke=True` (`submit --smoke`) does two things together, both
    load-bearing (design #744 section 7, and see `SMOKE_LEDGER_FILENAME`'s
    own comment above): sets `run_config["mode"] = "smoke"` on the `Job`
    (opaque to `packer.py`/`ledger.py`, read only by
    `assets/runner_invoke.py`'s `select_block()`), and routes the
    resulting `submitted` event to `smoke.jsonl` instead of
    `ledger.jsonl` — a different destination FILE, not a different event
    shape, which is what keeps a rehearsal from ever becoming an
    entrypoint's `latest[...]` submission in the main ledger's fold.
    `smoke=False` (the default) is byte-identical to this function's
    pre-T11 behavior.

    `target` is resolved to an absolute path as the very first thing this
    function does, before any other check and before any filesystem write —
    every data path this call touches (the guard's containment check, the
    ledger's location) is derived from that resolved value and never from
    the raw argument. A relative `--target` therefore never gets a chance to
    be interpreted against the wrong working directory later in the call,
    because by the time anything else runs, there is no relative path left
    to misinterpret.

    Order past that point is fixed by design, not incidental:
    `guard_entrypoint()` runs first because nothing after it — not the
    product, the digest, the plan, not the adapter call — should ever run
    against a path this forge's layout rule refuses. `product_for()` runs
    immediately after the guard, and BEFORE any digest, plan, or adapter
    call: a submission whose product cannot be resolved is refused right
    there, before anything is computed against a guessed tree (`tools`, in
    particular, which `product_for()` itself refuses to ever return) and
    before the adapter is given any chance to run — this is what keeps a
    job-folder submission with no resolvable product a clean refusal rather
    than a silently mis-recorded one. `_gate_job_folder_pin()` runs
    immediately after it and before everything else, so a job folder whose
    pin fails any pin condition is refused while refusing still
    costs nothing: no digest walk, no plan, no adapter call, no ledger
    line. This function used to compute a staleness verdict and place it
    in its return value AFTER `LEDGER.append()`, which reported on a
    submission that had already happened — a receipt with a warning
    printed on it rather than a gate. That verdict is still in the return
    payload for callers that read it; it is simply no longer the only
    thing standing between a stale pin and spent quota. `source_digest()`
    is called FRESH
    here, at submit time, and its result is never reused from a notebook's
    own post-hoc marker or from any earlier call in this process — that
    freshness is the one thing that later lets the ledger's fold tell a
    current result from a stale one (see `ledger.py`'s `currency_verdict`).
    `packer.plan()` runs before `adapter.submit()` so a submission is never
    attempted with no capacity clamp computed behind it. `ledger.append()`
    runs LAST, only after the adapter has already returned a real
    submission id — appending before that would risk recording a submission
    that was never actually made.

    `product` is this function's own `--product` override, forwarded
    unchanged to `product_for()` as its `explicit` argument — step 1 of
    that function's four-step resolution order, and the one step no
    earlier version of this function ever exposed a way to reach.

    `repo_credential_path` (S3) is `--repo-credential`'s parsed path and
    is forwarded into `_gate_job_folder_pin()` alone — the adapter that
    stages the credential was already constructed with it by the CLI's
    dispatch branch, under the carrier gate that ran there. Omitted (no
    flag), every branch below is byte-identical to before the flag
    existed.

    `worker` is now OPTIONAL. `None` (no `--worker` on the CLI) hands the
    choice to `packer.select()`, which walks `adapter.workers()` in
    declared order and returns the first healthy one with capacity —
    naming an account is a decision this call no longer forces on a
    caller with no reason to make it. A caller that DOES name one keeps
    today's non-selecting behavior exactly: `packer.plan()` is called for
    that exact worker, and an unhealthy NAMED worker refuses outright
    (via `ADAPTER.WorkerUnauthorized`, propagated, never caught here)
    rather than silently falling back to a different account — silently
    switching accounts changes whose quota is spent, which is a decision
    only a caller who named the account in the first place gets to make.
    Either way, `plan()`/`select()` runs BEFORE `adapter.submit()`, so a
    refusal on either path costs no quota.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    resolved_entrypoint = guard_entrypoint(target, Path(entrypoint))
    resolved_product = product_for(
        target, resolved_entrypoint, explicit=product, command="submit"
    )
    # `repo_credential_path` is threaded straight into the pin gate so the
    # SUBMIT-time `pin-published` probe behaves credential-identically to
    # generation's; the adapter itself already carries the path, handed to
    # it by `_construct_adapter()`.
    _gate_job_folder_pin(
        resolved_entrypoint, repo_credential_path=repo_credential_path
    )
    relative_entrypoint = _relative_entrypoint(
        target, resolved_entrypoint, resolved_product
    )

    if units and worker is not None:
        raise RemoteCLIError(
            "--worker and --unit are mutually exclusive: campaign mode "
            "(--unit) spreads across every healthy account itself and "
            "has no single named account for --worker to select"
        )

    # Unconditional invariant (this phase's correction to Finding 3):
    # every mode -- campaign, single send, rehearsal -- is verified here,
    # before the digest is computed, before any plan, and before
    # `adapter.submit()`. `units or ()` feeds `campaign_consent_token()`
    # the empty ordered unit list for a single send -- a legitimate input
    # to the SAME derivation, never a second one.
    # `worker` here is still the caller's own raw argument -- None unless
    # `--worker` was explicitly passed. The mutual-exclusivity refusal
    # above guarantees it is None whenever `units` is truthy, so passing
    # it straight through binds an explicit single-send worker and leaves
    # campaign/auto-select derivation untouched, in one expression.
    pin_commit = _job_folder_commit(resolved_entrypoint)
    expected_consent = campaign_consent_token(
        pin_commit=pin_commit,
        relative_entrypoint=relative_entrypoint,
        units=units or (),
        worker=worker,
    )
    _verify_diagrams_validated(target / resolved_product)
    _verify_launch_consent(
        consent=consent, expected_consent=expected_consent, units=units,
        worker=worker,
    )

    # A second, INDEPENDENT precondition (design §4.2) -- never folded into
    # the consent check above, and never sharing its payload. Runs right
    # after consent and before the digest walk, so a refusal here costs
    # exactly as little as a consent refusal does: no digest, no plan, no
    # adapter call, no ledger line.
    _verify_launch_authorization(
        smoke=smoke, target=target, product=resolved_product,
        pin_commit=pin_commit, relative_entrypoint=relative_entrypoint,
        units=units, worker=worker,
    )

    digest_fn = source_digest or _load_source_digest()
    digest = digest_fn(target, resolved_product)

    ledger_path = (
        _smoke_ledger_path(target, resolved_product)
        if smoke
        else _main_ledger_path(target, resolved_product)
    )
    ledger_lines = _read_ledger_lines(ledger_path)

    # S3 (session checkpoints): the backend's declared continuous session
    # limit travels to the runner, which turns it into
    # `FORGE_SESSION_DEADLINE`. It travels inside `run-config.json`, so only
    # a job folder carries it: the legacy shape has no runner to read it
    # (and a backend may refuse a non-empty run_config there). A backend
    # that declares none (`None`) adds nothing, so the job is exactly what
    # it was before this existed.
    session_limit = _declared_session_limit(adapter)
    session_config = (
        {"sessionLimitSeconds": session_limit}
        if session_limit is not None
        and (resolved_entrypoint.parent / RUN_CONFIG_FILENAME).is_file()
        else {}
    )
    # kernel-input-datasets S2-S3: a job declaring input datasets is told
    # where a capable backend mounts them; one declaring none is unchanged.
    inputs_status, inputs_config = _input_plan(adapter, resolved_entrypoint)

    if units:
        carry_paths = _declared_carry_paths(resolved_entrypoint)
        evidence = (
            _carry_evidence(
                target=target, product=resolved_product,
                relative_entrypoint=str(relative_entrypoint),
                live_digest=digest, ledger_lines=ledger_lines,
            )
            if carry_paths
            else {}
        )
        distribution = PACKER.distribute(
            adapter=adapter,
            units=units,
            ledger_lines=ledger_lines,
            live_digest=digest,
            affinity=_carry_affinity(evidence, units) or None,
        )
        protected = _protected_refs(
            adapter, target=target, product=resolved_product,
            resolved_entrypoint=resolved_entrypoint,
            relative_entrypoint=relative_entrypoint, digest=digest, smoke=smoke,
            evidence=evidence,
        )

        if not smoke and pin_commit is not None:
            _verify_campaign_readiness(
                job_dir=resolved_entrypoint.parent,
                workers=[row.plan.worker for row in distribution.assignments if row.units],
                pin_commit=pin_commit,
            )

        # What each share carries, decided for ALL shares before the FIRST
        # submission, for the same reason as the size check below: a
        # `CARRY_WORKER_MISMATCH` halfway through would leave a campaign
        # half launched.
        share_carry: dict[tuple[str, int], tuple[str, list[dict]] | None] = {}
        for row in distribution.assignments:
            for index, share in enumerate(PACKER.slot_shares(row)):
                share_carry[(row.plan.worker, index)] = _plan_share_carry(
                    adapter=adapter, evidence=evidence, worker=row.plan.worker,
                    share=share, no_carry=no_carry,
                )

        # Every share's `submitted` event must fit one ledger line, checked
        # for ALL shares before the FIRST submission: a refusal halfway
        # through would leave a campaign half launched.
        for row in distribution.assignments:
            for index, share in enumerate(PACKER.slot_shares(row)):
                planned = share_carry[(row.plan.worker, index)]
                probe = LEDGER.submitted_event(
                    entrypoint=str(relative_entrypoint),
                    source_digest=digest,
                    submission_id="x" * _SUBMISSION_ID_BUDGET_CHARS,
                    worker=row.plan.worker,
                    requested_capacity=row.plan.requested,
                    granted_capacity=row.plan.granted,
                    slot=index + 1 if index else None,
                    units=share,
                    carried_from=planned[1] if planned else None,
                )
                if LEDGER.event_bytes(probe) > LEDGER.MAX_EVENT_BYTES:
                    raise RemoteCLIError(
                        f"{LEDGER_EVENT_TOO_LARGE}: slot {index + 1} of worker "
                        f"{row.plan.worker!r} carries {len(share)} units whose "
                        "`submitted` event would exceed the ledger's "
                        f"{LEDGER.MAX_EVENT_BYTES}-byte line; nothing was "
                        "submitted. Send fewer units per campaign, or shorter "
                        "unit names"
                    )

        assignments: list[dict] = []
        seen_ids: dict[str, str] = {}
        for row in distribution.assignments:
            submissions: list[dict] = []
            for index, share in enumerate(PACKER.slot_shares(row)):
                # Slot 1 is shaped exactly as a one-slot worker's single job
                # always was; only slots 2..k name themselves, so the
                # adapter can give each its own remote identity and the
                # ledger its own lane.
                slot = index + 1
                run_config = {"mode": "smoke"} if smoke else {}
                run_config = dict(run_config)
                run_config.update(session_config)
                run_config.update(inputs_config)
                run_config["units"] = list(share)
                if slot > 1:
                    run_config["slot"] = slot
                planned = share_carry[(row.plan.worker, index)]
                if planned and planned[0] in ("attached", "uploaded"):
                    run_config["carry"] = [dict(source) for source in planned[1]]
                if protected:
                    run_config["carryProtected"] = list(protected)
                job = ADAPTER.Job(
                    entrypoint=resolved_entrypoint,
                    run_config=run_config,
                    worker=row.plan.worker,
                )
                submission = adapter.submit(job)
                if submission.id in seen_ids:
                    raise RemoteCLIError(
                        f"{DUPLICATE_SUBMISSION_ID}: the backend answered slot "
                        f"{slot} of worker {row.plan.worker!r} with submission id "
                        f"{submission.id!r}, already returned for "
                        f"{seen_ids[submission.id]} of this same campaign -- two "
                        "concurrent jobs cannot share one remote identity. It is "
                        "not recorded; the submissions recorded before it stand. "
                        "Run `reconcile` for this worker before submitting again"
                    )
                seen_ids[submission.id] = f"slot {slot} of worker {row.plan.worker!r}"

                event = LEDGER.submitted_event(
                    entrypoint=str(relative_entrypoint),
                    source_digest=digest,
                    submission_id=submission.id,
                    worker=row.plan.worker,
                    requested_capacity=row.plan.requested,
                    granted_capacity=row.plan.granted,
                    slot=slot if slot > 1 else None,
                    units=share,
                    carried_from=planned[1] if planned else None,
                )
                LEDGER.append(ledger_path, event)
                entry = {"slot": slot, "units": list(share), "submissionId": submission.id}
                if planned:
                    entry["carry"] = planned[0]
                    if planned[1]:
                        entry["carriedFrom"] = [
                            {"submissionId": source["submissionId"], "ref": source["ref"]}
                            for source in planned[1]
                        ]
                submissions.append(entry)
            # `submissionId` keeps naming slot 1's submission (the only one
            # a one-slot worker has); `submissions` lists every slot's.
            submission_id = submissions[0]["submissionId"] if submissions else None

            assignments.append(
                {
                    "worker": row.plan.worker,
                    "requested": row.plan.requested,
                    "cap": row.plan.cap,
                    "inFlight": row.plan.in_flight,
                    "granted": row.plan.granted,
                    "inFlightSource": row.plan.in_flight_source,
                    "units": list(row.units),
                    "submissionId": submission_id,
                    "submissions": submissions,
                }
            )

        campaign = {
            "assignments": assignments,
            "unplaced": list(distribution.unplaced),
            "skipped": [
                {"worker": row.worker, "reason": row.reason} for row in distribution.skipped
            ],
            "ledgerPath": ledger_path,
            "staleness": _job_folder_staleness(resolved_entrypoint),
            "smoke": smoke,
        }
        if inputs_status is not None:
            campaign["inputs"] = inputs_status
        return campaign

    if worker is None:
        plan = PACKER.select(
            adapter=adapter,
            requested=requested,
            ledger_lines=ledger_lines,
            live_digest=digest,
        )
        worker = plan.worker
    else:
        plan = PACKER.plan(
            adapter=adapter,
            worker_id=worker,
            requested=requested,
            ledger_lines=ledger_lines,
            live_digest=digest,
        )

    run_config = {"mode": "smoke"} if smoke else {}
    run_config = {**run_config, **session_config, **inputs_config}
    # A single send carries nothing, but it must not push over an output a
    # pending continuation still reads, nor over a kernel still running.
    protected = _protected_refs(
        adapter, target=target, product=resolved_product,
        resolved_entrypoint=resolved_entrypoint,
        relative_entrypoint=relative_entrypoint, digest=digest, smoke=smoke,
    )
    if protected:
        run_config["carryProtected"] = protected
    job = ADAPTER.Job(entrypoint=resolved_entrypoint, run_config=run_config, worker=worker)
    submission = adapter.submit(job)

    event = LEDGER.submitted_event(
        entrypoint=str(relative_entrypoint),
        source_digest=digest,
        submission_id=submission.id,
        worker=worker,
        requested_capacity=requested,
        granted_capacity=plan.granted,
    )
    LEDGER.append(ledger_path, event)

    single = {
        "plan": plan,
        "submission": submission,
        "event": event,
        "ledgerPath": ledger_path,
        "staleness": _job_folder_staleness(resolved_entrypoint),
        "smoke": smoke,
    }
    if inputs_status is not None:
        single["inputs"] = inputs_status
    # session-chains: a job declaring carry paths is a chain of sessions, and
    # only a share (`--unit`) lets `remaining` and the carry evidence see a
    # run cut at its limit. Sent as before, but said so.
    if not smoke and _declared_carry_paths(resolved_entrypoint):
        single["carry"] = "no-share"
        single["carryWarning"] = NO_SHARE_CARRY_WARNING
    return single


def cmd_status(
    *,
    target: str | Path,
    entrypoint: str | Path,
    source_digest: Callable[[Path, str], str] | None = None,
) -> dict:
    """The fold, rendered for a human: per-entrypoint state, what is
    pending, what is `staleInFlight`, what is quarantined, and how many
    lines could not be read at all — for `ledger.jsonl`, at this dict's own
    top-level keys, exactly as before, PLUS the same shape folded from
    `smoke.jsonl` alone, under `"smoke"`. The two are reported side by side,
    never merged into one: `smoke.jsonl` is folded through its own,
    separate `LEDGER.fold()` call, so a rehearsal submission still can never
    become part of `entrypoints`' own `latest[entrypoint]` index — only a
    second, clearly-labeled section a human can also see, where before
    there was nothing to see at all for a smoke-only entrypoint.

    This function accepts no `adapter` parameter at all — not merely
    "does not call one" but structurally cannot, since none is in scope to
    call. `status` reports what the ledgers already say; it never resolves
    anything, and the signature itself is what makes that true rather than
    a rule this function's body would otherwise have to be trusted to
    follow.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    product = product_for(target, entrypoint, command="status")
    ledger_path = _main_ledger_path(target, product)
    smoke_ledger_path = _smoke_ledger_path(target, product)

    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, product)
    state = LEDGER.fold(_read_ledger_lines(ledger_path), live_digest=live)
    smoke_state = LEDGER.fold(_read_ledger_lines(smoke_ledger_path), live_digest=live)

    def _render(folded: "LEDGER.LedgerState") -> dict:
        # `folded.entrypoints` is keyed by `(entrypoint, worker)` (F4:
        # Decision 6) -- `"entrypoints"` ALWAYS nests a per-worker sub-dict
        # under each entrypoint now, a documented breaking shape change
        # from the flat `{entrypoint: {...}}` this used to render. Five
        # accounts submitting the same entrypoint used to fold into one
        # flat entry where four of the five silently vanished; nesting is
        # what makes all five visible in one render.
        nested: dict[str, dict[str, dict]] = {}
        for (entry_name, worker), entry in folded.entrypoints.items():
            nested.setdefault(entry_name, {})[worker] = {
                "state": entry.state,
                "staleInFlight": entry.stale_in_flight,
            }
        return {
            "entrypoints": nested,
            "staleInFlight": folded.stale_in_flight,
            "quarantined": folded.from_stale_submission,
            "unreadableLines": folded.unreadable_lines,
        }

    return {
        "ledgerPath": ledger_path,
        **_render(state),
        "smoke": {"ledgerPath": smoke_ledger_path, **_render(smoke_state)},
        "staleness": _job_folder_staleness(Path(entrypoint).resolve()),
    }


def _job_service(entrypoint: Path) -> str | None:
    """The `service` the job folder's `run-config.json` beside `entrypoint`
    names, or `None` when there is none to read."""
    try:
        config = json.loads((entrypoint.parent / RUN_CONFIG_FILENAME)
                            .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    service = config.get("service") if isinstance(config, dict) else None
    return service if isinstance(service, str) and service.strip() else None


def cmd_remaining(
    *,
    target: str | Path,
    entrypoint: str | Path,
    units: Sequence[str],
    unit_field: str | None = None,
    source_digest: Callable[[Path, str], str] | None = None,
) -> dict:
    """Which of the declared `units` still have no complete result -- the
    list the next campaign sends, and only that list (S6).

    Reads the main ledger only and asks no backend anything (no `adapter`
    parameter, the same discipline `status` holds). Every campaign
    `submitted` event records its own share (`units`), and each is paired
    in append order with the terminal event that settled it
    (`LEDGER.submission_outcomes()`), so a resubmission under an
    identity-stable backend's reused id never erases what an earlier
    submission under that id returned. Only a submission of THIS
    entrypoint, at the CURRENT source digest, counts -- a result from a
    moved source is quarantined by `fetch`, so it completes nothing.

    - `complete`: a unit whose submission was settled `returned`, unless
      the result went to quarantine (it then completes nothing) or carries
      a `partial.json` (the units its `remaining` list names, or the whole
      share when it lists none, stay remaining); or, when
      `unit_field` names the dotted field the target's per-unit records
      carry, a unit a `runs.jsonl` record under that submission's artifact
      (a returned result or bytes `fetch` kept from a run that did not
      finish) declares done;
    - `inFlight`: a unit whose submission has not been settled yet --
      reported apart, never resent, since sending it again would run it
      twice;
    - `unknown`: a unit whose `returned` result is recorded at a path that
      is no longer a directory on disk, so whether it finished cannot be
      read. It completes nothing and stays in `remaining`; `refetch` names,
      per such submission, the `fetch` command that brings the result back
      before its units are sent again;
    - `remaining`: every other declared unit, in the DECLARED order, which
      is the order `distribute`'s consent token binds. Pass it back
      unchanged (`unitArgs` is the same list as repeated `--unit` flags).
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )
    declared = [str(unit) for unit in units]
    if not declared:
        raise RemoteCLIError("remaining needs at least one --unit to check")

    resolved_entrypoint = guard_entrypoint(target, Path(entrypoint))
    product = product_for(target, resolved_entrypoint, command="remaining")
    relative_entrypoint = str(_relative_entrypoint(target, resolved_entrypoint, product))
    ledger_path = _main_ledger_path(target, product)
    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, product)

    quarantine = (target / product / LEDGER_DIRNAME / QUARANTINE_DIRNAME).resolve()
    complete: set[str] = set()
    in_flight: set[str] = set()
    missing: list[tuple[dict, str, list[str]]] = []
    for submitted, terminal in LEDGER.submission_outcomes(_read_ledger_lines(ledger_path)):
        if str(submitted.get("entrypoint")) != relative_entrypoint:
            continue
        if submitted.get("sourceDigest") != live:
            continue
        share = [str(unit) for unit in submitted.get("units") or ()]
        if terminal is None:
            in_flight.update(share)
            continue
        artifact = terminal.get("artifactPath")
        if terminal.get("kind") == "returned":
            # A result `fetch` judged not current went to quarantine: it
            # completes nothing, whatever it holds.
            if artifact and Path(artifact).resolve().is_relative_to(quarantine):
                continue
            # A result deleted (or moved) since `fetch` recorded it cannot
            # say what it finished: never read as complete.
            if artifact and not Path(artifact).is_dir():
                missing.append((submitted, str(artifact), share))
                continue
            # A run that stopped early (at the deadline, say) exits 0 and is
            # `returned`, but its partial.json names what it did not finish.
            stopped, unfinished = (
                SHARD_IO.partial_marker(Path(artifact)) if artifact else (False, None)
            )
            if not stopped:
                complete.update(share)
            elif unfinished is not None:
                complete.update(set(share) - unfinished)
        if unit_field and artifact:
            complete.update(
                set(share) & SHARD_IO.unit_records(Path(artifact), unit_field)
            )
    # A unit some submission completed is complete even if a later one
    # carrying it is still running.
    in_flight -= complete

    remaining = [unit for unit in declared if unit not in complete and unit not in in_flight]
    refetch: list[dict] = []
    unknown: set[str] = set()
    service = _job_service(resolved_entrypoint) or "<backend>"
    for submitted, artifact, share in missing:
        units_left = [unit for unit in declared if unit in share and unit in remaining]
        if not units_left:
            continue
        unknown.update(units_left)
        submission_id = str(submitted.get("submissionId"))
        refetch.append({
            "submissionId": submission_id,
            "units": units_left,
            "artifactPath": artifact,
            "reason": f"the returned result recorded at {artifact} is not on disk, so "
                      f"whether {', '.join(units_left)} finished is unknown; fetch it again "
                      "before resending them",
            "command": f"remote_cli fetch --target {target} --entrypoint "
                       f"{resolved_entrypoint} --submission-id {submission_id} --dest "
                       f"{artifact} --backend {service}",
        })
    return {
        "ledgerPath": ledger_path,
        "entrypoint": relative_entrypoint,
        "declared": declared,
        "complete": [unit for unit in declared if unit in complete],
        "inFlight": [unit for unit in declared if unit in in_flight],
        "unknown": [unit for unit in declared if unit in unknown],
        "refetch": refetch,
        "remaining": remaining,
        "unitArgs": [token for unit in remaining for token in ("--unit", unit)],
        "unitField": unit_field,
    }


def cmd_distribute(
    *,
    target: str | Path,
    entrypoint: str | Path,
    adapter: "ADAPTER.Adapter",
    units: Sequence[str],
    source_digest: Callable[[Path, str], str] | None = None,
) -> dict:
    """Report how `units` -- opaque identifiers this function never
    inspects beyond passing them through -- would spread across every
    worker `adapter` reports right now, aggregated by
    `packer.distribute()`. Nothing is recorded and nothing is handed to
    the adapter's own work-issuing operation: this call's only route to
    the adapter is `distribute()`'s own health read, the same
    `list_active()`/`list_active()`-fallback path `plan()` already uses.

    Target/entrypoint resolve exactly as `cmd_status` resolves them --
    `product_for()`, the same main ledger path, the same digest seam --
    because this is `status`'s read discipline extended across every
    worker at once, never a dispatch-and-record command's write one.
    Unlike `cmd_status`,
    an `adapter` parameter genuinely is in scope, because a worker's
    health is read live here; that live read is the only thing this
    function does with the adapter, and three separate proofs at the
    CLI layer -- a double forbidding any work-issuing call, a whole-tree
    hash snapshot proving no path under `target` ever changes, and this
    function's own source naming neither of the two operations that
    would move work or record it -- hold that plainly rather than
    resting on this paragraph alone.

    The returned mapping carries four separate facts, mirroring
    `packer.Distribution` field for field: `units` (how many were
    handed in), `places` (total granted capacity, summed across every
    healthy worker), `assigned` (how many of `units` actually landed
    somewhere), and `unplaced` (the exact identities that did not).
    `assignments` renders each worker's whole `Plan` -- all four of its
    own numbers, plus `inFlightSource` -- next to the identities it was
    given, never a bare granted count alone; `skipped` names every
    worker `packer.distribute()` could not use and why.

    PLUS a fifth fact this call is the ONE place that ever prints
    (Finding 3; Decision 4): `consentToken`, the digest a caller must
    pass back through `--consent` before this exact pin, entrypoint and
    ordered unit list may go on to spend a single account's quota.
    Computed by `campaign_consent_token()` -- the SAME function the
    quota-spending command's own verification calls -- never a second,
    independently written hash here that could quietly drift from it.
    This function still issues no work and records nothing: printing a
    token is no more a write than reporting `places` or `unplaced`
    already was.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    resolved_entrypoint = Path(entrypoint).resolve()
    product = product_for(target, resolved_entrypoint, command="distribute")
    relative_entrypoint = _relative_entrypoint(target, resolved_entrypoint, product)
    ledger_path = _main_ledger_path(target, product)
    ledger_lines = _read_ledger_lines(ledger_path)

    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, product)

    # kernel-carry S4: a continuation is placed on the worker that produced
    # its earlier output -- the same affinity the launch applies, so the
    # preview and the launch agree. A job declaring no carry paths has none.
    evidence = (
        _carry_evidence(
            target=target, product=product,
            relative_entrypoint=str(relative_entrypoint),
            live_digest=live, ledger_lines=ledger_lines,
        )
        if _declared_carry_paths(resolved_entrypoint)
        else {}
    )
    result = PACKER.distribute(
        adapter=adapter, units=units, ledger_lines=ledger_lines, live_digest=live,
        affinity=_carry_affinity(evidence, units) or None,
    )

    consent_token = campaign_consent_token(
        pin_commit=_job_folder_commit(resolved_entrypoint),
        relative_entrypoint=relative_entrypoint,
        units=units,
    )

    return {
        "units": len(result.units),
        "places": result.places,
        "assigned": len(result.units) - len(result.unplaced),
        "unplaced": list(result.unplaced),
        "assignments": [
            {
                "worker": row.plan.worker,
                "requested": row.plan.requested,
                "cap": row.plan.cap,
                "inFlight": row.plan.in_flight,
                "granted": row.plan.granted,
                "inFlightSource": row.plan.in_flight_source,
                "units": list(row.units),
                "shares": [list(share) for share in PACKER.slot_shares(row)],
            }
            for row in result.assignments
        ],
        "skipped": [{"worker": row.worker, "reason": row.reason} for row in result.skipped],
        "consentToken": consent_token,
    }


def cmd_poll(*, submission_id: str, adapter: "ADAPTER.Adapter") -> "ADAPTER.Status":
    """Ask the adapter for one submission's status, in the seam's own
    five-value vocabulary — never the backend's raw text.

    `ADAPTER.Status.__post_init__` already refuses an out-of-vocabulary
    `state` for a genuine `Status` built the ordinary way, but that
    validation runs only at construction time, inside the adapter, and this
    function has no way to confirm every adapter actually goes through it —
    a misbehaving adapter could hand back any object carrying a `.state`
    attribute the ordinary constructor never touched. The check below is
    this seam's OWN refusal, made again at the one place a bad value would
    otherwise reach a caller: a state outside `ADAPTER.STATES` is the
    adapter's fault, and it is refused here, not translated, not guessed
    at, and never passed through.
    """
    status = adapter.poll(submission_id)
    state = getattr(status, "state", None)
    if state not in ADAPTER.STATES:
        raise RemoteCLIError(
            f"adapter.poll() returned state {state!r}, outside this seam's "
            f"own vocabulary {ADAPTER.STATES}; that is the adapter's fault, "
            "not something this CLI passes through"
        )
    return status


def cmd_fetch(
    *,
    target: str | Path,
    entrypoint: str | Path,
    submission_id: str,
    dest: str | Path | None,
    adapter: "ADAPTER.Adapter",
    source_digest: Callable[[Path, str], str] | None = None,
    force: bool = False,
    smoke: bool = False,
) -> dict:
    """Materialize one submission's result, quarantining it structurally
    when it is not judged current — never discarding it, and never merging
    it either.

    Ordering is fixed, and every step past the first exists to protect the
    one fact that matters most: a `returned` event must never be recorded
    unless the artifact it names is actually, completely, on disk.

    0. Once `final_dest` is known (step 2's placement decision), and
       BEFORE `adapter.fetch()` is ever called: if `final_dest` already
       exists, this is a re-fetch of a submission this call already
       materialized. Paying for a second download only to discover that
       `os.replace()` cannot replace a non-empty destination directory
       (`OSError: [Errno 66] Directory not empty`) is the wrong place to
       notice — the guard runs here, before the network call, not after
       it. Default: refuse cleanly, naming the existing path and the way
       out (`--force`). `force=True` means "the destination is already
       materialized, replace it" — and the replacement is DELAYED to
       step 6: nothing destructive runs here. The old tree survives until
       the adapter has actually returned a complete materialization in
       `.partial/`, so a fetch that fails mid-download or comes back
       `complete=False` leaves the previous artifact intact rather than
       trading a working artifact for a `.partial/` (D15). A duplicate
       `returned` ledger event, if one is ever appended for the same
       submission id regardless, is harmless: `fold()` has no accumulator
       for it — `terminal_by_id[submissionId]` is an overwrite by an
       equal-kind event and `verdicts[submissionId]` recomputes the
       identical value under the identical key.
    1. `<final_dest>.partial/` is a DIFFERENT fact from step 0's, and it
       is checked first — before step 0's `shutil.rmtree()` can destroy
       anything on a refusal that was going to happen anyway. Its
       presence means a previous fetch of this submission ended without
       reaching step 6's rename: a crashed or killed download, a
       `complete=False` result step 5 deliberately left on disk, or
       another fetch of this same submission running right now. Step 3
       hands that exact path to `adapter.fetch()`, which is free to write
       into a directory that already has files in it — so without this
       guard the leftover run's files and this run's files are promoted
       together, by step 6, as one artifact set that never existed. That
       is worse than either failure this function already refuses,
       because it does not raise: it produces a plausible wrong answer,
       which is precisely what the ledger machinery around it exists to
       prevent. Refuse, naming the leftover path and the action that
       clears it. `--force` does NOT clear it, deliberately: `--force`
       means "the destination is already materialized, replace it", and
       a `.partial/` is neither materialized nor necessarily inert — it
       may hold the only copy of bytes already paid for, or be the live
       working directory of a fetch still running. Removing it is a
       decision with real cost, so this reports and lets the human make
       it.
    2. `LEDGER.currency_verdict()` — the SAME rule `fold()` itself uses for
       an already-recorded `returned` event — is evaluated here BEFORE one
       exists, against the ledger state read at the top of this call. A
       `current` verdict uses the caller's own `dest`; anything else
       (`fromStaleSubmission`) overrides `dest` entirely and reroutes to
       `<target>/<Name>/.remote-execution/quarantine/<submissionId>/` — a
       location structurally outside `Results/shards/`, the only tree a
       shard reader ever enumerates. This is a placement decision made
       once, not a filter a merge step could forget to apply later: the
       artifact is never even offered a path a merge could reach.
    3. `observed_concurrency` is read from the SAME pre-fetch ledger state,
       via `LedgerState.pending_for()` — the count of this worker's pending
       submissions at the instant just before this one is about to be
       recorded as done, including itself. A grant the packer allowed for
       N concurrent jobs, honored by the service for fewer than N, shows up
       here as a smaller number than N — visible, not assumed.
    4. `adapter.fetch()` is handed `<dest-or-quarantine>.partial/`, never
       the final path directly. This is the ONE call in this whole function
       that can fail partway through after having already written SOME
       bytes to disk — a network drop, a killed process, a raised
       exception from inside the adapter itself. Nothing before this line
       has touched the filesystem at all, and nothing after it runs unless
       this call returns normally. With `--force` and an existing
       destination, that destination is still completely intact at this
       point: its removal is step 6's, gated on this call returning a
       complete materialization.
    5. `Fetched.complete` is checked before anything else happens. `False`
       means the backend itself considers the result unfinished, and it is
       never renamed into `final_dest` nor recorded `returned` (S5,
       session checkpoints). What came back is moved out of `.partial/` to
       `partial/<submissionId>/<UTC stamp>/` and returned as `path` -- kept,
       and no longer able to refuse a later fetch -- and `adapter.poll()`
       decides what it is: a run still going leaves the ledger `pending`
       (a retry is safe), while a run over without a complete result
       (`failed`, or `unknown` after a reclaim) is recorded `errored` with
       the kept path. An adapter that cannot reach the run at all is
       handled the same way when an earlier fetch kept a snapshot. Only
       `complete=True` reaches the rename.
    6. `os.replace()` — an atomic rename on the same filesystem — moves the
       `.partial/` directory into its final name. This is the one line
       that turns "an artifact happens to exist on disk" into "the
       artifact is at the path this call promises callers", and it runs
       before the ledger is touched. With `--force` and an existing
       destination, THIS is where the old tree is removed — immediately
       before the rename, only once `complete=True` has actually landed
       (D15) — never step 0's pre-fetch `shutil.rmtree()` the flag used to
       run.
    7. `LEDGER.append()` runs LAST, only after the rename above has
       already succeeded. If the process is killed at any point before
       this line, the submission reads back as `pending` on the next fold
       — retryable, never a false `returned` — because nothing before this
       line ever wrote to the ledger.
    """
    # Pure-argv pairing check, above every filesystem call: a rehearsal's
    # destination is computed and cannot be chosen, and a real fetch has no
    # computed destination to fall back to. `--dest` losing `required=True`
    # on the parser (so `--smoke` can omit it) opens the second half of
    # this hole the instant it happens, so both directions are checked
    # together here, not as two separate smoke-only refusals.
    if smoke and dest is not None:
        raise RemoteCLIError(
            "fetch --smoke computes its own rehearsal destination -- "
            "--dest is refused under --smoke, never merely defaulted away "
            "from"
        )
    if not smoke and dest is None:
        raise RemoteCLIError(
            "fetch requires --dest for a real (non-smoke) fetch -- only "
            "--smoke computes its own destination"
        )

    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    product = product_for(target, entrypoint, command="fetch")
    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, product)

    # `resolve_submission_ledger()` is what makes this reach a submission
    # recorded by `submit --smoke` into `smoke.jsonl` — this used to hardcode
    # `LEDGER_FILENAME` and could never find one, at all, no matter how
    # complete the artifact it was asked to fetch.
    ledger_path, state, arbitration = resolve_submission_ledger(
        target, product, submission_id, live, smoke=smoke
    )
    submission = state.by_id[submission_id]

    verdict = LEDGER.currency_verdict(submission, state.latest, live)
    if smoke:
        final_dest = target / product / LEDGER_DIRNAME / REHEARSAL_DIRNAME / submission_id
    elif verdict == "current":
        final_dest = Path(dest).resolve()
    else:
        final_dest = target / product / LEDGER_DIRNAME / QUARANTINE_DIRNAME / submission_id

    # `submission_id` originates from the remote service's response (the
    # ledger's own recorded `submitted` event, ultimately from
    # `adapter.submit()`'s returned id) and reaches this path join
    # unguarded otherwise -- the filesystem-destination-from-service-
    # supplied-`submission_id` threat-matrix row. `.resolve()` collapses
    # any `..` component; a result that escaped `LEDGER_DIRNAME` proves the
    # id was shaped to break out, so refuse before `adapter.fetch()` ever
    # runs and before anything is written.
    if smoke or verdict != "current":
        ledger_root = (target / product / LEDGER_DIRNAME).resolve()
        if ledger_root != final_dest.resolve() and ledger_root not in final_dest.resolve().parents:
            raise RemoteCLIError(
                f"submission id {submission_id!r} does not resolve to a "
                f"path under {ledger_root} -- refusing before any fetch"
            )

    partial_dest = final_dest.with_name(final_dest.name + PARTIAL_SUFFIX)

    # Ahead of the `--force` removal below on purpose: a refusal that was
    # going to happen anyway must not first delete an already-fetched tree.
    if partial_dest.exists():
        raise RemoteCLIError(
            f"a leftover {partial_dest} exists from a fetch that never "
            "finished -- a crashed or killed download, a result the "
            "backend reported as incomplete, or another fetch of this "
            "same submission running right now. It is never merged into "
            "and never promoted, because mixing two runs' files into one "
            "artifact set is a wrong answer that does not announce "
            "itself. --force does not clear it: it may hold the only "
            "copy of bytes already paid for, or be a running fetch's "
            "working directory. Inspect it, then remove it by hand "
            f"(rm -rf {partial_dest}) before retrying"
        )

    if final_dest.exists():
        if not force:
            raise RemoteCLIError(
                f"already fetched at {final_dest} -- pass --force to "
                "remove the existing directory and re-fetch"
            )
        # NO pre-emptive `shutil.rmtree` here (D15). The previous fetch's
        # tree survives until a successful materialization has actually
        # landed in `.partial/` and `complete=True` was returned — see
        # step 6 below, where the removal happens immediately before the
        # rename. A fetch that fails mid-download, or comes back
        # `complete=False`, must leave the existing artifact intact.

    observed_concurrency = state.pending_for(submission["worker"])
    staleness = _job_folder_staleness(Path(entrypoint).resolve())

    kept_root = target / product / LEDGER_DIRNAME / KEPT_PARTIAL_DIRNAME / submission_id
    ledger_root = (target / product / LEDGER_DIRNAME).resolve()
    if ledger_root not in kept_root.resolve().parents:
        raise RemoteCLIError(
            f"submission id {submission_id!r} does not resolve to a "
            f"path under {ledger_root} -- refusing before any fetch"
        )

    try:
        fetched = adapter.fetch(submission_id, partial_dest)
    except ADAPTER.AdapterError as exc:
        # S5: a backend that can no longer reach the run -- a reclaimed or
        # vanished session -- is not the end of its bytes when an earlier
        # fetch already kept a snapshot of them. Whatever this attempt left
        # in `.partial/` is kept the same way, never left to refuse every
        # later fetch. Recorded only when the run's own state says it is
        # over without a complete result; otherwise the refusal stands.
        kept = _keep_partial(partial_dest, kept_root)
        run_state, detail = _run_state(adapter, submission_id)
        latest = kept or _latest_kept(kept_root)
        if run_state in _UNFINISHED_TERMINAL_STATES and latest is not None:
            event = LEDGER.errored_event(
                submission_id=submission_id,
                reason=(
                    f"fetch could not reach the run ({exc}); run state "
                    f"{run_state} ({detail}); the last bytes fetched are kept "
                    f"at {latest}"
                ),
                artifact_path=latest,
                run_state=run_state,
            )
            LEDGER.append(ledger_path, event)
            return {
                "verdict": verdict,
                "complete": False,
                "path": latest,
                "event": event,
                "runState": run_state,
                "staleness": staleness,
                "arbitration": arbitration,
            }
        if kept is not None:
            raise ADAPTER.AdapterError(
                f"{exc} -- the bytes this attempt had already written are kept "
                f"at {kept}"
            ) from exc
        raise

    if not fetched.complete:
        # Never renamed into `final_dest` and never recorded `returned`.
        # The existing `final_dest` (when `--force` was given) is untouched
        # -- the removal below deliberately did not run. What the backend
        # did hand back is KEPT (S5), moved out of `.partial/` so it can
        # never refuse a later fetch, and the run's own state decides
        # whether this is a snapshot of a run still going (nothing
        # recorded: the ledger stays `pending`, the one state a retry can
        # safely start from) or the end of a run that did not finish
        # (recorded `errored`, naming the kept bytes). An EMPTY partial
        # holds no bytes anybody paid for and is simply removed.
        kept = _keep_partial(partial_dest, kept_root)
        run_state, detail = _run_state(adapter, submission_id)
        event = None
        if run_state in _UNFINISHED_TERMINAL_STATES:
            reason = f"run ended without a complete result: {run_state} ({detail})"
            if kept is not None:
                reason = f"{reason}; its output is kept at {kept}"
            event = LEDGER.errored_event(
                submission_id=submission_id,
                reason=reason,
                artifact_path=kept,
                run_state=run_state,
            )
            LEDGER.append(ledger_path, event)
        return {
            "verdict": verdict,
            "complete": False,
            "path": kept,
            "event": event,
            "runState": run_state,
            "staleness": staleness,
            "arbitration": arbitration,
        }

    # D15: the destructive step runs HERE, after the adapter has returned
    # a complete materialization and never before — so `--force` can only
    # ever destroy a previous artifact once its replacement is on disk.
    if final_dest.exists():
        shutil.rmtree(final_dest)
    final_dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(str(partial_dest), str(final_dest))

    event = LEDGER.returned_event(
        submission_id=submission_id,
        artifact_path=str(final_dest),
        observed_concurrency=observed_concurrency,
    )
    LEDGER.append(ledger_path, event)

    return {
        "verdict": verdict,
        "complete": True,
        "path": final_dest,
        "event": event,
        "staleness": staleness,
        "arbitration": arbitration,
    }


def _keep_partial(partial_dest: Path, kept_root: Path) -> Path | None:
    """Move a non-empty `.partial/` to a fresh directory under `kept_root`
    and return it; remove an empty one and return `None`. Never overwrites
    an earlier kept directory: each one may be the only copy of a
    checkpoint already paid for."""
    if not partial_dest.is_dir():
        return None
    if not any(partial_dest.iterdir()):
        partial_dest.rmdir()
        return None
    kept_root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    kept = kept_root / stamp
    suffix = 2
    while kept.exists():
        kept = kept_root / f"{stamp}-{suffix}"
        suffix += 1
    os.replace(str(partial_dest), str(kept))
    return kept


def _latest_kept(kept_root: Path) -> Path | None:
    """The most recently kept directory under `kept_root`, by name (the
    names are sortable UTC stamps), or `None` when nothing was kept."""
    if not kept_root.is_dir():
        return None
    kept = sorted(path for path in kept_root.iterdir() if path.is_dir())
    return kept[-1] if kept else None


def _run_state(adapter: "ADAPTER.Adapter", submission_id: str) -> tuple[str | None, str]:
    """The run's own state, in the seam's vocabulary, for deciding what an
    incomplete fetch means. A poll the backend refuses is `None` -- not
    known, and never read as terminal: nothing is recorded on it."""
    try:
        status = adapter.poll(submission_id)
    except ADAPTER.AdapterError as exc:
        return None, f"poll refused: {exc}"
    return status.state, status.detail


def cmd_reconcile(
    *,
    target: str | Path,
    entrypoint: str | Path,
    worker: str,
    adapter: "ADAPTER.Adapter",
    resolve: bool = False,
    source_digest: Callable[[Path, str], str] | None = None,
    smoke: bool = False,
) -> dict:
    """Compare the ledger's pending submissions for `worker` against what
    `adapter.list_active(worker)` reports right now, in both directions,
    and report the difference. Never resolves either side on its own
    initiative.

    An id `list_active()` reports that this ledger has no `submitted` event
    for at all is `orphanRemote`. It is reported ONLY — never cancelled
    (this function never calls `adapter.cancel()`, the same restraint
    `fold()`'s own `staleInFlight` handling already applies to a source
    that moved out from under a pending submission) and NEVER auto-adopted
    by fabricating a `submitted` line for it. Adoption would have to invent
    a `sourceDigest` this function has no way to know, and `sourceDigest`
    is the entire basis the fold's currency rule later judges a result by
    — a fabricated one would turn every future currency verdict for that id
    into a guess wearing the shape of a fact. Reporting the orphan and
    leaving the ledger untouched is the guarantee-preserving choice;
    adoption is the guarantee-destroying one.

    A `pending` submission EITHER ledger still expects — `ledger.jsonl` or
    `smoke.jsonl`, both folded here, separately, the same way
    `resolve_submission_ledger()` folds them for `fetch` — that
    `list_active()` no longer lists is `orphanLocal`. A still-active SMOKE
    submission is what `local_pending` including `smoke.jsonl`'s own pending
    ids actually protects here: without it, a rehearsal the service still
    considers active would misreport as `orphanRemote` on every call, since
    a smoke submission never touches `ledger.jsonl` at all. It is always
    reported, regardless of `resolve`. Only when `resolve=True` — reserved
    for a human explicitly passing `--resolve`, never set by any automated
    caller in this skill — does this function append one `errored` event
    per orphan, through the exact same `LEDGER.append()` path every other
    terminal event goes through, to WHICHEVER ledger that orphan's own
    `submitted` event actually lives in (`resolve_submission_ledger()`
    again — never assumed to be the main one). `resolve=False`, the
    default, appends nothing at all: an orphan-remote id is reported
    without a single ledger write, on every call.

    **The one remote call degrades rather than crashing, and says which
    happened.** `adapter.list_active()` is the only expression here that
    reaches a service, and it used to be unguarded -- so an unreachable
    host, a refusal, a timeout or a rotated token killed the one command an
    operator runs precisely BECAUSE something has already gone wrong.
    `packer.plan()` wraps the identical call, degrades, and reports
    `in_flight_source` so a live count is never mistaken for a fallback
    estimate; this function now does the same thing in its own currency.

    Degrading alone would have been worse than crashing. `orphanLocal: ()`
    from a service that answered means "every pending submission this
    ledger expects is still accounted for" -- the strongest all-clear this
    command can give. From a service that could not be asked it means
    nothing whatsoever, and it is the same empty tuple. So the difference
    is carried by a field and never by the payload's emptiness: `remote`
    is `{"status": "read", "reason": None}` when the service answered and
    `{"status": "unavailable", "reason": <why>}` when it did not, the same
    discipline `_staleness_for()` applies by returning a verdict of
    `unknown` rather than raising, and the same one
    `implementation_cli.prior_work_state()` applies through `recordStatus`
    so an unreadable record can never pass for a clean one. On an
    unavailable read both orphan tuples are empty, and the function returns
    BEFORE the `resolve` block rather than relying on that block to iterate
    an empty tuple: `--resolve` appends `errored` events on the strength of
    the service having said those ids are gone, and a read that never
    happened said nothing.

    `WorkerUnauthorized` is the ONE `list_active()` failure that still
    refuses, re-raised untouched. `plan()` re-raises it out of the identical
    call for the reason the seam states on the exception itself: a revoked
    or expired credential is a decision-bearing fact, not a service that is
    merely unreachable right now. Reporting it as "could not be asked"
    would send an operator to retry a command that cannot succeed until the
    token is replaced, in the same words used for a transient blip.

    Everything OUTSIDE that single call still refuses exactly as before. A
    `--target` that names nothing, an unresolvable product, an unreadable
    ledger: none of those reached the service, and answering "the service
    could not be asked" about them would name the wrong side of the fault.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    product = product_for(target, entrypoint, command="reconcile")
    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, product)

    main_state = LEDGER.fold(
        _read_ledger_lines(_main_ledger_path(target, product)), live_digest=live
    )
    smoke_state = LEDGER.fold(
        _read_ledger_lines(_smoke_ledger_path(target, product)), live_digest=live
    )

    def _pending_ids(folded: "LEDGER.LedgerState") -> set[str]:
        # `folded.entrypoints`/`folded.latest` are keyed by
        # `(entrypoint, worker)` (F4: Decision 6) -- filtering `.latest`
        # by `worker` first and indexing `.entrypoints` by the same pair
        # is what keeps this reconcile call scoped to only THIS worker's
        # own state, never another worker's resubmission of the same
        # entrypoint.
        # Filtered on the event's own `worker` field, never the key's
        # second half: a worker's slot lanes (`LEDGER.lane_key()`) are
        # keyed `<worker>#slot<n>`, and every one of them is this worker's.
        return {
            submission["submissionId"]
            for key, submission in folded.latest.items()
            if submission.get("worker") == worker
            and folded.entrypoints[key].state == "pending"
        }

    # Computed before the remote call so the degraded return below can
    # still carry it: a job folder's staleness is read from this disk and
    # is exactly as true whether or not the service answered.
    staleness = _job_folder_staleness(Path(entrypoint).resolve())

    try:
        remote_active = set(adapter.list_active(worker))
    except ADAPTER.WorkerUnauthorized:
        # NOT degraded, for the reason the seam states on the exception:
        # a revoked credential is a decision-bearing fact, never a mere
        # "service unreachable" one. `packer.plan()` re-raises it out of
        # this identical call, and reporting it here as an unavailable
        # read would describe a dead token in the words used for a blip.
        raise
    except Exception as exc:
        # Unreachable, refusing, timing out, or answering with something
        # unusable. Bare `Exception` rather than `ADAPTER.AdapterError`
        # deliberately, and identically to `plan()`: a concrete adapter
        # shells out to a driver process, so a transport-level failure
        # arrives as itself and never as the seam's own type. The single
        # decision-bearing case is caught above, so nothing that a
        # traceback is for is being swallowed here -- a defect inside this
        # function's own body is outside this `try` entirely.
        return {
            "orphanRemote": (),
            "orphanLocal": (),
            "resolved": (),
            "remote": {
                "status": "unavailable",
                "reason": (
                    f"adapter.list_active({worker!r}) failed, so nothing "
                    f"below says what the service considers active: {exc}"
                ),
            },
            "staleness": staleness,
            "arbitration": (),
        }

    local_pending = _pending_ids(main_state) | _pending_ids(smoke_state)

    orphan_remote = tuple(sorted(remote_active - local_pending))
    orphan_local = tuple(sorted(local_pending - remote_active))

    resolved_events: list[dict] = []
    arbitrations: list[str] = []
    if resolve:
        for submission_id in orphan_local:
            orphan_ledger_path, _, arbitration = resolve_submission_ledger(
                target, product, submission_id, live, smoke=smoke
            )
            if arbitration is not None:
                arbitrations.append(arbitration)
            event = LEDGER.errored_event(
                submission_id=submission_id, reason="not-found-at-service"
            )
            LEDGER.append(orphan_ledger_path, event)
            resolved_events.append(event)

    return {
        "orphanRemote": orphan_remote,
        "orphanLocal": orphan_local,
        "resolved": tuple(resolved_events),
        "remote": {"status": "read", "reason": None},
        "staleness": staleness,
        "arbitration": tuple(arbitrations),
    }


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _target_for_job_dir(resolved_job_dir: Path) -> Path:
    """The repository a job folder belongs to, derived the exact same
    structural way `jobfolder.read()` derives it internally
    (`<target>/tools/<service>/<job-name>/` → `.parents[2]`). Only ever
    called after `JOBFOLDER.read()` has already confirmed this exact
    shape by not raising.
    """
    return resolved_job_dir.parents[2]


def _smoke_ledger_path(target: Path, product: str) -> Path:
    return target / product / LEDGER_DIRNAME / SMOKE_LEDGER_FILENAME


#: The approvals that call for an operator-validated experiment diagram before
#: anything of that product is launched (the kinds `experiment-diagrams` draws).
DIAGRAM_APPROVALS = (("poc", "AGREED.md"), ("experiments", "Experimental_AGREED.md"))


def _diagram_cli():
    """The kit's `diagram_cli.py`, the one owner of the validation record."""
    script = (Path(__file__).resolve().parents[2] / "experiment-diagrams"
              / "scripts" / "diagram_cli.py")
    module_name = "remote_execution_diagram_cli"
    if module_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(module_name, script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return sys.modules[module_name]


#: The two routes by which the operator validates a diagram, and how to draw
#: a missing one -- the same sentence `submit` refuses with and `preflight`
#: names as its fix.
DIAGRAM_ROUTES = (
    "its experiment diagrams, in the dashboard (Experimentos tab, "
    "\"Validar diagrama\") or by approving each one explicitly in the agent chat "
    "(`diagram_cli.py validate`, run only on that approval)")
DIAGRAM_DRAW = ("Draw a missing one with `/experiment-diagrams <poc|experiments>` or the "
                "panel's \"Generar diagrama\".")


def _open_diagrams(product_dir: Path) -> tuple[list[str], list[str]]:
    """`(owed kinds, open "kind: state" items)` for `product_dir`. A product
    holding neither approval marker owes nothing."""
    owed = [kind for kind, marker in DIAGRAM_APPROVALS if (product_dir / marker).is_file()]
    if not owed:
        return [], []
    try:
        cli = _diagram_cli()
    except OSError as exc:
        raise DiagramValidationError(
            "DIAGRAM_NOT_VALIDATED: the experiment-diagrams skill this check reads is not "
            f"installed here ({exc}); run `smith upgrade`.") from None
    return owed, [f"{kind}: {state}" for kind in owed
                  if (state := cli.validation_state(product_dir, kind)) != "validated"]


def _verify_diagrams_validated(product_dir: Path) -> None:
    """Refuse `DIAGRAM_NOT_VALIDATED` while any approved kind's diagram is not
    `validated`. A product holding neither approval marker is not gated."""
    _, open_items = _open_diagrams(product_dir)
    if open_items:
        raise DiagramValidationError(
            "DIAGRAM_NOT_VALIDATED: nothing of this product is launched until the operator "
            f"validates {DIAGRAM_ROUTES}; open: {', '.join(open_items)}. {DIAGRAM_DRAW}")


def _main_ledger_path(target: Path, product: str) -> Path:
    return target / product / LEDGER_DIRNAME / LEDGER_FILENAME


def _read_ledger_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def resolve_submission_ledger(
    target: Path, product: str, submission_id: str, live_digest: str,
    *, smoke: bool = False,
) -> tuple[Path, "LEDGER.LedgerState", str | None]:
    """The one place in this module that answers "which ledger holds THIS
    submission id" — `ledger.jsonl` or `smoke.jsonl` — for every command
    that needs to act on one specific submission afterward (`cmd_fetch`,
    and `cmd_reconcile`'s `--resolve`). Neither command builds a ledger
    path for a submission id any other way: getting one now has exactly
    one route through this module, which is what keeps a future command
    that resolves a submission from being written blind to `smoke.jsonl`
    the way `cmd_status`, `cmd_fetch` and `cmd_reconcile` all were before
    this function existed — there is no second, ad hoc way left to spell
    "the ledger" that could quietly forget the smoke one exists.

    `ledger.jsonl` and `smoke.jsonl` are folded SEPARATELY here, through
    the exact same `LEDGER.fold()` every other reader in this module already
    calls — never concatenated into one call, and never merged into one
    `LedgerState`. That separation is not incidental: it is what
    `test_smoke_submission_never_enters_the_fold_or_supersedes_a_real_run`
    already pins — a smoke submission must never become part of the main
    ledger's own `latest[entrypoint]` index — and folding the two logs
    together here, even transiently, would do exactly that the moment this
    function's caller reused the merged result for anything shaped like
    "the main ledger's state". Each returned `LedgerState` is only ever
    valid against the file it was folded from; this function hands back
    both the path and that matching state together so no caller has to
    remember which one goes with which.

    A submission id absent from BOTH files is refused: there is nothing on
    record for it anywhere this module looks.

    A submission id present in BOTH is NOT, on its own, refused. A backend
    is free to mint an id deterministically from a worker/entrypoint pair,
    so a legitimate rehearse-then-launch pair — `submit --smoke` followed
    by a real `submit` of the identical job — can reuse the identical id BY
    CONSTRUCTION. A shared id is an expected condition on such a backend,
    not corruption. Only the two `submitted` records' recorded `entrypoint`
    and `worker` fields are compared (never the id string itself —
    `adapter.py` permits the ledger exactly equality and dict-key use on an
    id, and forbids splitting, parsing, or pattern-matching any part of
    it):

    - DISAGREE on `entrypoint` or `worker` → still refused, unconditionally
      (even under `smoke=True`): one record lies about what was actually
      submitted, and picking either file to act on would be guessing. This
      is the genuine corruption case — a hand-edited ledger line, a ledger
      file copied across targets, or an adapter whose id no longer encodes
      worker/entrypoint.
    - AGREE → resolves to the main ledger by default, with a returned
      arbitration note (the caller decides whether/where to surface it —
      this function never writes to stderr; every `file=sys.stderr` call
      in this module lives in `main()`). `smoke=True` (mirroring `submit
      --smoke`) overrides that precedence and resolves to the smoke ledger
      instead, with no note. `smoke` overrides PRECEDENCE only, never
      COHERENCE: the disagreement refusal above still fires regardless of
      `smoke`.
    """
    main_path = _main_ledger_path(target, product)
    smoke_path = _smoke_ledger_path(target, product)
    main_state = LEDGER.fold(_read_ledger_lines(main_path), live_digest=live_digest)
    smoke_state = LEDGER.fold(_read_ledger_lines(smoke_path), live_digest=live_digest)

    in_main = submission_id in main_state.by_id
    in_smoke = submission_id in smoke_state.by_id

    if in_main and in_smoke:
        main_record = main_state.by_id[submission_id]
        smoke_record = smoke_state.by_id[submission_id]
        if main_record["entrypoint"] != smoke_record["entrypoint"]:
            raise RemoteCLIError(
                f"submission {submission_id!r} is recorded in both "
                f"{main_path} and {smoke_path}, and the two records "
                f"disagree on entrypoint ({main_record['entrypoint']!r} vs "
                f"{smoke_record['entrypoint']!r}); refusing to guess which "
                "one is authoritative"
            )
        if main_record["worker"] != smoke_record["worker"]:
            raise RemoteCLIError(
                f"submission {submission_id!r} is recorded in both "
                f"{main_path} and {smoke_path}, and the two records "
                f"disagree on worker ({main_record['worker']!r} vs "
                f"{smoke_record['worker']!r}); refusing to guess which one "
                "is authoritative"
            )
        if smoke:
            return (smoke_path, smoke_state, None)
        note = (
            f"submission {submission_id!r} is recorded in both {main_path} "
            f"and {smoke_path} with agreeing entrypoint/worker; resolved to "
            f"the main ledger {main_path}"
        )
        return (main_path, main_state, note)
    if not in_main and not in_smoke:
        raise RemoteCLIError(
            f"no submitted event on record for submission {submission_id!r} "
            f"in {main_path} or {smoke_path}"
        )
    return (main_path, main_state, None) if in_main else (smoke_path, smoke_state, None)


#: The evidence stamp a smoke writes into its working directory.
SHARD_STAMP_FILENAME = "shard.json"


def cmd_smoke_record(
    *,
    job_dir: str | Path,
    artifact_path: str | Path,
    worker: str,
) -> dict:
    """Record a smoke run's verdict — never a human assertion. Reads
    `artifact_path` (a fetched `shard.json`) and passes iff
    `shard_io.completeness(...)` reports it complete: the SAME predicate
    T10's `merge()` uses, two consumers.

    The `required` field list reaches this function WITHOUT this module
    ever naming a field of its own: read from the job's own
    `run-config.json`, at `run.smoke.requiredEvidence` — a list the TARGET
    declares at `generate-job` time (repeatable `--smoke-required-evidence`
    flag; see `jobfolder.build_run_config()`). This forge module only
    carries that list from where the target wrote it to where
    `shard_io.completeness()` needs it; confirmed by
    `test_remote_cli_source_names_no_evidence_field_of_its_own` that no
    evidence-stamp field path exists in this module's own source — the
    same "caller brings the vocabulary" discipline
    `shard_io.completeness()` already states, carried one hop further.

    Routes through `JOBFOLDER.read()` — the single job-folder reader.
    Unlike `_job_folder_staleness()`, a `JobFolderError` here is NOT
    swallowed: `smoke record` has no legacy-shape fallback to fall through
    to at all.

    Appended to `smoke.jsonl` through the SAME `LEDGER.append()` every
    other event in this skill goes through — see `cmd_submit`'s own
    docstring and the module-level comment above `SMOKE_LEDGER_FILENAME`.
    """
    resolved_job_dir = Path(job_dir).resolve()
    job_folder = JOBFOLDER.read(resolved_job_dir)
    run_config = job_folder.run_config

    smoke_block = run_config.get("run", {}).get("smoke") or {}
    required = list(smoke_block.get("requiredEvidence") or [])

    artifact = Path(artifact_path)
    if artifact.is_dir():
        # A fetched rehearsal folder: the stamp is the file the smoke wrote
        # into its working directory, which is that folder's root.
        artifact = artifact / SHARD_STAMP_FILENAME
        if not artifact.is_file():
            raise RemoteCLIError(
                f"no {SHARD_STAMP_FILENAME} in {artifact.parent}: the smoke "
                f"must write its evidence stamp, {SHARD_STAMP_FILENAME}, into "
                "its working directory -- the folder `fetch --smoke` returns -- "
                "carrying every path the job's run.smoke.requiredEvidence names"
            )
    try:
        artifact_text = artifact.read_text(encoding="utf-8")
    except OSError as exc:
        raise RemoteCLIError(
            f"could not read artifact {artifact_path}: {exc}"
        ) from None
    try:
        stamp = json.loads(artifact_text)
    except json.JSONDecodeError as exc:
        raise RemoteCLIError(f"{artifact_path} is not valid JSON: {exc}") from None

    verdict = SHARD_IO.completeness(stamp, required)
    result = "pass" if verdict["complete"] else "fail"

    target = _target_for_job_dir(resolved_job_dir)
    smoke_ledger_path = _smoke_ledger_path(target, run_config["product"])

    event = {
        "kind": SMOKE_RESULT_KIND,
        "ts": _now(),
        "jobName": run_config["jobName"],
        "result": result,
        "commit": run_config["commit"],
        "worker": worker,
        "missing": verdict["missing"],
    }
    LEDGER.append(smoke_ledger_path, event)

    return {
        "result": result,
        "missing": verdict["missing"],
        "requiredEvidence": required,
        "smokeLedgerPath": smoke_ledger_path,
        "event": event,
    }


def latest_smoke_event(
    smoke_ledger_path: Path, job_name: str, worker: str | None = None
) -> dict | None:
    """The latest `smokeResult` line for `job_name` in `smoke_ledger_path`,
    by append order — last line wins, the same last-write-wins rule
    `ledger.fold()` already applies to its own log. `None` when the smoke
    ledger does not exist or holds no matching record.

    Extracted out of `cmd_readiness()` so a second caller —
    `proposal-implementation`'s own `probe` fact (design #744 section 9)
    — can find the SAME latest record `cmd_readiness()` itself binds
    against, rather than writing a second "walk `smoke.jsonl` for the
    newest match" loop that could quietly drift from this one.

    `worker`, when given, narrows the walk to that worker's own records
    (readiness is per worker: one account's later rehearsal never revokes
    another's). Omitted, it is the job's latest record on any worker, as
    before.
    """
    if not smoke_ledger_path.exists():
        return None
    latest: dict | None = None
    for raw_line in smoke_ledger_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(event, dict)
            and event.get("kind") == SMOKE_RESULT_KIND
            and event.get("jobName") == job_name
            and (worker is None or event.get("worker") == worker)
        ):
            latest = event
    return latest


def cmd_readiness(*, job_dir: str | Path, worker: str) -> dict:
    """States whether `job_dir` is ready to run its full submission on
    `worker` — reports only, the same "resolves nothing" discipline
    `cmd_status()` already holds structurally (no `adapter` parameter):
    issues no submission, offers no menu. (This is remote-execution's own
    report command — not a call into `implementation_cli.py`'s own
    `cmd_probe`, a later task's territory this function does not touch.)

    Binds three facts on ONE record — the latest smoke record for this
    job ON THIS WORKER, by append order in `smoke.jsonl` (last line wins,
    same rule `ledger.fold()` already applies to its own log): `result ==
    "pass"`, `commit` equal to the job's OWN currently-pinned commit,
    `worker` equal to the worker asked about. Per worker (S2, parallel
    campaigns; `rehearse-each-account`): a later rehearsal on ANOTHER
    worker never revokes this one's -- otherwise two accounts could never
    both be ready for the same campaign. No clock: nothing here reads or
    compares a timestamp. A record's usefulness expires the moment the
    job re-pins to a different commit or the worker changes — never after
    elapsed time.
    """
    resolved_job_dir = Path(job_dir).resolve()
    job_folder = JOBFOLDER.read(resolved_job_dir)
    run_config = job_folder.run_config

    target = _target_for_job_dir(resolved_job_dir)
    smoke_ledger_path = _smoke_ledger_path(target, run_config["product"])

    latest = latest_smoke_event(
        smoke_ledger_path, run_config["jobName"], worker=worker
    )

    if latest is None:
        return {
            "ready": False,
            "reason": f"no smoke record on file for this job on worker {worker!r}",
            "latestSmokeRecord": None,
            "staleness": dict(job_folder.staleness),
        }

    ready = (
        latest.get("result") == "pass"
        and latest.get("commit") == run_config["commit"]
        and latest.get("worker") == worker
    )
    reason = None
    if not ready:
        reason = (
            "latest smoke record does not match: expected result 'pass', "
            f"commit {run_config['commit']!r}, worker {worker!r}; got "
            f"result {latest.get('result')!r}, commit {latest.get('commit')!r}, "
            f"worker {latest.get('worker')!r}"
        )

    return {
        "ready": ready,
        "reason": reason,
        "latestSmokeRecord": latest,
        "staleness": dict(job_folder.staleness),
    }


def _construct_adapter(
    adapter_cls: type["ADAPTER.Adapter"],
    credentials_provider: Callable[[str], "ADAPTER.CredentialHandle"],
    repo_credential_path: str | Path | None = None,
    workspace: str | Path | None = None,
) -> "ADAPTER.Adapter":
    """Construct a registered adapter, handing it a credential provider only
    when its own constructor is written to accept one — and, since S3, the
    operator's repo-credential PATH under the same introspection.

    The `Adapter` ABC constrains exactly six operations and nothing about
    `__init__` — a second adapter genuinely may take no arguments at all
    (this skill's own test doubles do exactly that), and that has to keep
    working, unmodified, for the seam's own "zero ledger/packer changes"
    guarantee to mean anything at the CLI's own construction site too.
    Introspecting the signature here, rather than trying `credentials=` and
    falling back on a bare `TypeError`, is what keeps a GENUINE defect
    inside a compliant adapter's own `__init__` from being swallowed as
    "this adapter must not want credentials".

    `repo_credential_path` is passed only when the constructor declares it
    (or takes `**kwargs`), exactly the same rule; both may be passed
    together. It reaches the adapter as the PATH, never the bytes: the
    bytes are read by the adapter at its own single staging expression.
    A caller that supplies it to a class that cannot accept it is already
    impossible from the CLI (`REPO_CREDENTIAL_CARRIER` refuses first), so
    the introspection here is a second, structural belt on the same
    observation the gate makes.
    """
    try:
        parameters = inspect.signature(adapter_cls).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_var_keyword = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    )
    kwargs: dict[str, object] = {}
    if "credentials" in parameters or accepts_var_keyword:
        kwargs["credentials"] = credentials_provider
    if repo_credential_path is not None and (
        "repo_credential_path" in parameters or accepts_var_keyword
    ):
        kwargs["repo_credential_path"] = repo_credential_path
    # remote-preflight F3: the workspace whose team registry and account
    # store the adapter reads, passed under the same introspection and only
    # when a caller names one (`preflight --workspace`); omitted, every
    # adapter keeps its own default, the workspace it ships inside.
    if workspace is not None and ("workspace" in parameters or accepts_var_keyword):
        kwargs["workspace"] = Path(workspace)
    return adapter_cls(**kwargs)


def _accounts_cli_for(adapter_cls: type["ADAPTER.Adapter"]) -> Path | None:
    """Read a resolved backend's own credential-materializing CLI location
    off its class, without this module ever naming which backend that is.

    `credentials.py` is the only producer of a `CredentialHandle`, but it
    holds no opinion about WHERE a given backend's own materialize command
    lives — that knowledge is confined to the one file per backend allowed
    to name a service at all, one level below this seam, through that
    module's own `CREDENTIAL_CLI` class attribute. `CREDENTIAL_CLI` is an
    ordinary class attribute, not one of the `Adapter` ABC's six
    operations, so an adapter that never declares one (this skill's own
    test doubles included) is read as `None` here — `credentials.provider()`
    only refuses if it is actually asked to materialize with neither this
    nor `--credential-dir` supplied.
    """
    return getattr(adapter_cls, "CREDENTIAL_CLI", None)


def _repo_credential_carrier(adapter_cls: type["ADAPTER.Adapter"]) -> bool:
    """Whether a resolved backend declares it can stage a runner-side repo
    credential — read off the class exactly the way `_accounts_cli_for()`
    reads `CREDENTIAL_CLI`, so this module still never names a backend.

    `REPO_CREDENTIAL_CARRIER` is an ordinary class attribute, not one of
    the `Adapter` ABC's six operations, and a backend that never declares
    one is read as `False` here. That default is the point (S3/D6): a
    credential handed to a non-carrier would authenticate this process's
    own reachability probe while the runner that probe stands in for
    still could not clone — the credential would make the answer MORE
    wrong, not less. So `--repo-credential` on a non-carrier refuses
    before any probe runs, and a non-carrier's inability is declared by
    that omission rather than by an edit to its own module.
    """
    return bool(getattr(adapter_cls, "REPO_CREDENTIAL_CARRIER", False))


def _uncarried_repo_credential(backend: str) -> "RemoteCLIError":
    """The refusal both dispatch branches raise for a non-carrier."""
    return RemoteCLIError(
        f"--repo-credential was given, but the {backend!r} backend does not "
        "declare REPO_CREDENTIAL_CARRIER = True: it has no runner-side "
        "credential path, so a credential could authenticate only this "
        "process's own probe while the runner that probe stands in for "
        "still could not clone. Refusing before any probe runs — drop "
        "--repo-credential for this backend."
    )


ADAPTERS_DIRNAME = "adapters"

# `--backend`'s raw value is the one part of this mechanism actually driven
# by untrusted input, so it is constrained before it ever reaches the
# filesystem: a bare identifier only, no `.`, `/`, or `\\` — which is what
# makes `..`, an absolute path, or any other directory-separator trick
# impossible to SPELL in the first place, not merely unlikely to be tried.
_BACKEND_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _load_backend_module(name: str) -> None:
    """Best-effort: if `<this file's own directory>/adapters/<name>.py`
    exists, exec it once so its own top-level `ADAPTER.register(...)` (and,
    where present, `ADAPTER.register_metadata(...)`) calls run — before
    `ADAPTER.resolve(name)` is ever asked to find anything under that same
    name.

    This is the whole mechanism that lets `--backend` name a concrete
    adapter without this module ever importing one directly: a module
    dropped into `adapters/` becomes reachable through `--backend <its own
    filename, minus .py>` with no change to this file at all. It is also
    what keeps this file free of naming a service itself — `name` arrives
    at runtime, off the command line, typed by whoever is running this
    command; nothing in this function or anywhere else in this module ever
    spells a service's name as a literal.

    `name` is constrained BEFORE it ever touches the filesystem:
    `_BACKEND_NAME_RE` admits letters, digits, `_` and `-` only, so `..`, a
    leading `/`, or a `\\` component can never be spelled in it at all —
    refused structurally, not merely rejected after the fact by a
    containment check that a differently-shaped hostile value might slip
    past. The resolved candidate path is then checked a second, independent
    way — `candidate.relative_to(adapters_dir)` — so a future loosening of
    the regex alone could never reopen this by itself.

    Any value failing either check, or naming no file, is left alone here,
    silently: this function only ever ADDS a registration; it never raises
    for a name nothing backs, and it never removes or second-guesses a
    registration a caller already made directly (this skill's own test
    suite registers several fake adapters exactly that way, under names no
    file in `adapters/` ever backs). `ADAPTER.resolve()` still runs
    immediately after every call site below, and stays the one place a
    genuinely unknown backend is refused — now naming what IS registered,
    which is what turns an unknown value into an actionable message instead
    of a dead end.
    """
    if not _BACKEND_NAME_RE.match(name):
        return

    adapters_dir = (Path(__file__).resolve().parent / ADAPTERS_DIRNAME).resolve()
    candidate = (adapters_dir / f"{name}.py").resolve()
    try:
        candidate.relative_to(adapters_dir)
    except ValueError:
        return
    if not candidate.is_file():
        return

    module_name = f"remote_execution_adapters_{name.replace('-', '_')}"
    if module_name in sys.modules:
        return

    spec = importlib.util.spec_from_file_location(module_name, candidate)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    # Registered only once it has actually run — the same "retryable on
    # failure, never cached half-loaded" ordering `_load_source_digest()`
    # above already uses, for the same reason.
    spec.loader.exec_module(module)
    sys.modules[module_name] = module


# ---------------------------------------------------------------------------
# preflight: what a first remote rehearsal used to find, found locally
# ---------------------------------------------------------------------------

#: The workspace env's interpreter, relative to the workspace root: the one
#: that carries this skill's pinned service drivers, and so the one `submit`
#: has to run under.
WORKSPACE_ENV_PYTHON = Path(".micromamba") / "envs" / "papersmith" / "bin" / "python"

#: The workspace this skill was installed into: `<workspace>/skills/
#: remote-execution/scripts/remote_cli.py`.
DEFAULT_WORKSPACE = Path(__file__).resolve().parents[3]

#: Where the datasets skill keeps its registry, relative to the workspace.
DATASETS_REGISTRY = Path("datasets") / "registry.json"

PREFLIGHT_STAGES = ("poc", "full")


def _preflight_row(check: str, status: str, evidence: str, fix: str = "", **extra) -> dict:
    row = {"check": check, "status": status, "evidence": evidence, "fix": fix}
    row.update({key: value for key, value in extra.items() if value is not None})
    return row


def _parallelism_cli():
    """`remote-parallelism`'s CLI module, for its timing reader, its
    estimate formula and its session margin -- the `schedule`/`assess`
    rules, never a second copy of them."""
    module_name = "remote_execution_parallelism_cli"
    if module_name not in sys.modules:
        script = (Path(__file__).resolve().parents[2] / "remote-parallelism"
                  / "scripts" / "parallelism_cli.py")
        spec = importlib.util.spec_from_file_location(module_name, script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[module_name] = module
    return sys.modules[module_name]


def _no_credentials(worker: str) -> "ADAPTER.CredentialHandle":
    raise RemoteCLIError(
        f"preflight never materializes a credential (asked for {worker!r}); "
        "the account check uses the service's own read-only probe")


def _preflight_pin(job_folder: "JOBFOLDER.JobFolder") -> dict:
    staleness = dict(job_folder.staleness)
    state = staleness.get("status")
    commit = job_folder.run_config["commit"]
    if state == "fresh":
        return _preflight_row("pin", "pass", f"the job is pinned to {commit} and its "
                              "clone paths have not moved since")
    changed = ", ".join(staleness.get("changedPaths") or []) or staleness.get("reason") or state
    return _preflight_row(
        "pin", "fail", f"the job's pin {commit} is {state}: {changed}",
        "commit, then `generate-job ... --regenerate` so the job is re-pinned (a re-pinned "
        "job needs a fresh rehearsal and a fresh consent token)")


def _preflight_diagrams(product_dir: Path) -> dict:
    try:
        owed, open_items = _open_diagrams(product_dir)
    except DiagramValidationError as exc:
        return _preflight_row("diagrams", "fail", str(exc), "run `smith upgrade`")
    if not owed:
        return _preflight_row("diagrams", "pass", "the product holds no approval that owes "
                              "an experiment diagram")
    if not open_items:
        return _preflight_row("diagrams", "pass", "every approved kind's diagram is "
                              f"validated: {', '.join(owed)}")
    return _preflight_row(
        "diagrams", "fail", f"`submit` refuses DIAGRAM_NOT_VALIDATED; open: "
        f"{', '.join(open_items)}", f"the operator validates {DIAGRAM_ROUTES}. {DIAGRAM_DRAW}")


def _preflight_interpreter(adapter: "ADAPTER.Adapter", workspace: Path) -> dict:
    hook = getattr(adapter, "interpreter_check", None)
    if not callable(hook):
        return _preflight_row("interpreter", "warn", "this service declares no interpreter "
                              "probe; `submit` finds out at launch", "")
    try:
        result = dict(hook())
    except Exception as exc:  # noqa: BLE001 - a failing probe is a row
        result = {"ok": False, "evidence": f"the interpreter probe failed: {exc}"}
    evidence = f"{result.get('evidence', '')} (interpreter {sys.executable})".strip()
    if result.get("ok"):
        return _preflight_row("interpreter", "pass", evidence)
    env_python = workspace / WORKSPACE_ENV_PYTHON
    if env_python.exists() and env_python.resolve() != Path(sys.executable).resolve():
        fix = (f"run remote_cli under the workspace env interpreter, which carries the pinned "
               f"driver: `{env_python} {Path(__file__).resolve()} preflight ...` (and `submit` "
               "under the same interpreter)")
    else:
        fix = result.get("fix") or (
            f"install this skill's pinned requirements for {sys.executable}, or run remote_cli "
            "under the interpreter that has them")
    return _preflight_row("interpreter", "fail", evidence, fix)


def _preflight_reachability(
    adapter_cls: type["ADAPTER.Adapter"], run_config: Mapping, target: Path,
    repo_credential: Path | None,
) -> dict:
    bundle = run_config.get("codeBundle")
    if bundle is not None:
        return _preflight_row("code-reachability", "pass", "the job carries its code bundle "
                              f"(sha256 {bundle.get('sha256')}); the runner unpacks it and "
                              "never clones")
    repo = run_config.get("repo") or {}
    try:
        JOBFOLDER._verify_commit_reachable(run_config["commit"], repo.get("url"), repo.get("ref"),
                                           decision="preflight", target=target)
        return _preflight_row("code-reachability", "pass", f"{repo.get('url')} serves the pin "
                              "anonymously, as the runner's clone will ask for it")
    except (JOBFOLDER.JobFolderError, OSError) as exc:
        anonymous = str(exc)
    carrier = _repo_credential_carrier(adapter_cls)
    if repo_credential is not None and carrier:
        try:
            JOBFOLDER._verify_commit_reachable(
                run_config["commit"], repo.get("url"), repo.get("ref"), decision="preflight",
                repo_credential_path=repo_credential, target=target)
            return _preflight_row("code-reachability", "pass", "the pin is reachable with the "
                                  "declared repository credential; pass the same "
                                  "`--repo-credential` to `submit`")
        except (JOBFOLDER.JobFolderError, OSError) as exc:
            return _preflight_row("code-reachability", "fail", f"not even with the declared "
                                  f"credential: {exc}", "check the token's repository scope")
    if carrier:
        fix = ("this service carries a repository credential: pass `--repo-credential <token "
               "file>` to `submit` (and to `preflight`, to probe it)")
    elif getattr(adapter_cls, "CODE_BUNDLE_MAX_BYTES", None):
        fix = ("the runner cannot authenticate a clone on this service: regenerate with "
               "`generate-job ... --code-bundle --regenerate`")
    else:
        fix = "publish the pin where the runner can clone it anonymously, then regenerate"
    return _preflight_row("code-reachability", "fail",
                          f"the runner could not clone the pin: {anonymous}", fix)


def _registry_remote_sources(workspace: Path) -> list[str]:
    path = workspace / DATASETS_REGISTRY
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    named = []
    for entry in registry if isinstance(registry, list) else []:
        if not isinstance(entry, dict):
            continue
        remote = entry.get("remote") if isinstance(entry.get("remote"), dict) else {}
        source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        if remote.get("ref"):
            named.append(f"{entry.get('slug')} (published as {remote['ref']})")
        elif source.get("kind") not in (None, "", "synthetic") and source.get("url"):
            named.append(f"{entry.get('slug')} ({source['url']})")
    return named


def _preflight_inputs(adapter_cls: type["ADAPTER.Adapter"], run_config: Mapping,
                      workspace: Path) -> dict:
    declared = list(run_config.get("inputDatasets") or [])
    attaches = bool(getattr(adapter_cls, "INPUT_DATASETS_ROOT", None))
    if declared:
        how = ("attached to the push and mounted read-only" if attaches else
               "not attachable on this service: the runner exports them as null and the "
               "target downloads them")
        return _preflight_row("inputs", "pass", f"the job declares {', '.join(declared)}; {how}")
    sources = _registry_remote_sources(workspace) if attaches else []
    if sources:
        return _preflight_row(
            "inputs", "warn", "the job declares no --input-dataset, and on this service a "
            "non-interactive session cannot download a dataset it was not attached; the "
            f"workspace registry names a remote source: {'; '.join(sources)}",
            "if the target reads it, regenerate with `generate-job ... --dataset <slug> "
            "--regenerate` (the registry entry, with its preparation's sha256) or "
            "`generate-job ... --input-dataset <owner>/<slug> --regenerate`")
    return _preflight_row("inputs", "pass", "the job declares no input dataset"
                          + ("" if attaches else " and this service attaches none"))


def _preflight_accelerator(adapter: "ADAPTER.Adapter", run_config: Mapping, service: str,
                           expect: str | None) -> dict:
    hook = getattr(adapter, "accelerator_request", None)
    if not callable(hook):
        return _preflight_row("accelerator", "warn", "this service does not name the "
                              "accelerator it requests", "")
    try:
        request = dict(hook(dict(run_config)))
    except Exception as exc:  # noqa: BLE001 - an adapter refusal is a row
        return _preflight_row("accelerator", "fail", f"the service refuses the job's "
                              f"accelerator block: {exc}", "regenerate with an "
                              "`--accelerator-kind`/`--accelerator-architecture` the "
                              "service maps")
    name = str(request.get("name"))
    architectures = [str(a) for a in request.get("architectures") or []]
    label = f"{name} ({', '.join(architectures)})" if architectures else name
    if request.get("problem"):
        return _preflight_row("accelerator", "fail", f"the job will request {label}, but "
                              f"{request['problem']}", "regenerate with an "
                              "`--accelerator-architecture` the requested machine has")
    regenerate = ("regenerate with `--accelerator-kind cuda --accelerator-architecture "
                  "<the plan's sm_*>` (the service's own table chooses the machine), or "
                  "correct the plan")
    if expect:
        if expect.lower() in (value.lower() for value in (name, *architectures)):
            return _preflight_row("accelerator", "pass", f"the job will request {label}, as "
                                  f"the plan expects ({expect})")
        return _preflight_row("accelerator", "fail", f"the job will request {label}, but "
                              f"the plan expects {expect}", regenerate)
    default = ADAPTER.resolve_default_accelerator(service)
    declared = run_config.get("accelerator")
    if isinstance(declared, Mapping) and declared.get("kind") == JOBFOLDER.CPU_ONLY_KIND:
        return _preflight_row("accelerator", "pass", f"the job will request {label}: a CPU-only "
                              "session, generated with --accelerator-kind cpu")
    if default is not None:
        kind, default_architectures = default()
        if declared == {"kind": kind, "architectures": list(default_architectures)}:
            return _preflight_row(
                "accelerator", "warn", f"the job will request {label}, the service default "
                "(no --accelerator-* flag was given at generation): a default, not a measured "
                "choice",
                "compare CPU and GPU candidates with `/remote-parallelism plan` over the timing "
                "record; confirm a GPU it recommends with `--expect-accelerator <the plan's "
                "accelerator>`, regenerate with `--accelerator-kind cpu` when it recommends a "
                f"CPU-only session, and if the plan names another GPU, {regenerate}")
    return _preflight_row("accelerator", "pass", f"the job will request {label}")


def _session_fit_rows(par, items: list[dict], run_config: Mapping, service: str,
                      candidate: str | None) -> tuple[list[dict] | None, str, dict | None]:
    """A schema 2 record's rows for this job: its named `candidate`, or every
    candidate of this service on the job's own kind of machine (CPU-only or
    accelerator); the slowest of them is the one a unit must fit.
    Returns the rows, the candidate read, and a row that ends the check early."""
    declared = run_config.get("accelerator")
    cpu_job = isinstance(declared, Mapping) and declared.get("kind") == JOBFOLDER.CPU_ONLY_KIND
    kind = "CPU-only" if cpu_job else "accelerator"
    if candidate is not None:
        items = [item for item in items if par.candidate_of(item) == candidate]
        if items and (items[0]["device"] == "cpu") != cpu_job:
            return None, kind, _preflight_row(
                "session-fit", "warn", f"{candidate} is not a {kind} candidate, and this job runs "
                f"on {'a CPU-only session' if cpu_job else 'an accelerator'}",
                "name a candidate of the job's own machine, or regenerate the job")
    else:
        items = [item for item in items if (item["device"] == "cpu") == cpu_job]
    if not items:
        return None, kind, _preflight_row(
            "session-fit", "warn", f"unmeasured: no {kind} row of "
            f"{candidate or service} in the timing record",
            "run the timing probe on this service's machine for this job")
    by_candidate: dict[str, list[dict]] = {}
    for item in items:
        by_candidate.setdefault(par.candidate_of(item), []).append(item)
    slowest = max(by_candidate, key=lambda name: par.per_unit_of(par.best_setting(by_candidate[name])[0]))
    return par.best_setting(by_candidate[slowest])[0], slowest, None


def _session_fit_estimate(adapter: "ADAPTER.Adapter", run_config: Mapping, service: str,
                          timing: Path, stage: str, units: int,
                          candidate: str | None = None) -> dict:
    """`{"row": <a session-fit row that ends the check early>}`, or the
    measurement: `measured` (its text), `unitMinutes`, `sessionMinutes` (the
    whole stage in one session) and `usable` (the margin's minutes)."""
    limit = _declared_session_limit(adapter)
    if limit is None:
        return {"row": _preflight_row("session-fit", "warn",
                                      "this service declares no session limit", "")}
    if not timing.is_file():
        return {"row": _preflight_row(
            "session-fit", "warn", f"unmeasured: no timing record at {timing}",
            "run the timing probe on this service, then `/remote-parallelism estimate` "
            "(and pass --timing here when the record lives elsewhere)")}
    par = _parallelism_cli()
    try:
        data = par.load_timing(timing, str(timing))
    except par.Refusal as exc:
        return {"row": _preflight_row("session-fit", "warn", f"{exc.code}: {exc.message}",
                                      "repair the timing record")}
    items = [item for item in data["measurements"]
             if str(item.get("host", "")).split(":")[0] == service]
    read = ""
    if data["schema"] == 2 and items:
        items, read, refused = _session_fit_rows(par, items, run_config, service, candidate)
        if refused is not None:
            return {"row": refused}
        read = f"{read}: "
    if not items:
        return {"row": _preflight_row(
            "session-fit", "warn", f"unmeasured on {service}: {timing} holds no measurement "
            "on this service's own host, and a remote host is never estimated from another's",
            "run the timing probe on this service")}
    if len({item["device"] for item in items}) > 1:
        return {"row": _preflight_row("session-fit", "warn", f"{service} was timed on several "
                                      "devices; timing is never pooled across machines",
                                      "keep one device per host in the record")}
    estimate = par.host_estimate(items, data["scales"][stage])
    unit_minutes = float(estimate["high"]) / units / 60
    limit_minutes = limit / 60
    usable = par.usable_session(limit_minutes)
    measured = (f"{read}{stage} upper bound {par.num(estimate['high'])} s over {units} unit(s) is "
                f"{par.num(unit_minutes)} minutes per unit against {par.margin_text(limit_minutes)}")
    return {"measured": measured, "unitMinutes": unit_minutes,
            "sessionMinutes": float(estimate["high"]) / 60, "usable": usable}


def _deadline_rehearsal_required(estimate: Mapping, run_config: Mapping) -> bool:
    """S1: a job that declares carry paths, or whose unit or whole session
    estimate exceeds the usable session, must show it stops at a deadline
    and resumes."""
    if run_config.get("carryPaths"):
        return True
    return "row" not in estimate and estimate["sessionMinutes"] > estimate["usable"]


def _preflight_session_fit(adapter: "ADAPTER.Adapter", run_config: Mapping, service: str,
                           timing: Path, stage: str, units: int,
                           candidate: str | None = None, *,
                           estimate: Mapping | None = None,
                           deadline: Mapping | None = None) -> dict:
    """The `session-fit` row. A unit that spans sessions passes only when
    the job declares carry paths AND the deadline rehearsal (`deadline`,
    the `deadline-rehearsal` row) passed: it fails when that rehearsal
    failed -- no marker, among others -- and warns when it warned, quoting
    why: skipped, or run without ever stopping early."""
    if estimate is None:
        estimate = _session_fit_estimate(adapter, run_config, service, timing, stage, units,
                                         candidate)
    if "row" in estimate:
        return estimate["row"]
    measured = estimate["measured"]
    if estimate["unitMinutes"] <= estimate["usable"]:
        return _preflight_row("session-fit", "pass", f"{measured}: each unit fits one session")
    carry = list(run_config.get("carryPaths") or [])
    if carry:
        spans = (f"{measured}: a unit spans sessions and the job declares carry paths "
                 f"({', '.join(carry)})")
        status = (deadline or {}).get("status")
        if status == "pass":
            return _preflight_row("session-fit", "pass", f"{spans}, and the deadline rehearsal "
                                  "showed the target stop at its deadline and resume")
        if status == "fail":
            return _preflight_row("session-fit", "fail", f"{spans}, but the deadline rehearsal "
                                  f"failed: {deadline.get('evidence')}",
                                  deadline.get("fix") or "")
        evidence = str((deadline or {}).get("evidence") or "")
        if status == "warn" and not evidence.startswith("skipped:"):
            return _preflight_row("session-fit", "warn", f"{spans}, but the deadline "
                                  f"rehearsal did not exercise a stop: {evidence}",
                                  deadline.get("fix") or "")
        why = evidence.removeprefix("skipped:").strip()
        return _preflight_row("session-fit", "warn", f"{spans}, but the deadline rehearsal was "
                              f"skipped{f' ({why})' if why else ''}, so resuming from a "
                              "checkpoint is unproven",
                              (deadline or {}).get("fix") or "rerun preflight with --unit <id> "
                              "for each unit and without --skip-rehearsal")
    return _preflight_row(
        "session-fit", "fail", f"{measured}: a unit does not fit one session",
        "split the work into more units (`--units`, `submit --unit`) along the declared axis, "
        "or checkpoint and regenerate with `--carry-path <checkpoint dir>`")


def _preflight_accounts(adapter: "ADAPTER.Adapter", job_dir: Path, workers: Sequence[str] | None,
                        smoke_command: str) -> list[dict]:
    if workers:
        names = list(workers)
    else:
        try:
            names = [worker.id for worker in adapter.workers()]
        except Exception as exc:  # noqa: BLE001 - a failing listing is a row
            return [_preflight_row("account", "fail", f"the service's workers could not be "
                                   f"listed: {exc}", "check the account registry")]
    if not names:
        return [_preflight_row("account", "fail", "this service has no worker account",
                               "register one per person (`smith team add ... --attest`) and "
                               "validate its credential")]
    hook = getattr(adapter, "account_check", None)
    rows = []
    for worker in names:
        if callable(hook):
            try:
                result = dict(hook(worker))
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "evidence": f"the account probe failed: {exc}"}
        else:
            result = {"ok": None, "evidence": "this service declares no account probe"}
        evidence = str(result.get("evidence", ""))
        if result.get("ok") is False:
            rows.append(_preflight_row("account", "fail", evidence,
                                       result.get("fix") or "validate the account", worker=worker))
            continue
        try:
            readiness = cmd_readiness(job_dir=job_dir, worker=worker)
        except (RemoteCLIError, JOBFOLDER.JobFolderError) as exc:
            readiness = {"ready": False, "reason": str(exc)}
        if readiness["ready"]:
            status = "pass" if result.get("ok") else "warn"
            rows.append(_preflight_row("account", status, f"{evidence}; it has its own passing "
                                       "rehearsal at this pin", "", worker=worker))
            continue
        rows.append(_preflight_row(
            "account", "warn", f"{evidence}; it needs its own rehearsal at this pin "
            f"({readiness.get('reason')})",
            f"after the operator authorizes it: `{smoke_command} --worker {worker}`, then "
            "`fetch --smoke` and `smoke record`", worker=worker))
    return rows


def _preflight_rehearsal(
    *, job_dir: Path, target: Path, run_config: Mapping, adapter: "ADAPTER.Adapter | None",
    interpreter: Path | None, smoke_kwargs: Mapping | None, timeout: float,
    keep: Path | None, skip: bool,
) -> dict:
    if skip:
        return _preflight_row("local-rehearsal", "warn", "skipped (--skip-rehearsal)",
                              "run preflight without --skip-rehearsal before the first "
                              "remote rehearsal")
    local = _load_sibling("remote_execution_local_rehearsal", "local_rehearsal.py")
    python = Path(interpreter) if interpreter is not None else local.target_interpreter(target)
    if not python.exists():
        return _preflight_row(
            "local-rehearsal", "fail", f"the target has no .venv interpreter at {python}",
            "create it with the implementation skill's venv stage (the target's pinned "
            "dependencies installed), or pass --interpreter")
    try:
        result = local.rehearse(
            job_dir=job_dir, target=target, run_config=run_config, interpreter=python,
            completeness=SHARD_IO.completeness, smoke_kwargs=smoke_kwargs,
            session_limit_seconds=_declared_session_limit(adapter) if adapter else None,
            timeout=timeout, keep=keep)
    except local.RehearsalError as exc:
        return _preflight_row("local-rehearsal", "fail", str(exc),
                              exc.fix or "regenerate the job with a smoke block")
    return _preflight_row("local-rehearsal", result["status"], result["evidence"],
                          result["fix"], details=result["details"])


#: The `deadline-rehearsal` row's fix when it could not name the job's units.
DEADLINE_UNITS_FIX = (
    "rerun preflight with --unit <id> for each unit the job's `submit --unit` will send: "
    "partial.json ids must equal those strings, and a submit without --unit records no "
    "share, so `remaining` never lists the units of a run cut at its limit")


def _preflight_deadline(
    *, job_dir: Path, target: Path, run_config: Mapping, adapter: "ADAPTER.Adapter | None",
    interpreter: Path | None, smoke_kwargs: Mapping | None, timeout: float,
    keep: Path | None, skip: bool, unit_ids: Sequence[str] | None, block: str,
    rehearsal: Mapping,
) -> dict:
    """The `deadline-rehearsal` row (session-chains S1): two local runner
    sessions, the first under a deadline that has already arrived
    (`local_rehearsal.deadline_rehearse`). Skipped -- a `warn` -- with
    `--skip-rehearsal`, without `--unit`, or when the local rehearsal
    itself failed."""
    def skipped(why: str, fix: str) -> dict:
        return _preflight_row("deadline-rehearsal", "warn", f"skipped: {why}", fix)

    if skip:
        return skipped("--skip-rehearsal", "run preflight with --unit <id> for each unit and "
                       "without --skip-rehearsal before the first remote rehearsal")
    if rehearsal.get("status") == "fail":
        return skipped("the local rehearsal failed", "fix the local-rehearsal row first")
    if not unit_ids:
        return skipped("no --unit named the job's units", DEADLINE_UNITS_FIX)
    local = _load_sibling("remote_execution_local_rehearsal", "local_rehearsal.py")
    python = Path(interpreter) if interpreter is not None else local.target_interpreter(target)
    try:
        result = local.deadline_rehearse(
            job_dir=job_dir, target=target, run_config=run_config, interpreter=python,
            units=list(unit_ids), partial_marker=SHARD_IO.partial_marker, block=block,
            smoke_kwargs=smoke_kwargs,
            session_limit_seconds=_declared_session_limit(adapter) if adapter else None,
            timeout=timeout,
            keep=Path(keep) / local.DEADLINE_DIRNAME if keep is not None else None)
    except local.RehearsalError as exc:
        return _preflight_row("deadline-rehearsal", "fail", str(exc),
                              exc.fix or "regenerate the job with a smoke block")
    return _preflight_row("deadline-rehearsal", result["status"], result["evidence"],
                          result["fix"], details=result["details"])


def cmd_preflight(
    *,
    target: str | Path,
    entrypoint: str | Path,
    workers: Sequence[str] | None = None,
    workspace: str | Path | None = None,
    interpreter: str | Path | None = None,
    expect_accelerator: str | None = None,
    timing: str | Path | None = None,
    candidate: str | None = None,
    stage: str = "full",
    units: int = 1,
    local_smoke_kwargs: Mapping | None = None,
    local_timeout: float = 600,
    skip_rehearsal: bool = False,
    keep_rehearsal: str | Path | None = None,
    repo_credential: str | Path | None = None,
    unit_ids: Sequence[str] | None = None,
    deadline_block: str = "smoke",
) -> dict:
    """Every check a first remote rehearsal used to fail on, run locally:
    one row per check, `{check, status, evidence, fix}`, `status` one of
    `pass`/`warn`/`fail`. Read-only on every service: it never submits, and
    reaches a service only through the existing read-only probes (the
    anonymous reachability probe `generate-job` runs, an adapter's own
    account and interpreter probes). A `repo_credential` token is read only
    through the generator's single read site, inside that probe, as
    `generate-job` reads it; this function opens no credential file.
    """
    resolved_target = Path(target).resolve()
    resolved = guard_entrypoint(resolved_target, Path(entrypoint))
    job_dir = resolved.parent
    if not (job_dir / RUN_CONFIG_FILENAME).is_file():
        raise RemoteCLIError(f"{resolved} is not a generated job folder's notebook; "
                             "preflight checks a `generate-job` folder's runner.ipynb")
    if stage not in PREFLIGHT_STAGES:
        raise RemoteCLIError(f"--stage {stage!r}: one of {', '.join(PREFLIGHT_STAGES)}")
    if units < 1:
        raise RemoteCLIError("--units must be a positive whole number")
    job_folder = JOBFOLDER.read(job_dir)
    run_config = dict(job_folder.run_config)
    service, product = run_config["service"], run_config["product"]
    workspace_root = Path(workspace).resolve() if workspace is not None else DEFAULT_WORKSPACE
    rows = [_preflight_pin(job_folder), _preflight_diagrams(resolved_target / product)]

    adapter_cls = adapter = None
    _load_backend_module(service)
    try:
        adapter_cls = ADAPTER.resolve(service)
        adapter = _construct_adapter(
            adapter_cls, _no_credentials,
            workspace=workspace_root if workspace is not None else None)
    except KeyError as exc:
        rows.append(_preflight_row("service", "fail", f"no backend is registered as "
                                   f"{service!r}: {exc}", "run `smith upgrade`"))
    if adapter is not None:
        rows.append(_preflight_interpreter(adapter, workspace_root))
        rows.append(_preflight_reachability(
            adapter_cls, run_config, resolved_target,
            Path(repo_credential) if repo_credential is not None else None))
        rows.append(_preflight_inputs(adapter_cls, run_config, workspace_root))
    rehearsal = _preflight_rehearsal(
        job_dir=job_dir, target=resolved_target, run_config=run_config, adapter=adapter,
        interpreter=Path(interpreter) if interpreter is not None else None,
        smoke_kwargs=local_smoke_kwargs, timeout=local_timeout,
        keep=Path(keep_rehearsal) if keep_rehearsal is not None else None,
        skip=skip_rehearsal)
    rows.append(rehearsal)
    if adapter is not None:
        smoke_command = (f"remote_cli submit --smoke --target {resolved_target} "
                         f"--entrypoint {resolved} --backend {service}")
        rows.extend(_preflight_accounts(adapter, job_dir, workers, smoke_command))
        rows.append(_preflight_accelerator(adapter, run_config, service, expect_accelerator))
        timing_path = (Path(timing) if timing is not None
                       else resolved_target / product / "Results" / "timing.json")
        estimate = _session_fit_estimate(adapter, run_config, service, timing_path, stage,
                                         units, candidate)
        deadline = None
        if _deadline_rehearsal_required(estimate, run_config):
            deadline = _preflight_deadline(
                job_dir=job_dir, target=resolved_target, run_config=run_config,
                adapter=adapter,
                interpreter=Path(interpreter) if interpreter is not None else None,
                smoke_kwargs=local_smoke_kwargs, timeout=local_timeout,
                keep=Path(keep_rehearsal) if keep_rehearsal is not None else None,
                skip=skip_rehearsal, unit_ids=unit_ids, block=deadline_block,
                rehearsal=rehearsal)
            rows.append(deadline)
        rows.append(_preflight_session_fit(adapter, run_config, service, timing_path, stage,
                                           units, candidate, estimate=estimate,
                                           deadline=deadline))
    counts = {status: sum(1 for row in rows if row["status"] == status)
              for status in ("pass", "warn", "fail")}
    return {
        "jobFolder": str(job_dir),
        "service": service,
        "commit": run_config["commit"],
        "checks": rows,
        "summary": {**counts, "ok": counts["fail"] == 0},
    }


# ---------------------------------------------------------------------------
# generate-jobs: every remote step's job, from what the target declares
# ---------------------------------------------------------------------------

def _workspace_python(workspace: Path) -> Path:
    env_python = workspace / WORKSPACE_ENV_PYTHON
    return env_python if env_python.exists() else Path(sys.executable)


def cmd_generate_jobs(
    *,
    target: str | Path,
    product: str,
    from_schedule: str | Path | None = None,
    repo_url: str | None = None,
    repo_ref: str | None = None,
    repo_credential: str | Path | None = None,
    smoke_module: str | None = None,
    smoke_function: str | None = None,
    smoke_kwargs: Mapping | None = None,
    smoke_required_evidence: Sequence[str] | None = None,
    regenerate: bool = False,
    datasets: Sequence[str] | None = None,
    workspace: str | Path | None = None,
    accept_unresolved: bool = False,
    accept_unresolved_reads: bool = False,
    accept_produced_reads: bool = False,
) -> dict:
    """One `generate-job` per remote step the product's `__steps__`
    declares (remote-preflight S3), each derived rather than typed:

    - service: the step's `service`, or the one(s) a `schedule` output chose
      for it (one job per chosen service);
    - job folder: the step's `job`; run: the step's notebook among its
      `produces` (`Notebooks/...ipynb`), else its `module`/`function`;
      clone paths: what the generator's own import/read walk computes for
      those entries (plus the notebook itself);
    - code bundle: when the pin is not anonymously reachable and the
      service carries bundles (`CODE_BUNDLE_MAX_BYTES`);
    - environment requirements: the target's pinned requirements minus the
      adapter's `PROVIDED_REQUIREMENTS`;
    - carry paths: the step's non-notebook `produces` roots;
    - inputs: `--dataset` slugs, resolved as `generate-job --dataset` does.

    Every job is attempted; one refusal is that job's row, never the end of
    the others. Returns `{jobs, skipped, summary, next}` where `next` is the
    one `preflight` command over every generated job.
    """
    resolved = JOBFOLDER.resolve_target(target)
    steps = JOB_PLAN.declared_steps(resolved, product)
    remote, skipped = JOB_PLAN.remote_steps(steps)
    if not remote:
        raise RemoteCLIError(
            f"{product} declares no remote step in src/{product.replace('-', '_')}/__init__.py "
            "(or config.py) __steps__: a step needs placement 'remote', a job and a service")
    chosen = JOB_PLAN.schedule_services(Path(from_schedule)) if from_schedule else {}
    unknown = sorted(set(chosen) - {name for name, _ in remote})
    if unknown:
        raise RemoteCLIError(
            f"the schedule names {', '.join(unknown)}, which {product}'s __steps__ does not "
            "declare as a remote step; schedule step ids must be __steps__ names")
    origin, branch = JOB_PLAN.target_remote(resolved)
    url, ref = repo_url or origin, repo_ref or branch
    if not url or not ref:
        raise RemoteCLIError("the target has no origin remote or current branch: pass "
                             "--repo-url and --repo-ref")
    commit = JOBFOLDER._resolve_pin(resolved, None)
    pins = JOB_PLAN.pinned_requirements(resolved)
    workspace_root = Path(workspace).resolve() if workspace is not None else DEFAULT_WORKSPACE
    reachable: bool | None = None
    rows: list[dict] = []
    for step, entry in remote:
        services = chosen.get(step) or ([entry["service"]] if isinstance(entry.get("service"), str)
                                        and entry["service"].strip() else [])
        job = entry.get("job") if isinstance(entry.get("job"), str) else None
        for service in services or [None]:
            row = {"step": step, "service": service, "job": job}
            rows.append(row)
            if not service or not job:
                row.update(status="refused", error="the step declares no "
                           + ("service" if not service else "job"))
                continue
            _load_backend_module(service)
            try:
                adapter_cls = ADAPTER.resolve(service)
            except KeyError:
                adapter_cls = None
            bundle = False
            if adapter_cls is not None and getattr(adapter_cls, "CODE_BUNDLE_MAX_BYTES", None):
                if reachable is None:
                    try:
                        JOBFOLDER._verify_commit_reachable(commit, url, ref,
                                                           decision="generate-jobs",
                                                           target=resolved)
                        reachable = True
                    except (JOBFOLDER.JobFolderError, OSError):
                        reachable = False
                bundle = not reachable
            credential = (Path(repo_credential) if repo_credential is not None and not bundle
                          and adapter_cls is not None and _repo_credential_carrier(adapter_cls)
                          else None)
            notebook = JOB_PLAN.step_notebook(entry)
            module, function = entry.get("module"), entry.get("function")
            requirements = JOB_PLAN.without_provided(
                pins, getattr(adapter_cls, "PROVIDED_REQUIREMENTS", ()) if adapter_cls else ())
            carry = JOB_PLAN.carry_paths(entry)
            entry_notebook = f"{product}/{notebook}" if notebook else None
            try:
                inputs, checks = _dataset_plan(adapter_cls, workspace, datasets, None)
                # The clone paths the generator's own import/read walk
                # computes for this step's entries: exactly what its
                # `computedNotDeclared` check would otherwise refuse.
                walk = JOBFOLDER.resolve_clone_paths(
                    resolved, [m for m in ((None if notebook else module), smoke_module)
                               if isinstance(m, str) and m],
                    ["src"], [entry_notebook] if entry_notebook else [])
                clone_paths = sorted(set(walk["computed"])
                                     | set(walk["computedReadsNotDeclared"])) or ["src"]
                destination = JOBFOLDER.generate_job(
                    target=resolved, service=service, job_name=job, product=product,
                    commit=commit, repo_url=url, repo_ref=ref,
                    repo_credential_path=credential, clone_paths=clone_paths,
                    run_module=None if notebook else module,
                    run_function=None if notebook else function,
                    run_notebook=entry_notebook,
                    smoke_module=smoke_module, smoke_function=smoke_function,
                    smoke_kwargs=smoke_kwargs, smoke_required_evidence=smoke_required_evidence,
                    regenerate=regenerate, accept_unresolved=accept_unresolved,
                    accept_unresolved_reads=accept_unresolved_reads,
                    accept_produced_reads=accept_produced_reads,
                    environment_requirements=requirements or None,
                    carry_paths=carry or None, code_bundle=bundle,
                    input_datasets=inputs, dataset_checks=checks)
            except (JOBFOLDER.JobFolderError, JOB_PLAN.JobPlanError, ADAPTER.AdapterError,
                    KeyError) as exc:
                row.update(status="refused", error=str(exc))
                continue
            row.update(status="generated", jobFolder=str(destination), codeBundle=bundle,
                       inputDatasets=list(inputs or []), carryPaths=carry,
                       environmentRequirements=requirements)
    generated = [row for row in rows if row["status"] == "generated"]
    command = None
    if generated:
        command = (f"{_workspace_python(workspace_root)} {Path(__file__).resolve()} preflight "
                   f"--target {resolved}"
                   + (f" --workspace {workspace_root}" if workspace is not None else "")
                   + "".join(f" --entrypoint {Path(row['jobFolder']) / 'runner.ipynb'}"
                             for row in generated))
    return {"target": str(resolved), "product": product, "commit": commit, "jobs": rows,
            "skipped": skipped,
            "summary": {"generated": len(generated), "refused": len(rows) - len(generated)},
            "next": command}


def _add_dataset_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--dataset", dest="datasets", action="append", default=None, metavar="SLUG",
        help="repeatable: a workspace dataset (datasets/registry.json) the job reads. Its "
        "public ref -- the published remote when public, else the public dataset page its "
        "source names -- is declared as an input dataset, and the official preparation's "
        "sha256 values are recorded as datasetChecks (the runner exports them as "
        "FORGE_DATASET_CHECKS). Nothing is uploaded: an unpublished or private dataset "
        "refuses (DATASET_NOT_PUBLISHED / DATASET_NOT_PUBLIC) naming `/datasets publish` "
        "with the operator's consent")
    command.add_argument(
        "--workspace", type=Path, default=None,
        help="override: the workspace whose datasets/registry.json --dataset reads "
        "(default: the workspace this skill is installed in)")


def _dataset_plan(adapter_cls, workspace: Path | None,
                  slugs: Sequence[str] | None,
                  explicit: Sequence[str] | None) -> tuple[list[str] | None, dict | None]:
    """`(inputDatasets, datasetChecks)` for `--dataset` beside any explicit
    `--input-dataset` refs (kept first, in their order)."""
    if not slugs:
        return (list(explicit) if explicit else None), None
    root = Path(workspace).resolve() if workspace is not None else DEFAULT_WORKSPACE
    host = getattr(adapter_cls, "INPUT_DATASETS_HOST", None) if adapter_cls else None
    refs, checks = JOB_PLAN.dataset_inputs(root, slugs, host)
    merged = list(explicit or [])
    merged += [ref for ref in refs if ref not in merged]
    return merged, checks


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remote_cli",
        description="Forge-owned remote execution CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit = subparsers.add_parser(
        "submit", help="submit one notebook to a registered backend's worker"
    )
    submit.add_argument("--target", required=True, type=Path)
    submit.add_argument("--entrypoint", required=True, type=Path)
    submit.add_argument(
        "--worker", required=False, default=None,
        help="optional: the account to submit under. Omitted, `packer.select()` "
        "picks the first healthy account with capacity, in the accounts CLI's "
        "own declared order — naming one an existing decision, never a "
        "requirement this command asks the caller to make. Naming a specific "
        "account is still a legitimate override and is never gated by "
        "capacity the way automatic selection is: an unhealthy NAMED account "
        "refuses outright rather than silently falling back to another one.",
    )
    submit.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    submit.add_argument("--requested", type=int, default=1)
    submit.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )
    submit.add_argument(
        "--product", default=None,
        help="override: which product's ledger this submission belongs to; wins over a "
        "job folder's own declared run-config.json product and over the legacy shape's "
        "<Name> component",
    )
    submit.add_argument(
        "--smoke", action="store_true",
        help="submit a rehearsal run: mode='smoke', recorded to smoke.jsonl, never ledger.jsonl",
    )
    submit.add_argument(
        "--unit", dest="units", action="append", default=None,
        help="repeatable: the exact same flag `distribute` declares. Switches "
        "`submit` into campaign mode -- `packer.distribute()` replaces "
        "`packer.select()`/`packer.plan()`, spreading across every healthy "
        "account instead of stopping at the first one. Mutually exclusive "
        "with --worker: campaign mode has no single named account to select.",
    )
    submit.add_argument(
        "--consent", default=None,
        help="required for EVERY submission, campaign or single-send, "
        "rehearsal or not: the token authorizing this exact pin, "
        "entrypoint, and ordered unit list (empty for a single send). "
        "With --unit, `distribute --unit ...` mints and prints it first. "
        "Without --unit, there is no minting command -- run `submit` once "
        "with no --consent and it refuses, printing the exact token to "
        "pass back on a second, deliberate invocation. Read only from "
        "parsed argv -- never a config key, an environment variable, or "
        "any switch that outlives this process.",
    )
    submit.add_argument(
        "--repo-credential", dest="repo_credential", type=Path, default=None,
        help="path to a token file for the job's private repository: the "
        "credential-aware reachability probe and the runner's own clone "
        "both authenticate with it (staged for the runner by the backend, "
        "never written into the job folder, never on argv). Only backends "
        "declaring REPO_CREDENTIAL_CARRIER accept it, and with it only "
        "https:// remotes are admissible. Omitted, every probe stays "
        "anonymous, exactly as before.",
    )
    submit.add_argument(
        "--no-carry", dest="no_carry", action="store_true",
        help="campaign mode, for a job declaring --carry-path: start units "
        "an earlier submission left to be continued fresh instead of "
        "attaching that submission's output. Without it a continuation is "
        "carried automatically (carry: attached), reported carry: "
        "unsupported on a backend that cannot mount an earlier output, and "
        "refused CARRY_WORKER_MISMATCH when it was produced on another "
        "worker.",
    )

    status = subparsers.add_parser(
        "status", help="report the fold for one product's ledger; resolves nothing"
    )
    status.add_argument("--target", required=True, type=Path)
    status.add_argument("--entrypoint", required=True, type=Path)

    distribute = subparsers.add_parser(
        "distribute",
        help="report how opaque work units would spread across every healthy "
        "worker account right now; issues no work and records nothing",
    )
    distribute.add_argument("--target", required=True, type=Path)
    distribute.add_argument("--entrypoint", required=True, type=Path)
    distribute.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    distribute.add_argument(
        "--unit", dest="units", action="append", required=True,
        help="repeatable: one opaque work-unit identifier. Never comma-separated -- "
        "a separator would impose structure on an identifier this command, like "
        "packer.distribute() underneath it, treats as opaque; a unit containing "
        "its own comma would otherwise be split.",
    )
    distribute.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )

    remaining = subparsers.add_parser(
        "remaining",
        help="report which declared units have no complete result yet, the "
        "list the next campaign sends; asks no backend and records nothing",
    )
    remaining.add_argument("--target", required=True, type=Path)
    remaining.add_argument("--entrypoint", required=True, type=Path)
    remaining.add_argument(
        "--unit", dest="units", action="append", required=True,
        help="repeatable: one declared unit, exactly as `distribute`/`submit` "
        "take it; the answer keeps this order",
    )
    remaining.add_argument(
        "--unit-field", dest="unit_field", default=None,
        help="optional: the dotted field of the target's runs.jsonl records "
        "that names a unit (e.g. cell.unit); with it, the per-unit records "
        "in a kept partial result count those units complete",
    )

    poll = subparsers.add_parser(
        "poll", help="ask the adapter for one submission's status"
    )
    poll.add_argument("--submission-id", required=True)
    poll.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    poll.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )

    fetch = subparsers.add_parser(
        "fetch",
        help="materialize one submission's result, quarantining it when it is not current",
    )
    fetch.add_argument("--target", required=True, type=Path)
    fetch.add_argument("--entrypoint", required=True, type=Path)
    fetch.add_argument("--submission-id", required=True)
    fetch.add_argument(
        "--dest", required=False, default=None, type=Path,
        help="required for a real fetch; refused (not merely optional) "
        "under --smoke, which computes its own rehearsal destination",
    )
    fetch.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    fetch.add_argument(
        "--force",
        action="store_true",
        help="remove an already-materialized destination and re-fetch, "
        "instead of refusing; a leftover <dest>.partial/ from a fetch "
        "that was killed is never cleared by this flag (an incomplete "
        "result is kept under .remote-execution/partial/ instead and "
        "leaves no .partial/ behind)",
    )
    fetch.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )
    fetch.add_argument(
        "--smoke", action="store_true",
        help="when the submission id is recorded in both ledgers with "
        "agreeing entrypoint/worker, resolve to smoke.jsonl instead of the "
        "default main ledger.jsonl; does not suppress the refusal when the "
        "two records disagree",
    )

    reconcile = subparsers.add_parser(
        "reconcile",
        help="compare the ledger against the adapter's list_active() in both directions",
    )
    reconcile.add_argument("--target", required=True, type=Path)
    reconcile.add_argument("--entrypoint", required=True, type=Path)
    # Stays required, deliberately not widened to `submit`'s optional
    # selection: `reconcile` compares ONE already-known account's own
    # local ledger against that SAME account's remote state — it names no
    # new submission decision at all, so there is no "which account"
    # fork here for automatic selection to remove in the first place.
    reconcile.add_argument("--worker", required=True)
    reconcile.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    reconcile.add_argument(
        "--resolve",
        action="store_true",
        help="human-invoked only: append errored(reason=not-found-at-service) for each orphanLocal id",
    )
    reconcile.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )
    reconcile.add_argument(
        "--smoke", action="store_true",
        help="within --resolve: when an orphan's submission id is recorded "
        "in both ledgers with agreeing entrypoint/worker, resolve it to "
        "smoke.jsonl instead of the default main ledger.jsonl; does not "
        "suppress the refusal when the two records disagree",
    )

    generate_job = subparsers.add_parser(
        "generate-job",
        help="generate a forge-owned job folder at <target>/tools/<service>/<job-name>/",
    )
    generate_job.add_argument("--target", required=True, type=Path)
    generate_job.add_argument("--service", required=True)
    generate_job.add_argument("--job-name", required=True)
    generate_job.add_argument("--product", required=True)
    generate_job.add_argument(
        "--commit", default=None,
        help=(
            "the pinned commit, lowercase 40- or 64-hex. Optional: omitted, "
            "it defaults to the target's HEAD, which is a safe default only "
            "because generation refuses a dirty tree and a pin that is not "
            "HEAD. Never resolved from the remote"
        ),
    )
    generate_job.add_argument(
        "--repo-url", required=True,
        help="the remote the runner clones: https:// (or a local path for a "
        "local rehearsal); an SSH remote (git@host:o/r.git, ssh://, "
        "git+ssh://, ssh+git://) is refused, since the runner has no SSH "
        "agent or key, and a URL embedding a credential "
        "(a user, password or token before '@', other than a bare SSH "
        "login) is refused before any git call or write: pass the token "
        "with --repo-credential instead",
    )
    generate_job.add_argument("--repo-ref", required=True)
    generate_job.add_argument(
        "--repo-credential", dest="repo_credential", type=Path, default=None,
        help="path to a token file for the job's private repository: with "
        "it, generation's reachability probe authenticates through the "
        "same askpass material a credentialed runner clone will use, and "
        "only https:// remotes are admissible. Only services declaring "
        "REPO_CREDENTIAL_CARRIER accept it. Omitted, every probe stays "
        "anonymous, exactly as before.",
    )
    generate_job.add_argument(
        "--clone-path", dest="clone_paths", action="append", default=[],
        help="repeatable: one declared clone path, relative to the clone's own "
        "root. The run/smoke notebook is cloned on its own and needs no "
        "--clone-path; declaring its whole folder makes every notebook in "
        "it part of the pin, so an unrelated notebook change stales the job",
    )
    # `--run-module`/`--run-function` lost `required=True` when the notebook
    # shape landed, and the refusal for declaring neither moved INTO
    # `jobfolder.run_block_kind()` rather than being deleted. That is
    # deliberate: argparse's own "required" error fires before any shape is
    # known and could not have said "or a notebook", while the refusal that
    # replaced it is the same one that judges a hand-edited run-config at
    # submit. Nothing became optional; the check moved to where both shapes
    # are visible.
    generate_job.add_argument("--run-module", default=None)
    generate_job.add_argument("--run-function", default=None)
    generate_job.add_argument(
        "--run-kwargs", default="{}", help="a JSON object, passed to run.function as kwargs"
    )
    generate_job.add_argument(
        "--run-notebook", dest="run_notebook", default=None,
        help="the clone-relative path of the notebook this job runs (an "
        "alternative to --run-module/--run-function, never a companion to "
        "them): the worker executes this notebook and returns it executed. "
        "Must exist at the pin. Unless a --clone-path already covers it, "
        "the notebook file itself is added as a clone path, so only this "
        "notebook (not its folder) is part of the pin",
    )
    generate_job.add_argument("--smoke-module", default=None)
    generate_job.add_argument("--smoke-function", default=None)
    generate_job.add_argument("--smoke-kwargs", default=None, help="a JSON object")
    generate_job.add_argument(
        "--smoke-notebook", dest="smoke_notebook", default=None,
        help="the clone-relative path of the notebook a rehearsal runs (an "
        "alternative to --smoke-module/--smoke-function, never a companion "
        "to them)",
    )
    generate_job.add_argument(
        "--smoke-required-evidence", dest="smoke_required_evidence",
        action="append", default=[],
        help="repeatable: a field path shard_io.completeness() requires of a smoke "
        "run's shard.json; refused without --smoke-module/--smoke-function set",
    )
    generate_job.add_argument(
        "--regenerate", action="store_true",
        help="replace an existing job folder atomically instead of refusing",
    )
    generate_job.add_argument(
        "--accept-unresolved", action="store_true",
        help=(
            "record uncertain imports found by resolve_clone_paths() in "
            "run-config.json's unresolvedImports instead of refusing; never "
            "bypasses a computedNotDeclared refusal"
        ),
    )
    generate_job.add_argument(
        "--accept-unresolved-reads", action="store_true",
        help=(
            "record uncertain reads found by resolve_clone_paths() in "
            "run-config.json's unresolvedReads instead of refusing; a "
            "SEPARATE flag from --accept-unresolved and --accept-produced-reads "
            "— neither waives the other's refusal, and this never bypasses a "
            "computedReadsNotDeclared or producedReadsNotDeclared refusal"
        ),
    )
    generate_job.add_argument(
        "--accept-produced-reads", action="store_true",
        help=(
            "record an undeclared read as an accepted produced-file "
            "candidate in run-config.json's acceptedProducedReads instead "
            "of refusing, for a read whose resolved path the SAME walked "
            "file set also writes (the job may exist to produce that file "
            "on its first run); a SEPARATE flag from --accept-unresolved "
            "and --accept-unresolved-reads — neither waives the other's "
            "refusal, and this never bypasses a genuine "
            "computedReadsNotDeclared refusal (a read of a path nothing in "
            "the walk writes)"
        ),
    )
    generate_job.add_argument(
        "--accelerator-kind", dest="accelerator_kind", default=None,
        help="override: the expected accelerator kind (e.g. 'cuda'). Omitted "
        "together with --accelerator-architecture, the service adapter's own "
        "registered default is used instead (never a forge-invented value); "
        "given without --accelerator-architecture, refused -- except 'cpu', a "
        "CPU-only job with no architecture, on a service that declares a "
        "CPU-only session (refused, naming the service, elsewhere).",
    )
    generate_job.add_argument(
        "--accelerator-architecture", dest="accelerator_architectures",
        action="append", default=None,
        help="repeatable override: an expected accelerator architecture "
        "(e.g. 'sm_60'). Given without --accelerator-kind, refused.",
    )
    generate_job.add_argument(
        "--environment-requirement", dest="environment_requirements",
        action="append", default=None,
        help="repeatable: a pip requirement specifier for the target's own "
        "declared environment install — target knowledge, never a service "
        "or forge default.",
    )
    generate_job.add_argument(
        "--environment-index-url", dest="environment_index_url", default=None,
        help="optional index URL for --environment-requirement; given "
        "without at least one --environment-requirement, refused.",
    )
    generate_job.add_argument(
        "--local-budget-seconds", dest="local_budget_seconds", type=int, default=None,
        help="the target's own declared threshold, in seconds, for whether "
        "this job's pilot-projected cost is locally tolerable — recorded "
        "verbatim as localBudget.seconds, never judged here. Omitted, no "
        "localBudget block is written; that silence is never read as a "
        "budget of zero.",
    )
    generate_job.add_argument(
        "--carry-path", dest="carry_paths", action="append", default=None,
        help="repeatable: a path, relative to the product folder, whose "
        "contents a continuation of this job needs from the session before "
        "it (checkpoints, per-unit records, studies), recorded as "
        "carryPaths. When submit sends units an earlier submission left "
        "remaining, the earlier output is attached and these paths are "
        "restored before the entrypoint runs. Omitted, nothing is carried.",
    )
    generate_job.add_argument(
        "--input-dataset", dest="input_datasets", action="append", default=None,
        metavar="OWNER/SLUG",
        help="repeatable: a public dataset this job reads, as <owner>/<slug>, "
        "recorded as inputDatasets. A service that attaches inputs mounts it "
        "read-only in the push (submit reports inputs: attached); one that "
        "does not reports inputs: unsupported. Either way the runner exports "
        "FORGE_INPUT_DATASETS before the entrypoint: a JSON object mapping "
        "each ref to its mounted directory, or to null when it was not "
        "attached, so the target downloads it instead. Omitted, nothing is "
        "attached.",
    )
    generate_job.add_argument(
        "--code-bundle", dest="code_bundle", action="store_true", default=False,
        help="ship the declared clone paths (and the run/smoke notebook) "
        "inside the job instead of having the runner clone them: for a "
        "private repository on a service with no way to give the runner a "
        "repository credential. The paths are taken from the pinned commit "
        "with git archive (never the working tree), gzipped into "
        "code-bundle.tar.gz beside run-config.json, and recorded as "
        "codeBundle {file, format, sha256, bytes}; the runner verifies the "
        "sha256 and unpacks instead of cloning. The remote is never asked "
        "(no reachability probe, no credential), every local pin condition "
        "still applies. Only services whose adapter declares "
        "CODE_BUNDLE_MAX_BYTES accept it (CODE_BUNDLE_NOT_CARRIED "
        "otherwise), and a bundle over that limit refuses "
        "CODE_BUNDLE_TOO_LARGE. Omitted, the job clones as before.",
    )
    _add_dataset_arguments(generate_job)

    generate_jobs = subparsers.add_parser(
        "generate-jobs",
        help="generate every remote step's job folder in one call, from the product's "
        "declared __steps__ (and a `schedule` output), then name the one preflight to run",
    )
    generate_jobs.add_argument("--target", required=True, type=Path)
    generate_jobs.add_argument(
        "--product", required=True,
        help="the product whose src/<Package>/__init__.py (or config.py) declares __steps__; "
        "every step with placement 'remote' gets a job at tools/<service>/<job>/")
    generate_jobs.add_argument(
        "--from-schedule", dest="from_schedule", type=Path, default=None,
        help="a remote-parallelism `schedule` output: a step it names runs on the service(s) "
        "it chose (one job per service) instead of the step's declared service")
    generate_jobs.add_argument(
        "--repo-url", default=None,
        help="the remote the runner clones (default: the target's origin)")
    generate_jobs.add_argument(
        "--repo-ref", default=None, help="the branch (default: the target's current branch)")
    generate_jobs.add_argument(
        "--repo-credential", dest="repo_credential", type=Path, default=None,
        help="as for generate-job: a token file, used only for services declaring "
        "REPO_CREDENTIAL_CARRIER")
    generate_jobs.add_argument("--smoke-module", default=None)
    generate_jobs.add_argument("--smoke-function", default=None)
    generate_jobs.add_argument("--smoke-kwargs", default=None, help="a JSON object")
    generate_jobs.add_argument(
        "--smoke-required-evidence", dest="smoke_required_evidence", action="append",
        default=[], help="repeatable, as for generate-job; applied to every job")
    generate_jobs.add_argument(
        "--regenerate", action="store_true",
        help="replace existing job folders atomically instead of refusing")
    for flag in ("--accept-unresolved", "--accept-unresolved-reads", "--accept-produced-reads"):
        generate_jobs.add_argument(
            flag, action="store_true",
            help=f"as for generate-job's {flag}; applied to every job")
    _add_dataset_arguments(generate_jobs)

    smoke = subparsers.add_parser(
        "smoke", help="smoke-run bookkeeping: recording a rehearsal's evidence-derived verdict"
    )
    smoke_subparsers = smoke.add_subparsers(dest="smoke_command", required=True)
    smoke_record = smoke_subparsers.add_parser(
        "record",
        help="record a smoke run's verdict from its returned shard.json, "
        "derived from shard_io.completeness() — never a human assertion",
    )
    smoke_record.add_argument("--job-dir", required=True, type=Path)
    smoke_record.add_argument(
        "--from-artifact", required=True, type=Path, dest="from_artifact"
    )
    # Stays required: a smoke record files evidence for a rehearsal that
    # already RAN under one specific, already-known account — it reports
    # on a submission decision already made elsewhere, never makes one of
    # its own for automatic selection to take over.
    smoke_record.add_argument("--worker", required=True)

    readiness = subparsers.add_parser(
        "readiness",
        help="state whether a job is ready for a full submission on a worker; "
        "reports only, issues no submission",
    )
    readiness.add_argument("--job-dir", required=True, type=Path)
    # Stays required: readiness reports whether a job is fit to submit ON
    # a named account (its capacity, its own pending state) — it answers
    # "is THIS account ready", not "which account should this go to", so
    # there is nothing here for automatic selection to stand in for.
    readiness.add_argument("--worker", required=True)

    preflight = subparsers.add_parser(
        "preflight",
        help="check a generated job locally before its first remote rehearsal: one "
        "pass/warn/fail row per check with its evidence and fix; never submits",
    )
    preflight.add_argument("--target", required=True, type=Path)
    preflight.add_argument(
        "--entrypoint", dest="entrypoints", required=True, type=Path, action="append",
        help="the job folder's runner.ipynb (<target>/tools/<service>/<job-name>/runner.ipynb). "
        "Repeatable: with more than one, the report is {jobs: [one report per job], summary}",
    )
    preflight.add_argument(
        "--worker", dest="workers", action="append", default=None,
        help="repeatable: the account(s) to check. Omitted, every worker the service lists "
        "is checked, since each account needs its own rehearsal",
    )
    preflight.add_argument(
        "--workspace", type=Path, default=None,
        help="override: the workspace whose env interpreter, datasets/registry.json, team "
        "registry and account store are read (default: the workspace this skill is "
        "installed in)",
    )
    preflight.add_argument(
        "--interpreter", type=Path, default=None,
        help="override: the interpreter the local rehearsal runs the smoke under (default: "
        "the target's own .venv interpreter)",
    )
    preflight.add_argument(
        "--expect-accelerator", dest="expect_accelerator", default=None,
        help="the accelerator the plan expects (a machine name or an sm_* architecture); "
        "a job that will request another one fails",
    )
    preflight.add_argument(
        "--timing", type=Path, default=None,
        help="the timing record the session-fit check reads (default: "
        "<target>/<product>/Results/timing.json)",
    )
    preflight.add_argument(
        "--candidate", default=None,
        help="on a schema 2 timing record, the candidate (<host>:<owner>/<machine>) whose rows "
        "session-fit reads (default: the slowest of this service's candidates on the job's own "
        "kind of machine)",
    )
    preflight.add_argument("--stage", default="full", choices=("poc", "full"),
                           help="which scale of the timing record the job runs (default full)")
    preflight.add_argument(
        "--units", type=int, default=1,
        help="how many units the stage's work is split into across sessions (default 1)",
    )
    preflight.add_argument(
        "--unit", dest="unit_ids", action="append", default=None,
        help="one unit id the job's `submit --unit` will send (repeatable): the deadline "
        "rehearsal hands them to the target and checks partial.json against them",
    )
    preflight.add_argument(
        "--deadline-block", dest="deadline_block", default="smoke", choices=("smoke", "run"),
        help="which block the deadline rehearsal runs (default smoke: the one the local "
        "rehearsal already showed runs here)",
    )
    preflight.add_argument(
        "--local-smoke-kwargs", dest="local_smoke_kwargs", default=None,
        help="a JSON object replacing the smoke callable's kwargs for the local rehearsal "
        "only: a cheaper local scale the target declares",
    )
    preflight.add_argument(
        "--local-timeout", dest="local_timeout", type=float, default=600.0,
        help="the local rehearsal's time budget in seconds (default 600)",
    )
    preflight.add_argument(
        "--skip-rehearsal", dest="skip_rehearsal", action="store_true",
        help="skip the local rehearsal (its row reads warn)",
    )
    preflight.add_argument(
        "--keep-rehearsal", dest="keep_rehearsal", type=Path, default=None,
        help="leave the local rehearsal's scratch directory at this new path, to read it",
    )
    preflight.add_argument(
        "--repo-credential", dest="repo_credential", type=Path, default=None,
        help="path to the token file `submit --repo-credential` will carry, so the "
        "reachability probe authenticates the same way (carrier services only); read only "
        "through the generator's single read site, as generate-job reads it",
    )

    return parser


#: WHY THIS SKILL WAS INVOKED, AND WHERE IT HAS TO ARRIVE.
#:
#: Declared, invariant, and independent of any ledger, job folder or result on
#: disk. `status` answers *where am I* by folding what happened; this answers
#: *what is this for*, which nothing on disk implies. A session that hits an
#: error, an interruption or a gap consults it, locates itself, resolves what
#: blocks, and rejoins -- rather than improvising forward, which is what an
#: agent does when a blocker detaches it from the purpose.
#:
#: **Arrival is the result back and verified, never the submission accepted.**
#: The distinction is the whole point of this skill: a submission the service
#: took is a receipt, and a receipt is not a measurement. Between the two sit a
#: poll, a fetch, and a quarantine that refuses a result which is not current.
OBJECTIVE_FLOW = {
    "purpose": (
        "carry work a repository declared to a worker and bring its result "
        "back verified -- not accepted, not running, back and current"),
    "stages": [
        {"stage": "reachable",
         "establishes": "a job folder exists pinned to a commit the declared "
                        "remote can actually serve, which is what a worker "
                        "clones",
         "behindWhen": "`generate-job` wrote the folder -- it proves the pin "
                       "against the remote before writing a byte, so a folder "
                       "that exists is a pin that was published, or, with "
                       "`--code-bundle`, a pin whose code travels inside the "
                       "job and is never cloned"},
        {"stage": "wire",
         "establishes": "that this worker, at this pin, carries current -- the "
                        "cheapest possible answer, paid in minutes rather than "
                        "in the hours a campaign costs",
         "behindWhen": "`readiness` says ready, from a verdict derived from a "
                       "rehearsal's own evidence and never asserted"},
        {"stage": "authorized",
         "establishes": "a launch bound to this exact commit, entrypoint and "
                        "unit list, with a token minted for it and consumed "
                        "once",
         "behindWhen": "a `gate` record matches; a bound fact that moved makes "
                       "it stale, which is not the same as time passing"},
        {"stage": "sent",
         "establishes": "the submission is out and the ledger knows it, so no "
                        "second one answers a question already being answered",
         "behindWhen": "the ledger holds it with a terminal state"},
        {"stage": "returned",
         "establishes": "the result is on disk, current, and not quarantined",
         "behindWhen": "this is the arrival; it is behind nobody"},
    ],
    "arrival": (
        "the result on disk and verified as the current one, which is the "
        "only thing anybody can read a number out of"),
    # `reconcile` is not a stage and never advances one. It is the way back
    # when the ledger and the service stop agreeing, and a blocked session
    # needs to be told that explicitly: without it, `drift` reads as having
    # lost the work rather than as a detour that returns to `sent`.
    "repairs": [
        {"when": "the ledger and the service disagree, or a stale result "
                 "arrived (`drift`), or a ledger line could not be read at "
                 "all (`unreliable`)",
         "act": "reconcile",
         "returnsTo": "sent"},
    ],
    # Stops that are a person's decision, not defects to repair. An agent that
    # reads either as a blocker will stall on it or take it, and the second
    # spends somebody's quota without being asked.
    "humanStops": [
        "publishing the commit a worker would clone, which `generate-job` "
        "refuses without and names precisely",
        "authorizing the launch itself",
    ],
}


def _refused(exc: object) -> int:
    """The one place a refusal from this CLI reaches a reader.

    It did not exist: fourteen call sites each printed `error: {exc}` and
    returned 1, so there was nowhere to attach anything that every refusal
    should carry, and nothing could hold them to agreeing. Creating the single
    place is what makes the north reachable from a blocked session -- which is
    exactly the session that has lost it.

    Both halves go to stderr and the exit status is unchanged, so every caller
    that reads this CLI's stdout as data reads exactly what it read before.
    """
    print(f"error: {exc}", file=sys.stderr)
    print(json.dumps({"objective": OBJECTIVE_FLOW}, indent=2), file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "submit":
        try:
            _load_backend_module(args.backend)
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            return _refused(exc)

        # S3/D6: the carrier gate runs HERE — immediately after the class is
        # resolved, before `CREDENTIALS.provider()`, before
        # `_construct_adapter()`, before `cmd_submit()` and therefore before
        # any reachability probe could authenticate. A backend that does not
        # declare the carrier attribute has no runner-side credential path,
        # so the flag is refused rather than quietly authenticating a probe
        # whose runner still cannot clone.
        if args.repo_credential is not None and not _repo_credential_carrier(
            adapter_cls
        ):
            return _refused(_uncarried_repo_credential(args.backend))

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_submit(
                target=args.target,
                entrypoint=args.entrypoint,
                worker=args.worker,
                requested=args.requested,
                adapter=_construct_adapter(
                    adapter_cls, provider, args.repo_credential
                ),
                product=args.product,
                smoke=args.smoke,
                units=args.units,
                consent=args.consent,
                repo_credential_path=args.repo_credential,
                no_carry=args.no_carry,
            )
        except (RemoteCLIError, PACKER.PackerError, LEDGER.LedgerError,
                ADAPTER.AdapterError, JOBFOLDER.JobFolderError) as exc:
            return _refused(exc)

        if args.units:
            # Campaign mode's own JSON shape -- `assignments[]`/
            # `unplaced[]`/`skipped[]`, mirroring `distribute`'s own CLI
            # rendering, never the single-submission shape below.
            # `default=str` rather than naming each `Path` key by hand:
            # naming keys one at a time is what left a nested one
            # unreachable; naming none makes the next one harmless.
            print(json.dumps(result, sort_keys=True, default=str))
            if not result["assignments"] and result["unplaced"]:
                return 1
            return 0

        # Same six keys as ever -- this shape is reshaped, not spread, so
        # the reshaping stays. Only the hand-naming goes: `default=str`
        # rather than one named `Path` key, because naming keys one at a
        # time is what left a nested one unreachable; naming none makes the
        # next one harmless.
        rendered = {
            "submissionId": result["submission"].id,
            "worker": result["submission"].worker,
            "granted": result["plan"].granted,
            "ledgerPath": result["ledgerPath"],
            "staleness": result["staleness"],
            "smoke": result["smoke"],
        }
        # A seventh key only for a job declaring input datasets.
        if "inputs" in result:
            rendered["inputs"] = result["inputs"]
        # And two more only for a job declaring carry paths sent without a share.
        for key in ("carry", "carryWarning"):
            if key in result:
                rendered[key] = result[key]
        print(json.dumps(rendered, sort_keys=True, default=str))
        return 0

    if args.command == "status":
        try:
            result = cmd_status(target=args.target, entrypoint=args.entrypoint)
        except (RemoteCLIError, LEDGER.LedgerError, ADAPTER.AdapterError) as exc:
            return _refused(exc)

        # The north, above the fold that answers "where am I". `status` reports
        # what happened; nothing on disk says what any of it was FOR, and a
        # session reading a ledger without that has the facts and not the
        # purpose. Composed here rather than inside `cmd_status`, which many
        # callers use as data: this is the reporting surface, not the fold.
        result = {"objective": OBJECTIVE_FLOW, **result}

        # `default=str` rather than naming each `Path` key by hand: the
        # hand-named form stringified the top-level `ledgerPath` and left
        # `smoke.ledgerPath` a `Path`, so this command could never print at
        # all. Naming keys one at a time is what made a nested one
        # unreachable; naming none makes the next one harmless.
        print(json.dumps(result, sort_keys=True, default=str))
        return 0

    if args.command == "remaining":
        try:
            result = cmd_remaining(
                target=args.target,
                entrypoint=args.entrypoint,
                units=args.units,
                unit_field=args.unit_field,
            )
        except (RemoteCLIError, LEDGER.LedgerError) as exc:
            return _refused(exc)
        print(json.dumps(result, sort_keys=True, default=str))
        return 0

    if args.command == "distribute":
        try:
            _load_backend_module(args.backend)
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            return _refused(exc)

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_distribute(
                target=args.target,
                entrypoint=args.entrypoint,
                adapter=_construct_adapter(adapter_cls, provider),
                units=args.units,
            )
        except (RemoteCLIError, PACKER.PackerError, LEDGER.LedgerError,
                ADAPTER.AdapterError) as exc:
            return _refused(exc)

        # `default=str` for the same reason `submit`/`status`/`fetch`/
        # `smoke record` already carry it: this prints `result` whole, and
        # a future `cmd_distribute` field can nest a `Path` (a `staleness`
        # sub-dict, say) exactly the way `status` acquired one.
        print(json.dumps(result, sort_keys=True, default=str))
        if result["places"] == 0 and result["units"] > 0:
            return 1
        return 0

    if args.command == "poll":
        try:
            _load_backend_module(args.backend)
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            return _refused(exc)

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            status_result = cmd_poll(
                submission_id=args.submission_id, adapter=_construct_adapter(adapter_cls, provider)
            )
        except (RemoteCLIError, ADAPTER.AdapterError) as exc:
            return _refused(exc)

        # `default=str`: `Status.__post_init__` validates `state` against
        # the seam's own vocabulary but never constrains `detail`'s type --
        # a backend reporting a structured `detail` rather than the plain
        # string every adapter happens to send today would hit the same
        # `TypeError` `status` once did.
        print(
            json.dumps(
                {"state": status_result.state, "detail": status_result.detail},
                sort_keys=True,
                default=str,
            )
        )
        return 0

    if args.command == "fetch":
        try:
            _load_backend_module(args.backend)
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            return _refused(exc)

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_fetch(
                target=args.target,
                entrypoint=args.entrypoint,
                submission_id=args.submission_id,
                dest=args.dest,
                adapter=_construct_adapter(adapter_cls, provider),
                force=args.force,
                smoke=args.smoke,
            )
        except (RemoteCLIError, LEDGER.LedgerError, ADAPTER.AdapterError) as exc:
            return _refused(exc)

        arbitration = result["arbitration"]
        if arbitration is not None:
            print(arbitration, file=sys.stderr)

        # Same five keys as ever; only the hand-naming goes. `default=str`
        # rather than one named `Path` key, because naming keys one at a
        # time is what left a nested one unreachable; naming none makes the
        # next one harmless.
        print(
            json.dumps(
                {
                    "verdict": result["verdict"],
                    "complete": result["complete"],
                    "path": result["path"],
                    "event": result["event"],
                    "staleness": result["staleness"],
                    **(
                        {"runState": result["runState"]}
                        if "runState" in result
                        else {}
                    ),
                },
                sort_keys=True,
                default=str,
            )
        )
        return 0

    if args.command == "reconcile":
        try:
            _load_backend_module(args.backend)
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            return _refused(exc)

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_reconcile(
                target=args.target,
                entrypoint=args.entrypoint,
                worker=args.worker,
                adapter=_construct_adapter(adapter_cls, provider),
                resolve=args.resolve,
                smoke=args.smoke,
            )
        except (RemoteCLIError, LEDGER.LedgerError, ADAPTER.AdapterError) as exc:
            return _refused(exc)

        arbitration = result.pop("arbitration")
        for note in arbitration:
            print(note, file=sys.stderr)

        # `default=str`, same reason as `distribute`: this prints `result`
        # whole and it already carries `staleness`, the exact nested shape
        # `status` broke on.
        print(json.dumps(result, sort_keys=True, default=str))
        return 0

    if args.command == "generate-job":
        # `--service` is `--backend` under a second name: both select a module
        # in `adapters/`, and generation resolves a metadata assembler out of
        # the same registry the other four commands resolve an adapter from.
        # The side-loader was wired to `args.backend` at all four of its call
        # sites, so this one command — the first anybody runs to reach a
        # service at all — asked an empty registry and refused a correct
        # invocation.
        _load_backend_module(args.service)
        # S3/D6: the same carrier gate as `submit`'s, and it must run before
        # `generate_job()` — generation runs the same reachability probe, so
        # a credential here would authenticate it while the runner that probe
        # stands in for still could not clone. Resolved only when the flag is
        # actually given, so the credentialless path keeps its existing
        # registry semantics exactly (a service known only to the metadata
        # registry still generates, as before).
        if args.repo_credential is not None and args.code_bundle:
            return _refused(JOBFOLDER.JobFolderError(
                f"{JOBFOLDER.CODE_BUNDLE_WITH_REPO_CREDENTIAL}: --code-bundle and "
                "--repo-credential were both given. A bundled job's runner never "
                "clones, so a repository credential has nothing to authenticate; "
                "drop --repo-credential (or drop --code-bundle to clone with it)."
            ))
        if args.repo_credential is not None:
            try:
                adapter_cls = ADAPTER.resolve(args.service)
            except KeyError as exc:
                return _refused(exc)
            if not _repo_credential_carrier(adapter_cls):
                return _refused(_uncarried_repo_credential(args.service))
        if args.workspace is not None and not args.datasets:
            return _refused(RemoteCLIError(
                "WORKSPACE_WITHOUT_DATASET: --workspace only chooses whose "
                "datasets/registry.json --dataset reads; give --dataset <slug>, or drop "
                "--workspace"))
        try:
            try:
                dataset_cls = ADAPTER.resolve(args.service) if args.datasets else None
            except KeyError:
                dataset_cls = None
            input_datasets, dataset_checks = _dataset_plan(
                dataset_cls, args.workspace, args.datasets, args.input_datasets)
        except JOB_PLAN.JobPlanError as exc:
            return _refused(exc)
        try:
            destination = JOBFOLDER.generate_job(
                target=args.target,
                service=args.service,
                job_name=args.job_name,
                product=args.product,
                commit=args.commit,
                repo_url=args.repo_url,
                repo_ref=args.repo_ref,
                repo_credential_path=args.repo_credential,
                clone_paths=args.clone_paths,
                run_module=args.run_module,
                run_function=args.run_function,
                run_kwargs=json.loads(args.run_kwargs),
                run_notebook=args.run_notebook,
                smoke_module=args.smoke_module,
                smoke_function=args.smoke_function,
                smoke_kwargs=json.loads(args.smoke_kwargs) if args.smoke_kwargs else None,
                smoke_notebook=args.smoke_notebook,
                smoke_required_evidence=args.smoke_required_evidence or None,
                regenerate=args.regenerate,
                accept_unresolved=args.accept_unresolved,
                accept_unresolved_reads=args.accept_unresolved_reads,
                accept_produced_reads=args.accept_produced_reads,
                accelerator_kind=args.accelerator_kind,
                accelerator_architectures=args.accelerator_architectures,
                environment_requirements=args.environment_requirements,
                environment_index_url=args.environment_index_url,
                local_budget_seconds=args.local_budget_seconds,
                carry_paths=args.carry_paths,
                code_bundle=args.code_bundle,
                input_datasets=input_datasets,
                dataset_checks=dataset_checks,
            )
        except (JOBFOLDER.JobFolderError, ADAPTER.AdapterError, KeyError) as exc:
            return _refused(exc)

        # Routes through the SAME single reader every other job-folder-
        # touching command uses (design #744 §4) — a job folder is never
        # even momentarily reported without its staleness alongside it.
        job_folder = JOBFOLDER.read(destination)
        staleness = dict(job_folder.staleness)
        # `commitSource` is operator feedback and lives on stdout ONLY. It
        # describes how the caller typed an argument, not a fact about the
        # job, and `run-config.json` records facts about the job. The pin
        # itself is read back out of the written config rather than out of
        # `args`, so what is reported is what was actually recorded.
        print(
            json.dumps(
                {
                    "jobFolder": str(destination),
                    "staleness": staleness,
                    "commit": job_folder.run_config["commit"],
                    # Three sources, not two, and the third is why this is
                    # derived rather than inferred from the flag alone: an
                    # omitted `--commit` may resolve to HEAD or to the declared
                    # ref's published tip, and a reader who is told
                    # `default-head` when the pin is neither has been told the
                    # wrong thing about which code will run.
                    "commitSource": JOBFOLDER.pin_source(
                        args.target, args.commit, job_folder.run_config["commit"]),
                    **({"warnings": warnings}
                       if (warnings := JOBFOLDER.smoke_warnings(job_folder.run_config)) else {}),
                    **({"codeBundle": dict(job_folder.run_config["codeBundle"])}
                       if "codeBundle" in job_folder.run_config else {}),
                    **({"inputDatasets": list(job_folder.run_config["inputDatasets"]),
                        "datasetChecks": dict(job_folder.run_config["datasetChecks"])}
                       if args.datasets else {}),
                },
                sort_keys=True,
                # `default=str`: `staleness` is the exact sub-dict `status`
                # broke on once already, one layer up. `_staleness_for()`
                # returns str/list[str]/None today; that is a fact about
                # one helper's present shape, never a guarantee this print
                # site holds on its own.
                default=str,
            )
        )
        return 0

    if args.command == "smoke":
        if args.smoke_command == "record":
            try:
                result = cmd_smoke_record(
                    job_dir=args.job_dir,
                    artifact_path=args.from_artifact,
                    worker=args.worker,
                )
            except (RemoteCLIError, LEDGER.LedgerError, JOBFOLDER.JobFolderError) as exc:
                return _refused(exc)

            # Same four keys as ever; only the hand-naming goes.
            # `default=str` rather than one named `Path` key, because
            # naming keys one at a time is what left a nested one
            # unreachable; naming none makes the next one harmless.
            print(
                json.dumps(
                    {
                        "result": result["result"],
                        "missing": result["missing"],
                        "requiredEvidence": result["requiredEvidence"],
                        "smokeLedgerPath": result["smokeLedgerPath"],
                    },
                    sort_keys=True,
                    default=str,
                )
            )
            return 0
        return 1

    if args.command == "generate-jobs":
        try:
            smoke_kwargs = json.loads(args.smoke_kwargs) if args.smoke_kwargs else None
            result = cmd_generate_jobs(
                target=args.target, product=args.product, from_schedule=args.from_schedule,
                repo_url=args.repo_url, repo_ref=args.repo_ref,
                repo_credential=args.repo_credential, smoke_module=args.smoke_module,
                smoke_function=args.smoke_function, smoke_kwargs=smoke_kwargs,
                smoke_required_evidence=args.smoke_required_evidence or None,
                regenerate=args.regenerate, datasets=args.datasets, workspace=args.workspace,
                accept_unresolved=args.accept_unresolved,
                accept_unresolved_reads=args.accept_unresolved_reads,
                accept_produced_reads=args.accept_produced_reads)
        except json.JSONDecodeError as exc:
            return _refused(f"--smoke-kwargs is not JSON: {exc}")
        except (RemoteCLIError, JOB_PLAN.JobPlanError, JOBFOLDER.JobFolderError) as exc:
            return _refused(exc)
        print(json.dumps(result, sort_keys=True, default=str))
        return 0 if result["summary"]["refused"] == 0 else 1

    if args.command == "preflight":
        try:
            smoke_kwargs = (json.loads(args.local_smoke_kwargs)
                            if args.local_smoke_kwargs is not None else None)
            if smoke_kwargs is not None and not isinstance(smoke_kwargs, dict):
                raise RemoteCLIError("--local-smoke-kwargs must be a JSON object")
            reports = [cmd_preflight(
                target=args.target, entrypoint=entrypoint, workers=args.workers,
                workspace=args.workspace, interpreter=args.interpreter,
                expect_accelerator=args.expect_accelerator, timing=args.timing,
                candidate=args.candidate, stage=args.stage, units=args.units, local_smoke_kwargs=smoke_kwargs,
                local_timeout=args.local_timeout, skip_rehearsal=args.skip_rehearsal,
                keep_rehearsal=(args.keep_rehearsal if len(args.entrypoints) == 1
                                or args.keep_rehearsal is None
                                else args.keep_rehearsal / f"job-{index}"),
                repo_credential=args.repo_credential, unit_ids=args.unit_ids,
                deadline_block=args.deadline_block)
                for index, entrypoint in enumerate(args.entrypoints)]
        except json.JSONDecodeError as exc:
            return _refused(f"--local-smoke-kwargs is not JSON: {exc}")
        except (RemoteCLIError, JOBFOLDER.JobFolderError) as exc:
            return _refused(exc)
        if len(reports) == 1:
            result = reports[0]
        else:
            # One report per job, and one verdict over all of them: the
            # `generate-jobs` follow-up is a single command (S3).
            counts = {status: sum(r["summary"][status] for r in reports)
                      for status in ("pass", "warn", "fail")}
            result = {"jobs": reports,
                      "summary": {**counts, "ok": all(r["summary"]["ok"] for r in reports)}}
        # The report is data on stdout either way; the exit status is the
        # verdict: 0 only when no row fails.
        print(json.dumps(result, sort_keys=True, default=str))
        return 0 if result["summary"]["ok"] else 1

    if args.command == "readiness":
        try:
            result = cmd_readiness(job_dir=args.job_dir, worker=args.worker)
        except (RemoteCLIError, JOBFOLDER.JobFolderError) as exc:
            return _refused(exc)

        # `default=str`, same reason as `distribute`/`reconcile`: `result`
        # already carries `staleness`, the exact nested shape `status`
        # broke on once already, one layer up.
        print(json.dumps(result, sort_keys=True, default=str))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
