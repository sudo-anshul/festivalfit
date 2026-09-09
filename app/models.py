from datetime import date, datetime
from datetime import date as CalendarDate
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Screening(BaseModel):
    date: CalendarDate | None = None
    territory: str = Field(default="", max_length=100)
    kind: Literal["festival", "cinema", "private", "online"] = "festival"
    public: bool = True
    notes: str = Field(default="", max_length=300)


class Film(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    genre: Literal["Fiction", "Documentary", "Animation", "Experimental", "Music video", "Other"]
    runtime_minutes: int = Field(ge=0, le=300)
    runtime_seconds: int = Field(default=0, ge=0, le=59)
    country: str = Field(min_length=2, max_length=160)
    completed_on: date
    premiere_status: Literal[
        "World premiere available", "Already screened at a festival",
        "Publicly available online", "Unknown",
    ]
    region: str = Field(default="Worldwide", min_length=2, max_length=120)
    synopsis: str = Field(default="", max_length=1200)
    medium: Literal["Live action", "Animation", "Mixed media", "Other"] = "Live action"
    production_countries: list[str] = Field(default_factory=list, max_length=12)
    shooting_countries: list[str] = Field(default_factory=list, max_length=12)
    languages: list[str] = Field(default_factory=list, max_length=12)
    subtitles: list[str] = Field(default_factory=list, max_length=12)
    completion_status: Literal["completed", "planned"] = "completed"
    screenings: list[Screening] = Field(default_factory=list, max_length=20)
    prior_submissions: list[str] = Field(default_factory=list, max_length=30)
    prior_submissions_known: bool = False
    student_status: Literal["yes", "no", "unknown"] = "unknown"
    goals: list[str] = Field(default_factory=list, max_length=8)
    budget: float | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)
    max_fee: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    submission_until: date | None = None
    research_mode: Literal["quick", "detailed"] = "quick"
    focus_festival: str = Field(default="", max_length=160)

    @field_validator("production_countries", "shooting_countries", "languages", "subtitles", "prior_submissions", "goals")
    @classmethod
    def clean_values(cls, values):
        if any(len(value) > 160 for value in values):
            raise ValueError("Each value must be at most 160 characters.")
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def validate_runtime(self):
        if not 0 < self.runtime_minutes * 60 + self.runtime_seconds <= 18000:
            raise ValueError("Runtime must be between one second and 300 minutes, including credits.")
        return self

    @property
    def exact_minutes(self) -> float:
        return self.runtime_minutes + self.runtime_seconds / 60

    @property
    def countries(self) -> list[str]:
        return self.production_countries or [self.country]


class QueryPlan(BaseModel):
    objective: str = Field(max_length=1500)
    search_queries: list[str] = Field(min_length=2, max_length=5)


class Criterion(StrEnum):
    runtime = "runtime"
    genre = "genre"
    country = "country"
    premiere = "premiere"
    completion = "completion"
    deadline = "deadline"


class Check(BaseModel):
    criterion: Criterion
    status: Literal["met", "not_met", "unknown"]
    explanation: str = Field(max_length=700)
    source_id: str | None = None
    quote: str | None = Field(default=None, max_length=900)
    kind: Literal["requirement", "preference", "procedural"] = "requirement"


class AdditionalRule(BaseModel):
    criterion: Literal["shooting_location", "language", "subtitles", "prior_submission", "student", "online_release", "theme", "delivery", "other"]
    label: str = Field(max_length=100)
    kind: Literal["requirement", "preference", "procedural"] = "requirement"
    source_id: str
    quote: str = Field(max_length=1200)
    explanation: str = Field(default="", max_length=500)


class Fee(BaseModel):
    amount: float = Field(ge=0, le=100000, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    tier: str = Field(default="Entry fee", max_length=100)
    source_id: str
    quote: str = Field(max_length=900)


class Festival(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(max_length=140)
    reason: str = Field(max_length=600)
    source_id: str
    deadline: date | None = Field(default=None, description="Explicit submission deadline as YYYY-MM-DD, or null when unknown.")
    checks: list[Check] = Field(max_length=12)
    next_steps: list[str] = Field(max_length=5)
    edition: str = Field(default="", max_length=80)
    scope_quote: str = Field(default="", max_length=2400)
    additional_rules: list[AdditionalRule] = Field(default_factory=list, max_length=12)
    fee: Fee | None = None
    deadline_timezone: str | None = Field(default=None, max_length=80)
    scope_notes: str = Field(default="", max_length=500)

    @field_validator("deadline", mode="before")
    @classmethod
    def normalize_deadline(cls, value):
        if value is None or isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None
        value = value.strip()
        # Only explicit year-bearing, unambiguous dates. No relative or fuzzy parsing.
        for pattern in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(value, pattern).date()
            except ValueError:
                continue
        return None


class Assessment(BaseModel):
    festivals: list[Festival] = Field(max_length=5)


class CandidateRecheck(BaseModel):
    candidate_id: str = Field(max_length=10)
    source_id: str
    deadline: date | None = None
    checks: list[Check] = Field(max_length=12)
    edition: str = Field(default="", max_length=80)
    scope_quote: str = Field(default="", max_length=2400)
    additional_rules: list[AdditionalRule] = Field(default_factory=list, max_length=12)
    fee: Fee | None = None
    deadline_timezone: str | None = Field(default=None, max_length=80)
    scope_notes: str = Field(default="", max_length=500)

    @field_validator("deadline", mode="before")
    @classmethod
    def normalize_deadline(cls, value):
        return Festival.normalize_deadline(value)


class Reassessment(BaseModel):
    candidates: list[CandidateRecheck] = Field(max_length=5)


class Source(BaseModel):
    id: str
    title: str
    url: str
    excerpts: list[str]
    retrieved_at: str | None = None
    content_hash: str | None = None
    retrieval: Literal["search", "extract"] = "search"


def generation_schema(model: type[BaseModel]) -> dict:
    """Send a small generation schema; enforce full bounds and dates with Pydantic afterward.

    Gemini can reject nested schemas with many string/array bounds. Inline local
    references and retain the structure, enums, and required fields on the wire.
    """
    schema = model.model_json_schema()
    definitions = schema.get("$defs", {})
    omitted = {"$defs", "title", "default", "format", "minLength", "maxLength", "minItems", "maxItems"}

    def simplify(value):
        if isinstance(value, list):
            return [simplify(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return simplify(definitions[value["$ref"].rsplit("/", 1)[-1]])
        return {key: simplify(item) for key, item in value.items() if key not in omitted}

    return simplify(schema)
