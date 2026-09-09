from datetime import date

import pytest

from app.evidence import date_in_quote, safe_url, validate_assessment
from app.models import Assessment, Criterion, Film, Source

TODAY = date(2026, 9, 8)
QUOTES = {
    "runtime": "Short films must be no longer than 40 minutes including credits.",
    "genre": "This category accepts narrative fiction films.",
    "country": "Submissions are accepted from all countries, including India.",
    "premiere": "There are no premiere requirements for this category.",
    "completion": "Films completed on or after January 1, 2026 are eligible.",
    "deadline": "Submission deadline: October 1, 2026.",
}
FILM = Film(title="Example", genre="Fiction", runtime_minutes=18, country="India", completed_on="2026-07-01", premiere_status="World premiere available")


def candidate(**updates):
    data = {"name": "Example Festival", "category": "Shorts", "edition": "2027", "reason": "A candidate.", "source_id": "S1", "deadline": "2026-10-01", "checks": [{"criterion": c.value, "status": "met", "explanation": "Matched.", "source_id": "S1", "quote": QUOTES[c.value]} for c in Criterion], "next_steps": ["Read full rules."]}
    data.update(updates)
    return data


def assess(data):
    sources = [Source(id="S1", url="https://festival.example/rules", title="Example Festival 2027 Shorts", excerpts=list(QUOTES.values()) + ["Submission deadline: September 1, 2026.", "Submission deadline: September 8, 2026."])]
    return validate_assessment(Assessment.model_validate({"festivals": [data]}), sources, TODAY, FILM)


def test_invented_festival_source_is_rejected():
    assert assess(candidate(source_id="invented")) == []


def test_fabricated_quotation_cannot_support_a_match():
    data = candidate()
    data["checks"][0]["quote"] = "Fabricated requirement text not found in source."
    result = assess(data)[0]
    assert result["status"] == "review_required"
    assert result["checks"][0]["status"] == "unknown"
    assert result["checks"][0]["source_id"] is None


def test_missing_and_duplicate_requirements_are_unknown():
    data = candidate()
    data["checks"] = [data["checks"][0], data["checks"][0]]
    result = assess(data)[0]
    assert result["matched"] == 0
    assert len(result["checks"]) == 6
    assert result["deadline"] is None


@pytest.mark.parametrize("deadline,quote,status", [
    ("2026-09-01", "Submission deadline: September 1, 2026.", "not_fit"),
    ("2026-09-08", "Submission deadline: September 8, 2026.", "review_required"),
    ("2026-10-01", "Submission deadline: October 1, 2026.", "likely_fit"),
])
def test_deadline_recomputed_instead_of_trusting_model(deadline, quote, status):
    data = candidate(deadline=deadline)
    data["checks"][-1]["quote"] = quote
    assert assess(data)[0]["status"] == status


def test_uncited_deadline_is_removed():
    assert assess(candidate(deadline="2027-10-01"))[0]["deadline"] is None


def test_named_deadline_is_normalized_and_still_requires_citation():
    result = assess(candidate(deadline="October 1, 2026"))[0]
    assert result["deadline"] == "2026-10-01"
    assert result["status"] == "likely_fit"
    assert assess(candidate(deadline="October 1, 2027"))[0]["deadline"] is None


@pytest.mark.parametrize("deadline", ["next October", "10/01/26", "October 1", "2026-02-30"])
def test_ambiguous_or_invalid_deadline_becomes_unknown(deadline):
    result = assess(candidate(deadline=deadline))[0]
    assert result["deadline"] is None
    assert result["status"] == "review_required"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,hello", "https://user:pass@example.com", "https://", "not a url"])
def test_unsafe_source_links_rejected(url):
    assert not safe_url(url)


def test_dates_need_matching_year():
    assert date_in_quote(date(2026, 9, 8), "Deadline: 8 September 2026.")
    assert date_in_quote(date(2026, 9, 8), "Deadline: Sept. 8, 2026.")
    assert not date_in_quote(date(2026, 9, 8), "Deadline: September 8.")


def test_deadline_for_different_production_year_is_not_a_match():
    quote = "For films produced in 2025 – September 24, 2026"
    data = candidate(deadline="2026-09-24")
    data["checks"][-1]["quote"] = quote
    source = Source(id="S1", url="https://festival.example/rules", title="Example Festival 2027 Shorts", excerpts=[quote])
    film = Film(title="Example", genre="Fiction", runtime_minutes=18, country="India", completed_on="2026-07-01", premiere_status="World premiere available")
    result = validate_assessment(Assessment.model_validate({"festivals": [data]}), [source], TODAY, film)[0]
    assert result["deadline"] is None
    assert result["checks"][-1]["status"] == "unknown"
    assert "2025" in result["checks"][-1]["explanation"]
