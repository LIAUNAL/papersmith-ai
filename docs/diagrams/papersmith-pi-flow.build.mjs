/**
 * The source of `papersmith-pi-flow.html` and its PNG beside this file.
 *
 * It is here, and not only in the throwaway `.archify/` folder it was authored
 * in, because a diagram whose source lives outside the repository cannot be
 * regenerated from a clone -- and a diagram nobody can regenerate stops being
 * evidence and becomes an assertion.
 *
 *   node docs/diagrams/papersmith-pi-flow.build.mjs /tmp/flow/candidate.json
 *   node <archify-3.0.1>/bin/archify.mjs finalize architecture \
 *     /tmp/flow/candidate.json /tmp/flow/papersmith-pi-flow.html \
 *     --repo-root . --quality showcase --json
 *
 * `agentMeta` reads the shipped agent definitions, and every node's `sources`
 * names the repository path and line range it was transcribed from, so the
 * drawing is checkable against the code rather than trusted.
 *
 * Every label is English. The rendered page used to be Spanish through a
 * vendored translation table (`locales/es.json`, Archify 3.0.1, MIT); the
 * artifact is English now, so the table is gone and the labels are literal.
 *
 * The plausibility gate is drawn as a `security` edge from `screener` to `pool`
 * and not as a node of its own, and that is a measured constraint rather than a
 * preference. The readability cap is 1240px wide: rendered edge labels are 8px
 * and the desktop budget is 930px, so the projected text is 8 * 930 / width and
 * it has to reach 6px. Six columns need the gate's own column, and at the 24px
 * minimum connection length and the 186px node width the longest command label
 * needs, six columns floor at 30 + 6*186 + 5*24 + 70 = 1312. Five columns fit in
 * 1106. The gate keeps its citation -- moved onto the `pool` node, which is what
 * the acceptance section governs -- and the legend still reads the edge as a
 * human gate.
 *
 * The component count is capped too, at 80, and that cap is the renderer's: the
 * grid search that routes an edge around unrelated nodes gives up on a scene
 * with more than 80 obstacles (`maximumObstacleCount` in Archify's routing),
 * and an authored `via` cannot stand in for it, because only two automatic
 * routes may cross each other (with a halo); an authored crossing is a showcase
 * error. The flow stood at 78 components with exactly one edge that only the
 * grid can route -- the dashed `replication` -> `expBuild`, which has to cross
 * the five nodes of lane 5 -- so a lane of any size broke it. That arrow is
 * gone: the relation is carried by the `expBuild` tag and by the "Flow rules"
 * card. Lane 11a (journal choice and venue adaptation, after the PDF) takes
 * eleven nodes, merging consecutive steps where one node can honestly carry
 * both, in three rows laid out as a serpentine so every turn is a short
 * vertical edge. Any later edge that only the grid can route will fail at this
 * size, whatever lane it is in.
 */
import fs from 'fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = fileURLToPath(new URL('../../', import.meta.url)).replace(/\/$/, '');

const S=(path,line,end_line)=>{const r={path};if(line)r.line=line;if(end_line)r.end_line=end_line;return [r];};

const agentMeta=n=>{const fm=fs.readFileSync(`${REPO}/.pi/agents/${n}.md`,'utf8').split('---')[1];
 const tools=[...fm.split('tools:')[1].matchAll(/^\s+-\s+(\S+)/gm)].map(m=>m[1]);
 const caps=[];if(tools.some(t=>t==='write'||t==='edit'))caps.push('writes');if(tools.includes('bash'))caps.push('bash');if(tools.includes('mcp'))caps.push('MCP');
 const st=(fm.match(/^stretch:\s*(\S+)/m)||[])[1];
 const endLine=fm.split('\n').length;
 return {sub:caps.length?'reads · '+caps.join(' · '):'read-only',tag:st?`stretch: ${st}`:undefined,end:endLine};};
