# Setup and deployment

## Local setup

Install Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
uv sync --frozen
cp .env.example .env
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765. Sample mode uses fictional data and makes no provider calls.

The default backend is Vertex AI. Enable the Vertex AI API in a Cloud project with billing, run `gcloud auth application-default login`, and set the project ID and Parallel key in `.env`. For the separate Gemini Developer API, select `GEMINI_BACKEND=developer` and supply an [AI Studio key](https://aistudio.google.com/apikey). Keep credentials out of source control.

| Variable | Purpose |
| --- | --- |
| `GEMINI_BACKEND` | `vertex` for Vertex AI (default), or `developer` for AI Studio |
| `GEMINI_API_KEY` | Required only for the Developer API |
| `GEMINI_MODEL` | An available model; default `gemini-3.5-flash-lite` |
| `PARALLEL_API_KEY` | Required for Parallel Search and Detailed-mode Extract |
| `FESTIVALFIT_ACCESS_CODE` | Shared private live-demo code; required on Cloud Run |
| `MAX_RUNS_PER_HOUR` | Per-process allowance; default `20`, not a spending cap |
| `GOOGLE_CLOUD_PROJECT` | Required for Vertex AI |
| `GOOGLE_CLOUD_LOCATION` | Vertex location; default `global` |

Restart the local server after environment changes. Configuration status checks presence; a real run checks access, model availability and quota.

## Deploy to Google Cloud Run

Use a Google Cloud project with billing enabled and install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install-sdk). The deployer needs permission to enable APIs, build containers, deploy Cloud Run and act as the chosen service accounts. The one-time setup below also requires permission to create service accounts, grant the stated IAM roles, and manage secrets.

### One-time project setup

Choose your project ID before running these commands:

```sh
export FESTIVALFIT_PROJECT_ID=your-project-id
gcloud auth login
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com \
  secretmanager.googleapis.com iam.googleapis.com \
  --project="$FESTIVALFIT_PROJECT_ID"

gcloud iam service-accounts create festivalfit-runtime \
  --display-name="FestivalFit application runtime" --project="$FESTIVALFIT_PROJECT_ID"
gcloud iam service-accounts create festivalfit-build \
  --display-name="FestivalFit container builder" --project="$FESTIVALFIT_PROJECT_ID"

gcloud projects add-iam-policy-binding "$FESTIVALFIT_PROJECT_ID" \
  --member="serviceAccount:festivalfit-runtime@$FESTIVALFIT_PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/aiplatform.user --condition=None
gcloud projects add-iam-policy-binding "$FESTIVALFIT_PROJECT_ID" \
  --member="serviceAccount:festivalfit-build@$FESTIVALFIT_PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/run.builder --condition=None
```

