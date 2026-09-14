import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalHash, legacyPages } from '../src/navigation.ts';
import { verifyRelease, measure, savingMeasure } from '../src/releaseEvidence.ts';

test('every old entry enters archive and keeps task/run query',()=>{
 for(const page of legacyPages) assert.equal(canonicalHash(`#${page}?task=t1&left=r1`),`#archive?page=${page}&task=t1&left=r1`);
 assert.equal(canonicalHash(''),'#home');assert.equal(canonicalHash('#employees'),'#home');
 assert.equal(canonicalHash('#evidence?view=replay'),'#evidence?view=replay');
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
