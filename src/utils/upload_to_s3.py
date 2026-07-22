from typing import TYPE_CHECKING
import boto3
import io
import pandas as pd
from dotenv import load_dotenv
import os
from src.utils.time_utils import now_wib

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

load_dotenv()


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
        print(
            f" Menghapus {existing_objects['KeyCount']} file lama di folder ingestion_date={date_str}")

    file_key = (
        f"platform={platform}/ingestion_date={date_str}/{platform}_{timestamp}.parquet")

    parquet_buffer = io.BytesIO()
    df.to_parquet(parquet_buffer, engine="pyarrow", index=False)

    try:
        s3.put_object(Bucket=bucket_name, Key=file_key, Body=parquet_buffer.getvalue())
        print(f" Data mendarat di: s3://{bucket_name}/{file_key}")
        return True
    except Exception as e:
        print(f" Gagal upload ke S3: {e}")
        return False
