import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { cp, mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const repositoryRoot=path.resolve('.');

const typeboxEntry=createRequire(import.meta.url).resolve('typebox');
const {createJiti}=await import('jiti');
const jiti=createJiti(import.meta.url,{alias:{typebox:typeboxEntry}});
const v2=await jiti.import(path.resolve('skills/_core/deliberation/engine/exports.ts'));
const marker='<!-- proposal-workspace:artifact:v1 -->\n';
const r01='research-concept-r01.md';
const r02='research-concept-r02.md';
const operationId='22222222-2222-4222-8222-222222222222';
const lifecycleResultKeys=['status','operation','withdrawnFilename','restoredLatestFilename','artifactCount','backupLocation','auditStatus','selfAuditStatus','warnings'].sort();
const productiveLifecycleKeys=[...lifecycleResultKeys,'operationId','modelCalls','plannerCalls'].sort();

async function writeJson(filename,value) { await mkdir(path.dirname(filename),{recursive:true}); await writeFile(filename,JSON.stringify(value)); }
async function createRevision(root,filename,body,sourceFilename) {
 await writeFile(path.join(root,'proposals',filename),marker+body);
 const state=await v2.loadDocumentState(root,filename);
 if (sourceFilename) {
  const stored=JSON.parse(await readFile(v2.derivedStatePath(root,filename),'utf8'));
  stored.manifest.status='COMMITTED';
  await writeJson(v2.derivedStatePath(root,filename),stored);
  const sourceBytes=await readFile(path.join(root,'proposals',sourceFilename));
  const sourceRevision=sourceFilename.match(/-r(\d+)\.md$/)[1];
  await writeJson(v2.receiptPath(root,filename),{
   sourceRevision:`r${sourceRevision}`,targetRevision:state.revision,sourceFilename,targetFilename:filename,
   documentShaBefore:v2.sha256(sourceBytes),documentShaAfter:state.documentSha256,derivedStateStatus:'COMMITTED',
  });
 }
 return state;
}
async function fixture(options={}) {
 const root=await mkdtemp(path.join(os.tmpdir(),'proposal-deliberation-revision-lifecycle-'));
 await mkdir(path.join(root,'proposals'),{recursive:true});
 await createRevision(root,r01,'# Base\n\nBase text.\n');
 await createRevision(root,r02,'# Revision\n\nRevised text.\n',r01);
 if (options.r03) await createRevision(root,'research-concept-r03.md','# Dependent\n\nLater text.\n',r02);
 return {root,tx:(dependencies={})=>new v2.RevisionLifecycleTransaction(root,{newOperationId:()=>operationId,...dependencies})};
}
async function productiveTool(root) {
 await mkdir(path.join(root,'.pi'),{recursive:true});
 await cp(path.join(repositoryRoot,'skills/_core/deliberation/engine'),path.join(root,'skills/_core/deliberation/engine'),{recursive:true});
 // The engine reads the shared section-label convention beside it, as the kit ships it.
 await cp(path.join(repositoryRoot,'skills/_core/conventions'),path.join(root,'skills/_core/conventions'),{recursive:true});
 const workspace=await jiti.import(path.join(root,'skills/_core/deliberation/engine/proposal-workspace.ts'));
 const tools=[];
 workspace.default({registerTool:tool=>tools.push(tool),on:()=>{}});
 const tool=tools.find(candidate=>candidate.name==='proposal_deliberation_execute');
 assert.ok(tool);
 return tool;
}
async function treeSnapshot(root) {
 const result={};
 async function walk(directory) {
  let entries=[];
  try { entries=await readdir(directory,{withFileTypes:true}); } catch { return; }
  for (const entry of entries) {
   const absolute=path.join(directory,entry.name);
   if (entry.isDirectory()) await walk(absolute);
   else if (entry.isFile()) result[path.relative(root,absolute).split(path.sep).join('/')]=v2.sha256(await readFile(absolute));
  }
 }
 await walk(root);
 return Object.fromEntries(Object.entries(result).sort(([a],[b])=>a.localeCompare(b)));
}
async function publicBytes(root,filename=r02) {
 return Promise.all([readFile(path.join(root,'proposals',filename)),readFile(v2.derivedStatePath(root,filename)),readFile(v2.receiptPath(root,filename))]);
}
async function successfulWithdrawal(run,dependencies={}) {
 const result=await run.tx(dependencies).withdraw({filename:r02,reason:'Superseded by the base revision.'});
 assert.equal(result.status,'withdrawn',JSON.stringify(result));
 return result;
}

const repositoryProposalsBefore=await treeSnapshot(path.join(repositoryRoot,'proposals'));

test('classifies managed revision lifecycle intent before DELETE while preserving content deletion',()=>{
 assert.equal(v2.resolveIntent('Retira la revisión administrada research-concept-r02.md.').intent,'WITHDRAW_REVISION');
 assert.equal(v2.resolveIntent('retira la revisión r02').intent,'WITHDRAW_REVISION');
 assert.equal(v2.resolveIntent('restaura la revisión research-concept-r02.md').intent,'RESTORE_WITHDRAWN_REVISION');
 assert.equal(v2.resolveIntent('elimina esta sección').intent,'DELETE');
 assert.equal(v2.resolveIntent('elimina r02').intent,'AMBIGUOUS');
 assert.equal(v2.resolveIntent('retira este párrafo').intent,'AMBIGUOUS');
 assert.equal(v2.operationSpec.WITHDRAW_REVISION.maxModels,0);
 assert.equal(v2.operationSpec.RESTORE_WITHDRAWN_REVISION.maxRoleAuthorizations,0);
});

test('explicit lifecycle dispatch occurs before state, planner, tutor, reviewer, or model paths',async()=>{
 let stateCalls=0,lifecycleCalls=0,lifecycleInput;
 const expected={status:'blocked',operation:'WITHDRAW_REVISION',withdrawnFilename:null,restoredLatestFilename:null,artifactCount:0,backupLocation:null,auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',warnings:['stub']};
 const orchestrator=new v2.ProposalDeliberationOrchestrator('/unused',{},undefined,{plan:async()=>{throw new Error('planner called');}},{tutor:{assess:async()=>{throw new Error('tutor called');}},reviewer:{review:async()=>{throw new Error('reviewer called');}}},async()=>{stateCalls++;throw new Error('state called');},{withdraw:async input=>{lifecycleCalls++;lifecycleInput=input;return expected;},restore:async()=>{throw new Error('restore called');}});
 const result=await orchestrator.execute({instruction:'Elimina r02.',operation:'WITHDRAW_REVISION',sourceFilename:r02,withdrawalOperationId:operationId});
 assert.deepEqual(result,expected);
 assert.equal(stateCalls,0);
 assert.equal(lifecycleCalls,1);
 assert.equal(Object.hasOwn(lifecycleInput,'operationId'),false);
});

test('base, missing, malformed, inconsistent, missing-source, and dependent revisions block before mutation',async()=>{
 const base=await fixture();
 const baseBefore=await treeSnapshot(base.root);
 assert.match((await base.tx().withdraw({filename:r01})).warnings[0],/BASE_REVISION/);
 assert.deepEqual(await treeSnapshot(base.root),baseBefore);

 for (const mutate of [
  async run=>rm(v2.derivedStatePath(run.root,r02)),
  async run=>writeFile(v2.receiptPath(run.root,r02),'{'),
  async run=>{const receipt=JSON.parse(await readFile(v2.receiptPath(run.root,r02),'utf8'));receipt.targetRevision='r99';await writeJson(v2.receiptPath(run.root,r02),receipt);},
  async run=>rm(path.join(run.root,'proposals',r01)),
 ]) {
  const run=await fixture();
  await mutate(run);
  const before=await treeSnapshot(run.root);
  const result=await run.tx().withdraw({filename:r02});
  assert.equal(result.status,'blocked',JSON.stringify(result));
  assert.deepEqual(await treeSnapshot(run.root),before);
 }
 const dependent=await fixture({r03:true});
 const dependentBefore=await treeSnapshot(dependent.root);
 const blocked=await dependent.tx().withdraw({filename:r02});
 assert.equal(blocked.status,'blocked');
 assert.match(blocked.warnings[0],/LATER_DEPENDENT_REVISION_EXISTS/);
 assert.deepEqual(await treeSnapshot(dependent.root),dependentBefore);
});

test('unsafe withdrawal-root aliases fail closed without writing outside the project',async()=>{
 const run=await fixture();
 const outside=await mkdtemp(path.join(os.tmpdir(),'proposal-deliberation-withdrawal-escape-'));
 await symlink(outside,path.join(run.root,'.proposal-deliberation','withdrawn'));
 const before=await publicBytes(run.root);
 const result=await run.tx().withdraw({filename:r02});
 assert.equal(result.status,'blocked');
 assert.match(result.warnings[0],/UNSAFE_LIFECYCLE_DIRECTORY/);
 assert.deepEqual(await publicBytes(run.root),before);
 assert.deepEqual(await readdir(outside),[]);
});

test('successful withdrawal quarantines exact artifacts, writes complete metadata, and passes fresh audits',async()=>{
 const run=await fixture();
 const result=await successfulWithdrawal(run);
 assert.deepEqual(Object.keys(result).sort(),lifecycleResultKeys);
 assert.equal(result.restoredLatestFilename,r01);
 assert.equal(await v2.latestManagedFilename(run.root),r01);
 const directory=path.join(run.root,result.backupLocation);
 const metadata=JSON.parse(await readFile(path.join(directory,'metadata.json'),'utf8'));
 assert.equal(metadata.requestedFilename,r02);
 assert.equal(metadata.revision,'r02');
 assert.equal(metadata.sourceRevision,'r01');
 assert.equal(metadata.sourceFilename,r01);
 assert.equal(metadata.artifacts.length,3);
 assert.equal(metadata.inventoryDigest,v2.lifecycleInventoryDigest(metadata.artifacts));
 for (const artifact of metadata.artifacts) {
  assert.equal(v2.sha256(await readFile(path.join(directory,artifact.quarantineRelativePath))),artifact.sha256);
  assert.equal(v2.sha256(await readFile(path.join(directory,'public-backup',artifact.publicRelativePath))),artifact.sha256);
  await assert.rejects(readFile(path.join(run.root,artifact.publicRelativePath)));
 }
 const markerValue=JSON.parse(await readFile(path.join(directory,'audit-marker.json'),'utf8'));
 assert.equal(markerValue.state,'COMMITTED');
 assert.equal(markerValue.auditStatus,'PASS');
 assert.equal(markerValue.selfAuditStatus,'PASS');
 assert.equal((await v2.runConsistencyAudit({projectRoot:run.root})).status,'PASS');
 assert.equal((await v2.runProposalDeliberationSelfAudit({projectRoot:run.root})).status,'PASS');
});

test('withdrawal writes a bounded PENDING_AUDIT marker before SelfAudit and propagates the exact context',async()=>{
 const run=await fixture();
 let observed;
 const selfAudit=async input=>{
  observed=input.auditContext;
  assert.equal(input.auditContext.operationType,'WITHDRAW_REVISION');
  assert.equal(input.auditContext.phase,'WITHDRAW_PUBLIC_ARTIFACTS_MOVED');
  assert.equal(input.auditContext.temporarilyMovedArtifacts.length,3);
  const markerValue=JSON.parse(await readFile(path.join(run.root,input.auditContext.expectedMarker.relativePath),'utf8'));
  assert.equal(markerValue.state,'PENDING_AUDIT');
  assert.equal(markerValue.inventoryDigest,input.auditContext.expectedMarker.inventoryDigest);
  return v2.runProposalDeliberationSelfAudit(input);
 };
 const result=await successfulWithdrawal(run,{selfAudit});
 assert.ok(observed);
 assert.equal(result.auditStatus,'PASS');
});

test('Nth move, audit, and marker-finalization failures roll withdrawal back exactly',async()=>{
 for (const dependencies of [
  {fs:v2.createFaultInjectingLifecycleFs({failAtMove:7})},
  {selfAudit:async()=>({status:'FAIL',checks:[{id:'consistency',evidence:{status:'FAIL'}}]})},
  {beforeMarkerFinalize:()=>{throw new Error('INJECTED_MARKER_FINALIZATION_FAILURE');}},
 ]) {
  const run=await fixture();
  const before=await treeSnapshot(run.root);
  const result=await run.tx(dependencies).withdraw({filename:r02});
  assert.equal(result.status,'blocked',JSON.stringify(result));
  assert.deepEqual(await treeSnapshot(run.root),before);
  assert.equal(await v2.latestManagedFilename(run.root),r02);
  assert.equal((await v2.runConsistencyAudit({projectRoot:run.root})).status,'PASS');
  assert.equal((await v2.runProposalDeliberationSelfAudit({projectRoot:run.root})).status,'PASS');
  await assert.rejects(readFile(path.join(run.root,'.proposal-deliberation','withdrawn',operationId,'audit-marker.json')));
 }
});

test('exact restoration retains immutable quarantine data and completes marker-first audits',async()=>{
 const run=await fixture();
 const exact=await publicBytes(run.root);
 const withdrawal=await successfulWithdrawal(run);
 let observed;
 const restore=await run.tx({selfAudit:async input=>{
  observed=input.auditContext;
  const markerValue=JSON.parse(await readFile(path.join(run.root,input.auditContext.expectedMarker.relativePath),'utf8'));
  assert.equal(markerValue.state,'PENDING_AUDIT');
  assert.equal(input.auditContext.operationType,'RESTORE_WITHDRAWN_REVISION');
  assert.equal(input.auditContext.phase,'RESTORE_PUBLIC_ARTIFACTS_MOVED');
  assert.ok(input.auditContext.temporarilyMovedArtifacts.every(artifact=>artifact.expectedLocation==='public'));
  return v2.runProposalDeliberationSelfAudit(input);
 }}).restore({operationId});
 assert.equal(restore.status,'restored',JSON.stringify(restore));
 assert.deepEqual(Object.keys(restore).sort(),lifecycleResultKeys);
 assert.equal(restore.restoredLatestFilename,r02);
 assert.ok(observed);
 const restored=await publicBytes(run.root);
 assert.deepEqual(restored,exact);
 const directory=path.join(run.root,withdrawal.backupLocation);
 const metadata=JSON.parse(await readFile(path.join(directory,'metadata.json'),'utf8'));
 for (const artifact of metadata.artifacts) assert.equal(v2.sha256(await readFile(path.join(directory,artifact.quarantineRelativePath))),artifact.sha256);
 const markerValue=JSON.parse(await readFile(path.join(directory,'audit-marker.json'),'utf8'));
 assert.equal(markerValue.state,'COMMITTED');
 assert.equal(markerValue.operationType,'RESTORE_WITHDRAWN_REVISION');
 assert.equal(markerValue.auditStatus,'PASS');
 assert.equal(markerValue.selfAuditStatus,'PASS');
 assert.equal((await v2.runConsistencyAudit({projectRoot:run.root})).status,'PASS');
 assert.equal((await v2.runProposalDeliberationSelfAudit({projectRoot:run.root})).status,'PASS');
});

test('restore move, audit, and marker-finalization failures expose no partial public state and retain quarantine',async()=>{
 for (const dependencies of [
  {fs:v2.createFaultInjectingLifecycleFs({failAtMove:5})},
  {selfAudit:async()=>({status:'FAIL',checks:[{id:'consistency',evidence:{status:'FAIL'}}]})},
  {beforeMarkerFinalize:operation=>{if(operation==='RESTORE_WITHDRAWN_REVISION')throw new Error('INJECTED_RESTORE_FINALIZATION_FAILURE');}},
 ]) {
  const run=await fixture();
  await successfulWithdrawal(run);
  const before=await treeSnapshot(run.root);
  const result=await run.tx(dependencies).restore({operationId});
  assert.equal(result.status,'blocked',JSON.stringify(result));
  assert.deepEqual(await treeSnapshot(run.root),before);
  assert.equal(await v2.latestManagedFilename(run.root),r01);
  assert.equal((await v2.runConsistencyAudit({projectRoot:run.root})).status,'PASS');
  assert.equal((await v2.runProposalDeliberationSelfAudit({projectRoot:run.root})).status,'PASS');
 }
});

test('every restore rename failure rolls back exactly without touching unrelated quarantine files',async()=>{
 for (let failAtMove=1;failAtMove<=8;failAtMove++) {
  const run=await fixture();
  const withdrawal=await successfulWithdrawal(run);
  const operationDirectory=path.join(run.root,withdrawal.backupLocation);
  const markerPath=path.join(operationDirectory,'audit-marker.json');
  const markerValue=JSON.parse(await readFile(markerPath,'utf8'));
  await writeFile(markerPath,`\n${JSON.stringify(markerValue,null,2)}\n`);
  const unrelatedPath=path.join(operationDirectory,'unrelated.keep');
  await writeFile(unrelatedPath,Buffer.from([0,1,2,3,255]));
  const before=await treeSnapshot(run.root);
  const result=await run.tx({fs:v2.createFaultInjectingLifecycleFs({failAtMove})}).restore({operationId});
  assert.equal(result.status,'blocked',`move ${failAtMove}: ${JSON.stringify(result)}`);
  assert.match(result.warnings[0],/INJECTED_MOVE_FAILURE/,`move ${failAtMove}`);
  assert.deepEqual(await treeSnapshot(run.root),before,`move ${failAtMove}`);
  assert.deepEqual(await readFile(unrelatedPath),Buffer.from([0,1,2,3,255]));
  assert.equal(JSON.parse(await readFile(markerPath,'utf8')).state,'COMMITTED');
  assert.equal((await v2.runConsistencyAudit({projectRoot:run.root})).status,'PASS');
  assert.equal((await v2.runProposalDeliberationSelfAudit({projectRoot:run.root})).status,'PASS');
 }
});

test('restore rollback temporary cleanup is idempotent when a tracked temporary is already absent',async()=>{
 const run=await fixture();
 await successfulWithdrawal(run);
 const before=await treeSnapshot(run.root);
 const fs=v2.createFaultInjectingLifecycleFs({});
 const baseRename=fs.rename;
 let moves=0;
 fs.rename=async(source,destination)=>{
  moves++;
  if (moves===8) {
   await fs.rm(source,{force:true});
   throw new Error('INJECTED_MOVE_FAILURE_AFTER_TEMP_REMOVAL');
  }
  return baseRename(source,destination);
 };
 const result=await run.tx({fs}).restore({operationId});
 assert.equal(result.status,'blocked',JSON.stringify(result));
 assert.match(result.warnings[0],/INJECTED_MOVE_FAILURE_AFTER_TEMP_REMOVAL/);
 assert.deepEqual(await treeSnapshot(run.root),before);
});

test('restore rollback retains the original failure and reports owned-temporary cleanup failure secondarily',async()=>{
 const run=await fixture();
 const withdrawal=await successfulWithdrawal(run);
 const operationDirectory=path.join(run.root,withdrawal.backupLocation);
 const fs=v2.createFaultInjectingLifecycleFs({failAtMove:8});
 const baseRm=fs.rm;
 fs.rm=async(target,options)=>{
  if (path.basename(target).startsWith('audit-marker.json.')&&path.basename(target).endsWith('.tmp')) throw new Error('INJECTED_TEMP_CLEANUP_FAILURE');
  return baseRm(target,options);
 };
 const result=await run.tx({fs}).restore({operationId});
 assert.equal(result.status,'blocked',JSON.stringify(result));
 assert.match(result.warnings[0],/^RESTORE_FAILED:INJECTED_MOVE_FAILURE;/);
 assert.match(result.warnings[0],/RESTORE_ROLLBACK_INCOMPLETE:.*RESTORE_ROLLBACK_TEMP_CLEANUP_FAILED:audit-marker/);
 const files=Object.keys(await treeSnapshot(run.root));
 assert.equal(files.filter(name=>name.includes('audit-marker.json.')&&name.endsWith('.tmp')).length,1);
 assert.equal(JSON.parse(await readFile(path.join(operationDirectory,'audit-marker.json'),'utf8')).state,'COMMITTED');
 assert.equal(await v2.latestManagedFilename(run.root),r01);
});

test('restore can be retried after a successful exact rollback and ordinary audits remain available',async()=>{
 const run=await fixture();
 const exactPublic=await publicBytes(run.root);
 await successfulWithdrawal(run);
 const withdrawn=await treeSnapshot(run.root);
 const failed=await run.tx({fs:v2.createFaultInjectingLifecycleFs({failAtMove:8})}).restore({operationId});
 assert.equal(failed.status,'blocked',JSON.stringify(failed));
 assert.deepEqual(await treeSnapshot(run.root),withdrawn);
 assert.equal((await v2.runConsistencyAudit({projectRoot:run.root})).status,'PASS');
 assert.equal((await v2.runProposalDeliberationSelfAudit({projectRoot:run.root})).status,'PASS');
 const restored=await run.tx().restore({operationId});
 assert.equal(restored.status,'restored',JSON.stringify(restored));
 assert.deepEqual(await publicBytes(run.root),exactPublic);
 assert.equal((await v2.runConsistencyAudit({projectRoot:run.root})).status,'PASS');
 assert.equal((await v2.runProposalDeliberationSelfAudit({projectRoot:run.root})).status,'PASS');
});

test('pending lifecycle authorization fails closed for missing, mismatched, expired markers and orphan staging',async()=>{
 for (const mutate of [
  async (run,context)=>rm(path.join(run.root,context.expectedMarker.relativePath)),
  async (run,context)=>{const markerPath=path.join(run.root,context.expectedMarker.relativePath);const value=JSON.parse(await readFile(markerPath,'utf8'));value.inventoryDigest='0'.repeat(64);await writeJson(markerPath,value);},
 ]) {
  const run=await fixture();
  const result=await run.tx({selfAudit:async input=>{await mutate(run,input.auditContext);return v2.runProposalDeliberationSelfAudit(input);}}).withdraw({filename:r02});
  assert.equal(result.status,'blocked');
  assert.equal((await v2.runConsistencyAudit({projectRoot:run.root})).status,'PASS');
 }
 const expired=await fixture();
 const old=Date.now()-60_000;
 const result=await expired.tx({now:()=>new Date(old)}).withdraw({filename:r02});
 assert.equal(result.status,'blocked');
 assert.equal((await v2.runConsistencyAudit({projectRoot:expired.root})).status,'PASS');
 const orphan=await fixture();
 await mkdir(path.join(orphan.root,'.proposal-deliberation','withdrawn',`.staging-${operationId}`),{recursive:true});
 const audit=await v2.runConsistencyAudit({projectRoot:orphan.root});
 assert.equal(audit.status,'FAIL');
 assert.ok(audit.failures.some(failure=>failure.startsWith('ORPHAN_WITHDRAWAL_STAGING')));
});

test('productive tool preserves typed lifecycle operations, generates withdrawal identity, and restores a unique filename without an id',async()=>{
 const run=await fixture();
 const tool=await productiveTool(run.root);
 assert.ok(tool.parameters.properties.operation);
 assert.match(JSON.stringify(tool.parameters.properties.operation),/WITHDRAW_REVISION/);
 assert.match(JSON.stringify(tool.parameters.properties.operation),/RESTORE_WITHDRAWN_REVISION/);
 const response=await tool.execute('lifecycle-no-runtime',{instruction:'Elimina r02.',operation:'WITHDRAW_REVISION',sourceFilename:r02,withdrawalReason:'No longer current.'},undefined,undefined,{});
 assert.deepEqual(Object.keys(response.details).sort(),productiveLifecycleKeys);
 assert.equal(response.details.status,'withdrawn',JSON.stringify(response.details));
 assert.equal(response.details.operation,'WITHDRAW_REVISION');
 assert.equal(response.details.withdrawnFilename,r02);
 assert.equal(response.details.restoredLatestFilename,r01);
 assert.match(response.details.operationId,/^[0-9a-f]{8}-[0-9a-f-]{27}$/);
 assert.equal(response.details.backupLocation.split('/').at(-1),response.details.operationId);
 assert.equal(response.details.auditStatus,'PASS');
 assert.equal(response.details.selfAuditStatus,'PASS');
 assert.equal(response.details.modelCalls,0);
 assert.equal(response.details.plannerCalls,0);
 assert.doesNotMatch(JSON.stringify(response.details),/tutorCalls|reviewerCalls|documentSha|receipt|patch/);
 const restored=await tool.execute('lifecycle-restore-no-runtime',{instruction:'Restore the withdrawn managed revision.',operation:'RESTORE_WITHDRAWN_REVISION',sourceFilename:r02},undefined,undefined,{});
 assert.deepEqual(Object.keys(restored.details).sort(),productiveLifecycleKeys);
 assert.equal(restored.details.status,'restored',JSON.stringify(restored.details));
 assert.equal(restored.details.operation,'RESTORE_WITHDRAWN_REVISION');
 assert.equal(restored.details.operationId,response.details.operationId);
 assert.equal(restored.details.modelCalls,0);
 assert.equal(restored.details.plannerCalls,0);
 assert.doesNotMatch(JSON.stringify(restored.details),/tutorCalls|reviewerCalls|documentSha|receipt|patch/);
});

test('productive lifecycle language requests still classify directly without operation',async()=>{
 const run=await fixture();
 const tool=await productiveTool(run.root);
 const withdrawn=await tool.execute('lifecycle-language-withdraw',{instruction:`Retira la revisión administrada ${r02}.`},undefined,undefined,{});
 assert.equal(withdrawn.details.status,'withdrawn',JSON.stringify(withdrawn.details));
 assert.equal(withdrawn.details.operation,'WITHDRAW_REVISION');
 const restored=await tool.execute('lifecycle-language-restore',{instruction:`Restaura la revisión retirada ${withdrawn.details.operationId}.`},undefined,undefined,{});
 assert.equal(restored.details.status,'restored',JSON.stringify(restored.details));
 assert.equal(restored.details.operation,'RESTORE_WITHDRAWN_REVISION');
 assert.equal(restored.details.operationId,withdrawn.details.operationId);
});

test('productive lifecycle negatives block safely while ambiguous revision deletion clarifies and content deletion stays DELETE',async()=>{
 const base=await fixture();
 const baseTool=await productiveTool(base.root);
 const baseBlocked=await baseTool.execute('base',{instruction:'Withdraw the base revision.',operation:'WITHDRAW_REVISION',sourceFilename:r01},undefined,undefined,{});
 assert.equal(baseBlocked.details.status,'blocked');
 assert.match(baseBlocked.details.warnings[0],/BASE_REVISION_WITHDRAWAL_BLOCKED/);
 assert.equal(baseBlocked.details.modelCalls,0);
 assert.equal(baseBlocked.details.plannerCalls,0);

 const dependent=await fixture({r03:true});
 const dependentTool=await productiveTool(dependent.root);
 const dependentBlocked=await dependentTool.execute('dependent',{instruction:'Withdraw the managed revision.',operation:'WITHDRAW_REVISION',sourceFilename:r02},undefined,undefined,{});
 assert.equal(dependentBlocked.details.status,'blocked');
 assert.match(dependentBlocked.details.warnings[0],/LATER_DEPENDENT_REVISION_EXISTS/);

 const missing=await fixture();
 const missingTool=await productiveTool(missing.root);
 const missingBlocked=await missingTool.execute('missing',{instruction:'Withdraw the managed revision.',operation:'WITHDRAW_REVISION',sourceFilename:'research-concept-r99.md'},undefined,undefined,{});
 assert.equal(missingBlocked.details.status,'blocked');
 assert.match(missingBlocked.details.warnings[0],/MANAGED_DOCUMENT_MISSING/);

 const language=await fixture();
 const languageTool=await productiveTool(language.root);
 const ambiguous=await languageTool.execute('ambiguous',{instruction:'elimina r02'},undefined,undefined,{});
 assert.equal(ambiguous.details.status,'ambiguous',JSON.stringify(ambiguous.details));
 assert.equal(ambiguous.details.operation,'AMBIGUOUS');
 assert.match(ambiguous.details.message,/Name the exact fragment or scope/);
 const contentDelete=await languageTool.execute('content-delete',{instruction:'elimina esta sección',sourceFilename:r02},undefined,undefined,{});
 assert.equal(contentDelete.details.operation,'DELETE');
});

test('all lifecycle tests leave real repository proposal fixtures byte-identical',async()=>{
 assert.deepEqual(await treeSnapshot(path.join(repositoryRoot,'proposals')),repositoryProposalsBefore);
});
