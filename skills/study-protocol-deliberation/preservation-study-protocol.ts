import { sha256, type PreservationAtom, type PreservationViolation } from "../_core/deliberation/engine/types.js";
import { FIELD_LABELS, lineAt, parseProtocol, type Declared, type FieldKey, type ProtocolOutcome } from "./protocol-fields.js";

/**
 * This domain's preservation gate, wired through `profile.ts` as
 * `preservation.{extractAtoms, violations}`.
 *
 *   1. `extractAtoms` -- what a protocol declares that must never vanish in silence: the
 *      question, each outcome (keyed by id AND content, so switching what O1 measures is a
 *      loss, not an edit), the design, the eligibility, the sample size, the primary model,
 *      and every cited URL. A lost atom is reported on preview and refused on accept until
 *      the caller acknowledges it by id -- an amendment is deliberate or it does not publish.
 *   2. `violations` -- the canonical form of a protocol written before its data exist. Never
 *      intentional, so these block outright, v1 included.
 *
 * Nothing here reads `DOMAIN`: the module runs in process under any profile.
 */

const short = (value: string) => sha256(value).slice(0, 12);
const collapse = (value: string) => value.replace(/\s+/gu, " ").trim();
const key = (value: string) => collapse(value).replace(/[.,;:!?]+$/u, "").toLowerCase();

/**
 * Values that defer a decision. A field holding one of these declares nothing, exactly like
 * an empty label. Matched as the WHOLE value once punctuation and case are set aside, never as
 * a substring.
 */
const UNDECIDED = new Set(["", "tbd", "to be decided", "to be determined", "tba", "pending", "todo", "xxx", "?", "-", "...", "…"]);
/** Values that state an absence. A decision for covariates, missing data and multiplicity (`none`, `not applicable`), never for a field a protocol cannot do without. */
const ABSENT = new Set(["none", "n/a", "na", "not applicable", "nothing"]);

const normalizedWhole = (value: string) => collapse(value).replace(/[.;:!]+$/u, "").trim().toLowerCase();
const undecided = (value: string) => UNDECIDED.has(normalizedWhole(value));
const empty = (value: string) => undecided(value) || ABSENT.has(normalizedWhole(value));

/**
 * A result stated as already achieved. A protocol is written before its data are collected
 * or analysed, so a labelled field that reports an effect, a p-value or a finding is either a
 * fabrication or a protocol written after the fact -- the HARKing this document exists to
 * prevent. Narrow on purpose: past-tense reports and explicit p-values, never the future
 * tense a hypothesis is written in ("will lower", "is expected to reduce").
 *
 * Shared with `profile.ts`, which applies it document-wide at advisory severity: prose in a
 * background section may legitimately restate somebody else's published result, a labelled
 * field may not.
 */
export const STATED_RESULT = /\bp\s*(?:[<=≤]|&lt;)\s*0?\.\d+|\b(?:was|were)\s+(?:significantly\s+|substantially\s+)?(?:reduced|increased|improved|decreased|lowered|raised|higher|lower|greater|smaller|better|worse|superior|inferior|effective|associated)\b|\bwe\s+(?:found|observed|showed|demonstrated|confirmed|detected)\b|\bresults\s+(?:show|showed|demonstrate|demonstrated|confirm|confirmed)\b|\boutperform(?:s|ed)\b/iu;

/** The fields a hard `field-states-result` refusal covers: what the study will measure and ask. */
const RESULT_FREE_FIELDS: readonly FieldKey[] = ["researchQuestion", "primaryOutcome", "secondaryOutcome"];

/** An external URL, as the experimental sibling reads one. */
const EXTERNAL_URL = /https?:\/\/[^\s|)\]]+/gu;
/** The experimental sibling's verification convention, unchanged: every URL is tagged `[pending-verification]` or `[verified: YYYY-MM-DD]`, immediately after it. */
const VERIFICATION_TAG_FOLLOWS = /^[)\].,;:!?]*[ \t]*(?:\[pending-verification\]|\[verified: \d{4}-\d{2}-\d{2}\])/u;

type FoundUrl = { readonly value: string; readonly line: number; readonly trailing: string };

function externalUrls(source: string): FoundUrl[] {
	const out: FoundUrl[] = [];
	for (const match of source.matchAll(EXTERNAL_URL)) {
		const start = match.index ?? 0;
		const value = match[0].replace(/[.,;:!?]+$/u, "");
		const end = start + value.length;
		const lineEnd = source.indexOf("\n", end);
		out.push({ value, line: lineAt(source, start), trailing: source.slice(end, lineEnd < 0 ? source.length : lineEnd) });
	}
	return out;
}

