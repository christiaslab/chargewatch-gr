#!/usr/bin/env bash
# Reproducible GCP setup for ChargeWatch GR.
#
# What must be done manually first (cannot be scripted):
#   1. Create the GCP project and link a billing account.
#   2. Create the budget: Alerts only, €5/month, thresholds 50/90/100% Actual plus
#      100% Forecasted. In Scope, UNCHECK the Savings boxes so the budget tracks GROSS
#      spend — otherwise trial credits mask it and no alert ever fires.
#   3. gcloud auth login
#   4. gcloud components install beta -- needed for `gcloud beta monitoring channels`;
#      there is no GA command group for notification channels yet.
#   5. python3 must be on PATH -- used to parse IAM policy JSON where gcloud itself
#      has no --filter support (see the objectAdmin binding check below).
#
# Everything below is idempotent: safe to re-run.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-chargewatch-gr}"
REGION="${REGION:-europe-west1}"
BUCKET="${BUCKET:-chargewatch-raw-gr}"
SA_NAME="chargewatch-run"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA_NAME="chargewatch-scheduler"
SCHEDULER_SA="${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Required, never hardcoded: the address the dead-man switch emails on silence.
: "${ALERT_EMAIL:?set ALERT_EMAIL to the address that receives the ingestion-silence alert}"

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
  secretmanager.googleapis.com \
  monitoring.googleapis.com

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

echo "==> service account (chargewatch-run)"
if ! gcloud iam service-accounts describe "${SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="ChargeWatch Cloud Run"
else
  echo "    service account already exists, skipping create"
fi

# NOTE: storage role is bound to the BUCKET, not the project. Project-level binding
# would grant access to every bucket ever created here.
echo "==> IAM (chargewatch-run — least privilege)"
# objectCreator only: the logger can create a new object but can never overwrite or
# delete an existing one. This is what makes "raw is immutable" (CLAUDE.md) hold at
# the IAM layer, not just by convention.
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA}" \
  --role="roles/storage.objectCreator"

# objectAdmin also allowed delete/overwrite; drop it now that objectCreator covers the
# only permission the logger needs. Check before removing rather than swallowing the
# remove's exit code — a swallowed failure here could as easily be a typo or a
# permission problem as a genuinely absent binding.
# `buckets get-iam-policy` is not a list command (confirmed via --help): its only flags
# are the GCLOUD WIDE FLAGS (--flatten, --format, ...) — no --filter. Fetch the policy as
# JSON and match role+member in python3 instead. The get-iam-policy call is its own
# command substitution, so under set -e its failure (auth, wrong project) aborts the
# script rather than being read as "absent".
OBJECT_ADMIN_POLICY="$(gcloud storage buckets get-iam-policy "gs://${BUCKET}" --format=json)"
OBJECT_ADMIN_BOUND="$(python3 -c '
import json, sys
policy = json.loads(sys.argv[1])
sa = sys.argv[2]
role = "roles/storage.objectAdmin"
member = "serviceAccount:" + sa
for b in policy.get("bindings", []):
    if b.get("role") == role and member in b.get("members", []):
        print(role)
        break
' "${OBJECT_ADMIN_POLICY}" "${SA}")"
if [[ -n "${OBJECT_ADMIN_BOUND}" ]]; then
  gcloud storage buckets remove-iam-policy-binding "gs://${BUCKET}" \
    --member="serviceAccount:${SA}" \
    --role="roles/storage.objectAdmin" \
    --all
else
  echo "    objectAdmin binding already absent, skipping"
fi

# No agent in the ingestion path (CLAUDE.md) — the logger never calls Vertex AI, so
# this project-level grant only widened the blast radius of a leaked identity. Drop it.
# This is the only project-level IAM write in the script, so nothing earlier proves the
# caller even has the permission — check first instead of masking remove's exit code,
# so a real failure (PERMISSION_DENIED, a typo) surfaces instead of being read as
# "already absent".
AIPLATFORM_BOUND="$(gcloud projects get-iam-policy "${PROJECT_ID}" \
  --flatten="bindings[].members" \
  --filter="bindings.role=roles/aiplatform.user AND bindings.members=serviceAccount:${SA}" \
  --format="value(bindings.role)")"
