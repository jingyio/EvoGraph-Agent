import { z } from 'zod';
import type { DataSource } from '../shared/types.js';
import { defineTool, externalReportTool, type Tool, type ToolContext } from './tools.js';
import { acquireTools, type ApiSpec } from './autotool.js';
import erpSpec from '../specs/erpnext.openapi.json';
import zammadSpec from '../specs/zammad.openapi.json';

export interface ConnectorSettings { baseUrl: string; headers: Record<string, string>; timeoutMs?: number }
export class JsonConnector {
  constructor(private settings: ConnectorSettings) {
    const url = new URL(settings.baseUrl);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('Platform base URL must be HTTP(S), without credentials or query');
  }
  async get(path: string, query: Record<string, string>, signal: AbortSignal): Promise<unknown> {
    const url = new URL(`${this.settings.baseUrl.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`);
    for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
    const response = await fetch(url, { method: 'GET', redirect: 'error', headers: { Accept: 'application/json', ...this.settings.headers }, signal: AbortSignal.any([signal, AbortSignal.timeout(this.settings.timeoutMs || 15000)]) });
    if (!response.ok) throw new Error(`Platform API HTTP ${response.status} (${path.split('/').slice(0, 4).join('/')}); check URL, credentials and resource permissions`);
    if (Number(response.headers.get('content-length') || 0) > 2_000_000) throw new Error('Platform response too large; reduce page size');
    const body = await response.text();
    if (body.length > 2_000_000) throw new Error('Platform response too large; reduce page size');
    try { return JSON.parse(body); } catch { throw new Error('Platform returned non-JSON content; check the API base URL'); }
  }
}
const rowsSchema = z.array(z.record(z.unknown()));
const page = z.number().int().min(1).max(1000);
const size = z.number().int().min(1).max(50);
function observe(rows: Record<string, unknown>[], context: ToolContext, resourceType: string) {
  return rows.map(row => {
    const nativeId = context.run.request.source === 'erpnext' ? row.name ?? row.id : row.id ?? row.name;
    if (nativeId == null) return row;
    const reference = `${resourceType}:${String(nativeId)}`;
    context.evidence.add(reference);
    return { ...row, _evidenceRef: reference };
  });
}
export function erpnextTools(client: JsonConnector): Tool[] {
  async function list(doctype: string, fields: string[], filters: unknown[], pageNumber: number, pageSize: number, context: ToolContext) {
    const payload = await client.get(`/api/resource/${encodeURIComponent(doctype)}`, { fields: JSON.stringify(fields), filters: JSON.stringify(filters), limit_start: String((pageNumber - 1) * pageSize), limit_page_length: String(pageSize), order_by: 'name asc' }, context.signal);
    const result = z.object({ data: rowsSchema }).parse(payload);
    return { doctype, records: observe(result.data, context, doctype), page: pageNumber, pageSize, mayHaveMore: result.data.length === pageSize, note: 'Amounts retain native ERPNext field names and currency; do not assume cents or add different currencies. Cite the client-added _evidenceRef in reports.' };
  }
  const acquired = acquireTools(erpSpec as ApiSpec, (path, query, signal) => client.get(path, query, signal), (value, resource, context) => observe([z.record(z.unknown()).parse(value)], context, resource)[0]);
  return [
    defineTool('erpnext_list_invoices', '分页读取已提交的销售发票。status=outstanding 仅取剩余应收大于零；金额保持平台原生单位，并附币种。', 'read', { status: z.enum(['outstanding', 'all']), page, pageSize: size }, (args, context) => list('Sales Invoice', ['name', 'customer', 'customer_name', 'currency', 'grand_total', 'outstanding_amount', 'due_date', 'posting_date'], [['docstatus', '=', 1], ...(args.status === 'outstanding' ? [['outstanding_amount', '>', 0]] : [])], args.page, args.pageSize, context)),
    defineTool('erpnext_list_payments', '分页读取已提交的客户收款 Payment Entry。paid_amount、received_amount 和 unallocated_amount 的币种语义不同，汇总前须读取详情。', 'read', { page, pageSize: size }, (args, context) => list('Payment Entry', ['name', 'party', 'party_name', 'paid_amount', 'received_amount', 'unallocated_amount', 'paid_from_account_currency', 'paid_to_account_currency', 'reference_no', 'posting_date'], [['docstatus', '=', 1], ['payment_type', '=', 'Receive'], ['party_type', '=', 'Customer']], args.page, args.pageSize, context)),
    ...acquired,
    externalReportTool(),
  ];
}
export function zammadTools(client: JsonConnector): Tool[] {
  async function list(path: string, query: Record<string, string>, context: ToolContext) { return observe(rowsSchema.parse(await client.get(path, query, context.signal)), context, path.split('/')[3]); }
  return [
    defineTool('zammad_list_tickets', '分页读取当前 token 可见的工单；权限影响可见范围。保留原生状态/优先级 ID，需查询字典解释。', 'read', { page, pageSize: size }, async (args, context) => {
      const records = await list('/api/v1/tickets', { page: String(args.page), per_page: String(args.pageSize), expand: 'true' }, context);
      return { records, page: args.page, pageSize: args.pageSize, mayHaveMore: records.length === args.pageSize, scope: 'tickets visible to the configured API user', note: 'Cite the client-added _evidenceRef in reports.' };
    }),
    ...acquireTools(zammadSpec as ApiSpec, (path, query, signal) => client.get(path, { ...query, expand: 'true' }, signal), (value, resource, context) => Array.isArray(value) ? observe(rowsSchema.parse(value), context, resource) : observe([z.record(z.unknown()).parse(value)], context, resource)[0]),
    externalReportTool(),
  ];
}
export function platformTools(source: Exclude<DataSource, 'sandbox'>): Tool[] {
  if (source === 'erpnext') {
    const { ERPNEXT_BASE_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET } = process.env;
    if (!ERPNEXT_BASE_URL || !ERPNEXT_API_KEY || !ERPNEXT_API_SECRET) throw new Error('ERPNext connector is not configured');
    return erpnextTools(new JsonConnector({ baseUrl: ERPNEXT_BASE_URL, headers: { Authorization: `token ${ERPNEXT_API_KEY}:${ERPNEXT_API_SECRET}` } }));
  }
  const { ZAMMAD_BASE_URL, ZAMMAD_API_TOKEN } = process.env;
  if (!ZAMMAD_BASE_URL || !ZAMMAD_API_TOKEN) throw new Error('Zammad connector is not configured');
  return zammadTools(new JsonConnector({ baseUrl: ZAMMAD_BASE_URL, headers: { Authorization: `Token token=${ZAMMAD_API_TOKEN}` } }));
}
