"""Kalibrr listing API adapter using the supplied /kjs/job_board/search contract."""

import logging
from urllib.parse import parse_qs, urlparse

from src.scraper import _api_common as api

logger = logging.getLogger(__name__)
ENDPOINT = "https://kalibrr.id/kjs/job_board/search"


def listing_to_record(job, scraped_at):
    from src.scraper._bronze import map_record

    return map_record("kalibrr", job, scraped_at)


async def collect_job_cards(
    url: str, headless: bool = True, *, max_pages: int = 3
) -> list:
    """Default 3 pages corresponds to the original listing plus two Load More clicks."""
    api.positive_pages(max_pages)
    keyword = api.search_keyword(url, "kalibrr")
    query = parse_qs(urlparse(url).query)
    params = {
        "text": keyword,
        "sort": (query.get("sort") or ["Freshness"])[0],
        "limit": 20,
    }
    results, seen, listing_ids = [], set(), set()
    scraped_at = api.timestamp()
    async with api.client() as session:
        for page in range(max_pages):
            offset = page * params["limit"]
            logger.info("Kalibrr API listing offset %s", offset)
            body = await api.request_json(
                session, "GET", ENDPOINT, params={**params, "offset": offset}
            )
            jobs = api.list_field(body, "jobs")
            page_ids = {str(job.get("id")) for job in jobs}
            if not jobs or page_ids.issubset(listing_ids):
                break
            listing_ids.update(page_ids)
            for job in jobs:
                try:
                    api.add_record(results, seen, listing_to_record(job, scraped_at))
                except (ValueError, TypeError, AttributeError):
                    logger.warning("Skip Kalibrr listing: incomplete or invalid fields")
            if offset + len(jobs) >= body.get("count", float("inf")):
                break
    logger.info("Terkumpul %s URL job Kalibrr setelah filter judul", len(results))
    return results


async def scrape_job_details(results: list, headless: bool = True) -> list:
    from src.scraper._bronze import enrich_details

    return await enrich_details(results, "kalibrr")


async def jobscraper_kalibrr(
    url: str, headless: bool = True, seen_ids: set = None, *, max_pages: int = 3
) -> list:
    results = await collect_job_cards(url, headless=headless, max_pages=max_pages)
    results = api.new_records(results, seen_ids)
    for row in results:
        row["keyword"] = api.search_keyword(url, "kalibrr")
    return await scrape_job_details(results, headless=headless) if results else results


if __name__ == "__main__":
    api.preview_cli("kalibrr", jobscraper_kalibrr)
