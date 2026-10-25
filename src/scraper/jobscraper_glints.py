"""Glints API scraper producing the 24-column Bronze contract."""

import logging
import os
from urllib.parse import parse_qs, urlparse

from src.scraper import _api_common as api

logger = logging.getLogger(__name__)
ENDPOINT = "https://glints.com/api/v2-alc/graphql?op=searchJobsV3"
# Only fields verified in glints.txt; the listing contract has no description field.
QUERY = """
query searchJobsV3($data: JobSearchConditionInput!) {
  searchJobsV3(data: $data) {
    jobsInPage {
      id title workArrangementOption status createdAt updatedAt isHot isApplied
      shouldShowSalary educationLevel type fraudReportFlag
      company {
        id name brandName logo status isVIP IndustryId
        industry { id name }
        verificationTier { type userName }
      }
      citySubDivision { id name }
      city { id name }
      country { code name }
      salaries { id salaryType salaryMode maxAmount minAmount CurrencyCode }
      location {
        id name administrativeLevelName formattedName level slug latitude longitude
        parents {
          id name administrativeLevelName formattedName level slug
          CountryCode: countryCode
          parents { level formattedName slug }
        }
      }
      minYearsOfExperience maxYearsOfExperience source jobSource
      hierarchicalJobCategory {
        id level name
        children { name level id }
        parents { id level name }
      }
      skills { skill { id name } mustHave }
      traceInfo
    }
    expInfo hasMore
  }
}
"""


def listing_to_record(job, scraped_at):
    from src.scraper._bronze import map_record

    return map_record("glints", job, scraped_at)


async def collect_job_cards(
    url: str, headless: bool = True, *, max_pages: int = 1
) -> list:
    api.positive_pages(max_pages)
    keyword = api.search_keyword(url, "glints")
    cookie = os.getenv("GLINTS_COOKIE", "").strip()
    if not cookie:
        raise ValueError(
            "Set GLINTS_COOKIE to an authorized browser session before calling Glints API"
        )
    query = parse_qs(urlparse(url).query)
    variables = {
        "SearchTerm": keyword,
        "CountryCode": (query.get("country") or ["ID"])[0],
        "sortBy": (query.get("sortBy") or ["LATEST"])[0],
        "includeExternalJobs": True,
        "pageSize": 30,
        "page": 1,
    }
    results, seen, listing_ids = [], set(), set()
    scraped_at = api.timestamp()
    headers = {
        "Cookie": cookie,
        "Origin": "https://glints.com",
        "Referer": "https://glints.com/",
        "x-glints-country-code": variables["CountryCode"],
    }
    async with api.client(headers) as session:
        for page in range(1, max_pages + 1):
            logger.info("Glints API listing page %s", page)
            payload = {
                "operationName": "searchJobsV3",
                "query": QUERY,
                "variables": {"data": {**variables, "page": page}},
            }
            body = await api.request_json(session, "POST", ENDPOINT, json=payload)
            if body.get("isAuthenticated") is not True:
                raise RuntimeError(
                    "Glints session is missing or expired; refresh GLINTS_COOKIE"
                )
            data = (body.get("data") or {}).get("searchJobsV3")
            if not isinstance(data, dict):
                raise RuntimeError("Glints response is missing searchJobsV3")
            jobs = api.list_field(data, "jobsInPage")
            page_ids = {str(job.get("id")) for job in jobs}
            if not jobs or page_ids.issubset(listing_ids):
                break
            listing_ids.update(page_ids)
            for job in jobs:
                try:
                    api.add_record(results, seen, listing_to_record(job, scraped_at))
                except (ValueError, TypeError, AttributeError):
                    logger.warning("Skip Glints listing: incomplete or invalid fields")
            if not data.get("hasMore"):
                break
    logger.info("Terkumpul %s URL job Glints", len(results))
    return results


async def scrape_job_details(results: list, headless: bool = True) -> list:
    from src.scraper._bronze import enrich_details

    return await enrich_details(results, "glints")


async def jobscraper_glints(
    url: str, headless: bool = True, seen_ids: set = None, *, max_pages: int = 1
) -> list:
    results = await collect_job_cards(url, headless=headless, max_pages=max_pages)
    results = api.new_records(results, seen_ids)
    for row in results:
        row["keyword"] = api.search_keyword(url, "glints")
    return await scrape_job_details(results, headless=headless) if results else results


if __name__ == "__main__":
    api.preview_cli("glints", jobscraper_glints)
