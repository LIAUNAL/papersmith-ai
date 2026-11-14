// A first revision never carries a source document's own headings as headings, and a
// lineage that already does can be repaired through a normal successor.
//
// Reported against 0.74.0: `CREATE_INITIAL_REVISION` pasted every source document read
// through the source window verbatim under the domain's reference heading, its own `#` title
// included. A source that is an earlier proposal revision whose title equals the new
// document's title left several byte-identical level-1 headings in v1, and every successor
// copied them forward. Two things then broke:
//
//   - `RESOLVE_TARGET` on that title tied three ways and blocked, so no successor could name
//     the pasted copy it meant to remove;
//   - the last pasted `#` section ran to the end of the file, over `## Changes`, which every
//     successor of this domain replaces, so even a resolved target overlapped it.
//
// Both halves are pinned here through the public CLI, under the profile each case needs (the
// npm script fixes `DELIBERATION_DOMAIN_PROFILE` to the mathematical profile, so every child
// sets it explicitly).
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, readdir, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const EXPERIMENTAL_CLI = path.resolve('skills/experimental-deliberation/cli.mjs');
const EXPERIMENTAL_PROFILE = path.resolve('skills/experimental-deliberation/profile.ts');
const PROPOSAL_CLI = path.resolve('skills/proposal-deliberation/cli.mjs');
const PROPOSAL_PROFILE = path.resolve('skills/proposal-deliberation/profile.ts');
const MARKER = '<!-- proposal-workspace:artifact:v1 -->\n';

const TITLE = 'Hybrid Network for EEG Classification';
const IDEA = `${TITLE}. A plan that trains on one acquisition site and evaluates on the held-out site.`;

/** Every ATX heading line a Markdown reader (or this engine) would see, as `{ level, title }`. */
function atxHeadings(markdown) {
	return markdown.split('\n').flatMap((line) => {
		const match = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$/u.exec(line);
		return match ? [{ level: match[1].length, title: (match[2] ?? '').trim() }] : [];
	});
}

/** Runs one `--serve` session under `profile`, one NDJSON request per line, and returns every response in order. */
function serve(cli, profile, root, requests) {
	return new Promise((resolve, reject) => {
		const env = { ...process.env, PROPOSAL_DELIBERATION_PROJECT_ROOT: root, DELIBERATION_DOMAIN_PROFILE: profile };
		const child = spawn(process.execPath, [cli, '--serve'], { cwd: root, env, stdio: ['pipe', 'pipe', 'pipe'] });
		let out = '';
		let err = '';
		const responses = [];
		let pending = [...requests];
		child.stdout.on('data', (chunk) => {
			out += chunk;
			let newline;
			while ((newline = out.indexOf('\n')) >= 0) {
				const line = out.slice(0, newline);
				out = out.slice(newline + 1);
				if (!line.trim()) continue;
				const response = JSON.parse(line);
				responses.push(response);
				const next = pending.shift();
				if (next === undefined) child.stdin.end();
				else child.stdin.write(`${JSON.stringify(typeof next === 'function' ? next(responses) : next)}\n`);
			}
		});
		child.stderr.on('data', (chunk) => { err += chunk; });
		child.on('error', reject);
		child.on('close', (code) => (code === 0 ? resolve(responses) : reject(new Error(`exit ${code}: ${err}`))));
		const first = pending.shift();
		child.stdin.write(`${JSON.stringify(first)}\n`);
	});
}

async function freshRoot(prefix) {
	return mkdtemp(path.join(os.tmpdir(), prefix));
}

// ---------------------------------------------------------------------------
// Prevention: the v1 render
// ---------------------------------------------------------------------------

