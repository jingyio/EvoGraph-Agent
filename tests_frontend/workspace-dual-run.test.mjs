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
  assert.match(source, /后端同时登记两臂，并按严格串行策略执行/);
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
  for (const label of ['LLM 请求', 'Token', '工具调用', '串行耗时', '最终业务报告']) assert.match(source, new RegExp(label));
  assert.match(source, /学习写入状态未返回/);
  assert.match(source, /后端未返回报告/);
  assert.match(source, /后端未返回下载地址/);
  assert.match(source, /页面只展示后端保存的状态、事件、用量与报告/);
  assert.doesNotMatch(source, /Math\.random/);
  assert.doesNotMatch(source, /模拟进度/);
});

test('long task text grows to its real scroll height and mobile lanes stack', () => {
  assert.match(source, /requestArea\.current/);
  assert.match(source, /area\.style\.height = 'auto'/);
  assert.match(source, /Math\.max\(122, area\.scrollHeight\)/);
  assert.match(css, /workspace-request textarea\{[^}]*overflow-y:hidden[^}]*height:auto/);
  assert.match(css, /@media\(max-width:1120px\)\{\.workspace-agent-grid\{grid-template-columns:1fr\}/);
  assert.match(css, /@media\(max-width:420px\)/);
});