const A=n=>S(`.pi/agents/${n}.md`,1,agentMeta(n).end);
const K=(n,l,e)=>[{path:`.pi/prompts/${n}.md`,line:1,end_line:7,label:'template /'+n},{path:`skills/${n}/SKILL.md`,line:l,end_line:e}];
const W=200;
const n=(id,lane,col,type,label,sublabel,extra={})=>({id,lane,col,type,label,sublabel,width:Math.max(120,Math.ceil(label.length*6.9+16),Math.ceil(sublabel.length*5.4+20)),...extra});
const nodes=[
 n('piMd','pi',0,'external','.pi/APPEND_SYSTEM.md','Pi system prompt',{sources:S('.pi/APPEND_SYSTEM.md',1,28)}),
 n('canon','pi',1,'database','skills/','canonical · .pi/skills link',{tag:'setup:harnesses',sources:[{path:'.pi/APPEND_SYSTEM.md',line:16,end_line:20},{path:'package.json',line:16}]}),
 n('sync','pi',2,'messagebus','sync-repo-harness.py','writes the .pi/ projection',{tag:'--check',sources:S('scripts/sync-repo-harness.py',44,52)}),
 n('piDir','pi',3,'database','.pi/','prompts · agents · extensions',{sources:S('.pi/APPEND_SYSTEM.md',22,34)}),
 n('subagents','pi',4,'external','pi-subagents','package that reads .pi/agents',{sources:S('.pi/APPEND_SYSTEM.md',32,35)}),
 n('kwHelp','help',1,'external','Thematic help','3–5 keywords · optional',{tag:'phase-2 box',sources:[{path:'skills/_core/command_center/phase_actions.py',line:86,end_line:101}]}),
 n('banco','help',2,'messagebus','banco-lia MCP','search_bank · taxonomy',{tag:'uvx · stdio',sources:S('.mcp.json',4,12)}),
 n('draftGate','help',3,'security','Operator approves','edit the draft → launch',{sources:[{path:'skills/_core/command_center/phase_actions.py',line:86,end_line:101},{path:'skills/plausibility/SKILL.md',line:15,end_line:27}]}),
 n('plaus','plaus',0,'frontend','/plausibility','idea in ≥ 2 sentences',{tag:'.pi/prompts',sources:K('plausibility',33,35)}),
 n('scout','plaus',1,'backend','sota-scout',agentMeta('sota-scout').sub,{...(agentMeta('sota-scout').tag?{tag:agentMeta('sota-scout').tag}:{}),sources:A('sota-scout')}),
 n('grapher','plaus',2,'backend','sota-grapher',agentMeta('sota-grapher').sub,{...(agentMeta('sota-grapher').tag?{tag:agentMeta('sota-grapher').tag}:{}),sources:A('sota-grapher')}),
 n('screener','plaus',3,'backend','novelty-screener',agentMeta('novelty-screener').sub,{...(agentMeta('novelty-screener').tag?{tag:agentMeta('novelty-screener').tag}:{}),sources:A('novelty-screener')}),
 n('pool','plaus',4,'database','sota-pool/','candidates · atlas.html',{sources:[{path:'README.md',line:76},{path:'skills/plausibility/SKILL.md',line:153,end_line:176}]}),

 n('ingest','ingest',0,'frontend','/paper-ingestion','PDF in guidance/',{tag:'.pi/prompts',sources:K('paper-ingestion',27,29)}),
 n('ingestAgent','ingest',1,'backend','paper-ingestion',agentMeta('paper-ingestion').sub,{...(agentMeta('paper-ingestion').tag?{tag:agentMeta('paper-ingestion').tag}:{}),sources:A('paper-ingestion')}),
 n('guidance','ingest',4,'database','guidance/','Markdown + figures',{sources:S('README.md',77)}),

 n('delib','delib',0,'frontend','/proposal-deliberation','bound → published',{tag:'.pi/prompts',sources:K('proposal-deliberation',32,35)}),
 n('delibCli','delib',1,'messagebus','cli.mjs --serve','replace · insert · delete',{tag:'CREATE_SUCCESSOR',sources:S('skills/proposal-deliberation/SKILL.md',255,291)}),
 n('delibGate','delib',2,'security','Human acceptance','preview → accept',{sources:S('skills/proposal-deliberation/SKILL.md',33,64)}),
 n('delibPub','delib',3,'backend','deliberation-publish',agentMeta('deliberation-publish').sub,{...(agentMeta('deliberation-publish').tag?{tag:agentMeta('deliberation-publish').tag}:{}),sources:A('deliberation-publish')}),
 n('proposals','delib',4,'database','proposals/','rNN.md · rNN.graph.html',{sources:[{path:'README.md',line:78},{path:'skills/proposal-deliberation/SKILL.md',line:74,end_line:133}]}),

 n('tutor','dash',0,'frontend','/math-tutor','socratic · hand-written pages',{tag:'.pi/prompts',sources:K('math-tutor',54,74)}),
 n('tutorAgent','dash',1,'backend','math-tutor',agentMeta('math-tutor').sub,{...(agentMeta('math-tutor').tag?{tag:agentMeta('math-tutor').tag}:{}),sources:A('math-tutor')}),
 n('ui','dash',2,'external','smith ui','phase drawer → /<skill>',{tag:'command center',sources:S('skills/_core/command_center/phase_actions.py',1,15)}),
 n('mathApi','dash',3,'messagebus','/api/model/math','concept map · KaTeX cards',{sources:S('skills/_core/command_center/math_view.py',1,16)}),
 n('tutorStore','dash',4,'database','.papersmith/math-tutor/','thread + uploaded pages',{sources:S('skills/_core/command_center/tutor.py',1,12)}),

 n('expDelib','expdelib',0,'frontend','/experimental-deliberation','requires data-paper/',{tag:'.pi/prompts',sources:K('experimental-deliberation',34,38)}),
 n('expVal','expdelib',1,'backend','experimental-validation',agentMeta('experimental-validation').sub,{...(agentMeta('experimental-validation').tag?{tag:agentMeta('experimental-validation').tag}:{}),sources:A('experimental-validation')}),
 n('expGate','expdelib',2,'security','Human acceptance','deliberated = operator',{sources:S('skills/experimental-deliberation/SKILL.md',35,65)}),
 n('expPub','expdelib',3,'backend','experimental-publish',agentMeta('experimental-publish').sub,{...(agentMeta('experimental-publish').tag?{tag:agentMeta('experimental-publish').tag}:{}),sources:A('experimental-publish')}),
 n('experiments','expdelib',4,'database','experiments/','experimental protocol',{sources:S('README.md',83)}),

 n('impl','impl',0,'frontend','/proposal-implementation','standing → full-scale',{tag:'.pi/prompts',sources:K('proposal-implementation',96,101)}),
 n('implBuild','impl',1,'backend','implementation-build',agentMeta('implementation-build').sub,{...(agentMeta('implementation-build').tag?{tag:agentMeta('implementation-build').tag}:{}),sources:A('implementation-build')}),
 n('implWalk','impl',2,'backend','implementation-walk',agentMeta('implementation-walk').sub,{...(agentMeta('implementation-walk').tag?{tag:agentMeta('implementation-walk').tag}:{}),sources:A('implementation-walk')}),
 n('implGate','impl',3,'security','Authorizes a launch','operator only',{sources:S('skills/proposal-implementation/SKILL.md',144,144)}),
 n('repo','impl',4,'database','implementations/<repo>','its own git + .venv',{sources:S('README.md',81)}),
 n('replicator','impl',1,'backend','paper-replicator',agentMeta('paper-replicator').sub,{rowOff:1,...(agentMeta('paper-replicator').tag?{tag:agentMeta('paper-replicator').tag}:{}),sources:[...A('paper-replicator'),{path:'skills/proposal-implementation/SKILL.md',line:166,end_line:178}]}),
 n('pubCode','impl',2,'messagebus','Published code?','adopt + audit, else rebuild',{rowOff:1,sources:S('skills/proposal-implementation/SKILL.md',166,176)}),
 n('replication','impl',3,'database','REPLICATION.md','equation → line provenance',{rowOff:1,sources:S('skills/proposal-implementation/SKILL.md',145,145)}),

 n('discPoc','impl',4,'database','discussion.json','verdicts · tests · novelty',{rowOff:1,tag:'gates 5.8',sources:[{path:'skills/_core/results/discussion.py',line:1,end_line:14},{path:'skills/_core/results/discussion_cli.py',line:1,end_line:16},{path:'skills/_core/command_center/server.py',line:1354}]}),

 n('dataCmd','data',0,'frontend','/datasets','toy → published',{tag:'.pi/prompts',sources:K('datasets',18,32)}),
 n('dataScout','data',1,'backend','dataset-scout',agentMeta('dataset-scout').sub,{tag:'sourced → licensed',sources:A('dataset-scout')}),
 n('dataCurator','data',2,'backend','dataset-curator',agentMeta('dataset-curator').sub,{tag:'toy → published',sources:A('dataset-curator')}),
 n('dataGate','data',3,'security','Upload consent','private · --consent <slug>',{sources:S('skills/datasets/SKILL.md',34,45)}),
 n('dataStore','data',4,'database','datasets/','registry · splits.json',{sources:S('skills/datasets/SKILL.md',118,129)}),

 n('expImpl','expimpl',0,'frontend','/experimental-implementation','binding → full-scale',{tag:'.pi/prompts',sources:K('experimental-implementation',116,120)}),
 n('expBuild','expimpl',1,'backend','experiments-build',agentMeta('experiments-build').sub,{tag:'baselines: REPLICATION.md',sources:A('experiments-build')}),
 n('expRev','expimpl',2,'backend','experiments-reviewer',agentMeta('experiments-reviewer').sub,{...(agentMeta('experiments-reviewer').tag?{tag:agentMeta('experiments-reviewer').tag}:{}),sources:A('experiments-reviewer')}),
 n('expWalk','expimpl',3,'backend','experiments-walk',agentMeta('experiments-walk').sub,{...(agentMeta('experiments-walk').tag?{tag:agentMeta('experiments-walk').tag}:{}),sources:A('experiments-walk')}),
 n('expImplGate','expimpl',4,'security','Authorizes a launch','whole campaign',{sources:S('skills/experimental-implementation/SKILL.md',116,120)}),

 n('discFull','expimpl',1,'database','discussion.json','verdicts · tests · novelty',{rowOff:1,tag:'gates 5.11',sources:[{path:'skills/_core/results/discussion_cli.py',line:1,end_line:16},{path:'skills/experimental-implementation/SKILL.md',line:511,end_line:516},{path:'skills/_core/command_center/server.py',line:1357}]}),
 n('reviewRep','expimpl',2,'database','reviewer_report.json','blockers resolved',{rowOff:1,tag:'gates 5.12',sources:[{path:'.pi/agents/experiments-reviewer.md',line:98,end_line:100},{path:'skills/_core/command_center/server.py',line:1358}]}),

 n('kaggle','creds',0,'frontend','/kaggle-accounts','taken-in → decided',{tag:'.pi/prompts',sources:K('kaggle-accounts',28,30)}),
 n('accCli','creds',1,'security','accounts_cli.py','validate --interactive',{tag:'TTY only',sources:S('skills/kaggle-accounts/SKILL.md',224,250)}),
 n('store','creds',2,'database','store/','validated credentials',{sources:S('README.md',88)}),

 n('guard','remote',4,'security','refuse-offpath-push.js','extension: watches bash',{tag:'tool_call',sources:[{path:'.pi/extensions/refuse-offpath-push.js',line:1,end_line:30},{path:'.pi/APPEND_SYSTEM.md',line:37,end_line:43}]}),
 n('remote','remote',0,'frontend','/remote-execution','reachable → returned',{tag:'.pi/prompts',sources:K('remote-execution',40,44)}),
 n('readiness','remote',1,'security','readiness + gate','single-use token',{sources:S('skills/remote-execution/SKILL.md',42)}),
 n('remoteCli','remote',2,'messagebus','remote_cli.py','submit · poll · fetch',{tag:'12 subcommands',sources:S('skills/remote-execution/SKILL.md',1577,1595)}),
 n('inbox','remote',3,'database','kaggle-inbox/','ledger + results',{sources:S('README.md',89)}),

 n('novPanel','nov',1,'external','Novelty & Findings','Novedad & Hallazgos tab',{tag:'command center',sources:[{path:'skills/_core/command_center/static/novelty-panel.js',line:1,end_line:9},{path:'skills/_core/command_center/server.py',line:3256,end_line:3259}]}),
 n('novGate','nov',2,'security','G-NOVELTY','approve · iterate',{tag:'operator',sources:[{path:'skills/_core/results/novelty_gate.py',line:1,end_line:15},{path:'skills/_core/command_center/server.py',line:1696,end_line:1730}]}),
 n('novStore','nov',3,'database','novelty_gate.json','.papersmith/ · history',{sources:S('skills/_core/results/novelty_gate.py',59,60)}),
 n('novCli','nov',4,'messagebus','smith novelty','status · approve · iterate',{tag:'novelty_cli.py',sources:[{path:'src/papersmith/core/novelty.py',line:1,end_line:6},{path:'skills/_core/results/novelty_cli.py',line:1,end_line:12}]}),

 n('pw','write',0,'frontend','/paper-writing','sections/*.md → paper/',{tag:'.pi/prompts',sources:K('paper-writing',14,16)}),
 n('insumos','write',1,'backend','insumos-observer',agentMeta('insumos-observer').sub,{...(agentMeta('insumos-observer').tag?{tag:agentMeta('insumos-observer').tag}:{}),sources:A('insumos-observer')}),
 n('redactor','write',2,'backend','redactor',agentMeta('redactor').sub,{...(agentMeta('redactor').tag?{tag:agentMeta('redactor').tag}:{}),sources:A('redactor')}),
 n('contract','write',3,'backend','contract-auditor',agentMeta('contract-auditor').sub,{...(agentMeta('contract-auditor').tag?{tag:agentMeta('contract-auditor').tag}:{}),sources:A('contract-auditor')}),
 n('style','write',4,'backend','style-sampler',agentMeta('style-sampler').sub,{...(agentMeta('style-sampler').tag?{tag:agentMeta('style-sampler').tag}:{}),sources:A('style-sampler')}),
 n('grounding','figs',4,'backend','section-grounding-auditor',agentMeta('section-grounding-auditor').sub,{...(agentMeta('section-grounding-auditor').tag?{tag:agentMeta('section-grounding-auditor').tag}:{}),sources:A('section-grounding-auditor')}),

 n('paperCli','figs',0,'messagebus','paper_cli.py','write judges what comes back',{tag:'29 verbs',sources:S('skills/paper-writing/SKILL.md',14,16)}),
 n('diagram','figs',1,'backend','diagram-author',agentMeta('diagram-author').sub,{...(agentMeta('diagram-author').tag?{tag:agentMeta('diagram-author').tag}:{}),sources:A('diagram-author')}),
 n('figAud','figs',2,'backend','figure-auditor',agentMeta('figure-auditor').sub,{...(agentMeta('figure-auditor').tag?{tag:agentMeta('figure-auditor').tag}:{}),sources:A('figure-auditor')}),
 n('figRev','figs',3,'frontend','/figure-review','probe · raster, no changes',{tag:'.pi/prompts',sources:K('figure-review',1,12)}),
 n('paper','out',4,'database','paper/','main.tex · refs.bib',{sources:S('README.md',90)}),

 n('jfCmd','jv',4,'frontend','/journal-finder','Q1-Q2 · --oa-only · --max-apc',{tag:'.pi/prompts',sources:[{path:'.pi/prompts/journal-finder.md',line:1,end_line:7,label:'template /journal-finder'},{path:'skills/journal-finder/SKILL.md',line:15,end_line:23}]}),
 n('jfCli','jv',3,'messagebus','journal_cli.py search','OpenAlex works + sources',{tag:'stdlib only',sources:S('skills/journal-finder/scripts/journal_cli.py',983,1125)}),
 n('jfQr','jv',2,'messagebus','Quartile + review time','SJR / proxy · Crossref→PubMed',{tag:'sjr-import',sources:[{path:'skills/journal-finder/scripts/journal_cli.py',line:821,end_line:895},{path:'skills/journal-finder/scripts/journal_cli.py',line:1449,end_line:1498},{path:'skills/journal-finder/SKILL.md',line:206,end_line:235}]}),
 n('jfJson','jv',1,'database','journal-candidates.json','paper/ · schema 1',{sources:[{path:'skills/journal-finder/scripts/journal_cli.py',line:1569},{path:'skills/journal-finder/scripts/journal_cli.py',line:1742}]}),
 n('jvPick','jv',1,'security','Operator picks a journal','PDF Preview → venue select',{rowOff:1,sources:[{path:'skills/_core/command_center/static/journals-panel.js',line:680,end_line:700},{path:'skills/_core/command_center/server.py',line:2875,end_line:2902},{path:'skills/paper-writing/scripts/paper_venue.py',line:193,end_line:269}]}),
 n('jvAgent','jv',2,'backend','venue-adapter',agentMeta('venue-adapter').sub,{rowOff:1,tag:'requirements · quote + url',sources:[...A('venue-adapter'),{path:'skills/paper-writing/scripts/paper_venue.py',line:308,end_line:478}]}),
 n('jvDiff','jv',3,'messagebus','venue acquire · diff','template · audit.json',{rowOff:1,sources:[{path:'skills/paper-writing/scripts/paper_venue.py',line:563,end_line:642},{path:'skills/paper-writing/scripts/paper_venue.py',line:1355,end_line:1378}]}),
 n('jvApprove','jv',3,'security','Operator approves plan','sha256-bound · approval.json',{rowOff:2,sources:[{path:'skills/paper-writing/scripts/paper_venue.py',line:1384,end_line:1440},{path:'skills/paper-writing/SKILL.md',line:1826,end_line:1857},{path:'skills/_core/command_center/server.py',line:2915,end_line:2934}]}),
 n('jvWrite','jv',2,'messagebus','paper_cli.py write','text changes only here',{rowOff:2,tag:'redactor → audit',sources:S('skills/paper-writing/SKILL.md',1834,1840)}),
 n('jvBuild','jv',1,'messagebus','venue build','class · front matter · blocks',{rowOff:2,tag:'main.tex untouched',sources:S('skills/paper-writing/scripts/paper_venue.py',1653,1791)}),
 n('jvPdf','jv',0,'database','main.pdf','paper/venues/<slug>/',{rowOff:2,sources:[{path:'skills/_core/command_center/server.py',line:608,end_line:621},{path:'skills/_core/command_center/server.py',line:2957,end_line:2986}]}),

 n('audit','audit',0,'frontend','/skill-audit','subject: any skill',{tag:'.pi/prompts',sources:K('skill-audit',23,23)}),
 n('auditRep','audit',1,'backend','audit-report',agentMeta('audit-report').sub,{...(agentMeta('audit-report').tag?{tag:agentMeta('audit-report').tag}:{}),sources:A('audit-report')}),
 n('report','audit',2,'database','Audit report','never repairs',{sources:S('skills/skill-audit/SKILL.md',676,683)}),
];
const e=(from,to,label,extra={})=>({id:`${from}-${to}`,from,to,...(label?{label}:{}),...extra});
const main={variant:'emphasis',role:'main'};
const edges=[
 e('plaus','ingest','top-5 to ingest',main),
 e('ingest','delib','guidance/',main),
 e('delib','impl','revision rNN',main),
 e('impl','expDelib','proof of concept',main),
 e('expDelib','expImpl','protocol + repo',main),
 e('expImpl','kaggle','job ready',main),
 e('kaggle','remote','accounts proven',main),
 e('remote','pw','measured facts',main),

 e('piMd','plaus','/<skill>',main),
 e('canon','sync'), e('sync','piDir'), e('subagents','piDir',null,{variant:'dashed'}),
 e('kwHelp','banco'), e('banco','draftGate'), e('draftGate','plaus','/plausibility <draft>',{variant:'security'}),
 e('plaus','scout'), e('scout','grapher'), e('grapher','screener'), e('screener','pool',null,{variant:'security'}),
 e('ingest','ingestAgent'), e('ingestAgent','guidance'),
 e('delib','delibCli'), e('delibCli','delibGate'), e('delibGate','delibPub',null,{variant:'security'}), e('delibPub','proposals'),
 e('grapher','delibPub','atlas.json',{variant:'dashed'}),
 e('delib','tutor','concept + math',{variant:'dashed'}),
 e('tutor','tutorAgent'), e('ui','mathApi'), e('tutorAgent','tutorStore'),
 e('ui','tutorAgent','headless turn',{variant:'dashed'}),
 e('proposals','mathApi','$$ \\tag{N}',{variant:'dashed'}),
 e('expDelib','expVal'), e('expVal','expGate'), e('expGate','expPub',null,{variant:'security'}), e('expPub','experiments'),
 e('impl','implBuild'), e('implBuild','implWalk'), e('implWalk','implGate'), e('implGate','repo',null,{variant:'security'}),
 e('expImpl','expBuild'), e('expBuild','expRev'), e('expRev','expWalk'), e('expWalk','expImplGate'),
 e('impl','replicator','fidelity'), e('replicator','pubCode'), e('pubCode','replication'),
 e('repo','discPoc','discussion_cli.py'),
 e('expBuild','discFull','discussion_cli.py'), e('expRev','reviewRep'),
 e('dataCmd','dataScout'), e('dataScout','dataCurator'), e('dataCurator','dataGate'), e('dataGate','dataStore',null,{variant:'security'}),
 e('dataStore','implBuild','toy set',{variant:'dashed',fromSide:'bottom',toSide:'top'}),
 e('dataStore','expBuild','official set · mounted by notebooks',{variant:'dashed',fromSide:'right',toSide:'top'}),
 e('kaggle','accCli'), e('accCli','store'),
 e('remote','readiness'), e('readiness','remoteCli',null,{variant:'security'}), e('remoteCli','inbox'),
 e('store','remoteCli','credentials',{variant:'dashed'}),
 e('inbox','novPanel','results to assess',{variant:'dashed'}), e('novPanel','novGate'), e('novGate','novStore',null,{variant:'security'}), e('novCli','novStore',null,{variant:'dashed'}),
 e('novGate','pw','approved → writing',{variant:'security'}),
 e('pw','insumos'), e('insumos','redactor'), e('redactor','contract'), e('contract','style'), e('style','grounding'),
 e('pw','paperCli','delegates',{variant:'dashed'}),
 e('paperCli','diagram'), e('diagram','figAud'), e('figAud','figRev'),
 e('grounding','paper','sections',{variant:'dashed'}),
 e('paper','jfCmd','compiled PDF',main),
 e('jfCmd','jfCli'), e('jfCli','jfQr'), e('jfQr','jfJson'),
 e('jfJson','jvPick','candidates'), e('jvPick','jvAgent',null,{variant:'security'}), e('jvAgent','jvDiff'),
 e('jvDiff','jvApprove','agent drafts plan.md'), e('jvApprove','jvWrite',null,{variant:'security'}), e('jvWrite','jvBuild'), e('jvBuild','jvPdf'),
 e('audit','auditRep'), e('auditRep','report'),
];
const lanes=[
 ['pi','0 · Pi harness'], ['help','1a · Thematic help (optional, before /plausibility)'], ['plaus','1 · Plausibility'],['ingest','2 · Ingestion'],['delib','3 · Proposal deliberation'],['dash','3b · Concept map and math (dashboard)'],
 ['data','4a · Datasets (toy set → official preparation)'],['impl','4 · Implementation (proof of concept + replication)'],['expdelib','5 · Experimental deliberation'],['expimpl','6 · Experimental implementation'],
 ['creds','7 · Credentials'],['remote','8 · Remote execution'],['nov','8a · Novelty and findings (dashboard, G-NOVELTY)'],['write','9 · Writing'],['figs','10 · Figures and grounding'],['out','11 · Paper'],['jv','11a · Journal choice and venue adaptation (after the PDF)'],
 ['audit','Transversal · Audit']].map(([id,label])=>({id,label}));

