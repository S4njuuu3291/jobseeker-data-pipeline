# Lazy import: pindahkan import berat ke dalam fungsi
async def run_kalibrr_pipeline(keywords: list[str]):
    # Import pandas HANYA saat pipeline jalan
    import pandas as pd
    from src.scraper.jobscraper_kalibrr import jobscraper_kalibrr
    seen_ids = set()  # 👈 Track job_id yang sudah pernah discrap
    from src.utils.data_validator import validate_job_data
    from src.utils.upload_to_s3 import upload_to_s3

    df_kalibrr_full = (
        pd.DataFrame()
    )  # DataFrame kosong untuk menampung semua hasil dari berbagai keyword

    for keyword in keywords:
        print("--- Start Kalibrr Pipeline ---")
        # url pakai: https://kalibrr.id/id-ID/home/te/data-engineer-intern?sort=Freshness
        URL = f"https://kalibrr.id/id-ID/home/te/{keyword}?sort=Freshness"
        raw_data = await jobscraper_kalibrr(URL, headless=True, seen_ids=seen_ids)

        if not raw_data:
            print("❌ Gagal: Tidak ada data yang berhasil ditarik.")
            continue

        df_kalibrr = pd.DataFrame(raw_data)
        df_kalibrr["keyword"] = keyword

        df_kalibrr_full = pd.concat(
            [df_kalibrr_full, df_kalibrr], ignore_index=True
        )  # Gabungkan hasil ke DataFrame utama

    try:
        df = pd.DataFrame(df_kalibrr_full)
        df.drop_duplicates(
            subset=["job_id"], inplace=True
        )  # Hapus duplikat berdasarkan job_id

        df_validated = validate_job_data(df)
        print(f"✅ Validasi Sukses: {len(df_validated)} baris siap dikirim.")

        success = upload_to_s3(df_validated, platform="kalibrr")
        if success:
            print("--- 🏆 Pipeline Selesai dengan Sukses ---")
        else:
            print("--- ⚠️ Pipeline Selesai dengan Error di S3 ---")
        return len(df_validated) if success else 0
    except Exception as e:
        print(f"❌ Pipeline Berhenti di tahap Validasi/Upload: {e}")
        raise


if __name__ == "__main__":
    import asyncio

    keywords = [
        "data-engineer",
        "etl",
        "big-data-engineer",
    ]
    asyncio.run(run_kalibrr_pipeline(keywords))
