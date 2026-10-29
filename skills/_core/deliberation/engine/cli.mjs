#!/usr/bin/env node
// Native Claude Code host for the deliberation engine.
//
// Ambient-model paradigm (design `sdd/proposal-deliberation-ambient-model`): this host
// is keyless. It builds the extension, registers `proposal_deliberation_execute`, and
// invokes it with a runtime context — the ambient model calling this CLI IS the
// tutor/reviewer/planner (deliberating in-conversation and supplying already-
// resolved `resolvedDecisions` on CREATE_SUCCESSOR); the engine never performs a
// separate model/network call itself. The engine logic, operations, guards,
// receipts, and audits are unchanged.
//
// Usage:
//   node cli.mjs '<json-request>'      # one-shot; prints the JSON result
//   echo '<json-request>' | node cli.mjs
//   node cli.mjs --serve               # NDJSON stdin -> NDJSON stdout, one
//                                       # request per line; keeps in-memory
//                                       # chat/draft session state across turns
//   node cli.mjs --dry-run '<json>'    # sets dryRun:true on every request: the
//                                       # first revision is composed and checked,
//                                       # never locked or written; refused on any
//                                       # other writing operation
//
// Performance note (design `sdd/proposal-deliberation-serve-resolve`, "Lever 1"): this
// host's own jiti cold start (compiling the engine's ~63 TS files) dominates a
// deliberation's wall-clock cost -- roughly 0.72s per spawned node process. A
// full CREATE_SUCCESSOR round used to pay that cost THREE times: once for a
// separate `node --input-type=module -e` jiti recipe to resolve the target
// entry ID (see SKILL.md), once for the preview call, once for the accept
// call. `{ operation: "RESOLVE_TARGET" }` (below) moves that resolution INSIDE
// this same process/request loop -- one `--serve` session now pays the cold
// start ONCE for resolve + preview + accept + any further versions.
//
// `RESOLVE_TARGET` is a read-only, additive operation handled directly in this
// host, bypassing `proposal_deliberation_execute`/`ProposalDeliberationOrchestrator` entirely
// (no routing, schema, or operation-semantics change to the engine). It calls
// the EXACT SAME `loadDocumentState` + `resolveSuccessorTarget` +
// `ambiguityGate` functions `orchestrator.ts` calls internally for
// `CREATE_SUCCESSOR`, via the same jiti module cache, so a resolved entryId is
// guaranteed to match what `CREATE_SUCCESSOR` itself would resolve for the
// identical (sourceFilename, query) -- no divergence. It performs no
// mutation, no publish, and no model call, and needs no ANTHROPIC_API_KEY.
//
//   { "operation": "RESOLVE_TARGET", "sourceFilename": "<file>.md", "query": "<locus description>" }
//   -> { "status": "resolved", "operation": "RESOLVE_TARGET", "entryId": "...", "blocked": false, "question": null }
//   A blocked result also carries "candidates": [{ "entryId", "headingLevel", "headingPath", "score" }, ...].
//   A query opening with level marks ("## Data") considers only headings of that level.
//
//   { "operation": "RESOLVE_TARGET", "sourceFilename": "<file>.md", "queries": [{ "query": "..." }, ...] }
//   -> { "status": "resolved", "operation": "RESOLVE_TARGET", "results": [{ "query": "...", "entryId": "...", "blocked": false, "question": null }, ...] }
//
// `STATUS` (design `sdd/proposal-deliberation-base-reconciliation`) is another
// read-only, additive, keyless operation handled directly in this host. It
// gives an ambient agent a deterministic inventory of the managed directory instead of
// eyeballing the directory before deciding which base version to resume work
// on. It reuses `parseManagedRevisionFilename` and `resolveLatestManagedRevision`
// from `revision-lifecycle-store.ts` (the SAME functions `CREATE_SUCCESSOR`'s
// own withdrawal/inventory paths use) for filename-shape recognition and
// canonical latest/tie-break resolution -- no divergent regex or tie-break
// rule. It performs no mutation, no publish, and no model call, and needs no
// ANTHROPIC_API_KEY.
//
//   { "operation": "STATUS" }
//   { "operation": "STATUS", "sourceFilename": "<file>.md" }
//   -> {
//        "status": "ok", "operation": "STATUS",
//        "managedRevisions": [{ "filename": "...", "lineage": "...", "revisionNumber": 1, "isLatest": true }, ...],
//        "latest": "<managed-stem>-r03.md" | null,
//        "multipleActive": false, "candidates": [],
//        "nonManagedFiles": ["notes.md"],
//        "sourceClassification"?: "LATEST" | "OLDER_MANAGED" | "UNMANAGED" | "NOT_FOUND",
//        "newerRevisionNumbers"?: [2, 3]   // only present when sourceClassification is OLDER_MANAGED
//      }
//
// Environment:
//   PROPOSAL_DELIBERATION_PROJECT_ROOT  managed project root (default: process.cwd())
//   PROPOSAL_DELIBERATION_SESSION_ID    stable session identity (default: cli session)

