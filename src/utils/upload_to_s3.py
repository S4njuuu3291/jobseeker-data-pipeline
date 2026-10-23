from typing import TYPE_CHECKING
import boto3
import io
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from uuid import uuid4
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

    # Incremental batches must not delete jobs uploaded earlier on the same day.
    file_key = f"platform={platform}/ingestion_date={date_str}/{platform}_{timestamp}_{uuid4().hex}.parquet"

    parquet_buffer = io.BytesIO()
    from src.scraper.bronze_schema import BRONZE_COLUMNS, INTEGER_COLUMNS

    if set(df.columns) == set(BRONZE_COLUMNS):
        schema = pa.schema(
            [
                (name, pa.int64() if name in INTEGER_COLUMNS else pa.string())
                for name in BRONZE_COLUMNS
            ]
        )
        table = pa.Table.from_pandas(
            df[list(BRONZE_COLUMNS)], schema=schema, preserve_index=False
        )
        pq.write_table(table, parquet_buffer)
    else:
        df.to_parquet(parquet_buffer, engine="pyarrow", index=False)

    try:
        s3.put_object(Bucket=bucket_name, Key=file_key, Body=parquet_buffer.getvalue())
        print(f" Data mendarat di: s3://{bucket_name}/{file_key}")
        return True
    except Exception as e:
        print(f" Gagal upload ke S3: {e}")
        return False
