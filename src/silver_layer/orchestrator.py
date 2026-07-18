"""Pipeline orchestration for Silver layer transformations."""

import json
import logging
import pandas as pd

from .config import get_list_platforms
from .transformations import apply_location_normalization
from .validators import validate_silver_schema
from .storage import get_bronze_object, upload_to_silver
from src.ai.nlp import parse_job

logger = logging.getLogger(__name__)


def transform_silver(df: pd.DataFrame) -> str:
    """Orchestrate Silver layer transformation pipeline.

    Pipeline steps:
    1. AI parsing — extract structured fields from job_description
    2. Apply location normalization
    3. Validate against Silver schema
    4. Upload to Silver S3 bucket

    Args:
        df: Bronze layer dataframe

    Returns: [×2]
        S3 object key of uploaded file
    """
    logger.info(" Starting AI parsing step...")
    logger.info(f"Processing {len(df)} records")

    # Step 1: AI parsing
    parsed_records = []
    for idx, row in df.iterrows():
        try:
            result = parse_job(
                job_title=row.get("job_title", ""),
                job_description=row.get("job_description", ""),
                job_url=row.get("job_url", ""),
                keyword=row.get("keyword", ""),
            )
            logger.info(f" AI parse successful for row {idx}: {result['role']}")
            # Convert list fields to JSON string for parquet compatibility
            if isinstance(result.get("skills"), list):
                result["skills"] = json.dumps(result["skills"])
            if isinstance(result.get("benefits"), list):
                result["benefits"] = json.dumps(result["benefits"])
            parsed_records.append(result)
        except Exception as e:
            logger.warning(f"  AI parse failed for row {idx}: {e}, using defaults")
            parsed_records.append({
                "role": None,
                "company_name": None,
                "location": None,
                "salary_min": None,
                "salary_max": None,
                "salary_currency": None,
                "salary_period": None,
                "job_type": None,
                "seniority": None,
                "work_mode": None,
                "experience_min": None,
                "experience_max": None,
                "education": None,
                "company_industry": None,
                "skills": None,
                "benefits": None,
                "posting_date": None,
            })

    # Merge parsed fields into bronze DataFrame (skip job_title — already from bronze)
    df_parsed = pd.DataFrame(parsed_records)
    df_parsed = df_parsed.drop(columns=["job_title"], errors="ignore")
    df = pd.concat([df, df_parsed], axis=1)
    logger.info(f" AI parsing completed for {len(parsed_records)} records")

    # Step 2: Apply transformations
    logger.info("Starting location normalization...")
    df = apply_location_normalization(df)
    logger.info("Location normalization completed.")

    # Step 2.5: Fill NaN values for numeric columns
    numeric_columns = ['salary_min', 'salary_max', 'experience_min', 'experience_max']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    # Step 3: Validate schema
    logger.info("Validating data against Silver schema...")
    df_validated = validate_silver_schema(df)

    # Step 4: Upload to Silver layer
    logger.info("Uploading data to Silver layer...")
    object_key = upload_to_silver(df_validated)
    logger.info(f" Silver layer pipeline completed successfully — {object_key}")

    return object_key

def run_pipeline() -> dict:
    """Run complete Silver layer pipeline.

    Returns:
        Pipeline execution result containing object key and status
    """
    try:
        logger.info("Starting Silver layer pipeline...")

        # Get platforms configuration
        list_platforms = get_list_platforms()
        logger.info(f"Processing platforms: {list_platforms}")

        # Read from Bronze
        df_bronze = get_bronze_object(list_platforms)
        logger.info(f"Read {len(df_bronze)} records from Bronze layer")

        # Transform data
        object_key = transform_silver(df_bronze)

        logger.info(" Silver layer pipeline completed successfully")
        return {
            "statusCode": 200,
            "message": "Data transformation to Silver successful",
            "object_key": object_key,
        }

    except Exception as e:
        logger.error(f" Pipeline failed: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "message": f"Data transformation to Silver failed: {str(e)}",
            "error": str(e),
        }