#!/usr/bin/env python3
"""Cell 0 of the generated runner notebook — copied byte for byte.

`jobfolder.build_notebook()` copies this file's bytes into the notebook's
first cell with ZERO interpolation. The same bytes serve every job because
every fact this cell needs comes from `run-config.json`, read at runtime,
never baked in at generation time. Ten responsibilities, in order:

1. read `run-config.json`; validate schema/version
2. sparse-clone the pinned commit: `git init`, `remote add`,
   `sparse-checkout set <clonePaths>`, `fetch --depth 1 origin <commit>`,
   `checkout FETCH_HEAD`. When the job staged a repository credential
   beside this cell (`git-askpass.sh`, S3), every clone call carries
   `GIT_ASKPASS` pointing at it, a non-`https://` `repo.url` refuses
   before the first git call, and both material files are deleted in a
   `finally` immediately after the clone attempt. When `run-config.json`
   declares a `codeBundle`, the job carried its pinned code with it:
   `unpack_code_bundle()` verifies the bundle's sha256 and unpacks it
   into the same clone directory instead, with no git call at all
3. `sys.path.insert(0, <clone>/src)`
4. install the declared build: `sys.executable -m pip install`, list
   argv, against `run-config.json`'s additive `environment.install`
   (Decision 3). This runs BEFORE responsibility 5, never after —
   responsibility 5 imports the declared modules, and those modules
   import the tensor library this step installs; installing after that
   point would be too late. An older, undeclared config carries no
   `environment.install` block and this step is a no-op. Honest cost:
   this installs on every kernel that runs a job, adding minutes to each
   one — a campaign of thirty shards pays that cost thirty times.
   Determinism (the arriving capability verified against what was
   actually installed, never assumed) was chosen over the cheaper
   deferral of trusting a pre-baked image
5. import each declared module and assert its `__file__` resolves under
   the clone's own `src` — the "pip-installed copy" refusal: a module
   importable from somewhere ELSE already on `sys.path` would silently
   run against code this job never pinned a commit for. A declared
   NOTEBOOK gets the same proof in the only form a notebook can take
   (`verify_notebooks_under_clone`): the file is where the pinned sparse
   checkout should have put it, and it names a kernel
6. detect hardware — `torch` not importable IS "hardware missing"; no
   silent CPU fallback, or this refusal could never actually fire
7. write `bootstrap.json`: commit, config, detected environment, resolved
   imports and resolved notebooks
8. any of config / code / hardware missing raises `SystemExit` on the
   spot, so cell 1 never runs against a half-prepared runtime
9. the notebook-executor gate, when a notebook is declared: `nbformat`,
   `nbclient` and `jupyter_client` must be importable and the notebook's
   own kernel must resolve to an installed kernelspec. Probed, never
   assumed — this cell installs only what the target declared, and the
   remedy a refusal names is that same declaration. Runs AFTER
   responsibility 7 for the same reason the accelerator gate does
10. the accelerator gate: the arriving capability must appear in the
   installed arch list, and any declared `accelerator.architectures`
   must be covered by that same installed list. This runs AFTER
   responsibility 7, never before — a refusal whose evidence was never
   written is unreadable no matter how early it fires, so `bootstrap.json`
   already carries the arriving device, the torch build and the arch
   list the verdict was computed from by the time this refuses
11. no service name anywhere, ever

Importable and independently testable: every responsibility above is a
plain function, and `bootstrap()` composes them. Nothing runs at import
time — the orchestrating call sits behind `if __name__ == "__main__":`,
the state a notebook cell's own top-level code runs in (a Jupyter
kernel's namespace has `__name__ == "__main__"`), so importing this file
under a different module name never fires it. That is what lets the forge
suite drive `bootstrap()` and every helper directly against fake configs,
in-process — the whole justification `jobfolder.py` gives for shipping
this as a byte-for-byte copy rather than a per-job embedded prose cell.

Every git call goes through `_run_git()`, the single composition point:
`shell=False`, list argv, a PATH-only env allowlist, an explicit timeout,
non-zero exit is a refusal.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class BootstrapError(Exception):
    """A refusal: the run configuration, the declared code, or this
    runtime's hardware is missing or invalid. `bootstrap()` is the only
    place that turns one of these into `SystemExit`.
    """


class AcceleratorError(BootstrapError):
    """Responsibility 8's refusal: the arriving accelerator cannot run
    this build's kernels, or the declared architectures are not covered
    by the torch build actually installed. A subclass of
    `BootstrapError` so `bootstrap()`'s existing `except BootstrapError`
    converts it to `SystemExit` the same way as every other refusal —
    no second exception-handling path to keep in step.
    """


CONFIG_FILENAME = "run-config.json"
BOOTSTRAP_OUTPUT_FILENAME = "bootstrap.json"
CLONE_DIRNAME = "clone"
SRC_DIRNAME = "src"
RUN_CONFIG_SCHEMA_VERSION = 1
REQUIRED_RUN_CONFIG_FIELDS = ("schemaVersion", "commit", "repo", "clonePaths", "run")

# The whole allowlist a git subprocess's environment is built from — never
# `os.environ` forwarded wholesale, the same restraint every other
# subprocess call in this skill applies to its own child environment.
GIT_ENV_ALLOWLIST = ("PATH",)
GIT_TIMEOUT_SECONDS = 120.0

# The credential material a credentialed submission stages beside the
# executor (S3): an askpass script and the token file it reads. The names
# are declared in THREE files by convention — the backend adapter (the
# uploader and the fetch-time refusal), the executor asset (chmod,
# deletion, manifest exclusion) and this one (the clone's own use and
# deletion) — deliberately not shared by import: no module above the seam
# may name a backend, and the asset files are byte-copies, never importers
# of each other. `git-askpass.sh` prints the token file's bytes for
# whichever prompt git asks; HTTPS token auth on the hosts this skill
# targets accepts the token as the username with any password.
REPO_CREDENTIAL_ASKPASS_FILENAME = "git-askpass.sh"
REPO_CREDENTIAL_TOKEN_FILENAME = "git-askpass-token"

# The code bundle a job may carry instead of cloning (`generate-job
# --code-bundle`): staged beside `run-config.json` under this one name and
# recorded there as `codeBundle: {file, format, sha256, bytes}`. The name
# is duplicated by convention in the generator and the backend that ships
# it, never shared by import, for the same reason as the names above.
CODE_BUNDLE_FILENAME = "code-bundle.tar.gz"


def _config_path(base_dir: str | Path | None) -> Path:
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    return base / CONFIG_FILENAME


def load_run_config(base_dir: str | Path | None = None) -> dict:
    """Read `run-config.json` beside the notebook (or `base_dir`, for a
    test) and validate its schema/version — responsibility 1.
    """
    path = _config_path(base_dir)
    if not path.is_file():
        raise BootstrapError(
            f"config missing: {path} does not exist; nothing to bootstrap from"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BootstrapError(f"config missing: {path} is not valid JSON: {exc}") from exc
    _validate_run_config(payload)
    return payload


def _validate_run_config(run_config: object) -> None:
    if not isinstance(run_config, dict):
        raise BootstrapError("config missing: run-config.json must decode to a JSON object")
    missing = [f for f in REQUIRED_RUN_CONFIG_FIELDS if f not in run_config]
    if missing:
        raise BootstrapError(
            f"config missing: run-config.json missing required fields: {missing}"
        )
    if run_config.get("schemaVersion") != RUN_CONFIG_SCHEMA_VERSION:
        raise BootstrapError(
            f"config missing: run-config.json declares schemaVersion "
            f"{run_config.get('schemaVersion')!r}; this bootstrap reads only "
            f"{RUN_CONFIG_SCHEMA_VERSION}"
        )
    run_block = run_config.get("run")
    if not isinstance(run_block, dict):
        raise BootstrapError(
            "config missing: run-config.json's 'run' block must be an object"
        )
    # Exactly one of the two shapes, and this cell refuses rather than
    # guesses at a block that declares neither or both. The refusal has to
    # exist HERE and not only in the generator: this cell reads whatever
    # `run-config.json` the kernel was actually handed, and a config that
    # acquired a shapeless `run` block any other way (hand-edited, staged
    # by an older generator) reaches this file and nothing else.
    has_callable = bool(run_block.get("module"))
    has_notebook = bool(run_block.get("notebook"))
    if has_callable and has_notebook:
        raise BootstrapError(
            "config missing: run-config.json's 'run' block declares BOTH a "
            "'module' and a 'notebook'; a run has exactly one shape"
        )
    if not (has_callable or has_notebook):
        raise BootstrapError(
            "config missing: run-config.json's 'run' block must declare "
            "either a 'module' or a 'notebook'"
        )


def _run_git(
    args: Sequence[str],
    *,
    cwd: str | Path,
    timeout: float = GIT_TIMEOUT_SECONDS,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """The single composition point for every git invocation this cell
    makes. `shell=False` with a list argv means a value carrying shell
    metacharacters reaches `argv` as one element and is never evaluated —
    no shell is ever invoked to evaluate it. The environment is built from
    `GIT_ENV_ALLOWLIST` alone, never this process's own `os.environ`
    forwarded wholesale. A non-zero exit or an expired timeout raises
    `BootstrapError` rather than being silently ignored.

    `extra_env` (S3) is a caller-supplied mapping merged into the child's
    environment AFTER the allowlist — the credential-aware clone's
    `GIT_ASKPASS`, and never anything else. It is a separate channel from
    `GIT_ENV_ALLOWLIST` on purpose: the allowlist stays `("PATH",)`, and
    the askpass path is an explicit per-call decision rather than a
    widening of it. `None` (every credentialless clone) means the child's
    environment is built exactly as it was before this parameter existed.
    """
    argv = ["git", *args]
    env = {name: os.environ[name] for name in GIT_ENV_ALLOWLIST if name in os.environ}
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            argv,
            shell=False,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError(f"git {' '.join(args)} timed out after {timeout}s") from exc
    except OSError as exc:
        raise BootstrapError(f"could not run git: {exc}") from exc
    if result.returncode != 0:
        raise BootstrapError(
            f"git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result


def clone_repo(
    run_config: Mapping[str, Any],
    clone_dir: str | Path,
    *,
    askpass: str | Path | None = None,
) -> Path:
    """Sparse-clone the declared repo at the pinned commit — responsibility
    2 — every step through `_run_git()` alone: `init`, `remote add`,
    `sparse-checkout set <clonePaths>`, `fetch --depth 1 origin <commit>`,
    `checkout FETCH_HEAD`.

    `askpass` (S3) is the absolute path to the staged `git-askpass.sh`
    when — and only when — the submission carried a repository credential.
    With it, every git call this function makes carries
    `GIT_ASKPASS=<that path>` through `_run_git()`'s `extra_env`, and
    `run-config.json`'s `repo.url` must be `https://` — refused BEFORE the
    first git call otherwise, because a hand-edited config can bypass
    generation and a credential can only travel over TLS (the runner has
    no SSH agent and no key). The two material files are deleted in a
    `finally` immediately after the clone attempt, success or failure:
    that is D6's deletion point — before anything else in cell 0 proceeds
    — and a failed unlink is a printed `warning:` line, never a raise,
    because the clone's own outcome must not be masked and the executor's
    own fallback deletion plus its manifest exclusion already bound the
    residue. `None` (every credentialless job, and every run of a backend
    that stages no credential material) is byte-identical to before this
    parameter existed: no `GIT_ASKPASS`, no deletion, no URL gate.
    """
    clone_dir = Path(clone_dir)
    clone_dir.mkdir(parents=True, exist_ok=True)
    repo = run_config["repo"]
    commit = run_config["commit"]
    clone_paths = list(run_config["clonePaths"])

    askpass_path: Path | None = Path(askpass) if askpass is not None else None
    if askpass_path is not None:
        url = str(repo.get("url", ""))
        if not url.startswith("https://"):
            raise BootstrapError(
                f"repo credential refused: run-config.json's repo.url "
                f"{url!r} is not an https:// URL, and a staged repository "
                "credential can only travel over HTTPS — the runner's clone "
                "has no SSH agent and no key. Refusing before any git call."
            )
        clone_env: Mapping[str, str] | None = {
            "GIT_ASKPASS": str(askpass_path.resolve())
        }
    else:
        clone_env = None

    def _git(args: Sequence[str]) -> subprocess.CompletedProcess:
        return _run_git(args, cwd=clone_dir, extra_env=clone_env)

    try:
        _git(["init"])
        _git(["remote", "add", "origin", repo["url"]])
        _git(["sparse-checkout", "set", *clone_paths])
        _git(["fetch", "--depth", "1", "origin", commit])
        _git(["checkout", "FETCH_HEAD"])
    finally:
        if askpass_path is not None:
            for material in (
                askpass_path,
                askpass_path.parent / REPO_CREDENTIAL_TOKEN_FILENAME,
            ):
                try:
                    material.unlink()
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    print(
                        f"warning: could not delete credential material "
                        f"{material}: {exc}"
                    )
    return clone_dir


def _bundle_entry_refusal(member: tarfile.TarInfo, clone_paths: Sequence[str]) -> str | None:
    """Why one archive entry may not be unpacked, or `None`: only regular
    files and directories, relative names with no `..`, under a declared
    clone path (a directory may also be one of their ancestors). The same
    rule the generator applied, held again here because this cell unpacks
    whatever bytes it was actually handed."""
    name = member.name
    parts = name.split("/")
    if not name or name.startswith("/") or ".." in parts:
        return f"{name!r} is absolute or escapes the clone with '..'"
    if ".git" in parts:
        return f"{name!r} lies inside a .git directory"
    if not (member.isfile() or member.isdir()):
        return f"{name!r} is a link or special file"
    stripped = name.rstrip("/")
    under = any(stripped == path or stripped.startswith(path.rstrip("/") + "/")
                for path in clone_paths)
    ancestor = member.isdir() and any(
        path.startswith(stripped + "/") for path in clone_paths)
    if not (under or ancestor):
        return f"{name!r} lies outside the declared clone paths"
    return None


def unpack_code_bundle(
    run_config: Mapping[str, Any], base_dir: str | Path, clone_dir: str | Path
) -> Path:
    """Unpack the job's own code bundle into `clone_dir` — responsibility
    2's other form, for a job that carried its pinned code instead of
    cloning it. The bundle's sha256 is checked against `codeBundle.sha256`
    BEFORE a byte is unpacked (`CODE_BUNDLE_MISMATCH` otherwise), and every
    entry is checked before any is written (`CODE_BUNDLE_UNSAFE_ENTRY`):
    nothing absolute, nothing with `..`, no link or special file, nothing
    outside the declared clone paths, nothing inside a `.git` directory,
    and nothing that resolves outside `clone_dir`. Files are written one by
    one from their own bytes, never through `extractall`. No git call, no
    network, no credential.

    After a verified unpack it writes `<clone>/.git/HEAD` holding the pinned
    commit and nothing else: the shape of the detached checkout a clone
    leaves, so a notebook's own repository-root cell
    (`notebook_repo_root.py`), which reads that file to prove the root is
    at `FORGE_CLONE_COMMIT`, resolves a bundled clone exactly as it
    resolves a cloned one — and still refuses one at any other commit.
    """
    block = run_config.get("codeBundle")
    if not isinstance(block, Mapping) or block.get("file") != CODE_BUNDLE_FILENAME:
        raise BootstrapError(
            f"CODE_BUNDLE_MISMATCH: run-config.json's codeBundle must name "
            f"{CODE_BUNDLE_FILENAME!r}"
        )
    path = Path(base_dir) / CODE_BUNDLE_FILENAME
    if not path.is_file():
        raise BootstrapError(
            f"CODE_BUNDLE_MISMATCH: {path} does not exist, but run-config.json "
            "declares a code bundle"
        )
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != block.get("sha256"):
        raise BootstrapError(
            f"CODE_BUNDLE_MISMATCH: {path} hashes to {actual}, but "
            f"run-config.json records {block.get('sha256')!r}; refusing to unpack"
        )
    clone_paths = list(run_config["clonePaths"])
    commit = str(run_config.get("commit", ""))
    if len(commit) not in (40, 64) or any(c not in "0123456789abcdef" for c in commit):
        raise BootstrapError(
            f"CODE_BUNDLE_MISMATCH: run-config.json's commit {commit!r} is not a "
            "full lowercase object name; refusing to unpack"
        )
    clone_root = Path(clone_dir).resolve()
    try:
        archive = tarfile.open(path, mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise BootstrapError(f"CODE_BUNDLE_MISMATCH: {path} is not a tar.gz: {exc}") from exc
    with archive:
        members = archive.getmembers()
        for member in members:
            why = _bundle_entry_refusal(member, clone_paths)
            if why is None:
                destination = (clone_root / member.name).resolve()
                if destination != clone_root and clone_root not in destination.parents:
                    why = f"{member.name!r} resolves outside the clone directory"
            if why is not None:
                raise BootstrapError(f"CODE_BUNDLE_UNSAFE_ENTRY: {why}; refusing to unpack")
        clone_root.mkdir(parents=True, exist_ok=True)
        for member in members:
            destination = clone_root / member.name
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise BootstrapError(f"CODE_BUNDLE_UNSAFE_ENTRY: {member.name!r} has no data")
            destination.write_bytes(source.read())
    git_dir = clone_root / ".git"
    git_dir.mkdir(exist_ok=True)
    (git_dir / "HEAD").write_text(commit + "\n", encoding="utf-8")
    return Path(clone_dir)


def materialize_code(run_config: Mapping[str, Any], base: Path) -> Path:
    """The pinned code, in `<base>/clone`: unpacked from the job's own code
    bundle when `run-config.json` declares one, cloned otherwise (with the
    staged askpass when there is one). Either way `bootstrap.json` and the
    run record the same `run-config.json` `commit`."""
    if run_config.get("codeBundle") is not None:
        return unpack_code_bundle(run_config, base, base / CLONE_DIRNAME)
    # S3/D6: the credential material is discovered by NAME at the
    # session-dir convention — `exec -f` has no argv/env channel, so
    # nothing can be injected through a process environment. Inert on
    # every credentialless run: a run-config with no staged askpass
    # beside it passes `None` and behaves exactly as before this
    # existed.
    askpass = base / REPO_CREDENTIAL_ASKPASS_FILENAME
    return clone_repo(
        run_config,
        base / CLONE_DIRNAME,
        askpass=askpass if askpass.is_file() else None,
    )


def add_clone_to_path(clone_dir: str | Path) -> Path:
    """`sys.path.insert(0, <clone>/src)` — responsibility 3."""
    src_dir = (Path(clone_dir) / SRC_DIRNAME).resolve()
    sys.path.insert(0, str(src_dir))
    return src_dir


# The whole allowlist a pip subprocess's environment is built from —
# never `os.environ` forwarded wholesale, the same restraint
# `GIT_ENV_ALLOWLIST` above already applies to its own child environment.
# A separate constant, deliberately: this cell's pip invocation and its
# git invocations are different subprocess families, and each holds this
# discipline on its own rather than sharing one name that could drift for
# the wrong reason.
PIP_ENV_ALLOWLIST = ("PATH",)
PIP_INSTALL_TIMEOUT_SECONDS = 600.0


def _validate_requirement_specifier(spec: str) -> str:
    """A requirement specifier is data, never a flag. `pip install` reads
    each positional argv element as either a package specifier or, when
    it begins with `-`, an option of its own — a declared specifier
    shaped like `--index-url https://evil.invalid` would occupy the same
    argv position as a real package name and silently redirect the whole
    install to an attacker-controlled index. Refusing any specifier
    beginning with `-` is what keeps a declared `requirements` list
    unable to smuggle a flag this way. Nothing else about the string is
    inspected: shell metacharacters elsewhere in a specifier reach pip's
    argv as inert data, the same `shell=False`, list-argv guarantee
    `_run_git()` already gives every value this cell passes to git.
    """
    if not isinstance(spec, str) or not spec or spec.startswith("-"):
        raise BootstrapError(
            f"environment.install refuses requirement specifier {spec!r}: "
            "a specifier beginning with '-' would be read by pip as an "
            "option, not a package to install"
        )
    return spec


def _run_pip(args: Sequence[str], *, timeout: float = PIP_INSTALL_TIMEOUT_SECONDS) -> None:
    """The single composition point for the one pip invocation this cell
    makes — the same discipline `_run_git()` already holds: `shell=False`
    with a list argv, so a value carrying shell metacharacters reaches
    argv as one element and is never evaluated by a shell; the
    environment built from `PIP_ENV_ALLOWLIST` alone, never this
    process's own `os.environ` forwarded wholesale; an explicit timeout;
    a non-zero exit is a refusal, never silently ignored.
    """
    argv = [sys.executable, "-m", "pip", *args]
    env = {name: os.environ[name] for name in PIP_ENV_ALLOWLIST if name in os.environ}
    try:
        result = subprocess.run(
            argv,
            shell=False,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError(
            f"environment install timed out after {timeout}s running pip "
            f"{' '.join(args)}"
        ) from exc
    except OSError as exc:
        raise BootstrapError(f"could not run pip: {exc}") from exc
    if result.returncode != 0:
        raise BootstrapError(
            f"pip {' '.join(args)} exited {result.returncode}: "
            f"{result.stderr.strip()}"
        )


def install_environment(run_config: Mapping[str, Any]) -> None:
    """Responsibility 4: install the dual-architecture torch build (or
    whatever else the target declares) BEFORE responsibility 5 imports
    the target's own modules — those imports pull in the tensor library
    this step installs, so installing after that point would be too
    late.

    Reads `run-config.json`'s additive `environment.install:
    {requirements[], indexUrl}` (Decision 3). Additive: an older config
    with no `environment` block, or no `install` block within it,
    installs nothing at all — this is a no-op, exactly as this cell
    behaved before the field existed. This module names only those two
    fields and never a package: it does not know which tensor-library
    build a target needs, only that the target declared one.

    Every requirement specifier is validated by
    `_validate_requirement_specifier()` before any argv is built, and the
    whole install runs through `_run_pip()`, the single composition point
    matching `_run_git()`'s own discipline: `sys.executable -m pip
    install`, with `--index-url <indexUrl>` first when declared, then
    each requirement its own argv element — never one opaque command
    string.
    """
    environment = run_config.get("environment")
    install = environment.get("install") if isinstance(environment, Mapping) else None
    if not isinstance(install, Mapping):
        return
    requirements = [
        _validate_requirement_specifier(spec)
        for spec in (install.get("requirements") or [])
    ]
    if not requirements:
        raise BootstrapError(
            "config missing: environment.install declares no requirements "
            "to install"
        )
    index_url = install.get("indexUrl")
    args = ["install"]
    if index_url:
        args += ["--index-url", str(index_url)]
    args += requirements
    _run_pip(args)


def declared_modules(run_config: Mapping[str, Any]) -> list[str]:
    """Every module `run-config.json` names as an entry point: the normal
    `run.module`, plus `run.smoke.module` when present — both get the
    same `__file__`-under-clone proof at bootstrap time, since either one
    could be the module cell 1 actually calls.
    """
    run_block = run_config["run"]
    modules = []
    if run_block.get("module"):
        modules.append(run_block["module"])
    smoke = run_block.get("smoke")
    if isinstance(smoke, dict) and smoke.get("module"):
        modules.append(smoke["module"])
    return modules


def declared_notebooks(run_config: Mapping[str, Any]) -> list[str]:
    """Every notebook `run-config.json` names as an entry point: the normal
    `run.notebook`, plus `run.smoke.notebook` when present — the notebook
    shape's exact counterpart to `declared_modules()` above, and read the
    same way, since either one could be what cell 1 actually runs.
    """
    run_block = run_config["run"]
    notebooks = []
    if run_block.get("notebook"):
        notebooks.append(run_block["notebook"])
    smoke = run_block.get("smoke")
    if isinstance(smoke, dict) and smoke.get("notebook"):
        notebooks.append(smoke["notebook"])
    return notebooks


def verify_imports_under_clone(
    modules: Sequence[str],
    src_dir: str | Path,
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> dict[str, str]:
    """Import each declared module and assert its `__file__` resolves
    under the clone's own `src` — responsibility 5, the "pip-installed
    copy" refusal. `.resolve()` on both sides: a temp path traversing a
    `/var` -> `/private/var`-style symlink must compare equal either way.
    """
    resolved_src = Path(src_dir).resolve()
    verified: dict[str, str] = {}
    for name in modules:
        try:
            module = import_module(name)
        except ImportError as exc:
            raise BootstrapError(
                f"code missing: declared module {name!r} could not be imported: {exc}"
            ) from exc
        module_file = getattr(module, "__file__", None)
        if not module_file:
            raise BootstrapError(
                f"code missing: module {name!r} carries no __file__; its location "
                "cannot be verified"
            )
        resolved_file = Path(module_file).resolve()
        try:
            resolved_file.relative_to(resolved_src)
        except ValueError:
            raise BootstrapError(
                f"code missing: module {name!r} resolved to {resolved_file}, "
                f"outside the clone's own src at {resolved_src} — refusing the "
                "'pip-installed copy' case"
            )
        verified[name] = str(resolved_file)
    return verified


DEFAULT_KERNEL_NAME = "python3"

# The three modules a notebook run needs on the worker, and the whole of
# what `check_notebook_executor()` probes for. `nbformat` reads and writes
# the notebook, `nbclient` executes it, and `jupyter_client` is what
# resolves a kernel NAME to an installed kernel — the third one is not
# redundant with the other two: a runtime can have both readers and no
# kernelspec at all, which is exactly the shape of the failure that has
# already cost this skill a real push.
NOTEBOOK_EXECUTOR_MODULES = ("nbformat", "nbclient", "jupyter_client")


def verify_notebooks_under_clone(
    notebooks: Sequence[str], clone_dir: str | Path
) -> dict[str, dict]:
    """Prove every declared notebook actually ARRIVED in the clone, and
    read the kernel each one asks for — the notebook shape's exact
    counterpart to `verify_imports_under_clone()`, and it exists for the
    same reason that one does.

    A module gets its `__file__` checked because an importable copy from
    somewhere else on `sys.path` would silently run unpinned code. A
    notebook cannot be imported at all, so the equivalent proof is that
    the file is where the pinned checkout should have put it. `git
    sparse-checkout` reports NOTHING for a path its declared patterns do
    not cover, so the failure this refuses against is silent by
    construction: the clone succeeds, the kernel starts, and the run dies
    at the moment it goes looking for the notebook — with the quota
    already spent.

    The kernel name is read from each notebook's own
    `metadata.kernelspec.name`, defaulting to `DEFAULT_KERNEL_NAME` when
    the notebook declares none. It is read HERE rather than in
    `check_notebook_executor()` so the capability gate is handed a fact
    off the pinned notebook instead of re-opening the file to guess one.
    """
    resolved_clone = Path(clone_dir).resolve()
    verified: dict[str, dict] = {}
    for name in notebooks:
        candidate = (resolved_clone / name).resolve()
        try:
            candidate.relative_to(resolved_clone)
        except ValueError:
            raise BootstrapError(
                f"code missing: declared notebook {name!r} resolves to "
                f"{candidate}, outside the clone at {resolved_clone}"
            ) from None
        if not candidate.is_file():
            raise BootstrapError(
                f"code missing: declared notebook {name!r} is not at "
                f"{candidate}; the sparse checkout delivered nothing for it, "
                "which it does silently for any path the declared clone "
                "paths do not cover"
            )
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapError(
                f"code missing: declared notebook {name!r} at {candidate} is "
                f"not readable as a notebook: {exc}"
            ) from exc
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        kernelspec = metadata.get("kernelspec") if isinstance(metadata, dict) else None
        kernel = None
        if isinstance(kernelspec, dict):
            kernel = kernelspec.get("name")
        verified[name] = {
            "path": str(candidate),
            "kernel": str(kernel) if kernel else DEFAULT_KERNEL_NAME,
        }
    return verified


def check_notebook_executor(
    notebooks: Mapping[str, dict],
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> None:
    """The notebook-executor gate: refuse, here, when this runtime cannot
    execute a notebook — never after the run is already under way.

    This cell installs only what `run-config.json`'s `environment.install`
    declares, and nothing in this skill can know what a given worker image
    ships. So the mechanism is not ASSUMED to be present: it is probed,
    and its absence is a refusal that names the remedy, which is the
    target declaring it in `environment.install` like any other
    dependency. Responsibility 4 runs before this, so a declared install
    is what this gate then measures.

    Three probes, because three different absences produce the same
    unusable runtime:

    - `nbformat`/`nbclient` — the reader and the executor themselves.
    - `jupyter_client` and an actual kernelspec for each notebook's own
      declared kernel. A missing kernelspec is not a hypothetical: a
      notebook with no resolvable kernel made the service's own runner
      refuse before a single cell executed, and that was discovered only
      after a real push with the quota already gone. The same failure,
      one layer in, is a notebook this cell hands to `nbclient` that
      names a kernel nothing here can start.

    A job that declares no notebook passes through untouched — no import
    is attempted, and a callable-shaped run keeps behaving exactly as it
    did before any of this existed.
    """
    if not notebooks:
        return
    for module_name in NOTEBOOK_EXECUTOR_MODULES:
        try:
            import_module(module_name)
        except ImportError as exc:
            raise BootstrapError(
                f"notebook executor missing: {module_name!r} is not importable "
                f"in this runtime, and this job declares a notebook run "
                f"({sorted(notebooks)}). Declare it in run-config.json's "
                f"environment.install (--environment-requirement) so it is "
                f"installed before this cell asks for it: {exc}"
            ) from exc
    kernelspec_module = import_module("jupyter_client.kernelspec")
    manager = kernelspec_module.KernelSpecManager()
    for name, info in sorted(notebooks.items()):
        kernel = info.get("kernel") or DEFAULT_KERNEL_NAME
        try:
            manager.get_kernel_spec(kernel)
        except Exception as exc:  # noqa: BLE001 - any resolution failure is the refusal
            raise BootstrapError(
                f"notebook executor missing: notebook {name!r} declares kernel "
                f"{kernel!r} and this runtime has no kernelspec for it "
                f"({type(exc).__name__}: {exc}); the notebook would be handed "
                "to an executor that cannot start a kernel for it"
            ) from exc


def _capability_to_arch(capability: tuple[int, int]) -> str:
    """`torch.cuda.get_device_capability()`'s `(major, minor)` pair,
    formatted the same way `torch.cuda.get_arch_list()` names its own
    entries (`sm_60`, `sm_75`, ...) — the one shared vocabulary the
    accelerator gate compares against.
    """
    major, minor = capability
    return f"sm_{major}{minor}"


def detect_hardware(
    *, import_module: Callable[[str], Any] = importlib.import_module
) -> dict[str, Any]:
    """Hardware detection — responsibility 6. `torch` not importable IS
    the refusal mapping for "hardware missing": no silent CPU fallback,
    because a silent fallback would mean this refusal branch could never
    actually fire.

    Beside `device` and `torch`, this also captures `archList` — the
    architectures THIS INSTALLED torch build actually ships kernels for
    (`torch.cuda.get_arch_list()`) — and `capability`, the arriving
    device's own capability formatted the same way. Both are what
    responsibility 9's accelerator gate compares; neither requires the
    declared `accelerator` block to exist, since the arch list a build
    installs is a fact about that build, not about what any job declared.
    A runtime with no CUDA device carries nothing to compare: `archList`
    is `[]` and `capability` is `None`.
    """
    try:
        torch = import_module("torch")
    except ImportError as exc:
        raise BootstrapError(
            "hardware missing: torch is not importable in this runtime"
        ) from exc
    cuda_available = bool(torch.cuda.is_available())
    device = {
        "kind": "cuda" if cuda_available else "cpu",
        "name": torch.cuda.get_device_name(0) if cuda_available else "cpu",
    }
    if cuda_available:
        arch_list = list(torch.cuda.get_arch_list())
        capability = _capability_to_arch(torch.cuda.get_device_capability(0))
    else:
        arch_list = []
        capability = None
    return {
        "device": device,
        "torch": str(torch.__version__),
        "archList": arch_list,
        "capability": capability,
    }


def write_bootstrap_output(
    base_dir: str | Path | None,
    *,
    commit: str,
    run_config: Mapping[str, Any],
    environment: Mapping[str, Any],
    imports: Mapping[str, str],
    notebooks: Mapping[str, dict] | None = None,
) -> Path:
    """`bootstrap.json` — responsibility 7: the commit, the config, the
    detected environment, and the resolved import locations responsibility
    4 just proved.

    `notebooks` carries the same proof for the notebook shape — each
    declared notebook's resolved location inside the clone and the kernel
    it asks for — and is written for the same reason `imports` is: the
    notebook-executor gate below refuses AFTER this file exists, so its
    evidence (which notebook, which kernel) is already readable on disk
    when it fires. Always present, `{}` for a callable-shaped run, never
    absent — an absent key and an empty one are different facts and only
    one of them is true here.
    """
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    payload = {
        "commit": commit,
        "config": dict(run_config),
        "environment": dict(environment),
        "imports": dict(imports),
        "notebooks": dict(notebooks or {}),
    }
    path = base / BOOTSTRAP_OUTPUT_FILENAME
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    return path


def check_accelerator(run_config: Mapping[str, Any], environment: Mapping[str, Any]) -> None:
    """The accelerator gate — responsibility 9, run only AFTER
    `write_bootstrap_output()` (see `bootstrap()` below). Two assertions:

    1. the arriving `capability` must appear in the INSTALLED `archList`
       — the physics check: can this build run on this card at all. It
       needs no declaration and runs whenever a capability was detected
       (a CPU-only runtime has none, and nothing to refuse here).
    2. the declared `accelerator.architectures`, when `run-config.json`
       declares an `accelerator` block, must be covered by that same
       installed `archList` — this is how the dual-architecture torch
       build gets VERIFIED rather than assumed. An older, undeclared
       config carries no `accelerator` block and this assertion is
       skipped entirely: additive, `schemaVersion` stays 1.
    """
    capability = environment.get("capability")
    arch_list = list(environment.get("archList") or [])
    if capability is not None and capability not in arch_list:
        raise AcceleratorError(
            f"accelerator mismatch: this runtime's capability {capability!r} "
            f"is not in the installed torch build's arch list {arch_list!r}; "
            "training would fail with no kernel image for this device"
        )
    accelerator = run_config.get("accelerator")
    if isinstance(accelerator, Mapping):
        declared = list(accelerator.get("architectures") or [])
        uncovered = [arch for arch in declared if arch not in arch_list]
        if uncovered:
            raise AcceleratorError(
                f"accelerator mismatch: declared architectures {uncovered} "
                f"are not covered by the installed torch build's arch list "
                f"{arch_list!r}; the dual-architecture build was assumed, "
                "never verified"
            )


def bootstrap(
    base_dir: str | Path | None = None,
    *,
    hardware_import: Callable[[str], Any] = importlib.import_module,
) -> dict[str, Any]:
    """The whole of cell 0, in the fixed order the design pins:
    config -> clone -> `sys.path` -> install -> imports -> notebooks ->
    hardware -> `bootstrap.json` -> the notebook-executor gate -> the
    accelerator gate.

    The two gates sit together after the write, and the notebook one is
    first only because it is the cheaper question. Both are runtime
    CAPABILITY questions — can this runtime execute what was declared —
    as against `verify_imports_under_clone()`/`verify_notebooks_under_
    clone()` above them, which ask whether the pinned code ARRIVED and
    therefore belong beside the clone that was supposed to deliver it.

    Any of config / code / hardware missing raises `SystemExit` on the
    spot — responsibility 8 — so cell 1 never runs against a
    half-prepared runtime. `hardware_import` exists only so a test can
    drive `detect_hardware()`'s success path without a real GPU or a real
    `torch` install; the default is the real `importlib.import_module`.

    `check_accelerator()` runs LAST inside this `try`, strictly after
    `write_bootstrap_output()` — never before. Cell 1 already cannot run
    after this cell's own `SystemExit`, so "before training" is
    structural regardless of ordering; what ordering decides is whether
    the refusal's own evidence (the arriving device, the torch build, the
    installed arch list the verdict was computed from) is still readable
    on disk once it fires. It always is, because it was written first.
    """
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    try:
        run_config = load_run_config(base)
        clone_dir = materialize_code(run_config, base)
        src_dir = add_clone_to_path(clone_dir)
        install_environment(run_config)
        modules = declared_modules(run_config)
        imports = verify_imports_under_clone(modules, src_dir)
        notebooks = verify_notebooks_under_clone(
            declared_notebooks(run_config), clone_dir
        )
        environment = detect_hardware(import_module=hardware_import)
        write_bootstrap_output(
            base,
            commit=run_config["commit"],
            run_config=run_config,
            environment=environment,
            imports=imports,
            notebooks=notebooks,
        )
        check_notebook_executor(notebooks)
        check_accelerator(run_config, environment)
    except BootstrapError as exc:
        raise SystemExit(f"bootstrap refused: {exc}") from exc
    return {
        "commit": run_config["commit"],
        "environment": environment,
        "imports": imports,
        "notebooks": notebooks,
    }


if __name__ == "__main__":
    bootstrap()
