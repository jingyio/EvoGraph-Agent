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
 assert.equal(rows[1].rsiCumulativeLatency,null);
 assert.equal(rows[2].baselineCumulativeTokens,null);
 assert.equal(rows[2].latencySavingRate,null);
});
