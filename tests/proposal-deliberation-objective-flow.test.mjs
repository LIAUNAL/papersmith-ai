// The north: why a deliberation session was invoked and where it has to arrive.
//
// Structure lives in the engine: its shape, its presence in `STATUS`, its
// presence on both CLI-level error paths -- pinned below, core-scoped, and
// independent of any one domain. Its TEXT does not: it is the host-chosen
// profile's own, declared in `<skill>/profile.ts`'s `objective` field. This
// suite discovers every profile that declares one, pairs it with its sibling
// `SKILL.md`, and checks the pair agrees by text -- rather than naming one
// skill's stages, which is what let a second domain silently inherit the
// first domain's destination (change 11, "a north a second domain can hold").
//
// The doctrine-match comparison additionally holds the `establishes` and
// `behindWhen` columns equal, not only the stage names -- closing the gap in
// which a profile's stage content and `SKILL.md`'s stage table could drift
// while the previous version of this suite stayed green (change "the two
// declarations a plan owes").
import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';

const ENGINE_PATH = path.resolve('skills/_core/deliberation/engine/cli.mjs');
const CORE_DIR = path.resolve('skills/_core/deliberation/engine');
const SKILLS_DIR = path.resolve('skills');
const engine = await readFile(ENGINE_PATH, 'utf8');

/** Extracts the `<key>: { ... },` block at exactly one-tab indentation -- the
 * shape every `profile.ts` in this repo uses for its top-level object fields.
 * Nested closers (stage objects, arrays) sit at two-or-more tabs, so the
 * first one-tab `},` after the opening line is the block's own close. */
function extractBlock(source, key) {
	const openMarker = `\n\t${key}: {`;
	const openIdx = source.indexOf(openMarker);
	if (openIdx === -1) return null;
	const blockStart = openIdx + 1;
	const closeIdx = source.indexOf('\n\t},', blockStart);
	if (closeIdx === -1) return null;
	return source.slice(blockStart, closeIdx);
}

/** Parses the profile's `objective.stages` array into stage/establishes/
 * behindWhen triples via one combined per-stage match, instead of three
 * independent regexes scanning the whole block -- which silently misaligned
 * their index-paired arrays whenever a stage omitted a field. `stageCount` is
 * derived independently, from the bare `stage: "..."` token alone, so a stage
 * the combined regex failed to match (a malformed or reordered field) is
 * caught rather than silently shrinking `triples`. */
