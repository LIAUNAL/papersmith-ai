"""Artifact migrations: what a release changes beyond the files it ships.

``upgrade`` synchronizes framework FILES and preserves research state by not
touching it. That holds only while the shape of an artifact never changes. This
module carries a workspace's own artifacts — graph state, derived indices,
scaffolded topology — to the installed release's expectations, so the version a
workspace records is a claim about its artifacts and not only about its skills
tree.

Two kinds of migration share one mechanism:

* A **version-gated** migration (``applies_from`` set) is a shape change
  between releases. It runs once, when the workspace sits below the gate and
  the installed kit sits at or above it, and the applied ledger keeps it from
  running again.
* A **convergence** migration (``applies_from`` is ``None``) makes the
  workspace match the installed release regardless of its history. It is
  evaluated on every upgrade and is never recorded as finished, because the
  next release can change what there is to converge to. Its :meth:`Migration.
  plan` is a probe, so an already-satisfied workspace yields no actions and
  nothing is written.

Nothing here decides whether to write ``.papersmith/version``; ``upgrade`` owns
that, and it is the ordering that makes the whole thing honest — see
:func:`upgrade.upgrade`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .. import yamllite
from ..bridges.python import run_script
from ..errors import PapersmithError, SourceError, UserError
from . import fs, manifest
from .config import utc_timestamp

#: The applied-migration ledger, workspace state like ``runs_ledger.jsonl``
#: rather than configuration: ``config.json`` carries a validator and is
#: rewritten by ``upgrade`` on every run, and this is history.
LEDGER_REL = ".papersmith/migrations.json"
LEDGER_SCHEMA = 1


def version_order(value: str) -> tuple[int, ...] | None:
    """``value`` as an orderable tuple, or ``None`` when it carries no order.

    Only the leading dot-separated run of integers is read, so ``0.2.0rc1``
    orders beside ``0.2.0`` rather than refusing: a prerelease suffix is a claim
    this function is not equipped to rank, and treating the two as equal
    declines to guess in the direction that blocks nothing. A value with no
    leading integer at all — a branch name, a build label, an empty string —
    returns ``None``, because there is no order to report and inventing one is
    how a downgrade gets waved through.

    Lives here rather than in ``upgrade`` because two callers now need it: the
    downgrade guard and the migration gate, which refuse for the same reason.
    """
    parts: list[int] = []
    for chunk in value.strip().split("."):
        digits = ""
        for character in chunk:
            if not character.isdigit():
                break
            digits += character
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or None


class Migration:
    """One artifact change a release requires of an existing workspace.

    Subclasses set :attr:`id` — stable forever, because the ledger stores it —
    a one-line :attr:`summary`, and :attr:`applies_from` when the change
    belongs to a specific release. They implement :meth:`plan` as a read-only
    probe and :meth:`apply` as the writer.

    Neither method may raise for a condition the workspace can be in. A missing
    script, an unreadable artifact or a refusing filesystem is a *failure
    returned* by :meth:`apply`, because a migration that raises aborts a run
    that has already synchronized files, and the operator is left with no
    report of what did happen.
    """

    #: Stable identity recorded in the ledger. Renaming one re-runs it.
    id: str = ""
    #: The release whose shape this migration establishes, or ``None`` for a
    #: convergence step with no gate.
    applies_from: str | None = None
    #: One line, shown by ``--plan-migrations`` and by the upgrade report.
    summary: str = ""

    def plan(self, workspace: Path) -> list[str]:
        """Human-readable actions this migration would take, read-only.

        An empty list means the workspace already satisfies it; ``apply`` is
        then never called.
        """
        raise NotImplementedError

    def apply(self, workspace: Path) -> tuple[list[str], list[str]]:
        """Perform the migration. Returns ``(actions_done, failures)``."""
        raise NotImplementedError


@dataclass(frozen=True)
class Outcome:
    """What one migration did, and why it could not finish."""

    migration_id: str
    applies_from: str | None
    actions: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    summary: str = ""

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def recordable(self) -> bool:
        """Only a successful gated migration is finished for good."""
        return self.applies_from is not None and self.ok


@dataclass(frozen=True)
class RunReport:
    """The result of one migration pass, for ``upgrade`` to report and gate on."""

    applied: list[Outcome] = field(default_factory=list)
    satisfied: list[str] = field(default_factory=list)
    undetermined: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    recorded: bool = False

    @property
    def ok(self) -> bool:
        """Undetermined is not failure: nothing was attempted and nothing lied."""
        return not self.failures


@dataclass(frozen=True)
class PlanReport:
    """What a pass WOULD do, having written nothing."""

    pending: list[Outcome] = field(default_factory=list)
    satisfied: list[str] = field(default_factory=list)
    undetermined: list[str] = field(default_factory=list)


def ledger_path(workspace: Path) -> Path:
    return workspace / LEDGER_REL


def read_applied(workspace: Path) -> list[dict]:
    """Every migration this workspace has recorded as finished.

    A damaged ledger refuses rather than reading as empty, mirroring
    ``manifest.load_manifest``. The run ledger can afford to degrade because a
    lost run record costs a line of history; this one cannot, because reading
    it as empty re-applies every version-gated migration it was holding.
    """
    path = ledger_path(workspace)
    if not fs.is_regular_file(path):
        if fs.exists(path):
            raise UserError(f"corrupted migrations ledger {path}: not a readable regular file")
        return []
    text = fs.read_text(path)
    if text is None:
        raise UserError(f"corrupted migrations ledger {path}: unreadable or not valid UTF-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UserError(f"corrupted migrations ledger {path}: {exc}") from None
    if not isinstance(data, dict) or data.get("kind") != "migrations":
        raise UserError(f"corrupted migrations ledger {path}: missing migrations envelope")
    if data.get("schema") != LEDGER_SCHEMA:
        raise UserError(f"corrupted migrations ledger {path}: unsupported schema")
    applied = data.get("applied")
    if not isinstance(applied, list) or any(
        not isinstance(entry, dict) or not isinstance(entry.get("id"), str)
        for entry in applied
    ):
        raise UserError(f"corrupted migrations ledger {path}: malformed applied list")
    return applied


def _write_applied(workspace: Path, applied: Sequence[dict]) -> bool:
    """Record the ledger, or report that it could not be recorded.

    Returns False rather than raising: by the time this runs the migrations
    have already happened, and an unwritable ledger must be reported beside
    them instead of discarding the report of work that is already done. The
    caller refuses to advance the version marker, so a later run retries.
    """
    document = {
        "schema": LEDGER_SCHEMA,
        "kind": "migrations",
        "applied": list(applied),
        "updated_at": utc_timestamp(),
    }
    return fs.write_text(ledger_path(workspace), json.dumps(document, indent=2) + "\n")


def _gate_order(migration: Migration) -> tuple[int, ...]:
    order = version_order(migration.applies_from or "")
    if order is None:
        raise SourceError(
            f"migration {migration.id!r} declares an unorderable applies_from "
            f"({migration.applies_from!r}): a gate nobody can place is a defect "
            "in the installed framework, not in this workspace")
    return order


def _select(registry: Sequence[Migration], *, recorded: str, kit_version: str,
            applied_ids: set[str]) -> tuple[list[Migration], list[str]]:
    """Partition the registry into what to evaluate and what cannot be placed.

    Registry order is preserved, because a later migration may depend on an
    earlier one having run.
    """
    pending: list[Migration] = []
    undetermined: list[str] = []
    recorded_order = version_order(recorded)
    kit_order = version_order(kit_version)
    for migration in registry:
        if migration.applies_from is None:
            # Convergence: it asks the filesystem, so no version can withhold it.
            pending.append(migration)
            continue
        gate = _gate_order(migration)
        if migration.id in applied_ids:
            continue
        if kit_order is None or recorded_order is None:
            # Either side missing leaves the gate unplaceable. Reported, never
            # applied — the refusal `_refuse_a_downgrade` makes for files.
            undetermined.append(migration.id)
            continue
        if kit_order < gate:
            # The release that introduced this migration has not reached this
            # workspace; its artifacts would outrun its files.
            continue
        if recorded_order >= gate:
            continue
        pending.append(migration)
    return pending, undetermined


def plan(workspace: Path, *, recorded: str, kit_version: str,
         registry: Sequence[Migration] | None = None) -> PlanReport:
    """What a migration pass would do, having written nothing."""
    entries = REGISTRY if registry is None else registry
    applied_ids = {entry["id"] for entry in read_applied(workspace)}
    selected, undetermined = _select(entries, recorded=recorded, kit_version=kit_version,
                                     applied_ids=applied_ids)
    pending: list[Outcome] = []
    satisfied: list[str] = []
    for migration in selected:
        actions = migration.plan(workspace)
        if not actions:
            satisfied.append(migration.id)
            continue
        pending.append(Outcome(migration.id, migration.applies_from, tuple(actions),
                               summary=migration.summary))
    return PlanReport(pending=pending, satisfied=satisfied, undetermined=undetermined)


def run(workspace: Path, *, recorded: str, kit_version: str,
        registry: Sequence[Migration] | None = None) -> RunReport:
    """Apply every selected migration and report what happened.

    The ledger is read first and in full, so a damaged one refuses before any
    artifact is touched. Only successful gated migrations are recorded: a
    recorded failure would retire a migration that never ran, leaving old
    artifacts under a new version with nothing left to notice.
    """
    entries = REGISTRY if registry is None else registry
    ledger = read_applied(workspace)
    applied_ids = {entry["id"] for entry in ledger}
    selected, undetermined = _select(entries, recorded=recorded, kit_version=kit_version,
                                     applied_ids=applied_ids)

    applied: list[Outcome] = []
    satisfied: list[str] = []
    failures: list[str] = []
    additions: list[dict] = []
    for migration in selected:
        planned = migration.plan(workspace)
        if not planned:
            satisfied.append(migration.id)
            if migration.applies_from is not None:
                # The gate is passed with nothing to do. Recording it is what
                # keeps the probe from being re-run for every later release.
                additions.append(_entry(migration, kit_version, ()))
            continue
        actions, problems = migration.apply(workspace)
        outcome = Outcome(migration.id, migration.applies_from, tuple(actions), tuple(problems),
                          summary=migration.summary)
        applied.append(outcome)
        failures.extend(f"{migration.id}: {problem}" for problem in problems)
        if outcome.recordable:
            additions.append(_entry(migration, kit_version, outcome.actions))

    wrote = False
    if additions:
        wrote = _write_applied(workspace, [*ledger, *additions])
        if not wrote:
            failures.append(
                f"could not record applied migrations in {ledger_path(workspace)}; "
                "they would be re-applied on the next run")
    return RunReport(applied=applied, satisfied=satisfied, undetermined=undetermined,
                     failures=failures, recorded=wrote)


def _entry(migration: Migration, kit_version: str, actions: Sequence[str]) -> dict:
    return {
        "id": migration.id,
        "version": migration.applies_from,
        "kit_version": kit_version,
        "applied_at": utc_timestamp(),
        "actions": list(actions),
    }


# --------------------------------------------------------------------------
# The catalog. Everything above is mechanism; everything below is what this
# release asks of a workspace's own artifacts.
# --------------------------------------------------------------------------

#: The plausibility flow's graph pool, relative to a workspace.
GRAPH_POOL = "sota-pool"


class ScaffoldGraphPool(Migration):
    """Give an existing workspace the graph pool its release now scaffolds.

    ``init`` creates ``sota-pool/.gitkeep`` from this release on, so every
    workspace made after it already satisfies this. A workspace made before it
    cannot be reached by any other mechanism: ``upgrade`` synchronizes kit
    files and renders projections, and this directory is neither — it is not in
    ``KIT_ENTRIES``, so a kit can never ship it, and no generator derives it.

    It is convergence rather than version-gated on purpose. The claim it makes
    is about the workspace's shape, which the filesystem answers directly, and
    a probe that asks is correct for a workspace at any history — including one
    whose recorded version was lost, which is exactly the damaged workspace
    ``upgrade`` exists to repair.

    It scaffolds the folder and stops. The pool holds research state the
    ``sota-scout`` and ``sota-grapher`` agents produce, and rewriting an atlas
    would destroy the work the folder exists for.
    """

    id = "sota-pool-scaffold"
    summary = "scaffold sota-pool/ so the graph pool travels like every other drop-zone"

    def _keepfile(self, workspace: Path) -> Path:
        return workspace / GRAPH_POOL / ".gitkeep"

    def plan(self, workspace: Path) -> list[str]:
        if fs.is_regular_file(self._keepfile(workspace)):
            return []
        return [f"create {GRAPH_POOL}/.gitkeep"]

    def apply(self, workspace: Path) -> tuple[list[str], list[str]]:
        keepfile = self._keepfile(workspace)
        # ``fs.write_text`` creates the parents and reports an occupied or
        # unwritable path rather than raising, which is what this contract
        # needs: a migration that raises aborts a run that has already
        # synchronized files and leaves no report of what did happen.
        if not fs.write_text(keepfile, ""):
            return [], [f"could not create {GRAPH_POOL}/.gitkeep: "
                        f"{workspace / GRAPH_POOL} is occupied by something "
                        "other than a writable directory"]
        return [f"created {GRAPH_POOL}/.gitkeep"], []


class RefreshRenderedAtlas(Migration):
    """Re-render ``sota-pool/atlas.html`` when the release changed what makes it.

    The page is DERIVED, and both of its producers are kit files:
    ``render_atlas.py`` builds it and inlines ``atlas3d.bundle.js`` whole. So a
    release that ships either leaves the rendered graph stale while every file
    around it moved, and nothing in the workspace notices — the one artifact
    gap that is visible on ``main`` today rather than waiting for a future
    shape change.

    Staleness is decided by a hash of the atlas, the renderer and the viewer
    bundle, recorded in ``sota-pool/.atlas-render.json``, not by comparing
    modification times. A copy's mtime says when the file was written, which an
    ``upgrade`` rewrites for reasons that have nothing to do with the page; the
    same reasoning the manifest already applies to framework files. A stamp
    that is missing or unreadable reads as *unknown*, which re-renders: the
    cost is one deterministic rebuild, and the alternative is trusting a page
    nobody can place.

    The atlas itself is never written. This migration reads research state and
    rebuilds only the view of it.
    """

    id = "atlas-render-refresh"
    summary = "re-render sota-pool/atlas.html when its renderer or viewer bundle moved"

    ATLAS = f"{GRAPH_POOL}/atlas.json"
    PAGE = f"{GRAPH_POOL}/atlas.html"
    STAMP = f"{GRAPH_POOL}/.atlas-render.json"
    RENDERER = "skills/plausibility/scripts/render_atlas.py"
    VIEWER = "skills/plausibility/assets/atlas3d.bundle.js"

    def _fingerprint(self, workspace: Path) -> dict[str, str | None]:
        return {
            "atlas": manifest.sha256_if_readable(workspace / self.ATLAS),
            "renderer": manifest.sha256_if_readable(workspace / self.RENDERER),
            "viewer": manifest.sha256_if_readable(workspace / self.VIEWER),
        }

    def _recorded(self, workspace: Path) -> dict | None:
        """The stamp, or ``None`` for "unknown" — which re-renders."""
        text = fs.read_text(workspace / self.STAMP)
        if text is None:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def plan(self, workspace: Path) -> list[str]:
        if not fs.is_regular_file(workspace / self.ATLAS):
            # The pool is empty until the grapher fills it. Rendering a page
            # from an atlas that does not exist would invent a graph.
            return []
        if not fs.is_regular_file(workspace / self.PAGE):
            return [f"render {self.PAGE} from {self.ATLAS}"]
        recorded = self._recorded(workspace)
        if recorded is not None and all(
                recorded.get(key) == value
                for key, value in self._fingerprint(workspace).items()):
            return []
        return [f"re-render {self.PAGE}: its atlas, renderer or viewer bundle moved"]

    def apply(self, workspace: Path) -> tuple[list[str], list[str]]:
        try:
            completed = run_script(
                workspace, self.RENDERER,
                [str(workspace / self.ATLAS), "--out", str(workspace / self.PAGE)],
                timeout=300)
        except PapersmithError as error:
            # A missing script or a timeout is typed, and it belongs in the
            # report rather than aborting a run that already moved files.
            return [], [f"could not run {self.RENDERER}: {error}"]
        if completed.returncode != 0:
            # The renderer speaks in typed codes on stderr — ATLAS_NOT_JSON,
            # SYSTEMS_NOT_A_NONEMPTY_LIST, ATLAS_VIEWER_MISSING. Carry its own
            # last word through instead of restating it less precisely.
            lines = (completed.stderr or completed.stdout or "").strip().splitlines()
            reason = lines[-1].strip() if lines else f"exit {completed.returncode}"
            return [], [f"{self.RENDERER} refused {self.ATLAS}: {reason}"]
        if not fs.write_text(workspace / self.STAMP,
                             json.dumps(self._fingerprint(workspace), indent=2) + "\n"):
            return ([f"rendered {self.PAGE}"],
                    [f"could not record {self.STAMP}, so the page will be "
                     "re-rendered on every run until that path is writable"])
        return [f"rendered {self.PAGE}"], []


class RetireLegacyCommand(Migration):
    """Point MCP servers that still launch ``papersmith`` at ``smith``.

    The ``papersmith`` console script — an alias of ``smith`` since 0.19.0 — is
    no longer installed. From 0.2.0 to 0.18.x ``smith mcp print-config`` printed,
    and ``docs/mcp.md`` told operators to paste, ``"command": "papersmith"`` into
    their harness's MCP file. Such an entry now fails to start, and nothing in
    the workspace says why.

    Those files belong to the workspace: ``upgrade`` never overwrites them
    (``PRESERVE_PATTERNS``) and ``ensure_mcp_servers`` keeps every server it does
    not manage, so this is the one mechanism that reaches them. It rewrites
    exactly one field, the ``command`` of a server whose command is the bare
    name the old docs printed, under any key, and leaves every other server,
    key and argument as written. An explicit path (``/opt/tools/papersmith``)
    may be the operator's own wrapper and is left alone, as is a file that is
    not a JSON object: ``ensure_mcp_servers`` already warns about that one.

    It is convergence, not version-gated, for the reason ``ScaffoldGraphPool``
    gives: the files answer the question directly, at any history.
    """

    id = "mcp-legacy-papersmith-command"
    summary = "point MCP servers that still launch the removed `papersmith` command at `smith`"

    LEGACY = "papersmith"
    CURRENT = "smith"

    def _files(self) -> tuple[str, ...]:
        # Imported here: the generators module is the one owner of which file
        # each harness reads, and nothing at import time needs it.
        from ..generators import MCP_CONFIG_FILES

        return tuple(MCP_CONFIG_FILES.values())

    def _load(self, workspace: Path, relpath: str) -> dict | None:
        """The file as a JSON object with an ``mcpServers`` object, else ``None``."""
        path = workspace / relpath
        if not fs.is_regular_file(path):
            return None
        text = fs.read_text(path)
        if text is None:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict):
            return None
        return data

    def _stale(self, data: dict) -> list[str]:
        return [name for name, entry in data["mcpServers"].items()
                if isinstance(entry, dict) and entry.get("command") == self.LEGACY]

    def plan(self, workspace: Path) -> list[str]:
        actions: list[str] = []
        for relpath in self._files():
            data = self._load(workspace, relpath)
            if data is None:
                continue
            actions.extend(f"point {relpath}'s `{name}` server at `{self.CURRENT}`: "
                           f"the `{self.LEGACY}` command was removed"
                           for name in self._stale(data))
        return actions

    def apply(self, workspace: Path) -> tuple[list[str], list[str]]:
        done: list[str] = []
        failures: list[str] = []
        for relpath in self._files():
            data = self._load(workspace, relpath)
            if data is None:
                continue
            stale = self._stale(data)
            if not stale:
                continue
            for name in stale:
                data["mcpServers"][name]["command"] = self.CURRENT
            text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            if not fs.write_text(workspace / relpath, text):
                failures.append(f"could not rewrite {relpath}: point its "
                                f"{', '.join(f'`{name}`' for name in stale)} server(s) at "
                                f"`{self.CURRENT}` by hand")
                continue
            done.extend(f"pointed {relpath}'s `{name}` server at `{self.CURRENT}`"
                        for name in stale)
        return done, failures


class AstaConnectorRoles(Migration):
    """Name Ai2's Asta in an existing workspace's connector roles, once.

    From this release ``paper_writing.roles`` names ``asta`` first in
    ``resolution`` and in ``discovery``. A connector that needs a key is
    skipped while its key is not set, so a workspace without the Asta key
    behaves exactly as before; with the key (set in smith ui or with
    ``smith keys set asta``), Asta is asked first. ``papersmith.yaml`` belongs
    to the workspace and ``upgrade`` never rewrites it, so only this reaches
    the workspaces made before it.

    It edits only what it can recognize byte for byte: the block lists the
    template seeded (``resolution`` exactly openalex, crossref, arxiv;
    ``discovery`` exactly ``[]``). A list the operator changed is left exactly
    as written and named once in the report, with the line to add by hand.
    Line endings are kept, the result is checked with the orchestrator's own
    YAML reader before anything is written, and the write is atomic.

    Convergence, recorded by its own stamp (``.papersmith/connector-roles.json``)
    the way ``RefreshRenderedAtlas`` records its render: an operator who later
    removes ``asta`` is never overruled, and a customized list is reported
    once, not on every upgrade.
    """

    id = "paper-writing-asta-roles"
    summary = "name Ai2's Asta first in papersmith.yaml's resolution and discovery roles (used only with its key)"

    CONFIG = "papersmith.yaml"
    STAMP = ".papersmith/connector-roles.json"
    CANONICAL_RESOLUTION = ("      - openalex", "      - crossref", "      - arxiv")

    def _stamped(self, workspace: Path) -> bool:
        return fs.is_regular_file(workspace / self.STAMP)

    def _probe(self, workspace: Path) -> dict | None:
        """``{lines, roles, resolution, discovery}`` or ``None`` when there is
        nothing this migration may touch. ``resolution``/``discovery`` are
        ``"insert"``, ``"named"`` (already names asta), ``"custom"`` or ``None``
        (the key is absent)."""
        path = workspace / self.CONFIG
        if not fs.is_regular_file(path):
            return None
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        lines = text.splitlines(keepends=True)
        bare = [line.rstrip("\r\n") for line in lines]
        try:
            top = bare.index("paper_writing:")
        except ValueError:
            return None
        roles = None
        for index in range(top + 1, len(bare)):
            line = bare[index]
            if line and not line.startswith(" ") and not line.startswith("#"):
                break  # the next top-level key: no roles block
            if line == "  roles:":
                roles = index
                break
        if roles is None:
            return None
        state = {"lines": lines, "roles": roles, "resolution": None, "discovery": None}
        index = roles + 1
        while index < len(bare) and (bare[index].startswith("    ") or not bare[index].strip()
                                     or bare[index].lstrip().startswith("#")):
            line = bare[index]
            if line == "    resolution:":
                items = []
                cursor = index + 1
                while cursor < len(bare) and bare[cursor].startswith("      - "):
                    items.append(bare[cursor])
                    cursor += 1
                names = [item[len("      - "):].strip() for item in items]
                if "asta" in names:
                    state["resolution"] = "named"
                elif tuple(items) == self.CANONICAL_RESOLUTION:
                    state["resolution"] = ("insert", index)
                else:
                    state["resolution"] = "custom"
            elif line.startswith("    resolution:"):
                state["resolution"] = "named" if "asta" in line else "custom"
            elif line == "    discovery: []":
                state["discovery"] = ("insert", index)
            elif line == "    discovery:":
                cursor = index + 1
                names = []
                while cursor < len(bare) and bare[cursor].startswith("      - "):
                    names.append(bare[cursor][len("      - "):].strip())
                    cursor += 1
                state["discovery"] = "named" if "asta" in names else "custom"
            elif line.startswith("    discovery:"):
                state["discovery"] = "named" if "asta" in line else "custom"
            index += 1
        return state

    def plan(self, workspace: Path) -> list[str]:
        if self._stamped(workspace):
            return []
        state = self._probe(workspace)
        if state is None:
            return []
        actions = []
        for role in ("resolution", "discovery"):
            found = state[role]
            if isinstance(found, tuple):
                actions.append(f"name asta first in papersmith.yaml's paper_writing.roles.{role} "
                               "(skipped until its key is set in smith ui)")
            elif found == "custom":
                actions.append(f"leave paper_writing.roles.{role} as written: add `- asta` first by hand "
                               "to use Ai2's Asta once its key is set")
        return actions

    def apply(self, workspace: Path) -> tuple[list[str], list[str]]:
        state = self._probe(workspace)
        if state is None:
            return [], []
        lines = list(state["lines"])
        newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
        done: list[str] = []
        # Bottom-up, so an earlier insertion never shifts a later index.
        edits = sorted(((role, state[role][1]) for role in ("resolution", "discovery")
                        if isinstance(state[role], tuple)), key=lambda edit: -edit[1])
        for role, index in edits:
            if role == "resolution":
                lines.insert(index + 1, "      - asta" + newline)
            else:
                lines[index] = "    discovery:" + newline
                lines.insert(index + 1, "      - asta" + newline)
            done.append(f"named asta first in paper_writing.roles.{role}")
        manual = [f"paper_writing.roles.{role} was customized: add `- asta` first by hand to use it"
                  for role in ("resolution", "discovery") if state[role] == "custom"]
        if edits:
            text = "".join(lines)
            try:
                parsed = yamllite.loads(text.replace("\r\n", "\n"))
                roles = parsed["paper_writing"]["roles"]
                assert all(roles[role][0] == "asta" for role, _ in edits)
            except Exception as exc:  # noqa: BLE001 - never write what does not read back
                return [], [f"{self.CONFIG} was left unchanged: the edited roles did not read back ({exc})"]
            if not fs.replace_bytes(workspace / self.CONFIG, text.encode("utf-8")):
                return [], [f"could not rewrite {self.CONFIG}; add `- asta` first in its "
                            "paper_writing.roles.resolution and discovery by hand"]
        stamp = {"asta": {"named": [role for role, _ in edits], "manual": [m for m in manual]}}
        if not fs.write_text(workspace / self.STAMP, json.dumps(stamp, indent=2) + "\n"):
            return done + manual, [f"could not record {self.STAMP}; this migration will be planned again"]
        return done + manual, []


#: Every migration this release ships, in the order they must run.
#:
#: Order is contract: the scaffold creates the pool the renderer writes into.
#:
#: A gate at or below the current version would never be selected for a
#: workspace already on it and would fire for every older one without the
#: release that introduced it ever existing — ``test_the_shipped_registry_
#: declares_no_gate_at_or_below_this_release`` holds the rule.
REGISTRY: tuple[Migration, ...] = (
    ScaffoldGraphPool(),
    RefreshRenderedAtlas(),
    RetireLegacyCommand(),
    AstaConnectorRoles(),
)