/** The report's minimal reproduction: a proposal revision whose title equals the experiments idea title. */
async function seedExperimentalSources(root) {
	await mkdir(path.join(root, 'experiments'), { recursive: true });
	await mkdir(path.join(root, 'guidance/data-paper/site-eeg'), { recursive: true });
	await writeFile(path.join(root, 'guidance/data-paper/site-eeg/site-eeg.md'), [
		'# Site EEG Dataset Specification',
		'',
		'## 1. Dataset Overview',
		'',
		'The dataset splits are fixed by the data paper and are never resampled per run.',
		'',
		'Acquisition Notes',
		'=================',
		'',
		'```python',
		'# a comment, not a heading',
		'```',
		'',
	].join('\n'));
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await writeFile(path.join(root, 'proposals/research-concept-hybrid-network-r01.md'), [
		`# ${TITLE}`,
		'',
		'## Problem Formulation',
		'',
		'The proposal claims one shared latent code carries across acquisition sites.',
		'',
		'**Dataset:** Site EEG, source/target split as distributed',
		'',
		'**Validation scheme:** paired t-test, 5 seeds, 10 repetitions',
		'',
		'## Changes',
		'',
		'A source section that happens to share the change header title.',
		'',
	].join('\n'));
}

test('v1 never carries a source document\'s own headings as headings, so it has exactly one level-1 heading (experimental domain)', async () => {
	const root = await freshRoot('pasted-source-headings-render-');
	await seedExperimentalSources(root);
	const [created, resolved] = await serve(EXPERIMENTAL_CLI, EXPERIMENTAL_PROFILE, root, [
		{ operation: 'CREATE_INITIAL_REVISION', instruction: IDEA },
		(responses) => ({ operation: 'RESOLVE_TARGET', sourceFilename: responses[0].targetFilename, query: TITLE }),
	]);
	assert.equal(created.status, 'created', JSON.stringify(created));
	const written = await readFile(path.join(root, 'experiments', created.targetFilename), 'utf8');
	assert.ok(written.startsWith(MARKER), 'the managed marker heads the file');

	// Every heading in v1 is one the engine wrote itself, in this order: nothing pasted is a heading.
	assert.deepEqual(atxHeadings(written), [
		{ level: 1, title: TITLE },
		{ level: 2, title: 'A plan that trains on one acquisition site and evaluates on the held-out site' },
		{ level: 2, title: 'Reference Sources' },
		{ level: 3, title: 'guidance/data-paper/site-eeg/site-eeg.md' },
		{ level: 3, title: 'proposals/research-concept-hybrid-network-r01.md' },
		{ level: 2, title: 'Changes' },
	]);
	// A setext underline would make the line above it a heading for any Markdown reader.
	assert.doesNotMatch(written, /^ {0,3}(?:=+|-+)[ \t]*$/mu, 'no setext underline survives');

	// The pasted text itself survives, its heading markers escaped rather than dropped.
	assert.ok(written.includes(`\\# ${TITLE}\n\n\\## Problem Formulation\n\nThe proposal claims one shared latent code`), written);
	assert.ok(written.includes('Acquisition Notes\n\\=================\n'), written);
	assert.ok(written.includes('```python\n\\# a comment, not a heading\n```'), written);
	assert.ok(written.includes('\\## Changes\n\nA source section that happens to share the change header title.'), written);

	// The source window reports what the render did to each source.
	const bySource = Object.fromEntries(created.sourceWindow.sources.map((source) => [source.path, source.headingsNeutralized ?? 0]));
	assert.deepEqual(bySource, {
		'guidance/data-paper/site-eeg/site-eeg.md': 4,
		'proposals/research-concept-hybrid-network-r01.md': 3,
	});

	// The title now names one heading, so the resolver no longer ties on it.
	assert.equal(resolved.blocked, false, resolved.question);
	assert.ok(resolved.text.startsWith(`# ${TITLE}\n`), resolved.text);
});

