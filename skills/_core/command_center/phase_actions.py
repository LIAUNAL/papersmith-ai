"""What each pipeline phase card lets the operator do from the dashboard.

A phase runs one of three ways, and the drawer offers exactly these:

* ``prompt`` — the stage is a harness slash command (``/<skill> $ARGUMENTS``,
  projected to ``.claude/commands``, ``.opencode/commands`` and ``.pi/prompts``).
  The drawer shows a text box with the skill's input rules as a guide, and
  "Run" types ``/<skill> <text>`` into the support terminal's agent.
* ``command`` — a real ``smith`` subcommand, typed into a shell session.
* ``redirect`` — the work happens in another dashboard panel (the concept map,
  the math tutor, the PoC board, the PDF preview…), so the drawer opens it.

Every slash command named here exists as a projected command and every shell
command is a ``smith`` subcommand the CLI accepts; tests hold both.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

# The phase order of the pipeline phases panel; the phase id ``Fase N`` is index N-1.
STAGES: tuple[str, ...] = (
    "harness", "plausibility", "ingestion", "proposal", "poc_experiments",
    "scaffolding", "declarations", "writing", "figures", "paper", "audit",
)

#: Short label of each phase, in ``STAGES`` order; the agents table of the
#: Archify Flow pane reads "Phase N — <label>" from here. English; the
#: dashboard's Spanish comes from static/i18n/server-es.json (see localize.py).
PHASE_LABELS: dict[str, str] = {
    "harness": "Harness",
    "plausibility": "Plausibility",
    "ingestion": "Ingestion",
    "proposal": "Proposal deliberation",
    "poc_experiments": "Proof of concept and experiments",
    "scaffolding": "Scaffolding",
    "declarations": "Declarations",
    "writing": "Writing",
    "figures": "Figures",
    "paper": "Paper",
    "audit": "Audit",
}


def _prompt(slash: str, label: str, guide: list[str], placeholder: str, *,
            min_sentences: int = 0, optional: bool = False, prefix: str = "") -> dict[str, Any]:
    return {"kind": "prompt", "slash": slash, "label": label, "guide": guide,
            "placeholder": placeholder, "min_sentences": min_sentences,
            "optional": optional, "prefix": prefix}


def _command(command: str, label: str, desc: str) -> dict[str, Any]:
    return {"kind": "command", "command": command, "label": label, "desc": desc}


def _redirect(label: str, tab: str, desc: str, section: str = "") -> dict[str, Any]:
    return {"kind": "redirect", "label": label, "tab": tab, "section": section, "desc": desc}


_WRITING_GUIDE = [
    "Name a block or an action: open the paper/ tree, see which writing phase is unlocked, or write a block.",
    "A block is written on its own: the agent never touches another byte of paper/main.tex.",
    "Every claim needs a source that holds it (resolve); without a source, nothing is written.",
    "Write in the paper's language; the register and style come from the declarations.",
]

ACTIONS: dict[str, dict[str, Any]] = {
    "harness": {
        "skills": ["upgrade-project"],
        "agent": "smith CLI",
        "actions": [
            _command("smith status .", "View the workspace status",
                     "Workspace summary: kit, harnesses, stages and artifacts."),
            _command("smith audit . --check-drift", "Verify projections",
                     "Checks that .claude, .opencode, .pi and .agents match the kit."),
            _prompt("/upgrade-project", "Upgrade the workspace (agent)", [
                "Use it when the workspace runs an older papersmith release.",
                "The agent brings skills, agents, commands and artifact shapes to the installed release.",
                "Optional: say what you want to keep or review before upgrading.",
            ], "E.g.: upgrade the workspace and tell me what changed in the commands.", optional=True),
        ],
    },
    "plausibility": {
        "skills": ["plausibility"],
        "agent": "sota-scout → sota-grapher → novelty-screener",
        "actions": [
            _prompt("/plausibility", "Explore the plausibility of the idea", [
                "Write the idea in at least two sentences: the problem and what you propose (otherwise the agent refuses to search).",
                "The agent gathers ~25 SOTA references by their abstracts, in 3 to 5 families, and draws the constellation (atlas.html).",
                "Then it splits the hypothesis into claims and grades each one (novel / known / tension / contradicted) with verbatim quotes.",
                "Nothing is ingested or filed: the report awaits your acceptance before the top 5 move on to ingestion.",
                "You can adjust the idea and ask for a new screening; every pass is a new report.",
            ], "E.g.: Current models lose accuracy outside their training domain. I propose …",
                min_sentences=2),
            _redirect("View the SOTA constellation", "atlas", "3D atlas of the candidate pool."),
        ],
    },
    "ingestion": {
        "skills": ["paper-ingestion"],
        "agent": "paper-ingestion",
        "actions": [
            _prompt("/paper-ingestion", "Ingest references", [
                "Give the path or URL of the PDFs to ingest (usually the top 5 accepted in plausibility).",
                "Each PDF is filed in its topic folder and converted to Markdown: equations in LaTeX, tables in Markdown, figures as files.",
                "Local and keyless (Marker); nothing is published.",
            ], "E.g.: ingest guidance/reference-papers/inbox/*.pdf"),
            _command("smith ingest <path-or-url> .", "Ingest from the CLI",
                     "Replace <path-or-url> with the PDF or the URL."),
            _redirect("View ingested artifacts", "artifacts", "Markdown and figures of the references."),
        ],
    },
    "proposal": {
        "skills": ["proposal-deliberation", "math-tutor"],
        "agent": "proposal-deliberation & math-tutor",
        "actions": [
            _prompt("/proposal-deliberation", "Deliberate the proposal", [
                "Ask for the first version, a change to the current proposal or a revision operation (rNN).",
                "The agent is a tutor: it discusses before deciding and applies no change without your approval.",
                "The mathematics goes in $$ … \\tag{N} $$ blocks; the novelty is placed inside the SOTA sky.",
                "The domain guides in guidance/paper-guide/ load on their own.",
            ], "E.g.: let us discuss whether hypothesis H2 still stands against the Smith 2024 reference."),
            _redirect("Discuss the concept map", "modelo",
                      "Pillars, hypotheses and layers of the concept.", "mapa"),
            _redirect("Mathematics and Socratic tutor", "modelo",
                      "Equations in LaTeX, the novelty card and a tutor that reads hand-drawn images.", "matematico"),
        ],
    },
    "poc_experiments": {
        "skills": ["experimental-deliberation", "datasets", "proposal-implementation",
                   "remote-parallelism", "hyperparameter-search", "experimental-implementation",
                   "experiment-diagrams", "kaggle-accounts", "remote-execution"],
        "agent": ("experimental-validation → experimental-publish → dataset-scout / dataset-curator → "
                  "paper-replicator → implementation-build → experiments-build → experiments-reviewer → "
                  "experiments-walk"),
        "actions": [
            _prompt("/experimental-deliberation", "Deliberate the experimental design", [
                "The question that governs every turn: what experiment would test this claim of the proposal?",
                "Every experiment declares the claim it tests, its metric and its SOTA baseline.",
                "Ask for the first version, a change or a revision operation; nothing is applied without your approval.",
            ], "E.g.: design the experiment that tests claim C1 against the strongest SOTA baseline."),
            _prompt("/datasets", "Data: always a toy set, plus the official dataset", [
                "Verbs: synth (a seeded toy set, always), search, license, qc, prepare and publish.",
                "dataset-scout searches the paper's official repositories, Kaggle, Hugging Face, OpenNeuro and Zenodo, and decides the license.",
                "dataset-curator measures the quality (qc) and writes one official subject-wise preparation that the PoC and the experiments read.",
                "publish uploads a private dataset only with your explicit consent; making it public asks for a separate consent.",
            ], "E.g.: synth an 8-subject toy set and look for an official dataset for the task.", optional=True),
            _prompt("/proposal-implementation", "Replication of comparison methods", [
                "The paper-replicator agent replicates every baseline or comparison paper ingested in guidance/.",
                "It first looks for the paper's published code: when it exists, it adopts it pinned to a commit with its license and audits that it matches the paper and is implemented correctly.",
                "When there is no published code, it reimplements the method from the ingested Markdown; every hyperparameter cites its section or equation.",
                "It ends with REPLICATION.md, invariant tests and a short run on the toy set; it never launches a remote run.",
            ], "E.g.: replicate the guidance/smith-2024 baseline in ../my-poc", optional=True),
            _prompt("/proposal-implementation", "Implement the proof of concept", [
                "Turns the latest proposal into Python against a target repository, or verifies an existing implementation.",
                "Give the target repository and whether it is a first pass or a later one.",
            ], "E.g.: implement the PoC of proposal r03 in ../my-poc", optional=True),
            _redirect("Estimate the time and choose where to run", "experiments",
                      "Before the pilot and again before the full run: a short timing probe (one epoch of "
                      "one fold per arm) in Results/timing.json; the Experiments tab estimates the PoC and "
                      "the full run (±20%), shows the local environment and the local, Kaggle and Colab "
                      "run options."),
            _prompt("/hyperparameter-search", "Hyperparameter search (Optuna)", [
                "Only when the deliberation judged it worthwhile: the protocol declares the search and its space.",
                "Nested inside the training subjects of each outer fold, never seeing the test subjects.",
                "The same trial budget for every arm and baseline; it never tunes an independent variable the experiment tests.",
                "A seeded sampler and a declared importance evaluator (Optuna 5 uses PED-ANOVA by default).",
                "report writes the contours and importances the Experiments tab shows.",
                "It runs remotely like the full run, and only the operator launches it.",
            ], "E.g.: plan for the hybrid and linear arms with 40 trials and fANOVA as the evaluator.", optional=True),
            _prompt("/experimental-implementation", "Implement and measure the experiments", [
                "Turns the current experimental protocol into Python and runs its declared measurements.",
                "Give the target repository; the verification compares against the protocol and the proposal.",
                "Before any remote rehearsal, experiments-reviewer reviews the code (quality, optimization, GPU use and statistical tests) and hands in its report.",
            ], "E.g.: implement E1 and E2 and report the metrics.", optional=True),
            _prompt("/experiment-diagrams", "Diagrams of the PoC and of the experiments", [
                "When the PoC is approved (AGREED.md) it draws the poc diagram; when the full experiments are approved (Experimental_AGREED.md), the experiments diagram.",
                "Each one is a TikZ figure (PDF and PNG) in <product>/diagrams/; the \"Generate diagram\" button of the Experiments tab also produces it.",
                "Validate it yourself in the Experiments tab (\"Validate diagram\") or approve it explicitly in the chat with the agent, which runs validate with your words: submit refuses with DIAGRAM_NOT_VALIDATED until then, and drawing it again asks for a new validation.",
            ], "E.g.: poc for the product implementations/my-poc/Model.", optional=True),
            _prompt("/remote-parallelism", "Decide whether to split across accounts", [
                "First estimate --timing <target>/<Name>/Results/timing.json: the range per stage and host (±20%).",
                "Then assess with the measured inputs; --owners is the number of distinct owners in the team (smith team list), never the number of accounts.",
                "Team rule: one account per person and service; each person registers with `smith team add --owner <slug> --name \"<name>\" --kaggle-username <username> --attest`.",
                "It places, generates and launches nothing: the operator reads the verdict.",
            ], "E.g.: estimate the PoC with its timing.json and assess splitting the full run among 3 owners.",
                optional=True),
            _prompt("/kaggle-accounts", "Validate the Kaggle accounts", [
                "validate re-checks every stored account against the service and takes whatever is in kaggle-inbox/ (kaggle.json or a `username token` line).",
                "Only the accounts the team registry assigns to an owner are workers: one per person.",
            ], "E.g.: validate the accounts and take the new credentials from the inbox.", optional=True, prefix="validate "),
            _prompt("/remote-execution", "Remote rehearsal and launch (Kaggle / Colab)", [
                "Order: generate-job → submit --smoke → fetch --smoke and smoke record → readiness → gate (operator only) → submit → status / poll → fetch.",
                "The ledger is append-only; if the accounts do not authenticate, use /kaggle-accounts first.",
                "Only the operator authorizes a launch: no agent runs submit on its own.",
                "submit (--smoke too) requires that you validated the diagrams of the approved PoC and experiments.",
            ], "E.g.: generate the job for experiments/e1.py and prepare its smoke rehearsal.", optional=True),
            _redirect("View the PoC and the experiments", "experiments",
                      "Products, verdicts and diagrams of the proof of concept and of the experiments."),
        ],
    },
    "scaffolding": {
        "skills": ["paper-writing"],
        "agent": "paper-writing",
        "actions": [
            _prompt("/paper-writing", "Open the paper tree", _WRITING_GUIDE,
                    "E.g.: open the skeleton of the paper's sections and blocks.", prefix="skeleton "),
            _redirect("View the paper sections", "sections", "Section contracts and canonical blocks."),
        ],
    },
    "declarations": {
        "skills": ["paper-writing"],
        "agent": "paper-writing (mark)",
        "actions": [
            _prompt("/paper-writing", "Record a declaration", [
                "A declaration fixes a decision of the paper: CRediT authorship, funding, data and code, ethics, language or style.",
                "Write the declaration and its value; it is recorded with its provenance (mark).",
            ], "E.g.: manuscript language: English; code availability: public GitHub.", prefix="mark "),
            _redirect("View the paper sections", "sections", "Declarations and blocks of the manuscript."),
        ],
    },
    "writing": {
        "skills": ["paper-writing"],
        "agent": "paper-writing (redactor)",
        "actions": [
            _prompt("/paper-writing", "Write a block", _WRITING_GUIDE,
                    "E.g.: write the intro.motivation block"),
            _redirect("View the paper sections", "sections", "State of every block."),
            _redirect("View the PDF", "preview", "Preview of paper/main.pdf."),
        ],
    },
    "figures": {
        "skills": ["figure-review"],
        "agent": "figure-review",
        "actions": [
            _prompt("/figure-review", "Review a figure", [
                "Give the id of the figure already compiled in paper/Figures/<id>.pdf.",
                "The review judges whether the picture reads on its own, not the text that describes it.",
            ], "E.g.: review the fig-architecture figure"),
            _redirect("View the PDF", "preview", "Figures in the compiled manuscript."),
        ],
    },
    "paper": {
        "skills": ["paper-writing"],
        "agent": "pdflatex",
        "actions": [
            _redirect("View the PDF", "preview", "PDF viewer with live reload."),
        ],
    },
    "audit": {
        "skills": ["skill-audit"],
        "agent": "skill-audit & smith audit",
        "actions": [
            _command("smith audit . --verbose", "Audit the workspace",
                     "Structure and consistency of the workspace."),
            _prompt("/skill-audit", "Audit a skill or a CLI", [
                "Name the subject: a skill, a CLI or any closed set (operations, subcommands, error codes).",
                "The audit looks for the gap between what the code accepts and what its documentation claims.",
            ], "E.g.: audit skills/paper-writing"),
            _redirect("View the gates", "pipeline",
                      "State of the framework's gates, at the end of Pipeline and Progress.",
                      "gates"),
        ],
    },
}


# Bare keywords earlier releases accepted as a phase id. They match only as
# the whole id (case-insensitive); an id that merely contains one, which the
# old substring routing also took, is refused.
LEGACY_IDS: dict[str, str] = {
    "pdf": "paper", "compile": "paper", "figure": "figures", "sota": "plausibility",
    "ingest": "ingestion", "prop": "proposal", "scaffold": "scaffolding",
    "declaration": "declarations",
}


def stage_for(phase_id: str) -> str | None:
    """The stage a ``/api/phase/run`` id names: a stage id, ``Fase N``, or a
    legacy keyword."""
    text = str(phase_id or "").strip()
    if text in STAGES:
        return text
    if text.lower() in LEGACY_IDS:
        return LEGACY_IDS[text.lower()]
    parts = text.split()
    if len(parts) == 2 and parts[0].lower() == "fase" and parts[1].isdigit():
        index = int(parts[1]) - 1
        if 0 <= index < len(STAGES):
            return STAGES[index]
    return None


def primary_command(stage: str) -> str:
    """The text the drawer shows as the phase's command."""
    for action in ACTIONS.get(stage, {}).get("actions", []):
        if action["kind"] == "prompt":
            return f"{action['slash']} <text>" if not action["optional"] else action["slash"]
        if action["kind"] == "command":
            return action["command"]
    return "Compile from the dashboard (pdflatex + bibtex)" if stage == "paper" else ""


