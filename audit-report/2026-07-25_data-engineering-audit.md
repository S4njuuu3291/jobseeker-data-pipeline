# Data Engineering Audit Report

**Project:** Job Data Pipeline — `S4njuuu3291/job-data-pipeline`
**Date:** 2026-07-25
**Auditor:** Automated Agent (DeepSeek V4 Flash)
**Confidence:** High — full codebase reviewed

---

## Executive Summary

| Dimensi | Score | Status |
|---------|:-----:|--------|
| 1. Pipeline Architecture & Design | **8/10** | ✅ Solid |
| 2. Data Modeling | **6/10** | ⚠️ Needs improvement |
| 3. Code Quality & Maintainability | **8/10** | ✅ Solid |
| 4. Data Quality & Testing | **7/10** | ⚠️ Needs improvement |
| 5. Security & Compliance | **9/10** | ✅ Best practice |
| 6. Performance & Scalability | **8/10** | ✅ Solid |
| 7. Documentation & Observability | **7/10** | ⚠️ Needs improvement |
| **Overall** | **7.6/10** | **On the right track** |

**Strengths:** Modular architecture, IaC with Terraform, secret management via SSM, GitHub OIDC, Pandera validation, parallel execution, conventional commits.

**Gaps:** No SCD strategy, backfill not integrated, missing freshness monitoring, no incident runbook, no data contracts.

---

## Dimensi 1: Pipeline Architecture & Design — **8/10**

### Scoring

| Sub-item | Nilai | Bukti |
|----------|:-----:|-------|
| Modularity: Extract, transform, load dipisah jadi reusable components | ✅ (+2) | `src/scraper/`, `src/silver_layer/`, `src/slack-alert/`, `src/ai/` — jelas terpisah |
| ELT paradigm: Load raw dulu, baru transform | ✅ (+2) | Bronze = raw JSON → Silver = Parquet transformed |
| Idempotency: Bisa re-run tanpa duplikasi/korupsi | ✅ (+2) | `job_id` dedup di manifest (`src/utils/manifest.py:filter_new_jobs`). Tapi di Silver belum ada idempotency untuk AI parsing |
| Backfill capability: Mampu proses historical data | ⚠️ (+1) | Ada `scripts/backfill_silver.py` tapi manual, bukan bagian dari pipeline otomatis. Tidak ada backfill untuk AI parsing |
| Orchestration: Ada workflow definition | ✅ (+2) | Step Functions state machine (`terraform/modules/step_functions/JobScraperMachine.asl.json`) + EventBridge cron |

**Temuan:**
- **Backfill manual** (`scripts/backfill_silver.py`): Bisa diproses historical data dari Bronze, tapi tidak otomatis dan tidak melewati AI parsing. Perlu integrasi ke workflow.
- **Idempotency Silver**: Jika pipeline di-re-run di hari yang sama, Silver akan menulis ulang file Parquet yang sama (overwrite). Belum ada cek apakah data sudah diproses.
- **Positive:** Parallel scraping (Step Functions Parallel state) mengurangi runtime 52% — best practice.

---

## Dimensi 2: Data Modeling — **6/10**

### Scoring

| Sub-item | Nilai | Bukti |
|----------|:-----:|-------|
| Grain definition: Tiap table punya grain yang jelas | ✅ (+2) | Satu row = satu job posting. Grain: `job_id` |
| Business key: Ada unique business key | ✅ (+2) | `job_id` = MD5 hash of normalized URL (`src/scraper/jobscraper_glints.py:121`) |
| SCD: Dimensional data pakai SCD type yang tepat | ❌ (+0) | Tidak ada SCD strategy. Data overwrite tiap hari. Discovery type hanya `NEW`/`RE-POST` tanpa history tracking |
| Normalization balance: Sesuai use case | ⚠️ (+1) | Schema flat (denormalized) — acceptable untuk analytics. `skills` dan `benefits` disimpan sebagai JSON string, bukan array di Parquet |
| Surrogate keys: Digunakan dengan tepat | ❌ (+0) | Tidak ada surrogate key. `job_id` dipakai sebagai natural key sekaligus primary key |

**Temuan:**
- **SCD missing:** Data hanya di-overwrite. Untuk analisis tren (salary trend, skill demand over time), perlu SCD Type 2 atau minimal snapshot table. **Critical finding untuk analytics goals.**
- **Skills sebagai string JSON:** `skills: Column(str, nullable=True)` di `config.py`. Ini membuat query `WHERE array_contains(skills, 'python')` tidak bisa langsung — perlu parsing di Athena. Sebaiknya pakai `array<string>` di Glue table definition.
- **Surrogate keys:** Tidak ada `job_sk` (surrogate key). Jika ada perubahan company name di job yang sama, akan dianggap job baru.

---

## Dimensi 3: Code Quality & Maintainability — **8/10**

### Scoring

