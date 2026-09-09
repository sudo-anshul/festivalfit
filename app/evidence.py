import calendar
import hashlib
import re
from datetime import date
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import Assessment, Check, Criterion, Film, Source, AdditionalRule
from .rules import (completion_rule, country_rule, extra_rule, fold, genre_rule,
                    premiere_rule, rule_kind, runtime_rule, sentences)

LABELS = {"runtime": "runtime", "genre": "film type", "country": "production country", "premiere": "premiere status", "completion": "completion date", "deadline": "submission deadline", "shooting_location": "shooting location", "subtitles": "subtitles", "language": "language", "prior_submission": "prior submission", "student": "student status", "online_release": "online release", "theme": "thematic relevance", "delivery": "delivery materials", "other": "additional requirement"}


def safe_url(value: str) -> bool:
    try:
        p = urlsplit(value)
        return p.scheme in {"https", "http"} and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False


def normalize(text):
    return re.sub(r"\s+", " ", text).strip().casefold()


def quote_supported(quote, source):
    return bool(quote and source and len(normalize(quote)) >= 15 and any(normalize(quote) in normalize(e) for e in source.excerpts))


def date_in_quote(value, quote):
    month, short = calendar.month_name[value.month], calendar.month_abbr[value.month]
    month_pattern = rf"(?:{month}|{short}\.?|{'Sept\\.?' if value.month == 9 else short})"
    day = rf"0?{value.day}(?:\s*(?:st|nd|rd|th))?"
    return any(re.search(p, quote, re.I) for p in [rf"\b{value.isoformat()}\b", rf"\b{month_pattern}\s+{day},?\s+{value.year}\b", rf"\b{day}\s+{month_pattern},?\s+{value.year}\b"])


def runtime_verdict(quote, minutes):
    return runtime_rule(quote, minutes)


def scope_issues(festival, source, today):
    if not source:
        return ["Source unavailable"]
    # A supplied context must really be in the retrieved source.
    if festival.scope_quote and not quote_supported(festival.scope_quote, source):
        return ["The edition/category context is not present in the source"]
    text = source.title + " " + (festival.scope_quote or " ".join(source.excerpts))
    issues = []
    if fold(festival.name) not in fold(text):
        issues.append("Festival identity is not established by this source")
    if not festival.edition or not re.search(r"\b20\d{2}\b", festival.edition):
        issues.append("Current edition is unconfirmed")
    else:
        year = re.search(r"\b20\d{2}\b", festival.edition).group()
        if year not in text or not today.year <= int(year) <= today.year + 2:
            issues.append("The cited text does not establish the requested current edition")
    # Compare meaningful category words; a named category must actually occur.
    terms = [w for w in fold(festival.category).split() if w not in {"competition", "category", "international", "and", "the", "film", "films"}]
    if not terms or not all(re.search(rf"\b{re.escape(t.rstrip('s'))}s?\b", fold(text)) for t in terms):
        issues.append("The selected category is not established by this source")
    return issues


def deadline_verdict(value, quote, today, film):
    if not value:
        return "unknown", "A year-bearing submission deadline was not established.", None
    year_condition = re.search(r"\bfilms?\s+(?:produced|completed|made|released)\s+(?:in|during)\s+(\d{4})\b", quote, re.I)
    if film and year_condition and int(year_condition.group(1)) != film.completed_on.year:
        return "unknown", f"This deadline applies to films from {year_condition.group(1)}; confirm the appropriate completion-year round.", None
    window = re.search(r"\bcompletion\s+date\s+between\s+([A-Za-z]+)\s+(20\d{2})\s+and\s+([A-Za-z]+)\s+(20\d{2})", quote, re.I)
    if film and window:
        months = {name.casefold(): i for i, name in enumerate(calendar.month_name) if name}
        months.update({name.casefold(): i for i, name in enumerate(calendar.month_abbr) if name})
        first, y1, last, y2 = window.groups()
        if first.casefold() not in months or last.casefold() not in months:
            return "unknown", "Confirm the completion window for this deadline round.", None
        lower, upper = (int(y1), months[first.casefold()]), (int(y2), months[last.casefold()])
        if not lower <= (film.completed_on.year, film.completed_on.month) <= upper:
            return "unknown", "This deadline round is for a different completion window; confirm the film's applicable round.", None
    relevant = [s for s in sentences(quote) if date_in_quote(value, s)]
    good = []
    for clause in relevant:
        if re.search(r"\b(notification|screening copy|screening copies|event dates?|takes place|festival runs)\b", clause, re.I):
            continue
        if re.search(r"\bdeadlines?\b|\b(?:submissions?|entries)\b.{0,90}\b(?:due|close|closing|until|by)\b|\b(?:submit|submitted|enter|accepting)\b.{0,90}\b(?:by|before|until)\b", clause, re.I):
            # A second date labelled event/screening must not borrow the deadline label.
            if re.search(r"\b(?:event|screening|festival date|notification)\b", clause, re.I):
                continue
            good.append(clause)
    if not good:
        return "unknown", "The chosen date is not bound to a submission deadline; event and notification dates cannot substitute.", None
    status = "not_met" if value < today else "unknown" if value == today else "met"
    return status, {"not_met": "This submission deadline has passed.", "unknown": "Deadline is today; confirm closing time and timezone.", "met": "The cited submission date is ahead; closing time and applicable round still need confirmation."}[status], value.isoformat()