test('the shared renderer applies the same rule to every domain (mathematical domain, paper guide)', async () => {
	const root = await freshRoot('pasted-source-headings-math-');
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await mkdir(path.join(root, 'guidance/paper-guide/guide'), { recursive: true });
	await writeFile(path.join(root, 'guidance/paper-guide/guide/guide.md'), '# A Bounded Tutor\n\n## Style\n\nWrite one claim per sentence.\n');
	const [created] = await serve(PROPOSAL_CLI, PROPOSAL_PROFILE, root, [
		{ operation: 'CREATE_INITIAL_REVISION', instruction: 'A Bounded Tutor. It names the step it doubts.' },
	]);
	assert.equal(created.status, 'created', JSON.stringify(created));
	const written = await readFile(path.join(root, 'proposals', created.targetFilename), 'utf8');
	assert.deepEqual(atxHeadings(written), [
		{ level: 1, title: 'A Bounded Tutor' },
		{ level: 2, title: 'It names the step it doubts' },
		{ level: 2, title: 'Paper Guide Reference' },
		{ level: 3, title: 'guidance/paper-guide/guide/guide.md' },
	]);
	assert.ok(written.endsWith('### guidance/paper-guide/guide/guide.md\n\n\\# A Bounded Tutor\n\n\\## Style\n\nWrite one claim per sentence.\n'), written);
	assert.equal(created.sourceWindow.sources[0].headingsNeutralized, 2);
});

test('a source without headings renders byte-identically to before', async () => {
	const root = await freshRoot('pasted-source-headings-plain-');
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await mkdir(path.join(root, 'guidance/paper-guide/guide'), { recursive: true });
	await writeFile(path.join(root, 'guidance/paper-guide/guide/guide.md'), 'Write one claim per sentence.\n\nA #hashtag is not a heading.\n');
	const [created] = await serve(PROPOSAL_CLI, PROPOSAL_PROFILE, root, [
		{ operation: 'CREATE_INITIAL_REVISION', instruction: 'A Bounded Tutor. It names the step it doubts.' },
	]);
	assert.equal(created.status, 'created', JSON.stringify(created));
	const written = await readFile(path.join(root, 'proposals', created.targetFilename), 'utf8');
	assert.equal(written, `${MARKER}# A Bounded Tutor

## It names the step it doubts

A Bounded Tutor. It names the step it doubts.

## Paper Guide Reference

### guidance/paper-guide/guide/guide.md

Write one claim per sentence.

A #hashtag is not a heading.
`);
	assert.equal(created.sourceWindow.sources[0].headingsNeutralized, undefined, 'nothing neutralized, nothing reported');
});

// ---------------------------------------------------------------------------
// Repair: an already-affected lineage
// ---------------------------------------------------------------------------

const AFFECTED_FILENAME = 'experiments-hybrid-network-for-eeg-classification-v01.md';
const PASTED_TWO = `# ${TITLE}\n\n## Loss Function\n\nPasted body two.\n\n`;
const AFFECTED = `# ${TITLE}

## Plan Overview

**Dataset:** Site EEG, source/target split as distributed

**Validation scheme:** paired t-test, 5 seeds, 10 repetitions

The plan trains on one split and evaluates on the held-out split.

## Reference Sources

### proposals/research-concept-a-r01.md

# ${TITLE}

## Problem Formulation

Pasted body one.

### proposals/research-concept-a-r02.md

${PASTED_TWO}## Changes

**What:** Initial revision.

**Why:** First published version.

`;

/** The shape an 0.74.0 render left behind, seeded directly so the repair is tested against it. */
async function seedAffected() {
	const root = await freshRoot('pasted-source-headings-repair-');
	await mkdir(path.join(root, 'experiments'), { recursive: true });
	await writeFile(path.join(root, 'experiments', AFFECTED_FILENAME), `${MARKER}${AFFECTED}`);
	return root;
}

const sha16 = (text) => createHash('sha256').update(text).digest('hex').slice(0, 16);

test('a repeated title still blocks, and the refusal names the #<n> form for each occurrence', async () => {
	const root = await seedAffected();
	const [bare] = await serve(EXPERIMENTAL_CLI, EXPERIMENTAL_PROFILE, root, [
		{ operation: 'RESOLVE_TARGET', sourceFilename: AFFECTED_FILENAME, query: TITLE },
	]);
	assert.equal(bare.blocked, true);
	assert.equal(bare.entryId, null);
	assert.equal(bare.candidates.length, 3);
	for (const ordinal of [1, 2, 3]) assert.ok(bare.question.includes(`${TITLE}#${ordinal}`), bare.question);
});

