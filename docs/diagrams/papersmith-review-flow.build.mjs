/**
 * The source of `papersmith-review-flow.html` beside this file: the flow of a
 * review workspace (`smith init --kind review`, `paper_kind: review`), drawn
 * from the repository's own files the same way `papersmith-pi-flow.build.mjs`
 * draws the experimental line.
 *
 *   SCRATCH=$(mktemp -d)
 *   node docs/diagrams/papersmith-review-flow.build.mjs "$SCRATCH/candidate.json"
 *   node <archify-3.0.1>/bin/archify.mjs finalize architecture \
 *     "$SCRATCH/candidate.json" "$SCRATCH/papersmith-review-flow.html" \
 *     --repo-root . --quality showcase --out-dir "$SCRATCH/evidence" --json
 *
 * The lanes are the ten review steps the dashboard shows under Pipeline for a
 * review workspace (`review_board.REVIEW_STAGES` and `REVIEW_LABELS`, the steps
 * of `src/papersmith/templates/paper-flow-review.md.tpl`), numbered 1 to 10;
 * `tests/test_review_flow_diagram.py` holds the numbering and the labels
 * against the board, and every `review_cli.py` verb and `review/` record named
 * here against `review_cli.py`. The three operator gates (G-PROTOCOL,
 * G-SCREENING, G-SYNTHESIS) are `security` nodes, and the edge that leaves
 * each one is the step it unlocks (`review_board.REVIEW_PHASE_GATES`).
 *
 * Every label is English; the Pi flow has no translation table any more, so
 * neither does this one. Every node's `sources` names the repository path and
 * line range it was transcribed from, checked by Archify's strict provenance
 * gate against `meta.repository.revision`.
 *
 * The layout follows the Pi flow's measured constraints: five columns of 182px
 * (the 1240px readability cap), a label only on an edge that leaves its row
 * (a 24px gap between row neighbours cannot hold one), and every edge routable
 * between row neighbours, straight down a column, or with one bend through the
 * corridor between two rows.
 */
import fs from 'fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = fileURLToPath(new URL('../../', import.meta.url)).replace(/\/$/, '');

const S=(path,line,end_line)=>{const r={path};if(line)r.line=line;if(end_line)r.end_line=end_line;return [r];};
const CLI='skills/systematic-review/scripts/review_cli.py';
const BOARD='skills/_core/command_center/review_board.py';
const SKILL='skills/systematic-review/SKILL.md';
const FLOW='src/papersmith/templates/paper-flow-review.md.tpl';
const C=(line,end_line)=>({path:CLI,line,end_line});
const B=(line,end_line)=>({path:BOARD,line,end_line});
const K=(line,end_line)=>({path:SKILL,line,end_line});
const T=(line,end_line)=>({path:FLOW,line,end_line});

const agentMeta=n=>{const fm=fs.readFileSync(`${REPO}/.pi/agents/${n}.md`,'utf8').split('---')[1];
 const tools=[...fm.split('tools:')[1].matchAll(/^\s+-\s+(\S+)/gm)].map(m=>m[1]);
 const caps=[];if(tools.some(t=>t==='write'||t==='edit'))caps.push('writes');if(tools.includes('bash'))caps.push('bash');if(tools.includes('mcp'))caps.push('MCP');
 const endLine=fs.readFileSync(`${REPO}/.pi/agents/${n}.md`,'utf8').split('---')[1].split('\n').length;
 return {sub:caps.length?'reads · '+caps.join(' · '):'read-only',end:endLine};};
const A=n=>S(`.pi/agents/${n}.md`,1,agentMeta(n).end);
const P=n=>({path:`.pi/prompts/${n}.md`,line:1,end_line:7,label:'template /'+n});
const n=(id,lane,col,type,label,sublabel,extra={})=>({id,lane,col,type,label,sublabel,...extra});
const agent=(id,lane,col,name,extra={})=>n(id,lane,col,'backend',name,agentMeta(name).sub,{...extra,sources:[...A(name),...(extra.sources||[])]});

