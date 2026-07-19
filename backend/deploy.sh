#!/usr/bin/env bash
# One-command Cloud Run deploy. Prereqs (once per project):
#   gcloud services enable run.googleapis.com firestore.googleapis.com \
#     cloudtasks.googleapis.com secretmanager.googleapis.com
#   gcloud firestore databases create --location=us-central1
#   gcloud tasks queues create toolshare-jobs --location=us-central1
#   echo -n "$STRIPE_SECRET_KEY"  | gcloud secrets create stripe-secret --data-file=-
#   echo -n "$ANTHROPIC_API_KEY"  | gcloud secrets create anthropic-key --data-file=-
#   openssl rand -hex 32 | tr -d '\n' | gcloud secrets create internal-task-secret --data-file=-
set -euo pipefail

PROJECT_ID=${PROJECT_ID:?set PROJECT_ID}
REGION=${REGION:-us-central1}
SERVICE=${SERVICE:-toolshare-api}

gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --source . \
  --allow-unauthenticated \
  --set-env-vars "TOOLSHARE_ENV=prod,TOOLSHARE_GCP_PROJECT=$PROJECT_ID,TOOLSHARE_TASKS_QUEUE=toolshare-jobs,TOOLSHARE_TASKS_LOCATION=$REGION" \
  --set-secrets "TOOLSHARE_STRIPE_SECRET_KEY=stripe-secret:latest,TOOLSHARE_ANTHROPIC_API_KEY=anthropic-key:latest,TOOLSHARE_INTERNAL_TASK_SECRET=internal-task-secret:latest"

URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')
echo "Deployed: $URL"
echo "Now set the callback URL for Cloud Tasks:"
echo "  gcloud run services update $SERVICE --project $PROJECT_ID --region $REGION \\"
echo "    --update-env-vars TOOLSHARE_SERVICE_BASE_URL=$URL"
