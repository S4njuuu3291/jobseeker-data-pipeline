"""Preview dan rekonsiliasi parquet Bronze/Silver untuk satu tanggal ingestion."""

import argparse
import io
import logging
import os
import sys
from datetime import datetime

import boto3
import pandas as pd
import pyarrow.parquet as pq
from dotenv import load_dotenv


logger = logging.getLogger(__name__)


DESCRIPTION_COLUMNS = {"job_description", "description", "jobdesc","job_url"}
PLATFORMS = ("glints", "kalibrr", "jobstreet", "dealls", "techinasia")
SILVER_PREVIEW_COLUMNS = (
    "job_id", "job_title", "company_name", "platform", "scraped_at",
    "keyword", "role", "location", "api_cost_idr",
)


def read_parquet(bucket: str, prefix: str) -> pd.DataFrame:
    """Baca prefix hanya jika berisi tepat satu parquet (termasuk semua halaman)."""
    s3 = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-1"))
    prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
    keys = [
        obj["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=prefix
        )
        for obj in page.get("Contents", [])
        if obj["Key"].lower().endswith(".parquet")
    ]
    if len(keys) != 1:
        raise ValueError(
            f"s3://{bucket}/{prefix} harus berisi tepat 1 parquet; "
            f"ditemukan {len(keys)}."
        )

    response = s3.get_object(Bucket=bucket, Key=keys[0])
    body = response["Body"]
    try:
        buffer = io.BytesIO(body.read())
    finally:
        body.close()
    columns = [
        name for name in pq.read_schema(buffer).names
        if name.lower() not in DESCRIPTION_COLUMNS
    ]
    buffer.seek(0)
    df = pd.read_parquet(buffer, engine="pyarrow", columns=columns)
    logger.info("File: s3://%s/%s", bucket, keys[0])
    return df


def print_preview(label: str, df: pd.DataFrame) -> None:
    print(f"\n{label} — jumlah baris: {len(df)}")
    print(df.head(5).to_string(index=False, max_cols=None, max_colwidth=60))


def reconcile(ingestion_date: str) -> list[str]:
    """Periksa semua prefix; kegagalan tidak menghentikan prefix lainnya."""
    bronze_bucket = os.getenv("AWS_S3_BUCKET_NAME", "jobscraper-bronze-data-8424560-dev")
    silver_bucket = os.getenv("AWS_S3_SILVER_BUCKET_NAME", "jobscraper-silver-data-8424560-dev")
    errors = []
    bronze_counts = {}
    silver_counts = {}
    logger.info("Ingestion date: %s", ingestion_date)

    for platform in PLATFORMS:
        prefix = f"platform={platform}/ingestion_date={ingestion_date}/"
        try:
            df = read_parquet(bronze_bucket, prefix)
            bronze_counts[platform] = len(df)
            print_preview(f"BRONZE / {platform}", df)
        except Exception as exc:
            message = f"BRONZE / {platform}: {exc}"
            errors.append(message)
            logger.error("%s", message)

    silver_total = None
    try:
        df_silver = read_parquet(silver_bucket, f"ingestion_date={ingestion_date}/")
        silver_total = len(df_silver)
        print(f"\nSILVER — jumlah baris parquet: {silver_total}")
        if "platform" not in df_silver.columns:
            raise ValueError("Kolom platform tidak ada pada parquet silver")
        for platform in PLATFORMS:
            df_platform = df_silver.loc[df_silver["platform"].eq(platform)]
            silver_counts[platform] = len(df_platform)
            preview_columns = [
                column for column in SILVER_PREVIEW_COLUMNS if column in df_platform.columns
            ]
            print_preview(f"SILVER / {platform}", df_platform.loc[:, preview_columns])
        unexpected = df_silver.loc[~df_silver["platform"].isin(PLATFORMS)]
        if not unexpected.empty:
            raise ValueError(f"Silver berisi {len(unexpected)} baris dengan platform kosong/tidak dikenal")
    except Exception as exc:
        message = f"SILVER: {exc}"
        errors.append(message)
        logger.error("%s", message)

    rows = []
    for platform in PLATFORMS:
        bronze = bronze_counts.get(platform)
        silver = silver_counts.get(platform)
        complete = bronze is not None and silver is not None
        rows.append({
            "platform": platform,
            "bronze": bronze if bronze is not None else "ERROR",
            "silver": silver if silver is not None else "ERROR",
            "selisih (silver-bronze)": silver - bronze if complete else "N/A",
            "status": ("MATCH" if bronze == silver else "MISMATCH") if complete else "INCOMPLETE",
        })
    print("\nREKONSILIASI JUMLAH BARIS")
    print(pd.DataFrame(rows).to_string(index=False))
    total_bronze = sum(bronze_counts.values()) if len(bronze_counts) == len(PLATFORMS) else None
    print(f"Total bronze: {total_bronze if total_bronze is not None else 'INCOMPLETE'}")
    print(f"Total silver: {silver_total if silver_total is not None else 'INCOMPLETE'}")
    return errors


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Ingestion date YYYY-MM-DD.")
    args = parser.parse_args()
    try:
        parsed_date = datetime.strptime(args.date, "%Y-%m-%d")
        if parsed_date.strftime("%Y-%m-%d") != args.date:
            raise ValueError
    except ValueError:
        parser.error("--date harus berupa tanggal valid YYYY-MM-DD")
    errors = reconcile(args.date)
    if errors:
        logger.error("Rekonsiliasi tidak lengkap: %s error.", len(errors))
        parser.exit(1)


if __name__ == "__main__":
    main()
