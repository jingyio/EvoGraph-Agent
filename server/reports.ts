import type { AgentRun, DataSource, Report, Scenario, World } from '../shared/types.js';

export const money = (cents: number) => `¥${(cents / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export function invoiceBalance(world: World, id: string): number {
  const invoice = world.invoices.find(item => item.id === id);
  if (!invoice) throw new Error(`Invoice not found: ${id}`);
  return invoice.amountCents - world.allocations.filter(item => item.invoiceId === id).reduce((sum, item) => sum + item.amountCents, 0);
}
export function paymentBalance(world: World, id: string): number {
  const payment = world.payments.find(item => item.id === id);
  if (!payment) throw new Error(`Payment not found: ${id}`);
  return payment.amountCents - world.allocations.filter(item => item.paymentId === id).reduce((sum, item) => sum + item.amountCents, 0);
}
export function makeReport(scenario: Scenario, world: World, summary: string, source: DataSource = 'sandbox'): Report {
  if (scenario === 'finance') {
    const total = world.invoices.reduce((sum, item) => sum + item.amountCents, 0);
    const allocated = world.allocations.reduce((sum, item) => sum + item.amountCents, 0);
    const open = world.invoices.filter(item => invoiceBalance(world, item.id) > 0);
    return {
      title: '回款核对 · 运营简报', summary, source, createdAt: new Date().toISOString(),
      metrics: [{ label: '应收原始金额', value: money(total) }, { label: '已分配回款', value: money(allocated), note: '沙箱匹配，不代表新增回款' }, { label: '剩余应收', value: money(total - allocated) }, { label: '已登记异常', value: String(world.cases.length) }],
      columns: ['发票', '客户', '原始金额', '已分配', '剩余应收', '状态'],
      rows: world.invoices.map(item => [item.id, item.customer, money(item.amountCents), money(item.amountCents - invoiceBalance(world, item.id)), money(invoiceBalance(world, item.id)), invoiceBalance(world, item.id) === 0 ? '已匹配' : item.dueDate < world.asOf.slice(0, 10) ? '逾期未结清' : '未结清']),
      findings: [...world.cases.map(item => `${item.id} · ${item.summary} [${item.evidenceIds.join(', ')}]`), `共有 ${open.length} 张发票尚未结清。异常金额不等同于已确认损失；重复流水记录不合并计作新增回款。`],
    };
  }
  const active = world.tickets.filter(item => item.status !== 'closed');
  const overdue = active.filter(item => Date.parse(item.dueAt) < Date.parse(world.asOf));
  return {
    title: '工单巡检 · 服务简报', summary, source, createdAt: new Date().toISOString(),
    metrics: [{ label: '未关闭工单', value: String(active.length) }, { label: '已分派', value: String(active.filter(item => item.ownerId).length) }, { label: 'SLA 已超时', value: String(overdue.length), note: '分派后仍然计为超时' }, { label: '回复草稿', value: String(world.drafts.length), note: '已保存，未发送' }],
    columns: ['工单', '主题', '优先级', '负责人', 'SLA', '草稿'],
    rows: active.map(item => [item.id, item.subject, item.priority, world.agents.find(agent => agent.id === item.ownerId)?.name || '待分派', Date.parse(item.dueAt) < Date.parse(world.asOf) ? '已超时' : '时限内', world.drafts.some(draft => draft.ticketId === item.id) ? '已保存' : '未生成']),
    findings: [...world.escalations.map(item => `${item.ticketId} · ${item.reason}`), `当前 ${overdue.length} 个工单超时；分派和回复草稿不代表问题已经解决。`],
  };
}

function cell(text: string) { return text.replaceAll('|', '\\|').replaceAll('\n', ' '); }
export function reportMarkdown(run: AgentRun): string {
  const report = run.report;
  const graphNote = run.graph ? `\n\n任务图：${run.graph.status}；图执行工具调用：${run.graph.toolCalls}；完成节点：${run.graph.completedNodes}；来源运行：${run.graph.sourceRunId || '冷启动'}。学习读取调用：${run.graph.learning?.toolCalls ?? 0}（单列，未计入执行工具调用）；学习耗时：${run.graph.learning ? run.graph.learning.compileMs + run.graph.learning.durationMs : 0} ms。` : '';
  const thinkingNote = run.modelSettings ? `；enable_thinking=${run.modelSettings.enableThinking}；供应商返回 reasoning token 合计=${run.metrics.reasoningTokens ?? '未知'}` : '';
  const header = `# ${report?.title || 'Agent 执行记录'}\n\n运行：${run.id}\n\n模式：${run.request.mode === 'fixture' ? '离线固定流程示例（没有调用 LLM）' : run.request.strategy === 'graph' ? '真实模型 Graph RSI' : '真实模型 ReAct'}；数据源：${run.request.source}；状态：${run.status}${thinkingNote}${graphNote}\n\n`;
  if (!report) return header + (run.finalText || run.error || '未生成报告。');
  return header + report.summary + '\n\n' + report.metrics.map(item => `- ${item.label}：${item.value}${item.note ? `（${item.note}）` : ''}`).join('\n') + '\n\n' +
    `| ${report.columns.map(cell).join(' | ')} |\n| ${report.columns.map(() => '---').join(' | ')} |\n` + report.rows.map(row => `| ${row.map(cell).join(' | ')} |`).join('\n') + '\n\n' + report.findings.map(item => `- ${item}`).join('\n') +
    `\n\nLLM 请求：${run.metrics.modelRequests}；输入 token：${run.metrics.inputTokens ?? '未提供'}；输出 token：${run.metrics.outputTokens ?? '未提供'}；token 统计完整：${run.metrics.usageComplete ? '是' : '否'}；耗时：${run.metrics.durationMs} ms。\n`;
}
