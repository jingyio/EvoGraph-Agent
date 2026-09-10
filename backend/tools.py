from copy import deepcopy
from dataclasses import dataclass, field
import inspect
import json
from typing import Callable, Any
from jsonschema import Draft7Validator
from .domain import ROOT, active_tickets, clock, invoice_balance, payment_balance, preview_match, record, overdue_invoices, make_report


@dataclass
class ToolContext:
    run: dict
    evidence: set = field(default_factory=set)


@dataclass
class Tool:
    name: str
    description: str
    effect: str
    parameters: dict
    handler: Callable
    origin: Any = None
    outputs: Any = None

    def __post_init__(self):
        Draft7Validator.check_schema(self.parameters)
        self.validator = Draft7Validator(self.parameters)

    def card(self):
        value = {'name': self.name, 'description': self.description, 'effect': self.effect, 'parameters': self.parameters}
        if self.origin:
            value['origin'] = self.origin
        if self.outputs:
            value['outputs'] = list(self.outputs)
        return deepcopy(value)

    async def execute(self, args, context):
        errors = sorted(self.validator.iter_errors(args), key=lambda error: str(list(error.path)))
        if errors:
            # Do not echo attacker-controlled record values or server secrets.
            raise ValueError('; '.join(f"{'.'.join(map(str, e.path)) or 'arguments'}: schema {e.validator} validation failed" for e in errors[:5]))
        result = self.handler(args, context)
        if inspect.isawaitable(result):
            result = await result
        return deepcopy(result)


def object_schema(properties=None, required=None):
    return {'type': 'object', 'properties': properties or {}, 'required': list(properties or {}) if required is None else required, 'additionalProperties': False}