/** The fields a protocol owes exactly once, with the rule a missing or placeholder value raises. */
const SINGLE_FIELDS: readonly { readonly field: FieldKey; readonly slug: string; readonly missingRule: string; readonly allowsAbsent: boolean }[] = [
	{ field: "researchQuestion", slug: "research-question", missingRule: "research-question-declaration-missing", allowsAbsent: false },
	{ field: "design", slug: "design", missingRule: "design-declaration-missing", allowsAbsent: false },
	{ field: "eligibility", slug: "eligibility", missingRule: "eligibility-declaration-missing", allowsAbsent: false },
	{ field: "sampleSize", slug: "sample-size", missingRule: "sample-size-declaration-missing", allowsAbsent: false },
	{ field: "primaryModel", slug: "primary-model", missingRule: "analysis-plan-without-primary-model", allowsAbsent: false },
	{ field: "covariates", slug: "covariates", missingRule: "covariates-declaration-missing", allowsAbsent: true },
	{ field: "missingData", slug: "missing-data", missingRule: "missing-data-declaration-missing", allowsAbsent: true },
	{ field: "multiplicity", slug: "multiplicity", missingRule: "multiplicity-declaration-missing", allowsAbsent: true },
];

const label = (field: FieldKey) => `\`**${FIELD_LABELS[field]}:**\``;

function repeated(field: FieldKey, slug: string, found: readonly Declared[]): PreservationViolation {
	return {
		rule: `${slug}-declaration-repeated`,
		line: found[1]!.line,
		detail: `declared on lines ${found.map((d) => d.line).join(", ")}; exactly one ${label(field)} line is required, and the engine must not pick one silently`,
	};
}

/**
 * Every atom this protocol declares, keyed by a stable id. Presence-based: an atom is lost only
 * when no line of the successor carries it. Keys fold whitespace, case and trailing punctuation,
 * so a reflow is not a loss and a changed value is.
 *
 *   `research-question:<hash>`, `design:<hash>`, `eligibility:<hash>`, `primary-model:<hash>`
 *   `primary-outcome:<id>:<hash of measure and time point>`, `secondary-outcome:<id>:<hash>`
 *   `sample-size:<value>`   legible, so the caller echoing a changed N back reads the N
 *   `url:<url>`
 */
export function extractAtoms(source: string): Map<string, PreservationAtom> {
	const atoms = new Map<string, PreservationAtom>();
	const add = (kind: string, id: string, text: string) => {
		const full = `${kind}:${id}`;
		if (!atoms.has(full)) atoms.set(full, { id: full, kind, text });
	};
	const parsed = parseProtocol(source);
	for (const [field, kind] of [["researchQuestion", "research-question"], ["design", "design"], ["eligibility", "eligibility"], ["primaryModel", "primary-model"]] as const)
		for (const declared of parsed.fields[field]) if (!empty(declared.value)) add(kind, short(key(declared.value)), collapse(declared.value));
	for (const outcome of parsed.outcomes) {
		if (outcome.id === null) continue;
		add(`${outcome.role}-outcome`, `${outcome.id}:${short(`${key(outcome.measure)}|${key(outcome.timePoint)}`)}`, collapse(outcome.raw));
	}
	for (const declared of parsed.fields.sampleSize) if (!empty(declared.value)) add("sample-size", key(declared.value), collapse(declared.value));
	for (const found of externalUrls(source)) add("url", found.value, found.value);
	return atoms;
}

function outcomeViolations(outcome: ProtocolOutcome, out: PreservationViolation[]): void {
	const name = outcome.role === "primary" ? FIELD_LABELS.primaryOutcome : FIELD_LABELS.secondaryOutcome;
	if (outcome.id === null) {
		out.push({ rule: "outcome-without-id", line: outcome.line, detail: `a ${name.toLowerCase()} opens with its id, \`O<n> -- <measure>; time point: <when>\`; ${JSON.stringify(outcome.raw)} names none, so nothing can cite it` });
		return;
	}
	if (empty(outcome.measure))
		out.push({ rule: "outcome-without-measure", line: outcome.line, detail: `${outcome.id} names no measure (what is measured, and in which unit or instrument)` });
	if (empty(outcome.timePoint))
		out.push({ rule: "outcome-without-time-point", line: outcome.line, detail: `${outcome.id} names no time point; write \`; time point: <when>\` after its measure` });
}

