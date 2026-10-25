import { sha256,type FidelityConstraints,type Position,type ResolvedIntent } from './types.js';
import { DOMAIN } from './domain-profile.js';
import { scanManagedRevision } from './artifact-naming.js';
const REVISION_REFERENCE=/(?:\brevisi[oó]n\s+(?:administrada\s+)?(?:[a-z0-9-]+\s+)?r\d{2,}\b|\br\d{2,}\b)/i;
const OPERATION_ID=/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/i;
// Operation verbs match as whole words (Unicode letters on both sides), allowing only the
// infinitive `r` and enclitic pronouns, so "borrador", "preliminares" or "remueve" never
// select DELETE or MOVE by substring.
const verbs=(...stems:string[])=>new RegExp(`(?<![\\p{L}\\p{N}])(?:${stems.join('|')})r?(?:l[oa]s?|les?)?(?![\\p{L}\\p{N}])`,'iu');
const DESTRUCTIVE_VERB=verbs('elimina','borra','quita','suprime','remueve');
const MOVE_VERB=verbs('mueve','traslada');
const position=(s:string):Position|undefined=>/al inicio|dentro.*inicio|inside.?start/i.test(s)?'inside_start':/al final|dentro.*final|inside.?end/i.test(s)?'inside_end':/antes de|before/i.test(s)?'before':/despu[eé]s de|after/i.test(s)?'after':undefined;
function descriptions(instruction:string){const match=instruction.match(/(?:mueve|traslada|copia|duplica|pasa este contenido)\s+(.+?)\s+(?:a|en|antes de|despu[eé]s de)\s+(.+)/i);return {source:match?.[1]?.trim(),destination:match?.[2]?.trim()};}
function fidelityConstraints(instruction:string):FidelityConstraints {const match=instruction.match(/(?:reemplaza|sustituye)\s+(?:exactamente\s+|literalmente\s+)?este\s+bloque\s*:\s*([\s\S]*?)\s*\n(?:por|con)\s+este\s+bloque\s*:\s*([\s\S]*?)(?:\s*\n(?:no\s+(?:modifiques|cambies)\s+(?:ningún|ningun|nada)|no\s+reformatees)|\s*$)/i);if(!match)return {};return {targetBlock:match[1],replacementBlock:match[2],preserveExternalBytes:true,noReformat:true,noSemanticReinterpretation:true};}
function lifecycleIntent(instruction:string):ResolvedIntent['intent']|undefined {
 const restore=/(?:restaura|restaurar|restore|reinstala|recupera)\b/i.test(instruction);
 const withdraw=/(?:retira|retirar|retire|withdraw|jubila|remove\s+(?:the\s+)?revision|remueve\s+(?:la\s+)?revisi[oó]n|quita\s+(?:la\s+)?revisi[oó]n)\b/i.test(instruction);
 const destructive=DESTRUCTIVE_VERB.test(instruction);
 const filename=scanManagedRevision(instruction)!==undefined,revision=REVISION_REFERENCE.test(instruction),operationId=OPERATION_ID.test(instruction);
 if (restore&&(filename||revision||operationId)) return 'RESTORE_WITHDRAWN_REVISION';
 if (withdraw&&(filename||revision)) return 'WITHDRAW_REVISION';
 if (destructive&&(filename||revision)) return 'AMBIGUOUS';
 return undefined;
}
export function extractManagedRevisionFilename(instruction:string) { return scanManagedRevision(instruction); }
export function extractRevisionReference(instruction:string) { const match=instruction.match(/\br(\d{2,})\b/i); return match?`r${match[1]}`.toLowerCase():undefined; }
export function extractWithdrawalOperationId(instruction:string) { return instruction.match(OPERATION_ID)?.[0].toLowerCase(); }

const CLOSE_DELIBERATION=/(?:cierra|finaliza|termina)\s+(?:la\s+|el\s+)?(?:deliberaci[oó]n|conversaci[oó]n|chat)|close\s+(?:the\s+)?(?:deliberation|chat|conversation)|end\s+(?:the\s+)?deliberation/i;

