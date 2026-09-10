from backend.business_report import evidence_rows, render_report


def test_report_uses_observations_not_unread_records_and_escapes_untrusted_text():
    task = dict(id='tickets-x', title='工单报告', recordCount=2, asOf='2026-09-10', task='筛选工单', sourceUrl='https://example.org')
    run = dict(id='r', status='completed', evaluation={'status': 'passed', 'issues': []},
               submission=dict(metrics={'count': 1}, selectedIds=['a'], summary='<script>alert(1)</script>'), events=[
                   dict(type='observation', detail=dict(ok=True, result={'records': [{'id': 'a', '_evidenceRef': 'tickets:a', 'state': 'open'}]})),
                   dict(type='observation', detail=dict(ok=True, result={'id': 'a', '_evidenceRef': 'tickets:a', 'title': '<img src=x onerror=evil>'})),
                   dict(type='observation', detail=dict(ok=False, result={'id': 'b', '_evidenceRef': 'tickets:b'}))])
    rows = evidence_rows(run)
    assert list(rows) == ['tickets:a'] and rows['tickets:a']['state'] == 'open'
    html = render_report(run, task)
    assert '<script>' not in html and '<img src=x' not in html
    assert '&lt;script&gt;' in html and 'tickets:b' not in html
    assert 'pending' in html and '文字' in html


async def test_report_and_human_review_endpoints(tmp_path, monkeypatch):
    import httpx
    from backend.app import create_app
    from backend.service import RunService
    from test_task_runner import Bank, Model
    class ReportBank(Bank):
        def task(self, key):
            return dict(super().task(key), title='报告验收', recordCount=1, asOf='2026-09-10', sourceUrl='https://example.org')
    bank = ReportBank(tmp_path)
    monkeypatch.setattr('backend.app.TaskBank', lambda: bank)
    app = create_app(RunService(tmp_path / 'legacy'))
    runner = app.state.task_runner
    runner.provider_factory = lambda role: Model(role, [])
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/taskbank/runs', json={'taskId': 'sample'})
            key = response.json()['id']
            if key in runner.tasks:
                await runner.tasks[key]
            report = await client.get('/api/taskbank/runs/' + key + '/report')
            assert report.status_code == 200 and 'pending' in report.text
            assert "default-src 'none'" in report.headers['content-security-policy']
            review = await client.post('/api/taskbank/runs/' + key + '/review', json={'factualConsistency': 2, 'requirementCoverage': 1, 'readability': 2, 'note': '协议测试'})
            assert review.status_code == 200 and review.json()['source'] == 'human'
            assert runner.runs[key]['evaluation']['status'] == 'passed'
            report = await client.get('/api/taskbank/runs/' + key + '/report')
            assert 'reviewed' in report.text and '协议测试' in report.text
            assert (await client.post('/api/taskbank/runs/' + key + '/review', json={'factualConsistency': 3, 'requirementCoverage': 1, 'readability': 2})).status_code == 400