const nodes=[
 // 1 · Harness
 n('init','harness',0,'messagebus','smith init --kind review','review/ · 9 review contracts',{tag:'smith kind set review',sources:[{path:'src/papersmith/core/init.py',line:59,end_line:82},{path:'src/papersmith/core/init.py',line:142,end_line:143},{path:'src/papersmith/core/manifest.py',line:390,end_line:394}]}),
 n('config','harness',1,'database','.papersmith/config.json','paper_kind: review',{sources:[{path:'src/papersmith/core/init.py',line:543},{path:'skills/_core/paper_types/decision.py',line:144,end_line:151}]}),
 n('ui','harness',2,'external','smith ui','ten review steps · Review tab',{tag:'command center',sources:[B(47,65),B(630,688),{path:'skills/_core/command_center/static/review-panel.js',line:1,end_line:12}]}),
 n('status','harness',3,'messagebus','smith status · audit','audit . --check-drift',{sources:[{path:'skills/_core/command_center/phase_actions.py',line:84,end_line:91},B(70,70),T(16,17)]}),
 n('upgrade','harness',4,'frontend','/upgrade-project','older release only',{tag:'.pi/prompts',sources:[P('upgrade-project'),{path:'skills/_core/command_center/phase_actions.py',line:92,end_line:96}]}),

 // 2 · Scoping
 n('scopeCmd','scope',0,'frontend','/systematic-review scope','topic in ≥ 2 sentences',{sources:[K(36,42),B(71,84)]}),
 n('scopeCli','scope',1,'messagebus','review_cli.py scope','OpenAlex · type:review',{tag:'not part of the PRISMA flow',sources:[C(517,529),C(1417,1420)]}),
 n('scopeJson','scope',2,'database','review/scope.json','existing reviews · the gap',{sources:[C(525,526),B(206,206)]}),
 n('plaus','scope',3,'frontend','/plausibility','optional · field constellation',{tag:'.pi/prompts',sources:[P('plausibility'),T(18,21)]}),
 n('pool','scope',4,'database','sota-pool/','atlas.html',{sources:[{path:'src/papersmith/core/init.py',line:63,end_line:74},T(20,21)]}),

 // 3 · Protocol
 n('protCmd','protocol',0,'frontend','/systematic-review protocol','RQs · PICOC · criteria · queries',{sources:[K(44,69),B(85,102)]}),
 n('initCli','protocol',1,'messagebus','review_cli.py init','protocol.json template',{sources:[C(316,327),C(1406,1409)]}),
 n('protJson','protocol',2,'database','review/protocol.json','one query per source',{tag:'items 5-7',sources:[C(186,188),K(46,63)]}),
 n('check','protocol',3,'messagebus','review_cli.py protocol','check · lists what is missing',{sources:[C(328,338),C(1411,1415)]}),
 n('gProt','protocol',4,'security','G-PROTOCOL','protocol approve --by · operator',{tag:'before any search',sources:[C(339,347),B(97,98),K(63,66)]}),
 n('lock','protocol',4,'database','review/protocol.lock.json','approver · sha256 · amendments',{rowOff:1,sources:[C(190,192),C(347,347)]}),
 n('amend','protocol',3,'messagebus','protocol amend','--by · --reason · logged',{rowOff:1,tag:'after the approval',sources:[C(348,358),B(99,100)]}),
 n('reg','protocol',2,'frontend','/paper-writing declare','review-registration',{rowOff:1,tag:'PROSPERO · OSF · item 24',sources:[{path:'skills/paper-writing/SKILL.md',line:462,end_line:466},{path:'skills/_core/command_center/review_view.py',line:41},T(30,31)]}),

 // 4 · Identification
 n('search','ident',4,'messagebus','review_cli.py search','openalex · crossref · europepmc',{tag:'after G-PROTOCOL',sources:[C(531,548),C(1422,1425)]}),
 n('searches','ident',3,'database','review/searches.jsonl','date · exact query · counts',{tag:'item 16',sources:[C(498,514)]}),
 n('import','ident',2,'messagebus','review_cli.py import','RIS · BibTeX export · --query',{tag:'Scopus · WoS · IEEE · ACM',sources:[C(621,641),C(1427,1432)]}),
 n('records','ident',3,'database','review/records.jsonl','one row per record · search_id',{rowOff:1,sources:[C(498,514)]}),
 n('dedupe','ident',2,'messagebus','review_cli.py dedupe','DOI, then title and year',{rowOff:1,sources:[C(644,675),C(1434,1435)]}),

 // 5 · Screening
 n('scrCmd','screen',4,'frontend','/systematic-review screen','the agent is one reviewer',{sources:[K(83,107),B(121,141)]}),
 n('screen','screen',3,'messagebus','review_cli.py screen','--stage ta → ft · 2 reviewers',{tag:'ft: one exclusion criterion',sources:[C(747,774),C(1446,1455)]}),
 n('screening','screen',2,'database','review/screening.jsonl','one decision per row',{tag:'item 8',sources:[C(770,770),B(210,210)]}),
 n('qck','screen',1,'messagebus','queue · conflicts · kappa','owed · disagreements · agreement',{sources:[C(734,823),C(1436,1460)]}),
 n('settle','screen',0,'security','Operator settles','each conflict · screen --final',{sources:[K(92,93),T(43,46),T(91,95)]}),
 n('ingest','screen',3,'frontend','/paper-ingestion','full texts for --stage ft',{rowOff:1,tag:'.pi/prompts',sources:[P('paper-ingestion'),K(95,97)]}),
 n('prio','screen',2,'messagebus','review_cli.py prioritize','100–200 refs · SJR quartile',{rowOff:1,tag:'--apply after the operator',sources:[C(1166,1232),C(1485,1495)]}),
 n('gScr','screen',0,'security','G-SCREENING','signoff --gate screening',{rowOff:1,tag:'operator',sources:[C(1316,1347),B(137,140),K(98,107)]}),
 n('prioJson','screen',2,'database','review/prioritization.json','ranked · past the budget',{rowOff:2,sources:[C(1221,1221),K(128,139)]}),
 n('so1','screen',0,'database','review/signoffs.json','sha256 of screening.jsonl',{rowOff:2,sources:[C(1241,1262)]}),

 // 6 · Appraisal and extraction
 n('appCmd','appraisal',0,'frontend','/systematic-review appraise','agent extracts · operator checks',{sources:[K(109,116),B(142,154)]}),
 n('appraise','appraisal',1,'messagebus','review_cli.py appraise','protocol checklist QA1…',{tag:'after G-PROTOCOL',sources:[C(839,860)]}),
 n('appraisal','appraisal',2,'database','review/appraisal.jsonl','quality answers per study',{tag:'item 11',sources:[C(855,855),B(211,211)]}),
 n('statusCli','appraisal',3,'messagebus','review_cli.py status','summary of the records',{sources:[C(1369,1387)]}),
 n('extract','appraisal',1,'messagebus','review_cli.py extract','each value + quote or page',{rowOff:1,sources:[C(861,895)]}),
 n('extraction','appraisal',2,'database','review/extraction.jsonl','checked against the fields',{rowOff:1,tag:'items 9-10',sources:[C(891,891),B(211,211)]}),

 // 7 · Synthesis
 n('synCmd','synth',2,'frontend','/systematic-review','synthesize · themes · tables',{tag:'with the operator',sources:[K(118,157),B(155,174)]}),
 n('prisma','synth',1,'messagebus','review_cli.py prisma','counts the PRISMA 2020 flow',{sources:[C(932,940)]}),
 n('prismaJson','synth',0,'database','review/prisma.json','flow counts',{tag:'items 16-17',sources:[C(935,938)]}),
 n('biblio','synth',3,'messagebus','review_cli.py biblio','per year · venue · keywords',{sources:[C(1023,1043)]}),
 n('biblioJson','synth',4,'database','review/biblio.json','bibliometrics',{sources:[C(1042,1043)]}),
 n('flow','synth',2,'messagebus','review_cli.py flow','recounts · draws the figure',{rowOff:1,sources:[C(1011,1022),C(1477,1479)]}),
 n('svg','synth',1,'database','prisma-flow.svg','paper/Figures/prisma-flow.svg',{rowOff:1,sources:[C(1016,1016)]}),
 n('gSyn','synth',0,'security','G-SYNTHESIS','signoff --gate synthesis',{rowOff:1,tag:'operator',sources:[C(1316,1347),B(170,172),K(143,149)]}),
 agent('diag','synth',3,'diagram-author',{rowOff:1,tag:'protocol-flow · no counts',sources:[K(124,129)]}),
 n('render','synth',4,'messagebus','paper_cli.py render','--figure-id protocol-flow',{rowOff:1,tag:'then /figure-review',sources:[K(124,129),T(66,69)]}),
 n('so2','synth',0,'database','review/signoffs.json','hash of counts + flow',{rowOff:2,sources:[C(1241,1262),C(1335,1345)]}),

 // 8 · Scaffolding, declarations and writing
 n('pw','write',0,'frontend','/paper-writing','skeleton · declare · one block',{tag:'.pi/prompts',sources:[P('paper-writing'),B(175,183),T(76,83)]}),
 agent('redactor','write',1,'redactor'),
 agent('contract','write',2,'contract-auditor'),
 n('tex','write',3,'database','paper/main.tex','counts from review/prisma.json',{sources:[T(81,83),B(216,216)]}),
 n('sections','write',0,'database','sections/*.md','9 review section contracts',{rowOff:1,tag:'from sections-review/',sources:[{path:'src/papersmith/core/manifest.py',line:390,end_line:394},T(76,80)]}),

 // 9 · Figures and paper
 agent('figVis','paper',0,'figure-visual-reviewer',{tag:'by eye · after the audit'}),
 agent('figAud','paper',1,'figure-auditor'),
 n('figRev','paper',2,'frontend','/figure-review','raster probe · no changes',{tag:'.pi/prompts',sources:[P('figure-review'),B(184,191)]}),
 n('pdf','paper',3,'database','paper/main.pdf','compiled from main.tex',{sources:[B(217,217),T(84,85)]}),
 n('pdfTab','paper',4,'external','PDF preview tab','final judge panel per round',{tag:'command center',sources:[{path:'skills/_core/command_center/static/paper-review-panel.js',line:1,end_line:6}]}),
 n('reviewJson','paper',1,'database','paper_review.json','.papersmith/ · one per round',{rowOff:1,sources:[{path:'skills/_core/command_center/static/paper-review-panel.js',line:1,end_line:6}]}),
 n('reviewCli','paper',2,'messagebus','paper_cli.py review','--input <round.json>',{rowOff:1,tag:'rubric systematic-review',sources:[{path:'skills/paper-writing/scripts/paper_cli.py',line:3694,end_line:3700},{path:'skills/paper-writing/scripts/paper_review.py',line:66,end_line:67}]}),
 agent('judge','paper',3,'paper-reviewer',{rowOff:1,tag:'final judge · AMSTAR 2',sources:[{path:'.pi/agents/paper-reviewer.md',line:257,end_line:276}]}),

 // 10 · Reporting check and audit
 n('smithAudit','audit',0,'messagebus','smith audit .','--verbose · never repairs',{sources:[{path:'skills/_core/command_center/phase_actions.py',line:276,end_line:281},T(89,89)]}),
 n('auditJson','audit',1,'database','.papersmith/audit.json','audit verdict',{sources:[{path:'skills/_core/command_center/phase_actions.py',line:364}]}),
 n('checklist','audit',3,'messagebus','review_cli.py checklist','27 PRISMA 2020 items · owed',{tag:'supplementary file',sources:[C(1348,1368),C(1503,1504),T(86,88)]}),
 n('reviewTab','audit',4,'external','Review tab','27-item checklist on demand',{tag:'GET /api/review/checklist',sources:[{path:'skills/_core/command_center/review_view.py',line:324,end_line:335},{path:'skills/_core/command_center/static/review-panel.js',line:1,end_line:12}]}),
 n('skillAudit','audit',0,'frontend','/skill-audit','subject: any skill',{rowOff:1,tag:'.pi/prompts',sources:[P('skill-audit'),{path:'skills/_core/command_center/phase_actions.py',line:282,end_line:284}]}),
 agent('auditRep','audit',1,'audit-report',{rowOff:1}),
];