export function resolveIntent(instruction:string):ResolvedIntent {
 const s=instruction.toLowerCase(),has=(...x:string[])=>x.some(v=>s.includes(v));
 const destructive=DESTRUCTIVE_VERB.test(instruction);
 // Explicit natural-language CLOSE (task 2.3): recognized before any other keyword, never ambiguous.
 const closeDeliberation=CLOSE_DELIBERATION.test(instruction);
 const lifecycleSelection=lifecycleIntent(instruction);
 let intent:ResolvedIntent['intent']=closeDeliberation?'CLOSE_DELIBERATION':(lifecycleSelection??'AMBIGUOUS');
 if(intent==='AMBIGUOUS'&&lifecycleSelection===undefined) {
  if(MOVE_VERB.test(instruction)||has('pasa este contenido a'))intent='MOVE';
  else if(has('copia','duplica en')||(has('incluye también en')&&has('conserva','mantén','preserva')))intent='COPY';
  else if(destructive)intent='DELETE';
  else if(has('agrega','inserta','añade'))intent='INSERT';
  else if(has('analiza','propón alternativas','no la cambies','delibera','explica'))intent='DELIBERATE';
  else if(has('revisa críticamente','review explícito','revisión independiente'))intent='REVIEW';
  else if(has('adapta','reorganiza el argumento','conceptual',...DOMAIN.vocabulary.conceptualTerms))intent='CONCEPTUAL_REVISION';
  else if(has('cambia','modifica','reemplaza','corrige','aplica','aplicar'))intent='MODIFY';
 }
 const adaptive=has('adapta la transición','ajusta al nuevo contexto','reformula para que encaje');
 const moveCopy=intent==='MOVE'||intent==='COPY';
 const lifecycle=intent==='WITHDRAW_REVISION'||intent==='RESTORE_WITHDRAWN_REVISION';
 const parsed=descriptions(instruction);
 const fidelity=fidelityConstraints(instruction);
 const semanticCleanup=has('elimina los remanentes','quita redundancias','adapta la transición','deja coherente','elimina lo repetido','limpia el texto residual','quita el texto residual');
 const cleanupLevel:ResolvedIntent['cleanupLevel']=semanticCleanup?'SEMANTIC':(has('cleanup estructural','limpia separadores')?'STRUCTURAL':'NONE');
 const semanticChange=intent==='MODIFY'||intent==='CONCEPTUAL_REVISION'||adaptive;
 const targetDescription=has(...DOMAIN.vocabulary.subjectTerms)?DOMAIN.vocabulary.subjectLocusDescription:fidelity.targetBlock??instruction;
 const ambiguous=intent==='AMBIGUOUS'||(intent==='DELETE'&&!destructive)||(has('reorganiza')&&!moveCopy&&intent!=='CONCEPTUAL_REVISION');
 const pendingQuestions=ambiguous?['Indicá el fragmento o alcance exacto.']:[];
 const constraints:string[]=[];
 if(fidelity.targetBlock)constraints.push('Use only the supplied target block.');
 if(fidelity.replacementBlock)constraints.push('Use the supplied replacement block byte-for-byte.');
 if(fidelity.preserveExternalBytes)constraints.push('Preserve external bytes.');
 if(fidelity.noReformat)constraints.push('Do not reformat.');
 if(fidelity.noSemanticReinterpretation)constraints.push('Do not semantically reinterpret supplied replacement text.');
 return {intent:ambiguous?'AMBIGUOUS':intent,targetDescription,sourceDescription:moveCopy?parsed.source:undefined,destinationDescription:moveCopy?parsed.destination:undefined,requestedPosition:position(instruction),requestedEffect:DOMAIN.vocabulary.requestedEffect&&has(...DOMAIN.vocabulary.requestedEffect.terms)?DOMAIN.vocabulary.requestedEffect.label:undefined,semanticChange,constraints,fidelity,scope:has('sección','subsección')?'SECTION':'LOCAL',evidence:[instruction],destructiveIntent:lifecycle||intent==='DELETE'||intent==='MOVE',cleanupAuthorized:semanticCleanup,moveMode:adaptive?'ADAPTIVE':'LITERAL',removeSource:intent==='MOVE',cleanupLevel,modelBudget:intent==='CONCEPTUAL_REVISION'?2:(adaptive&&moveCopy?1:0),confidence:ambiguous?0:.85,pendingQuestions,unresolvedQuestions:pendingQuestions};
}
export const instructionHash=(instruction:string)=>sha256(instruction);
