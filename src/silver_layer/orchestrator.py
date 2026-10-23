"""Pipeline orchestration for Silver layer transformations."""

import json
import os
import logging
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import time
import threading
import random

from .config import get_list_platforms
from .transformations import apply_location_normalization
from .validators import validate_silver_schema
from .storage import get_bronze_object, upload_to_silver
from src.ai.nlp import parse_job

logger = logging.getLogger(__name__)

MAX_WORKERS = max(1, int(os.getenv("AI_MAX_WORKERS", "64 ")))
MAX_RETRIES = 3


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


def parse_single_job(row: Dict[str, Any], idx: int, rate_limiter: RateLimiter) -> Dict[str, Any]:
    base_delay = 1.0
    
    for attempt in range(MAX_RETRIES):
        try:
            result = parse_job(
                row.get("job_title", ""),
                row.get("job_description", ""),
                row.get("job_url", ""),
                row.get("keyword", ""),
                False,
                request_gate=rate_limiter.acquire,
            )
            
            result["_row_idx"] = idx
            result["_parse_success"] = bool(result.get("parsed_success", False))
            return result
            
        except Exception as e:
            error_msg = str(e).lower()
            is_rate_limit = any(k in error_msg for k in ["rate limit", "too many", "429", "quota", "throttle"])
            
            if attempt == MAX_RETRIES - 1:
                logger.error(f"Failed row {idx} after {MAX_RETRIES} attempts: {e}")
                break
            
            if is_rate_limit:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(f"Rate limit hit row {idx}, retry {attempt+1}/{MAX_RETRIES} in {delay:.2f}s")
            else:
                delay = base_delay * (1.5 ** attempt) + random.uniform(0, 0.2)
                logger.warning(f"Error row {idx}: {e}, retry {attempt+1}/{MAX_RETRIES} in {delay:.2f}s")
            
            time.sleep(delay)
    
    return {
        "job_title": row.get("job_title", ""),
        "role": "Unknown",
        "location": "Unknown",
        "salary_min": 0,
        "salary_max": 0,
        "salary_currency": "IDR",
        "salary_period": "monthly",
        "job_type": "full_time",
        "seniority": "mid",
        "work_mode": "unknown",
        "experience_min": 0,
        "experience_max": 0,
        "education": "unknown",
        "company_industry": "Unknown",
        "skills": [],
        "benefits": [],
        "posting_date": "",
        "api_model": "error",
        "api_usage_total_tokens": 0,
        "api_usage_prompt_tokens": 0,
        "api_usage_completion_tokens": 0,
        "api_cache_hit_tokens": 0,
        "api_cache_miss_tokens": 0,
        "api_finish_reason": "max_retries_exceeded",
        "api_cost_usd": 0.0,
        "api_cost_idr": 0.0,
        "api_attempt": 0,
        "parsed_success": False,
        "parsed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "_row_idx": idx,
        "_parse_success": False,
    }


def parse_jobs_parallel(df: pd.DataFrame) -> List[Dict[str, Any]]:
    total_rows = len(df)
    logger.info(f"Starting parallel AI parsing for {total_rows} records with {MAX_WORKERS} workers")
    
    rows = df.to_dict('records')
    results = [None] * total_rows
    rate_limiter = RateLimiter(rpm_limit=max(1, int(os.getenv("AI_RPM_LIMIT", "120"))), burst_size=MAX_WORKERS)
    
    success_count = 0
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
                if result.get("_parse_success", False):
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Thread error for row {idx}: {e}")
                error_count += 1
                results[idx] = {
                    "job_title": rows[idx].get("job_title", ""),
                    "role": "Unknown",
                    "location": "Unknown",
                    "salary_min": 0,
                    "salary_max": 0,
                    "salary_currency": "IDR",
                    "salary_period": "monthly",
                    "job_type": "full_time",
                    "seniority": "mid",
                    "work_mode": "unknown",
                    "experience_min": 0,
                    "experience_max": 0,
                    "education": "unknown",
                    "company_industry": "Unknown",
                    "skills": [],
                    "benefits": [],
                    "posting_date": "",
                    "api_model": "error",
                    "api_usage_total_tokens": 0,
                    "api_usage_prompt_tokens": 0,
                    "api_usage_completion_tokens": 0,
                    "api_cache_hit_tokens": 0,
                    "api_cache_miss_tokens": 0,
                    "api_finish_reason": "thread_error",
                    "api_cost_usd": 0.0,
                    "api_cost_idr": 0.0,
                    "api_attempt": 0,
                    "parsed_success": False,
                    "parsed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "_row_idx": idx,
                    "_parse_success": False,
                }
    
    elapsed = time.time() - start_time
    
    logger.info(f"Parallel AI parsing completed in {elapsed:.2f}s")
    logger.info(f"AI success: {success_count}/{total_rows} ({success_count/max(total_rows, 1)*100:.1f}%)")
    logger.info(f"Fallback/error: {error_count}/{total_rows}")
    logger.info(f"Total tokens: {total_tokens:,}")
    logger.info(f"Est. cost: ${total_cost:.6f} (Rp {total_cost*16000:.2f})")
    logger.info(f"Throughput: {total_rows/elapsed:.2f} jobs/sec")
    
    return results


def transform_silver(df: pd.DataFrame) -> str:
    logger.info(f"Processing {len(df)} records")
    
    parsed_results = parse_jobs_parallel(df)
    
    df_parsed = pd.DataFrame(parsed_results)
    df_parsed = df_parsed.drop(columns=["_row_idx", "_parse_success"], errors="ignore")
    df_parsed = df_parsed.drop(columns=["job_title", "company_name"], errors="ignore")
    if "company_name" not in df.columns:
        df["company_name"] = "Unknown"
    
    df = pd.concat([df, df_parsed], axis=1)
    logger.info(f"AI parsing completed for {len(parsed_results)} records")
    
    df = apply_location_normalization(df)
    logger.info("Location normalization completed")
    
    numeric_columns = ['salary_min', 'salary_max', 'experience_min', 'experience_max']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    list_columns = ['skills', 'benefits']
    for col in list_columns:
        if col in df.columns and df[col].dtype == 'object':
            df[col] = df[col].apply(
                lambda x: json.loads(x) if isinstance(x, str) and x.startswith('[') else x
            )
            df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, list) else x)
    
    df_validated = validate_silver_schema(df)
    
    object_key = upload_to_silver(df_validated)
    logger.info(f"Silver layer pipeline completed - {object_key}")
    
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
