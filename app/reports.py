"""Versioned report data and consistent document exports."""
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

from pydantic import BaseModel, Field

from .evidence import safe_url
from .models import Fee, Film, Source

LIMITATION = "Only extracted rules were evaluated. Confirm complete current rules, category, fees and closing time before submitting. Eligibility is not a prediction of selection."
STATUS = {"likely_fit": "Potential match", "review_required": "Needs review", "not_fit": "Excluded"}


class ReportCheck(BaseModel):
    criterion: str = Field(max_length=100)
    label: str = Field(default="", max_length=100)
    status: Literal["met", "not_met", "unknown"]
    kind: Literal["requirement", "preference", "procedural"] = "requirement"
    explanation: str = Field(default="", max_length=1500)
    quote: str | None = Field(default=None, max_length=2400)
    source_id: str | None = Field(default=None, max_length=40)
    reason_code: str = Field(default="", max_length=100)


class ReportFestival(BaseModel):
    id: str = Field(default="", max_length=100)
    name: str = Field(max_length=160)
    edition: str = Field(default="", max_length=80)
    category: str = Field(max_length=140)
    status: Literal["likely_fit", "review_required", "not_fit"]
    reason: str = Field(max_length=2400)
    deadline: str | None = Field(default=None, max_length=40)
    deadline_timezone: str | None = Field(default=None, max_length=80)
    fee: Fee | None = None
    url: str = Field(default="", max_length=2500)
    source_id: str = Field(default="", max_length=40)
    checks: list[ReportCheck] = Field(max_length=24)
    next_steps: list[str] = Field(default_factory=list, max_length=10)
    scope_issues: list[str] = Field(default_factory=list, max_length=8)
    scope_status: str = Field(default="unconfirmed", max_length=30)
    coverage_note: str = Field(default=LIMITATION, max_length=1000)
    matched: int = Field(ge=0, le=24)
    total: int = Field(ge=0, le=24)
    unresolved: list[str] = Field(default_factory=list, max_length=24)
    blockers: list[str] = Field(default_factory=list, max_length=24)


class TraceStep(BaseModel):
    stage: str = Field(max_length=40)
    detail: str = Field(max_length=1200)
    seconds: float = Field(default=0, ge=0, le=100000, allow_inf_nan=False)


