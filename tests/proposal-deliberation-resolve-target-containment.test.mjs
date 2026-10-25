import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';
import { createJiti } from 'jiti';

const engine = path.resolve('skills/_core/deliberation/engine');
const profile = path.resolve('skills/proposal-deliberation/profile.ts');
process.env.DELIBERATION_DOMAIN_PROFILE = profile;
const jiti = createJiti(import.meta.url);
const { parseManagedRevision } = await jiti.import(path.join(engine, 'artifact-naming.ts'));
const store = await jiti.import(path.join(engine, 'derived-state-store.ts'));
const { rebuildDerivedState } = await jiti.import(path.join(engine, 'derived-state-builder.ts'));
const exec = promisify(execFile);
const filename = 'research-concept-Any_Weird.Chars-r3.md';
const source = Buffer.from('# Overview\n\n## Unique locus\n\nInert sandbox content.\n');
const malformed = [
	'research-concept-a..b-r1.md',
	'research-concept-../outside-r1.md',
	'research-concept-a/b-r1.md',
	'research-concept-a\\b-r1.md',
	'/research-concept-a-r1.md',
	'C:\\research-concept-a-r1.md',
	'\\\\server\\research-concept-a-r1.md',
	'research-concept-C:drive-r1.md',
	'research-concept-a\0b-r1.md',
	'research-concept-a\tb-r1.md',
	'research-concept-a\rb-r1.md',
	'research-concept-a\nb-r1.md',
	'research-concept-a\x7fb-r1.md',
	'research-concept-a\x85b-r1.md',
	'research-concept-caf\u00e9-r1.md',
	'research-concept-a-r1.md\n',
	'research-concept-a-r1.md.json',
	'research-concept-a-r1.md/extra',
	'research-concept-a-r1.MD',
	'research-concept-a-r.md',
	'research-concept-a-r1x.md',
	'research-concept-a-r9007199254740992.md',
];

async function sandbox(t) {
	const base = await mkdtemp(path.join(tmpdir(), 'pp-target-containment-'));
	t.after(() => rm(base, { recursive: true, force: true }));
	const root = path.join(base, 'nested', 'project');
	const outside = path.join(base, 'nested', 'project-sibling');
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await mkdir(outside);
	await writeFile(path.join(outside, 'sentinel'), 'unchanged');
	return { base, root, outside };
}

async function resolve(root, request) {
	const { stdout } = await exec(process.execPath, [path.join(engine, 'cli.mjs'), JSON.stringify({ operation: 'RESOLVE_TARGET', ...request })], {
		cwd: root,
		env: { ...process.env, DELIBERATION_DOMAIN_PROFILE: profile, PROPOSAL_DELIBERATION_PROJECT_ROOT: root },
		timeout: 30_000,
	});
	return JSON.parse(stdout);
}

async function assertOutsideUntouched(outside) {
	assert.equal(await readFile(path.join(outside, 'sentinel'), 'utf8'), 'unchanged');
	assert.deepEqual(await readdir(outside), ['sentinel']);
}

for (const name of malformed) {
	test(`parser rejects unsafe artifact ${JSON.stringify(name)}`, () => {
		// Given an untrusted artifact identifier; when parsed; then no identity escapes.
		assert.equal(parseManagedRevision(name), undefined);
	});
}

for (const [name, identity] of [
	['research-concept-r1.md', { lineage: 'ROOT', revision: 'r1', ordinal: 1, digits: '1' }],
	[filename, { lineage: 'Any_Weird.Chars', revision: 'r3', ordinal: 3, digits: '3' }],
	['research-concept-a_b.C-9-r001.md', { lineage: 'a_b.C-9', revision: 'r001', ordinal: 1, digits: '001' }],
]) {
	test(`parser preserves safe identity ${name}`, () => {
		// Given a legacy safe identifier; when parsed; then all captures retain their spelling.
		assert.deepEqual(parseManagedRevision(name), identity);
	});
}

const writers = {
	saveDerivedState: async (root, name) => store.saveDerivedState(root, await rebuildDerivedState(name, 'r3', 'Any_Weird.Chars', source)),
	markDerivedState: (root, name) => store.markDerivedState(root, name, 'FAILED', 'inert regression'),
	saveRevisionReceipt: (root, name) => store.saveRevisionReceipt(root, name, { inert: true }),
};

