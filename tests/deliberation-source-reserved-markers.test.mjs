// X15: a declared source that is itself a managed revision carries the engine's reserved
// artifact marker, and the first revision used to paste it verbatim.
//
// The experiments domain declares `proposals/` as a source, and every published proposal
// revision opens with the reserved marker line. Since the first revision runs the same
// pre-publish validation as every successor, `CREATE_INITIAL_REVISION` was refused
// (`initial-candidate-limit`) whenever a proposal fitted in the source window, which is the
// normal flow. Before that, the same call wrote a v1 holding the pasted markers, and no
// successor could ever be accepted from it.
//
// Now the source window neutralises every reserved marker it loads (and reports how many), so a
// fresh v1 is created clean. A v1 written before the fix keeps its bytes: a successor preview
// names the copied markers and the sections that hold them, and a successor that replaces those
// sections without the marker lines is accepted. A candidate that still carries a copied marker
// is refused exactly as before. Every fixture is generic.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const engineDir = path.resolve('skills/_core/deliberation/engine');
const proposalCli = path.resolve('skills/proposal-deliberation/cli.mjs');
const experimentalCli = path.resolve('skills/experimental-deliberation/cli.mjs');
const { createJiti } = await import('jiti');
const jiti = createJiti(import.meta.url);
const workspaceModule = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));
const v2 = await jiti.import(path.join(engineDir, 'exports.ts'));
const { artifact } = await jiti.import(path.join(engineDir, 'artifact-naming.ts'));

const MARKER = artifact.marker.toString('utf8');
const NAMESPACE = 'proposal-workspace:artifact';
const DECLARATIONS = '**Dataset:** Synthetic-Blobs, fixed train/test split\n\n**Validation scheme:** paired comparison, 3 seeds, 2 repetitions per seed';
const occurrences = (text, needle) => text.split(needle).length - 1;

function cli(script, root, request, args = []) {
	return new Promise((resolve, reject) => {
		const env = { ...process.env, PROPOSAL_DELIBERATION_PROJECT_ROOT: root };
		delete env.DELIBERATION_DOMAIN_PROFILE;
		const child = spawn(process.execPath, [script, ...args], { cwd: root, env, stdio: ['pipe', 'pipe', 'pipe'] });
		let out = '';
		child.stdout.on('data', (chunk) => { out += chunk; });
		child.on('error', reject);
		child.on('close', () => {
			try { resolve(JSON.parse(out)); } catch { reject(new Error(`unparseable: ${out}`)); }
		});
		child.stdin.end(JSON.stringify(request));
	});
}

/** One `--serve` process: every request on one line, every answer on one line. */
function serve(script, root) {
	const env = { ...process.env, PROPOSAL_DELIBERATION_PROJECT_ROOT: root };
	delete env.DELIBERATION_DOMAIN_PROFILE;
	const child = spawn(process.execPath, [script, '--serve'], { cwd: root, env, stdio: ['pipe', 'pipe', 'inherit'] });
	let buffer = '';
	const waiting = [];
	child.stdout.on('data', (chunk) => {
		buffer += chunk;
		let index;
		while ((index = buffer.indexOf('\n')) !== -1) {
			const line = buffer.slice(0, index);
			buffer = buffer.slice(index + 1);
			waiting.shift()?.(JSON.parse(line));
		}
	});
	return {
		call: (request) => new Promise((resolve) => { waiting.push(resolve); child.stdin.write(`${JSON.stringify(request)}\n`); }),
		close: () => new Promise((resolve) => { child.on('close', resolve); child.stdin.end(); }),
	};
}

async function workspace(files) {
	const root = await mkdtemp(path.join(os.tmpdir(), 'deliberation-reserved-markers-'));
	for (const [relative, content] of Object.entries(files)) {
		await mkdir(path.dirname(path.join(root, relative)), { recursive: true });
		await writeFile(path.join(root, relative), content);
	}
	return root;
}

/** Inserts one section after the section `query` resolves to (or replaces that section), through preview and accept. */
async function insertAfter(script, root, sourceFilename, query) {
	return successor(script, root, sourceFilename, [{ query, decision: (entryId) => ({ kind: 'insert', anchorEntryId: entryId, position: 'after', content: '## Notes\n\nOne closing note.\n\n' }) }]);
}

