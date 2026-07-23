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
        "job_url": "https://glints.com/id/opportunities/jobs/it-support-engineer/334e3787-771f-44ff-add8-1814c3bd72f1?traceInfo=208b15a1-8ddd-47a5-9199-cc95a8790272",
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
    asyncio.run(test_glints())