/** The canonical form: what a protocol written before its data must say, once each. */
export function violations(source: string): PreservationViolation[] {
	const out: PreservationViolation[] = [];
	const parsed = parseProtocol(source);
	const { fields, outcomes } = parsed;

	// Exactly one primary outcome (D3). Zero and several are different facts, different ids.
	const primaries = outcomes.filter((outcome) => outcome.role === "primary");
	if (primaries.length === 0)
		out.push({ rule: "primary-outcome-missing", line: 1, detail: `a protocol declares exactly one ${label("primaryOutcome")} line, \`O<n> -- <measure>; time point: <when>\`; the choice of that outcome is the operator's, never inferred` });
	else if (primaries.length > 1)
		out.push({ rule: "primary-outcome-repeated", line: primaries[1]!.line, detail: `declared on lines ${primaries.map((o) => o.line).join(", ")}; exactly one primary outcome is allowed -- demote the others to ${label("secondaryOutcome")} lines` });
	for (const outcome of outcomes) outcomeViolations(outcome, out);

	const seen = new Map<string, number>();
	for (const outcome of outcomes) {
		if (outcome.id === null) continue;
		const first = seen.get(outcome.id);
		if (first === undefined) seen.set(outcome.id, outcome.line);
		else out.push({ rule: "outcome-id-repeated", line: outcome.line, detail: `${outcome.id} is declared on lines ${first} and ${outcome.line}; every outcome owns its id` });
	}

	// Secondary outcomes: one or more lines, or one explicit `**Secondary outcomes:** none`.
	const none = fields.secondaryOutcomesNone;
	const secondaries = fields.secondaryOutcome;
	if (secondaries.length === 0 && none.length === 0)
		out.push({ rule: "secondary-outcomes-undeclared", line: 1, detail: `declare each secondary outcome on its own ${label("secondaryOutcome")} line, or state ${label("secondaryOutcomesNone")} none; silence is not a decision` });
	else if (none.length > 0 && secondaries.length > 0)
		out.push({ rule: "secondary-outcomes-contradictory", line: none[0]!.line, detail: `${label("secondaryOutcomesNone")} says none while ${secondaries.length} ${label("secondaryOutcome")} line(s) declare some` });
	else if (none.length > 0 && !none.every((declared) => ABSENT.has(normalizedWhole(declared.value))))
		out.push({ rule: "secondary-outcomes-undeclared", line: none[0]!.line, detail: `${label("secondaryOutcomesNone")} only ever says none; list each secondary outcome on its own ${label("secondaryOutcome")} line with its id` });

	for (const { field, slug, missingRule, allowsAbsent } of SINGLE_FIELDS) {
		const found = fields[field];
		if (found.length > 1) {
			out.push(repeated(field, slug, found));
			continue;
		}
		const value = found[0]?.value ?? "";
		if (found.length === 0 || (allowsAbsent ? undecided(value) : empty(value)))
			out.push({ rule: missingRule, line: found[0]?.line ?? 1, detail: `${label(field)} must be declared once with a decided value${allowsAbsent ? " (an explicit none or not applicable counts)" : ""}; ${found.length === 0 ? "it is absent" : `${JSON.stringify(value)} defers the decision`}` });
	}

	// The sample size names a number and owes its justification (a calculation or a rationale).
	const size = fields.sampleSize.length === 1 ? fields.sampleSize[0]! : null;
	if (size && !empty(size.value) && !/\d/u.test(size.value))
		out.push({ rule: "sample-size-without-number", line: size.line, detail: `${JSON.stringify(size.value)} names no target number of participants, units or samples` });
	const justification = fields.sampleSizeJustification;
	if (justification.length > 1) out.push(repeated("sampleSizeJustification", "sample-size-justification", justification));
	else if (size && (justification.length === 0 || empty(justification[0]!.value)))
		out.push({ rule: "sample-size-without-justification", line: justification[0]?.line ?? size.line, detail: `the sample size owes a ${label("sampleSizeJustification")} line: the power calculation (effect, variability, alpha, power, attrition) or the rationale for the number` });

	// No outcome field and no research question reports a result. The planning
	// fields (design, eligibility, sample size and its justification, the
	// analysis plan) legitimately cite a significance threshold, a past-tense
	// screening criterion or a pilot estimate; result language there is left to
	// the document-wide advisory bound (`profile.ts`), which the operator
	// acknowledges by id.
	for (const field of RESULT_FREE_FIELDS)
		for (const declared of fields[field]) {
			const hit = STATED_RESULT.exec(declared.value);
			if (hit) out.push({ rule: "field-states-result", line: declared.line, detail: `${label(field)} states a result (${JSON.stringify(hit[0])}); a protocol is written before its data exist, so every field plans and none reports` });
		}

	for (const found of externalUrls(source))
		if (!VERIFICATION_TAG_FOLLOWS.test(found.trailing))
			out.push({ rule: "url-without-verification-marker", line: found.line, detail: `${found.value} must be followed by [pending-verification] or [verified: YYYY-MM-DD]; an unmarked URL claims a search that left no trace` });

	return out.sort((left, right) => left.line - right.line);
}
