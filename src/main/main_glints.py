# Lazy import untuk cold start cepat
import asyncio  # Untuk __main__ block saja


async def run_glints_pipeline(keywords: list):
    # Import HANYA saat fungsi dipanggil
    import pandas as pd
    from src.scraper.jobscraper_glints import jobscraper_glints
    from src.utils.data_validator import validate_job_data
    from src.utils.upload_to_s3 import upload_to_s3

    df_glints_full = pd.DataFrame()
    seen_ids = set()  # 👈 Track job_id yang sudah pernah discrap

    for keyword in keywords:
        print(f"🔍 Scraping keyword: {keyword}")
        URL = f"https://glints.com/id/opportunities/jobs/explore?keyword={keyword}&country=ID&locationName=All+Cities%2FProvinces&lowestLocationLevel=1&sortBy=LATEST"
        raw_data = await jobscraper_glints(URL, headless=True, seen_ids=seen_ids)

        if not raw_data:
            print("❌ Gagal: Tidak ada data yang berhasil ditarik.")
            continue

        print(f" ✅ Job baru dari keyword: {len(raw_data)}")
        df_glints = pd.DataFrame(raw_data)
        df_glints["keyword"] = keyword

        df_glints_full = pd.concat([df_glints_full, df_glints], ignore_index=True)

    try:
        df = pd.DataFrame(df_glints_full)
        df.drop_duplicates(
            subset=["job_id"], inplace=True
        )  # Hapus duplikat berdasarkan job_id

        df_validated = validate_job_data(df)
        print(f"✅ Validasi Sukses: {len(df_validated)} baris siap dikirim.")

        success = upload_to_s3(df_validated, platform="glints")
        if success:
            print("--- 🏆 Pipeline Selesai dengan Sukses ---")
        else:
            print("--- ⚠️ Pipeline Selesai dengan Error di S3 ---")
        return len(df_validated) if success else 0
    except Exception as e:
        print(f"❌ Pipeline Berhenti di tahap Validasi/Upload: {e}")
        raise


if __name__ == "__main__":
    keywords = [
        "data+engineer",
        "etl",
        "big+data+engineer",
    ]
    asyncio.run(run_glints_pipeline(keywords))