import { createInterface } from 'node:readline';
import { readdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createJiti } from 'jiti';

const engineDir = path.dirname(fileURLToPath(import.meta.url));
const jiti = createJiti(import.meta.url);

const host = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));

const projectRoot = process.env.PROPOSAL_DELIBERATION_PROJECT_ROOT ?? process.cwd();
const sessionId = process.env.PROPOSAL_DELIBERATION_SESSION_ID ?? 'deliberation-cli-session';

/** Runtime context: the exact ExtensionContext surface the engine reads. No model
 * identity or model-auth registry is wired -- the keyless CREATE_SUCCESSOR +
 * `resolvedDecisions` path never needs one. */
const ctx = {
	sessionManager: { getSessionId: () => sessionId },
	hasUI: false,
	ui: { confirm: async () => false },
};

// Build the extension once so in-memory session state (chat conversations,
// draft registry) survives across requests within a single process — matching
// how pi loaded the extension once per long-running session.
const registered = [];
host.createProposalDeliberationExtension({ projectRoot })({
	registerTool: (tool) => registered.push(tool),
	on: () => {},
});
const tool = registered.find((candidate) => candidate.name === 'proposal_deliberation_execute');
if (!tool) {
	process.stderr.write('proposal_deliberation_execute tool was not registered\n');
	process.exit(1);
}

// Same jiti instance/module cache the `host` import above already populated --
// `orchestrator.ts` (reached transitively through `proposal-workspace.ts`)
// already imports these exact three modules, so re-importing them here by
// path returns the SAME cached, already-compiled module instances (no extra
// compile cost, and literally the same function objects `CREATE_SUCCESSOR`
// resolves through internally).
const domainProfileModule = await jiti.import(path.join(engineDir, 'domain-profile.ts'));
const documentStateModule = await jiti.import(path.join(engineDir, 'document-state.ts'));
const targetResolverModule = await jiti.import(path.join(engineDir, 'target-resolver.ts'));
const ambiguityGateModule = await jiti.import(path.join(engineDir, 'ambiguity-gate.ts'));
const revisionLifecycleModule = await jiti.import(path.join(engineDir, 'revision-lifecycle-store.ts'));
const artifactNamingModule = await jiti.import(path.join(engineDir, 'artifact-naming.ts'));

// Deliberately NOT memoizing `loadDocumentState` results across calls within a
// `--serve` session (would-be item 2 of the amortization design): the real
// CREATE_SUCCESSOR path calls `materializeCompositeTarget(state, target)`,
// which MUTATES the resolved `DocumentState`'s `structuralIndex` (`entries`/
// `byId`) IN PLACE to register the composite entry it just resolved. If a
// cached `DocumentState` object were shared/returned across independent
// RESOLVE_TARGET/preview/accept calls in the same process, one call's
// materialized composite entries would leak into and contaminate a later,
// unrelated call's resolution against the "same" (root, filename,
// documentSha256) key -- a genuine staleness/correctness hazard, not merely a
// performance question. Skipping the cache keeps every call's `DocumentState`
// independent and correct; the persistent-process reuse above (no per-call
// jiti cold start) is the amortization win.
async function resolveOneTarget(sourceFilename, query) {
	if (typeof sourceFilename !== 'string' || !sourceFilename) {
		return { entryId: null, blocked: true, question: 'RESOLVE_TARGET_SOURCE_FILENAME_REQUIRED' };
	}
	if (typeof query !== 'string' || !query.trim()) {
		return { entryId: null, blocked: true, question: 'RESOLVE_TARGET_QUERY_REQUIRED' };
	}
	let state;
	try {
		state = await documentStateModule.loadDocumentState(projectRoot, sourceFilename);
	} catch (error) {
		return { entryId: null, blocked: true, question: error?.message ?? String(error) };
	}
	const resolution = targetResolverModule.resolveSuccessorTarget(state, query);
	const gate = ambiguityGateModule.ambiguityGate(resolution.candidates);
	return {
		entryId: gate.candidate?.entryId ?? null,
		blocked: gate.blocked,
		question: gate.question ?? null,
		// A blocked locus lists every candidate, each with its level and real
		// heading path, so the caller can name the one it meant (by its own
		// heading words, or by level marks for an outer section).
		...(gate.blocked && gate.candidates.length ? { candidates: gate.candidates.map(candidateSummary) } : {}),
		// A `replace` decision must carry the entry's WHOLE new text, so a caller
		// that cannot read the current text cannot write a faithful one: it either
		// guesses the boundaries or silently drops whatever else the entry holds.
		// The resolver already computes this for composites; simple entries come
		// from their own byte range in the same state.
		text: gate.blocked ? null : candidateText(state, gate.candidate),
	};
}

