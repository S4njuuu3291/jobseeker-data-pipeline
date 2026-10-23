"""Pipeline orchestration for Silver layer transformations."""

import json
import os
import logging
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import time
import threading

from .config import get_list_platforms
from .transformations import apply_location_normalization
from .validators import validate_silver_schema
from .storage import get_bronze_object, upload_to_silver
from src.ai.nlp import parse_job, empty_result
from src.ai.extraction import FIELDS
from src.scraper.bronze_schema import INTEGER_COLUMNS

logger = logging.getLogger(__name__)

MAX_WORKERS = max(1, int(os.getenv("AI_MAX_WORKERS", "64 ")))


class RateLimiter:
    def __init__(self, rpm_limit: int = 10000, burst_size: int = 500):
        self.rpm_limit = rpm_limit
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_refill = time.time()
        self.lock = threading.Lock()
        self.tokens_per_second = rpm_limit / 60.0

    def acquire(self, timeout: float = 60.0) -> bool:
        start_time = time.time()

        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_refill
                new_tokens = elapsed * self.tokens_per_second
                self.tokens = min(self.burst_size, self.tokens + new_tokens)
                self.last_refill = now

                if self.tokens >= 1:
                    self.tokens -= 1
                    return True

                wait_time = (1 - self.tokens) / self.tokens_per_second

            if wait_time > 0 and wait_time < 0.1:
                time.sleep(0.01)
            elif wait_time > 0:
                time.sleep(min(wait_time, 0.1))

            if time.time() - start_time > timeout:
                return False

    def get_stats(self) -> dict:
        with self.lock:
            return {
                "tokens_available": self.tokens,
                "rpm_limit": self.rpm_limit,
                "burst_size": self.burst_size,
                "tokens_per_second": self.tokens_per_second,
            }


def is_missing(value):
    if value is None:
        return True
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "",
            "unknown",
            "null",
            "none",
            "nan",
            "n/a",
            "[]",
        }
    return bool(pd.isna(value))


def parse_single_job(
    row: Dict[str, Any], idx: int, rate_limiter: RateLimiter
) -> Dict[str, Any]:
    fields = [field for field in FIELDS if is_missing(row.get(field))]
    if not fields:
        result = empty_result()
    else:
        # parse_job owns the retry budget and accounts for every AI request.
        try:
            result = parse_job(
                row.get("job_title", ""),
                row.get("job_description", ""),
                verbose=False,
                request_gate=rate_limiter.acquire,
                fields=fields,
            )
        except Exception:
            logger.exception(
                "AI extraction failed for row %s; missing fields remain null", idx
            )
            result = empty_result(fields, reason="extraction_error", success=False)
    result["_row_idx"] = idx
    result["_parse_success"] = bool(result.get("parsed_success", False))
    return result


def parse_jobs_parallel(df: pd.DataFrame) -> List[Dict[str, Any]]:
    total_rows = len(df)
    logger.info(
        f"Starting parallel AI parsing for {total_rows} records with {MAX_WORKERS} workers"
    )

    rows = df.to_dict("records")
    results = [None] * total_rows
    rate_limiter = RateLimiter(
        rpm_limit=max(1, int(os.getenv("AI_RPM_LIMIT", "120"))), burst_size=MAX_WORKERS
    )

    success_count = 0
    skipped_count = 0
    error_count = 0
    total_tokens = 0
    total_cost = 0.0

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for idx, row in enumerate(rows):
            future = executor.submit(parse_single_job, row, idx, rate_limiter)
            futures[future] = idx

        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result(timeout=60)
                results[idx] = result

                total_tokens += result.get("api_usage_total_tokens", 0)
                total_cost += result.get("api_cost_usd", 0.0)
                if result.get("api_finish_reason") == "not_needed":
                    skipped_count += 1
                elif result.get("_parse_success", False):
                    success_count += 1
                else:
                    error_count += 1

            except Exception as e:
                logger.error(f"Thread error for row {idx}: {e}")
                error_count += 1
                results[idx] = empty_result(reason="thread_error", success=False)
                results[idx]["_row_idx"] = idx
                results[idx]["_parse_success"] = False

    elapsed = time.time() - start_time

    logger.info(f"Parallel AI parsing completed in {elapsed:.2f}s")
    logger.info(
        f"AI success: {success_count}/{total_rows} ({success_count / max(total_rows, 1) * 100:.1f}%)"
    )
    logger.info(f"Unresolved/error: {error_count}/{total_rows}")
    logger.info("Skipped AI (Bronze complete): %s/%s", skipped_count, total_rows)
    logger.info(f"Total tokens: {total_tokens:,}")
    logger.info(f"Est. cost: ${total_cost:.6f} (Rp {total_cost * 16000:.2f})")
    logger.info(f"Throughput: {total_rows / elapsed:.2f} jobs/sec")

    return results


def transform_silver(df: pd.DataFrame) -> str:
    logger.info("Processing %s records; AI fills only missing fields", len(df))
    if not df.columns.is_unique:
        raise ValueError("Bronze has duplicate column names")
    df = df.copy().reset_index(drop=True)
    for field in FIELDS:
        if field not in df.columns:
            df[field] = None
        # Normalize missing sentinels without turning a genuine zero into null.
        df[field] = (
            df[field]
            .map(lambda value: None if is_missing(value) else value)
            .astype(object)
        )
    if "company_name" not in df.columns:
        df["company_name"] = None
    parsed_results = parse_jobs_parallel(df)
    metadata = list(empty_result())
    for idx, result in enumerate(parsed_results):
        for field in FIELDS:
            value = result.get(field)
            if is_missing(df.at[idx, field]) and not is_missing(value):
                df.at[idx, field] = value
    for name in metadata:
        df[name] = [result.get(name, empty_result()[name]) for result in parsed_results]
    df = apply_location_normalization(df)
    for field in INTEGER_COLUMNS:
        df[field] = pd.to_numeric(df[field], errors="raise").astype("Int64")
    for field in ("skills", "benefits"):
        df[field] = df[field].map(
            lambda value: (
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, list)
                else value
            )
        )
    df_validated = validate_silver_schema(df)
    object_key = upload_to_silver(df_validated)
    logger.info("Silver layer pipeline completed - %s", object_key)
    return object_key


def run_pipeline() -> dict:
    try:
        logger.info("Starting Silver layer pipeline")

        list_platforms = get_list_platforms()
        logger.info(f"Processing platforms: {list_platforms}")

        df_bronze = get_bronze_object(list_platforms)
        logger.info(f"Read {len(df_bronze)} records from Bronze layer")

        object_key = transform_silver(df_bronze)

        return {
            "statusCode": 200,
            "message": "Data transformation to Silver successful",
            "object_key": object_key,
        }

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "message": f"Data transformation to Silver failed: {str(e)}",
            "error": str(e),
        }
