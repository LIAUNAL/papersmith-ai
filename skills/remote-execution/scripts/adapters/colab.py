#!/usr/bin/env python3
"""The Colab backend adapter — this file's own service is named here and
nowhere above the seam.

Every module above `adapter.py` (`ledger.py`, `packer.py`, `remote_cli.py`)
stays deliberately blind to what backend, if any, is behind a given worker.
This module is where that blindness ends: it is the one place permitted to
say "Colab", to spawn the one child that speaks to it, and to know that
service's own vocabulary well enough to translate it into the seam's.

Structural guarantees, held by what this file's own dependency graph can
even reach — never by convention:

1. This module imports `hashlib`, `json`, `os`, `re`, `subprocess`, `sys`,
   `tempfile` and `pathlib` — nothing else. It names no packaged SDK, and
   the one thing it shells out to is the official `colab` command line
   (`google-colab-cli`), which is the service's own headless client.

   2. Colab authentication is the CLI's own business, read by the CLI's own
    child process: it resolves `~/.config/colab-cli/token.json` from the
    `HOME` this adapter forwards, and this module never opens that file,
    never learns a path to it, and never sees a token value. There is no
    `credentials` parameter on this adapter and no `CREDENTIAL_CLI` class
    attribute, so `remote_cli._construct_adapter()` never hands it a
    credential provider at all.

   The CLI's own session STATE file (`~/.config/colab-cli/sessions.json`)
    is credential-grade too, and for a measured reason: it carries a live
    per-session access token beside the session record (spike S0). Nothing
    here reads it, copies it or prints it — every session fact this module
    uses comes from the CLI's own stdout, and the only environment this
    module ever forwards is `PATH` and `HOME`.

   The repo-credential route (S3) does not change any of that: the
   operator's token file arrives as `repo_credential_path`, and its bytes
   are read at exactly ONE expression in this module — `submit()`'s
   staging, below — then written into a per-call temp directory and
   uploaded as `git-askpass-token` (0o600, stripped, no trailing
   newline). The path is what `remote_cli` threads; the bytes never touch
   argv, `run-config.json`, the job folder, the ledger or any log.

   Under the TEAM model (one worker per team owner, below) the same two
   names are forwarded and nothing else — only the VALUE of `HOME`
   changes: a team worker's child runs with `HOME=<configDir>`, the
   owner's own state directory from `<workspace>/.papersmith/team.json`.
   That is load-bearing, measured in the CLI's own source (0.6.0 and
   0.7.5 alike): the OAuth token path is
   `os.path.expanduser("~/.config/colab-cli/token.json")`, fixed at import
   from `HOME`, and the global `--config PATH` flag names the session
   state FILE (`sessions.json`) only — it never moves the token. So the
   child's `HOME` is what keeps one owner's credential apart from
   another's, and `--config <configDir>/.config/colab-cli/sessions.json`
   is passed besides, on every argv, so the state file a worker uses is
   stated rather than inferred. This module reads exactly three fields of
   the registry (`owner`, `accounts.colab.tier`,
   `accounts.colab.configDir`), stats the directory itself (exists, mode
   0700), and never opens, lists or copies anything inside it.

3. Every subprocess call is `shell=False` with a list argv, an explicit
   timeout, and that same two-variable environment. A non-zero exit, an
   expired timeout, or output this module cannot honestly read is a
   refusal — `ColabAdapterError`, never a fabricated `Status`, `Submission`
   or `Fetched` the service never confirmed.

Slice status, stated so a refusal is never a mystery: this file owns the
S1 surface (registration, the static worker, `list_active()`, `cancel()`),
the S2 session lifecycle (`submit()`, `poll()`, `fetch()` — uploads,
the detached launch, the `/content/.psmith/<session>/` sentinel protocol,
downloads, release), the S3 repo-credential route
(`REPO_CREDENTIAL_CARRIER`, the `repo_credential_path` constructor
parameter, the staged askpass material), and the D13 accelerator mapping
(`COLAB_ACCELERATOR_VARIANTS`: a declared `sm_*` architecture becomes the
matching `--gpu` variant on `new`, and anything the table cannot map
refuses by name rather than silently running on CPU).

Measured against `google-colab-cli` 0.6.0, live (spike S0; evidence in
`proposals/colab-cli-spike/findings.md`):
    [name] m-... | Hardware: CPU | Variant: DEFAULT          (sessions)
    [psmith-s0] m-... | Hardware: CPU | Variant: DEFAULT | Status: IDLE
    [colab] Session 'x' not found.                            (stop, exit 0)
    [colab] Creating session 'x'... / [colab] Session READY.  (new, exit 0)
Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath


def _load_adapter_seam():
    """Path-import `adapter.py`, one directory up from this file, reusing
    an already-loaded copy under `remote_execution_adapter` when one
    exists.

    Same `sys.modules`-reuse technique `kaggle.py` uses, and the same
    correctness reason: a second, separately exec'd copy of `adapter.py`
    would define a second, distinct `Adapter` class with the same name,
    and `isinstance(colab_adapter, ADAPTER.Adapter)` checks made by a
    caller holding the first copy would silently fail against an instance
    built from the second.
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


class ColabAdapterError(ADAPTER.AdapterError):
    """A refusal: the service CLI failed, timed out, or answered with
    something this adapter will not guess at.

    Never raised to report a guess — only to report that this adapter
    declined to fabricate an answer the service never actually confirmed.
    """


class ColabTransportError(ColabAdapterError):
    """The RETRYABLE half of this adapter's refusals: the request died in
    flight (an expired subprocess timeout, or the CLI's own
    `Connection was lost.` transport message) rather than the service
    answering with a state.

    Only idempotent READS are retried on this class, once (S0 obligation
    4: `exec` can hang after `Connection was lost`, and retry-once is
    justified for reads alone). A launch is never retried — a second
    launch could spawn a second executor — and neither is `new`, an
    upload, an install or a stop.
    """


# The one worker this backend exposes: the operator's own Colab account.
WORKER_ID = "colab"

# The concurrent-job figure this backend claims, and the honest reason it
# is 1 rather than a discovered number: this adapter serializes its work
# on purpose (one named session per submission, one submission in flight
# per account), and the CLI reports no concurrency allowance to read.
# Revise only alongside a measured reason.
COLAB_WORKER_CAPACITY = 1

# The TEAM registry: one Colab account per person, each owned and operated
# by a distinct team member. Git-ignored, no secrets, written by the
# operator's own tooling (`smith team`); this module only reads it. Its
# default location is the workspace root this file ships inside
# (`<workspace>/skills/remote-execution/scripts/adapters/colab.py`), read
# at call time so a caller (or a test) can point it elsewhere.
TEAM_REGISTRY_RELATIVE = Path(".papersmith") / "team.json"
DEFAULT_TEAM_REGISTRY = Path(__file__).resolve().parents[4] / TEAM_REGISTRY_RELATIVE
TEAM_REGISTRY_SCHEMA = 1

# A team worker's id: this prefix plus the owner slug. Parallelism across
# accounts counts DISTINCT OWNERS, and the id makes that structural — an
# owner appears once in the registry, so it appears once here.
TEAM_WORKER_PREFIX = "colab:"
_OWNER_RE = re.compile(r"^[a-z0-9-]{1,40}$")

# The tiers a registry entry may declare, and the ones admitted to a split
# campaign. A `free` account may run one interactive or proof-of-concept
# session; it is never a worker of a split campaign.
COLAB_TIERS = ("free", "pro", "payg", "enterprise")
COLAB_CAMPAIGN_TIERS = frozenset({"pro", "payg", "enterprise"})

# The rule the free-tier refusal cites, quoted from the service's own FAQ
# (verified 2026-10-25): disallowed on managed runtimes running free of
# charge without a positive compute-unit balance.
COLAB_FAQ_URL = "https://research.google.com/colaboratory/faq.html"
COLAB_FAQ_FREE_RULE = "running distributed computing workers"

def restore_notebook_json(path: Path) -> None:
    """Rewrite a downloaded notebook the service CLI handed back as a dict repr.

    google-colab-cli 0.6.0 asks the Jupyter contents API for the file and,
    for a notebook (served as `format: json`, a dict), writes `str(content)`:
    a Python repr, not JSON, that no notebook reader opens. `literal_eval`
    accepts literals only, so the remote bytes are never executed; a file
    that is already JSON, or is not a dict literal, is left exactly as is.
    """
    text = path.read_text(encoding="utf-8")
    try:
        json.loads(text)
        return
    except ValueError:
        pass
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return
    if isinstance(value, dict):
        path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# Where the CLI keeps its session state under a given HOME — the value
# passed to the CLI's own global `--config` flag for a team worker. It is
# the CLI's default path re-rooted at the owner's directory, so the flag
# states the file rather than changing it.
CLI_SESSIONS_FILE_RELATIVE = Path(".config") / "colab-cli" / "sessions.json"

