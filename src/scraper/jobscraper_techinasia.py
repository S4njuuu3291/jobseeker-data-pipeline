"""Tech in Asia Algolia listing API adapter with a temporary ID-based job URL."""

import json
import logging
import os
from urllib.parse import urlencode

from src.scraper import _api_common as api

logger = logging.getLogger(__name__)
APP_ID = "219WX3MPV4"
ENDPOINT = "https://219wx3mpv4-dsn.algolia.net/1/indexes/*/queries"


def listing_to_record(job, scraped_at):
    from src.scraper._api_mapping import techinasia

    return techinasia(job, scraped_at)


async def collect_job_cards(
    url: str, headless: bool = True, *, max_pages: int = 1
) -> list:
    api.positive_pages(max_pages)
    keyword = api.search_keyword(url, "techinasia")
    key = os.getenv("TECHINASIA_API_KEY", "").strip()
    if not key:
        raise ValueError("Set TECHINASIA_API_KEY to the Algolia search API key")
    results, seen, listing_ids = [], set(), set()
    scraped_at = api.timestamp()
    logger.warning(
        "Tech in Asia: resolve URL canonical dan konteks perusahaan lewat HTTP setelah filter manifest."
    )
    # Headers avoid exposing the search key through HTTP request URL logs.
    headers = {"x-algolia-application-id": APP_ID, "x-algolia-api-key": key}
    async with api.client(headers) as session:
        for page in range(max_pages):
            logger.info("Tech in Asia API listing page %s", page)
            params = urlencode(
                {
                    "query": keyword,
                    "hitsPerPage": 9,
                    "page": page,
                    "facetFilters": json.dumps(
                        [["city.country_name:Indonesia"]], separators=(",", ":")
                    ),
                }
            )
            body = await api.request_json(
                session,
                "POST",
                ENDPOINT,
                json={"requests": [{"indexName": "job_postings", "params": params}]},
            )
            batches = api.list_field(body, "results")
            if len(batches) != 1:
                raise RuntimeError("Algolia did not return exactly one index result")
            data = batches[0]
            jobs = api.list_field(data, "hits")
            page_ids = {str(job.get("objectID") or job.get("id")) for job in jobs}
            if not jobs or page_ids.issubset(listing_ids):
                break
            listing_ids.update(page_ids)
            for job in jobs:
                try:
                    candidate = listing_to_record(job, scraped_at)
                    if candidate:
                        candidate["_company_slug"] = (job.get("company") or {}).get(
                            "entity_slug"
                        )
                    api.add_record(results, seen, candidate)
                except (ValueError, TypeError, AttributeError):
                    logger.warning(
                        "Skip Tech in Asia listing: incomplete or invalid fields"
                    )
            if page + 1 >= data.get("nbPages", page + 1):
                break
    logger.info("Terkumpul %s URL job Tech in Asia", len(results))
    return results


async def scrape_job_details(results: list, headless: bool = True) -> list:
    from src.scraper._api_details import techinasia_details

    return await techinasia_details(results)


async def jobscraper_techinasia(
    url: str, headless: bool = True, seen_ids: set = None, *, max_pages: int = 1
) -> list:
    results = await collect_job_cards(url, headless=headless, max_pages=max_pages)
    results = api.new_records(results, seen_ids)
    results = (
        await scrape_job_details(results, headless=headless) if results else results
    )
    return api.with_keyword(results, api.search_keyword(url, "techinasia"))


if __name__ == "__main__":
    api.preview_cli("techinasia", jobscraper_techinasia)
