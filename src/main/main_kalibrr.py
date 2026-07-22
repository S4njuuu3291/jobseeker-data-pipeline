import asyncio
import logging

logger = logging.getLogger(__name__)

# Lazy import: pindahkan import berat ke dalam fungsi
async def run_kalibrr_pipeline(keywords: list[str]):
    # Import pandas HANYA saat pipeline jalan
    import pandas as pd
    from src.scraper.jobscraper_kalibrr import jobscraper_kalibrr
    from src.utils.data_validator import validate_job_data
    from src.utils.upload_to_s3 import upload_to_s3
    from src.utils.manifest import read_manifest, update_manifest

    df_kalibrr_full = (
        pd.DataFrame()
    )  # DataFrame kosong untuk menampung semua hasil dari berbagai keyword

    for keyword in keywords:
        seen_ids = read_manifest("kalibrr")  #  Baca manifest SATU KALI sebelum loop
        logger.info("--- Start Kalibrr Pipeline ---")
        # url pakai: https://kalibrr.id/id-ID/home/te/data-engineer-intern?sort=Freshness
        URL = f"https://kalibrr.id/id-ID/home/te/{keyword}?sort=Freshness"
        raw_data = await jobscraper_kalibrr(URL, headless=True, seen_ids=seen_ids)

        if not raw_data:
            logger.warning(" Gagal: Tidak ada data yang berhasil ditarik.")
            continue

        df_kalibrr = pd.DataFrame(raw_data)
        df_kalibrr["keyword"] = keyword

        df_kalibrr_full = pd.concat(
            [df_kalibrr_full, df_kalibrr], ignore_index=True
        )  # Gabungkan hasil ke DataFrame utama

    if df_kalibrr_full.empty:
        logger.info(" Tidak ada job baru. Pipeline selesai (skip validasi & upload).")
        return 0

    try:
        df = pd.DataFrame(df_kalibrr_full)
        df.drop_duplicates(
            subset=["job_id"], inplace=True
        )  # Hapus duplikat berdasarkan job_id

        df_validated = validate_job_data(df)
        logger.info(f" Validasi Sukses: {len(df_validated)} baris siap dikirim.")

        success = upload_to_s3(df_validated, platform="kalibrr")
        if success:
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
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    keywords = [
        "data-engineer",
        "etl",
        "big-data-engineer",
    ]
    asyncio.run(run_kalibrr_pipeline(keywords))
