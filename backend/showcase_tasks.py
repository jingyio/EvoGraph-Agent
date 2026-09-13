"""Higher-complexity, read-only business tasks used by the recording demo.

These tasks deliberately live outside the frozen 300-task benchmark.  They
reuse only records already installed in the taskbank SQLite file, derive their
expected facts locally, and never expose those facts to the Agent or browser.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any


TASKS_FILE = Path('benchmarks/showcase-tasks-v1.json')


def _seconds(value: str) -> int:
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())


def _amounts(row: dict[str, Any]) -> tuple[int, int, int]:
    return (
        sum(item['amount_cents'] for item in row['payments']),
        sum(item['price_cents'] for item in row['items']),
        sum(item['freight_cents'] for item in row['items']),
    )


def answer(task: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the private deterministic contract for one showcase task."""
    family = task['family']
    if family == 'weekly_risk_review':
        cancelled = [row for row in records if row['status'] == 'canceled' and row['payments']]
        mismatches = [
            row for row in records
            if row['payments'] and row['items']
            and abs(_amounts(row)[0] - _amounts(row)[1] - _amounts(row)[2]) > 1
        ]
        freight = [row for row in records if _amounts(row)[1] > 0 and _amounts(row)[2] * 5 >= _amounts(row)[1]]
        selected = sorted({row['id'] for row in cancelled + mismatches + freight})
        selected_rows = [row for row in records if row['id'] in selected]
        return {
            'metrics': {
                'cancelled_paid_count': len(cancelled),
                'cancelled_paid_cents': sum(_amounts(row)[0] for row in cancelled),
                'reconciliation_mismatch_count': len(mismatches),
                'freight_burden_count': len(freight),
                'priority_order_count': len(selected),
                'priority_paid_cents': sum(_amounts(row)[0] for row in selected_rows),
            },
            'selectedIds': selected,
            'ordered': False,
        }
    if family == 'escalation_review':
        def forwarding_seconds(row: dict[str, Any]) -> int | None:
            if not row.get('date_received') or not row.get('date_sent_to_company'):
                return None
            return _seconds(row['date_sent_to_company']) - _seconds(row['date_received'])

        late_narrative = [row for row in records if row['timely'] == 'No' and row['narrative'].strip()]
        forwarded = [row for row in records if (forwarding_seconds(row) or 0) > 86400]
        selected = sorted({row['id'] for row in late_narrative + forwarded})
        selected_rows = [row for row in records if row['id'] in selected]
        return {
            'metrics': {
                'late_with_narrative_count': len(late_narrative),
                'forwarded_over_day_count': len(forwarded),
                'priority_complaint_count': len(selected),
                'priority_company_count': len({row['company'] for row in selected_rows}),
                'priority_forwarding_seconds': sum(forwarding_seconds(row) or 0 for row in selected_rows),
            },
            'selectedIds': selected,
            'ordered': False,
        }
    if family == 'engineering_attention_review':
        as_of = _seconds(task['asOf'])
        priority = [
            row for row in records
            if row['state'] == 'open' and row['assignee_count'] == 0
            and (row['milestone'] is None or as_of - _seconds(row['updated_at']) > 30 * 86400)
        ]
        priority.sort(key=lambda row: (-row['comments'], row['id']))
        return {
            'metrics': {
                'priority_issue_count': len(priority),
                'stale_priority_count': sum(as_of - _seconds(row['updated_at']) > 30 * 86400 for row in priority),
                'bug_priority_count': sum(any('bug' in label.lower() for label in row['labels']) for row in priority),
                'priority_comment_total': sum(row['comments'] for row in priority),
            },
            'selectedIds': [row['id'] for row in priority],
            'ordered': True,
        }
    raise ValueError(f'Unknown showcase task family: {family}')


def load(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Load public task specs and calculate their private answers from SQLite."""
    root = Path(root)
    task_path = root / TASKS_FILE
    record_path = root / 'artifacts/taskbank/records.sqlite3'
    if not task_path.exists() or not record_path.exists():
        return {}, {}
    tasks = {row['id']: row for row in json.loads(task_path.read_text(encoding='utf-8'))}
    gold: dict[str, dict[str, Any]] = {}
    with sqlite3.connect(record_path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        for task_id, task in tasks.items():
            records = []
            for record_id in task['recordIds']:
                row = db.execute('SELECT payload FROM records WHERE scenario=? AND id=?', (task['scenario'], record_id)).fetchone()
                if row is None:
                    raise ValueError(f'Showcase task {task_id} references unavailable frozen record {record_id}')
                records.append(json.loads(row[0]))
            gold[task_id] = answer(task, records)
    return tasks, gold