const e=(from,to,label,extra={})=>({id:`${from}-${to}`,from,to,...(label?{label}:{}),...extra});
const main={variant:'emphasis',role:'main'};
const gate={variant:'security',role:'main'};
const edges=[
 // The main path: one step to the next.
 e('init','scopeCmd','review workspace',main),
 e('scopeCmd','protCmd','the gap to close',main),
 e('lock','search','approved protocol',gate),
 e('records','screen','unique records',main),
 e('so1','appCmd','screening signed off',gate),
 e('extraction','synCmd','data items',main),
 e('so2','pw','synthesis accepted',gate),
 e('tex','pdf','compiled',main),

 // 1 · Harness
 e('init','config'), e('config','ui',null,{variant:'dashed'}), e('status','upgrade',null,{variant:'dashed'}),
 // 2 · Scoping
 e('scopeCmd','scopeCli'), e('scopeCli','scopeJson'), e('plaus','pool'),
 // 3 · Protocol
 e('protCmd','initCli'), e('initCli','protJson'), e('protJson','check'), e('check','gProt'),
 e('gProt','lock',null,{variant:'security'}), e('amend','lock'), e('protJson','reg','registered',{variant:'dashed'}),
 // 4 · Identification
 e('search','searches'), e('import','searches'), e('searches','records','search_id',{variant:'dashed'}), e('dedupe','records'),
 // 5 · Screening
 e('scrCmd','screen'), e('screen','screening'), e('screening','qck',null,{variant:'dashed'}), e('qck','settle'),
 e('ingest','screen','full texts'), e('prio','screening','--apply: exclusions'), e('prio','prioJson'),
 e('settle','gScr','no conflict left'), e('gScr','so1',null,{variant:'security'}),
 // 6 · Appraisal and extraction
 e('appCmd','appraise'), e('appraise','appraisal'), e('appraisal','statusCli',null,{variant:'dashed'}),
 e('appCmd','extract'), e('extract','extraction'),
 // 7 · Synthesis
 e('synCmd','prisma'), e('prisma','prismaJson'), e('synCmd','biblio'), e('biblio','biblioJson'),
 e('synCmd','flow'), e('flow','svg'), e('prismaJson','gSyn','counts'), e('svg','gSyn'),
 e('gSyn','so2',null,{variant:'security'}), e('biblioJson','render',null,{variant:'dashed'}), e('diag','render'),
 // 8 · Writing
 e('pw','redactor'), e('redactor','contract'), e('contract','tex',null,{variant:'dashed'}), e('pw','sections','review contracts'),
 // 9 · Figures and paper
 e('figAud','figVis',null,{variant:'dashed'}), e('figAud','figRev'), e('pdf','pdfTab',null,{variant:'dashed'}),
 e('pdf','judge','one round'), e('judge','reviewCli'), e('reviewCli','reviewJson'),
 // 10 · Reporting check and audit
 e('checklist','judge','PRISMA gaps',{variant:'dashed'}), e('checklist','reviewTab'),
 e('smithAudit','auditJson'), e('skillAudit','auditRep'),
];