def sandbox_tools(scenario):
    cards = json.loads((ROOT / 'specs' / f'sandbox-{scenario}.tools.json').read_text())

    def execute(name, args, context):
        run, world = context.run, context.run['state']
        if name == 'get_business_clock':
            return {'asOf': world['asOf']}
        if name == 'publish_report':
            run['report'] = make_report(run, args['summary'])
            return run['report']
        if name == 'list_invoices':
            return [dict(item, outstandingCents=invoice_balance(world, item['id'])) for item in world['invoices']]
        if name == 'list_payments':
            return [dict(item, unallocatedCents=payment_balance(world, item['id'])) for item in world['payments']]
        if name == 'get_invoice':
            return dict(record(world['invoices'], args['invoiceId']), outstandingCents=invoice_balance(world, args['invoiceId']))
        if name == 'preview_payment_match':
            return preview_match(world, args['paymentId'])
        if name == 'list_overdue_invoices':
            return overdue_invoices(world)
        if name == 'allocate_payment':
            payment = record(world['payments'], args['paymentId'])
            allocations = args['allocations']
            if len({a['invoiceId'] for a in allocations}) != len(allocations):
                raise ValueError('Duplicate invoice IDs in allocation batch')
            existing = [a for a in world['allocations'] if a['paymentId'] == payment['id']]
            if len(existing) == len(allocations) and all(any(old['invoiceId'] == a['invoiceId'] and old['amountCents'] == a['amountCents'] for old in existing) for a in allocations):
                return {'status': 'already_applied', 'allocations': existing}
            if sum(p['bankRef'] == payment['bankRef'] for p in world['payments']) > 1:
                raise ValueError('Duplicate bank reference: investigate before allocating')
            total = 0
            for a in allocations:
                invoice = record(world['invoices'], a['invoiceId'])
                if invoice['customerId'] != payment['customerId'] or invoice['currency'] != payment['currency'] or invoice['id'] not in payment['invoiceRefs']:
                    raise ValueError('Customer, currency or invoice reference mismatch')
                if a['amountCents'] > invoice_balance(world, invoice['id']):
                    raise ValueError('Allocation exceeds invoice outstanding balance')
                total += a['amountCents']
            if total > payment_balance(world, payment['id']) or total > 9007199254740991:
                raise ValueError('Allocation exceeds payment balance')
            world['allocations'].extend(dict(a, paymentId=payment['id']) for a in allocations)
            return {'status': 'applied_in_sandbox', 'allocations': allocations, 'remainingCents': payment_balance(world, payment['id'])}
        if name == 'create_finance_case':
            all_ids = {i['id'] for i in world['invoices'] + world['payments']}
            if args['entityId'] not in all_ids or not set(args['evidenceIds']).issubset(all_ids) or args['entityId'] not in args['evidenceIds']:
                raise ValueError('Case must cite existing invoice/payment records including its entity')
            if args['kind'] == 'duplicate':
                payment = record(world['payments'], args['entityId'])
                peers = [p for p in world['payments'] if p['bankRef'] == payment['bankRef']]
                if len(peers) < 2 or any(p['id'] not in args['evidenceIds'] for p in peers):
                    raise ValueError('Duplicate case requires all matching bank-reference records')
            elif args['kind'] == 'overdue':
                if not any(i['id'] == args['entityId'] for i in overdue_invoices(world)):
                    raise ValueError('Invoice is not overdue and outstanding')
            else:
                preview = preview_match(world, args['entityId'])
                if preview['eligible'] or payment_balance(world, args['entityId']) <= 0 or preview['reason'] == 'duplicate_bank_reference':
                    raise ValueError('Payment is not an unmatched exception')
            existing = next((c for c in world['cases'] if c['kind'] == args['kind'] and c['entityId'] == args['entityId']), None)
            if existing:
                return existing
            case = dict(args, id=f"CASE-{len(world['cases']) + 1:03d}")
            world['cases'].append(case)
            return case
        if name == 'list_tickets':
            return world['tickets'] if args['scope'] == 'all' else active_tickets(world)
        if name == 'get_ticket':
            return record(world['tickets'], args['ticketId'])
        if name == 'get_sla_risks':
            return [{'ticketId': t['id'], 'overdue': clock(t['dueAt']) < clock(world['asOf']), 'priority': t['priority']}
                    for t in active_tickets(world) if clock(t['dueAt']) < clock(world['asOf']) or t['priority'] == 'urgent']
        if name == 'list_agents':
            return [dict(a, activeCount=sum(t['ownerId'] == a['id'] for t in active_tickets(world))) for a in world['agents']]
        if name == 'assign_ticket':
            ticket, agent = record(world['tickets'], args['ticketId']), record(world['agents'], args['agentId'])
            if ticket['status'] == 'closed':
                raise ValueError('Closed tickets cannot be assigned')
            if ticket['ownerId'] == agent['id']:
                return {'status': 'already_assigned', 'ticket': ticket}
            if ticket['version'] != args['expectedVersion']:
                raise ValueError('Version conflict: read the ticket again')
            if not agent['available'] or ticket['category'] not in agent['skills']:
                raise ValueError('Agent unavailable or missing required skill')
            if sum(t['ownerId'] == agent['id'] for t in active_tickets(world)) >= agent['capacity']:
                raise ValueError('Agent has no remaining capacity')
            ticket['ownerId'], ticket['version'] = agent['id'], ticket['version'] + 1
            return {'status': 'assigned_in_sandbox', 'ticket': ticket}
        if name == 'search_knowledge':
            items = [dict(k, score=sum(char in k['title'] for char in set(args['query']))) for k in world['knowledge'] if k['category'] == args['category']]
            return sorted(items, key=lambda k: -k['score'])
        if name == 'save_reply_draft':
            ticket = record(world['tickets'], args['ticketId'])
            if ticket['status'] == 'closed':
                raise ValueError('Cannot draft for closed ticket')
            if any(record(world['knowledge'], article)['category'] != ticket['category'] for article in args['articleIds']):
                raise ValueError('Knowledge article category mismatch')
            draft = dict(args, sent=False)
            index = next((i for i, d in enumerate(world['drafts']) if d['ticketId'] == ticket['id']), None)
            if index is None:
                world['drafts'].append(draft)
            else:
                world['drafts'][index] = draft
            return {'status': 'draft_saved_not_sent', 'draft': draft}
        if name == 'escalate_ticket':
            if record(world['tickets'], args['ticketId'])['status'] == 'closed':
                raise ValueError('Cannot escalate closed ticket')
            existing = next((e for e in world['escalations'] if e['ticketId'] == args['ticketId']), None)
            if existing:
                return existing
            world['escalations'].append(dict(args))
            return args
        raise ValueError('Unknown tool')

    return [Tool(card['name'], card['description'], card['effect'], card['parameters'],
                 lambda args, context, name=card['name']: execute(name, args, context)) for card in cards]
