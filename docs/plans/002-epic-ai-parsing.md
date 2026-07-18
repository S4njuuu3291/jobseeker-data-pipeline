# EPIC: AI-Based Job Description Parsing (ADR-002)

> **ADR Terkait:** `ADR-002-migrasi-parsing-job-description-ke-ai-based-extraction.md`
> **Status:** Proposed

## Ringkasan

Upgrade pipeline dari alerting ke analytics layer dengan menambahkan AI parsing untuk mengekstrak atribut job (salary, seniority, skills, dll) dari job description menggunakan DeepSeek-V4-Flash.

---

## Tasks

### Phase 1: Data Preparation

#### [TASK-1] Flatten job description di scraper
- [ ] Update scraper (kalibrr, glints, jobstreet) untuk mengambil full text job description
- [ ] Bersihkan HTML tags → plain text
- [ ] Simpan `job_description` di Bronze layer
- **Story Points:** 5

#### [TASK-2] Setup AI client module
- [ ] Buat `src/ai_parser/client.py` — wrapper untuk DeepSeek API
- [ ] Implement retry logic + error handling
- [ ] Implement JSON mode untuk output terstruktur
- [ ] Simpan API key di SSM Parameter Store
- **Story Points:** 3

### Phase 2: Pipeline Integration

#### [TASK-3] Implement AI parsing di Silver layer
- [ ] Tambah step AI parsing di Silver orchestrator (sebelum validasi)
- [ ] Mapping output AI → Silver schema fields
- [ ] Handle partial data (AI gagal extract beberapa field → null)
- **Story Points:** 5

#### [TASK-4] Implement incremental scraping and parsing (hashed job id-based dedup)
- [ ] Generate SHA256 hash dari job_id
- [ ] Simpan job_id seen ke manifest di S3
- [ ] Cek hash sebelum scraping job detail dan AI parsing → skip jika sudah ada
- **Story Points:** 3

### Phase 3: Schema & Storage

#### [TASK-5] Update Silver schema & Glue table
- [ ] Update schema validasi di Silver layer (field baru)
- [ ] Update Glue Crawler / table definition
- [ ] Update Parquet partition columns (jika perlu)
- **Story Points:** 3

#### [TASK-6] Update Gold Athena views
- [ ] Update `v_jobscraper_clean` dengan kolom baru
- [ ] Update `analytics_views.sql` (salary stats, skill trends)
- **Story Points:** 3

### Phase 4: Monitoring & Backfill

#### [TASK-7] Setup cost monitoring
- [ ] Log jumlah token per pipeline run
- [ ] Hitung estimasi biaya harian
- [ ] Alert jika biaya > threshold (misal $1/hari)
- **Story Points:** 2

#### [TASK-8] Backfill data existing (opsional)
- [ ] Script untuk parse ulang job description yang sudah ada
- [ ] Batch processing (bertahap, jangan kena rate limit)
- **Story Points:** 5

---

## Ringkasan Story Points

| Task | Description | Points |
|------|-------------|--------|
| TASK-1 | Flatten job description di scraper | 5 |
| TASK-2 | Setup AI client module | 3 |
| TASK-3 | AI parsing di Silver layer | 5 |
| TASK-4 | Incremental parsing (hash dedup) | 3 |
| TASK-5 | Update Silver schema & Glue table | 3 |
| TASK-6 | Update Gold Athena views | 3 |
| TASK-7 | Setup cost monitoring | 2 |
| TASK-8 | Backfill data existing (opsional) | 5 |
| **Total** | | **29** |
