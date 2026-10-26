"""The MCP capability catalog.

Every exposed capability projects an existing CLI contract; nothing here is
domain logic. The catalog is the single source of truth for the tool surface,
and it also declares a *disposition* for every verb the CLI registers, so the
roster is total: a verb is exposed, or deferred by name, or declared out.

Adding a tool is a data edit here, never a new code path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bridge import ChildPlan, INGEST_TIMEOUT

#: `full_text` downloads a multi-MB PDF with a 10 s per-op socket timeout and
#: one retry; the default child cap (``bridge.DEFAULT_TIMEOUT``, 120 s) is
#: comfortably under that worst case, so the download gets its own long cap
#: like the other network path (`ingest`, ``INGEST_TIMEOUT``).
FULL_TEXT_TIMEOUT = 1800.0

#: The paper-writing CLI's own verb roster (``paper_cli.COMMANDS``), in
#: ``paper_cli.COMMANDS`` order.
PAPER_VERBS: tuple[str, ...] = (
    "scaffold",
    "status",
    "open",
    "substitute",
    "contract",
    "readiness",
    "phases",
    "skeleton",
    "order",
    "declare",
    "bind",
    "mark",
    "separate",
    "observe",
    "plan",
    "resolve",
    "full_text",
    "bib",
    "validate",
    "write",
    "render",
    "place",
    "couplings",
    "verify",
    "figure",
    "packet",
    "reuse",
    "exhaustion",
)

#: The orchestrator CLI's own command roster (``cli._REGISTRY``).
CLI_COMMANDS: tuple[str, ...] = (
    "init",
    "env",
    "upgrade",
    "status",
    "ingest",
    "deliberate",
    "implement",
    "run",
    "remote",
    "target",
    "audit",
    "ui",
    "atlas",
    "mcp",
    "team",
    "colab",
    "doctor",
)


class ToolRefusal(Exception):
    """A domain refusal decided before any child is spawned."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Flag:
    """One argument a tool accepts, and how it becomes child argv.

    A ``flag`` that does not begin with ``-`` names a positional: its value
    is emitted after ``--`` (see ``_cli_child``), never behind its own name.
    ``default`` is the one value an omitted argument takes, both in the
    advertised schema and in the argv the child receives.
    """

    name: str
    flag: str
    kind: str = "str"  # str | bool | list | int | enum
    required: bool = False
    choices: tuple[str, ...] | None = None
    path: bool = False
    description: str = ""
    default: Any = None

    @property
    def positional(self) -> bool:
        return not self.flag.startswith("-")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    verb: str
    surface: str  # "cli" | "paper" | "skill" (a skill script run by the workspace interpreter)
    annotations: dict[str, Any]
    input_schema: dict[str, Any]
    build: Callable[[dict[str, Any], Path], ChildPlan]
    precondition: Callable[[dict[str, Any], Path], None] | None = None
    result_json: bool = False

    def as_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": dict(self.annotations),
        }


def tool_annotations(
    title: str,
    *,
    read_only: bool,
    destructive: bool,
    open_world: bool,
    idempotent: bool = False,
) -> dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": open_world,
    }


def resolve_under(root: Path, raw: str) -> Path:
    """Resolve ``raw`` against ``root`` and refuse anything outside it."""
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise ToolRefusal(
            "WORKSPACE_ESCAPE", f"{resolved} is outside the bound workspace {root}"
        ) from None
    return resolved


# --------------------------------------------------------------------------- #
# workspace orchestration tools
# --------------------------------------------------------------------------- #