def evaluate(criterion, quote, film, category=""):
    if not film:
        return "unknown", "A film profile is needed to evaluate this requirement."
    if criterion == "runtime": return runtime_rule(quote, film.exact_minutes, category)
    if criterion == "genre": return genre_rule(quote, film)
    if criterion == "country": return country_rule(quote, film.countries)
    if criterion == "premiere": return premiere_rule(quote, film)
    if criterion == "completion": return completion_rule(quote, film)
    return "unknown", "This rule requires review."


def decision_text(checks, deadline, film):
    required = [c for c in checks if c.get("kind", "requirement") == "requirement"]
    missing = [c.get("label") or LABELS.get(c["criterion"], c["criterion"]) for c in required if c["status"] == "unknown"]
    failed = [c.get("label") or LABELS.get(c["criterion"], c["criterion"]) for c in required if c["status"] == "not_met"]
    if failed:
        reason = "A quoted requirement conflicts with this film: " + ", ".join(failed) + "."
        steps = ["Do not submit to this category on the current evidence. Check: " + ", ".join(failed) + "."]
    else:
        reason = f"{sum(c['status'] == 'met' for c in required)} of {len(required)} extracted requirements are supported for this profile."
        steps = []
    if missing:
        reason += " Still to verify: " + ", ".join(missing) + "."
        steps.append("Verify " + ", ".join(missing) + " using complete current category rules and missing film facts.")
    if deadline and not failed:
        steps.append(f"Confirm the closing time, fee tier and category for {deadline} before applying.")
    steps.append("Check complete rules, screening rights and required materials before paying. Selection is not guaranteed.")
    return reason, steps


def validated_fee(fee, index, festival, today):
    if not fee:
        return None
    source = index.get(fee.source_id)
    if not quote_supported(fee.quote, source) or scope_issues(festival.model_copy(update={"scope_quote": ""}), source, today):
        return None
    q = fee.quote
    if not re.search(r"\b(entry|submission|submit|registration)\b", q, re.I) or re.search(r"\b(screening fee|prize|award|compensation)\b", q, re.I):
        return None
    if not re.search(rf"(?<![\d.]){re.escape(f'{fee.amount:g}')}(?:\.0+)?(?!\d|\.\d)", q):
        return None
    symbols = {"USD": r"USD|US\$", "EUR": r"EUR|€", "GBP": r"GBP|£", "INR": r"INR|₹"}
    if not re.search(symbols.get(fee.currency, re.escape(fee.currency)), q, re.I):
        return None
    return fee.model_dump(mode="json")