function parseObjective(block) {
	const stageCount = [...block.matchAll(/\n\t+stage:\s*"([^"]+)"/g)].length;
	const triples = [...block.matchAll(/stage:\s*"([^"]+)",\s*establishes:\s*"([^"]*(?:\\.[^"]*)*)",\s*behindWhen:\s*"([^"]*(?:\\.[^"]*)*)",/g)]
		.map((m) => ({ stage: m[1], establishes: m[2], behindWhen: m[3] }));
	assert.equal(
		triples.length,
		stageCount,
		`parsed ${triples.length} stage/establishes/behindWhen triples but found ${stageCount} "stage:" declarations -- a stage is missing establishes or behindWhen, or the fields are out of order`,
	);
	const stages = triples.map((t) => t.stage);
	const behindWhens = triples.map((t) => t.behindWhen);
	// `humanStops` is a string ARRAY, not an object -- `extractBlock` looks for `{`,
	// so it is parsed directly here instead.
	const arrivalMatch = block.match(/\n\t+arrival:\s*"([^"]*(?:\\.[^"]*)*)"/);
	const humanStopsMatch = block.match(/\n\t+humanStops:\s*\[([\s\S]*?)\n\t+\],/);
	const humanStops = humanStopsMatch ? [...humanStopsMatch[1].matchAll(/"([^"]*(?:\\.[^"]*)*)"/g)].map((m) => m[1]) : [];
	const entrances = [...block.matchAll(/arrivesAt:\s*"([^"]+)"/g)].map((m) => m[1]);
	return { stages, behindWhens, triples, arrival: arrivalMatch ? arrivalMatch[1] : null, humanStops, entrances };
}

/** Parses the objective-flow doctrine table's body rows into stage/establishes/
 * behindWhen triples. Splits on a pipe not preceded by a backslash, so a cell
 * containing its own backtick span (`` `STATUS` named the latest… ``) parses
 * correctly instead of choking a raw backtick split -- and an escaped pipe
 * inside a cell survives as a literal `|` rather than ending the cell early. */
function parseDoctrineTable(skillSource) {
	const start = skillSource.indexOf('## The objective flow');
	assert.ok(start >= 0, 'SKILL.md has no objective-flow section');
	const arrivalIdx = skillSource.indexOf('**Arrival:**', start);
	assert.ok(arrivalIdx >= 0, "SKILL.md's objective-flow section has no **Arrival:** line");
	const table = skillSource.slice(start, arrivalIdx);
	const lines = table.split('\n').filter((line) => line.startsWith('| `'));
	return lines.map((line) => {
		const raw = line.split(/(?<!\\)\|/u);
		assert.equal(raw[0], '', `doctrine row does not open with a bare pipe: ${line}`);
		assert.equal(raw[raw.length - 1], '', `doctrine row does not close with a bare pipe: ${line}`);
		const cells = raw.slice(1, -1).map((cell) => cell.trim().replace(/\\\|/gu, '|'));
		assert.equal(cells.length, 3, `doctrine row has ${cells.length} cells, expected exactly 3: ${line}`);
		return { stage: cells[0].replace(/^`|`$/gu, ''), establishes: cells[1], behindWhen: cells[2] };
	});
}

async function discoverPairs() {
	const entries = await readdir(SKILLS_DIR, { withFileTypes: true });
	const pairs = [];
	for (const entry of entries) {
		if (!entry.isDirectory() || entry.name === '_core') continue;
		const profilePath = path.join(SKILLS_DIR, entry.name, 'profile.ts');
		const skillPath = path.join(SKILLS_DIR, entry.name, 'SKILL.md');
		const profileSource = await readFile(profilePath, 'utf8').catch(() => null);
		if (profileSource === null) continue;
		const objectiveBlock = extractBlock(profileSource, 'objective');
		if (objectiveBlock === null) continue;
		const skillSource = await readFile(skillPath, 'utf8').catch(() => null);
		pairs.push({ skillName: entry.name, profileSource, objective: parseObjective(objectiveBlock), skillSource });
	}
	return pairs;
}

const pairs = await discoverPairs();
const norm = (text) => text.replace(/\s+/g, ' ').trim();
// A stage whose closing condition is a person's word, not a byte the engine can
// read -- the honest gap this project's own doctrine insists on naming rather
// than papering over.
const REFUSES_MEASUREMENT = /the user said so|nothing (?:here )?measures/i;

/** Normalizes doctrine text and profile text onto one comparable shape:
 * unescape the TS string escapes this repo's `objective` fields actually use,
 * strip backtick/bold markers, fold an em-dash, en-dash or a double hyphen to
 * a space, lowercase, replace every remaining non-alphanumeric run with a
 * space, then trim. */
function normalizeDoctrine(text) {
	return text
		.replace(/\\"/gu, '"')
		.replace(/\\n/gu, ' ')
		.replace(/\\t/gu, ' ')
		.replace(/[`*]/gu, '')
		.replace(/--|[—–]/gu, ' ')
		.toLowerCase()
		.replace(/[^a-z0-9]+/gu, ' ')
		.trim();
}

/** Everything before the first `": "` that sits outside a backtick span -- the
 * doctrine table legitimately omits a colon-introduced rationale clause the
 * profile field is allowed to keep (design D5, option (d), "head-equality").
 * Returns the text unchanged when no such colon exists, so a cell with no
 * rationale clause is compared in full on both sides. */
function head(text) {
	let inBacktick = false;
	for (let at = 0; at < text.length - 1; at += 1) {
		if (text[at] === '`') {
			inBacktick = !inBacktick;
			continue;
		}
		if (!inBacktick && text[at] === ':' && text[at + 1] === ' ') return text.slice(0, at);
	}
	return text;
}

// The third (study-protocol-deliberation) was a decision: D1, accepted by the operator in
// odd/tasks/paper-type-lines.md L47. A fourth is a decision again.
test('exactly three profiles declare a north (proposal, experimental, study-protocol; a fourth is a decision)', () => {
	assert.equal(pairs.length, 3, `expected 3 profiles declaring objective (proposal-deliberation, experimental-deliberation and the decided third, study-protocol-deliberation), found ${pairs.length}: ${pairs.map((p) => p.skillName).join(', ')}`);
});

test('every error path carries the north', () => {
	// A blocked session is exactly the one that has lost the purpose. Both of
	// the engine's two output paths are pinned, so a third added later has to
	// be a decision rather than a drift.
	const paths = [...engine.matchAll(/status: 'error', message: [^}]*}/g)].map((m) => m[0]);
	assert.equal(paths.length, 2, 'the engine has two error paths; that count is what this pins');
	for (const emitted of paths) {
		assert.match(emitted, /objective: domainProfileModule\.DOMAIN\.objective/, 'an error reaches a reader without the north');
	}
});

test('STATUS reports it above the inventory', () => {
	assert.match(engine, /operation: 'STATUS',\n\t\t\/\/[\s\S]{0,700}?objective: domainProfileModule\.DOMAIN\.objective,/);
});

