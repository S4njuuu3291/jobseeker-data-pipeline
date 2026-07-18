# Lazy import untuk cold start cepat
import asyncio  # Untuk __main__ block saja
import logging

logger = logging.getLogger(__name__)


async def run_glints_pipeline(keywords: list):
    # Import HANYA saat fungsi dipanggil
    import pandas as pd
    from src.scraper.jobscraper_glints import jobscraper_glints
    from src.utils.data_validator import validate_job_data
    from src.utils.upload_to_s3 import upload_to_s3
    from src.utils.manifest import read_manifest, update_manifest

    df_glints_full = pd.DataFrame()

    for keyword in keywords:
        seen_ids = read_manifest("glints")  # 👈 Baca manifest SATU KALI sebelum loop
        logger.info(f"🔍 Scraping keyword: {keyword}")
        URL = f"https://glints.com/id/opportunities/jobs/explore?keyword={keyword}&country=ID&locationName=All+Cities%2FProvinces&lowestLocationLevel=1&sortBy=LATEST"
        raw_data = await jobscraper_glints(URL, headless=True, seen_ids=seen_ids)

        if not raw_data:
            logger.warning("❌ Gagal: Tidak ada data yang berhasil ditarik.")
            continue

        logger.info(f" ✅ Job baru dari keyword: {len(raw_data)}")

        df_glints = pd.DataFrame(raw_data)
        df_glints["keyword"] = keyword

        df_glints_full = pd.concat([df_glints_full, df_glints], ignore_index=True)

    if df_glints_full.empty:
        print("✅ Tidak ada job baru. Pipeline selesai (skip validasi & upload).")
        return 0
    
    try:
        df = pd.DataFrame(df_glints_full)
        df.drop_duplicates(
            subset=["job_id"], inplace=True
        )  # Hapus duplikat berdasarkan job_id

        df_validated = validate_job_data(df)
        logger.info(f"✅ Validasi Sukses: {len(df_validated)} baris siap dikirim.")

        success = upload_to_s3(df_validated, platform="glints")
        if success:
            logger.info("--- 🏆 Pipeline Selesai dengan Sukses ---")
        else:
            logger.warning("--- ⚠️ Pipeline Selesai dengan Error di S3 ---")
        return len(df_validated) if success else 0
    except Exception as e:
        logger.error(f"❌ Pipeline Berhenti di tahap Validasi/Upload: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    keywords = [
        "data+engineer",
        "etl",
        "big+data+engineer",
    ]
    asyncio.run(run_glints_pipeline(keywords))
