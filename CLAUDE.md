# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
poetry install --with dev

# Run all tests
poetry run pytest --tb=short

# Run a single test file
poetry run pytest tests/test_silver_transformations.py -v

# Format code
poetry run ruff format src tests

# Lint (check + fix)
poetry run ruff format --check src tests
poetry run ruff check src tests --fix --unsafe-fixes

# Type check (skip src/slack-alert — excluded in pyproject.toml)
poetry run mypy src tests

# Full CI pipeline
make ci

# Docker (Superset dashboard)
make docker-build && make docker-up && make init-superset

# Deploy (requires AWS credentials)
cd terraform && terraform init && terraform apply -var-file=terraform.tfvars
```

## Architecture Overview

This is an **event-driven ETL pipeline** on AWS that scrapes job postings from 3 Indonesian job platforms (Kalibrr, Glints, JobStreet), processes them through a medallion architecture, sends Slack alerts, and visualizes trends via Apache Superset.

### Pipeline Flow

```
EventBridge (cron: 09:00 / 16:00 WIB)
  → Step Functions (parallel branch per platform)
    → 3x Lambda Scrapers (Playwright + stealth, run concurrently)
    → Silver Layer Lambda (validates, normalizes, deduplicates)
    → Slack Alert Lambda (queries Athena, sends Block Kit message)
  → Succeed
```

**Data Layers:**
- **Bronze** — Raw JSON from scrapers → S3 `jobscraper-bronze-data-*`
- **Silver** — Cleaned Parquet (snappy, partitioned by `ingestion_date` + `platform`) → S3 `jobscraper-silver-data-*`
- **Gold** — Athena SQL views (`v_job_*`) for dashboard consumption
- **Dashboard** — Apache Superset connected to Athena

### Key Directories

| Path | Purpose |
|---|---|
| `src/scraper/` | Per-platform Playwright scrapers (async, stealth plugins, ad blocking) |
| `src/main/` | Async pipeline runners per platform (orchestrate browser lifecycle) |
| `src/silver_layer/` | Bronze → Silver: config (19-field schema), validators (Pandera), transformations (normalize location), storage (S3 Parquet upload, Glue partition update) |
| `src/slack-alert/` | Athena query → Slack Block Kit formatting → webhook dispatch |
| `src/entrypoint/` | Lambda handlers (thin wrappers, lazy imports for cold start) |
| `src/utils/` | Playwright browser helpers, time utils (WIB timezone), keyword filters, S3 upload wrapper |
| `terraform/` | IaC: S3, Lambda, Step Functions, EventBridge, Glue, Athena, ECR, IAM, SSM, DLQ, DynamoDB locking |
| `terraform/step_functions/` | ASL JSON template using JSONata query language |
| `tests/` | Pytest suite covering silver_layer modules and utils |
| `lambda-layers/slack-alert-layer/` | Pre-bundled Python deps (requests, urllib3, certifi) for Slack Lambda |
| `scripts/` | Backfill script (Bronze → Silver reprocessing), Superset init script |
| `dashboards/` | Superset dashboard export zip |
| `img/` | Screenshots for README (architecture, Step Functions graph, Slack message, dashboard) |

### Lambda Functions

| Function | Runtime | Memory | Timeout | Source |
|---|---|---|---|---|
| `jobscraper-kalibrr` | Container (Python 3.12) | 3008 MB | 15 min | `src/scraper/jobscraper_kalibrr.py` |
| `jobscraper-glints` | Container | 3008 MB | 15 min | `src/scraper/jobscraper_glints.py` |
| `jobscraper-jobstreet` | Container | 3008 MB | 15 min | `src/scraper/jobscraper_jobstreet.py` |
| `jobscraper-silver-layer` | Container | 1024 MB | 5 min | `src/silver_layer/` |
| `jobscraper-slack-alert` | Zip (Python 3.12 + layer) | 512 MB | 1 min | `src/slack-alert/slack_handler.py` |

### Key Patterns to Know

1. **Lazy imports** — All scrapers import Playwright/utilities inside the function body, not at module level, to reduce Lambda cold start time.

2. **Retry with exponential backoff** — Scrapers use `tenacity` with `@retry(stop=stop_after_attempt(2), wait=wait_exponential())`. Step Functions also retries Lambda invocations (3 attempts, full jitter).

3. **Stealth scraping** — Playwright with stealth plugins, ad/multi-media resource blocking, human-like delays, and random user agents.

4. **Deduplication** — Silver layer generates `job_id` as MD5 hash of `title+company+location` and skips records seen in the past 7 days. Tags `NEW` vs `RE-POST`.

5. **SQL injection prevention** — `ingestion_date` is validated against `^\d{4}-\d{2}-\d{2}$` regex before being interpolated into Athena queries.

6. **Secrets** — Slack webhook URL stored in SSM Parameter Store as `SecureString` (path `/jobscraper/slack/webhook_url`). Lambda retrieves it at runtime via `ssm:GetParameter` with `WithDecryption=True`.

7. **DLQ** — All Lambda functions have a Dead Letter Queue (SQS). A CloudWatch alarm fires if messages appear in the DLQ.

8. **CI/CD** — GitHub Actions with OIDC (no static AWS keys). Runs: test → terraform infra → build & push Docker to ECR → terraform full apply.

9. **Superset dashboard** — Runs locally via Docker Compose. Uses AWS credentials mounted from `~/.aws:ro` to connect to Athena.

### IAM Roles (separated by concern)

- `lambda_exec_role` — Lambda execution (scrapers + silver layer)
- `slack_lambda_role` — Slack alert Lambda (Athena, Glue, SSM, S3, Lake Formation)
- `glue_role` — Glue crawler service role
- `step_functions_role` — State machine (invoke Lambda, CloudWatch logs)
- `eventbridge_role` — EventBridge to Step Functions trigger
- `github_actions_role` — CI/CD (currently overprivileged with AdministratorAccess)
