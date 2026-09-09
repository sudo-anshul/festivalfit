import asyncio
import hmac
import json
import logging
import os
import time
from collections import deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from google.genai import errors as google_errors

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from .agent import configuration, run_agent
from .models import Film
from .reports import ExportRequest, canonical_report, render_export

app = FastAPI(title="FestivalFit", docs_url=None, redoc_url=None)
static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static), name="static")
logger = logging.getLogger("festivalfit")
active_runs = 0
run_times: deque[float] = deque()


@app.middleware("http")
async def security_headers(request, call_next):
    if request.method == "POST" and len(await request.body()) > 1_500_000:
        return Response("Report or request is too large.", status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


@app.get("/")
async def index():
    return FileResponse(static / "index.html")


@app.get("/api/status")
async def status():
    return configuration()


@app.get("/healthz")
async def health():
    return {"status": "ok"}


@app.get("/api/sample")
async def sample():
    return canonical_report(json.loads((static / "sample.json").read_text()))


@app.post("/api/export")
async def export_report(request: ExportRequest):
    try:
        content, media = await run_in_threadpool(render_export, request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="festivalfit-report.{request.format}"', "Cache-Control": "no-store"})


@app.post("/api/match")
async def match(film: Film, x_access_code: str = Header(default="")):
    global active_runs
    config = configuration()
    if not config["configured"]:
        raise HTTPException(503, "Live research needs server configuration. You can explore the sample report now.")
    access_code = os.getenv("FESTIVALFIT_ACCESS_CODE", "")
    if access_code and not hmac.compare_digest(x_access_code.encode(), access_code.encode()):
        raise HTTPException(401, "Enter the correct access code to start live research.")
    now = time.monotonic()
    while run_times and now - run_times[0] >= 3600:
        run_times.popleft()
    if active_runs >= 2 or len(run_times) >= int(os.getenv("MAX_RUNS_PER_HOUR", "20")):
        raise HTTPException(429, "Live research is at capacity. Please try again later.")
    run_times.append(now)
    active_runs += 1

    async def stream():
        global active_runs
        try:
            async with asyncio.timeout(180):
                async for event in run_agent(film):
                    if event["event"] in {"partial", "result"}:
                        event["data"] = canonical_report(event["data"])
                    yield json.dumps(event) + "\n"
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            yield json.dumps({"event": "error", "data": {"message": "Research timed out. Try a broader region or retry shortly."}}) + "\n"
        except google_errors.APIError as exc:
            logger.warning("Gemini request failed: %s", exc.code)
            if exc.code == 429:
                message = "Gemini's quota or rate limit was reached. Wait before retrying; the operator can check quota for the configured Google backend."
            elif exc.code in (401, 403):
                message = "Gemini could not authorize this request. The operator can check the configured Google credentials, permissions, and account access."
            elif exc.code == 404:
                message = "The configured Gemini model is unavailable to this account. Choose an available model in GEMINI_MODEL and restart the app."
            elif exc.code and exc.code >= 500:
                message = "Google's Gemini service is temporarily unavailable. Please retry shortly."
            else:
                message = "Gemini rejected this request. Check the configured model and account settings."
            yield json.dumps({"event": "error", "data": {"message": message}}) + "\n"
        except Exception as exc:
            # Don't expose credentials, provider response bodies, or film data in logs/errors.
            logger.warning("Live research failed: %s", type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) and str(exc).startswith(("No usable source", "Gemini returned an empty")) else "Live research could not finish. Check Gemini credentials and quota, model availability, and Parallel credits, then retry."
            yield json.dumps({"event": "error", "data": {"message": message}}) + "\n"
        finally:
            active_runs -= 1

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
