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
 * The lanes are numbered by the eleven dashboard phases
 * (`phase_actions.STAGES`), and a lettered lane is a sub-lane of the phase whose
 * number it carries: 2a the optional thematic help; 4a the proposal's ordered
 * steps (problem and pillars, hypotheses, mathematics, SOTA citations with
 * `smith atlas coverage`), the judge-reviewer's contribution type and the math
 * tutor; 5a to 5g Phase 5 in the order the
 * harness entrypoints state it -- datasets, replication and proof of concept,
 * the proof-of-concept verification gate (G-EXP-POC), the full experiments,
 * credentials, the remote rehearsal and launch, and the findings with their
 * contribution type and G-NOVELTY; 10a the journal choice (international by SJR
 * quartile, or national from Publindex), the venue adaptation and the Spanish
 * translation for a journal that only receives Spanish.
 * `tests/test_flow_consistency.py` holds the numbering against the phases.
 *
 * Three lanes draw what happens around those phases. Lane 2 continues below
 * the pool: on the report's acceptance `/paper-type` hands the idea to the
 * paper-type-advisor, records the type the operator agrees in
 * `.papersmith/paper_type.json` (a `security` edge: the agreement is the
 * operator's), and `smith kind set` moves the workspace to another line. Its
 * second and third rows keep column 2 empty, because the dashed sota-grapher
 * -> deliberation-publish edge runs straight down that column. Lane 6 names
 * the eight lines (`smith init --kind <line>`, `manifest.LINES`); the six
 * empirical lines have flows of their own (`papersmith-line-flow.build.mjs`).
 * Lane 10's second row is the PDF tab around the final judge: the "Launch the
 * final judge" round button, Caztor (the LaTeX editor the tab's switch shows)
 * and the Change Control panel that hands the operator's marks to its chat.
 *
 * `sources` ranges are checked at `meta.repository.revision`, so the agent
 * definitions are read from that commit with `git show`, not from the working
 * tree: move REVISION and the ranges together.
 *
 * The component count matters for one reason: Archify's grid search, which
 * routes an edge around nodes it has no relationship with, gives up on a scene
 * with more than 80 obstacles (`maximumObstacleCount` in Archify's routing),
 * and an authored `via` cannot stand in for it, because only two automatic
 * routes may cross each other (with a halo); an authored crossing is a showcase
 * error. The drawing is past 80 components, so every edge must be routable
 * without the grid: between neighbours in a row, straight down a column, or
 * through the corridor between two rows. The dashed `replication` ->
 * `expBuild` arrow was dropped for that reason (its relation lives in the
 * `expBuild` tag and the "Flow rules" card), and a label sits only on an edge
 * that leaves its row, since a 24px gap between row neighbours cannot hold one.
 * Lane 10a takes three rows laid out as a serpentine so every turn is a short
 * vertical edge, and a fourth for the translation, entered straight down from
 * the venue PDF. The final judge panel (paper-reviewer, `paper_cli.py review`,
 * paper_review.json) shares lane 10's row with the PDF preview tab, and the
 * dashboard's "Update board" hangs off `smith ui` in lane 4a. Agents and skills
 * without a node of their own (hyperparameter-search, experiment-diagrams,
 * upgrade-project, ui-github) are named in the cards.
 */
import fs from 'fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const REPO = fileURLToPath(new URL('../../', import.meta.url)).replace(/\/$/, '');
// The commit the drawing describes: Archify's strict provenance gate checks every
// `sources` range at this revision, so the agent definitions are read from it too
// (a working tree with uncommitted edits cannot shift a range the gate checks).
const REVISION='33926cf563259bb67b30c6e79085a09df3172ebe';
const atRevision=p=>execFileSync('git',['-C',REPO,'show',`${REVISION}:${p}`],{encoding:'utf8'});
const AGENT_COUNT=execFileSync('git',['-C',REPO,'ls-tree','--name-only',REVISION,'.pi/agents/'],{encoding:'utf8'}).split('\n').filter(f=>f.endsWith('.md')).length;

const S=(path,line,end_line)=>{const r={path};if(line)r.line=line;if(end_line)r.end_line=end_line;return [r];};

const agentMeta=n=>{const fm=atRevision(`.pi/agents/${n}.md`).split('---')[1];
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
 n('canon','pi',1,'database','skills/','canonical · .pi/skills link',{tag:'setup:harnesses',sources:[{path:'.pi/APPEND_SYSTEM.md',line:16,end_line:20},{path:'package.json',line:21}]}),
 n('sync','pi',2,'messagebus','sync-repo-harness.py','writes the .pi/ projection',{tag:'--check',sources:S('scripts/sync-repo-harness.py',42,52)}),
 n('piDir','pi',3,'database','.pi/','prompts · agents · extensions',{sources:S('.pi/APPEND_SYSTEM.md',22,34)}),
 n('subagents','pi',4,'external','pi-subagents','package that reads .pi/agents',{sources:S('.pi/APPEND_SYSTEM.md',32,35)}),
 n('kwHelp','help',1,'external','Thematic help','3–5 keywords · optional',{tag:'phase-2 box',sources:[{path:'skills/_core/command_center/phase_actions.py',line:100,end_line:111}]}),
 n('banco','help',2,'messagebus','banco-lia MCP','search_bank · taxonomy',{tag:'uvx · stdio',sources:S('.mcp.json',4,12)}),
 n('draftGate','help',3,'security','Operator approves','edit the draft → launch',{sources:[{path:'skills/_core/command_center/phase_actions.py',line:100,end_line:111},{path:'skills/plausibility/SKILL.md',line:15,end_line:27}]}),
 n('plaus','plaus',0,'frontend','/plausibility','idea in ≥ 2 sentences',{tag:'.pi/prompts',sources:K('plausibility',33,35)}),
 n('scout','plaus',1,'backend','sota-scout',agentMeta('sota-scout').sub,{...(agentMeta('sota-scout').tag?{tag:agentMeta('sota-scout').tag}:{}),sources:A('sota-scout')}),
 n('grapher','plaus',2,'backend','sota-grapher',agentMeta('sota-grapher').sub,{...(agentMeta('sota-grapher').tag?{tag:agentMeta('sota-grapher').tag}:{}),sources:A('sota-grapher')}),
 n('screener','plaus',3,'backend','novelty-screener',agentMeta('novelty-screener').sub,{...(agentMeta('novelty-screener').tag?{tag:agentMeta('novelty-screener').tag}:{}),sources:A('novelty-screener')}),
 n('pool','plaus',4,'database','sota-pool/','candidates · atlas.html',{sources:[{path:'src/papersmith/core/init.py',line:94,end_line:96},{path:'skills/plausibility/SKILL.md',line:153,end_line:176}]}),
 n('ptCmd','plaus',4,'frontend','/paper-type','scores the idea · catalogue',{rowOff:1,tag:'.pi/prompts',sources:K('paper-type',6,64)}),
 n('ptAgent','plaus',3,'backend','paper-type-advisor',agentMeta('paper-type-advisor').sub,{rowOff:1,tag:'relates every type',sources:A('paper-type-advisor')}),
 n('ptJson','plaus',4,'database','paper_type.json','.papersmith/ · type + variant',{rowOff:2,sources:S('skills/paper-type/SKILL.md',65,72)}),
 n('kindSet','plaus',3,'messagebus','smith kind set','another line: contracts + flow',{rowOff:2,tag:'operator · --force',sources:[{path:'src/papersmith/core/kind.py',line:1,end_line:13},{path:'src/papersmith/core/kind.py',line:222,end_line:233},{path:'skills/paper-type/SKILL.md',line:73,end_line:82}]}),

 n('ingest','ingest',0,'frontend','/paper-ingestion','PDF in guidance/',{tag:'.pi/prompts',sources:K('paper-ingestion',60,60)}),
 n('ingestAgent','ingest',1,'backend','paper-ingestion',agentMeta('paper-ingestion').sub,{...(agentMeta('paper-ingestion').tag?{tag:agentMeta('paper-ingestion').tag}:{}),sources:A('paper-ingestion')}),
 n('guidance','ingest',4,'database','guidance/','Markdown + figures',{sources:S('src/papersmith/core/init.py',74,77)}),
 n('pixelrag','ingest',4,'frontend','/pixelrag','figure → evidence · keyless',{rowOff:1,tag:'facts · record · status',sources:K('pixelrag',33,43)}),

 n('delib','delib',0,'frontend','/proposal-deliberation','bound → published',{tag:'.pi/prompts',sources:K('proposal-deliberation',32,35)}),
 n('delibCli','delib',1,'messagebus','cli.mjs --serve','replace · insert · delete',{tag:'CREATE_SUCCESSOR',sources:S('skills/proposal-deliberation/SKILL.md',433,445)}),
 n('delibGate','delib',2,'security','Human acceptance','preview → accept',{sources:S('skills/proposal-deliberation/SKILL.md',33,64)}),
 n('delibPub','delib',3,'backend','deliberation-publish',agentMeta('deliberation-publish').sub,{...(agentMeta('deliberation-publish').tag?{tag:agentMeta('deliberation-publish').tag}:{}),sources:A('deliberation-publish')}),
 n('proposals','delib',4,'database','proposals/','rNN.md · rNN.graph.html',{sources:[{path:'src/papersmith/core/init.py',line:89,end_line:93},{path:'skills/proposal-deliberation/SKILL.md',line:95,end_line:102}]}),

 n('stepPP','steps',0,'external','Problem & pillars','step 1 · Generar y deliberar',{tag:'Mapa Conceptual',sources:[{path:'skills/_core/command_center/phase_steps.py',line:1,end_line:19},{path:'skills/_core/command_center/static/model-panel.js',line:319,end_line:422}]}),
 n('stepHyp','steps',1,'external','Hypotheses','step 2 · locked until step 1',{sources:S('skills/_core/command_center/phase_steps.py',100,131)}),
 n('stepMath','steps',2,'external','Mathematics','step 3 · $$ \\tag{N} in rNN.md',{sources:S('skills/_core/command_center/phase_steps.py',12,14)}),
 n('tutor','steps',3,'frontend','/math-tutor','socratic · hand-written pages',{tag:'.pi/prompts',sources:K('math-tutor',54,74)}),
 n('tutorAgent','steps',4,'backend','math-tutor',agentMeta('math-tutor').sub,{...(agentMeta('math-tutor').tag?{tag:agentMeta('math-tutor').tag}:{}),sources:A('math-tutor')}),
 n('modelSpec','steps',0,'database','model_spec.json','.papersmith/ · contribution_type',{rowOff:1,sources:[{path:'skills/proposal-deliberation/SKILL.md',line:221,end_line:241}]}),
 n('contribProp','steps',1,'backend','paper-reviewer','judge-reviewer · step 5',{rowOff:1,tag:'contribution type',sources:[{path:'skills/_core/results/contribution_type.py',line:1,end_line:16},...A('paper-reviewer')]}),
 n('stepCite','steps',2,'database','SOTA citations','step 4 · citations.json quotes',{rowOff:1,tag:'citations_cli check · routes',sources:[{path:'skills/_core/command_center/phase_steps.py',line:16,end_line:19},{path:'skills/proposal-deliberation/SKILL.md',line:312,end_line:320}]}),
 n('atlasCov','steps',2,'messagebus','smith atlas coverage','cited refs the sky lacks',{rowOff:2,sources:S('src/papersmith/core/atlas.py',118,128)}),
 n('ui','steps',3,'external','smith ui','phase drawer → /<skill>',{rowOff:2,tag:'command center',sources:S('skills/_core/command_center/phase_actions.py',1,15)}),
 n('board','steps',4,'external','Update board','phase · missing steps · gates',{rowOff:2,tag:'refresh at start · --no-refresh',sources:[{path:'skills/_core/command_center/board_refresh.py',line:1,end_line:25},{path:'skills/_core/command_center/server.py',line:3817,end_line:3827},{path:'src/papersmith/core/ui.py',line:769}]}),
 n('mathApi','steps',3,'messagebus','/api/model/math','concept map · KaTeX cards',{rowOff:1,sources:S('skills/_core/command_center/math_view.py',1,16)}),
 n('tutorStore','steps',4,'database','.papersmith/math-tutor/','thread + uploaded pages',{rowOff:1,sources:S('skills/_core/command_center/tutor.py',1,12)}),

 n('expDelib','expdelib',0,'frontend','/experimental-deliberation','requires data-paper/',{tag:'.pi/prompts',sources:K('experimental-deliberation',34,38)}),
 n('expVal','expdelib',1,'backend','experimental-validation',agentMeta('experimental-validation').sub,{...(agentMeta('experimental-validation').tag?{tag:agentMeta('experimental-validation').tag}:{}),sources:A('experimental-validation')}),
 n('expGate','expdelib',2,'security','Human acceptance','deliberated = operator',{sources:S('skills/experimental-deliberation/SKILL.md',35,65)}),
 n('expPub','expdelib',3,'backend','experimental-publish',agentMeta('experimental-publish').sub,{...(agentMeta('experimental-publish').tag?{tag:agentMeta('experimental-publish').tag}:{}),sources:A('experimental-publish')}),
 n('experiments','expdelib',4,'database','experiments/','experimental protocol',{tag:'5.1–5.5',sources:S('src/papersmith/core/init.py',107,109)}),

 n('dataCmd','data',0,'frontend','/datasets','toy → published',{tag:'.pi/prompts',sources:K('datasets',18,32)}),
 n('dataScout','data',1,'backend','dataset-scout',agentMeta('dataset-scout').sub,{tag:'sourced → licensed',sources:A('dataset-scout')}),
 n('dataCurator','data',2,'backend','dataset-curator',agentMeta('dataset-curator').sub,{tag:'toy → published',sources:A('dataset-curator')}),
 n('dataGate','data',3,'security','Upload consent','private · --consent <slug>',{sources:S('skills/datasets/SKILL.md',34,58)}),
 n('dataStore','data',4,'database','datasets/','registry · splits.json',{tag:'5.6',sources:S('skills/datasets/SKILL.md',199,216)}),

 n('impl','impl',0,'frontend','/proposal-implementation','standing → full-scale',{tag:'.pi/prompts',sources:K('proposal-implementation',96,101)}),
 n('implBuild','impl',1,'backend','implementation-build',agentMeta('implementation-build').sub,{...(agentMeta('implementation-build').tag?{tag:agentMeta('implementation-build').tag}:{}),sources:A('implementation-build')}),
 n('implWalk','impl',2,'backend','implementation-walk',agentMeta('implementation-walk').sub,{...(agentMeta('implementation-walk').tag?{tag:agentMeta('implementation-walk').tag}:{}),sources:A('implementation-walk')}),
 n('implGate','impl',3,'security','Authorizes a launch','operator only',{sources:S('skills/proposal-implementation/SKILL.md',144,144)}),
 n('repo','impl',4,'database','implementations/<repo>','its own git + .venv',{sources:[{path:'src/papersmith/core/init.py',line:107,end_line:109},{path:'src/papersmith/core/executor.py',line:33}]}),
 n('replicator','impl',1,'backend','paper-replicator',agentMeta('paper-replicator').sub,{rowOff:1,...(agentMeta('paper-replicator').tag?{tag:agentMeta('paper-replicator').tag}:{}),sources:[...A('paper-replicator'),{path:'skills/proposal-implementation/SKILL.md',line:166,end_line:178}]}),
 n('pubCode','impl',2,'messagebus','Published code?','adopt + audit, else rebuild',{rowOff:1,sources:S('skills/proposal-implementation/SKILL.md',166,176)}),
 n('replication','impl',3,'database','REPLICATION.md','equation → line provenance',{rowOff:1,tag:'5.7',sources:S('skills/proposal-implementation/SKILL.md',145,145)}),
 n('discPoc','impl',4,'database','discussion.json','verdicts · tests · novelty',{rowOff:1,tag:'gates 5.8',sources:[{path:'skills/_core/results/discussion.py',line:1,end_line:14},{path:'skills/_core/results/discussion_cli.py',line:1,end_line:16},{path:'skills/_core/command_center/server.py',line:1916}]}),

 n('pocCli','pocv',1,'messagebus','smith novelty --gate poc','approve · iterate',{tag:'novelty_cli.py',sources:[{path:'src/papersmith/core/novelty.py',line:1,end_line:8},{path:'skills/_core/results/novelty_cli.py',line:1,end_line:12}]}),
 n('pocRec','pocv',2,'database','novelty_gate.json · poc','beside the full decision',{sources:S('skills/_core/results/novelty_gate.py',278,303)}),
 n('pocGate','pocv',3,'security','G-EXP-POC','results + contrasted hypotheses',{tag:'operator · 5.9',sources:[{path:'skills/_core/command_center/server.py',line:1917},{path:'skills/_core/command_center/server.py',line:4536,end_line:4558}]}),
 n('pocCard','pocv',4,'external','Verify the PoC','Novedad tab · Experimentos stepper',{tag:'command center',sources:[{path:'skills/_core/command_center/static/novelty-panel.js',line:166,end_line:180},{path:'skills/_core/command_center/static/experiments-panel.js',line:38,end_line:45}]}),

 n('expImpl','expimpl',0,'frontend','/experimental-implementation','locked until G-EXP-POC',{tag:'.pi/prompts',sources:K('experimental-implementation',303,305)}),
 n('expBuild','expimpl',1,'backend','experiments-build',agentMeta('experiments-build').sub,{tag:'baselines: REPLICATION.md',sources:A('experiments-build')}),
 n('expRev','expimpl',2,'backend','experiments-reviewer',agentMeta('experiments-reviewer').sub,{...(agentMeta('experiments-reviewer').tag?{tag:agentMeta('experiments-reviewer').tag}:{}),sources:A('experiments-reviewer')}),
 n('expWalk','expimpl',3,'backend','experiments-walk',agentMeta('experiments-walk').sub,{...(agentMeta('experiments-walk').tag?{tag:agentMeta('experiments-walk').tag}:{}),sources:A('experiments-walk')}),
 n('expImplGate','expimpl',4,'security','Authorizes a launch','whole campaign',{sources:S('skills/experimental-implementation/SKILL.md',263,266)}),

 n('discFull','expimpl',1,'database','discussion.json','verdicts · tests · novelty',{rowOff:1,tag:'gates 5.12',sources:[{path:'skills/_core/results/discussion_cli.py',line:1,end_line:16},{path:'skills/experimental-implementation/SKILL.md',line:511,end_line:516},{path:'skills/_core/command_center/server.py',line:1920}]}),
 n('reviewRep','expimpl',2,'database','reviewer_report.json','blockers resolved',{rowOff:1,tag:'gates 5.13',sources:[{path:'.pi/agents/experiments-reviewer.md',line:98,end_line:100},{path:'skills/_core/command_center/server.py',line:1921}]}),

 n('expTutorCmd','expimpl',3,'frontend','/experiments-tutor','explains · asks · evaluates',{rowOff:1,tag:'Experimentos tab',sources:K('experiments-tutor',64,83)}),
 n('expTutor','expimpl',4,'backend','experiments-tutor',agentMeta('experiments-tutor').sub,{rowOff:1,tag:'never invents a number',sources:A('experiments-tutor')}),

 n('kaggle','creds',0,'frontend','/kaggle-accounts','taken-in → decided',{tag:'.pi/prompts',sources:K('kaggle-accounts',28,30)}),
 n('accCli','creds',1,'security','accounts_cli.py','validate --interactive',{tag:'TTY only',sources:S('skills/kaggle-accounts/SKILL.md',224,250)}),
 n('store','creds',2,'database','store/','validated credentials',{sources:S('skills/kaggle-accounts/SKILL.md',259)}),
 n('remPar','creds',3,'frontend','/remote-parallelism','estimate · assess --owners',{tag:'split a campaign?',sources:K('remote-parallelism',25,50)}),

 n('guard','remote',4,'security','refuse-offpath-push.js','extension: watches bash',{tag:'tool_call',sources:[{path:'.pi/extensions/refuse-offpath-push.js',line:1,end_line:30},{path:'.pi/APPEND_SYSTEM.md',line:37,end_line:43}]}),
 n('remote','remote',0,'frontend','/remote-execution','reachable → returned',{tag:'.pi/prompts',sources:K('remote-execution',40,44)}),
 n('readiness','remote',1,'security','readiness + gate','single-use token',{tag:'5.14',sources:S('skills/remote-execution/SKILL.md',42)}),
 n('remoteCli','remote',2,'messagebus','remote_cli.py','submit · poll · fetch',{tag:'13 subcommands',sources:S('skills/remote-execution/SKILL.md',1595,1607)}),
 n('inbox','remote',3,'database','kaggle-inbox/','ledger + results',{sources:S('src/papersmith/core/init.py',107,109)}),

 n('contribFind','nov',0,'backend','paper-reviewer','contribution type of the findings',{tag:'discussion.json',sources:[{path:'skills/_core/results/contribution_type.py',line:1,end_line:16},{path:'skills/experimental-implementation/SKILL.md',line:579,end_line:579}]}),
 n('novPanel','nov',1,'external','Novelty & Findings','Novedad & Hallazgos tab',{tag:'command center',sources:[{path:'skills/_core/command_center/static/novelty-panel.js',line:1,end_line:9},{path:'skills/_core/command_center/server.py',line:4531,end_line:4534}]}),
 n('novGate','nov',2,'security','G-NOVELTY','approve · iterate',{tag:'operator',sources:[{path:'skills/_core/results/novelty_gate.py',line:1,end_line:15},{path:'skills/_core/command_center/server.py',line:4536,end_line:4558}]}),
 n('novStore','nov',3,'database','novelty_gate.json','.papersmith/ · history',{sources:S('skills/_core/results/novelty_gate.py',59,60)}),
 n('novCli','nov',4,'messagebus','smith novelty','status · approve · iterate',{tag:'--gate full',sources:[{path:'src/papersmith/core/novelty.py',line:1,end_line:8},{path:'skills/_core/results/novelty_cli.py',line:1,end_line:12}]}),

 n('pwSkel','scaf',0,'frontend','/paper-writing skeleton','paper/ tree + contracts',{tag:'.pi/prompts',sources:K('paper-writing',14,16)}),
 n('sectionsDir','scaf',1,'database','sections/*.md','section contracts',{tag:'G1',sources:S('src/papersmith/core/manifest.py',190,195)}),
 n('lineInit','scaf',2,'messagebus','smith init --kind <line>','eight lines · own board + flow',{tag:'its own section contracts',sources:[{path:'src/papersmith/core/manifest.py',line:62,end_line:169},{path:'src/papersmith/core/init.py',line:599,end_line:602}]}),
 n('sysRev','scaf',3,'frontend','/systematic-review','protocol · search · screening',{tag:'review line · PRISMA 2020',sources:S('skills/systematic-review/SKILL.md',34,173)}),

 n('pwMark','decl',0,'frontend','/paper-writing mark','authorship · funding · ethics',{tag:'.pi/prompts',sources:K('paper-writing',14,16)}),
 n('insumos','decl',1,'backend','insumos-observer',agentMeta('insumos-observer').sub,{...(agentMeta('insumos-observer').tag?{tag:agentMeta('insumos-observer').tag}:{}),sources:A('insumos-observer')}),

 n('pw','write',0,'frontend','/paper-writing','one named block at a time',{tag:'.pi/prompts',sources:K('paper-writing',14,16)}),
 n('redactor','write',1,'backend','redactor',agentMeta('redactor').sub,{...(agentMeta('redactor').tag?{tag:agentMeta('redactor').tag}:{}),sources:A('redactor')}),
 n('contract','write',2,'backend','contract-auditor',agentMeta('contract-auditor').sub,{...(agentMeta('contract-auditor').tag?{tag:agentMeta('contract-auditor').tag}:{}),sources:A('contract-auditor')}),
 n('style','write',3,'backend','style-sampler',agentMeta('style-sampler').sub,{...(agentMeta('style-sampler').tag?{tag:agentMeta('style-sampler').tag}:{}),sources:A('style-sampler')}),
 n('aiAud','write',1,'backend','ai-auditor',agentMeta('ai-auditor').sub,{rowOff:1,tag:'ai_audit · humanize',sources:A('ai-auditor')}),
 n('grounding','write',4,'backend','section-grounding-auditor',agentMeta('section-grounding-auditor').sub,{...(agentMeta('section-grounding-auditor').tag?{tag:agentMeta('section-grounding-auditor').tag}:{}),sources:A('section-grounding-auditor')}),

 n('paperCli','figs',0,'messagebus','paper_cli.py','write judges what comes back',{tag:'34 verbs · --expect-digest',sources:[{path:'skills/paper-writing/SKILL.md',line:14,end_line:16},{path:'skills/paper-writing/scripts/paper_cli.py',line:4863,end_line:4868}]}),
 n('diagram','figs',1,'backend','diagram-author',agentMeta('diagram-author').sub,{...(agentMeta('diagram-author').tag?{tag:agentMeta('diagram-author').tag}:{}),sources:A('diagram-author')}),
 n('figAud','figs',2,'backend','figure-auditor',agentMeta('figure-auditor').sub,{...(agentMeta('figure-auditor').tag?{tag:agentMeta('figure-auditor').tag}:{}),sources:A('figure-auditor')}),
 n('figVis','figs',1,'backend','figure-visual-reviewer',agentMeta('figure-visual-reviewer').sub,{rowOff:1,tag:'by eye · after the audit',sources:[...A('figure-visual-reviewer'),{path:'skills/paper-writing/SKILL.md',line:2043}]}),
 n('figRev','figs',3,'frontend','/figure-review','probe · raster, no changes',{tag:'.pi/prompts',sources:K('figure-review',1,12)}),

 n('finalJudge','out',0,'backend','paper-reviewer','final judge · overall 1–6',{tag:'returns one round',sources:[...A('paper-reviewer'),{path:'skills/paper-writing/SKILL.md',line:2088}]}),
 n('reviewCli','out',1,'messagebus','paper_cli.py review','--input <round.json>',{tag:'verdict per revision',sources:S('skills/paper-writing/scripts/paper_cli.py',3799,3805)}),
 n('reviewJson','out',2,'database','paper_review.json','.papersmith/ · one per round',{sources:[{path:'skills/_core/command_center/static/paper-review-panel.js',line:1,end_line:41},{path:'skills/_core/command_center/server.py',line:3863,end_line:3865}]}),
 n('styleRed','out',3,'external','PDF preview tab','style · redundancy · judge',{tag:'command center',sources:[{path:'skills/_core/command_center/static/index.html',line:4104},{path:'skills/_core/command_center/server.py',line:946,end_line:996}]}),
 n('paper','out',4,'database','paper/','main.tex · main.pdf',{sources:S('src/papersmith/core/init.py',107,111)}),
 n('judgeBtn','out',0,'external','Launch the final judge','next round → agent terminal',{rowOff:1,tag:'PDF tab · one per round',sources:[{path:'skills/_core/command_center/static/paper-review-panel.js',line:28,end_line:36},{path:'skills/_core/command_center/static/paper-review-panel.js',line:262,end_line:271}]}),
 n('changeCtl','out',2,'external','Change Control','marks → Caztor chat',{rowOff:1,tag:'PDF tab panel',sources:[{path:'skills/_core/command_center/static/index.html',line:4227,end_line:4245},{path:'skills/_core/command_center/static/index.html',line:7797,end_line:7798}]}),
 n('caztor','out',3,'external','Caztor LaTeX editor','files · LaTeX · PDF · chat',{rowOff:1,tag:'editor switch · sidecar',sources:[{path:'skills/_core/command_center/caztor.py',line:1,end_line:29},{path:'skills/_core/command_center/static/index.html',line:4097,end_line:4125},{path:'skills/_core/command_center/server.py',line:2754,end_line:2795}]}),

 n('jfCmd','jv',4,'frontend','/journal-finder','--scope national · Q1-Q2',{tag:'.pi/prompts',sources:[{path:'.pi/prompts/journal-finder.md',line:1,end_line:7,label:'template /journal-finder'},{path:'skills/journal-finder/SKILL.md',line:15,end_line:26}]}),
 n('jfCli','jv',3,'messagebus','journal_cli.py search','OpenAlex · Publindex IBN 2026',{tag:'national: A1 · A2 · B',sources:[{path:'skills/journal-finder/scripts/journal_cli.py',line:2965,end_line:3207},{path:'skills/journal-finder/scripts/journal_cli.py',line:2761,end_line:2924},{path:'skills/journal-finder/SKILL.md',line:138,end_line:195}]}),
 n('jfQr','jv',2,'messagebus','Quartile + review time','SCImago 2025 · Crossref→PubMed',{tag:'bundled · sjr-import wins',sources:[{path:'skills/journal-finder/scripts/journal_cli.py',line:1144,end_line:1153},{path:'skills/journal-finder/scripts/journal_cli.py',line:1795,end_line:1852},{path:'skills/journal-finder/SKILL.md',line:479,end_line:520}]}),
 n('jfJson','jv',1,'database','journal-candidates.json','paper/ · schema 1',{sources:[{path:'skills/journal-finder/scripts/journal_cli.py',line:2985},{path:'skills/journal-finder/scripts/journal_cli.py',line:3206}]}),
 n('jvPick','jv',1,'security','Operator picks a journal','PDF Preview → venue select',{rowOff:1,sources:[{path:'skills/_core/command_center/static/journals-panel.js',line:987,end_line:992},{path:'skills/_core/command_center/server.py',line:3950,end_line:3977},{path:'skills/paper-writing/scripts/paper_venue.py',line:213,end_line:300}]}),
 n('jvAgent','jv',2,'backend','venue-adapter',agentMeta('venue-adapter').sub,{rowOff:1,tag:'requirements · quote + url',sources:[...A('venue-adapter'),{path:'skills/paper-writing/scripts/paper_venue.py',line:339,end_line:509}]}),
 n('jvDiff','jv',3,'messagebus','venue acquire · diff','template · audit.json',{rowOff:1,sources:[{path:'skills/paper-writing/scripts/paper_venue.py',line:594,end_line:673},{path:'skills/paper-writing/scripts/paper_venue.py',line:1396,end_line:1419}]}),
 n('jvApprove','jv',3,'security','Operator approves plan','sha256-bound · approval.json',{rowOff:2,sources:[{path:'skills/paper-writing/scripts/paper_venue.py',line:1425,end_line:1481},{path:'skills/paper-writing/SKILL.md',line:2491,end_line:2522},{path:'skills/_core/command_center/server.py',line:3990,end_line:4009}]}),
 n('jvWrite','jv',2,'messagebus','paper_cli.py write','text changes only here',{rowOff:2,tag:'redactor → audit',sources:S('skills/paper-writing/SKILL.md',2551,2558)}),
 n('jvBuild','jv',1,'messagebus','venue build','class · front matter · blocks',{rowOff:2,tag:'main.tex untouched',sources:[{path:'skills/paper-writing/scripts/paper_venue.py',line:1735,end_line:1888},{path:'skills/_core/command_center/server.py',line:4011,end_line:4030}]}),
 n('translate','jv',0,'messagebus','paper_cli.py translate','plan · store · build · audit',{rowOff:3,tag:'fidelity gate per block',sources:[{path:'skills/paper-writing/scripts/paper_cli.py',line:3459,end_line:3477},{path:'skills/paper-writing/SKILL.md',line:2598,end_line:2739}]}),
 n('translator','jv',1,'backend','translator',agentMeta('translator').sub,{rowOff:3,tag:'neutral academic Spanish',sources:A('translator')}),
 n('tsReviewer','jv',2,'backend','translation-style-reviewer',agentMeta('translation-style-reviewer').sub,{rowOff:3,tag:'reads translate audit',sources:A('translation-style-reviewer')}),
 n('translations','jv',3,'database','paper/translations/es/','Spanish main.pdf · PDF tab',{rowOff:3,sources:[{path:'skills/_core/command_center/server.py',line:3867,end_line:3875},{path:'skills/_core/command_center/server.py',line:2690,end_line:2691}]}),
 n('jvPdf','jv',0,'database','main.pdf','paper/venues/<slug>/',{rowOff:2,sources:[{path:'skills/_core/command_center/server.py',line:2690,end_line:2727},{path:'skills/_core/command_center/server.py',line:2415,end_line:2442}]}),

 n('audit','audit',0,'frontend','/skill-audit','subject: any skill',{tag:'.pi/prompts',sources:K('skill-audit',23,23)}),
 n('auditRep','audit',1,'backend','audit-report',agentMeta('audit-report').sub,{...(agentMeta('audit-report').tag?{tag:agentMeta('audit-report').tag}:{}),sources:A('audit-report')}),
 n('report','audit',2,'database','Audit report','never repairs',{sources:S('skills/skill-audit/SKILL.md',668,683)}),
];
const e=(from,to,label,extra={})=>({id:`${from}-${to}`,from,to,...(label?{label}:{}),...extra});
const main={variant:'emphasis',role:'main'};
const edges=[
 e('plaus','ingest','top-5 to ingest',main),
 e('ingest','delib','guidance/',main),
 e('delib','expDelib','revision rNN',main),
 e('expDelib','impl','protocol',main),
 e('discPoc','pocCard','complete discussion',main),
 e('pocGate','expImpl','verified PoC',{variant:'security',role:'main'}),
 e('expImpl','kaggle','job ready',main),
 e('kaggle','remote','accounts proven',main),
 e('inbox','novPanel','measured results',main),
 e('novGate','pwSkel','approved → writing',{variant:'security',role:'main',fromSide:'bottom',toSide:'top'}),
 e('pwSkel','pwMark','section contracts',main),
 e('pwMark','pw','declarations',main),

 e('piMd','plaus','/<skill>',main),
 e('canon','sync'), e('sync','piDir'), e('subagents','piDir',null,{variant:'dashed'}),
 e('kwHelp','banco'), e('banco','draftGate'), e('draftGate','plaus','/plausibility <draft>',{variant:'security'}),
 e('pool','ptCmd','accepted report'), e('ptCmd','ptAgent'), e('ptCmd','ptJson','operator agrees',{variant:'security'}), e('ptJson','kindSet',null,{variant:'dashed'}),
 e('plaus','scout'), e('scout','grapher'), e('grapher','screener'), e('screener','pool',null,{variant:'security'}),
 e('ingest','ingestAgent'), e('ingestAgent','guidance'), e('guidance','pixelrag'),
 e('delib','delibCli'), e('delibCli','delibGate'), e('delibGate','delibPub',null,{variant:'security'}), e('delibPub','proposals'),
 e('grapher','delibPub','atlas.json',{variant:'dashed'}),
 e('delib','stepPP','concept + math',{variant:'dashed'}),
 e('stepPP','stepHyp'), e('stepHyp','stepMath'), e('stepMath','tutor',null,{variant:'dashed'}), e('tutor','tutorAgent'), e('tutorAgent','tutorStore'),
 e('stepMath','stepCite'), e('stepCite','contribProp'), e('stepCite','atlasCov'), e('contribProp','modelSpec'), e('ui','mathApi'), e('ui','board'),
 e('expDelib','expVal'), e('expVal','expGate'), e('expGate','expPub',null,{variant:'security'}), e('expPub','experiments'),
 e('dataCmd','dataScout'), e('dataScout','dataCurator'), e('dataCurator','dataGate'), e('dataGate','dataStore',null,{variant:'security'}),
 e('dataStore','implBuild','toy set',{variant:'dashed',fromSide:'bottom',toSide:'top'}),
 e('impl','implBuild'), e('implBuild','implWalk'), e('implWalk','implGate'), e('implGate','repo',null,{variant:'security'}),
 e('impl','replicator','fidelity'), e('replicator','pubCode'), e('pubCode','replication'),
 e('repo','discPoc','discussion_cli.py'),
 e('pocCard','pocGate'), e('pocGate','pocRec',null,{variant:'security'}), e('pocCli','pocRec',null,{variant:'dashed'}),
 e('expImpl','expBuild'), e('expBuild','expRev'), e('expRev','expWalk'), e('expWalk','expImplGate'),
 e('expBuild','discFull','discussion_cli.py'), e('expRev','reviewRep'),
 e('reviewRep','expTutorCmd',null,{variant:'dashed'}), e('expTutorCmd','expTutor'),
 e('kaggle','accCli'), e('accCli','store'), e('store','remPar',null,{variant:'dashed'}),
 e('remote','readiness'), e('readiness','remoteCli',null,{variant:'security'}), e('remoteCli','inbox'),
 e('store','remoteCli','credentials',{variant:'dashed'}),
 e('contribFind','novPanel',null,{variant:'dashed'}), e('novPanel','novGate',null,{fromSide:'right',toSide:'left'}), e('novGate','novStore',null,{variant:'security'}), e('novCli','novStore',null,{variant:'dashed'}),
 e('pwSkel','sectionsDir'), e('lineInit','sectionsDir',null,{variant:'dashed'}), e('lineInit','sysRev'), e('pwMark','insumos',null,{variant:'dashed'}),
 e('pw','redactor'), e('redactor','contract'), e('contract','style'), e('style','grounding'), e('redactor','aiAud',null,{variant:'dashed'}),
 e('pw','paperCli','delegates',{variant:'dashed'}),
 e('paperCli','diagram'), e('diagram','figAud'), e('figAud','figRev'), e('diagram','figVis',null,{variant:'dashed'}),
 e('grounding','paper','sections',{variant:'dashed'}),
 e('paper','styleRed',null,{variant:'dashed'}),
 e('finalJudge','reviewCli'), e('reviewCli','reviewJson'), e('reviewJson','styleRed',null,{variant:'dashed'}),
 e('judgeBtn','finalJudge','round N'), e('styleRed','caztor','LaTeX editor on'), e('changeCtl','caztor'),
 e('paper','jfCmd','compiled PDF',main),
 e('jfCmd','jfCli'), e('jfCli','jfQr'), e('jfQr','jfJson'),
 e('jfJson','jvPick','candidates'), e('jvPick','jvAgent',null,{variant:'security'}), e('jvAgent','jvDiff'),
 e('jvDiff','jvApprove','agent drafts plan.md'), e('jvApprove','jvWrite',null,{variant:'security'}), e('jvWrite','jvBuild'), e('jvBuild','jvPdf'),
 e('jvPdf','translate','Spanish-only journal'), e('translate','translator'), e('translator','tsReviewer'), e('tsReviewer','translations'),
 e('audit','auditRep'), e('auditRep','report'),
];
// Lanes are numbered by the eleven dashboard phases (phase_actions.STAGES);
// a lettered lane is a sub-lane of the phase it carries the number of.
const lanes=[
 ['pi','1 · Harness (Pi)'], ['help','2a · Thematic help (optional, before /plausibility)'], ['plaus','2 · Plausibility, then the paper type (/paper-type; smith kind set moves the workspace to another line)'],['ingest','3 · Ingestion'],['delib','4 · Proposal deliberation'],['steps','4a · Problem & pillars → hypotheses → mathematics → SOTA citations → judge-reviewer (Mapa Conceptual); smith ui and Update board'],
 ['expdelib','5 · Proof of concept and experiments: the protocol first'],['data','5a · Datasets (toy set → official preparation)'],['impl','5b · Replication and proof of concept'],['pocv','5c · Proof-of-concept verification (G-EXP-POC, operator)'],['expimpl','5d · Full experiments (after G-EXP-POC)'],
 ['creds','5e · Credentials'],['remote','5f · Remote rehearsal and launch'],['nov','5g · Findings: contribution type and G-NOVELTY'],['scaf','6 · Scaffolding (the line chosen with smith init --kind <line>: experimental, review or one of six empirical lines)'],['decl','7 · Declarations'],['write','8 · Writing'],['figs','9 · Figures and grounding'],['out','10 · Paper (PDF tab: Caztor LaTeX editor, Change Control, final judge rounds)'],['jv','10a · Journal choice, venue adaptation and Spanish translation (after the PDF)'],
 ['audit','11 · Audit (transversal)']].map(([id,label])=>({id,label}));

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
  repository:{url:'https://github.com/LIAUNAL/papersmith-ai',provider:'github',link_mode:'web',revision:REVISION},
  legend:{mode:'auto',entries:{frontend:{label:'Pi command /skill'},backend:{label:'Pi subagent'},messagebus:{label:'CLI'},security:{label:'Gate (human)'},database:{label:'Artifact on disk'},external:{label:'Pi harness'}}}
 },
 layout:{mode:'grid',origin:[30,48],cols:5,cellW:182,cellH:58,gapX:24,gapY:62},
 components, boundaries, connections,
 cards:[
  {dot:'cyan',title:'How Pi sees it',items:['.pi/APPEND_SYSTEM.md is the system prompt: Pi appends it to the project one','/<skill> = .pi/prompts/<skill>.md: it loads the SKILL.md and passes $ARGUMENTS, after the prompt gate (skills/prompt-gate) measured them: under its threshold it proposes a clearer prompt or asks, and waits for the operator; /prompt-gate /<skill> <prompt> reviews one by hand',`The ${AGENT_COUNT} .pi/agents/ are projected from .claude/agents/; Pi core has no subagents, so they need pi-subagents`,'Each agent declares tools (read, find, grep, write, edit, bash, mcp) and its stretch','refuse-offpath-push.js intercepts bash tool_call; it is a warning that fails open, not a gate']},
  {dot:'emerald',title:'Harness commands',items:['npm run setup:harnesses — links .pi/skills -> ../skills','python scripts/sync-repo-harness.py — regenerates .pi/prompts, .pi/agents, .pi/extensions (--check detects drift)','smith init · env · upgrade · kind · status · ingest · deliberate · implement · run · remote · target · audit · doctor · gpu · novelty · ui · atlas · paper · mcp · team · colab · keys','smith init --kind <line> picks one of eight paper lines: experimental (the default, these phases), review (PRISMA 2020, /systematic-review and review_cli.py), and six empirical lines that start from a study protocol (/study-protocol-deliberation): observational-measurement, hardware, lab-simulation, data-resource, experiment-intervention and qualitative-participatory; each line has its own board and its own Archify flow (docs/diagrams/papersmith-<line>-flow.html)','smith kind set <type> --by <operator> moves a workspace to the line of the paper type agreed with /paper-type; it refuses once a proposal revision or paper/main.tex exists, unless --force','smith env install builds the workspace micromamba environment from its lock, env/<cpu|cuda|rocm>.conda-lock.yml, never from a live solve (--rebuild forces it; smith env status · clean)','smith ui regenerates the board\'s derived artifacts at start (SOTA atlas page, manuscript layer and graph, novelty graph, wiring health; --no-refresh skips it); the topbar\'s Update board (POST /api/board/refresh) does it again and reports the current phase, its missing steps and the open or failed gates','smith ui --export-snapshot · --publish-pages (/ui-github) · --lan; /upgrade-project brings an older workspace to this release','npm run test:all — the quality gate']},
  {dot:'violet',title:'Per-skill CLIs',items:['paper-ingestion: python scripts/setup_env.py install','deliberation: node skills/<skill>/cli.mjs --serve','the proposal graph: merge_proposal_sky.py → check_atlas.py → render_atlas.py','implementation: implementation_cli.py materialize · verify · fidelity · audit · step','kaggle-accounts: accounts_cli.py list · discover · validate · remove · materialize','remote-execution: remote_cli.py submit · status · poll · fetch · readiness …','paper-writing: paper_cli.py status · plan · write · verify · reorder · review · translate … (34 verbs); substitute, write and humanize --apply take --expect-digest; verify adds advisory coherence warnings','journal-finder: journal_cli.py search [--scope national] [--refine-top N] · sjr-import · status; a first stage ranks every journal by fit, a second reads similar papers in the top N (5 by default) for a style match; SCImago 2025 is bundled, Publindex IBN 2026 for the national scope','venue adaptation: paper_cli.py venue select · requirements · acquire · catalog · diff · plan · approve · build · status · list','datasets: datasets_cli.py synth · search · license · qc · prepare · publish','translation: paper_cli.py translate plan · store · build · audit · status','final judge: paper_cli.py review --input <round.json>','figure-review: review_cli.py probe · raster · measure; paper_cli.py figure provenance','pixelrag: facts · record · status; experiment diagrams: diagram_cli.py render · validate · submit','skill-audit: audit_cli.py']},
  {dot:'amber',title:'Flow rules',items:['The order is optional: each skill refuses with a code when its input is missing','Starting with /plausibility, before ingestion, is the recommendation','On the plausibility report\'s acceptance, /paper-type scores the idea against the paper-type catalogue, the paper-type-advisor relates each type to it, and the operator agrees a type and variant (.papersmith/paper_type.json); when the type belongs to another line, the operator moves the workspace with smith kind set or starts one with smith init --kind <line>','The proposal is built in order: the central problem and its pillars, then the hypotheses, then the mathematics, then the SOTA citations, then the judge-reviewer; each step stays locked until the one before it exists (Mapa Conceptual tab, one Generar y deliberar button per step)','Every pillar, hypothesis, layer, equation and experiment cites 2 to 5 pool references in citations.json, each with a verbatim 20–300 character quote of its abstract; phases 4, 5 and 8 end with smith atlas coverage, and sota-scout and sota-grapher add what the constellation lacks','paper-reviewer, the judge-reviewer, classifies the contribution type of the proposal (model_spec.json) and of each stage\'s findings (discussion.json)','Phase 5 runs protocol → toy set → replication → proof of concept → its verification (G-EXP-POC) → timing → optional search (/hyperparameter-search) → full experiments → review → rehearsal → launch; /experiment-diagrams draws the proof of concept and the full experiments for the operator to validate, /remote-parallelism decides whether to split a campaign, and /experiments-tutor explains each design decision','The full experiments stay locked until the operator verifies the proof of concept (smith novelty approve --gate poc, or the Novedad tab card); the writing waits for G-NOVELTY','/datasets gives a seeded toy set first (dataset-scout: sourced → licensed; dataset-curator: toy → checked → prepared → published); publishing is private and only on the operator\'s consent','The proof of concept reads the toy set; the full experiments read the one official subject-wise preparation, mounted by remote notebooks','paper-replicator (implementation fidelity) searches for published code first: adopt it and audit its correspondence to the paper, else reimplement from the ingested paper; its baselines feed the experiments','experiments-reviewer reviews the instrumented code before any rehearsal or launch','No walk can launch a campaign: the operator authorizes it','contract-auditor, redactor and style-sampler have no code path: the orchestrator launches them and write judges','/figure-review and /skill-audit only report; they never repair','Once the paper compiles, /journal-finder ranks international journals by SJR quartile (the bundled SCImago 2025 snapshot; a newer sjr-import wins), access, APC and an estimated review time, or with --scope national the Colombian Publindex IBN 2026 journals (A1, A2, B) by measured review time; nothing is submitted','The operator picks a journal in the PDF Preview tab; venue-adapter reads its guidelines and every requirement carries a quote and a url','The operator approves the adaptation plan by its sha256; text changes go only through write, and venue build never writes paper/main.tex','For a journal that only receives Spanish, paper_cli.py translate turns the verified English paper into paper/translations/es/ block by block (translator, then translation-style-reviewer); every block passes a fidelity gate (citations, labels, math, numbers, paragraphs) and the English paper stays the source','The final judge panel: paper-reviewer reviews the compiled paper and returns a round; /paper-writing records it with paper_cli.py review --input in .papersmith/paper_review.json, and the PDF tab shows the verdict per round and launches the next round from its Launch the final judge button','The PDF tab shows Caztor, the LaTeX editor (four panes: files, LaTeX source, PDF and assistant chat), while its LaTeX editor switch is on, and the PDF viewer while it is off; the Change Control panel turns the operator\'s marks into a message in Caztor\'s chat','pixelrag turns an extracted figure into evidence bound to the image sha256; ai-auditor scores writing quality for ai_audit and humanize; figure-visual-reviewer judges a rendered diagram by eye once its mechanical audit passed','smith ui: each pipeline phase card sends its /<skill> with the rules as a guide, or opens the panel that owns the work']}
 ]};
const out = path.resolve(process.argv[2] || fileURLToPath(new URL('./candidate.json', import.meta.url)));
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify(doc, null, 1));
console.log(`candidate: ${out}`);
