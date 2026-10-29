#!/usr/bin/env python3
"""The remote-execution adapter seam.

This module defines the ABC every backend-specific adapter must satisfy in
full, the frozen data shapes that cross the seam in either direction, and a
small name-to-class registry so a caller can select a backend by a string
without importing it directly.

Nothing here knows what any backend is called or how it talks over the
network. That knowledge is confined to exactly one file per backend, living
below this seam. This module is the boundary that makes swapping one such
file for another a no-op for everything above it: the ledger, the packer,
and the CLI depend on this interface only, never on a concrete adapter class.

A second backend, if one is ever added, would expose exactly four places
this seam could otherwise leak its details through. Each shape below states,
next to the field it concerns, the rule that keeps it from doing so:

- `Submission.id` — opaque outside the adapter that issued it.
- `Status.state` — the seam's own vocabulary, never a backend's raw text.
- `Job.run_config` — an opaque mapping the adapter interprets; the packer
  and the ledger never read or branch on a key inside it.
- `Worker.capacity` — concurrent jobs per worker, not a backend's own
  metering unit.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Sequence


@dataclass(frozen=True)
class Worker:
    """One execution slot a backend exposes, and the cap it states for it.

    `capacity` means concurrent jobs this worker may run at once — never a
    quota, a byte budget, or a time budget. A backend that meters capacity
    some other way converts that into "how many jobs at once" inside its own
    adapter; this shape carries only the converted number, never the
    backend's own unit.
    """

    id: str
    capacity: int


@dataclass(frozen=True)
class Job:
    """One unit of work handed to `Adapter.submit()`.

    `entrypoint` is a path and nothing more. This dataclass carries no
    opinion about what kind of file it points to — no extension check, no
    directory-containment rule. That is deliberate: this repository's rule
    that a submitted entrypoint must end `.ipynb` and live under
    `<Name>/Notebooks/` is real and stays enforced, but it is *the
    submitting CLI's path guard's* policy, held in exactly one place. A
    future workload that is not a notebook becomes admissible by widening
    that one guard — not by reworking this dataclass, the ledger's event
    schema, the fold's indices, or any other consumer that would otherwise
    need to change alongside a field rename.

    `run_config` is an opaque mapping this dataclass does not interpret.
    What one backend's adapter expects there (a dataset identifier, a run
    mode, a set of seeds) and what another expects is that adapter's
    business alone; nothing above this seam — the packer and the ledger
    included — ever reads or branches on a key inside it. `__post_init__`
    normalizes whatever mapping a caller passes into a `MappingProxyType`
    over a private copy, so even mutating the mapping a caller gets back
    from `job.run_config` is structurally refused, and mutating the
    caller's own original dict after construction cannot leak in either.
    An empty `run_config` is the legacy shape every existing caller already
    uses; a non-empty one is what a generated job carries.
    """

    entrypoint: Path
    run_config: Mapping[str, object]
    worker: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_config", MappingProxyType(dict(self.run_config)))


@dataclass(frozen=True)
class Submission:
    """A backend's receipt for one `submit()` call.

    `id` is OPAQUE to everything above this seam. The ledger and the packer
    are permitted exactly two operations on it: equality, and use as a dict
    key. Neither is permitted to split it, parse it, or pattern-match any
    part of it — an id's internal shape is a fact about the backend that
    issued it, and code that came to depend on that shape would break the
    moment a second backend issued ids shaped differently.
    """

    id: str
    worker: str


# The seam's own five-value vocabulary for `Status.state` — not any
# backend's. A backend's raw status text (a queue position, an internal
# code) never belongs here; it goes in `Status.detail` instead. Translating
# a backend's own vocabulary into this one is the adapter's job, every time.
STATES = ("queued", "running", "complete", "failed", "unknown")


@dataclass(frozen=True)
class Status:
    """A poll result, expressed in the seam's vocabulary, never the backend's.

    `state` is validated against `STATES` at construction — enforced, not
    merely documented, for the same reason the ABC below refuses an
    incomplete subclass rather than trusting a comment to be read. `detail`
    is where a backend's own raw status text belongs; anything that would
    tempt a caller to start pattern-matching backend-specific strings out of
    `state` itself goes there instead.
    """

    state: str
    detail: str

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(
                f"{self.state!r} is not one of this seam's states {STATES}; "
                "a backend's own status text belongs in `detail`, not here"
            )


@dataclass(frozen=True)
class Fetched:
    """The result of one `fetch()` call."""

    path: Path
    complete: bool
    files: tuple[str, ...]


@dataclass(frozen=True)
class CredentialHandle:
    """One worker's credential, as a path to it.

    `token_path` names a filesystem path a concrete adapter consumes; this
    dataclass holds no opinion about how — which environment variable it
    ends up in, whether the path names a file or a directory, or whether
    the client behind it wants the path or the bytes at it. All of those
    are facts about one service's client, and the concrete adapter is the
    one place allowed to know them. Everything else about a credential
    handle is common to every backend this seam could ever hold, which is
    why this shape lives here instead of being redefined inside each
    adapter module.

    It exposes no read method, and nothing in this seam reads one. The
    guarantee is scoped exactly that far and no further: `token_path` is
    carried here, and every module ABOVE a concrete adapter is structurally
    incapable of turning it into a value, because none of them touches the
    attribute at all. Whether the credential's VALUE is read below this
    seam is a question about one client, answered in the adapter that
    names it — not a promise this shape can make on every backend's behalf.
    """

    worker_id: str
    token_path: Path


class AdapterError(Exception):
    """A backend refused, timed out, or answered with something unusable.

    The seam's own error type, and the fifth thing that crosses this boundary
    besides the four data shapes above. Every concrete adapter raises a
    subclass of this and nothing else.

    Without it the seam has a hole exactly where it is supposed to be sealed.
    A caller has to catch a backend's failures somehow, and if the only type
    available is the concrete adapter's own, then catching it means importing
    it — so the CLI would have to name every backend it might be run against,
    which is the one thing this whole file exists to prevent. The alternative,
    catching bare `Exception`, is worse: it swallows the genuine defects a
    traceback is for.

    So the failure this closes is not a crash but a leak: a common base is
    what lets code above the seam handle a backend it has never heard of.
    """


class WorkerUnauthorized(AdapterError):
    """A backend refused a worker's credential specifically — not a generic
    failure, a timeout, or an unreachable service, but the backend's own
    distinct signal that THIS credential is no longer valid (a revoked or
    expired token, most concretely).

    Backend-blind by design, the same way every other name in this seam is:
    nothing here says "401", "403", or any other backend's own wire-level
    detail. A concrete adapter recognizes its own backend's unauthorized
    signal and raises this in its place, so code above the seam — the
    packer's automatic worker selection, chiefly — can tell "this worker is
    unhealthy, try another" apart from "the service is merely unreachable
    right now, fall back to what the ledger already knows" without ever
    importing a concrete adapter to catch its backend-specific exception.

    This is the fact that keeps automatic selection honest: swallowing this
    exception the same way an unreachable-service failure is swallowed would
    let a revoked account look exactly like a healthy one that merely could
    not be reached — the one failure mode this class exists to make
    impossible to confuse.
    """


class Adapter(ABC):
    """The seam every backend-specific adapter must satisfy in full.

    Ledger and packer code depends on this interface only — never on a
    concrete adapter class. Leaving even one of the six operations
    unimplemented in a subclass must make that subclass itself
    uninstantiable; that is what `ABC` and `@abstractmethod` are doing here,
    together, and it is a structural guarantee, not a convention a future
    subclass could quietly ignore.
    """

    # Optional capability, deliberately NOT a seventh operation: the most
    # bytes of compressed code bundle (`generate-job --code-bundle`) this
    # backend can carry inside the job it pushes. A backend whose runner
    # cannot authenticate a clone of a private repository declares an int
    # here and ships the bundle's bytes with the job; `None` (this
    # default) means the backend carries no bundle, and generation refuses
    # `--code-bundle` for it by code (`CODE_BUNDLE_NOT_CARRIED`).
    CODE_BUNDLE_MAX_BYTES: int | None = None

    # Optional capability, deliberately NOT a seventh operation either
    # (kernel-input-datasets S2): the directory inside a job under which
    # this backend mounts, read-only, the public datasets the job declares
    # (`generate-job --input-dataset`, `run_config["inputDatasets"]`) and
    # which this backend attaches to the push itself. `submit` hands it to
    # the job as `run_config["inputRoot"]`, the runner searches it for each
    # ref's slug and exports what it found in `FORGE_INPUT_DATASETS`, and
    # `submit` reports `inputs: attached`. `None` (this default) means the
    # backend attaches no inputs: `submit` reports `inputs: unsupported`
    # and the runner exports every ref mapped to null, so the target
    # downloads the data itself.
    INPUT_DATASETS_ROOT: str | None = None

    # Optional, and not an operation either (remote-preflight S2): the
    # dataset host -- as the datasets skill's `hosts` package names it --
    # whose public datasets this backend attaches. `generate-job --dataset`
    # refuses `DATASET_HOST_NOT_ATTACHABLE` for a dataset another host
    # serves. `None` (this default) means no host is named, so none is
    # refused.
    INPUT_DATASETS_HOST: str | None = None

    # Optional, and not an operation either (session-chains S5): a backend
    # whose jobs cannot mount an earlier submission's output
    # (`carry_source()` answers `None`) but which uploads files from this
    # machine into the session it starts. `True` makes `submit` hand a
    # continuation `{"submissionId", "ref", "upload": <the local directory
    # `fetch` left>}` rows in `run_config["carry"]`; the backend uploads the
    # job's declared carry paths from there and rewrites each row to the
    # `mount` the runner restores from. `False` (this default) leaves such
    # a continuation `carry: unsupported`.
    CARRY_UPLOAD: bool = False

    # Optional, and not an operation either (remote-preflight S3): the
    # distribution names this backend's worker image already provides.
    # `generate-jobs` leaves them out of the requirements it derives from
    # the target's pins. Empty (this default) means nothing is assumed
    # provided, so every pin is installed.
    PROVIDED_REQUIREMENTS: tuple[str, ...] = ()

    @abstractmethod
    def workers(self) -> list[Worker]:
        """Report the workers this backend currently exposes, and each cap."""

    @abstractmethod
    def submit(self, job: Job) -> Submission:
        """Hand one job to the backend, returning its opaque submission receipt."""

    @abstractmethod
    def poll(self, submission_id: str) -> Status:
        """Report a submission's state, translated into the seam's vocabulary."""

    @abstractmethod
    def fetch(self, submission_id: str, into: Path) -> Fetched:
        """Materialize a submission's result under `into`, complete or not."""

    @abstractmethod
    def cancel(self, submission_id: str) -> None:
        """Ask the backend to stop a submission. Never called by this seam itself."""

    @abstractmethod
    def list_active(self, worker: str) -> list[str]:
        """Report the submission ids the backend still considers active for `worker`."""

    @classmethod
    def session_limit_seconds(cls, machine_shape: str | None = None) -> int | None:
        """The service's continuous run limit for one session, in seconds.

        Deliberately NOT abstract, and not a seventh operation: it asks the
        service nothing. A backend answers from a constant it declares --
        the limit the service published for that accelerator -- and
        `machine_shape=None` means the accelerator that backend requests by
        default. A classmethod so a planner can read it before any worker
        or credential exists. This default, `None`, means "unknown": a
        caller must then treat the session as unbounded by this skill's
        knowledge, never invent a number (see "What this skill cannot see").
        """
        return None

    def carry_source(self, submission_id: str) -> Mapping[str, str] | None:
        """How a later job of this backend reads an earlier submission's
        output, or `None` when this backend cannot mount one (kernel-carry
        S2, S5).

        Deliberately NOT abstract, and not a seventh operation: it asks the
        service nothing. A backend whose jobs can name another job's output
        as an input answers `{"ref": <the input reference it pushes>,
        "mount": <the directory that output appears under inside the
        job>}`; `submit` hands both to the next job in
        `run_config["carry"]` and the runner restores the job's declared
        carry paths from `mount`. This default, `None`, means the backend
        carries nothing automatically, and `submit` reports
        `carry: unsupported` rather than dropping the continuation silently.
        """
        return None