/** One successor over one or more resolved loci, through preview and accept. */
async function successor(script, root, sourceFilename, loci) {
	const session = serve(script, root);
	try {
		const decisions = [];
		for (const { query, decision } of loci) {
			const resolved = await session.call({ operation: 'RESOLVE_TARGET', sourceFilename, query });
			assert.equal(resolved.status, 'resolved', JSON.stringify(resolved));
			decisions.push(decision(resolved.entryId));
		}
		const queries = loci.map((locus) => locus.query);
		const request = {
			operation: 'CREATE_SUCCESSOR', sourceFilename,
			...(queries.length === 1 ? { selectedEntryId: queries[0] } : { selectedEntryIds: queries }),
			resolvedDecisions: decisions,
			instruction: 'Revise the named sections.',
			changeSummary: { what: 'Revised the named sections.', why: 'The plan needs them revised.' },
		};
		const preview = await session.call(request);
		if (preview.status !== 'awaiting_acceptance') return { preview };
		const accepted = await session.call({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
		return { preview, accepted };
	} finally {
		await session.close();
	}
}

test('experiments domain: a published proposal inside the window no longer blocks the first revision', async () => {
	const proposal = `${MARKER}# Shared code.\n\n## One latent code explains both views.\n\nThe proposal claims one shared latent code.\n`;
	const root = await workspace({
		'guidance/data-paper/blobs/blobs.md': '# Blobs\n\nA generic synthetic dataset.\n',
		'proposals/research-concept-shared-code-r01.md': proposal,
		'experiments/.gitkeep': '',
	});
	const created = await cli(experimentalCli, root, { operation: 'CREATE_INITIAL_REVISION', instruction: `Sweep plan. It tests the shared code.\n\n${DECLARATIONS}` });
	assert.equal(created.status, 'created', JSON.stringify(created).slice(0, 1500));
	const body = await readFile(path.join(root, 'experiments', created.targetFilename), 'utf8');
	assert.equal(occurrences(body, NAMESPACE), 1, 'only the revision\'s own head marker');
	assert.ok(body.startsWith(MARKER));
	assert.match(body, /The proposal claims one shared latent code\./, 'the source content itself is still pasted');
	const source = created.sourceWindow.sources.find((entry) => entry.path.startsWith('proposals/'));
	assert.equal(source.status, 'loaded');
	assert.equal(source.reservedMarkersRemoved, 1);
	const { preview, accepted } = await insertAfter(experimentalCli, root, created.targetFilename, 'Sweep plan');
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview).slice(0, 1500));
	assert.equal(accepted.status, 'published', JSON.stringify(accepted).slice(0, 1500));
});

test('proposal domain: every reserved marker in a guide is neutralised, the rest of the guide is kept', async () => {
	const guide = [
		'# Guide', '',
		'<!-- proposal-workspace:artifact:v1 -->',
		'  <!-- proposal-workspace:revision r07 -->',
		'A guide paragraph that quotes proposal-workspace:artifact inline.',
		'', 'Closing guide line.', '',
	].join('\n');
	const root = await workspace({ 'guidance/paper-guide/notes.md': guide, 'proposals/.gitkeep': '' });
	const created = await cli(proposalCli, root, { operation: 'CREATE_INITIAL_REVISION', instruction: 'A bounded tutor for proof drafts. It names the step it doubts.' });
	assert.equal(created.status, 'created', JSON.stringify(created).slice(0, 1500));
	const body = await readFile(path.join(root, 'proposals', created.targetFilename), 'utf8');
	assert.equal(occurrences(body, NAMESPACE), 1);
	assert.equal(occurrences(body, 'proposal-workspace:revision'), 0);
	assert.match(body, /A guide paragraph that quotes .* inline\./);
	assert.match(body, /Closing guide line\./);
	assert.equal(created.sourceWindow.sources[0].reservedMarkersRemoved, 3);
});

test('a source without reserved markers reports nothing new', async () => {
	const root = await workspace({ 'guidance/paper-guide/notes.md': '# Guide\n\nPlain guide.\n', 'proposals/.gitkeep': '' });
	const body = await cli(proposalCli, root, { operation: 'CREATE_INITIAL_REVISION', instruction: 'A bounded tutor for proof drafts. It names the step it doubts.' }, ['--dry-run']);
	assert.equal(body.status, 'preview', JSON.stringify(body).slice(0, 800));
	// No `reservedMarkersRemoved`. The guide's own `# Guide` line is counted by the separate
	// heading rule (`headingsNeutralized`, tests/deliberation-pasted-source-headings.test.mjs).
	assert.deepEqual(body.sourceWindow.sources, [{ path: 'guidance/paper-guide/notes.md', bytes: 22, loadedBytes: 22, status: 'loaded', headingsNeutralized: 1 }]);
});

