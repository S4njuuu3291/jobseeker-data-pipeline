"""S3 storage operations for Silver layer."""

import io
import logging
import os
from typing import TYPE_CHECKING

import pandas as pd
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from .config import get_bronze_bucket_name
from src.utils.time_utils import now_wib

load_dotenv()

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_glue import GlueClient

logger = logging.getLogger(__name__)


def get_bronze_object(list_platforms: list[str]) -> pd.DataFrame:
    """Read parquet files from Bronze S3 bucket for given platforms.

    Args:
        list_platforms: List of platform names to read data from

    Returns:
        Combined dataframe from all platforms
    """
    bucket_name = get_bronze_bucket_name()
    s3: S3Client = boto3.client("s3")
    ingestion_date = now_wib().strftime("%Y-%m-%d")

    try:
        df = pd.DataFrame()

        for platform in list_platforms:
        #     if platform != "glints":
        #         logger.info(f"Skipping platform: {platform}")
        #         continue
            object_key_prefix = f"platform={platform}/ingestion_date={ingestion_date}/"
            logger.info(f"Listing objects with prefix: {object_key_prefix}")

            response = s3.list_objects_v2(Bucket=bucket_name, Prefix=object_key_prefix)

            if "Contents" not in response:
                logger.info(f"No objects found with prefix: {object_key_prefix}")
                continue

            for obj in response["Contents"]:
                obj_key = obj["Key"]
                logger.info(f"Processing object: {obj_key}")

                obj_response = s3.get_object(Bucket=bucket_name, Key=obj_key)
                df_obj = pd.read_parquet(io.BytesIO(obj_response["Body"].read()))
                df = pd.concat([df, df_obj], ignore_index=True)

        logger.info(f"Combined DataFrame shape: {df.shape}")
        logger.info(f"Combined DataFrame columns: {df.columns.tolist()}")
        return df

    except ClientError as e:
        logger.error(f"Error accessing S3: {e}")
        raise e


def upload_to_silver(df: pd.DataFrame) -> str:
    """
    Upload processed dataframe ke Silver S3 bucket dan daftarkan partisinya ke Glue.

    Args:
        df: Dataframe yang sudah dibersihkan (Silver data).
        platform: Nama platform (kalibrr, glints, atau jobstreet).

    Returns:
        S3 object key yang berhasil diupload.
    """
    bucket_name = os.getenv("AWS_S3_SILVER_BUCKET_NAME")
    db_name = os.getenv("AWS_GLUE_DATABASE_NAME", "jobscraper_db")
    table_name = os.getenv("AWS_GLUE_SILVER_TABLE_NAME", "jobscraper_silver_table")

    if not bucket_name:
        raise ValueError("AWS_S3_SILVER_BUCKET_NAME is not set")

    s3: S3Client = boto3.client("s3")
    glue: GlueClient = boto3.client("glue")

    now = now_wib()
    processed_date = now.strftime("%Y-%m-%d")
    file_timestamp = now.strftime("%Y%m%d_%H%M%S")

    partition_prefix = f"ingestion_date={processed_date}/"
    object_key = f"{partition_prefix}job_data_{processed_date}_{file_timestamp}.parquet"

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    try:
        logger.info(f"Uploading to S3: s3://{bucket_name}/{object_key}")
        s3.put_object(Bucket=bucket_name, Key=object_key, Body=buffer.getvalue())
        logger.info("✅ File uploaded successfully.")

        logger.info(f"Registering partition to Glue: {db_name}.{table_name}")

        # Create partition if it doesn't exist yet (idempotent)
        try:
            glue.create_partition(
                DatabaseName=db_name,
                TableName=table_name,
                PartitionInput={
                    "Values": [processed_date],
                    "StorageDescriptor": {
                        "Location": f"s3://{bucket_name}/{partition_prefix}",
                        "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                        "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                        "SerdeInfo": {
                            "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                            "Parameters": {"serialization.format": "1"},
                        },
                    },
                },
            )
            logger.info(f"✅ Partition /{processed_date} created successfully")
        except ClientError as e:
            if e.response["Error"]["Code"] == "AlreadyExistsException":
                logger.info(f"ℹ️ Partition /{processed_date} already exists, skipping.")
            else:
                logger.warning(f"⚠️ Could not create partition: {e}")

    except ClientError as e:
        logger.error(f"❌ AWS ClientError: {e}")
        raise e
    except Exception as e:
        logger.error(f"❌ Unexpected Error: {e}")
        raise e

    return object_key
