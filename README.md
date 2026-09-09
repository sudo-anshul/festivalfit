# FestivalFit

Find your next audience. FestivalFit helps independent filmmakers build a submission shortlist from cited festival rules, then compare deadlines, fees and unresolved conditions before committing money.

The fictional sample needs no credentials. Live research on Google Cloud Run requires a private demo code.

## Decision workspace

- **Film profile:** exact minutes and seconds, story type and medium, co-production and shooting countries, languages/subtitles, screening history, prior submissions, student status, goals and entry budget.
- **Research:** Quick shortlist, Detailed verification, or a focused recheck of a festival. Detailed mode retrieves fuller text from up to three promising pages.
- **Report:** edition/category context, supported requirements, blockers, preferences, open questions, source quotations, fees and closing-date uncertainty.
- **Compare & plan:** compare up to four candidates, save a shortlist, and see known entry fees summed separately by currency. Unknown fees and additional platform/travel/delivery costs remain explicit.
- **Portable research:** generated PDF, Markdown, CSV and JSON from one versioned report. Choose all candidates or the saved shortlist; synopsis inclusion is opt-in.
- **Recovery:** partial findings, cancellation, previous-report preservation, browser-local drafts and up to eight explicitly saved reports/plans.

The sample uses invented festivals, fees and rules and remains labeled as fictional in the interface and exports.

## Run locally

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
uv sync --frozen
cp .env.example .env
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765. Use the fictional sample immediately. The example selects Vertex AI; configure your Cloud project and Application Default Credentials for live research. To use an AI Studio key locally, select `GEMINI_BACKEND=developer` and set `GEMINI_API_KEY`. Both backends need `PARALLEL_API_KEY`. See [SETUP.md](SETUP.md).

No new service or credential is required for Detailed verification or document exports beyond the existing provider access. Parallel Extract availability and provider quotas still depend on the account. Extraction failure preserves search evidence.

## Architecture

Plain HTML, CSS and JavaScript → FastAPI on Cloud Run → Google Gen AI SDK calling Gemini on Vertex AI + Parallel SDK calling Search and Extract. Cloud Run uses its service identity for Vertex and Secret Manager for the Parallel key and private demo code. ReportLab creates PDF documents in a worker thread.

1. Gemini plans searches from a fixed film snapshot and the current UTC date.
2. Parallel Search returns pages/excerpts; Detailed mode also requests full-page extraction for up to three sources.
3. Gemini extracts scoped candidates, the six core checks and additional material rules.
4. Local validation checks quotation presence, festival/edition/category context and supported rule predicates. It derives decisions and next steps from validated checks.
5. A partial report becomes available before one bounded follow-up investigates gaps or alternatives. Final and partial reports use the same report ID and schema version.
6. The browser renders the canonical report and can explicitly save a local copy. Every export uses that same snapshot, rather than generating another model-written report.

Both modes have a **180-second total request limit**. A run uses at most two logical searches, one optional Extract request, and three logical Gemini calls; SDK retries can add provider attempts. Up to 20 source pages are retained. Keep the tab connected: this release does not implement durable background jobs or leave-and-return research. Closing a tab does not create a resumable job.

## Evidence boundaries

“Potential match” means the extracted mandatory checks are supported for the supplied profile. It does **not** mean every rule was found or that the festival will select the film.

Explicit runtime bounds include seconds; completion boundaries retain their operators. Country, genre, premiere and supported additional conditions are evaluated conservatively. Requirements and preferences remain distinct, including mixed quotes containing a mandatory restriction. Deadline checks reject event/notification dates and incompatible supported completion windows. Directly evaluable contradictions from another scoped source remain unresolved.

Scope checks use retrieved text and category/edition labels; they do not establish publisher ownership or fully understand every section, exception or regional definition. The engine retains six core checks plus extracted additional rules, rather than a complete universal festival-rules ontology. Ambiguous language, private screenings, territorial premieres and omitted requirements still need human review.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /healthz` | Health check |
| `GET /api/status` | Configuration presence, without secret values |
| `GET /api/sample` | Canonical fictional report |
| `POST /api/match` | Film profile → newline-delimited progress, partial report and final report |
| `POST /api/export` | Canonical report + format/scope → PDF, Markdown, CSV or JSON download |

Live requests use `X-Access-Code` when a code is configured. On Cloud Run, live research stays disabled until a code is configured. Sample and export routes are public. Report uploads are limited to 1.5 MB.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 uv run pytest -q
node --check app/static/app.js
```

**126 tests pass** in the recorded local release check. Coverage includes adverse evidence cases with positive controls, actual SDK serialization through mock transports, Extract failure fallback, partial streaming, access control, export scope/privacy defaults and spreadsheet-formula protection. Two local Detailed-verification calls each completed in 15.6 seconds with 17 sources and three expanded pages. Browser checks covered mobile layouts, draft/plan restoration, controlled cancellation/failure recovery and completed downloads in all four formats. These observations are not an accuracy or production-reliability benchmark.

## Deploy

Deploy the Dockerfile with Cloud Build and Cloud Run using [scripts/deploy-cloud-run.sh](scripts/deploy-cloud-run.sh). The upload includes only the runtime application, Dockerfile and locked requirements. Defaults are zero minimum instances, one maximum instance, request-based CPU billing and a 240-second host timeout. No database or frontend build step is required. [Deployment instructions](SETUP.md#deploy-to-google-cloud-run).

## Limits and privacy

Film details go to Google; relevant search terms go to Parallel. The server does not persist profiles or reports. Explicitly saved drafts/reports live in this browser's local storage until deleted or browser data is cleared. There is no cloud sync. Provider retention policies still apply. Access codes are not saved with reports. The app never submits films or makes payments.

The planning budget is a separate scenario; it does not rewrite the original research profile. Re-save the report to retain updated choices and budget. Exports preserve the original report snapshot. Synopsis omission removes that profile field; it is not an automatic confidential-text redactor for evidence or search queries.

PDF embeds Latin-script fonts; non-Latin font shaping has not been validated. Markdown/JSON retain Unicode text. Entry fees have no implicit currency conversion, and missing fees never mean zero.

Hourly and concurrency limits are per process, reset on restart, and **are not a global quota or spending cap**. Serverless instances have separate counters. Unrestricted public production use needs shared limits and provider quota management.

Google Cloud and provider usage may cost money. Eligible Cloud Free Trial credits can cover Cloud Run, build/storage services and Google Gemini on Vertex AI; this does not make Vertex inference an unlimited free service. AI Studio's Gemini Developer API has separate billing and free-tier limits. Parallel credits are also separate. See [cost controls](SETUP.md#cost-controls).

## License

[MIT License](LICENSE).
