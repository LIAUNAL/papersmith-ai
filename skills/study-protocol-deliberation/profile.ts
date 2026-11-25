import type { DeliberationDomainProfile } from "../_core/deliberation/engine/domain-profile.js";
import { sha256 } from "../_core/deliberation/engine/types.js";
import { extractAtoms, violations, STATED_RESULT } from "./preservation-study-protocol.js";
import { declares, cites } from "./reference-study-protocol.js";
import { OUTCOME_ID } from "./protocol-fields.js";

/**
 * What the shared deliberation engine needs to know about THIS domain: the third profile,
 * after the mathematical proposal and the experiments plan. The engine gained no line of
 * code to serve it.
 *
 * A STUDY PROTOCOL is a commitment made before any datum exists: the question, the ONE
 * primary outcome, the design, who is eligible, how many and why, and how the primary
 * outcome will be analysed. Everything below follows from that. The fields are labelled
 * lines a parser reads (`protocol-fields.ts`), because a later lock hashes this revision
 * and a later verify compares the manuscript against it; a result stated here is refused,
 * because a protocol that already knows its answer is the HARKing it exists to prevent;
 * and changing what the primary outcome measures is a lost atom the caller must
 * acknowledge, because a silent outcome switch is the failure a protocol is written to
 * make visible.
 *
 * The lock itself (G-STUDY-PROTOCOL: approve or amend, ethics, registration) is not here.
 * It reads the published revision this engine writes and binds to its bytes.
 */

/** Where a dataset's own description lives -- data, never this study's findings. The bound named on a stated-result conflict. */
const DATA_SOURCE = "guidance/data-paper";

/** The methodological / style references, the same optional slot both sibling profiles read. */
const PAPER_GUIDE = "guidance/paper-guide";

