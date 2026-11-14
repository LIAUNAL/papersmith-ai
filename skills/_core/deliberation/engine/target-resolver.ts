import { readFileSync } from 'node:fs';
import { buildStructuralIndex } from './document-index.js';
import { DOMAIN } from './domain-profile.js';
/** How this domain names a numbered display, and what its documents are about. Both stateless (no `g`), so one instance each is safe; the stripping form below needs `g` and is built per call. */
const DISPLAY_NOUN=new RegExp(DOMAIN.vocabulary.displayNounPattern,'i');
const SUBJECT=new RegExp(DOMAIN.vocabulary.subjectPattern,'i');
import { sha256,type CompositeTarget,type DocumentState,type SectionReplacementContract,type StructuralEntry,type TargetCandidate } from './types.js';

export type TargetResolutionOptions={allowInterEntryWhitespaceFallback?:boolean};
export type SectionRangeResolution={candidate?:TargetCandidate;entryIds?:string[];reason?:'SECTION_RANGE_INVALID'|'SECTION_RANGE_NOT_FOUND'|'SECTION_RANGE_AMBIGUOUS'|'SECTION_RANGE_REVERSED'|'SECTION_RANGE_INCOMPLETE_BODY'};
export type SuccessorTargetResolution={candidates:TargetCandidate[];reason?:'SUCCESSOR_TARGET_NOT_FOUND'};

type StructuralCore={entry:StructuralEntry;startByte:number;endByte:number;text:Buffer};

const words=(value:string)=>(value.toLowerCase().match(/[\p{L}\p{N}_-]{2,}/gu)??[]);
/**
 * Function words that carry no discriminating power in a heading. Term matching
 * is a plain substring test against the heading line, so a single `de` matches
 * nearly every Spanish heading, lifts them all into contention, and collapses
 * the ambiguity gate's score margin — turning an otherwise exact locus
 * description into a blocked one.
 */
const STOPWORDS=new Set(['de','del','la','el','los','las','un','una','unos','unas','en','con','por','para','sin','sobre','entre','al','lo','su','sus','que','se','es','son','como','mas','más','of','the','an','in','on','for','to','with','and','or','by','from','is','are','as','at','be']);
/** Drops stopword tokens, keeping the original when nothing discriminating survives. */
const dropStopwords=(value:string)=>{
 const kept=value.split(/\s+/u).filter(token=>!STOPWORDS.has(token.toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu,''))).join(' ').trim();
 return words(kept).length?kept:value;
};
const escapeRegExp=(value:string)=>value.replace(/[.*+?^${}()|[\]\\]/gu,'\\$&');
/**
 * True when `value` occurs in `query` as a standalone token.
 *
 * Label and tag matching used to ask `query.includes(label)` — the containment
 * test the wrong way round. A one-character tag like `3` is a substring of any
 * query mentioning `30`, `13` or `3-3`, and each match is worth 8 points against
 * 3 for a content word, so a spurious hit outranks nearly three real ones.
 * Boundaries fix that without breaking punctuated labels like `eq:uno`, whose
 * `:` is not a word character on either side.
 */
const isolatedInQuery=(query:string,value:string)=>new RegExp(`(?<![\\p{L}\\p{N}_-])${escapeRegExp(value)}(?![\\p{L}\\p{N}_-])`,'u').test(query);
/**
 * Maps each label/tag to the smallest entry carrying it — the one that actually
 * declares it.
 *
 * `document-index` reads an entry's tags straight out of its own text, and a
 * section's text contains every equation inside it, so the section ends up
 * carrying `\tag{3}` without ever writing it. Since the section also matches all
 * the prose the equation lacks, asking for equation 3 resolved to the whole
 * section that owns it. Crediting only the declaring entry keeps the ancestor
 * from outscoring its own descendant.
 */