# The files that show a phase's work, as (label, glob) pairs relative to the
# workspace. The run tracker lists them and watches them change; the PASS
# verdict itself is the server's status rule for the phase.
EVIDENCE: dict[str, tuple[tuple[str, str], ...]] = {
    "harness": (("Workspace manifest", "papersmith.yaml"),
                ("Framework state", ".papersmith/version")),
    "plausibility": (("Candidate pool", "sota-pool/candidates.json"),
                     ("Atlas SOTA", "sota-pool/atlas.json"),
                     ("HTML constellation", "sota-pool/atlas.html")),
    "ingestion": (("Ingested references", "guidance/reference-papers/*/*.md"),),
    "proposal": (("Proposal revisions", "proposals/research-concept-*-r*.md"),
                 ("Proposal sky", "proposals/*.sky.json")),
    "poc_experiments": (("Experimental protocols", "experiments/*"),
                        ("Implementations", "implementations/*")),
    "scaffolding": (("Manuscript", "paper/main.tex"),
                    ("Section contracts", "sections/*.md")),
    "declarations": (("Manuscript (declarations region)", "paper/main.tex"),),
    "writing": (("Manuscript", "paper/main.tex"),),
    "figures": (("Compiled figures", "paper/Figures/*.pdf"),),
    "paper": (("Compiled PDF", "paper/main.pdf"),),
    "audit": (("Audit verdict", ".papersmith/audit.json"),),
}

