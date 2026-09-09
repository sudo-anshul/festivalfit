import json

import pytest
from fastapi.testclient import TestClient
from google.genai.errors import ClientError

from app import main

FILM = {"title": "Example Film", "genre": "Fiction", "runtime_minutes": 18, "country": "India", "completed_on": "2026-07-01", "premiere_status": "World premiere available"}


@pytest.fixture
def client(monkeypatch):
    for key in ("GOOGLE_CLOUD_PROJECT", "PARALLEL_API_KEY", "FESTIVALFIT_ACCESS_CODE", "GEMINI_BACKEND", "GEMINI_API_KEY", "K_SERVICE"):
        monkeypatch.delenv(key, raising=False)
    main.run_times.clear()
    main.active_runs = 0
    return TestClient(main.app)


def test_missing_credentials_return_actionable_error(client):
    assert client.get("/api/status").json()["configured"] is False
    response = client.post("/api/match", json=FILM)
    assert response.status_code == 503
    assert "sample report" in response.json()["detail"]


def test_sample_stays_explicit_and_separate(client):
    sample = client.get("/api/sample").json()
    assert sample["mode"] == "sample"
    assert len(sample["festivals"]) == 3
    assert sample["model"].startswith("No model call")
    assert {f["status"] for f in sample["festivals"]} == {"likely_fit", "review_required", "not_fit"}


def test_runtime_validation(client):
    assert client.post("/api/match", json={**FILM, "runtime_minutes": -1}).status_code == 422


def test_developer_mode_requires_key_instead_of_cloud_project(client, monkeypatch):
    monkeypatch.setenv("GEMINI_BACKEND", "developer")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-only")
    config = client.get("/api/status").json()
    assert config["missing"] == ["GEMINI_API_KEY"]
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-gemini")
    assert client.get("/api/status").json()["configured"] is True
    assert "test-only" not in client.get("/api/status").text


def test_access_code_and_run_limit(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-secret")
    monkeypatch.setenv("FESTIVALFIT_ACCESS_CODE", "private-demo")
    assert client.post("/api/match", json=FILM).status_code == 401
    main.active_runs = 2
    assert client.post("/api/match", json=FILM, headers={"X-Access-Code": "private-demo"}).status_code == 429


def test_cloud_run_live_research_requires_access_code_configuration(client, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "1")
    monkeypatch.setenv("GEMINI_BACKEND", "developer")
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-gemini")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-only-parallel")
    status = client.get("/api/status").json()
    assert status["configured"] is False
    assert status["missing"] == ["FESTIVALFIT_ACCESS_CODE"]
    assert client.post("/api/match", json=FILM).status_code == 503
    assert client.get("/api/sample").status_code == 200


def test_cloud_run_live_research_rejects_missing_or_wrong_code(client, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "1")
    monkeypatch.setenv("GEMINI_BACKEND", "developer")
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-gemini")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-only-parallel")
    monkeypatch.setenv("FESTIVALFIT_ACCESS_CODE", "private-demo")
    status = client.get("/api/status").json()
    assert status["configured"] is True
    assert status["access_code_required"] is True
    assert client.post("/api/match", json=FILM).status_code == 401
    assert client.post("/api/match", json=FILM, headers={"X-Access-Code": "wrong"}).status_code == 401


def test_stream_errors_do_not_leak_provider_secrets(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-secret")

    async def fake_agent(film):
        yield {"event": "stage", "data": {"stage": "plan", "detail": "Planning"}}
        raise RuntimeError("provider exposed test-secret")

    monkeypatch.setattr(main, "run_agent", fake_agent)
    response = client.post("/api/match", json=FILM)
    messages = [json.loads(line) for line in response.text.splitlines()]
    assert messages[-1]["event"] == "error"
    assert "test-secret" not in response.text
    assert main.active_runs == 0


def test_browser_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_unavailable_google_model_has_actionable_error(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-only")

    async def fake_agent(film):
        yield {"event": "stage", "data": {"stage": "plan", "detail": "Planning"}}
        raise ClientError(404, {"error": {"code": 404, "message": "test-secret model unavailable", "status": "NOT_FOUND"}})

    monkeypatch.setattr(main, "run_agent", fake_agent)
    response = client.post("/api/match", json=FILM)
    assert "GEMINI_MODEL" in response.text
    assert "test-secret" not in response.text
    assert main.active_runs == 0


def test_partial_report_precedes_redacted_stream_error(client, monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    monkeypatch.setenv('PARALLEL_API_KEY', 'test-only')
    partial = client.get('/api/sample').json()
    partial['completion'] = 'partial'

    async def fake_agent(film):
        yield {'event': 'partial', 'data': partial}
        raise RuntimeError('private-provider-detail')

    monkeypatch.setattr(main, 'run_agent', fake_agent)
    response = client.post('/api/match', json=FILM)
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]['data']['completion'] == 'partial'
    assert events[0]['data']['festivals']
    assert events[-1]['event'] == 'error'
    assert 'private-provider-detail' not in response.text
    assert main.active_runs == 0
