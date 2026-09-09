import json
import os
from urllib.parse import quote, urlsplit
import httpx
from .domain import ROOT, now
from .tools import Tool, object_schema
from .autotool import acquire_tools


class JsonConnector:
    def __init__(self, base_url, headers, transport=None):
        url = urlsplit(base_url)
        if url.scheme not in ['http', 'https'] or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Invalid platform HTTP(S) base URL')
        self.base_url, self.headers, self.transport = base_url.rstrip('/'), headers, transport

    async def get(self, path, query):
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False, transport=self.transport) as client:
                async with client.stream('GET', self.base_url + '/' + path.lstrip('/'), params=query, headers={'Accept': 'application/json', **self.headers}) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f'Platform API HTTP {response.status_code}; check permissions and URL')
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 2000000:
                            raise ValueError('Platform response too large; reduce page size')
                        chunks.append(chunk)
                    try:
                        return json.loads(b''.join(chunks))
                    except (ValueError, UnicodeError):
                        raise ValueError('Platform returned non-JSON content') from None
        except httpx.HTTPError:
            raise RuntimeError('Platform network request failed') from None


def observe(value, resource, context):
    is_list = isinstance(value, list)
    rows = value if is_list else [value]
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Platform resource must be an object')
        native = row.get('name', row.get('id')) if context.run['request']['source'] == 'erpnext' else row.get('id', row.get('name'))
        if native is None:
            result.append(row)
        else:
            ref = f'{resource}:{native}'
            context.evidence.add(ref)
            result.append(dict(row, _evidenceRef=ref))
    return result if is_list else result[0]


def external_report():
    text = {'type': 'string', 'minLength': 1, 'maxLength': 3000}
    schema = object_schema({'title': {'type': 'string', 'minLength': 1, 'maxLength': 100}, 'summary': text,
                            'findings': {'type': 'array', 'minItems': 1, 'maxItems': 30, 'items': text},
                            'evidenceIds': {'type': 'array', 'minItems': 1, 'maxItems': 100, 'items': {'type': 'string', 'minLength': 1, 'maxLength': 250}}})
    def publish(args, context):
        if not set(args['evidenceIds']).issubset(context.evidence):
            raise ValueError('Report cites a resource that has not been observed')
        report = dict(title=args['title'], summary=args['summary'], findings=args['findings'], source=context.run['request']['source'], createdAt=now(),
                      metrics=[{'label': '已引用资源', 'value': str(len(args['evidenceIds']))}, {'label': '平台写入', 'value': '0', 'note': '当前外部连接仅提供读取工具'}],
                      columns=['来源', '资源 ID'], rows=[[context.run['request']['source'], ref] for ref in args['evidenceIds']])
        context.run['report'] = report
        return report
    return Tool('publish_report', '基于实际 API 观察生成只读简报；evidenceIds 使用返回的 _evidenceRef，不能宣称已修改平台数据。', 'artifact', schema, publish)


PAGE = {'type': 'integer', 'minimum': 1, 'maximum': 1000}
SIZE = {'type': 'integer', 'minimum': 1, 'maximum': 50}


def platform_tools(source, client=None):
    if source not in ['erpnext', 'zammad']:
        raise ValueError('Unknown platform')
    if client is None:
        base = os.getenv(source.upper() + '_BASE_URL')
        if source == 'erpnext':
            key, secret = os.getenv('ERPNEXT_API_KEY'), os.getenv('ERPNEXT_API_SECRET')
            if not all([base, key, secret]):
                raise ValueError('ERPNext connector is not configured')
            headers = {'Authorization': f'token {key}:{secret}'}
        else:
            token = os.getenv('ZAMMAD_API_TOKEN')
            if not base or not token:
                raise ValueError('Zammad connector is not configured')
            headers = {'Authorization': f'Token token={token}'}
        client = JsonConnector(base, headers)
    spec = json.loads((ROOT / 'specs' / f'{source}.openapi.json').read_text())
    async def transport(path, query):
        return await client.get(path, dict(query, expand='true') if source == 'zammad' else query)
    tools = acquire_tools(spec, transport, observe)
    if source == 'erpnext':
        async def read_list(doctype, fields, filters, args, context):
            payload = await client.get('/api/resource/' + quote(doctype), {'fields': json.dumps(fields), 'filters': json.dumps(filters),
                'limit_start': str((args['page'] - 1) * args['pageSize']), 'limit_page_length': str(args['pageSize']), 'order_by': 'name asc'})
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                raise ValueError('Invalid ERPNext list response')
            return {'doctype': doctype, 'records': observe(payload['data'], doctype, context), 'page': args['page'], 'pageSize': args['pageSize'],
                    'mayHaveMore': len(payload['data']) == args['pageSize'], 'note': 'Native ERPNext amounts and currencies; do not assume cents. Cite _evidenceRef.'}
        async def invoices(args, context):
            return await read_list('Sales Invoice', ['name', 'customer', 'customer_name', 'currency', 'grand_total', 'outstanding_amount', 'due_date', 'posting_date'],
                                   [['docstatus', '=', 1]] + ([['outstanding_amount', '>', 0]] if args['status'] == 'outstanding' else []), args, context)
        async def payments(args, context):
            return await read_list('Payment Entry', ['name', 'party', 'party_name', 'paid_amount', 'received_amount', 'unallocated_amount', 'paid_from_account_currency', 'paid_to_account_currency', 'reference_no', 'posting_date'],
                                   [['docstatus', '=', 1], ['payment_type', '=', 'Receive'], ['party_type', '=', 'Customer']], args, context)
        tools[:0] = [Tool('erpnext_list_invoices', '分页读取已提交销售发票，保留平台原生金额和币种。', 'read', object_schema({'status': {'enum': ['outstanding', 'all'], 'type': 'string'}, 'page': PAGE, 'pageSize': SIZE}), invoices),
                     Tool('erpnext_list_payments', '分页读取已提交客户收款。金额字段币种语义不同，汇总前读取详情。', 'read', object_schema({'page': PAGE, 'pageSize': SIZE}), payments)]
    else:
        async def tickets(args, context):
            rows = await client.get('/api/v1/tickets', {'page': str(args['page']), 'per_page': str(args['pageSize']), 'expand': 'true'})
            if not isinstance(rows, list):
                raise ValueError('Invalid Zammad list response')
            return {'records': observe(rows, 'tickets', context), 'page': args['page'], 'pageSize': args['pageSize'], 'mayHaveMore': len(rows) == args['pageSize'], 'scope': 'tickets visible to configured API user'}
        tools.insert(0, Tool('zammad_list_tickets', '分页读取 token 可见工单。状态和优先级 ID 需查字典解释。', 'read', object_schema({'page': PAGE, 'pageSize': SIZE}), tickets))
    return tools + [external_report()]
