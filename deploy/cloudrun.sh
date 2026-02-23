#!/usr/bin/env bash
# Deploy Chemo Rota Converter to Google Cloud Run (free tier).
#
# Prerequisites (run once from home machine):
#   1. Install gcloud CLI: https://cloud.google.com/sdk/docs/install
#   2. gcloud auth login
#   3. gcloud config set project YOUR_PROJECT_ID
#   4. gcloud services enable run.googleapis.com artifactregistry.googleapis.com
#
# Usage:
#   cd "/path/to/Chemo rotas"
#   bash deploy/cloudrun.sh

set -euo pipefail

SERVICE_NAME="chemo-rota-converter"
REGION="europe-west2"  # London — closest to QE Hospital

echo "=== Deploying ${SERVICE_NAME} to Cloud Run (${REGION}) ==="
echo ""
echo "This builds the Docker image, pushes to Artifact Registry, and deploys."
echo "First deploy may take 3-5 minutes."
echo ""

gcloud run deploy "${SERVICE_NAME}" \
    --source . \
    --region "${REGION}" \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --max-instances 1 \
    --platform managed \
    --set-env-vars "PORT=8080"

echo ""
echo "=== Deployment complete ==="
echo ""
gcloud run services describe "${SERVICE_NAME}" \
    --region "${REGION}" \
    --format="value(status.url)"
