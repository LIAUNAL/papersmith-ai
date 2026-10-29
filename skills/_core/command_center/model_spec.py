"""Conceptual and mathematical model specification.

Defines the formal domains, core equations, cost functions, optimization problems,
and proof-of-concept experimental plan for paper workspaces.

A workspace that wants its own specification writes it to
``.papersmith/model_spec.json``; otherwise this module answers a neutral
specification built only from ``papersmith.yaml``. No project's data ships with
the framework; the test suite carries one worked example under ``tests/fixtures/``.
"""

import json
from pathlib import Path
from typing import Any


def get_model_specification(root_path: Path | None = None) -> dict[str, Any]:
    """Return the structured specification of conceptual architecture,
    mathematical modeling, and proof-of-concept plan for a workspace."""
    if root_path is not None:
        root = Path(root_path).expanduser().resolve()
        spec_json = root / ".papersmith" / "model_spec.json"
        if spec_json.is_file():
            try:
                return json.loads(spec_json.read_text(encoding="utf-8"))
            except Exception:
                pass

        yaml_file = root / "papersmith.yaml"
        title = ""
        topic = ""
        authors_str = "No author assigned"
        venue = "unspecified"
        if yaml_file.is_file():
            try:
                import yaml
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
                title = data.get("title", "")
                topic = data.get("topic", "")
                venue = data.get("venue_target", "unspecified")
                authors_list = data.get("authors", [])
                if isinstance(authors_list, list) and authors_list:
                    authors_str = ", ".join(a if isinstance(a, str) else a.get("name", "") for a in authors_list if isinstance(a, (str, dict)))
            except Exception:
                pass

        # Dynamic clean model specification for this workspace
        project_title = title or root.name
        return {
            "title": project_title,
            "target_journal": venue,
            "authors": authors_str,
            "trl": "Initial Phase (Pending deliberation)",
            "executive_summary": (
                f"Conceptual and formal model for the {project_title} project. "
                "The conceptual architecture, the mathematical model and the proof-of-concept plan "
                "are formalized during Phase 4 (Proposal Deliberation in proposals/) and "
                "Phase 5 (Experimental Deliberation in experiments/)."
            ),
            "novelty": {
                "problem_statement": f"Problem statement and technical gap for {project_title}, under deliberation.",
                "pillars": [
                    {
                        "id": "pillar-1",
                        "name": "Pillar 1: Methodological / Theoretical Innovation",
                        "badge": "CONCEPTUAL",
                        "color": "#38bdf8",
                        "summary": f"Main contribution of {project_title}.",
                        "details": "Pending formalization during the proposal deliberation (proposals/)."
                    },
                    {
                        "id": "pillar-2",
                        "name": "Pillar 2: System Architecture",
                        "badge": "ARCHITECTURE",
                        "color": "#10b981",
                        "summary": "Design and technical structure of the system.",
                        "details": "Pending scaffolding and empirical verification."
                    },
                    {
                        "id": "pillar-3",
                        "name": "Pillar 3: Empirical Validation & Contrasts",
                        "badge": "METROLOGY",
                        "color": "#f59e0b",
                        "summary": "Test protocols and performance metrics.",
                        "details": "Pending the run of the experiments (experiments/)."
                    }
                ]
            },
            "conceptual_map": {
                "layers": [
                    {"layer": "Layer 1: Inputs & Data", "desc": "Raw data, bibliographic references and instrumentation."},
                    {"layer": "Layer 2: Preprocessing & Feature Extraction", "desc": "Conditioning and hidden representations."},
                    {"layer": "Layer 3: Algorithmic Core", "desc": "Theoretical, mathematical or machine-learning models."},
                    {"layer": "Layer 4: Inference & Metrics", "desc": "Quantitative evaluation and cost functions."},
                    {"layer": "Layer 5: Synthesis & Manuscript", "desc": "Technical writing and PDF compilation."}
                ]
            },
            "mathematical_model": {
                "domains": [
                    {"name": "Input Space", "symbol": "X", "definition": "Domain of the observations and input data."},
                    {"name": "Output Space", "symbol": "Y", "definition": "Domain of prediction or transduction."}
                ],
                "equations": [],
                "optimization_problems": []
            },
            "poc_plan": {
                "experiments": []
            }
        }

    return get_model_specification(Path("Paper"))