# Every session this adapter creates carries this name prefix. The CLI
# lists the ACCOUNT's sessions, not this skill's — `list_active()` claims
# only the prefixed ones, so a session some other tooling created can
# never be reported as a submission this adapter issued.
SESSION_NAME_PREFIX = "psmith-"

# The job-folder slug's own cap, chosen against the measured accepted
# name length (a 56-character name was accepted live; this construction's
# own maximum is 6 + 40 + 1 + 8 = 55).
SESSION_SLUG_MAX_CHARS = 40
SESSION_NAME_MAX_CHARS = 55

# The VM-side root every session's directory lives under, from the parent
# plan's protocol §4. A constructor parameter (below) rather than a bare
# literal, because it is the VM's mount root and the offline suite
# executes the REAL rendered templates against a temp directory standing
# in for it — no path literal here is test-only, and the production
# default is exactly the plan's.
DEFAULT_REMOTE_ROOT = "/content/.psmith"

# The token the two RENDERED asset templates carry in place of their
# session directory (`assets/colab/launch.py`, `read_state.py`), and the
# inline mkdir source below. `exec -f` has no argument channel, so the
# directory is substituted into the source before the file is executed.
SESSION_DIR_TOKEN = "__SESSION_DIR__"

# Timeout classes (parent plan D7), each its own named number:
#   control   — `sessions`, `status`, `stop`: small requests whose answer
#               the service produces immediately; failing fast is right.
#   new       — provisioning a machine, measured at ~14 s live.
#   transfer  — per-file upload/download, sized for real artifacts.
#   install   — `colab install`: its own operation class, same magnitude
#               as a transfer because it moves packages and runs pip.
#   kernel    — the `--timeout` every in-kernel helper execution passes to
#               `exec`, and the subprocess timeout is that plus slack.
COLAB_CONTROL_TIMEOUT_SECONDS = 120.0
COLAB_NEW_TIMEOUT_SECONDS = 300.0
COLAB_TRANSFER_TIMEOUT_SECONDS = 1800.0
COLAB_INSTALL_TIMEOUT_SECONDS = 1800.0
COLAB_KERNEL_TIMEOUT_SECONDS = 600.0
COLAB_SUBPROCESS_SLACK_SECONDS = 30.0

# The three distributions `executor.py` needs on the VM (measured present
# live; the probe exists for the machines where they are not).
PROBE_PACKAGES = ("nbclient", "nbformat", "jupyter_client")

# D13's declared-architecture → GPU-variant table: the `sm_*` names this
# project's dual-architecture torch builds declare, mapped to the variant
# names `colab new --gpu` accepts (all three are in the captured
# `help-new.log` surface, S0 fact 4). A declared architecture outside this
# table refuses by name — never a fallback to CPU — and TPU kinds are
# refused outright, because no `--tpu` mapping is invented here. This table
# only decides which machine arrives; the VM-side `check_accelerator()`
# remains the authority on whether that machine can run the build.
COLAB_ACCELERATOR_VARIANTS = {"sm_75": "T4", "sm_80": "A100", "sm_90": "H100"}

# The accelerator a job generated with no `--accelerator-*` flags declares,
# registered below exactly as `adapters/kaggle.py` registers its own. Without
# it a from-zero Colab job carried no `accelerator` block, `colab new` got no
# `--gpu`, and the run landed on a CPU runtime without a word. One
# architecture, for the reason Kaggle's comment gives: the VM-side gate reads
# a declaration as "the installed build must cover every architecture named
# here". `sm_75` (T4) because every tier, free included, can be handed one;
# a job that wants an A100 or H100 says so with the override flags.
COLAB_ACCELERATOR_KIND = "cuda"
COLAB_ACCELERATOR_ARCHITECTURES = ("sm_75",)

# The continuous run time one Colab Pro session may last: 24 hours, for
# every accelerator. This is the service's PUBLISHED limit at the time of
# writing (2026-10), not a measurement -- re-check it against Colab's own
# documentation before planning around it. It is an upper bound, not a promise:
# the service also reclaims a session it judges idle well before it, and a
# free-tier session is shorter still (campaigns refuse the free tier
# anyway, `TeamAccount.campaign_refusal`). A reclaimed VM takes its disk
# with it, which is why the executor keeps a running manifest and why
# `fetch` keeps every snapshot it has already brought back.
COLAB_PRO_SESSION_LIMIT_SECONDS = 24 * 3600


def _default_accelerator() -> tuple[str, tuple[str, ...]]:
    """`ADAPTER.register_default_accelerator("colab", ...)`'s provider: called
    by `jobfolder.generate_job()` only when the caller declared neither half
    of the accelerator pair, so a Colab job asks for a GPU by default."""
    return COLAB_ACCELERATOR_KIND, COLAB_ACCELERATOR_ARCHITECTURES

# The two job-folder names this adapter knows: `run-config.json` beside
# the entrypoint is what makes a submission shaped like this backend's
# protocol at all, and `runner.ipynb` is the entrypoint's own fixed name
# (jobfolder.py's constants, duplicated here the way kaggle.py duplicates
# its own — this module may not import jobfolder).
RUN_CONFIG_FILENAME = "run-config.json"
RUNNER_FILENAME = "runner.ipynb"

# The rendered/uploaded assets under `assets/colab/`.
LAUNCH_ASSET = "launch.py"
EXECUTOR_ASSET = "executor.py"
READ_STATE_ASSET = "read_state.py"

# The credential material a credentialed submission stages beside the
# executor (S3): an askpass script (uploaded verbatim; the executor makes
# it executable) and the token file it prints. The names are declared in
# THREE files by convention — this one (the uploader and the fetch-time
# refusal), `assets/colab/executor.py` (chmod, deletion, manifest
# exclusion) and `assets/runner_bootstrap.py` (the clone's own use and
# deletion) — deliberately not shared by import, for the same reason no
# module above the seam may name a backend.
REPO_CREDENTIAL_ASKPASS_FILENAME = "git-askpass.sh"
REPO_CREDENTIAL_TOKEN_FILENAME = "git-askpass-token"

# The two names `fetch()` refuses to download: the executor deletes this
# material after the run and excludes it from its manifest, so a manifest
# naming either one at the top level is a manifest this protocol never
# produces.
CREDENTIAL_MATERIAL_FILENAMES = frozenset(
    {REPO_CREDENTIAL_ASKPASS_FILENAME, REPO_CREDENTIAL_TOKEN_FILENAME}
)

# The askpass script uploaded as `git-askpass.sh`: prints the staged token
# file's bytes for whichever prompt git asks. HTTPS token auth on the
# hosts this skill targets accepts the token as the username with any
# password, so one answer serves both prompts (recorded in the slice
# plan's §4, and verified live only at S5's credential differential —
# until then this is a unit-asserted convention, never an assumption
# dressed as a measurement).
REPO_CREDENTIAL_ASKPASS_SOURCE = """#!/bin/sh
# Prints the staged repo credential for both prompts git may ask. HTTPS
# token auth on the hosts this skill targets accepts the token as the
# username with any password, so one answer serves both prompts.
cat "$(dirname "$0")/git-askpass-token"
"""

# The tokens a hand-typed launch would carry without ever routing through
# `remote_cli.py submit`. Read by `hooks/refuse_offpath_push.py`; a second
# service is covered by declaring its own tuple beside its own adapter,
# never by editing the hook. Deliberately absent: `sessions`, `status`,
# `ls` and `stop` are reads or cleanup, not launches.
PUSH_SURFACE: tuple[str, ...] = ("colab new", "colab exec", "colab run", "colab upload")

# The sessions listing's own line shape, measured in spike S0:
#     [name] m-... | Hardware: X | Variant: Y
# A machine whose name the CLI can no longer resolve is rendered `[?]`;
# it is deliberately NOT converted into a submission id below — there is
# no name to address it by.
_SESSION_LINE_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s+(?P<endpoint>\S+)\s*\|")

# The names a session may carry: lowercase alphanumerics and hyphens,
# starting with an alphanumeric. This module GENERATES exactly this shape
# (`SESSION_NAME_PREFIX` + slug + digest), so a submission id that does
# not match cannot have come from here — and the name is substituted into
# rendered sources, so accepting an arbitrary string from argv would be
# accepting an injection into a file executed on the VM. Refused at the
# boundary, before any substitution (ledger S2-J7).
_SESSION_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# The inline helper sources: rendered per submission into the temp dir,
# exactly like the two asset templates, and for the same reason — they
# must know their session directory and `exec -f` cannot tell them.
_MKDIR_SOURCE = '''\
"""Create the session's remote directory (rendered per submission)."""
import json
from pathlib import Path

SESSION_DIR = Path("__SESSION_DIR__")


def main() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"created": str(SESSION_DIR), "exists": SESSION_DIR.is_dir()}))


if __name__ == "__main__":
    main()
'''

