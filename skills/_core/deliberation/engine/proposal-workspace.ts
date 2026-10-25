import { StringEnum } from "./_pi-compat/pi-ai.js";
import {
	type ExtensionAPI,
	type ExtensionContext,
	withFileMutationQueue,
} from "./_pi-compat/pi-coding-agent.js";
import { createHash, randomBytes, randomUUID } from "node:crypto";
import { constants } from "node:fs";
import {
	type FileHandle,
	link,
	lstat,
	open,
	readdir,
	readFile,
	realpath,
	stat,
	unlink,
} from "node:fs/promises";
import { basename, dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { type Static, Type } from "typebox";
import { DOMAIN } from "./domain-profile.js";
import {
	artifact,
	escapedRevisionPrefix,
	escapedStem,
	managedRevisionSchemaPattern,
	parseRevisionIncrement,
	SEGMENT,
	strictManagedRevision,
} from "./artifact-naming.js";

/**
 * How this profile spells a revision label with its ordinal left as a placeholder
 * (`rNN` under a domain whose revision prefix is `r`, `vNN` under one whose prefix is
 * `v`), and its first two concrete labels.
 *
 * Prose only: every one of these three is read by a caller -- JSON-Schema `description`
 * strings and refusal messages -- and never by a matcher. `artifact-naming.ts` owns every
 * pattern that actually parses a filename. They existed here as the hardcoded literals
 * `rNN`, `r01` and `r02`, which are simply false for any domain that does not spell its
 * revisions with an `r`.
 */
const REVISION_PLACEHOLDER = `${DOMAIN.artifact.revisionPattern}NN`;
const FIRST_REVISION_LABEL = artifact.revisionLabel(1);
const SECOND_REVISION_LABEL = artifact.revisionLabel(2);

const GUIDE_DIRECTORY = "guidance/paper-guide";
const PROPOSAL_DIRECTORY = artifact.directory;
const MAX_READ_BYTES = 64 * 1024;
const MAX_WRITE_BYTES = 256 * 1024;
const MAX_APPEND_BYTES = 64 * 1024;
const MAX_INVENTORY_ENTRIES = 200;
const MAX_RESULT_BYTES = 64 * 1024;
const MAX_NAME_LENGTH = 200;
const MAX_SLUG_LENGTH = 80;
const MAX_DERIVE_INSERTIONS = 32;
const MAX_DERIVE_ANCHOR_BYTES = 16 * 1024;
const MAX_DERIVE_INSERTION_BYTES = 64 * 1024;
const MAX_DERIVE_REPLACEMENTS = 16;
const MAX_DERIVE_REPLACEMENT_BYTES = 64 * 1024;
const MAX_DERIVE_EQUATION_AUTHORIZATIONS = 16;
const MAX_DERIVE_DISPLAY_RELOCATIONS = 16;
const MAX_DERIVE_SECTION_REMOVALS = 32;
const MAX_SUCCESSOR_PATCHES = 32;
const MAX_SUCCESSOR_PATCH_BYTES = 64 * 1024;
const MAX_SUCCESSOR_TOTAL_PATCH_BYTES = 128 * 1024;
const MAX_CONTINUITY_ENTRIES = 64;
const MAX_CONTINUITY_BLOCK_BYTES = 64 * 1024;
const MAX_CONTINUITY_TOTAL_BYTES = 128 * 1024;
const MAX_FIXED_INVENTORY_PAGE = 32;
const MAX_FIXED_BASE_SECTIONS = 512;
const FIXED_DERIVE_BASE = DOMAIN.deriveBase;
const CAPABILITY_LENGTH = 43;
const ARTIFACT_MARKER = DOMAIN.artifact.marker;
const ARTIFACT_MARKER_NAMESPACE = "proposal-workspace:artifact";
const ARTIFACT_MARKER_BUFFER = artifact.marker;
/**
 * Every reserved engine-marker namespace a managed document's body may never carry: the
 * artifact marker (owned by the head line alone) and the legacy revision marker. One list, so
 * the source neutraliser below and the guards that refuse these bytes cannot drift apart.
 */
const REVISION_MARKER_NAMESPACE = "proposal-workspace:revision";
const RESERVED_MARKER_NAMESPACES = [ARTIFACT_MARKER_NAMESPACE, REVISION_MARKER_NAMESPACE] as const;
const RESERVED_MARKER_PATTERN = RESERVED_MARKER_NAMESPACES.map((namespace) => namespace.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
const RESERVED_MARKER_LINE = new RegExp(`^[ \\t]*<!--[^\\n]*?(?:${RESERVED_MARKER_PATTERN})[^\\n]*?-->[ \\t]*(?:\\r?\\n|$)`, "gm");
const RESERVED_MARKER_RESIDUE = new RegExp(RESERVED_MARKER_PATTERN, "g");

/**
 * Source material loaded into a new document with every reserved engine marker neutralised.
 * A declared source may itself be a managed revision (a downstream domain declares another
 * skill's managed directory), and that document's own head marker is not this one's: pasted verbatim it
 * made the first revision unpublishable. A whole marker comment line is removed; any other
 * occurrence of a reserved namespace (a truncated comment, an inline quotation) loses its colon,
 * so it reads the same and is no longer reserved; NUL bytes are dropped. `removed` counts every
 * neutralised occurrence. The guards that refuse reserved bytes are unchanged: this only keeps
 * another document's markers out of the bytes they judge.
 */
export function neutralizeReservedMarkers(text: string): { text: string; removed: number } {
	let removed = 0;
	const lines = text.replace(RESERVED_MARKER_LINE, () => { removed++; return ""; });
	const residue = lines.replace(RESERVED_MARKER_RESIDUE, (namespace) => { removed++; return namespace.replace(":", " "); });
	const clean = residue.replace(/\0/g, () => { removed++; return ""; });
	return { text: clean, removed };
}

/**
 * A first revision created before 0.14.0 pasted its declared sources verbatim, so a source that
 * was itself a managed revision left whole copies of the artifact marker line inside the body.
 * Those copies confer nothing: ownership is the head line alone. These two helpers find them
 * (an exact marker line that starts after a newline) so a successor can read such a source and
 * drop them, while the composed candidate is still refused if any reserved byte survives.
 */
const COPIED_ARTIFACT_MARKER = new RegExp(`(?<=\\n)${ARTIFACT_MARKER.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "g");

function copiedArtifactMarkerOffsets(text: string): number[] {
	return [...text.matchAll(COPIED_ARTIFACT_MARKER)].map((match) => match.index ?? 0);
}

function withoutCopiedArtifactMarkers(text: string): string {
	return text.replace(COPIED_ARTIFACT_MARKER, "");
}
export const OVERWRITE_CAPABILITY_TTL_MS = 5 * 60 * 1000;

const SAFE_SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
// Profile-derived, like `MANAGED_REVISION_TARGET_MARKDOWN` below: the revision LETTER is
// `DOMAIN.artifact.revisionPattern`, never a literal `r`. These two constants were the last
// site in this file still assuming it, which made every successor unpublishable for any
// domain whose prefix is not `r` -- the neighbouring checks were swept and these were missed.
const SAFE_DERIVE_SLUG = new RegExp(`^${SEGMENT}-${escapedRevisionPrefix}[0-9]{2,}$`);
const SAFE_ROOT_REVISION_SLUG = new RegExp(`^${escapedRevisionPrefix}([0-9]{2,})$`);
const SAFE_INSERTION_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const SAFE_EQUATION_LABEL = /^[A-Za-z][A-Za-z0-9:._-]{0,127}$/;
const SAFE_DISPLAY_ID = /^display-sha256-[a-f0-9]{64}-occurrence-[1-9][0-9]{0,5}$/;
const SAFE_SECTION_ID = /^section-sha256-[a-f0-9]{64}-occurrence-[1-9][0-9]{0,5}$/;
const MAX_NUMBERED_TAG = 999_999;
const SAFE_CAPABILITY = /^[A-Za-z0-9_-]{43}$/;
const GUIDE_MARKDOWN = /^[^/\\\0]+\.md$/;
const GUIDE_MANIFEST = /^[^/\\\0]+\.manifest\.json$/;
const BASE_MARKDOWN = /^[^/\\\0]+\.md$/;
const MANAGED_TARGET_MARKDOWN = new RegExp(`^${escapedStem}-${SEGMENT}\\.md$`);
const MANAGED_REVISION_TARGET_MARKDOWN = new RegExp(`^${escapedStem}-(${SEGMENT})-${escapedRevisionPrefix}([0-9]{2,})\\.md$`);
const ROOT_MANAGED_REVISION_TARGET_MARKDOWN = new RegExp(`^${escapedStem}-${escapedRevisionPrefix}([0-9]{2,})\\.md$`);

const equationBlockAnchorSchema = Type.Object(
	{
		equationLabel: Type.Optional(
			Type.String({
				description: `Exact LaTeX equation label from the ${DOMAIN.baseLabel}, such as eq:ksc.`,
				minLength: 1,
				maxLength: 128,
				pattern: "^[A-Za-z][A-Za-z0-9:._-]{0,127}$",
			}),
		),
		numberedTag: Type.Optional(
			Type.Integer({
				description: `Positive integer selecting an exact numbered \\tag{...} in the ${DOMAIN.baseLabel}.`,
				minimum: 1,
				maximum: MAX_NUMBERED_TAG,
			}),
		),
	},
	{ additionalProperties: false },
);

const displayBlockAuthorizationSchema = Type.Object(
	{
		equationLabel: Type.Optional(
			Type.String({
				description: `Exact LaTeX equation label from the ${DOMAIN.baseLabel}, such as eq:ksc.`,
				minLength: 1,
				maxLength: 128,
				pattern: "^[A-Za-z][A-Za-z0-9:._-]{0,127}$",
			}),
		),
		numberedTag: Type.Optional(
			Type.Integer({
				description: `Positive integer selecting an exact numbered \\tag{...} in the ${DOMAIN.baseLabel}.`,
				minimum: 1,
				maximum: MAX_NUMBERED_TAG,
			}),
		),
		displayBlock: Type.Optional(
			Type.String({
				description: "Exact complete fixed-base display block, including both standalone $$ delimiter lines.",
				minLength: 1,
				maxLength: MAX_DERIVE_REPLACEMENT_BYTES,
			}),
		),
		displayId: Type.Optional(
			Type.String({
				description: "Stable ID returned by inventory/displays or read/display for one exact parsed fixed-base display block.",
				minLength: 1,
				maxLength: 104,
				pattern: "^display-sha256-[a-f0-9]{64}-occurrence-[1-9][0-9]{0,5}$",
			}),
		),
	},
	{ additionalProperties: false },
);

const authorizedDisplayRelocationSchema = Type.Object(
	{
		sourceReplacementId: Type.String({
			description:
				"Replacement that removes the complete source group of individually authorized inherited displays.",
			minLength: 1,
			maxLength: 64,
			pattern: "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
		}),
		destinationReplacementId: Type.String({
			description:
				"Display-free base replacement whose newText contains the moved group exactly once at its authorized destination.",
			minLength: 1,
			maxLength: 64,
			pattern: "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
		}),
	},
	{ additionalProperties: false },
);

const authorizedSectionRemovalSchema = Type.Object(
	{
		sectionId: Type.String({
			description:
				`Stable whole-section ID returned by inventory/sections for the ${DOMAIN.baseLabel}.`,
			minLength: 1,
			maxLength: 104,
			pattern: "^section-sha256-[a-f0-9]{64}-occurrence-[1-9][0-9]{0,5}$",
		}),
	},
	{ additionalProperties: false },
);

const deriveInsertionSchema = Type.Object(
	{
		id: Type.String({
			description: "Unique lowercase-hyphen identifier for this additive insertion.",
			minLength: 1,
			maxLength: 64,
			pattern: "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
		}),
		anchor: Type.Optional(
			Type.Union(
				[
					Type.String({
						description: `Exact unique text or section marker copied from the ${DOMAIN.baseLabel}.`,
						minLength: 1,
						maxLength: MAX_DERIVE_ANCHOR_BYTES,
					}),
					equationBlockAnchorSchema,
				],
				{
					description:
						"Exact unique base text, or one equationLabel/numberedTag selector that always inserts after its complete base display block; omit for end.",
				},
			),
		),
		position: StringEnum(["before", "after", "end"] as const, {
			description:
				"Insert before or after exact text, after a complete equation-selected display block, or append once at end without an anchor.",
		}),
		content: Type.String({
			description: "Additive Markdown bytes to insert without normalization or replacement.",
			minLength: 1,
			maxLength: MAX_DERIVE_INSERTION_BYTES,
		}),
	},
	{ additionalProperties: false },
);

const deriveReplacementSchema = Type.Object(
	{
		id: Type.String({
			description: "Unique lowercase-hyphen identifier for this researcher-authorized correction.",
			minLength: 1,
			maxLength: 64,
			pattern: "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
		}),
		oldText: Type.Optional(
			Type.String({
				description: `Exact unique bounded span of complete Markdown blocks copied from the ${DOMAIN.baseLabel}. It may contain adjacent prose plus complete selected displays. Omit only when exactly one authorizedEquations displayId selects the complete replacement block.`,
				minLength: 1,
				maxLength: MAX_DERIVE_REPLACEMENT_BYTES,
			}),
		),
		newText: Type.String({
			description: "Bounded replacement Markdown; use an empty string for an explicitly authorized removal.",
			maxLength: MAX_DERIVE_REPLACEMENT_BYTES,
		}),
		authorizedEquations: Type.Optional(
			Type.Array(displayBlockAuthorizationSchema, {
				description:
					"One exact fixed-base equationLabel, numberedTag, complete displayBlock, or inventory displayId selector for every inherited display block removed or altered by this replacement. An explicit empty array is accepted only when both oldText and newText are wholly display-free.",
				minItems: 0,
				maxItems: MAX_DERIVE_EQUATION_AUTHORIZATIONS,
			}),
		),
	},
	{ additionalProperties: false },
);

const successorStructuralSelectorSchema = Type.Object({entryId:Type.String({minLength:1,maxLength:256}),startByte:Type.Integer({minimum:0}),endByte:Type.Integer({minimum:1}),textSha256:Type.String({minLength:64,maxLength:64,pattern:'^[a-f0-9]{64}$'}),documentSha256:Type.String({minLength:64,maxLength:64,pattern:'^[a-f0-9]{64}$'})},{additionalProperties:false});

	const successorReplacementPatchSchema = Type.Object(
	{
		id: Type.String({
			description: "Unique lowercase-hyphen patch identifier.",
			minLength: 1,
			maxLength: 64,
			pattern: "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
		}),
		kind: Type.Literal("replace"),
		oldText: Type.String({
			description: "Exact uniquely occurring current-state bytes to replace.",
			minLength: 1,
			maxLength: MAX_SUCCESSOR_PATCH_BYTES,
		}),
		newText: Type.String({
			description: "Exact researcher-authorized successor bytes; empty removes the selected bytes.",
			maxLength: MAX_SUCCESSOR_PATCH_BYTES,
		}),
		selector: Type.Optional(successorStructuralSelectorSchema),
	},
	{ additionalProperties: false },
);

const successorInsertionPatchSchema = Type.Object(
	{
		id: Type.String({
			description: "Unique lowercase-hyphen patch identifier.",
			minLength: 1,
			maxLength: 64,
			pattern: "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
		}),
		kind: Type.Literal("insert"),
		anchor: Type.String({
			description: "Exact uniquely occurring current-state bytes adjacent to the insertion.",
			minLength: 1,
			maxLength: MAX_DERIVE_ANCHOR_BYTES,
		}),
		position: StringEnum(["before", "after"] as const, {
			description: "Insert immediately before or after the exact current-state anchor.",
		}),
		content: Type.String({
			description: "Exact additive Markdown bytes.",
			minLength: 1,
			maxLength: MAX_SUCCESSOR_PATCH_BYTES,
		}),
	},
	{ additionalProperties: false },
);

const successorPatchSchema = Type.Union(
	[successorReplacementPatchSchema, successorInsertionPatchSchema],
	{ description: "One deterministic exact replacement or narrowly anchored additive insertion." },
);

const continuityBlockAssertionSchema = Type.Object(
	{
		id: Type.String({
			description: "Unique manifest-wide lowercase-hyphen assertion identifier.",
			minLength: 1,
			maxLength: 64,
			pattern: "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
		}),
		block: Type.String({
			description: "Exact current-state block bytes to count in the latest body and fully composed candidate.",
			minLength: 1,
			maxLength: MAX_CONTINUITY_BLOCK_BYTES,
		}),
	},
	{ additionalProperties: false },
);

const continuitySupersessionSchema = Type.Object(
	{
		id: Type.String({
			description: "Unique manifest-wide lowercase-hyphen supersession identifier.",
			minLength: 1,
			maxLength: 64,
			pattern: "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
		}),
		priorBlock: Type.String({
			description: "Exact protected block that must occur once in the latest body and zero times in the candidate.",
			minLength: 1,
			maxLength: MAX_CONTINUITY_BLOCK_BYTES,
		}),
		successorBlock: Type.String({
			description: "Exact authorized successor that must be absent from the latest body and occur once in the candidate.",
			minLength: 1,
			maxLength: MAX_CONTINUITY_BLOCK_BYTES,
		}),
	},
	{ additionalProperties: false },
);

const continuityManifestSchema = Type.Object(
	{
		source: Type.Object(
			{
				target: Type.String({
					description: `Exact marker-owned latest revision filename in ${PROPOSAL_DIRECTORY}/, never a path.`,
					minLength: 1,
					maxLength: MAX_NAME_LENGTH,
					pattern: managedRevisionSchemaPattern({ requireLineage: true }),
				}),
				sha256: Type.String({
					description: "SHA-256 of the exact complete marker-owned latest target bytes.",
					minLength: 64,
					maxLength: 64,
					pattern: "^[a-f0-9]{64}$",
				}),
			},
			{ additionalProperties: false },
		),
		required: Type.Optional(
			Type.Array(continuityBlockAssertionSchema, {
				description: "Exact blocks protected as present exactly once in both latest and candidate state.",
				minItems: 1,
				maxItems: MAX_CONTINUITY_ENTRIES,
			}),
		),
		forbidden: Type.Optional(
			Type.Array(continuityBlockAssertionSchema, {
				description: "Explicit prior-removed blocks protected as absent from both latest and candidate state.",
				minItems: 1,
				maxItems: MAX_CONTINUITY_ENTRIES,
			}),
		),
		supersessions: Type.Optional(
			Type.Array(continuitySupersessionSchema, {
				description: "Exact latest-prior to candidate-successor transition pairs.",
				minItems: 1,
				maxItems: MAX_CONTINUITY_ENTRIES,
			}),
		),
	},
	{ additionalProperties: false },
);

const proposalWorkspaceSchema = Type.Object(
	{
		action: StringEnum(
			["inventory", "read", "authorize_overwrite", "write", "append", "derive", "derive_revision", "derive_successor"] as const,
			{
				description: "Operation to perform.",
			},
		),
		resource: StringEnum(
			["guides", "bases", "displays", "sections", "guide", "base", "display", "managed_target", "proposal"] as const,
			{
				description:
					`inventory: guides|bases|displays|sections; read: guide|base|display|managed_target; authorize_overwrite/write/append/derive/derive_revision: proposal. displays/display and sections always target the ${DOMAIN.baseLabel}.`,
			},
		),
		name: Type.Optional(
			Type.String({
				description: "A guide, base, or managed target filename only; never a path.",
				minLength: 1,
				maxLength: MAX_NAME_LENGTH,
			}),
		),
		slug: Type.Optional(
			Type.String({
				description: "Safe lowercase-hyphen slug for a proposal target.",
				minLength: 1,
				maxLength: MAX_SLUG_LENGTH,
				pattern: "^[a-z0-9]+(?:-[a-z0-9]+)*$",
			}),
		),
		content: Type.Optional(
			Type.String({
				description: "Complete Markdown for write, or the Markdown body of one append-only revision.",
				maxLength: MAX_WRITE_BYTES,
			}),
		),
		capability: Type.Optional(
			Type.String({
				description: "One-time opaque capability returned by authorize_overwrite for this exact proposal target.",
				minLength: CAPABILITY_LENGTH,
				maxLength: CAPABILITY_LENGTH,
				pattern: "^[A-Za-z0-9_-]{43}$",
			}),
		),
		operationAuthorization: Type.Optional(
			Type.String({
				description: "One-time DOCUMENT_OPERATION authorization for an approved successor mutation.",
				minLength: CAPABILITY_LENGTH,
				maxLength: CAPABILITY_LENGTH,
				pattern: "^[A-Za-z0-9_-]{43}$",
			}),
		),
		operation_id: Type.Optional(
			Type.String({
				description: "Explicit active document-operation identifier used only to route guarded mutations.",
				minLength: 1,
				maxLength: 80,
				pattern: "^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$",
			}),
		),
		displayId: Type.Optional(
			Type.String({
				description: "Stable parsed fixed-base display ID returned by inventory/displays.",
				minLength: 1,
				maxLength: 104,
				pattern: "^display-sha256-[a-f0-9]{64}-occurrence-[1-9][0-9]{0,5}$",
			}),
		),
		offset: Type.Optional(
			Type.Integer({
				description: "Zero-based fixed-base display or section inventory offset.",
				minimum: 0,
			}),
		),
		limit: Type.Optional(
			Type.Integer({
				description: `Fixed-base display or section inventory page size from 1 to ${MAX_FIXED_INVENTORY_PAGE}.`,
				minimum: 1,
				maximum: MAX_FIXED_INVENTORY_PAGE,
			}),
		),
		base: Type.Optional(
			Type.Literal(FIXED_DERIVE_BASE, {
				description: "The only source accepted by derive and derive_revision.",
			}),
		),
		insertions: Type.Optional(
			Type.Array(deriveInsertionSchema, {
				description: "Bounded ordered additive insertions anchored to exact unique base text.",
				minItems: 1,
				maxItems: MAX_DERIVE_INSERTIONS,
			}),
		),
		replacements: Type.Optional(
			Type.Array(deriveReplacementSchema, {
				description: "Bounded exact unique complete-block replacements for derive_revision only.",
				minItems: 1,
				maxItems: MAX_DERIVE_REPLACEMENTS,
			}),
		),
		authorizedDisplayRelocations: Type.Optional(
			Type.Array(authorizedDisplayRelocationSchema, {
				description:
					"Explicit source-to-destination display move groups. Every display authorized by the source replacement must reappear byte-identically once in the destination replacement and in source order.",
				minItems: 1,
				maxItems: MAX_DERIVE_DISPLAY_RELOCATIONS,
			}),
		),
		authorizedSectionRemovals: Type.Optional(
			Type.Array(authorizedSectionRemovalSchema, {
				description:
					"Explicit researcher-authorized whole fixed-base sections to remove in derive_revision. Each selector removes its heading and body through the next heading of the same or higher level.",
				minItems: 1,
				maxItems: MAX_DERIVE_SECTION_REMOVALS,
			}),
		),
		continuityManifest: Type.Optional(continuityManifestSchema),
		source: Type.Optional(
			Type.String({
				description: `Exact latest marker-owned ${artifact.stem}-${REVISION_PLACEHOLDER}.md root-lineage or ${artifact.stem}-<lineage>-${REVISION_PLACEHOLDER}.md explicit-lineage filename.`,
				minLength: 1,
				maxLength: MAX_NAME_LENGTH,
				pattern: managedRevisionSchemaPattern(),
			}),
		),
		sourceSha256: Type.Optional(
			Type.String({
				description: "Lowercase SHA-256 of the exact complete marker-owned source file bytes.",
				minLength: 64,
				maxLength: 64,
				pattern: "^[a-f0-9]{64}$",
			}),
		),
		patches: Type.Optional(
			Type.Array(successorPatchSchema, {
				description: "Bounded researcher-authorized patch manifest against the exact current state.",
				minItems: 1,
				maxItems: MAX_SUCCESSOR_PATCHES,
			}),
		),
	},
	{ additionalProperties: false },
);

export type ProposalWorkspaceInput = Static<typeof proposalWorkspaceSchema>;
type EquationBlockAnchor = Static<typeof equationBlockAnchorSchema>;
type DisplayBlockAuthorization = Static<typeof displayBlockAuthorizationSchema>;
type DeriveInsertion = Static<typeof deriveInsertionSchema>;
type DeriveReplacement = Static<typeof deriveReplacementSchema>;
type AuthorizedDisplayRelocation = Static<typeof authorizedDisplayRelocationSchema>;
type AuthorizedSectionRemoval = Static<typeof authorizedSectionRemovalSchema>;
type SuccessorPatch = Static<typeof successorPatchSchema>;
type ContinuityManifest = Static<typeof continuityManifestSchema>;
type ContinuityBlockAssertion = Static<typeof continuityBlockAssertionSchema>;
type ContinuitySupersession = Static<typeof continuitySupersessionSchema>;

type ToolResult = {
	content: Array<{ type: "text"; text: string }>;
	details: Record<string, unknown>;
};

type ProposalTargetIdentity = {
	dev: number;
	ino: number;
};

type OverwriteCapability = {
	target: string;
	identity: ProposalTargetIdentity;
	expiresAt: number;
};

export type ProposalWorkspaceToolOptions = {
	now?: () => number;
	operationGuard?: DocumentOperationGuard;
};

function blocked(reason: string, nextStep: string): Error {
	return new Error(`proposal_workspace blocked: ${reason} ${nextStep}`);
}

type CandidateOperation = "initial_create" | "derive" | "derive_revision" | "derive_successor";

export type CandidateValidationFailure = {
	status: "failed";
	phase: "pre-publish";
	operation: CandidateOperation;
	code: string;
	message: string;
	nextStep: string;
	wroteTarget: false;
	[key: string]: unknown;
};

function candidateRejected(
	operation: CandidateOperation,
	code: string,
	message: string,
	nextStep: string,
	evidence: Record<string, unknown> = {},
): Error {
	const candidateValidation: CandidateValidationFailure = {
		status: "failed",
		phase: "pre-publish",
		operation,
		code,
		message,
		nextStep,
		wroteTarget: false,
		...evidence,
	};
	const error = new Error(
		`proposal_workspace candidate validation failed: ${JSON.stringify(candidateValidation)}`,
	) as Error & { candidateValidation: CandidateValidationFailure };
	error.candidateValidation = candidateValidation;
	return error;
}

function throwIfAborted(signal?: AbortSignal): void {
	if (signal?.aborted) throw new Error("proposal_workspace cancelled: operation aborted.");
}

function isMissing(error: unknown): boolean {
	return (
		typeof error === "object" &&
		error !== null &&
		"code" in error &&
		(error.code === "ENOENT" || error.code === "ENOTDIR")
	);
}

function ensureWithin(root: string, candidate: string): void {
	const rel = relative(root, candidate);
	if (rel === "" || (!rel.startsWith(`..${sep}`) && rel !== ".." && !isAbsolute(rel))) return;
	throw blocked("the resolved path is outside the project workspace.", "Use only the named resource fields.");
}

async function canonicalProjectRoot(projectRoot: string): Promise<string> {
	const resolvedRoot = resolve(projectRoot);
	let canonicalRoot: string;
	try {
		canonicalRoot = await realpath(resolvedRoot);
	} catch {
		throw blocked("the project root cannot be resolved.", "Run the tool from its trusted project installation.");
	}
	const rootStat = await stat(canonicalRoot);
	if (!rootStat.isDirectory()) {
		throw blocked("the resolved project root is not a directory.", "Repair the project installation.");
	}
	return canonicalRoot;
}

async function canonicalDirectory(root: string, relativeDirectory: string): Promise<string> {
	const segments = relativeDirectory.split("/").filter(Boolean);
	let current = root;
	for (const segment of segments) {
		current = resolve(current, segment);
		ensureWithin(root, current);
		let entry;
		try {
			entry = await lstat(current);
		} catch (error) {
			if (isMissing(error)) {
				throw blocked(
					`required directory ${JSON.stringify(relativeDirectory)} does not exist.`,
					"Create the real project directory outside this tool, then retry.",
				);
			}
			throw error;
		}
		if (entry.isSymbolicLink()) {
			throw blocked(
				`directory ${JSON.stringify(relativeDirectory)} contains a symbolic-link component.`,
				"Replace it with a real directory; directory symlinks are never authorized.",
			);
		}
		if (!entry.isDirectory()) {
			throw blocked(
				`${JSON.stringify(relativeDirectory)} is not a directory.`,
				"Repair the project workspace and retry.",
			);
		}
	}

	const expected = resolve(root, relativeDirectory);
	const canonical = await realpath(expected);
	if (canonical !== expected) {
		throw blocked(
			`directory ${JSON.stringify(relativeDirectory)} does not resolve to its expected location.`,
			"Replace all path aliases with real project directories.",
		);
	}
	return canonical;
}

function validateFilename(name: string | undefined, pattern: RegExp, kind: string): string {
	if (!name || name.length > MAX_NAME_LENGTH || !pattern.test(name) || isAbsolute(name)) {
		throw blocked(
			`${kind} must be a plain eligible filename, not an absolute or relative path.`,
			`Inventory ${kind === "base" ? "bases" : "guides"} and pass one returned filename exactly.`,
		);
	}
	return name;
}

async function canonicalRegularFile(directory: string, name: string, label: string): Promise<string> {
	const candidate = resolve(directory, name);
	if (dirname(candidate) !== directory) {
		throw blocked(`${label} resolved outside its approved directory.`, "Pass a filename from inventory exactly.");
	}

	let entry;
	try {
		entry = await lstat(candidate);
	} catch (error) {
		if (isMissing(error)) {
			throw blocked(`${label} does not exist.`, "Run inventory and select an existing eligible file.");
		}
		throw error;
	}
	if (entry.isSymbolicLink()) {
		throw blocked(`${label} is a symbolic link.`, "Use a real regular file inside the approved directory.");
	}
	if (!entry.isFile()) {
		throw blocked(`${label} is not a regular file.`, "Use a regular file returned by inventory.");
	}
	if (entry.nlink !== 1) {
		throw blocked(`${label} has multiple hard links.`, "Replace it with a standalone in-place file.");
	}

	const canonical = await realpath(candidate);
	if (canonical !== candidate) {
		throw blocked(`${label} resolves outside its exact approved location.`, "Use a real in-place file, not a path alias.");
	}
	return canonical;
}

async function authorizeGuide(projectRoot: string, rawName: string | undefined): Promise<{ path: string; name: string }> {
	const isMarkdown = rawName ? GUIDE_MARKDOWN.test(rawName) && !GUIDE_MANIFEST.test(rawName) : false;
	if (!isMarkdown) {
		throw blocked(
			"guide reads accept only a .md filename.",
			"Run guide inventory and pass one returned filename exactly.",
		);
	}
	const name = validateFilename(rawName, GUIDE_MARKDOWN, "guide");
	const stem = name.slice(0, -".md".length);
	const directory = await canonicalDirectory(projectRoot, `${GUIDE_DIRECTORY}/${stem}`);
	const markdownPath = await canonicalRegularFile(directory, name, "guide Markdown");
	return { path: markdownPath, name };
}

async function authorizeBase(projectRoot: string, rawName: string | undefined): Promise<{ path: string; name: string }> {
	const name = validateFilename(rawName, BASE_MARKDOWN, "base");
	const directory = await canonicalDirectory(projectRoot, PROPOSAL_DIRECTORY);
	return { path: await canonicalRegularFile(directory, name, "proposal base"), name };
}

function validateManagedTargetFilename(rawName: string | undefined): string {
	if (
		!rawName ||
		rawName.length > MAX_NAME_LENGTH ||
		!MANAGED_TARGET_MARKDOWN.test(rawName) ||
		isAbsolute(rawName)
	) {
		throw blocked(
			`managed target must be an exact ${artifact.stem}-<slug>.md filename, not a base or path.`,
			"Pass the filename of a prior proposal_workspace write exactly.",
		);
	}
	const slug = rawName.slice(`${artifact.stem}-`.length, -".md".length);
	if (slug.length > MAX_SLUG_LENGTH || !SAFE_SLUG.test(slug)) {
		throw blocked(
			"managed target filename does not match a valid proposal_workspace target.",
			`Pass the exact ${artifact.stem}-<slug>.md filename created by proposal_workspace write.`,
		);
	}
	return rawName;
}

async function authorizeManagedTarget(
	projectRoot: string,
	rawName: string | undefined,
): Promise<{ path: string; name: string }> {
	const name = validateManagedTargetFilename(rawName);
	const directory = await canonicalDirectory(projectRoot, PROPOSAL_DIRECTORY);
	return { path: await canonicalRegularFile(directory, name, "managed proposal target"), name };
}

function noFollowFlag(): number {
	if (typeof constants.O_NOFOLLOW !== "number") {
		throw blocked(
			"this platform does not provide O_NOFOLLOW protection.",
			"Use a platform with O_NOFOLLOW support; the tool fails closed rather than follow a raced symlink.",
		);
	}
	return constants.O_NOFOLLOW;
}

async function readBounded(
	path: string,
	displayName: string,
	signal?: AbortSignal,
	requireArtifactMarker = false,
): Promise<ToolResult> {
	throwIfAborted(signal);
	const handle = await open(path, constants.O_RDONLY | noFollowFlag());
	try {
		const [fileStat, pathStat, canonical] = await Promise.all([handle.stat(), lstat(path), realpath(path)]);
		if (
			!fileStat.isFile() ||
			!pathStat.isFile() ||
			pathStat.isSymbolicLink() ||
			fileStat.nlink !== 1 ||
			pathStat.nlink !== 1 ||
			fileStat.dev !== pathStat.dev ||
			fileStat.ino !== pathStat.ino ||
			canonical !== path
		) {
			throw blocked(
				"the authorized read target changed, is linked, or is no longer a standalone regular file.",
				"Retry after repairing the workspace.",
			);
		}
		if (requireArtifactMarker) {
			if (fileStat.size > MAX_WRITE_BYTES) {
				throw blocked(
					"the managed target exceeds the managed proposal size limit.",
					"Use an unchanged bounded target created by proposal_workspace.",
				);
			}
			if (!(await openHandleHasArtifactMarker(handle))) {
				throw blocked(
					"the managed target is not marked as a tool-created artifact.",
					"Read only a target created by proposal_workspace write; matching filenames alone never authorize managed reads.",
				);
			}
		}
		const buffer = Buffer.alloc((requireArtifactMarker ? MAX_WRITE_BYTES : MAX_READ_BYTES) + 1);
		let total = 0;
		while (total < buffer.length) {
			throwIfAborted(signal);
			const { bytesRead } = await handle.read(buffer, total, buffer.length - total, total);
			if (bytesRead === 0) break;
			total += bytesRead;
		}
		let sha256: string | undefined;
		if (requireArtifactMarker) {
			const [after, pathAfter, canonicalAfter] = await Promise.all([
				handle.stat(),
				lstat(path),
				realpath(path),
			]);
			if (
				total > MAX_WRITE_BYTES ||
				total !== fileStat.size ||
				fileStat.dev !== after.dev ||
				fileStat.ino !== after.ino ||
				fileStat.size !== after.size ||
				fileStat.mtimeMs !== after.mtimeMs ||
				fileStat.ctimeMs !== after.ctimeMs ||
				!pathAfter.isFile() ||
				pathAfter.isSymbolicLink() ||
				pathAfter.nlink !== 1 ||
				after.dev !== pathAfter.dev ||
				after.ino !== pathAfter.ino ||
				canonicalAfter !== path
			) {
				throw blocked(
					"the managed target changed while its complete bytes were read.",
					"Retry after the exact marker-owned target is stable.",
				);
			}
			sha256 = createHash("sha256").update(buffer.subarray(0, total)).digest("hex");
		}
		const truncated = total > MAX_READ_BYTES;
		const text = buffer.subarray(0, Math.min(total, MAX_READ_BYTES)).toString("utf8");
		const suffix = truncated ? `\n\n[proposal_workspace output truncated at ${MAX_READ_BYTES} bytes]` : "";
		return {
			content: [{ type: "text", text: `${text}${suffix}` }],
			details: {
				resource: displayName,
				...(sha256 === undefined ? {} : { sha256, managedBytes: Buffer.from(buffer.subarray(0, total)) }),
				bytesReturned: Math.min(total, MAX_READ_BYTES),
				truncated,
			},
		};
	} finally {
		await handle.close();
	}
}

function boundedResult(text: string): { text: string; truncated: boolean } {
	const encoded = Buffer.from(text, "utf8");
	if (encoded.length <= MAX_RESULT_BYTES) return { text, truncated: false };
	return {
		text: `${encoded.subarray(0, MAX_RESULT_BYTES).toString("utf8")}\n[proposal_workspace output truncated]`,
		truncated: true,
	};
}

async function inventoryGuides(projectRoot: string): Promise<ToolResult> {
	const directory = await canonicalDirectory(projectRoot, GUIDE_DIRECTORY);
	const entries = await readdir(directory, { withFileTypes: true });
	const folders = entries
		.filter((entry) => entry.isDirectory())
		.map((entry) => entry.name)
		.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
	const guides: Array<{ markdown: string }> = [];
	for (const folder of folders) {
		const markdown = `${folder}.md`;
		if (!GUIDE_MARKDOWN.test(markdown)) continue;
		let paperDir: string;
		try {
			paperDir = await canonicalDirectory(projectRoot, `${GUIDE_DIRECTORY}/${folder}`);
		} catch {
			continue;
		}
		try {
			await canonicalRegularFile(paperDir, markdown, "guide Markdown");
		} catch {
			continue;
		}
		guides.push({ markdown });
	}
	const selected = guides.slice(0, MAX_INVENTORY_ENTRIES);
	const rendered = boundedResult(JSON.stringify(selected, null, 2));
	return {
		content: [{ type: "text", text: rendered.text }],
		details: {
			resource: "guides",
			count: guides.length,
			truncated: rendered.truncated || guides.length > selected.length,
		},
	};
}

async function inventoryBases(projectRoot: string): Promise<ToolResult> {
	const directory = await canonicalDirectory(projectRoot, PROPOSAL_DIRECTORY);
	const entries = await readdir(directory, { withFileTypes: true });
	const names = entries
		.filter((entry) => entry.isFile() && BASE_MARKDOWN.test(entry.name))
		.map((entry) => entry.name)
		.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
	for (const name of names) await canonicalRegularFile(directory, name, "proposal base");
	const selected = names.slice(0, MAX_INVENTORY_ENTRIES);
	const rendered = boundedResult(JSON.stringify(selected, null, 2));
	return {
		content: [{ type: "text", text: rendered.text }],
		details: {
			resource: "bases",
			count: names.length,
			truncated: rendered.truncated || names.length > selected.length,
		},
	};
}

function assertShape(params: ProposalWorkspaceInput): void {
	const allowedKeys = new Set([
		"action",
		"resource",
		"name",
		"slug",
		"content",
		"capability",
		"operationAuthorization",
		"operation_id",
		"displayId",
		"offset",
		"limit",
		"base",
		"insertions",
		"replacements",
		"authorizedDisplayRelocations",
		"authorizedSectionRemovals",
		"continuityManifest",
		"source",
		"sourceSha256",
		"patches",
	]);
	for (const key of Object.keys(params)) {
		if (!allowedKeys.has(key)) {
			throw blocked(
				`unknown authorization or operation field ${JSON.stringify(key)} is not accepted.`,
				"Use only the documented action fields; boolean flags and model claims cannot authorize replacement.",
			);
		}
	}
	const hasName = params.name !== undefined;
	const hasSlug = params.slug !== undefined;
	const hasContent = params.content !== undefined;
	const hasCapability = params.capability !== undefined;
	const hasOperationAuthorization = params.operationAuthorization !== undefined;
	const hasDisplayId = params.displayId !== undefined;
	const hasOffset = params.offset !== undefined;
	const hasLimit = params.limit !== undefined;
	const hasBase = params.base !== undefined;
	const hasInsertions = params.insertions !== undefined;
	const hasReplacements = params.replacements !== undefined;
	const hasAuthorizedDisplayRelocations = params.authorizedDisplayRelocations !== undefined;
	const hasAuthorizedSectionRemovals = params.authorizedSectionRemovals !== undefined;
	const hasContinuityManifest = params.continuityManifest !== undefined;
	const hasSource = params.source !== undefined;
	const hasSourceSha256 = params.sourceSha256 !== undefined;
	const hasPatches = params.patches !== undefined;
	const noSuccessorFields = !hasSource && !hasSourceSha256 && !hasPatches;
	const noDeriveFields =
		!hasBase &&
		!hasInsertions &&
		!hasReplacements &&
		!hasAuthorizedDisplayRelocations &&
		!hasAuthorizedSectionRemovals &&
		!hasContinuityManifest &&
		noSuccessorFields;
	const noDisplayFields = !hasDisplayId && !hasOffset && !hasLimit;
	const valid =
		(params.action === "inventory" &&
			(params.resource === "guides" || params.resource === "bases") &&
			!hasName &&
			!hasSlug &&
			!hasContent &&
			!hasCapability &&
			!hasDisplayId &&
			!hasOffset &&
			!hasLimit &&
			noDeriveFields) ||
		(params.action === "inventory" &&
			(params.resource === "displays" || params.resource === "sections") &&
			!hasName &&
			!hasSlug &&
			!hasContent &&
			!hasCapability &&
			!hasDisplayId &&
			noDeriveFields) ||
		(params.action === "read" &&
			(params.resource === "guide" || params.resource === "base" || params.resource === "managed_target") &&
			hasName &&
			!hasSlug &&
			!hasContent &&
			!hasCapability &&
			!hasDisplayId &&
			!hasOffset &&
			!hasLimit &&
			noDeriveFields) ||
		(params.action === "read" &&
			params.resource === "display" &&
			!hasName &&
			!hasSlug &&
			!hasContent &&
			!hasCapability &&
			hasDisplayId &&
			!hasOffset &&
			!hasLimit &&
			noDeriveFields) ||
		(params.action === "authorize_overwrite" &&
			params.resource === "proposal" &&
			!hasName &&
			hasSlug &&
			!hasContent &&
			!hasCapability &&
			noDisplayFields &&
			noDeriveFields) ||
		(params.action === "write" &&
			params.resource === "proposal" &&
			!hasName &&
			hasSlug &&
			hasContent &&
			noDisplayFields &&
			!hasBase &&
			!hasInsertions &&
			!hasReplacements &&
			!hasAuthorizedDisplayRelocations &&
			!hasAuthorizedSectionRemovals &&
			!hasContinuityManifest &&
			noSuccessorFields) ||
		(params.action === "append" &&
			params.resource === "proposal" &&
			!hasName &&
			hasSlug &&
			hasContent &&
			!hasCapability &&
			noDisplayFields &&
			noDeriveFields) ||
		(params.action === "derive" &&
			params.resource === "proposal" &&
			!hasName &&
			hasSlug &&
			!hasContent &&
			!hasCapability &&
			noDisplayFields &&
			hasBase &&
			hasInsertions &&
			!hasReplacements &&
			!hasAuthorizedDisplayRelocations &&
			!hasAuthorizedSectionRemovals &&
			noSuccessorFields) ||
		(params.action === "derive_revision" &&
			params.resource === "proposal" &&
			!hasName &&
			hasSlug &&
			!hasContent &&
			!hasCapability &&
			noDisplayFields &&
			hasBase &&
			(hasReplacements || hasAuthorizedSectionRemovals) &&
			(!hasAuthorizedDisplayRelocations || hasReplacements) &&
			noSuccessorFields) ||
		(params.action === "derive_successor" &&
			params.resource === "proposal" &&
			!hasName &&
			hasSlug &&
			!hasContent &&
			!hasCapability &&
			noDisplayFields &&
			!hasBase &&
			!hasInsertions &&
			!hasReplacements &&
			!hasAuthorizedDisplayRelocations &&
			!hasAuthorizedSectionRemovals &&
			!hasContinuityManifest &&
			hasSource &&
			hasSourceSha256 &&
			hasPatches);
	if (
		!valid ||
		(hasOperationAuthorization && params.action !== "write" && params.action !== "derive_successor")
	) {
		throw blocked(
			"the action/resource fields do not form an allowed operation.",
			`Use inventory/read/write as documented; derive and derive_revision retain fixed-base compatibility; derive_successor requires only proposal, the exact latest source filename and SHA-256, a greater same-lineage -${REVISION_PLACEHOLDER} slug, and a bounded exact patch manifest.`,
		);
	}
}

function validateSlug(slug: string | undefined): string {
	if (!slug || slug.length > MAX_SLUG_LENGTH || !SAFE_SLUG.test(slug)) {
		throw blocked(
			"proposal slug must contain only lowercase ASCII letters, digits, and single hyphen separators.",
			"Provide a slug such as neural-signal-modeling.",
		);
	}
	return slug;
}

async function proposalTarget(
	projectRoot: string,
	slug: string | undefined,
): Promise<{ root: string; target: string; filename: string }> {
	const safeSlug = validateSlug(slug);
	const filename = `${artifact.stem}-${safeSlug}.md`;
	const root = await canonicalProjectRoot(projectRoot);
	const directory = await canonicalDirectory(root, PROPOSAL_DIRECTORY);
	const target = resolve(directory, filename);
	if (dirname(target) !== directory) {
		throw blocked(`proposal target resolved outside ${PROPOSAL_DIRECTORY}/.`, "Use a strict lowercase-hyphen slug.");
	}
	return { root, target, filename };
}

async function inspectProposalTarget(target: string): Promise<ProposalTargetIdentity | undefined> {
	let entry;
	try {
		entry = await lstat(target);
	} catch (error) {
		if (isMissing(error)) return undefined;
		throw error;
	}
	if (entry.isSymbolicLink() || !entry.isFile() || entry.nlink !== 1) {
		throw blocked(
			"the proposal target exists but is not a standalone real regular file.",
			"Remove the alias, hard link, or non-file target outside this tool before retrying.",
		);
	}
	if ((await realpath(target)) !== target) {
		throw blocked("the proposal target resolves outside its exact location.", "Use a real in-place proposal file.");
	}
	return { dev: entry.dev, ino: entry.ino };
}

function sameIdentity(left: ProposalTargetIdentity, right: ProposalTargetIdentity): boolean {
	return left.dev === right.dev && left.ino === right.ino;
}

async function openHandleHasArtifactMarker(handle: FileHandle): Promise<boolean> {
	const marker = Buffer.alloc(ARTIFACT_MARKER_BUFFER.length);
	let total = 0;
	while (total < marker.length) {
		const { bytesRead } = await handle.read(marker, total, marker.length - total, total);
		if (bytesRead === 0) return false;
		total += bytesRead;
	}
	return marker.equals(ARTIFACT_MARKER_BUFFER);
}

function newCapability(capabilities: Map<string, OverwriteCapability>): string {
	let capability: string;
	do {
		capability = randomBytes(32).toString("base64url");
	} while (capabilities.has(capability));
	return capability;
}

async function authorizeProposalOverwrite(
	projectRoot: string,
	slug: string | undefined,
	signal: AbortSignal | undefined,
	ctx: ExtensionContext | undefined,
	capabilities: Map<string, OverwriteCapability>,
	now: () => number,
): Promise<ToolResult> {
	throwIfAborted(signal);
	const { root, target, filename } = await proposalTarget(projectRoot, slug);
	const identity = await withFileMutationQueue(target, async () => {
		const current = await inspectProposalTarget(target);
		if (!current) {
			throw blocked(
				"the proposal target does not exist, so overwrite authorization cannot be issued.",
				"Write the new target directly without a capability.",
			);
		}
		return current;
	});
	if (!ctx?.hasUI) {
		throw blocked(
			"overwrite authorization requires an interactive UI confirmation.",
			"Retry in a UI-enabled Pi session; headless authorization is always denied.",
		);
	}
	const approved = await ctx.ui.confirm(
		"Authorize proposal replacement",
		`Allow one replacement of ${PROPOSAL_DIRECTORY}/${filename} within five minutes? This approval cannot modify any base path.`,
	);
	if (approved !== true) {
		throw blocked("the human did not approve proposal replacement.", "Leave the existing proposal unchanged.");
	}
	throwIfAborted(signal);

	return withFileMutationQueue(target, async () => {
		throwIfAborted(signal);
		const directory = await canonicalDirectory(root, PROPOSAL_DIRECTORY);
		if (resolve(directory, filename) !== target) {
			throw blocked(`the ${PROPOSAL_DIRECTORY} directory changed during authorization.`, "Repair the workspace and retry.");
		}
		const current = await inspectProposalTarget(target);
		if (!current || !sameIdentity(identity, current)) {
			throw blocked(
				"the proposal target changed during human confirmation.",
				"Inspect the current target and request a new overwrite authorization.",
			);
		}
		const issuedAt = now();
		for (const [token, authorization] of capabilities) {
			if (authorization.expiresAt <= issuedAt) capabilities.delete(token);
		}
		const capability = newCapability(capabilities);
		const expiresAt = issuedAt + OVERWRITE_CAPABILITY_TTL_MS;
		capabilities.set(capability, { target, identity: current, expiresAt });
		return {
			content: [
				{
					type: "text",
					text: `Human-approved one-time overwrite capability for ${PROPOSAL_DIRECTORY}/${filename}: ${capability}`,
				},
			],
			details: {
				resource: "proposal",
				path: `${PROPOSAL_DIRECTORY}/${filename}`,
				capability,
				expiresAt,
			},
		};
	});
}

async function writeProposal(
	projectRoot: string,
	slug: string | undefined,
	content: string | undefined,
	capability: string | undefined,
	signal: AbortSignal | undefined,
	capabilities: Map<string, OverwriteCapability>,
	now: () => number,
): Promise<ToolResult> {
	if (content === undefined) {
		throw blocked("proposal content is required.", "Provide the complete Markdown content in the content field.");
	}
	const contentBytes = Buffer.byteLength(content, "utf8");
	if (contentBytes > MAX_WRITE_BYTES) {
		throw blocked(
			`proposal content exceeds the ${MAX_WRITE_BYTES}-byte write limit.`,
			"Reduce the proposal size before retrying.",
		);
	}
	if (content.includes("\0") || content.includes(ARTIFACT_MARKER_NAMESPACE)) {
		throw blocked(
			"proposal content contains the reserved tool-owned artifact marker or a NUL byte.",
			"Remove reserved proposal-workspace artifact markers and pass only the proposal Markdown body.",
		);
	}
	if (capability !== undefined && (typeof capability !== "string" || !SAFE_CAPABILITY.test(capability))) {
		throw blocked(
			"the overwrite capability is malformed.",
			"Use the opaque capability returned by authorize_overwrite without modification.",
		);
	}

	const { root, target, filename } = await proposalTarget(projectRoot, slug);
	return withFileMutationQueue(target, async () => {
		throwIfAborted(signal);
		const directory = await canonicalDirectory(root, PROPOSAL_DIRECTORY);
		if (resolve(directory, filename) !== target) {
			throw blocked(`the ${PROPOSAL_DIRECTORY} directory changed during authorization.`, "Repair the workspace and retry.");
		}
		const existingIdentity = await inspectProposalTarget(target);
		let flags = (existingIdentity ? constants.O_RDWR : constants.O_WRONLY) | noFollowFlag();
		if (existingIdentity) {
			if (!capability) {
				throw blocked(
					"the proposal target already exists and no overwrite capability was presented.",
					"Run authorize_overwrite for this exact slug and obtain human UI approval before retrying the write.",
				);
			}
			const authorization = capabilities.get(capability);
			if (!authorization) {
				throw blocked(
					"the overwrite capability is invalid or has already been consumed.",
					"Request a fresh human-approved capability for this exact slug.",
				);
			}
			capabilities.delete(capability);
			if (authorization.expiresAt <= now()) {
				throw blocked(
					"the overwrite capability has expired.",
					"Request a fresh human-approved capability for this exact slug.",
				);
			}
			if (authorization.target !== target || !sameIdentity(authorization.identity, existingIdentity)) {
				throw blocked(
					"the overwrite capability does not match the current proposal target.",
					"Inspect the target and request a fresh capability for this exact slug.",
				);
			}
		} else {
			if (capability !== undefined) {
				const authorization = capabilities.get(capability);
				if (authorization) capabilities.delete(capability);
				throw blocked(
					"an overwrite capability cannot authorize creation of a missing target.",
					"Write the new proposal without a capability.",
				);
			}
			flags |= constants.O_CREAT | constants.O_EXCL;
		}

		let bytesWritten = contentBytes;
		let handle;
		try {
			handle = await open(target, flags, 0o600);
		} catch (error) {
			if (
				!existingIdentity &&
				typeof error === "object" &&
				error !== null &&
				"code" in error &&
				error.code === "EEXIST"
			) {
				throw blocked(
					"the proposal target appeared before exclusive creation.",
					"Inspect it and request human overwrite authorization if replacement is intended.",
				);
			}
			throw error;
		}
		try {
			throwIfAborted(signal);
			const [fileStat, pathStat] = await Promise.all([handle.stat(), lstat(target)]);
			if (
				!fileStat.isFile() ||
				!pathStat.isFile() ||
				pathStat.isSymbolicLink() ||
				fileStat.nlink !== 1 ||
				pathStat.nlink !== 1 ||
				fileStat.dev !== pathStat.dev ||
				fileStat.ino !== pathStat.ino ||
				(existingIdentity !== undefined && !sameIdentity(existingIdentity, fileStat)) ||
				(await realpath(target)) !== target
			) {
				throw blocked(
					"the proposal target changed or became linked before mutation.",
					"Repair the target and request a fresh authorization if replacement is still intended.",
				);
			}
			const preserveArtifactMarker = existingIdentity
				? await openHandleHasArtifactMarker(handle)
				: true;
			const output = preserveArtifactMarker ? `${ARTIFACT_MARKER}${content}` : content;
			bytesWritten = Buffer.byteLength(output, "utf8");
			if (existingIdentity) await handle.truncate(0);
			await handle.writeFile(output, "utf8");
			await handle.sync();
		} finally {
			await handle.close();
		}
		throwIfAborted(signal);
		return {
			content: [{ type: "text", text: `Wrote ${bytesWritten} bytes to ${PROPOSAL_DIRECTORY}/${filename}.` }],
			details: { resource: "proposal", path: `${PROPOSAL_DIRECTORY}/${filename}`, bytesWritten },
		};
	});
}

function validateRevisionBody(content: string | undefined): string {
	if (content === undefined || content.trim().length === 0) {
		throw blocked(
			"append revision content is required and cannot be blank.",
			"Provide the approved Markdown update as the content field.",
		);
	}
	if (
		content.includes("\0") ||
		content.includes(REVISION_MARKER_NAMESPACE) ||
		content.includes(ARTIFACT_MARKER_NAMESPACE)
	) {
		throw blocked(
			"append revision content contains a reserved revision marker, tool-owned artifact marker, or NUL byte.",
			"Remove reserved proposal-workspace markers and pass only the Markdown revision body.",
		);
	}
	if (Buffer.byteLength(content, "utf8") > MAX_APPEND_BYTES) {
		throw blocked(
			`append revision content exceeds the ${MAX_APPEND_BYTES}-byte append limit.`,
			"Reduce the revision to one bounded approved update before retrying.",
		);
	}
	return content.endsWith("\n") ? content : `${content}\n`;
}

async function appendProposalRevision(
	projectRoot: string,
	slug: string | undefined,
	content: string | undefined,
	signal: AbortSignal | undefined,
): Promise<ToolResult> {
	const revisionBody = validateRevisionBody(content);
	const { root, target, filename } = await proposalTarget(projectRoot, slug);
	return withFileMutationQueue(target, async () => {
		throwIfAborted(signal);
		const directory = await canonicalDirectory(root, PROPOSAL_DIRECTORY);
		if (resolve(directory, filename) !== target) {
			throw blocked(`the ${PROPOSAL_DIRECTORY} directory changed during authorization.`, "Repair the workspace and retry.");
		}
		const existingIdentity = await inspectProposalTarget(target);
		if (!existingIdentity) {
			throw blocked(
				"append requires an existing generated proposal target.",
				"Create the target once with write, then append approved revisions to it.",
			);
		}

		const handle = await open(target, constants.O_RDWR | constants.O_APPEND | noFollowFlag());
		try {
			throwIfAborted(signal);
			const [fileStat, pathStat] = await Promise.all([handle.stat(), lstat(target)]);
			if (
				!fileStat.isFile() ||
				!pathStat.isFile() ||
				pathStat.isSymbolicLink() ||
				fileStat.nlink !== 1 ||
				pathStat.nlink !== 1 ||
				fileStat.dev !== pathStat.dev ||
				fileStat.ino !== pathStat.ino ||
				!sameIdentity(existingIdentity, fileStat) ||
				(await realpath(target)) !== target
			) {
				throw blocked(
					"the proposal target changed or became linked before append.",
					"Repair the target and retry the append against the real generated proposal.",
				);
			}

			if (!(await openHandleHasArtifactMarker(handle))) {
				throw blocked(
					"the proposal target is not marked as a tool-created artifact.",
					"Create a new target with proposal_workspace write; matching filenames alone never authorize append.",
				);
			}

			const previousBytes = fileStat.size;
			const bodyDigest = createHash("sha256").update(revisionBody, "utf8").digest("hex");
			const revisionId = createHash("sha256")
				.update(`${previousBytes}\0${bodyDigest}`, "utf8")
				.digest("hex");
			const block =
				`\n\n<!-- proposal-workspace:revision:start id=sha256:${revisionId} -->\n` +
				revisionBody +
				"<!-- proposal-workspace:revision:end -->\n";
			const blockBuffer = Buffer.from(block, "utf8");
			if (blockBuffer.length > MAX_APPEND_BYTES) {
				throw blocked(
					`the immutable revision block exceeds the ${MAX_APPEND_BYTES}-byte append limit.`,
					"Reduce the Markdown revision body and retry.",
				);
			}

			throwIfAborted(signal);
			await handle.writeFile(blockBuffer);
			await handle.sync();
			const [finalFileStat, finalPathStat] = await Promise.all([handle.stat(), lstat(target)]);
			const resultingBytes = previousBytes + blockBuffer.length;
			if (
				!finalFileStat.isFile() ||
				!finalPathStat.isFile() ||
				finalPathStat.isSymbolicLink() ||
				finalFileStat.nlink !== 1 ||
				finalPathStat.nlink !== 1 ||
				finalFileStat.dev !== finalPathStat.dev ||
				finalFileStat.ino !== finalPathStat.ino ||
				!sameIdentity(existingIdentity, finalFileStat) ||
				finalFileStat.size !== resultingBytes ||
				(await realpath(target)) !== target
			) {
				throw blocked(
					"the proposal target changed during append, so a reliable revision receipt cannot be issued.",
					"Inspect the generated proposal before attempting another revision.",
				);
			}

			const blockSha256 = createHash("sha256").update(blockBuffer).digest("hex");
			const artifactPath = `${PROPOSAL_DIRECTORY}/${filename}`;
			return {
				content: [
					{
						type: "text",
						text: `Appended immutable revision sha256:${revisionId} to ${artifactPath} at byte offset ${previousBytes} (${blockBuffer.length} bytes).`,
					},
				],
				details: {
					resource: "proposal",
					path: artifactPath,
					operation: "append",
					revision: {
						id: `sha256:${revisionId}`,
						offset: previousBytes,
						bytesAppended: blockBuffer.length,
						resultingBytes,
						blockSha256,
					},
				},
			};
		} finally {
			await handle.close();
		}
	});
}

type SourceSpan = {
	start: number;
	end: number;
	text: string;
};

type InlineReplacement = SourceSpan & {
	replacement: string;
};

function displayMathBlocks(source: string, requireAtLeastOne = true): SourceSpan[] {
	const blocks: SourceSpan[] = [];
	let opening: number | undefined;
	let cursor = 0;
	while (cursor < source.length) {
		const newline = source.indexOf("\n", cursor);
		const end = newline === -1 ? source.length : newline + 1;
		const rawLine = source.slice(cursor, end);
		const line = rawLine.replace(/\r?\n$/, "");
		if (/^[ \t]*\$\$[ \t]*$/.test(line)) {
			if (opening === undefined) {
				opening = cursor;
			} else {
				blocks.push({ start: opening, end, text: source.slice(opening, end) });
				opening = undefined;
			}
		}
		cursor = end;
	}
	if (opening !== undefined) {
		throw blocked(
			`the ${DOMAIN.baseLabel} has an unclosed display-math block.`,
			"Restore the complete selected base before deriving a proposal.",
		);
	}
	if (requireAtLeastOne && blocks.length === 0) {
		throw blocked(
			`the ${DOMAIN.baseLabel} is missing its display-math blocks.`,
			"Restore the selected base before deriving a proposal.",
		);
	}
	return blocks;
}

type FixedSectionDescriptor = {
	sectionId: string;
	index: number;
	headingText: string;
	headingLevel: number;
	heading: SourceSpan;
	section: SourceSpan;
	bytes: number;
	displayCount: number;
};

function fixedSectionDescriptors(
	source: string,
	displayBlocks: SourceSpan[],
): FixedSectionDescriptor[] {
	const headings: Array<{
		headingText: string;
		headingLevel: number;
		heading: SourceSpan;
	}> = [];
	let fence: { marker: "`" | "~"; length: number } | undefined;
	let cursor = 0;
	while (cursor < source.length) {
		const newline = source.indexOf("\n", cursor);
		const end = newline === -1 ? source.length : newline + 1;
		const rawLine = source.slice(cursor, end);
		const line = rawLine.replace(/\r?\n$/, "");
		const insideDisplay = displayBlocks.some(
			(block) => cursor >= block.start && cursor < block.end,
		);
		if (insideDisplay) {
			cursor = end;
			continue;
		}

		if (fence) {
			const closing = line.match(/^ {0,3}(`+|~+)[ \t]*$/);
			if (
				closing &&
				closing[1][0] === fence.marker &&
				closing[1].length >= fence.length
			) {
				fence = undefined;
			}
			cursor = end;
			continue;
		}
		const opening = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
		if (opening && (opening[1][0] === "~" || !opening[2].includes("`"))) {
			fence = {
				marker: opening[1][0] as "`" | "~",
				length: opening[1].length,
			};
			cursor = end;
			continue;
		}

		const headingMatch = line.match(/^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$/);
		if (headingMatch) {
			const headingText = (headingMatch[2] ?? "")
				.replace(/[ \t]+#+[ \t]*$/, "")
				.trim();
			headings.push({
				headingText,
				headingLevel: headingMatch[1].length,
				heading: { start: cursor, end, text: rawLine },
			});
			if (headings.length > MAX_FIXED_BASE_SECTIONS) {
				throw blocked(
					`the ${DOMAIN.baseLabel} exceeds the ${MAX_FIXED_BASE_SECTIONS}-section inventory limit.`,
					"Reduce the heading count before inventorying or deriving section removals.",
				);
			}
		}
		cursor = end;
	}
	if (fence) {
		throw blocked(
			`the ${DOMAIN.baseLabel} has an unclosed fenced code block.`,
			"Restore the complete selected base before inventorying or removing Markdown sections.",
		);
	}

	const digestOccurrences = new Map<string, number>();
	return headings.map((item, index) => {
		const nextBoundary = headings
			.slice(index + 1)
			.find((candidate) => candidate.headingLevel <= item.headingLevel);
		const sectionEnd = nextBoundary?.heading.start ?? source.length;
		const section = {
			start: item.heading.start,
			end: sectionEnd,
			text: source.slice(item.heading.start, sectionEnd),
		};
		const digest = createHash("sha256").update(item.heading.text, "utf8").digest("hex");
		const occurrence = (digestOccurrences.get(digest) ?? 0) + 1;
		digestOccurrences.set(digest, occurrence);
		return {
			sectionId: `section-sha256-${digest}-occurrence-${occurrence}`,
			index: index + 1,
			headingText: item.headingText,
			headingLevel: item.headingLevel,
			heading: item.heading,
			section,
			bytes: Buffer.byteLength(section.text, "utf8"),
			displayCount: displayBlocks.filter(
				(block) => block.start >= section.start && block.end <= section.end,
			).length,
		};
	});
}

function sectionDescriptorForId(
	sectionId: string,
	operationId: string,
	descriptors: FixedSectionDescriptor[],
): FixedSectionDescriptor {
	if (!SAFE_SECTION_ID.test(sectionId)) {
		throw blocked(
			`sectionId for ${JSON.stringify(operationId)} is malformed.`,
			"Use one exact stable ID returned by inventory/sections without modification.",
		);
	}
	const matches = descriptors.filter((descriptor) => descriptor.sectionId === sectionId);
	if (matches.length === 0) {
		throw blocked(
			`sectionId ${JSON.stringify(sectionId)} for ${JSON.stringify(operationId)} is unknown in the current ${DOMAIN.baseLabel}.`,
			"Inventory sections again and use an ID from the current parsed fixed base.",
		);
	}
	if (matches.length !== 1) {
		throw blocked(
			`sectionId ${JSON.stringify(sectionId)} for ${JSON.stringify(operationId)} is ambiguous in the current ${DOMAIN.baseLabel}.`,
			"Repair the base section inventory before retrying.",
		);
	}
	return matches[0];
}

function inlineReplacements(source: string, displayBlocks: SourceSpan[]): InlineReplacement[] {
	const replacements: InlineReplacement[] = [];
	let cursor = 0;
	const scan = (start: number, end: number) => {
		const segment = source.slice(start, end);
		const pattern = /\\\(([^\r\n]*?)\\\)/g;
		for (const match of segment.matchAll(pattern)) {
			const relativeStart = match.index;
			const absoluteStart = start + relativeStart;
			replacements.push({
				start: absoluteStart,
				end: absoluteStart + match[0].length,
				text: match[0],
				replacement: `$${match[1]}$`,
			});
		}
	};
	for (const block of displayBlocks) {
		scan(cursor, block.start);
		cursor = block.end;
	}
	scan(cursor, source.length);
	return replacements;
}

function normalizedSource(source: string, replacements: InlineReplacement[]): string {
	let cursor = 0;
	let normalized = "";
	for (const replacement of replacements) {
		normalized += source.slice(cursor, replacement.start);
		normalized += replacement.replacement;
		cursor = replacement.end;
	}
	return normalized + source.slice(cursor);
}

function normalizedOffset(rawOffset: number, replacements: InlineReplacement[]): number {
	let delta = 0;
	for (const replacement of replacements) {
		if (rawOffset > replacement.start && rawOffset < replacement.end) {
			throw blocked(
				"an insertion boundary falls inside an inline-math fragment.",
				"Anchor before or after the complete exact \\(...\\) fragment instead.",
			);
		}
		if (replacement.end <= rawOffset) {
			delta += replacement.replacement.length - replacement.text.length;
		}
	}
	return rawOffset + delta;
}

function boundaryInsideDisplayBlock(rawOffset: number, displayBlocks: SourceSpan[]): boolean {
	return displayBlocks.some((block) => rawOffset > block.start && rawOffset < block.end);
}

type LatexCommandOccurrence = {
	value: string;
	start: number;
	end: number;
};

function labelOccurrences(source: string): LatexCommandOccurrence[] {
	return [...source.matchAll(/(?<!\\)\\label[ \t]*\{([^{}\r\n]+)\}/g)].map((match) => ({
		value: match[1],
		start: match.index,
		end: match.index + match[0].length,
	}));
}

function numberedTagOccurrences(source: string): LatexCommandOccurrence[] {
	return [...source.matchAll(/(?<!\\)\\tag[ \t]*\{[ \t]*([1-9][0-9]*[a-z]*)[ \t]*\}/g)].map((match) => ({
		value: match[1],
		start: match.index,
		end: match.index + match[0].length,
	}));
}

function validNumberedTagValue(value: string): boolean {
	const match = /^([1-9][0-9]*)([a-z]*)$/.exec(value);
	if (!match) return false;

	const numericPrefix = Number(match[1]);
	return (
		Number.isSafeInteger(numericPrefix) &&
		numericPrefix >= 1 &&
		numericPrefix <= MAX_NUMBERED_TAG
	);
}

type FixedDisplayDescriptor = {
	displayId: string;
	index: number;
	block: SourceSpan;
	bytes: number;
	equationLabels: string[];
	numberedTags: number[];
};

function fixedDisplayDescriptors(displayBlocks: SourceSpan[]): FixedDisplayDescriptor[] {
	const digestOccurrences = new Map<string, number>();
	return displayBlocks.map((block, index) => {
		const digest = createHash("sha256").update(block.text, "utf8").digest("hex");
		const occurrence = (digestOccurrences.get(digest) ?? 0) + 1;
		digestOccurrences.set(digest, occurrence);
		return {
			displayId: `display-sha256-${digest}-occurrence-${occurrence}`,
			index: index + 1,
			block,
			bytes: Buffer.byteLength(block.text, "utf8"),
			equationLabels: labelOccurrences(block.text).map((item) => item.value),
			numberedTags: numberedTagOccurrences(block.text)
				.filter((item) => /^[1-9][0-9]*$/.test(item.value))
				.map((item) => Number(item.value)),
		};
	});
}

function displayDescriptorForId(
	displayId: string,
	operationId: string,
	displayBlocks: SourceSpan[],
): FixedDisplayDescriptor {
	if (!SAFE_DISPLAY_ID.test(displayId)) {
		throw blocked(
			`displayId for ${JSON.stringify(operationId)} is malformed.`,
			"Use one exact stable ID returned by inventory/displays without modification.",
		);
	}
	const matches = fixedDisplayDescriptors(displayBlocks).filter(
		(descriptor) => descriptor.displayId === displayId,
	);
	if (matches.length === 0) {
		throw blocked(
			`displayId ${JSON.stringify(displayId)} for ${JSON.stringify(operationId)} is unknown in the current ${DOMAIN.baseLabel}.`,
			"Inventory displays again and use an ID from the current parsed fixed base.",
		);
	}
	if (matches.length !== 1) {
		throw blocked(
			`displayId ${JSON.stringify(displayId)} for ${JSON.stringify(operationId)} is ambiguous in the current ${DOMAIN.baseLabel}.`,
			"Repair the base display inventory before retrying.",
		);
	}
	return matches[0];
}

function displayBlockForOccurrence(
	occurrence: LatexCommandOccurrence,
	displayBlocks: SourceSpan[],
): SourceSpan | undefined {
	return displayBlocks.find(
		(block) => occurrence.start >= block.start && occurrence.end <= block.end,
	);
}

function validateEquationBlockAnchor(anchor: unknown, insertionId: string): EquationBlockAnchor {
	if (typeof anchor !== "object" || anchor === null || Array.isArray(anchor)) {
		throw blocked(
			`insertion ${JSON.stringify(insertionId)} has an invalid anchor.`,
			"Use bounded non-empty exact base text or an equation anchor with exactly one equationLabel or numberedTag.",
		);
	}
	const record = anchor as Record<string, unknown>;
	const keys = Object.keys(record);
	if (
		keys.length !== 1 ||
		(keys[0] !== "equationLabel" && keys[0] !== "numberedTag")
	) {
		throw blocked(
			`equation anchor for insertion ${JSON.stringify(insertionId)} is ambiguous or contains unknown fields.`,
			"Provide exactly one equationLabel or numberedTag selector.",
		);
	}
	if (
		keys[0] === "equationLabel" &&
		(typeof record.equationLabel !== "string" || !SAFE_EQUATION_LABEL.test(record.equationLabel))
	) {
		throw blocked(
			`equation anchor for insertion ${JSON.stringify(insertionId)} has an invalid equation label.`,
			`Use the exact bounded LaTeX label from the ${DOMAIN.baseLabel}, such as eq:ksc.`,
		);
	}
	if (
		keys[0] === "numberedTag" &&
		(typeof record.numberedTag !== "number" ||
			!Number.isSafeInteger(record.numberedTag) ||
			record.numberedTag < 1 ||
			record.numberedTag > MAX_NUMBERED_TAG)
	) {
		throw blocked(
			`equation anchor for insertion ${JSON.stringify(insertionId)} has an invalid numbered tag selector.`,
			`Use an integer between 1 and ${MAX_NUMBERED_TAG}.`,
		);
	}
	return record as EquationBlockAnchor;
}

function equationBlockForAnchor(
	anchor: EquationBlockAnchor,
	operationId: string,
	source: string,
	displayBlocks: SourceSpan[],
): SourceSpan {
	const isLabel = anchor.equationLabel !== undefined;
	const selector = isLabel ? anchor.equationLabel : String(anchor.numberedTag);
	const matches = (isLabel ? labelOccurrences(source) : numberedTagOccurrences(source)).filter(
		(occurrence) => occurrence.value === selector,
	);
	const selectorKind = isLabel ? "equation label" : "numbered tag";
	if (matches.length === 0) {
		throw blocked(
			`${selectorKind} ${JSON.stringify(selector)} for ${JSON.stringify(operationId)} is unknown in the ${DOMAIN.baseLabel}.`,
			"Use a unique label or numbered tag parsed from that base only.",
		);
	}
	if (matches.length > 1) {
		throw blocked(
			`${selectorKind} ${JSON.stringify(selector)} for ${JSON.stringify(operationId)} is duplicate or ambiguous in the ${DOMAIN.baseLabel}.`,
			"Repair the base so the selector identifies exactly one display equation.",
		);
	}
	const displayBlock = displayBlockForOccurrence(matches[0], displayBlocks);
	if (!displayBlock) {
		throw blocked(
			`${selectorKind} ${JSON.stringify(selector)} for ${JSON.stringify(operationId)} is not within display math in the ${DOMAIN.baseLabel}.`,
			"Use a label or numbered tag contained by one complete parsed base display block.",
		);
	}
	return displayBlock;
}

function exactDisplayBlockForAuthorization(
	selector: string,
	replacementId: string,
	source: string,
	displayBlocks: SourceSpan[],
): SourceSpan {
	const matches = displayBlocks.filter((block) => block.text === selector);
	if (matches.length > 1) {
		throw blocked(
			`displayBlock authorization for replacement ${JSON.stringify(replacementId)} is duplicate or ambiguous in the ${DOMAIN.baseLabel}.`,
			"Use the exact complete bytes of a display block that occurs once in that base.",
		);
	}
	if (matches.length === 1) return matches[0];

	let foundInSource = false;
	let overlapsDisplay = false;
	let start = source.indexOf(selector);
	while (start !== -1) {
		foundInSource = true;
		const end = start + selector.length;
		if (displayBlocks.some((block) => block.end > start && block.start < end)) {
			overlapsDisplay = true;
			break;
		}
		start = source.indexOf(selector, start + 1);
	}
	if (overlapsDisplay) {
		throw blocked(
			`displayBlock authorization for replacement ${JSON.stringify(replacementId)} overlaps a fixed-base display block but is not its exact complete parsed block.`,
			"Copy the full base block from its opening standalone $$ line through its closing standalone $$ line, including exact whitespace and line endings.",
		);
	}
	if (foundInSource) {
		throw blocked(
			`displayBlock authorization for replacement ${JSON.stringify(replacementId)} selects non-display text in the ${DOMAIN.baseLabel}.`,
			"Use only the exact complete bytes of one parsed $$...$$ display block.",
		);
	}
	throw blocked(
		`displayBlock authorization for replacement ${JSON.stringify(replacementId)} is missing from the ${DOMAIN.baseLabel}.`,
		"Copy the exact complete parsed base display block and retry.",
	);
}

function validateDisplayBlockAuthorization(
	raw: unknown,
	replacementId: string,
	authorizationIndex: number,
): DisplayBlockAuthorization {
	if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
		throw blocked(
			`display authorization ${authorizationIndex} for replacement ${JSON.stringify(replacementId)} is invalid.`,
			"Provide exactly one equationLabel, numberedTag, displayBlock, or displayId selector.",
		);
	}
	const record = raw as Record<string, unknown>;
	const keys = Object.keys(record);
	if (
		keys.length !== 1 ||
		(keys[0] !== "equationLabel" &&
			keys[0] !== "numberedTag" &&
			keys[0] !== "displayBlock" &&
			keys[0] !== "displayId")
	) {
		throw blocked(
			`display authorization ${authorizationIndex} for replacement ${JSON.stringify(replacementId)} is ambiguous or contains unknown fields.`,
			"Provide exactly one equationLabel, numberedTag, displayBlock, or displayId selector.",
		);
	}
	if (keys[0] === "displayId") {
		if (typeof record.displayId !== "string" || !SAFE_DISPLAY_ID.test(record.displayId)) {
			throw blocked(
				`displayId authorization for replacement ${JSON.stringify(replacementId)} is invalid.`,
				"Use one exact stable ID returned by inventory/displays without modification.",
			);
		}
		return record as DisplayBlockAuthorization;
	}
	if (keys[0] === "displayBlock") {
		if (
			typeof record.displayBlock !== "string" ||
			record.displayBlock.length === 0 ||
			record.displayBlock.includes("\0") ||
			Buffer.byteLength(record.displayBlock, "utf8") > MAX_DERIVE_REPLACEMENT_BYTES
		) {
			throw blocked(
				`displayBlock authorization for replacement ${JSON.stringify(replacementId)} is invalid.`,
				`Copy one bounded, non-empty complete display block from the ${DOMAIN.baseLabel}.`,
			);
		}
		return record as DisplayBlockAuthorization;
	}
	validateEquationBlockAnchor(record, `${replacementId}-authorization-${authorizationIndex}`);
	return record as DisplayBlockAuthorization;
}

function displayBlockForAuthorization(
	authorization: DisplayBlockAuthorization,
	replacementId: string,
	source: string,
	displayBlocks: SourceSpan[],
): SourceSpan {
	if (authorization.displayId !== undefined) {
		return displayDescriptorForId(
			authorization.displayId,
			`replacement ${replacementId}`,
			displayBlocks,
		).block;
	}
	if (authorization.displayBlock !== undefined) {
		return exactDisplayBlockForAuthorization(
			authorization.displayBlock,
			replacementId,
			source,
			displayBlocks,
		);
	}
	return equationBlockForAnchor(
		authorization as EquationBlockAnchor,
		`replacement ${replacementId}`,
		source,
		displayBlocks,
	);
}

function equationBlockEndOffset(
	anchor: EquationBlockAnchor,
	insertionId: string,
	source: string,
	displayBlocks: SourceSpan[],
): number {
	return equationBlockForAnchor(anchor, `insertion ${insertionId}`, source, displayBlocks).end;
}

function validateDeriveSlug(slug: string | undefined): string {
	const safeSlug = validateSlug(slug);
	if (!SAFE_DERIVE_SLUG.test(safeSlug)) {
		throw blocked(
			`derive and derive_revision require a revision slug ending in -${DOMAIN.artifact.revisionPattern}NN with at least two digits.`,
			`Use a new slug such as ${DOMAIN.exampleSlug}.`,
		);
	}
	return safeSlug;
}

function validateSuccessorSlug(slug: string | undefined): string {
	const safeSlug = validateSlug(slug);
	if (SAFE_ROOT_REVISION_SLUG.test(safeSlug) || SAFE_DERIVE_SLUG.test(safeSlug)) return safeSlug;
	return validateDeriveSlug(slug);
}

type ValidatedDeriveInsertion =
	| { id: string; content: string; position: "end" }
	| { id: string; content: string; position: "before" | "after"; rawOffset: number };

function validateDeriveInsertions(
	raw: unknown,
	source: string,
	displayBlocks: SourceSpan[],
): ValidatedDeriveInsertion[] {
	if (!Array.isArray(raw) || raw.length === 0 || raw.length > MAX_DERIVE_INSERTIONS) {
		throw blocked(
			`derive requires between 1 and ${MAX_DERIVE_INSERTIONS} ordered additive insertions.`,
			"Provide a bounded non-empty insertion list.",
		);
	}
	const ids = new Set<string>();
	let totalContentBytes = 0;
	let hasEndInsertion = false;
	return raw.map((candidate, index) => {
		if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) {
			throw blocked(
				`insertion ${index + 1} is invalid.`,
				"Provide an insertion object with id, position, content, and an anchor unless position is end.",
			);
		}
		const record = candidate as Record<string, unknown>;
		const keys = Object.keys(record);
		const hasOnlyInsertionKeys = keys.every((key) =>
			key === "id" || key === "anchor" || key === "position" || key === "content"
		);
		if (
			!hasOnlyInsertionKeys ||
			!keys.includes("id") ||
			!keys.includes("position") ||
			!keys.includes("content")
		) {
			throw blocked(
				`insertion ${index + 1} contains missing or unknown fields.`,
				"Use only id, position, content, and anchor; anchor may be exact base text or one equationLabel/numberedTag selector.",
			);
		}
		const { id, anchor, position, content } = record;
		if (typeof id !== "string" || id.length > 64 || !SAFE_INSERTION_ID.test(id)) {
			throw blocked(
				`insertion ${index + 1} has an invalid id.`,
				"Use a unique lowercase-hyphen identifier of at most 64 characters.",
			);
		}
		if (ids.has(id)) {
			throw blocked(`duplicate insertion id ${JSON.stringify(id)}.`, "Give every additive insertion a unique id.");
		}
		ids.add(id);
		if (position !== "before" && position !== "after" && position !== "end") {
			throw blocked(
				`insertion ${JSON.stringify(id)} has an invalid position.`,
				"Use exactly before, after, or end.",
			);
		}
		if (position === "end") {
			if (keys.includes("anchor")) {
				throw blocked(
					`end insertion ${JSON.stringify(id)} must not include an anchor.`,
					"Omit anchor when position is end.",
				);
			}
			if (hasEndInsertion) {
				throw blocked(
					"derive accepts at most one end insertion.",
					"Combine the final pending material into one bounded end insertion.",
				);
			}
			hasEndInsertion = true;
		} else if (typeof anchor === "string") {
			if (
				anchor.length === 0 ||
				anchor.includes("\0") ||
				Buffer.byteLength(anchor, "utf8") > MAX_DERIVE_ANCHOR_BYTES
			) {
				throw blocked(
					`insertion ${JSON.stringify(id)} has an invalid anchor.`,
					"Use bounded non-empty exact text copied from the fixed base.",
				);
			}
		} else {
			validateEquationBlockAnchor(anchor, id);
		}
		if (
			typeof content !== "string" ||
			content.trim().length === 0 ||
			content.includes("\0") ||
			content.includes("proposal-workspace:") ||
			Buffer.byteLength(content, "utf8") > MAX_DERIVE_INSERTION_BYTES
		) {
			throw blocked(
				`insertion ${JSON.stringify(id)} has invalid content.`,
				"Provide bounded non-blank Markdown without NUL bytes or reserved proposal-workspace markers.",
			);
		}
		totalContentBytes += Buffer.byteLength(content, "utf8");
		if (totalContentBytes > MAX_DERIVE_INSERTION_BYTES) {
			throw blocked(
				`derive insertion content exceeds the ${MAX_DERIVE_INSERTION_BYTES}-byte aggregate limit.`,
				"Reduce the additive insertion set.",
			);
		}
		if (position === "end") return { id, content, position };

		if (typeof anchor !== "string") {
			if (position !== "after") {
				throw blocked(
					`equation anchor for insertion ${JSON.stringify(id)} only supports position after.`,
					"Use position after; equation anchors always resolve to the end of the complete base display block.",
				);
			}
			const equationAnchor = validateEquationBlockAnchor(anchor, id);
			return {
				id,
				content,
				position,
				rawOffset: equationBlockEndOffset(equationAnchor, id, source, displayBlocks),
			};
		}

		const first = source.indexOf(anchor);
		const second = first === -1 ? -1 : source.indexOf(anchor, first + 1);
		if (first === -1) {
			throw blocked(
				`anchor for insertion ${JSON.stringify(id)} is missing from the fixed base.`,
				"Copy an exact base text or section marker and retry.",
			);
		}
		if (second !== -1) {
			throw blocked(
				`anchor for insertion ${JSON.stringify(id)} is not unique in the fixed base.`,
				"Use a longer exact anchor that occurs once.",
			);
		}
		const rawOffset = position === "before" ? first : first + anchor.length;
		if (boundaryInsideDisplayBlock(rawOffset, displayBlocks)) {
			throw blocked(
				`insertion ${JSON.stringify(id)} would split a base display-math block.`,
				"Anchor before or after the complete display block.",
			);
		}
		return { id, content, position, rawOffset };
	});
}

type ValidatedRevisionMutation = {
	kind: "replacement" | "section-removal";
	id: string;
	sectionId?: string;
	start: number;
	end: number;
	newText: string;
	preservedBlocks: Array<{ baseIndex: number; relativeStart: number }>;
	copiedInheritedBlocks: Array<{ relativeStart: number; candidateBaseIndexes: number[] }>;
	targetDisplayCount: number;
	selectedBaseIndexes: number[];
	authorizedBaseIndexes: number[];
};

function completeMarkdownBlockSpan(source: string, start: number, end: number): boolean {
	const selected = source.slice(start, end);
	const before = source.slice(0, start);
	const after = source.slice(end);
	const startsAtBoundary = start === 0 || before.endsWith("\n\n") || before.endsWith("\r\n\r\n");
	const endsAtBoundary =
		end === source.length ||
		(selected.endsWith("\n") && after.startsWith("\n")) ||
		(selected.endsWith("\r\n") && after.startsWith("\r\n")) ||
		(!selected.endsWith("\n") && (after.startsWith("\n\n") || after.startsWith("\r\n\r\n")));
	return startsAtBoundary && endsAtBoundary;
}

function hasMarkdownBlockSeparation(left: string, right: string): boolean {
	if (left.length === 0 || right.length === 0) return true;
	return /(?:\r?\n){2}/.test(`${left.slice(-4)}${right.slice(0, 4)}`);
}

function markdownBoundaryLineBreaks(left: string, right: string): number {
	const trailing = left.match(/(?:\r?\n)+$/)?.[0].match(/\n/g)?.length ?? 0;
	const leading = right.match(/^(?:\r?\n)+/)?.[0].match(/\n/g)?.length ?? 0;
	return trailing + leading;
}

function preservesExistingMarkdownBoundaryOnRight(
	left: string,
	oldRight: string,
	newRight: string,
): boolean {
	const existingBreaks = markdownBoundaryLineBreaks(left, oldRight);
	return existingBreaks > 0 && markdownBoundaryLineBreaks(left, newRight) >= existingBreaks;
}

function preservesExistingMarkdownBoundaryOnLeft(
	oldLeft: string,
	newLeft: string,
	right: string,
): boolean {
	const existingBreaks = markdownBoundaryLineBreaks(oldLeft, right);
	return existingBreaks > 0 && markdownBoundaryLineBreaks(newLeft, right) >= existingBreaks;
}

function validateReplacementBlockBoundaries(
	source: string,
	start: number,
	end: number,
	newText: string,
	replacementId: string,
): void {
	const before = source.slice(0, start);
	const after = source.slice(end);
	if (newText.length === 0) {
		if (!hasMarkdownBlockSeparation(before, after)) {
			throw candidateRejected(
				"derive_revision",
				"markdown-block-boundary",
				`replacement ${JSON.stringify(replacementId)} removal fuses adjacent Markdown blocks`,
				"Select the complete block including safe surrounding separation, without consuming inherited headings.",
				{ replacementId, boundary: "removal-join" },
			);
		}
		return;
	}
	if (!hasMarkdownBlockSeparation(before, newText)) {
		throw candidateRejected(
			"derive_revision",
			"markdown-block-boundary",
			`replacement ${JSON.stringify(replacementId)} lacks block-boundary separation before newText`,
			"Start replacement bytes at a complete Markdown block boundary.",
			{ replacementId, boundary: "before-newText" },
		);
	}
	if (!hasMarkdownBlockSeparation(newText, after)) {
		throw candidateRejected(
			"derive_revision",
			"markdown-block-boundary",
			`replacement ${JSON.stringify(replacementId)} lacks block-boundary separation after newText`,
			"End replacement bytes with enough newline separation to keep the following block standalone.",
			{ replacementId, boundary: "after-newText" },
		);
	}
}

function validateDisplayCommands(source: string, displayBlocks: SourceSpan[], label: string): void {
	const delimiterCount = source.match(/\$\$/g)?.length ?? 0;
	if (delimiterCount !== displayBlocks.length * 2) {
		throw blocked(
			`${label} contains malformed or non-standalone display-math delimiters.`,
			"Use paired standalone $$ lines for every display block.",
		);
	}
	const labels = labelOccurrences(source);
	const tags = numberedTagOccurrences(source);
	const labelCommandCount = [...source.matchAll(/(?<!\\)\\label\b/g)].length;
	const tagCommandCount = [
		...source.matchAll(/(?<!\\)\\tag(?=[^A-Za-z]|$)/g),
	].length;
	if (
		labelCommandCount !== labels.length ||
		labels.some((occurrence) => !SAFE_EQUATION_LABEL.test(occurrence.value)) ||
		tagCommandCount !== tags.length ||
		tags.some((occurrence) => !validNumberedTagValue(occurrence.value))
	) {
		throw blocked(
			`${label} contains a malformed equation label or numbered tag.`,
			"Use bounded labels or positive integer numbered tags with complete braces.",
		);
	}
	for (const [kind, occurrences] of [
		["equation label", labels],
		["numbered tag", tags],
	] as const) {
		const seen = new Set<string>();
		for (const occurrence of occurrences) {
			if (!displayBlockForOccurrence(occurrence, displayBlocks)) {
				throw blocked(
					`${label} contains a ${kind} outside a complete display-math block.`,
					"Keep every equation selector inside one well-formed complete display block.",
				);
			}
			if (seen.has(occurrence.value)) {
				throw blocked(
					`${label} contains duplicate ${kind} ${JSON.stringify(occurrence.value)}.`,
					"Use unique equation labels and numbered tags in the corrected derivative.",
				);
			}
			seen.add(occurrence.value);
		}
	}
}

function validateInheritedEquationOrder(
	baseSource: string,
	baseBlocks: SourceSpan[],
	revisedSource: string,
	revisedBlocks: SourceSpan[],
	authorizedBaseIndexes: Set<number>,
): void {
	for (const [kind, baseOccurrences, revisedOccurrences] of [
		["equation labels", labelOccurrences(baseSource), labelOccurrences(revisedSource)],
		["numbered tags", numberedTagOccurrences(baseSource), numberedTagOccurrences(revisedSource)],
	] as const) {
		const inheritedOrder = new Map<string, number>();
		for (const occurrence of baseOccurrences) {
			const block = displayBlockForOccurrence(occurrence, baseBlocks);
			if (block) inheritedOrder.set(occurrence.value, baseBlocks.indexOf(block));
		}
		let previous = -1;
		for (const occurrence of revisedOccurrences) {
			if (!displayBlockForOccurrence(occurrence, revisedBlocks)) continue;
			const baseIndex = inheritedOrder.get(occurrence.value);
			if (baseIndex === undefined || authorizedBaseIndexes.has(baseIndex)) continue;
			if (baseIndex < previous) {
				throw blocked(
					`derive_revision reordered inherited ${kind}.`,
					"Keep inherited equation selectors in their fixed-base order; correct them in place only.",
				);
			}
			previous = baseIndex;
		}
	}
}

type ResolvedDisplayAuthorization = {
	authorization: DisplayBlockAuthorization;
	block: SourceSpan;
	baseIndex: number;
};

function resolveRevisionSelection(
	record: Record<string, unknown>,
	replacementId: string,
	source: string,
	displayBlocks: SourceSpan[],
): { oldText: string; start: number; end: number; authorizations: ResolvedDisplayAuthorization[] } {
	const rawAuthorizations = record.authorizedEquations === undefined ? [] : record.authorizedEquations;
	if (
		!Array.isArray(rawAuthorizations) ||
		rawAuthorizations.length > MAX_DERIVE_EQUATION_AUTHORIZATIONS
	) {
		throw blocked(
			`replacement ${JSON.stringify(replacementId)} has invalid authorizedEquations.`,
			"Use an empty array only for a wholly display-free correction, or provide one equationLabel, numberedTag, displayBlock, or displayId selector per altered display block.",
		);
	}
	const authorizations = rawAuthorizations.map((rawAuthorization, authorizationIndex) => {
		const authorization = validateDisplayBlockAuthorization(
			rawAuthorization,
			replacementId,
			authorizationIndex + 1,
		);
		const block = displayBlockForAuthorization(
			authorization,
			replacementId,
			source,
			displayBlocks,
		);
		return { authorization, block, baseIndex: displayBlocks.indexOf(block) };
	});
	const displayIdAuthorizations = authorizations.filter(
		(item) => item.authorization.displayId !== undefined,
	);
	const suppliedOldText = record.oldText;
	if (suppliedOldText === undefined) {
		if (authorizations.length !== 1 || displayIdAuthorizations.length !== 1) {
			throw blocked(
				`replacement ${JSON.stringify(replacementId)} omits oldText without one unambiguous displayId authorization.`,
				"Omit oldText only when authorizedEquations contains exactly one {displayId}; otherwise provide exact complete oldText.",
			);
		}
		const block = displayIdAuthorizations[0].block;
		return { oldText: block.text, start: block.start, end: block.end, authorizations };
	}
	if (
		typeof suppliedOldText !== "string" ||
		suppliedOldText.length === 0 ||
		suppliedOldText.includes("\0") ||
		Buffer.byteLength(suppliedOldText, "utf8") > MAX_DERIVE_REPLACEMENT_BYTES
	) {
		throw blocked(
			`replacement ${JSON.stringify(replacementId)} has invalid oldText.`,
			`Copy one bounded non-empty exact complete block from the ${DOMAIN.baseLabel}.`,
		);
	}
	if (displayIdAuthorizations.length > 0 && authorizations.length === 1) {
		const block = displayIdAuthorizations[0].block;
		if (suppliedOldText !== block.text) {
			throw blocked(
				`oldText for replacement ${JSON.stringify(replacementId)} does not exactly match the complete block resolved by displayId.`,
				"Omit oldText or use the exact canonical complete block returned by read/display; a single displayId never authorizes surrounding text.",
			);
		}
		return { oldText: suppliedOldText, start: block.start, end: block.end, authorizations };
	}
	const start = source.indexOf(suppliedOldText);
	const duplicate = start === -1 ? -1 : source.indexOf(suppliedOldText, start + 1);
	if (start === -1) {
		throw blocked(
			`oldText for replacement ${JSON.stringify(replacementId)} is missing from the ${DOMAIN.baseLabel}.`,
			"Copy the exact complete base block and retry.",
		);
	}
	if (duplicate !== -1) {
		throw blocked(
			`oldText for replacement ${JSON.stringify(replacementId)} is not unique in the ${DOMAIN.baseLabel}.`,
			"Use a larger complete block that occurs exactly once, or select one parsed display by displayId.",
		);
	}
	return {
		oldText: suppliedOldText,
		start,
		end: start + suppliedOldText.length,
		authorizations,
	};
}

function validateRevisionReplacements(
	raw: unknown,
	source: string,
	displayBlocks: SourceSpan[],
): ValidatedRevisionMutation[] {
	if (raw === undefined) return [];
	if (!Array.isArray(raw) || raw.length === 0 || raw.length > MAX_DERIVE_REPLACEMENTS) {
		throw blocked(
			`derive_revision requires between 1 and ${MAX_DERIVE_REPLACEMENTS} exact replacements.`,
			"Provide a bounded non-empty replacement list.",
		);
	}
	const ids = new Set<string>();
	let aggregateBytes = 0;
	const validated = raw.map((candidate, index): ValidatedRevisionMutation => {
		if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) {
			throw blocked(
				`replacement ${index + 1} is invalid.`,
				"Provide id, newText, optional oldText, and authorizedEquations only when a display block changes.",
			);
		}
		const record = candidate as Record<string, unknown>;
		const keys = Object.keys(record);
		if (
			!keys.every((key) =>
				key === "id" || key === "oldText" || key === "newText" || key === "authorizedEquations"
			) ||
			!keys.includes("id") ||
			!keys.includes("newText")
		) {
			throw blocked(
				`replacement ${index + 1} contains missing or unknown fields.`,
				"Use only id, optional oldText, newText, and optional authorizedEquations; oldText may be omitted only for one displayId selector.",
			);
		}
		const { id, newText } = record;
		if (typeof id !== "string" || id.length > 64 || !SAFE_INSERTION_ID.test(id)) {
			throw blocked(
				`replacement ${index + 1} has an invalid id.`,
				"Use a unique lowercase-hyphen identifier of at most 64 characters.",
			);
		}
		if (ids.has(id)) {
			throw blocked(`duplicate replacement id ${JSON.stringify(id)}.`, "Give every replacement a unique id.");
		}
		ids.add(id);
		if (
			typeof newText !== "string" ||
			newText.includes("\0") ||
			newText.includes("proposal-workspace:") ||
			(newText.length > 0 && newText.trim().length === 0) ||
			Buffer.byteLength(newText, "utf8") > MAX_DERIVE_REPLACEMENT_BYTES
		) {
			throw blocked(
				`replacement ${JSON.stringify(id)} has malformed newText.`,
				"Use valid bounded Markdown, or an empty string for an explicitly authorized removal.",
			);
		}
		const selection = resolveRevisionSelection(record, id, source, displayBlocks);
		const { oldText, start, end, authorizations } = selection;
		aggregateBytes += Buffer.byteLength(oldText, "utf8") + Buffer.byteLength(newText, "utf8");
		if (aggregateBytes > MAX_DERIVE_REPLACEMENT_BYTES) {
			throw blocked(
				`derive_revision replacement text exceeds the ${MAX_DERIVE_REPLACEMENT_BYTES}-byte aggregate limit.`,
				"Reduce the atomic correction set.",
			);
		}
		const selectsExactParsedDisplay = displayBlocks.some(
			(block) => block.start === start && block.end === end,
		);
		if (!selectsExactParsedDisplay && !completeMarkdownBlockSpan(source, start, end)) {
			throw blocked(
				`replacement ${JSON.stringify(id)} does not select complete Markdown blocks.`,
				"Select complete prose blocks separated by blank lines or one exact complete parsed display block.",
			);
		}
		const affected = displayBlocks
			.map((block, baseIndex) => ({ block, baseIndex }))
			.filter(({ block }) => block.end > start && block.start < end);
		if (affected.some(({ block }) => block.start < start || block.end > end)) {
			throw blocked(
				`replacement ${JSON.stringify(id)} intersects only part of an inherited display block.`,
				"Select the complete display block before correcting or removing it.",
			);
		}
		const replacementBlocks = displayMathBlocks(newText, false);
		validateDisplayCommands(newText, replacementBlocks, `replacement ${JSON.stringify(id)}`);
		validateReplacementBlockBoundaries(source, start, end, newText, id);
		if (
			record.authorizedEquations !== undefined &&
			authorizations.length === 0 &&
			(affected.length > 0 || replacementBlocks.length > 0)
		) {
			throw blocked(
				`replacement ${JSON.stringify(id)} uses empty authorizedEquations for display-bearing content.`,
				"Use empty authorizedEquations only when both oldText and newText are wholly display-free; every removed or changed inherited display still needs one matching source selector.",
			);
		}
		const preservedBlocks: Array<{ baseIndex: number; relativeStart: number }> = [];
		for (const { block, baseIndex } of affected) {
			const matches = replacementBlocks.filter(
				(candidateBlock) => candidateBlock.text === block.text,
			);
			if (matches.length > 1) {
				throw blocked(
					`replacement ${JSON.stringify(id)} duplicates an inherited display block.`,
					"Preserve an inherited display block once in its selected replacement or explicitly authorize its removal before one exact cross-block move.",
				);
			}
			if (matches.length === 1) {
				preservedBlocks.push({ baseIndex, relativeStart: matches[0].start });
			}
		}
		const copiedInheritedBlocks = replacementBlocks.flatMap((replacementBlock) => {
			if (
				preservedBlocks.some(
					(preserved) =>
						preserved.relativeStart === replacementBlock.start &&
						displayBlocks[preserved.baseIndex].text === replacementBlock.text,
				)
			) {
				return [];
			}
			const candidateBaseIndexes = displayBlocks
				.map((block, baseIndex) => ({ block, baseIndex }))
				.filter(({ block }) => block.text === replacementBlock.text)
				.map(({ baseIndex }) => baseIndex);
			return candidateBaseIndexes.length === 0
				? []
				: [{ relativeStart: replacementBlock.start, candidateBaseIndexes }];
		});
		const authorizedBaseIndexes: number[] = [];
		for (const { baseIndex } of authorizations) {
			if (!affected.some((item) => item.baseIndex === baseIndex)) {
				throw blocked(
					`display authorization for replacement ${JSON.stringify(id)} does not match a display block completely selected by its exact oldText.`,
					"Authorize only an altered display block contained byte-for-byte in this replacement's oldText.",
				);
			}
			if (authorizedBaseIndexes.includes(baseIndex)) {
				throw blocked(
					`replacement ${JSON.stringify(id)} has overlapping authorization selectors for the same display block.`,
					"Use exactly one numberedTag, equationLabel, displayBlock, or displayId selector for each altered display block.",
				);
			}
			authorizedBaseIndexes.push(baseIndex);
		}
		const alteredBaseIndexes = affected
			.map(({ baseIndex }) => baseIndex)
			.filter((baseIndex) => !preservedBlocks.some((preserved) => preserved.baseIndex === baseIndex));
		for (const baseIndex of alteredBaseIndexes) {
			if (!authorizedBaseIndexes.includes(baseIndex)) {
				throw blocked(
					`replacement ${JSON.stringify(id)} omits or alters an inherited display block without matching authorization.`,
					"Add its exact numberedTag, equationLabel, complete displayBlock, or inventory displayId selector to authorizedEquations.",
				);
			}
		}
		if (authorizedBaseIndexes.some((baseIndex) => !alteredBaseIndexes.includes(baseIndex))) {
			throw blocked(
				`replacement ${JSON.stringify(id)} includes an authorization for a byte-preserved display block.`,
				"Remove unused authorizations; authorize only displays that are removed or altered.",
			);
		}
		return {
			kind: "replacement",
			id,
			start,
			end,
			newText,
			preservedBlocks,
			copiedInheritedBlocks,
			targetDisplayCount: replacementBlocks.length,
			selectedBaseIndexes: affected.map(({ baseIndex }) => baseIndex),
			authorizedBaseIndexes,
		};
	});
	validated.sort((left, right) => left.start - right.start);
	for (let index = 1; index < validated.length; index += 1) {
		if (validated[index].start < validated[index - 1].end) {
			throw blocked(
				`replacements ${JSON.stringify(validated[index - 1].id)} and ${JSON.stringify(validated[index].id)} overlap.`,
				"Use disjoint exact complete-block replacements.",
			);
		}
	}
	return validated;
}

type ValidatedDisplayRelocation = {
	sourceReplacementId: string;
	destinationReplacementId: string;
	baseIndexes: number[];
};

function validateAuthorizedDisplayRelocations(
	raw: unknown,
	replacements: ValidatedRevisionMutation[],
): ValidatedDisplayRelocation[] {
	const replacementById = new Map(replacements.map((replacement) => [replacement.id, replacement]));
	const authorizationOwners = new Map<number, string>();
	for (const replacement of replacements) {
		for (const baseIndex of replacement.authorizedBaseIndexes) {
			const priorOwner = authorizationOwners.get(baseIndex);
			if (priorOwner !== undefined) {
				throw blocked(
					`replacements ${JSON.stringify(priorOwner)} and ${JSON.stringify(replacement.id)} authorize the same inherited display block.`,
					"Authorize every altered inherited display exactly once in the replacement that completely selects it.",
				);
			}
			authorizationOwners.set(baseIndex, replacement.id);
		}
	}

	const resolvedCopies = replacements.flatMap((replacement) =>
		replacement.copiedInheritedBlocks.map((copy) => {
			const authorizedCandidates = copy.candidateBaseIndexes.filter((baseIndex) =>
				authorizationOwners.has(baseIndex),
			);
			if (authorizedCandidates.length === 0) {
				throw candidateRejected(
					"derive_revision",
					"unauthorized-display-relocation",
					`replacement ${JSON.stringify(replacement.id)} copies an unselected inherited display`,
					"Declare one explicit authorizedDisplayRelocations source-to-destination group and authorize every source display exactly once.",
					{ destinationReplacementId: replacement.id },
				);
			}
			if (authorizedCandidates.length !== 1) {
				throw candidateRejected(
					"derive_revision",
					"ambiguous-display-relocation",
					`replacement ${JSON.stringify(replacement.id)} copies display bytes shared by multiple authorized source displays`,
					"Relocation requires byte content that identifies one source display unambiguously.",
					{ destinationReplacementId: replacement.id, candidateBaseIndexes: authorizedCandidates.map((index) => index + 1) },
				);
			}
			return {
				destinationReplacementId: replacement.id,
				relativeStart: copy.relativeStart,
				baseIndex: authorizedCandidates[0],
				sourceReplacementId: authorizationOwners.get(authorizedCandidates[0])!,
			};
		}),
	);

	if (raw === undefined) {
		if (resolvedCopies.length > 0) {
			throw candidateRejected(
				"derive_revision",
				"unauthorized-display-relocation",
				"copying or reordering inherited display blocks is denied without explicit authorizedDisplayRelocations",
				"Bind each complete authorized source replacement to its exact destination replacement.",
				{ copiedDisplayCount: resolvedCopies.length },
			);
		}
		return [];
	}
	if (!Array.isArray(raw) || raw.length === 0 || raw.length > MAX_DERIVE_DISPLAY_RELOCATIONS) {
		throw blocked(
			`derive_revision accepts between 1 and ${MAX_DERIVE_DISPLAY_RELOCATIONS} explicit display relocation groups.`,
			"Provide a bounded authorizedDisplayRelocations list or omit it when no inherited display moves.",
		);
	}

	const sourceIds = new Set<string>();
	const pairs = new Set<string>();
	const validated = raw.map((candidate, index): ValidatedDisplayRelocation => {
		if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) {
			throw blocked(
				`authorized display relocation ${index + 1} is invalid.`,
				"Provide exactly sourceReplacementId and destinationReplacementId.",
			);
		}
		const record = candidate as Record<string, unknown>;
		const keys = Object.keys(record);
		if (
			keys.length !== 2 ||
			!keys.includes("sourceReplacementId") ||
			!keys.includes("destinationReplacementId") ||
			typeof record.sourceReplacementId !== "string" ||
			typeof record.destinationReplacementId !== "string" ||
			!SAFE_INSERTION_ID.test(record.sourceReplacementId) ||
			!SAFE_INSERTION_ID.test(record.destinationReplacementId)
		) {
			throw blocked(
				`authorized display relocation ${index + 1} has missing, unknown, or malformed fields.`,
				"Use only valid sourceReplacementId and destinationReplacementId values from this derive_revision call.",
			);
		}
		const sourceReplacementId = record.sourceReplacementId;
		const destinationReplacementId = record.destinationReplacementId;
		if (sourceReplacementId === destinationReplacementId) {
			throw blocked(
				`authorized display relocation ${index + 1} uses the same source and destination replacement.`,
				"Relocation must bind two distinct exact replacements.",
			);
		}
		const pair = `${sourceReplacementId}\0${destinationReplacementId}`;
		if (pairs.has(pair) || sourceIds.has(sourceReplacementId)) {
			throw blocked(
				`authorized display relocation repeats source replacement ${JSON.stringify(sourceReplacementId)}.`,
				"Move each selected source group exactly once to one destination.",
			);
		}
		pairs.add(pair);
		sourceIds.add(sourceReplacementId);
		const source = replacementById.get(sourceReplacementId);
		const destination = replacementById.get(destinationReplacementId);
		if (!source || !destination) {
			throw blocked(
				`authorized display relocation ${index + 1} references an unknown replacement id.`,
				"Use ids from the replacements array in the same derive_revision call.",
			);
		}
		if (source.authorizedBaseIndexes.length === 0 || source.selectedBaseIndexes.length === 0) {
			throw blocked(
				`source replacement ${JSON.stringify(sourceReplacementId)} has no individually authorized inherited display group.`,
				"Select complete source displays and authorize each one before relocating them.",
			);
		}
		if (source.targetDisplayCount !== 0) {
			throw candidateRejected(
				"derive_revision",
				"invalid-display-relocation-source",
				`source replacement ${JSON.stringify(sourceReplacementId)} retains or introduces display math`,
				"A relocation source must remove its selected display group; preserve only display-free source prose if needed.",
				{ sourceReplacementId },
			);
		}
		if (destination.selectedBaseIndexes.length > 0) {
			throw candidateRejected(
				"derive_revision",
				"invalid-display-relocation-destination",
				`destination replacement ${JSON.stringify(destinationReplacementId)} also selects inherited displays`,
				"Use a display-free inherited destination block so source and destination scopes remain disjoint.",
				{ destinationReplacementId },
			);
		}
		const expected = [...source.authorizedBaseIndexes].sort((left, right) => left - right);
		const actual = resolvedCopies
			.filter(
				(copy) =>
					copy.sourceReplacementId === sourceReplacementId &&
					copy.destinationReplacementId === destinationReplacementId,
			)
			.sort((left, right) => left.relativeStart - right.relativeStart)
			.map((copy) => copy.baseIndex);
		if (actual.length !== expected.length || actual.some((baseIndex, position) => baseIndex !== expected[position])) {
			throw candidateRejected(
				"derive_revision",
				"display-relocation-group-coverage",
				`relocation from ${JSON.stringify(sourceReplacementId)} to ${JSON.stringify(destinationReplacementId)} duplicates, omits, or reorders selected displays`,
				"Copy every selected source display byte-identically exactly once and preserve selected display relative order within the moved group.",
				{
					sourceReplacementId,
					destinationReplacementId,
					expectedBaseIndexes: expected.map((baseIndex) => baseIndex + 1),
					actualBaseIndexes: actual.map((baseIndex) => baseIndex + 1),
				},
			);
		}
		return { sourceReplacementId, destinationReplacementId, baseIndexes: expected };
	});

	const declaredPairs = new Set(
		validated.flatMap((group) =>
			group.baseIndexes.map(
				(baseIndex) => `${group.sourceReplacementId}\0${group.destinationReplacementId}\0${baseIndex}`,
			),
		),
	);
	for (const copy of resolvedCopies) {
		if (!declaredPairs.has(`${copy.sourceReplacementId}\0${copy.destinationReplacementId}\0${copy.baseIndex}`)) {
			throw candidateRejected(
				"derive_revision",
				"unauthorized-display-relocation",
				`destination replacement ${JSON.stringify(copy.destinationReplacementId)} contains an inherited display outside its declared move group`,
				"Declare the exact source-to-destination group or remove the copied inherited display.",
				{ baseIndex: copy.baseIndex + 1, destinationReplacementId: copy.destinationReplacementId },
			);
		}
	}
	for (const destination of new Set(validated.map((group) => group.destinationReplacementId))) {
		const mutation = replacementById.get(destination)!;
		const copiedCount = resolvedCopies.filter((copy) => copy.destinationReplacementId === destination).length;
		if (mutation.targetDisplayCount !== copiedCount) {
			throw candidateRejected(
				"derive_revision",
				"unapproved-destination-display",
				`destination replacement ${JSON.stringify(destination)} contains a target-side unapproved display`,
				"Keep relocation destinations byte-exact to declared moved displays; add anything else unrelated through a separate insertion.",
				{ destinationReplacementId: destination, targetDisplayCount: mutation.targetDisplayCount, copiedDisplayCount: copiedCount },
			);
		}
	}

	const sourceOrdered = validated
		.flatMap((group) => group.baseIndexes.map((baseIndex) => ({ ...group, baseIndex })))
		.sort((left, right) => left.baseIndex - right.baseIndex)
		.map((item) => item.baseIndex);
	const outputOrdered = resolvedCopies
		.filter((copy) => declaredPairs.has(`${copy.sourceReplacementId}\0${copy.destinationReplacementId}\0${copy.baseIndex}`))
		.sort((left, right) => {
			const leftDestination = replacementById.get(left.destinationReplacementId)!;
			const rightDestination = replacementById.get(right.destinationReplacementId)!;
			return leftDestination.start - rightDestination.start || left.relativeStart - right.relativeStart;
		})
		.map((copy) => copy.baseIndex);
	if (outputOrdered.some((baseIndex, index) => baseIndex !== sourceOrdered[index])) {
		throw candidateRejected(
			"derive_revision",
			"cross-group-display-reorder",
			"authorized display relocation changes the fixed-base order across moved groups",
			"Preserve relative order within each moved group and preserve source group order across all destinations.",
			{
				expectedBaseIndexes: sourceOrdered.map((baseIndex) => baseIndex + 1),
				actualBaseIndexes: outputOrdered.map((baseIndex) => baseIndex + 1),
			},
		);
	}
	return validated;
}

function validateAuthorizedSectionRemovals(
	raw: unknown,
	source: string,
	displayBlocks: SourceSpan[],
): ValidatedRevisionMutation[] {
	if (raw === undefined) return [];
	if (
		!Array.isArray(raw) ||
		raw.length === 0 ||
		raw.length > MAX_DERIVE_SECTION_REMOVALS
	) {
		throw blocked(
			`derive_revision accepts between 1 and ${MAX_DERIVE_SECTION_REMOVALS} authorized section removals.`,
			"Inventory sections and provide a bounded non-empty authorizedSectionRemovals list.",
		);
	}
	const descriptors = fixedSectionDescriptors(source, displayBlocks);
	const selectedIds = new Set<string>();
	const selected = raw.map((candidate, index) => {
		if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) {
			throw blocked(
				`authorized section removal ${index + 1} is invalid.`,
				"Provide exactly one sectionId returned by inventory/sections.",
			);
		}
		const record = candidate as Record<string, unknown>;
		const keys = Object.keys(record);
		if (keys.length !== 1 || keys[0] !== "sectionId") {
			throw blocked(
				`authorized section removal ${index + 1} is ambiguous or contains unknown fields.`,
				"Provide exactly one sectionId selector and no model-authored approval fields.",
			);
		}
		if (typeof record.sectionId !== "string" || !SAFE_SECTION_ID.test(record.sectionId)) {
			throw blocked(
				`sectionId for authorized section removal ${index + 1} is malformed.`,
				"Use one exact stable ID returned by inventory/sections without modification.",
			);
		}
		if (selectedIds.has(record.sectionId)) {
			throw blocked(
				`authorized section removal repeats sectionId ${JSON.stringify(record.sectionId)}.`,
				"Select each whole section exactly once.",
			);
		}
		selectedIds.add(record.sectionId);
		return sectionDescriptorForId(
			record.sectionId,
			`authorized section removal ${index + 1}`,
			descriptors,
		);
	});
	selected.sort((left, right) => left.section.start - right.section.start);
	for (let index = 1; index < selected.length; index += 1) {
		if (selected[index].section.start < selected[index - 1].section.end) {
			throw blocked(
				`authorized section selectors ${JSON.stringify(selected[index - 1].sectionId)} and ${JSON.stringify(selected[index].sectionId)} overlap or are nested.`,
				"Select only disjoint whole sections; selecting both a parent and its descendant is unsafe and denied.",
			);
		}
	}
	return selected.map((descriptor) => {
		const authorizedBaseIndexes = displayBlocks
			.map((block, baseIndex) => ({ block, baseIndex }))
			.filter(
				({ block }) =>
					block.start >= descriptor.section.start && block.end <= descriptor.section.end,
			)
			.map(({ baseIndex }) => baseIndex);
		if (
			displayBlocks.some(
				(block) =>
					block.end > descriptor.section.start &&
					block.start < descriptor.section.end &&
					(block.start < descriptor.section.start || block.end > descriptor.section.end),
			)
		) {
			throw blocked(
				`section ${JSON.stringify(descriptor.sectionId)} intersects only part of an inherited display block.`,
				"Repair the fixed-base Markdown structure before authorizing a whole-section removal.",
			);
		}
		return {
			kind: "section-removal" as const,
			id: `section-removal-${descriptor.index}`,
			sectionId: descriptor.sectionId,
			start: descriptor.section.start,
			end: descriptor.section.end,
			newText: "",
			preservedBlocks: [],
			copiedInheritedBlocks: [],
			targetDisplayCount: 0,
			selectedBaseIndexes: authorizedBaseIndexes,
			authorizedBaseIndexes,
		};
	});
}