function candidateSummary(candidate) {
	return { entryId: candidate.entryId, headingLevel: candidate.headingLevel ?? null, headingPath: candidate.headingPath ?? [], score: candidate.score };
}

function candidateText(state, candidate) {
	if (!candidate) return null;
	if (typeof candidate.composite?.exactProvidedText === 'string') return candidate.composite.exactProvidedText;
	const entry = state.structuralIndex?.entries?.find(item => item.entryId === candidate.entryId);
	if (!entry || typeof entry.startByte !== 'number' || typeof entry.endByte !== 'number') return null;
	return state.documentBytes.subarray(entry.startByte, entry.endByte).toString('utf8');
}

async function runResolveTarget(request) {
	if (Array.isArray(request.queries)) {
		const results = [];
		for (const item of request.queries) {
			const resolved = await resolveOneTarget(item?.sourceFilename ?? request.sourceFilename, item?.query);
			results.push({ query: item?.query, ...resolved });
		}
		return { status: 'resolved', operation: 'RESOLVE_TARGET', results };
	}
	const resolved = await resolveOneTarget(request.sourceFilename, request.query);
	return { status: 'resolved', operation: 'RESOLVE_TARGET', ...resolved };
}

// Same literal byte marker every other engine module (draft-materialization.ts,
// orchestrator.ts, initial-revision-creation.ts, patch-compiler.ts,
// proposal-workspace.ts, revision-lifecycle-store.ts) already defines as its
// own local constant -- an established codebase convention, not a new
// divergence risk. The filename-shape recognition and canonical latest/tie-
// break rule themselves are NOT reimplemented here: they come straight from
// `parseManagedRevisionFilename`/`resolveLatestManagedRevision` below.
const STATUS_MARKER = artifactNamingModule.artifact.marker;

function classifySourceFilename(sourceFilename, { proposalEntryNames, managedRevisions, latest }) {
	if (typeof sourceFilename !== 'string' || !sourceFilename || path.basename(sourceFilename) !== sourceFilename) {
		return { sourceClassification: 'NOT_FOUND' };
	}
	if (!proposalEntryNames.has(sourceFilename)) return { sourceClassification: 'NOT_FOUND' };
	const managedEntry = managedRevisions.find((revision) => revision.filename === sourceFilename);
	if (!managedEntry) return { sourceClassification: 'UNMANAGED' };
	if (latest !== null && managedEntry.filename === latest) return { sourceClassification: 'LATEST' };
	const newerRevisionNumbers = managedRevisions
		.filter((revision) => revision.lineage === managedEntry.lineage && revision.revisionNumber > managedEntry.revisionNumber)
		.map((revision) => revision.revisionNumber)
		.sort((a, b) => a - b);
	return { sourceClassification: 'OLDER_MANAGED', newerRevisionNumbers };
}

/** The empty inventory a project that has not created the managed directory yet must report.
 * A brand-new project is exactly the state `CREATE_INITIAL_REVISION` exists for, and
 * SKILL.md tells the agent to run `STATUS` FIRST -- before anything has been created.
 * Reporting a raw `ENOENT ... scandir <abs path>` there would both break that documented
 * first step and leak an absolute filesystem path into the agent's transcript. */
function emptyStatusInventory() {
	return { managedRevisions: [], latest: null, multipleActive: false, candidates: [], nonManagedFiles: [], proposalEntryNames: new Set() };
}

