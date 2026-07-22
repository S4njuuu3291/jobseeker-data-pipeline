"""Data validation for Silver layer."""

import logging
import pandas as pd
import pandera.pandas as pa
from .config import JOB_SILVER_SCHEMA

logger = logging.getLogger(__name__)


def validate_silver_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Validate dataframe against Silver layer schema.

    Args:
        df: Input dataframe to validate

    Returns:
        Validated dataframe

    Raises:
        pa.errors.SchemaError: If dataframe doesn't match schema
    """
    try:
        df_validated = JOB_SILVER_SCHEMA.validate(df)
        logger.info(" Data validation against silver schema successful.")
        return df_validated
    except pa.errors.SchemaError as e:
        logger.error(f" Data validation against silver schema failed: {e}")
        raise e
