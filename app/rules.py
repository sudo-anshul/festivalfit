"""Conservative predicates over quoted rules; uncertain semantics stay explicit."""
import re
from datetime import date, datetime

from .models import Film


def fold(text):
    return re.sub(r"[^\w]+", " ", text.casefold()).strip()


def sentences(text):
    return [s.strip() for s in re.split(r"[;\n]|(?<=[.!?])\s+(?=[A-Z])", text) if s.strip()]


def rule_kind(quote, proposed="requirement"):
    mandatory = r"\b(?:must|required|have to|not eligible|ineligible|not (?:be )?(?:accepted|considered|permitted)|cannot|shall not)\b"
    if re.search(r"\b(prefer(?:red|ence|ably)?|priority|encouraged|welcomed|desirable)\b", quote, re.I) and not re.search(mandatory, quote, re.I):
        return "preference"
    # An extraction cannot soften an explicitly mandatory rule.
    if re.search(mandatory, quote, re.I):
        return "requirement"
    return proposed


def runtime_rule(quote, minutes, category=""):
    if re.search(r"\b(?:long|feature)\s+fiction\b", quote, re.I) and re.search(r"\bshort\s+fiction\b", quote, re.I):
        # A common numbered-category format permits an exact local clause.
        # Never apply its short limit to another category from the same page.
        short_clause = re.search(r"\bshort\s+fiction\s*\(([^)]+)\)", quote, re.I)
        if short_clause and re.match(r"^short fiction(?:\s|$)", fold(category)):
            return runtime_rule(short_clause.group(1), minutes)
        return "unknown", "Mixed long/short fiction rules require a quoted boundary for the selected category."
    values = set(re.findall(r"\b(\d+(?:\.\d+)?)\s*[-–]?\s*min(?:ute)?s?\b", quote, re.I))
    if re.search(r"\b(?:not|no|cannot)\s+(?:(?:be|run)\s+)?(?:under|less than|shorter than)\b", quote, re.I):
        return "unknown", "This minimum/negated duration rule needs category review."
    ranges = list(re.finditer(r"\b(\d+(?:\.\d+)?)\s*(?:min(?:ute)?s?\s*)?(?:[-–]|to)\s*(\d+(?:\.\d+)?)\s*min(?:ute)?s?\b", quote, re.I))
    if len(ranges) == 1 and not re.search(r"\b(features?|between)\b", quote, re.I) and len(values) <= 2:
        low, high = map(float, ranges[0].groups())
        return ("met" if low <= minutes <= high else "not_met"), f"Runtime {minutes:g} min; quoted range {low:g}–{high:g} min."
    if len(values) > 1 or re.search(r"\bfeatures?\b.*\bshorts?\b|\bshorts?\b.*\bfeatures?\b", quote, re.I):
        return "unknown", "Multiple duration/category rules appear together. Isolate the applicable category."
    patterns = [
        (r"(?:under|less than|shorter than)\s+(\d+(?:\.\d+)?)\s*[-–]?\s*min(?:ute)?s?\b", False),
        (r"(?:no longer than|not (?:exceed|exceeding)|up to|at most|maximum(?: runtime| length)?(?: of| is|:)?|limited to)\s+(?:the\s+)?(\d+(?:\.\d+)?)\s*[-–]?\s*min(?:ute)?s?\b", True),
    ]
    limits = {(float(m.group(1)), inc) for p, inc in patterns for m in re.finditer(p, quote, re.I)}
    if len(limits) != 1:
        return "unknown", "A category-specific numerical runtime boundary was not established."
    limit, inclusive = limits.pop()
    met = minutes <= limit if inclusive else minutes < limit
    return ("met" if met else "not_met"), f"Runtime {minutes:g} min; quoted limit {'at most' if inclusive else 'under'} {limit:g} min, including the supplied seconds."