_PROBE_SOURCE = '''\
"""Report the executor's three dependencies without importing them
(rendered per submission; an import would be the failure it reports)."""
import json
from importlib import metadata

PACKAGES = ("nbclient", "nbformat", "jupyter_client")


def main() -> None:
    found = {}
    for package in PACKAGES:
        try:
            found[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            found[package] = None
    print(json.dumps(found))


if __name__ == "__main__":
    main()
'''


def _slugify(text: str) -> str:
    """A deterministic slug from raw text — never a lookup, never state
    kept anywhere in this process. Used on the job folder's own name
    (`entrypoint.parent.name`), which is the one fact that separates two
    generated job folders before their bytes are hashed.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:SESSION_SLUG_MAX_CHARS] or "job"


def _mode_token(run_config) -> str:
    """The submit-time mode, as it enters the session name's digest.
    `run_config` is the in-memory job's opaque mapping; `--smoke` is the
    one mode `cmd_submit` ever sets (`"smoke"`), everything else is a
    full run. The mode is NOT persisted in `run-config.json`, which is
    exactly why it must be hashed here: a rehearsal and a full run of the
    same job folder are different submissions and must never collide on
    one session name.
    """
    return "smoke" if run_config.get("mode") == "smoke" else "full"


def _digest8(entrypoint_bytes: bytes, commit: str, mode: str) -> str:
    """The submission digest: `sha256(entrypoint bytes NUL commit NUL
    mode)[:8]`. The NUL separators are this construction's own
    disambiguation of the parent plan's "entrypoint bytes + commit +
    mode" prose — recorded as a refinement in the slice plan (SD1) — so
    two different triples can never hash the same concatenated byte
    string.
    """
    joined = b"\0".join((entrypoint_bytes, commit.encode("utf-8"), mode.encode("utf-8")))
    return hashlib.sha256(joined).hexdigest()[:8]


def _escape_source_literal(text: str) -> str:
    """Escape a value for inclusion inside a double-quoted Python literal
    in a rendered source file. The session directory is composed of this
    module's own validated parts (prefixed name, VM root), so this is
    belt-and-braces rather than the load-bearing check — the load-bearing
    check is `_SESSION_NAME_RE` at the boundary.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _append_note(exc: BaseException, note: str) -> None:
    """Append a cleanup note to a refusal about to be re-raised, without
    changing its type and without ever swallowing it: the caller sees the
    original failure AND the fact that cleanup also failed.
    """
    if exc.args and isinstance(exc.args[0], str):
        exc.args = (f"{exc.args[0]} [{note}]", *exc.args[1:])
    else:
        exc.args = (*exc.args, note)


class TeamAccount:
    """One owner's Colab account, as the team registry declares it: the
    owner slug, the declared tier, and the owner's state directory. The
    directory is a PATH this module hands to the child as `HOME` — never a
    place this module reads from."""

    __slots__ = ("owner", "tier", "config_dir")

    def __init__(self, owner: str, tier: str, config_dir: Path) -> None:
        self.owner = owner
        self.tier = tier
        self.config_dir = config_dir

    @property
    def worker_id(self) -> str:
        return f"{TEAM_WORKER_PREFIX}{self.owner}"

    @property
    def sessions_file(self) -> Path:
        return self.config_dir / CLI_SESSIONS_FILE_RELATIVE

    def campaign_refusal(self) -> str | None:
        """Why this account may not take part in a split campaign, or
        `None` when its tier admits it."""
        if self.tier in COLAB_CAMPAIGN_TIERS:
            return None
        return (
            f"worker {self.worker_id!r} (owner {self.owner!r}) is declared "
            f"tier {self.tier!r}: a free account may run one interactive or "
            "proof-of-concept session, but it is never a worker of a split "
            "campaign — the Colab FAQ disallows, on free runtimes without a "
            f"positive compute-unit balance, \"{COLAB_FAQ_FREE_RULE}\" "
            f"({COLAB_FAQ_URL}). Run this campaign on owners whose tier is "
            f"one of {sorted(COLAB_CAMPAIGN_TIERS)}, or send this unit alone "
            "as a single submission"
        )


def load_colab_team(path: str | Path) -> tuple[TeamAccount, ...] | None:
    """The Colab accounts the team registry at `path` declares, or `None`
    when no registry exists there (the single-worker behaviour, unchanged).

    Reads exactly three fields per member — `owner`, `accounts.colab.tier`,
    `accounts.colab.configDir` — and ignores everything else (display name,
    attestation, other services). A member with no Colab account is not a
    worker here. Fail-closed on every shape it cannot honestly read: a
    registry that exists but is not schema 1, an owner slug outside
    `[a-z0-9-]{1,40}` or repeated, an unknown tier, a `configDir` that is
    not an absolute path, or the SAME directory under two owners (one
    account per person: two owners sharing one state directory would be
    one account wearing two names). Directory identity is compared after
    normalization and symlink resolution of the directory path itself;
    nothing inside it is opened.
    """
    registry = Path(path)
    try:
        text = registry.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ColabAdapterError(f"cannot read the team registry {registry}: {exc}") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ColabAdapterError(
            f"the team registry {registry} is not JSON ({exc}); refusing to "
            "guess which accounts it declares"
        ) from exc
    if not isinstance(document, dict) or document.get("schema") != TEAM_REGISTRY_SCHEMA:
        raise ColabAdapterError(
            f"the team registry {registry} is not a schema-{TEAM_REGISTRY_SCHEMA} "
            "object; refusing to guess which accounts it declares"
        )
    members = document.get("members")
    if not isinstance(members, list):
        raise ColabAdapterError(f"the team registry {registry} carries no 'members' list")

    accounts: list[TeamAccount] = []
    owners_seen: set[str] = set()
    owner_by_dir: dict[str, str] = {}
    for index, member in enumerate(members):
        if not isinstance(member, dict):
            raise ColabAdapterError(f"{registry}: member #{index} is not an object")
        owner = member.get("owner")
        if not isinstance(owner, str) or _OWNER_RE.match(owner) is None:
            raise ColabAdapterError(
                f"{registry}: member #{index} owner {owner!r} is not a slug "
                "of 1-40 characters in [a-z0-9-]"
            )
        if owner in owners_seen:
            raise ColabAdapterError(
                f"{registry}: owner {owner!r} appears more than once; an owner "
                "is one person and is listed once"
            )
        owners_seen.add(owner)
        services = member.get("accounts")
        colab = services.get("colab") if isinstance(services, dict) else None
        if colab is None:
            continue
        if not isinstance(colab, dict):
            raise ColabAdapterError(f"{registry}: owner {owner!r} accounts.colab is not an object")
        tier = colab.get("tier")
        if tier not in COLAB_TIERS:
            raise ColabAdapterError(
                f"{registry}: owner {owner!r} declares Colab tier {tier!r}; "
                f"expected one of {list(COLAB_TIERS)}"
            )
        config_dir = colab.get("configDir")
        if (
            not isinstance(config_dir, str)
            or "\0" in config_dir
            or not os.path.isabs(config_dir)
        ):
            raise ColabAdapterError(
                f"{registry}: owner {owner!r} declares configDir {config_dir!r}; "
                "an absolute directory path is required"
            )
        identity = os.path.normcase(os.path.realpath(config_dir))
        if identity in owner_by_dir:
            raise ColabAdapterError(
                f"{registry}: owners {owner_by_dir[identity]!r} and {owner!r} "
                f"declare the same Colab configDir ({config_dir}); each owner "
                "operates exactly one account of their own, with their own "
                "state directory"
            )
        owner_by_dir[identity] = owner
        accounts.append(TeamAccount(owner, tier, Path(os.path.normpath(config_dir))))
    return tuple(accounts)


