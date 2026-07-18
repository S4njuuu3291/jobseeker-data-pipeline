# Lazy import untuk cold start cepat
import asyncio  # Untuk __main__ block saja
import logging

logger = logging.getLogger(__name__)


async def run_jobstreet_pipeline(keywords: list):
    # Import HANYA saat fungsi dipanggil
    import pandas as pd
    from src.scraper.jobscraper_jobstreet import jobscraper_jobstreet
    seen_ids = set()  # 👈 Track job_id yang sudah pernah discrap
    from src.utils.data_validator import validate_job_data
    from src.utils.upload_to_s3 import upload_to_s3
    from src.utils.manifest import read_manifest, update_manifest

    df_jobstreet_full = (
        pd.DataFrame()
    )  # DataFrame kosong untuk menampung semua hasil dari berbagai keyword

    for keyword in keywords:
        seen_ids = read_manifest("jobstreet")  # 👈 Baca manifest SATU KALI sebelum loop
        logger.info("--- Start JobStreet Pipeline ---")
        URL = f"https://id.jobstreet.com/id/{keyword}-jobs?daterange=7"

        raw_data = await jobscraper_jobstreet(URL, headless=True, seen_ids=seen_ids)

        if not raw_data:
            logger.warning("ERROR: No data extracted.")
            continue

        df_jobstreet = pd.DataFrame(raw_data)
        df_jobstreet["keyword"] = keyword

        df_jobstreet_full = pd.concat(
            [df_jobstreet_full, df_jobstreet], ignore_index=True
        )  # Gabungkan hasil ke DataFrame utama

    if df_jobstreet_full.empty:
        logger.info("✅ No new jobs. Pipeline completed (skip validation & upload).")
        return 0
    try:
        df = pd.DataFrame(df_jobstreet_full)
        df.drop_duplicates(
            subset=["job_id"], inplace=True
        )  # Hapus duplikat berdasarkan job_id

        df_validated = validate_job_data(df)
        logger.info(f"[OK] Validation Success: {len(df_validated)} rows ready.")

        success = upload_to_s3(df_validated, platform="jobstreet")
        if success:
            logger.info("--- Pipeline Completed Successfully ---")
        else:
            logger.warning("--- Pipeline Completed with S3 Error ---")
        return len(df_validated) if success else 0
    except Exception as e:
        logger.error(f"ERROR: Pipeline stopped at Validation/Upload: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    keywords = [
        "data-engineer",
        "etl",
        "big-data-engineer",
    ]
    asyncio.run(run_jobstreet_pipeline(keywords))
