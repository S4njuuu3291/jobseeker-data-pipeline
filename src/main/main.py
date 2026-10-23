"""Shared Bronze pipeline for all job platforms."""

import argparse
import asyncio
import logging
from importlib import import_module
from urllib.parse import quote

logger = logging.getLogger(__name__)

URL_TEMPLATES = {
    "glints": "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}&country=ID&locationName=All+Cities%2FProvinces&lowestLocationLevel=1&sortBy=LATEST",
    "kalibrr": "https://kalibrr.id/id-ID/home/te/{keyword}?sort=Freshness",
    "jobstreet": "https://id.jobstreet.com/id/{keyword}-jobs?daterange=7",
    "dealls": "https://dealls.com/?sortParam=publishedAt&searchJob={keyword}",
    "techinasia": "https://www.techinasia.com/jobs/search?query={keyword}&country_name[]=Indonesia",
}


def build_search_url(platform: str, keyword: str) -> str:
    """Preserve each platform's keyword format and search parameters."""
    if platform not in URL_TEMPLATES:
        raise ValueError(f"Unsupported platform: {platform}")
    if platform == "techinasia":
        keyword = quote(keyword, safe="")
    return URL_TEMPLATES[platform].format(keyword=keyword)


async def run_scraper_pipeline(platform: str, keywords: list[str]) -> int:
    """Scrape, deduplicate, validate, upload, then persist the manifest."""
    if platform not in URL_TEMPLATES:
        raise ValueError(f"Unsupported platform: {platform}")
    if not keywords:
        return 0

    # Heavy imports remain lazy for Lambda cold starts.
    import pandas as pd
    from src.utils.data_validator import validate_job_data
    from src.utils.manifest import read_manifest, update_manifest
    from src.utils.upload_to_s3 import upload_to_s3

    module = import_module(f"src.scraper.jobscraper_{platform}")
    scraper = getattr(module, f"jobscraper_{platform}")
    seen_ids = set(read_manifest(platform))
    records = []

    for keyword in keywords:
        logger.info("Scraping %s keyword: %s", platform, keyword)
        jobs = await scraper(
            build_search_url(platform, keyword), headless=True, seen_ids=seen_ids
        )
        for job in jobs:
            jid = job.get("job_id")
            if jid and jid in seen_ids:
                continue
            records.append({**job, "keyword": keyword})
            if jid:
                seen_ids.add(jid)

    if not records:
        logger.info("No new jobs for %s; skipping upload.", platform)
        return 0

    df = pd.DataFrame(records).drop_duplicates(subset=["job_id"])
    df_validated = validate_job_data(df)
    if not upload_to_s3(df_validated, platform=platform):
        logger.error("Bronze upload failed for %s; manifest unchanged.", platform)
        return 0

    if not update_manifest(platform, seen_ids):
        raise RuntimeError(f"Bronze uploaded but manifest update failed for {platform}")
    logger.info("%s: uploaded %s new jobs.", platform, len(df_validated))
    return len(df_validated)


async def run_glints_pipeline(keywords: list[str]) -> int:
    return await run_scraper_pipeline("glints", keywords)


async def run_kalibrr_pipeline(keywords: list[str]) -> int:
    return await run_scraper_pipeline("kalibrr", keywords)


async def run_jobstreet_pipeline(keywords: list[str]) -> int:
    return await run_scraper_pipeline("jobstreet", keywords)


async def run_dealls_pipeline(keywords: list[str]) -> int:
    return await run_scraper_pipeline("dealls", keywords)


async def run_techinasia_pipeline(keywords: list[str]) -> int:
    return await run_scraper_pipeline("techinasia", keywords)


async def run_cli(platform: str, keywords: list[str] | None = None) -> None:
    from dotenv import load_dotenv
    from src.entrypoint.handlers import PLATFORM_KEYWORDS, _get_keywords

    load_dotenv()
    platforms = list(URL_TEMPLATES) if platform == "all" else [platform]
    for selected in platforms:
        if keywords is None:
            selected_keywords = _get_keywords(PLATFORM_KEYWORDS[selected])
        else:
            separator = "+" if selected in {"glints", "dealls"} else "-"
            selected_keywords = [
                keyword if selected == "techinasia" else keyword.replace(" ", separator)
                for keyword in keywords
            ]
        count = await run_scraper_pipeline(selected, selected_keywords)
        print(f"{selected}: {count} jobs uploaded")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local scraper pipelines and upload to Bronze S3.")
    parser.add_argument("--platform", required=True, choices=[*URL_TEMPLATES, "all"])
    parser.add_argument("--keywords", nargs="+", help='Override keywords, e.g. --keywords "data engineer" "etl".')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(run_cli(args.platform, args.keywords))


if __name__ == "__main__":
    main()
