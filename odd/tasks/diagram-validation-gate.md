# Diagram validation gate

Objective: the operator validates each experiment diagram in the dashboard before any run is launched.
Branch: feat/diagram-validation-gate · Delivery: single-pr · Runner: pytest (PYTHONPATH=<wt>/src:<wt>), node --test

## Specs

- S1 Generation at each approval: "al definir la prueba de concepto y luego la prueba de experimentos, debe generarse los diagramas". When `AGREED.md` (proof of concept) and later `Experimental_AGREED.md` (full experiments) exist, the flow (Phase 5 actions, flow guides, implementation skills) asks for `/experiment-diagrams poc` and then `/experiment-diagrams experiments`.
- S2 Operator validation: "deben ser validados por el usuario atnes de lanzar corridas". Decision (2026-10-26): "Botón del dashboard (Recomendado)" — a "Validar diagrama" button in the Experimentos panel records the validation together with the PNG fingerprint; no CLI command writes it; regenerating the diagram invalidates it.
- S3 Launch gate: `remote_cli.py submit` (both `--smoke` and the full launch) refuses `DIAGRAM_NOT_VALIDATED` while a diagram whose approval marker exists in the product is missing, unvalidated, or changed since validation. Assumption: local engine `step` runs are not gated (they are the development of the proof of concept itself).
- S4 Triggers: "debe permitirse lanzar la generacion de dichos diagramas como boton en el panel de expdrimentos o como comando con el assistente cli". The panel button "Generar diagrama" (exists) and the slash command `/experiment-diagrams <kind>` (exists) both regenerate; the panel also offers regeneration of an existing diagram.

## Tasks

- [x] T1 S2,S4 inline — validation record in `diagram_cli.py` (`status` reports it; `render` drops it) + panel view/button + `POST /api/experiments/diagrams/validate`.
- [x] T2 S3 inline — `DIAGRAM_NOT_VALIDATED` in `remote_cli.cmd_submit`; docs in remote-execution SKILL.md.
- [x] T3 S1 inline — Phase 5 actions and flow text (template + four guides) name generation and validation before launch.

## Log

- L1 (2026-10-26) "luego revisa y asegurate de que en los flujos de smith, al definir la prueba de concepto y luego la prueba de experimentos, debe generarse los diagramas y deben ser validados por el usuario atnes de lanzar corridas. y debe permitirse lanzar la generacion de dichos diagramas como boton en el panel de expdrimentos o como comando con el assistente cli"
- L2 (2026-10-26) Validation recorded by: "Botón del dashboard (Recomendado)".
- L3 Map: no validation record existed; no launch path read the diagrams; Phase 5 actions had no `/experiment-diagrams` prompt.
- L4 RED→GREEN: T1 10 tests (diagram CLI, view, `POST /api/experiments/diagrams/validate`, panel render); T2 6 tests in `ConsentGateTests`; affected suites 3601 passed. Pre-existing local failures (also at base): 3 workspace/convention e2e, 5 `GateInterpreterTests`; `test_the_toy_targets_left_nothing_behind` fails only under xdist, passes alone.
- L5 Endpoint refuses requests without an Origin header (curl, an agent's shell); a local agent can still forge one, which the skills forbid.
- L6 Verifier: S1 PASS, S2 PARTIAL (B1: record written through a planted symlink), S3 PASS, S4 PASS. Fixed: atomic temp-file + os.replace; refusal names no absolute path; regression tests added.
