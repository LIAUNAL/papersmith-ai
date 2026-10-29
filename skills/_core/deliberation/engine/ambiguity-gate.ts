import type { TargetCandidate } from './types.js';
export function ambiguityGate(candidates:TargetCandidate[]){
 if(!candidates.length)return {blocked:true,status:'ambiguous' as const,question:'No target found. Name the section, the label or a distinctive fragment.',candidates:[]};
 const [first,second]=candidates;
 if(second&&first.score-second.score<=4){
  // Terms every candidate matched carry no discriminating power; naming them
  // turns an opaque menu into an error the caller can act on, because the fix
  // is to drop them, never to add more words.
  const shared=(first.matchedTerms??[]).filter(term=>candidates.every(c=>(c.matchedTerms??[]).includes(term)));
  const hint=shared.length?`\n\nThe terms ${shared.map(t=>`"${t}"`).join(', ')} match every candidate and do not discriminate: repeat the query without them, keeping only distinctive words — no stopwords, no punctuation, no section number, and with accents exactly as they appear in the heading.`:'';
  // A heading locus names its level marks and its real ancestor path, so two
  // `### Setup` sections, or a section and the subsection inside it, read as
  // different candidates. When one candidate spans another, say how to name
  // the outer one: by its level marks.
  const label=(c:TargetCandidate)=>c.headingLevel?`${'#'.repeat(c.headingLevel)} ${(c.headingPath??[]).join(' › ')}`:((c.headingPath??[]).join(' › ') || c.type);
  const nested=candidates.some(outer=>candidates.some(inner=>inner!==outer&&outer.composite&&inner.composite&&inner.composite.startByte>=outer.composite.startByte&&inner.composite.endByte<=outer.composite.endByte));
  const outerHint=nested?'\n\nOne candidate contains another. To name the outer section, open the query with its level marks, e.g. `## <heading>`; to name the inner one, use its own heading words.':'';
  return {blocked:true,status:'ambiguous' as const,question:`Select a target:\n${candidates.map((c,i)=>`${i+1}. ${label(c)}: ${c.shortPreview??''}`).join('\n')}${hint}${outerHint}`,candidates};
 }
 return {blocked:false,status:'resolved' as const,candidate:first,candidates:[first]};
}
