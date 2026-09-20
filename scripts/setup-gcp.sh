#!/usr/bin/env bash
# Reproducible GCP setup for ChargeWatch GR.
#
# What must be done manually first (cannot be scripted):
#   1. Create the GCP project and link a billing account.
#   2. Create the budget: Alerts only, €5/month, thresholds 50/90/100% Actual plus
#      100% Forecasted. In Scope, UNCHECK the Savings boxes so the budget tracks GROSS
#      spend — otherwise trial credits mask it and no alert ever fires.
#   3. gcloud auth login
#
# Everything below is idempotent: safe to re-run.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-chargewatch-gr}"
REGION="${REGION:-europe-west1}"
BUCKET="${BUCKET:-chargewatch-raw-gr}"
SA_NAME="chargewatch-run"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "==> project=${PROJECT_ID} region=${REGION} bucket=${BUCKET}"

gcloud config set project "${PROJECT_ID}"
gcloud config set run/region "${REGION}"

echo "==> enabling APIs"
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com

echo "==> bucket"
# --uniform-bucket-level-access : all access via IAM, no legacy per-object ACLs
# --public-access-prevention    : makes accidental public exposure impossible
if ! gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET}" \
    --location="${REGION}" \
    --uniform-bucket-level-access \
    --public-access-prevention
else
  echo "    bucket already exists, skipping create"
fi

echo "==> lifecycle: STANDARD -> COLDLINE after 30 days"
LIFECYCLE="$(mktemp)"
cat > "${LIFECYCLE}" <<'JSON'
{"lifecycle":{"rule":[
  {"action":{"type":"SetStorageClass","storageClass":"COLDLINE"},
   "condition":{"age":30,"matchesStorageClass":["STANDARD"]}}
]}}
JSON
gcloud storage buckets update "gs://${BUCKET}" --lifecycle-file="${LIFECYCLE}"
rm -f "${LIFECYCLE}"

echo "==> service account"
if ! gcloud iam service-accounts describe "${SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="ChargeWatch Cloud Run"
else
  echo "    service account already exists, skipping create"
fi

# NOTE: storage role is bound to the BUCKET, not the project. Project-level binding
# would grant access to every bucket ever created here.
echo "==> IAM"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA}" \
  --role="roles/storage.objectAdmin"

# Vertex has no resource-level binding, so this one is project-scoped by necessity.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA}" \
  --role="roles/aiplatform.user" \
  --condition=None

# Do NOT create a service-account key file. Cloud Run assumes this identity directly.

echo "==> verify"
gcloud storage buckets describe "gs://${BUCKET}"

echo
echo "Done. Smoke test:"
echo "  curl -sSO https://electrokinisi.yme.gov.gr/public/static_files/GR.IDRO.dynamic.data.latest.json.zip"
echo "  gcloud storage cp GR.IDRO.dynamic.data.latest.json.zip gs://${BUCKET}/raw/smoke/"
echo "  gcloud storage ls -l gs://${BUCKET}/raw/smoke/"
