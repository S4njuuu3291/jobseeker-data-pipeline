# Lazy import untuk cold start cepat
import logging

logger = logging.getLogger(__name__)


async def collect_job_cards(url: str, headless: bool = True) -> list:
    """Scrape listing page, kumpulin semua job card (title, URL, job_id).

    Args:
        url: Kalibrr explore URL dengan keyword
        headless: Mode headless browser
    Returns:
        List of dict: [{job_id, job_title, job_url, platform, scraped_at}, ...]
    """
    from playwright.async_api import Browser, BrowserContext, async_playwright
    from src.utils.scraper_utils import (
        normalize_url,
        create_browser,
        create_stealth_context,
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

            ad_hosts = [
                "doubleclick.net", "googlesyndication.com", "google-analytics.com",
                "googletagmanager.com", "adsystem.com", "ads.yahoo.com", "adservice.google.com",
            ]
            image_exts = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"]

            async def route_handler(route):
                url_lower = route.request.url.lower()
                if any(host in url_lower for host in ad_hosts) or any(
                    url_lower.endswith(ext) for ext in image_exts
                ):
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", route_handler)

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

            # Klik "Load more jobs" untuk reveal semua card
            button_selector = "button.k-btn-primary:has-text('Load more jobs')"
            max_clicks = 2
            for i in range(max_clicks):
                try:
                    load_more = await page.wait_for_selector(button_selector, timeout=3000)
                    if load_more:
                        await load_more.click()
                        logger.info(f"Klik Load More ke-{i + 1}...")
                        await asyncio.sleep(2)
                except Exception:
                    break

            job_cards = await page.locator("div.css-1otdiuc").all()
            timestamp = now_wib().strftime("%Y%m%d_%H%M%S")
            results = []

            for card in job_cards:
                try:
                    title_elem = card.locator('h2 a[itemprop="name"]').first
                    job_title = (await title_elem.text_content()).strip()

                    from src.utils.manifest import is_relevant_title
                    if not is_relevant_title(job_title):
                        continue

                    relative_url = await title_elem.get_attribute("href")
                    if not relative_url:
                        continue
                    full_url = f"https://www.kalibrr.com{relative_url}"

                    job_id = hashlib.md5(normalize_url(full_url).encode()).hexdigest()

                    results.append({
                        "job_id": job_id,
                        "job_title": job_title,
                        "job_url": full_url,
                        "platform": "kalibrr",
                        "scraped_at": timestamp,
                    })
                except Exception as e:
                    logger.warning(f"Gagal ekstrak card: {e}")

            logger.info(f"\U0001f4e5 Terkumpul {len(results)} URL job")
            return results

        finally:
            await browser.close()


async def scrape_job_details(results: list, headless: bool = True) -> list:
    """Scrape halaman detail untuk ambil job description.

    Args:
        results: List dari collect_job_cards()
        headless: Mode headless browser

    Returns:
        List yang sama dengan tambahan field "job_description"
    """
    if not results:
        return results

    from playwright.async_api import Browser, async_playwright
    from bs4 import BeautifulSoup
    from src.utils.scraper_utils import create_browser, create_stealth_context

    async with async_playwright() as p:
        browser: Browser = await create_browser(p, headless=headless)
        try:
            context = await create_stealth_context(browser)

            logger.info(f"\n\U0001f4c4 Scraping {len(results)} halaman detail job...")
            for i, job in enumerate(results, 1):
                try:
                    detail_page = await context.new_page()
                    await detail_page.goto(job["job_url"], wait_until="domcontentloaded", timeout=30000)

                    html = await detail_page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    container = soup.select_one('div.k-bg-white.k-relative.k-p-4.md\\:k-rounded-b-lg')
                    job_desc = container.get_text(separator="\n", strip=True) if container else ""

                    job["job_description"] = job_desc or None
                    logger.info(f"  [{i}/{len(results)}] ✅ {job['job_url']}")

                    await detail_page.close()
                except Exception as e:
                    logger.warning(f"  [{i}/{len(results)}] \u26a0\ufe0f Gagal: {e}")

            return results

        finally:
            await browser.close()


async def jobscraper_kalibrr(url: str, headless: bool = True, seen_ids: set = None) -> list:
    """Main orchestrator: collect cards -> filter manifest -> scrape details."""
    import asyncio
    from src.utils.manifest import filter_new_jobs

    try:
        results = await collect_job_cards(url, headless=headless)
    except Exception as e:
        logger.error(f"collect_job_cards gagal: {e}")
        return []

    if seen_ids is not None:
        results = filter_new_jobs(results, seen_ids)

    if results:
        results = await scrape_job_details(results, headless=headless)
        # Pastikan job_description ada walau scrape gagal per-row
        for j in results:
            j.setdefault("job_description", "")
    return results


if __name__ == "__main__":
    import asyncio
    from src.utils.manifest import read_manifest, update_manifest, filter_new_jobs

    async def main():
        keyword = "data-engineer-intern"
        url = f"https://kalibrr.id/id-ID/home/te/{keyword}?sort=Freshness"

        seen_ids = read_manifest("kalibrr")
        logger.info(f"\U0001f4cb Sudah ada {len(seen_ids)} job_id di manifest")

        all_cards = await collect_job_cards(url, headless=True)
        logger.info(f"\U0001f4e5 Total card dari listing: {len(all_cards)}")

        new_cards = filter_new_jobs(all_cards, seen_ids)
        logger.info(f"\U0001f195 Job baru (belum di manifest): {len(new_cards)}")

        if new_cards:
            results = await scrape_job_details(new_cards, headless=True)
            new_ids = {c["job_id"] for c in new_cards}
            seen_ids.update(new_ids)
            update_manifest("kalibrr", seen_ids)
            logger.info(f"\n\U0001f4ca Total: {len(results)} job baru discrape & disimpan")
        else:
            logger.info("\u2705 Semua job sudah ada di manifest, tidak ada yang perlu discrape")

    asyncio.run(main())
