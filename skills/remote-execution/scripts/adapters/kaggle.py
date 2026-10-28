#!/usr/bin/env python3
"""The Kaggle backend adapter — the ONLY file in this entire skill allowed
to name a service.

Every module above `adapter.py` (`ledger.py`, `packer.py`, `remote_cli.py`)
stays deliberately blind to what backend, if any, is behind a given worker.
This module is where that blindness ends: it is the one place permitted to
say "Kaggle", to spawn the one child that speaks to it, and to know that
service's own vocabulary well enough to translate it into the seam's.

Two structural guarantees hold everywhere below, not by convention but by
what this file's own dependency graph can even reach:

1. This module imports `subprocess`, `json`, `csv`, `io`, `re`, `sys`, `os`,
   `dataclasses`, `pathlib` and this skill's own `adapter.py` — nothing
   else. It has no constant, no argument and no configuration key naming
   the credential file `kaggle-accounts` keeps for itself, and it never
   constructs a path into that skill's own data directory. Worker identity
   comes from exactly one sanctioned command, run as a subprocess:
   `sys.executable <kaggle-accounts>/scripts/accounts_cli.py list --json`,
   which answers with usernames and nothing else (`cmd_list` under `--json`
   builds a fresh dict holding only `username` per account — no other key
   can reach a caller even by accident). This module never imports that
   script; it only runs it, exactly the way a human at a terminal would.

2. A credential VALUE is read at exactly one expression, here, and
   reaches exactly one child process's own environment. `CredentialHandle`
   below is the only credential type this adapter accepts; it carries a
   path, and `_env_for()` — the single sink in the whole file — reads the
   file that path names and puts its stripped content on
   `KAGGLE_API_TOKEN`.

   This is a TRADE, not a preserved invariant, and the old by-path claim
   is retracted rather than reworded: the installed client's
   `_try_fill_auth()` reads `KAGGLE_API_TOKEN` and hands it straight to
   `BearerAuth(api_token)`, by value, with no path check of any kind, so a
   path in that variable becomes the literal text of an
   `Authorization: Bearer` header and authenticates nothing. The legacy
   `KAGGLE_CONFIG_DIR`/`kaggle.json` shape is not an escape either — it
   routes an access token through a Basic-auth path it was never meant for
   and answers 401 for every account regardless of validity.

   What genuinely holds, and is locked by tests rather than stated here:
   `.token_path` is touched in no module above this one, so no credential
   value has any route into `credentials.py`, `remote_cli.py`, `ledger.py`,
   `packer.py` or `jobfolder.py`; the value is never logged, never
   interpolated into a refusal, and never returned upward; and a file that
   cannot be read, or that holds nothing once stripped, is refused instead
   of sent. See `SKILL.md`'s credential-transport table for the full list
   and the test that proves each row.

Every subprocess call here is `shell=False` with a list argv, an explicit
timeout, and an env built from an allowlist (`PATH` plus, when a credential
is involved, `KAGGLE_API_TOKEN` — nothing else is ever forwarded from this
process's own environment). A non-zero exit or an expired timeout is a
refusal: this module raises `KaggleAdapterError` rather than fabricate a
`Status`, a `Submission` or a `Fetched` result the service never actually
confirmed.

This module imports no packaged client and names none — a lock refuses even
the mention, so an edit that inlined one would fail rather than quietly
empty a recorder. The one file permitted that import is
`kaggle_driver.py`, which this module spawns as a child through
`sys.executable`, so the child runs whatever interpreter runs the skill.
Whether that interpreter can import the client is answered by the driver's
own `selftest`, not by a version stated here and enforced nowhere:
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, NamedTuple


def _load_adapter_seam():
    """Path-import `adapter.py`, one directory up from this file, reusing
    an already-loaded copy under `remote_execution_adapter` when one
    exists.

    Same `sys.modules`-reuse technique `remote_cli.py` and `packer.py` use
    for their own sibling loads, and the same correctness reason: a second,
    separately exec'd copy of `adapter.py` would define a second, distinct
    `Adapter` class with the same name, and `isinstance(kaggle_adapter,
    ADAPTER.Adapter)` checks made by a caller holding the first copy would
    silently fail against an instance built from the second.
    """
    module_name = "remote_execution_adapter"
    if module_name in sys.modules:
        return sys.modules[module_name]
    script = Path(__file__).resolve().parent.parent / "adapter.py"
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


ADAPTER = _load_adapter_seam()


class KaggleAdapterError(ADAPTER.AdapterError):
    """A refusal: the service CLI failed, timed out, or this adapter was
    asked to act for a worker it holds no `CredentialHandle` for.

    Never raised to report a guess — only to report that this adapter
    declined to fabricate an answer the service never actually confirmed.
    """


# `skills/kaggle-accounts/scripts/accounts_cli.py`, computed once
# relative to this file. This traversal names the sanctioned command's
# location only — never the credential file that command guards, which
# this module has no path to at all.
DEFAULT_ACCOUNTS_CLI = (
    Path(__file__).resolve().parents[3] / "kaggle-accounts" / "scripts" / "accounts_cli.py"
)


def _account_names_on_disk(
    accounts_cli: Path, run: Callable[[list[str]], subprocess.CompletedProcess]
) -> list[str]:
    """Every account username the sanctioned `list --json` command reports
    right now, run through `run` -- the one subprocess boundary the two
    callers below this share, never built twice.

    `run` is handed the finished argv (`sys.executable`, never a bare
    `python3` -- the two coincide only by accident of `PATH`, and a
    sibling skill launched under a different interpreter answers about a
    different installation, or fails to start at all) and returns
    a `CompletedProcess`; what happens between those two moments -- which
    environment the child inherits, what timeout bounds it -- is entirely
    the caller's own choice, made once by `workers()` below (an
    authenticated instance's own `_run`) and once by `_declared_capacity()`
    further down (a bare, credential-free call this adapter's own launch-
    proposal reporter makes).

    Raises `KaggleAdapterError` on a non-zero exit or output `json.loads`
    cannot parse -- exactly the two failures the single call site this was
    extracted from always raised on, in the identical wording. What a
    caller does with that raise is its own decision; see
    `_declared_capacity()`'s own docstring for the caller that turns it
    into a quiet absence instead of letting it propagate.
    """
    result = run([sys.executable, str(accounts_cli), "list", "--json"])
    if result.returncode != 0:
        raise KaggleAdapterError(
            f"{accounts_cli} list --json exited {result.returncode}: "
            f"{result.stderr.strip()}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise KaggleAdapterError(
            f"{accounts_cli} list --json did not print JSON: {exc}"
        ) from exc
    return [account["username"] for account in payload.get("accounts", [])]


# The TEAM registry: which person owns which Kaggle account. Git-ignored,
# no secrets, written by the operator's own tooling (`smith team`); this
# module only reads it, and only two fields per member — `owner` and
# `accounts.kaggle.username`. Never a token path, never anything a token
# file holds: the credential still travels only as a `CredentialHandle`.
# The default location is the workspace root this file ships inside
# (`<workspace>/skills/remote-execution/scripts/adapters/kaggle.py`), the
# same resolution the Colab adapter uses, read at call time so a caller
# (or a test) can point it elsewhere.
TEAM_REGISTRY_RELATIVE = Path(".papersmith") / "team.json"
DEFAULT_TEAM_REGISTRY = Path(__file__).resolve().parents[4] / TEAM_REGISTRY_RELATIVE
TEAM_REGISTRY_SCHEMA = 1
_OWNER_RE = re.compile(r"^[a-z0-9-]{1,40}$")

# The rule the exclusion cites. Kaggle staff, verified 2026-10-25: the one
# account per person rule is site-wide, so a second account under distinct
# email addresses is still the same person's second account — it is never
# a campaign worker, whatever address it was registered with.
KAGGLE_ONE_ACCOUNT_RULE_URL = "https://www.kaggle.com/discussions/general/192527"
KAGGLE_ONE_ACCOUNT_RULE = "the one account per person applies to all Kaggle site use"
TEAM_UNMAPPED_REASON = (
    "not mapped to a team owner: one account per person — Kaggle staff: "
    f"'{KAGGLE_ONE_ACCOUNT_RULE}' ({KAGGLE_ONE_ACCOUNT_RULE_URL})"
)


def load_kaggle_team(path: str | Path) -> dict[str, str] | None:
    """`{username: owner}` for every owner the registry at `path` maps to a
    Kaggle username, or `None` when there is no registry or it maps none —
    the plain-listing behaviour, unchanged.

    Fail-closed on every shape it cannot honestly read: not JSON, not a
    schema-1 object, no `members` list, an owner slug outside
    `[a-z0-9-]{1,40}` or repeated, a username that is not a non-empty
    string, or the SAME username under two owners (one account cannot
    belong to two people).
    """
    registry = Path(path)
    try:
        text = registry.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise KaggleAdapterError(f"cannot read the team registry {registry}: {exc}") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise KaggleAdapterError(
            f"the team registry {registry} is not JSON ({exc}); refusing to "
            "guess which accounts it maps"
        ) from exc
    if not isinstance(document, dict) or document.get("schema") != TEAM_REGISTRY_SCHEMA:
        raise KaggleAdapterError(
            f"the team registry {registry} is not a schema-{TEAM_REGISTRY_SCHEMA} "
            "object; refusing to guess which accounts it maps"
        )
    members = document.get("members")
    if not isinstance(members, list):
        raise KaggleAdapterError(f"the team registry {registry} carries no 'members' list")

    owner_by_username: dict[str, str] = {}
    owners_seen: set[str] = set()
    for index, member in enumerate(members):
        if not isinstance(member, dict):
            raise KaggleAdapterError(f"{registry}: member #{index} is not an object")
        owner = member.get("owner")
        if not isinstance(owner, str) or _OWNER_RE.match(owner) is None:
            raise KaggleAdapterError(
                f"{registry}: member #{index} owner {owner!r} is not a slug "
                "of 1-40 characters in [a-z0-9-]"
            )
        if owner in owners_seen:
            raise KaggleAdapterError(
                f"{registry}: owner {owner!r} appears more than once; an owner "
                "is one person and is listed once"
            )
        owners_seen.add(owner)
        services = member.get("accounts")
        entry = services.get("kaggle") if isinstance(services, dict) else None
        if entry is None:
            continue
        username = entry.get("username") if isinstance(entry, dict) else None
        if not isinstance(username, str) or not username.strip():
            raise KaggleAdapterError(
                f"{registry}: owner {owner!r} accounts.kaggle.username is not "
                "a non-empty string"
            )
        if username in owner_by_username:
            raise KaggleAdapterError(
                f"{registry}: Kaggle username {username!r} is mapped to both "
                f"{owner_by_username[username]!r} and {owner!r}; one account "
                "belongs to one person"
            )
        owner_by_username[username] = owner
    return owner_by_username or None


class KaggleTeamReport(NamedTuple):
    """What the team registry did to the listed accounts.

    `workers` — the listed usernames an owner maps, in listing order, one per
    owner. `excluded` — `(username, reason)` for every listed account no
    owner maps; it stays listed, it is never a worker. `not_validated` —
    `(owner, username, reason)` for every mapping whose username the listing
    does not hold; no worker exists for it until it is validated.
    """

    workers: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]
    not_validated: tuple[tuple[str, str, str], ...]


def _team_report(names: list[str], team: Mapping[str, str]) -> KaggleTeamReport:
    workers: list[str] = []
    excluded: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        if name in team:
            workers.append(name)
        else:
            excluded.append((name, TEAM_UNMAPPED_REASON))
    not_validated = tuple(
        (
            owner,
            username,
            f"owner {owner!r} maps Kaggle username {username!r}, which the "
            "kaggle-accounts listing does not hold: not validated, so it is no "
            "worker until that account is taken in and validated",
        )
        for username, owner in team.items()
        if username not in seen
    )
    return KaggleTeamReport(tuple(workers), tuple(excluded), not_validated)

# `adapters/kaggle_driver.py`, this module's own sibling — the one file in
# this skill permitted to import the Kaggle SDK package. `submit()`/
# `_push()` shell out to it exactly the way this module used to shell out
# to the `kaggle` command-line tool: same `_run()`/`_env_for()` boundary,
# same `shell=False`/list-argv/allowlisted-env discipline, only the
# child's own identity changed. Overridable at construction
# (`driver_script=`) so a test can substitute a fake stand-in never
# running under a real interpreter that has the SDK installed nor within
# reach of the real service.
DEFAULT_KAGGLE_DRIVER = Path(__file__).resolve().parent / "kaggle_driver.py"

KAGGLE_EXECUTABLE = "kaggle"

# Read by `scripts/hooks/refuse_offpath_push.py` (design §5,
# `the-position-nobody-holds`) -- the exact substrings a hand-rolled Bash
# command would have to contain to reach THIS service's own push surface
# without going through `remote_cli.py submit` at all: this adapter's own
# driver script by name, and the SDK method it shells out to
# (`kernels_push`, see `_push()` below). Declared here, never hardcoded in
# the hook itself, because naming a service's own vocabulary belongs to
# this file alone -- the one confinement rule this whole skill enforces
# (see this module's own docstring above, and
# `implementation_cli.py`'s "No service is named here" comment). A second
# service is covered by declaring its own `PUSH_SURFACE` beside its own
# adapter, never by editing the hook.
PUSH_SURFACE: tuple[str, ...] = ("kaggle_driver.py", "kernels_push")

# The CONTROL-PLANE budget: worker listing, `submit`'s own push, `poll`,
# and `capacity`. Every one of those is a small request whose answer the
# service produces immediately, so two minutes is already generous and
# failing fast is the correct behaviour — a control call that has not
# answered in that long is not slow, it is wrong, and this adapter would
# rather refuse than let a caller sit on an unanswered status.
SUBPROCESS_TIMEOUT_SECONDS = 120.0

# The FETCH budget, deliberately separate. `fetch()` is not a fast-fail
# path: it is a bulk transfer whose SIZE IS DECIDED BY THE REMOTE JOB, not
# by anything this process can see before the call, and the observed link
# throughput between this machine and the service varies by more than an
# order of magnitude — 2.1 MB/s in one measurement, 0.06 MB/s in another.
# Under the shared 120s budget above, that combination does not merely
# fail slowly; it MISDIAGNOSES. A 12.4 MiB probe once took 209s and 27s
# the same day, and the refusal read as the probe's fault rather than the
# link's; a 256 MB artifact from a completed 75-minute GPU run was killed
# at 120s and read as a broken fetch. 1800s is generous enough that a
# working transfer at the slow end of that range finishes, while still
# BOUNDED — a genuinely hung child process must still die rather than
# hold this process open forever.
KAGGLE_FETCH_TIMEOUT_SECONDS = 1800.0

# `kaggle_driver.py`'s own `EXIT_UNAUTHORIZED`, duplicated here rather than
# imported — this module never imports the driver, the same reason
# `RUN_CONFIG_FILENAME` above is this module's own constant rather than a
# shared one. The driver maps a 401/403 `requests.exceptions.HTTPError` to
# exactly this exit code; a `capacity` call that exits with it is this
# adapter's own signal to raise `ADAPTER.WorkerUnauthorized` rather than a
# generic refusal, so `packer.select()` can tell "this worker's credential
# is refused" apart from every other failure shape without importing this
# module's own exception type.
_DRIVER_EXIT_UNAUTHORIZED = 3

# This service's documented per-worker concurrent-kernel allowance, stated
# here and nowhere else in this skill — NOT a universal constant, and not
# something a second backend's adapter should read off this module. A
# backend metering capacity some other way (a quota, a byte budget) would
# convert it into "concurrent jobs" inside its own adapter, exactly the
# same way this one does.
#
# This is the batch-session figure: how many `kernels push` submissions
# this service has, at the time this was last checked, let one account run
# concurrently. It is an observed property of the service, measured
# against `kernels push`, not a law — it is documented and expected to be
# revised as Kaggle's own concurrent-kernel allowance changes, and it is
# never asserted as a universal per-account or per-service ceiling.
KAGGLE_WORKER_CAPACITY = 2

# The accelerator ARCHITECTURE this service is expected to hand a
# submitted kernel by default — beside `KAGGLE_WORKER_CAPACITY` above, and
# framed with the exact same honesty: an observed property of the
# service, measured against real rehearsals, not a law. Kaggle has been
# seen to hand out both a Tesla P100 (`sm_60`) and a Tesla T4 (`sm_75`)
# for the same free-tier GPU request, and WHICH one arrives on any given
# submission is the service's own draw, never this adapter's to pick —
# see `Status.detail` for what the service reports it actually granted.
# "cuda"/"sm_75" name a CUDA compute capability, the SAME
# vocabulary `runner_bootstrap.py`'s own accelerator gate already compares
# `torch.cuda.get_arch_list()` entries against — never a Kaggle-specific
# vocabulary, and never a device model name (Decision 1's own rule: an
# architecture answers "can this build run here", never "is this the
# card I named").
#
# This is a DEFAULT, not a requirement: a job's own declaration (this
# module's `register_default_accelerator` call below) is consulted only
# when a caller supplies neither `--accelerator-kind` nor
# `--accelerator-architecture` at `generate-job` time — an explicit
# declaration always overrides it. It is documented and expected to be
# revised as Kaggle's own hardware pool changes, and it is never asserted
# as a universal per-account or per-service guarantee.
#
# It names ONE architecture on purpose. The gate reads a declaration as
# "the installed build must cover every architecture named here", so a
# second, wider entry does not broaden what the job accepts -- it adds a
# second thing the build has to satisfy, and refuses the job when it does
# not. A measured 2026-08-24 rehearsal proved the cost of getting this
# wrong: a two-entry default naming an architecture the installed build
# never carries refused on EVERY runtime, including one the job was
# otherwise free to run on.
KAGGLE_ACCELERATOR_KIND = "cuda"
KAGGLE_ACCELERATOR_ARCHITECTURES = ("sm_75",)

# The named accelerator this adapter requests on every push, and the
# architecture-vocabulary mapping that keeps the request and the runner's
# own bootstrap gate from drifting apart. Observed, not a law, exactly like
# `KAGGLE_ACCELERATOR_ARCHITECTURES` above: Kaggle has been seen to hand out
# both a Tesla P100 (`sm_60`) and a Tesla T4 (`sm_75`) for the same
# free-tier GPU request, and a bare `enable_gpu=True` cannot steer which one
# arrives -- `machine_shape` is the field that can, and both are sent on
# every push (Decision 3): `enable_gpu` because it is still the field a
# reader unfamiliar with `machine_shape` expects, `machine_shape` because it
# is the one the service actually consults for accelerator selection.
#
# PROVEN LIVE, 2026-08-24: a smoke kernel pushed to one account this
# machine already holds a credential for, with
# `machine_shape: "NvidiaTeslaT4"`, through this skill's own SDK driver
# (`kaggle_driver.py` -- see `requirements.txt` for the pinned dependency
# version), reached terminal state `complete`; its own `bootstrap.json`
# reported
# `{"capability": "sm_75", "device": {"kind": "cuda", "name": "Tesla T4"}}`,
# matching `KAGGLE_ACCELERATOR_ARCHITECTURES[0]` below. Five earlier
# submissions using bare `enable_gpu` alone all reported `failed` at 35-38s
# on a drawn P100. Cost: 75s of GPU time, stated absolutely. This skill
# cannot see a worker's remaining time budget -- see `## What this skill
# cannot see` in SKILL.md -- so a cost here is never a fraction of one.
KAGGLE_MACHINE_SHAPES = {"NvidiaTeslaT4": "sm_75", "NvidiaTeslaP100": "sm_60"}
KAGGLE_MACHINE_SHAPE = "NvidiaTeslaT4"

# The continuous run time one Kaggle session may last, per accelerator:
# 12 hours for a GPU session. This is the service's PUBLISHED limit at the
# time of writing (2026-10), not a measurement and not a law -- re-check it
# against Kaggle's own documentation before planning around it, and revise
# this table when it changes. A session that reaches it is stopped by the
# service, and nothing it had not already written to its output survives.
# `KaggleAdapter.session_limit_seconds()` reads this table and nothing else;
# a shape not listed here answers `None` (unknown), never a guess.
KAGGLE_SESSION_LIMIT_SECONDS = {
    "NvidiaTeslaT4": 12 * 3600,
    "NvidiaTeslaP100": 12 * 3600,
}


def _default_accelerator() -> tuple[str, tuple[str, ...]]:
    """`ADAPTER.register_default_accelerator("kaggle", ...)`'s own
    provider — called by `jobfolder.generate_job()` only when a caller
    declared neither half of the accelerator pair itself, so a job
    generated from zero still comes out with a declared expectation
    instead of none at all.
    """
    return KAGGLE_ACCELERATOR_KIND, KAGGLE_ACCELERATOR_ARCHITECTURES


# The boolean accelerator request every push still carries alongside the
# NAMED one (`KAGGLE_MACHINE_SHAPE` above). This constant, on its own, is a request, not a receipt:
# asking for one is not the same as receiving one. What a submission
# actually ran on is a fact the service states, at poll or fetch time, in
# `Status.detail`, never assumed from this constant and never stamped
# anywhere by this module on its own initiative.
#
# A named accelerator COULD NOT be requested through the retired
# `kaggle==1.7.4.5` client at all -- that claim was measured, not assumed
# (its `kernels_push()` built the save-kernel request field by field and
# read exactly `enable_gpu`/`enable_tpu`; the string `machine_shape` occurred
# nowhere in that package, so a `machine_shape` key in `kernel-metadata.json`
# was never transmitted, and every push this skill made before this change
# silently ran wherever the service's own default draw landed). That claim
# is retired, not carried forward: the packaged client `kaggle_driver.py`
# imports now maps `machine_shape` straight onto its own save-kernel
# request, and `KAGGLE_MACHINE_SHAPE` above reaches every push.
# `enable_gpu`/`enable_tpu`
# are documented DEPRECATED in the service's own request shape in favor of
# `machine_shape`, and are kept here anyway as the field a reader unfamiliar
# with the newer one still expects to see -- never relied on alone to steer
# which card arrives.
REQUEST_GPU = True

# The filename `kernels push -p <dir>` looks for beside a kernel's
# entrypoint — Kaggle's own convention, not this module's invention. A
# generated job's directory must carry this file before `submit()` will
# push it; see `KaggleAdapter.submit()`'s refusal below.
KERNEL_METADATA_FILENAME = "kernel-metadata.json"

# Where a kernel that names another kernel in its metadata's
# `kernel_sources` finds that kernel's output: `<root>/<owner>/<slug>/`.
# LIVE-VERIFIED (2026-10-27, on one account): a kernel
# pushed with `kernel_sources: ["<owner>/psmith-carry-test-a"]` read the
# source kernel's `/kaggle/working/ckpt/state.json` at
# `/kaggle/input/notebooks/<owner>/psmith-carry-test-a/ckpt/state.json` --
# note the `notebooks/` segment. Verified within one account only; carrying
# across two owners' private kernels was not (kernel-carry S4).
KERNEL_INPUT_ROOT = "/kaggle/input/notebooks"

# The root under which a kernel finds the public datasets its metadata names
# in `dataset_sources` (kernel-input-datasets S2-S3), read-only. The exact
# sub-path below it is NOT hard-coded: the runner searches this root for
# each ref's slug, because the live-verified kernel output above appeared
# under a `notebooks/<owner>/<slug>/` segment nobody predicted, and a
# dataset's own segment is not verified live here. A pushed kernel is a
# non-interactive session: it cannot attach a dataset at run time (the
# service refused `New Datasets cannot be attached in non-interactive
# sessions`), so the datasets must be named in the push itself.
DATASET_INPUT_ROOT = "/kaggle/input"

# The suffix of the alternate kernel a continuation is pushed to when the
# kernel it carries from has the ref it would otherwise reuse (see
# `KaggleAdapter.submit()`): `<slug>` and `<slug>-carry` take turns.
CARRY_ALTERNATE_SUFFIX = "-carry"

# `jobfolder.py`'s own `RUN_CONFIG_FILENAME` constant, duplicated here
# rather than imported: this module never imports `jobfolder.py` (the
# dependency runs the other way — `jobfolder.py` reaches this module only
# through the opaque `ADAPTER.resolve_metadata()` registry, never a direct
# import), the same reason `KERNEL_METADATA_FILENAME` above is this
# module's own constant rather than a shared one. RE-VERIFIED against the
# installed `kaggle` 1.7.4.5, the version claim here having named one that
# was never installed on this machine: `kernels_push()` reads `code_file`,
# sends its bytes as the request's `text`, and has no directory upload at
# all, so no sibling file in the pushed directory ever reaches the worker
# on its own. A generated job's `run-config.json` is real and versioned
# beside its `runner.ipynb`, but the worker never sees it unless something
# puts it there; see `_run_config_cell()` below.
RUN_CONFIG_FILENAME = "run-config.json"

# The code bundle (`generate-job --code-bundle`), duplicated by name for the
# same reason as `RUN_CONFIG_FILENAME`: this module does not import
# `jobfolder.py`. A kernel has no way to be handed a repository credential,
# so a private repository's pinned code travels INSIDE the pushed notebook:
# `submit()` stages one more cell that writes the bundle's bytes (base64)
# beside `run-config.json`, and `runner_bootstrap.py` unpacks it instead of
# cloning.
CODE_BUNDLE_FILENAME = "code-bundle.tar.gz"

# The bound on a bundle's COMPRESSED bytes this adapter will carry. The
# service documents no size limit for a pushed notebook's source (searched
# 2026-10-28: neither the API's own documentation nor its release notes
# state one), so this is a conservative choice, not a published number:
# 768 KiB of gzip becomes ~1 MiB of base64 in the cell, a few times the
# 236,855 bytes the target that motivated this measured at its pin.
KAGGLE_CODE_BUNDLE_MAX_BYTES = 768 * 1024

# The seam's own five-value vocabulary a raw Kaggle status is translated
# into — never passed through. Anything Kaggle reports that is not a key
# here (a cancellation state, a future addition to Kaggle's own vocabulary,
# anything this table was not updated for) becomes "unknown", deliberately,
# rather than guessed at.
_KAGGLE_STATUS_TO_SEAM = {
    "queued": "queued",
    "running": "running",
    "complete": "complete",
    "error": "failed",
}

_SLUG_DISALLOWED = re.compile(r"[^a-z0-9-]+")


def _slugify(text: str) -> str:
    """A deterministic slug from raw text — never a lookup, never state
    kept anywhere in this process. Kaggle kernel refs are
    `<username>/<slug>`; this supplies the second half.
    """
    lowered = text.lower()
    slug = _SLUG_DISALLOWED.sub("-", lowered).strip("-")
    return slug or "kernel"


def _kernel_slug(entrypoint: Path) -> str:
    """A deterministic slug derived from an entrypoint's own filename —
    the legacy shape's own source of one: `<Name>/Notebooks/<Something>.ipynb`
    names exactly one notebook per file, so the filename is what actually
    tells two legacy submissions apart. NEVER the right source for a
    generated job folder, whose entrypoint is `runner.ipynb` for every
    job — see `submit()`'s own docstring for why that distinction matters.
    """
    return _slugify(entrypoint.stem)


def kernel_ref(
    *,
    worker: str,
    title: str | None,
    entrypoint: Path,
    run_config: Mapping[str, object],
) -> tuple[str, str | None, list[str]]:
    """The `<worker>/<slug>` ref a push goes to, the title that yields it,
    and the earlier kernel refs it carries from -- `(ref, title, carried)`.

    A campaign sends one job per granted slot (S1, parallel campaigns):
    slot 2 and up of the same job on the same account is its OWN kernel
    (`-slot-<n>`), or the second push would overwrite the first under one
    ref; slot 1 keeps the ref it always had. The title carries the suffix
    too, since the service derives a new kernel's slug from its title.

    kernel-carry: a push never goes to a PROTECTED ref -- one this job
    carries from (`run_config["carry"]`), or one any other share of the
    same campaign carries from, or one pending continuation evidence still
    points to (`run_config["carryProtected"]`, computed by `submit` over
    the whole ledger). A new version of such a kernel may replace the very
    output a continuation is about to read, and a kernel naming itself as
    its own source was never verified live. The push then goes to the
    first alternate not protected, deterministically: `<slug>-carry`,
    `<slug>-carry-2`, `<slug>-carry-3`, ... A job with neither key keeps
    exactly the ref it had before this existed.
    """
    slot = run_config.get("slot")
    if isinstance(slot, int) and not isinstance(slot, bool) and slot > 1:
        if title:
            title = f"{title}-slot-{slot}"
            slug = _slugify(title)
        else:
            slug = f"{_kernel_slug(entrypoint)}-slot-{slot}"
    else:
        slug = _slugify(title) if title else _kernel_slug(entrypoint)
    carried = [
        str(row["ref"]) for row in run_config.get("carry") or ()
        if isinstance(row, Mapping) and row.get("ref")
    ]
    protected = set(carried) | {
        str(ref) for ref in run_config.get("carryProtected") or () if ref
    }
    if f"{worker}/{slug}" in protected:
        base_title, base_slug = title, slug
        attempt = 1
        while True:
            suffix = (
                CARRY_ALTERNATE_SUFFIX if attempt == 1
                else f"{CARRY_ALTERNATE_SUFFIX}-{attempt}"
            )
            if base_title:
                title = f"{base_title}{suffix}"
                slug = _slugify(title)
            else:
                slug = f"{base_slug}{suffix}"
            if f"{worker}/{slug}" not in protected:
                break
            attempt += 1
    return f"{worker}/{slug}", title, carried


def _declared_input_datasets(job: "ADAPTER.Job") -> list[str]:
    """The `inputDatasets` refs a job declares: the job folder's own
    `run-config.json` (`generate-job --input-dataset`, validated by
    `submit` before this is reached), overridden by the submission's
    `run_config` when it names the key. `[]` when neither does, or when
    there is no readable job folder (the legacy shape attaches nothing)."""
    declared: object = None
    run_config_path = job.entrypoint.parent / RUN_CONFIG_FILENAME
    if run_config_path.is_file():
        try:
            parsed = json.loads(run_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, Mapping):
            declared = parsed.get("inputDatasets")
    if "inputDatasets" in job.run_config:
        declared = job.run_config["inputDatasets"]
    if not isinstance(declared, (list, tuple)):
        return []
    return [str(ref) for ref in declared if isinstance(ref, str) and ref]


def assemble_metadata(run_config: Mapping[str, object]) -> tuple[str, str]:
    """Build the `kernel-metadata.json` a generated job folder ships beside
    its runner notebook, so `kernels push -p <dir>` both accepts the push
    and requests the pinned accelerator.

    Registered under `ADAPTER.register_metadata("kaggle", ...)` below —
    the ONE thing a caller above the adapter registry ever gets back is an
    opaque `(filename, text)` pair; nothing above this module ever learns
    what either one means, only that they exist and where to write them.

    The field set below maps onto `ApiSaveKernelRequest` through
    `kaggle_driver.py`'s own `_METADATA_PASSTHROUGH_KEYS` table (this
    module never builds that request type itself — that stays the driver's
    own job, the one file permitted to import the packaged client):

    - `machine_shape` — `KAGGLE_MACHINE_SHAPE` (`"NvidiaTeslaT4"`), sent on
      EVERY push. A prior version of this adapter emitted this key against
      the retired `kaggle==1.7.4.5` client, whose `kernels_push()` built its
      request field by field and never read `machine_shape` at all — that
      key silently reached nobody, and every push this skill made before
      that was noticed ran wherever the service's own default draw landed.
      PROVEN LIVE against the current dependency (see
      `KAGGLE_MACHINE_SHAPE`'s own comment above): a kernel pushed with this
      field reached a Tesla T4 and completed.
    - `enable_gpu` — kept alongside `machine_shape`, not in place of it: the
      service's own request shape documents `enable_gpu`/`enable_tpu` as
      DEPRECATED in favor of `machine_shape`, but a reader unfamiliar with
      the newer field still expects to see this one, and sending both costs
      nothing extra.

      This is where the honesty about scope belongs: emitting the fields
      the client reads is a request, and a request is not a receipt. No
      offline test can prove a submission actually received a T4. The
      receipt arrives with the first real run, in `Status.detail` — which
      is what that field is for.
    - `enable_internet` — `True`. The generated runner does `git init` /
      `remote add` / `fetch` inside the kernel to reach the pinned commit,
      and Kaggle kernels have internet access disabled by default; without
      this the clone fails at runtime, after the push already succeeded.
    - `language`/`kernel_type` — `"python"`/`"notebook"`: the runner this
      skill generates is always a `.ipynb` file of Python cells.
    - `is_private` — `True`, a deliberate default this brief left
      unspecified: nothing about a submitted training run should default
      to public.
    - `id` and `code_file` — present, but deliberately BLANK. `id` is
      `<owner>/<kernel-slug>`; it names the account, and no worker is
      assigned yet at `generate-job` time — the packer only assigns one at
      submit time, and the very same job folder pushed to five accounts
      needs five different `id` values. `code_file` names the entrypoint
      file relative to this folder, which this function has no path to
      either (`run_config` carries no notebook path). Both are completed
      by `KaggleAdapter.submit()` below, in a STAGED COPY of the job
      folder — never by mutating this versioned file in place.
    - `title` — derived from `run_config`'s own `jobName`, when present,
      so the pushed kernel is identifiable; padded to satisfy the client's
      own five-character minimum.

    `run_config` is read only for `jobName`, with a fallback when absent
    — this function must not crash on a caller (this module's own test
    suite included) that hands it a partial mapping.
    """
    job_name = str(run_config.get("jobName") or "job")
    title = f"papersmith-{job_name}"
    payload = {
        "id": "",
        "title": title,
        "code_file": "",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_internet": True,
        "enable_gpu": REQUEST_GPU,
        "machine_shape": KAGGLE_MACHINE_SHAPE,
    }
    return KERNEL_METADATA_FILENAME, json.dumps(payload)


def _run_config_cell_source(run_config_text: str) -> str:
    """The injected cell's own source: writes `run_config_text` — the job
    folder's own `run-config.json` content, staged by the caller either
    verbatim or merged with `job.run_config`'s submission-time overrides
    (see `submit()`'s own docstring for that merge rule) — to
    `run-config.json` in whatever directory the kernel is executing in.
    This function itself is agnostic to which of the two `run_config_text`
    is: it only ever writes the string it is handed.

    `Path("run-config.json")`, relative, deliberately not an absolute
    `/kaggle/working/...` guess: `runner_bootstrap.py`'s own
    `load_run_config()` resolves `Path.cwd() / "run-config.json"` when no
    `base_dir` is given, which is exactly how the real notebook cell runs
    it (`if __name__ == "__main__": bootstrap()`). This injected cell runs
    in the SAME kernel process, immediately before that one, so writing
    relative to whatever `Path.cwd()` already is at that point lands in
    the exact place the next cell will look — no assumption about
    Kaggle's own working directory convention needed, and none made.

    `repr(run_config_text)` is what keeps this safe for arbitrary JSON
    content (quotes, newlines, unicode) as a single Python string literal,
    without needing to guess at a quoting scheme of its own.
    """
    return (
        "from pathlib import Path\n\n"
        f"Path('run-config.json').write_text({run_config_text!r}, encoding='utf-8')\n"
    )


def _run_config_notebook_cell(run_config_text: str) -> dict:
    """One notebook cell, in the exact shape `jobfolder.py`'s own
    `_notebook_cell()` uses (`cell_type`/`metadata`/`execution_count`/
    `outputs`/`source`) — duplicated rather than imported, for the same
    reason `RUN_CONFIG_FILENAME` above is duplicated: this module does not
    import `jobfolder.py`. This is CONFIGURATION, not runner logic: unlike
    the two real cells `build_notebook()` copies byte for byte with zero
    interpolation, this cell's own source is job-specific by construction
    — it always was going to differ between two jobs, because the file it
    materializes differs between them. It is a NEW cell prepended ahead of
    the other two, never an edit to either of their bytes.
    """
    source = _run_config_cell_source(run_config_text)
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def _code_bundle_cell(bundle: bytes) -> dict:
    """One cell that writes the code bundle's bytes to `code-bundle.tar.gz`
    in the kernel's working directory — relative, for the same reason as
    the run-config cell. Base64 inside a `repr`'d literal keeps arbitrary
    bytes one safe Python string."""
    encoded = base64.b64encode(bundle).decode("ascii")
    source = (
        "import base64\nfrom pathlib import Path\n\n"
        f"Path({CODE_BUNDLE_FILENAME!r}).write_bytes(base64.b64decode({encoded!r}))\n"
    )
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def _read_declared_code_bundle(job_dir: Path, run_config_text: str) -> bytes | None:
    """The bundle bytes a job folder's `run-config.json` declares, checked
    against its recorded sha256 before anything is pushed; `None` for a job
    that declares none. Refuses an absent or mismatched file: a push without
    the code would only fail inside the kernel, after quota was spent."""
    try:
        block = json.loads(run_config_text).get("codeBundle")
    except (json.JSONDecodeError, AttributeError):
        return None
    if block is None:
        return None
    path = job_dir / CODE_BUNDLE_FILENAME
    if not isinstance(block, Mapping) or block.get("file") != CODE_BUNDLE_FILENAME:
        raise KaggleAdapterError(
            f"run-config.json's codeBundle does not name {CODE_BUNDLE_FILENAME!r}: "
            "refusing to push"
        )
    if not path.is_file():
        raise KaggleAdapterError(
            f"CODE_BUNDLE_MISMATCH: {path} is absent but run-config.json "
            "declares a code bundle: refusing to push a kernel with no code"
        )
    bundle = path.read_bytes()
    if hashlib.sha256(bundle).hexdigest() != block.get("sha256"):
        raise KaggleAdapterError(
            f"CODE_BUNDLE_MISMATCH: {path} does not hash to run-config.json's "
            "codeBundle.sha256: refusing to push"
        )
    return bundle


def _stage_run_config_cell(notebook_path: Path, run_config_text: str) -> None:
    """Prepend the injected cell to the notebook at `notebook_path` — a
    file inside the STAGED copy `submit()` builds, never the job folder's
    own versioned `runner.ipynb`. Reads and rewrites only that staged
    file; the two existing cells travel through unread and unmodified,
    since this only ever inserts at index 0.
    """
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    notebook["cells"].insert(0, _run_config_notebook_cell(run_config_text))
    notebook_path.write_text(json.dumps(notebook, indent=1), encoding="utf-8")


# The seam's own shape (`adapter.py`), aliased under this module's name so
# every existing caller and test that imports `CredentialHandle` FROM here
# keeps working unchanged. The class is defined exactly once, in the seam,
# because it carries no service-specific behavior at all — moving it there
# is what lets a second backend adapter reuse the same shape without
# redefining it; only the environment variable it is eventually handed to
# (`KAGGLE_API_TOKEN`, below) is this service's own.
CredentialHandle = ADAPTER.CredentialHandle


class KaggleAdapter(ADAPTER.Adapter):
    """The concrete `Adapter` this skill ships for Kaggle.

    Constructible with no arguments, matching every other adapter this
    skill's own CLI instantiates via `ADAPTER.resolve(name)()`
    (`remote_cli.py`'s `main()` calls `adapter_cls()`, never with
    arguments). With no credentials supplied, every method that needs one
    refuses cleanly the first time it is asked to act for a worker —
    fails closed, not silently.
    """

    # Read by `remote_cli.py`'s generic construction site, through a bare
    # `getattr(adapter_cls, "CREDENTIAL_CLI", None)` that names no backend
    # at all — see `_accounts_cli_for()` there. This is an ordinary class
    # attribute, not one of the `Adapter` ABC's six operations, which is
    # what lets an adapter with no credential-materializing CLI of its own
    # (this skill's own test doubles included) simply not define it. Reusing
    # `DEFAULT_ACCOUNTS_CLI` here, rather than declaring a second path, is
    # what keeps this module's own `workers()` and `credentials.py`'s
    # `materialize()` pointed at the exact same script.
    CREDENTIAL_CLI = DEFAULT_ACCOUNTS_CLI

    # The optional seam capability (`adapter.py`): this backend ships a
    # code bundle inside the pushed notebook, up to this many compressed
    # bytes. See `KAGGLE_CODE_BUNDLE_MAX_BYTES` for where the number comes
    # from.
    CODE_BUNDLE_MAX_BYTES = KAGGLE_CODE_BUNDLE_MAX_BYTES

    # kernel-input-datasets S2: this adapter attaches a job's declared
    # `inputDatasets` to the push as the metadata's `dataset_sources`, and
    # the kernel finds them mounted under this root.
    INPUT_DATASETS_ROOT = DATASET_INPUT_ROOT

    @classmethod
    def session_limit_seconds(cls, machine_shape: str | None = None) -> int | None:
        """`KAGGLE_SESSION_LIMIT_SECONDS` for `machine_shape` -- the shape
        every push requests (`KAGGLE_MACHINE_SHAPE`) when `None`; `None`
        for a shape the table does not list."""
        shape = KAGGLE_MACHINE_SHAPE if machine_shape is None else machine_shape
        return KAGGLE_SESSION_LIMIT_SECONDS.get(shape)

    def carry_source(self, submission_id: str) -> dict[str, str] | None:
        """kernel-carry S2: an earlier submission's id IS its kernel ref
        (`<worker>/<slug>`, see `submit()`), so a later kernel names it in
        `kernel_sources` and reads its output under `KERNEL_INPUT_ROOT`.
        Asks the service nothing. `None` for an id without the one `/`
        this adapter's own ids always carry."""
        owner, _, slug = str(submission_id).partition("/")
        if not owner or not slug:
            return None
        return {"ref": submission_id, "mount": f"{KERNEL_INPUT_ROOT}/{submission_id}"}

    def __init__(
        self,
        *,
        credentials: (
            Mapping[str, CredentialHandle] | Callable[[str], CredentialHandle] | None
        ) = None,
        accounts_cli: Path | str | None = None,
        kaggle_executable: str = KAGGLE_EXECUTABLE,
        timeout: float = SUBPROCESS_TIMEOUT_SECONDS,
        fetch_timeout: float = KAGGLE_FETCH_TIMEOUT_SECONDS,
        driver_script: Path | str | None = None,
        team_registry: Path | str | None = None,
    ) -> None:
        self._credential_provider = self._normalize_credentials(credentials)
        # The registry's PATH, read lazily by `_team()`; `None` means the
        # module default, resolved at read time.
        self._team_registry = Path(team_registry) if team_registry is not None else None
        self._accounts_cli = Path(accounts_cli) if accounts_cli else DEFAULT_ACCOUNTS_CLI
        self._kaggle_executable = kaggle_executable
        self._timeout = timeout
        # Held separately from `self._timeout`, never derived from it: the
        # two budgets answer different questions (see the two module
        # constants), and collapsing them is exactly the defect this
        # attribute exists to prevent.
        self._fetch_timeout = fetch_timeout
        self._driver_script = Path(driver_script) if driver_script else DEFAULT_KAGGLE_DRIVER

    @staticmethod
    def _normalize_credentials(
        credentials: (
            Mapping[str, CredentialHandle] | Callable[[str], CredentialHandle] | None
        ),
    ) -> Callable[[str], CredentialHandle]:
        """One internal shape regardless of what a caller handed in.

        A caller that already knows every worker it will ever ask for —
        most of this module's own test suite — passes a plain mapping,
        unchanged from before this method existed. A caller that does NOT
        pass one instead: `remote_cli.py`'s `poll` command never learns a
        worker id at all, only a submission id this adapter alone is
        permitted to split, so nothing above this seam can build a full
        mapping up front for that command. That caller passes a callable,
        resolved lazily the first time a worker is actually needed.

        Both collapse to the same shape here so `_credential_for()` below
        never has to ask which one it was given.
        """
        if credentials is None:
            def _none(worker: str) -> CredentialHandle:
                raise KeyError(worker)

            return _none
        if callable(credentials) and not isinstance(credentials, Mapping):
            return credentials
        mapping = dict(credentials)

        def _lookup(worker: str) -> CredentialHandle:
            return mapping[worker]

        return _lookup

    def _credential_for(self, worker: str) -> CredentialHandle:
        try:
            return self._credential_provider(worker)
        except KeyError:
            raise KaggleAdapterError(
                f"no credential handle registered for worker {worker!r}; this "
                "adapter accepts credentials only as CredentialHandle instances, "
                "supplied directly or produced by a provider callable, never by "
                "reading a credential file on its own initiative"
            ) from None

    def _env_for(self, handle: CredentialHandle | None) -> dict[str, str]:
        """Build the child process's WHOLE environment from an allowlist —
        never this process's own `os.environ` forwarded wholesale, which
        would leak every other variable this process happens to be
        carrying, credential-shaped or not.

        `KAGGLE_API_TOKEN` carries the token's VALUE, and this is the one
        expression in this skill that ever reads one. Measured, not
        assumed: the installed client's own `_try_fill_auth()` reads that
        variable and hands it straight to `BearerAuth(api_token)` — by
        value, with no path check of any kind — so a path here becomes
        the literal text of an `Authorization: Bearer` header and
        authenticates nothing. The legacy `KAGGLE_CONFIG_DIR`/`kaggle.json`
        shape is not an escape from that: it routes an access token
        through a Basic-auth path it was never meant for and answers 401
        for every account regardless of validity.

        So the by-path-only contract this adapter used to hold is SPENT,
        not preserved, and saying so is the point: what still holds is
        narrower and structural. The read happens here, in the one file
        allowed to name a service, in a single expression whose result goes
        straight onto one child process's environment; no module above this
        one touches `token_path` at all, and the value is never logged,
        never interpolated into a message, and never returned upward.

        `.strip()` is load-bearing: the credential file ends with the
        newline `materialize` writes, and a newline inside a bearer header
        is a malformed header rather than a credential. A file that cannot
        be read, or that holds nothing once stripped, is refused here —
        the same fail-closed discipline every other unusable answer in this
        module gets, rather than a request sent with a header the service
        can only answer 401 to.
        """
        env = {"PATH": os.environ.get("PATH", "")}
        if handle is not None:
            try:
                env["KAGGLE_API_TOKEN"] = handle.token_path.read_text(
                    encoding="utf-8"
                ).strip()
            except OSError as exc:
                raise KaggleAdapterError(
                    f"could not read the credential file for worker "
                    f"{handle.worker_id!r}: {exc}"
                ) from exc
            if not env["KAGGLE_API_TOKEN"]:
                raise KaggleAdapterError(
                    f"the credential file for worker {handle.worker_id!r} holds "
                    "nothing once stripped; materialize that worker's credential "
                    "again rather than sending an empty bearer header"
                )
        return env

    def _run(
        self,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess:
        """One subprocess boundary for every child this adapter starts.

        `timeout=None` — what every caller but `fetch()` passes, by simply
        not passing it — means `self._timeout`, the control-plane budget,
        so those call sites behave exactly as they did before this
        parameter existed. `fetch()` passes `self._fetch_timeout`
        explicitly because its child is a bulk transfer, not a control
        call; see the module constants for why one number cannot serve
        both.
        """
        effective_timeout = self._timeout if timeout is None else timeout
        try:
            return subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            # Names the budget that ACTUALLY expired, never `self._timeout`
            # unconditionally: a fetch killed at 1800s reported as "timed
            # out after 120.0s" would send the reader hunting for a limit
            # that was not the one enforced.
            raise KaggleAdapterError(
                f"{argv[0]} timed out after {effective_timeout}s: refusing to guess "
                "at a status or a completion this process never confirmed"
            ) from exc
        except OSError as exc:
            # Naming what failed is not naming what to do. On a machine where
            # the service CLI was never installed this is the whole question,
            # and the skill's own `## Environment` section is where a reader
            # would look — so the sentence lives here, in the one file this
            # skill lets name a service, rather than in a seam that must not.
            remedy = ""
            if argv and argv[0] == self._kaggle_executable:
                remedy = (
                    f" — this adapter shells out to the {argv[0]!r} command line, "
                    "which arrives with `pip install kaggle`; install it and make "
                    "sure the directory pip reports putting it in is on PATH"
                )
            elif len(argv) > 1 and argv[0] == sys.executable and argv[1] == str(
                self._driver_script
            ):
                # The SDK driver's own remedy, distinct from the CLI's: a
                # missing `kaggle_driver.py` (moved or deleted) is not the
                # same failure as a missing SDK import (that one is the
                # driver's own `selftest` refusal, printed as JSON on its
                # stdout, never an `OSError` this branch would ever see)
                # — this is "the interpreter could not even launch the
                # script", so the remedy names the interpreter and the
                # SDK-path install command for it, never the retired
                # `pip install kaggle` sentence a CLI-shaped failure used
                # to get.
                remedy = (
                    f" — this adapter shells out to the SDK driver at "
                    f"{argv[1]!r} under {sys.executable!r}; install this "
                    f"skill's own pinned dependency (see `requirements.txt`) "
                    f"for that interpreter with `{sys.executable} -m pip "
                    "install -r requirements.txt`"
                )
            raise KaggleAdapterError(
                f"could not run {argv[0]}: {exc}{remedy}") from exc

    def workers(self) -> list["ADAPTER.Worker"]:
        """Usernames from the sanctioned `list --json` command, each
        stamped with THIS service's documented per-worker allowance.

        Runs `<this interpreter> <accounts_cli> list --json` as a subprocess
        and reads only its stdout, through `_account_names_on_disk()` below
        — the one place this module builds that argv and reads it back. It
        never opens, globs or otherwise touches any file `accounts_cli`
        itself might consult. That is what lets this method answer
        normally even when whatever file backs `accounts_cli`'s own answer
        is unreadable to THIS process directly — this process never tries
        to read it at all.

        Under the TEAM model (`<workspace>/.papersmith/team.json` maps at
        least one owner to a Kaggle username) only the owner-mapped listed
        accounts are workers, one per owner; `team_report()` states why
        every other listed account is excluded and which mappings are not
        validated. With no registry, or one mapping no Kaggle account, the
        list is every listed account, exactly as before.
        """
        names = _account_names_on_disk(self._accounts_cli, self._run)
        team = self._team()
        if team is not None:
            names = list(_team_report(names, team).workers)
        return [ADAPTER.Worker(id=name, capacity=KAGGLE_WORKER_CAPACITY) for name in names]

    def _team(self) -> dict[str, str] | None:
        path = self._team_registry if self._team_registry is not None else DEFAULT_TEAM_REGISTRY
        return load_kaggle_team(path)

    def team_report(self) -> KaggleTeamReport | None:
        """The team registry's effect on the listed accounts, or `None` when
        no registry maps a Kaggle account (every listed account is a
        worker). Not one of the seam's six operations: an ordinary method a
        planner or an operator-facing report can ask."""
        team = self._team()
        if team is None:
            return None
        return _team_report(_account_names_on_disk(self._accounts_cli, self._run), team)

    def submit(self, job: "ADAPTER.Job") -> "ADAPTER.Submission":
        """Push a kernel version and report back the ref this adapter will
        recognize it by later.

        The submission id is `<worker>/<slug>`, never read out of anything
        the `kaggle` process printed. `poll()`, `fetch()` and
        `list_active()` all recover `worker` from this same id, by
        splitting on the one `/` this construction guarantees is there.

        The slug itself has two different sources depending on shape, and
        conflating them was a real bug this docstring now exists to
        prevent reintroducing: for a GENERATED job folder (metadata file
        present), the slug is derived from the metadata's own `title` —
        confirmed against a real Kaggle account that a newly-created
        kernel's actual slug is the one the service derives from `title`,
        not from the `id` field this method sends it. That one is a LIVE
        observation and was not re-verified against the installed client,
        because it cannot be: the client only warns when `id`'s slug and
        `slugify(title)` disagree, and what the service does with the two
        is not visible in its source. It is recorded here as observed, not
        as read. `job.entrypoint`'s
        own filename is `runner.ipynb` for every generated job
        (`jobfolder.py`'s `RUNNER_FILENAME` constant), so deriving the
        slug from it instead — as this method used to — made every
        job-folder submission to the same worker collide on the identical
        ref `<worker>/runner`, silently overwriting one job's kernel with
        the next one pushed. For the LEGACY shape (no metadata file), the
        entrypoint genuinely does name one notebook per file, so its own
        filename remains the right source there.

        A non-empty `job.run_config` marks a generated job — one whose
        directory `jobfolder.py` was supposed to have written
        `assemble_metadata()`'s output into. This method refuses, before
        ever calling `kernels push`, when that metadata file is absent:
        pushing a folder the service will reject on its own is worse than
        refusing here. An empty `run_config` is the legacy shape and is
        never checked — it behaves exactly as it did before this refusal
        existed.

        The metadata file's own PRESENCE, not `job.run_config`, is what
        decides whether this method completes and stages it: `cmd_submit`
        only ever sets `run_config["mode"] = "smoke"` for a smoke run, so
        an ordinary (non-smoke) job-folder submission carries an EMPTY
        `run_config` exactly like the legacy shape does. `id` names an
        account, which is only known here at submit time — the same
        versioned job folder pushed to five different workers needs five
        different `id` values, and a static file written once at
        `generate-job` time cannot hold that. So when the metadata file is
        present, this method reads the template `assemble_metadata()`
        wrote, fills in `id` (`<worker>/<slug>`) and `code_file`
        (`job.entrypoint`'s own basename — known here, never guessed at by
        `assemble_metadata()`, which has no path to it), and writes the
        completed file into a STAGED COPY of the job folder in a temp
        directory — `kernels push -p <staged dir>` runs against that copy.
        The versioned `kernel-metadata.json` inside the job folder itself
        is read, never opened for writing, and stays byte-for-byte
        unchanged: nothing here mutates a committed artifact per worker.

        `kernels push` uploads `code_file` alone — re-verified by reading
        `kernels_push()` in the installed `kaggle` 1.7.4.5, there is no
        directory upload, so a job folder's own sibling `run-config.json`
        never reaches the worker on its own. This same staging step also
        prepends a cell to the STAGED notebook copy that materializes that
        file back onto disk before the runner's own first cell ever reads
        it (`_stage_run_config_cell()`), whenever `run-config.json` is
        present beside the entrypoint — it always is for a real generated
        job, written by `jobfolder.generate_job()` before the metadata
        file. Its absence (a synthetic job folder carrying only a
        metadata file, as several of this module's own narrower tests
        build) is not treated as an error here: there is nothing to
        materialize, so nothing is injected — a silent no-op rather than
        a refusal, since it changes nothing the caller asked for.

        The staged bytes are the FILE's own content merged with
        `job.run_config`, never the file verbatim on its own. The file was
        made authoritative by a prior fix (`kernels push` uploads only
        `code_file`, so the versioned `run-config.json` had to be injected
        as a cell), and that same stroke silently orphaned every
        submission-time mutation of `job.run_config` — `submit --smoke`
        sets `run_config["mode"] = "smoke"` on the in-memory `Job`, but
        `select_block()` in the pushed kernel only ever saw the file's own
        `mode`-less content, so a `--smoke` submission always ran the
        normal `run` block. The merge rule: when `job.run_config` is
        empty — the legacy shape, and also the ordinary (non-smoke)
        job-folder shape `cmd_submit` produces — the file's own bytes are
        read and staged completely unread otherwise, exactly as before
        this fix; no `json.loads`/`json.dumps` round-trip ever touches
        them, so this path stays byte-identical to today's behavior by
        construction, not by coincidence of formatting. Only when
        `job.run_config` is non-empty is the file parsed, shallow-updated
        at the TOP LEVEL with `dict(job.run_config)` (so `job.run_config`
        wins on a key collision), and re-serialized. Shallow/top-level is
        the deliberate choice, not an oversight: every override this seam
        has ever needed to express — `mode` — is itself a top-level key,
        and `job.run_config` is normalized to an opaque, flat mapping by
        `adapter.py`'s own `Job.__post_init__`; nothing upstream of this
        adapter ever constructs a nested override. This rule does NOT
        cover replacing a single nested field (say, one key inside the
        file's own `run.smoke` block) without clobbering the rest of that
        block — a caller needing that would have to pass the whole nested
        value, since a top-level key present in `job.run_config` replaces
        the file's value for that key entirely rather than merging into
        it.

        Both branches now stage into the SAME temporary copy and always
        complete a `kernel-metadata.json` there, even for the LEGACY
        shape: `_push()` shells out to `kaggle_driver.py` unconditionally
        now, and that driver's own request-mapping step
        (`_save_kernel_request_from_staging`) always reads one from the
        staging directory — Decision 4's table has nothing else to build
        an `ApiSaveKernelRequest` from. A legacy job folder that genuinely
        carries none gets a minimal template synthesized here, in the
        staged copy only; the job folder itself still never needs to
        carry one, exactly as before.

        `machine_shape` is force-set onto the staged template with
        `setdefault`, immediately before `id`/`code_file` are filled in —
        ABSENT-key-only, never value-only: a GENERATED job folder whose
        `kernel-metadata.json` predates this (`assemble_metadata()` did
        not yet write the key) is the one shape that otherwise reaches
        `kernels push` with no requested card at all, silently landing on
        whatever the service defaults to. A template that already names
        one — freshly generated, or a target that deliberately asks for a
        different card — is staged exactly as read.
        """
        metadata_path = job.entrypoint.parent / KERNEL_METADATA_FILENAME
        if job.run_config and not metadata_path.is_file():
            raise KaggleAdapterError(
                f"{job.entrypoint} carries a non-empty run_config but "
                f"{metadata_path} is absent: refusing to push a kernel "
                "the service would reject for missing metadata"
            )

        # Under the team model a listed account no owner maps is never
        # spent, even when named explicitly — refused from the registry
        # alone, before any credential is asked for or any child runs.
        team = self._team()
        if team is not None and job.worker not in team:
            raise KaggleAdapterError(
                f"worker {job.worker!r} is {TEAM_UNMAPPED_REASON}; submit to "
                f"an owner-mapped account ({', '.join(sorted(team))})"
            )

        handle = self._credential_for(job.worker)

        with tempfile.TemporaryDirectory(prefix="kaggle-push-") as staging_dir:
            staging_path = Path(staging_dir)
            shutil.copytree(job.entrypoint.parent, staging_path, dirs_exist_ok=True)

            if metadata_path.is_file():
                template = json.loads(metadata_path.read_text(encoding="utf-8"))
            else:
                # LEGACY shape, synthesized rather than read: the same
                # minimal template `assemble_metadata()` would have
                # written, built here in the staged copy only — never
                # written back to the job folder itself.
                template = {
                    "language": "python",
                    "kernel_type": "notebook",
                    "is_private": True,
                    "enable_internet": True,
                    "enable_gpu": REQUEST_GPU,
                    "machine_shape": KAGGLE_MACHINE_SHAPE,
                }

            # `id` and `code_file`, below, are not the only fields this
            # method has ever forced onto a staged template -- this one
            # joins them, but ABSENCE-gated rather than unconditional.
            # `assemble_metadata()` only writes `machine_shape` into
            # templates it generates fresh; a `kernel-metadata.json`
            # versioned into a job folder before that landed carries none
            # at all, and was the one shape that kept landing on whatever
            # the service defaults to (a P100, observed) even after this
            # adapter started requesting a named card everywhere else.
            # `setdefault` rather than a plain assignment: a template that
            # already names a `machine_shape` -- generated fresh, or a
            # target that deliberately asks for something else -- is read
            # back exactly as staged. This method cannot tell "never set"
            # apart from "set on purpose to a different value", and only
            # the former is this defect.
            template.setdefault("machine_shape", KAGGLE_MACHINE_SHAPE)

            ref, title, carried = kernel_ref(
                worker=job.worker, title=template.get("title"),
                entrypoint=job.entrypoint, run_config=job.run_config,
            )
            if title:
                template["title"] = title
            template["id"] = ref
            template["code_file"] = job.entrypoint.name
            # kernel-carry S2: a continuation names each earlier kernel whose
            # output it resumes from, so the service mounts that output
            # under `KERNEL_INPUT_ROOT`. Added only when `submit` handed a
            # `carry` list; a job without one is staged exactly as before.
            if carried:
                sources = list(template.get("kernel_sources") or [])
                sources.extend(ref_ for ref_ in carried if ref_ not in sources)
                template["kernel_sources"] = sources
            # kernel-input-datasets S2: the public datasets the job folder
            # declares are named in the push, so the non-interactive kernel
            # gets them mounted read-only under `DATASET_INPUT_ROOT`. A job
            # declaring none is staged exactly as before.
            declared_inputs = _declared_input_datasets(job)
            if declared_inputs:
                datasets = list(template.get("dataset_sources") or [])
                datasets.extend(ref_ for ref_ in declared_inputs if ref_ not in datasets)
                template["dataset_sources"] = datasets
            (staging_path / KERNEL_METADATA_FILENAME).write_text(
                json.dumps(template), encoding="utf-8"
            )

            run_config_path = job.entrypoint.parent / RUN_CONFIG_FILENAME
            if run_config_path.is_file():
                run_config_text = run_config_path.read_text(encoding="utf-8")
                if job.run_config:
                    merged = json.loads(run_config_text)
                    merged.update(dict(job.run_config))
                    run_config_text = json.dumps(merged)
                bundle = _read_declared_code_bundle(
                    job.entrypoint.parent, run_config_text
                )
                _stage_run_config_cell(
                    staging_path / job.entrypoint.name,
                    run_config_text,
                )
                if bundle is not None:
                    staged = staging_path / job.entrypoint.name
                    notebook = json.loads(staged.read_text(encoding="utf-8"))
                    notebook["cells"].insert(0, _code_bundle_cell(bundle))
                    staged.write_text(json.dumps(notebook, indent=1), encoding="utf-8")

            self._push(staging_path, handle)

        return ADAPTER.Submission(id=ref, worker=job.worker)

    def _push(self, push_dir: Path, handle: CredentialHandle) -> dict:
        """Invoke `kaggle_driver.py submit <push_dir>` as a child process —
        `kernels push -p <push_dir>` retargeted onto the SDK driver, the
        one composition point `submit()`'s staging step funnels through so
        nothing here can drift from the caller's own error handling.

        Argv carries only a path (`push_dir`; small, credential-free); the
        credential still crosses only through `env`, unchanged. `push_dir`
        is `sys.argv[2]` from the driver's own perspective (`argv[0]` is
        this script's own path, `argv[1]` is `"submit"`) — see
        `kaggle_driver.py`'s `main()`.
        """
        argv = [sys.executable, str(self._driver_script), "submit", str(push_dir)]
        result = self._run(argv, env=self._env_for(handle))
        return self._parse_driver_result(result, action=f"submit for {push_dir}")

    @staticmethod
    def _parse_driver_result(
        result: subprocess.CompletedProcess, *, action: str
    ) -> dict:
        """Read the one JSON object `kaggle_driver.py` always prints on
        stdout, and decide whether to raise from its own `ok` field —
        never from the exit code alone, since the driver's own contract
        is to print a typed refusal object rather than a bare non-zero
        exit whenever it can (`main()`'s own `except` clauses all do
        this).
        """
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise KaggleAdapterError(
                f"{action} did not print JSON: {exc}; stderr: "
                f"{result.stderr.strip()}"
            ) from exc
        if result.returncode != 0 or not payload.get("ok", False):
            raise KaggleAdapterError(
                f"{action} refused: {payload.get('error', result.stderr.strip())}"
            )
        return payload

    def poll(self, submission_id: str) -> "ADAPTER.Status":
        """Ask the SDK driver for one kernel session's status
        (`kaggle_driver.py`'s own `cmd_poll`, which calls
        `get_kernel_session_status`) and translate it into the seam's own
        five-value vocabulary — never pass Kaggle's own text through as
        `state`. `kernels status` (the `kaggle` CLI's own Basic-auth path)
        is retired here exactly the way `_push()` already retired
        `kernels push`: same `_run()`/`_env_for()` boundary, same
        `shell=False`/list-argv/allowlisted-env discipline, only the
        child's own identity and the shape of its answer changed.

        The driver prints the bare `KernelWorkerStatus` member name
        (`response.status.name`, e.g. `"RUNNING"`) as JSON, never the old
        CLI's quoted-sentence shape — no extraction step is needed to pull
        a candidate token out of a line of prose anymore, only a
        lowercase and a table lookup. `failureMessage`, when the service
        supplies one, is appended to `detail` rather than silently
        dropped; `detail` never becomes anything but this driver's own
        reported facts.
        """
        worker = submission_id.split("/", 1)[0]
        handle = self._credential_for(worker)
        argv = [sys.executable, str(self._driver_script), "poll", submission_id]
        result = self._run(argv, env=self._env_for(handle))
        payload = self._parse_driver_result(result, action=f"poll for {submission_id}")
        raw_status = str(payload.get("status") or "")
        failure_message = payload.get("failureMessage")
        detail = raw_status if not failure_message else f"{raw_status}: {failure_message}"
        state = _KAGGLE_STATUS_TO_SEAM.get(raw_status.strip().lower(), "unknown")
        return ADAPTER.Status(state=state, detail=detail)

    def fetch(self, submission_id: str, into: Path) -> "ADAPTER.Fetched":
        """Materialize a kernel's output under `into`, via the SDK driver's
        own `cmd_fetch` (`kaggle_driver.py`) rather than `kernels output`
        (the `kaggle` CLI's own Basic-auth path, retired here the same way
        `poll()` retired `kernels status`). A non-zero exit is a refusal —
        this method never reports `complete=False` for a call that
        actually failed; `complete=False` is reserved for a backend that
        positively says "not finished yet", which neither the retired CLI
        nor this driver distinguishes from failure, so this adapter does
        not fabricate that distinction either.

        The driver writes files directly into `into` (a real filesystem
        path both processes share); this method still derives the
        returned file LIST by listing that directory afterward, never by
        trusting the driver's own JSON `files` field — the same
        discipline `kernels output`'s retired call already held, now
        applied to a different child.
        """
        worker = submission_id.split("/", 1)[0]
        handle = self._credential_for(worker)
        into.mkdir(parents=True, exist_ok=True)
        argv = [sys.executable, str(self._driver_script), "fetch", submission_id, str(into)]
        # The ONE call site in this module that does not run under the
        # control-plane budget. Everything else this adapter shells out to
        # asks the service a question; this one moves however many bytes
        # the remote job decided to produce.
        result = self._run(
            argv, env=self._env_for(handle), timeout=self._fetch_timeout
        )
        payload = self._parse_driver_result(result, action=f"fetch for {submission_id}")
        files = tuple(sorted(p.name for p in into.iterdir() if p.is_file()))
        # The driver reports the session's own status beside the files it
        # wrote, read BEFORE the output listing (`cmd_fetch`). Only a
        # `complete` session is a complete result: a failed or timed-out
        # run's output is downloaded all the same -- it may hold the only
        # checkpoint a later session can resume from -- but it is reported
        # `complete=False`, so the CLI never records it `returned`. A status
        # the driver could not read (`None`) is unknown, never complete. A
        # payload with no `status` key at all is a driver older than this
        # rule, and keeps that driver's behaviour: complete.
        complete = True
        if "status" in payload:
            raw_status = payload.get("status")
            state = (
                _KAGGLE_STATUS_TO_SEAM.get(raw_status.strip().lower(), "unknown")
                if isinstance(raw_status, str)
                else "unknown"
            )
            complete = state == "complete"
        return ADAPTER.Fetched(path=into, complete=complete, files=files)

    def cancel(self, submission_id: str) -> None:
        """Refuse, explicitly.

        Kaggle's own kernels CLI documents no single-kernel cancel
        operation; this method exists only to satisfy the ABC — the seam
        itself never calls `cancel()` on its own initiative (see
        `remote_cli.py`'s `reconcile` docstring: an `orphanRemote` id is
        reported, never cancelled). Raising here rather than guessing at
        an unofficial command is the same restraint every other refusal in
        this file already applies to a service response it cannot confirm.
        """
        raise KaggleAdapterError(
            f"cannot cancel {submission_id}: this backend's CLI has no "
            "documented single-kernel cancel operation, and this adapter "
            "will not guess at an unofficial one"
        )

    def list_active(self, worker: str) -> list[str]:
        """Refs this worker's account currently reports `queued` or
        `running`, rebuilt from `kaggle_driver.py`'s own `capacity` op
        (Decision 6) — `kernels list --mine --csv`, the `kaggle` CLI's own
        Basic-auth path, is retired here the same way `poll()`/`fetch()`
        already retired their own CLI calls; there is no `list_active`
        RPC on the installed SDK to call directly instead.

        A driver refusal that is specifically the distinct unauthorized
        exit becomes `ADAPTER.WorkerUnauthorized` here — never a generic
        `KaggleAdapterError` a caller would have to inspect a message to
        tell apart from any other failure. Every OTHER driver refusal
        (a structurally failed `list_kernels`, a timeout, an unreachable
        service) stays a generic `KaggleAdapterError` naming the remedy:
        retry, or let `packer.plan()`'s own ledger fallback answer instead.

        Only a ref confirmed `queued`/`running` counts as CONFIRMED active.
        `cmd_capacity` classifies each unresolved ref: `session_absent`
        (exact 404 — definitive, no session exists), `unaddressable_ref`
        (never asked), or `status_lookup_failed` (timeout/429/5xx — state
        genuinely UNKNOWN). The first two are real evidence of NOT in
        flight and are never counted. `status_lookup_failed` IS counted
        active: dropping it would undercount a possibly-running kernel and
        oversubscribe the worker, while counting it only delays a
        submission — the conservative direction.

        FAIL-CLOSED GUARD: raises only when NOTHING resolved and NO
        definitive evidence exists either (no confirmed kernel, no
        `session_absent`, no `unaddressable_ref`, at least one unknown). An
        account whose refs are all 404 is an ordinary idle account and
        returns `[]` — that IS evidence, never a missing read.
        """
        handle = self._credential_for(worker)
        argv = [sys.executable, str(self._driver_script), "capacity"]
        result = self._run(argv, env=self._env_for(handle))
        payload = self._parse_capacity_result(result, worker=worker)

        kernels = payload.get("kernels", [])
        unresolved = payload.get("unresolved", [])
        session_absent = [u for u in unresolved if u.get("reason") == "session_absent"]
        unaddressable = [u for u in unresolved if u.get("reason") == "unaddressable_ref"]
        unknown = [u for u in unresolved if u.get("reason") == "status_lookup_failed"]

        if not kernels and not session_absent and not unaddressable and unknown:
            raise KaggleAdapterError(
                f"capacity check for {worker!r} enumerated {len(unknown)} "
                "kernel ref(s) but resolved the state of none of them (every "
                "per-ref status lookup failed with no definitive answer) — "
                "this is not evidence of an idle account, and packer.plan()'s "
                "own ledger fold should answer instead of a live count built "
                "from zero confirmed refs"
            )

        active: list[str] = []
        for kernel in kernels:
            ref = kernel.get("ref")
            if not ref:
                continue
            raw_status = str(kernel.get("status") or "")
            state = _KAGGLE_STATUS_TO_SEAM.get(raw_status.strip().lower(), "unknown")
            if state in ("queued", "running"):
                active.append(ref)
        active.extend(u["ref"] for u in unknown if u.get("ref"))
        return active

    @staticmethod
    def _parse_capacity_result(
        result: subprocess.CompletedProcess, *, worker: str
    ) -> dict:
        """`_parse_driver_result`'s own sibling, for the `capacity` op
        alone: the one driver call whose refusal must distinguish
        "credential refused" (`ADAPTER.WorkerUnauthorized`, the fact
        `packer.select()` needs to skip an unhealthy worker rather than
        count it healthy) from every other failure shape. `submit()`,
        `poll()` and `fetch()` keep `_parse_driver_result`'s own generic
        refusal unchanged — widening THEIR contract the same way is no
        part of this task, and would change already-passing behavior no
        design decision here asks for.

        The `"(list_kernels failed structurally)"` text below describes
        exactly one fact: the DRIVER's own exit says the enumeration
        itself did not complete (a non-zero exit, or a printed `ok` that
        is not `True`). Since `kaggle_driver.py::cmd_capacity` now catches
        every per-ref failure internally and still exits 0 with `ok: True`
        whenever `list_kernels` itself succeeded, a payload that reaches
        this point with `result.returncode == 0` and `payload["ok"] is
        True` is, by construction, a successful enumeration — even when
        its own `unresolved` list is non-empty. This function never
        inspects `unresolved` and never raises over it; that list is
        `list_active()`'s concern (see its own docstring for the
        fail-closed guard that DOES read it), not a reason to misattribute
        a downstream per-ref gap to the enumeration that produced it.
        """
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise KaggleAdapterError(
                f"capacity check for {worker!r} did not print JSON: {exc}; "
                f"stderr: {result.stderr.strip()}"
            ) from exc

        if result.returncode == _DRIVER_EXIT_UNAUTHORIZED:
            raise ADAPTER.WorkerUnauthorized(
                f"worker {worker!r}'s credential was refused while checking "
                "capacity; the remedy is re-materializing that account's "
                "token through the accounts skill's own command"
            )

        if result.returncode != 0 or not payload.get("ok", False):
            raise KaggleAdapterError(
                f"capacity check for {worker!r} could not obtain live "
                "capacity evidence (list_kernels failed structurally): "
                f"{payload.get('error', result.stderr.strip())}; retry, or "
                "let packer.plan()'s own ledger fold answer instead"
            )

        return payload


def _run_accounts_cli_for_declared_capacity(
    argv: list[str],
) -> subprocess.CompletedProcess:
    """A bare `subprocess.run`, no instance, no credential, no environment
    override -- this reporter never authenticates as anyone and reads
    nothing but what THIS process's own environment already carries,
    because a launch proposal is composed before any worker or credential
    has been chosen for it.
    """
    return subprocess.run(
        argv, shell=False, capture_output=True, text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )


def _declared_capacity() -> tuple[int, int] | None:
    """`ADAPTER.register_declared_capacity("kaggle", ...)`'s own reporter
    (see that registry's own module-level comment for the contract every
    reporter registered there must keep): every account name on disk
    right now, read through the identical subprocess `workers()` itself
    calls, multiplied by this service's own pinned per-account allowance.

    A subprocess that exits non-zero, or one whose stdout is not JSON, is
    read here as "no capacity figure can be declared right now" -- caught
    and turned into `None` rather than left to propagate, because the one
    caller of this function (a launch proposal's own publisher) needs to
    leave that whole action out of what it publishes, not crash publishing
    every other action alongside it over a subprocess this reporter does
    not control.
    """
    try:
        names = _account_names_on_disk(
            DEFAULT_ACCOUNTS_CLI, _run_accounts_cli_for_declared_capacity)
    except (KaggleAdapterError, subprocess.TimeoutExpired, OSError):
        return None
    # Under the team model only owner-mapped accounts are workers, so only
    # they count; a registry this process cannot read declares nothing.
    try:
        team = load_kaggle_team(DEFAULT_TEAM_REGISTRY)
    except KaggleAdapterError:
        return None
    if team is not None:
        names = list(_team_report(names, team).workers)
    return (len(names), KAGGLE_WORKER_CAPACITY)


ADAPTER.register("kaggle", KaggleAdapter)
ADAPTER.register_metadata("kaggle", assemble_metadata)
ADAPTER.register_default_accelerator("kaggle", _default_accelerator)
ADAPTER.register_declared_capacity("kaggle", _declared_capacity)