async function readProposalsInventory() {
	const managedDirectory = path.join(projectRoot, artifactNamingModule.artifact.directory);
	let entries;
	try {
		entries = await readdir(managedDirectory, { withFileTypes: true });
	} catch (error) {
		// Only a genuinely ABSENT directory is the benign pre-creation state. An existing
		// but unreadable the managed directory (a file in its place, a permission failure) still
		// fails closed -- STATUS must never report "empty" for a workspace it could not read.
		if (error?.code === 'ENOENT') return emptyStatusInventory();
		throw error;
	}
	const proposalEntryNames = new Set();
	const managedRevisions = [];
	const nonManagedFiles = [];
	for (const entry of entries) {
		if (!entry.isFile()) continue;
		proposalEntryNames.add(entry.name);
		if (entry.name === '.gitkeep' || entry.name === '.DS_Store' || entry.name.startsWith('.')) continue;
		let identity;
		try {
			identity = revisionLifecycleModule.parseManagedRevisionFilename(entry.name);
		} catch {
			nonManagedFiles.push(entry.name);
			continue;
		}
		let bytes;
		try {
			bytes = await readFile(path.join(managedDirectory, entry.name));
		} catch {
			nonManagedFiles.push(entry.name);
			continue;
		}
		if (!bytes.subarray(0, STATUS_MARKER.length).equals(STATUS_MARKER)) {
			nonManagedFiles.push(entry.name);
			continue;
		}
		managedRevisions.push({ filename: entry.name, lineage: identity.lineage, revisionNumber: identity.revisionNumber });
	}
	managedRevisions.sort((a, b) => a.revisionNumber - b.revisionNumber || a.filename.localeCompare(b.filename));
	nonManagedFiles.sort((a, b) => a.localeCompare(b));

	// Same canonical resolver every other "latest managed revision" call site
	// (CREATE_SUCCESSOR's orchestrator, draft-materialization) shares -- no
	// divergent tie-break rule here.
	const resolution = await revisionLifecycleModule.resolveLatestManagedRevision(projectRoot, { markerOwned: true });
	const latest = resolution.status === 'empty' ? null : resolution.latest.filename;
	const multipleActive = resolution.status === 'multiple';
	const candidates = multipleActive ? [...resolution.candidates.map((candidate) => candidate.filename)].sort() : [];

	const managedRevisionsWithLatest = managedRevisions.map((revision) => ({ ...revision, isLatest: latest !== null && revision.filename === latest }));
	return { managedRevisions: managedRevisionsWithLatest, latest, multipleActive, candidates, nonManagedFiles, proposalEntryNames };
}

async function runStatus(request) {
	const { managedRevisions, latest, multipleActive, candidates, nonManagedFiles, proposalEntryNames } = await readProposalsInventory();

	const result = {
		status: 'ok',
		operation: 'STATUS',
		// The north, above the inventory. `STATUS` lists what has been
		// published; nothing in that list says what any of it was FOR, and a
		// session reading an inventory without the purpose has the facts and
		// not the destination. Its text is the host-chosen profile's, never
		// the engine's own -- see `domain-profile.ts`'s `objective` field.
		objective: domainProfileModule.DOMAIN.objective,
		managedRevisions,
		latest,
		multipleActive,
		candidates,
		nonManagedFiles,
	};

	if (request.sourceFilename !== undefined) {
		Object.assign(result, classifySourceFilename(request.sourceFilename, { proposalEntryNames, managedRevisions, latest }));
	}
	return result;
}

// The CLOSED public operation set. The two host-handled read-only operations plus the
// exact enum `proposal_deliberation_execute` declares for its `operation` parameter.
// The tool's TypeBox schema is NOT enforced on this path (the host calls `tool.execute`
// directly, not through a validating dispatcher), so an unrecognized `operation` used to
// be carried straight into the orchestrator, where `request.operation` becomes the
// resolved `intent` WITH `destructiveIntent:true` and the natural-language classifier's
// pending/unresolved questions cleared (`orchestrator.ts` `execute()`). Accepting an
// operation outside this set is therefore not a cosmetic echo -- it is an unvalidated
// path into destructive intent. Reject it here instead.
const HOST_OPERATIONS = new Set(['STATUS', 'RESOLVE_TARGET']);
const TOOL_OPERATIONS = new Set([
	'WITHDRAW_REVISION',
	'RESTORE_WITHDRAWN_REVISION',
	'CREATE_SUCCESSOR',
	'CREATE_INITIAL_REVISION',
	'ADOPT_INITIAL_REVISION',
	'CHAT_DELIBERATION',
	'CLOSE_DELIBERATION',
	'MAINTENANCE',
]);

class RequestRejected extends Error {}

