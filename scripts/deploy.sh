#!/usr/bin/env bash
# Deploy the ChargeWatch logger service and wire up its Cloud Scheduler jobs.
#
# Prerequisite: scripts/setup-gcp.sh has been run at least once (bucket, both
# service accounts, monitoring). This script only creates/updates the Cloud Run
# service, the service-scoped run.invoker binding for chargewatch-scheduler
# (the service must exist first, so it cannot live in setup-gcp.sh — see §6/§7
# of docs/specs/m1-logger.md), and the two Scheduler jobs.
#
# First-ever `--source` deploy in a project can prompt interactively (enabling
# Artifact Registry, creating its repo, or a "Continue?" for source deploys).
# Run this once from an interactive shell before wiring it into any
# non-interactive automation — a prompt with no tty attached will hang rather
# than proceed.
#
# Everything below is idempotent: safe to re-run.

set -euo pipefail

# --source below must point at the repo root regardless of the caller's cwd,
# or a run from elsewhere silently uploads the wrong directory and fails only
# after a paid Cloud Build. Resolved the same way setup-gcp.sh locates
# monitoring/dead-man.json relative to itself, via BASH_SOURCE.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROJECT_ID="${PROJECT_ID:-chargewatch-gr}"
REGION="${REGION:-europe-west1}"
BUCKET="${BUCKET:-chargewatch-raw-gr}"
SERVICE_NAME="${SERVICE_NAME:-chargewatch-logger}"
SA_NAME="chargewatch-run"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA_NAME="chargewatch-scheduler"
SCHEDULER_SA="${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "==> project=${PROJECT_ID} region=${REGION} bucket=${BUCKET} service=${SERVICE_NAME}"

gcloud config set project "${PROJECT_ID}"
gcloud config set run/region "${REGION}"

echo "==> deploying ${SERVICE_NAME}"
gcloud run deploy "${SERVICE_NAME}" \
  --source "${REPO_ROOT}" \
  --region "${REGION}" \
  --service-account "${SA}" \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --concurrency 1 \
  --cpu 1 \
  --memory 256Mi \
  --timeout 120 \
  --set-env-vars "GCS_BUCKET=${BUCKET}"

# Service-scoped, not project-scoped: chargewatch-scheduler gets no other
# permission anywhere (see setup-gcp.sh's note on this SA). This binding could
# not be made in setup-gcp.sh because the service did not exist yet.
echo "==> IAM: run.invoker for chargewatch-scheduler on ${SERVICE_NAME}"
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region "${REGION}" \
  --member "serviceAccount:${SCHEDULER_SA}" \
  --role roles/run.invoker

echo "==> capturing service URL"
SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --format 'value(status.url)')"
# gcloud exiting 0 with empty stdout would otherwise slip through set -e and
# create the jobs below with a relative URI and an empty OIDC audience.
: "${SERVICE_URL:?failed to resolve service URL for ${SERVICE_NAME}}"
echo "    ${SERVICE_URL}"

# Scheduler jobs: describe (existence only) then create-if-absent, then an
# unconditional update. A job is enabled the moment `create` succeeds, so
# create must not leave it briefly running on defaults (0 retries, no OIDC
# auth) — that would mean a job firing every 10 minutes against a
# --no-allow-unauthenticated service, 403ing every run, until the update
# below happens to also succeed. Build the full flag set once and pass the
# identical array to both create and update (confirmed via --help: every flag
# here is accepted by both http subcommands) so the job is never briefly
# wrong.
upsert_scheduler_job() {
  local job_name="$1" schedule="$2" uri="$3"

  # --oidc-token-audience is set explicitly to the bare service URL rather
  # than left to its default. Cloud Scheduler defaults the OIDC audience to
  # the entire --uri, and Google's own docs warn the audience must not
  # contain URL parameters — our --uri always carries ?feed=..., so the
  # default would produce an invalid audience and every invocation would
  # fail authentication.
  local job_flags=(
    --location "${REGION}"
    --schedule "${schedule}"
    --uri "${uri}"
    --time-zone Etc/UTC
    --http-method POST
    --oidc-service-account-email "${SCHEDULER_SA}"
    --oidc-token-audience "${SERVICE_URL}"
    --attempt-deadline 120s
    --max-retry-attempts 3
    --min-backoff 30s
    --max-backoff 120s
  )

  echo "==> scheduler job: ${job_name} (${schedule})"
  if ! gcloud scheduler jobs describe "${job_name}" --location "${REGION}" >/dev/null 2>&1; then
    gcloud scheduler jobs create http "${job_name}" "${job_flags[@]}"
  else
    echo "    job already exists, converging config via update"
  fi

  gcloud scheduler jobs update http "${job_name}" "${job_flags[@]}"
}

# Dynamic feed: every 10 minutes, matching the archive's own slot grain (§3.2).
upsert_scheduler_job \
  "chargewatch-logger-dynamic" \
  "*/10 * * * *" \
  "${SERVICE_URL}/run?feed=dynamic"

# Static feed: once a day, deliberately off the 10-minute grid at 03:05 UTC —
# feed phase is unknown; revisit at M2 by comparing max last_updated to fetch
# time (§7).
upsert_scheduler_job \
  "chargewatch-logger-static" \
  "5 3 * * *" \
  "${SERVICE_URL}/run?feed=static"

echo "==> verify: service"
gcloud run services describe "${SERVICE_NAME}" --region "${REGION}"

echo "==> verify: service IAM policy (chargewatch-scheduler should hold only run.invoker)"
gcloud run services get-iam-policy "${SERVICE_NAME}" --region "${REGION}"

echo "==> verify: scheduler jobs (schedule and state)"
gcloud scheduler jobs describe chargewatch-logger-dynamic --location "${REGION}"
gcloud scheduler jobs describe chargewatch-logger-static --location "${REGION}"

echo
echo "Done. Service URL: ${SERVICE_URL}"
echo "End-to-end check (§11):"
echo "  gcloud scheduler jobs run chargewatch-logger-dynamic --location ${REGION}"
echo "  gcloud storage ls -l gs://${BUCKET}/raw/dynamic/"
