// The last core site that declared the artifact marker as its own literal.
//
// `patch-compiler.ts` and `draft-materialization.ts` stopped doing it; this one kept
// its copy, and the comment beside it justified the copy by a Python cross-language
// guard that reads THIS FILE by regex as "the canonical source of truth". That is a
// choice of where the guard looks, not a technical constraint: the file already has
// the profile's artifact config in scope (`artifact as artifactConfig`, from
// `artifact-naming.js`, which itself imports `DOMAIN`).
//
// What the copy cost, and why this is behaviour and not tidiness: `cli.mjs` recognises
// a managed file through the PROFILE's marker while `resolveLatestManagedRevision` used
// the literal. A domain declaring its own marker therefore got an inventory holding a
// managed revision that is not the latest while nothing is the latest, reported as
// `ok` -- and neither host's decision tree has a branch for that state. Self-
// contradictory, not merely silent.
//
// A fresh Node process with a custom-marker profile, for the reason every other
// domain-profile test here spawns one: `domain-profile.ts` reads the variable once, at
// import time, and the module cache keys on it.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, writeFile, mkdir } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const piRoot = path.resolve('.');

const CUSTOM_MARKER = '<!-- test-marker:artifact:v9 -->\n';

const PROFILE_SOURCE = `export const profile = {
	deriveBase: "base.md",
	baseLabel: "base",
	baseLabelLong: "base document",
	exampleSlug: "example-slug-r01",
	names: ["TESTDOMAIN"],
	proseReferencePattern: "\\\\(Ec\\\\. ([0-9]+)\\\\)",
	vocabulary: {
		conceptualTerms: [],
		expertPattern: "x",
		displayNounPattern: "x",
		displayNounStripPattern: "x",
		subjectPattern: "x",
		subjectTerms: [],
		subjectLocusDescription: "x",
		subjectEvidenceLabel: "x",
	},
	artifact: {
		directory: "proposals",
		stem: "testdoc",
		revisionPattern: "r",
		revisionLabel: (ordinal) => \`r\${String(ordinal).padStart(2, "0")}\`,
		sidecarRoot: ".test-deliberation",
		marker: ${JSON.stringify(CUSTOM_MARKER)},
	},
	preservation: { extractAtoms: () => new Map(), violations: () => [] },
	references: { declares: () => [], cites: () => [] },
	sources: [{ path: "guidance", required: false }],
	objective: {
		purpose: "test purpose",
		stages: [{ stage: "bound", establishes: "x", behindWhen: "x" }],
		arrival: "test arrival",
		humanStops: ["a person decides"],
	},
};
`;

function harnessScript() {
	return `import path from 'node:path';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const engineDir = process.env.ENGINE_DIR;
const { DOMAIN } = await jiti.import(path.join(engineDir, 'domain-profile.ts'));
const store = await jiti.import(path.join(engineDir, 'revision-lifecycle-store.ts'));

// markerOwned:true or the marker is never compared at all -- without the option
// the file resolves by name pattern and this test would pass proving nothing.
const found = await store.resolveLatestManagedRevision(
	process.env.PROJECT_ROOT, { markerOwned: true });
process.stdout.write(JSON.stringify({
	profileMarker: DOMAIN.artifact.marker,
	latest: found?.latest ? found.latest.filename : null,
	shape: Object.keys(found ?? {}).sort(),
}));
`;
}

test('resolveLatestManagedRevision recognises a file bearing the profile marker, not a literal of its own', async () => {
	const tmp = await mkdtemp(path.join(os.tmpdir(), 'lifecycle-marker-'));
	const profilePath = path.join(tmp, 'profile.ts');
	await writeFile(profilePath, PROFILE_SOURCE, 'utf8');

	// A managed revision exactly as this domain would write one: its own marker first.
	const proposals = path.join(tmp, 'proposals');
	await mkdir(proposals, { recursive: true });
	await writeFile(path.join(proposals, 'testdoc-sample-r01.md'),
		`${CUSTOM_MARKER}# 1 Section\n\nBody.\n`, 'utf8');

	const scriptPath = path.join(tmp, 'harness.mjs');
	await writeFile(scriptPath, harnessScript(), 'utf8');

	const { stdout } = await execFileAsync(process.execPath, [scriptPath], {
		env: {
			...process.env,
			DELIBERATION_DOMAIN_PROFILE: profilePath,
			ENGINE_DIR: engineDir,
			PROJECT_ROOT: tmp,
		},
	});
	const seen = JSON.parse(stdout);

	assert.equal(seen.profileMarker, CUSTOM_MARKER,
		'the spawned process must have loaded the custom-marker profile');
	assert.equal(seen.latest, 'testdoc-sample-r01.md',
		"the store did not recognise a revision carrying this domain's own marker -- "
		+ 'it is still comparing against a literal of its own, which is what leaves an '
		+ 'inventory holding a managed revision while nothing is the latest');
});

test('no core module declares the artifact marker as its own literal any more', async () => {
	// The structural half. Three sites once carried a copy; the last one justified its
	// copy by a Python guard that reads it. With the guard repointed at the profile,
	// nothing in core needs to restate the bytes -- and a fourth copy cannot appear
	// without this going red.
	const { readdir, readFile } = await import('node:fs/promises');
	const files = (await readdir(engineDir)).filter((f) => f.endsWith('.ts') || f.endsWith('.mjs'));
	const offenders = [];
	for (const file of files) {
		const source = await readFile(path.join(engineDir, file), 'utf8');
		// A LIVE literal, not a comment recounting that one was removed: it only counts
		// if the bytes sit inside a `Buffer.from(...)` in code, with comment lines
		// discarded. Without that, a fix's historical note reads the same as the
		// defect it describes.
		const code = source.split('\n').filter((l) => !l.trimStart().startsWith('//')).join('\n');
		if (/Buffer\.from\('<!-- proposal-workspace:artifact:v1/.test(code)) offenders.push(file);
	}
	assert.deepEqual(offenders, [],
		`core modules restating the marker bytes: ${offenders.join(', ')}`);
});