export const profile: DeliberationDomainProfile = {
	deriveBase: "study_protocol_base.md",
	baseLabel: "fixed protocol base",
	baseLabelLong: "fixed study protocol base",
	exampleSlug: "supervised-exercise-cohort-v03",
	// The one word this domain names itself by is its own namespace, which no file under
	// `_core/` spells, so the core-scan lock stays meaningful rather than vacuous.
	names: ["study-protocol-deliberation"],
	// Prose cites an outcome as `(Outcome O1)`; the explicit form is `[outcome:O1]`
	// (`reference-study-protocol.ts`). The id is not positional: outcomes are added and
	// demoted by amendment, and a positional number would re-point every citation.
	proseReferencePattern: `\\(Outcome (${OUTCOME_ID})\\)`,
	vocabulary: {
		conceptualTerms: ["study protocol", "primary outcome", "sample size", "analysis plan", "eligibility criteria"],
		// The engine's intent matching is Spanish and shared; only the SUBJECT is this
		// domain's, so each subject word is accepted in both spellings.
		expertPattern: "protocol|protocolo|outcome|desenlace|sample size|muestra|eligibility|elegibilidad|analysis plan|an[aá]lisis|covariate|covariable|multiplicity|multiplicidad|missing data|faltantes",
		// A protocol's numbered displays are its schedule tables and its participant-flow figure.
		displayNounPattern: "tabla|table|figura|figure",
		displayNounStripPattern: "\\b(?:tablas?|tables?|figuras?|figures?)\\b",
		subjectPattern: "outcome|desenlace|sample size|muestra|eligibility|elegibilidad|analysis plan|an[aá]lisis",
		subjectTerms: ["primary outcome", "desenlace primario", "resultado primario"],
		subjectLocusDescription: "protocol field related to the primary outcome",
		subjectEvidenceLabel: "nearby primary outcome declaration",
	},
	artifact: {
		directory: "protocol",
		stem: "study-protocol",
		// `v`, two digits, as the experiments sibling: a revision of a protocol is a version
		// of a plan, and the core's STRICT and LOOSE matchers require `\d{2,}`. The engine's
		// INITIAL matcher requires a lineage slug, so the names are
		// `protocol/study-protocol-<slug>-v01.md`, `-v02.md`, and so on.
		revisionPattern: "v",
		revisionLabel: (ordinal) => `v${String(ordinal).padStart(2, "0")}`,
		sidecarRoot: ".study-protocol-deliberation",
		// Byte-identical to both siblings' marker on purpose: `revision-lifecycle-store.ts`
		// still spells this literal for a Python cross-language guard (see its own comment).
		marker: "<!-- proposal-workspace:artifact:v1 -->\n",
		sourceReferenceHeading: "Reference Sources",
		// Declared: every amendment of a protocol says what changed and why, in the document
		// itself, because the reader holding the manuscript against it has to know.
		changeHeader: {
			heading: "Changes",
			render: (summary) => `## Changes\n\n**What:** ${summary.what}\n\n**Why:** ${summary.why}\n\n`,
		},
	},
	// Advisory, not `'refuse'`: a background section may restate a published result of
	// somebody else's, acknowledged by id on the accept turn. A LABELLED FIELD that states a
	// result is refused outright by `field-states-result` in the preservation gate.
	sourceAuthority: {
		names: [DATA_SOURCE],
		severity: "advisory",
		detectConflicts: (candidateText) => {
			const conflicts: { id: string; sourceName: string; claim: string; evidence: string }[] = [];
			const seen = new Set<string>();
			for (const line of candidateText.split("\n")) {
				const evidence = line.replace(/\s+/gu, " ").trim();
				if (!evidence || !STATED_RESULT.test(evidence)) continue;
				const id = `stated-result:${sha256(evidence).slice(0, 12)}`;
				if (seen.has(id)) continue;
				seen.add(id);
				conflicts.push({
					id,
					sourceName: DATA_SOURCE,
					claim: "a study protocol is written before its data are collected or analysed, so no result of this study may be stated in it; a dataset's description bounds what the data are, never what they show",
					evidence,
				});
			}
			return conflicts;
		},
	},
	preservation: { extractAtoms, violations },
	references: { declares, cites },
	// Both optional. A protocol is drafted with the operator from the agreed idea, so its
	// fields arrive in the idea text of `CREATE_INITIAL_REVISION`, not from a source it
	// cannot start without; and no flow calls this skill until its line arrives.
	//
	//   1. The paper guide -- the methodological references both siblings read.
	//   2. The data paper -- when the study analyses an existing dataset, its description.
	sources: [
		{ path: PAPER_GUIDE, required: false },
		{ path: DATA_SOURCE, required: false },
	],
	objective: {
		// Worded under the core-scan lock's C-3 rule: a word of five letters or more that only
		// this north uses must not appear anywhere in the shared core, so the common words the
		// core already spells ("outcome", "primary", "model") are avoided here. The main
		// endpoint is the `**Primary outcome:**` line; the main analysis is `**Primary model:**`.
		purpose: "carry the study protocol that was discussed as far as a published managed revision -- its aim, its main endpoint, its eligibility, its sample size and its analysis plan, in a document that exists and is the current one",
		stages: [
			{
				stage: "bound",
				establishes: "which revision is current and which entry of it the change touches",
				behindWhen: "`STATUS` named the latest and the target resolved to an entry",
			},
			{
				stage: "validated",
				establishes: "the aim, the main endpoint, the eligibility, the sample size with its justification and the analysis plan are each stated once, none of them stating findings",
				behindWhen: "no main endpoint or two of them, an endpoint with no id, measure or timing, a sample size with no target or no justification, an analysis plan with no main analysis named, or a line stating findings, stops this stage",
			},
			{
				stage: "deliberated",
				establishes: "the change was argued through rather than typed",
				behindWhen: "THE USER SAID SO. Nothing here measures it, and nothing may: an agent that could close this stage on its own word would be approving its own protocol",
			},
			{
				stage: "composed",
				establishes: "the replacement exists written as the protocol, not a description of it",
				behindWhen: "a block exists carrying the change",
			},
			{
				stage: "published",
				establishes: "the successor exists carrying the artifact marker and is the current revision",
				behindWhen: "this is the arrival; it is behind nobody",
			},
		],
		arrival: "the successor revision published and current, which is the only form the study protocol travels in",
		humanStops: [
			"picking the main endpoint, which is the operator's to make and which nothing here infers",
			"accepting the change, which closes the deliberated stage and which nothing here may close on its own",
			"authorizing publication, because it advances the real lineage",
		],
	},
};
