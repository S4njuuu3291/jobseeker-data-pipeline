"""Temporary Dealls listing API adapter; full job/company descriptions are absent."""

import logging
from urllib.parse import parse_qs, quote, urlparse

from src.scraper import _api_common as api

logger = logging.getLogger(__name__)
ENDPOINT = "https://api.sejutacita.id/v1/explore-job/job"


def listing_to_record(job, scraped_at):
    company = job.get("company") or {}
    if not job.get("slug") or not company.get("slug"):
        raise ValueError("Dealls listing lacks a job/company slug")
    url = f"https://dealls.com/loker/{quote(job['slug'], safe='-')}~{quote(company['slug'], safe='-')}"
    description = api.summary(
        ("", job.get("role")),
        ("", company.get("name")),
        ("LOCATION", (job.get("city") or {}).get("name")),
        ("EMPLOYMENT TYPES", job.get("employmentTypes")),
        ("WORKPLACE", job.get("workplaceType")),
        ("SALARY", job.get("salaryRange")),
        ("SKILLS", [skill.get("name") for skill in job.get("skills") or []]),
        ("CANDIDATE PREFERENCE", job.get("candidatePreference")),
        ("INDUSTRY", company.get("sector")),
        ("COMPANY INSIGHT", company.get("insight")),
    )
    return api.record(
        "dealls", job.get("role"), company.get("name"), url, description, scraped_at
    )


async def collect_job_cards(
    url: str, headless: bool = True, *, max_pages: int = 1
) -> list:
    """Translate the existing search URL into listing API requests; headless is ignored."""
    api.positive_pages(max_pages)
    keyword = api.search_keyword(url, "dealls")
    query = parse_qs(urlparse(url).query)
    params = {
        "page": 1,
        "limit": 40,
        "sortParam": (query.get("sortParam") or ["publishedAt"])[0],
        "sortBy": (query.get("sortBy") or ["desc"])[0],
        "search": keyword,
        "boostTheBoostedJob": "true",
        "published": "true",
        "status": "active",
    }
    results, seen, listing_ids = [], set(), set()
    scraped_at = api.timestamp()
    logger.warning(
        "Dealls API sementara: deskripsi pekerjaan/kualifikasi dan detail perusahaan tidak tersedia."
    )
    async with api.client(
        {"Origin": "https://dealls.com", "Referer": "https://dealls.com/"}
    ) as session:
        for page in range(1, max_pages + 1):
            logger.info("Dealls API listing page %s", page)
            body = await api.request_json(
                session, "GET", ENDPOINT, params={**params, "page": page}
            )
            if body.get("code") != 200 or not isinstance(body.get("data"), dict):
                raise RuntimeError("Dealls returned an unsuccessful API response")
            data = body["data"]
            jobs = api.list_field(data, "docs")
            page_ids = {str(job.get("id")) for job in jobs}
            if not jobs or page_ids.issubset(listing_ids):
                break
            listing_ids.update(page_ids)
            for job in jobs:
                try:
                    api.add_record(results, seen, listing_to_record(job, scraped_at))
                except (ValueError, TypeError, AttributeError):
                    logger.warning("Skip Dealls listing: incomplete or invalid fields")
            if page >= data.get("totalPages", page):
                break
    logger.info("Terkumpul %s URL job Dealls", len(results))
    return results


async def scrape_job_details(results: list, headless: bool = True) -> list:
    return await api.listing_details(results, "dealls")


async def jobscraper_dealls(
    url: str, headless: bool = True, seen_ids: set = None, *, max_pages: int = 1
) -> list:
    results = await collect_job_cards(url, headless=headless, max_pages=max_pages)
    results = api.new_records(results, seen_ids)
    return await scrape_job_details(results, headless=headless) if results else results


if __name__ == "__main__":
    api.preview_cli("dealls", jobscraper_dealls)