function declaringEntries(entries:readonly StructuralEntry[],key:'labels'|'tags'){const owner=new Map<string,{id:string;size:number}>();for(const entry of entries){const size=entry.endByte-entry.startByte;for(const value of entry[key]){const current=owner.get(value);if(!current||size<current.size)owner.set(value,{id:entry.entryId,size});}}return owner;}
const equationSymbols=(value:string)=>[...new Set(value.match(/\\[A-Za-z]+|\b[A-Za-z]\b/g)??[])];
/**
 * What a matched term is worth, by WHERE it was found.
 *
 * Term matching used to run against one flat blob — the entry's own text, both
 * neighbouring entries' text and the heading path concatenated — so every word
 * written inside an entry scored identically for the entry BEFORE it, the entry
 * AFTER it, and the ancestor that merely spans it. A GFM table could therefore
 * never be singled out by its own column headers: the table, its section and both
 * neighbouring paragraphs (which contain none of those words) all tied, and
 * `ambiguityGate` — which blocks whenever the top two are within 4 — handed the
 * caller a menu instead of the table. That predates tables and hit ordinary
 * paragraphs the same way; it only became load-bearing once documents became
 * mostly tables and "replace the third result table" became the usual query.
 *
 * Context is NOT dropped: describing a locus by what surrounds it ("the paragraph
 * after the accuracy table") is a real and supported way to aim, and an entry
 * whose own text says nothing must stay reachable through its neighbours. It is
 * demoted instead, so the entry that actually writes the word outranks the ones
 * that merely sit beside or above it. Three distinctive terms then separate the
 * declaring entry from its context by 6, clearing the gate's margin of 4; a
 * one-word query still ties inside the margin, which is the correct answer for a
 * query that genuinely does not discriminate.
 *
 * `OWN_TERM` stays at the historical 3 so that every locus already resolved by
 * its own words keeps its exact score, its `confidence` (score/12) and its
 * ranking against labels and tags (8 each). Only context-only matches move.
 */
const OWN_TERM=3,CONTEXT_TERM=1;
const entryText=(state:DocumentState,id:string)=>{const e=state.structuralIndex.byId[id];return e?state.documentBytes.subarray(e.startByte,e.endByte).toString('utf8'):''};
const leaf=(entry:StructuralEntry)=>['display_equation','paragraph','inline_math_region','list','code_block','definition','theorem','algorithm','table','figure_placeholder'].includes(entry.type);
const sameHeadingPath=(left:string[],right:string[])=>JSON.stringify(left)===JSON.stringify(right);
const whitespaceOnly=(bytes:Buffer,start:number,end:number)=>/^\s*$/u.test(bytes.subarray(start,end).toString('utf8'));

function structuralCore(bytes:Buffer,entry:StructuralEntry):StructuralCore{
 let endByte=entry.endByte;
 if(entry.type==='display_equation'){
  const text=bytes.subarray(entry.startByte,entry.endByte).toString('utf8');
  const closing=[...text.matchAll(/^\$\$(?=[ \t]*(?:\r?$))/gm)].at(-1);
  if(closing?.index!==undefined)endByte=entry.startByte+Buffer.byteLength(text.slice(0,closing.index+2));
 }
 return {entry,startByte:entry.startByte,endByte,text:bytes.subarray(entry.startByte,endByte)};
}

function compositeCandidate(state:DocumentState,members:StructuralEntry[],startByte:number,endByte:number,evidence:string):TargetCandidate{
 const actualText=state.documentBytes.subarray(startByte,endByte);
 const textSha256=sha256(actualText);
 const composite:CompositeTarget={entryIds:members.map(entry=>entry.entryId),startByte,endByte,documentSha256:state.documentSha256,textSha256,exactProvidedText:actualText.toString('utf8')};
 return {entryId:`composite:${startByte}:${textSha256.slice(0,16)}`,type:'composite',headingPath:members[0].headingPath,matchedTerms:[],matchedLabels:[],matchedTags:[],matchedSymbols:[],score:100,confidence:1,shortPreview:actualText.toString('utf8').slice(0,180),evidence:[evidence],composite};
}

function exactCompositeTargets(state:DocumentState,providedText:string):TargetCandidate[]{
 const needle=Buffer.from(providedText);if(!needle.length)return [];
 const candidates:TargetCandidate[]=[];
 for(let start=state.documentBytes.indexOf(needle);start>=0;start=state.documentBytes.indexOf(needle,start+1)){
  const end=start+needle.length;
  const members=state.structuralIndex.entries.filter(e=>leaf(e)&&e.startByte>=start&&e.startByte<end&&e.endByte<=end+1).sort((a,b)=>a.startByte-b.startByte);
  if(!members.length||members[0].startByte!==start||members.at(-1)!.endByte<end||members.at(-1)!.endByte>end+1)continue;
  if(!members.every(e=>sameHeadingPath(e.headingPath,members[0].headingPath)))continue;
  if(members.some((e,i)=>i>0&&!whitespaceOnly(state.documentBytes,members[i-1].endByte,e.startByte)))continue;
  candidates.push(compositeCandidate(state,members,start,end,'explicit composite selection'));
 }
 return candidates;
}

