"""What each pipeline phase card lets the operator do from the dashboard.

A phase runs one of three ways, and the drawer offers exactly these:

* ``prompt`` — the stage is a harness slash command (``/<skill> $ARGUMENTS``,
  projected to ``.claude/commands``, ``.opencode/commands`` and ``.pi/prompts``).
  The drawer shows a text box with the skill's input rules as a guide, and
  "Ejecutar" types ``/<skill> <text>`` into the support terminal's agent.
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

# The phase order of the "Fases del Pipeline" panel; ``Fase N`` is index N-1.
STAGES: tuple[str, ...] = (
    "harness", "plausibility", "ingestion", "proposal", "poc_experiments",
    "scaffolding", "declarations", "writing", "figures", "paper", "audit",
)

#: Short Spanish label of each phase, in ``STAGES`` order; the agents table of
#: the Flujo Archify pane reads "Fase N — <label>" from here.
PHASE_LABELS: dict[str, str] = {
    "harness": "Harness",
    "plausibility": "Plausibilidad",
    "ingestion": "Ingestión",
    "proposal": "Deliberación de la propuesta",
    "poc_experiments": "Prueba de concepto y experimentos",
    "scaffolding": "Andamiaje",
    "declarations": "Declaraciones",
    "writing": "Redacción",
    "figures": "Figuras",
    "paper": "Paper",
    "audit": "Auditoría",
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
    "Nombra un bloque o una acción: abrir el árbol paper/, ver qué fase de escritura está desbloqueada, o escribir un bloque.",
    "Un bloque se escribe solo: el agente nunca toca otro byte de paper/main.tex.",
    "Cada afirmación necesita una fuente que la sostenga (resolve); sin fuente, no se escribe.",
    "Escribe en el idioma del paper; el registro y el estilo vienen de las declaraciones.",
]

ACTIONS: dict[str, dict[str, Any]] = {
    "harness": {
        "skills": ["upgrade-project"],
        "agent": "smith CLI",
        "actions": [
            _command("smith status .", "Ver estado del workspace",
                     "Resumen del workspace: kit, harnesses, etapas y artefactos."),
            _command("smith audit . --check-drift", "Verificar proyecciones",
                     "Comprueba que .claude, .opencode, .pi y .agents coinciden con el kit."),
            _prompt("/upgrade-project", "Actualizar el workspace (agente)", [
                "Úsalo cuando el workspace corre una versión anterior de papersmith.",
                "El agente trae skills, agentes, comandos y formas de artefacto a la versión instalada.",
                "Opcional: indica qué quieres conservar o revisar antes de actualizar.",
            ], "Ej.: actualiza el workspace y dime qué cambió en los comandos.", optional=True),
        ],
    },
    "plausibility": {
        "skills": ["plausibility"],
        "agent": "sota-scout → sota-grapher → novelty-screener",
        "actions": [
            _prompt("/plausibility", "Explorar la plausibilidad de la idea", [
                "Escribe la idea en al menos dos oraciones: el problema y lo que propones (si no, el agente se niega a buscar).",
                "El agente reúne ~25 referencias SOTA por sus abstracts, en 3 a 5 familias, y dibuja la constelación (atlas.html).",
                "Luego divide la hipótesis en afirmaciones y califica cada una (novel / known / tension / contradicted) con citas literales.",
                "Nada se ingiere ni se archiva: el informe espera tu aceptación antes de pasar el top 5 a ingestión.",
                "Puedes ajustar la idea y pedir un nuevo screening; cada pasada es un informe nuevo.",
            ], "Ej.: Los modelos actuales pierden precisión fuera de su dominio de entrenamiento. Propongo …",
                min_sentences=2),
            _redirect("Ver la constelación SOTA", "atlas", "Atlas 3D del pool de candidatos."),
        ],
    },
    "ingestion": {
        "skills": ["paper-ingestion"],
        "agent": "paper-ingestion",
        "actions": [
            _prompt("/paper-ingestion", "Ingerir referencias", [
                "Indica la ruta o URL de los PDF a ingerir (normalmente el top 5 aceptado en plausibilidad).",
                "Cada PDF se archiva en su carpeta de tema y se convierte a Markdown: ecuaciones en LaTeX, tablas en Markdown, figuras como archivos.",
                "Local y sin llaves (Marker); nada se publica.",
            ], "Ej.: ingiere guidance/reference-papers/inbox/*.pdf"),
            _command("smith ingest <ruta-o-url> .", "Ingerir desde el CLI",
                     "Reemplaza <ruta-o-url> por el PDF o la URL."),
            _redirect("Ver artefactos ingeridos", "artifacts", "Markdown y figuras de las referencias."),
        ],
    },
    "proposal": {
        "skills": ["proposal-deliberation", "math-tutor"],
        "agent": "proposal-deliberation & math-tutor",
        "actions": [
            _prompt("/proposal-deliberation", "Deliberar la propuesta", [
                "Pide la primera versión, un cambio a la propuesta vigente o una operación de revisión (rNN).",
                "El agente es tutor: discute antes de decidir y no aplica un cambio sin tu aprobación.",
                "La matemática se escribe en bloques $$ … \\tag{N} $$; la novedad se ubica dentro del cielo SOTA.",
                "Las guías de dominio en guidance/paper-guide/ se cargan solas.",
            ], "Ej.: discutamos si la hipótesis H2 sigue en pie con la referencia de Smith 2024."),
            _redirect("Discutir el mapa conceptual", "modelo",
                      "Pilares, hipótesis y capas del concepto.", "mapa"),
            _redirect("Matemática y tutor socrático", "modelo",
                      "Ecuaciones en LaTeX, tarjeta de novedad y tutor con imágenes a mano.", "matematico"),
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
            _prompt("/experimental-deliberation", "Deliberar el diseño experimental", [
                "Pregunta que gobierna cada turno: ¿qué experimento pondría a prueba esta afirmación de la propuesta?",
                "Cada experimento declara la afirmación que prueba, su métrica y su baseline SOTA.",
                "Pide la primera versión, un cambio o una operación de revisión; nada se aplica sin tu aprobación.",
            ], "Ej.: diseña el experimento que prueba la afirmación C1 contra el baseline más fuerte del SOTA."),
            _prompt("/datasets", "Datos: toy set siempre y dataset oficial", [
                "Verbos: synth (toy set sembrado, siempre), search, license, qc, prepare y publish.",
                "dataset-scout busca en repositorios oficiales del paper, Kaggle, Hugging Face, OpenNeuro y Zenodo, y decide la licencia.",
                "dataset-curator mide la calidad (qc) y escribe una sola preparación oficial por sujeto que leen la PoC y los experimentos.",
                "publish sube un dataset privado solo con tu consentimiento explícito; hacerlo público pide un consentimiento aparte.",
            ], "Ej.: synth un toy set de 8 sujetos y busca un dataset oficial para la tarea.", optional=True),
            _prompt("/proposal-implementation", "Réplica de métodos de comparación", [
                "El agente paper-replicator replica cada baseline o paper de comparación ingerido en guidance/.",
                "Primero busca el código publicado del paper: si existe, lo adopta fijado a un commit con su licencia y audita que corresponda con el paper y esté bien implementado.",
                "Si no hay código publicado, reimplementa el método desde el Markdown ingerido; cada hiperparámetro cita su sección o ecuación.",
                "Termina con REPLICATION.md, pruebas de invariantes y una corrida corta sobre el toy set; nunca lanza una corrida remota.",
            ], "Ej.: replica el baseline de guidance/smith-2024 en ../mi-poc", optional=True),
            _prompt("/proposal-implementation", "Implementar la prueba de concepto", [
                "Convierte la última propuesta en Python contra un repositorio objetivo, o verifica una implementación existente.",
                "Indica el repositorio objetivo y si es primera pasada o una pasada posterior.",
            ], "Ej.: implementa la PoC de la propuesta r03 en ../mi-poc", optional=True),
            _redirect("Estimar tiempo y elegir dónde correr", "experiments",
                      "Antes del piloto y otra vez antes de la corrida completa: sonda de tiempo corta (una "
                      "época de un fold por brazo) en Results/timing.json; la pestaña Experimentos estima la "
                      "PoC y la corrida completa (±20%), muestra el entorno local y las opciones de corrida "
                      "local, Kaggle y Colab."),
            _prompt("/hyperparameter-search", "Búsqueda de hiperparámetros (Optuna)", [
                "Solo si la deliberación lo estimó conveniente: el protocolo declara la búsqueda y su espacio.",
                "Anidada dentro de los sujetos de entrenamiento de cada fold externo, sin ver los sujetos de prueba.",
                "Mismo presupuesto de trials para cada brazo y baseline; nunca ajusta una variable independiente que el experimento prueba.",
                "Sampler con semilla y evaluador de importancia declarado (Optuna 5 usa PED-ANOVA por defecto).",
                "report escribe contornos e importancia que la pestaña Experimentos muestra.",
                "Corre en remoto como la corrida completa y solo el operador la lanza.",
            ], "Ej.: plan para los brazos hybrid y linear con 40 trials y fANOVA como evaluador.", optional=True),
            _prompt("/experimental-implementation", "Implementar y medir los experimentos", [
                "Convierte el protocolo experimental vigente en Python y corre sus mediciones declaradas.",
                "Indica el repositorio objetivo; la verificación compara contra el protocolo y la propuesta.",
                "Antes de cualquier ensayo remoto, experiments-reviewer revisa el código (calidad, optimización, uso de GPU y pruebas estadísticas) y entrega su informe.",
            ], "Ej.: implementa E1 y E2 y reporta las métricas.", optional=True),
            _prompt("/experiment-diagrams", "Diagramas de la PoC y de los experimentos", [
                "Al aprobar la PoC (AGREED.md) dibuja el diagrama poc; al aprobar los experimentos completos (Experimental_AGREED.md), el diagrama experiments.",
                "Cada uno es una figura TikZ (PDF y PNG) en <producto>/diagrams/; también se genera con el botón \"Generar diagrama\" de la pestaña Experimentos.",
                "Valídalo tú en la pestaña Experimentos (\"Validar diagrama\") o apruébalo explícitamente en el chat con el agente, que corre validate con tus palabras: submit se niega con DIAGRAM_NOT_VALIDATED hasta entonces, y redibujarlo pide validarlo de nuevo.",
            ], "Ej.: poc para el producto implementations/mi-poc/Modelo.", optional=True),
            _prompt("/remote-parallelism", "Decidir si repartir entre cuentas", [
                "Primero estimate --timing <objetivo>/<Nombre>/Results/timing.json: el rango por etapa y host (±20%).",
                "Luego assess con las entradas medidas; --owners es el número de propietarios distintos del equipo (smith team list), nunca el de cuentas.",
                "Regla del equipo: una cuenta por persona y servicio; cada persona se registra con `smith team add --owner <slug> --name \"<nombre>\" --kaggle-username <usuario> --attest`.",
                "No coloca, no genera ni lanza nada: el veredicto lo lee el operador.",
            ], "Ej.: estima la PoC con su timing.json y evalúa repartir la corrida completa entre 3 propietarios.",
                optional=True),
            _prompt("/kaggle-accounts", "Validar las cuentas Kaggle", [
                "validate re-comprueba cada cuenta guardada contra el servicio y toma lo que haya en kaggle-inbox/ (kaggle.json o una línea `usuario token`).",
                "Solo las cuentas que el registro del equipo asigna a un propietario son workers: una por persona.",
            ], "Ej.: valida las cuentas y toma las credenciales nuevas del inbox.", optional=True, prefix="validate "),
            _prompt("/remote-execution", "Ensayo remoto y lanzamiento (Kaggle / Colab)", [
                "Orden: generate-job → submit --smoke → fetch --smoke y smoke record → readiness → gate (solo el operador) → submit → status / poll → fetch.",
                "El ledger es de solo anexar; si las cuentas no autentican, usa primero /kaggle-accounts.",
                "Solo el operador autoriza un lanzamiento: ningún agente ejecuta submit por su cuenta.",
                "submit (también --smoke) exige que hayas validado los diagramas de la PoC y de los experimentos aprobados.",
            ], "Ej.: genera el job de experiments/e1.py y prepara su ensayo smoke.", optional=True),
            _redirect("Ver la PoC y los experimentos", "experiments",
                      "Productos, veredictos y diagramas de la prueba de concepto y de los experimentos."),
        ],
    },
    "scaffolding": {
        "skills": ["paper-writing"],
        "agent": "paper-writing",
        "actions": [
            _prompt("/paper-writing", "Abrir el árbol del paper", _WRITING_GUIDE,
                    "Ej.: abre el esqueleto de secciones y bloques del paper.", prefix="skeleton "),
            _redirect("Ver secciones del paper", "sections", "Contratos de sección y bloques canónicos."),
        ],
    },
    "declarations": {
        "skills": ["paper-writing"],
        "agent": "paper-writing (mark)",
        "actions": [
            _prompt("/paper-writing", "Registrar una declaración", [
                "Una declaración fija una decisión del paper: autoría CRediT, financiación, datos y código, ética, idioma o estilo.",
                "Escribe la declaración y su valor; queda registrada con su procedencia (mark).",
            ], "Ej.: idioma del manuscrito: inglés; disponibilidad de código: GitHub público.", prefix="mark "),
            _redirect("Ver secciones del paper", "sections", "Declaraciones y bloques del manuscrito."),
        ],
    },
    "writing": {
        "skills": ["paper-writing"],
        "agent": "paper-writing (redactor)",
        "actions": [
            _prompt("/paper-writing", "Escribir un bloque", _WRITING_GUIDE,
                    "Ej.: escribe el bloque intro.motivation"),
            _redirect("Ver secciones del paper", "sections", "Estado de cada bloque."),
            _redirect("Ver el PDF", "preview", "Previsualización de paper/main.pdf."),
        ],
    },
    "figures": {
        "skills": ["figure-review"],
        "agent": "figure-review",
        "actions": [
            _prompt("/figure-review", "Revisar una figura", [
                "Indica el id de la figura ya compilada en paper/Figures/<id>.pdf.",
                "La revisión juzga si la imagen se lee por sí misma, no el texto que la describe.",
            ], "Ej.: revisa la figura fig-architecture"),
            _redirect("Ver el PDF", "preview", "Figuras en el manuscrito compilado."),
        ],
    },
    "paper": {
        "skills": ["paper-writing"],
        "agent": "pdflatex",
        "actions": [
            _redirect("Ver el PDF", "preview", "Visor PDF con recarga en vivo."),
        ],
    },
    "audit": {
        "skills": ["skill-audit"],
        "agent": "skill-audit & smith audit",
        "actions": [
            _command("smith audit . --verbose", "Auditar el workspace",
                     "Estructura y consistencia del workspace."),
            _prompt("/skill-audit", "Auditar un skill o un CLI", [
                "Nombra el sujeto: un skill, un CLI o cualquier conjunto cerrado (operaciones, subcomandos, códigos de error).",
                "La auditoría busca la brecha entre lo que el código acepta y lo que su documentación afirma.",
            ], "Ej.: audita skills/paper-writing"),
            _redirect("Ver compuertas", "pipeline",
                      "Estado de las compuertas del framework, al final de Pipeline y Avance.",
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
            return f"{action['slash']} <texto>" if not action["optional"] else action["slash"]
        if action["kind"] == "command":
            return action["command"]
    return "Compilar desde el tablero (pdflatex + bibtex)" if stage == "paper" else ""


# The files that show a phase's work, as (label, glob) pairs relative to the
# workspace. The run tracker lists them and watches them change; the PASS
# verdict itself is the server's status rule for the phase.
EVIDENCE: dict[str, tuple[tuple[str, str], ...]] = {
    "harness": (("Manifiesto del workspace", "papersmith.yaml"),
                ("Estado del framework", ".papersmith/version")),
    "plausibility": (("Pool de candidatos", "sota-pool/candidates.json"),
                     ("Atlas SOTA", "sota-pool/atlas.json"),
                     ("Constelación HTML", "sota-pool/atlas.html")),
    "ingestion": (("Referencias ingeridas", "guidance/reference-papers/*/*.md"),),
    "proposal": (("Revisiones de propuesta", "proposals/research-concept-*-r*.md"),
                 ("Cielo de la propuesta", "proposals/*.sky.json")),
    "poc_experiments": (("Protocolos experimentales", "experiments/*"),
                        ("Implementaciones", "implementations/*")),
    "scaffolding": (("Manuscrito", "paper/main.tex"),
                    ("Contratos de sección", "sections/*.md")),
    "declarations": (("Manuscrito (región de declaraciones)", "paper/main.tex"),),
    "writing": (("Manuscrito", "paper/main.tex"),),
    "figures": (("Figuras compiladas", "paper/Figures/*.pdf"),),
    "paper": (("PDF compilado", "paper/main.pdf"),),
    "audit": (("Veredicto de auditoría", ".papersmith/audit.json"),),
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
