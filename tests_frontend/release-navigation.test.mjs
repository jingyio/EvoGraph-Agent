import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalHash, legacyPages } from '../src/navigation.ts';
import { verifyRelease, measure, savingMeasure } from '../src/releaseEvidence.ts';

test('every old entry enters archive and keeps task/run query',()=>{
 for(const page of legacyPages) assert.equal(canonicalHash(`#${page}?task=t1&left=r1`),`#archive?page=${page}&task=t1&left=r1`);
 assert.equal(canonicalHash(''),'#home');assert.equal(canonicalHash('#employees'),'#home');
 assert.equal(canonicalHash('#analysis?dataset=v17'),'#analysis?dataset=v17');
 assert.equal(canonicalHash('#evidence?view=replay'),'#analysis?view=replay');
});
test('a response from a different release/runtime/asset fails closed',()=>{
 const r={releaseId:'current',experimentId:'one',runtimeRevision:'sha256:a',assetVersion:'v2',status:'candidate',protocol:{limits:{run:1}}};
 verifyRelease(r,{...r});
 for(const key of Object.keys(r))assert.throws(()=>verifyRelease(r,{...r,[key]:'other'}));
});
test('curves retain failure and do not treat unknown usage as zero',()=>{
 const r={status:'limited',evaluation:{status:'failed'},metrics:{inputTokens:100,outputTokens:10,usageComplete:true,modelRequests:2,durationMs:30}};
 assert.equal(measure(r,'success'),0);assert.equal(measure(r,'tokens'),110);
 assert.equal(measure({...r,metrics:{...r.metrics,usageComplete:false}},'tokens'),null);
 assert.equal(measure(undefined,'tokens'),null);
 const point={tokenSaving:null,latencySaving:-0.2,cumulativeTokenSaving:null,cumulativeLatencySaving:0.1};
 assert.equal(savingMeasure(point,'tokenSaving'),null);
 assert.equal(savingMeasure(point,'latencySaving'),-0.2);
});

test('filtered cumulative curves keep unknown usage and latency as gaps', async()=>{
 const { cumulativePoints }=await import('../src/dataAnalysisMath.ts');
 const rows=cumulativePoints([
  {baseline:{tokens:100,durationMs:1000},rsi:{tokens:50,durationMs:800}},
  {baseline:{tokens:null,durationMs:900},rsi:{tokens:40,durationMs:null}},
  {baseline:{tokens:100,durationMs:1000},rsi:{tokens:50,durationMs:700}},
 ]);
 assert.equal(rows[0].baselineCumulativeTokens,100);
 assert.equal(rows[0].tokenSavingRate,.5);
 assert.equal(rows[1].baselineCumulativeTokens,null);
 assert.equal(rows[1].rsiCumulativeTokens,90);
 assert.equal(rows[1].baselineCumulativeLatency,1900);
 assert.equal(rows[1].rsiCumulativeLatency,null);
 assert.equal(rows[2].baselineCumulativeTokens,null);
 assert.equal(rows[2].latencySavingRate,null);
});

test('learning evidence distinguishes creation, material revision and later use', async()=>{
 const { evolutionSignals }=await import('../src/dataAnalysisMath.ts');
 const revisions=[{
  sourcePairId:'pair-3',graphChanged:true,matchingChanged:false,
  subsequentUses:[{pairId:'pair-4',runId:'run-4'}],
 }];
 const created=evolutionSignals({pairId:'pair-1',workpackId:'task-1',generatedVersionIds:['g0'],generatedMatchVersions:[0]},revisions);
 assert.equal(created.createdGraph,true);
 assert.equal(created.createdMatching,true);
 assert.equal(created.graphRevision,false);
 assert.equal(created.usedGraphRevision,false);
 const revised=evolutionSignals({pairId:'pair-3',workpackId:'task-3',generatedVersionIds:['g1']},revisions);
 assert.equal(revised.graphRevision,true);
 assert.equal(revised.usedGraphRevision,false);
 const reused=evolutionSignals({pairId:'pair-4',workpackId:'task-4',usedVersionId:'g1'},revisions);
 assert.equal(reused.usedGraph,true);
 assert.equal(reused.usedGraphRevision,true);
 assert.equal(reused.usedMatchingRevision,false);
});