Create `festivalfit-parallel-api-key` and `festivalfit-access-code` in [Secret Manager](https://console.cloud.google.com/security/secret-manager). Add the Parallel key and a strong private demo code as their first secret versions. Grant **Secret Manager Secret Accessor** to the runtime service account on these two secrets only. Do not grant the build account access to application secrets. Cloud Run authenticates to Vertex using the runtime identity; no Gemini API key or downloaded service-account key is needed.

### Publish a revision

Commit the source, push it to your repository, then deploy that clean checkout:

```sh
FESTIVALFIT_PROJECT_ID=your-project-id ./scripts/deploy-cloud-run.sh
```

The script uses the Dockerfile, builds in Cloud Build, and deploys to `us-central1`. It sets a source-commit label, one Uvicorn worker, one CPU, 512 MiB memory, concurrency four, zero minimum instances, a maximum of one instance, and a 240-second request timeout. Application research is limited to 180 seconds and two simultaneous runs per process. The public site and fictional sample are accessible without login; live research requires the private code.

Optional script variables: `FESTIVALFIT_REGION`, `FESTIVALFIT_SERVICE`, `FESTIVALFIT_MODEL`, `FESTIVALFIT_PARALLEL_SECRET_VERSION`, `FESTIVALFIT_ACCESS_SECRET_VERSION`, and `GCLOUD_BIN`. Secret versions default to `1`. Pin a new numeric version when rotating a secret, then redeploy. These values are references, not the secrets themselves.

Deploying from source creates an Artifact Registry repository named `cloud-run-source-deploy`. Cloud Build stores build logs and uploaded source. `.gcloudignore` and `.dockerignore` allow only runtime files, so `.env`, git metadata, credentials, tests and local notes are excluded. Builds and storage have their own usage charges.

Open the URL printed by deployment. Verify `/healthz`, `/api/status`, the sample, rejection of an incorrect live code, a real Quick and Detailed run, and PDF/Markdown/CSV/JSON downloads. Keep private codes out of public documentation, URLs and frontend assets.

Reference: [Cloud Run source deployment](https://cloud.google.com/run/docs/deploying-source-code).

## Cost controls

- Keep the service at minimum zero and maximum one instance, with request-based CPU billing. Cloud Run can temporarily exceed an instance maximum during transitions; this is not a financial cap.
- Keep the private live-demo code enabled and use the per-process run allowance. The allowance resets on restart and is not a global usage limit.
- Set a small project-specific Cloud Billing budget with email thresholds. Exclude credits from the calculation if you want alerts about gross resource usage while trial credits are paying for it. Budgets notify; they do not stop spending.
- An active, unupgraded Google Cloud Free Trial does not charge the payment method. Eligible resource usage consumes credits, and resources stop when the trial ends unless the account is upgraded. Once upgraded to paid billing, usage beyond credits/free allowances can be charged. Check the account's current status and remaining credits.
- Google Gemini through Vertex AI has token-based pricing. Cloud trial credits and AI Studio Gemini API billing are separate; Cloud trial credits do not fund paid Gemini Developer API usage. A qualifying AI Studio free-tier project can remain separate and unbilled.
- Parallel usage follows that account's credits and pricing. Detailed mode can add an Extract request.

References: [Cloud Free Trial](https://docs.cloud.google.com/free/docs/free-cloud-features), [Vertex AI pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing), [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing).

## Containers

```sh
docker build -t festivalfit .
docker run --rm --env-file .env -p 8765:8080 festivalfit
```

The container listens on `PORT` (default `8080`) and runs as a non-root user. For a local Vertex container, also provide ADC through an appropriate credential mount; `.env` alone does not authenticate to Vertex. Configure server-side secrets at runtime, never as build arguments.

## Research modes and saved work

Quick and Detailed modes both use a 180-second request limit. Detailed mode adds a bounded Extract request for up to three pages. Keep the browser connected; this release does not have durable background jobs. If extraction is unavailable, search evidence remains available.

ReportLab supplies PDF export without an additional service. Drafts, saved reports and shortlist choices remain in browser-local storage; deployment does not create cloud report storage. A planning-budget change is saved with the local plan, while exports retain the original researched profile. Work saved on a different origin is not automatically transferred to the new URL; export anything needed before changing hosts.

## Verification and troubleshooting

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 uv run pytest -q
node --check app/static/app.js
```

- **Sample works but live mode is unavailable:** check the backend, project and secret references; missing private-code configuration disables live research on Cloud Run.
- **401:** enter the correct private demo code.
- **429:** wait for app capacity or provider quota to recover. Check Vertex project/model quota or Parallel account limits.
- **403 from Google:** verify that Vertex AI is enabled and the runtime service account has Vertex AI User access.
- **Unavailable model:** verify the model name and availability for the configured backend/location.
- **Timeout:** check the Cloud Run 240-second timeout and provider health. The application returns an error at its own 180-second limit; keep any partial findings.
- **Build or startup error:** inspect Cloud Build and Cloud Run logs. Never add secrets or film data to debug output.