test('<title>#<n> names the n-th heading with that exact title, and its span stops before ## Changes', async () => {
	const root = await seedAffected();
	const [third, second, past] = await serve(EXPERIMENTAL_CLI, EXPERIMENTAL_PROFILE, root, [
		{ operation: 'RESOLVE_TARGET', sourceFilename: AFFECTED_FILENAME, query: `${TITLE}#3` },
		{ operation: 'RESOLVE_TARGET', sourceFilename: AFFECTED_FILENAME, query: `# ${TITLE}#2` },
		{ operation: 'RESOLVE_TARGET', sourceFilename: AFFECTED_FILENAME, query: `${TITLE}#4` },
	]);
	const bytes = Buffer.from(`${MARKER}${AFFECTED}`);
	const thirdStart = bytes.indexOf(Buffer.from(PASTED_TWO));
	assert.equal(third.blocked, false, third.question);
	assert.equal(third.text, PASTED_TWO, 'the last pasted section ends where ## Changes begins');
	assert.equal(third.entryId, `composite:${thirdStart}:${sha16(PASTED_TWO)}`);

	assert.equal(second.blocked, false, second.question);
	assert.equal(second.text, `# ${TITLE}\n\n## Problem Formulation\n\nPasted body one.\n\n### proposals/research-concept-a-r02.md\n\n`);

	assert.equal(past.blocked, true, 'an ordinal past the last occurrence names nothing');
	assert.equal(past.entryId, null);
	assert.match(past.question, /^No target found/u);
});

test('an unrepeated heading resolves exactly as before', async () => {
	const root = await seedAffected();
	const [plain] = await serve(EXPERIMENTAL_CLI, EXPERIMENTAL_PROFILE, root, [
		{ operation: 'RESOLVE_TARGET', sourceFilename: AFFECTED_FILENAME, query: 'Loss Function' },
	]);
	assert.equal(plain.blocked, false, plain.question);
	assert.equal(plain.text, '## Loss Function\n\nPasted body two.\n\n');
});

test('an affected lineage is repaired through a normal successor that names the pasted copy by #<n>', async () => {
	const root = await seedAffected();
	const repaired = `\\# ${TITLE}\n\n\\## Loss Function\n\nPasted body two.\n\n`;
	const request = (entryId) => ({
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: AFFECTED_FILENAME,
		instruction: 'Escape the heading markers of the pasted proposal revision.',
		selectedEntryId: `${TITLE}#3`,
		changeSummary: { what: 'Escaped the pasted source headings.', why: 'A pasted title duplicated the document title.' },
		resolvedDecisions: [{ kind: 'replace', targetEntryId: entryId, replacementText: repaired }],
	});
	const responses = await serve(EXPERIMENTAL_CLI, EXPERIMENTAL_PROFILE, root, [
		{ operation: 'RESOLVE_TARGET', sourceFilename: AFFECTED_FILENAME, query: `${TITLE}#3` },
		(previous) => request(previous[0].entryId),
		(previous) => ({ ...request(previous[0].entryId), acceptSuccessor: true, successorAcceptanceToken: previous[1].acceptanceToken }),
	]);
	const [, preview, published] = responses;
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.equal(published.status, 'published', JSON.stringify(published));
	const files = (await readdir(path.join(root, 'experiments'))).sort();
	assert.deepEqual(files, [AFFECTED_FILENAME, 'experiments-hybrid-network-for-eeg-classification-v02.md']);
	const successor = await readFile(path.join(root, 'experiments', files[1]), 'utf8');
	assert.equal(atxHeadings(successor).filter((heading) => heading.level === 1).length, 2, 'one pasted title gone; the other is the next successor\'s');
	assert.ok(successor.includes(`### proposals/research-concept-a-r02.md\n\n${repaired}## Changes\n\n**What:** Escaped the pasted source headings.`), successor);
});
