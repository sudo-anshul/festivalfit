# Verification record

[← Back to FestivalFit](../README.md)

These are recorded release checks from September 9, 2026. They establish that the exercised paths worked; they do not establish festival-selection accuracy, exhaustive rule extraction, average latency or production reliability.

## Automated checks

The recorded migration check passed **126 tests**. Coverage includes adverse evidence cases with positive controls, SDK serialization through mocked transports, Extract failure fallback, partial streaming, access control, export privacy/scope and spreadsheet-formula protection.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 uv run --frozen pytest -q
node --check app/static/app.js
```

## Hosted research

Executed against Cloud Run revision `festivalfit-00002-x98`, with Gemini `gemini-3.5-flash-lite` on Vertex AI and the real Parallel APIs. The film was an example 18-minute Indian fiction short, completed July 1, 2026, with a world premiere available and English subtitles.

| Observation | Quick | Detailed |
| --- | ---: | ---: |
| Wall time for this single run | 17.0 seconds | 18.9 seconds |
| Retained source pages | 18 | 18 |
| Festival candidates | 2 | 2 |
| Pages expanded by Extract | Not requested | 3 |
| Partial report received | Yes | Yes |
| Completed final report | Yes | Yes |

The two observations are not a controlled performance comparison. Search results, film profiles, provider load and quotas can change the work performed and time required. A completed report can still contain unresolved requirements.

Additional hosted checks verified health/configuration endpoints, byte-matched frontend assets, security headers, missing/incorrect access-code rejection, fictional sample labeling, PDF/Markdown/CSV/JSON responses, default synopsis omission, selected-shortlist scope and inaccessible local configuration/git paths.

The diagram's numbers are recorded here for inspection, rather than presented as live CI or ongoing monitoring.

## Browser compatibility

After the Firefox wordmark fix in commit `ed465d66b0838fca62de2573348ca5142d5dbe31`, Firefox and Chrome were compared on the hosted site at widths **320, 390, 640, 760, 768, 840, 1024, 1100, 1320 and 1440 pixels**. The wordmark remained on one line, header dimensions matched, and the page had no horizontal overflow at those widths.

At 390px and 1440px, the example profile, profile tabs, research screen, sample report, comparison and export menu were also exercised locally in both browsers. This is a bounded set of checks, not a claim that every browser and device has been tested.

## Recheck a deployment

1. Open the public app and explore the fictional sample.
2. Expand a rule, compare candidates, save choices and export each format.
3. Verify that missing or incorrect live access codes are rejected.
4. With authorized provider access, run Quick and Detailed research. Confirm actual sources, a final report, and the Extract status in Detailed mode.
5. Check the browser console and repeat the key paths at narrow and desktop widths.

Live research consumes provider requests. Keep demo codes and credentials out of recordings, screenshots and public logs.