function interEntryWhitespaceCompositeTargets(state:DocumentState,providedText:string):TargetCandidate[]{
 const providedBytes=Buffer.from(providedText);
 const providedEntries=buildStructuralIndex(providedText).entries.filter(leaf).sort((a,b)=>a.startByte-b.startByte);
 if(providedEntries.length<2)return [];
 const providedCores=providedEntries.map(entry=>structuralCore(providedBytes,entry));
 if(providedCores[0].startByte!==0||providedCores.at(-1)!.endByte!==providedBytes.length)return [];
 if(providedCores.some((core,index)=>index>0&&!whitespaceOnly(providedBytes,providedCores[index-1].endByte,core.startByte)))return [];

 const documentEntries=state.structuralIndex.entries.filter(leaf).sort((a,b)=>a.startByte-b.startByte||a.endByte-b.endByte);
 const candidates:TargetCandidate[]=[];
 for(let startIndex=0;startIndex<=documentEntries.length-providedEntries.length;startIndex++){
  const members=documentEntries.slice(startIndex,startIndex+providedEntries.length);
  if(!members.every(entry=>sameHeadingPath(entry.headingPath,members[0].headingPath)))continue;
  const cores=members.map(entry=>structuralCore(state.documentBytes,entry));
  if(cores.some((core,index)=>core.entry.type!==providedCores[index].entry.type||!core.text.equals(providedCores[index].text)))continue;
  if(cores.some((core,index)=>index>0&&!whitespaceOnly(state.documentBytes,cores[index-1].endByte,core.startByte)))continue;
  candidates.push(compositeCandidate(state,members,cores[0].startByte,cores.at(-1)!.endByte,'explicit composite selection with document inter-entry whitespace'));
 }
 return candidates;
}

