import type { CanonicalProposalMetadata, CreateR01PayloadV1, MaterializationClaimProvenance } from './revision-domain.js';
import { artifact, managedRevisionFilename } from './artifact-naming.js';
import { DOMAIN } from './domain-profile.js';

/** Change 8, option (b): v1's own default change summary, rendered only when `profile.artifact.changeHeader` is declared -- the header must exist as a span in v1 for a later successor to replace. The managed directory holds only `.gitkeep` today, so this is zero migration. */
const INITIAL_CHANGE_SUMMARY = { what: 'Initial revision.', why: 'First published version.' };

/** Read-only paper-guide reference fragment, mirroring `ChatGuideFragment`'s shape without importing chat-only types. */
export type InitialRevisionGuideFragment = { path: string; content: string };
export type ComposedInitialRevision = { markdown: string; slug: string; canonicalMetadata: CanonicalProposalMetadata };

/** An ATX heading opener as a Markdown reader sees it: up to three spaces, one to six `#`, then a space, a tab or the end of the line. */
const ATX_OPENER = /^( {0,3})(#{1,6})(?=[ \t\r]|$)/u;
/** A setext underline: a run of `=` or of `-`, alone on its line. It makes the line above it a heading. */
const SETEXT_UNDERLINE = /^( {0,3})([=-]+[ \t\r]*)$/u;
/** A fenced code block's opening or closing delimiter. */
const FENCE = /^ {0,3}(`{3,}|~{3,})/u;
/** A line that opens a block a setext underline cannot turn into a heading: a table row, a block quote, a list item. */
const NOT_PARAGRAPH = /^ {0,3}(?:\||>|[-*+](?:[ \t]|$)|\d{1,9}[.)](?:[ \t]|$))/u;

/**
 * A source document's text with every one of its own headings turned into plain text, so it
 * can be pasted into a managed document as reference material without becoming part of that
 * document's structure.
 *
 * Pasted verbatim, a source's headings were the document's headings: a source whose `#` title
 * equals the new document's own title left several identical level-1 headings, every locus
 * query on that title tied, and the last pasted section ran over `## Changes`. The escape is
 * the smallest change that ends that: a backslash before the heading marker (`\#`, `\=`,
 * `\-`), which every CommonMark reader prints as the literal character. Every other byte --
 * tables, display blocks, declarations, URLs -- is left as it was, so the gates that judge
 * pasted sources see what they saw before.
 *
 * ATX openers are escaped everywhere, inside fenced code too: a fence hides them from a
 * Markdown reader but not from this engine's structural index or from `paper-writing`'s
 * outline, both of which read any line that opens with `#` as a heading. A setext underline
 * is escaped only outside a fence and only under a paragraph line (an escaped ATX line is
 * one), which is the only place it makes a heading. Idempotent: an escaped line no longer
 * matches. `neutralized` counts the lines changed.
 */
export function neutralizeSourceHeadings(text: string): { text: string; neutralized: number } {
	let neutralized = 0;
	let fence: string | undefined;
	let previousParagraph = false;
	const lines = text.split('\n').map((line) => {
		const fenceMatch = FENCE.exec(line);
		const insideFence = fence !== undefined;
		if (fenceMatch) {
			const marker = fenceMatch[1]!;
			if (fence === undefined) fence = marker;
			else if (marker[0] === fence[0] && marker.length >= fence.length && line.trim() === marker) fence = undefined;
		}
		let out = line;
		const atx = ATX_OPENER.exec(line);
		if (atx) out = `${atx[1]}\\${line.slice(atx[1]!.length)}`;
		else if (!insideFence && !fenceMatch && previousParagraph) {
			const setext = SETEXT_UNDERLINE.exec(line);
			if (setext) out = `${setext[1]}\\${setext[2]}`;
		}
		if (out !== line) neutralized++;
		previousParagraph = !insideFence && !fenceMatch && out.trim() !== '' && !NOT_PARAGRAPH.test(out);
		return out;
	});
	return { text: lines.join('\n'), neutralized };
}

function splitIdeaSentences(idea: string): string[] {
	return idea.split(/(?<=[.!?])\s+/).map((sentence) => sentence.trim()).filter(Boolean);
}

/**
 * A sentence as a heading: its terminal `.`/`!`/`?` run dropped. The splitter above keeps that
 * punctuation on each sentence (it is what ended the sentence), but a heading is a label, not a
 * sentence, and a trailing full stop is also exactly where `RESOLVE_TARGET` truncates a query.
 * Punctuation inside the sentence (`2.1`, `revisited...` mid-text) is untouched. A sentence that
 * is nothing but punctuation keeps its bytes rather than collapsing to the generic fallback.
 */
function asHeading(sentence: string): string {
	const bounded = sentence.slice(0, 200).trim();
	return bounded.replace(/[.!?]+$/u, '').trim() || bounded;
}

/**
 * Derives title/sectionHeading directly from the caller's idea text -- never a hardcoded generic
 * label (spec I5). Title from the first sentence, section heading from the second; the idea itself
 * is written verbatim as the section body by `renderFromIdea`, because these two are derived
 * labels capped at 200 characters and the body is the only place the whole text survives.
 */
function deriveCanonicalMetadataFromIdea(idea: string): CanonicalProposalMetadata {
	const sentences = splitIdeaSentences(idea);
	const title = asHeading(sentences[0] ?? idea) || 'Untitled Research Concept';
	const sectionHeading = asHeading(sentences[1] ?? sentences[0] ?? idea) || 'Concept Overview';
	return { schemaVersion: 1, title, sectionHeading };
}

/** Derives a lowercase-hyphen filename slug from the idea-derived title -- never the fixed `r01` slug. Also names an adopted first revision after its own title (`adoptInitialRevision`). */
export function deriveSlugFromTitle(title: string): string {
	const normalized = title
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-+|-+$/g, '')
		.slice(0, 60)
		.replace(/-+$/g, '');
	return normalized || 'concept';
}

function validMetadata(metadata: CanonicalProposalMetadata) {
	return metadata.schemaVersion === 1
		&& typeof metadata.title === 'string' && metadata.title.trim().length > 0 && metadata.title.length <= 200
		&& typeof metadata.sectionHeading === 'string' && metadata.sectionHeading.trim().length > 0 && metadata.sectionHeading.length <= 200;
}

function validClaims(claims: readonly MaterializationClaimProvenance[]) {
	return claims.length > 0
		&& claims.every((claim, index) => typeof claim.claimId === 'string' && claim.claimId.length > 0
			&& typeof claim.summary === 'string' && claim.summary.trim().length > 0
			&& (index === 0 || claims[index - 1]!.decisionId < claim.decisionId));
}

/** Renders only immutable accepted decisions and caller-frozen canonical metadata. */
export class InitialRevisionRenderer {
	render(input: { acceptedDecisions: readonly MaterializationClaimProvenance[]; canonicalMetadata: CanonicalProposalMetadata }): CreateR01PayloadV1 {
		if (!validMetadata(input.canonicalMetadata) || !validClaims(input.acceptedDecisions)) throw new Error('MATERIALIZATION_INITIAL_RENDER_INPUT_INVALID');
		const markdown = [
			`# ${input.canonicalMetadata.title.trim()}`,
			'',
			`## ${input.canonicalMetadata.sectionHeading.trim()}`,
			'',
			...input.acceptedDecisions.flatMap((claim) => [`### ${claim.decisionId}`, '', claim.summary.trim(), '']),
		].join('\n');
		return {
			kind: 'CREATE_R01',
			payloadVersion: 1,
			markdown,
			target: { filename: managedRevisionFilename('ROOT', 1), revision: artifact.revisionLabel(1) },
			canonicalMetadata: structuredClone(input.canonicalMetadata),
		};
	}

	/**
	 * Composes v1 content from the caller's idea plus paper-guide fragments (spec I2, I5). Unlike
	 * `render()` (which only ever renders immutable accepted scientific decisions for the gated
	 * scientific-workflow route), this never requires accepted decisions and never emits a fixed
	 * generic skeleton: title/sectionHeading and the filename slug are both derived from the idea
	 * text itself, and the guide fragments (when present) are included as reference context,
	 * verbatim except that each fragment's own headings are escaped into plain text.
	 */
	renderFromIdea(input: { idea: string; guideFragments?: readonly InitialRevisionGuideFragment[] }): ComposedInitialRevision {
		const idea = input.idea.trim();
		if (!idea) throw new Error('INITIAL_REVISION_IDEA_REQUIRED');
		const canonicalMetadata = deriveCanonicalMetadataFromIdea(idea);
		const slug = deriveSlugFromTitle(canonicalMetadata.title);
		const sections = [`# ${canonicalMetadata.title}`, '', `## ${canonicalMetadata.sectionHeading}`, '', idea, ''];
		const guideFragments = input.guideFragments ?? [];
		if (guideFragments.length > 0) {
			// Finding L6: was a hardcoded `'## Paper Guide Reference'`, regardless of domain --
			// accurate for a domain whose one source really is a paper guide, wrong for a
			// domain whose declared sources never are. `DOMAIN.artifact.sourceReferenceHeading`
			// defaults to the exact prior literal when undeclared, so this is zero migration
			// for a domain that never opts in.
			sections.push(`## ${DOMAIN.artifact.sourceReferenceHeading ?? 'Paper Guide Reference'}`, '');
			// Each fragment under its own `### <path>`, its own headings escaped as text
			// (`neutralizeSourceHeadings`): the engine's headings above are the only ones this
			// section carries, so it ends where the next engine-written section begins.
			for (const fragment of guideFragments) sections.push(`### ${fragment.path}`, '', neutralizeSourceHeadings(fragment.content.trim()).text, '');
		}
		if (DOMAIN.artifact.changeHeader) sections.push(DOMAIN.artifact.changeHeader.render(INITIAL_CHANGE_SUMMARY), '');
		const markdown = `${sections.join('\n').replace(/\n+$/, '')}\n`;
		return { markdown, slug, canonicalMetadata };
	}
}