def _build_status(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    return ChildPlan("cli", ("status", "--json", str(workspace)))


def _build_doctor(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    return ChildPlan("cli", ("doctor", str(workspace), "--json"))


def _build_audit(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    return ChildPlan("cli", ("audit", str(workspace), "--check-drift"))


def _build_target_list(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    return ChildPlan("cli", ("target", "list"))


def _build_target_check(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    tokens = ["target", "check"]
    name = arguments.get("name")
    if name:
        tokens.append(str(name))
    return ChildPlan("cli", tuple(tokens))


def _build_target_set(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    return ChildPlan("cli", ("target", "set", str(arguments["name"])))


def _refuse_npm(arguments: dict[str, Any], workspace: Path) -> None:
    return None


def _build_init(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    target = resolve_under(workspace, str(arguments["name"]))
    tokens = [
        "init",
        str(target),
        "--title",
        str(arguments.get("title", "Untitled Paper")),
        "--topic",
        str(arguments.get("topic", "unspecified")),
    ]
    remote = arguments.get("remote")
    if remote:
        tokens.extend(["--remote", str(remote)])
    tools = arguments.get("tools")
    if tools:
        tokens.extend(["--tools", str(tools)])
    if not arguments.get("allow_npm"):
        tokens.append("--no-npm")
    if not arguments.get("allow_env"):
        tokens.append("--no-env")
    if arguments.get("allow_dirty_kit"):
        tokens.append("--allow-dirty-kit")
    return ChildPlan("cli", tuple(tokens), timeout=600.0)


def _build_upgrade(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    tokens = ["upgrade", str(workspace)]
    tools = arguments.get("tools")
    if tools:
        tokens.extend(["--tools", str(tools)])
    if arguments.get("force"):
        tokens.append("--force")
    if arguments.get("allow_dirty_kit"):
        tokens.append("--allow-dirty-kit")
    return ChildPlan("cli", tuple(tokens), timeout=600.0)


def _build_ingest(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    source = str(arguments["source"])
    if not source.startswith(("http://", "https://")):
        source = str(resolve_under(workspace, source))
    tokens = ["ingest", source, str(workspace)]
    if arguments.get("ocr"):
        tokens.append("--ocr")
    return ChildPlan("cli", tuple(tokens), timeout=INGEST_TIMEOUT)


_FRAGMENT_SELECTORS = (
    Flag("page", "--page", kind="int", description="page number, from 1"),
    Flag("heading", "--heading", description="text contained in a heading"),
    Flag("equation", "--equation", kind="int", description="display equation index, from 0"),
    Flag("search", "--search", description="text to find in the paragraphs"),
    Flag("outline", "--outline", kind="bool", description="headings and counts only"),
)
_FRAGMENT_FLAGS = (
    Flag("paper", "paper", required=True, path=True,
         description="workspace-relative ingested paper folder, or its .json / .md"),
    *_FRAGMENT_SELECTORS,
    Flag("max_chars", "--max-chars", kind="int", description="cap on the returned text (default 6000)"),
)


def _build_ingest_fragment(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    script = workspace / "skills" / "paper-ingestion" / "scripts" / "pdf_fragment.py"
    tokens = [str(script), str(resolve_under(workspace, str(arguments["paper"])))]
    for spec in _FRAGMENT_FLAGS[1:]:
        value = arguments.get(spec.name)
        if value is None or value is False:
            continue
        tokens.extend([spec.flag] if spec.kind == "bool" else [spec.flag, str(value)])
    tokens.append("--json")
    return ChildPlan("paper", tuple(tokens))


# --------------------------------------------------------------------------- #
# paper-writing tools
# --------------------------------------------------------------------------- #


def _paper_child(
    verb: tuple[str, ...],
    flags: tuple[Flag, ...],
    arguments: dict[str, Any],
    workspace: Path,
    *,
    timeout: float | None = None,
) -> ChildPlan:
    script = workspace / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
    argv = [str(script), *verb]
    for spec in flags:
        value = arguments.get(spec.name)
        if value is None:
            continue
        if spec.kind == "bool":
            if value:
                argv.append(spec.flag)
            continue
        if spec.kind == "list":
            for item in value:
                argv.extend([spec.flag, str(item)])
            continue
        text = str(value)
        if spec.path:
            text = str(resolve_under(workspace, text))
        argv.extend([spec.flag, text])
    return ChildPlan("paper", tuple(argv), timeout=timeout)


def _paper_builder(verb: tuple[str, ...], flags: tuple[Flag, ...]) -> Callable[..., ChildPlan]:
    def build(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
        return _paper_child(verb, flags, arguments, workspace)

    return build


def _schema(flags: tuple[Flag, ...]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for spec in flags:
        if spec.kind == "list":
            properties[spec.name] = {"type": "array", "items": {"type": "string"}}
        elif spec.kind == "bool":
            properties[spec.name] = {"type": "boolean"}
        elif spec.kind == "int":
            properties[spec.name] = {"type": "integer"}
        else:
            properties[spec.name] = {"type": "string"}
        if spec.choices:
            properties[spec.name]["enum"] = list(spec.choices)
        if spec.description:
            properties[spec.name]["description"] = spec.description
        if spec.default is not None:
            properties[spec.name]["default"] = spec.default
        if spec.required:
            required.append(spec.name)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


# One tuple feeds both the schema and the argv, so `file` cannot be confined in
# one and passed raw in the other.
_CONTRACT_FLAGS = (
    Flag("sections", "--sections", path=True),
    Flag("file", "--file", path=True, description="one file's parsed header"),
)


def _no_args() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": False}


_READINESS_FLAGS = (
    Flag("paper", "--paper", path=True),
    Flag("sections", "--sections", path=True),
    Flag("fact", "--fact", kind="list"),
    Flag("declaration", "--declaration", kind="list"),
)


def _build_readiness(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    """`readiness` needs a basis: upstream's post-merge call refuses
    `READINESS_BASIS_REQUIRED` unless `--paper` or `--fact`/`--declaration`
    is given, so a bare MCP call defaults `--paper` to the workspace's own
    `paper/` (basis "declaration-backed") instead of guessing an answer.
    """
    args = dict(arguments)
    args.setdefault("paper", "paper")
    return _paper_child(("readiness",), _READINESS_FLAGS, args, workspace)


_FULL_TEXT_FLAGS = (
    Flag("paper", "--paper", path=True),
    Flag("guidance", "--guidance", path=True),
    Flag("section", "--section", required=True),
    Flag("metadata_digest", "--metadata-digest", required=True),
    Flag("cite_key", "--cite-key", required=True),
)


def _build_full_text(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
    """`full_text` reaches the network (``openWorldHint``), so it gets its
    own explicit child cap rather than the default 120 s.
    """
    return _paper_child(
        ("full_text",), _FULL_TEXT_FLAGS, arguments, workspace, timeout=FULL_TEXT_TIMEOUT
    )


_PAPER_READONLY = (
    ToolSpec(
        name="papersmith.paper_status",
        title="Paper block table",
        description="Report the paper's block table, read-only.",
        verb="status",
        surface="paper",
        annotations=tool_annotations(
            "Paper block table", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema((Flag("paper", "--paper", path=True),)),
        build=_paper_builder(("status",), (Flag("paper", "--paper", path=True),)),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_contract",
        title="Section contract",
        description="Validate the section corpus, or show one file's parsed header.",
        verb="contract",
        surface="paper",
        annotations=tool_annotations(
            "Section contract", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(_CONTRACT_FLAGS),
        build=_paper_builder(("contract",), _CONTRACT_FLAGS),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_readiness",
        title="Per-block readiness",
        description=(
            "Per-block writable/blocked given satisfied facts and declarations. A bare call "
            "defaults --paper to the workspace's own paper/ (basis declaration-backed)."
        ),
        verb="readiness",
        surface="paper",
        annotations=tool_annotations(
            "Per-block readiness", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(_READINESS_FLAGS),
        build=_build_readiness,
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_order",
        title="Writing order",
        description="Derive the writing order from the block graph.",
        verb="order",
        surface="paper",
        annotations=tool_annotations(
            "Writing order", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema((Flag("sections", "--sections", path=True),)),
        build=_paper_builder(("order",), (Flag("sections", "--sections", path=True),)),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_observe",
        title="Validate observer report",
        description=(
            "Validate an insumos-observer report against the observable-fact schema, read-only. "
            "Never calls declare and never writes anything."
        ),
        verb="observe",
        surface="paper",
        annotations=tool_annotations(
            "Validate observer report", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(
            (Flag("report", "--report", required=True, path=True, description="observer JSON report"),)
        ),
        build=_paper_builder(("observe",), (Flag("report", "--report", required=True, path=True),)),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_plan",
        title="Paper plan",
        description="Read-only: guidance classes, declaration/fact fill state, provenance state.",
        verb="plan",
        surface="paper",
        annotations=tool_annotations(
            "Paper plan", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("sections", "--sections", path=True),
            )
        ),
        build=_paper_builder(
            ("plan",),
            (
                Flag("paper", "--paper", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("sections", "--sections", path=True),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_verify",
        title="Coupling verification",
        description=(
            "Read-only report over the cross-section couplings, citation integrity and "
            "contract currency."
        ),
        verb="verify",
        surface="paper",
        annotations=tool_annotations(
            "Coupling verification", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(
            (Flag("paper", "--paper", path=True), Flag("sections", "--sections", path=True))
        ),
        build=_paper_builder(
            ("verify",),
            (Flag("paper", "--paper", path=True), Flag("sections", "--sections", path=True)),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_phases",
        title="Writing phases",
        description=(
            "Read-only: what can I write now — waves with per-block readiness, opened, provenance."
        ),
        verb="phases",
        surface="paper",
        annotations=tool_annotations(
            "Writing phases", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("sections", "--sections", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("phase", "--phase", kind="int"),
            )
        ),
        build=_paper_builder(
            ("phases",),
            (
                Flag("paper", "--paper", path=True),
                Flag("sections", "--sections", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("phase", "--phase", kind="int"),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_packet",
        title="Redactor packet",
        description=(
            "Read-only: one block's own contract prose plus reference heading outlines, plus its "
            "bound source sections for a transposition-mode block."
        ),
        verb="packet",
        surface="paper",
        annotations=tool_annotations(
            "Redactor packet", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(
            (
                Flag("section", "--section", required=True),
                Flag("block", "--block", required=True),
                Flag("sections", "--sections", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("paper", "--paper", path=True),
            )
        ),
        build=_paper_builder(
            ("packet",),
            (
                Flag("section", "--section", required=True),
                Flag("block", "--block", required=True),
                Flag("sections", "--sections", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("paper", "--paper", path=True),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_reuse",
        title="Open-claim reuse report",
        description=(
            "Read-only: for one block's open claims, which already-ingested, evidence-classed "
            "papers carry no verdict yet."
        ),
        verb="reuse",
        surface="paper",
        annotations=tool_annotations(
            "Open-claim reuse report", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("block", "--block", required=True),
                Flag("min_sources", "--min-sources", kind="int"),
            )
        ),
        build=_paper_builder(
            ("reuse",),
            (
                Flag("paper", "--paper", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("block", "--block", required=True),
                Flag("min_sources", "--min-sources", kind="int"),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_exhaustion",
        title="Corpus-wide exhaustion report",
        description=(
            "Read-only, corpus-wide: every evidence-classed ingested paper's exhaustion state — "
            "lists only, never deletes."
        ),
        verb="exhaustion",
        surface="paper",
        annotations=tool_annotations(
            "Corpus-wide exhaustion report", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("min_sources", "--min-sources", kind="int"),
            )
        ),
        build=_paper_builder(
            ("exhaustion",),
            (
                Flag("paper", "--paper", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("min_sources", "--min-sources", kind="int"),
            ),
        ),
        result_json=True,
    ),
)

_WORKSPACE_TOOLS = (
    ToolSpec(
        name="papersmith.workspace_status",
        title="Workspace status",
        description="Show comprehensive workspace status as machine-readable JSON.",
        verb="status",
        surface="cli",
        annotations=tool_annotations(
            "Workspace status", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_no_args(),
        build=_build_status,
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.workspace_doctor",
        title="Workspace health",
        description=(
            "One table of the workspace's health: framework versions and drift, packages and "
            "external tools (TeX, rasterizers, git, node, micromamba), skills, agents and the "
            "dashboard's phases, each ok, absent, warn or fail."
        ),
        verb="doctor",
        surface="cli",
        annotations=tool_annotations(
            "Workspace health", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_no_args(),
        build=_build_doctor,
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.workspace_audit",
        title="Workspace audit",
        description=(
            "Audit workspace structure and consistency; reports generated-file drift as findings "
            "and never repairs it."
        ),
        verb="audit",
        surface="cli",
        annotations=tool_annotations(
            "Workspace audit", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_no_args(),
        build=_build_audit,
    ),
    ToolSpec(
        name="papersmith.target_list",
        title="List compute targets",
        description="List configured compute targets, marking the active one.",
        verb="target list",
        surface="cli",
        annotations=tool_annotations(
            "List compute targets", read_only=True, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_no_args(),
        build=_build_target_list,
    ),
    ToolSpec(
        name="papersmith.target_check",
        title="Check target connectivity",
        description=(
            "Test compute-target connectivity. Not hermetic: a remote-ssh target runs ssh "
            "and a kaggle target invokes the accounts helper."
        ),
        verb="target check",
        surface="cli",
        annotations=tool_annotations(
            "Check target connectivity", read_only=True, destructive=False, open_world=True, idempotent=True
        ),
        input_schema=_schema((Flag("name", "--name", description="target name; defaults to the active target"),)),
        build=_build_target_check,
    ),
    ToolSpec(
        name="papersmith.workspace_init",
        title="Initialize workspace",
        description=(
            "Create a standalone paper workspace under the bound root. npm install is skipped "
            "unless allow_npm is explicitly set, and the micromamba environment download is "
            "skipped unless allow_env is explicitly set."
        ),
        verb="init",
        surface="cli",
        annotations=tool_annotations(
            "Initialize workspace", read_only=False, destructive=False, open_world=True
        ),
        input_schema=_schema(
            (
                Flag("name", "name", required=True, description="new directory, under the bound root"),
                Flag("title", "--title"),
                Flag("topic", "--topic"),
                Flag("remote", "--remote", kind="enum", choices=("kaggle", "local", "slurm")),
                Flag("tools", "--tools", description="comma-separated runtimes"),
                Flag("allow_npm", "allow_npm", kind="bool", description="run the best-effort npm install"),
                Flag(
                    "allow_env", "allow_env", kind="bool",
                    description="provision the workspace's micromamba environment (a multi-gigabyte download)",
                ),
                Flag(
                    "allow_dirty_kit", "allow_dirty_kit", kind="bool",
                    description=("proceed even when the kit source has uncommitted changes or an "
                                 "unreadable git state; never a default"),
                ),
            )
        ),
        build=_build_init,
    ),
    ToolSpec(
        name="papersmith.workspace_upgrade",
        title="Upgrade workspace",
        description=(
            "Synchronize framework files in the workspace, preserving all research artifacts. "
            "force is never a default."
        ),
        verb="upgrade",
        surface="cli",
        annotations=tool_annotations(
            "Upgrade workspace", read_only=False, destructive=True, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("tools", "--tools", description="replace active runtime generators"),
                Flag("force", "--force", kind="bool", description="force framework-file writes"),
                Flag(
                    "allow_dirty_kit", "allow_dirty_kit", kind="bool",
                    description=("proceed even when the kit source has uncommitted changes or an "
                                 "unreadable git state; never a default"),
                ),
            )
        ),
        build=_build_upgrade,
    ),
    ToolSpec(
        name="papersmith.target_set",
        title="Select compute target",
        description=(
            "Persist the default compute target in .papersmith/config.json. Idempotent:false — "
            "each call rewrites the config with a new updated_at."
        ),
        verb="target set",
        surface="cli",
        annotations=tool_annotations(
            "Select compute target", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema((Flag("name", "name", required=True, description="configured target name"),)),
        build=_build_target_set,
    ),
    ToolSpec(
        name="papersmith.ingest_add",
        title="Ingest a reference",
        description=(
            "Ingest a PDF or literature URL into the workspace as Markdown plus figure files. "
            "Long-running and open-world; the first run may download model weights."
        ),
        verb="ingest",
        surface="cli",
        annotations=tool_annotations(
            "Ingest a reference", read_only=False, destructive=False, open_world=True
        ),
        input_schema=_schema(
            (
                Flag("source", "source", required=True, description="URL or workspace-relative PDF path"),
                Flag("ocr", "--ocr", kind="bool", description="balanced OCR-oriented extraction mode"),
            )
        ),
        build=_build_ingest,
    ),
    ToolSpec(
        name="papersmith.ingest_fragment",
        title="Read part of an ingested paper",
        description=(
            "Return one fragment of an ingested paper -- a page, the section under a heading, "
            "a display equation as LaTeX, the paragraphs matching a search, or the outline -- "
            "never the whole document. Exactly one selector is required; the child refuses "
            "otherwise (exit 2) and answers exit 1 when nothing matches."
        ),
        verb="fragment",
        surface="skill",
        annotations=tool_annotations(
            "Read part of an ingested paper", read_only=True, destructive=False, open_world=False,
            idempotent=True
        ),
        input_schema=_schema(_FRAGMENT_FLAGS),
        build=_build_ingest_fragment,
        result_json=True,
    ),
)

def _cli_child(
    tokens: tuple[str, ...],
    flags: tuple[Flag, ...],
    arguments: dict[str, Any],
    workspace: Path,
    *,
    timeout: float | None = None,
) -> ChildPlan:
    """Options first, then ``--``, then positionals in declared order.

    A positional value never follows its own name and never precedes the
    options, so a value beginning with ``-`` cannot be read as an option.
    Every ``cli`` verb taking a positional list (``extra``) declares an
    optional ``[<dir>]`` before it; the child runs in the workspace, so
    ``.`` fills that slot rather than letting the first extra become it.
    """
    argv = list(tokens)
    positionals: list[str] = []
    for spec in flags:
        value = arguments.get(spec.name, spec.default)
        if value is None:
            continue
        if spec.positional:
            if spec.kind == "list":
                if value:
                    positionals.extend([".", *(str(item) for item in value)])
                continue
            text = str(value)
            if spec.path:
                text = str(resolve_under(workspace, text))
            positionals.append(text)
            continue
        if spec.kind == "bool":
            if value:
                argv.append(spec.flag)
            continue
        if spec.kind == "list":
            for item in value:
                argv.extend([spec.flag, str(item)])
            continue
        text = str(value)
        if spec.path:
            text = str(resolve_under(workspace, text))
        argv.extend([spec.flag, text])
    if positionals:
        argv.extend(["--", *positionals])
    return ChildPlan("cli", tuple(argv), timeout=timeout)


def _cli_builder(
    tokens: tuple[str, ...], flags: tuple[Flag, ...], *, timeout: float | None = None
) -> Callable[[dict[str, Any], Path], ChildPlan]:
    def build(arguments: dict[str, Any], workspace: Path) -> ChildPlan:
        return _cli_child(tokens, flags, arguments, workspace, timeout=timeout)

    return build


def _refuse_stdin_body(arguments: dict[str, Any], workspace: Path) -> None:
    """`--body -` would read the server's own stdin: the JSON-RPC wire."""
    if arguments.get("body") == "-":
        raise ToolRefusal(
            "STDIN_NOT_AVAILABLE_OVER_MCP",
            "the bound body must be a file path; '-' would read the JSON-RPC wire",
        )


def _refuse_stdin_file(arguments: dict[str, Any], workspace: Path) -> None:
    """`--file -` would read the server's own stdin: the JSON-RPC wire."""
    if arguments.get("file") == "-":
        raise ToolRefusal(
            "STDIN_NOT_AVAILABLE_OVER_MCP",
            "the couplings record must be a file path; '-' would read the JSON-RPC wire",
        )


def _refuse_run_without_consent(arguments: dict[str, Any], workspace: Path) -> None:
    """A real dispatch spends quota; MCP defaults to planning only.

    Reads the same ``_DRY_RUN`` default ``_cli_child`` emits, so an omitted
    ``dry_run`` is judged as exactly the ``--dry-run`` argv the child gets.
    """
    if not arguments.get("dry_run", _DRY_RUN.default) and not arguments.get("consent"):
        raise ToolRefusal(
            "CONSENT_REQUIRED",
            "a non-dry run dispatches real work; pass an explicit consent token",
        )


def _refuse_remote_push_without_consent(arguments: dict[str, Any], workspace: Path) -> None:
    if arguments.get("operation") == "push" and not arguments.get("consent"):
        raise ToolRefusal(
            "CONSENT_REQUIRED",
            "remote push submits real work; pass an explicit consent token, or use --smoke",
        )


_PERMISSION_FLAGS = (Flag("paper", "--paper", path=True),)
_SECTIONS_FLAGS = (Flag("sections", "--sections", path=True),)
_GUIDANCE_FLAG = Flag("guidance", "--guidance", path=True)

_PAPER_MUTATING = (
    ToolSpec(
        name="papersmith.paper_scaffold",
        title="Scaffold the paper",
        description="Create or re-enter the paper/ tree idempotently.",
        verb="scaffold",
        surface="paper",
        annotations=tool_annotations(
            "Scaffold the paper", read_only=False, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(_PERMISSION_FLAGS),
        build=_paper_builder(("scaffold",), _PERMISSION_FLAGS),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_open",
        title="Open a block",
        description=(
            "Insert an empty block pair into the paper. Exactly one of after/at_end is required; "
            "the child refuses OPEN_POSITION_REQUIRED / OPEN_POSITION_CONFLICT."
        ),
        verb="open",
        surface="paper",
        annotations=tool_annotations(
            "Open a block", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("block", "--block", required=True),
                Flag("after", "--after"),
                Flag("at_end", "--at-end", kind="bool"),
            )
        ),
        build=_paper_builder(
            ("open",),
            (
                Flag("paper", "--paper", path=True),
                Flag("block", "--block", required=True),
                Flag("after", "--after"),
                Flag("at_end", "--at-end", kind="bool"),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_substitute",
        title="Substitute a block body",
        description=(
            "Replace one block's body, or adopt a hand edit. The body is a file path; '-' is refused "
            "because the child's stdin is closed."
        ),
        verb="substitute",
        surface="paper",
        annotations=tool_annotations(
            "Substitute a block body", read_only=False, destructive=True, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("block", "--block", required=True),
                Flag("body", "--body", path=True),
                Flag("adopt", "--adopt", kind="bool"),
                Flag("contract", "--contract", path=True),
            )
        ),
        build=_paper_builder(
            ("substitute",),
            (
                Flag("paper", "--paper", path=True),
                Flag("block", "--block", required=True),
                Flag("body", "--body", path=True),
                Flag("adopt", "--adopt", kind="bool"),
                Flag("contract", "--contract", path=True),
            ),
        ),
        precondition=_refuse_stdin_body,
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_declare",
        title="Record a declaration or fact",
        description="Record a declaration or fact resolution, or reopen a fixed one.",
        verb="declare",
        surface="paper",
        annotations=tool_annotations(
            "Record a declaration or fact", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("declaration", "--declaration"),
                Flag("fact", "--fact"),
                Flag("reopen", "--reopen"),
                Flag("value", "--value"),
            )
        ),
        build=_paper_builder(
            ("declare",),
            (
                Flag("paper", "--paper", path=True),
                Flag("declaration", "--declaration"),
                Flag("fact", "--fact"),
                Flag("reopen", "--reopen"),
                Flag("value", "--value"),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_bib_build",
        title="Rebuild the bibliography",
        description=(
            "Rebuild paper/refs.bib whole and sorted, from cached resolved metadata only -- "
            "never hand-typed."
        ),
        verb="bib",
        surface="paper",
        annotations=tool_annotations(
            "Rebuild the bibliography", read_only=False, destructive=False, open_world=False, idempotent=True
        ),
        input_schema=_schema(_PERMISSION_FLAGS),
        build=_paper_builder(("bib", "build"), _PERMISSION_FLAGS),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_write",
        title="Write a drafted block",
        description=(
            "Judge an already-drafted, already-audited block: reconcile the evidence, then "
            "substitute the block body or report why not. Every operand is a file path."
        ),
        verb="write",
        surface="paper",
        annotations=tool_annotations(
            "Write a drafted block", read_only=False, destructive=True, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("sections", "--sections", path=True),
                Flag("section", "--section", required=True),
                Flag("block", "--block", required=True),
                Flag("draft", "--draft", required=True, path=True),
                Flag("audit", "--audit", required=True, path=True),
                Flag("evidence", "--evidence", path=True),
                Flag("style", "--style", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("transcript", "--transcript", path=True),
            )
        ),
        build=_paper_builder(
            ("write",),
            (
                Flag("paper", "--paper", path=True),
                Flag("sections", "--sections", path=True),
                Flag("section", "--section", required=True),
                Flag("block", "--block", required=True),
                Flag("draft", "--draft", required=True, path=True),
                Flag("audit", "--audit", required=True, path=True),
                Flag("evidence", "--evidence", path=True),
                Flag("style", "--style", path=True),
                Flag("guidance", "--guidance", path=True),
                Flag("transcript", "--transcript", path=True),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_place",
        title="Place a measured figure",
        description=(
            "Place an already-measured figure's PDF; compiles nothing and needs provenance."
        ),
        verb="place",
        surface="paper",
        annotations=tool_annotations(
            "Place a measured figure", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("figure_id", "--figure-id", required=True),
                Flag("pdf", "--pdf", required=True, path=True),
                Flag("provenance", "--provenance", required=True, path=True),
            )
        ),
        build=_paper_builder(
            ("place",),
            (
                Flag("paper", "--paper", path=True),
                Flag("figure_id", "--figure-id", required=True),
                Flag("pdf", "--pdf", required=True, path=True),
                Flag("provenance", "--provenance", required=True, path=True),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_validate",
        title="Validate a claim for a block",
        description=(
            "The single citation gate: submit one judged verdict, check round-bounded satisfaction, "
            "write on success. NOT read-only -- it appends an evidence record when claim is given "
            "and, only once every claim is satisfied with a body supplied, substitutes the block."
        ),
        verb="validate",
        surface="paper",
        annotations=tool_annotations(
            "Validate a claim for a block", read_only=False, destructive=True, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("block", "--block", required=True),
                Flag("claim", "--claim"),
                Flag("quote", "--quote"),
                Flag("source_md", "--source-md", path=True),
                Flag("verdict", "--verdict", kind="enum", choices=("holds", "does-not-hold")),
                Flag("reason", "--reason"),
                Flag("cite_key", "--cite-key"),
                Flag("identifier", "--identifier"),
                Flag("resolver", "--resolver"),
                Flag("metadata_digest", "--metadata-digest"),
                Flag("regime", "--regime"),
                Flag("section_md", "--section-md", path=True),
                Flag("round", "--round", kind="int"),
                Flag("guidance", "--guidance", path=True),
                Flag("body", "--body", path=True),
                Flag("sentence", "--sentence", path=True),
            )
        ),
        build=_paper_builder(
            ("validate",),
            (
                Flag("paper", "--paper", path=True),
                Flag("block", "--block", required=True),
                Flag("claim", "--claim"),
                Flag("quote", "--quote"),
                Flag("source_md", "--source-md", path=True),
                Flag("verdict", "--verdict", kind="enum", choices=("holds", "does-not-hold")),
                Flag("reason", "--reason"),
                Flag("cite_key", "--cite-key"),
                Flag("identifier", "--identifier"),
                Flag("resolver", "--resolver"),
                Flag("metadata_digest", "--metadata-digest"),
                Flag("regime", "--regime"),
                Flag("section_md", "--section-md", path=True),
                Flag("round", "--round", kind="int"),
                Flag("guidance", "--guidance", path=True),
                Flag("body", "--body", path=True),
                Flag("sentence", "--sentence", path=True),
            ),
        ),
        precondition=_refuse_stdin_body,
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_skeleton",
        title="Open the section skeleton",
        description=(
            "Open every section/block id the two structural answers imply, empty, via open_block only."
        ),
        verb="skeleton",
        surface="paper",
        annotations=tool_annotations(
            "Open the section skeleton", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("sections", "--sections", path=True),
                Flag("related_work", "--related-work", kind="enum", choices=("yes", "no")),
                Flag(
                    "dataset_in", "--dataset-in", kind="enum",
                    choices=("materials", "experimental-setup"),
                ),
            )
        ),
        build=_paper_builder(
            ("skeleton",),
            (
                Flag("paper", "--paper", path=True),
                Flag("sections", "--sections", path=True),
                Flag("related_work", "--related-work", kind="enum", choices=("yes", "no")),
                Flag(
                    "dataset_in", "--dataset-in", kind="enum",
                    choices=("materials", "experimental-setup"),
                ),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_bind",
        title="Bind a block to source sections",
        description=(
            "Record which section(s) of a source document feed one block's own bindable "
            "requirement, or reopen a previously recorded binding."
        ),
        verb="bind",
        surface="paper",
        annotations=tool_annotations(
            "Bind a block to source sections", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("sections", "--sections", path=True),
                Flag("block", "--block", required=True),
                Flag("fact", "--fact", required=True),
                Flag("lineage", "--lineage"),
                Flag("section", "--section", kind="list"),
                Flag("reopen", "--reopen", kind="bool"),
            )
        ),
        build=_paper_builder(
            ("bind",),
            (
                Flag("paper", "--paper", path=True),
                Flag("sections", "--sections", path=True),
                Flag("block", "--block", required=True),
                Flag("fact", "--fact", required=True),
                Flag("lineage", "--lineage"),
                Flag("section", "--section", kind="list"),
                Flag("reopen", "--reopen", kind="bool"),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_mark_revisions",
        title="Record a source root's revision rule",
        description=(
            "Record <root>/.paper-writing.json's own revisions grammar, validated against the "
            "*.md files actually there right now."
        ),
        verb="mark",
        surface="paper",
        annotations=tool_annotations(
            "Record a source root's revision rule", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("root", "--root", required=True),
                Flag("revision_prefix", "--revision-prefix", required=True),
                Flag("ordinal_digits", "--ordinal-digits", kind="int", required=True),
                Flag("unsealed", "--unsealed", kind="bool"),
            )
        ),
        build=_paper_builder(
            ("mark", "revisions"),
            (
                Flag("paper", "--paper", path=True),
                Flag("root", "--root", required=True),
                Flag("revision_prefix", "--revision-prefix", required=True),
                Flag("ordinal_digits", "--ordinal-digits", kind="int", required=True),
                Flag("unsealed", "--unsealed", kind="bool"),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_mark_class",
        title="Record a guidance folder's class",
        description=(
            "Record guidance/<folder>/.paper-writing.json's own class grammar, validated against "
            "the folders actually there right now."
        ),
        verb="mark",
        surface="paper",
        annotations=tool_annotations(
            "Record a guidance folder's class", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("folder", "--folder", required=True),
                Flag("class_value", "--class", required=True),
                Flag("guidance", "--guidance", path=True),
                Flag("unsealed", "--unsealed", kind="bool"),
            )
        ),
        build=_paper_builder(
            ("mark", "class"),
            (
                Flag("folder", "--folder", required=True),
                Flag("class_value", "--class", required=True),
                Flag("guidance", "--guidance", path=True),
                Flag("unsealed", "--unsealed", kind="bool"),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_separate",
        title="Score a source-section cut",
        description=(
            "Score a proposed whole-cut assignment of source sections to blocks and refuse on any "
            "defect; records the separation round on success."
        ),
        verb="separate",
        surface="paper",
        annotations=tool_annotations(
            "Score a source-section cut", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("sections", "--sections", path=True),
                Flag("proposal", "--proposal", required=True, path=True),
            )
        ),
        build=_paper_builder(
            ("separate",),
            (
                Flag("paper", "--paper", path=True),
                Flag("sections", "--sections", path=True),
                Flag("proposal", "--proposal", required=True, path=True),
            ),
        ),
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_full_text",
        title="Fetch a reference's PDF",
        description=(
            "Fetch one already-resolved identifier's own PDF, keyless, from its cached metadata's "
            "measured full-text URL, and place it loose under guidance/<section>/. Open-world: "
            "reaches the network."
        ),
        verb="full_text",
        surface="paper",
        annotations=tool_annotations(
            "Fetch a reference's PDF", read_only=False, destructive=False, open_world=True
        ),
        input_schema=_schema(_FULL_TEXT_FLAGS),
        build=_build_full_text,
        result_json=True,
    ),
    ToolSpec(
        name="papersmith.paper_couplings",
        title="Validate and write the couplings record",
        description=(
            "Validate a JSON couplings record and write paper/couplings.json whole. The record is "
            "a file path; '-' is refused because the child's stdin is closed."
        ),
        verb="couplings",
        surface="paper",
        annotations=tool_annotations(
            "Validate and write the couplings record", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema(
            (
                Flag("paper", "--paper", path=True),
                Flag("file", "--file", required=True, path=True),
            )
        ),
        build=_paper_builder(
            ("couplings",),
            (
                Flag("paper", "--paper", path=True),
                Flag("file", "--file", required=True, path=True),
            ),
        ),
        precondition=_refuse_stdin_file,
        result_json=True,
    ),
)

_DELIBERATE_FLAGS = (
    Flag("action", "--action", description="real engine operation or supported alias"),
    Flag("request", "--request", description="raw JSON request object"),
    Flag("request_file", "--request-file", path=True),
    Flag("revision", "--revision", description="managed source filename"),
    Flag("instruction", "--instruction"),
    Flag("query", "--query", kind="list"),
    Flag("selected_entry_id", "--selected-entry-id", kind="list"),
    Flag("decisions", "--decisions", description="JSON array of resolved edit decisions"),
    Flag("accept", "--accept", kind="bool"),
    Flag("acceptance_token", "--acceptance-token"),
    Flag("withdrawal_operation_id", "--withdrawal-operation-id"),
    Flag("withdrawal_reason", "--withdrawal-reason"),
    Flag("prior_conclusion", "--prior-conclusion"),
)

_IMPLEMENT_FLAGS = (
    Flag("target", "--target"),
    Flag("name", "--name"),
    Flag("plan", "--plan"),
    Flag("finding", "--finding"),
    Flag("entry_text", "--entry-text"),
    Flag("python", "--python"),
    Flag("shards", "--shards"),
    Flag("revision", "--revision"),
    Flag("extra", "extra", kind="list", description="additional implementation_cli arguments, verbatim"),
)

_DRY_RUN = Flag(
    "dry_run", "--dry-run", kind="bool", default=True, description="plan only; the MCP default"
)
_RUN_FLAGS = (
    Flag("target", "--target"),
    _DRY_RUN,
    Flag("shard", "--shard", kind="int"),
    Flag("consent", "--consent", description="required for a non-dry dispatch"),
)

_REMOTE_FLAGS = (
    Flag("target", "--target"),
    Flag("entrypoint", "--entrypoint"),
    Flag("backend", "--backend"),
    Flag("account", "--account"),
    Flag("job", "--job"),
    Flag("submission_id", "--submission-id"),
    Flag("dest", "--dest", path=True),
    Flag("consent", "--consent", description="required for push"),
    Flag("smoke", "--smoke", kind="bool"),
    Flag("unit", "--unit", kind="list"),
    Flag("force", "--force", kind="bool"),
    Flag("resolve", "--resolve", kind="bool"),
    Flag("service", "--service"),
    Flag("job_name", "--job-name"),
    Flag("product", "--product"),
    Flag("commit", "--commit"),
    Flag("repo_url", "--repo-url"),
    Flag("repo_ref", "--repo-ref"),
    Flag("run_module", "--run-module"),
    Flag("run_function", "--run-function"),
    Flag("clone_path", "--clone-path", kind="list"),
    Flag("regenerate", "--regenerate", kind="bool"),
    Flag("extra", "extra", kind="list", description="additional remote_cli arguments, verbatim"),
)

_ORCHESTRATION = (
    ToolSpec(
        name="papersmith.deliberate",
        title="Proposal deliberation",
        description=(
            "Bridge to the deterministic proposal-deliberation engine: run an action, or pass a raw "
            "JSON request. Keyless and local; no state operation calls a model."
        ),
        verb="deliberate",
        surface="cli",
        annotations=tool_annotations(
            "Proposal deliberation", read_only=False, destructive=False, open_world=False
        ),
        input_schema=_schema(_DELIBERATE_FLAGS),
        build=_cli_builder(("deliberate",), _DELIBERATE_FLAGS, timeout=900.0),
    ),
    ToolSpec(
        name="papersmith.implement",
        title="Proposal implementation",
        description=(
            "Bridge to the proposal-implementation harness. Action is required; tokens after the "
            "known flags are forwarded verbatim to implementation_cli."
        ),
        verb="implement",
        surface="cli",
        annotations=tool_annotations(
            "Proposal implementation", read_only=False, destructive=True, open_world=False
        ),
        input_schema=_schema((Flag("action", "--action", required=True), *_IMPLEMENT_FLAGS)),
        build=_cli_builder(
            ("implement",),
            (Flag("action", "--action", required=True), *_IMPLEMENT_FLAGS),
            timeout=1800.0,
        ),
    ),
    ToolSpec(
        name="papersmith.run",
        title="Run a compute profile",
        description=(
            "Run an execution profile. Planning only by default: a real dispatch needs dry_run "
            "explicitly false AND a consent token, otherwise the call is refused CONSENT_REQUIRED."
        ),
        verb="run",
        surface="cli",
        annotations=tool_annotations(
            "Run a compute profile", read_only=False, destructive=False, open_world=True
        ),
        input_schema=_schema((Flag("profile", "profile", required=True), *_RUN_FLAGS)),
        build=_cli_builder(("run",), (Flag("profile", "profile", required=True), *_RUN_FLAGS), timeout=1800.0),
        precondition=_refuse_run_without_consent,
    ),
    ToolSpec(
        name="papersmith.remote",
        title="Remote execution",
        description=(
            "Direct remote-execution interface. push spends real quota and is refused without a "
            "consent token; pack/status/pull are the cheap rehearsals."
        ),
        verb="remote",
        surface="cli",
        annotations=tool_annotations(
            "Remote execution", read_only=False, destructive=True, open_world=True
        ),
        input_schema=_schema(
            (
                Flag(
                    "operation",
                    "operation",
                    required=True,
                    kind="enum",
                    choices=("pack", "push", "status", "pull", "sync"),
                ),
                *_REMOTE_FLAGS,
            )
        ),
        build=_cli_builder(
            ("remote",),
            (
                Flag(
                    "operation",
                    "operation",
                    required=True,
                    kind="enum",
                    choices=("pack", "push", "status", "pull", "sync"),
                ),
                *_REMOTE_FLAGS,
            ),
            timeout=1800.0,
        ),
        precondition=_refuse_remote_push_without_consent,
    ),
)

TOOLS: tuple[ToolSpec, ...] = (
    *_WORKSPACE_TOOLS,
    *_PAPER_READONLY,
    *_PAPER_MUTATING,
    *_ORCHESTRATION,
)

TOOLS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOLS}

#: Every CLI command and every paper verb has a declared disposition, so the
#: roster-drift test can prove the surface is deliberate rather than partial.
CLI_DISPOSITIONS: dict[str, str] = {
    "init": "exposed",
    "upgrade": "exposed",
    "status": "exposed",
    "ingest": "exposed",
    "audit": "exposed",
    "target": "exposed",
    "deliberate": "exposed",
    "implement": "exposed",
    "run": "exposed",
    "remote": "exposed",
    # The dashboard host. It starts an HTTP server and opens a browser, so it is
    # a thing an operator runs and watches, never a tool an agent calls mid-turn
    # -- the same reason the server host below is declared out rather than
    # exposed. Its own `/api/*` surface is what an agent would read, and that
    # surface is not a CLI command.
    "ui": "out",
    # `atlas build` re-renders sota-pool/atlas.html: the dashboard's
    # "Regenerar grafo" button from a terminal, an operator action like `ui`.
    # An agent regenerates the atlas through the plausibility skill's own
    # check_atlas.py/render_atlas.py, which this command only sequences.
    "atlas": "out",
    # The server host itself: never a tool it exposes.
    "mcp": "out",
    # Operator environment provisioning: long-running multi-gigabyte command.
    "env": "out",
    # The team registry records people and their own attestation that they
    # own one account per service: a person's declaration, never an agent's.
    "team": "out",
    # `colab login` runs an interactive Google consent for one person's own
    # account; `status` probes that sign-in. Both are an operator's acts.
    "colab": "out",
    "doctor": "exposed",
}

PAPER_DISPOSITIONS: dict[str, str] = {
    verb: (
        "deferred" if verb in {"resolve", "render"}
        # `figure` bundles a READ-ONLY verb (`audit`) and a SOURCE-MUTATING one
        # (`optimize`) under a single namespace, so one MCP tool spec would have
        # to state one `readOnlyHint`/`destructiveHint` pair and be wrong about
        # the other half. Declared out rather than exposed with a hint that
        # lies; `PAPER_VERBS` still carries it, so the roster stays total.
        else "out" if verb == "figure"
        else "exposed"
    )
    for verb in PAPER_VERBS
}