class ColabAdapter(ADAPTER.Adapter):
    """The official `colab` CLI, behind the seam's six operations."""

    # Read off the CLASS by `remote_cli` exactly the way it reads
    # `CREDENTIAL_CLI` — an ordinary class attribute, never one of the
    # ABC's six operations, so this module still never has to be named by
    # anything above the seam. A backend that can stage a runner-side repo
    # credential declares it; a backend that cannot declares nothing, and
    # `--repo-credential` refuses there rather than authenticating a probe
    # whose runner still could not clone (S3/D6).
    REPO_CREDENTIAL_CARRIER = True

    @classmethod
    def session_limit_seconds(cls, machine_shape: str | None = None) -> int | None:
        """`COLAB_PRO_SESSION_LIMIT_SECONDS`, whatever the accelerator."""
        return COLAB_PRO_SESSION_LIMIT_SECONDS

    def __init__(
        self,
        *,
        colab_executable: str = "colab",
        timeout: float = COLAB_CONTROL_TIMEOUT_SECONDS,
        new_timeout: float = COLAB_NEW_TIMEOUT_SECONDS,
        transfer_timeout: float = COLAB_TRANSFER_TIMEOUT_SECONDS,
        install_timeout: float = COLAB_INSTALL_TIMEOUT_SECONDS,
        kernel_timeout: float = COLAB_KERNEL_TIMEOUT_SECONDS,
        subprocess_slack: float = COLAB_SUBPROCESS_SLACK_SECONDS,
        remote_root: str = DEFAULT_REMOTE_ROOT,
        assets_dir: Path | None = None,
        repo_credential_path: str | Path | None = None,
        team_registry: str | Path | None = None,
    ) -> None:
        self._colab_executable = colab_executable
        # The registry's PATH; read lazily (and once) by `_team()`, so a
        # constructor never fails over a file no operation has needed yet.
        # `None` means the module default, resolved at read time.
        self._team_registry = Path(team_registry) if team_registry is not None else None
        self._team_cache: tuple[TeamAccount, ...] | None = None
        self._team_loaded = False
        self._control_timeout = timeout
        self._new_timeout = new_timeout
        self._transfer_timeout = transfer_timeout
        self._install_timeout = install_timeout
        self._kernel_timeout = kernel_timeout
        self._subprocess_slack = subprocess_slack
        self._remote_root = remote_root.rstrip("/")
        self._assets_dir = (
            Path(assets_dir)
            if assets_dir is not None
            else Path(__file__).resolve().parents[2] / "assets" / "colab"
        )
        # The PATH, never the bytes: the token itself is read at the one
        # staging expression in `submit()`, and a `None` here (every
        # credentialless caller) makes the whole route inert.
        self._repo_credential_path = (
            Path(repo_credential_path) if repo_credential_path is not None else None
        )

    # -- the repo credential (S3) ------------------------------------------

    def _read_repo_credential(self) -> str:
        """The ONE expression in this module that reads the credential
        bytes (D6's two-site rule: here and `jobfolder`'s probe env
        builder, nothing else skill-wide).

        `.strip()` because a trailing newline in a token file is an
        editing artifact, and an unreadable-or-empty value refuses HERE,
        naming the path — an empty credential would be uploaded as a
        token that is nothing but whitespace, a configuration accident
        this method must not launder into a VM-side clone failure after
        quota is spent.
        """
        path = self._repo_credential_path
        assert path is not None, "_read_repo_credential called with no path"
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ColabAdapterError(
                f"the repository credential at {path} could not be read: {exc}"
            ) from exc
        if not value:
            raise ColabAdapterError(
                f"the repository credential at {path} is empty after "
                "stripping whitespace; refusing to stage an empty credential "
                "(git would present it as the token)"
            )
        return value

    # -- the team (one worker per owner) -----------------------------------

    def _team(self) -> tuple[TeamAccount, ...] | None:
        """The registry's Colab accounts, or `None` for the single-worker
        mode (no registry, or a registry declaring no Colab account — the
        operator's own account then stays the one worker, exactly as
        before the team model existed)."""
        if not self._team_loaded:
            path = self._team_registry if self._team_registry is not None else DEFAULT_TEAM_REGISTRY
            team = load_colab_team(path)
            self._team_cache = team if team else None
            self._team_loaded = True
        return self._team_cache

    def _account_for(self, worker: str | None, *, allow_legacy: bool) -> TeamAccount | None:
        """The team account a worker id names, or `None` for the legacy
        single worker. In team mode the legacy id is admitted only where
        `allow_legacy` says so (reads and cleanup of sessions issued before
        the registry existed — never a new submission, which would spend
        an account the registry does not list)."""
        team = self._team()
        if team is None:
            if worker is None or worker == WORKER_ID:
                return None
            raise ColabAdapterError(
                f"worker {worker!r} is not this adapter's: with no team registry "
                f"the only Colab worker is {WORKER_ID!r}"
            )
        if worker is None or worker == WORKER_ID:
            if allow_legacy:
                return None
            raise ColabAdapterError(
                f"worker {worker!r} names the single operator account, but a team "
                "registry is in force: submit to one owner's worker "
                f"({', '.join(account.worker_id for account in team)})"
            )
        for account in team:
            if account.worker_id == worker:
                return account
        raise ColabAdapterError(
            f"worker {worker!r} is not declared in the team registry; declared: "
            f"{', '.join(account.worker_id for account in team)}"
        )

    def campaign_refusal(self, worker: str) -> str | None:
        """Why `worker` may not take part in a split campaign, or `None`
        when it may. Not one of the seam's six operations: an ordinary
        method a campaign planner can ask before placing units, answered
        from the registry alone (no subprocess, no network)."""
        account = self._account_for(worker, allow_legacy=True)
        return None if account is None else account.campaign_refusal()

    def _cli(self, account: TeamAccount | None) -> list[str]:
        """The argv prefix for one worker's child: the executable, plus —
        for a team worker — the CLI's own global `--config` naming that
        owner's session state file."""
        if account is None:
            return [self._colab_executable]
        return [self._colab_executable, "--config", str(account.sessions_file)]

    # -- the subprocess boundary ------------------------------------------

    def _env_for(self, account: TeamAccount | None = None) -> dict[str, str]:
        """The child's WHOLE environment, from a two-name allowlist:
        `PATH` and `HOME`. Nothing else is ever forwarded.

        `HOME` is load-bearing, not convenience: the CLI authenticates
        ITSELF out of `~/.config/colab-cli/token.json`, and it resolves
        that directory from the child's own `HOME`. This adapter never
        touches that file or its contents — the child is the only party
        that does. A process with no `HOME` is refused here rather than
        passed a child that would fail authentication for a reason no
        caller could read.

        For a team worker the same two names are forwarded, and `HOME` is
        the owner's `configDir` — the one route by which that owner's own
        token file is the one the child resolves. The directory itself is
        stat'ed (it must exist and be mode 0700, since what the CLI keeps
        in it is credential-grade) and nothing inside it is touched; a
        missing directory refuses naming the owner's one-time login.
        """
        if account is not None:
            directory = account.config_dir
            login = (
                f"HOME={directory} {self._colab_executable} --config "
                f"{account.sessions_file} sessions"
            )
            try:
                mode = directory.stat().st_mode
            except FileNotFoundError:
                raise ColabAdapterError(
                    f"owner {account.owner!r}'s Colab configDir {directory} does "
                    f"not exist; create it (mode 0700) and have that owner sign "
                    f"in once with: {login}"
                ) from None
            except OSError as exc:
                raise ColabAdapterError(
                    f"cannot stat owner {account.owner!r}'s Colab configDir "
                    f"{directory}: {exc}"
                ) from exc
            if not (mode & 0o170000) == 0o040000:
                raise ColabAdapterError(
                    f"owner {account.owner!r}'s Colab configDir {directory} is "
                    "not a directory"
                )
            if mode & 0o077:
                raise ColabAdapterError(
                    f"owner {account.owner!r}'s Colab configDir {directory} is "
                    f"mode {oct(mode & 0o777)}; it holds that owner's token, so "
                    f"it must be 0700 (chmod 700 {directory})"
                )
            return {"PATH": os.environ.get("PATH", ""), "HOME": str(directory)}
        home = os.environ.get("HOME")
        if not home:
            raise ColabAdapterError(
                "HOME is not set in this process's environment; the colab "
                "CLI resolves its own credential file from HOME, and "
                "forwarding a child without one only moves the failure "
                "somewhere harder to read"
            )
        return {"PATH": os.environ.get("PATH", ""), "HOME": home}

    def _run(
        self,
        argv: list[str],
        *,
        timeout: float | None = None,
        account: TeamAccount | None = None,
    ) -> subprocess.CompletedProcess:
        """One subprocess boundary for every child this adapter starts.
        `account` selects whose environment the child gets (`_env_for`);
        the argv already carries that worker's `_cli()` prefix.

        `timeout=None` means the control-plane budget. A timeout is a
        `ColabTransportError` (the request died in flight — retry-eligible
        for reads alone), and a missing executable is a refusal naming the
        exact install command: this skill's `## Environment` section in
        `SKILL.md` is where a reader would look, and the sentence lives
        here, in the one file this skill lets name a service.
        """
        effective_timeout = self._control_timeout if timeout is None else timeout
        env = self._env_for(account)
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
            raise ColabTransportError(
                f"{argv[0]} timed out after {effective_timeout}s: refusing to "
                "guess at a state this process never confirmed"
            ) from exc
        except OSError as exc:
            remedy = ""
            if argv and argv[0] == self._colab_executable:
                remedy = (
                    f" — this adapter shells out to the {argv[0]!r} command "
                    "line, which arrives with `"
                    'uv tool install --force --python 3.14 "google-colab-cli==0.6.0" --with "jupyter-kernel-client<1"'
                    "`; "
                    "install it and make sure the tool bin directory it "
                    "reports is on PATH"
                )
            raise ColabAdapterError(f"could not run {argv[0]}: {exc}{remedy}") from exc

    def _run_read(
        self,
        argv: list[str],
        *,
        timeout: float | None = None,
        account: TeamAccount | None = None,
    ) -> subprocess.CompletedProcess:
        """`_run`, with the ONE retry this adapter ever performs: an
        idempotent read that died in flight is retried once, then
        refused. The transport class is explicit — an expired subprocess
        timeout, or the CLI's own `Connection was lost.` message in the
        child's output — and nothing about a state the service actually
        ANSWERED is ever retried into a different answer.
        """
        retried = False
        while True:
            try:
                result = self._run(argv, timeout=timeout, account=account)
            except ColabTransportError:
                if retried:
                    raise
                retried = True
                continue
            combined = f"{result.stdout}\n{result.stderr}".lower()
            if not retried and "connection was lost" in combined:
                retried = True
                continue
            return result

    def _parse_json_line(self, result: subprocess.CompletedProcess, action: str) -> dict:
        """Read the one compact JSON line a helper execution prints as its
        LAST non-empty output line. The CLI's own surrounding prose is
        tolerated, never parsed; a non-zero exit, no output, a final line
        that is not JSON, or JSON that is not an object are each a
        refusal — never a half-read state.
        """
        if result.returncode != 0:
            raise ColabAdapterError(
                f"{action} refused (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            raise ColabAdapterError(
                f"{action} printed nothing this adapter can read: "
                f"{result.stderr.strip()}"
            )
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise ColabAdapterError(
                f"{action}: the last output line is not JSON ({exc}): "
                f"{lines[-1]!r}"
            ) from exc
        if not isinstance(payload, dict):
            raise ColabAdapterError(
                f"{action}: the JSON line is {type(payload).__name__}, not an object"
            )
        return payload

    # -- session vocabulary -----------------------------------------------

    def _session_dir(self, session_name: str) -> str:
        return f"{self._remote_root}/{session_name}"

    def _parse_submission(self, submission_id: str) -> tuple[TeamAccount | None, str]:
        """Split `"<worker>/<session-name>"` and validate BOTH halves: the
        worker must be this adapter's own (the single worker, or a team
        owner the registry declares — whose account the returned tuple
        carries, so every child for this submission runs as that owner),
        and the name must match the
        shape this adapter generates (`SESSION_NAME_PREFIX` + slug +
        digest). The name is substituted into rendered sources that run
        on the VM, so anything else is refused here, before any
        substitution (ledger S2-J7).
        """
        worker, separator, session_name = submission_id.partition("/")
        if not separator or not session_name:
            raise ColabAdapterError(
                f"{submission_id!r} is not '<worker>/<session-name>'; "
                "refusing to guess which session this names"
            )
        try:
            account = self._account_for(worker, allow_legacy=True)
        except ColabAdapterError as exc:
            raise ColabAdapterError(
                f"{submission_id!r} names worker {worker!r}, which this adapter "
                f"does not issue ids for: {exc}"
            ) from exc
        if (
            len(session_name) > SESSION_NAME_MAX_CHARS
            or not session_name.startswith(SESSION_NAME_PREFIX)
            or _SESSION_NAME_RE.match(session_name) is None
        ):
            raise ColabAdapterError(
                f"{submission_id!r} carries {session_name!r}, which is not a "
                "session name this adapter generates; refusing before that "
                "name could reach a rendered source"
            )
        return account, session_name

    def _status_line(self, stdout: str, session_name: str) -> tuple[str, str] | None:
        """The measured status line for `session_name`, or `None` when the
        output carries no such line. Returns `(line, endpoint)`.
        """
        for line in stdout.splitlines():
            match = _SESSION_LINE_RE.match(line.strip())
            if match is None:
                continue
            if match.group("name") != session_name:
                continue
            return line.strip(), match.group("endpoint")
        return None

    @staticmethod
    def _looks_like_not_found(result: subprocess.CompletedProcess) -> bool:
        """The CLI's own "no such session" family, matched on OUTPUT and
        never on the exit code (measured: `stop` on an unknown session
        exits 0 — S0 obligation 3).
        """
        combined = f"{result.stdout}\n{result.stderr}".lower()
        return "not found" in combined

    @staticmethod
    def _service_prose_only(
            result: subprocess.CompletedProcess) -> subprocess.CompletedProcess:
        """The same result with the HELPER'S PAYLOAD LINE removed, so the
        wording test above reads only what the service itself said.

        A helper execution prints one compact JSON line last
        (`_parse_json_line`), and that line carries the RUN's own words --
        `status.json` verbatim, the error text the executor recorded
        included. `_looks_like_not_found()` matches its phrase anywhere in
        the output, so scanning that line let the run answer a question
        about the SERVICE: a run whose recorded error happened to contain
        that phrase was reported as a vanished session. Measured: changing
        only the wording of a recorded error, every other byte of the
        scenario identical, flipped the verdict from `failed` to
        `unknown` -- and `unknown` means evidence is MISSING, so a caller
        waiting for a terminal state keeps polling instead of stopping to
        look. The wording test itself is right to read output rather than
        the exit code (measured: 0 even for a session that does not
        exist); what was wrong is which output it was allowed to read.

        The last line is dropped ONLY when it parses as JSON. When the
        session really is gone there is no payload, and the service's own
        sentence IS the last line -- dropping it unconditionally would
        blind the very check this protects.
        """
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if lines:
            try:
                json.loads(lines[-1])
            except ValueError:  # not the payload, so it is the service talking
                pass
            else:
                lines = lines[:-1]
        return subprocess.CompletedProcess(
            result.args, result.returncode, "\n".join(lines), result.stderr
        )

    # -- rendering and helper execution -----------------------------------

    def _render(self, source: str, session_name: str) -> str:
        return source.replace(
            SESSION_DIR_TOKEN, _escape_source_literal(self._session_dir(session_name))
        )

    def _render_asset(self, asset_name: str, session_name: str, destination: Path) -> Path:
        """Render one `assets/colab/` template for this submission into
        `destination`. A missing asset is a refusal naming the path —
        never an empty file that would run as a no-op helper.
        """
        asset = self._assets_dir / asset_name
        try:
            source = asset.read_text(encoding="utf-8")
        except OSError as exc:
            raise ColabAdapterError(
                f"cannot read the {asset_name!r} template at {asset}: {exc}"
            ) from exc
        destination.write_text(self._render(source, session_name), encoding="utf-8")
        return destination

    def _write_helper(self, source: str, destination: Path, session_name: str) -> Path:
        destination.write_text(self._render(source, session_name), encoding="utf-8")
        return destination

    def _exec_result(
        self,
        helper: Path,
        session_name: str,
        *,
        retry_read: bool = False,
        account: TeamAccount | None = None,
    ) -> subprocess.CompletedProcess:
        """One in-kernel helper execution: `exec -f <rendered file>`, with
        the kernel budget passed to the CLI explicitly (the CLI's own
        default is 30 s — never reachable from here) and the subprocess
        timeout set to that budget plus slack, so the CLI's own timeout
        fires first and its message is the one a caller reads.
        """
        argv = [
            *self._cli(account),
            "exec",
            "-s",
            session_name,
            "-f",
            str(helper),
            "--timeout",
            str(self._kernel_timeout),
        ]
        timeout = self._kernel_timeout + self._subprocess_slack
        runner = self._run_read if retry_read else self._run
        return runner(argv, timeout=timeout, account=account)

    # -- lifecycle pieces --------------------------------------------------

    def _refuse_existing_session(
        self, session_name: str, account: TeamAccount | None = None
    ) -> None:
        """S0 obligation 1: `colab new` on an existing name REPLACES the
        machine and orphans the old one, which has no CLI release path
        and burns compute until idle reclaim. The listing is read BEFORE
        `new`, and a name already on it is a refusal — never a replace.
        """
        result = self._run_read([*self._cli(account), "sessions"], account=account)
        if result.returncode != 0:
            raise ColabAdapterError(
                f"colab sessions refused (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        for line in result.stdout.splitlines():
            match = _SESSION_LINE_RE.match(line.strip())
            if match is None or match.group("name") != session_name:
                continue
            raise ColabAdapterError(
                f"a session named {session_name!r} already exists on this "
                "account, and `colab new` would REPLACE it — silently "
                "orphaning the running machine, which has no CLI release "
                "path. Fetch, stop, or let that session expire before "
                "resubmitting this same job."
            )

    def _accelerator_variant(self, accelerator: object) -> str | None:
        """The `--gpu` variant a declared `accelerator` block maps to, or
        `None` when the run-config declares no block at all (CPU, exactly
        as before this existed).

        Fail-closed in every direction (SD18/D13), because every failure
        here is one the VM-side gate could not catch except after session
        spend: `kind` must be `cuda` (a TPU refuses — no `--tpu` mapping
        is invented), exactly one architecture string is required (zero
        or two cannot choose a machine, and a non-list is not a shape
        this protocol writes), and an architecture absent from
        `COLAB_ACCELERATOR_VARIANTS` refuses naming both the declared
        value and the table. The declared block still travels unchanged
        to the VM, where `check_accelerator()` remains the authority: it
        compares the declared `sm_*` names against the torch build
        actually installed on the arriving machine.
        """
        if accelerator is None:
            return None
        if not isinstance(accelerator, dict):
            raise ColabAdapterError(
                f"run-config.json's 'accelerator' block is "
                f"{type(accelerator).__name__}, not an object; refusing to "
                "guess at which machine this job needs"
            )
        kind = accelerator.get("kind")
        if kind != "cuda":
            raise ColabAdapterError(
                f"run-config.json declares accelerator kind {kind!r}, and "
                "this backend maps only 'cuda' architectures to a GPU "
                "variant (D13); a TPU is never requested here. Refusing "
                "rather than silently running the job on CPU."
            )
        architectures = accelerator.get("architectures")
        if (
            not isinstance(architectures, list)
            or len(architectures) != 1
            or not isinstance(architectures[0], str)
        ):
            raise ColabAdapterError(
                f"run-config.json declares accelerator architectures "
                f"{architectures!r}; exactly one architecture string is "
                "required to choose a GPU variant. Refusing rather than "
                "guessing."
            )
        architecture = architectures[0]
        variant = COLAB_ACCELERATOR_VARIANTS.get(architecture)
        if variant is None:
            raise ColabAdapterError(
                f"run-config.json declares accelerator architecture "
                f"{architecture!r}, which is not in this backend's variant "
                f"table {COLAB_ACCELERATOR_VARIANTS!r}; refusing rather than "
                "silently running the job on CPU."
            )
        return variant

    def _new_session(
        self,
        session_name: str,
        *,
        accelerator_variant: str | None = None,
        account: TeamAccount | None = None,
    ) -> None:
        """Provision one machine, requiring the measured positive
        confirmation (`Session READY`) rather than a bare exit code. A
        mapped accelerator is requested with `--gpu <variant>`; the flag
        and all three mapped variants are in the captured `help-new.log`
        surface (S0 fact 4).
        """
        argv = [*self._cli(account), "new", "-s", session_name]
        if accelerator_variant is not None:
            argv += ["--gpu", accelerator_variant]
        result = self._run(argv, timeout=self._new_timeout, account=account)
        combined = f"{result.stdout}\n{result.stderr}"
        if result.returncode != 0 or "session ready" not in combined.lower():
            raise ColabAdapterError(
                f"`new` for {session_name!r} did not report READY "
                f"(exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )

    def _endpoint_for(self, session_name: str, account: TeamAccount | None = None) -> str:
        """The `m-…` endpoint token from the measured `status` line. An
        unparseable endpoint refuses the launch BEFORE any upload: a
        session without keep-alive idles out mid-run and wastes the run.
        """
        result = self._run_read(
            [*self._cli(account), "status", "-s", session_name], account=account
        )
        if self._looks_like_not_found(result):
            raise ColabAdapterError(
                f"the session {session_name!r} vanished between `new` and "
                "`status`; refusing to launch into a machine this process "
                "cannot observe"
            )
        found = self._status_line(result.stdout, session_name)
        if found is None:
            raise ColabAdapterError(
                f"colab status for {session_name!r} printed no line this "
                f"adapter can read (exit {result.returncode}): "
                f"{result.stdout.strip() or result.stderr.strip()}"
            )
        return found[1]

    def _spawn_keep_alive(
        self, endpoint: str, session_name: str, account: TeamAccount | None = None
    ) -> None:
        """Best-effort keep-alive, detached, output to DEVNULL (parent
        plan D9). A spawn failure is deliberately NOT a refusal: the plan
        calls this best-effort, the session is already usable, and the
        endpoint above was the load-bearing parse. The invocation shape
        is the plan's (`keep-alive <endpoint> <name>`); the live daemon
        probe measured on this CLI was the module-form of the same hidden
        command, and S5 verifies this form against the real service
        (ledger S2-J5).
        """
        argv = [*self._cli(account), "keep-alive", endpoint, session_name]
        env = self._env_for(account)
        try:
            subprocess.Popen(
                argv,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return

    def _upload(
        self,
        local: Path,
        remote: str,
        session_name: str,
        account: TeamAccount | None = None,
    ) -> None:
        if not local.is_file():
            raise ColabAdapterError(
                f"cannot upload {local}: not a readable regular file"
            )
        result = self._run(
            [
                *self._cli(account),
                "upload",
                "-s",
                session_name,
                str(local),
                remote,
            ],
            timeout=self._transfer_timeout,
            account=account,
        )
        if result.returncode != 0:
            raise ColabAdapterError(
                f"upload of {local.name!r} refused (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )

    def _ensure_dependencies(
        self, probe: Path, session_name: str, account: TeamAccount | None = None
    ) -> None:
        """D10: probe, install only what is missing, re-probe once, and
        refuse a still-broken runtime — after a stop, never before one.
        """
        payload = self._parse_json_line(
            self._exec_result(probe, session_name, account=account),
            f"dependency probe for {session_name!r}",
        )
        missing = [package for package in PROBE_PACKAGES if payload.get(package) is None]
        if not missing:
            return
        install = self._run(
            [*self._cli(account), "install", "-s", session_name, *missing],
            timeout=self._install_timeout,
            account=account,
        )
        if install.returncode != 0:
            raise ColabAdapterError(
                f"installing {missing!r} on {session_name!r} refused "
                f"(exit {install.returncode}): "
                f"{install.stderr.strip() or install.stdout.strip()}"
            )
        reparsed = self._parse_json_line(
            self._exec_result(probe, session_name, account=account),
            f"dependency re-probe for {session_name!r}",
        )
        still = [package for package in PROBE_PACKAGES if reparsed.get(package) is None]
        if still:
            raise ColabAdapterError(
                f"the VM still cannot import {still!r} after `colab install`; "
                "refusing to launch a run that would die in its executor. "
                "Install them yourself (`colab install -s "
                f"{session_name} {' '.join(still)}`) and resubmit"
            )

    def _launch(
        self, launcher: Path, session_name: str, account: TeamAccount | None = None
    ) -> None:
        """Run the rendered launcher and require its receipt line. Never
        retried: a retry could spawn a second executor.
        """
        payload = self._parse_json_line(
            self._exec_result(launcher, session_name, account=account),
            f"launch for {session_name!r}",
        )
        if not isinstance(payload.get("launched_pid"), int):
            raise ColabAdapterError(
                f"the launcher for {session_name!r} did not report a pid: "
                f"{payload!r}"
            )

    def _stop_session(self, session_name: str, account: TeamAccount | None = None) -> None:
        """`colab stop -s <session>`, output-interpreted (measured:
        unknown sessions print "not found" and exit 0 — the exit code is
        not truth, S0 obligation 3).
        """
        argv = [*self._cli(account), "stop", "-s", session_name]
        result = self._run(argv, account=account)
        if self._looks_like_not_found(result):
            return
        if result.returncode != 0:
            raise ColabAdapterError(
                f"stop for {session_name!r} refused (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )

    def _stop_session_quietly(
        self, session_name: str, account: TeamAccount | None = None
    ) -> str:
        """Best-effort cleanup for a failure path: attempt the stop and
        return a note describing a FAILED cleanup, or `""` when the stop
        succeeded or the session was already gone. Never raises — the
        caller is already unwinding a primary failure.
        """
        try:
            self._stop_session(session_name, account)
        except ColabAdapterError as exc:
            return f"session cleanup also failed: {exc}"
        return ""

    # -- the seam's six operations ----------------------------------------

    def workers(self) -> list["ADAPTER.Worker"]:
        """This backend's workers, stated rather than discovered: the
        operator's single account, or — when the team registry declares
        Colab accounts — one worker per owner (`colab:<owner>`).

        No subprocess, no network, no credential read: a unit of capacity
        is one account (the registry is read, never anything inside an
        owner's state directory), its sessions are serialized by this
        adapter, and a `workers()` that dialed the service would make
        `packer`'s own capacity path depend on the network for a figure no
        call could change.
        """
        team = self._team()
        if team is None:
            return [ADAPTER.Worker(id=WORKER_ID, capacity=COLAB_WORKER_CAPACITY)]
        # One worker per owner, FREE-tier accounts listed first. The order
        # is load-bearing for the campaign path: `packer.distribute()`
        # assigns in this order and the campaign submit loop launches in
        # assignment order, so a campaign that would place a unit on a
        # free account reaches that account's refusal in `submit()` before
        # any paid account has launched anything — the campaign refuses
        # whole, never half-launched. A single send (`packer.select()`)
        # may pick a free account first, which its tier allows.
        ordered = [a for a in team if a.campaign_refusal() is not None] + [
            a for a in team if a.campaign_refusal() is None
        ]
        return [
            ADAPTER.Worker(id=account.worker_id, capacity=COLAB_WORKER_CAPACITY)
            for account in ordered
        ]

    def submit(self, job: "ADAPTER.Job") -> "ADAPTER.Submission":
        """The full session lifecycle, in the parent plan's own order:
        job-folder checks → `new` → endpoint → keep-alive → remote mkdir →
        uploads (plus the credential material, when one is configured —
        after the three payload uploads, before the probe) → dependency
        probe (install only what is missing) → the detached launch → the
        submission receipt.

        The credential bytes are read ONCE, before any network call at
        all (S3/D6): a bad path refuses before a session is even checked
        for, let alone uploaded to. The bytes are then written into the
        same per-call temp dir the rendered helpers use — never into the
        job folder, never into `run-config.json` — and both files die
        with the call after being uploaded.

        Everything after the `new` INVOCATION sits inside one cleanup
        boundary: any failure attempts a stop, and a cleanup that itself
        fails is appended to the refusal rather than swallowing it (the
        parent plan's D9 says "any failure after `colab new`", which
        includes `new`'s own timeouts and its missing-READY case — the
        ledger's S2-J2). The stop is a measured no-op when no session
        exists, so the boundary can start at the invocation without
        inventing a session that was never created.
        """
        # Whose account this is, decided before anything else: an unknown
        # worker, or the legacy single worker while a team registry is in
        # force, refuses here. Then the tier rule: a job carrying campaign
        # `units` on a free account refuses by name, citing the service's
        # own FAQ, before any CLI call — refusing is free here.
        account = self._account_for(job.worker, allow_legacy=False) if (
            self._team() is not None
        ) else None
        if account is not None and job.run_config.get("units"):
            refusal = account.campaign_refusal()
            if refusal is not None:
                raise ColabAdapterError(f"campaign submission refused: {refusal}")
        entrypoint = Path(job.entrypoint)
        run_config_path = entrypoint.parent / RUN_CONFIG_FILENAME
        if not run_config_path.is_file():
            raise ColabAdapterError(
                f"{entrypoint} has no {RUN_CONFIG_FILENAME} sibling: this "
                "backend admits only the generated job-folder shape, and a "
                "bare notebook has no session protocol to run. Generate one "
                "with `generate-job --service colab` and submit its "
                f"{RUNNER_FILENAME}"
            )
        try:
            run_config_text = run_config_path.read_text(encoding="utf-8")
            parsed_run_config = json.loads(run_config_text)
        except (OSError, json.JSONDecodeError) as exc:
            raise ColabAdapterError(
                f"cannot read {run_config_path}: {exc}"
            ) from exc
        if not isinstance(parsed_run_config, dict):
            raise ColabAdapterError(
                f"{run_config_path} is not a JSON object; refusing to guess "
                "at a run configuration"
            )
        commit = parsed_run_config.get("commit")
        if not isinstance(commit, str) or not commit:
            raise ColabAdapterError(
                f"{run_config_path} carries no usable 'commit' string; the "
                "submission digest is built from it and a guessed pin would "
                "name the wrong session"
            )
        # D13/S4: the declared accelerator decides which machine arrives,
        # and the decision is made BEFORE any CLI call at all — an
        # unmappable declaration refuses here, while refusing is free.
        accelerator_variant = self._accelerator_variant(
            parsed_run_config.get("accelerator")
        )
        try:
            entrypoint_bytes = entrypoint.read_bytes()
        except OSError as exc:
            raise ColabAdapterError(f"cannot read {entrypoint}: {exc}") from exc

        mode = _mode_token(job.run_config)
        digest = _digest8(entrypoint_bytes, commit, mode)
        session_name = f"{SESSION_NAME_PREFIX}{_slugify(entrypoint.parent.name)}-{digest}"

        # S3/D6: the credential bytes are read once, here — before the
        # session pre-check and before any upload — so a bad path refuses
        # while refusing still costs nothing, and the stripped value is
        # carried in this local until it is written into the temp dir.
        credential_token = (
            self._read_repo_credential()
            if self._repo_credential_path is not None
            else None
        )

        self._refuse_existing_session(session_name, account)

        if job.run_config:
            merged = dict(parsed_run_config)
            merged.update(dict(job.run_config))
            staged_run_config_text = json.dumps(merged)
        else:
            staged_run_config_text = run_config_text

        with tempfile.TemporaryDirectory(prefix="psmith-colab-session-") as raw_tmp:
            tmp = Path(raw_tmp)
            # Both rendered templates are materialized here (parent plan
            # §4's submit step 5); `poll()`/`fetch()` render their own
            # read_state copies at their own call sites, each inside a
            # temp dir that dies with the call.
            launcher = self._render_asset(LAUNCH_ASSET, session_name, tmp / LAUNCH_ASSET)
            self._render_asset(READ_STATE_ASSET, session_name, tmp / READ_STATE_ASSET)
            mkdir_helper = self._write_helper(_MKDIR_SOURCE, tmp / "remote-mkdir.py", session_name)
            probe_helper = self._write_helper(
                _PROBE_SOURCE, tmp / "dependency-probe.py", session_name
            )
            staged_run_config = tmp / RUN_CONFIG_FILENAME
            staged_run_config.write_text(staged_run_config_text, encoding="utf-8")

            try:
                self._new_session(
                    session_name,
                    accelerator_variant=accelerator_variant,
                    account=account,
                )
                endpoint = self._endpoint_for(session_name, account)
                self._spawn_keep_alive(endpoint, session_name, account)

                payload = self._parse_json_line(
                    self._exec_result(mkdir_helper, session_name, account=account),
                    f"remote mkdir for {session_name!r}",
                )
                if payload.get("exists") is not True:
                    raise ColabAdapterError(
                        f"the remote mkdir helper did not confirm the session "
                        f"directory: {payload!r}"
                    )

                self._upload(self._assets_dir / EXECUTOR_ASSET, f"{self._session_dir(session_name)}/{EXECUTOR_ASSET}", session_name, account)
                self._upload(staged_run_config, f"{self._session_dir(session_name)}/{RUN_CONFIG_FILENAME}", session_name, account)
                self._upload(entrypoint, f"{self._session_dir(session_name)}/{entrypoint.name}", session_name, account)

                # S3/D6 staging: the askpass script (verbatim) and the
                # token file (stripped bytes, 0o600, no trailing newline)
                # go up AFTER the payload and BEFORE the probe. The local
                # copies live in `tmp` and die with this call; the job
                # folder and `run-config.json` are never written.
                if credential_token is not None:
                    askpass_local = tmp / REPO_CREDENTIAL_ASKPASS_FILENAME
                    askpass_local.write_text(
                        REPO_CREDENTIAL_ASKPASS_SOURCE, encoding="utf-8"
                    )
                    token_local = tmp / REPO_CREDENTIAL_TOKEN_FILENAME
                    token_local.write_bytes(credential_token.encode("utf-8"))
                    os.chmod(token_local, 0o600)
                    self._upload(
                        askpass_local,
                        f"{self._session_dir(session_name)}/{REPO_CREDENTIAL_ASKPASS_FILENAME}",
                        session_name,
                        account,
                    )
                    self._upload(
                        token_local,
                        f"{self._session_dir(session_name)}/{REPO_CREDENTIAL_TOKEN_FILENAME}",
                        session_name,
                        account,
                    )

                self._ensure_dependencies(probe_helper, session_name, account)
                self._launch(launcher, session_name, account)
            except BaseException as exc:  # noqa: BLE001 - D9's cleanup boundary
                note = self._stop_session_quietly(session_name, account)
                if note:
                    _append_note(exc, note)
                raise

        return ADAPTER.Submission(id=f"{job.worker}/{session_name}", worker=job.worker)

    def poll(self, submission_id: str) -> "ADAPTER.Status":
        """One honest status, translated into the seam's vocabulary, never
        the service's own text (the parent plan's D8 table, exactly).

        A session gone mid-flight is `unknown` — evidence is MISSING, not
        negative — including the case where it vanishes between the
        `status` read and the state read (ledger S2-J6). `status` and the
        state read are the two idempotent reads this adapter retries
        once; neither is ever retried into a different answer, because
        the same input is re-asked, not a new question.
        """
        account, session_name = self._parse_submission(submission_id)
        status_result = self._run_read(
            [*self._cli(account), "status", "-s", session_name], account=account
        )
        if self._looks_like_not_found(status_result):
            return ADAPTER.Status(state="unknown", detail="session not found")
        found = self._status_line(status_result.stdout, session_name)
        if found is None:
            raise ColabAdapterError(
                f"colab status for {submission_id!r} printed no line this "
                f"adapter can read (exit {status_result.returncode}): "
                f"{status_result.stdout.strip() or status_result.stderr.strip()}"
            )
        line = found[0]

        with tempfile.TemporaryDirectory(prefix="psmith-colab-read-") as raw_tmp:
            reader = self._render_asset(
                READ_STATE_ASSET, session_name, Path(raw_tmp) / READ_STATE_ASSET
            )
            read_result = self._exec_result(
                reader, session_name, retry_read=True, account=account
            )
        if self._looks_like_not_found(self._service_prose_only(read_result)):
            return ADAPTER.Status(state="unknown", detail="session not found")
        payload = self._parse_json_line(read_result, f"state read for {submission_id!r}")

        status = payload.get("status")
        if status is not None:
            if not isinstance(status, dict):
                raise ColabAdapterError(
                    f"{submission_id!r}: status.json is not a JSON object: {status!r}"
                )
            exit_code = status.get("exitCode")
            if isinstance(exit_code, bool) or not isinstance(exit_code, int):
                raise ColabAdapterError(
                    f"{submission_id!r}: status.json carries no usable "
                    f"exitCode: {status!r}"
                )
            if exit_code == 0:
                return ADAPTER.Status(state="complete", detail=line)
            # The executor records WHY beside the exit code, already
            # bounded at the writer (`ERROR_MAX_CHARS`, so a runaway
            # traceback cannot turn a completion signal into megabytes).
            # Reporting the number alone left that field written and read
            # by nobody, and left the caller with a digit to go digging
            # from -- measured: a run whose notebook could not start
            # surfaced as `unit process exited 1` beside a log holding one
            # unrelated warning, with the reason sitting in `status.json`
            # the whole time. A non-string or blank `error` is simply
            # absent: this reports what the run recorded, and never
            # invents a reason it did not.
            detail = f"unit process exited {exit_code}"
            recorded = status.get("error")
            if isinstance(recorded, str) and recorded.strip():
                detail = f"{detail}: {recorded.strip()}"
            return ADAPTER.Status(state="failed", detail=detail)

        launch = payload.get("launch")
        if launch is not None:
            pid = launch.get("pid") if isinstance(launch, dict) else None
            return ADAPTER.Status(state="running", detail=f"pid {pid}")
        return ADAPTER.Status(state="queued", detail=line)

    def fetch(self, submission_id: str, into: Path) -> "ADAPTER.Fetched":
        """Materialize the run's working-directory capture under `into`,
        completely or as completely as it exists, then release the
        session when the run is terminal (the parent plan's D9/D12).

        The manifest is downloaded entry by entry (the CLI has no
        directory transfer), each entry validated as a relative,
        non-escaping path first — and refused outright when it names this
        protocol's own staged credential material at the top level
        (S3/D6). The release runs only AFTER the downloads, and only for
        a run whose `status.json` exists — whatever its exit code,
        because the run is over either way; a session gone at read time
        is a refusal naming it, and a refusal to stop fails the fetch
        only after the bytes are already local.
        """
        account, session_name = self._parse_submission(submission_id)
        into = Path(into)
        into.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="psmith-colab-read-") as raw_tmp:
            reader = self._render_asset(
                READ_STATE_ASSET, session_name, Path(raw_tmp) / READ_STATE_ASSET
            )
            read_result = self._exec_result(
                reader, session_name, retry_read=True, account=account
            )
        if self._looks_like_not_found(self._service_prose_only(read_result)):
            raise ColabAdapterError(
                f"the session for {submission_id!r} no longer exists; it may "
                "already have been released by a terminal fetch, or stopped "
                "outside this skill. The ledger's own fold is the completion "
                "authority — this call will not invent one."
            )
        payload = self._parse_json_line(read_result, f"state read for {submission_id!r}")

        manifest = payload.get("files")
        if manifest is None:
            entries: list[str] = []
        elif isinstance(manifest, list) and all(isinstance(entry, str) for entry in manifest):
            entries = list(manifest)
        else:
            raise ColabAdapterError(
                f"{submission_id!r}: files.json is not a list of strings: "
                f"{manifest!r}"
            )
        for entry in entries:
            candidate = PurePosixPath(entry)
            if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
                raise ColabAdapterError(
                    f"{submission_id!r}: manifest entry {entry!r} is not a "
                    "safe relative path; refusing before any download"
                )
            # S3/D6, defense in depth: the executor deletes the staged
            # askpass material after the run and excludes both names from
            # its manifest at the top level, so a manifest naming either
            # one is a shape this protocol never produces — refusing here
            # keeps a credential file from being downloaded even if a
            # future executor regressed. The same basename under a
            # subdirectory is a product of the run, not protocol material,
            # and does NOT refuse.
            if candidate.parts[0] in CREDENTIAL_MATERIAL_FILENAMES:
                raise ColabAdapterError(
                    f"{submission_id!r}: manifest entry {entry!r} names this "
                    "protocol's own credential material; the executor deletes "
                    "both staged names after the run and never lists them, so "
                    "refusing before any download"
                )

        materialized: list[str] = []
        for entry in sorted(entries):
            local = into / entry
            local.parent.mkdir(parents=True, exist_ok=True)
            remote = f"{self._session_dir(session_name)}/{entry}"
            result = self._run(
                [
                    *self._cli(account),
                    "download",
                    "-s",
                    session_name,
                    remote,
                    str(local),
                ],
                timeout=self._transfer_timeout,
                account=account,
            )
            if result.returncode != 0:
                raise ColabAdapterError(
                    f"download of {entry!r} for {submission_id!r} refused "
                    f"(exit {result.returncode}): "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )
            if local.suffix == ".ipynb":
                restore_notebook_json(local)
            materialized.append(entry)

        status = payload.get("status")
        complete = False
        terminal = status is not None
        if terminal:
            if not isinstance(status, dict):
                raise ColabAdapterError(
                    f"{submission_id!r}: status.json is not a JSON object: {status!r}"
                )
            exit_code = status.get("exitCode")
            if isinstance(exit_code, bool) or not isinstance(exit_code, int):
                raise ColabAdapterError(
                    f"{submission_id!r}: status.json carries no usable "
                    f"exitCode: {status!r}"
                )
            complete = exit_code == 0

        if terminal:
            self._stop_session(session_name, account)

        return ADAPTER.Fetched(path=into, complete=complete, files=tuple(sorted(materialized)))

    def cancel(self, submission_id: str) -> None:
        """`colab stop -s <session>`, addressed by the session name the
        submission id carries. No caller in the nine-command roster
        invokes this operation on its own initiative (`reconcile` reports
        orphans, never cancels them); it exists for an explicit caller
        and for tests.
        """
        account, session_name = self._parse_submission(submission_id)
        self._stop_session(session_name, account)

    def list_active(self, worker: str) -> list[str]:
        """Submission ids this adapter issued whose sessions still exist,
        from `colab sessions` (measured shape in this module's docstring).

        Only names carrying this adapter's own prefix are claimed — the
        CLI lists the ACCOUNT's sessions, so a session some other tooling
        created is not this adapter's to report. A `[?]` machine is
        skipped deliberately: the CLI can no longer resolve a name for
        it, and fabricating one would make `reconcile` claim a session
        this skill can neither stop nor fetch.
        """
        account = self._account_for(worker, allow_legacy=True)
        result = self._run([*self._cli(account), "sessions"], account=account)
        if result.returncode != 0:
            raise ColabAdapterError(
                f"colab sessions refused (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        active: list[str] = []
        for line in result.stdout.splitlines():
            match = _SESSION_LINE_RE.match(line.strip())
            if match is None:
                continue
            name = match.group("name")
            if name == "?" or not name.startswith(SESSION_NAME_PREFIX):
                continue
            active.append(f"{worker}/{name}")
        return active


def _declared_capacity() -> tuple[int, int] | None:
    """The engine's declared-capacity channel (`adapter.py`'s fourth
    registry), answered from disk and constants alone — no subprocess, no
    network, per that registry's own contract.

    With no team registry (or one declaring no Colab account): the static
    single worker, `(1, COLAB_WORKER_CAPACITY)`, exactly as before. With
    one: parallelism counts DISTINCT OWNERS whose tier admits a split
    campaign, because a free account is never a campaign worker; a team
    of free accounts only still declares the one session a single send
    can use, `(1, COLAB_WORKER_CAPACITY)`. A registry this module cannot
    honestly read declares nothing (`None`), so a caller leaves the figure
    out rather than publishing a guess."""
    try:
        team = load_colab_team(DEFAULT_TEAM_REGISTRY)
    except ColabAdapterError:
        return None
    if not team:
        return (1, COLAB_WORKER_CAPACITY)
    paid = sum(1 for account in team if account.campaign_refusal() is None)
    return (max(paid, 1), COLAB_WORKER_CAPACITY)


ADAPTER.register("colab", ColabAdapter)
ADAPTER.register_declared_capacity("colab", _declared_capacity)
ADAPTER.register_default_accelerator("colab", _default_accelerator)
