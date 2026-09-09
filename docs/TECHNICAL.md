# Technical notes

[← Back to FestivalFit](../README.md)

## Evidence boundaries

“Potential match” means the extracted mandatory checks are supported for the supplied profile. It does **not** mean every rule was found or that the festival will select the film.

Explicit runtime bounds include seconds; completion boundaries retain their operators. Country, genre, premiere and supported additional conditions are evaluated conservatively. Requirements and preferences remain distinct, including mixed quotes containing a mandatory restriction. Deadline checks reject event/notification dates and incompatible supported completion windows. Directly evaluable contradictions from another scoped source remain unresolved.

Scope checks use retrieved text and category/edition labels; they do not establish publisher ownership or fully understand every section, exception or regional definition. The engine retains six core checks plus extracted additional rules, rather than a complete universal festival-rules ontology. Ambiguous language, private screenings, territorial premieres and omitted requirements still need human review.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Public health check |
| `GET /api/status` | Configuration presence, without secret values |
| `GET /api/sample` | Canonical fictional report |
| `POST /api/match` | Film profile → newline-delimited progress, partial report and final report |
| `POST /api/export` | Canonical report + format/scope → PDF, Markdown, CSV or JSON download |

Live requests use `X-Access-Code` when a code is configured. On Cloud Run, live research stays disabled until a code is configured. Sample and export routes are public. Report uploads are limited to 1.5 MB.

## Limits and privacy

Film details go to Google; relevant search terms go to Parallel. The server does not persist profiles or reports. Explicitly saved drafts/reports live in this browser's local storage until deleted or browser data is cleared. There is no cloud sync. Provider retention policies still apply. Access codes are not saved with reports. The app never submits films or makes payments.

The planning budget is a separate scenario; it does not rewrite the original research profile. Re-save the report to retain updated choices and budget. Exports preserve the original report snapshot. Synopsis omission removes that profile field; it is not an automatic confidential-text redactor for evidence or search queries.

PDF embeds Latin-script fonts; non-Latin font shaping has not been validated. Markdown/JSON retain Unicode text. Entry fees have no implicit currency conversion, and missing fees never mean zero.

Hourly and concurrency limits are per process, reset on restart, and **are not a global quota or spending cap**. Serverless instances have separate counters. Unrestricted public production use needs shared limits and provider quota management.

Google Cloud and provider usage may cost money. Eligible Cloud Free Trial credits can cover Cloud Run, build/storage services and Google Gemini on Vertex AI; this does not make Vertex inference an unlimited free service. AI Studio's Gemini Developer API has separate billing and free-tier limits. Parallel credits are also separate. See [cost controls](../SETUP.md#cost-controls).
