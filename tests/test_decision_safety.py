"""Adversarial regressions: a real quotation must not produce contradictory advice."""
from copy import deepcopy
from datetime import date

import pytest

from app.evidence import validate_assessment
from app.models import Assessment, Film, Source
from test_evidence import candidate, QUOTES

TODAY = date(2026, 9, 8)
FILM = Film(title="Boundary Film", genre="Fiction", runtime_minutes=30, country="India",
            completed_on="2026-07-01", premiere_status="World premiere available")


def check_candidate(criterion, quote, *, status="met", deadline="2026-10-01", film=FILM, steps=None):
    data = candidate(deadline=deadline, next_steps=steps or [])
    check = next(c for c in data["checks"] if c["criterion"] == criterion)
    check.update(quote=quote, status=status)
    source = Source(id="S1", title="Example Festival 2027 Shorts", url="https://festival.example/rules",
                    excerpts=[quote] + list(QUOTES.values()))
    assessment = Assessment.model_validate({"festivals": [data]})
    before = deepcopy(assessment.model_dump())
    result = validate_assessment(assessment, [source], TODAY, film)[0]
    assert assessment.model_dump() == before, "Validation must not mutate its input."
    return result, next(c for c in result["checks"] if c["criterion"] == criterion)


@pytest.mark.parametrize("quote,expected", [
    ("Short films must run under 30 minutes including credits.", "not_met"),
    ("Short films must run less than 30 minutes including credits.", "not_met"),
    ("Films must be no longer than 30 minutes including credits.", "met"),
    ("Films must not exceed the 30-minute mark.", "met"),
    ("The maximum runtime is 20 minutes including credits.", "not_met"),
    ("Documentaries must run under 30 minutes; fiction films must run under 40 minutes.", "unknown"),
    ("Films must not be shorter than 30 minutes including credits.", "unknown"),
    ("The festival accepts short (under 40 minutes) and feature documentaries (between 41 – 180 minutes).", "unknown"),
])
def test_runtime_boundary_and_ambiguous_categories(quote, expected):
    _, check = check_candidate("runtime", quote)
    assert check["status"] == expected


def test_unknown_runtime_scope_cannot_be_promoted_by_arithmetic():
    _, check = check_candidate("runtime", "Short films must run under 40 minutes including credits.", status="unknown")
    assert check["status"] == "unknown"


def test_exceed_the_minute_mark_is_checked():
    _, check = check_candidate("runtime", "Short films must not exceed the 30-minute mark.", film=FILM.model_copy(update={"runtime_minutes": 31}))
    assert check["status"] == "not_met"


def test_unknown_premiere_cannot_be_claimed_as_met():
    film = FILM.model_copy(update={"premiere_status": "Unknown"})
    _, check = check_candidate("premiere", "Films must retain their world premiere status.", film=film)
    assert check["status"] == "unknown"


def test_explicitly_unrestricted_premiere_can_still_match():
    film = FILM.model_copy(update={"premiere_status": "Unknown"})
    _, check = check_candidate("premiere", "There are no premiere requirements for this short film category.", film=film)
    assert check["status"] == "met"


def test_previous_festival_screening_does_not_prove_loss_of_regional_premiere():
    film = FILM.model_copy(update={"premiere_status": "Already screened at a festival"})
    _, check = check_candidate("premiere", "Documentaries should be at least Sydney Premiere.", status="not_met", film=film)
    assert check["status"] == "unknown"


@pytest.mark.parametrize("quote,status", [
    ("International Festival", "unknown"),
    ("Submissions are accepted from filmmakers in all countries, including India.", "met"),
])
def test_country_needs_more_than_an_international_label(quote, status):
    _, check = check_candidate("country", quote)
    assert check["status"] == status


@pytest.mark.parametrize("quote,status", [
    ("The festival is calling for short film submissions to its international competition.", "unknown"),
    ("This category accepts animated short films from around the world.", "met"),
    ("This category is open to films of all genres.", "met"),
])
def test_animation_is_not_inferred_from_a_generic_short_film_call(quote, status):
    _, check = check_candidate("genre", quote, film=FILM.model_copy(update={"genre": "Animation"}))
    assert check["status"] == status


@pytest.mark.parametrize("quote", [
    "The festival is accepting documentaries until October 1, 2026.",
    "Extended Deadline: (1 st September 2026 to 1 st October 2026)",
])
def test_explicit_submission_wording_and_spaced_ordinals(quote):
    result, check = check_candidate("deadline", quote)
    assert result["deadline"] == "2026-10-01"
    assert check["status"] == "met"


def test_event_date_does_not_become_submission_deadline():
    result, check = check_candidate("deadline", "The festival takes place on October 1, 2026.")
    assert result["deadline"] is None
    assert check["status"] == "unknown"


def test_submission_notification_is_not_a_deadline():
    result, check = check_candidate("deadline", "Your submission notification date is October 1, 2026.")
    assert result["deadline"] is None
    assert check["status"] == "unknown"


def test_unknown_deadline_scope_cannot_be_promoted_by_calendar():
    result, check = check_candidate("deadline", "Submission deadline: October 1, 2026.", status="unknown")
    assert result["deadline"] is None
    assert check["status"] == "unknown"


def test_rejected_deadline_cannot_survive_in_advice():
    result, _ = check_candidate("deadline", "For films produced in 2025, the deadline is September 24, 2026.",
                                deadline="2026-09-24", steps=["Submit before September 24, 2026 and pay 500 dollars."])
    assert result["deadline"] is None
    advice = " ".join(result["next_steps"])
    assert "September 24" not in advice
    assert "500" not in advice
    assert "Verify" in advice


def test_expired_deadline_does_not_encourage_submission():
    result, _ = check_candidate("deadline", "Submission deadline: September 1, 2026.",
                                deadline="2026-09-01", steps=["Submit now to this great match."])
    assert result["status"] == "not_fit"
    assert result["next_steps"][0].startswith("Do not submit")
    assert "Submit now" not in " ".join(result["next_steps"])
