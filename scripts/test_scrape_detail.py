"""Test cepat scrape_job_details saja tanpa full pipeline."""
import asyncio
import sys
sys.path.insert(0, ".")

from src.scraper.jobscraper_glints import scrape_job_details as glints_detail
from src.scraper.jobscraper_jobstreet import scrape_job_details as jobstreet_detail
from src.scraper.jobscraper_kalibrr import scrape_job_details as kalibrr_detail

async def test_glints():
    results = [{
        "job_id": "test-001",
        "job_title": "Data Engineer Intern",
        "job_url": "https://glints.com/id/opportunities/jobs/data-engineer/a0bdb6e2-8162-4810-8248-d76b54cf4fad?traceInfo=fc8003d4-237a-42bf-ad11-e7fd70e8a6ee",
    }]
    enriched = await glints_detail(results, headless=False)
    print(f"\nGlints: {enriched}")

async def test_jobstreet():
    results = [{
        "job_id": "test-001",
        "job_title": "Data Engineer Intern",
        "job_url": "https://id.jobstreet.com/id/job/93335984?type=standard&ref=search-standalone&origin=cardTitle",
    }]
    enriched = await jobstreet_detail(results, headless=False)
    print(f"\nJobStreet: {enriched}")

async def test_kalibrr():
    results = [{
        "job_id": "test-001",
        "job_title": "Data Engineer Intern",
        "job_url": "https://www.kalibrr.id/job/kalibrr-data-engineer-intern-1",
    }]
    enriched = await kalibrr_detail(results, headless=False)
    print(f"\nKalibrr: {enriched}")


if __name__ == "__main__":
    asyncio.run(test_jobstreet())
