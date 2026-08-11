# Lazy import untuk cold start cepat
import asyncio  # Untuk __main__ block saja
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)


async def run_techinasia_pipeline(keywords: list):
    # Import HANYA saat fungsi dipanggil
    import pandas as pd
    from src.scraper.jobscraper_techinasia import jobscraper_techinasia
    from src.utils.data_validator import validate_job_data
    from src.utils.upload_to_s3 import upload_to_s3
    from src.utils.manifest import read_manifest, update_manifest

    df_techinasia_full = pd.DataFrame()
    seen_ids = read_manifest("techinasia")  # Baca manifest SATU KALI sebelum loop
    new_ids = set()  # Kumpulin job_id baru selama loop

    for keyword in keywords:
        logger.info(f" Scraping keyword: {keyword}")
        # TechInAsia pakai %20 untuk spasi (bukan + atau -)
        query = quote(keyword)
        URL = f"https://www.techinasia.com/jobs/search?query={query}&country_name[]=Indonesia"
        raw_data = await jobscraper_techinasia(URL, headless=True, seen_ids=seen_ids)

        if not raw_data:
            logger.warning(" Gagal: Tidak ada data yang berhasil ditarik.")
            continue

        logger.info(f"  Job baru dari keyword: {len(raw_data)}")

        # Kumpulin job_id baru (belum ada di manifest)
        for job in raw_data:
            new_ids.add(job["job_id"])

        df_techinasia = pd.DataFrame(raw_data)
        df_techinasia["keyword"] = keyword

        df_techinasia_full = pd.concat([df_techinasia_full, df_techinasia], ignore_index=True)

    if df_techinasia_full.empty:
        logger.info(" Tidak ada job baru. Pipeline selesai (skip validasi & upload).")
        return 0

    try:
        df = pd.DataFrame(df_techinasia_full)
        df.drop_duplicates(
            subset=["job_id"], inplace=True
        )  # Hapus duplikat berdasarkan job_id

        df_validated = validate_job_data(df)
        logger.info(f" Validasi Sukses: {len(df_validated)} baris siap dikirim.")

        success = upload_to_s3(df_validated, platform="techinasia")
        if success:
            # Update manifest SEKALI di akhir, setelah upload sukses
            seen_ids.update(new_ids)
            update_manifest("techinasia", seen_ids)
            logger.info("---  Pipeline Selesai dengan Sukses ---")
        else:
            logger.warning("---  Pipeline Selesai dengan Error di S3 ---")
        return len(df_validated) if success else 0
    except Exception as e:
        logger.error(f" Pipeline Berhenti di tahap Validasi/Upload: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    keywords = [
        "data engineer",
        "etl",
        "data analyst",
    ]
    asyncio.run(run_techinasia_pipeline(keywords))
