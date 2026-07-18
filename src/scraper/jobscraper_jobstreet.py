# Lazy import untuk cold start cepat
import logging

logger = logging.getLogger(__name__)


async def collect_job_cards(url: str, headless: bool = True) -> list:
    """Scrape listing page, kumpulin semua job card (title, URL, job_id).

    Args:
        url: JobStreet explore URL dengan keyword
        headless: Mode headless browser
    Returns:
        List of dict: [{job_id, job_title, job_url, platform, scraped_at}, ...]
    """
    from playwright.async_api import Browser, BrowserContext, async_playwright
    from src.utils.scraper_utils import (
        normalize_url,
        create_browser,
        create_stealth_context,
        fast_human_scroll,
    )
    from src.utils.time_utils import now_wib
    from tenacity import retry, stop_after_attempt, wait_exponential
    import asyncio
    import hashlib

    async with async_playwright() as p:
        browser: Browser = await create_browser(p, headless=headless)
        try:
            context: BrowserContext = await create_stealth_context(browser)
            page = await context.new_page()

            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
            )
            async def navigate_with_retry():
                logger.info(f"Navigating to URL: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)

            try:
                await navigate_with_retry()
            except Exception as e:
                logger.error(f"Error during page.goto: {type(e).__name__}: {str(e)}")
                return []

            await asyncio.sleep(1)
            for i in range(3):
                await fast_human_scroll(page)
                await asyncio.sleep(1)

            results = []
            job_cards = await page.locator('article[data-automation="normalJob"]').all()
            timestamp = now_wib().strftime("%Y%m%d_%H%M%S")

            for card in job_cards:
                try:
                    title_elem = card.locator('[data-automation="jobTitle"]').first
                    job_title = (await title_elem.text_content()).strip()

                    from src.ai.nlp import filter_job
                    if not filter_job(job_title):
                        continue

                    relative_url = await title_elem.get_attribute("href")
                    if not relative_url:
                        continue
                    full_url = f"https://id.jobstreet.com{relative_url}"
                    job_id = hashlib.md5(normalize_url(full_url).encode()).hexdigest()

                    results.append({
                        "job_id": job_id,
                        "job_title": job_title,
                        "job_url": full_url,
                        "platform": "jobstreet",
                        "scraped_at": timestamp,
                    })
                except Exception:
                    pass

            logger.info(f"\U0001f4e5 Terkumpul {len(results)} URL job")
            return results

        finally:
            await browser.close()


async def scrape_job_details(results: list, headless: bool = True) -> list:
    """Scrape halaman detail untuk ambil job description (plus metadata).

    Args:
        results: List dari collect_job_cards()
        headless: Mode headless browser

    Returns:
        List yang sama dengan tambahan field "job_description"
    """
    if not results:
        return results

    from playwright.async_api import Browser, async_playwright
    from src.utils.scraper_utils import create_browser, create_stealth_context

    async def safe_text(detail_page, selector, timeout=3000):
        try:
            element = await detail_page.wait_for_selector(selector, timeout=timeout)
            return (await element.text_content()).strip() if element else ""
        except Exception:
            return ""

    async with async_playwright() as p:
        browser: Browser = await create_browser(p, headless=headless)
        try:
            context = await create_stealth_context(browser)

            logger.info(f"\n\U0001f4c4 Scraping {len(results)} halaman detail job...")
            for i, job in enumerate(results, 1):
                try:
                    detail_page = await context.new_page()
                    await detail_page.goto(job["job_url"], wait_until="domcontentloaded", timeout=30000)

                    desc = await safe_text(detail_page, '[data-automation="jobAdDetails"]', 5000)
                    title = await safe_text(detail_page, '[data-automation="job-detail-title"]', 2000)
                    company = await safe_text(detail_page, '[data-automation="advertiser-name"]', 2000)
                    location = await safe_text(detail_page, '[data-automation="job-detail-location"]', 2000)
                    salary = await safe_text(detail_page, '[data-automation="job-detail-salary"]', 2000)
                    work_type = await safe_text(detail_page, '[data-automation="job-detail-work-type"]', 2000)

                    full_text = f"{title or ''}\n{company or ''}\n{location or ''}\n{salary or ''}\n{work_type or ''}\n\n{desc or ''}"
                    job["job_description"] = full_text.strip() if full_text.strip() else None

                    if job.get("job_description"):
                        logger.info(f"  [{i}/{len(results)}] \u2705 {job['job_url']}")
                    else:
                        logger.warning(f"  [{i}/{len(results)}] \u26a0\ufe0f Kosong - {job['job_title'][:30]}...")

                    await detail_page.close()
                except Exception as e:
                    logger.warning(f"  [{i}/{len(results)}]  Gagal: {e}")

            return results

        finally:
            await browser.close()


async def jobscraper_jobstreet(url: str, headless: bool = True, seen_ids: set = None) -> list:
    """Main orchestrator: collect cards -> filter manifest -> scrape details."""
    import asyncio
    from src.utils.manifest import filter_new_jobs, update_manifest

    results = await collect_job_cards(url, headless=headless)

    if seen_ids is not None:
        results = filter_new_jobs(results, seen_ids)

    if results:
        results = await scrape_job_details(results, headless=headless)
        new_ids = {j["job_id"] for j in results}
        seen_ids.update(new_ids)
        update_manifest("jobstreet", seen_ids)
        logger.info(f"  \U0001f4cb Manifest diperbarui: +{len(new_ids)} job_id baru (total: {len(seen_ids)})")
    return results


if __name__ == "__main__":
    import asyncio
    from src.utils.manifest import read_manifest, update_manifest, filter_new_jobs

    async def main():
        keyword = "data-engineer-intern"
        url = f"https://id.jobstreet.com/id/{keyword}-jobs?daterange=7"

        seen_ids = read_manifest("jobstreet")
        logger.info(f"\U0001f4cb Sudah ada {len(seen_ids)} job_id di manifest")

        all_cards = await collect_job_cards(url, headless=True)
        logger.info(f"\U0001f4e5 Total card dari listing: {len(all_cards)}")

        new_cards = filter_new_jobs(all_cards, seen_ids)
        logger.info(f"\U0001f195 Job baru (belum di manifest): {len(new_cards)}")

        if new_cards:
            results = await scrape_job_details(new_cards, headless=True)
            new_ids = {c["job_id"] for c in new_cards}
            seen_ids.update(new_ids)
            update_manifest("jobstreet", seen_ids)
            logger.info(f"\n\U0001f4ca Total: {len(results)} job baru discrape & disimpan")
        else:
            logger.info("\u2705 Semua job sudah ada di manifest, tidak ada yang perlu discrape")

    asyncio.run(main())
