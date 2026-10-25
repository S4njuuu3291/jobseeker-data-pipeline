from typing import TYPE_CHECKING
import boto3
import io
import logging
import pandas as pd
from dotenv import load_dotenv
import os
from src.utils.time_utils import now_wib

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

load_dotenv()

logger = logging.getLogger(__name__)


def upload_to_s3(df: pd.DataFrame, platform: str):
    s3: S3Client = boto3.client("s3")
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")

    if not bucket_name:
        raise ValueError("AWS_S3_BUCKET_NAME environment variable not set")

    now = now_wib()
    date_str = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%H%M%S")

    # check if already exist object in ingestion_date, if exist, replace with new file, if not exist, create new file

    existing_objects = s3.list_objects_v2(
        Bucket=bucket_name, Prefix=f"platform={platform}/ingestion_date={date_str}/")
    if existing_objects.get("KeyCount", 0) > 0:
        for obj in existing_objects["Contents"]:
            s3.delete_object(Bucket=bucket_name, Key=obj["Key"])
        logger.info(
            "Menghapus %s file lama untuk platform=%s, ingestion_date=%s",
            existing_objects["KeyCount"], platform, date_str,
        )

    file_key = (
        f"platform={platform}/ingestion_date={date_str}/{platform}_{timestamp}.parquet")

    parquet_buffer = io.BytesIO()
    df.to_parquet(parquet_buffer, engine="pyarrow", index=False)

    try:
        s3.put_object(Bucket=bucket_name, Key=file_key, Body=parquet_buffer.getvalue())
        logger.info("Data berhasil diunggah ke s3://%s/%s", bucket_name, file_key)
        return True
    except Exception as e:
        logger.exception("Gagal mengunggah data ke S3: %s", e)
        return False
