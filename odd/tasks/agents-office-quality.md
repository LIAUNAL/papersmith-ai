# Agents Office quality (resolution, text, agents, interactions)

Objective: make the 3D Agents Office (static/office3d.js, office-panel.js) sharp, fast on software WebGL, readable, with better agent models and visible orchestrator/agent/Engram interactions.
Branch: feat/agents-office-quality (from main 0.72.0). Delivery: ask-on-risk. Runner: `.venv/bin/python -m pytest` (+ node harness) and a Chromium e2e measurement on this PC (llvmpipe).

## Specs

- S1 (Request): "revisa el panle de agentes office tipo weherd, la resolucikn y calidad se ve muy nal, explora como podemos ampliar tamaño de letrar, mejorar mecanicas, calidad de los dibujos tipo agente y mostrar de forma mas clara la interaccion entre agentes con mejor calidad visual". Approved plan ("si"), three deliveries in order:
- S2 (Delivery 1, sharpness + speed + text + camera): merge the repeated static pieces into a few draws; shadows only while the measured frame rate allows (automatic quality tier); names and states as HTML labels over the scene that follow the dashboard text size ("A ×1"); camera opens framing the orchestrator and the active agents, drag to pan, wheel zoom, click flies to an agent, "Fit all" button. Measured on this PC.
- S3 (Delivery 2, agents): rounded bodies, faces with blinking eyes, several hair styles, shirt color per tramo, a role object on the desk, a soft shadow under each person.
- S4 (Delivery 3, interactions): dispatch (orchestrator -> agent) and return (agent -> orchestrator, check mark) visible with a thick arc, a travelling document and a bubble; Engram saves/loads larger and brighter with the brain showing the action; an events strip with the last 8 events and their time; desks grouped into tramo zones with a colored floor and a sign.
- S5 (Kept): read-only panel, measured states only (no invented activity), vendored three.js 0.183.0 core only (no addons, no network), i18n keys in en.js and es.js, docs/terminals.md updated.

## Tasks

- [x] T1 [S2, S5] Merged geometry + quality tier + HTML labels + camera controls — inline
- [x] T2 [S3, S5] Agent models + role props + blob shadows — inline
- [x] T3 [S4, S5] Flows, couriers, bubbles, events strip, tramo zones + docs — inline

## Log

- L1 (2026-11-10) User request (verbatim): "luego, revisa el panle de agentes office tipo weherd, la resolucikn y calidad se ve muy nal, explora como podemos ampliar tamaño de letrar, mejorar mecanicas, calidad de los dibujos tipo agente y mostrar de forma mas clara la interaccion entre agentes con mejor calidad visual". Then, on the three-delivery proposal: "si".
- L2 Baseline (llvmpipe, 1440x900): dpr1 16.3 fps (worst 183 ms), dpr2 12.5 fps (worst 233 ms); ~1200 meshes drawn twice (shadow pass); people ~15 px tall, label subtitle ~7 px.
- L3 Route: all three deliveries edit the same two files (office3d.js, office-panel.js) and depend on each other, so no parallel writer reason: inline.
- L4 Evidence (Chromium, llvmpipe, 1440x900, fake agent timeline): dpr1 34 fps (worst frame 34-50 ms), dpr2 33.8 fps, tier settles at 1 (dpr1) / 0 (dpr2); ~325-400 draw calls (was ~1200 x2). Tag name 13.8 px, status 11.8 px (was ~7 px), 20.6 px at A x1.5. Events strip showed dispatch, Engram save/load and done in order with bubbles; click opens the card and flies (half 6.5); drag pans; wheel zooms; Fit all / Follow activity reframe. Two defects found and fixed in the run: tags never placed (NaN start position) and an orphan Engram tag after rebuild; duplicate CLI names deduplicated.
- L5 Tests: office + i18n 82 passed (new EventsModelTests, scene/HUD wiring); full suite 9896 passed, 1 failure (vocabulary scan flagged one platform name in roleOf) fixed by dropping it.
- L6 Commits: 370d8762 (scene, panel, i18n, tests: T1-T3), docs commit (terminals.md + this log). RDD assess: medium, review_due false (under_budget). Flaky under xdist only: test_the_toy_targets_left_nothing_behind (pass serially, untouched code).
- L7 Gentle AI review (reliability lens, lineage review-a73edffc579ff969): approved and acknowledged; informational advisories R3-001 office3d.js:593-605 (transition animations untested by committed tests), R3-002 office3d.js:503 (maxHalf from a possibly unsized container), R3-003 test suggestion — follow-ups, not blockers.
