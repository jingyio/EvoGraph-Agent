"""Run inside the isolated ERPNext backend, using its Python environment.

Creates only RSI-prefixed synthetic records. Credentials go to a private file;
stdout contains counts and business totals, never passwords or API secrets.
"""
import json
import os
import secrets

import frappe

os.chdir('/home/frappe/frappe-bench/sites')
frappe.init(site='frontend', sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()
frappe.set_user('Administrator')

COMPANY = 'RSI Demo Company'
USER = 'rsi-reader@example.invalid'
OUTPUT = '/home/frappe/frappe-bench/sites/private-rsi-connection.json'


def insert_once(doctype, name, values, submit=False):
    if frappe.db.exists(doctype, name):
        return frappe.get_doc(doctype, name)
    document = frappe.get_doc(dict(doctype=doctype, **values))
    document.insert(ignore_permissions=True, set_name=name)
    if submit:
        document.submit()
    return document


def main():
    from erpnext.setup.setup_wizard.setup_wizard import setup_complete
    existing_companies = frappe.get_all('Company', pluck='name')
    if existing_companies and COMPANY not in existing_companies:
        raise RuntimeError('Refusing to seed a site with a non-RSI company')
    if not frappe.db.exists('Company', COMPANY):
        setup_complete(frappe._dict(company_name=COMPANY, company_abbr='RSI', country='China', currency='CNY', fy_start_date='2026-01-01', fy_end_date='2026-12-31', chart_of_accounts='Standard', domain='Services', bank_name='RSI Test Bank', bank_account='RSI Test Bank', language='en'))
    frappe.db.set_single_value('System Settings', 'time_zone', 'Asia/Shanghai')
    frappe.db.set_single_value('System Settings', 'setup_complete', 1)
    receivable = frappe.db.get_value('Account', {'company': COMPANY, 'account_type': 'Receivable', 'is_group': 0}, 'name')
    income = frappe.db.get_value('Account', {'company': COMPANY, 'root_type': 'Income', 'is_group': 0}, 'name')
    bank = frappe.db.get_value('Account', {'company': COMPANY, 'account_type': 'Bank', 'is_group': 0}, 'name')
    cost_center = frappe.db.get_value('Cost Center', {'company': COMPANY, 'is_group': 0}, 'name')
    if not all([receivable, income, bank, cost_center]):
        raise RuntimeError('Company account setup did not produce required accounts')
    insert_once('Item Group', 'RSI Services', {'item_group_name': 'RSI Services', 'parent_item_group': 'All Item Groups', 'is_group': 0})
    insert_once('Item', 'RSI-SERVICE', {'item_code': 'RSI-SERVICE', 'item_name': 'RSI synthetic service', 'item_group': 'RSI Services', 'stock_uom': 'Nos', 'is_stock_item': 0})
    insert_once('Customer Group', 'RSI Customers', {'customer_group_name': 'RSI Customers', 'parent_customer_group': 'All Customer Groups', 'is_group': 0})
    insert_once('Territory', 'RSI Territory', {'territory_name': 'RSI Territory', 'parent_territory': 'All Territories', 'is_group': 0})
    customers = [('01', '青禾科技'), ('02', '远山零售'), ('03', '星海制造'), ('04', '白鹭设计'), ('05', '橙光教育'), ('99', '待核查付款方')]
    for code, label in customers:
        insert_once('Customer', 'RSI-CUST-' + code, {'customer_name': label + '（合成测试）', 'customer_type': 'Company', 'customer_group': 'RSI Customers', 'territory': 'RSI Territory', 'default_currency': 'CNY'})
    invoices = [('001', '01', 12000, '2026-09-07'), ('002', '02', 8500, '2026-09-04'), ('003', '03', 20000, '2026-09-15'), ('004', '04', 6000, '2026-09-06'), ('005', '05', 15000, '2026-09-05'), ('006', '03', 5000, '2026-09-16')]
    for code, customer, amount, due in invoices:
        insert_once('Sales Invoice', 'RSI-INV-' + code, {'company': COMPANY, 'customer': 'RSI-CUST-' + customer, 'currency': 'CNY', 'conversion_rate': 1, 'posting_date': '2026-09-01', 'set_posting_time': 1, 'due_date': due, 'debit_to': receivable, 'is_pos': 0, 'items': [{'item_code': 'RSI-SERVICE', 'qty': 1, 'rate': amount, 'income_account': income, 'cost_center': cost_center}], 'remarks': 'Synthetic RSI experiment invoice; no real transaction.'}, submit=True)
    payments = [('001', '01', 12000, 'RSI-BANK-1001', [('001', 12000)]), ('002', '02', 5000, 'RSI-BANK-1002', [('002', 5000)]), ('003', '03', 25000, 'RSI-BANK-1003', [('003', 20000), ('006', 5000)]), ('004', '04', 6000, 'RSI-BANK-1004', []), ('005', '04', 6000, 'RSI-BANK-1004', []), ('006', '99', 3200, 'RSI-BANK-1006', [])]
    for code, customer, amount, reference, allocations in payments:
        insert_once('Payment Entry', 'RSI-PAY-' + code, {'company': COMPANY, 'payment_type': 'Receive', 'party_type': 'Customer', 'party': 'RSI-CUST-' + customer, 'posting_date': '2026-09-08', 'paid_from': receivable, 'paid_to': bank, 'paid_amount': amount, 'received_amount': amount, 'source_exchange_rate': 1, 'target_exchange_rate': 1, 'reference_no': reference, 'reference_date': '2026-09-08', 'references': [{'reference_doctype': 'Sales Invoice', 'reference_name': 'RSI-INV-' + invoice, 'allocated_amount': allocated} for invoice, allocated in allocations], 'remarks': 'Synthetic RSI experiment payment; duplicate bank reference held for review.' if code in ['004', '005'] else 'Synthetic RSI experiment payment; no real money movement.'}, submit=True)
    role = 'RSI API Reader'
    insert_once('Role', role, {'role_name': role, 'desk_access': 1})
    from frappe.permissions import add_permission, update_permission_property
    for doctype in ['Sales Invoice', 'Payment Entry', 'Customer']:
        add_permission(doctype, role, 0)
        for permission in ['read', 'select']:
            update_permission_property(doctype, role, 0, permission, 1)
        for permission in ['write', 'create', 'delete', 'submit', 'cancel', 'amend', 'share', 'export', 'import']:
            update_permission_property(doctype, role, 0, permission, 0)
    insert_once('User', USER, {'email': USER, 'first_name': 'RSI Reader', 'send_welcome_email': 0, 'user_type': 'System User', 'roles': [{'role': role}], 'new_password': secrets.token_urlsafe(32)})
    user = frappe.get_doc('User', USER)
    if os.path.exists(OUTPUT):
        with open(OUTPUT) as stream:
            credentials = json.load(stream)
    else:
        user.api_key = frappe.generate_hash(length=15)
        user.api_secret = frappe.generate_hash(length=32)
        user.save(ignore_permissions=True)
        credentials = {'ERPNEXT_API_KEY': user.api_key, 'ERPNEXT_API_SECRET': user.get_password('api_secret')}
    frappe.db.commit()
    descriptor = os.open(OUTPUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(credentials, stream)
    summary = {'company': COMPANY, 'invoices': frappe.db.count('Sales Invoice', {'company': COMPANY, 'docstatus': 1}), 'payments': frappe.db.count('Payment Entry', {'company': COMPANY, 'docstatus': 1}), 'outstanding': sum(frappe.get_all('Sales Invoice', filters={'company': COMPANY, 'docstatus': 1}, pluck='outstanding_amount')), 'api_user': USER, 'credentials_saved': True}
    print('RSI_SEED_RESULT=' + json.dumps(summary, ensure_ascii=False))


try:
    main()
except Exception:
    frappe.db.rollback()
    raise
finally:
    frappe.destroy()