// --- A first revision written before the fix, copied markers and all -----------------------

const LEGACY = 'research-concept-legacy-r01.md';
const LEGACY_BODY = [
	'# Legacy plan.', '',
	'## It was created before the fix.', '',
	'Main body paragraph.', '',
	'## Reference Sources', '',
	'### proposals/research-concept-upstream-r01.md', '',
	MARKER.trimEnd(),
	'# Upstream title.', '',
	'Upstream paragraph.', '',
	'### proposals/research-concept-upstream-r02.md', '',
	MARKER.trimEnd(),
	'# Upstream title.', '',
	'Upstream second paragraph.', '',
].join('\n');

/** Publishes the legacy v1 through the creation port, which writes what it is handed, as 0.13.0 did. */
async function legacyWorkspace() {
	const root = await workspace({ 'proposals/.gitkeep': '' });
	await v2.createFilesystemInitialRevisionPublicationPort(root).publish({
		filename: LEGACY, revision: artifact.revisionLabel(1), markdown: LEGACY_BODY,
		canonicalMetadata: { schemaVersion: 1, title: 'Legacy plan', sectionHeading: 'It was created before the fix' },
	});
	const bytes = await readFile(path.join(root, 'proposals', LEGACY));
	assert.equal(occurrences(bytes.toString('utf8'), NAMESPACE), 3, 'the fixture holds two copied markers');
	return { root, bytes };
}

test('legacy v1: a successor that keeps the copied markers is refused and told why and how to repair', async () => {
	const { root, bytes } = await legacyWorkspace();
	const { preview } = await insertAfter(proposalCli, root, LEGACY, 'created before the fix');
	assert.equal(preview.status, 'blocked', JSON.stringify(preview).slice(0, 1500));
	assert.equal(preview.message, 'CANDIDATE_VALIDATION_FAILED');
	assert.equal(preview.nextAction, 'repair_candidate', JSON.stringify(preview).slice(0, 1500));
	assert.deepEqual(preview.blockers.map((b) => b.code), ['successor-copied-artifact-marker']);
	assert.match(preview.blockers[0].message, /2 copied/);
	assert.match(preview.blockers[0].message, /## Reference Sources/);
	assert.match(preview.blockers[0].message, /replace/i);
	assert.deepEqual(await readFile(path.join(root, 'proposals', LEGACY)), bytes);
});

test('legacy v1: a successor that replaces the section holding the copied markers is accepted', async () => {
	const { root, bytes } = await legacyWorkspace();
	// The pasted documents brought their own `# ` headings, so the two copies sit in two
	// sections: the refusal names both, and one successor replaces both.
	const replace = (text) => (entryId) => ({ kind: 'replace', targetEntryId: entryId, replacementText: text });
	const { preview, accepted } = await successor(proposalCli, root, LEGACY, [
		{ query: '### proposals/research-concept-upstream-r01.md', decision: replace('### proposals/research-concept-upstream-r01.md\n\n') },
		{ query: '### proposals/research-concept-upstream-r02.md', decision: replace('### proposals/research-concept-upstream-r02.md\n\n## Notes\n\nOne closing note.\n\n') },
	]);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview).slice(0, 1500));
	assert.equal(accepted.status, 'published', JSON.stringify(accepted).slice(0, 1500));
	const written = await readFile(path.join(root, 'proposals', accepted.targetFilename), 'utf8');
	assert.equal(occurrences(written, NAMESPACE), 1, 'the successor carries only its own head marker');
	assert.match(written, /## Notes/);
	assert.deepEqual(await readFile(path.join(root, 'proposals', LEGACY)), bytes, 'the legacy v1 is never rewritten');
});

test('legacy v1: a replacement that writes a marker back is still refused', () => {
	const source = `${MARKER}${LEGACY_BODY}`;
	const sha = v2.sha256(Buffer.from(source));
	const start = source.indexOf('## Reference Sources');
	const section = source.slice(start);
	const refusal = workspaceModule.successorCandidateRefusal(source, sha, [
		{ id: 'p1', kind: 'replace', oldText: section, newText: `## Reference Sources\n\n${MARKER}Kept.\n` },
	]).refusal;
	assert.equal(refusal?.code, 'successor-patch-limit', JSON.stringify(refusal));
	const kept = workspaceModule.successorCandidateRefusal(source, sha, [
		{ id: 'p1', kind: 'replace', oldText: 'Main body paragraph.', newText: 'Edited body paragraph.' },
	]).refusal;
	assert.equal(kept?.code, 'successor-copied-artifact-marker', JSON.stringify(kept));
});
