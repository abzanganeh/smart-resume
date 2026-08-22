# Flint Apply — Job Search Infrastructure (Release Phase 3 §18.10)

This directory contains AWS Lambda handlers and Terraform for the job-search
cache pipeline and saved-search alert dispatcher described in
`docs/SYSTEM_DESIGN_PHASE_2.md` §18.10 and `docs/IMPLEMENTATION_PLAN.md`
Steps 21–22.

## Components

| Component | Trigger | Purpose |
|---|---|---|
| `apify_cache_worker/` | EventBridge hourly | Reads top-100 queries from `job_search_log`, runs Apify Google Jobs scraper, enqueues result batches to SQS |
| `job_cache_writer/` | SQS (batch) | Normalizes Apify payloads, deduplicates by `dedup_key`, upserts into `job_cache` |
| `alert_dispatcher/` | EventBridge daily + weekly | Finds `saved_search` rows matching the schedule, queries `job_cache`, emits `notifications` for in-app + email delivery (Step 31) |
| `terraform/` | — | SQS queue, Lambda functions, EventBridge rules, IAM roles |

## Data flow

```
EventBridge (hourly)
  → apify_cache_worker Lambda
      → Apify API (Google Jobs scraper)
      → SQS (job-cache queue)
          → job_cache_writer Lambda
              → PostgreSQL job_cache (upsert on dedup_key)

EventBridge (daily / weekly)
  → alert_dispatcher Lambda
      → PostgreSQL saved_search + job_cache
      → PostgreSQL notifications (pending)
```

## Environment variables

Lambda functions expect:

| Variable | Used by | Description |
|---|---|---|
| `POSTGRES_URL` | all | Sync Postgres URL (`postgresql://…`) |
| `APIFY_API_TOKEN` | apify_cache_worker | Apify API token |
| `APIFY_ACTOR_ID` | apify_cache_worker | Default `automation-lab/google-jobs-scraper` |
| `JOB_CACHE_SQS_URL` | apify_cache_worker | Output of Terraform `job_cache_queue_url` |
| `JOB_CACHE_TTL_COMMON_SECONDS` | job_cache_writer | Cache TTL (default 3600) |
| `AWS_REGION` | all | AWS region for boto3 clients |

The FastAPI backend uses the same keys via `backend/app/config.py` and
`backend/.env.example` (with `DATABASE_URL` instead of `POSTGRES_URL`).

## Deploy

```bash
cd infra/terraform
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

Package each Lambda (from repo root):

```bash
# Example: job cache writer
cd infra/job_cache_writer
zip -r ../terraform/build/job_cache_writer.zip handler.py
# Add psycopg2-binary + boto3 to the zip or attach a Lambda layer.
```

Set `lambda_*_zip` variables in `terraform.tfvars` to the built zip paths.

## Local testing

- Unit tests for dedup/normalization: `cd backend && uv run pytest tests/unit/test_job_normalization.py -v`
- Integration (Postgres required): `uv run pytest tests/integration/test_job_cache_writer.py -m integration -v`

## Related backend code

- Models: `backend/app/models/jobs.py`
- Migration: `backend/alembic/versions/0007_jobs_rp3.py`
- Normalization: `backend/app/services/jobs/normalization.py`
- Upsert service: `backend/app/services/jobs/cache_writer.py`
