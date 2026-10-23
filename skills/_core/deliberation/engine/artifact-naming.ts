import { DOMAIN } from './domain-profile.js';

/**
 * The only speller of the managed-artifact namespace.
 *
 * Every managed-revision naming decision -- stem, revision spelling, lineage
 * segment shape, directory, sidecar root, marker -- is read off `DOMAIN.artifact`
 * (the profile the host chose) exactly once here, and every other core file
 * imports the builders and matchers below instead of writing its own regex or
 * template literal. `DOMAIN.artifact.stem`/`sidecarRoot` themselves are never
 * re-spelled: `the core-scan lock (`no file in the shared core names any domain`)`'s
 * core-only scan reads this file too and holds it to the same rule.
 *
 * Five distinct matcher semantics survive here under five distinct names
 * (measured, not assumed -- see design.md's corrections table): collapsing them
 * into one canonical regex would silently tighten `loadDocumentState`'s LAX
 * gate into today's STRICT one. Each stays a separate, independently testable
 * export instead.
 */

/** One lineage segment: lowercase alnum tokens joined by single hyphens. A shared core convention, not a domain value -- every managed-revision family composes it the same way regardless of what a domain calls its stem. */
export const SEGMENT = '[a-z0-9]+(?:-[a-z0-9]+)*';

/** Produced only by `initialRevisionFilename()`/`managedRevisionFilename()`. A TypeScript literal type cannot depend on a runtime profile value, so this brand is the compile-time constraint that stands in its place. */
export type ManagedRevisionName = string & { readonly __managedRevision: unique symbol };
/** Produced only by `initialRevisionFilename()`. Every fixed-first-revision literal-type site in the old code becomes this brand. */
export type ManagedInitialName = string & { readonly __managedInitial: unique symbol };