// A lane takes one grid row per row offset its nodes use (implementation draws
// replication on a second row: five columns is the readability cap above).
const laneIdx={};let nextRow=0;
for(const l of lanes){laneIdx[l.id]=nextRow;nextRow+=1+Math.max(0,...nodes.filter(x=>x.lane===l.id).map(x=>x.rowOff||0));}
const components=nodes.map(({lane,col,width,rowOff,...r})=>({...r,row:laneIdx[lane]+(rowOff||0),col,size:[182,58]}));
const connections=edges.map(({role,...r})=>r);
const boundaries=lanes.map(l=>({kind:'region',label:l.label,wraps:nodes.filter(x=>x.lane===l.id).map(x=>x.id)}));
const doc={schema_version:1,diagram_type:'architecture',meta:{
  title:'Papersmith AI in Pi — commands, skills and agents',
  quality_profile:'showcase',
  output:'docs/diagrams/papersmith-pi-flow.html',
  repository:{url:'https://github.com/LIAUNAL/papersmith-ai',provider:'github',link_mode:'web',revision:'e83356d757ff6bd9bf8faba15c3d0d3cc6ffb0fa'},
  legend:{mode:'auto',entries:{frontend:{label:'Pi command /skill'},backend:{label:'Pi subagent'},messagebus:{label:'CLI'},security:{label:'Gate (human)'},database:{label:'Artifact on disk'},external:{label:'Pi harness'}}}
 },
 layout:{mode:'grid',origin:[30,48],cols:5,cellW:182,cellH:58,gapX:24,gapY:62},
 components, boundaries, connections,
 cards:[
  {dot:'cyan',title:'How Pi sees it',items:['.pi/APPEND_SYSTEM.md is the system prompt: Pi appends it to the project one','/<skill> = .pi/prompts/<skill>.md: it loads the SKILL.md and passes $ARGUMENTS',`The ${fs.readdirSync(`${REPO}/.pi/agents`).filter(f=>f.endsWith('.md')).length} .pi/agents/ are projected from .claude/agents/; Pi core has no subagents, so they need pi-subagents`,'Each agent declares tools (read, find, grep, write, edit, bash, mcp) and its stretch','refuse-offpath-push.js intercepts bash tool_call; it is a warning that fails open, not a gate']},
  {dot:'emerald',title:'Harness commands',items:['npm run setup:harnesses — links .pi/skills -> ../skills','python scripts/sync-repo-harness.py — regenerates .pi/prompts, .pi/agents, .pi/extensions (--check detects drift)','smith init · status · ingest · deliberate · implement · run · remote · audit · ui','npm run test:all — the quality gate']},
  {dot:'violet',title:'Per-skill CLIs',items:['paper-ingestion: python scripts/setup_env.py install','deliberation: node skills/<skill>/cli.mjs --serve','the proposal graph: merge_proposal_sky.py → check_atlas.py → render_atlas.py','implementation: implementation_cli.py materialize · verify · fidelity · audit · step','kaggle-accounts: accounts_cli.py list · discover · validate · remove · materialize','remote-execution: remote_cli.py submit · status · poll · fetch · readiness …','paper-writing: paper_cli.py status · plan · write · verify … (29 verbs)','journal-finder: journal_cli.py search · sjr-import · status','venue adaptation: paper_cli.py venue select · requirements · acquire · diff · plan · approve · build','datasets: datasets_cli.py synth · search · license · qc · prepare · publish','figure-review: review_cli.py probe · raster · skill-audit: audit_cli.py']},
  {dot:'amber',title:'Flow rules',items:['The order is optional: each skill refuses with a code when its input is missing','Starting with /plausibility, before ingestion, is the recommendation','After a proposal revision, discuss its concept map and mathematics (dashboard Mapa Conceptual tab, /math-tutor) before implementing it','/datasets gives a seeded toy set first (dataset-scout: sourced → licensed; dataset-curator: toy → checked → prepared → published); publishing is private and only on the operator\'s consent','The proof of concept reads the toy set; the full experiments read the one official subject-wise preparation, mounted by remote notebooks','paper-replicator (implementation fidelity) searches for published code first: adopt it and audit its correspondence to the paper, else reimplement from the ingested paper; its baselines feed the experiments','experiments-reviewer reviews the instrumented code before any rehearsal or launch','No walk can launch a campaign: the operator authorizes it','contract-auditor, redactor and style-sampler have no code path: the orchestrator launches them and write judges','/figure-review and /skill-audit only report; they never repair','Once the paper compiles, /journal-finder ranks journals by quartile, access, APC and an estimated review time; nothing is submitted, and without an SJR file the quartile is a labelled OpenAlex proxy','The operator picks a journal in the PDF Preview tab; venue-adapter reads its guidelines and every requirement carries a quote and a url','The operator approves the adaptation plan by its sha256; text changes go only through write, and venue build never writes paper/main.tex','smith ui: each pipeline phase card sends its /<skill> with the rules as a guide, or opens the panel that owns the work']}
 ]};
const out = path.resolve(process.argv[2] || fileURLToPath(new URL('./candidate.json', import.meta.url)));
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify(doc, null, 1));
console.log(`candidate: ${out}`);
