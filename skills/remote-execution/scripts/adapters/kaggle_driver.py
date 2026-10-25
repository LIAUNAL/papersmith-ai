#!/usr/bin/env python3
"""The Kaggle SDK driver — the ONLY file in this entire skill allowed to
import `kagglesdk`.

`adapters/kaggle.py` shells out to this script as a child process, exactly
the way it used to shell out to the `kaggle` command-line tool. What moved
is the CHILD's identity, not the boundary: `_env_for()` in `kaggle.py` still
builds one child process's whole environment from an allowlist and puts the
stored account's credential value on it there; this file never reads that
variable itself and never constructs one of its own — the only route to
that value is `kagglesdk`'s own `_try_fill_auth()`, reading the child's
environment on its own, inside `_init_session()`, well after this process
starts.

The installed client's own `authenticate()` demands a classic key or a
`kaggle.json` and performs Basic auth before any request is built; the
stored accounts hold 37-character access tokens that answer Basic with 401
for every account, valid or not. `kagglesdk`'s own `_try_fill_auth()`
prefers a Bearer credential sourced from the child's environment over that
Basic fallback — a route Kaggle's own developers document as unfinished
(`kagglesdk/kaggle_http_client.py:14-17`: "This was created from
kaggle_api_client.py, prior to recent changes to auth handling. The new
client requires KAGGLE_API_TOKEN, so it is not currently usable by the
CLI."). Driving that route directly is the entire reason this file exists.

The child-process boundary is preserved deliberately, not incidentally:
`KaggleHttpClient.__init__` takes no credential argument at all, so the
only public way to hand it one is that process-global environment variable
— two concurrent workers sharing one process would race it. One process
per submission is what makes concurrent credentials correct, and it is the
exact same boundary that keeps an argv/env observation point alive for this
skill's own offline proof. See `SKILL.md`'s credential-transport table for
the guarantees this preserves and the ones a second interception point,
mounted on this driver's own `requests` session in its tests, exists to
prove instead (what a submission's outbound request actually contains).

The one client this file ever builds is constructed at exactly one
expression (`_build_client()`, below) — the same idiom
`CredentialSecurityTests` already locks `adapters/kaggle.py` to for
`.token_path`. Every operation function below receives that already-built
client rather than constructing its own; a function that built one anyway
would bypass whatever transport a caller (this file's own test suite
included) mounted on the shared session and attempt a real socket.

Run with the interpreter that has this package installed — measured on
this machine to be the interpreter the CommandLineTools ship,
`sys.executable` in the invoking (adapter) process, since that is the one
process the whole call chain already inherits from. `selftest` is the
first thing a caller should run: it reports whether the interpreter
running this file has a `kagglesdk` that both imports AND can name an
accelerator, and if either is untrue, the refusal names that interpreter
and the install command by which it becomes true, rather than a bare
traceback.

Both halves of that question are asked at module level, not in the
`selftest` branch, so `submit`, `poll`, `fetch` and `capacity` are refused
under a bad interpreter too — `selftest` is the recommended first call,
never the only gate. See `_accelerator_capability_error()` for why the
second half is a `hasattr` against the real request class rather than a
version comparison.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import uuid
from pathlib import Path

try:
    from kagglesdk.kaggle_http_client import KaggleHttpClient
    from kagglesdk.kernels.services.kernels_api_service import KernelsApiClient
    from kagglesdk.kernels.types.kernels_api_service import (
        ApiGetKernelSessionStatusRequest,
        ApiListKernelSessionOutputRequest,
        ApiListKernelsRequest,
        ApiSaveKernelRequest,
    )
    from kagglesdk.kernels.types.kernels_enums import (
        KernelsListSortType,
        KernelsListViewType,
    )
    import requests  # a `kagglesdk` dependency in its own right; imported
    # after it, so an interpreter missing only this one still reports the
    # accurate cause below rather than a misleading `kagglesdk` complaint.

    _IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # exercised by running this file under an
    # interpreter with no `kaggle` distribution installed — see
    # `test_driver_selftest_imports_kagglesdk`'s failure half.
    requests = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


def _accelerator_capability_error() -> str | None:
    """Whether the `kagglesdk` that just imported can actually ASK for a
    card, answered against the real class rather than a version string.

    Importing is necessary and not sufficient. Two distributions both
    satisfy the block above and only one knows `machine_shape`, the single
    field by which a job requests the T4 (sm_75): the standalone
    `kagglesdk==0.1.37` this skill pins carries it; the copy vendored
    inside the retired `kaggle==1.7.4.5` — measured on this machine under a
    3.9 user site — imports cleanly and does not. An interpreter admitted
    on the import axis alone can therefore be one whose every submission
    silently draws whatever accelerator the scheduler hands out, and a P100
    kills these runs in seconds.

    Asked as `hasattr` against a real `ApiSaveKernelRequest`, deliberately,
    never as a comparison against `__version__`: this module's own
    docstring rejects "a version stated here and enforced nowhere", and a
    distribution is free to carry the pinned version string and not the
    field. The field is the capability; the version is a rumor about it.

    Fails CLOSED. A probe that cannot complete has not established the
    capability, and the failure this guards against is silent — the whole
    point is that an unproven accelerator request is refused loudly and
    locally rather than discovered from a run that came back on the wrong
    card.
    """
    if _IMPORT_ERROR is not None:
        return None
    try:
        if hasattr(ApiSaveKernelRequest(), "machine_shape"):
            return None
        return (
            "the importable kagglesdk cannot request an accelerator: its "
            "ApiSaveKernelRequest has no `machine_shape` field, so a job "
            "cannot name the T4 and would run on whatever card the "
            "scheduler draws"
        )
    except Exception as exc:  # fail closed: unproven is not proven
        return (
            "the importable kagglesdk could not be checked for the "
            f"`machine_shape` field a job needs to name the T4: {exc}"
        )


_CAPABILITY_ERROR: str | None = _accelerator_capability_error()

# The one reason `main()` refuses to do anything at all, whichever axis
# produced it. Kept as a single value, checked at a single site, because
# these two failures need the SAME remedy sentence: the pinned
# distribution, installed for THIS interpreter. Two refusal sites would
# also invite the capability check to drift into the `selftest` branch,
# where a caller that skipped `selftest` would sail straight past it.
_UNUSABLE_SDK: str | None = (
    f"kagglesdk is not importable: {_IMPORT_ERROR}"
    if _IMPORT_ERROR is not None
    else _CAPABILITY_ERROR
)


EXIT_OK = 0
EXIT_UNAUTHORIZED = 3
EXIT_REFUSED = 1

_KERNEL_METADATA_FILENAME = "kernel-metadata.json"

# The metadata keys `adapters/kaggle.py`'s own `assemble_metadata()` writes,
# and later completes with `id`/`code_file`, that map straight onto an
# identically-named `ApiSaveKernelRequest` attribute. `id` and `code_file`
# are handled separately, immediately below, because neither maps straight
# across: `id` on the request is an int the service assigns, while the
# metadata's own `id` carries the STRING `<owner>/<slug>` that belongs on
# `slug` instead; `code_file` names a path, not a request field, and is
# consumed to read the bytes that become `text`.
_METADATA_PASSTHROUGH_KEYS = (
    "language",
    "kernel_type",
    "is_private",
    "enable_gpu",
    "enable_internet",
    "machine_shape",
)


class DriverError(Exception):
    """A refusal this driver raises on its own initiative: an unmapped
    metadata key, a request the service refused, or any other answer this
    file declines to fabricate. Caught once, in `main()`, and reported as
    one JSON object on stdout plus a non-zero exit — never a raw traceback,
    which a caller reading only an exit code and stdout could not act on.
    """


def _build_client() -> "KaggleHttpClient":
    """The one place in this whole file `KaggleHttpClient` is constructed.

    Locked by `test_driver_client_constructed_at_one_locked_expression`,
    parsed as an AST exactly like `CredentialSecurityTests` already locks
    `.token_path` in `adapters/kaggle.py`: a second construction inside an
    operation function would build a session nothing mounted a test
    transport onto, and would reach for a real socket instead of failing
    the lock.
    """
    return KaggleHttpClient()


def _save_kernel_request_from_staging(staging_dir: Path) -> "ApiSaveKernelRequest":
    """Read the staged `kernel-metadata.json` `adapters/kaggle.py` already
    completed with `id` and `code_file`, and map it onto one
    `ApiSaveKernelRequest` — the ONLY place in this driver that builds one.

    The table is CLOSED: every metadata key is either consumed explicitly
    above (`id`, `code_file`) or passed straight through by name
    (`_METADATA_PASSTHROUGH_KEYS`, which now includes `machine_shape` —
    see `adapters/kaggle.py`'s own `KAGGLE_MACHINE_SHAPE`); a key that is
    neither is a refusal naming it, never a silent drop. This is what
    keeps a genuinely unmapped key from repeating the `machine_shape`
    defect class under a different name: the retired `kaggle==1.7.4.5`
    client's `kernels_push()` never read that key at all, so it silently
    reached nobody for the life of this skill before this table started
    mapping it explicitly.

    No cancel path exists through this table or this client. Kaggle's own
    `ApiCancelKernelSessionRequest` requires a `kernel_session_id`, and no
    RPC this SDK exposes returns one for an existing session:
    `get_kernel_session_status` answers only `status`/`failure_message`
    (see `cmd_poll` above), `list_kernel_session_output` answers only
    `files`/`log` (see `cmd_fetch` below), and `list_kernels` answers only
    per-kernel metadata (see `cmd_capacity` below) — none of the three
    carries a session id. The only reachable levers to stop a running
    kernel are `delete_kernel` (destroys the kernel outright, not merely
    the session) or Kaggle's own web UI; this is a durable limitation of
    the service's public surface, not a gap in this driver, and
    `adapters/kaggle.py`'s own `cancel()` refuses explicitly rather than
    guessing at an unofficial operation. See
    `test_fetch_never_relies_on_kernel_session_id_from_status_response`,
    which proves the id's structural absence from `poll`'s own response
    but never carried that fact to this cancel case until now.
    """
    metadata_path = staging_dir / _KERNEL_METADATA_FILENAME
    metadata = dict(json.loads(metadata_path.read_text(encoding="utf-8")))

    request = ApiSaveKernelRequest()

    # TRAP, measured rather than assumed: the request's own `id` attribute
    # is typed `int` (the service's numeric kernel id); the metadata's `id`
    # carries the STRING `<owner>/<slug>` `adapters/kaggle.py` builds at
    # submit time. Assigning the metadata's `id` onto the request's `id`
    # raises `TypeError` immediately — assigning it onto `slug` instead is
    # the fix, not a workaround.
    owner_slug = metadata.pop("id", None)
    if owner_slug:
        request.slug = owner_slug

    title = metadata.pop("title", None)
    if title:
        request.new_title = title

    code_file = metadata.pop("code_file", None)
    if code_file:
        request.text = (staging_dir / code_file).read_text(encoding="utf-8")

    for key in _METADATA_PASSTHROUGH_KEYS:
        if key in metadata:
            setattr(request, key, metadata.pop(key))

    if metadata:
        raise DriverError(
            f"{metadata_path} carries key(s) {sorted(metadata)} this driver "
            "has no mapping for onto a save-kernel request; refusing rather "
            "than silently dropping them the way `machine_shape` once "
            "traveled to nobody"
        )

    return request


def cmd_submit(client: "KernelsApiClient", staging_dir: Path) -> dict:
    """Push one staged job folder's kernel, returning the service's own
    receipt fields — never anything this driver invented on its own.
    """
    request = _save_kernel_request_from_staging(staging_dir)
    response = client.save_kernel(request)
    return {
        "ref": response.ref,
        "url": response.url,
        "versionNumber": response.version_number,
    }


def cmd_poll(client: "KernelsApiClient", submission_id: str) -> dict:
    """Ask the service for one kernel session's status, translated no
    further than the enum's own name — `adapters/kaggle.py` is where a raw
    status becomes the seam's own five-value vocabulary, not here.
    """
    worker, slug = submission_id.split("/", 1)
    request = ApiGetKernelSessionStatusRequest()
    request.user_name = worker
    request.kernel_slug = slug
    response = client.get_kernel_session_status(request)
    return {
        "status": response.status.name,
        "failureMessage": response.failure_message,
    }


def cmd_capacity(client: "KernelsApiClient") -> dict:
    """Rebuild the in-flight-kernel count `list_active`/`plan()` needs, with
    no `list_active`-shaped RPC anywhere on this SDK to answer it directly.

    MEASURED, not assumed: `list_kernels(group=PROFILE)` answers with
    `ApiKernelMetadata` entries carrying `ref`/`slug` and no `status` field
    at all — enumeration, not state. `get_kernel_session_status`, one call
    per ref, is what answers the state question `list_active()` actually
    needs. Cost is `1 + N` requests, and this function makes only the
    FIRST page's worth of that cost — `request.page = 1`, sorted
    `DATE_RUN` (most-recently-run first, the only ordering under which
    "first page" can still stand in for "every kernel that could possibly
    still be active"). That is a stated BOUND, not a claim of
    completeness: a kernel outside the first page is, by definition, one
    this call does not report on, and `adapters/kaggle.py`'s own
    `list_active()` never claims otherwise either.

    MEASURED, not assumed, against the live service on 2026-09-24, across
    all 9 accounts configured on this repository at the time: `list_kernels`
    itself succeeded on every single one of the 9, and two distinct per-ref
    failure shapes were what left 7 of the 9 looking unreachable before this
    function grew the handling below.

    - HTTP 404 from `get_kernel_session_status` — 17 refs across 6 accounts.
      A 404 on that endpoint means no session exists for that kernel; that
      reading rests on the ordinary meaning of a 404 on a session-status
      resource, NOT on ever having observed a genuinely `queued` or
      `running` kernel answer differently — no account had one at probe
      time, every resolved status was `COMPLETE`, `ERROR` or
      `CANCEL_ACKNOWLEDGED`. Say that plainly rather than overstate it.
    - `ValueError` from the two-target unpack below (`ref.split("/", 1)`) —
      one of those accounts enumerated an entry with `ref == ''`
      and `title == '[Private Notebook]'`; `''.split("/", 1)` yields
      `['']`, which cannot fill `user_name, kernel_slug` and raised before
      any request was attempted.

    A hypothesis TESTED AND REFUTED against that same measurement: the
    per-kernel `current_version_number` field does NOT discriminate a
    resolvable ref from an unresolvable one — every enumerated kernel
    reported `0`, resolved and unresolved alike. Do not gate anything on
    it, and do not cite it as evidence either way.

    Before this fix, NEITHER shape was caught: a ref that could not even
    be split raised before a request was sent, and a ref whose status
    lookup answered non-200 raised from inside `client.get_kernel_session_
    status`, and either one propagated straight out of this function, past
    `main()`'s own generic `except Exception`, and turned a SUCCESSFUL
    enumeration into a driver-level refusal — which `adapters/kaggle.py`'s
    `_parse_capacity_result` then stamped `"(list_kernels failed
    structurally)"`, blaming the enumeration for a downstream per-ref
    failure it never had.

    The fix: a ref is guarded BEFORE it is used at all — one containing no
    `/` cannot address a status request and is recorded unresolved without
    an attempt — and the status call itself is wrapped so ANY exception it
    raises makes that ONE ref unresolved without interrupting the refs
    around it. Reports `{"kernels": [{"ref": ..., "status": ...}, ...],
    "unresolved": [{"ref": ..., "reason": ..., "detail": ...}, ...]}`.
    `kernels` keeps exactly its pre-existing shape for every ref that
    resolved — `status` is still the bare `KernelWorkerStatus` member name,
    the same shape `cmd_poll` already prints, so `adapters/kaggle.py`
    translates both through the one table it already owns. `reason` is one
    of three machine-stable values: `"unaddressable_ref"` (never reached a
    request), `"session_absent"` (HTTP 404 — definitive: no session
    exists), or `"status_lookup_failed"` (failed any other way — timeout,
    429, 5xx — state genuinely unknown); `detail` carries the HTTP status
    code when the exception exposes one. An unresolved ref is reported, never
    dropped and never fabricated a status for — silently dropping it would
    make `list_active()` undercount a kernel that might still be running
    outside this function's view, and fabricating one would invent
    evidence this call never obtained.

    This function itself still raises, and rightly, when `list_kernels`
    fails — an enumeration this driver could not perform at all is a
    genuinely different failure than a per-ref lookup this driver
    performed and lost, and `main()`'s existing exit-code handling for
    THAT case (401/403 → `EXIT_UNAUTHORIZED`, anything else →
    `EXIT_REFUSED`) is unchanged by this fix.
    """
    request = ApiListKernelsRequest()
    request.group = KernelsListViewType.PROFILE
    request.sort_by = KernelsListSortType.DATE_RUN
    request.page = 1
    response = client.list_kernels(request)

    kernels: list[dict] = []
    unresolved: list[dict] = []
    for kernel in response.kernels or []:
        ref = kernel.ref or ""
        if "/" not in ref:
            unresolved.append(
                {
                    "ref": ref,
                    "reason": "unaddressable_ref",
                    "detail": f"ref {ref!r} carries no '/' separator to "
                    "split into user_name/kernel_slug",
                }
            )
            continue

        try:
            status_request = ApiGetKernelSessionStatusRequest()
            status_request.user_name, status_request.kernel_slug = ref.split("/", 1)
            status_response = client.get_kernel_session_status(status_request)
        except Exception as exc:  # any per-ref failure stays per-ref
            http_response = getattr(exc, "response", None)
            status_code = getattr(http_response, "status_code", None)
            # An auth refusal is a fact about the WORKER, never about this
            # ref, so it does NOT stay per-ref: it is re-raised to reach
            # `main()`'s own `requests.exceptions.HTTPError` handler, which
            # returns `EXIT_UNAUTHORIZED` for exactly 401/403, which
            # `adapters/kaggle.py`'s `_parse_capacity_result` maps to
            # `ADAPTER.WorkerUnauthorized`, which `packer.plan()` re-raises
            # rather than degrading to the ledger.
            #
            # Containing it per-ref the way a 404 is contained looks
            # symmetrical and is not: the next ref may well answer after a
            # 404 or a timeout, and will answer identically after a refused
            # credential. Folded into `status_lookup_failed`, the ref counts
            # as unknown, `list_active()` counts unknown as ACTIVE, and a
            # revoked account reads as a busy one -- inverting the single
            # distinction `_parse_capacity_result`'s docstring says it exists
            # to preserve, and hiding the only remedy that works.
            if status_code in (401, 403):
                raise
            detail = f"HTTP {status_code}: {exc}" if status_code is not None else str(exc)
            # A 404 is DEFINITIVE negative evidence (no session exists), not
            # a lookup this driver merely failed to complete.
            reason = "session_absent" if status_code == 404 else "status_lookup_failed"
            unresolved.append({"ref": ref, "reason": reason, "detail": detail})
            continue

        kernels.append({"ref": ref, "status": status_response.status.name})

    return {"kernels": kernels, "unresolved": unresolved}


#: Hosts a per-file download may send this session's stored credential to:
#: Kaggle's API endpoint and its web origin, over https on the default port.
#: Any other host, a signed storage URL say, is fetched with no credential.
KAGGLE_CREDENTIAL_HOSTS = frozenset({"api.kaggle.com", "www.kaggle.com", "kaggle.com"})
#: Redirect hops one per-file download may follow before it is refused.
FETCH_MAX_REDIRECTS = 5
#: Seconds to connect, and seconds a read may stall, on each download hop.
FETCH_TIMEOUT = (10, 60)
#: Bytes one fetch may write, every file together: 20 GiB, above the 20 GB a
#: Kaggle notebook's output directory holds, so only a runaway answer
#: reaches it.
FETCH_MAX_BYTES = 20 * 1024**3
#: The output listing is paged; a token that never empties must not loop forever.
FETCH_MAX_PAGES = 1000


def _is_kaggle_origin(url: str) -> bool:
    """True when `url` is https on a `KAGGLE_CREDENTIAL_HOSTS` host, on the
    default port and with no userinfo of its own."""
    parts = urllib.parse.urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname in KAGGLE_CREDENTIAL_HOSTS
        and port in (None, 443)
        and parts.username is None
        and parts.password is None
    )


def _send(session, prepared):
    """Send one download hop through the transport mounted for its URL.

    Not through `session.send`, which reads a redirect's whole body itself,
    unbounded, even with redirects off. Skipping it also skips what it adds
    on top of the transport, on purpose: no response hook runs (`kagglesdk`
    registers none) and no cookie a file host sets joins the authenticated
    session. The environment's proxy and CA bundle settings still apply, as
    they do on every `session.request`.
    """
    settings = session.merge_environment_settings(prepared.url, {}, True, None, None)
    return session.get_adapter(prepared.url).send(prepared, timeout=FETCH_TIMEOUT, **settings)


def _stream_into(response, destination: Path, budget: int, url: str) -> int:
    """Stream `response`'s body into `destination`, refusing past `budget`
    bytes; returns the bytes written.

    The body lands in a temporary file beside `destination` that replaces it
    only once complete, so a refused or broken download leaves no partial
    file behind and never truncates a copy an earlier fetch wrote.
    """
    declared = response.headers.get("Content-Length", "")
    if declared.isdigit() and int(declared) > budget:
        raise DriverError(
            f"refusing to download {url!r}: it declares {declared} bytes, over the "
            f"{budget} this fetch has left of its {FETCH_MAX_BYTES}-byte limit"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.parent / f".fetch-{uuid.uuid4().hex}.part"
    written = 0
    out = partial.open("xb")
    try:
        with out:
            for chunk in response.iter_content(chunk_size=1 << 20):
                written += len(chunk)
                if written > budget:
                    raise DriverError(
                        f"refusing to download {url!r}: it sent more than the {budget} "
                        f"bytes this fetch has left of its {FETCH_MAX_BYTES}-byte limit"
                    )
                out.write(chunk)
        partial.replace(destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return written


def _fetch_file(session, url: str, destination: Path, budget: int) -> int:
    """Download one listed file through `session`; returns the bytes written.

    Each hop's request is built here: with the session's auth, headers and
    cookies while every hop so far has been a Kaggle origin, bare from the
    first one that was not. Redirects are followed here too, https only and
    at most `FETCH_MAX_REDIRECTS` of them.
    """
    credentialed = True
    for _hop in range(FETCH_MAX_REDIRECTS + 1):
        if urllib.parse.urlsplit(url).scheme != "https":
            raise DriverError(f"refusing to download {url!r}: only https is fetched")
        credentialed = credentialed and _is_kaggle_origin(url)
        request = requests.Request("GET", url)
        prepared = session.prepare_request(request) if credentialed else request.prepare()
        with _send(session, prepared) as response:
            if response.is_redirect:
                url = urllib.parse.urljoin(url, response.headers["Location"])
                continue
            response.raise_for_status()
            return _stream_into(response, destination, budget, url)
    raise DriverError(f"refusing to download {url!r}: more than {FETCH_MAX_REDIRECTS} redirects")


def cmd_fetch(client: "KernelsApiClient", submission_id: str, into: Path) -> dict:
    """Materialize one kernel session's output under `into`, file by file.

    MEASURED, not assumed: `ApiGetKernelSessionStatusResponse` (`poll`'s own
    response shape, `kernels_api_service.py:245`) carries exactly `status`
    and `failure_message` — no `kernel_session_id` anywhere on it — so
    `download_kernel_output_zip`, which needs precisely that id
    (`ApiDownloadKernelOutputZipRequest.kernel_session_id`), is structurally
    unreachable from any poll this driver could ever perform. That is the
    design's own reason for going file-by-file through
    `list_kernel_session_output` instead: it takes a `user_name`/
    `kernel_slug` pair (this function already has both, from `submission_id`
    alone) and answers with a `files` list — each entry a `(url, fileName)`
    pair — plus the session's own `log`, with no session id required on

    Also MEASURED, and worth stating because it looks like a plausible
    alternative route: `download_kernel_output` (a THIRD download RPC,
    distinct from both `list_kernel_session_output` above and
    `download_kernel_output_zip`) takes `ApiDownloadKernelOutputRequest`,
    whose owner-naming field is `owner_slug`, not `user_name` — leaving it
    unset answers 403 Forbidden, not a field-shaped error, and its response
    is an `HttpRedirect` requiring a SECOND fetch of `redirect.url`. This
    function never constructs that request type at all, so neither trap
    applies here: `ApiListKernelSessionOutputRequest.user_name` above is the
    correct field for the RPC this function actually calls, not a mistaken
    echo of `download_kernel_output`'s own `owner_slug`.
    either side.

    Which download carries this session's stored credential is decided
    here, not by `requests` (#55). The per-file `url`s come from a response,
    and a URL in a response is no authority to send the credential wherever
    it points. Each file goes through `client._client._session`, the one
    session a test transport is mounted on, but `_fetch_file` applies that
    session's auth, headers and cookies only to a Kaggle origin
    (`KAGGLE_CREDENTIAL_HOSTS`, https, default port). Any other host, such
    as a signed storage URL, gets a bare GET with no credential at all.
    Redirects are followed by hand: https only, at most
    `FETCH_MAX_REDIRECTS`, and the credential stops for good at the first
    hop that leaves a Kaggle origin. Every hop has `FETCH_TIMEOUT`, and each
    body streams into a temporary file, renamed into place once complete,
    under one `FETCH_MAX_BYTES` budget for the whole fetch, so a stalled or
    oversized answer is refused instead of hanging or filling the disk.
    Whether Kaggle's own file URLs need the credential at all is still
    unrehearsed against a live account; one that did, on a host that is not
    a Kaggle origin, would answer 401 or 403, which `main()` reports as
    unauthorized rather than as a download.

    `client._client._session` reaches into two attributes the SDK marks
    private (`KernelsApiClient._client`, `KaggleHttpClient._session`)
    because `kagglesdk` exposes no public accessor for the session a raw
    per-file URL must be fetched through — `download_kernel_output`/
    `download_kernel_output_zip` are RPC calls returning a redirect or a
    typed file download, neither of which is the shape
    `list_kernel_session_output` itself already returns. There is no route
    to these URLs through this SDK's own public surface.

    Never relies on the driver's own reported file names for anything but
    what to write to disk; a file entry missing a name or url refuses
    rather than guessing at either.
    """
    worker, slug = submission_id.split("/", 1)

    def list_page(token: str):
        request = ApiListKernelSessionOutputRequest()
        request.user_name = worker
        request.kernel_slug = slug
        request.page_token = token
        return client.list_kernel_session_output(request)

    response = list_page("")

    into.mkdir(parents=True, exist_ok=True)
    session = client._client._session
    written: list[str] = []

    # The log goes first, before a single output file is attempted. It used
    # to be written after the loop, which meant any file that failed took the
    # log down with it -- and the log is the only artifact that says why a
    # remote run failed. A log that arrives only when everything else already
    # worked is a log nobody will ever have at the moment they need it.
    if response.log:
        (into / "log.txt").write_text(response.log, encoding="utf-8")
        written.append("log.txt")

    # The listing is paged, as `kaggle kernels output` reads it: follow
    # `next_page_token` until it comes back empty (#93). The log rides on the
    # first page and is already written.
    files = list(response.files or [])
    seen = {""}
    pages = 1
    token = getattr(response, "next_page_token", "") or ""
    while token:
        if token in seen:
            raise DriverError(
                f"list_kernel_session_output for {submission_id} returned a "
                f"repeated page token {token!r}; refusing to loop")
        if pages >= FETCH_MAX_PAGES:
            raise DriverError(
                f"list_kernel_session_output for {submission_id} returned more "
                f"than {FETCH_MAX_PAGES} pages; refusing to continue")
        seen.add(token)
        response = list_page(token)
        pages += 1
        files.extend(response.files or [])
        token = getattr(response, "next_page_token", "") or ""

    root = into.resolve()
    budget = FETCH_MAX_BYTES
    for output_file in files:
        name = output_file.file_name
        url = output_file.url
        if not name or not url:
            raise DriverError(
                f"list_kernel_session_output for {submission_id} returned a "
                f"file entry missing a name or url: name={name!r} url={url!r}"
            )
        # `file_name` is a path relative to the remote working directory, not
        # a flat basename: a run that reads a dataset answers with entries
        # several directories deep under the clone. One `mkdir` on `into`
        # cannot serve those, so each file makes its own parents.
        destination = (into / name).resolve()
        # Creating parents for a name the service chose is what makes this
        # check necessary rather than merely prudent: before, a name climbing
        # out of `into` failed on a missing directory; now it would be built
        # on the way out. Refuse instead of writing somewhere nobody asked for.
        if destination != root and root not in destination.parents:
            raise DriverError(
                f"list_kernel_session_output for {submission_id} returned a "
                f"file name that leaves the destination: {name!r}"
            )
        budget -= _fetch_file(session, url, destination, budget)
        written.append(name)

    return {"files": sorted(written)}


def _print_result(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def main(argv: list[str]) -> int:
    # Checked before the operation is even read, exactly as the import
    # refusal always was: an unusable SDK is unusable for `submit`, `poll`,
    # `fetch` and `capacity` alike, and a check that lived in the `selftest`
    # branch would be skipped by every caller that never runs `selftest`.
    if _UNUSABLE_SDK is not None:
        _print_result(
            {
                "ok": False,
                "error": (
                    f"under {sys.executable}, {_UNUSABLE_SDK}; install it with "
                    f"`{sys.executable} -m pip install --user kagglesdk==0.1.37`"
                ),
            }
        )
        return EXIT_REFUSED

    if not argv:
        _print_result(
            {
                "ok": False,
                "error": "no operation named; expected one of: submit, poll, fetch, "
                "capacity, selftest",
            }
        )
        return EXIT_REFUSED

    op, rest = argv[0], argv[1:]

    if op == "selftest":
        _print_result({"ok": True, "interpreter": sys.executable})
        return EXIT_OK

    client = KernelsApiClient(_build_client())

    try:
        if op == "submit":
            result = cmd_submit(client, Path(rest[0]))
        elif op == "poll":
            result = cmd_poll(client, rest[0])
        elif op == "fetch":
            result = cmd_fetch(client, rest[0], Path(rest[1]))
        elif op == "capacity":
            result = cmd_capacity(client)
        else:
            _print_result({"ok": False, "error": f"unknown operation {op!r}"})
            return EXIT_REFUSED
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        _print_result({"ok": False, "error": str(exc)})
        return EXIT_UNAUTHORIZED if status in (401, 403) else EXIT_REFUSED
    except DriverError as exc:
        _print_result({"ok": False, "error": str(exc)})
        return EXIT_REFUSED
    except Exception as exc:  # a refusal, never a fabricated result
        _print_result({"ok": False, "error": str(exc)})
        return EXIT_REFUSED

    _print_result({"ok": True, **result})
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