function escapeRegExp(value: string): string {
	return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const STEM = DOMAIN.artifact.stem;
const ESCAPED_STEM = escapeRegExp(STEM);
/** The profile's own revision-spelling prefix (e.g. `"r"`), escaped -- never invented here. */
const REVISION_PREFIX = escapeRegExp(DOMAIN.artifact.revisionPattern);

/** The escaped stem, exported so a call site that still needs to compose its own one-off pattern never re-spells the literal itself. */
export const escapedStem = ESCAPED_STEM;
/** The escaped revision-spelling prefix, same reason. */
export const escapedRevisionPrefix = REVISION_PREFIX;

// STRICT: anchored, lowercase-alnum lineage (or none), minimum two digits. Byte-identical to the
// five previously hardcoded stem-(lineage-)?prefix\d{2,}.md sites.
const STRICT_SOURCE = `^${ESCAPED_STEM}-(?:${SEGMENT}-)?${REVISION_PREFIX}\\d{2,}\\.md$`;
// LAX PARSE: safe legacy ASCII lineage, ONE-digit revision -- still looser than STRICT.
const LAX_SOURCE = `^${ESCAPED_STEM}-(?:([A-Za-z0-9_.-]+)-)?${REVISION_PREFIX}(\\d+)\\.md$`;
// INCREMENT: captures the "stem[-lineage]-prefix" head and the ordinal digits separately, so a
// successor slug can be built by bumping the ordinal and re-padding it to the same width.
const INCREMENT_SOURCE = `^(${ESCAPED_STEM}-(?:${SEGMENT}-)?${REVISION_PREFIX})(\\d+)\\.md$`;
// LOOSE SCAN: unanchored and case-insensitive -- finds a managed filename anywhere inside free text.
const LOOSE_SOURCE = `\\b${ESCAPED_STEM}-(?:${SEGMENT}-)?${REVISION_PREFIX}\\d{2,}\\.md\\b`;
// INITIAL: a lineage segment is MANDATORY (unlike STRICT), and the revision is pinned to the
// profile's own first-ordinal label (`revisionLabel(1)`, e.g. `"r01"`) -- never a second hardcoded "01".
const INITIAL_SOURCE = `^${ESCAPED_STEM}-${SEGMENT}-${escapeRegExp(DOMAIN.artifact.revisionLabel(1))}\\.md$`;

// A bare revision label on its own (not a whole filename), STRICT's own digit-count rule (`\d{2,}`).
const STRICT_REVISION_LABEL_SOURCE = `^${REVISION_PREFIX}\\d{2,}$`;
const STRICT_REVISION_LABEL_RE = new RegExp(STRICT_REVISION_LABEL_SOURCE);

const STRICT_RE = new RegExp(STRICT_SOURCE);
const LAX_RE = new RegExp(LAX_SOURCE);
const INCREMENT_RE = new RegExp(INCREMENT_SOURCE);
const LOOSE_RE = new RegExp(LOOSE_SOURCE, 'i');
const INITIAL_RE = new RegExp(INITIAL_SOURCE);

/** The frozen, profile-derived values every naming site reads instead of spelling its own. */
export const artifact = {
	directory: DOMAIN.artifact.directory,
	sidecarRoot: DOMAIN.artifact.sidecarRoot,
	stem: DOMAIN.artifact.stem,
	marker: Buffer.from(DOMAIN.artifact.marker, 'utf8'),
	revisionLabel: DOMAIN.artifact.revisionLabel,
};

/** STRICT: anchored, lowercase-alnum lineage, minimum two ordinal digits. */
export function strictManagedRevision(name: string): name is ManagedRevisionName {
	return STRICT_RE.test(name);
}

/** STRICT's own revision-label rule (`r\d{2,}`), tested against a bare label rather than a whole filename. */
export function strictRevisionLabel(value: string): boolean {
	return STRICT_REVISION_LABEL_RE.test(value);
}

/** LAX PARSE: the sole gate on `loadDocumentState`. Accepts safe legacy lineage and a single ordinal digit. */
export function parseManagedRevision(name: string): { lineage: 'ROOT' | string; revision: string; ordinal: number; digits: string } | undefined {
	if (name.includes('..') || /[\x00-\x1f\x7f-\x9f]/.test(name)) return undefined;
	const match = LAX_RE.exec(name);
	if (!match) return undefined;
	const digits = match[2]!;
	const ordinal = Number(digits);
	if (!Number.isSafeInteger(ordinal)) return undefined;
	return { lineage: match[1] ?? 'ROOT', revision: `${DOMAIN.artifact.revisionPattern}${digits}`, ordinal, digits };
}

/**
 * INCREMENT: splits a managed filename into its stable head and its ordinal digits, for bumping
 * the successor slug. `digits` is the RAW captured digit string (preserving any leading zero
 * width, e.g. `"01"`), never just `String(ordinal)` -- a caller re-padding the bumped ordinal
 * must pad to the ORIGINAL width, not to `String(1).length` (which has already lost the zero).
 */
export function parseRevisionIncrement(name: string): { prefix: string; ordinal: number; digits: string } | undefined {
	const match = INCREMENT_RE.exec(name);
	if (!match) return undefined;
	const digits = match[2]!;
	const ordinal = Number(digits);
	if (!Number.isSafeInteger(ordinal)) return undefined;
	return { prefix: match[1]!, ordinal, digits };
}

/** LOOSE SCAN: unanchored, case-insensitive. Finds a managed filename anywhere inside free text. */
export function scanManagedRevision(text: string): string | undefined {
	return LOOSE_RE.exec(text)?.[0];
}

// COMPANION SCAN: a managed revision's own name followed by any suffix other than `.md` -- an
// artifact named after ONE revision (a picture or an overlay rendered for it), found anywhere in
// free text. Captures the revision head and the suffix separately.
const COMPANION_SOURCE = `\\b(${ESCAPED_STEM}-(?:${SEGMENT}-)?${REVISION_PREFIX}\\d{2,})((?:\\.[A-Za-z0-9_-]+)+)`;

/** A reference to an artifact named after one managed revision, and the revision it names. */
export type CompanionReference = { reference: string; revision: string };

/**
 * Every distinct companion-artifact reference in `text`, in document order. A reference to a
 * managed document itself (`.md`) is a citation, not a companion artifact, and is skipped.
 */
export function scanCompanionReferences(text: string): CompanionReference[] {
	const seen = new Set<string>();
	const found: CompanionReference[] = [];
	for (const match of text.matchAll(new RegExp(COMPANION_SOURCE, 'g'))) {
		if (match[2].toLowerCase() === '.md' || seen.has(match[0])) continue;
		seen.add(match[0]);
		found.push({ reference: match[0], revision: `${match[1]}.md` });
	}
	return found;
}

/** A companion reference in a successor that names another revision, and whether the successor inherited it from its source. */
export type StaleCompanionReference = CompanionReference & { inherited: boolean };

/**
 * The companion-artifact references in a successor's bytes that name a revision OTHER than the
 * successor itself. A successor inherits every byte outside its locus, so a link to the
 * source revision's picture keeps pointing there; nothing in the engine renders that picture, so
 * this only reports. `inherited` is true when the source carried the same reference.
 */
export function staleCompanionReferences(successor: string, source: string, successorFilename: string): StaleCompanionReference[] {
	const inSource = new Set(scanCompanionReferences(source).map(item => item.reference));
	return scanCompanionReferences(successor)
		.filter(item => item.revision !== successorFilename)
		.map(item => ({ ...item, inherited: inSource.has(item.reference) }));
}

/** INITIAL: `stem-SEGMENT-<first-revision-label>.md` only -- a mandatory lineage, no bare-ROOT form. */
export function isInitialRevision(name: string): boolean {
	return INITIAL_RE.test(name);
}

function renderManagedFilename(lineage: 'ROOT' | string, label: string): string {
	return lineage === 'ROOT' ? `${STEM}-${label}.md` : `${STEM}-${lineage}-${label}.md`;
}

/** Builds a managed revision filename for an arbitrary ordinal. Never spelled by a caller directly. */
export function managedRevisionFilename(lineage: 'ROOT' | string, ordinal: number): ManagedRevisionName {
	return renderManagedFilename(lineage, artifact.revisionLabel(ordinal)) as ManagedRevisionName;
}

/** Builds the one well-formed initial-revision filename for a lineage (`stem-SEGMENT-<first-label>.md`). */
export function initialRevisionFilename(lineage: string): ManagedInitialName {
	return renderManagedFilename(lineage, artifact.revisionLabel(1)) as ManagedInitialName;
}

/** `${directory}/${filename}` -- the public path of a managed revision, never a bare literal. */
export function documentPath(filename: string): string {
	return `${artifact.directory}/${filename}`;
}

/** `${sidecarRoot}/state/${filename}.json` -- the derived-state sidecar path. */
export function statePath(filename: string): string {
	return `${artifact.sidecarRoot}/state/${filename}.json`;
}

/** `${sidecarRoot}/receipts/${filename}.json` -- the publication receipt sidecar path. */
export function receiptPath(filename: string): string {
	return `${artifact.sidecarRoot}/receipts/${filename}.json`;
}

/** `${sidecarRoot}/withdrawn/${operationId}/audit-marker.json` -- the withdrawal audit-marker path. */
export function withdrawnMarkerPath(operationId: string): string {
	return `${artifact.sidecarRoot}/withdrawn/${operationId}/audit-marker.json`;
}

/** The three public artifacts a managed revision always carries, in document/state/receipt order. */
export function publicRelativePaths(filename: string): readonly [string, string, string] {
	return [documentPath(filename), statePath(filename), receiptPath(filename)];
}

/**
 * The JSON-Schema `pattern` source for a managed revision filename, replacing the three
 * previously hand-spelled `pattern` strings in `proposal-workspace.ts`. `requireLineage`
 * reproduces the one site that never accepted a bare-ROOT filename; `directoryPrefix`
 * reproduces the one site that also accepts the filename prefixed once by `directory/`.
 */
export function managedRevisionSchemaPattern(opts: { directoryPrefix?: boolean; requireLineage?: boolean } = {}): string {
	const lineageGroup = opts.requireLineage ? `${SEGMENT}-` : `(?:${SEGMENT}-)?`;
	const body = `${ESCAPED_STEM}-${lineageGroup}${REVISION_PREFIX}\\d{2,}\\.md`;
	return opts.directoryPrefix ? `^(?:${artifact.directory}/)?${body}$` : `^${body}$`;
}
