#!/usr/bin/env node
// This skill's entry point into the shared deliberation engine.
//
// The engine under `_core/` serves no domain of its own and refuses to start
// without one, so the only thing this file does is name which domain is asking
// before handing over. Every argument, stdin mode and exit code is the engine's.
//
// `??=` rather than `=`: an explicit DELIBERATION_DOMAIN_PROFILE in the
// environment is a deliberate override (a test fixture, a sibling domain being
// exercised through this launcher) and must win over the default.
import { fileURLToPath } from 'node:url';
process.env.DELIBERATION_DOMAIN_PROFILE ??= fileURLToPath(new URL('./profile.ts', import.meta.url));
await import('../_core/deliberation/engine/cli.mjs');
