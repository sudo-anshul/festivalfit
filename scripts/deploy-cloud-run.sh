#!/bin/sh
set -eu

: "${FESTIVALFIT_PROJECT_ID:?Set FESTIVALFIT_PROJECT_ID to your Google Cloud project ID}"
GCLOUD_BIN=${GCLOUD_BIN:-gcloud}
region=${FESTIVALFIT_REGION:-us-central1}
service=${FESTIVALFIT_SERVICE:-festivalfit}
model=${FESTIVALFIT_MODEL:-gemini-3.5-flash-lite}
parallel_version=${FESTIVALFIT_PARALLEL_SECRET_VERSION:-1}
access_version=${FESTIVALFIT_ACCESS_SECRET_VERSION:-1}

cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ -n "$(git status --porcelain)" ]; then
    printf '%s\n' 'Commit and push your source changes before deploying a labeled revision.' >&2
    exit 1
fi
revision=$(git rev-parse --short=12 HEAD)

"$GCLOUD_BIN" run deploy "$service" \
    --project="$FESTIVALFIT_PROJECT_ID" \
    --region="$region" \
    --source=. \
    --build-service-account="projects/$FESTIVALFIT_PROJECT_ID/serviceAccounts/festivalfit-build@$FESTIVALFIT_PROJECT_ID.iam.gserviceaccount.com" \
    --service-account="festivalfit-runtime@$FESTIVALFIT_PROJECT_ID.iam.gserviceaccount.com" \
    --allow-unauthenticated \
    --cpu=1 --memory=512Mi --concurrency=4 \
    --min=0 --max=1 --min-instances=0 --max-instances=1 \
    --cpu-throttling --no-cpu-boost --timeout=240s --port=8080 \
    --set-env-vars="GEMINI_BACKEND=vertex,GOOGLE_CLOUD_PROJECT=$FESTIVALFIT_PROJECT_ID,GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=$model,MAX_RUNS_PER_HOUR=20" \
    --set-secrets="PARALLEL_API_KEY=festivalfit-parallel-api-key:$parallel_version,FESTIVALFIT_ACCESS_CODE=festivalfit-access-code:$access_version" \
    --labels="app=festivalfit,environment=demo,source-commit=$revision" \
    --quiet
