-- =========================================================
-- VIEW: v_jobscraper_clean
-- Deskripsi: Membersihkan & mengklasifikasikan job postings
--            Menentukan apakah job adalah 'NEW' atau 'EXISTING'
--            berdasarkan ingestion_date
--            
-- Cara deploy: Jalankan di Athena Query Editor
-- =========================================================

CREATE OR REPLACE VIEW "v_jobscraper_clean" AS
WITH
  -- Hitung first_seen, first_date, dan row_number per URL yang dinormalisasi
  stats_cte AS (
    SELECT
      job_id,
      job_title,
      company_name,
      location,
      job_url,
      platform,
      scraped_at,
      keyword,
      ingestion_date,
      MIN(scraped_at) OVER (
        PARTITION BY regexp_replace(lower(job_url), '(\?.*|#.*|/$)', '')
      ) AS first_seen_at,
      MIN(ingestion_date) OVER (
        PARTITION BY regexp_replace(lower(job_url), '(\?.*|#.*|/$)', '')
      ) AS first_ingestion_date,
      ROW_NUMBER() OVER (
        PARTITION BY regexp_replace(lower(job_url), '(\?.*|#.*|/$)', ''), ingestion_date
        ORDER BY scraped_at DESC
      ) AS rn
    FROM "jobscraper_db"."jobscraper_silver_table"
  ),

  -- Dedup per hari + klasifikasi NEW/EXISTING
  cleaning AS (
    SELECT
      job_id,
      job_title,
      company_name,
      location,
      job_url,
      platform,
      scraped_at,
      keyword,
      ingestion_date,
      first_seen_at,
      first_ingestion_date,
      CASE
        WHEN (ingestion_date = first_ingestion_date) THEN 'NEW'
        ELSE 'EXISTING'
      END AS discovery_type
    FROM stats_cte
    WHERE rn = 1
  )

-- Output final
SELECT
  job_id,
  job_title,
  company_name,
  location,
  job_url,
  keyword,
  ingestion_date,
  scraped_at,
  first_seen_at,
  first_ingestion_date,
  discovery_type,
  platform
FROM cleaning;