// Lanes are the ten review steps, in the board's order (review_board.REVIEW_STAGES).
const lanes=[
 ['harness','1 · Harness (smith init --kind review)'],
 ['scope','2 · Scoping (existing reviews)'],
 ['protocol','3 · Protocol (G-PROTOCOL, operator)'],
 ['ident','4 · Identification (searches and imports)'],
 ['screen','5 · Screening (two reviewers, G-SCREENING)'],
 ['appraisal','6 · Appraisal and extraction'],
 ['synth','7 · Synthesis (PRISMA flow, G-SYNTHESIS)'],
 ['write','8 · Scaffolding, declarations and writing'],
 ['paper','9 · Figures and paper (final judge: AMSTAR 2)'],
 ['audit','10 · Reporting check and audit (transversal)'],
].map(([id,label])=>({id,label}));

const laneIdx={};let nextRow=0;
for(const l of lanes){laneIdx[l.id]=nextRow;nextRow+=1+Math.max(0,...nodes.filter(x=>x.lane===l.id).map(x=>x.rowOff||0));}
const components=nodes.map(({lane,col,rowOff,...r})=>({...r,row:laneIdx[lane]+(rowOff||0),col,size:[182,58]}));
const connections=edges.map(({role,...r})=>r);
const boundaries=lanes.map(l=>({kind:'region',label:l.label,wraps:nodes.filter(x=>x.lane===l.id).map(x=>x.id)}));
const doc={schema_version:1,diagram_type:'architecture',meta:{
  title:'Papersmith AI review line — PRISMA 2020 systematic review',
  quality_profile:'showcase',
  output:'docs/diagrams/papersmith-review-flow.html',
  repository:{url:'https://github.com/LIAUNAL/papersmith-ai',provider:'github',link_mode:'web',revision:'3984b69c1dcb2eb632059ccb8ccd07dc6d181b12'},
  legend:{mode:'auto',entries:{frontend:{label:'Command /skill'},backend:{label:'Agent'},messagebus:{label:'CLI'},security:{label:'Gate (human)'},database:{label:'Record on disk'},external:{label:'Harness or dashboard'}}}
 },
 layout:{mode:'grid',origin:[30,48],cols:5,cellW:182,cellH:58,gapX:24,gapY:62},
 components, boundaries, connections,
 cards:[
  {dot:'cyan',title:'The review line',items:[
   'smith init --kind review writes paper_kind: review in .papersmith/config.json; smith kind set review switches a workspace',
   'No proposal, no experiments, no remote runs: every step writes its records under review/',
   'The board reads the line per request and shows these ten steps instead of the eleven experimental phases',
   'Hidden for a review: Concept Map & Model, Experiments, Novelty & Findings, the SOTA constellation']},
  {dot:'amber',title:'Human gates',items:[
   'G-PROTOCOL: protocol approve --by <operator>; search, import, screen, appraise and signoff refuse before it',
   'The operator is always one of the two screening reviewers and settles every conflict with screen --final',
   'G-SCREENING: refused while a record is undecided or in conflict; current while screening.jsonl is unchanged',
   'G-SYNTHESIS: refused until prisma.json and prisma-flow.svg exist; current while they are unchanged',
   'An agent never approves, signs or decides a gate on the operator’s behalf']},
  {dot:'violet',title:'CLI verbs',items:[
   'python skills/systematic-review/scripts/review_cli.py --root . <verb>: one JSON object, a refusal exits 2',
   'init · protocol check|approve|amend · scope · search · import · dedupe',
   'queue · screen · conflicts · kappa · prioritize',
   'appraise · extract · prisma · flow · biblio · signoff · checklist · status']},
  {dot:'emerald',title:'Dashboard',items:[
   'Pipeline: each step locked until the one before passes; identification waits for G-PROTOCOL, appraisal for G-SCREENING, writing for G-SYNTHESIS',
   'Review tab: protocol and registration, search log, screening, PRISMA flow, extraction, risk of bias, sign-offs',
   'Final judge: paper-reviewer with the systematic-review rubric (AMSTAR 2 items 1-16, PRISMA 2020 gaps)',
   'Flujo Archify: this drawing, unless the workspace has its own docs/papersmith-flow.html']},
 ]};
const out = path.resolve(process.argv[2] || fileURLToPath(new URL('./candidate.json', import.meta.url)));
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify(doc, null, 1));
console.log(`candidate: ${out}`);
