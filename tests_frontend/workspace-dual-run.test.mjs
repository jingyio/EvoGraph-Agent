import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../src/WorkspaceWorkbench.tsx', import.meta.url), 'utf8');
const css = await readFile(new URL('../src/workspace.css', import.meta.url), 'utf8');

test('one confirmed action creates the native three-arm comparison', () => {
  assert.match(source, /\/api\/workspaces\/tasks\/\$\{readyTask\.id\}\/comparison-runs/);
  assert.match(source, /body: JSON\.stringify\(\{ confirmCost: true \}\)/);
  assert.match(source, /运行三臂对照/);
  assert.match(source, /确认 3 次真实运行及模型费用/);
  assert.doesNotMatch(source, /workspace-dual-protocol/);
  assert.doesNotMatch(source, /rsiStartTask/);
  assert.doesNotMatch(source, /startRsiRun/);
  assert.doesNotMatch(source, /awaitingRsi/);
  assert.doesNotMatch(source, /rsiStarting/);
  assert.doesNotMatch(source, /strategy: 'plan_react', confirmCost: true/);
  assert.doesNotMatch(source, /strategy: 'graph_rsi', confirmCost: true/);
});

test('three lanes use one comparison poll and expose real events metrics and reports', () => {
  assert.match(source, /api<WorkspaceComparison>\(`\/api\/workspaces\/comparison-runs\/\$\{comparison\.id\}`\)/);
  assert.match(source, /window\.setInterval\(\(\) => void poll\(\), 800\)/);
  assert.doesNotMatch(source, /activeArms\.map\(async \(\[arm, run\]\)/);
  assert.match(source, /图执行 · 不学习/);
  assert.match(source, /图执行 · 在线 RSI/);
  assert.match(source, /三种 Agent 实测对比/);
  assert.match(source, /aria-label="传统规划、图执行不学习与在线 RSI 方法差异"/);
  assert.match(source, /传统 Plan \+ ReAct/);
  assert.match(source, /模型逐步规划并执行/);
  assert.match(source, /每次重新规划，不读取经验/);
  assert.match(source, /复用冻结经验，按当前资料重算/);
  assert.match(source, /<b>A → B<\/b> 图运行时与编译方式的差异/);
  assert.match(source, /<b>B → C<\/b> 跨任务学习的净贡献/);
  assert.match(source, /executionPolicy: 'strict_serial' \| 'parallel_dual_key' \| 'parallel_three_arm_two_key'/);
  assert.match(source, /design\?: 'plan_react_graph_learning_three_arm'/);
  assert.match(source, /knowledgeBase\?: \{ releaseId\?: string; datasetId\?: string; versionCount\?: number; readOnly\?: boolean \}/);
  assert.match(source, /comparisonArm\(comparison, 'plan_react'\)/);
  assert.match(source, /comparisonArm\(comparison, 'no_learning'\)/);
  assert.match(source, /comparisonArm\(comparison, 'online_rsi'\)/);
  for (const label of ['LLM 请求', 'Token', '工具调用', '串行耗时', '最终业务报告']) assert.match(source, new RegExp(label));
  assert.match(source, /learningEnabled: arm\.learningEnabled \?\? arm\.runDetail\?\.learningEnabled/);
  assert.match(source, /读取冻结经验，不写入/);
  assert.match(source, /后端未返回报告/);
  assert.match(source, /后端未返回下载地址/);
  assert.match(source, /只按后端真实事件更新/);
  assert.doesNotMatch(source, /Math\.random/);
  assert.doesNotMatch(source, /模拟进度/);
});

test('digital employee is fixed to finance and the paired arms state the learning difference', () => {
  assert.match(source, /const FINANCE_CAPABILITY = \{ key: 'finance' as const, label: '财务运营'/);
  assert.match(source, /role: FINANCE_CAPABILITY\.key, label: `\$\{FINANCE_CAPABILITY\.label\}工作区`/);
  assert.match(source, /item\.id === lastWorkspaceId && item\.role === FINANCE_CAPABILITY\.key/);
  assert.match(source, /aria-label="当前业务能力"/);
  assert.match(source, /当前演示固定能力/);
  assert.doesNotMatch(source, /workspace-role-picker/);
  assert.doesNotMatch(source, /客服运营/);
  assert.doesNotMatch(source, /技术工单/);
  assert.doesNotMatch(source, /role === 'support'/);
  assert.doesNotMatch(source, /role === 'tickets'/);
  assert.match(source, /<h3>\{laneName\(arm\)\}<\/h3>/);
  assert.match(css, /\.workspace-agent-lane\{--lane-accent:#60758f;--lane-soft:#f3f6f9/);
  assert.match(css, /\.workspace-agent-lane\.rsi\{--lane-accent:#6b4cc5;--lane-secondary:#07836e;--lane-soft:#f2f8f6/);
  assert.match(css, /\.workspace-agent-lane\.rsi \.workspace-lane-report\{border-top-color:#07836e\}/);
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
  assert.doesNotMatch(source, /准备双轨追问|无法恢复已保存的双轨执行/);
});

test('long task text grows to its real scroll height and mobile lanes stack', () => {
  assert.match(source, /requestArea\.current/);
  assert.match(source, /area\.style\.height = 'auto'/);
  assert.match(source, /Math\.max\(122, area\.scrollHeight\)/);
  assert.match(css, /workspace-request textarea\{[^}]*overflow-y:hidden[^}]*height:auto/);
  assert.match(css, /@media\(max-width:1180px\)\{\.workspace-agent-grid\{grid-template-columns:1fr\}/);
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


test('paired comparison spans the workspace width and shows the full task once', () => {
  const layoutIndex = source.indexOf('<section className="workspace-layout">');
  const historyIndex = source.indexOf('<aside className="workspace-history">', layoutIndex);
  const comparisonIndex = source.indexOf('<section className="workspace-comparison workspace-comparison-wide">', layoutIndex);
  assert.ok(layoutIndex >= 0 && historyIndex > layoutIndex && comparisonIndex > historyIndex);
  assert.match(source, /className="workspace-comparison-task" aria-label="本次完整问题"/);
  assert.match(source, /readyTask\?\.task \|\| request \|\| '当前历史任务未返回完整题面。'/);
  assert.match(css, /\.workspace-shell\{max-width:1720px/);
  assert.match(css, /grid-template-columns:minmax\(190px,220px\) minmax\(0,1fr\) minmax\(190px,220px\)/);
  assert.match(css, /\.workspace-comparison-task p\{[^}]*white-space:pre-wrap[^}]*overflow-wrap:anywhere/);
});

test('protocol details stay in a collapsed experiment note instead of the presentation layer', () => {
  assert.match(source, /<details className="workspace-experiment-notes">/);
  assert.doesNotMatch(source, /<details className="workspace-experiment-notes" open/);
  const notesStart = source.indexOf('<details className="workspace-experiment-notes">');
  const notesEnd = source.indexOf('</details>', notesStart);
  const notes = source.slice(notesStart, notesEnd);
  assert.match(notes, /主 Key 承载 A\/B，Secondary Key 承载 C/);
  assert.match(notes, /knowledgeBase\.versionCount/);
  assert.match(notes, /knowledgeBase\.releaseId/);
  assert.match(notes, /阶段计时/);
  assert.match(css, /\.workspace-experiment-notes>summary/);
});

test('live execution uses transient Apple-style stage notifications with real values', () => {
  assert.match(source, /function WorkspaceLiveOverlay/);
  assert.match(source, /function LiveStageNotification/);
  assert.match(source, /className="workspace-live-overlay" role="status" aria-live="polite"/);
  assert.match(source, /planRun=\{planRun\} traditionalRun=\{traditionalRun\} rsiRun=\{rsiRun\} active=\{active\}/);
  assert.match(source, /run\?\.events\.at\(-1\)/);
  assert.match(source, /activeInThisView = useRef\(false\)/);
  assert.match(source, /const mayAnnounce = active \|\| activeInThisView\.current/);
  assert.match(source, /active=\{active && activeRun\(planRun\)\}/);
  assert.match(source, /active=\{active && activeRun\(traditionalRun\)\}/);
  assert.match(source, /active=\{active && activeRun\(rsiRun\)\}/);
  assert.match(source, /if \(!active\) activeInThisView\.current = false/);
  assert.match(source, /notificationEventTitle\(event, id\)/);
  assert.match(source, /if \(event\.type === 'action'\) return toolLabel\(event\.title\)/);
  assert.match(source, /eventStageFacts\(event, shownRun\)/);
  assert.match(source, /输入 token/);
  assert.match(source, /当前阈值/);
  assert.match(source, /记录数量/);
  assert.match(source, /新经验版本/);
  assert.match(source, /window\.setTimeout\(\(\) => \{/);
  assert.match(source, /\}, 3100\)/);
  assert.match(source, /window\.clearTimeout\(timer\)/);
  assert.match(source, /function WorkspaceStageBoard/);
  assert.match(source, /已持续 \$\{formatMs\(waitingMs\)\}/);
  assert.match(source, /只按后端真实事件更新/);
  assert.doesNotMatch(source, /启动后显示真实模型、图执行、工具与报告阶段/);
  assert.match(source, /<details className="workspace-event-history">/);
  assert.doesNotMatch(source, /<details className="workspace-event-history" open/);
  assert.match(css, /\.workspace-live-overlay\{position:fixed;top:82px;right:24px/);
  assert.match(css, /backdrop-filter:blur\(28px\) saturate\(180%\)/);
  assert.match(css, /@keyframes workspace-notification-cycle/);
  assert.match(css, /@keyframes workspace-notification-progress/);
  assert.match(css, /\.workspace-event-history>summary/);
});