_REGISTRY: dict[str, type[Adapter]] = {}


def register(name: str, adapter_cls: type[Adapter]) -> None:
    """Register a concrete adapter class under a name a caller can select by.

    This is the one place a backend-specific module and this seam-only
    module meet, and the meeting happens by the backend module calling IN to
    this function — this module never imports OUT to any backend module.
    That direction is what keeps this file free of any backend's name, no
    matter how many backends the registry eventually holds.
    """
    if not (isinstance(adapter_cls, type) and issubclass(adapter_cls, Adapter)):
        raise TypeError(f"{adapter_cls!r} does not subclass Adapter")
    _REGISTRY[name] = adapter_cls


def resolve(name: str) -> type[Adapter]:
    """Look up a previously registered adapter class by name.

    A miss names what IS registered, not just what was asked for: a caller
    staring at "no adapter registered under 'x'" alone has no way to tell a
    typo from a name whose module was never even loaded, and the available
    list is exactly the fact that turns this from a dead end into something
    actionable.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY)) if _REGISTRY else "none registered"
        raise KeyError(
            f"no adapter registered under {name!r}; available: {available}"
        ) from None


# A second, separate registry from the one above — deliberately not a
# seventh `Adapter` ABC operation. The spec pins that ABC at exactly six
# operations, so a backend that needs to assemble a service-specific
# metadata file (an accelerator request, say) registers a plain function
# here instead of widening the ABC every other backend would then also
# have to implement, whether it needs one or not.
MetadataAssembler = Callable[[Mapping[str, object]], tuple[str, str]]

_METADATA_REGISTRY: dict[str, MetadataAssembler] = {}


def register_metadata(name: str, fn: MetadataAssembler) -> None:
    """Register a metadata assembler under a name a caller can select by.

    `fn(run_config) -> (filename, text)`. Whatever this returns is opaque
    to every caller above the adapter that registered it — a future
    `jobfolder.py` writes the returned bytes under the returned filename
    without ever learning what either one means.
    """
    _METADATA_REGISTRY[name] = fn


def resolve_metadata(name: str) -> MetadataAssembler:
    """Look up a previously registered metadata assembler by name."""
    try:
        return _METADATA_REGISTRY[name]
    except KeyError:
        raise KeyError(f"no metadata assembler registered under {name!r}") from None


# A THIRD, separate registry — the same reason the metadata one above is
# separate from the ABC: which accelerator a service is EXPECTED to hand
# out by default is service knowledge (a fact about one backend's own
# hardware pool), never a forge default and never required of every
# backend.
# `jobfolder.py` calls `resolve_default_accelerator(service)` only when a
# caller declared NEITHER half of the accelerator pair itself; a caller's
# own `--accelerator-kind`/`--accelerator-architecture` always overrides
# whatever this returns, and a backend that registers nothing here simply
# leaves `generate_job()` writing no `accelerator` block at all — silence,
# not a guess, exactly the behavior every backend had before this registry
# existed.
DefaultAcceleratorProvider = Callable[[], tuple[str, Sequence[str]]]

_DEFAULT_ACCELERATOR_REGISTRY: dict[str, DefaultAcceleratorProvider] = {}


def register_default_accelerator(name: str, fn: DefaultAcceleratorProvider) -> None:
    """Register a service's own expected-accelerator default under a name
    a caller can select by.

    `fn() -> (kind, architectures)` — exactly the two fields
    `jobfolder.build_run_config()` already names, and nothing else: this
    registry carries no device name, no package, no target vocabulary.
    """
    _DEFAULT_ACCELERATOR_REGISTRY[name] = fn


def resolve_default_accelerator(name: str) -> DefaultAcceleratorProvider | None:
    """Look up a previously registered default-accelerator provider by
    name, or `None` when no backend registered one under it.

    Unlike `resolve()`/`resolve_metadata()` above, a miss here is never an
    error: having no declared default is a legitimate, additive-safe
    state a caller (`generate_job()`) is expected to handle by writing no
    `accelerator` block at all, not a caller mistake to refuse.
    """
    return _DEFAULT_ACCELERATOR_REGISTRY.get(name)


# Which services can run a job on a CPU-only session (`generate-job
# --accelerator-kind cpu`). Service knowledge again, and opt-in: a backend
# that registers nothing here has a CPU-only job refused at generation,
# naming the service, rather than handed whatever machine it defaults to.
_CPU_ONLY_SERVICES: set[str] = set()


def register_cpu_only(name: str) -> None:
    """Declare that the service named `name` can run a CPU-only session."""
    _CPU_ONLY_SERVICES.add(name)


def supports_cpu_only(name: str) -> bool:
    return name in _CPU_ONLY_SERVICES


# A FOURTH, separate registry — deliberately not a seventh `Adapter` ABC
# operation, for the identical reason the metadata registry above is not:
# the spec pins that ABC at exactly six operations
# (`test_adapter_abc_still_exposes_exactly_six_operations`), and a
# non-abstract seventh method would survive that count while still living
# one attribute lookup away from `workers()` — a subclass could implement
# it as `return self.workers()` and nothing here would notice.
#
# The contract this registry carries, load-bearing for every caller above
# it: a reporter registered here answers from what is already on disk — or
# from constants the backend already fixes, when its capacity is constant
# by construction — and issues NO network request of its own. A backend
# that cannot answer that way registers nothing — silence, not a guess,
# matching `register_default_accelerator`'s own convention just above. A
# caller
# composing a launch proposal reads a registry miss, or a registered
# reporter's own runtime `None` answer, the same way: by leaving that
# figure out of what it publishes entirely, never by falling back to
# `Adapter.workers()`, which carries no disk-only promise for every
# backend the way this registry's own contract does.
DeclaredCapacityReporter = Callable[[], tuple[int, int] | None]

_DECLARED_CAPACITY_REGISTRY: dict[str, DeclaredCapacityReporter] = {}


def register_declared_capacity(name: str, fn: DeclaredCapacityReporter) -> None:
    """Register a backend's disk-only capacity reporter under a name a
    caller can select by.

    `fn() -> (workers, per_worker) | None` — no arguments, because the
    caller that reads this registry composes a launch proposal before any
    worker or credential has been chosen for it. See this registry's own
    module-level comment above for the contract every reporter registered
    here must keep.
    """
    _DECLARED_CAPACITY_REGISTRY[name] = fn


def resolve_declared_capacity(name: str) -> DeclaredCapacityReporter | None:
    """Look up a previously registered declared-capacity reporter by name,
    or `None` when no backend registered one under it.

    A miss here is never an error, matching `resolve_default_accelerator`'s
    own convention: a caller composing a launch proposal reads `None` as
    "no capacity figure to publish" and leaves that whole action out
    entirely, never as a caller mistake to refuse.
    """
    return _DECLARED_CAPACITY_REGISTRY.get(name)
