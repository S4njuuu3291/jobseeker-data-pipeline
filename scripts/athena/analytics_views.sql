-- =========================================================
-- ANALYTICS VIEWS untuk Dashboard Superset
-- Basis: v_jobscraper_clean
-- 
-- Cara deploy: Jalankan semua query di Athena Query Editor
-- =========================================================

-- =========================================================
-- 1. v_job_daily_trend
--    Tren lowongan per hari (Line Chart)
-- =========================================================
CREATE OR REPLACE VIEW "v_job_daily_trend" AS
SELECT
  ingestion_date,
  platform,
  keyword,
  COUNT(*) AS total_jobs,
  COUNT(DISTINCT job_id) AS unique_jobs
FROM "jobscraper_db"."v_jobscraper_clean"
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- =========================================================
-- 2. v_job_top_companies
--    Perusahaan paling banyak hiring (Table / Bar Chart)
-- =========================================================
CREATE OR REPLACE VIEW "v_job_top_companies" AS
SELECT
  company_name,
  platform,
  COUNT(DISTINCT job_id) AS total_postings,
  MIN(ingestion_date) AS first_seen,
  MAX(ingestion_date) AS last_seen
FROM "jobscraper_db"."v_jobscraper_clean"
WHERE discovery_type = 'NEW'
GROUP BY 1, 2
ORDER BY 3 DESC;

-- =========================================================
-- 3. v_job_location_stats
--    Sebaran lokasi (Bar Chart / Map)
-- =========================================================
CREATE OR REPLACE VIEW "v_job_location_stats" AS
SELECT
  location,
  platform,
  keyword,
  COUNT(*) AS job_count,
  COUNT(DISTINCT ingestion_date) AS active_days
FROM "jobscraper_db"."v_jobscraper_clean"
GROUP BY 1, 2, 3
ORDER BY 4 DESC;

-- =========================================================
-- 4. v_job_new_vs_existing
--    Perbandingan NEW vs EXISTING (Pie Chart / Area Chart)
-- =========================================================
CREATE OR REPLACE VIEW "v_job_new_vs_existing" AS
SELECT
  ingestion_date,
  discovery_type,
  platform,
  COUNT(*) AS total
FROM "jobscraper_db"."v_jobscraper_clean"
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- =========================================================
-- 5. v_job_keyword_performance
--    Keywords mana yang paling menghasilkan job (Bar Chart)
-- =========================================================
CREATE OR REPLACE VIEW "v_job_keyword_performance" AS
SELECT
  keyword,
  platform,
  COUNT(DISTINCT job_id) AS total_jobs,
  COUNT(DISTINCT company_name) AS total_companies,
  COUNT(DISTINCT location) AS total_locations
FROM "jobscraper_db"."v_jobscraper_clean"
WHERE discovery_type = 'NEW'
GROUP BY 1, 2
ORDER BY 3 DESC;

-- =========================================================
-- 6. v_job_weekly_summary
--    Rangkuman mingguan (opsional)
-- =========================================================
CREATE OR REPLACE VIEW "v_job_weekly_summary" AS
SELECT
  DATE_TRUNC('week', DATE(ingestion_date)) AS week_start,
  platform,
  keyword,
  COUNT(DISTINCT job_id) AS total_jobs,
  COUNT(DISTINCT company_name) AS total_companies
FROM "jobscraper_db"."v_jobscraper_clean"
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- =========================================================
-- 7. v_job_discovery_rate
--    Rate penemuan job baru per platform (Time Series)
-- =========================================================
CREATE OR REPLACE VIEW "v_job_discovery_rate" AS
SELECT
  ingestion_date,
  platform,
  discovery_type,
  COUNT(*) AS total
FROM "jobscraper_db"."v_jobscraper_clean"
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
