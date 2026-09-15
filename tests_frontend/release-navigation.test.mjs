import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
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

test('filtered analysis keeps revision sources and later uses inside the selected task scope', async()=>{
 const { scopedRevisionEvidence }=await import('../src/dataAnalysisMath.ts');
 const revisions=[
  {sourcePairId:'FX09',graphChanged:true,subsequentUses:[{pairId:'FX10'},{pairId:'FX12'}]},
  {sourcePairId:'CX01',matchingChanged:true,subsequentUses:[{pairId:'CX02'}]},
 ];
 const scoped=scopedRevisionEvidence(revisions,[
  {pairId:'FX09',workpackId:'FX09'},
  {pairId:'FX10',workpackId:'FX10'},
 ]);
 assert.equal(scoped.length,1);
 assert.equal(scoped[0].sourcePairId,'FX09');
 assert.deepEqual(scoped[0].subsequentUses,[{pairId:'FX10'}]);
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

test('post-release maintenance is visibly isolated from current release KPI curves', async()=>{
 const { readFile }=await import('node:fs/promises');
 const source=await readFile(new URL('../src/DataAnalysis.tsx',import.meta.url),'utf8');
 assert.match(source,/发布后维护验证/);
 assert.match(source,/跨 runtime · 独立诊断/);
 assert.match(source,/不进入当前发布 KPI、累计曲线、成功率或收益/);
 assert.match(source,/不能作为正式收益率或普遍性能结论/);
 assert.match(source,/首个配置失败诊断与解释边界/);
});

test('formal cost claims remain gated while candidate observations stay dynamic', async()=>{
 const { attributionTimelineHeading, releaseAllowsCostClaims }=await import('../src/dataAnalysisMath.ts');
 assert.equal(attributionTimelineHeading(12),'12任务机会链与实际证据');
 assert.equal(releaseAllowsCostClaims('candidate',true),false);
 assert.equal(releaseAllowsCostClaims('historical',true),true);
 assert.equal(releaseAllowsCostClaims('formal',false),false);
 assert.equal(releaseAllowsCostClaims('formal',true),true);
 const source=await readFile(new URL('../src/DataAnalysis.tsx',import.meta.url),'utf8');
 assert.match(source,/create_reconciliation: "首次创建订单复核经验"/);
 assert.match(source,/extension_threshold_rebind: "扩展任务阈值重绑"/);
});

test('analysis explains execution decisions and shows the fixed-scope candidate observation', async()=>{
 const { readFile }=await import('node:fs/promises');
 const source=await readFile(new URL('../src/DataAnalysis.tsx',import.meta.url),'utf8');
 for(const label of ['模型决策请求分解','读取选择','计算选择','混合决策','报告组合']) assert.match(source,new RegExp(label));
 assert.match(source,/四类合计只覆盖 execute 阶段/);
 assert.match(source,/在线 RSI 在本组质量更高/);
 assert.match(source,/累计效率变化/);
 assert.match(source,/在线 RSI 在当前固定范围全部通过/);
 assert.match(source,/不代表跨场景普遍收益/);
 assert.doesNotMatch(source,/<dt>实验 ID<\/dt>/);
 assert.doesNotMatch(source,/<dt>Runtime<\/dt>/);
 assert.doesNotMatch(source,/模型成本估算价格快照/);
 assert.doesNotMatch(source,/质量受限/);
 assert.doesNotMatch(source,/质量门槛未通过/);
});


test('current attribution evidence normalizes stored arms and presents RSI quality leadership', async()=>{
 const { normalizeEvidenceArms, armLabel }=await import('../src/releaseEvidence.ts');
 const normalized=normalizeEvidenceArms({summary:{arms:{
  no_learning:{attempts:12,passed:11,inputTokens:20,outputTokens:2,modelRequests:3,toolCalls:4,toolErrors:1,durationMs:10,usageComplete:true},
  online_rsi:{attempts:12,passed:12,inputTokens:10,outputTokens:1,modelRequests:2,toolCalls:3,toolErrors:0,durationMs:8,usageComplete:true},
 }}});
 assert.equal(normalized.summary.arms.baseline.passed,11);
 assert.equal(normalized.summary.arms.rsi.passed,12);
 assert.equal(armLabel.baseline,'图执行 · 不学习');
 assert.equal(armLabel.rsi,'图执行 · 在线 RSI');
 const evidence=await readFile(new URL('../src/CurrentEvidence.tsx',import.meta.url),'utf8');
 assert.match(evidence,/当前候选证据 · 在线 RSI 质量领先/);
 assert.match(evidence,/真实 API 对照已完成/);
 assert.match(evidence,/当前候选状态表示仍需扩大场景和补充独立审核/);
 assert.match(evidence,/本组累计净 token 减少/);
 assert.match(evidence,/不代表跨场景普遍收益/);
 assert.match(evidence,/查看修订来源任务 · \{r\.sourcePairId\}/);
 assert.match(evidence,/查看修订后实际使用 · \{u\.pairId\}/);
 assert.doesNotMatch(evidence,/当前候选证据 · 质量受限/);
 const analysis=await readFile(new URL('../src/DataAnalysis.tsx',import.meta.url),'utf8');
 assert.match(analysis,/在线 RSI 在本组质量更高/);
 assert.match(analysis,/累计效率变化/);
 assert.doesNotMatch(analysis,/当前候选结果已完成，质量门槛未通过/);
});


test('scope cost claims require equal passed quality and complete usage', async()=>{
 const { scopeAllowsCostClaims }=await import('../src/dataAnalysisMath.ts');
 const comparable=[
  {baseline:{passed:true,usageComplete:true},rsi:{passed:true,usageComplete:true}},
  {baseline:{passed:true,usageComplete:true},rsi:{passed:true,usageComplete:true}},
 ];
 assert.equal(scopeAllowsCostClaims(comparable,true,false),true);
 assert.equal(scopeAllowsCostClaims(comparable,false,true),true);
 assert.equal(scopeAllowsCostClaims(comparable,false,false),false);
 const qualityUnequal=[...comparable,{baseline:{passed:false,usageComplete:true},rsi:{passed:true,usageComplete:true}}];
 assert.equal(scopeAllowsCostClaims(qualityUnequal,true,true),false);
 const usageIncomplete=[...comparable,{baseline:{passed:true,usageComplete:false},rsi:{passed:true,usageComplete:true}}];
 assert.equal(scopeAllowsCostClaims(usageIncomplete,true,true),false);
});

test('analysis uses stable cohort ids and avoids fixed experiment counts', async()=>{
 const source=await readFile(new URL('../src/DataAnalysis.tsx',import.meta.url),'utf8');
 assert.match(source,/cohortId:\s*asString\(row\.cohortId\)/);
 assert.match(source,/asString\(spec\.cohort\)/);
 assert.match(source,/\(point\.cohortId \|\| point\.workflowType\) === workflow/);
 assert.match(source,/setWorkflow\(cohort\.cohortId\)/);
 assert.match(source,/scenarioNames\[cohortScenario\]/);
 assert.match(source,/cohort\.pairIds\.length/);
 assert.doesNotMatch(source,/全量十二任务/);
 assert.doesNotMatch(source,/双方都通过的 11 项/);
 assert.doesNotMatch(source,/正式六任务/);
});

test('filtered graph wording separates version selection from strict graph execution', async()=>{
 const source=await readFile(new URL('../src/DataAnalysis.tsx',import.meta.url),'utf8');
 assert.match(source,/版本选择不等于严格图执行/);
 assert.match(source,/记录选择 G .*严格图执行见真实轨迹/);
 assert.doesNotMatch(source,/当前筛选有 .*项记录使用历史版本，严格图执行状态/);
});


test('timeline highlights only auditable G or M revisions and marks later validation', async()=>{
 const { revisionIsAuditable, revisionVisualState }=await import('../src/dataAnalysisMath.ts');
 const revisions=[
  {sourcePairId:'F03',sourceRunId:'run-f03',graphChanged:true,graphDiff:[{op:'add',node:'n2'}],subsequentUses:[{pairId:'F04',runId:'run-f04'}]},
  {sourcePairId:'C03',sourceRunId:'run-c03',matchingChanged:true,matchingDiff:[{before:'a',after:'b'}],subsequentUses:[{pairId:'C04',runId:'run-c04'}]},
  {sourcePairId:'T03',sourceRunId:'run-t03',graphChanged:true,graphDiff:[],subsequentUses:[{pairId:'T04'}]},
  {sourcePairId:'G0',graphChanged:true,graphDiff:[{op:'create'}],subsequentUses:[{pairId:'G1'}]},
  {sourcePairId:'N03',sourceRunId:'run-n03',graphChanged:true,graphDiff:[{op:'add'}],subsequentUses:[{pairId:'N04'}]},
 ];
 assert.equal(revisionIsAuditable(revisions[0],'graph'),true);
 assert.equal(revisionIsAuditable(revisions[2],'graph'),false);
 assert.equal(revisionIsAuditable(revisions[3],'graph'),false);
 const graphSource=revisionVisualState({pairId:'F03',workpackId:'F03'},revisions);
 assert.deepEqual(graphSource,{graphRevision:true,matchingRevision:false,verifiedLaterUse:true,usesGraphRevision:false,usesMatchingRevision:false});
 const graphUse=revisionVisualState({pairId:'F04',workpackId:'F04'},revisions);
 assert.equal(graphUse.usesGraphRevision,true);
 const matchingSource=revisionVisualState({pairId:'C03',workpackId:'C03'},revisions);
 assert.equal(matchingSource.matchingRevision,true);
 assert.equal(matchingSource.verifiedLaterUse,true);
 assert.equal(revisionVisualState({pairId:'T03',workpackId:'T03'},revisions).graphRevision,false);
 assert.equal(revisionVisualState({pairId:'G0',workpackId:'G0'},revisions).graphRevision,false);
 assert.equal(revisionVisualState({pairId:'N03',workpackId:'N03'},revisions).verifiedLaterUse,false);
 assert.equal(revisionVisualState({pairId:'N04',workpackId:'N04'},revisions).usesGraphRevision,false);
 const source=await readFile(new URL('../src/DataAnalysis.tsx',import.meta.url),'utf8');
 const css=await readFile(new URL('../src/data-analysis.css',import.meta.url),'utf8');
 assert.match(source,/graph-evolution/);
 assert.match(source,/matching-evolution/);
 assert.match(source,/verified-use/);
 assert.match(source,/已验证使用/);
 assert.match(css,/li\.graph-evolution/);
 assert.match(css,/li\.matching-evolution/);
 assert.match(css,/graph-evolution\.matching-evolution/);
 assert.match(css,/li\.verified-use/);
 assert.match(css,/path-badge\.graph-revision/);
 assert.match(css,/path-badge\.matching-revision/);
});

test('saved-result replay reveals only a bounded task prefix', async()=>{
 const { replayPrefix }=await import('../src/dataAnalysisMath.ts');
 const points=[{index:1},{index:2},{index:3}];
 assert.deepEqual(replayPrefix(points,null),points);
 assert.deepEqual(replayPrefix(points,1),[{index:1}]);
 assert.deepEqual(replayPrefix(points,2),[{index:1},{index:2}]);
 assert.deepEqual(replayPrefix(points,99),points);
 assert.deepEqual(replayPrefix(points,-1),[]);
});

test('memory activation is highlighted on the first later task that reuses the created version', async()=>{
 const { firstMemoryReuseIndex }=await import('../src/dataAnalysisMath.ts');
 const chain=[
  {index:1,workpackId:'FX01',generatedVersionIds:['g0'],generatedMatchVersions:[0]},
  {index:2,workpackId:'FX02',usedVersionId:'g0',usedMatchVersion:0},
  {index:3,workpackId:'FX03',usedVersionId:'g0',usedMatchVersion:0},
 ];
 assert.equal(firstMemoryReuseIndex(chain),2);
 assert.equal(firstMemoryReuseIndex(chain.slice(0,1)),null);
 assert.equal(firstMemoryReuseIndex([
  chain[0],
  {index:2,workpackId:'FX02',usedVersionId:'other',usedMatchVersion:9},
 ]),null);
});

test('analysis replays saved evidence without presenting it as a live model run', async()=>{
 const source=await readFile(new URL('../src/DataAnalysis.tsx',import.meta.url),'utf8');
 const css=await readFile(new URL('../src/data-analysis.css',import.meta.url),'utf8');
 for(const label of ['保存结果回放','播放保存结果','暂停回放','重播保存结果','回放速度','最终结果']) {
  assert.match(source,new RegExp(label));
 }
 assert.match(source,/不会重新调用模型/);
 assert.match(source,/replayPrefix\(visible, replayCount\)/);
 assert.match(source,/scopedRevisionEvidence\(revisions, replayVisible\)/);
 assert.match(source,/cumulativePoints\(replayVisible\)/);
 assert.match(source,/window\.clearTimeout\(timer\)/);
 assert.match(source,/memory-activated/);
 assert.match(source,/记忆已构建 · 首次复用/);
 assert.doesNotMatch(source,/initialCreation/);
 assert.doesNotMatch(source,/initial-creation/);
 assert.match(css,/li\.memory-activated/);
 assert.match(css,/analysis-replay/);
 assert.doesNotMatch(css,/initial-creation/);
});