function mergeRevisionMutations(
	replacements: ValidatedRevisionMutation[],
	sectionRemovals: ValidatedRevisionMutation[],
): ValidatedRevisionMutation[] {
	const mutations = [...replacements, ...sectionRemovals].sort(
		(left, right) => left.start - right.start,
	);
	for (let index = 1; index < mutations.length; index += 1) {
		if (mutations[index].start < mutations[index - 1].end) {
			throw blocked(
				`derive_revision mutations ${JSON.stringify(mutations[index - 1].id)} and ${JSON.stringify(mutations[index].id)} overlap or are nested.`,
				"Keep exact replacements outside authorized whole-section removals and select only disjoint sections.",
			);
		}
	}
	return mutations;
}

function buildRevisedSource(
	source: string,
	displayBlocks: SourceSpan[],
	replacements: ValidatedRevisionMutation[],
): { source: string; authorizedEquationCount: number; inheritedDisplayBlocksPreserved: number } {
	let cursor = 0;
	let revisedSource = "";
	for (const replacement of replacements) {
		revisedSource += source.slice(cursor, replacement.start);
		revisedSource += replacement.newText;
		cursor = replacement.end;
	}
	revisedSource += source.slice(cursor);
	const revisedBlocks = displayMathBlocks(revisedSource, false);
	validateDisplayCommands(revisedSource, revisedBlocks, "derive_revision output");
	const authorizedBaseIndexes = new Set(
		replacements.flatMap((replacement) => replacement.authorizedBaseIndexes),
	);
	validateInheritedEquationOrder(
		source,
		displayBlocks,
		revisedSource,
		revisedBlocks,
		authorizedBaseIndexes,
	);

	const mappedPreserved: Array<{ baseIndex: number; outputStart: number }> = [];
	for (const [baseIndex, block] of displayBlocks.entries()) {
		const containingReplacement = replacements.find(
			(replacement) => block.start >= replacement.start && block.end <= replacement.end,
		);
		if (containingReplacement) {
			const preserved = containingReplacement.preservedBlocks.find((item) => item.baseIndex === baseIndex);
			if (preserved) {
				const outputStart =
					containingReplacement.start +
					replacements
						.filter((replacement) => replacement.end <= containingReplacement.start)
						.reduce((delta, replacement) => delta + replacement.newText.length - (replacement.end - replacement.start), 0) +
					preserved.relativeStart;
				mappedPreserved.push({ baseIndex, outputStart });
			}
			continue;
		}
		const outputStart =
			block.start +
			replacements
				.filter((replacement) => replacement.end <= block.start)
				.reduce((delta, replacement) => delta + replacement.newText.length - (replacement.end - replacement.start), 0);
		mappedPreserved.push({ baseIndex, outputStart });
	}
	let previousOutputStart = -1;
	for (const mapping of mappedPreserved.sort((left, right) => left.baseIndex - right.baseIndex)) {
		const block = displayBlocks[mapping.baseIndex];
		if (
			mapping.outputStart <= previousOutputStart ||
			revisedSource.slice(mapping.outputStart, mapping.outputStart + block.text.length) !== block.text ||
			!revisedBlocks.some(
				(revisedBlock) => revisedBlock.start === mapping.outputStart && revisedBlock.text === block.text,
			)
		) {
			throw blocked(
				"derive_revision output does not preserve authorized display coverage and source order.",
				"Keep every non-authorized inherited display block byte-for-byte and in fixed-base order.",
			);
		}
		previousOutputStart = mapping.outputStart;
	}
	const authorizedEquationCount = replacements.reduce(
		(total, replacement) => total + replacement.authorizedBaseIndexes.length,
		0,
	);
	if (mappedPreserved.length + authorizedEquationCount !== displayBlocks.length) {
		throw blocked(
			"derive_revision output has incomplete inherited display coverage.",
			"Preserve each base display byte-for-byte or authorize exactly one in-place alteration.",
		);
	}
	return {
		source: revisedSource,
		authorizedEquationCount,
		inheritedDisplayBlocksPreserved: mappedPreserved.length,
	};
}

