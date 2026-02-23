# Google Cloud Run Deployment

Deploy the Chemo Rota Converter as a web app on Google Cloud Run (free tier).

The deployed URL will be `*.run.app` (Google domain — low NHS firewall risk).

## Prerequisites

Run these **once** from your home machine:

1. **Google Cloud account** — sign up at https://cloud.google.com (free tier includes 2M Cloud Run requests/month)

2. **Install gcloud CLI**:
   ```bash
   # Ubuntu/Debian
   sudo apt install google-cloud-cli

   # Or follow: https://cloud.google.com/sdk/docs/install
   ```

3. **Authenticate and set project**:
   ```bash
   gcloud auth login
   gcloud projects create chemo-rota-converter --name="Chemo Rota Converter"
   gcloud config set project chemo-rota-converter
   ```

4. **Enable required APIs**:
   ```bash
   gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
   ```

5. **Link a billing account** (required even for free tier):
   ```bash
   gcloud billing accounts list
   gcloud billing projects link chemo-rota-converter --billing-account=ACCOUNT_ID
   ```

## Deploy

From the project root:

```bash
cd "/path/to/Chemo rotas"
bash deploy/cloudrun.sh
```

First deploy takes 3-5 minutes (builds Docker image). Subsequent deploys are faster.

The script will print the public URL at the end, e.g.:
```
https://chemo-rota-converter-abc123-nw.a.run.app
```

## Free Tier Settings

The deploy script uses these settings to stay within free tier:

| Setting | Value | Why |
|---|---|---|
| `--max-instances 1` | Single instance | Prevents scaling charges |
| `--memory 512Mi` | 512 MB RAM | Minimum viable for OCR |
| `--cpu 1` | 1 vCPU | Sufficient for PDF processing |
| `--region europe-west2` | London | Closest to QE Hospital, free tier region |
| `--allow-unauthenticated` | Public access | No login needed from NHS browser |

## Update

To deploy a new version after code changes:

```bash
bash deploy/cloudrun.sh
```

## Tear Down

To remove the deployment:

```bash
gcloud run services delete chemo-rota-converter --region=europe-west2
```
