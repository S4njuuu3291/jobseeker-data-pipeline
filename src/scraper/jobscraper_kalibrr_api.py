"""Kalibrr listing API adapter using the supplied /kjs/job_board/search contract."""

import logging
from urllib.parse import parse_qs, quote, urlparse

from src.scraper import _api_common as api

logger = logging.getLogger(__name__)
ENDPOINT = "https://kalibrr.id/kjs/job_board/search"


def listing_to_record(job, scraped_at):
    company = job.get("company") or {}
    if not job.get("id") or not job.get("slug") or not company.get("code"):
        raise ValueError("Kalibrr listing lacks id, slug, or company code")
    url = "https://www.kalibrr.com/c/{}/jobs/{}/{}".format(
        quote(company["code"], safe="-"),
        quote(str(job["id"]), safe=""),
        quote(job["slug"], safe="-"),
    )
    location = (job.get("google_location") or {}).get("address_components")
    description = api.summary(
        ("", job.get("name")),
        ("", company.get("name") or job.get("company_name")),
        ("LOCATION", location),
        ("WORK TYPE", job.get("tenure")),
        ("JOB DESCRIPTION", job.get("description")),
        ("QUALIFICATIONS", job.get("qualifications")),
        ("EXPERIENCE", job.get("work_experience")),
        ("PERKS", job.get("perks")),
        ("ABOUT COMPANY", company.get("description")),
        ("INDUSTRY", company.get("industry")),
        (
            "SALARY",
            {
                "min": job.get("base_salary"),
                "max": job.get("maximum_salary"),
                "currency": job.get("salary_currency"),
                "interval": job.get("salary_interval"),
            }
            if job.get("salary_shown")
            else None,
        ),
    )
    return api.record(
        "kalibrr",
        job.get("name"),
        company.get("name") or job.get("company_name"),
        url,
        description,
        scraped_at,
    )


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
    logger.warning(
        "Kalibrr API: respons HTTP sukses belum menjamin filter keyword diterapkan; filter judul existing tetap aktif."
    )
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
    return await api.listing_details(results, "kalibrr")


async def jobscraper_kalibrr(
    url: str, headless: bool = True, seen_ids: set = None, *, max_pages: int = 3
) -> list:
    results = await collect_job_cards(url, headless=headless, max_pages=max_pages)
    results = api.new_records(results, seen_ids)
    return await scrape_job_details(results, headless=headless) if results else results


if __name__ == "__main__":
    api.preview_cli("kalibrr", jobscraper_kalibrr)
