"""Jobstreet API scraper producing the 24-column Bronze contract."""

import logging
from urllib.parse import parse_qs, urlparse

from src.scraper import _api_common as api

logger = logging.getLogger(__name__)
ENDPOINT = "https://id.jobstreet.com/api/jobsearch/v5/search"


def listing_to_record(job, scraped_at):
    from src.scraper._bronze import map_record

    return map_record("jobstreet", job, scraped_at)


async def collect_job_cards(
    url: str, headless: bool = True, *, max_pages: int = 1
) -> list:
    api.positive_pages(max_pages)
    keyword = api.search_keyword(url, "jobstreet")
    query = parse_qs(urlparse(url).query)
    params = {
        "siteKey": "ID-Main",
        "keywords": keyword,
        "daterange": (query.get("daterange") or ["7"])[0],
    }
    results, seen, listing_ids = [], set(), set()
    fetched = 0
    scraped_at = api.timestamp()
    async with api.client() as session:
        for page in range(1, max_pages + 1):
            logger.info("Jobstreet API listing page %s", page)
            body = await api.request_json(
                session, "GET", ENDPOINT, params={**params, "page": page}
            )
            jobs = api.list_field(body, "data")
            page_ids = {str(job.get("id")) for job in jobs}
            if not jobs or page_ids.issubset(listing_ids):
                break
            listing_ids.update(page_ids)
            fetched += len(jobs)
            for job in jobs:
                try:
                    api.add_record(results, seen, listing_to_record(job, scraped_at))
                except (ValueError, TypeError, AttributeError):
                    logger.warning(
                        "Skip Jobstreet listing: incomplete or invalid fields"
                    )
            if fetched >= body.get("totalCount", float("inf")):
                break
    logger.info("Terkumpul %s URL job Jobstreet", len(results))
    return results


async def scrape_job_details(results: list, headless: bool = True) -> list:
    from src.scraper._bronze import enrich_details

    return await enrich_details(results, "jobstreet")


async def jobscraper_jobstreet(
    url: str, headless: bool = True, seen_ids: set = None, *, max_pages: int = 1
) -> list:
    results = await collect_job_cards(url, headless=headless, max_pages=max_pages)
    results = api.new_records(results, seen_ids)
    for row in results:
        row["keyword"] = api.search_keyword(url, "jobstreet")
    return await scrape_job_details(results, headless=headless) if results else results


if __name__ == "__main__":
    api.preview_cli("jobstreet", jobscraper_jobstreet)