def extract_dates(text):
    patterns = [r"\b20\d{2}-\d{2}-\d{2}\b", r"\b[A-Z][a-z]+\.?\s+\d{1,2}(?:\s*(?:st|nd|rd|th))?,?\s+20\d{2}\b", r"\b\d{1,2}(?:\s*(?:st|nd|rd|th))?\s+[A-Z][a-z]+\.?,?\s+20\d{2}\b"]
    result = []
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            value = re.sub(r"(\d)\s*(st|nd|rd|th)\b", r"\1", m.group(), flags=re.I)
            value = re.sub(r"\bSept\b", "Sep", value, flags=re.I).replace(".", "").replace(",", "")
            for fmt in ("%Y-%m-%d", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"):
                try:
                    result.append((datetime.strptime(value, fmt).date(), m.start(), m.end()))
                    break
                except ValueError:
                    pass
    return sorted(set(result), key=lambda x: x[1])


def completion_rule(quote, film):
    if film.completion_status != "completed":
        return "unknown", "Completion is planned; confirm whether this category accepts work in progress."
    dates = extract_dates(quote)
    if len(dates) != 1 or not re.search(r"\b(complet(?:ed|ion)|produc(?:ed|tion)|made)\b", quote, re.I):
        return "unknown", "A precise applicable completion window was not established."
    boundary, start, _ = dates[0]
    before = quote[:start].casefold()
    if re.search(r"\b(?:not|except|unless)\b", before):
        return "unknown", "The completion window contains a negation or exception that needs review."
    if re.search(r"(?:on or after|since|from)\s*$", before):
        met = film.completed_on >= boundary
    elif re.search(r"after\s*$", before):
        met = film.completed_on > boundary
    elif re.search(r"(?:on or before|by)\s*$", before):
        met = film.completed_on <= boundary
    elif re.search(r"before\s*$", before):
        met = film.completed_on < boundary
    else:
        return "unknown", "The completion date is present but its operator or condition needs review."
    return ("met" if met else "not_met"), f"Completion {film.completed_on.isoformat()} compared with the quoted {boundary.isoformat()} boundary."


def genre_rule(quote, film):
    kinds = {"Fiction": r"fiction|narrative", "Documentary": r"documentar(?:y|ies)", "Animation": r"animation|animated", "Experimental": "experimental", "Music video": "music videos?", "Other": "other"}
    pattern = rf"\b(?:{kinds[film.genre]})\b"
    for clause in sentences(quote):
        if re.search(pattern, clause, re.I) and re.search(r"\b(?:not (?:eligible|accepted|permitted)|ineligible|exclude[ds]?|do not accept|no fiction|no documentaries)\b", clause, re.I):
            return "not_met", "The quoted rule explicitly excludes this film type."
    if re.search(r"\b(?:all|any)\s+(?:kinds?(?: of films)?|genres?|types?(?: of films)?|forms?)\b", quote, re.I):
        return "met", "The quotation explicitly permits all film types."
    if re.search(pattern, quote, re.I) and re.search(r"\b(accepts?|accepted|open|eligible|welcome[ds]?|permitted|showcases)\b", quote, re.I):
        return "met", f"The quoted category explicitly accepts {film.genre.lower()}."
    return "unknown", "A generic short-film call does not establish this film type's eligibility."


def country_rule(quote, countries):
    for clause in sentences(quote):
        mentions = [country for country in countries if re.search(rf"\b{re.escape(country)}\b", clause, re.I)]
        if mentions and re.search(r"\b(not eligible|ineligible|not accepted|excluded|do not accept)\b", clause, re.I):
            return "not_met", "The source explicitly excludes a supplied production country."
    if re.search(r"\b(?:all|any)\s+countr(?:y|ies)\b|\bworldwide\b|\b(?:across|around|over)\s+the\s+(?:world|globe)\b", quote, re.I) and not re.search(r"\b(except|excluding|unless|not eligible)\b", quote, re.I):
        return "met", "The source explicitly permits entries across countries."
    if all(re.search(rf"\b{re.escape(c)}\b", quote, re.I) for c in countries) and re.search(r"\b(films?|productions?)\b.{0,80}\b(?:from|produced|made)\b|\b(?:from|produced|made)\b.{0,80}\b(films?|productions?)\b", quote, re.I) and re.search(r"\b(accepted|accepts?|eligible|open|welcome[ds]?)\b", quote, re.I):
        if re.search(r"\b(shot|filmed|subject matter|relevance|residenc|nationalit)\w*\b", quote, re.I):
            return "unknown", "Production country alone does not answer the additional geographic or thematic condition."
        return "met", "The quoted production-country rule includes the supplied countries."
    return "unknown", "The production-country rule is not explicit for all supplied countries. Filmmaker nationality and shooting location are separate facts."


def premiere_rule(quote, film):
    if re.search(r"\bno\s+(?:formal\s+)?premiere\s+(?:requirements?|restrictions?)\b|does not have a (?:formal )?premiere requirement|premiere (?:status )?(?:is )?not required", quote, re.I):
        return "met", "The quoted category has no premiere restriction."
    if film.premiere_status == "Unknown":
        return "unknown", "Add the film's screening/release history to evaluate this rule."
    has_public = any(s.public and s.kind != "private" for s in film.screenings)
    if re.search(r"\bworld premiere\b|\bnever\s+(?:been\s+)?(?:publicly\s+)?screened\b", quote, re.I):
        if film.premiere_status in {"Already screened at a festival", "Publicly available online"} or has_public:
            return "not_met", "A public screening/release conflicts with the quoted world-premiere requirement."
        if film.premiere_status == "World premiere available":
            return "met", "Declared world-premiere availability meets the quoted requirement; all screening history must be included."
    return "unknown", "Territorial/private/online premiere conditions require the full rule and matching screening history."


def extra_rule(rule, film):
    q = rule.quote
    criterion = rule.criterion
    if criterion == "subtitles":
        if not film.subtitles:
            return "unknown", "Add available subtitle languages."
        if re.search(r"\bEnglish\s+subtitles?\b|\bsubtitled\s+in\s+English\b", q, re.I):
            return ("met" if any(s.casefold() == "english" for s in film.subtitles) else "not_met"), "Compared the explicit English-subtitle rule with the supplied subtitle languages."
    if criterion == "shooting_location":
        if re.search(r"\b(?:not|except|excluding|unless)\b", q, re.I):
            return "unknown", "The shooting-location rule contains an exclusion or exception; confirm its scope."
        if film.shooting_countries and all(re.search(rf"\b{re.escape(c)}\b", q, re.I) for c in film.shooting_countries) and re.search(r"\b(?:shot|filmed) in\b", q, re.I):
            return "met", "The supplied shooting countries are explicitly included in the quoted location rule."
        return "unknown", "Confirm the exact shooting territory against this rule." if film.shooting_countries else "Add shooting countries; production country does not establish filming location."
    if criterion == "prior_submission":
        if film.prior_submissions_known and not film.prior_submissions and re.search(r"\b(?:submitted|submission)\b", q, re.I) and re.search(r"\b(?:earlier|previous|again|resubmit)\b", q, re.I):
            return "met", "The filmmaker explicitly confirmed no previous festival submissions."
        return "unknown", "Confirm the outcome/category of the film's earlier submission to this festival." if film.prior_submissions_known else "Confirm whether this film was previously submitted to this festival."
    if criterion == "student":
        if film.student_status == "unknown":
            return "unknown", "Add student status if targeting this category."
        if re.search(r"\bonly\s+(?:by\s+)?students?\b|\bmust be (?:a )?students?\b|\bstudents? only\b", q, re.I):
            return ("met" if film.student_status == "yes" else "not_met"), "Compared the explicit student-only rule with the declared status."
    if criterion == "online_release" and (re.search(r"\b(not|no|never)\b.{0,70}\b(online|internet)\b", q, re.I) or re.search(r"\bonline\b.{0,70}\bnot be considered\b", q, re.I)):
        if film.premiere_status == "Publicly available online" or any(s.kind == "online" and s.public for s in film.screenings):
            return "unknown", "The film has an online release; confirm territories and exceptions before treating this rule as met."
        if film.premiere_status == "World premiere available":
            return "met", "No public release is declared; preserve that condition until submission."
    return "unknown", "This condition needs a filmmaker answer or a review of the complete scoped rule."
