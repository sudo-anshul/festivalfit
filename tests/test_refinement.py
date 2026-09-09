import json
from pathlib import Path

from app.agent import followup_queries, merge_refinement
from app.models import Assessment, Reassessment


def sample():
    return json.loads((Path(__file__).parents[1] / "app/static/sample.json").read_text())


def test_refinement_uses_ids_and_keeps_names_and_categories():
    original = Assessment.model_validate(sample())
    candidate = original.festivals[1]
    refined = Reassessment.model_validate({"candidates": [{"candidate_id": "C2", "source_id": "S4", "deadline": "November 2, 2026", "checks": [c.model_dump() for c in candidate.checks]}]})
    result = merge_refinement(original, refined)
    assert result.festivals[1].source_id == "S4"
    assert result.festivals[1].name == candidate.name
    assert result.festivals[1].category == candidate.category
    assert result.festivals[0] == original.festivals[0]
    assert original.festivals[1].source_id == "S2"


def test_duplicate_or_unknown_candidate_ids_cannot_replace_candidates():
    original = Assessment.model_validate(sample())
    row = {"candidate_id": "C2", "source_id": "S4", "deadline": None, "checks": []}
    result = merge_refinement(original, Reassessment.model_validate({"candidates": [row, row, {**row, "candidate_id": "C99"}]}))
    assert result == original


def test_followup_targets_only_missing_checks_of_potential_candidates():
    queries = followup_queries(sample()["festivals"], 2026)
    assert len(queries) == 1
    assert "Open Frame Weekend" in queries[0]
    assert "premiere status" in queries[0]
    assert "First Light" not in queries[0]
    assert "Lantern" not in queries[0]