| Sub-item | Nilai | Bukti |
|----------|:-----:|-------|
| Naming conventions | ✅ (+2) | `snake_case`, deskriptif: `validate_silver_schema`, `get_bronze_object`, `jobscraper_glints.py` |
| DRY: Tidak ada duplikasi kode | ✅ (+2) | Shared utils di `src/utils/manifest.py`, `src/utils/time_utils.py`, `src/utils/keywords.py`. Scraper punya pola seragam |
| Comments & docstrings | ✅ (+2) | Docstrings di fungsi-fungsi utama (`validators.py`, `storage.py`, `orchestrator.py`, `nlp.py`) |
| Modular functions | ⚠️ (+1) | Umumnya baik, tapi `entrypoint/handlers.py` punya duplikasi boilerplate untuk tiap platform. Bisa diekstrak |
| Meaningful commits | ✅ (+2) | Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`) |

**Temuan:**
- **Handler boilerplate:** `src/entrypoint/handlers.py` mengulang pola yang sama untuk 3 platform. Bisa di-refactor jadi satu fungsi handler dengan parameter platform.
- **Type hints:** Beberapa fungsi tidak punya type hints:
  - `src/silver_layer/transformations.py:normalize_location()` → `def normalize_location(location: str) -> str:`
  - `src/ai/nlp.py:calculate_cost()` → parameter tidak di-type hint
- **Positive:** Lazy imports di `nlp.py` dan `handlers.py` untuk mengurangi cold start — best practice Lambda.

---

## Dimensi 4: Data Quality & Testing — **7/10**

### Scoring

| Sub-item | Nilai | Bukti |
|----------|:-----:|-------|
| Validation checks | ✅ (+2) | Pandera schema validation di Silver layer (`validators.py:validate_silver_schema`) — 25+ fields |
| Testing framework | ✅ (+2) | pytest dengan 5 test files: `test_silver_validators.py`, `test_silver_storage.py`, `test_silver_orchestrator.py`, `test_silver_transformations.py`, `test_silver_config.py` |
| Freshness monitoring | ❌ (+0) | Tidak ada. Tidak ada alert jika data tidak masuk di jadwal |
| Row count validation | ⚠️ (+1) | Tidak ada ekspektasi volume eksplisit. Pipeline hanya log jumlah data |
| Unit tests | ✅ (+2) | Test untuk validasi schema, storage, orchestrator, transformations, config. Tapi **tidak ada test untuk AI parsing** (`src/ai/nlp.py`) |

**Temuan:**
- **No AI parser tests:** `src/ai/nlp.py` memiliki 526 baris tanpa satu test pun. Parsing logic yang paling kritis tidak ter-cover.
- **No freshness monitoring:** Jika EventBridge gagal trigger atau Lambda error, tidak ada yang tahu. Perlu CloudWatch alarm + SNS notification.
- **Positive:** Pandera validation dengan `Check.isin()` untuk enum fields (`platform`, `job_type`, `seniority`, dll) — mencegah invalid data masuk ke Silver.

---

## Dimensi 5: Security & Compliance — **9/10**

### Scoring

| Sub-item | Nilai | Bukti |
|----------|:-----:|-------|
| Secrets management | ✅ (+2) | `DEEPSEEK_API_KEY` dan `SLACK_WEBHOOK_URL` via SSM Parameter Store (`terraform/modules/ssm.tf`). Tidak ada hardcoded keys |
| PII handling | ⚠️ (+1) | Tidak ada PII yang dikumpulkan (hanya job description publik). Tapi tidak ada data classification policy atau deklarasi eksplisit |
| SQL injection | ✅ (+2) | Tidak relevan — query Athena via view yang sudah didefinisikan |
| Access control | ✅ (+2) | IAM least privilege (`terraform/modules/iam.tf`). Setiap Lambda punya role spesifik |
| Safe logging | ✅ (+2) | Tidak ada data sensitif di log. Logging menggunakan level INFO/ERROR standar |

**Temuan:**
- **Data classification:** Meskipun tidak ada PII, proyek ini tidak punya policy tertulis. Untuk portfolio, disarankan tambah pernyataan di README tentang data handling.
- **SSM encryption:** Sudah pakai SecureString untuk Slack webhook — ✅.
- **GitHub OIDC:** Keyless AWS auth — best practice.

---

## Dimensi 6: Performance & Scalability — **8/10**

### Scoring

| Sub-item | Nilai | Bukti |
|----------|:-----:|-------|
| Partitioning | ✅ (+2) | Partisi `ingestion_date` dan `platform` di Silver (`storage.py`) |
| Join optimization | ❌ (+0) | Tidak ada SQL join complexity analysis. Tapi ini simple pipeline (1 table), jadi acceptable |
| Incremental processing | ✅ (+2) | `job_id` dedup di manifest — hanya job baru yang diproses |
| Resource efficiency | ✅ (+2) | 3GB memory untuk scrapers (headless browser), 1GB untuk Silver, 500MB untuk Slack. Parallel execution + 500 workers untuk AI parsing |
| Monitoring | ✅ (+2) | CloudWatch Logs + Step Functions execution history. Tapi **tidak ada dashboard monitoring** |

**Temuan:**
- **No performance testing:** Tidak ada benchmark atau load test. Untuk skala kecil (<10 job/hari) masih fine.
- **Athena query cost:** Tidak ada tracking atau alert untuk biaya query Athena. Bisa membengkak diam-diam.
- **Positive:** Rate limiter (Token bucket, 10k RPM) untuk DeepSeek API mencegah throttling.

---

## Dimensi 7: Documentation & Observability — **7/10**

### Scoring

| Sub-item | Nilai | Bukti |
|----------|:-----:|-------|
| README: Jelas cara run, requirements, output | ✅ (+2) | README lengkap: arsitektur, setup, deploy, testing, usage, dashboard, biaya |
| Data lineage: Alur dari source → staging → mart | ✅ (+2) | Medallion architecture jelas: Bronze → Silver → Gold → Dashboard. Flow diagram + Step Functions graph |
| Data contracts: Ekspektasi antar tim/consumer | ❌ (+0) | Tidak ada data contract. Tidak ada schema versioning atau consumer guidance |
| Incident plan: Apa yang dilakukan kalau data error | ❌ (+0) | Tidak ada. Tidak ada SOP untuk pipeline failure |
| Schema docs: Deskripsi kolom, tipe data, contoh nilai | ✅ (+2) | 25+ fields didokumentasi di README + config.py. Tipe data dan contoh nilai jelas |

**Temuan:**
- **No incident runbook:** Jika pipeline gagal, tidak ada panduan troubleshooting. Developer harus baca CloudWatch logs manually.
- **No data contracts:** Consumer (Superset dashboard, Slack alert) tidak tahu schema version atau breaking changes.
- **Positive:** 2 ADRs + epic plans — menunjukkan architectural decision making yang baik.

---

## Learning Roadmap

Berdasarkan temuan audit, berikut prioritas pengembangan:

### Priority 1: Critical (harus segera)

| Temuan | Konsep | Resource | Praktek | Priority |
|--------|--------|----------|---------|:--------:|
| **AI parser tidak di-test** | Unit testing untuk LLM-based code; mocking API calls | [pytest docs](https://docs.pytest.org/), [responses library](https://github.com/getsentry/responses) untuk mock HTTP | Buat test untuk `parse_job()` dengan mock response DeepSeek | 🔴 Tinggi |
| **Tidak ada freshness monitoring** | Data observability; SLA monitoring | [AWS CloudWatch Alarm docs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html) | Setup CloudWatch alarm: jika Step Functions FAILED → SNS → email | 🔴 Tinggi |

### Priority 2: High (minggu ini)

| Temuan | Konsep | Resource | Praktek | Priority |
|--------|--------|----------|---------|:--------:|
| **Tidak ada SCD strategy** | Slowly Changing Dimensions Type 1 vs 2 | [Kimball SCD guide](https://www.kimballgroup.com/data-warehouse-basics/scd/) | Implementasi SCD Type 1 untuk salary/skills update, atau snapshot harian | 🟠 High |
| **Skills sebagai string JSON** | Complex types di Parquet/Athena | [AWS Glue `array<string>` docs](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-python-serde.html) | Ubah schema Glue: `skills ARRAY<STRING>` | 🟠 High |
| **Tidak ada incident plan** | Incident response; runbook | [Google SRE Book](https://sre.google/sre-book/table-of-contents/) | Buat `docs/runbook.md` — apa yang dilakukan saat pipeline gagal | 🟠 High |

### Priority 3: Medium (bulan ini)

| Temuan | Konsep | Resource | Praktek | Priority |
|--------|--------|----------|---------|:--------:|
| **Handler boilerplate** | DRY principle; factory pattern | Refactoring patterns | Ekstrak handler jadi satu fungsi dengan parameter platform | 🟡 Medium |
| **Backfill tidak terintegrasi** | Backfill strategy; re-processing | AWS Step Functions `Map` state | Buat Step Functions state untuk backfill batch | 🟡 Medium |
| **Athena cost tracking** | Cost observability | [AWS Cost Explorer](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/) | Setup Budget alarm untuk Athena > $1/bulan | 🟡 Medium |

---

## Appendix: File Reference

| File | Relevance |
|------|-----------|
| `src/silver_layer/orchestrator.py` | Pipeline orchestration, AI parsing integration, rate limiter |
| `src/silver_layer/config.py` | Schema definition (25+ fields), environment config |
| `src/silver_layer/validators.py` | Pandera validation |
| `src/silver_layer/storage.py` | S3 I/O, partitioning |
| `src/silver_layer/transformations.py` | Location normalization |
| `src/ai/nlp.py` | DeepSeek API client, cost tracking (526 lines, **no tests**) |
| `src/utils/manifest.py` | Job ID dedup with Parquet manifest |
| `src/entrypoint/handlers.py` | Lambda entry points |
| `src/scraper/*.py` | 3 Playwright scrapers |
| `terraform/modules/step_functions/JobScraperMachine.asl.json` | Step Functions definition |
| `tests/test_silver_*.py` | 5 test files |
| `scripts/backfill_silver.py` | Historical backfill (manual) |
| `docs/adr/ADR-002.md` | AI parsing decision record |
| `docs/plans/002-epic-ai-parsing.md` | Epic implementation plan |

---

*Report generated by Data Engineering Best Practice Auditor*
