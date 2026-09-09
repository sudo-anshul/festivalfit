"""Exercise real SDK serialization against stub HTTP transports, without credentials."""
import json
from pathlib import Path

import httpx
import pytest
from google import genai
from google.oauth2.credentials import Credentials
from parallel import AsyncParallel

from app import agent
from app.models import Film


@pytest.mark.parametrize("backend,transient_failure,followup", [("vertex", False, "same"), ("developer", False, "same"), ("developer", True, "same"), ("developer", False, "new"), ("developer", False, "expanded"), ("developer", False, "outage"), ("developer", False, "alternatives"), ("developer", False, "empty")])
@pytest.mark.parametrize("detailed", [False, "available", "unavailable"])
async def test_real_sdk_contracts_and_workflow(monkeypatch, backend, transient_failure, followup, detailed):
    sample = json.loads((Path(__file__).parents[1] / "app/static/sample.json").read_text())
    plan = {"objective": "Find current official festival requirements.", "search_queries": ["short film festivals 2026 official rules", "fiction short film submission deadlines 2026"]}
    assessment = {"festivals": sample["festivals"]}
    refined = json.loads(json.dumps(assessment))
    refined["festivals"][1]["checks"][3].update(status="met", source_id="S4" if followup == "new" else "S2", quote="There are no premiere requirements for this category.")
    refined = {"candidates": [{"candidate_id": f"C{i}", **{key: f[key] for key in ["source_id", "deadline", "checks"]}} for i, f in enumerate(refined["festivals"], 1)]}
    if followup in {"alternatives", "empty"}:
        assessment = {"festivals": [sample["festivals"][2]] if followup == "alternatives" else []}
        refined = {"festivals": sample["festivals"]}
    google_requests, parallel_requests, google_attempts, extract_requests = [], [], [], []

    def google_transport(request):
        google_attempts.append(request.url)
        if transient_failure and len(google_attempts) == 1:
            return httpx.Response(503, json={"error": {"code": 503, "message": "Temporary test outage", "status": "UNAVAILABLE"}})
        google_requests.append(json.loads(request.content))
        assert ("aiplatform.googleapis.com" if backend == "vertex" else "generativelanguage.googleapis.com") in str(request.url)
        assert "generateContent" in str(request.url)
        content = plan if len(google_requests) == 1 else assessment if len(google_requests) == 2 else refined
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps(content)}]}, "finishReason": "STOP"}]})

    def parallel_transport(request):
        if request.url.path == "/v1/extract":
            extract_requests.append(json.loads(request.content))
            if detailed == "unavailable": return httpx.Response(401, json={"error": "Test-only extract unavailable"})
            return httpx.Response(200, json={"extract_id": "extract_test", "results": [{"url": s['url'], "title": s['title'], "excerpts": [], "full_content": "Full rules context. " + "\n".join(s['excerpts'])} for s in sample['sources']]})
        parallel_requests.append(json.loads(request.content))
        assert request.url.path == "/v1/search"
        results = [{"url": s["url"], "title": s["title"], "excerpts": s["excerpts"]} for s in sample["sources"]]
        if len(parallel_requests) > 1:
            if followup == "outage":
                return httpx.Response(401, json={"error": "Test-only follow-up unavailable"})
            if followup in {"new", "expanded", "alternatives", "empty"}:
                results = [{"url": sample["sources"][1]["url"] if followup == "expanded" else "https://example.com/additional-rules", "title": "Open Frame Weekend 2027 Independent voices", "excerpts": ["There are no premiere requirements for this category."]}]
        return httpx.Response(200, json={"search_id": "search_test", "results": results})

    google_options = {"async_client_args": {"transport": httpx.MockTransport(google_transport)}, "retry_options": {"attempts": 1}}
    google_client = genai.Client(vertexai=True, project="test-project", location="global", credentials=Credentials(token="test-only-token"), http_options=google_options) if backend == "vertex" else genai.Client(vertexai=False, api_key="test-only-gemini", http_options=google_options)
    parallel_client = AsyncParallel(api_key="test-only", http_client=httpx.AsyncClient(transport=httpx.MockTransport(parallel_transport)))
    monkeypatch.setattr(agent.genai, "Client", lambda **kwargs: google_client)
    monkeypatch.setattr(agent, "AsyncParallel", lambda **kwargs: parallel_client)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GEMINI_BACKEND", backend)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-gemini")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-only")
    film = Film.model_validate({**sample["film"], "research_mode": "detailed" if detailed else "quick"})
    events = [event async for event in agent.run_agent(film)]
    expected_google = 3 if followup in {"new", "expanded", "alternatives", "empty"} else 2
    assert len(google_requests) == expected_google
    assert len(google_attempts) == expected_google + transient_failure
    assert len(parallel_requests) == 2
    assert parallel_requests[0]["search_queries"] == plan["search_queries"]
    assert parallel_requests[0]["advanced_settings"]["max_results"] == 12
    assert google_requests[0]["generationConfig"]["responseMimeType"] == "application/json"
    assert events[-1]["event"] == "result"
    assert events[-1]["data"]["mode"] == "live"
    assert len(events[-1]["data"]["festivals"]) == 3
    assert [e["data"]["stage"] for e in events if e["event"] == "stage"] == ["plan", "discover", *(["extract"] if detailed else []), "assess", "refine", "verify"]
    partial = next(e['data'] for e in events if e['event'] == 'partial')
    assert partial['completion'] == 'partial'
    assert partial['report_id'] == events[-1]['data']['report_id']
    assert events[-1]['data']['completion'] == 'complete'
    assert events[-1]['data']['enrichment']['status'] == {'available': 'completed', 'unavailable': 'unavailable', False: 'not_requested'}[detailed]
    assert len(extract_requests) == bool(detailed)
    if detailed:
        assert extract_requests[0]['advanced_settings']['full_content'] is True
        assert 'full_content' not in extract_requests[0]
        assert len(extract_requests[0]['urls']) <= 3
    outcome = events[-1]["data"]["followup"]
    assert outcome["resolved_checks"] == (1 if followup in {"new", "expanded"} else 0)
    assert outcome["status"] == {"new": "completed", "expanded": "completed", "same": "no_new_sources", "outage": "unavailable", "alternatives": "completed", "empty": "completed"}[followup]
    if followup in {"alternatives", "empty"}:
        assert outcome["purpose"] == "alternatives"
        assert outcome["new_candidates"] == 2
        assert "deadline after" in parallel_requests[1]["search_queries"][0]
    else:
        assert "Open Frame Weekend" in parallel_requests[1]["search_queries"][0]
        assert "premiere status" in parallel_requests[1]["search_queries"][0]