if [[ -n "${AIPLATFORM_BOUND}" ]]; then
  gcloud projects remove-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA}" \
    --role="roles/aiplatform.user" \
    --condition=None
else
  echo "    aiplatform.user binding already absent, skipping"
fi

# Do NOT create a service-account key file. Cloud Run assumes this identity directly.

echo "==> service account (chargewatch-scheduler)"
if ! gcloud iam service-accounts describe "${SCHEDULER_SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SCHEDULER_SA_NAME}" \
    --display-name="ChargeWatch Cloud Scheduler"
else
  echo "    service account already exists, skipping create"
fi

# No project- or bucket-level roles for this identity on purpose: its only permission
# is roles/run.invoker, scoped to the chargewatch-logger service, bound in deploy.sh
# (§7) because that binding needs the service to exist first.

echo "==> notification channel (email: ${ALERT_EMAIL})"
# `channels` has no GA command group yet (checked: `gcloud monitoring channels --help`
# fails, `gcloud beta monitoring channels --help` exists) — beta is the only option.
# Look up by the label gcloud itself indexes email channels on, so re-runs don't
# create a duplicate.
CHANNEL_NAME="$(gcloud beta monitoring channels list \
  --filter="type=\"email\" AND labels.email_address=\"${ALERT_EMAIL}\"" \
  --format="value(name)" | head -n1)"
if [[ -z "${CHANNEL_NAME}" ]]; then
  CHANNEL_NAME="$(gcloud beta monitoring channels create \
    --display-name="ChargeWatch alerts (${ALERT_EMAIL})" \
    --type=email \
    --channel-labels="email_address=${ALERT_EMAIL}" \
    --format="value(name)")"
  echo "    created channel ${CHANNEL_NAME}"
else
  echo "    channel already exists: ${CHANNEL_NAME}"
fi

echo "==> alert policy: dead-man's switch"
# `policies` does have a GA command group (checked: `gcloud monitoring policies --help`),
# unlike `channels` above, so no alpha/beta fallback is needed here.
# A metric-absence condition never fires for a series that has never reported at all —
# the policy is inert until the first successful write lands after deploy.sh runs. Do
# not test it (e.g. by pausing the Scheduler job) before that first write has happened.
# The `method="WriteObject"` label below is unverified until then too: confirm it in
# Metrics Explorer against real traffic (see dead-man.json's own documentation.content).
POLICY_DISPLAY_NAME="chargewatch-raw-ingestion-silence"
POLICY_FILE="$(dirname "${BASH_SOURCE[0]}")/monitoring/dead-man.json"
POLICY_TMP="$(mktemp)"
trap 'rm -f "${POLICY_TMP}"' EXIT
sed -e "s|__NOTIFICATION_CHANNEL__|${CHANNEL_NAME}|g" \
    -e "s|__BUCKET__|${BUCKET}|g" \
    "${POLICY_FILE}" > "${POLICY_TMP}"

EXISTING_POLICY="$(gcloud monitoring policies list \
  --filter="displayName=\"${POLICY_DISPLAY_NAME}\"" \
  --format="value(name)" | head -n1)"
if [[ -z "${EXISTING_POLICY}" ]]; then
  gcloud monitoring policies create --policy-from-file="${POLICY_TMP}"
  echo "    created alert policy"
else
  gcloud monitoring policies update "${EXISTING_POLICY}" --policy-from-file="${POLICY_TMP}"
  echo "    updated alert policy ${EXISTING_POLICY}"
fi

echo "==> verify"
gcloud storage buckets describe "gs://${BUCKET}"

echo "==> verify: chargewatch-run holds only objectCreator on the bucket"
gcloud storage buckets get-iam-policy "gs://${BUCKET}"

echo "==> verify: chargewatch-run holds no project-level roles"
gcloud projects get-iam-policy "${PROJECT_ID}" \
  --flatten="bindings[].members" \
  --filter="bindings.members=serviceAccount:${SA}" \
  --format="table(bindings.role)"

echo
echo "Done. Smoke test:"
echo "  curl -sSO https://electrokinisi.yme.gov.gr/public/static_files/GR.IDRO.dynamic.data.latest.json.zip"
echo "  gcloud storage cp GR.IDRO.dynamic.data.latest.json.zip gs://${BUCKET}/smoke/"
echo "  gcloud storage ls -l gs://${BUCKET}/smoke/"
