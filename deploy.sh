#!/usr/bin/env bash
# Deploy Matrix to Cloud Run with Firestore reviews and Firebase Google login.
#
#   ./deploy.sh <gcp-project-id>
#
# Before running: create a Firebase web app in the same project and put its config in .env
# (FIREBASE_API_KEY, FIREBASE_AUTH_DOMAIN, FIREBASE_PROJECT_ID, FIREBASE_APP_ID). See README.
set -euo pipefail

PROJECT_ID="${1:?Usage: ./deploy.sh <gcp-project-id>}"
REGION="${REGION:-asia-south1}"                      # Mumbai: closest Cloud Run region to Nepal
GEMINI_LOCATION="${GEMINI_LOCATION:-us-central1}"    # Vertex AI region for Gemini
SERVICE="${SERVICE:-swasthya-saathi}"

# Read Firebase / Maps settings from .env if present
if [ -f .env ]; then set -a; . ./.env; set +a; fi
: "${FIREBASE_API_KEY:?Set FIREBASE_API_KEY in .env (Firebase console > Project settings > Web app)}"
: "${FIREBASE_AUTH_DOMAIN:?Set FIREBASE_AUTH_DOMAIN in .env}"
: "${FIREBASE_APP_ID:?Set FIREBASE_APP_ID in .env}"

gcloud config set project "$PROJECT_ID"

echo "Enabling APIs..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  aiplatform.googleapis.com firestore.googleapis.com

echo "Creating the Firestore database (skipped if it already exists)..."
gcloud firestore databases create --location="$REGION" --type=firestore-native 2>/dev/null || true

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for ROLE in roles/aiplatform.user roles/datastore.user; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${RUN_SA}" --role="$ROLE" \
    --condition=None >/dev/null
done

ENV_VARS="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${GEMINI_LOCATION}"
ENV_VARS+=",AUTH_MODE=firebase,STORE=firestore"
ENV_VARS+=",FIREBASE_API_KEY=${FIREBASE_API_KEY},FIREBASE_AUTH_DOMAIN=${FIREBASE_AUTH_DOMAIN}"
ENV_VARS+=",FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID:-$PROJECT_ID},FIREBASE_APP_ID=${FIREBASE_APP_ID}"
ENV_VARS+=",MAPS_EMBED_API_KEY=${MAPS_EMBED_API_KEY:-}"
# Optional: report by email (see .env.example). Without SMTP_HOST the "Email me" button explains it is off.
ENV_VARS+=",SMTP_HOST=${SMTP_HOST:-},SMTP_PORT=${SMTP_PORT:-587},SMTP_USER=${SMTP_USER:-},MAIL_FROM=${MAIL_FROM:-}"
ENV_VARS+=",SMTP_PASSWORD=${SMTP_PASSWORD:-}"

echo "Building and deploying (takes a few minutes)..."
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 1Gi --cpu 1 --timeout 120 \
  --min-instances 0 --max-instances 1 \
  --set-env-vars "$ENV_VARS"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo
echo "Deployed: $URL   (health check: $URL/api/health)"
echo "Next: firebase deploy --only hosting, then add hospitalsofnepal.com as a custom domain (README)."