type CandidateValidationSuccess = {
	status: "passed";
	phase: "pre-publish";
	operation: CandidateOperation;
	bytesValidated: number;
	inheritedHeadingsPreserved: number;
	authorizedRelocatedDisplayCount: number;
	relocationGroups: Array<{
		sourceReplacementId: string;
		destinationReplacementId: string;
		baseIndexes: number[];
	}>;
	flatDomainDefinitionsChecked: number;
	wroteTargetBeforeValidation: false;
};

function countByText(items: SourceSpan[]): Map<string, number> {
	const counts = new Map<string, number>();
	for (const item of items) counts.set(item.text, (counts.get(item.text) ?? 0) + 1);
	return counts;
}

/**
 * The line with every inline code span replaced by placeholder bytes, so the ATX check below
 * never reads a backtick span such as `## Results` as a heading fused with prose. CommonMark
 * code spans: a backtick run of length n opens a span that the next run of EXACTLY n closes;
 * an unclosed run is literal text, and a backslash outside a span makes the next character
 * literal. Spans are matched within one line only, so a span that crosses a line ending stays
 * unmasked and keeps failing closed. The placeholder is never `#` and never whitespace: a
 * masked span must not turn a fused line into a standalone heading (`` `a`## x `` stays fused).
 */
function maskInlineCodeSpans(line: string): string {
	let masked = "";
	let index = 0;
	while (index < line.length) {
		const character = line[index];
		if (character === "\\" && index + 1 < line.length) {
			masked += line.slice(index, index + 2);
			index += 2;
			continue;
		}
		if (character !== "`") {
			masked += character;
			index += 1;
			continue;
		}
		let runEnd = index;
		while (runEnd < line.length && line[runEnd] === "`") runEnd += 1;
		const length = runEnd - index;
		let closing = -1;
		let cursor = runEnd;
		while (cursor < line.length) {
			if (line[cursor] !== "`") {
				cursor += 1;
				continue;
			}
			let closingEnd = cursor;
			while (closingEnd < line.length && line[closingEnd] === "`") closingEnd += 1;
			if (closingEnd - cursor === length) {
				closing = cursor;
				break;
			}
			cursor = closingEnd;
		}
		if (closing === -1) {
			masked += line.slice(index, runEnd);
			index = runEnd;
			continue;
		}
		masked += "x".repeat(closing + length - index);
		index = closing + length;
	}
	return masked;
}

