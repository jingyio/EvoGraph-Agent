import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../src/WorkspaceWorkbench.tsx', import.meta.url), 'utf8');
const css = await readFile(new URL('../src/workspace.css', import.meta.url), 'utf8');

test('one confirmed action creates the native paired comparison', () => {
  assert.match(source, /\/api\/workspaces\/tasks\/\$\{readyTask\.id\}\/comparison-runs/);
  assert.match(source, /body: JSON\.stringify\(\{ confirmCost: true \}\)/);
  assert.match(source, /开始双轨对照/);
  assert.match(source, /我确认启动 2 次真实 Agent 运行/);
  assert.match(source, /两个 run 与模型请求并行/);
  assert.match(source, /qwen\/qwen3\.5-27b · 主 Key \/ Secondary Key 各承载一臂/);
  assert.doesNotMatch(source, /rsiStartTask/);
  assert.doesNotMatch(source, /startRsiRun/);
  assert.doesNotMatch(source, /awaitingRsi/);
  assert.doesNotMatch(source, /rsiStarting/);
  assert.doesNotMatch(source, /strategy: 'plan_react', confirmCost: true/);
  assert.doesNotMatch(source, /strategy: 'graph_rsi', confirmCost: true/);
});

test('both lanes use one comparison poll and expose real events metrics and reports', () => {
  assert.match(source, /api<WorkspaceComparison>\(`\/api\/workspaces\/comparison-runs\/\$\{comparison\.id\}`\)/);
  assert.match(source, /window\.setInterval\(\(\) => void poll\(\), 800\)/);
  assert.doesNotMatch(source, /activeArms\.map\(async \(\[arm, run\]\)/);
  assert.match(source, /传统 Agent/);
  assert.match(source, /在线 RSI Agent/);
  assert.match(source, /主 Key 与 Secondary Key 并行执行/);
  assert.match(source, /executionPolicy: 'strict_serial' \| 'parallel_dual_key'/);
  for (const label of ['LLM 请求', 'Token', '工具调用', '串行耗时', '最终业务报告']) assert.match(source, new RegExp(label));
  assert.match(source, /learningEnabled: arm\.learningEnabled \?\? arm\.runDetail\?\.learningEnabled/);
  assert.match(source, /学习写入状态未返回/);
  assert.match(source, /后端未返回报告/);
  assert.match(source, /后端未返回下载地址/);
  assert.match(source, /页面只展示后端保存的状态、事件、用量与报告/);
  assert.doesNotMatch(source, /Math\.random/);
  assert.doesNotMatch(source, /模拟进度/);
});


test('last workspace restores silently without a visible continuation section', () => {
  assert.match(source, /COMPARISON_STORAGE_KEY = 'rsi-workspace-comparisons-v1'/);
  assert.match(source, /LAST_WORKSPACE_STORAGE_KEY = 'rsi-last-workspace-v1'/);
  assert.match(source, /current\[workspaceId\] = \{ comparisonId: comparison\.id, taskId: comparison\.taskId \}/);
  assert.match(source, /rememberComparison\(workspace\.id, result\)/);
  assert.match(source, /rememberComparison\(workspace\.id, current\)/);
  assert.match(source, /window\.localStorage\.getItem\(LAST_WORKSPACE_STORAGE_KEY\)/);
  assert.match(source, /if \(lastWorkspace\) void activateWorkspace\(lastWorkspace\)/);
  assert.match(source, /restoreComparison\(item\.id, item\)/);
  assert.match(source, /api<WorkspaceComparison>\(`\/api\/workspaces\/comparison-runs\/\$\{saved\.comparisonId\}`\)/);
  assert.doesNotMatch(source, /if \(!\['queued', 'running'\]\.includes\(restored\.status\)\) return/);
  assert.doesNotMatch(source, /继续之前的工作/);
  assert.doesNotMatch(source, /继续追问/);
  assert.doesNotMatch(source, /准备双轨追问/);
});

test('long task text grows to its real scroll height and mobile lanes stack', () => {
  assert.match(source, /requestArea\.current/);
  assert.match(source, /area\.style\.height = 'auto'/);
  assert.match(source, /Math\.max\(122, area\.scrollHeight\)/);
  assert.match(css, /workspace-request textarea\{[^}]*overflow-y:hidden[^}]*height:auto/);
  assert.match(css, /@media\(max-width:1120px\)\{\.workspace-agent-grid\{grid-template-columns:1fr\}/);
  assert.match(css, /@media\(max-width:420px\)/);
});


test('history can be cleared persistently without deleting audit artifacts', () => {
  assert.match(source, /HISTORY_CUTOFF_STORAGE_KEY = 'rsi-workspace-history-cutoff-v1'/);
  assert.match(source, /function clearHistory\(\)/);
  assert.match(source, /cutoffs\[workspace\.id\] = cutoff/);
  assert.match(source, /delete comparisons\[workspace\.id\]/);
  assert.match(source, /setRuns\(\[\]\)/);
  assert.match(source, /history\.runs\.filter\(run => run\.createdAt > cutoff\)/);
  assert.match(source, /清空历史记录/);
  const clearBlock = source.slice(source.indexOf('function clearHistory'), source.indexOf('async function openRun'));
  assert.doesNotMatch(clearBlock, /api</);
});

test('the whole data preview is collapsed by default and can be expanded', () => {
  assert.match(source, /<details className="workspace-data workspace-data-collapsible"><summary>/);
  assert.doesNotMatch(source, /<details className="workspace-data workspace-data-collapsible" open/);
  assert.match(css, /workspace-data-collapsible\[open\]>summary:before/);
  assert.match(css, /workspace-data-body/);
});