class ResearchReport(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    report_id: str = Field(default="", max_length=100)
    mode: Literal["sample", "live"]
    film: Film
    created_at: str = Field(max_length=80)
    research_mode: Literal["quick", "detailed"] = "quick"
    completion: Literal["complete", "partial"] = "complete"
    festivals: list[ReportFestival] = Field(max_length=12)
    sources: list[Source] = Field(max_length=30)
    trace: list[TraceStep] = Field(default_factory=list, max_length=30)
    search_queries: list[str] = Field(default_factory=list, max_length=10)
    duration_seconds: float = Field(default=0, ge=0, le=100000, allow_inf_nan=False)
    followup: dict = Field(default_factory=dict)
    enrichment: dict = Field(default_factory=dict)
    model: str = Field(default="", max_length=120)
    backend: str = Field(default="", max_length=30)


class ExportRequest(BaseModel):
    report: ResearchReport
    format: Literal["md", "pdf", "csv", "json"]
    selected_ids: list[str] | None = Field(default=None, max_length=12)
    include_synopsis: bool = False
    include_evidence: bool = True


def canonical_report(data):
    report = ResearchReport.model_validate(data)
    if not report.report_id:
        report.report_id = hashlib.sha256((report.created_at + report.film.title + report.mode).encode()).hexdigest()[:24]
    for f in report.festivals:
        if not f.id:
            f.id = hashlib.sha256((f.name + f.edition + f.category).encode()).hexdigest()[:16]
    return report.model_dump(mode="json")


def export_data(request):
    data = canonical_report(request.report)
    if request.selected_ids is not None:
        data["festivals"] = [f for f in data["festivals"] if f["id"] in request.selected_ids]
    if not data["festivals"]:
        raise ValueError("Select at least one candidate to export.")
    if not request.include_synopsis:
        data["film"]["synopsis"] = ""
    data["export_scope"] = "Selected shortlist" if request.selected_ids is not None else "All researched candidates"
    data["limitation"] = LIMITATION
    return data


def profile_lines(film):
    lines = [("Title", film['title']), ("Story / medium", f"{film['genre']} / {film['medium']}"),
             ("Runtime including credits", f"{film['runtime_minutes']} min {film['runtime_seconds']:02d} sec"),
             ("Production countries", ", ".join(film['production_countries']) or film['country']),
             ("Completion", f"{film['completed_on']} ({film['completion_status']})"),
             ("Premiere status", film['premiere_status'])]
    labels = {'shooting_countries': 'Shooting countries', 'languages': 'Original languages',
              'subtitles': 'Available subtitles', 'region': 'Preferred regions', 'goals': 'Campaign goals',
              'submission_until': 'Submission horizon', 'focus_festival': 'Research focus', 'synopsis': 'Synopsis'}
    for key, label in labels.items():
        value = film.get(key)
        if value: lines.append((label, ', '.join(value) if isinstance(value, list) else str(value)))
    lines.append(('Student filmmaker', {'yes': 'Yes', 'no': 'No', 'unknown': 'Not specified'}[film['student_status']]))
    for key, label in [('budget', 'Entry budget'), ('max_fee', 'Maximum entry fee')]:
        if film.get(key) is not None: lines.append((label, f"{film[key]:g} {film['currency']}"))
    lines.append(('Prior submissions', ', '.join(film['prior_submissions']) or ('None declared; list confirmed complete' if film['prior_submissions_known'] else 'Not confirmed')))
    for i, s in enumerate(film['screenings'], 1):
        lines.append((f'Screening / release {i}', f"{s['date'] or 'Date unspecified'} · {s['kind']} · {s['territory'] or 'Territory unspecified'} · {'public' if s['public'] else 'private'}" + (f" · {s['notes']}" if s['notes'] else '')))
    return lines


def md_text(value):
    return re.sub(r"([\\`*_{}\[\]<>#!|])", r"\\\1", str(value)).replace("\r", "").replace("\n", " ")


def research_summary(data):
    if data['mode'] == 'sample': return ['Fictional demonstration. No provider calls were made.']
    lines = [f"Research: {data['research_mode']}; {data['completion']}. Only retrieved rules were evaluated."]
    enrichment = data.get('enrichment', {})
    if enrichment.get('requested'):
        lines.append(f"Fuller source pages: {enrichment.get('pages', 0)}; {str(enrichment.get('status', 'unavailable')).replace('_', ' ')}.")
    followup = data.get('followup', {})
    if followup.get('attempted'):
        lines.append(f"Follow-up: {str(followup.get('status', 'unknown')).replace('_', ' ')}; {followup.get('resolved_checks', 0)} previously unknown checks resolved. This is not an accuracy score.")
    return lines


def markdown(data, evidence=True):
    lines = [f"# FestivalFit — {md_text(data['film']['title'])}", "", "**FICTIONAL SAMPLE. No live research.**" if data["mode"] == "sample" else "**Research report — verify current official rules before submission.**", "", f"Report: {data['report_id']} · Schema {data['schema_version']}", f"Created: {data['created_at']} · {data['research_mode']} · {data['completion']}", f"Scope: {data['export_scope']}", "", LIMITATION, "", "## Film profile", ""]
    lines += [f"- **{md_text(k)}:** {md_text(v)}" for k, v in profile_lines(data["film"])]
    sources = {s['id']: s for s in data['sources']}
    for f in data["festivals"]:
        fee = f['fee']
        lines += ["", f"## {md_text(f['name'])}", f"{md_text(f['edition'] or 'Edition unconfirmed')} · {md_text(f['category'])}", "", f"**{STATUS[f['status']]}** · {f['matched']}/{f['total']} extracted requirements supported", "", md_text(f["reason"]), "", f"Deadline: {f['deadline'] or 'Unconfirmed'}; timezone: {md_text(f['deadline_timezone'] or 'unconfirmed')}", f"Entry fee: {fee['amount']:g} {fee['currency']} ({md_text(fee['tier'])})" if fee else "Entry fee: unconfirmed", ""]
        lines += [f"- Scope issue: {md_text(issue)}" for issue in f["scope_issues"]]
        if fee:
            if evidence: lines += [f"> Fee evidence: {md_text(fee['quote'])}"]
            source = sources.get(fee['source_id'])
            if source and safe_url(source['url']): lines += [f"Fee source [{md_text(source['id'])}](<{source['url']}>)"]
        for c in f['checks']:
            lines += [f"- **{md_text(c['label'] or c['criterion'])}** [{c['kind']}] — {c['status']}: {md_text(c['explanation'])}"]
            if evidence and c.get('quote'):
                lines += [f"  > {md_text(c['quote'])}"]
            source = sources.get(c.get('source_id'))
            if source and safe_url(source['url']):
                lines += [f"  Source [{md_text(source['id'])}](<{source['url']}>) · retrieved {source.get('retrieved_at') or 'not recorded'}"]
        lines += ["", "Next actions:"] + [f"- {md_text(s)}" for s in f['next_steps']]
    lines += ["", "## Research scope", *[md_text(line) for line in research_summary(data)], "", "## Sources"]
    for s in data['sources']:
        if safe_url(s['url']):
            lines += [f"- [{md_text(s['id'] + ' · ' + s['title'])}](<{s['url']}>) — retrieved {s.get('retrieved_at') or 'not recorded'}; {s['retrieval']}; hash {s.get('content_hash') or 'not recorded'}"]
    return "\n".join(lines) + "\n"


def csv_report(data):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    def cell(v):
        text = "" if v is None else str(v)
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r")) else text
    writer.writerow(["Report type", "Report ID", "Created", "Completion", "Film", "Festival", "Edition", "Category", "Decision", "Deadline", "Timezone", "Fee amount", "Currency", "Fee tier", "Blockers / unknowns", "Source", "Limitations"])
    for f in data['festivals']:
        fee = f['fee'] or {}
        gaps = "; ".join((c['label'] or c['criterion']) + ": " + c['status'] for c in f['checks'] if c['status'] != 'met' and c['kind'] == 'requirement')
        writer.writerow(map(cell, ["FICTIONAL SAMPLE" if data['mode'] == 'sample' else 'Live research', data['report_id'], data['created_at'], data['completion'], data['film']['title'], f['name'], f['edition'], f['category'], STATUS[f['status']], f['deadline'], f['deadline_timezone'] or 'Unconfirmed', fee.get('amount'), fee.get('currency'), fee.get('tier'), gaps, f['url'], LIMITATION]))
    return out.getvalue()


def pdf_report(data, evidence=True):
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
    fontdir = Path(reportlab.__file__).parent / 'fonts'
    if 'FestivalBody' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('FestivalBody', str(fontdir / 'Vera.ttf')))
        pdfmetrics.registerFont(TTFont('FestivalBold', str(fontdir / 'VeraBd.ttf')))
    ink, muted = colors.HexColor('#2d263b'), colors.HexColor('#655d6f')
    body = ParagraphStyle('Body', fontName='FestivalBody', fontSize=9.2, leading=13, textColor=ink, spaceAfter=5, splitLongWords=True)
    small = ParagraphStyle('Small', parent=body, fontSize=8.3, leading=11, textColor=muted, spaceAfter=4)
    heading = ParagraphStyle('Heading', parent=body, fontName='FestivalBold', fontSize=18, leading=23, spaceAfter=14)
    sub = ParagraphStyle('Sub', parent=body, fontName='FestivalBold', fontSize=11, leading=16, spaceBefore=10, keepWithNext=True)
    rulehead = ParagraphStyle('Rule', parent=sub, fontSize=9.2, leading=12, spaceBefore=9, spaceAfter=4)
    def p(text, style=body):
        return Paragraph(escape(str(text)).replace('\n', '<br/>'), style)
    def link(url, text):
        if not safe_url(url): return p(text, small)
        return Paragraph(f'<link href="{escape(url, {chr(34): "&quot;"})}" color="#705488">{escape(text)}</link>', small)
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=53, bottomMargin=48, title='FestivalFit decision report', author='FestivalFit')
    story = [p('FESTIVALFIT / DECISION REPORT', small), Spacer(1, 10), p(data['film']['title'], heading), p('FICTIONAL SAMPLE - no live research.' if data['mode'] == 'sample' else 'Research to support your next submission.'), p(f"{data['created_at']} | {data['research_mode']} | {data['completion']} | {data['export_scope']}", small), p(LIMITATION, small), p('Decision overview', sub)]
    rows = [[p('Festival / category', small), p('Decision', small), p('Deadline / fee', small)]]
    for f in data['festivals']:
        fee = f['fee']
        rows.append([p(f"{f['name']}\n{f['edition'] or 'Edition unconfirmed'} · {f['category']}", small), p(STATUS[f['status']], small), p(f"{f['deadline'] or 'Date unconfirmed'}\n" + (f"{fee['amount']:g} {fee['currency']}" if fee else 'Fee unconfirmed'), small)])
    table = Table(rows, colWidths=[240, 100, 171], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eee8f4')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#dfdbe4')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story += [table, p('Film profile used for this report', sub)]
    profile_rows = [[p(k, small), p(v, small)] for k, v in profile_lines(data['film'])]
    profile = Table(profile_rows, colWidths=[140, 371], hAlign='LEFT')
    profile.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
    story.append(profile)
    sources = {s['id']:s for s in data['sources']}
    for f in data['festivals']:
        story += [PageBreak(), p(f['name'], heading), p(f"{f['edition'] or 'Edition unconfirmed'} / {f['category']}"), p(f"{STATUS[f['status']]} - {f['matched']}/{f['total']} extracted requirements supported", sub), p(f['reason']), p(f"Deadline: {f['deadline'] or 'unconfirmed'}; timezone: {f['deadline_timezone'] or 'unconfirmed'}", small)]
        fee = f['fee']
        story.append(p(f"Entry fee: {fee['amount']:g} {fee['currency']} - {fee['tier']}" if fee else 'Entry fee: unconfirmed', small))
        if fee:
            source = sources.get(fee['source_id'])
            fee_parts = [p('Fee evidence: ' + fee['quote'], small)] if evidence else []
            if source: fee_parts.append(link(source['url'], f"Fee source {source['id']}"))
            story.append(KeepTogether(fee_parts))
        for issue in f['scope_issues']: story.append(p('Scope: ' + issue))
        for c in f['checks']:
            block = [p(f"{c['label'] or c['criterion'].replace('_',' ').capitalize()} / {c['kind']} / {c['status'].replace('_',' ')}", rulehead), p(c['explanation'])]
            if evidence and c.get('quote'): block.append(p('“' + c['quote'] + '”', small))
            source = sources.get(c.get('source_id'))
            if source:
                block.append(link(source['url'], f"Source {source['id']} · retrieved {source.get('retrieved_at') or 'not recorded'}"))
            story.append(KeepTogether(block))
        story.append(p('Your next actions', sub))
        for i, action in enumerate(f['next_steps'],1): story.append(p(f'{i}. {action}'))
    story += [PageBreak(), p('Sources and research scope', heading), p(f"Report {data['report_id']} / schema {data['schema_version']}", small)]
    story += [p(line, small) for line in research_summary(data)]
    for s in data['sources']:
        story.append(KeepTogether([p(f"{s['id']} - {s['title']}", sub), link(s['url'], s['url']), p(f"Retrieved {s.get('retrieved_at') or 'not recorded'} / {s['retrieval']}", small), p(f"Content hash: {s.get('content_hash') or 'not recorded'}", small)]))
    def footer(canvas, document):
        canvas.saveState(); canvas.setFont('FestivalBody',8); canvas.setFillColor(muted)
        canvas.drawString(42, 25, 'FestivalFit · ' + ('Fictional sample' if data['mode']=='sample' else 'Verify current official rules'))
        canvas.drawRightString(A4[0]-42,25,str(document.page)); canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


def render_export(request):
    data = export_data(request)
    if request.format == 'pdf': return pdf_report(data, request.include_evidence), 'application/pdf'
    if request.format == 'csv': return csv_report(data).encode('utf-8-sig'), 'text/csv; charset=utf-8'
    if request.format == 'json': return json.dumps(data, indent=2, ensure_ascii=False).encode(), 'application/json'
    return markdown(data, request.include_evidence).encode(), 'text/markdown; charset=utf-8'
