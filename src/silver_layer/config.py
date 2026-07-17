"""Configuration and schema definitions for Silver layer."""

import os
from dotenv import load_dotenv
from pandera.pandas import DataFrameSchema, Column, Check

load_dotenv()


def get_list_platforms() -> list[str]:
    """Get list of job posting platforms from environment variables."""
    platforms = os.getenv("platform")
    if not platforms:
        raise ValueError("platform environment variable not set")
    return platforms.split(",")


def get_bronze_bucket_name() -> str:
    """Get Bronze S3 bucket name from environment variables."""
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("AWS_S3_BUCKET_NAME environment variable not set")
    return bucket_name


def get_silver_bucket_name() -> str:
    """Get Silver S3 bucket name from environment variables."""
    bucket_name = os.getenv("AWS_S3_SILVER_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("AWS_S3_SILVER_BUCKET_NAME environment variable not set")
    return bucket_name


def get_glue_database_name() -> str:
    """Get Glue database name from environment variables."""
    db_name = os.getenv("AWS_GLUE_DATABASE_NAME")
    if not db_name:
        raise ValueError("AWS_GLUE_DATABASE_NAME environment variable not set")
    return db_name


def get_glue_silver_table_name() -> str:
    """Get Glue Silver table name from environment variables."""
    table_name = os.getenv("AWS_GLUE_SILVER_TABLE_NAME")
    if not table_name:
        raise ValueError("AWS_GLUE_SILVER_TABLE_NAME environment variable not set")
    return table_name


# Job posting schema for Silver layer
JOB_SILVER_SCHEMA = DataFrameSchema(
    {
        "job_id": Column(str, unique=True),
        "job_title": Column(str),
        "company_name": Column(str),
        "location": Column(str),
        "job_url": Column(str),
        "platform": Column(str, Check.isin(get_list_platforms())),
        "scraped_at": Column(str),
        "keyword": Column(str),
    }
)