test('C-1: no core file declares a north\'s text, only its structure', async () => {
	// The absence layer (design.md, Decision C, C-1): would have caught the
	// original defect regardless of what any domain called its stages, because
	// it checks for a STRING LITERAL assigned to these keys -- not the type's
	// own field names (`readonly purpose: string;` has no literal after the
	// colon, and is not a leak).
	const coreEntries = await readdir(CORE_DIR, { recursive: true, withFileTypes: true });
	const coreFiles = coreEntries.filter((e) => e.isFile() && (e.name.endsWith('.ts') || e.name.endsWith('.mjs')));
	assert.ok(coreFiles.length > 40, `expected the whole engine, scanned ${coreFiles.length}`);
	const leaks = [];
	for (const entry of coreFiles) {
		const file = path.join(entry.parentPath ?? entry.path, entry.name);
		const source = await readFile(file, 'utf8');
		const rel = path.relative(CORE_DIR, file);
		if (/OBJECTIVE_FLOW/.test(source)) leaks.push(`${rel} still declares OBJECTIVE_FLOW`);
		if (/(?:purpose|arrival|behindWhen):\s*['"]/.test(source)) leaks.push(`${rel} spells a purpose/arrival/behindWhen string literal`);
	}
	assert.deepEqual(leaks, [], 'the north is reached only via DOMAIN.objective, never declared inline in core');
});

for (const { skillName, objective, skillSource } of pairs) {
	test(`${skillName}: the profile declares a non-empty ordered north`, () => {
		assert.ok(objective.stages.length > 0, `${skillName} declares no stages`);
		assert.ok(objective.arrival, `${skillName} declares no arrival`);
		assert.ok(objective.humanStops.length >= 1, `${skillName} declares no humanStops entry`);
	});

	test(`${skillName}: at least one stage refuses to claim it can be measured`, () => {
		// The honest gap. If every stage pretended to be byte-decidable, an agent
		// could close all of them on its own word -- a failure this project has
		// already seen once.
		assert.ok(objective.behindWhens.some((text) => REFUSES_MEASUREMENT.test(text)),
			`${skillName} declares no stage whose behindWhen names an unmeasurable, human-only condition`);
	});

	test(`${skillName}: the doctrine states the same stages, in the same order`, () => {
		assert.ok(skillSource, `${skillName}/SKILL.md is missing`);
		const rows = parseDoctrineTable(skillSource).map((row) => row.stage);
		assert.deepEqual(rows, objective.stages, `${skillName}'s doctrine table does not match its profile's declared stages`);
	});

	test(`${skillName}: the doctrine's arrival text matches the profile's, whitespace-normalized`, () => {
		const start = skillSource.indexOf('**Arrival:**');
		assert.ok(start >= 0, `${skillName}/SKILL.md has no **Arrival:** line`);
		const rest = skillSource.slice(start + '**Arrival:**'.length);
		const docArrival = rest.slice(0, rest.indexOf('\n\n')).trim();
		assert.equal(norm(docArrival).toLowerCase().replace(/[.]$/, ''), norm(objective.arrival).toLowerCase(),
			`${skillName}'s doctrine arrival text does not match its profile's arrival, after whitespace normalisation`);
	});

	test(`${skillName}: the doctrine's establishes column matches the profile's, normalized`, () => {
		const doctrineRows = parseDoctrineTable(skillSource);
		assert.equal(doctrineRows.length, objective.triples.length,
			`${skillName}: doctrine table has ${doctrineRows.length} rows, profile declares ${objective.triples.length} stages`);
		for (let at = 0; at < doctrineRows.length; at += 1) {
			const doctrine = doctrineRows[at];
			const profile = objective.triples[at];
			assert.equal(doctrine.stage, profile.stage,
				`${skillName}: doctrine row ${at} is stage "${doctrine.stage}", profile stage ${at} is "${profile.stage}" -- order mismatch`);
			assert.equal(
				normalizeDoctrine(doctrine.establishes),
				normalizeDoctrine(profile.establishes),
				`${skillName}/${profile.stage}: doctrine "Establishes" cell does not match the profile's establishes text, after normalization`,
			);
		}
	});

	test(`${skillName}: the doctrine's behindWhen column matches the profile's head, normalized`, () => {
		const doctrineRows = parseDoctrineTable(skillSource);
		assert.equal(doctrineRows.length, objective.triples.length,
			`${skillName}: doctrine table has ${doctrineRows.length} rows, profile declares ${objective.triples.length} stages`);
		for (let at = 0; at < doctrineRows.length; at += 1) {
			const doctrine = doctrineRows[at];
			const profile = objective.triples[at];
			assert.equal(
				normalizeDoctrine(head(doctrine.behindWhen)),
				normalizeDoctrine(head(profile.behindWhen)),
				`${skillName}/${profile.stage}: doctrine "Behind you when" head does not match the profile's behindWhen head, after normalization -- ` +
					'the doctrine table may omit a colon-introduced rationale clause the profile keeps, but must not diverge before the colon',
			);
		}
	});
}

test('every declared entrance names a stage its own profile actually declares', () => {
	let entranceCount = 0;
	for (const { skillName, objective } of pairs) {
		for (const arrivesAt of objective.entrances) {
			entranceCount += 1;
			assert.ok(objective.stages.includes(arrivesAt), `${skillName} declares an entrance arriving at "${arrivesAt}", which is not one of its own declared stages`);
		}
	}
	// Global vacuity guard: if no profile declared an entrance at all, the loop
	// above never ran a single assertion, and a check that never ran is not a
	// pass.
	assert.ok(entranceCount >= 1, 'no profile declares an entrance at all -- this check would otherwise be vacuous');
});