def validate_assessment(assessment: Assessment, sources: list[Source], today: date, film: Film | None = None) -> list[dict]:
    index = {s.id: s for s in sources if safe_url(s.url)}
    output, seen = [], set()
    for original in assessment.festivals:
        festival = original.model_copy(deep=True)
        key = (normalize(festival.name), normalize(festival.edition), normalize(festival.category))
        if festival.source_id not in index or key in seen:
            continue
        seen.add(key)
        issues = scope_issues(festival, index[festival.source_id], today)
        checks, deadline = [], None
        for criterion in Criterion:
            matches = [c for c in festival.checks if c.criterion == criterion]
            check = (matches[0].model_copy(deep=True) if len(matches) == 1 else Check(criterion=criterion, status="unknown", explanation="A unique rule was not found."))
            source = index.get(check.source_id)
            supported = quote_supported(check.quote, source)
            reason_code = "missing_evidence"
            if not supported:
                check.status, check.source_id, check.quote = "unknown", None, None
                check.explanation = "No matching quotation was found in retrieved evidence."
            else:
                check.kind = rule_kind(check.quote, "requirement")
                if criterion == Criterion.deadline:
                    check.kind = "requirement"
                scoped = not scope_issues(festival.model_copy(update={"scope_quote": ""}), source, today)
                if issues or not scoped:
                    check.status = "unknown"
                    check.explanation = "Festival, edition and category must be bound to this source before evaluating the rule."
                    reason_code = "scope_unconfirmed"
                elif check.status == "unknown":
                    # Keep uncertainty, but do not repeat a model's unsupported
                    # claim about the filmmaker's supplied facts.
                    if criterion == Criterion.deadline:
                        check.explanation = "The applicable submission deadline remains unconfirmed; verify the quoted round and conditions."
                    else:
                        local_status, explanation = evaluate(criterion.value, check.quote, film, festival.category)
                        check.explanation = explanation if local_status == "unknown" else "Applicability remains unconfirmed. " + explanation
                    reason_code = "ambiguous_rule"
                elif criterion == Criterion.deadline:
                    check.status, check.explanation, deadline = deadline_verdict(festival.deadline, check.quote, today, film)
                    reason_code = "date_rule"
                else:
                    check.status, check.explanation = evaluate(criterion.value, check.quote, film, festival.category)
                    reason_code = "evaluated" if check.status != "unknown" else "missing_fact_or_ambiguous_rule"
                # A conflicting same-edition source must remain visible. This only catches
                # directly evaluable conflicts; absence of a conflict is not a guarantee.
                if check.status in {"met", "not_met"} and criterion != Criterion.deadline:
                    opposite = "not_met" if check.status == "met" else "met"
                    for other in sources:
                        if other.id == check.source_id or scope_issues(festival.model_copy(update={"scope_quote": ""}), other, today):
                            continue
                        if any(evaluate(criterion.value, clause, film, festival.category)[0] == opposite for excerpt in other.excerpts for clause in sentences(excerpt)):
                            check.status = "unknown"
                            check.explanation = f"A directly contradictory rule appears in source {other.id}. Resolve the conflict for this edition/category."
                            reason_code = "source_conflict"
                            break
            checks.append({**check.model_dump(mode="json"), "reason_code": reason_code})
        additional = list(festival.additional_rules)
        present = {r.criterion for r in additional}
        for c in checks:
            quote = c.get("quote") or ""
            inferred = None
            if c['criterion'] == 'country' and re.search(r"\b(?:shot|filmed) in\b", quote, re.I):
                inferred = ('shooting_location', 'Shooting location', 'requirement')
            if c['criterion'] == 'genre' and re.search(r"\bpolitical\b|\bsubject matter\b|\bthematic\b", quote, re.I):
                inferred = ('theme', 'Programming relevance', 'requirement')
            if inferred and inferred[0] not in present and c.get('source_id'):
                additional.append(AdditionalRule(criterion=inferred[0], label=inferred[1], kind=inferred[2], quote=quote, source_id=c['source_id']))
                present.add(inferred[0])
        for rule in additional:
            source = index.get(rule.source_id)
            supported = quote_supported(rule.quote, source)
            scoped = supported and not issues and not scope_issues(festival.model_copy(update={"scope_quote": ""}), source, today)
            status, explanation = extra_rule(rule, film) if scoped and film else ("unknown", "A scoped source and film fact are needed for this additional condition.")
            checks.append({**rule.model_dump(mode="json"), "kind": rule_kind(rule.quote, rule.kind), "status": status, "explanation": explanation, "reason_code": "additional_rule" if scoped else "scope_unconfirmed", "source_id": rule.source_id if supported else None, "quote": rule.quote if supported else None})
        required = [c for c in checks if c["kind"] == "requirement"]
        states = [c["status"] for c in required]
        status = "not_fit" if "not_met" in states else "review_required" if issues or "unknown" in states else "likely_fit"
        item = festival.model_dump(mode="json")
        item.update(id=hashlib.sha256("|".join(key).encode()).hexdigest()[:16], checks=checks, deadline=deadline,
                    status=status, matched=states.count("met"), total=len(required), scope_issues=issues,
                    scope_status="unconfirmed" if issues else "scoped", url=index[festival.source_id].url,
                    fee=validated_fee(festival.fee, index, festival, today), deadline_timezone=None,
                    coverage_note="Only extracted rules were evaluated. Complete eligibility and source ownership require confirmation.")
        if festival.deadline_timezone and deadline:
            try:
                ZoneInfo(festival.deadline_timezone)
                deadline_check = next(c for c in checks if c["criterion"] == "deadline")
                if festival.deadline_timezone in (deadline_check.get("quote") or ""):
                    item["deadline_timezone"] = festival.deadline_timezone
            except ZoneInfoNotFoundError:
                pass
        item["reason"], item["next_steps"] = decision_text(checks, deadline, film)
        if issues:
            item["next_steps"].insert(0, "Confirm source scope: " + "; ".join(issues) + ".")
        item["unresolved"] = [c["criterion"] for c in required if c["status"] == "unknown"]
        item["blockers"] = [c["criterion"] for c in required if c["status"] == "not_met"]
        output.append(item)
    ranks = {"likely_fit": 0, "review_required": 1, "not_fit": 2}
    return sorted(output, key=lambda f: (ranks[f["status"]], bool(f["scope_issues"]), -f["matched"]))
