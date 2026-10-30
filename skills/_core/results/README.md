# Results discussion

Each product folder (`implementations/<repo>/<Name>/`) closes its proof of concept (`AGREED.md`) or its full experiments (`Experimental_AGREED.md`) with one checked `Results/discussion.json`: hypothesis verdicts backed by tests, the novelty justification, the qualitative/interpretability analysis and a summarised discussion.

- `discussion.py` is the contract (stdlib only). Import it **by file path** with `importlib.util.spec_from_file_location`; the folder has no package `__init__`.
- `discussion_cli.py` is the command line over it.

## CLI

```
python skills/_core/results/discussion_cli.py scaffold --product implementations/<repo>/<Name>
python skills/_core/results/discussion_cli.py check    --product implementations/<repo>/<Name>
python skills/_core/results/discussion_cli.py status   --product implementations/<repo>/<Name>
```

Every verb prints exactly one JSON object. A refusal prints `{"ok": false, "error": <CODE>, "message": ...}`, exits non-zero (1; 2 for `USAGE`) and writes nothing. The only file ever written is `<product>/Results/discussion.json`, and only by a successful `scaffold` (`Results/` is created if missing).

| Verb | Does | Exit |
| --- | --- | --- |
| `scaffold` | Writes the pending skeleton. Never overwrites. | 0 on success |
| `check` | `{"ok", "status", "errors", "warnings", "stage"}` | 0 for `complete`/`draft`; non-zero for `invalid`, and `DISCUSSION_ABSENT` when the file is missing |
| `status` | Same output as `check`; a missing file is `"status": "absent"` | 0 whenever the product exists |

`ok` is true only for `complete` and `draft`.

Refusal codes: `USAGE`, `PRODUCT_ABSENT` (not a directory), `APPROVAL_ABSENT` (scaffold, no `AGREED.md`/`Experimental_AGREED.md`), `DISCUSSION_EXISTS`, `DISCUSSION_ABSENT` (check), `RESULTS_UNSAFE` (`Results/` is a symlink leaving the product), `WRITE_FAILED`.

## Scaffold

The stage comes from the holder (`Experimental_AGREED.md` → `full`, else `AGREED.md` → `poc`). The workspace root is `product.parents[2]`. From the latest `experiments/experiments-*-vNN.md` (highest `NN`), each `## Experiment [exp:<id>]` becomes one hypothesis `H1..Hn` (in order) with its **Hypothesis** and **Success criterion** bullets copied verbatim; `verdict` is `pending`, `observed` and `summary` are empty. `metrics` starts empty. `available_evidence` lists the figures, tables, qualitative artifacts (`Results/qualitative/**`) and significance comparisons found on disk, to help the author; it is ignored by the check. No number is ever written.

**A fresh scaffold is `invalid` on purpose** (empty `summary`, no `metrics`, no qualitative entry or reason). The author fills it, then runs `check` until it is `complete`. If no protocol exists, `protocol` is `""` and the hypotheses must be added by hand (the CLI warns).

## Schema 1

```json
{
  "schema": 1,
  "stage": "poc | full",
  "protocol": "experiments/experiments-<name>-vNN.md",
  "generated_at": "<ISO timestamp>",
  "summary": "summarised discussion, 1..2000 chars",
  "discussion_type": ["comparative | ablation | failure-analysis | sensitivity | interpretability | cost | generalization"],
  "metrics": [{"name": "", "role": "primary | secondary", "why": "", "source": ""}],
  "hypotheses": [{
    "id": "H1", "experiment": "E1", "statement": "", "metric": "", "test": "", "criterion": "", "observed": "",
    "evidence": ["Results/figures/x.png", "significance:<comparison>"],
    "verdict": "supported | partially_supported | not_supported | inconclusive | pending",
    "rationale": ""
  }],
  "novelty": {"claim": "", "verdict": "justified | partially_justified | not_justified | pending",
              "evidence": [], "rationale": ""},
  "qualitative": [{"title": "", "kind": "qualitative | interpretability | explainability",
                   "method": "", "figure": "Results/qualitative/x.png", "reading": ""}],
  "qualitative_not_applicable": "reason, when no qualitative analysis applies",
  "limitations": [], "next_steps": []
}
```

Evidence is either a path relative to the product folder or `significance:<comparison>`, matched against the `comparison` values of the product's `Results/**/significance*.json` (a list, or a dict wrapping a list under `tests`, `comparisons` or `results`).

## Check rules

`status` is `invalid` with any error, `draft` when valid but a hypothesis verdict or the novelty verdict is `pending`, `complete` when valid and nothing is pending.

Errors:

- `schema` is not the integer `1`; `stage` is missing, not `poc`/`full`, or disagrees with the holder (or the product has no holder).
- `summary` is empty or longer than 2000 characters.
- `metrics` is empty, or a metric lacks `name` or `why`.
- `hypotheses` is empty; a hypothesis lacks `id` or `statement`, or its `verdict` is outside the enum.
- A `supported`/`partially_supported`/`not_supported` verdict has no evidence (`inconclusive` and `pending` need none).
- An evidence path (or qualitative `figure`) is absolute, escapes the product with `..` or a symlink, or does not exist; a `significance:<comparison>` matches no comparison.
- **At stage `full`**, a `supported`/`partially_supported`/`not_supported` verdict cites no `significance:` evidence (the hypothesis test is mandatory). At `poc` this is only a warning.
- `novelty` is missing or not an object, its verdict is outside the enum, or a non-pending verdict has no evidence.
- Neither a non-empty `qualitative` list nor a non-empty `qualitative_not_applicable`; a qualitative entry has a `kind` outside the enum or a `figure` that does not exist.
- Too many entries (200 hypotheses, 100 metrics, 100 qualitative entries, 50 evidence entries per item).

Warnings (never errors): unknown keys, duplicate hypothesis ids, `discussion_type` values outside the enum, a metric `role` outside `primary`/`secondary`, and the PoC significance gap above.

Reads are bounded (2 MiB per file, 200 significance rows per file, 100 significance files, 20 000 files scanned) and contained in the product folder. `check_discussion` and `load_and_check` never raise on malformed input.

## Python API

```python
STAGES, VERDICTS, NOVELTY_VERDICTS, QUALITATIVE_KINDS, DISCUSSION_TYPES   # tuples
product_stage(product: Path) -> str | None
check_discussion(product: Path, data: Any) -> dict      # {"status", "errors", "warnings", "stage"}
load_and_check(product: Path) -> dict                   # {"present", "file", "data", **check}; "absent" when missing
significance_comparisons(product: Path) -> list[str]
scaffold(product: Path, root: Path | None = None) -> dict   # raises DiscussionRefusal(code, message)
```