for (const [writer, write] of Object.entries(writers)) {
	test(`${writer} rejects direct namespace and project escapes before creating directories`, async (t) => {
		// Given no sidecars, and paths that escape the namespace or project.
		const { root, outside } = await sandbox(t);
		for (const name of ['../receipts/foreign.md', '../../../project-sibling/foreign.md', 'research-concept-a\\b-r3.md']) {
			// When a direct store caller supplies the name; then reject before any mkdir/write.
			await assert.rejects(() => write(root, name));
		}
		assert.deepEqual((await readdir(root)).sort(), ['proposals']);
		await assertOutsideUntouched(outside);
	});

	for (const ancestor of ['sidecar', 'namespace', 'nested']) {
		test(`${writer} rejects an existing ${ancestor} symlink escaping its namespace`, async (t) => {
			// Given an existing symlink, including a prefix-sibling outside the project.
			const { root, outside } = await sandbox(t);
			const namespace = writer === 'saveRevisionReceipt' ? 'receipts' : 'state';
			const sidecar = path.join(root, '.proposal-deliberation');
			let name = filename;
			let link = sidecar;
			if (ancestor !== 'sidecar') {
				await mkdir(sidecar);
				link = path.join(sidecar, namespace);
			}
			if (ancestor === 'nested') {
				await mkdir(link);
				link = path.join(link, 'research-concept-link');
				name = 'research-concept-link/new/deeper-r3.md';
			}
			await symlink(outside, link, 'dir');
			// When the writer reaches its atomic boundary; then no outside artifact is created.
			await assert.rejects(() => write(root, name));
			await assertOutsideUntouched(outside);
		});

	}

	test(`${writer} accepts a safe name in a fresh project`, async (t) => {
		// Given a fresh project; when storing a safe legacy name; then write the intended sidecar.
		const { root, outside } = await sandbox(t);
		await write(root, filename);
		const target = writer === 'saveRevisionReceipt' ? store.receiptPath(root, filename) : store.derivedStatePath(root, filename);
		assert.ok(JSON.parse(await readFile(target, 'utf8')));
		await assertOutsideUntouched(outside);
	});
}

for (const batch of [false, true]) {
	test(`RESOLVE_TARGET blocks ${batch ? 'batch overrides' : 'single requests'} with traversal without outside writes`, async (t) => {
		// Given controlled source and sidecar destinations, all inside a disposable sandbox.
		const { root, outside } = await sandbox(t);
		const traversal = 'research-concept-pad/../../../project-sibling/escape-r3.md';
		await mkdir(path.join(root, 'proposals', 'research-concept-pad'));
		await writeFile(path.join(outside, 'escape-r3.md'), source);
		const before = await readdir(outside);
		// When the real CLI sees malformed single names or per-item batch overrides.
		const result = await resolve(root, batch ? {
			sourceFilename: filename,
			queries: [traversal, ...malformed].map(sourceFilename => ({ sourceFilename, query: '## Unique locus' })),
		} : { sourceFilename: traversal, query: '## Unique locus' });
		// Then all requests block and neither sources nor outside sidecars change.
		for (const item of batch ? result.results : [result]) {
			assert.equal(item.blocked, true);
			assert.equal(item.entryId, null);
			assert.equal(item.question, 'INVALID_MANAGED_REVISION');
		}
		assert.deepEqual(await readdir(outside), before);
		assert.deepEqual(await readFile(path.join(outside, 'escape-r3.md')), source);
		assert.equal(await readFile(path.join(outside, 'sentinel'), 'utf8'), 'unchanged');
		assert.deepEqual((await readdir(root)).sort(), ['proposals']);
	});
}

test('RESOLVE_TARGET blocks a safe name when a sidecar ancestor redirects outside', async (t) => {
	// Given a valid source but an escaping sidecar symlink.
	const { root, outside } = await sandbox(t);
	await writeFile(path.join(root, 'proposals', filename), source);
	await symlink(outside, path.join(root, '.proposal-deliberation'), 'dir');
	// When resolving with the actual CLI; then cache persistence must block without outside writes.
	const result = await resolve(root, { sourceFilename: filename, query: '## Unique locus' });
	assert.equal(result.blocked, true);
	assert.equal(result.entryId, null);
	await assertOutsideUntouched(outside);
});

test('RESOLVE_TARGET resolves safe ROOT and legacy names and writes only their intended state', async (t) => {
	// Given valid legacy and ROOT sources in a nested project.
	const { root, outside } = await sandbox(t);
	const names = ['research-concept-r1.md', filename];
	for (const name of names) await writeFile(path.join(root, 'proposals', name), source);
	// When resolving both via real batch overrides; then identity and cache destination remain intact.
	const result = await resolve(root, { queries: names.map(sourceFilename => ({ sourceFilename, query: '## Unique locus' })) });
	assert.equal(result.results.length, 2);
	for (const [index, item] of result.results.entries()) {
		assert.equal(item.blocked, false);
		assert.ok(item.entryId);
		const stored = JSON.parse(await readFile(store.derivedStatePath(root, names[index]), 'utf8'));
		assert.equal(stored.manifest.documentFilename, names[index]);
	}
	await assertOutsideUntouched(outside);
});