function headingLevel(state:DocumentState,entry:StructuralEntry){return /^#{1,6}(?=\s)/u.exec(entryText(state,entry.entryId))?.[0].length;}
/**
 * The heading entry of the domain's change header (`profile.artifact.changeHeader.heading`),
 * the first heading carrying exactly that text -- the one `changeHeaderLocusCandidate` and
 * therefore every successor replaces -- or `undefined` when the domain declares none or the
 * document does not carry it.
 */
function changeHeaderEntry(state:DocumentState,heading:string|undefined=DOMAIN.artifact.changeHeader?.heading){
 if(heading===undefined)return undefined;
 return state.structuralIndex.entries.find(e=>['section','subsection','heading'].includes(e.type)&&entryText(state,e.entryId).split(/\r?\n/u,1)[0].replace(/^#{1,6}\s+/,'').trim()===heading);
}
/**
 * A heading's natural span: from the heading through the next heading of the same or a higher
 * level, or the document end -- but never over the change header. Every successor of a domain
 * that declares one replaces that header, so a span reaching over it could only ever be
 * refused `SUCCESSOR_TARGET_OVERLAP`; it happens whenever the header is nested under the
 * section before it, as under the last of several `#` sections. Ending such a span where the
 * header begins changes nothing that resolved before, and makes that last section editable.
 */
function sectionBodyEnd(state:DocumentState,entry:StructuralEntry){const level=headingLevel(state,entry);if(!level)return entry.endByte;const next=state.structuralIndex.entries.filter(candidate=>candidate.startByte>entry.startByte&&['section','subsection','heading'].includes(candidate.type)).sort((a,b)=>a.startByte-b.startByte).find(candidate=>(headingLevel(state,candidate)??7)<=level);const end=next?.startByte??state.documentBytes.length;const header=changeHeaderEntry(state);return header&&header.startByte>entry.startByte&&header.startByte<end?header.startByte:end;}
/**
 * The document's root block — the `#` title plus the introduction that runs up
 * to the first `##` — as its own locus, or `undefined` for every other heading.
 *
 * The structural index already gives that block the exact span we want, but
 * `sectionBodyEnd` then stretched the title over the WHOLE document, because no
 * same-or-higher heading follows it. The stretched candidate contains every
 * section, so `collapseNestedSuccessorCandidates` discarded it and the root
 * block became unreachable: a query aiming at the title silently landed on
 * whichever section shared a word with it, and one that matched nothing else
 * rewrote the entire document. Both are the wrong-target-in-silence failure this
 * resolver refuses everywhere else.
 *
 * A lone `#` is a document title; two or more mean `#` IS the section level, and
 * `# Parent` legitimately spans its `## Child`. So this applies only to the
 * first heading of a document with exactly one level-1 heading, and only when
 * that heading does not already span its own subtree — leaving `##`-with-`###`
 * and multi-`#` documents targeting their whole subtree exactly as before.
 */
function rootBlockEnd(state:DocumentState,entry:StructuralEntry){
 const headings=state.structuralIndex.entries.filter(candidate=>['section','subsection','heading'].includes(candidate.type)).sort((left,right)=>left.startByte-right.startByte);
 if(headings[0]?.entryId!==entry.entryId||headingLevel(state,entry)!==1)return undefined;
 if(headings.filter(candidate=>headingLevel(state,candidate)===1).length!==1)return undefined;
 return entry.endByte<sectionBodyEnd(state,entry)?entry.endByte:undefined;
}
function hasSectionBody(state:DocumentState,startByte:number,endByte:number){const selected=state.documentBytes.subarray(startByte,endByte).toString('utf8');return selected.replace(/^ {0,3}#{1,6}\s+.*(?:\r?\n|$)/gmu,'').trim().length>0;}
function sectionReplacementCandidate(state:DocumentState,start:StructuralEntry,requestedSectionIds:string[],evidence:string){
 const startByte=start.startByte,endByte=sectionBodyEnd(state,start),last=state.structuralIndex.entries.filter(entry=>entry.startByte>=startByte&&entry.endByte===endByte).sort((left,right)=>right.startByte-left.startByte)[0];
 const startsAtLineStart=startByte===0||state.documentBytes[startByte-1]===0x0a,endsAfterCompleteLine=endByte===state.documentBytes.length||state.documentBytes[endByte-1]===0x0a;
 if(!last||!startsAtLineStart||!endsAfterCompleteLine||!hasSectionBody(state,startByte,endByte))return;
 const candidate=compositeCandidate(state,[start,last],startByte,endByte,evidence);
 candidate.composite!.sectionReplacement={kind:'numbered-section-range',startByte,endByte,newline:state.documentBytes.includes(0x0d)?'\r\n':'\n',startAtLineStart:true,endAfterCompleteLine:true,requestedSectionIds};
 return candidate;
}

/** Resolves only `sections <number>–<number>` against complete numbered Markdown section bodies. */
export function resolveSectionRange(state:DocumentState,raw:string):SectionRangeResolution {
 const match=/^(?:sections?\s+)?(\d+(?:\.\d+)*)\s*[–-]\s*(\d+(?:\.\d+)*)$/iu.exec(raw.trim());
 if(!match)return {reason:'SECTION_RANGE_INVALID'};
 const sectionNumber=(entry:StructuralEntry)=>{
  if(!['section','subsection','heading'].includes(entry.type))return;
  return /^#{1,6}\s+(\d+(?:\.\d+)*)(?=[\s.:]|$)/u.exec(entryText(state,entry.entryId))?.[1];
 };
 const numbered=state.structuralIndex.entries.filter(entry=>sectionNumber(entry) !== undefined);
 const starts=numbered.filter(entry=>sectionNumber(entry)===match[1]);
 const ends=numbered.filter(entry=>sectionNumber(entry)===match[2]);
 if(starts.length>1||ends.length>1)return {reason:'SECTION_RANGE_AMBIGUOUS'};
 if(starts.length!==1||ends.length!==1)return {reason:'SECTION_RANGE_NOT_FOUND'};
 const [start]=starts,[end]=ends;
 if(start.startByte>end.startByte)return {reason:'SECTION_RANGE_REVERSED'};
 const startByte=start.startByte,endByte=sectionBodyEnd(state,end);
 const startsAtLineStart=startByte===0||state.documentBytes[startByte-1]===0x0a;
 const endsAfterCompleteLine=endByte===state.documentBytes.length||state.documentBytes[endByte-1]===0x0a;
 if(!startsAtLineStart||!endsAfterCompleteLine||!hasSectionBody(state,startByte,endByte))return {reason:'SECTION_RANGE_INCOMPLETE_BODY'};
 const entryIds=state.structuralIndex.entries.filter(entry=>entry.type!=='document'&&entry.startByte>=startByte&&entry.endByte<=endByte).map(entry=>entry.entryId);
 const candidate=compositeCandidate(state,[start,end],startByte,endByte,`explicit numbered section range ${match[1]}–${match[2]}`);
 const sectionReplacement:SectionReplacementContract={kind:'numbered-section-range',startByte,endByte,newline:state.documentBytes.includes(0x0d)?'\r\n':'\n',startAtLineStart:true,endAfterCompleteLine:true,requestedSectionIds:[start.entryId,end.entryId]};
 candidate.composite!.sectionReplacement=sectionReplacement;
 return {candidate,entryIds};
}

function successorSelectionQuery(query:string){const selected=/(?:\bsecci[oó]n|\bsubsecci[oó]n|\bsection|\bsubsection|\bapartado)\s+(?:de(?:l|\s+la)?\s+)?(.+?)(?=[,;:.]|\b(?:para|pero|donde|que|conserva|preserva|mant(?:é|e)n|keep)\b|$)/iu.exec(query)?.[1];return dropStopwords((selected??query).replace(new RegExp(DOMAIN.vocabulary.displayNounStripPattern,'giu'),' ').trim());}
/**
 * The section-label convention (`_core/conventions/sections.json`), read rather
 * than restated: a heading whose first token is a label (`3.1`, `O1.`) is
 * matched exactly with or without that label.
 */
const SECTION_CONVENTION=JSON.parse(readFileSync(new URL('../../conventions/sections.json',import.meta.url),'utf8')) as {label:string;closer:string};
const SECTION_LABEL=new RegExp(`^(?:${SECTION_CONVENTION.label})(?:${SECTION_CONVENTION.closer})?$`,'u');
/** A query that opens with ATX level marks (`## Data`) names a heading at exactly that level. */
const LEVEL_MARKS=/^[ \t]{0,3}(#{1,6})[ \t]+(?=\S)/u;
/** What an exact heading match is worth over the same words matched inside a longer heading: more than the gate's margin of 4. */
const EXACT_HEADING=6;
/**
 * Lowercased tokens of a heading or a query. A dotted identifier (`3.1`,
 * `H2.1`) stays one token, so an identifier is compared whole: `o1` is not a
 * token of `O10`.
 */
const headingTokens=(value:string)=>(value.toLowerCase().match(/[\p{L}\p{N}_-]+(?:\.\p{N}+)*/gu)??[]).filter(token=>token.length>=2);
/** A heading's matchable tokens: each whole token plus the parts of a hyphenated or underscored one, so `entropy` still reaches `Cross-entropy`. */
const matchableTokens=(title:string)=>{const whole=headingTokens(title);return new Set([...whole,...whole.flatMap(token=>token.split(/[-_]/u)).filter(part=>part.length>=2)]);};
const contentTokens=(tokens:Iterable<string>)=>new Set([...tokens].filter(token=>!STOPWORDS.has(token)));
const sameSet=(left:Set<string>,right:Set<string>)=>left.size===right.size&&[...left].every(token=>right.has(token));
type HeadingOutlineEntry={entry:StructuralEntry;level:number;title:string;path:string[]};
/**
 * Every ATX heading with its level, its title and its REAL ancestor path (the
 * nearest shallower heading at each level). The structural index's own
 * `headingPath` lists preceding headings, siblings included, so it cannot tell
 * two `### Setup` sections apart; this can.
 */
function headingOutline(state:DocumentState):HeadingOutlineEntry[]{
 const stack:{level:number;title:string}[]=[];
 return state.structuralIndex.entries.filter(entry=>['section','subsection','heading'].includes(entry.type)).sort((left,right)=>left.startByte-right.startByte).flatMap(entry=>{
  const match=/^[ \t]{0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$/u.exec(entryText(state,entry.entryId).split(/\r?\n/u,1)[0]);
  if(!match)return [];
  const level=match[1].length,title=match[2].trim();
  while(stack.length&&stack.at(-1)!.level>=level)stack.pop();
  stack.push({level,title});
  return [{entry,level,title,path:stack.map(item=>item.title)}];
 });
}
/** True when the query's content words are exactly the heading's, with or without its leading section label. */
function exactHeading(title:string,query:Set<string>){
 if(!query.size)return false;
 const [first,...rest]=title.split(/\s+/u);
 const variants=[title,...(first&&rest.length&&SECTION_LABEL.test(first)?[rest.join(' ')]:[])];
 return variants.some(variant=>sameSet(contentTokens(headingTokens(variant)),query));
}

/**
 * Builds a successor locus candidate directly from a matched heading's natural
 * span (heading start through the next same-or-higher-level heading, or the
 * document end). Unlike `sectionReplacementCandidate` (used only by the
 * explicit numbered-range path), this does NOT require a "complete section
 * body" or line-start/line-end alignment, and never attaches a
 * `sectionReplacement` contract: the byte-preserving composite engine splices
 * at these exact offsets directly, with no boundary reformatting, so those
 * numbered-range-only requirements would only add friction here.
 */
function successorLocusCandidate(state:DocumentState,entry:StructuralEntry,evidence:string){
 const startByte=entry.startByte,endByte=rootBlockEnd(state,entry)??sectionBodyEnd(state,entry);
 if(endByte<startByte)return;
 // The heading's own structural entry may end before the natural section
 // boundary (e.g. when it has child subsections it does not itself span);
 // find whichever entry actually ends exactly at that boundary so
 // `materializeCompositeTarget` can validate the composite's full span.
 const last=state.structuralIndex.entries.filter(candidate=>candidate.startByte>=startByte&&candidate.endByte===endByte).sort((left,right)=>right.startByte-left.startByte)[0];
 if(!last)return;
 return compositeCandidate(state,[entry,last],startByte,endByte,evidence);
}

/** `<exact heading title>#<n>`: the title as the heading spells it, then `#` and an ordinal with no space before it. */
const HEADING_ORDINAL=/^(.*\S)#([1-9]\d*)$/u;
/**
 * The one heading a `<title>#<n>` query names: the n-th heading, in document order, whose
 * title is exactly `<title>` (and whose level is the requested one, when the query opens with
 * level marks). It exists for a title two or more headings share -- a first revision rendered
 * by an earlier release pasted each source's own `#` title, so a source titled like the document left
 * byte-identical headings that no choice of words can tell apart. `paper-writing`'s
 * `separate`/`bind` read the same `<title>#<n>` form, counted the same way.
 *
 * `undefined` -- read the query as before -- unless it has that shape, no heading is literally
 * titled the whole query, and at least two headings carry the title; so no query that resolved
 * before resolves differently now. An ordinal past the last occurrence names nothing.
 */
function headingOrdinalTarget(state:DocumentState,raw:string,requestedLevel:number|undefined):SuccessorTargetResolution|undefined{
 const match=HEADING_ORDINAL.exec(raw);
 if(!match)return undefined;
 const outline=headingOutline(state).filter(heading=>requestedLevel===undefined||heading.level===requestedLevel);
 if(outline.some(heading=>heading.title===raw))return undefined;
 const same=outline.filter(heading=>heading.title===match[1]!.trim());
 if(same.length<2)return undefined;
 const heading=same[Number(match[2])-1];
 const structural=heading&&successorLocusCandidate(state,heading.entry,`heading ordinal ${match[2]} of ${same.length}: ${heading.title}`);
 if(!heading||!structural)return {candidates:[],reason:'SUCCESSOR_TARGET_NOT_FOUND'};
 return {candidates:[{...structural,headingPath:heading.path,headingLevel:heading.level,matchedTerms:[],score:100,confidence:1,evidence:[...structural.evidence,'exact heading ordinal']}]};
}

/**
 * Resolves a semantic successor target into one Markdown heading's natural span, inferred from the request/deliberation without requiring a numbered range.
 *
 * A query term matches a heading when it equals one of the heading's tokens
 * (never a substring of one), and a heading whose words are exactly the
 * query's earns `EXACT_HEADING` on top, so `Alignment loss` names the section
 * of that name rather than tying with `Alignment loss weighting`. A query that
 * opens with level marks (`## Data`) only considers headings of that level,
 * which is how an outer section is named when a nested heading shares its
 * words. Nested matches are NOT collapsed to the innermost: the gate decides
 * on the scores, and a tie lists every candidate with its level and path.
 */
export function resolveSuccessorTarget(state:DocumentState,query:string):SuccessorTargetResolution {
 const marks=LEVEL_MARKS.exec(query);
 const requestedLevel=marks?marks[1].length:undefined;
 const ordinal=headingOrdinalTarget(state,marks?query.slice(marks[0].length).trim():query.trim(),requestedLevel);
 if(ordinal)return ordinal;
 // A level-marked query is a heading spelled out, so it is read literally:
 // the section-noun and display-noun stripping below would eat a heading word.
 const semanticQuery=marks?query.slice(marks[0].length).trim():successorSelectionQuery(query);
 const allTerms=[...new Set(headingTokens(semanticQuery))],content=allTerms.filter(term=>!STOPWORDS.has(term));
 const terms=content.length?content:allTerms,querySet=new Set(terms);
 // Scored on the heading LINE alone, never on `resolveTargets`. That scorer
 // reads an entry's body, its neighbours and its `headingPath`, so a section
 // inherited its parent's title words and every section competed with the root
 // block's introduction, which paraphrases the whole paper. Matching a heading
 // means matching what the heading says.
 const direct=headingOutline(state).filter(heading=>requestedLevel===undefined||heading.level===requestedLevel).flatMap(heading=>{
  const tokens=matchableTokens(heading.title),matchedTerms=terms.filter(term=>tokens.has(term));
  if(!matchedTerms.length)return [];
  const exact=exactHeading(heading.title,querySet);
  return [{heading,matchedTerms,score:matchedTerms.length*3+(exact?EXACT_HEADING:0),confidence:exact?1:Math.min(1,matchedTerms.length/3),evidence:exact?[...matchedTerms,'exact heading']:matchedTerms}];
 });
 // A successor locus must be matched by its own heading line. Falling back to
 // `headingCandidates` would accept a section scored on its BODY — including a
 // descendant equation's `\tag`, whose label the section entry also carries —
 // so a query like "3-3" silently resolved to whichever section owns equation 3.
 // A wrong target is worse than none: report NOT_FOUND and let the caller name
 // the section.
 if(!direct.length)return {candidates:[],reason:'SUCCESSOR_TARGET_NOT_FOUND'};
 const candidates=direct.flatMap(match=>{
  const structural=successorLocusCandidate(state,match.heading.entry,`semantic successor target: ${match.evidence.join(', ')}`);
  return structural?[{...structural,headingPath:match.heading.path,headingLevel:match.heading.level,matchedTerms:match.matchedTerms,score:match.score,confidence:match.confidence,evidence:[...structural.evidence,...match.evidence]}]:[];
 });
 // `ambiguityGate` reads candidates[0] as the best and measures the margin to
 // candidates[1], so they must arrive sorted by score. Document order would
 // hand it the weakest first and turn a clear win into a negative margin.
 // Equal scores always block, so their order only shapes the menu: document
 // order reads the way the document does.
 const canonical=candidates.sort((left,right)=>right.score-left.score||left.composite!.startByte-right.composite!.startByte);
 return canonical.length?{candidates:canonical}:{candidates:[],reason:'SUCCESSOR_TARGET_NOT_FOUND'};
}

/**
 * Change 8, option (b): locates the change header's OWN structural entry by its declared
 * heading text (`profile.artifact.changeHeader.heading`), and returns it as a one-entry
 * composite candidate at its natural span -- exactly the span `document-index.ts` already
 * gives a heading chunk (start through the next heading of ANY level), so it never needs
 * `sectionBodyEnd`'s same-or-higher-level widening. `undefined` when the document does not
 * (yet) carry the header, e.g. a document seeded before the profile declared one.
 */
export function changeHeaderLocusCandidate(state:DocumentState,heading:string):TargetCandidate|undefined{
 const entry=changeHeaderEntry(state,heading);
 if(!entry)return undefined;
 return compositeCandidate(state,[entry],entry.startByte,entry.endByte,'change header locus');
}

export function materializeCompositeTarget(state:DocumentState,candidate:TargetCandidate){
 const composite=candidate.composite;if(!composite)return;
 const existing=state.structuralIndex.byId[candidate.entryId];if(existing)return existing;
 const first=state.structuralIndex.byId[composite.entryIds[0]],last=state.structuralIndex.byId[composite.entryIds.at(-1)!];
 if(composite.documentSha256!==state.documentSha256||!first||!last||first.startByte!==composite.startByte||last.endByte<composite.endByte||sha256(state.documentBytes.subarray(composite.startByte,composite.endByte))!==composite.textSha256)throw new Error('INVALID_COMPOSITE_TARGET');
 const entry:StructuralEntry={entryId:candidate.entryId,type:'composite',startByte:composite.startByte,endByte:composite.endByte,textSha256:composite.textSha256,parentId:first.parentId,childIds:[],ordinal:first.ordinal,headingPath:first.headingPath,labels:[],tags:[],lexicalTerms:[],deterministicAliases:[],neighboringEntryIds:[],...(composite.sectionReplacement?{sectionReplacement:composite.sectionReplacement}:{})};
 state.structuralIndex.entries.push(entry);state.structuralIndex.byId[entry.entryId]=entry;return entry;
}

export function resolveTargets(state:DocumentState,query:string,options:TargetResolutionOptions={}):TargetCandidate[]{
 const exact=exactCompositeTargets(state,query);
 const composite=exact.length?exact:(options.allowInterEntryWhitespaceFallback?interEntryWhitespaceCompositeTargets(state,query):[]);
 if(composite.length||query.includes('$$'))return composite;
 const direct=state.structuralIndex.byId[query]??state.structuralIndex.entries.find(e=>e.labels.includes(query)||e.tags.includes(query));
 if(direct&&direct.type!=='document')return [{entryId:direct.entryId,type:direct.type,headingPath:direct.headingPath,matchedTerms:[],matchedLabels:direct.labels,matchedTags:direct.tags,matchedSymbols:[],score:100,confidence:1,shortPreview:entryText(state,direct.entryId).slice(0,180),evidence:['explicit selection']}];
 const terms=words(query); const equationRequested=DISPLAY_NOUN.test(query); const oneHot=SUBJECT.test(query);
 const entries=(equationRequested?state.structuralIndex.entries.filter(e=>e.type==='display_equation'):state.structuralIndex.entries).filter(e=>e.type!=='document');
 // Ownership is resolved over EVERY entry, not the filtered set: an equation
 // still declares its tag even when the filter above has excluded its ancestors.
 const labelOwner=declaringEntries(state.structuralIndex.entries,'labels'),tagOwner=declaringEntries(state.structuralIndex.entries,'tags');
 // A term counts as an entry's OWN only when the entry is the smallest one that
 // writes it — the same "smallest entry carrying it declares it" rule
 // `declaringEntries` applies to labels and tags, and for the same reason: a
 // section's text contains every entry nested inside it, so an ancestor would
 // otherwise score a descendant's words as if it had written them itself and tie
 // with the descendant that did. An ancestor keeps the demoted CONTEXT_TERM, so
 // it stays findable by its body, just never ahead of the entry that owns it.
 const scored=state.structuralIndex.entries.filter(e=>e.type!=='document');
 const ownLower=new Map(scored.map(e=>[e.entryId,entryText(state,e.entryId).toLowerCase()]));
 const writes=(entryId:string,term:string)=>ownLower.get(entryId)?.includes(term)??false;
 const declares=(e:StructuralEntry,term:string)=>writes(e.entryId,term)&&!scored.some(other=>other.entryId!==e.entryId&&other.startByte>=e.startByte&&other.endByte<=e.endByte&&other.endByte-other.startByte<e.endByte-e.startByte&&writes(other.entryId,term));
 return entries.map(e=>{
  const own=entryText(state,e.entryId); const neighbors=e.neighboringEntryIds.map(id=>entryText(state,id)).join('\n'); const nearby=`${own}\n${neighbors}\n${e.headingPath.join(' ')}`.toLowerCase();
  const matchedTerms=terms.filter(t=>nearby.includes(t)||e.lexicalTerms.includes(t)||e.deterministicAliases.some(a=>a.includes(t)));
  const declaredTerms=matchedTerms.filter(t=>declares(e,t)); const termScore=declaredTerms.length*OWN_TERM+(matchedTerms.length-declaredTerms.length)*CONTEXT_TERM;
  const matchedLabels=e.labels.filter(x=>isolatedInQuery(query,x)&&labelOwner.get(x)?.id===e.entryId); const matchedTags=e.tags.filter(x=>isolatedInQuery(query,x)&&tagOwner.get(x)?.id===e.entryId);
  const symbols=equationSymbols(own); const matchedSymbols=symbols.filter(symbol=>Object.values(state.symbolIndex.symbols).some(x=>x.normalized===symbol.replace(/^\\/,'').toLowerCase()||x.uses.includes(e.entryId)));
  const semanticEvidence=oneHot&&SUBJECT.test(neighbors)?4:0;
  const oneHotMatch=SUBJECT.test(own)||semanticEvidence>0;const score=termScore+matchedLabels.length*8+matchedTags.length*8+semanticEvidence+(equationRequested&&e.type==='display_equation'&&(!oneHot||oneHotMatch)?3:0);
  return {entryId:e.entryId,type:e.type,headingPath:e.headingPath,matchedTerms,matchedLabels,matchedTags,matchedSymbols,score,confidence:Math.min(1,score/12),shortPreview:own.slice(0,180),evidence:[...matchedTerms,...matchedLabels,...matchedTags,...(semanticEvidence?[DOMAIN.vocabulary.subjectEvidenceLabel]:[])]};
 }).filter(c=>c.score>0).sort((a,b)=>b.score-a.score||a.entryId.localeCompare(b.entryId)).slice(0,8);
}

export function resolveSourceAndDestination(state:DocumentState,sourceQuery:string,destinationQuery:string){return {sourceCandidates:resolveTargets(state,sourceQuery),destinationCandidates:resolveTargets(state,destinationQuery)}}