function validateStandaloneAtxMarkers(
	operation: CandidateOperation,
	source: string,
	displayBlocks: SourceSpan[],
): void {
	let fence: { marker: "`" | "~"; length: number } | undefined;
	let cursor = 0;
	while (cursor < source.length) {
		const newline = source.indexOf("\n", cursor);
		const end = newline === -1 ? source.length : newline + 1;
		const line = source.slice(cursor, end).replace(/\r?\n$/, "");
		if (displayBlocks.some((block) => cursor >= block.start && cursor < block.end)) {
			cursor = end;
			continue;
		}
		if (fence) {
			const closing = line.match(/^ {0,3}(`+|~+)[ \t]*$/);
			if (closing && closing[1][0] === fence.marker && closing[1].length >= fence.length) {
				fence = undefined;
			}
			cursor = end;
			continue;
		}
		const opening = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
		if (opening && (opening[1][0] === "~" || !opening[2].includes("`"))) {
			fence = { marker: opening[1][0] as "`" | "~", length: opening[1].length };
			cursor = end;
			continue;
		}
		const scanned = maskInlineCodeSpans(line);
		const standalone = /^ {0,3}#{1,6}(?:[ \t]+.*)?[ \t]*$/.test(scanned);
		if (!standalone && /(?:^|[^#])#{1,6}[ \t]+/.test(scanned)) {
			throw candidateRejected(
				operation,
				"atx-heading-standalone",
				"the fully composed candidate contains an ATX-like heading marker fused with other line content",
				"Put every ATX heading on a standalone line and preserve blank-line separation around composed blocks.",
				{ line: line.slice(0, 200) },
			);
		}
		cursor = end;
	}
}

function canonicalInheritedHeadingText(text: string): string {
	return normalizedSource(text, inlineReplacements(text, []));
}

function countByCanonicalHeading(items: SourceSpan[]): Map<string, number> {
	const counts = new Map<string, number>();
	for (const item of items) {
		const canonical = canonicalInheritedHeadingText(item.text);
		counts.set(canonical, (counts.get(canonical) ?? 0) + 1);
	}
	return counts;
}

function validateInheritedHeadings(
	operation: "derive" | "derive_revision",
	baseSource: string,
	baseBlocks: SourceSpan[],
	candidateBody: string,
	candidateBlocks: SourceSpan[],
	mutations: ValidatedRevisionMutation[],
): number {
	const baseHeadings = fixedSectionDescriptors(baseSource, baseBlocks).map((descriptor) => descriptor.heading);
	const removedSections = mutations.filter((mutation) => mutation.kind === "section-removal");
	const expected = baseHeadings.filter(
		(heading) =>
			!removedSections.some(
				(removal) => heading.start >= removal.start && heading.end <= removal.end,
			),
	);
	const candidateHeadings = fixedSectionDescriptors(candidateBody, candidateBlocks).map(
		(descriptor) => descriptor.heading,
	);
	const expectedCounts = countByCanonicalHeading(expected);
	const baseCounts = countByCanonicalHeading(baseHeadings);
	const candidateCounts = countByCanonicalHeading(candidateHeadings);
	for (const heading of baseCounts.keys()) {
		const expectedCount = expectedCounts.get(heading) ?? 0;
		if ((candidateCounts.get(heading) ?? 0) !== expectedCount) {
			throw candidateRejected(
				operation,
				"inherited-heading-integrity",
				"a surviving inherited ATX heading is missing, duplicated, altered beyond sanctioned inline-math normalization, moved, or fused with adjacent bytes",
				"Keep every nonremoved inherited ATX heading standalone and in fixed-base order; only automatic \\(...\\) to $...$ delimiter normalization may change its text.",
				{ heading: heading.replace(/\r?\n$/, ""), expectedCount, actualCount: candidateCounts.get(heading) ?? 0 },
			);
		}
	}
	const expectedOrder = expected.map((heading) => canonicalInheritedHeadingText(heading.text));
	const inheritedHeadingTexts = new Set(expectedOrder);
	const actualOrder = candidateHeadings
		.map((heading) => canonicalInheritedHeadingText(heading.text))
		.filter((heading) => inheritedHeadingTexts.has(heading));
	if (
		actualOrder.length !== expectedOrder.length ||
		actualOrder.some((heading, index) => heading !== expectedOrder[index])
	) {
		throw candidateRejected(
			operation,
			"inherited-heading-integrity",
			"surviving inherited ATX headings no longer follow fixed-base order",
			"Keep inherited headings stationary; only explicit whole-section removal may omit them.",
			{ expectedHeadingCount: expectedOrder.length, actualHeadingCount: actualOrder.length },
		);
	}
	validateStandaloneAtxMarkers(operation, candidateBody, candidateBlocks);
	return expected.length;
}

const FLAT_DOMAIN_SYMBOLS = [
	{ label: "\\mathcal D^s", exponent: "s" },
	{ label: "\\mathcal D^t", exponent: "t" },
] as const;

function flatDomainSymbolPattern(exponent: string, definition = false): RegExp {
	const symbol = String.raw`\\mathcal(?:\s*\{D\}|\s+D)\s*\^\s*\{?${exponent}\}?`;
	const suffix = definition
		? String.raw`\s*(?:&\s*)?(?::=|=|\\coloneqq\b|\\equiv\b)`
		: "";
	return new RegExp(`${symbol}${suffix}`, "g");
}

function validateFlatDomainDefinitions(
	operation: CandidateOperation,
	baseBlocks: SourceSpan[],
	candidateBody: string,
	candidateBlocks: SourceSpan[],
): number {
	let checked = 0;
	const missing: string[] = [];
	for (const symbol of FLAT_DOMAIN_SYMBOLS) {
		const baseDefinitions = baseBlocks.filter((block) =>
			flatDomainSymbolPattern(symbol.exponent, true).test(block.text),
		);
		if (baseDefinitions.length === 0) continue;
		if (baseDefinitions.length !== 1) {
			throw candidateRejected(
				operation,
				"flat-domain-definition-scope",
				`the fixed-base flat-domain definition scope for ${symbol.label} is ambiguous`,
				"Keep exactly one standalone fixed-base definition display for each guarded flat-domain symbol.",
				{ symbol: symbol.label, baseDefinitionDisplayCount: baseDefinitions.length },
			);
		}
		checked += 1;
		const references = candidateBody.match(flatDomainSymbolPattern(symbol.exponent))?.length ?? 0;
		const definitions = candidateBlocks.filter((block) =>
			flatDomainSymbolPattern(symbol.exponent, true).test(block.text),
		).length;
		if (references > 0 && definitions !== 1) missing.push(symbol.label);
	}
	if (missing.length > 0) {
		throw candidateRejected(
			operation,
			"flat-domain-definition",
			"retained flat-domain references lack exactly one valid standalone replacement definition display",
			"Restore each removed flat-domain display or provide one replacement display that defines the same exact symbol with =, :=, \\coloneqq, or \\equiv.",
			{ symbols: missing },
		);
	}
	return checked;
}

function validatePrePublishCandidate(
	operation: "derive" | "derive_revision",
	baseSource: string,
	candidateBody: string,
	mutations: ValidatedRevisionMutation[] = [],
	relocations: ValidatedDisplayRelocation[] = [],
): CandidateValidationSuccess {
	const baseBlocks = displayMathBlocks(baseSource);
	const candidateBlocks = displayMathBlocks(candidateBody, false);
	validateDisplayCommands(candidateBody, candidateBlocks, `${operation} fully composed candidate`);
	const inheritedHeadingsPreserved = validateInheritedHeadings(
		operation,
		baseSource,
		baseBlocks,
		candidateBody,
		candidateBlocks,
		mutations,
	);
	const authorizedIndexes = new Set(mutations.flatMap((mutation) => mutation.authorizedBaseIndexes));
	const relocatedIndexes = new Set(relocations.flatMap((relocation) => relocation.baseIndexes));
	const expectedCounts = new Map<string, number>();
	for (const [baseIndex, block] of baseBlocks.entries()) {
		const expected = !authorizedIndexes.has(baseIndex) || relocatedIndexes.has(baseIndex) ? 1 : 0;
		expectedCounts.set(block.text, (expectedCounts.get(block.text) ?? 0) + expected);
	}
	const candidateCounts = countByText(candidateBlocks);
	for (const [blockText, expectedCount] of expectedCounts) {
		const actualCount = candidateCounts.get(blockText) ?? 0;
		if (actualCount !== expectedCount) {
			throw candidateRejected(
				operation,
				"inherited-display-coverage",
				"the fully composed candidate duplicates, omits, or relocates inherited display bytes outside explicit authorization",
				"Preserve non-moved displays exactly once and use authorizedDisplayRelocations for every selected move group.",
				{ expectedCount, actualCount, displaySha256: createHash("sha256").update(blockText).digest("hex") },
			);
		}
	}
	const flatDomainDefinitionsChecked = validateFlatDomainDefinitions(
		operation,
		baseBlocks,
		candidateBody,
		candidateBlocks,
	);
	return {
		status: "passed",
		phase: "pre-publish",
		operation,
		bytesValidated: Buffer.byteLength(`${ARTIFACT_MARKER}${candidateBody}`, "utf8"),
		inheritedHeadingsPreserved,
		authorizedRelocatedDisplayCount: relocatedIndexes.size,
		relocationGroups: relocations.map((relocation) => ({
			sourceReplacementId: relocation.sourceReplacementId,
			destinationReplacementId: relocation.destinationReplacementId,
			baseIndexes: relocation.baseIndexes.map((baseIndex) => baseIndex + 1),
		})),
		flatDomainDefinitionsChecked,
		wroteTargetBeforeValidation: false,
	};
}

type ContinuityValidationResult =
	| { status: "not-requested"; phase: "pre-publish"; wroteTargetBeforeValidation: false }
	| {
			status: "passed";
			phase: "pre-publish";
			source: { target: string; sha256: string; bytes: number };
			requiredCount: number;
			forbiddenCount: number;
			supersessionCount: number;
			assertionsChecked: number;
			wroteTargetBeforeValidation: false;
	  };

type ValidatedContinuityManifest = {
	source: { target: string; sha256: string };
	required: ContinuityBlockAssertion[];
	forbidden: ContinuityBlockAssertion[];
	supersessions: ContinuitySupersession[];
};

function continuityFailure(
	operation: CandidateOperation,
	code: string,
	message: string,
	nextStep: string,
	itemId: string,
	evidence: Record<string, unknown> = {},
): never {
	throw candidateRejected(operation, code, message, nextStep, { itemId, ...evidence });
}

/** `Number.isInteger` itself, re-declared with the type predicate its lib signature omits.
 *  Not a wrapper: the same function object is invoked, and it reads no `this`. */
const isInteger = Number.isInteger as (value: unknown) => value is number;

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: readonly string[]): boolean {
	const allowedKeys = new Set(allowed);
	return Object.keys(value).every((key) => allowedKeys.has(key));
}

function validateContinuityManifestShape(
	operation: "derive" | "derive_revision",
	manifest: ContinuityManifest,
	candidateSlug: string,
): ValidatedContinuityManifest {
	const raw = manifest as unknown;
	if (!isRecord(raw) || !hasOnlyKeys(raw, ["source", "required", "forbidden", "supersessions"])) {
		continuityFailure(
			operation,
			"continuity-manifest-shape",
			"continuityManifest must be an exact bounded object",
			"Provide only source, required, forbidden, and supersessions using the documented schema.",
			"manifest",
		);
	}
	const source = raw.source;
	if (
		!isRecord(source) ||
		!hasOnlyKeys(source, ["target", "sha256"]) ||
		typeof source.target !== "string" ||
		typeof source.sha256 !== "string" ||
		!MANAGED_REVISION_TARGET_MARKDOWN.test(source.target) ||
		!MANAGED_TARGET_MARKDOWN.test(source.target) ||
		source.target.length > MAX_NAME_LENGTH ||
		!/^[a-f0-9]{64}$/.test(source.sha256)
	) {
		continuityFailure(
			operation,
			"continuity-source-identity",
			"continuityManifest source is not an exact safe managed revision identity",
			`Use one ${artifact.stem}-<lineage>-${REVISION_PLACEHOLDER}.md filename and the lowercase SHA-256 of its complete marker-owned bytes.`,
			"source",
		);
	}
	const sourceMatch = source.target.match(MANAGED_REVISION_TARGET_MARKDOWN);
	const candidateMatch = candidateSlug.match(new RegExp(`^(${SEGMENT})-${escapedRevisionPrefix}([0-9]{2,})$`));
	if (
		!sourceMatch ||
		!candidateMatch ||
		sourceMatch[1] !== candidateMatch[1] ||
		Number(sourceMatch[2]) >= Number(candidateMatch[2])
	) {
		continuityFailure(
			operation,
			"continuity-source-identity",
			"continuityManifest source is not an earlier revision in the candidate lineage",
			`Select the exact latest marker-owned revision from the same lineage and derive a greater ${REVISION_PLACEHOLDER} target.`,
			"source",
			{ sourceTarget: source.target, candidateSlug },
		);
	}

	const arrays = {
		required: raw.required,
		forbidden: raw.forbidden,
		supersessions: raw.supersessions,
	};
	for (const [kind, value] of Object.entries(arrays)) {
		if (value !== undefined && (!Array.isArray(value) || value.length < 1)) {
			continuityFailure(
				operation,
				"continuity-manifest-shape",
				`continuityManifest ${kind} must be a non-empty array when provided`,
				"Omit an unused assertion array or provide at least one bounded entry.",
				kind,
			);
		}
	}
	const required = (Array.isArray(arrays.required) ? arrays.required : []) as unknown[];
	const forbidden = (Array.isArray(arrays.forbidden) ? arrays.forbidden : []) as unknown[];
	const supersessions = (Array.isArray(arrays.supersessions) ? arrays.supersessions : []) as unknown[];
	const entryCount = required.length + forbidden.length + supersessions.length;
	if (entryCount < 1 || entryCount > MAX_CONTINUITY_ENTRIES) {
		continuityFailure(
			operation,
			"continuity-manifest-limit",
			`continuityManifest must contain between 1 and ${MAX_CONTINUITY_ENTRIES} total assertions`,
			"Reduce the protected current-state assertion set.",
			"manifest",
			{ entryCount },
		);
	}

	const ids = new Set<string>();
	let aggregateBytes = 0;
	const validateId = (value: unknown, fallback: string): string => {
		if (typeof value !== "string" || value.length > 64 || !SAFE_INSERTION_ID.test(value)) {
			continuityFailure(
				operation,
				"continuity-manifest-shape",
				"continuity assertion id is invalid",
				"Use a unique lowercase-hyphen id of at most 64 characters.",
				fallback,
			);
		}
		if (ids.has(value)) {
			continuityFailure(
				operation,
				"continuity-manifest-shape",
				"continuity assertion ids must be unique across the complete manifest",
				"Rename the duplicate assertion id.",
				value,
			);
		}
		ids.add(value);
		return value;
	};
	const validateBlock = (value: unknown, itemId: string, field: string): string => {
		if (typeof value !== "string") {
			continuityFailure(
				operation,
				"continuity-manifest-shape",
				`continuity assertion ${field} must be exact text bytes`,
				"Provide a non-empty bounded UTF-8 string copied exactly from the protected state.",
				itemId,
			);
		}
		const bytes = Buffer.byteLength(value, "utf8");
		if (
			bytes < 1 ||
			bytes > MAX_CONTINUITY_BLOCK_BYTES ||
			value.includes("\0") ||
			value.includes(ARTIFACT_MARKER_NAMESPACE)
		) {
			continuityFailure(
				operation,
				"continuity-manifest-limit",
				`continuity assertion ${field} is empty, oversized, or contains reserved bytes`,
				`Use 1 through ${MAX_CONTINUITY_BLOCK_BYTES} UTF-8 bytes without NUL or proposal-workspace markers.`, 
				itemId,
				{ bytes },
			);
		}
		aggregateBytes += bytes;
		return value;
	};
	const validatedRequired = required.map((entry, index) => {
		if (!isRecord(entry) || !hasOnlyKeys(entry, ["id", "block"])) {
			continuityFailure(operation, "continuity-manifest-shape", "required assertion shape is invalid", "Use exactly id and block.", `required-${index + 1}`);
		}
		const id = validateId(entry.id, `required-${index + 1}`);
		return { id, block: validateBlock(entry.block, id, "block") };
	});
	const validatedForbidden = forbidden.map((entry, index) => {
		if (!isRecord(entry) || !hasOnlyKeys(entry, ["id", "block"])) {
			continuityFailure(operation, "continuity-manifest-shape", "forbidden assertion shape is invalid", "Use exactly id and block.", `forbidden-${index + 1}`);
		}
		const id = validateId(entry.id, `forbidden-${index + 1}`);
		return { id, block: validateBlock(entry.block, id, "block") };
	});
	const validatedSupersessions = supersessions.map((entry, index) => {
		if (!isRecord(entry) || !hasOnlyKeys(entry, ["id", "priorBlock", "successorBlock"])) {
			continuityFailure(operation, "continuity-manifest-shape", "supersession assertion shape is invalid", "Use exactly id, priorBlock, and successorBlock.", `supersession-${index + 1}`);
		}
		const id = validateId(entry.id, `supersession-${index + 1}`);
		const priorBlock = validateBlock(entry.priorBlock, id, "priorBlock");
		const successorBlock = validateBlock(entry.successorBlock, id, "successorBlock");
		if (priorBlock === successorBlock) {
			continuityFailure(operation, "continuity-manifest-shape", "supersession prior and successor blocks must differ", "Provide the exact distinct prior and accepted successor bytes.", id);
		}
		return { id, priorBlock, successorBlock };
	});
	if (aggregateBytes > MAX_CONTINUITY_TOTAL_BYTES) {
		continuityFailure(
			operation,
			"continuity-manifest-limit",
			`continuityManifest exact blocks exceed the ${MAX_CONTINUITY_TOTAL_BYTES}-byte aggregate limit`,
			"Reduce the protected assertion set to the smallest exact current-state blocks.",
			"manifest",
			{ aggregateBytes },
		);
	}
	return {
		source: { target: source.target, sha256: source.sha256 },
		required: validatedRequired,
		forbidden: validatedForbidden,
		supersessions: validatedSupersessions,
	};
}

function exactOccurrenceCount(source: string, block: string): number {
	let count = 0;
	let cursor = 0;
	while (cursor <= source.length - block.length) {
		const found = source.indexOf(block, cursor);
		if (found === -1) break;
		count += 1;
		cursor = found + 1;
	}
	return count;
}

async function assertContinuitySourceIsLatest(
	operation: CandidateOperation,
	projectRoot: string,
	sourceTarget: string,
): Promise<void> {
	const sourceMatch = sourceTarget.match(MANAGED_REVISION_TARGET_MARKDOWN);
	const rootSourceMatch = operation === "derive_successor"
		? sourceTarget.match(ROOT_MANAGED_REVISION_TARGET_MARKDOWN)
		: null;
	if (!sourceMatch && !rootSourceMatch) {
		continuityFailure(operation, "continuity-source-identity", "continuity source revision identity is invalid", `Use an exact marker-owned terminal ${REVISION_PLACEHOLDER} target.`, "source");
	}
	const directory = await canonicalDirectory(projectRoot, PROPOSAL_DIRECTORY);
	const entries = await readdir(directory, { withFileTypes: true });
	const newerMatchingTargets = entries
		.map((entry) => entry.name)
		.filter((name) => {
			if (rootSourceMatch) {
				const match = name.match(ROOT_MANAGED_REVISION_TARGET_MARKDOWN);
				return match && Number(match[1]) > Number(rootSourceMatch[1]);
			}
			const match = name.match(MANAGED_REVISION_TARGET_MARKDOWN);
			return match && match[1] === sourceMatch?.[1] && Number(match[2]) > Number(sourceMatch?.[2]);
		})
		.sort();
	if (newerMatchingTargets.length > MAX_INVENTORY_ENTRIES) {
		continuityFailure(
			operation,
			"continuity-source-limit",
			"the candidate lineage has too many newer matching revision targets to authorize bounded latest-source validation",
			"Reduce or archive the lineage outside this tool, then inventory it again.",
			"source",
			{ newerTargetCount: newerMatchingTargets.length },
		);
	}
	if (newerMatchingTargets.length > 0) {
		continuityFailure(
			operation,
			"continuity-source-stale",
			"continuityManifest source is not the latest matching revision target in its lineage",
			`Inventory the lineage again and bind the manifest to the greatest current terminal ${REVISION_PLACEHOLDER} target.`,
			"source",
			{ sourceTarget, newerTargets: newerMatchingTargets },
		);
	}
}

async function readContinuitySource(
	operation: CandidateOperation,
	projectRoot: string,
	target: string,
	signal?: AbortSignal,
): Promise<{ body: string; bytes: number; sha256: string }> {
	let authorized: { path: string; name: string };
	try {
		authorized = await authorizeManagedTarget(projectRoot, target);
	} catch (error) {
		continuityFailure(
			operation,
			"continuity-source-unavailable",
			"the continuity source is missing, linked, or no longer a safe managed target",
			"Inventory the lineage again and use the exact current marker-owned latest target.",
			"source",
			{ sourceTarget: target, reason: error instanceof Error ? error.message : String(error) },
		);
	}
	return withFileMutationQueue(authorized.path, async () => {
		throwIfAborted(signal);
		let handle: FileHandle;
		try {
			handle = await open(authorized.path, constants.O_RDONLY | noFollowFlag());
		} catch (error) {
			continuityFailure(operation, "continuity-source-unavailable", "the continuity source could not be opened safely", "Retry after the exact latest managed target is stable.", "source", { sourceTarget: target, reason: error instanceof Error ? error.message : String(error) });
		}
		try {
			const before = await handle.stat();
			const pathStat = await lstat(authorized.path);
			if (
				!before.isFile() ||
				!pathStat.isFile() ||
				pathStat.isSymbolicLink() ||
				before.nlink !== 1 ||
				pathStat.nlink !== 1 ||
				before.dev !== pathStat.dev ||
				before.ino !== pathStat.ino ||
				(await realpath(authorized.path)) !== authorized.path
			) {
				continuityFailure(operation, "continuity-source-unavailable", "the continuity source changed identity or is linked", "Restore a standalone in-place marker-owned latest target and retry.", "source", { sourceTarget: target });
			}
			if (before.size > MAX_WRITE_BYTES) {
				continuityFailure(operation, "continuity-source-limit", "the continuity source exceeds the managed proposal size limit", "Use a bounded marker-owned latest target.", "source", { sourceTarget: target, bytes: before.size });
			}
			const bytes = await handle.readFile();
			const after = await handle.stat();
			if (
				before.dev !== after.dev ||
				before.ino !== after.ino ||
				before.size !== after.size ||
				before.mtimeMs !== after.mtimeMs ||
				before.ctimeMs !== after.ctimeMs ||
				bytes.length !== before.size
			) {
				continuityFailure(operation, "continuity-source-stale", "the continuity source changed while it was read", "Inventory and hash the stable latest managed target again.", "source", { sourceTarget: target });
			}
			if (!bytes.subarray(0, ARTIFACT_MARKER_BUFFER.length).equals(ARTIFACT_MARKER_BUFFER)) {
				continuityFailure(operation, "continuity-source-unowned", "the continuity source lacks the exact tool-owned artifact marker", "Use only the exact latest target created by proposal_workspace.", "source", { sourceTarget: target });
			}
			const text = bytes.toString("utf8");
			const body = text.slice(ARTIFACT_MARKER.length);
			if (
				!Buffer.from(text, "utf8").equals(bytes) ||
				body.includes("\0") ||
				withoutCopiedArtifactMarkers(body).includes(ARTIFACT_MARKER_NAMESPACE)
			) {
				continuityFailure(operation, "continuity-source-unowned", "the continuity source contains invalid or reserved bytes", "Use an unchanged marker-owned latest target.", "source", { sourceTarget: target });
			}
			return {
				body,
				bytes: bytes.length,
				sha256: createHash("sha256").update(bytes).digest("hex"),
			};
		} finally {
			await handle.close();
		}
	});
}

async function validateContinuityManifest(
	operation: "derive" | "derive_revision",
	projectRoot: string,
	candidateSlug: string,
	candidateBody: string,
	manifest: ContinuityManifest | undefined,
	signal?: AbortSignal,
): Promise<ContinuityValidationResult> {
	if (manifest === undefined) {
		return { status: "not-requested", phase: "pre-publish", wroteTargetBeforeValidation: false };
	}
	const validated = validateContinuityManifestShape(operation, manifest, candidateSlug);
	await assertContinuitySourceIsLatest(operation, projectRoot, validated.source.target);
	const latest = await readContinuitySource(operation, projectRoot, validated.source.target, signal);
	if (latest.sha256 !== validated.source.sha256) {
		continuityFailure(
			operation,
			"continuity-source-stale",
			"continuityManifest SHA-256 does not match the exact current source bytes",
			"Read and hash the latest marker-owned target again, then rebuild the manifest and candidate.",
			"source",
			{ sourceTarget: validated.source.target, expectedSha256: validated.source.sha256, actualSha256: latest.sha256 },
		);
	}
	for (const item of validated.required) {
		const latestCount = exactOccurrenceCount(latest.body, item.block);
		if (latestCount !== 1) {
			continuityFailure(operation, "continuity-source-binding", "required protected block is not unique in the exact latest source", "Copy one exact uniquely occurring block from the latest managed target.", item.id, { expectedCount: 1, actualCount: latestCount, location: "latest" });
		}
	}
	for (const item of validated.forbidden) {
		const latestCount = exactOccurrenceCount(latest.body, item.block);
		if (latestCount !== 0) {
			continuityFailure(operation, "continuity-source-binding", "forbidden block is not a prior-removed state in the exact latest source", "Use forbidden only for exact blocks already absent from the latest managed target.", item.id, { expectedCount: 0, actualCount: latestCount, location: "latest" });
		}
	}
	for (const item of validated.supersessions) {
		const priorCount = exactOccurrenceCount(latest.body, item.priorBlock);
		const successorCount = exactOccurrenceCount(latest.body, item.successorBlock);
		if (priorCount !== 1 || successorCount !== 0) {
			continuityFailure(operation, "continuity-source-binding", "supersession is not bound to one exact prior block with an absent successor in the latest source", "Copy a unique prior block from the latest target and a distinct successor not already present there.", item.id, { expectedPriorCount: 1, actualPriorCount: priorCount, expectedSuccessorCount: 0, actualSuccessorCount: successorCount, location: "latest" });
		}
	}
	for (const item of validated.required) {
		const actualCount = exactOccurrenceCount(candidateBody, item.block);
		if (actualCount !== 1) {
			continuityFailure(operation, "continuity-required-block-count", "fully composed candidate omits or duplicates a protected current-state block", "Recompose the candidate so this exact protected block occurs once.", item.id, { expectedCount: 1, actualCount, location: "candidate" });
		}
	}
	for (const item of validated.forbidden) {
		const actualCount = exactOccurrenceCount(candidateBody, item.block);
		if (actualCount !== 0) {
			continuityFailure(operation, "continuity-forbidden-block-count", "fully composed candidate reintroduces a protected prior removal", "Remove every exact occurrence of this forbidden block before publication.", item.id, { expectedCount: 0, actualCount, location: "candidate" });
		}
	}
	for (const item of validated.supersessions) {
		const priorCount = exactOccurrenceCount(candidateBody, item.priorBlock);
		if (priorCount !== 0) {
			continuityFailure(operation, "continuity-supersession-prior-count", "fully composed candidate retains a superseded protected block", "Remove the exact prior block while keeping its authorized successor once.", item.id, { expectedCount: 0, actualCount: priorCount, location: "candidate", blockRole: "prior" });
		}
		const successorCount = exactOccurrenceCount(candidateBody, item.successorBlock);
		if (successorCount !== 1) {
			continuityFailure(operation, "continuity-supersession-successor-count", "fully composed candidate omits or duplicates the authorized successor block", "Recompose the candidate so the exact successor occurs once.", item.id, { expectedCount: 1, actualCount: successorCount, location: "candidate", blockRole: "successor" });
		}
	}
	return {
		status: "passed",
		phase: "pre-publish",
		source: { target: validated.source.target, sha256: latest.sha256, bytes: latest.bytes },
		requiredCount: validated.required.length,
		forbiddenCount: validated.forbidden.length,
		supersessionCount: validated.supersessions.length,
		assertionsChecked: validated.required.length + validated.forbidden.length + validated.supersessions.length,
		wroteTargetBeforeValidation: false,
	};
}

async function readFixedDeriveBase(
	projectRoot: string,
	signal?: AbortSignal,
): Promise<{ path: string; source: string }> {
	const directory = await canonicalDirectory(projectRoot, PROPOSAL_DIRECTORY);
	const path = await canonicalRegularFile(directory, FIXED_DERIVE_BASE, `${DOMAIN.baseLabelLong}`);
	return withFileMutationQueue(path, async () => {
		throwIfAborted(signal);
		const handle = await open(path, constants.O_RDONLY | noFollowFlag());
		try {
			const before = await handle.stat();
			const pathStat = await lstat(path);
			if (
				!before.isFile() ||
				!pathStat.isFile() ||
				pathStat.isSymbolicLink() ||
				before.nlink !== 1 ||
				pathStat.nlink !== 1 ||
				before.dev !== pathStat.dev ||
				before.ino !== pathStat.ino ||
				(await realpath(path)) !== path
			) {
				throw blocked(
					`the ${DOMAIN.baseLabel} changed, is linked, or is not a standalone regular file.`,
					"Restore the real selected base and retry.",
				);
			}
			if (before.size > MAX_WRITE_BYTES) {
				throw blocked(
					`the ${DOMAIN.baseLabel} exceeds the ${MAX_WRITE_BYTES}-byte derive limit.`,
					"Reduce or restore the selected base before deriving.",
				);
			}
			const bytes = await handle.readFile();
			const after = await handle.stat();
			if (
				before.dev !== after.dev ||
				before.ino !== after.ino ||
				before.size !== after.size ||
				before.mtimeMs !== after.mtimeMs ||
				before.ctimeMs !== after.ctimeMs ||
				bytes.length !== before.size
			) {
				throw blocked(
					`the ${DOMAIN.baseLabel} changed while it was being read.`,
					"Retry only after the base is stable.",
				);
			}
			const source = bytes.toString("utf8");
			if (
				!Buffer.from(source, "utf8").equals(bytes) ||
				source.includes("\0") ||
				source.includes(ARTIFACT_MARKER_NAMESPACE)
			) {
				throw blocked(
					`the ${DOMAIN.baseLabel} contains invalid UTF-8, a NUL byte, or a reserved artifact marker.`,
					"Restore the valid unmarked Markdown base.",
				);
			}
			return { path, source };
		} finally {
			await handle.close();
		}
	});
}

function fixedInventoryPage(offset: number | undefined, limit: number | undefined): { offset: number; limit: number } {
	const resolvedOffset = offset ?? 0;
	const resolvedLimit = limit ?? 16;
	if (!Number.isSafeInteger(resolvedOffset) || resolvedOffset < 0) {
		throw blocked(
			"fixed-base inventory offset is invalid.",
			"Use a non-negative integer offset returned as nextOffset by the prior page.",
		);
	}
	if (
		!Number.isSafeInteger(resolvedLimit) ||
		resolvedLimit < 1 ||
		resolvedLimit > MAX_FIXED_INVENTORY_PAGE
	) {
		throw blocked(
			"fixed-base inventory limit is invalid.",
			`Use an integer from 1 through ${MAX_FIXED_INVENTORY_PAGE}.`,
		);
	}
	return { offset: resolvedOffset, limit: resolvedLimit };
}

function publicDisplayMetadata(descriptor: FixedDisplayDescriptor): Record<string, unknown> {
	return {
		displayId: descriptor.displayId,
		index: descriptor.index,
		bytes: descriptor.bytes,
		equationLabels: descriptor.equationLabels,
		numberedTags: descriptor.numberedTags,
		read: { action: "read", resource: "display", displayId: descriptor.displayId },
	};
}

async function inventoryFixedDisplays(
	projectRoot: string,
	offset: number | undefined,
	limit: number | undefined,
	signal?: AbortSignal,
): Promise<ToolResult> {
	const page = fixedInventoryPage(offset, limit);
	const { source } = await readFixedDeriveBase(projectRoot, signal);
	const displayBlocks = displayMathBlocks(source);
	const descriptors = fixedDisplayDescriptors(displayBlocks);
	const selected = descriptors.slice(page.offset, page.offset + page.limit);
	const nextOffset = page.offset + selected.length < descriptors.length
		? page.offset + selected.length
		: undefined;
	const payload = {
		base: `${PROPOSAL_DIRECTORY}/${FIXED_DERIVE_BASE}`,
		offset: page.offset,
		limit: page.limit,
		total: descriptors.length,
		nextOffset,
		displays: selected.map(publicDisplayMetadata),
	};
	const rendered = JSON.stringify(payload, null, 2);
	if (Buffer.byteLength(rendered, "utf8") > MAX_RESULT_BYTES) {
		throw blocked(
			"the requested display inventory page exceeds the bounded result limit.",
			"Retry with a smaller limit; inventory pages never truncate display metadata.",
		);
	}
	return {
		content: [{ type: "text", text: rendered }],
		details: {
			resource: "displays",
			base: `${PROPOSAL_DIRECTORY}/${FIXED_DERIVE_BASE}`,
			offset: page.offset,
			limit: page.limit,
			count: selected.length,
			total: descriptors.length,
			nextOffset,
			truncated: nextOffset !== undefined,
		},
	};
}

function publicSectionMetadata(
	descriptor: FixedSectionDescriptor,
	source: string,
): Record<string, unknown> {
	const startByte = Buffer.byteLength(source.slice(0, descriptor.section.start), "utf8");
	const endByte = startByte + descriptor.bytes;
	return {
		sectionId: descriptor.sectionId,
		index: descriptor.index,
		headingText: descriptor.headingText,
		headingLevel: descriptor.headingLevel,
		headingBytes: Buffer.byteLength(descriptor.heading.text, "utf8"),
		startByte,
		endByte,
		bytes: descriptor.bytes,
		displayCount: descriptor.displayCount,
	};
}

async function inventoryFixedSections(
	projectRoot: string,
	offset: number | undefined,
	limit: number | undefined,
	signal?: AbortSignal,
): Promise<ToolResult> {
	const page = fixedInventoryPage(offset, limit);
	const { source } = await readFixedDeriveBase(projectRoot, signal);
	const displayBlocks = displayMathBlocks(source, false);
	const descriptors = fixedSectionDescriptors(source, displayBlocks);
	const selected = descriptors.slice(page.offset, page.offset + page.limit);
	const nextOffset = page.offset + selected.length < descriptors.length
		? page.offset + selected.length
		: undefined;
	const payload = {
		base: `${PROPOSAL_DIRECTORY}/${FIXED_DERIVE_BASE}`,
		offset: page.offset,
		limit: page.limit,
		total: descriptors.length,
		nextOffset,
		sections: selected.map((descriptor) => publicSectionMetadata(descriptor, source)),
	};
	const rendered = JSON.stringify(payload, null, 2);
	if (Buffer.byteLength(rendered, "utf8") > MAX_RESULT_BYTES) {
		throw blocked(
			"the requested section inventory page exceeds the bounded result limit.",
			"Retry with a smaller limit; inventory pages never truncate section metadata.",
		);
	}
	return {
		content: [{ type: "text", text: rendered }],
		details: {
			resource: "sections",
			base: `${PROPOSAL_DIRECTORY}/${FIXED_DERIVE_BASE}`,
			offset: page.offset,
			limit: page.limit,
			count: selected.length,
			total: descriptors.length,
			nextOffset,
			truncated: nextOffset !== undefined,
		},
	};
}

async function readFixedDisplay(
	projectRoot: string,
	displayId: string | undefined,
	signal?: AbortSignal,
): Promise<ToolResult> {
	if (typeof displayId !== "string") {
		throw blocked(
			"read/display requires a displayId.",
			"Inventory displays and pass one returned stable ID exactly.",
		);
	}
	const { source } = await readFixedDeriveBase(projectRoot, signal);
	const descriptor = displayDescriptorForId(displayId, "read/display", displayMathBlocks(source));
	if (descriptor.bytes > MAX_DERIVE_REPLACEMENT_BYTES) {
		throw blocked(
			`display ${JSON.stringify(displayId)} exceeds the ${MAX_DERIVE_REPLACEMENT_BYTES}-byte display read and replacement limit.`,
			"Reduce the fixed-base display outside this tool before selecting it.",
		);
	}
	return {
		content: [{ type: "text", text: descriptor.block.text }],
		details: {
			resource: "display",
			base: `${PROPOSAL_DIRECTORY}/${FIXED_DERIVE_BASE}`,
			...publicDisplayMetadata(descriptor),
			canonicalCompleteBlock: true,
		},
	};
}

function buildDerivedBody(
	source: string,
	insertions: DeriveInsertion[],
	operation: "derive" | "derive_revision",
	allowNoInsertions = false,
	requireAtLeastOneDisplay = true,
): {
	body: string;
	displayBlockCount: number;
	numberedEquationCount: number;
	inlineNormalizationCount: number;
} {
	const displayBlocks = displayMathBlocks(source, requireAtLeastOneDisplay);
	const replacements = inlineReplacements(source, displayBlocks);
	const normalized = normalizedSource(source, replacements);
	const validated: ValidatedDeriveInsertion[] =
		allowNoInsertions && insertions.length === 0
			? []
			: validateDeriveInsertions(insertions, source, displayBlocks);
	const anchored = validated.flatMap((insertion) =>
		insertion.position === "end"
			? []
			: [{ ...insertion, offset: normalizedOffset(insertion.rawOffset, replacements) }],
	);
	const endInsertion = validated.find((insertion) => insertion.position === "end");
	const byOffset = new Map<number, Array<(typeof anchored)[number]>>();
	for (const insertion of anchored) {
		const atOffset = byOffset.get(insertion.offset) ?? [];
		atOffset.push(insertion);
		byOffset.set(insertion.offset, atOffset);
	}
	const orderedOffsets = [...byOffset.keys()].sort((left, right) => left - right);
	for (const offset of orderedOffsets) {
		const atOffset = byOffset.get(offset) ?? [];
		const parts = [normalized.slice(0, offset), ...atOffset.map((insertion) => insertion.content), normalized.slice(offset)];
		for (let index = 1; index < parts.length; index += 1) {
			if (!hasMarkdownBlockSeparation(parts[index - 1], parts[index])) {
				throw candidateRejected(
					operation,
					"markdown-block-boundary",
					`insertion boundary at composed offset ${offset} fuses Markdown blocks`,
					"Add explicit blank-line separation around every insertion block and keep inherited headings standalone.",
					{
						insertionIds: atOffset.map((insertion) => insertion.id),
						boundaryPart: index,
					},
				);
			}
		}
	}
	if (endInsertion && !hasMarkdownBlockSeparation(normalized, endInsertion.content)) {
		throw candidateRejected(
			operation,
			"markdown-block-boundary",
			`end insertion ${JSON.stringify(endInsertion.id)} fuses with the preceding Markdown block`,
			"Begin the end insertion with explicit blank-line separation.",
			{ insertionIds: [endInsertion.id], boundaryPart: "end" },
		);
	}
	let cursor = 0;
	let body = "";
	for (const offset of orderedOffsets) {
		body += normalized.slice(cursor, offset);
		for (const insertion of byOffset.get(offset) ?? []) body += insertion.content;
		cursor = offset;
	}
	body += normalized.slice(cursor);
	if (endInsertion) body += endInsertion.content;

	const insertedLengthBefore = (offset: number) =>
		anchored
			.filter((insertion) => insertion.offset <= offset)
			.reduce((total, insertion) => total + insertion.content.length, 0);
	let previousEnd = -1;
	for (const block of displayBlocks) {
		const normalizedStart = normalizedOffset(block.start, replacements);
		const expectedStart = normalizedStart + insertedLengthBefore(normalizedStart);
		if (expectedStart < previousEnd || body.slice(expectedStart, expectedStart + block.text.length) !== block.text) {
			throw blocked(
				"derived output does not preserve complete source display-math coverage and order.",
				"Use additive anchors outside base display blocks and retry.",
			);
		}
		previousEnd = expectedStart + block.text.length;
	}
	if (Buffer.byteLength(`${ARTIFACT_MARKER}${body}`, "utf8") > MAX_WRITE_BYTES) {
		throw blocked(
			`derived output exceeds the ${MAX_WRITE_BYTES}-byte managed write limit.`,
			"Reduce the additive insertion set.",
		);
	}
	return {
		body,
		displayBlockCount: displayBlocks.length,
		numberedEquationCount: displayBlocks.filter((block) => /\\tag\{[^}\r\n]+\}/.test(block.text)).length,
		inlineNormalizationCount: replacements.length,
	};
}

async function assertNewManagedProposalTargetAvailable(
	projectRoot: string,
	slug: string,
): Promise<void> {
	const { target } = await proposalTarget(projectRoot, slug);
	if (await inspectProposalTarget(target)) {
		throw blocked(
			"derive requires a new proposal target and never replaces an existing file.",
			`Choose a new -${REVISION_PLACEHOLDER} slug; overwrite capabilities do not apply to derive.`,
		);
	}
}

function validateInitialCandidate(content: string | undefined): {
	body: string;
	candidateValidation: Record<string, unknown>;
} {
	if (typeof content !== "string" || content.trim().length === 0) {
		throw candidateRejected(
			"initial_create",
			"initial-candidate-empty",
			"the authorized initial proposal content must be non-empty",
			"Provide complete non-empty Markdown before beginning INITIAL_CREATE.",
		);
	}
	const outputBytes = Buffer.byteLength(`${ARTIFACT_MARKER}${content}`, "utf8");
	if (
		outputBytes > MAX_WRITE_BYTES ||
		content.includes("\0") ||
		content.includes(ARTIFACT_MARKER_NAMESPACE)
	) {
		throw candidateRejected(
			"initial_create",
			"initial-candidate-limit",
			"the authorized initial proposal is oversized or contains reserved bytes",
			`Keep complete initial Markdown within ${MAX_WRITE_BYTES} UTF-8 bytes and omit reserved markers.`,
			{ bytesValidated: outputBytes },
		);
	}
	let displayBlocks: SourceSpan[];
	try {
		displayBlocks = displayMathBlocks(content, false);
		validateDisplayCommands(content, displayBlocks, "initial_create fully composed candidate");
	} catch (error) {
		throw candidateRejected(
			"initial_create",
			"initial-markdown-block-safety",
			"the authorized initial proposal contains malformed display-math, labels, or tags",
			"Provide complete well-formed Markdown/display blocks before publication.",
			{ reason: error instanceof Error ? error.message : String(error) },
		);
	}
	validateStandaloneAtxMarkers("initial_create", content, displayBlocks);
	return {
		body: content,
		candidateValidation: {
			status: "passed",
			phase: "pre-publish",
			operation: "initial_create",
			bytesValidated: outputBytes,
			atxHeadingsStandalone: true,
			markdownBlockSafety: true,
			displayBlocksValidated: displayBlocks.length,
			wroteTargetBeforeValidation: false,
		},
	};
}

async function atomicCreateManagedProposal(
	projectRoot: string,
	slug: string,
	body: string,
	signal?: AbortSignal,
): Promise<{ path: string; bytesWritten: number; sha256: string }> {
	const { root, target, filename } = await proposalTarget(projectRoot, slug);
	return withFileMutationQueue(target, async () => {
		throwIfAborted(signal);
		const directory = await canonicalDirectory(root, PROPOSAL_DIRECTORY);
		if (resolve(directory, filename) !== target) {
			throw blocked(`the ${PROPOSAL_DIRECTORY} directory changed during derive authorization.`, "Repair the workspace and retry.");
		}
		if (await inspectProposalTarget(target)) {
			throw blocked(
				"derive requires a new proposal target and never replaces an existing file.",
				`Choose a new -${REVISION_PLACEHOLDER} slug; overwrite capabilities do not apply to derive.`,
			);
		}
		const output = Buffer.from(`${ARTIFACT_MARKER}${body}`, "utf8");
		const digest = createHash("sha256").update(output).digest("hex");
		const tempName = `.${filename}.derive-${randomBytes(16).toString("hex")}.tmp`;
		const temp = resolve(directory, tempName);
		if (dirname(temp) !== directory) {
			throw blocked(`the derive staging path escaped ${PROPOSAL_DIRECTORY}/.`, "Repair the workspace and retry.");
		}
		let tempExists = false;
		try {
			const handle = await open(
				temp,
				constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | noFollowFlag(),
				0o600,
			);
			tempExists = true;
			try {
				throwIfAborted(signal);
				await handle.writeFile(output);
				await handle.sync();
				const staged = await handle.stat();
				if (
					!staged.isFile() ||
					staged.nlink !== 1 ||
					staged.size !== output.length ||
					(await realpath(temp)) !== temp
				) {
					throw blocked(
						"the derived staging file changed before publication.",
						`Repair the ${PROPOSAL_DIRECTORY} directory and retry.`,
					);
				}
			} finally {
				await handle.close();
			}
			throwIfAborted(signal);
			try {
				await link(temp, target);
			} catch (error) {
				if (typeof error === "object" && error !== null && "code" in error && error.code === "EEXIST") {
					throw blocked(
						"the derived proposal target appeared before atomic publication.",
						`Inspect it and choose a new -${REVISION_PLACEHOLDER} slug.`,
					);
				}
				throw error;
			}
			await unlink(temp);
			tempExists = false;
			const identity = await inspectProposalTarget(target);
			if (!identity) {
				throw blocked(
					"atomic derive publication did not produce a target.",
					`Inspect the ${PROPOSAL_DIRECTORY} directory before retrying.`,
				);
			}
			const published = await open(target, constants.O_RDONLY | noFollowFlag());
			try {
				const publishedStat = await published.stat();
				const publishedBytes = await published.readFile();
				if (
					publishedStat.dev !== identity.dev ||
					publishedStat.ino !== identity.ino ||
					publishedStat.size !== output.length ||
					!publishedBytes.equals(output) ||
					!(await openHandleHasArtifactMarker(published))
				) {
					throw blocked(
						"the atomically published derived proposal failed marker or byte verification.",
						"Inspect the target; do not retry with the same slug.",
					);
				}
			} finally {
				await published.close();
			}
			return { path: `${PROPOSAL_DIRECTORY}/${filename}`, bytesWritten: output.length, sha256: digest };
		} finally {
			if (tempExists) await unlink(temp).catch(() => undefined);
		}
	});
}

async function createInitialProposal(
	projectRoot: string,
	slug: string | undefined,
	content: string | undefined,
	signal?: AbortSignal,
): Promise<ToolResult> {
	// The first revision's slug IS the profile's own first-revision label, never the literal
	// `"r01"`: `managedRevisionFilename('ROOT', 1)` -- what `proposal-workspace-adapter.ts`
	// checks the candidate's filename against -- is spelled `<stem>-v01.md` under a domain
	// whose revision prefix is `v`, so a hardcoded `"r01"` here refused every such candidate.
	if (slug !== FIRST_REVISION_LABEL) {
		throw candidateRejected(
			"initial_create",
			"initial-target-identity",
			`INITIAL_CREATE publishes only ${artifact.stem}-${FIRST_REVISION_LABEL}.md`,
			`Use slug ${FIRST_REVISION_LABEL} for the first managed proposal.`,
			{ slug },
		);
	}
	const validated = validateInitialCandidate(content);
	await assertNewManagedProposalTargetAvailable(projectRoot, slug);
	const written = await atomicCreateManagedProposal(
		projectRoot,
		slug,
		validated.body,
		signal,
	);
	return {
		content: [{ type: "text", text: `Created ${written.path} atomically after initial validation.` }],
		details: {
			resource: "proposal",
			operation: "initial_create",
			target: written.path,
			targetSha256: written.sha256,
			bytesWritten: written.bytesWritten,
			patchIds: [],
			patchCount: 0,
			candidateValidation: validated.candidateValidation,
		},
	};
}

type ValidatedSuccessorPatch = {
	id: string;
	kind: "replace" | "insert";
	start: number;
	end: number;
	scopeStart: number;
	scopeEnd: number;
	newText: string;
};

type UntouchedRegionEvidence = {
	verified: true;
	unchangedBytes: number;
	sourceBodyBytes: number;
	candidateBodyBytes: number;
	coverageRatio: number;
	regionCount: number;
	regions: Array<{
		sourceStartByte: number;
		sourceEndByte: number;
		candidateStartByte: number;
		candidateEndByte: number;
		sha256: string;
	}>;
};

function successorFailure(
	code: string,
	message: string,
	nextStep: string,
	evidence: Record<string, unknown> = {},
): never {
	throw candidateRejected("derive_successor", code, message, nextStep, evidence);
}

function validateSuccessorIdentity(
	source: string | undefined,
	sourceSha256: string | undefined,
	slug: string | undefined,
): { source: string; sourceSha256: string; slug: string } {
	const safeSlug = validateSuccessorSlug(slug);
	if (
		typeof source !== "string" ||
		source.length > MAX_NAME_LENGTH ||
		(!MANAGED_REVISION_TARGET_MARKDOWN.test(source) &&
			!ROOT_MANAGED_REVISION_TARGET_MARKDOWN.test(source)) ||
		!MANAGED_TARGET_MARKDOWN.test(source) ||
		isAbsolute(source)
	) {
		successorFailure(
			"successor-source-identity",
			`source must be one exact terminal-${REVISION_PLACEHOLDER} managed proposal filename`,
			`Inventory managed ${PROPOSAL_DIRECTORY} and pass the exact latest root or explicit-lineage terminal-${REVISION_PLACEHOLDER} filename.`,
		);
	}
	if (typeof sourceSha256 !== "string" || !/^[a-f0-9]{64}$/.test(sourceSha256)) {
		successorFailure(
			"successor-source-identity",
			"sourceSha256 must be the lowercase SHA-256 of the complete marker-owned source bytes",
			"Read and hash the exact latest managed proposal again.",
		);
	}
	const sourceRootMatch = source.match(ROOT_MANAGED_REVISION_TARGET_MARKDOWN);
	const targetRootMatch = safeSlug.match(SAFE_ROOT_REVISION_SLUG);
	const sourceMatch = source.match(MANAGED_REVISION_TARGET_MARKDOWN);
	const targetMatch = safeSlug.match(new RegExp(`^(${SEGMENT})-${escapedRevisionPrefix}([0-9]{2,})$`));
	const validRootTransition =
		sourceRootMatch &&
		targetRootMatch &&
		Number(targetRootMatch[1]) === Number(sourceRootMatch[1]) + 1;
	const validExplicitTransition =
		sourceMatch &&
		targetMatch &&
		sourceMatch[1] === targetMatch[1] &&
		Number(sourceMatch[2]) < Number(targetMatch[2]);
	if (!validRootTransition && !validExplicitTransition) {
		successorFailure(
			"successor-lineage-identity",
			`target slug must remain in the exact source lineage; root revisions must advance by exactly one ${REVISION_PLACEHOLDER}`,
			`For ${artifact.stem}-${FIRST_REVISION_LABEL}.md use ${SECOND_REVISION_LABEL}; otherwise keep the explicit lineage prefix unchanged and choose a greater ${REVISION_PLACEHOLDER} slug.`,
			{ source, slug: safeSlug },
		);
	}
	return { source, sourceSha256, slug: safeSlug };
}

function validateSuccessorPatchText(
	value: unknown,
	patchId: string,
	field: string,
	allowEmpty: boolean,
	allowArtifactMarkerPrefix = false,
	allowCopiedMarkerLines = false,
): string {
	if (typeof value !== "string") {
		successorFailure(
			"successor-patch-shape",
			`patch ${JSON.stringify(patchId)} ${field} must be exact text bytes`,
			"Provide only the documented patch fields with UTF-8 string values.",
			{ patchId, field },
		);
	}
	const bytes = Buffer.byteLength(value, "utf8");
	// A field that only READS the source (oldText, anchor) may span marker lines a first
	// revision copied from another managed document before 0.14.0; writing fields never may.
	const judged = allowCopiedMarkerLines ? withoutCopiedArtifactMarkers(value) : value;
	const markerOccurrences = judged.split(ARTIFACT_MARKER_NAMESPACE).length - 1;
	const hasAllowedMarkerPrefix = allowArtifactMarkerPrefix && judged.startsWith(ARTIFACT_MARKER) && markerOccurrences === 1;
	if (
		(!allowEmpty && bytes === 0) ||
		bytes > MAX_SUCCESSOR_PATCH_BYTES ||
		value.includes("\0") ||
		(judged.includes(ARTIFACT_MARKER_NAMESPACE) && !hasAllowedMarkerPrefix)
	) {
		successorFailure(
			"successor-patch-limit",
			`patch ${JSON.stringify(patchId)} ${field} is empty, oversized, or contains reserved bytes`,
			`Use ${allowEmpty ? "0" : "1"} through ${MAX_SUCCESSOR_PATCH_BYTES} UTF-8 bytes without NUL or proposal-workspace markers.`,
			{ patchId, field, bytes },
		);
	}
	return value;
}

function validateSuccessorPatches(
	raw: unknown,
	source: string,
	sourceSha256: string,
): ValidatedSuccessorPatch[] {
	if (!Array.isArray(raw) || raw.length < 1 || raw.length > MAX_SUCCESSOR_PATCHES) {
		successorFailure(
			"successor-patch-count",
			`derive_successor requires between 1 and ${MAX_SUCCESSOR_PATCHES} declared patches`,
			"Provide a bounded non-empty patch manifest.",
		);
	}
	const ids = new Set<string>();
	const sourceDisplays = displayMathBlocks(source, false);
	let aggregateBytes = 0;
	const patches = raw.map((candidate, index): ValidatedSuccessorPatch => {
		if (!isRecord(candidate)) {
			successorFailure(
				"successor-patch-shape",
				`patch ${index + 1} is not an object`,
				"Use one exact replace or insert patch object.",
			);
		}
		const id = candidate.id;
		if (typeof id !== "string" || id.length > 64 || !SAFE_INSERTION_ID.test(id)) {
			successorFailure(
				"successor-patch-shape",
				`patch ${index + 1} has an invalid id`,
				"Use a unique lowercase-hyphen id of at most 64 characters.",
			);
		}
		if (ids.has(id)) {
			successorFailure(
				"successor-patch-id",
				`duplicate patch id ${JSON.stringify(id)}`,
				"Give every declared patch a unique id.",
				{ patchId: id },
			);
		}
		ids.add(id);
		if (candidate.kind === "replace") {
			if (!hasOnlyKeys(candidate, ["id", "kind", "oldText", "newText", "selector"])) {
				successorFailure(
					"successor-patch-shape",
					`replacement patch ${JSON.stringify(id)} contains missing or unknown fields`,
					"Use exactly id, kind, oldText, and newText.",
					{ patchId: id },
				);
			}
			const oldText = validateSuccessorPatchText(candidate.oldText, id, "oldText", false, true, true);
			const oldTextIncludesMarker = oldText.startsWith(ARTIFACT_MARKER);
			const newText = validateSuccessorPatchText(candidate.newText, id, "newText", true, oldTextIncludesMarker);
			if (oldTextIncludesMarker !== newText.startsWith(ARTIFACT_MARKER)) {
				successorFailure(
					"successor-artifact-marker",
					`replacement patch ${JSON.stringify(id)} would alter the immutable artifact marker`,
					"Preserve the exact artifact marker prefix in marker-inclusive replacement bytes.",
					{ patchId: id },
				);
			}
			if (oldText === newText) {
				successorFailure(
					"successor-no-op",
					`replacement patch ${JSON.stringify(id)} does not change bytes`,
					"Remove the no-op or provide the exact authorized successor bytes.",
					{ patchId: id },
				);
			}
			const selector=candidate.selector;let structuralStart:number|undefined;let structuralEnd:number|undefined;
			if(selector!==undefined){
				if(!isRecord(selector)||typeof selector.entryId!=="string"||!isInteger(selector.startByte)||!isInteger(selector.endByte)||typeof selector.textSha256!=="string"||selector.documentSha256!==sourceSha256)successorFailure("successor-structural-selector","structural selector is invalid or stale","Rebuild the patch from the exact current source.",{patchId:id});
				const sourceBytes=Buffer.from(source,"utf8");if(selector.startByte<ARTIFACT_MARKER_BUFFER.length||selector.endByte<=selector.startByte||selector.endByte>sourceBytes.length)successorFailure("successor-structural-range","structural selector range is invalid","Use exact entry byte bounds after the immutable artifact marker.",{patchId:id});
				const range=sourceBytes.subarray(selector.startByte,selector.endByte);if(createHash("sha256").update(range).digest("hex")!==selector.textSha256||range.toString("utf8")!==oldText)successorFailure("successor-structural-hash","structural selector bytes do not match oldText","Rebuild the patch from exact entry bytes.",{patchId:id});
				structuralStart=sourceBytes.subarray(0,selector.startByte).toString("utf8").length;structuralEnd=sourceBytes.subarray(0,selector.endByte).toString("utf8").length;
			}
			const start = structuralStart??source.indexOf(oldText);
			const duplicate = selector===undefined?(start === -1 ? -1 : source.indexOf(oldText, start + 1)):-1;
			if (start === -1) {
				successorFailure(
					"successor-patch-missing",
					`oldText for patch ${JSON.stringify(id)} is missing from the exact current state`,
					"Copy the exact bytes from the latest managed source and rebuild the patch manifest.",
					{ patchId: id },
				);
			}
			if (duplicate !== -1) {
				successorFailure(
					"successor-patch-ambiguous",
					`oldText for patch ${JSON.stringify(id)} is not unique in the exact current state`,
					"Expand oldText to one exact uniquely occurring bounded span.",
					{ patchId: id },
				);
			}
			const end = structuralEnd??(start + oldText.length);
			const blockScoped =
				/(?:\r?\n){2}/.test(oldText) ||
				/(?:\r?\n){2}/.test(newText) ||
				/^ {0,3}#{1,6}[ \t]/m.test(oldText) ||
				/^ {0,3}#{1,6}[ \t]/m.test(newText) ||
				/^\$\$\r?$/m.test(oldText) ||
				/^\$\$\r?$/m.test(newText);
			if (blockScoped) {
				const before = source.slice(0, start);
				const after = source.slice(end);
				// A removal joins `before` to `after`. When `before` is exactly the artifact marker,
				// the removed span was the document's first block: the marker is an HTML comment line
				// that ends in its own single newline and that no Markdown block can fuse into, and
				// the source itself joins it to its first heading with that one newline. Any other
				// left side still needs a blank line.
				const safe = newText.length === 0
					? hasMarkdownBlockSeparation(before, after) || before === ARTIFACT_MARKER
					: (hasMarkdownBlockSeparation(before, newText) ||
						preservesExistingMarkdownBoundaryOnRight(before, oldText, newText)) &&
						(hasMarkdownBlockSeparation(newText, after) ||
							preservesExistingMarkdownBoundaryOnLeft(oldText, newText, after));
				if (!safe) {
					successorFailure(
						"successor-markdown-block-safety",
						`replacement patch ${JSON.stringify(id)} fuses Markdown blocks at its candidate boundary`,
						"Keep explicit blank-line separation around block-scoped replacement bytes.",
						{ patchId: id },
					);
				}
			}
			aggregateBytes += Buffer.byteLength(oldText, "utf8") + Buffer.byteLength(newText, "utf8");
			return {
				id,
				kind: "replace",
				start,
				end,
				scopeStart: start,
				scopeEnd: end,
				newText,
			};
		}
		if (candidate.kind === "insert") {
			if (!hasOnlyKeys(candidate, ["id", "kind", "anchor", "position", "content"])) {
				successorFailure(
					"successor-patch-shape",
					`insertion patch ${JSON.stringify(id)} contains missing or unknown fields`,
					"Use exactly id, kind, anchor, position, and content.",
					{ patchId: id },
				);
			}
			const anchor = validateSuccessorPatchText(candidate.anchor, id, "anchor", false, true, true);
			const content = validateSuccessorPatchText(candidate.content, id, "content", false);
			if (candidate.position !== "before" && candidate.position !== "after") {
				successorFailure(
					"successor-patch-shape",
					`insertion patch ${JSON.stringify(id)} has an invalid position`,
					"Use exactly before or after.",
					{ patchId: id },
				);
			}
			const anchorStart = source.indexOf(anchor);
			const duplicate = anchorStart === -1 ? -1 : source.indexOf(anchor, anchorStart + 1);
			if (anchorStart === -1) {
				successorFailure(
					"successor-patch-missing",
					`anchor for patch ${JSON.stringify(id)} is missing from the exact current state`,
					"Copy one exact current-state anchor and retry.",
					{ patchId: id },
				);
			}
			if (duplicate !== -1) {
				successorFailure(
					"successor-patch-ambiguous",
					`anchor for patch ${JSON.stringify(id)} is not unique in the exact current state`,
					"Expand the anchor to one exact uniquely occurring bounded span.",
					{ patchId: id },
				);
			}
			const anchorEnd = anchorStart + anchor.length;
			const at = candidate.position === "before" ? anchorStart : anchorEnd;
			if (boundaryInsideDisplayBlock(at, sourceDisplays)) {
				successorFailure(
					"successor-markdown-block-safety",
					`insertion patch ${JSON.stringify(id)} would split a display-math block`,
					"Anchor immediately outside the complete display block.",
					{ patchId: id },
				);
			}
			if (
				!hasMarkdownBlockSeparation(source.slice(0, at), content) ||
				!hasMarkdownBlockSeparation(content, source.slice(at))
			) {
				successorFailure(
					"successor-markdown-block-safety",
					`insertion patch ${JSON.stringify(id)} lacks Markdown block separation`,
					"Include blank-line separation before and after additive insertion bytes.",
					{ patchId: id },
				);
			}
			aggregateBytes += Buffer.byteLength(anchor, "utf8") + Buffer.byteLength(content, "utf8");
			return {
				id,
				kind: "insert",
				start: at,
				end: at,
				scopeStart: anchorStart,
				scopeEnd: anchorEnd,
				newText: content,
			};
		}
		successorFailure(
			"successor-patch-shape",
			`patch ${JSON.stringify(id)} has an unknown kind`,
			"Use exactly kind replace or insert.",
			{ patchId: id },
		);
	});
	if (aggregateBytes > MAX_SUCCESSOR_TOTAL_PATCH_BYTES) {
		successorFailure(
			"successor-patch-limit",
			`patch manifest exceeds the ${MAX_SUCCESSOR_TOTAL_PATCH_BYTES}-byte aggregate limit`,
			"Reduce the manifest to the smallest exact researcher-authorized patches.",
			{ aggregateBytes },
		);
	}
	for (let leftIndex = 0; leftIndex < patches.length; leftIndex += 1) {
		for (let rightIndex = leftIndex + 1; rightIndex < patches.length; rightIndex += 1) {
			const left = patches[leftIndex];
			const right = patches[rightIndex];
			const scopesOverlap =
				Math.max(left.scopeStart, right.scopeStart) < Math.min(left.scopeEnd, right.scopeEnd);
			const mutationsConflict =
				(left.start === right.start) ||
				(left.start < right.end && right.start < left.end) ||
				(left.start === left.end && left.start >= right.start && left.start <= right.end) ||
				(right.start === right.end && right.start >= left.start && right.start <= left.end);
			if (scopesOverlap || mutationsConflict) {
				successorFailure(
					"successor-patch-overlap",
					`patches ${JSON.stringify(left.id)} and ${JSON.stringify(right.id)} overlap or depend on the same source scope`,
					"Use disjoint exact source scopes and one declared mutation per source boundary.",
					{ patchIds: [left.id, right.id] },
				);
			}
		}
	}
	return patches.sort((left, right) => left.start - right.start || left.end - right.end);
}

function composeSuccessorCandidate(
	source: string,
	patches: ValidatedSuccessorPatch[],
): { candidate: string; invariant: UntouchedRegionEvidence } {
	let sourceCursor = 0;
	let candidate = "";
	let candidateByteCursor = 0;
	let unchangedBytes = 0;
	const regions: UntouchedRegionEvidence["regions"] = [];
	for (const patch of patches) {
		const untouched = source.slice(sourceCursor, patch.start);
		const sourceStartByte = Buffer.byteLength(source.slice(0, sourceCursor), "utf8");
		const sourceEndByte = sourceStartByte + Buffer.byteLength(untouched, "utf8");
		const candidateStartByte = candidateByteCursor;
		candidate += untouched;
		candidateByteCursor += Buffer.byteLength(untouched, "utf8");
		if (untouched.length > 0) {
			const sourceBytes = Buffer.from(untouched, "utf8");
			const candidateBytes = Buffer.from(
				candidate.slice(candidate.length - untouched.length),
				"utf8",
			);
			if (!sourceBytes.equals(candidateBytes)) {
				successorFailure(
					"successor-untouched-invariant",
					"an untouched source region changed during candidate composition",
					"Rebuild the candidate only through the declared patch manifest.",
					{ patchId: patch.id },
				);
			}
			unchangedBytes += sourceBytes.length;
			regions.push({
				sourceStartByte,
				sourceEndByte,
				candidateStartByte,
				candidateEndByte: candidateByteCursor,
				sha256: createHash("sha256").update(sourceBytes).digest("hex"),
			});
		}
		candidate += patch.newText;
		candidateByteCursor += Buffer.byteLength(patch.newText, "utf8");
		sourceCursor = patch.end;
	}
	const trailing = source.slice(sourceCursor);
	const trailingSourceStartByte = Buffer.byteLength(source.slice(0, sourceCursor), "utf8");
	const trailingCandidateStartByte = candidateByteCursor;
	candidate += trailing;
	candidateByteCursor += Buffer.byteLength(trailing, "utf8");
	if (trailing.length > 0) {
		const trailingBytes = Buffer.from(trailing, "utf8");
		unchangedBytes += trailingBytes.length;
		regions.push({
			sourceStartByte: trailingSourceStartByte,
			sourceEndByte: trailingSourceStartByte + trailingBytes.length,
			candidateStartByte: trailingCandidateStartByte,
			candidateEndByte: candidateByteCursor,
			sha256: createHash("sha256").update(trailingBytes).digest("hex"),
		});
	}
	const sourceBodyBytes = Buffer.byteLength(source, "utf8");
	const candidateBodyBytes = Buffer.byteLength(candidate, "utf8");
	if (candidate === source) {
		successorFailure(
			"successor-no-op",
			"the declared patch manifest produces no candidate byte change",
			"Provide at least one effective researcher-authorized patch.",
		);
	}
	return {
		candidate,
		invariant: {
			verified: true,
			unchangedBytes,
			sourceBodyBytes,
			candidateBodyBytes,
			coverageRatio: sourceBodyBytes === 0 ? 1 : unchangedBytes / sourceBodyBytes,
			regionCount: regions.length,
			regions,
		},
	};
}

function validateSuccessorCandidate(
	source: string,
	candidate: string,
	invariant: UntouchedRegionEvidence,
): Record<string, unknown> {
	const outputBytes = Buffer.byteLength(`${ARTIFACT_MARKER}${candidate}`, "utf8");
	if (
		outputBytes > MAX_WRITE_BYTES ||
		candidate.includes("\0") ||
		candidate.includes(ARTIFACT_MARKER_NAMESPACE)
	) {
		successorFailure(
			"successor-candidate-limit",
			"fully patched candidate is oversized or contains reserved bytes",
			`Keep the complete marker-owned candidate within ${MAX_WRITE_BYTES} UTF-8 bytes and omit reserved markers.`,
			{ bytesValidated: outputBytes },
		);
	}
	let sourceBlocks: SourceSpan[];
	let candidateBlocks: SourceSpan[];
	try {
		sourceBlocks = displayMathBlocks(source, false);
		candidateBlocks = displayMathBlocks(candidate, false);
		validateDisplayCommands(candidate, candidateBlocks, "derive_successor fully patched candidate");
	} catch (error) {
		successorFailure(
			"successor-markdown-block-safety",
			"fully patched candidate contains malformed display-math, labels, or tags",
			"Patch only complete Markdown/display blocks and keep every display command well formed.",
			{ reason: error instanceof Error ? error.message : String(error) },
		);
	}
	validateStandaloneAtxMarkers("derive_successor", candidate, candidateBlocks);
	const flatDomainDefinitionsChecked = validateFlatDomainDefinitions(
		"derive_successor",
		sourceBlocks,
		candidate,
		candidateBlocks,
	);
	return {
		status: "passed",
		phase: "pre-publish",
		operation: "derive_successor",
		bytesValidated: outputBytes,
		atxHeadingsStandalone: true,
		markdownBlockSafety: true,
		displayBlocksValidated: candidateBlocks.length,
		flatDomainDefinitionsChecked,
		untouchedRegionInvariant: invariant,
		wroteTargetBeforeValidation: false,
	};
}

/**
 * The successor's whole pre-publish validation over a patch manifest: patch shape, composition,
 * marker integrity and the fully composed candidate. `derive_successor` runs exactly this before
 * it writes, and `successorCandidateRefusal` runs exactly this for the CREATE_SUCCESSOR preview,
 * so the preview can never hand out an acceptance token the accept turn would refuse.
 */
function validateSuccessorManifest(
	latestDocument: string,
	latestSha256: string,
	patches: unknown,
): {
	validatedPatches: ValidatedSuccessorPatch[];
	composed: { candidate: string; invariant: UntouchedRegionEvidence };
	candidateBody: string;
	candidateValidation: Record<string, unknown>;
} {
	const validatedPatches = validateSuccessorPatches(patches, latestDocument, latestSha256);
	const composed = composeSuccessorCandidate(latestDocument, validatedPatches);
	refuseInheritedCopiedMarkers(composed.candidate);
	if (!composed.candidate.startsWith(ARTIFACT_MARKER) || composed.candidate.slice(ARTIFACT_MARKER.length).includes(ARTIFACT_MARKER_NAMESPACE)) {
		successorFailure(
			"successor-artifact-marker",
			"the fully patched candidate changed or duplicated the immutable artifact marker",
			"Preserve the exact single artifact marker prefix.",
		);
	}
	const candidateBody = composed.candidate.slice(ARTIFACT_MARKER.length);
	const candidateValidation = validateSuccessorCandidate(
		latestDocument.slice(ARTIFACT_MARKER.length),
		candidateBody,
		composed.invariant,
	);
	return { validatedPatches, composed, candidateBody, candidateValidation };
}

/**
 * The heading path ("## A > ### B") enclosing `offset` in `text`, outside fenced code. It names
 * where a copied marker sits in words a caller can resolve.
 */
function enclosingHeadings(text: string, offset: number): string {
	const stack: { level: number; heading: string }[] = [];
	let fenced = false;
	for (const line of text.slice(0, offset).split("\n")) {
		if (/^ {0,3}(?:```|~~~)/.test(line)) fenced = !fenced;
		const match = fenced ? null : /^ {0,3}(#{1,6})[ \t]+\S/.exec(line);
		if (!match) continue;
		const level = match[1].length;
		while (stack.length && stack[stack.length - 1].level >= level) stack.pop();
		stack.push({ level, heading: line.trim() });
	}
	return stack.map((entry) => entry.heading).join(" > ") || "the document's opening";
}

/**
 * A candidate whose only reserved bytes are marker lines inherited from a legacy first revision
 * (see `copiedArtifactMarkerOffsets`) is refused with its own code, the sections that hold them,
 * and the repair: replace those sections without the marker lines. The source revision is never
 * rewritten; the repaired successor is the clean one. Any other reserved byte falls through to
 * the general marker refusal below.
 */
function refuseInheritedCopiedMarkers(candidate: string): void {
	if (!candidate.startsWith(ARTIFACT_MARKER)) return;
	const body = candidate.slice(ARTIFACT_MARKER.length);
	if (!body.includes(ARTIFACT_MARKER_NAMESPACE) || withoutCopiedArtifactMarkers(body).includes(ARTIFACT_MARKER_NAMESPACE)) return;
	const offsets = copiedArtifactMarkerOffsets(body);
	const sections = [...new Set(offsets.map((offset) => enclosingHeadings(body, offset)))];
	successorFailure(
		"successor-copied-artifact-marker",
		`the candidate still carries ${offsets.length} copied artifact marker line${offsets.length === 1 ? "" : "s"} inherited from its source, under ${sections.map((section) => JSON.stringify(section)).join(", ")}: a first revision created before 0.14.0 pasted them from another managed document, and no revision may carry them. The source is never rewritten.`,
		"In this successor, also replace each section named above (RESOLVE_TARGET it, then a replace decision whose content is the section without the marker lines); the successor is then clean and every later one reads it normally.",
		{ copiedMarkers: offsets.length, sections },
	);
}

function refusalOf(error: unknown): CandidateValidationFailure {
	const failure = (error as { candidateValidation?: CandidateValidationFailure } | null)?.candidateValidation;
	if (failure && failure.status === "failed") return failure;
	throw error;
}

/** Outcome of running a publication point's own pre-publish validation without writing. */
export type PrePublishVerdict =
	| { applicable: true; refusal: CandidateValidationFailure | null }
	| { applicable: false; refusal: null };

/**
 * Dry run of the accept turn's validation (`derive_successor`) for a preview. `sourceDocument`
 * is the complete managed document, artifact marker included, and `sourceSha256` its digest --
 * the same pair the accept turn passes. A document without the artifact marker is not a managed
 * revision and can never reach `derive_successor` (its read refuses an unowned source), so the
 * verdict is `applicable: false`, never a pass. Errors that are not candidate refusals propagate.
 */
export function successorCandidateRefusal(
	sourceDocument: string,
	sourceSha256: string,
	patches: unknown,
): PrePublishVerdict {
	if (!sourceDocument.startsWith(ARTIFACT_MARKER)) return { applicable: false, refusal: null };
	try {
		validateSuccessorManifest(sourceDocument, sourceSha256, patches);
		return { applicable: true, refusal: null };
	} catch (error) {
		return { applicable: true, refusal: refusalOf(error) };
	}
}

/**
 * The first managed revision's pre-publish validation (`INITIAL_CREATE`) run over a v1 body
 * without writing, so CREATE_INITIAL_REVISION refuses exactly what a guarded initial write and
 * every later successor would refuse.
 */
export function initialCandidateRefusal(body: string): CandidateValidationFailure | null {
	try {
		validateInitialCandidate(body);
		return null;
	} catch (error) {
		return refusalOf(error);
	}
}

export function nextSuccessorTarget(sourceFilename: string): string {
	const parsed = parseRevisionIncrement(sourceFilename);
	if (!parsed) throw new Error("INVALID_MANAGED_SUCCESSOR_SOURCE");
	return `${parsed.prefix}${String(parsed.ordinal + 1).padStart(2, "0")}.md`;
}

async function deriveSuccessorProposal(
	projectRoot: string,
	source: string | undefined,
	sourceSha256: string | undefined,
	slug: string | undefined,
	patches: SuccessorPatch[] | undefined,
	signal?: AbortSignal,
): Promise<ToolResult> {
	const identity = validateSuccessorIdentity(source, sourceSha256, slug);
	try {
		await assertNewManagedProposalTargetAvailable(projectRoot, identity.slug);
	} catch (error) {
		successorFailure(
			"successor-target-collision",
			"the immutable successor target already exists or is not a safe standalone target",
			`Inventory the lineage and choose the next unused terminal-${REVISION_PLACEHOLDER} slug.`,
			{ targetSlug: identity.slug, reason: error instanceof Error ? error.message : String(error) },
		);
	}
	await assertContinuitySourceIsLatest("derive_successor", projectRoot, identity.source);
	const latest = await readContinuitySource("derive_successor", projectRoot, identity.source, signal);
	if (latest.sha256 !== identity.sourceSha256) {
		successorFailure(
			"successor-source-stale",
			"sourceSha256 does not match the exact current marker-owned source bytes",
			"Read and hash the latest managed proposal again, then rebuild the patch manifest.",
			{
				source: identity.source,
				expectedSha256: identity.sourceSha256,
				actualSha256: latest.sha256,
			},
		);
	}
	const { validatedPatches, composed, candidateBody, candidateValidation } = validateSuccessorManifest(
		`${ARTIFACT_MARKER}${latest.body}`,
		latest.sha256,
		patches,
	);
	await assertContinuitySourceIsLatest("derive_successor", projectRoot, identity.source);
	const current = await readContinuitySource("derive_successor", projectRoot, identity.source, signal);
	if (current.sha256 !== latest.sha256) {
		successorFailure(
			"successor-source-stale",
			"the exact current-state source changed before atomic publication",
			"Read the latest immutable source again and rebuild the patch manifest.",
			{ source: identity.source, expectedSha256: latest.sha256, actualSha256: current.sha256 },
		);
	}
	const written = await atomicCreateManagedProposal(
		projectRoot,
		identity.slug,
		candidateBody,
		signal,
	);
	return {
		content: [
			{
				type: "text",
				text: `Derived immutable successor ${written.path} atomically from ${PROPOSAL_DIRECTORY}/${identity.source}.`,
			},
		],
		details: {
			resource: "proposal",
			operation: "derive_successor",
			source: `${PROPOSAL_DIRECTORY}/${identity.source}`,
			sourceSha256: latest.sha256,
			sourceBytes: latest.bytes,
			target: written.path,
			targetSha256: written.sha256,
			bytesWritten: written.bytesWritten,
			patchIds: validatedPatches.map((patch) => patch.id),
			patchCount: validatedPatches.length,
			unchangedByteCoverage: composed.invariant,
			candidateValidation,
		},
	};
}

async function deriveProposal(
	projectRoot: string,
	base: string | undefined,
	slug: string | undefined,
	insertions: DeriveInsertion[] | undefined,
	continuityManifest: ContinuityManifest | undefined,
	signal?: AbortSignal,
): Promise<ToolResult> {
	if (base !== FIXED_DERIVE_BASE) {
		throw blocked(
			`derive accepts only the fixed base ${JSON.stringify(FIXED_DERIVE_BASE)}.`,
			"Pass that exact base literal; arbitrary source files are never authorized.",
		);
	}
	const safeSlug = validateDeriveSlug(slug);
	await assertNewManagedProposalTargetAvailable(projectRoot, safeSlug);
	const { source } = await readFixedDeriveBase(projectRoot, signal);
	const derived = buildDerivedBody(source, insertions ?? [], "derive");
	const candidateValidation = validatePrePublishCandidate("derive", source, derived.body);
	const continuityValidation = await validateContinuityManifest(
		"derive",
		projectRoot,
		safeSlug,
		derived.body,
		continuityManifest,
		signal,
	);
	const written = await atomicCreateManagedProposal(projectRoot, safeSlug, derived.body, signal);
	return {
		content: [{ type: "text", text: `Derived ${written.path} atomically from ${PROPOSAL_DIRECTORY}/${FIXED_DERIVE_BASE}.` }],
		details: {
			resource: "proposal",
			path: written.path,
			operation: "derive",
			base: `${PROPOSAL_DIRECTORY}/${FIXED_DERIVE_BASE}`,
			bytesWritten: written.bytesWritten,
			sha256: written.sha256,
			inlineNormalizationCount: derived.inlineNormalizationCount,
			displayBlocksPreserved: derived.displayBlockCount,
			numberedEquationsPreserved: derived.numberedEquationCount,
			insertionCount: insertions?.length ?? 0,
			candidateValidation,
			continuityValidation,
		},
	};
}

async function deriveProposalRevision(
	projectRoot: string,
	base: string | undefined,
	slug: string | undefined,
	replacements: DeriveReplacement[] | undefined,
	authorizedDisplayRelocations: AuthorizedDisplayRelocation[] | undefined,
	authorizedSectionRemovals: AuthorizedSectionRemoval[] | undefined,
	insertions: DeriveInsertion[] | undefined,
	continuityManifest: ContinuityManifest | undefined,
	signal?: AbortSignal,
): Promise<ToolResult> {
	if (base !== FIXED_DERIVE_BASE) {
		throw blocked(
			`derive_revision accepts only the fixed base ${JSON.stringify(FIXED_DERIVE_BASE)}.`,
			"Pass that exact base literal; arbitrary source files are never authorized.",
		);
	}
	const safeSlug = validateDeriveSlug(slug);
	await assertNewManagedProposalTargetAvailable(projectRoot, safeSlug);
	const { source } = await readFixedDeriveBase(projectRoot, signal);
	const baseDisplayBlocks = displayMathBlocks(source);
	const validatedReplacements = validateRevisionReplacements(replacements, source, baseDisplayBlocks);
	const validatedRelocations = validateAuthorizedDisplayRelocations(
		authorizedDisplayRelocations,
		validatedReplacements,
	);
	const validatedSectionRemovals = validateAuthorizedSectionRemovals(
		authorizedSectionRemovals,
		source,
		baseDisplayBlocks,
	);
	if (validatedReplacements.length === 0 && validatedSectionRemovals.length === 0) {
		throw blocked(
			"derive_revision requires at least one exact replacement or authorized whole-section removal.",
			"Provide replacements and/or authorizedSectionRemovals from the current fixed-base inventories.",
		);
	}
	const revisionMutations = mergeRevisionMutations(
		validatedReplacements,
		validatedSectionRemovals,
	);
	const revised = buildRevisedSource(source, baseDisplayBlocks, revisionMutations);
	const derived = buildDerivedBody(revised.source, insertions ?? [], "derive_revision", true, false);
	const candidateValidation = validatePrePublishCandidate(
		"derive_revision",
		source,
		derived.body,
		revisionMutations,
		validatedRelocations,
	);
	const continuityValidation = await validateContinuityManifest(
		"derive_revision",
		projectRoot,
		safeSlug,
		derived.body,
		continuityManifest,
		signal,
	);
	const written = await atomicCreateManagedProposal(projectRoot, safeSlug, derived.body, signal);
	return {
		content: [
			{
				type: "text",
				text: `Derived researcher-authorized revision ${written.path} atomically from ${PROPOSAL_DIRECTORY}/${FIXED_DERIVE_BASE}.`,
			},
		],
		details: {
			resource: "proposal",
			path: written.path,
			operation: "derive_revision",
			base: `${PROPOSAL_DIRECTORY}/${FIXED_DERIVE_BASE}`,
			bytesWritten: written.bytesWritten,
			sha256: written.sha256,
			inlineNormalizationCount: derived.inlineNormalizationCount,
			displayBlocksPreserved: revised.inheritedDisplayBlocksPreserved,
			authorizedEquationCount: revised.authorizedEquationCount,
			authorizedDisplayRelocationCount: validatedRelocations.length,
			resultingDisplayBlockCount: derived.displayBlockCount,
			numberedEquationCount: derived.numberedEquationCount,
			replacementCount: replacements?.length ?? 0,
			authorizedSectionRemovalCount: validatedSectionRemovals.length,
			authorizedSectionDisplayCount: validatedSectionRemovals.reduce(
				(total, removal) => total + removal.authorizedBaseIndexes.length,
				0,
			),
			insertionCount: insertions?.length ?? 0,
			candidateValidation,
			continuityValidation,
		},
	};
}

export type DocumentOperationGuardInput = { action: 'begin_document_operation'|'inspect'|'authorize_role'|'preflight_plan'|'authorize_mutation'|'complete_operation'|'block_operation'; operation_id:string; role?:string; mode?:'INITIAL_CREATE'|'INCREMENTAL_EDIT'; operation?:'MODIFY'|'INSERT'|'DELETE'|'MOVE'|'COPY'|'CONCEPTUAL_REVISION'; budget?:{max_document_delegations:number;attempts:number;model_candidates:number;patches:number}; targetFilename?:string; sourceFilename?:string; sourceSha256?:string; successorFilename?:string; mutationAction?:'write'|'derive_successor'|'create_draft'; userAuthorized?:boolean; reason?:string };
type DocumentOperationReceipt = { receipt_version:'document-operation-guard/v2'; receipt_id:string; operation_id:string; decision:'allowed'|'denied'; reason:{code:string;message:string}; terminal_state:'ACTIVE'|'BLOCKED'|'COMPLETED'; allowed_document_roles:readonly string[]; state:{execution_scope:'DOCUMENT_OPERATION';maintenance_authorized:false;infrastructure_mutation_allowed:false;test_execution_allowed:false;mode:'INITIAL_CREATE'|'INCREMENTAL_EDIT'|null;operation:DocumentOperationGuardInput['operation']|null}; budget:{max_document_delegations:number;attempts:number;model_candidates:number;patches:number}; consumed:{document_delegations:number;attempts:number;model_candidates:number;patches:number}; authorization?:string };
export type DocumentOperationGuard = { execute(input:DocumentOperationGuardInput,signal?:AbortSignal):Promise<DocumentOperationReceipt>; authorizeWorkspaceMutation(params:ProposalWorkspaceInput):DocumentOperationReceipt; completeWorkspaceMutation(operationId?:string):DocumentOperationReceipt; failWorkspaceMutation(operationId?:string,reason?:string):DocumentOperationReceipt; handleToolCall(_event:unknown):void;handleToolResult(_event:unknown):void };
const documentOperationGuardSchema = Type.Object({
 action: StringEnum(['begin_document_operation','inspect','authorize_role','preflight_plan','authorize_mutation','complete_operation','block_operation'] as const),
 operation_id: Type.String({minLength:1,maxLength:80}), role: Type.Optional(Type.String()),
 mode: Type.Optional(StringEnum(['INITIAL_CREATE','INCREMENTAL_EDIT'] as const)),
 operation: Type.Optional(StringEnum(['MODIFY','INSERT','DELETE','MOVE','COPY','CONCEPTUAL_REVISION'] as const)),
 budget: Type.Optional(Type.Object({max_document_delegations:Type.Integer({minimum:0,maximum:3}),attempts:Type.Integer({minimum:0,maximum:1}),model_candidates:Type.Integer({minimum:0,maximum:2}),patches:Type.Integer({minimum:0,maximum:8})})),
 targetFilename: Type.Optional(Type.String()), sourceFilename: Type.Optional(Type.String()), sourceSha256: Type.Optional(Type.String()), successorFilename: Type.Optional(Type.String()), mutationAction: Type.Optional(StringEnum(['write','derive_successor','create_draft'] as const)), userAuthorized: Type.Optional(Type.Boolean()), reason: Type.Optional(Type.String())
},{additionalProperties:false});
export function createDocumentOperationGuard(_projectRoot:string):DocumentOperationGuard {
 let active:{id:string;mode:any;operation:any;budget:any;token?:string;terminal:'ACTIVE'|'BLOCKED'|'COMPLETED';mutationAction?:DocumentOperationGuardInput['mutationAction'];targetFilename?:string;userAuthorized?:boolean}|undefined;
 const terminalIds=new Set<string>();
 const receipt=(decision:'allowed'|'denied',code:string,message:string):DocumentOperationReceipt=>({receipt_version:'document-operation-guard/v2',receipt_id:randomUUID(),operation_id:active?.id??'missing',decision,reason:{code,message},terminal_state:active?.terminal??'BLOCKED',allowed_document_roles:['deliberation-router','deliberation-editor','deliberation-reviewer','deliberation-tutor'],state:{execution_scope:'DOCUMENT_OPERATION',maintenance_authorized:false,infrastructure_mutation_allowed:false,test_execution_allowed:false,mode:active?.mode??null,operation:active?.operation??null},budget:active?.budget??{max_document_delegations:0,attempts:0,model_candidates:0,patches:0},consumed:{document_delegations:0,attempts:0,model_candidates:0,patches:0},authorization:active?.token});
 return {
  async execute(input){
   if(input.action==='begin_document_operation'){
    if(active)return receipt('denied','operation-active','another document operation is active');
    if(terminalIds.has(input.operation_id))return receipt('denied','operation-inactive','operation is terminal');
    active={id:input.operation_id,mode:null,operation:null,budget:{max_document_delegations:2,attempts:1,model_candidates:1,patches:4},terminal:'ACTIVE'};
    return receipt('allowed','begun','operation begun');
   }
   if(!active||active.id!==input.operation_id||active.terminal!=='ACTIVE')return receipt('denied','operation-inactive','operation is not active');
   if(input.action==='preflight_plan'){
    if(input.mutationAction==='create_draft'&&(input.mode!=='INITIAL_CREATE'||input.userAuthorized!==true||!input.targetFilename))return receipt('denied','draft-preflight-invalid','draft creation requires a bound target and explicit current-turn INITIAL_CREATE authorization');
    active.mode=input.mode;active.operation=input.operation;active.budget=input.budget??active.budget;active.mutationAction=input.mutationAction;active.targetFilename=input.targetFilename;active.userAuthorized=input.userAuthorized;
    return receipt('allowed','preflight-approved','V2 plan approved');
   }
   if(input.action==='authorize_mutation'){
    if(active.mutationAction==='create_draft'&&active.userAuthorized!==true)return receipt('denied','draft-authorization-missing','draft creation was not explicitly authorized');
    active.token=randomBytes(32).toString('base64url');return receipt('allowed','mutation-authorized',active.mutationAction==='create_draft'?'draft creation authorized':'successor publication authorized');
   }
   if(input.action==='complete_operation'){active.terminal='COMPLETED';const done=receipt('allowed','completed','operation completed');terminalIds.add(active.id);active=undefined;return done}
   if(input.action==='block_operation'){active.terminal='BLOCKED';const done=receipt('allowed','blocked',input.reason??'blocked');terminalIds.add(active.id);active=undefined;return done}
   return receipt('allowed','ok','operation active');
  },
  authorizeWorkspaceMutation(params){if(!active||params.operation_id!==active.id||params.operationAuthorization!==active.token)return receipt('denied','mutation-unauthorized','mutation is not authorized');return receipt('allowed','mutation-authorized','mutation authorized')},
  completeWorkspaceMutation(){if(!active)return receipt('denied','operation-inactive','operation is not active');active.terminal='COMPLETED';const done=receipt('allowed','completed','published');terminalIds.add(active.id);active=undefined;return done},
  failWorkspaceMutation(_id,reason){if(!active)return receipt('denied','operation-inactive','operation is not active');active.terminal='BLOCKED';const done=receipt('denied','publish-failed',reason??'publish failed');terminalIds.add(active.id);active=undefined;return done},
  handleToolCall(){},handleToolResult(){}
 };
}

export function createDocumentOperationGuardTool(guard: DocumentOperationGuard) {
	return {
		name: "document_operation_guard",
		label: "Document Operation Guard",
		description:
			"Controls explicit operation_id-scoped lifecycles. No guard is active on extension load or general tool use. begin_document_operation enables the bounded document policy. complete_operation and block_operation make only the named operation terminal.",
		promptSnippet: "Begin and finish explicit isolated document or authorized maintenance operation lifecycles",
		promptGuidelines: [
			"Call document_operation_guard begin_document_operation with a new operation_id before any document workflow action; use the same operation_id through complete_operation or block_operation.",
			"Maintenance is a separate explicitly authorized infrastructure workflow.",
			"A terminal or reused operation_id cannot be reactivated, and only one operation may be ACTIVE at a time.",
		],
		parameters: documentOperationGuardSchema,
		async execute(
			_toolCallId: string,
			params: DocumentOperationGuardInput,
			signal?: AbortSignal,
		): Promise<ToolResult> {
			throwIfAborted(signal);
			const receipt = await guard.execute(params, signal);
			return { content: [{ type: "text", text: JSON.stringify(receipt) }], details: { receipt } };
		},
	};
}

export function createProposalWorkspaceTool(
	projectRoot: string,
	options: ProposalWorkspaceToolOptions = {},
) {
	const capabilities = new Map<string, OverwriteCapability>();
	const now = options.now ?? Date.now;
	return {
		name: "proposal_workspace",
		label: "Proposal Workspace",
		description: options.operationGuard
			? `DOCUMENT_OPERATION proposal workspace. Reads remain sandboxed; mutations fail closed except one preflight-bound initial ${FIRST_REVISION_LABEL} write or one exact latest/SHA-bound incremental derive_successor under the declared operation budget.`
			: `Sandboxed proposal workspace. Reads only eligible proposal evidence and marker-owned managed targets; writes only ${PROPOSAL_DIRECTORY}/${artifact.stem}-<slug>.md. derive_successor atomically patches the exact SHA-bound latest root or explicit-lineage managed revision into a new immutable same-lineage ${REVISION_PLACEHOLDER} target with byte-level untouched-region verification. Legacy derive and derive_revision remain available for fixed-base compatibility. All other filesystem access is denied.`,
		promptSnippet: "Use the sandboxed proposal corpus and proposal target workspace",
		promptGuidelines: options.operationGuard
			? [
					"Use proposal_workspace exclusively for document-operation filesystem access; if it blocks or is unavailable, stop.",
					"Inventory and read only bounded eligible proposal resources. Generic filesystem and shell tools remain outside this boundary.",
					`Mutation is limited to the exact proposal route approved by document_operation_guard: write only for INITIAL_CREATE ${FIRST_REVISION_LABEL}, or derive_successor only for existing incremental updates.`,
					"Pass the active operation_id and one-time operationAuthorization unchanged. Never request append, derive, derive_revision, authorize_overwrite, a route mismatch, an undeclared patch, a second attempt, tests, maintenance, or infrastructure mutation.",
				]
			: [
					"Use proposal_workspace exclusively for this domain's filesystem access; if it blocks or is unavailable, stop and report the failure.",
					`Use proposal_workspace read/managed_target with the exact generated filename to resume or migrate an existing marker-owned draft; never use it for bases or manual ${PROPOSAL_DIRECTORY}.`,
					`When a latest managed proposal exists, use derive_successor with its exact terminal-${REVISION_PLACEHOLDER} filename, complete-file SHA-256, and only disjoint researcher-authorized exact replace or narrowly anchored insert patches. Root ${artifact.stem}-${FIRST_REVISION_LABEL}.md advances only with slug ${SECOND_REVISION_LABEL}; explicit lineages retain the greater same-lineage terminal-${REVISION_PLACEHOLDER} rule, and root/explicit transitions are forbidden.`,
					`Use legacy derive only for initial fixed-base creation or backward-compatible flows: ${DOMAIN.deriveBase}, a new slug ending -${REVISION_PLACEHOLDER}, and bounded additive insertions anchored to exact unique base text or anchor={equationLabel} / anchor={numberedTag} with position=after.`,
					"Use inventory/displays with bounded offset/limit and read/display with a returned displayId to inspect parser-exact fixed-base display blocks; IDs are deterministic for exact block bytes and duplicate occurrence, and stale IDs fail closed.",
					"Use inventory/sections with bounded offset/limit to obtain stable fixed-base sectionId selectors, heading text/level, byte extents, and inherited display counts; a section extends from its ATX heading through the next heading of the same or higher level.",
					"Use proposal_workspace derive_revision only for an explicitly researcher-authorized correction: select bounded exact complete base blocks and/or authorizedSectionRemovals by current sectionId, provide one numberedTag, equationLabel, displayBlock, or displayId authorization for each removed or altered inherited display, and use authorizedDisplayRelocations source/destination ids for every explicit move group.",
					`When a latest managed target is part of a derive or derive_revision decision, pass continuityManifest with its exact terminal-${REVISION_PLACEHOLDER} filename, complete-file SHA-256, and bounded required, forbidden, or supersession assertions; publication fails closed unless latest-source and fully composed candidate byte counts match exactly.`,
					"Treat proposal_workspace derive and derive_revision as fail-closed pre-publish transactions: fully composed bytes must preserve standalone ATX headings, Markdown block boundaries, exact non-moved display/heading coverage and order, authorized move-group coverage/order, guarded flat-domain definitions, and any supplied continuityManifest before atomic target creation.",
					"When replacing a proposal target, call authorize_overwrite for its exact slug and use the returned unexpired capability on the next write; never claim approval or send a boolean replacement flag.",
				],
		parameters: proposalWorkspaceSchema,
		async execute(
			_toolCallId: string,
			params: ProposalWorkspaceInput,
			signal?: AbortSignal,
			_onUpdate?: unknown,
			ctx?: ExtensionContext,
		): Promise<ToolResult> {
			assertShape(params);
			throwIfAborted(signal);
			if (
				options.operationGuard &&
				params.action !== "inventory" &&
				params.action !== "read"
			) {
				const mutationAuthorization = options.operationGuard.authorizeWorkspaceMutation(params);
				if (mutationAuthorization.decision !== "allowed") throw blocked("the document operation has not authorized this mutation.", "Complete preflight and present the one-time authorization.");
			}
			const root = await canonicalProjectRoot(projectRoot);
			if (params.action === "inventory") {
				if (params.resource === "guides") return inventoryGuides(root);
				if (params.resource === "bases") return inventoryBases(root);
				if (params.resource === "sections") {
					return inventoryFixedSections(root, params.offset, params.limit, signal);
				}
				return inventoryFixedDisplays(root, params.offset, params.limit, signal);
			}
			if (params.action === "read") {
				if (params.resource === "display") {
					return readFixedDisplay(root, params.displayId, signal);
				}
				const authorized =
					params.resource === "guide"
						? await authorizeGuide(root, params.name)
						: params.resource === "base"
							? await authorizeBase(root, params.name)
							: await authorizeManagedTarget(root, params.name);
				if (params.resource === "managed_target") {
					return withFileMutationQueue(authorized.path, () =>
						readBounded(authorized.path, authorized.name, signal, true),
					);
				}
				return readBounded(authorized.path, authorized.name, signal);
			}
			if (params.action === "authorize_overwrite") {
				return authorizeProposalOverwrite(root, params.slug, signal, ctx, capabilities, now);
			}
			if (params.action === "append") {
				return appendProposalRevision(root, params.slug, params.content, signal);
			}
			if (params.action === "derive") {
				return deriveProposal(
					root,
					params.base,
					params.slug,
					params.insertions,
					params.continuityManifest,
					signal,
				);
			}
			if (params.action === "derive_revision") {
				return deriveProposalRevision(
					root,
					params.base,
					params.slug,
					params.replacements,
					params.authorizedDisplayRelocations,
					params.authorizedSectionRemovals,
					params.insertions,
					params.continuityManifest,
					signal,
				);
			}
			if (params.action === "derive_successor") {
				try {
					const result = await deriveSuccessorProposal(
						root,
						params.source,
						params.sourceSha256,
						params.slug,
						params.patches,
						signal,
					);
					return result;
				} catch (error) {
					if (options.operationGuard) {
						options.operationGuard.failWorkspaceMutation(
							params.operation_id,
							error instanceof Error ? error.message : String(error),
						);
					}
					throw error;
				}
			}
			try {
				const result = options.operationGuard
					? await createInitialProposal(root, params.slug, params.content, signal)
					: await writeProposal(
						root,
						params.slug,
						params.content,
						params.capability,
						signal,
						capabilities,
						now,
					);
				if (options.operationGuard) {
					result.details.operationGuard = options.operationGuard.completeWorkspaceMutation(params.operation_id);
				}
				return result;
			} catch (error) {
				if (options.operationGuard) {
					options.operationGuard.failWorkspaceMutation(
						params.operation_id,
						error instanceof Error ? error.message : String(error),
					);
				}
				throw error;
			}
		},
	};
}

import { adoptInitialRevision, ChatDeliberationService, createFilesystemInitialRevisionPublicationPort, initialRevisionLockState, DraftMaterializationService, InitialRevisionCreationService, LifecycleV1PublicRouter, ProposalDeliberationOrchestrator, ProposalWorkspaceAdapter, defaultPiSessionDraftLifecycleAdapter, getRuntimeMetrics, getSharedPiSessionDraftRegistry, loadDocumentState, MAX_CHAT_DOCUMENT_CONTEXT_BYTES, MAX_CHAT_GUIDE_CONTEXT_BYTES, recordLifecycleMetric, recordRouteMetric, resolveIntent, resolveLatestManagedRevision, runConsistencyAudit, runProposalDeliberationSelfAudit, type ChatDocumentContext, type ChatGuideFragment, type DraftMaterializationPolicy, type EditAction, type DraftMaterializationRequest, type PiSessionDraftLifecycleAdapter, type PiSessionDraftRegistry, type ReviewerAdapter, type SemanticEditPlanner, type TutorAdapter } from './exports.js';
import { createSuccessorAcceptanceRegistry, type SuccessorAcceptanceRegistry } from './successor-acceptance-registry.js';

type GlobalRouteStage = 'LIFECYCLE' | 'DIRECT_DOCUMENT' | 'CHAT_DELIBERATION' | 'DRAFT_MATERIALIZATION' | 'MAINTENANCE' | 'CREATE_INITIAL_REVISION' | 'EXISTING_FALLBACK';
type GlobalRouteInput = { instruction: string } & { operation?: string; conversationId?: string; draftMaterialization?: DraftMaterializationRequest; openDeliberation?: boolean };
type GlobalRoute = { stage: GlobalRouteStage; bypassedStages: GlobalRouteStage[] };
export type V2ExecutionAuthority = { scope:'CHAT_DELIBERATION'|'DOCUMENT_EDIT'|'MAINTENANCE'|'EXISTING_FALLBACK'; taskDelegation:'FORBIDDEN'|'LOCAL_ONLY'|'PERMITTED'; documentAuthority:'FORBIDDEN'|'GUARDED'|'NOT_APPLICABLE'; durableState:'FORBIDDEN'|'PERMITTED'|'NOT_APPLICABLE'; stateIdentifier:'conversationId'|'maintenanceTaskId'|'scientificThreadId'|null; explicitHandoffRequired:boolean };
const LIFECYCLE_OPERATIONS = new Set(['WITHDRAW_REVISION', 'RESTORE_WITHDRAWN_REVISION']);
const DIRECT_DOCUMENT_INTENTS = new Set(['MODIFY', 'INSERT', 'DELETE', 'MOVE', 'COPY', 'CONCEPTUAL_REVISION', 'REVIEW']);
const MAINTENANCE_OPERATION = 'MAINTENANCE';
const CREATE_SUCCESSOR_OPERATION = 'CREATE_SUCCESSOR';
const CREATE_INITIAL_REVISION_OPERATION = 'CREATE_INITIAL_REVISION';
/** The longest `rationale` a successor receipt records. */
const MAX_RATIONALE_CHARACTERS = 2_000;

/**
 * The optional decision record a successor receipt carries beside its `instructionHash`:
 * `rationale` (why) and `decider` (`agent` or `human`, who). Validated before anything runs, so a
 * malformed record is refused at the preview rather than published, and refused on any operation
 * that writes no successor receipt rather than silently dropped.
 */
function decisionRecordBlocker(params:{operation?:string;rationale?:unknown;decider?:unknown}):{code:string;message:string}|undefined{
 if(params.rationale===undefined&&params.decider===undefined) return undefined;
 if(params.operation!==CREATE_SUCCESSOR_OPERATION) return {code:'DECISION_RECORD_UNSUPPORTED',message:'rationale and decider are recorded only in a CREATE_SUCCESSOR receipt; nothing was run.'};
 if(params.rationale!==undefined&&!(typeof params.rationale==='string'&&params.rationale.trim().length>0&&params.rationale.length<=MAX_RATIONALE_CHARACTERS)) return {code:'DECISION_RECORD_INVALID',message:`rationale must be a non-blank string of at most ${MAX_RATIONALE_CHARACTERS} characters; nothing was run.`};
 if(params.decider!==undefined&&params.decider!=='agent'&&params.decider!=='human') return {code:'DECISION_RECORD_INVALID',message:`decider must be "agent" or "human"; got ${JSON.stringify(params.decider)}. Nothing was run.`};
 return undefined;
}

/** Operations that accept `dryRun`: the ones that publish without a preview turn of their own. */
const ADOPT_INITIAL_REVISION_OPERATION = 'ADOPT_INITIAL_REVISION';
const DRY_RUN_OPERATIONS = new Set([CREATE_INITIAL_REVISION_OPERATION, ADOPT_INITIAL_REVISION_OPERATION]);

/**
 * The longest `instruction` any operation accepts, in characters (UTF-16 code units, what a
 * JavaScript string's `length` counts). For `CREATE_INITIAL_REVISION` the instruction IS the idea,
 * so this is also the largest idea a first revision can start from. Declared once: the tool schema
 * below states it, and `tool.execute` enforces it, because the CLI host calls `execute` directly
 * and no validating dispatcher ever reads that schema on its path.
 */
export const MAX_INSTRUCTION_CHARACTERS = 65_536;

/** How much of the instruction cap a request used, reported on the successor preview and on the first revision's result. `remaining` is negative only on the refusal. */
export function instructionBudget(instruction:unknown):{limit:number;used:number;remaining:number}{
 const used=typeof instruction==='string'?instruction.length:0;
 return {limit:MAX_INSTRUCTION_CHARACTERS,used,remaining:MAX_INSTRUCTION_CHARACTERS-used};
}

/**
 * The caller-facing projection of a `CREATE_INITIAL_REVISION` refusal: its `nextAction` and its
 * one blocker. Extracted from the nested ternary it replaced because a third refusal code --
 * `INITIAL_REVISION_CANONICAL_FORM_VIOLATION`, raised when the COMPOSED v1 breaks the domain's
 * own canonical form -- carries evidence the other two do not, and a caller told only "blocked"
 * cannot repair a source document it was never shown.
 */
function projectInitialRevisionRefusal(result:{code:string;violations?:readonly {rule:string;line:number;detail:string}[];candidateValidation?:CandidateValidationFailure}):{nextAction:string;blockers:{code:string;message:string}[]}{
 if(result.code==='MANAGED_PROPOSAL_ALREADY_EXISTS')
  return {nextAction:'use_existing_managed_proposal',blockers:[{code:result.code,message:'A managed proposal already exists; CREATE_INITIAL_REVISION never overwrites or duplicates it.'}]};
 if(result.code==='INITIAL_REVISION_CANONICAL_FORM_VIOLATION'){
  const evidence=(result.violations??[]).map((violation)=>`line ${violation.line}: ${violation.rule} -- ${violation.detail}`).join('; ');
  return {nextAction:'repair_canonical_form',blockers:[{code:result.code,message:`The composed first revision violates this domain's canonical form, so nothing was written. Repair the idea or the declared source it came from, then retry: ${evidence}`}]};
 }
 // The composed v1 failed the same pre-publish validation a guarded first write and every
 // successor's accept turn run (`initialCandidateRefusal`). The rule code, its message, its
 // repair step and the offending line are the evidence a caller needs to repair the source.
 if(result.code==='INITIAL_REVISION_CANDIDATE_VALIDATION_FAILED'){
  const failure=result.candidateValidation;
  const line=typeof failure?.line==='string'?` Offending line: ${JSON.stringify(failure.line)}.`:'';
  return {nextAction:'repair_candidate_markdown',blockers:[{code:result.code,message:`The composed first revision fails pre-publish validation (${failure?.code ?? 'unknown'}: ${failure?.message ?? 'no detail'}), so nothing was written. ${failure?.nextStep ?? ''}${line} Repair the idea or the declared source it came from, then retry.`}]};
 }
 // A one-sentence idea is not an empty one: the first sentence becomes the title and the
 // second the section heading, so the refusal names that requirement instead.
 if(result.code==='INITIAL_IDEA_SINGLE_SENTENCE'){
  return {nextAction:'supply_initial_idea',blockers:[{code:result.code,message:'The idea in instruction needs at least two sentences, and it has one, so nothing was written: the first sentence becomes the title and the second the section heading. A sentence ends with ".", "!" or "?"; a line break does not end one. Add a second sentence and retry.'}]};
 }
 return {nextAction:'supply_initial_idea',blockers:[{code:result.code,message:'Provide a non-empty idea in instruction.'}]};
}
const MANAGED_CHAT_DOCUMENT_FILENAME = strictManagedRevision;
const MANAGED_ARTIFACT_MARKER = artifact.marker;

/** Canonicalizes only the two public CHAT_DELIBERATION spellings; it never normalizes paths. */
export function resolveChatDocumentFilename(rawFilename: unknown): { filename?: string; reason?: string } {
 if (rawFilename === undefined) return {};
 if (typeof rawFilename !== 'string') return { reason: 'CHAT_DOCUMENT_FILENAME_INVALID' };
 const directoryPrefix = `${PROPOSAL_DIRECTORY}/`;
 const filename = rawFilename.startsWith(directoryPrefix) ? rawFilename.slice(directoryPrefix.length) : rawFilename;
 if (!MANAGED_CHAT_DOCUMENT_FILENAME(filename) || (rawFilename !== filename && rawFilename !== `${PROPOSAL_DIRECTORY}/${filename}`)) return { reason: 'CHAT_DOCUMENT_FILENAME_INVALID' };
 return { filename };
}

/**
 * Loads every declared source's directory (task 3.5/3.6, spec I2; generalized in change 7 to
 * `profile.sources`, replacing the single hardcoded `GUIDE_DIRECTORY` path) as read-only
 * reference fragments for a NEW deliberation's initial context assembly. Reused across every
 * invocation but only ever called by `execute()` for a conversation's first turn -- never per
 * turn. Never hardcodes a guide filename: it inventories each declared source path exactly like
 * `inventoryGuides` does for the legacy single guide, and silently skips a source whose
 * directory is absent (never throws), so projects without one (or existing fixtures that never
 * configured one) are unaffected. `required: true` presence is enforced separately -- only at
 * `CREATE_INITIAL_REVISION`, by `missingRequiredSources` below -- never here.
 *
 * TWO shapes are collected from each declared directory, nested first and flat second: the
 * legacy `<folder>/<folder>.md` per-paper shape, and plain `.md` files sitting directly in the
 * directory. A managed revision is the latter, so a source declaring another skill's managed
 * directory delivered nothing at all until the flat pass existed.
 */
async function loadGuideDirectoryFragments(projectRoot: string): Promise<ChatGuideFragment[]> {
 return (await loadSourceWindow(projectRoot, MAX_CHAT_GUIDE_CONTEXT_BYTES)).fragments;
}

/** The largest source window one `CREATE_INITIAL_REVISION` may ask for: the managed document's own size limit, since every loaded byte is pasted into v1. */
export const MAX_SOURCE_WINDOW_BYTES = MAX_WRITE_BYTES;

/** What the source window read: every Markdown document the declared sources offer, in load order, and how much of each reached the fragments. */
export type SourceWindowReport = {
 limitBytes: number;
 loadedBytes: number;
 sources: { path: string; bytes: number; loadedBytes: number; status: 'loaded' | 'truncated' | 'not-loaded'; reservedMarkersRemoved?: number }[];
};

/**
 * The fragments `loadGuideDirectoryFragments` hands a first revision, plus the report of what the
 * window did. Same walk, same order (declared sources in profile order; nested before flat inside
 * each), same `limit` semantics: the window is a total across every source, a document that
 * crosses it is cut at the limit, and every document after it is not read at all. The report
 * lists every document regardless, so a cut or a left-out source is visible instead of silent.
 */
async function loadSourceWindow(projectRoot: string, limit: number): Promise<{ fragments: ChatGuideFragment[]; report: SourceWindowReport }> {
 const report: SourceWindowReport = { limitBytes: limit, loadedBytes: 0, sources: [] };
 let root: string;
 try {
  root = await canonicalProjectRoot(projectRoot);
 } catch {
  return { fragments: [], report };
 }
 const fragments: ChatGuideFragment[] = [];
 let bytes = 0;
 for (const source of DOMAIN.sources) {
  for (const file of await sourceMarkdownFiles(root, source.path)) {
   let size = 0;
   try { size = (await stat(file.canonical)).size; } catch { continue; }
   if (bytes >= limit) {
    report.sources.push({ path: file.relative, bytes: size, loadedBytes: 0, status: 'not-loaded' });
    continue;
   }
   const buffer = await readFile(file.canonical);
   const raw = buffer.subarray(0, limit - bytes).toString("utf8");
   const loaded = Buffer.byteLength(raw);
   const { text, removed } = neutralizeReservedMarkers(raw);
   report.sources.push({ path: file.relative, bytes: buffer.length, loadedBytes: Math.min(loaded, buffer.length), status: loaded >= buffer.length ? 'loaded' : 'truncated', ...(removed ? { reservedMarkersRemoved: removed } : {}) });
   if (!raw) continue;
   bytes += loaded;
   fragments.push({ path: file.relative, content: text });
  }
 }
 report.loadedBytes = bytes;
 return { fragments, report };
}

/** The `SOURCE_WINDOW_TRUNCATED` warning for a report that cut or left out a document, or none. */
function sourceWindowWarnings(report: SourceWindowReport): { code: string; message: string }[] | undefined {
 const truncated = report.sources.filter((source) => source.status === 'truncated').map((source) => `${source.path} (${source.loadedBytes} of ${source.bytes} bytes)`);
 const left = report.sources.filter((source) => source.status === 'not-loaded').map((source) => source.path);
 if (!truncated.length && !left.length) return undefined;
 const parts = [truncated.length ? `cut at the window: ${truncated.join(', ')}` : '', left.length ? `not read at all: ${left.join(', ')}` : ''].filter(Boolean).join('; ');
 return [{ code: 'SOURCE_WINDOW_TRUNCATED', message: `The first revision reads at most ${report.limitBytes} bytes across its declared sources, in declaration order; ${parts}. Pass sourceWindowBytes (up to ${MAX_SOURCE_WINDOW_BYTES}) to widen it for this creation, shorten the sources, or carry what matters in the idea text.` }];
}

/**
 * Every Markdown file one declared source directory offers, in the loader's own order:
 * the nested `<folder>/<folder>.md` shape first, then flat `*.md` sitting directly
 * inside the directory. `relative` is what a fragment reports as its path; `canonical`
 * is the resolved regular file to read.
 *
 * TWO shapes, nested first and flat second. The nested shape is what the legacy single
 * guide was -- one directory per ingested paper -- and the mathematical domain still
 * depends on it. It is NOT what a managed revision is: a managed revision is a flat file
 * named `<stem>-<lineage>-<label>.md` sitting directly in its own directory. So a domain
 * that declares another skill's managed directory as a source (a downstream document
 * whose claims trace back to an upstream managed revision) used to get the WORST of both:
 * the required-source gate enforced the directory's presence, and the loader then
 * descended one level, found no sub-directories, and delivered nothing. The source was
 * required, present, and silent.
 *
 * ONE derivation, shared by `loadGuideDirectoryFragments` (which reads these bytes) and
 * `missingRequiredSources` (which only needs to know whether there is at least one). A
 * second enumeration would drift the first time a shape changes, and the gate would then
 * swear a source holds a document the loader cannot find.
 *
 * Never throws: an absent or unreadable directory, and any entry that fails a path check,
 * are silently skipped -- the same read-only try/catch shape the loader already used.
 */
async function sourceMarkdownFiles(
 root: string,
 sourcePath: string,
): Promise<readonly { readonly relative: string; readonly canonical: string }[]> {
 let directory: string;
 try {
  directory = await canonicalDirectory(root, sourcePath);
 } catch {
  return [];
 }
 let entries;
 try {
  entries = await readdir(directory, { withFileTypes: true });
 } catch {
  return [];
 }
 const byName = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
 const found: { relative: string; canonical: string }[] = [];
 const folders = entries
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort(byName);
 for (const folder of folders) {
  const markdownName = `${folder}.md`;
  if (!GUIDE_MARKDOWN.test(markdownName)) continue;
  try {
   const paperDir = await canonicalDirectory(root, `${sourcePath}/${folder}`);
   found.push({
    relative: `${sourcePath}/${folder}/${markdownName}`,
    canonical: await canonicalRegularFile(paperDir, markdownName, "guide Markdown"),
   });
  } catch {
   continue;
  }
 }
 const files = entries
  .filter((entry) => entry.isFile() && GUIDE_MARKDOWN.test(entry.name))
  .map((entry) => entry.name)
  .sort(byName);
 for (const name of files) {
  try {
   found.push({
    relative: `${sourcePath}/${name}`,
    canonical: await canonicalRegularFile(directory, name, "source Markdown"),
   });
  } catch {
   continue;
  }
 }
 return found;
}

/**
 * Every declared `required: true` source whose directory is absent from disk (change 7). A
 * read-only presence check, never a fragment load -- mirrors the same try/catch shape
 * `loadGuideDirectoryFragments` already uses per source. Empty when every required source is
 * present, or when the profile declares none.
 *
 * Widened to report WHY, in two kinds. `'absent'` is the original check: the directory is
 * not on disk. `'empty'` is new, and exists because the original was checking the wrong
 * thing -- presence was an `lstat`, so `mkdir <declared path>` satisfied a source the domain
 * cannot draft without, and v1 then rendered against nothing. A required source is required
 * for its CONTENT; an empty directory answers the letter of the declaration and none of it.
 *
 * Emptiness is derived from `sourceMarkdownFiles`, the SAME enumeration the loader itself
 * walks -- never a second scan of its own. Were it a second scan, this gate could swear a
 * source holds a document the loader would not find, which is the failure the two shapes
 * (nested and flat) already caused once.
 *
 * Optional sources are untouched: an absent or empty one stays legal and stays silent here.
 */
async function missingRequiredSources(
 projectRoot: string,
): Promise<readonly { readonly path: string; readonly reason: "absent" | "empty" }[]> {
 let root: string;
 try {
  root = await canonicalProjectRoot(projectRoot);
 } catch {
  return DOMAIN.sources
   .filter((source) => source.required)
   .map((source) => ({ path: source.path, reason: "absent" as const }));
 }
 const unanswered: { path: string; reason: "absent" | "empty" }[] = [];
 for (const source of DOMAIN.sources) {
  if (!source.required) continue;
  try {
   await canonicalDirectory(root, source.path);
  } catch {
   unanswered.push({ path: source.path, reason: "absent" });
   continue;
  }
  if ((await sourceMarkdownFiles(root, source.path)).length === 0) {
   unanswered.push({ path: source.path, reason: "empty" });
  }
 }
 return unanswered;
}

/** Wraps `resolveLatestManagedRevision` for the base-confirmation gate: a project with no managed
 * directory at all (e.g. a fresh workspace, or fixtures that never created one) has nothing to confirm,
 * so any resolution failure degrades to `{status:'empty'}` rather than blocking ordinary chat. */
async function safeResolveLatestManagedRevision(projectRoot: string) {
 try {
  return await resolveLatestManagedRevision(projectRoot);
 } catch {
  return { status: "empty" as const };
 }
}

async function loadChatDocumentContext(projectRoot: string, filename: string): Promise<{ document?: ChatDocumentContext; reason?: string }> {
 try {
  const state = await loadDocumentState(projectRoot, filename, { readOnly: true });
  if (!state.documentBytes.subarray(0, MANAGED_ARTIFACT_MARKER.length).equals(MANAGED_ARTIFACT_MARKER)) return { reason: 'CHAT_DOCUMENT_UNMANAGED' };
  const content = state.documentBytes.subarray(0, MAX_CHAT_DOCUMENT_CONTEXT_BYTES).toString('utf8');
  return { document: Object.freeze({ access: 'READ_ONLY', filename: state.filename, revision: state.revision, lineage: state.lineage, documentSha256: state.documentSha256, content, bytesRead: state.documentBytes.length, truncated: state.documentBytes.length > MAX_CHAT_DOCUMENT_CONTEXT_BYTES }) };
 } catch {
  return { reason: 'CHAT_DOCUMENT_NOT_FOUND' };
 }
}

function selectedGlobalRoute(stage: GlobalRouteStage, bypassedStages: GlobalRouteStage[]): GlobalRoute {
 const route = {stage, bypassedStages};
 recordRouteMetric(route.stage, route.bypassedStages);
 return route;
}
/** Public V2 authority boundary. Generic worker/task control is external; V2 never mints it for chat or document edits. */
export function resolveV2ExecutionAuthority(stage: GlobalRouteStage): V2ExecutionAuthority {
 if(stage==='CHAT_DELIBERATION') return {scope:'CHAT_DELIBERATION',taskDelegation:'FORBIDDEN',documentAuthority:'FORBIDDEN',durableState:'FORBIDDEN',stateIdentifier:'conversationId',explicitHandoffRequired:false};
 if(stage==='DIRECT_DOCUMENT'||stage==='DRAFT_MATERIALIZATION') return {scope:'DOCUMENT_EDIT',taskDelegation:'LOCAL_ONLY',documentAuthority:'GUARDED',durableState:'NOT_APPLICABLE',stateIdentifier:null,explicitHandoffRequired:true};
 if(stage==='MAINTENANCE') return {scope:'MAINTENANCE',taskDelegation:'PERMITTED',documentAuthority:'FORBIDDEN',durableState:'NOT_APPLICABLE',stateIdentifier:'maintenanceTaskId',explicitHandoffRequired:true};
 if(stage==='CREATE_INITIAL_REVISION') return {scope:'DOCUMENT_EDIT',taskDelegation:'LOCAL_ONLY',documentAuthority:'GUARDED',durableState:'NOT_APPLICABLE',stateIdentifier:null,explicitHandoffRequired:true};
 return {scope:'EXISTING_FALLBACK',taskDelegation:'LOCAL_ONLY',documentAuthority:'NOT_APPLICABLE',durableState:'NOT_APPLICABLE',stateIdentifier:null,explicitHandoffRequired:true};
}
export function resolveGlobalRoute(input: GlobalRouteInput): GlobalRoute {
 // Draft materialization is the only explicit create-only exit from session-local chat.
 if(input.draftMaterialization) return selectedGlobalRoute('DRAFT_MATERIALIZATION',['LIFECYCLE','DIRECT_DOCUMENT','CHAT_DELIBERATION','MAINTENANCE']);
 // Mode is otherwise an authority boundary: explicit chat wins before every generic heuristic, including lifecycle text.
 // CLOSE_DELIBERATION is an explicit chat-scoped operation too (task 2.2): it is dispatched inside the CHAT_DELIBERATION branch, never a separate route stage.
 if(input.operation==='CHAT_DELIBERATION'||input.operation==='CLOSE_DELIBERATION') return selectedGlobalRoute('CHAT_DELIBERATION',['LIFECYCLE','DIRECT_DOCUMENT','DRAFT_MATERIALIZATION','MAINTENANCE']);
 if(input.operation===MAINTENANCE_OPERATION) return selectedGlobalRoute('MAINTENANCE',['LIFECYCLE','DIRECT_DOCUMENT','CHAT_DELIBERATION','DRAFT_MATERIALIZATION']);
 // CREATE_INITIAL_REVISION (spec I1) is an explicit, user-triggered operation only -- it is never inferred
 // from natural language and never auto-bootstrapped from any other route, including an open deliberation.
 if(input.operation===CREATE_INITIAL_REVISION_OPERATION) return selectedGlobalRoute('CREATE_INITIAL_REVISION',['LIFECYCLE','DIRECT_DOCUMENT','CHAT_DELIBERATION','DRAFT_MATERIALIZATION','MAINTENANCE']);
 // CREATE_SUCCESSOR is an explicit document-edit route, never a lifecycle inference.
 if(input.operation===CREATE_SUCCESSOR_OPERATION) return selectedGlobalRoute('DIRECT_DOCUMENT',['LIFECYCLE','CHAT_DELIBERATION','DRAFT_MATERIALIZATION','MAINTENANCE']);
 // An explicit lifecycle operation is always honored, even while a conversation is in open deliberation.
 const explicitLifecycle = typeof input.operation === 'string' && LIFECYCLE_OPERATIONS.has(input.operation);
 if(explicitLifecycle) return selectedGlobalRoute('LIFECYCLE',[]);
 const resolved = resolveIntent(input.instruction);
 // An explicit natural-language CLOSE (task 2.3) is itself the exit action: always honored, same as the explicit operation above.
 if(resolved.intent==='CLOSE_DELIBERATION') return selectedGlobalRoute('CHAT_DELIBERATION',['LIFECYCLE','DIRECT_DOCUMENT','DRAFT_MATERIALIZATION','MAINTENANCE']);
 // Mode-first lock (D1/D2): while a conversation is in OPEN deliberation, only the explicit exits above (chat re-send, MAINTENANCE, CREATE_SUCCESSOR,
 // an explicit lifecycle operation, or an explicit CLOSE) can leave it. A keyword-inferred lifecycle/edit/deliberate follow-up never leaks to a
 // mutating route; control stays in the tutor loop until CLOSE.
 if(input.openDeliberation) return selectedGlobalRoute('CHAT_DELIBERATION',['LIFECYCLE','DIRECT_DOCUMENT','DRAFT_MATERIALIZATION','MAINTENANCE']);
 if(LIFECYCLE_OPERATIONS.has(resolved.intent)) return selectedGlobalRoute('LIFECYCLE',[]);
 // An edit is the only natural-language exit from an established chat conversation.
 if(DIRECT_DOCUMENT_INTENTS.has(resolved.intent)) return selectedGlobalRoute('DIRECT_DOCUMENT',['LIFECYCLE']);
 if(resolved.intent==='DELIBERATE') return selectedGlobalRoute('CHAT_DELIBERATION',['LIFECYCLE','DIRECT_DOCUMENT','DRAFT_MATERIALIZATION','MAINTENANCE']);
 if(input.conversationId) return selectedGlobalRoute('CHAT_DELIBERATION',['LIFECYCLE','DIRECT_DOCUMENT','DRAFT_MATERIALIZATION','MAINTENANCE']);
 return selectedGlobalRoute('EXISTING_FALLBACK',['LIFECYCLE','DIRECT_DOCUMENT','CHAT_DELIBERATION','DRAFT_MATERIALIZATION','MAINTENANCE']);
}

const extensionPath = fileURLToPath(import.meta.url);
// Host lives at <root>/skills/_core/deliberation/engine/proposal-workspace.ts,
// so the installed project root is four directories up from here. It was three
// while the engine sat inside the one skill that used it; moving it into `_core`
// added a level, and nothing in the suite would have caught that -- every test
// passes `projectRoot` explicitly, so this constant is only reached in real use.
const installedProjectRoot = resolve(dirname(extensionPath), '..', '..', '..', '..');

const errorCategory=(result:any)=>result.category??(/MODEL|PLANNER/.test(result.reason??'')?'model':/PUBLISH|DERIVED/.test(result.reason??'')?'publication':result.status==='ambiguous'||result.status==='needs-clarification'?'validation':'recovery');
const WITHDRAWAL_OPERATION_ID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
function lifecycleOperationId(result:any){const candidate=typeof result?.operationId==='string'?result.operationId:typeof result?.backupLocation==='string'?result.backupLocation.split('/').at(-1):undefined;return typeof candidate==='string'&&WITHDRAWAL_OPERATION_ID.test(candidate)?candidate:null;}
export function projectRevisionLifecyclePublicResult(result:any){
 const operation=result?.operation==='RESTORE_WITHDRAWN_REVISION'?'RESTORE_WITHDRAWN_REVISION':'WITHDRAW_REVISION';
 const status=['withdrawn','restored','blocked','ambiguous'].includes(result?.status)?result.status:'blocked';
 return {status,operation,withdrawnFilename:typeof result?.withdrawnFilename==='string'?result.withdrawnFilename:null,restoredLatestFilename:typeof result?.restoredLatestFilename==='string'?result.restoredLatestFilename:null,operationId:lifecycleOperationId(result),artifactCount:Number.isSafeInteger(result?.artifactCount)&&result.artifactCount>=0?result.artifactCount:0,backupLocation:typeof result?.backupLocation==='string'?result.backupLocation:null,auditStatus:['PASS','WARN','FAIL','NOT_RUN'].includes(result?.auditStatus)?result.auditStatus:'NOT_RUN',selfAuditStatus:['PASS','WARN','FAIL','NOT_RUN'].includes(result?.selfAuditStatus)?result.selfAuditStatus:'NOT_RUN',modelCalls:0,plannerCalls:0,warnings:Array.isArray(result?.warnings)?result.warnings.filter((warning:any)=>typeof warning==='string').slice(0,16):[],...(status==='ambiguous'&&typeof result?.question==='string'?{question:result.question}:{})};
}

/** Projects lifecycle-v1 records without falling back to filename-era withdrawal state. */
export function projectLifecycleV1PublicResult(operation:'WITHDRAW_REVISION'|'RESTORE_WITHDRAWN_REVISION',requestId:string,result:any){
 if(result?.outcome==='COMMITTED'||result?.outcome==='ALREADY_COMMITTED'){
  const inventory=result.inventory;
  const revisionId=result.revision?.revisionId??result.withdrawal?.revisionId??null;
  const withdrawalId=result.withdrawalId??result.withdrawal?.withdrawalId??null;
  const lifecycleState=inventory.lifecycleState;
  const activeRevisionId=inventory.activeRevisionId??null;
  const transitionEvidence={operation,requestId,outcome:'committed' as const,lifecycleState,activeRevisionId,revisionId,withdrawalId};
  return {status:operation==='WITHDRAW_REVISION'?'withdrawn':'restored',operation,requestId,revisionId,withdrawalId,lifecycleState,activeRevisionId,transitionEvidence,auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',modelCalls:0,plannerCalls:0,warnings:[]};
 }
 const semanticCode=typeof result?.code==='string'?result.code:'LIFECYCLE_INVENTORY_INCONSISTENT';
 const transitionEvidence={operation,requestId,outcome:'rejected' as const,semanticCode};
 return {status:'blocked',operation,requestId,revisionId:null,withdrawalId:null,lifecycleState:null,activeRevisionId:null,semanticCode,transitionEvidence,auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',modelCalls:0,plannerCalls:0,warnings:[]};
}

export function projectProposalDeliberationPublicResult(input:{result:any;operation:string;sourceFilename?:string;instruction?:string;metricsBefore:any;metricsAfter:any;audit?:any;selfAudit?:any}){
 const {result}=input,delta=(key:string)=>Math.max(0,(input.metricsAfter[key]??0)-(input.metricsBefore[key]??0));
 const calls={modelCalls:result.modelCalls??delta('totalModelCalls'),plannerCalls:result.plannerCalls??delta('totalPlannerCalls'),tutorCalls:delta('totalTutorCalls'),reviewerCalls:delta('totalReviewerCalls')};
 const base={operation:input.operation,sourceFilename:result.published?.sourceFilename??result.sourceFilename??input.sourceFilename??null,...calls,mutations:result.mutations??0,warnings:input.audit?.warnings??[]};
 if(result.status==='awaiting_acceptance')return {...base,status:'awaiting_acceptance',targetFilename:result.targetFilename,acceptanceToken:result.acceptanceToken,patchCount:result.patchCount,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'accept_successor',...(typeof input.instruction==='string'?{instructionBudget:instructionBudget(input.instruction)}:{}),...(result.mathDelta?{mathDelta:result.mathDelta,preservationDelta:result.preservationDelta}:{}),...(result.staleCompanionReferences?{staleCompanionReferences:result.staleCompanionReferences}:{})};
 if(result.status==='published'){
  const unresolved=input.audit?.status==='FAIL'||input.selfAudit?.status==='FAIL';
  return {...base,status:unresolved?'blocked':'published',...(unresolved?{category:'audit',message:'Terminal audit failed; inspect the receipt before retrying.'}:{}),targetFilename:result.published.targetFilename,targetSha256:result.published.publishedSha256,patchCount:result.published.patchCount,receiptId:`${result.published.targetFilename}:${result.published.targetRevision}`,manifestStatus:result.derived.derivedStateManifest.status,auditStatus:input.audit?.status??'NOT_RUN',selfAuditStatus:input.selfAudit?.status??'NOT_RUN',recoveryStatus:unresolved?'required':'not_required',nextAction:unresolved?'inspect_receipt':null,...(result.staleCompanionReferences?{staleCompanionReferences:result.staleCompanionReferences}:{})};
 }
 // A preview refused by the accept turn's own pre-publish validation names that refusal (its
 // code, message and repair step), never a bare CANDIDATE_VALIDATION_FAILED the caller cannot act on.
 const candidateRefusal=result.reason==='CANDIDATE_VALIDATION_FAILED'&&result.validation?.candidateValidation?.status==='failed'?result.validation.candidateValidation as CandidateValidationFailure:null;
 return {...base,status:result.status,category:errorCategory(result),message:result.reason??result.question??'Execution did not complete.',patchCount:0,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:result.status==='published-derived-failed'?'required':'not_required',nextAction:result.status==='budget_block'?'reduce_request_or_raise_budget':result.status==='needs-clarification'||result.status==='ambiguous'?'clarify_request':candidateRefusal?'repair_candidate':'inspect_error',...(candidateRefusal?{blockers:[{code:candidateRefusal.code,message:`${candidateRefusal.message.replace(/\.?$/,'.')} ${candidateRefusal.nextStep}`}]}:{}),...(result.assessment?{assessment:result.assessment}:{}),...(Array.isArray(result.alternatives)?{alternatives:result.alternatives}:{}),...(Array.isArray(result.risks)?{risks:result.risks}:{}),...(Array.isArray(result.unresolvedQuestions)?{unresolvedQuestions:result.unresolvedQuestions}:{}),...(result.budget?{budget:result.budget}:{}),...(Array.isArray(result.outsideSelection)?{outsideSelection:result.outsideSelection}:{})};
}

/**
 * `tutor`/`reviewer`/`semanticPlanner` are the SAME injectable ports
 * `orchestrator.ts`/`chat-deliberation.ts` already accept (design
 * `sdd/proposal-deliberation-ambient-model`, SLICE 2): the ambient-model paradigm
 * removed the separate real-API production implementations of these roles, so
 * production no longer wires a default. The primary CREATE_SUCCESSOR path
 * (keyless CLI, `resolvedDecisions`) never needs them; CHAT_DELIBERATION and
 * the legacy non-ambient model-planner path fail closed (`TUTOR_REQUIRED`/
 * `REVIEWER_REQUIRED`/`CONCEPTUAL_PLANNER_REQUIRED`) unless a caller (a host,
 * or a test) supplies scripted adapters here.
 */
export type ProposalDeliberationExtensionOptions = { projectRoot?: string; lifecycleV1?: { workspaceId: string }; operationGuard?: DocumentOperationGuard; draftMaterialization?: DraftMaterializationPolicy; draftRegistry?: PiSessionDraftRegistry; draftLifecycle?: PiSessionDraftLifecycleAdapter; successorAcceptanceRegistry?: SuccessorAcceptanceRegistry; tutor?: TutorAdapter; reviewer?: ReviewerAdapter; semanticPlanner?: SemanticEditPlanner };

/** Creates the registered public-tool composition for the installed project or an explicitly hosted workspace. */
export function createProposalDeliberationExtension(options: ProposalDeliberationExtensionOptions = {}): (pi: ExtensionAPI) => void {
 return function proposalWorkspaceExtension(pi: ExtensionAPI): void {
 const projectRoot=options.projectRoot??installedProjectRoot;
 const operationGuard=options.operationGuard??createDocumentOperationGuard(projectRoot);
 const proposalWorkspace=createProposalWorkspaceTool(projectRoot,{operationGuard});
 const adapter=new ProposalWorkspaceAdapter(projectRoot,operationGuard,proposalWorkspace);
 // Ambient-model paradigm (design `sdd/proposal-deliberation-ambient-model`, SLICE 2): no production
 // real-API tutor/reviewer/planner is wired by default anymore -- these are the same
 // injectable ports the deterministic/scripted-adapter test suites already use. A host or
 // test supplies them via `options`; omitting them leaves the model-backed routes (chat
 // tutor loop, the legacy non-ambient CREATE_SUCCESSOR planner path) failing closed rather
 // than calling out to a real API.
 const tutor=options.tutor;
 const reviewer=options.reviewer;
 const successorAcceptanceRegistry=options.successorAcceptanceRegistry??createSuccessorAcceptanceRegistry();
 const orchestrator=new ProposalDeliberationOrchestrator(projectRoot,adapter,undefined,options.semanticPlanner,{tutor,reviewer},undefined,undefined,successorAcceptanceRegistry);
 const draftRegistry=options.draftRegistry??getSharedPiSessionDraftRegistry();
 const draftLifecycle=options.draftLifecycle??defaultPiSessionDraftLifecycleAdapter;
 const chatDeliberation=new ChatDeliberationService(tutor,draftRegistry,reviewer);
 const draftMaterialization=new DraftMaterializationService(projectRoot,operationGuard,options.draftMaterialization);
 const lifecycleV1Router=options.lifecycleV1?.workspaceId
  ?new LifecycleV1PublicRouter({projectRoot,workspaceId:options.lifecycleV1.workspaceId})
  :undefined;
 // CREATE_INITIAL_REVISION (spec I1): independent of any canonical-metadata option. The existing-proposal check
 // and publication are both injectable ports so the full creation logic is unit-testable without a real
 // filesystem; production wiring uses the real managed directory below.
 const initialRevisionCreation=new InitialRevisionCreationService(
  {hasManagedProposal:async()=>(await safeResolveLatestManagedRevision(projectRoot)).status!=='empty'},
  createFilesystemInitialRevisionPublicationPort(projectRoot),
 );
 let runtimeSessionIdentity:string|undefined;
 const sessionIdentity=(ctx:Pick<ExtensionContext,'sessionManager'>)=>runtimeSessionIdentity=draftLifecycle.sessionIdentity(ctx);
 pi.registerTool(createDocumentOperationGuardTool(operationGuard));
 pi.registerTool(proposalWorkspace);
 pi.registerTool({
  name:'proposal_deliberation_execute',
  label:'Execute Proposal Deliberation V2',
  description:'Execute a bounded Proposal Deliberation V2 chat, explicitly authorized draft creation, document change, or managed-revision lifecycle request.',
  promptSnippet:'Deliberate conversationally or execute a resolved Proposal Deliberation V2 instruction.',
  promptGuidelines:['Use operation CHAT_DELIBERATION for non-mutating tutor conversation; it is session-local, mode-first, and cannot mint document or task authority. Materialize chat only with draftMaterialization INITIAL_CREATE plus explicit current-turn authorization and an exact validated route or approval of the pending proposed route; UPDATE and REPLACE are forbidden. Use document mutation verbs only for explicit principal-local managed edits, which retain exact target resolution and guarded publication. Use operation CREATE_INITIAL_REVISION, with instruction as the idea, only to explicitly create the first managed proposal (v1); it never runs automatically and is rejected outright whenever a managed proposal already exists. MAINTENANCE is an explicit external-controller handoff only; V2 does not create or resume workers or grant document authority. For managed-revision withdrawal or restore, pass the typed lifecycle operation and an exact sourceFilename or restore withdrawalOperationId; omit withdrawalOperationId for withdrawal because V2 generates it. Supply only user-facing semantic selectors and content; never construct patches, offsets, manifests, receipts, or internal revision mechanics.'],
  parameters:Type.Object({
   instruction:Type.String({minLength:1,maxLength:MAX_INSTRUCTION_CHARACTERS}),
   operation:Type.Optional(StringEnum(['WITHDRAW_REVISION','RESTORE_WITHDRAWN_REVISION','CREATE_SUCCESSOR','CREATE_INITIAL_REVISION','ADOPT_INITIAL_REVISION','CHAT_DELIBERATION','CLOSE_DELIBERATION','MAINTENANCE'] as const,{description:'Explicit lifecycle, managed-successor edit, explicit first-managed-version creation, session-local chat, explicit chat close, external-maintenance handoff, or persistent scientific-workflow operation. Omit for existing direct-document classification.'})),
       editIntent:Type.Optional(StringEnum(['MODIFY','CONCEPTUAL_REVISION'] as const,{description:'Required only with CREATE_SUCCESSOR; identifies the bounded inner document edit.'})),
       sectionRange:Type.Optional(Type.String({minLength:5,maxLength:64,pattern:'^(?:sections?\\s+)?\\d+(?:\\.\\d+)*\\s*[–-]\\s*\\d+(?:\\.\\d+)*$',description:'Required only with CREATE_SUCCESSOR. Exact numbered Markdown-heading range, for example sections 1–2.2.'})),
       acceptSuccessor:Type.Optional(Type.Boolean({description:'Set true only for an explicit current-turn acceptance of a previously previewed successor.'})),
       successorAcceptanceToken:Type.Optional(Type.String({minLength:32,maxLength:128,pattern:'^[A-Za-z0-9_-]+$',description:'Opaque token forwarded internally from the immediately preceding successor preview.'})),
   selectedEntryId:Type.Optional(Type.String({minLength:1,maxLength:256})),
   resolvedDecisions:Type.Optional(Type.Array(Type.Unknown(),{description:'CREATE_SUCCESSOR + MODIFY only (ambient-model paradigm): one already-resolved EditAction per approved locus, supplied by the caller instead of a separate model call. Routes through the ambient-supplied echo-and-validate planner; no model/network call happens on this path.'})),
   sourceFilename:Type.Optional(Type.String({minLength:1,maxLength:266,pattern:managedRevisionSchemaPattern({directoryPrefix:true}),description:`For CHAT_DELIBERATION, pass an exact managed revision filename or the same filename prefixed once by ${PROPOSAL_DIRECTORY}/. Paths are never normalized.`})),
   sourceQuery:Type.Optional(Type.String({minLength:1,maxLength:4096})),
   destinationQuery:Type.Optional(Type.String({minLength:1,maxLength:4096})),
   position:Type.Optional(StringEnum(['before','after','inside_start','inside_end'] as const)),
   adaptive:Type.Optional(Type.Boolean()),
   literalContent:Type.Optional(Type.String({minLength:1,maxLength:65536})),
   expectedSourceSha256:Type.Optional(Type.String({pattern:'^[a-f0-9]{64}$'})),
   withdrawalOperationId:Type.Optional(Type.String({minLength:36,maxLength:36,pattern:'^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'})),
   withdrawalReason:Type.Optional(Type.String({minLength:1,maxLength:500})),
       conversationId:Type.Optional(Type.String({minLength:5,maxLength:256,pattern:'^chat-[a-z0-9][a-z0-9-]{0,250}$'})),
       confirmBase:Type.Optional(Type.Boolean({description:'CHAT_DELIBERATION only: confirms the auto-proposed latest managed revision as this new deliberation\'s base, returned by a prior base_confirmation_required response. Omit or override with sourceFilename instead.'})),
       draftMaterialization:Type.Optional(Type.Object({
        operation:StringEnum(['INITIAL_CREATE','UPDATE','REPLACE'] as const,{description:'Only INITIAL_CREATE is authorized for chat materialization; UPDATE and REPLACE are explicit fail-closed values.'}),
        route:Type.Optional(Type.String({minLength:1,maxLength:512,description:'Exact project-relative route. It is never normalized or rewritten on the caller’s behalf.'})),
        approveProposedRoute:Type.Optional(Type.Boolean({description:'Approve the exact route previously proposed for this conversation.'})),
        authorized:Type.Boolean({description:'Explicit current-turn authorization for INITIAL_CREATE.'}),
        metadata:Type.Optional(Type.Object({slug:Type.Optional(Type.String({minLength:1,maxLength:80})),purpose:Type.Optional(Type.String({minLength:1,maxLength:80})),revision:Type.Optional(Type.String({minLength:1,maxLength:40})),extension:Type.Optional(Type.String({minLength:2,maxLength:12}))},{additionalProperties:false})),
       },{additionalProperties:false})),
       maintenanceTaskId:Type.Optional(Type.String({minLength:13,maxLength:256,pattern:'^maintenance-[a-z0-9][a-z0-9-]{0,242}$'})),
       idempotencyKey:Type.Optional(Type.String({minLength:1,maxLength:256})),
       rationale:Type.Optional(Type.String({minLength:1,maxLength:MAX_RATIONALE_CHARACTERS,description:'CREATE_SUCCESSOR only: why the change was made, recorded verbatim in the successor receipt. Optional.'})),
       decider:Type.Optional(StringEnum(['agent','human'] as const,{description:'CREATE_SUCCESSOR only: who took the decision, recorded in the successor receipt. Optional.'})),
       sourceWindowBytes:Type.Optional(Type.Integer({minimum:1,maximum:MAX_SOURCE_WINDOW_BYTES,description:'CREATE_INITIAL_REVISION only: how many bytes of the declared sources, in total and in declaration order, v1 reads (default 4000). Refused on every other operation.'})),
       dryRun:Type.Optional(Type.Boolean({description:'CREATE_INITIAL_REVISION only: run every check and compose the first revision, then stop before the creation lock and any write (status preview). Refused on every other operation.'})),
  }),
  async execute(_toolCallId,params,_signal,_onUpdate,ctx){
   /** ADOPT_INITIAL_REVISION: an existing document becomes v1 under CREATE_INITIAL_REVISION's own gate, state and receipt (`adoptInitialRevision`). */
   const runAdoption=async(request:{sourceFilename?:unknown;dryRun?:boolean})=>{
    const authority=resolveV2ExecutionAuthority('CREATE_INITIAL_REVISION');
    const base={operation:ADOPT_INITIAL_REVISION_OPERATION,routeStage:'CREATE_INITIAL_REVISION',authority,sourceFilename:typeof request.sourceFilename==='string'?request.sourceFilename:null};
    const result=await adoptInitialRevision({projectRoot,sourceFilename:request.sourceFilename,dryRun:request.dryRun===true,hasManagedProposal:async()=>(await safeResolveLatestManagedRevision(projectRoot)).status!=='empty'});
    if(result.status==='preview')return {...base,status:'preview' as const,dryRun:true as const,mode:result.mode,targetFilename:result.filename,targetRevision:result.revision,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'adopt_initial_revision'};
    if(result.status==='adopted'){
     let auditStatus='FAIL';
     try{auditStatus=(await runConsistencyAudit({projectRoot})).status;}catch{auditStatus='FAIL';}
     return {...base,status:'adopted' as const,mode:result.mode,targetFilename:result.filename,targetRevision:result.revision,targetSha256:result.documentSha256,mutations:1 as const,receiptId:`${result.filename}:${result.revision}`,manifestStatus:'COMMITTED',auditStatus,selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:result.mode==='rename'?'move_adopted_source_to_backup':null,...(result.mode==='rename'?{sourceLeftInPlace:true}:{})};
    }
    const blockers='detail' in result
     ?{nextAction:result.code==='ADOPTION_ALREADY_RECORDED'||result.code==='MANAGED_PROPOSAL_ALREADY_EXISTS'?'use_existing_managed_proposal':'fix_adoption_source',blockers:[{code:result.code,message:`${result.detail} Nothing was written.`}]}
     :projectInitialRevisionRefusal(result);
    return {...base,status:'blocked' as const,targetFilename:null,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',...blockers};
   };
   // The schema's `maxLength`, enforced on every host: refused before any route runs, nothing written.
   if(typeof params.instruction==='string'&&params.instruction.length>MAX_INSTRUCTION_CHARACTERS){
    const publicResult={status:'blocked' as const,operation:params.operation??null,targetFilename:null,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'shorten_instruction',instructionBudget:instructionBudget(params.instruction),blockers:[{code:'INSTRUCTION_TOO_LONG',message:`instruction is ${params.instruction.length} characters; every operation accepts at most ${MAX_INSTRUCTION_CHARACTERS}. Nothing was written. Shorten it, or move long reference material into a declared source instead of the instruction.`}]};
    return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
   }
   // A dry run exists only where an operation has no preview of its own; anywhere else it would
   // silently mutate a caller who believed nothing would be written, so it is refused instead.
   const decisionRecordRefusal=decisionRecordBlocker(params as {operation?:string;rationale?:unknown;decider?:unknown});
   if(decisionRecordRefusal){
    const publicResult={status:'blocked' as const,operation:params.operation??null,targetFilename:null,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'fix_decision_record',blockers:[decisionRecordRefusal]};
    return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
   }
   if((params as {sourceWindowBytes?:unknown}).sourceWindowBytes!==undefined&&params.operation!==CREATE_INITIAL_REVISION_OPERATION){
    const publicResult={status:'blocked' as const,operation:params.operation??null,targetFilename:null,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'drop_source_window',blockers:[{code:'SOURCE_WINDOW_UNSUPPORTED',message:'sourceWindowBytes applies only to CREATE_INITIAL_REVISION, the one operation that reads the declared sources into a document; nothing was run.'}]};
    return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
   }
   if(params.dryRun!==undefined&&!DRY_RUN_OPERATIONS.has(params.operation??'')){
    const publicResult={status:'blocked' as const,operation:params.operation??null,targetFilename:null,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'drop_dry_run',blockers:[{code:'DRY_RUN_UNSUPPORTED',message:`dryRun applies only to ${[...DRY_RUN_OPERATIONS].join(', ')}; nothing was run. CREATE_SUCCESSOR previews without it; STATUS and RESOLVE_TARGET never write.`}]};
    return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
   }
   if(params.operation===ADOPT_INITIAL_REVISION_OPERATION){
    const publicResult=await runAdoption(params as {sourceFilename?:unknown;dryRun?:boolean});
    return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
   }
   const openDeliberation=params.conversationId?chatDeliberation.isOpen(sessionIdentity(ctx),params.conversationId):false;
   const route=resolveGlobalRoute({...params,openDeliberation});
   if(route.stage==='DRAFT_MATERIALIZATION'){
    const conversationId=params.conversationId??'';
    const currentSessionIdentity=sessionIdentity(ctx);
    const materializationPayload=conversationId?draftRegistry.get(currentSessionIdentity,conversationId):undefined;
    const result=await draftMaterialization.execute({conversationId,materializationPayload,request:params.draftMaterialization!});
    // D5: a direct materialization terminates the conversation's own deliberation state, not merely the draft-registry entry.
    if(result.status==='materialized'&&conversationId)chatDeliberation.close(currentSessionIdentity,conversationId);
    const publicResult={...result,operation:result.operation,routeStage:'DOCUMENT_EDIT',transition:'CHAT_DELIBERATION_TO_DOCUMENT_EDIT',authority:resolveV2ExecutionAuthority(route.stage),conversationId:params.conversationId??null,modelCalls:0,plannerCalls:0,tutorCalls:0,reviewerCalls:0,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required'};
    return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
   }
   if(route.stage==='CHAT_DELIBERATION'){
    // Task D2 (five-guards-that-cannot-fire): this early return is why
    // `resolveEffectiveOperationProfile` never throws for CLOSE_DELIBERATION.
    // `role-budget.ts` declares `BudgetedIntent = Exclude<Intent,'CLOSE_DELIBERATION'>`,
    // so `operationProfile` (which mirrors `roleBudgets`) has no entry for
    // CLOSE_DELIBERATION, and `resolveEffectiveOperationProfile` would throw
    // `UNSUPPORTED_OPERATION_PROFILE` if it were ever called with that intent.
    // CLOSE_DELIBERATION never reaches it: this branch handles and returns
    // before the orchestrator's publish path -- the only caller of
    // `resolveEffectiveOperationProfile` -- is ever entered. Ships unguarded
    // by design (spec requirement A5): a test asserting this comment's text
    // would guard bytes, not behavior.
    if(params.operation==='CLOSE_DELIBERATION'){
     const currentSessionIdentity=sessionIdentity(ctx);
     const closeResult=chatDeliberation.close(currentSessionIdentity,params.conversationId??'');
     const publicResult={operation:'CLOSE_DELIBERATION',routeStage:'CHAT_DELIBERATION',authority:resolveV2ExecutionAuthority(route.stage),...closeResult};
     return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
    }
    // Interactive base confirmation (spec I4, user requirement 3): gates only the very first turn of a
    // NEW deliberation, and only when the caller has not already named an explicit base via sourceFilename.
    // Auto-identifies the latest managed revision via the unified resolver -- never a hardcoded name/path --
    // and requires the caller to confirm it (confirmBase:true) or override it (sourceFilename) before the
    // tutor runs. This also satisfies "load prior materialized version as base": whatever is currently the
    // latest managed revision (e.g. after a prior deliberation's materialization) is what gets proposed.
    if(!openDeliberation&&!params.sourceFilename&&!params.confirmBase){
     const baseResolution=await safeResolveLatestManagedRevision(projectRoot);
     if(baseResolution.status!=='empty'){
      const authority=resolveV2ExecutionAuthority(route.stage);
      const publicResult=baseResolution.status==='multiple'
       ?{status:'base_confirmation_required' as const,operation:'CHAT_DELIBERATION',routeStage:'CHAT_DELIBERATION',authority,conversationId:params.conversationId??null,warnings:['MULTIPLE_ACTIVE_REVISIONS'],candidates:baseResolution.candidates.map(c=>c.filename),modelCalls:0,tutorCalls:0,reviewerCalls:0,mutations:0,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'confirm_or_override_base',question:'Multiple active revisions were found. Pass one exact filename as sourceFilename to select the base.'}
       :{status:'base_confirmation_required' as const,operation:'CHAT_DELIBERATION',routeStage:'CHAT_DELIBERATION',authority,conversationId:params.conversationId??null,proposedBase:baseResolution.latest.filename,modelCalls:0,tutorCalls:0,reviewerCalls:0,mutations:0,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'confirm_or_override_base',question:`Use ${baseResolution.latest.filename} as the deliberation base? Resend with confirmBase:true to accept it, or sourceFilename to override.`};
      return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
     }
     // status 'empty' -- no managed proposal exists yet; nothing to confirm, proceed document-less as before.
    }
    const confirmedBaseResolution=params.sourceFilename||!params.confirmBase?undefined:await safeResolveLatestManagedRevision(projectRoot);
    const effectiveSourceFilename=params.sourceFilename??(confirmedBaseResolution&&confirmedBaseResolution.status!=='empty'?confirmedBaseResolution.latest.filename:undefined);
    // FORBIDDEN is mutation authority: an explicitly selected managed document may be loaded as immutable tutor context only.
    const resolvedDocument=resolveChatDocumentFilename(effectiveSourceFilename);
    const chatDocument:{filename?:string;document?:ChatDocumentContext;reason?:string}=resolvedDocument.filename?await loadChatDocumentContext(projectRoot,resolvedDocument.filename):resolvedDocument;
    // Paper-guide initial context (task 3.5/3.6, spec I2): loaded once, only for this conversation's first turn.
    const guideFragments=!openDeliberation?await loadGuideDirectoryFragments(projectRoot):[];
    const result=chatDocument.reason
     ?{status:'blocked' as const,conversationId:params.conversationId??'chat-unresolved',alternatives:[],risks:[],unresolvedQuestions:[],context:{turnCount:0,reusedConclusion:false},modelCalls:0,tutorCalls:0,reviewerCalls:0,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED' as const,auditStatus:'NOT_RUN' as const,selfAuditStatus:'NOT_RUN' as const,recoveryStatus:'not_required' as const,nextAction:'clarify_request' as const,reason:chatDocument.reason}
     :await chatDeliberation.deliberate({instruction:params.instruction,sessionIdentity:sessionIdentity(ctx),...(params.conversationId?{conversationId:params.conversationId}:{}),...(chatDocument.document?{document:chatDocument.document}:{}),...(guideFragments.length?{guideFragments}:{})});
    const {reason,...publicChat}=result;
    const calls={plannerCalls:0,tutorCalls:result.tutorCalls,reviewerCalls:result.reviewerCalls};
    const authority=resolveV2ExecutionAuthority(route.stage);
    const publicResult=result.status==='blocked'
     ?{operation:'CHAT_DELIBERATION',routeStage:'CHAT_DELIBERATION',authority,...publicChat,...calls,category:/MODEL|PRODUCTION/.test(reason??'')?'model':'validation',message:reason??'Chat deliberation did not complete.'}
     :{operation:'CHAT_DELIBERATION',routeStage:'CHAT_DELIBERATION',authority,...publicChat,...calls};
    return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
   }
   if(route.stage==='MAINTENANCE'){
    const authority=resolveV2ExecutionAuthority(route.stage);
    const maintenanceTaskId=params.maintenanceTaskId;
    const publicResult=maintenanceTaskId!==undefined&&!/^maintenance-[a-z0-9][a-z0-9-]{0,242}$/.test(maintenanceTaskId)
     ?{status:'blocked',operation:MAINTENANCE_OPERATION,routeStage:'MAINTENANCE',authority,maintenanceTaskId:null,mutations:0,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'supply_maintenance_task_id',blockers:[{code:'MAINTENANCE_TASK_ID_INVALID',message:'Maintenance handoff requires a maintenance-prefixed task ID.'}]}
     :{status:'delegation_permitted',operation:MAINTENANCE_OPERATION,routeStage:'MAINTENANCE',authority,maintenanceTaskId:maintenanceTaskId??null,mutations:0,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'handoff_to_maintenance_controller'};
    return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
   }
   if(route.stage==='CREATE_INITIAL_REVISION'){
    const authority=resolveV2ExecutionAuthority(route.stage);
    // Required sources (change 7): a `required: true` source that is absent -- or present
    // and holding no document at all -- blocks here, before any fragment is loaded and
    // before any v1 is rendered. Never a silent `[]`, and never a bare directory passing
    // for content it does not hold.
    const missingSources=await missingRequiredSources(projectRoot);
    if(missingSources.length){
     const publicResult={status:'blocked' as const,operation:CREATE_INITIAL_REVISION_OPERATION,routeStage:'CREATE_INITIAL_REVISION',authority,targetFilename:null,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'supply_required_source',blockers:missingSources.map((source)=>source.reason==='absent'
      ?{code:'REQUIRED_SOURCE_MISSING',message:`Required source "${source.path}" is missing; CREATE_INITIAL_REVISION cannot proceed without it.`}
      :{code:'REQUIRED_SOURCE_EMPTY',message:`Required source "${source.path}" exists but holds no Markdown document; CREATE_INITIAL_REVISION cannot proceed without its content. Ingest at least one document into it, as "${source.path}/<name>/<name>.md" or as a Markdown file directly inside it.`})};
     return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
    }
    const windowRequest=params.sourceWindowBytes;
    if(windowRequest!==undefined&&!(typeof windowRequest==='number'&&Number.isInteger(windowRequest)&&windowRequest>=1&&windowRequest<=MAX_SOURCE_WINDOW_BYTES)){
     const publicResult={status:'blocked' as const,operation:CREATE_INITIAL_REVISION_OPERATION,routeStage:'CREATE_INITIAL_REVISION',authority,targetFilename:null,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'fix_source_window',blockers:[{code:'SOURCE_WINDOW_INVALID',message:`sourceWindowBytes must be an integer from 1 to ${MAX_SOURCE_WINDOW_BYTES}; got ${JSON.stringify(windowRequest)}. Nothing was composed.`}]};
     return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
    }
    const window=await loadSourceWindow(projectRoot,windowRequest??MAX_CHAT_GUIDE_CONTEXT_BYTES);
    const guideFragments=window.fragments;
    const windowWarnings=sourceWindowWarnings(window.report);
    const windowFields={sourceWindow:window.report,...(windowWarnings?{warnings:windowWarnings}:{})};
    const dryRun=params.dryRun===true;
    const result=await initialRevisionCreation.execute({idea:params.instruction,...(guideFragments.length?{guideFragments}:{}),...(dryRun?{dryRun}:{})});
    if(result.status==='preview'){
     // The real call would also take the slug-independent creation lock; predict its refusal
     // rather than report a v1 that could never be created. The lock itself is never touched.
     const lock=await initialRevisionLockState(projectRoot);
     const publicResult=lock.present
      ?{status:'blocked' as const,operation:CREATE_INITIAL_REVISION_OPERATION,routeStage:'CREATE_INITIAL_REVISION',authority,dryRun:true as const,targetFilename:null,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'use_existing_managed_proposal',blockers:[{code:'MANAGED_PROPOSAL_ALREADY_EXISTS',message:`The creation lock ${lock.path} is present, so a real CREATE_INITIAL_REVISION would be refused. It records that a first revision was already created here; it is never removed by the engine.`}]}
      :{status:'preview' as const,operation:CREATE_INITIAL_REVISION_OPERATION,routeStage:'CREATE_INITIAL_REVISION',authority,dryRun:true as const,targetFilename:result.filename,targetRevision:result.revision,canonicalMetadata:result.canonicalMetadata,markdown:result.markdown,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:'create_initial_revision',instructionBudget:instructionBudget(params.instruction),...windowFields};
     return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
    }
    const publicResult=result.status==='created'
     ?{status:'created' as const,operation:CREATE_INITIAL_REVISION_OPERATION,routeStage:'CREATE_INITIAL_REVISION',authority,targetFilename:result.filename,targetRevision:result.revision,targetSha256:result.documentSha256,canonicalMetadata:result.canonicalMetadata,mutations:1 as const,receiptId:`${result.filename}:${result.revision}`,manifestStatus:'NOT_TRACKED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',nextAction:null,instructionBudget:instructionBudget(params.instruction),...windowFields}
     :{status:'blocked' as const,operation:CREATE_INITIAL_REVISION_OPERATION,routeStage:'CREATE_INITIAL_REVISION',authority,targetFilename:null,mutations:0 as const,receiptId:null,manifestStatus:'NOT_PUBLISHED',auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',recoveryStatus:'not_required',...projectInitialRevisionRefusal(result),...windowFields};
    return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
   }
   const resolvedIntent=resolveIntent(params.instruction).intent;
   const requestedOperation=params.operation??resolvedIntent;
   /* `lifecycle` is `route.stage==='LIFECYCLE'`, which resolveGlobalRoute only selects when the explicit operation or the resolved intent is already in LIFECYCLE_OPERATIONS; line 5786 then keeps it or falls back to that same resolved intent, so both arms are lifecycle operations here */
   const lifecycle=route.stage==='LIFECYCLE';
   const operation=lifecycle?(LIFECYCLE_OPERATIONS.has(requestedOperation)?requestedOperation:resolvedIntent):requestedOperation;
   const metricsBefore=getRuntimeMetrics();
   if(lifecycle&&lifecycleV1Router){
    const requestId=params.idempotencyKey??randomUUID();
    const result=operation==='WITHDRAW_REVISION'
     ?await lifecycleV1Router.execute({operation,requestId,locator:params.sourceFilename,reason:params.withdrawalReason})
     :await lifecycleV1Router.execute({operation:'RESTORE_WITHDRAWN_REVISION',requestId,withdrawalId:params.withdrawalOperationId,reference:params.sourceFilename});
    recordLifecycleMetric(operation==='WITHDRAW_REVISION'
     ?(result.outcome==='COMMITTED'||result.outcome==='ALREADY_COMMITTED'?'withdrawal_committed':'withdrawal_rejected')
     :(result.outcome==='COMMITTED'||result.outcome==='ALREADY_COMMITTED'?'restore_committed':'restore_rejected'));
    const publicResult=projectLifecycleV1PublicResult(operation as 'WITHDRAW_REVISION'|'RESTORE_WITHDRAWN_REVISION',requestId,result);
    return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
   }
   // `resolvedDecisions` is declared `Type.Array(Type.Unknown())` in the schema above because the
   // payload is untrusted JSON; its element contract is `EditAction`, enforced at runtime inside
   // `ambient-supplied-planner.ts` (`parseProposedEdit`, `allowedKeysFor`, `unexpectedKeys`), which is
   // what `V2Request.resolvedDecisions` declares. Restated here at that parse boundary only.
   const {operation:_operation,conversationId,draftMaterialization:_draftMaterialization,maintenanceTaskId:_maintenanceTaskId,idempotencyKey:_idempotencyKey,...existingParams}=params as Omit<typeof params,'resolvedDecisions'>&{resolvedDecisions?:readonly EditAction[]};
   const priorConclusion=route.stage==='DIRECT_DOCUMENT'?chatDeliberation.latestConclusion(conversationId):undefined;
   const conversationSource=operation===CREATE_SUCCESSOR_OPERATION?chatDeliberation.currentManagedDocument(conversationId)?.filename:undefined;
   const executionParams=lifecycle?{...existingParams,operation:operation as 'WITHDRAW_REVISION'|'RESTORE_WITHDRAWN_REVISION'}:{...existingParams,...(operation===CREATE_SUCCESSOR_OPERATION?{operation,sessionIdentity:sessionIdentity(ctx),...(conversationSource&&!params.sourceFilename?{sourceFilename:conversationSource}:{})}:{}),...(priorConclusion?{priorConclusion}:{})};
   const result=await orchestrator.execute(executionParams);
   let audit,selfAudit;
   if(!lifecycle&&result.status==='published'){
    try {
     audit=await runConsistencyAudit({projectRoot});
     selfAudit=await runProposalDeliberationSelfAudit({projectRoot});
    } catch { audit={status:'FAIL',warnings:[]};selfAudit={status:'FAIL'}; }
   }
   const projected=lifecycle?projectRevisionLifecyclePublicResult(result):projectProposalDeliberationPublicResult({result,operation,sourceFilename:params.sourceFilename,instruction:params.instruction,metricsBefore,metricsAfter:getRuntimeMetrics(),audit,selfAudit});
   const publicResult=route.stage==='DIRECT_DOCUMENT'?{...projected,authority:resolveV2ExecutionAuthority(route.stage)}:projected;
   return {content:[{type:'text',text:JSON.stringify(publicResult)}],details:publicResult};
  },
 });
 pi.on('session_start',(_event,ctx)=>{runtimeSessionIdentity=draftLifecycle.sessionIdentity(ctx);});
 pi.on('session_shutdown',(event,ctx)=>{if(draftLifecycle.shouldClearSession(event)){const identity=runtimeSessionIdentity??draftLifecycle.sessionIdentity(ctx);draftRegistry.clearSession(identity);successorAcceptanceRegistry.clearSession(identity);}});
 pi.on('input', async ()=>({action:'continue'}));
 pi.on('tool_call',(event)=>operationGuard.handleToolCall(event));
 pi.on('tool_result',(event)=>operationGuard.handleToolResult(event));
 }
}

export default createProposalDeliberationExtension();
