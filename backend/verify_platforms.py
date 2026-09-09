"""Explicit integration check against the isolated RSI deployment, not arbitrary production data."""
import asyncio
import json
import os
import httpx
from .config import ARTIFACTS
from .connectors import platform_tools
from .domain import now
from .graph_store import write_private
from .runtime import create_run
from .tools import ToolContext


async def verify(source):
    base = os.getenv(source.upper() + '_BASE_URL')
    assert base == 'http://127.0.0.1:' + ('18080' if source == 'erpnext' else '18081'), 'Expected isolated experiment tunnel'
    tools = {t.name: t for t in platform_tools(source)}
    context = ToolContext(create_run({'scenario': 'finance' if source == 'erpnext' else 'support', 'mode': 'live', 'source': source, 'task': 'Platform validation'}))
    async def call(name, **args):
        return await tools[name].execute(args, context)
    rows = []
    for page in range(1, 6):
        data = await call('erpnext_list_invoices' if source == 'erpnext' else 'zammad_list_tickets', **({'status': 'all'} if source == 'erpnext' else {}), page=page, pageSize=2)
        rows.extend(data['records'])
        if not data['mayHaveMore']:
            break
    assert len(rows) == len({r.get('id', r.get('name')) for r in rows}) == 6
    if source == 'erpnext':
        assert all(r['name'].startswith('RSI-INV-') and r['currency'] == 'CNY' for r in rows)
        assert sum(r['grand_total'] for r in rows) == 66500
        assert sum(r['outstanding_amount'] for r in rows) == 24500
        payments = (await call('erpnext_list_payments', page=1, pageSize=50))['records']
        assert len(payments) == 6
        assert sum(p['reference_no'] == 'RSI-BANK-1004' for p in payments) == 2
        payment = await call('erpnext_get_payment', paymentId='RSI-PAY-002')
        assert payment['references'][0]['reference_name'] == 'RSI-INV-002' and payment['references'][0]['allocated_amount'] == 5000
        invoice = await call('erpnext_get_invoice', invoiceId='RSI-INV-002')
        assert invoice['outstanding_amount'] == 3500
        customer = await call('erpnext_get_customer', customerId=invoice['customer'])
        headers = {'Authorization': f"token {os.environ['ERPNEXT_API_KEY']}:{os.environ['ERPNEXT_API_SECRET']}"}
        path, body = '/api/resource/Customer/' + customer['name'], {'customer_name': customer['customer_name']}
        details = {'invoices': 6, 'payments': 6, 'outstandingCny': 24500, 'partialReferencesVerified': True}
    else:
        assert all(r['title'].startswith('[RSI-') for r in rows)
        states = await call('zammad_list_states')
        await call('zammad_list_priorities')
        closed = next(s['id'] for s in states if s['name'] == 'closed')
        assert sum(r['state_id'] != closed for r in rows) == 5
        ticket = await call('zammad_get_ticket', ticketId=rows[0]['id'])
        assert ticket['first_response_escalation_at']
        assert await call('zammad_get_ticket_articles', ticketId=ticket['id'])
        headers = {'Authorization': 'Token token=' + os.environ['ZAMMAD_API_TOKEN']}
        path, body = '/api/v1/tickets/' + str(ticket['id']), {'title': ticket['title']}
        async with httpx.AsyncClient(trust_env=False) as client:
            assert (await client.get(base + '/api/v1/tickets/1', headers=headers)).status_code == 403
        details = {'tickets': 6, 'activeTickets': 5, 'slaVerified': True, 'defaultGroupDenied': True}
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.put(base + path, headers=headers, json=body)
        assert response.status_code == 403, 'Reader must not be able to update platform state'
    return {'platform': source, 'status': 'passed', 'writeStatus': 403, 'pageSize': 2, 'evidenceReferences': len(context.evidence), **details}


async def main():
    results = await asyncio.gather(verify('erpnext'), verify('zammad'))
    report = {'verifiedAt': now(), 'backend': 'python', 'results': results}
    write_private(ARTIFACTS / 'platform-deployment' / 'python-verification.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
