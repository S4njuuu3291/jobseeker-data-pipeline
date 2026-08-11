# Lazy import untuk cold start cepat
import asyncio  # Untuk __main__ block saja
import logging

logger = logging.getLogger(__name__)


async def run_dealls_pipeline(keywords: list):
    # Import HANYA saat fungsi dipanggil
    import pandas as pd
    from src.scraper.jobscraper_dealls import jobscraper_dealls
    from src.utils.data_validator import validate_job_data
    from src.utils.upload_to_s3 import upload_to_s3
    from src.utils.manifest import read_manifest, update_manifest

    df_dealls_full = pd.DataFrame()
    seen_ids = read_manifest("dealls")  # Baca manifest SATU KALI sebelum loop
    new_ids = set()  # Kumpulin job_id baru selama loop

    for keyword in keywords:
        logger.info(f" Scraping keyword: {keyword}")
        URL = f"https://dealls.com/?sortParam=publishedAt&searchJob={keyword}"
        raw_data = await jobscraper_dealls(URL, headless=True, seen_ids=seen_ids)

        if not raw_data:
            logger.warning(" Gagal: Tidak ada data yang berhasil ditarik.")
            continue

        logger.info(f"  Job baru dari keyword: {len(raw_data)}")

        # Kumpulin job_id baru (belum ada di manifest)
        for job in raw_data:
            new_ids.add(job["job_id"])

        df_dealls = pd.DataFrame(raw_data)
        df_dealls["keyword"] = keyword

        df_dealls_full = pd.concat([df_dealls_full, df_dealls], ignore_index=True)

    if df_dealls_full.empty:
        logger.info(" Tidak ada job baru. Pipeline selesai (skip validasi & upload).")
        return 0

    try:
        df = pd.DataFrame(df_dealls_full)
        df.drop_duplicates(
            subset=["job_id"], inplace=True
        )  # Hapus duplikat berdasarkan job_id

        df_validated = validate_job_data(df)
        logger.info(f" Validasi Sukses: {len(df_validated)} baris siap dikirim.")

        success = upload_to_s3(df_validated, platform="dealls")
        if success:
            # Update manifest SEKALI di akhir, setelah upload sukses
            seen_ids.update(new_ids)
            update_manifest("dealls", seen_ids)
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
        "data+engineer",
        "etl",
        "big+data+engineer",
    ]
    asyncio.run(run_dealls_pipeline(keywords))
