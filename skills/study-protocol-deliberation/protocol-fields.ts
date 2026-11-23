/**
 * The field grammar of a study protocol, and the one parser of it.
 *
 * A protocol is a Markdown managed revision whose decisions are LABELLED LINES: a bold
 * label, optionally carried by a list bullet, and the value as the rest of the line --
 * `**Primary outcome:** O1 -- systolic blood pressure (mmHg); time point: 12 weeks`. The
 * colon may sit inside or outside the bold (`**Design**: ...` keys the same field).
 *
 * Three readers depend on this grammar and must never disagree about it:
 *
 *   - `preservation-study-protocol.ts`, the canonical-form gate and the atom set;
 *   - `reference-study-protocol.ts`, which declares the outcome ids;
 *   - the later units that read a published protocol (the protocol lock hashes the
 *     revision bytes; the analysis log maps a run to an analysis-plan entry; verify diffs
 *     the manuscript against the primary outcome). They call `parseProtocol` (or mirror the
 *     grammar documented in SKILL.md, "The document") rather than re-deriving it.
 *
 * Imports nothing from the engine, so it loads in any process, under any profile.
 */

/** An outcome id: `O` and a positive ordinal (`O1`, `O12`). Stable across amendments: a citation re-points nowhere when another outcome is added. */
export const OUTCOME_ID = "O[1-9][0-9]*";

/** Every label this domain reads, by the key the parser reports it under. */
export const FIELD_LABELS = {
	researchQuestion: "Research question",
	primaryOutcome: "Primary outcome",
	secondaryOutcome: "Secondary outcome",
	secondaryOutcomesNone: "Secondary outcomes",
	design: "Design",
	eligibility: "Eligibility",
	sampleSize: "Sample size",
	sampleSizeJustification: "Sample size justification",
	primaryModel: "Primary model",
	covariates: "Covariates",
	missingData: "Missing data",
	multiplicity: "Multiplicity",
} as const;

export type FieldKey = keyof typeof FIELD_LABELS;

export type Declared = { readonly value: string; readonly line: number };

export type ProtocolOutcome = {
	readonly role: "primary" | "secondary";
	/** Null when the line names no `O<n>` id at its start. */
	readonly id: string | null;
	/** The text between the id and `; time point:`; empty when absent. */
	readonly measure: string;
	/** The text after `time point:`; empty when absent. */
	readonly timePoint: string;
	readonly line: number;
	readonly raw: string;
};

export type ParsedProtocol = {
	/** Every labelled line, per field, in document order -- cardinality is the caller's to judge. */
	readonly fields: Readonly<Record<FieldKey, readonly Declared[]>>;
	/** Every primary and secondary outcome line, in document order. */
	readonly outcomes: readonly ProtocolOutcome[];
	/** The id of the ONE primary outcome; null when there is none, several, or the one names no id. */
	readonly primaryOutcomeId: string | null;
	readonly researchQuestion: string | null;
	readonly design: string | null;
	readonly eligibility: string | null;
	readonly sampleSize: { readonly value: string; readonly justification: string | null } | null;
	readonly analysisPlan: { readonly primaryModel: string | null; readonly covariates: string | null; readonly missingData: string | null; readonly multiplicity: string | null };
};

const escape = (literal: string) => literal.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** One label's matcher. `Secondary outcome` never matches `**Secondary outcomes:**`: the bold must close right after the label (and its optional colon). */
function labelPattern(label: string): RegExp {
	return new RegExp(`^[ \\t]*(?:[-*+][ \\t]+)?\\*\\*${escape(label)}:?\\*\\*:?[ \\t]*(.*?)[ \\t]*$`, "gmu");
}

/** The 1-based line an index falls on. */
export function lineAt(source: string, index: number): number {
	let line = 1;
	for (let at = 0; at < index; at += 1) if (source[at] === "\n") line += 1;
	return line;
}

function declarations(source: string, label: string): Declared[] {
	const out: Declared[] = [];
	for (const match of source.matchAll(labelPattern(label))) out.push({ value: (match[1] ?? "").trim(), line: lineAt(source, match.index ?? 0) });
	return out;
}

const OUTCOME_HEAD = new RegExp(`^(${OUTCOME_ID})\\b[ \\t]*(?:--|—|–|-|:|\\.)?[ \\t]*`, "u");
const TIME_POINT = /;?[ \t]*time point:[ \t]*/iu;

/** `O1 -- <measure>; time point: <when>` split into its parts. Absent parts come back empty, never guessed. */
export function parseOutcome(role: "primary" | "secondary", declared: Declared): ProtocolOutcome {
	const raw = declared.value;
	const head = OUTCOME_HEAD.exec(raw);
	const id = head ? head[1]! : null;
	const rest = head ? raw.slice(head[0].length) : raw;
	const split = TIME_POINT.exec(rest);
	const measure = (split ? rest.slice(0, split.index) : rest).trim().replace(/[;,]+$/u, "").trim();
	const timePoint = split ? rest.slice(split.index + split[0].length).trim() : "";
	return { role, id, measure, timePoint, line: declared.line, raw };
}

const only = (found: readonly Declared[]): string | null => (found.length === 1 ? found[0]!.value : null);

/** The whole protocol, parsed once. Pure: the same bytes always parse the same way. */
export function parseProtocol(source: string): ParsedProtocol {
	const fields = Object.fromEntries(
		(Object.keys(FIELD_LABELS) as FieldKey[]).map((key) => [key, declarations(source, FIELD_LABELS[key])]),
	) as Record<FieldKey, Declared[]>;
	const outcomes = [
		...fields.primaryOutcome.map((declared) => parseOutcome("primary", declared)),
		...fields.secondaryOutcome.map((declared) => parseOutcome("secondary", declared)),
	].sort((left, right) => left.line - right.line);
	const primaries = outcomes.filter((outcome) => outcome.role === "primary");
	const size = only(fields.sampleSize);
	return {
		fields,
		outcomes,
		primaryOutcomeId: primaries.length === 1 ? primaries[0]!.id : null,
		researchQuestion: only(fields.researchQuestion),
		design: only(fields.design),
		eligibility: only(fields.eligibility),
		sampleSize: size === null ? null : { value: size, justification: only(fields.sampleSizeJustification) },
		analysisPlan: {
			primaryModel: only(fields.primaryModel),
			covariates: only(fields.covariates),
			missingData: only(fields.missingData),
			multiplicity: only(fields.multiplicity),
		},
	};
}

/** The outcome ids later units key on: the one primary (null unless exactly one) and every secondary, in document order. */
export function outcomeIds(source: string): { primary: string | null; secondary: string[] } {
	const parsed = parseProtocol(source);
	return {
		primary: parsed.primaryOutcomeId,
		secondary: parsed.outcomes.filter((outcome) => outcome.role === "secondary" && outcome.id !== null).map((outcome) => outcome.id!),
	};
}