/** Validates the request ENVELOPE only -- never an operation's own semantics, which stay
 * entirely the engine's concern. Without this the host dereferenced caller-controlled
 * fields directly and surfaced internal `TypeError`s (`Cannot read properties of
 * undefined (reading 'toLowerCase')`) as the public answer to a malformed payload. */
function validateRequest(request) {
	if (typeof request !== 'object' || request === null || Array.isArray(request)) {
		throw new RequestRejected('MALFORMED_REQUEST: the request must be a JSON object');
	}
	const { operation } = request;
	if (operation !== undefined && (typeof operation !== 'string' || (!HOST_OPERATIONS.has(operation) && !TOOL_OPERATIONS.has(operation)))) {
		throw new RequestRejected(`UNKNOWN_OPERATION: ${JSON.stringify(operation)} is not one of ${[...HOST_OPERATIONS, ...TOOL_OPERATIONS].join(', ')}`);
	}
	if (HOST_OPERATIONS.has(operation)) return;
	// `instruction` is a required, minLength-1 string in the tool's own declared schema.
	// A blank-but-present string still reaches the engine, which answers with its own
	// typed blocker (for example INITIAL_IDEA_REQUIRED) -- that stays unchanged.
	if (typeof request.instruction !== 'string' || request.instruction.length < 1) {
		throw new RequestRejected('INSTRUCTION_REQUIRED: every operation except STATUS and RESOLVE_TARGET needs a non-empty instruction string');
	}
}

// `--dry-run`: the CLI spelling of `dryRun: true`, applied to every request this process
// reads (one-shot or `--serve`). The two host-handled operations never write, so it means
// nothing to them; every tool operation receives the field and the engine decides -- it runs
// the dry run where one exists and refuses DRY_RUN_UNSUPPORTED everywhere else, so a caller
// who asked for no writes is never answered with one.
const dryRunFlag = process.argv.slice(2).includes('--dry-run');

let sequence = 0;
async function run(request) {
	validateRequest(request);
	if (request.operation === 'RESOLVE_TARGET') return runResolveTarget(request);
	if (request.operation === 'STATUS') return runStatus(request);
	if (dryRunFlag) request = { ...request, dryRun: true };
	const result = await tool.execute(`cli-${++sequence}`, request, undefined, undefined, ctx);
	return result.details ?? result;
}

function parseRequest(text) {
	const trimmed = text.trim();
	if (!trimmed) throw new Error('empty request');
	return JSON.parse(trimmed);
}

async function readStdin() {
	const chunks = [];
	for await (const chunk of process.stdin) chunks.push(chunk);
	return Buffer.concat(chunks).toString('utf8');
}

// WHY THIS SKILL WAS INVOKED, AND WHERE IT HAS TO ARRIVE.
//
// `STATUS` answers *where am I* by listing what has been published; the north
// answers *what is this for*, which no listing implies. A session that hits an
// error, an interruption or a gap consults it, locates itself, resolves what
// blocks, and rejoins -- rather than improvising forward, which is what an
// agent does when a blocker detaches it from the purpose. Emitted at exactly
// three sites: `runStatus`, above, and the two CLI-level error paths below.
//
// The STRUCTURE is the engine's -- its shape, its presence at these three
// sites -- but the TEXT is not: it lives in the host-chosen domain profile
// (`domain-profile.ts`'s `objective` field), never spelled here. A profile
// says what THIS domain is called and which notation it uses, and a second
// domain measurably does NOT say the same north the first one does -- its
// `purpose`, `composed`-equivalent stage and `arrival` all name what THAT
// domain is about. The engine has no domain of its own, so the north is not
// its text to declare, only its structure to carry.
const args = process.argv.slice(2);

if (args.includes('--serve')) {
	const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
	for await (const line of rl) {
		if (!line.trim()) continue;
		try {
			const result = await run(parseRequest(line));
			process.stdout.write(`${JSON.stringify(result)}\n`);
		} catch (error) {
			process.stdout.write(`${JSON.stringify({ status: 'error', message: error?.message ?? String(error), objective: domainProfileModule.DOMAIN.objective })}\n`);
		}
	}
} else {
	const inline = args.find((arg) => !arg.startsWith('--'));
	const raw = inline ?? (await readStdin());
	try {
		const result = await run(parseRequest(raw));
		process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
	} catch (error) {
		process.stdout.write(`${JSON.stringify({ status: 'error', message: error?.message ?? String(error), objective: domainProfileModule.DOMAIN.objective }, null, 2)}\n`);
		process.exit(1);
	}
}
