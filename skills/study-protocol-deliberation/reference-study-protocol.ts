import { proseReference } from "../_core/deliberation/engine/domain-profile.js";
import { OUTCOME_ID, parseProtocol } from "./protocol-fields.js";

/**
 * This domain's reference-integrity vocabulary, wired through `profile.ts` as
 * `references.{declares, cites}`.
 *
 * An OUTCOME LINE declares its id (`**Primary outcome:** O1 -- ...`,
 * `**Secondary outcome:** O2 -- ...`). The analysis plan and the prose CITE one,
 * explicitly as `[outcome:O1]` or in prose as `(Outcome O1)`. So an analysis of an
 * outcome the protocol never declared is an unresolved reference the core refuses,
 * and two outcomes sharing an id are a duplicate it reports.
 *
 * Declared under the core's own `tag` kind, which `document-index.ts` folds into an
 * entry's aliases: `RESOLVE_TARGET` can then select the block carrying `O1` by its id.
 *
 * The ids themselves come from `protocol-fields.ts`, the one parser every reader of a
 * protocol shares; later units (the analysis log, verify) call `outcomeIds` there.
 *
 * `proseReference` is read lazily, inside `cites`, never at this module's top level:
 * `profile.ts` imports this module while `domain-profile.ts` is still loading it.
 */

/** Every declaration: one `tag` per outcome line that names an id, in document order. */
export function declares(source: string): readonly { kind: string; value: string }[] {
	return parseProtocol(source).outcomes.filter((outcome) => outcome.id !== null).map((outcome) => ({ kind: "tag", value: outcome.id! }));
}

/** Every citation: an explicit `[outcome:O1]`, or the prose form this domain declares. */
export function cites(source: string): readonly { kind: string; value: string }[] {
	const out: { kind: string; value: string }[] = [];
	for (const [, value] of source.matchAll(new RegExp(`\\[outcome:(${OUTCOME_ID})\\]`, "g"))) out.push({ kind: "ref", value });
	for (const [, value] of source.matchAll(proseReference("g"))) out.push({ kind: "prose", value });
	return out;
}
