import logging

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import DataFrameSchema, Column, Check
import json

logger = logging.getLogger(__name__)

job_schema = DataFrameSchema(
    {
        "job_id": Column(str, unique=True),
        "job_title": Column(str),
        "job_url": Column(str),
        "platform": Column(
            str, Check.isin(["kalibrr","jobstreet","glints","dealls","techinasia"])
        ),
        "scraped_at": Column(str),
        "job_description": Column(str, nullable=True),
    },
    strict=False,
    coerce=True,
)

def validate_job_data(df: pd.DataFrame):
    try:
        df_validated = job_schema.validate(df)
        logger.info("Data berhasil divalidasi: %s baris", len(df_validated))
        return df_validated
    except pa.errors.SchemaError as e:
        logger.error("Data tidak valid: %s", e)
        raise e


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    file_path = r"output/kalibrr_raw_20260216_081739.json"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            results = json.load(f)
        logger.info("JSON berhasil dimuat dari %s", file_path)

        df = pd.DataFrame(results)

        job_schema.validate(df)
        logger.info("Data berhasil divalidasi: %s baris", len(df))

    except Exception as e:
        logger.exception("Gagal memproses data: %s", e)