#: Phases that need nothing before them: the harness starts everything and the
#: audit is transversal. Every other phase needs the one before it.
UNGATED = frozenset({"harness", "audit"})
MAX_MATCHES = 500


def evidence(root: Path, stage: str) -> list[dict[str, Any]]:
    """Each evidence item with how many files match and the newest change
    (epoch ms), bounded so a large tree never stalls the status poll."""
    root = Path(root)
    items = []
    for label, pattern in EVIDENCE.get(stage, ()):
        count, newest = 0, 0
        try:
            matches = root.glob(pattern)
            for path in matches:
                # One unreadable entry (a broken symlink) never hides the rest.
                try:
                    if path.name.startswith(".") or not path.resolve().is_relative_to(root.resolve()):
                        continue
                    newest = max(newest, int(path.stat().st_mtime * 1000))
                except OSError:
                    continue
                count += 1
                if count >= MAX_MATCHES:
                    break
        except OSError:
            pass
        items.append({"label": label, "path": pattern, "count": count, "mtime": newest})
    return items


def attach(fases: list[dict[str, Any]], root: Path | None = None) -> list[dict[str, Any]]:
    """Add each phase's actions, real skills, command, evidence and lock to
    the status view."""
    previous: dict[str, Any] | None = None
    for phase in fases:
        stage = phase.get("stage_id", "")
        entry = ACTIONS.get(stage)
        if entry:
            phase["actions"] = copy.deepcopy(entry["actions"])
            phase["skills"] = list(entry["skills"])
            phase["agent"] = entry["agent"]
            phase["cli_command"] = primary_command(stage)
        if root is not None:
            phase["evidence"] = evidence(root, stage)
        gated = stage not in UNGATED and previous is not None
        blocked = gated and previous.get("status") != "PASS"
        phase["unlocked"] = not blocked
        phase["blocked_by"] = previous.get("id") if blocked else None
        if stage != "audit":
            previous = phase
    return fases


__all__ = ["ACTIONS", "EVIDENCE", "STAGES", "UNGATED", "attach", "evidence", "primary_command", "stage_for"]
