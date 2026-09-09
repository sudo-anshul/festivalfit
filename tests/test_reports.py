"""Portable decisions, selected scope, privacy defaults and export failure paths."""
import csv
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.reports import ExportRequest, export_data, render_export


@pytest.fixture
def report():
    return json.loads((Path(__file__).parents[1] / 'app/static/sample.json').read_text())


def test_selected_export_preserves_decision_and_omits_synopsis(report):
    selected = report['festivals'][1]
    request = ExportRequest(report=report, format='json', selected_ids=[selected['id']])
    content, _ = render_export(request)
    result = json.loads(content)
    assert [f['id'] for f in result['festivals']] == [selected['id']]
    assert result['festivals'][0]['status'] == selected['status']
    assert result['festivals'][0]['checks'] == selected['checks']
    assert result['film']['synopsis'] == ''
    assert report['film']['synopsis']
    assert result['export_scope'] == 'Selected shortlist'


def test_synopsis_opt_in_and_empty_scope(report):
    request = ExportRequest(report=report, format='md', include_synopsis=True)
    assert export_data(request)['film']['synopsis'] == report['film']['synopsis']
    with pytest.raises(ValueError, match='at least one'):
        export_data(ExportRequest(report=report, format='md', selected_ids=[]))


def test_markdown_preserves_unknowns_fee_evidence_and_citations(report):
    body, _ = render_export(ExportRequest(report=report, format='md'))
    text = body.decode()
    assert 'FICTIONAL SAMPLE' in text and 'Needs review' in text and 'Excluded' in text
    assert report['film']['synopsis'] not in text
    assert 'unconfirmed' in text and 'Fee evidence:' in text
    for festival in report['festivals']:
        assert festival['name'] in text
        for check in festival['checks']:
            assert check['status'] in text
    assert report['sources'][0]['url'] in text
    reduced, _ = render_export(ExportRequest(report=report, format='md', include_evidence=False))
    assert 'Fee evidence:' not in reduced.decode()
    assert report['festivals'][0]['checks'][0]['quote'] not in reduced.decode()


def test_csv_separate_currency_unknown_fee_and_formula_safety(report):
    report['film']['title'] = '=HYPERLINK("https://example.com")'
    report['festivals'][0]['fee'] = None
    body, _ = render_export(ExportRequest(report=report, format='csv'))
    rows = list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
    assert len(rows) == 3
    assert rows[0]['Film'].startswith("'=")
    assert rows[0]['Fee amount'] == '' and rows[0]['Currency'] == ''
    assert rows[1]['Currency'] == 'USD'
    assert 'unknown' in rows[1]['Blockers / unknowns']


@pytest.mark.parametrize('fmt,media', [('md', 'text/markdown'), ('csv', 'text/csv'), ('json', 'application/json'), ('pdf', 'application/pdf')])
def test_export_download_contract(report, fmt, media):
    response = TestClient(app).post('/api/export', json={'report': report, 'format': fmt})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith(media)
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['content-disposition'].endswith(f'.{fmt}"')
    assert len(response.content) > 100
    if fmt == 'pdf': assert response.content.startswith(b'%PDF-')


def test_export_rejects_invalid_selection_and_oversized_body(report):
    client = TestClient(app)
    assert client.post('/api/export', json={'report': report, 'format': 'pdf', 'selected_ids': ['missing']}).status_code == 422
    assert client.post('/api/export', content=b'x' * 1_500_001).status_code == 413