test('an explicit empty revision list remains empty and G0 creation is not a revision',async()=>{
 const { normalizedRevisionEvidence }=await import('../src/dataAnalysisMath.ts');
 assert.deepEqual(normalizedRevisionEvidence([], [{spec:{id:'FA01'},experienceAfter:{onlineRsiVersions:[
  {id:'g0',generation:0,parentGraphId:null,patches:[{before:[],after:['node']}],matchPatches:[{before:null,after:{purpose:'x'}}]},
 ]}}]),[]);
 assert.deepEqual(normalizedRevisionEvidence(undefined, [{spec:{id:'FA01'},experienceAfter:{onlineRsiVersions:[
  {id:'g0',generation:0,parentGraphId:null,patches:[{before:[],after:['node']}],matchPatches:[{before:null,after:{purpose:'x'}}]},
 ]}}]),[]);
 const revisions=normalizedRevisionEvidence(undefined, [{spec:{id:'FA03'},experienceAfter:{onlineRsiVersions:[
  {id:'g1',generation:1,parentGraphId:'g0',patches:[{before:['a'],after:['a','b']}],matchPatches:[]},
 ]}}]);
 assert.equal(revisions.length,1);
 assert.equal(revisions[0].graphChanged,true);
});

test('cumulative model calls and task accuracy keep failures in the denominator', async()=>{
 const { cumulativePoints }=await import('../src/dataAnalysisMath.ts');
 const rows=cumulativePoints([
  {baseline:{tokens:100,durationMs:1000,modelRequests:4,passed:true},rsi:{tokens:50,durationMs:800,modelRequests:2,passed:true}},
  {baseline:{tokens:100,durationMs:1000,modelRequests:3,passed:false},rsi:{tokens:50,durationMs:700,modelRequests:2,passed:true}},
 ]);
 assert.equal(rows[1].baselineCumulativeRequests,7);
 assert.equal(rows[1].rsiCumulativeRequests,4);
 assert.equal(rows[1].requestSavingRate,3/7);
 assert.equal(rows[1].baselineCumulativeAccuracy,.5);
 assert.equal(rows[1].rsiCumulativeAccuracy,1);
});

test('unknown model calls or unassessed outcomes remain gaps', async()=>{
 const { cumulativePoints }=await import('../src/dataAnalysisMath.ts');
 const rows=cumulativePoints([
  {baseline:{tokens:100,durationMs:1000,modelRequests:4,passed:true},rsi:{tokens:50,durationMs:800,modelRequests:2,passed:true}},
  {baseline:{tokens:100,durationMs:1000,modelRequests:null,passed:true},rsi:{tokens:50,durationMs:700,modelRequests:2,passed:true}},
  {baseline:{tokens:100,durationMs:1000,modelRequests:3,passed:true},rsi:{tokens:50,durationMs:700,modelRequests:2}},
 ]);
 assert.equal(rows[1].baselineCumulativeRequests,null);
 assert.equal(rows[2].rsiCumulativeRequests,6);
 assert.equal(rows[2].baselineCumulativeAccuracy,1);
 assert.equal(rows[2].rsiCumulativeAccuracy,null);
});

test('M-only changes are revisions and loaded versions count as use only after graph execution',async()=>{
 const { normalizedRevisionEvidence }=await import('../src/dataAnalysisMath.ts');
 const pairs=[
  {spec:{id:'FA02'},experienceAfter:{onlineRsiVersions:[{
   id:'g0',generation:0,matchVersion:1,parentGraphId:null,patches:[{before:[],after:['read']}],
   matchPatches:[{before:{threshold:8},after:{threshold:10}}],
  }]}},
  {spec:{id:'FA03'},online_rsi:{id:'loaded-only',evolution:{usedVersionId:'g0'},toolTrace:[]}},
  {spec:{id:'FA04'},online_rsi:{id:'executed',evolution:{usedVersionId:'g0'},toolTrace:[{executor:'graph',ok:true}]}}
 ];
 const revisions=normalizedRevisionEvidence(undefined,pairs);
 assert.equal(revisions.length,1);
 assert.equal(revisions[0].graphChanged,false);
 assert.equal(revisions[0].matchingChanged,true);
 assert.deepEqual(revisions[0].subsequentUses,[{pairId:'FA04',taskId:'FA04',runId:'executed'}]);
});

test('cumulative model cost keeps a per-arm unknown value as a gap', async()=>{
 const { cumulativePoints }=await import('../src/dataAnalysisMath.ts');
 const rows=cumulativePoints([
  {baseline:{tokens:100,costUsd:.02,durationMs:1000},rsi:{tokens:50,costUsd:.01,durationMs:700}},
  {baseline:{tokens:100,costUsd:.02,durationMs:900},rsi:{tokens:50,costUsd:null,durationMs:600}},
  {baseline:{tokens:100,costUsd:.02,durationMs:800},rsi:{tokens:50,costUsd:.01,durationMs:500}},
 ]);
 assert.equal(rows[0].baselineCumulativeCostUsd,.02);
 assert.equal(rows[0].rsiCumulativeCostUsd,.01);
 assert.equal(rows[0].costSavingRate,.5);
 assert.equal(rows[1].baselineCumulativeCostUsd,.04);
 assert.equal(rows[1].rsiCumulativeCostUsd,null);
 assert.equal(rows[2].rsiCumulativeCostUsd,null);
 assert.equal(rows[2].costSavingRate,null);
});
