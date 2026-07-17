# Lazy import untuk cold start cepat
import asyncio  # Untuk __main__ block saja


async def run_jobstreet_pipeline(keywords: list):
    # Import HANYA saat fungsi dipanggil
    import pandas as pd
    from src.scraper.jobscraper_jobstreet import jobscraper_jobstreet
    seen_ids = set()  # 👈 Track job_id yang sudah pernah discrap
    from src.utils.data_validator import validate_job_data
    from src.utils.upload_to_s3 import upload_to_s3

    df_jobstreet_full = (
        pd.DataFrame()
    )  # DataFrame kosong untuk menampung semua hasil dari berbagai keyword

    for keyword in keywords:
        print("--- Start JobStreet Pipeline ---")
        URL = f"https://id.jobstreet.com/id/{keyword}-jobs?daterange=7"

        raw_data = await jobscraper_jobstreet(URL, headless=True, seen_ids=seen_ids)

        if not raw_data:
            print("ERROR: No data extracted.")
            continue

        df_jobstreet = pd.DataFrame(raw_data)
        df_jobstreet["keyword"] = keyword

        df_jobstreet_full = pd.concat(
            [df_jobstreet_full, df_jobstreet], ignore_index=True
        )  # Gabungkan hasil ke DataFrame utama

    try:
        df = pd.DataFrame(df_jobstreet_full)
        df.drop_duplicates(
            subset=["job_id"], inplace=True
        )  # Hapus duplikat berdasarkan job_id

        df_validated = validate_job_data(df)
        print(f"[OK] Validation Success: {len(df_validated)} rows ready.")

        success = upload_to_s3(df_validated, platform="jobstreet")
        if success:
            print("--- Pipeline Completed Successfully ---")
        else:
            print("--- Pipeline Completed with S3 Error ---")
        return len(df_validated) if success else 0
    except Exception as e:
        print(f"ERROR: Pipeline stopped at Validation/Upload: {e}")
        raise


if __name__ == "__main__":
    keywords = [
        "data-engineer",
        "etl",
        "big-data-engineer",
    ]
    asyncio.run(run_jobstreet_pipeline(keywords))
