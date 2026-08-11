# Lazy import untuk cold start cepat
import logging

logger = logging.getLogger(__name__)


async def collect_job_cards(url: str, headless: bool = True) -> list:
    """Scrape listing page, kumpulin semua job card (title, URL, job_id).

    Args:
        url: TechInAsia search URL dengan keyword
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
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
    )
    from src.utils.manifest import is_relevant_title
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
            timestamp = now_wib().strftime("%Y%m%d_%H%M%S")

            # Navigasi dengan retry
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception_type(Exception),
            )
            async def navigate_with_retry():
                logger.info(f"Navigating to URL: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if "not-found" in page.url:
                    raise Exception("Page not found")

            await navigate_with_retry()
            logger.info("Waiting 5 seconds for hydration...")
            await page.wait_for_timeout(5000)

            # Scroll pelan
            logger.info("Waiting for job cards...")
            for _ in range(3):
                await fast_human_scroll(page)
                await asyncio.sleep(1)

            # Selector card TechInAsia: link ke halaman detail job
            selector = 'a[href^="/jobs/"]'
            try:
                await page.wait_for_selector(selector, timeout=20000)
            except Exception:
                logger.warning("Tidak ada job card ditemukan (selector kosong)")
                return []

            job_cards = await page.locator(selector).all()
            logger.info(f"Found {len(job_cards)} potential cards")

            results = []
            for card in job_cards:
                try:
                    # Title ada di text card, ambil text_content
                    job_title = (await card.text_content()).strip().split("\n")[0].strip()
                    if not job_title:
                        continue

                    # Filter IT jobs
                    if not is_relevant_title(job_title):
                        continue

                    relative_url = await card.get_attribute("href")
                    if not relative_url:
                        continue

                    full_url = f"https://www.techinasia.com{relative_url}"
                    job_id = hashlib.md5(normalize_url(full_url).encode()).hexdigest()

                    results.append({
                        "job_id": job_id,
                        "job_title": job_title,
                        "job_url": full_url,
                        "platform": "techinasia",
                        "scraped_at": timestamp,
                    })
                except Exception as e:
                    logger.warning(f"  Skip card: {e}")

            logger.info(f"Terkumpul {len(results)} URL job")
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
    from src.utils.scraper_utils import create_browser, create_stealth_context

    async with async_playwright() as p:
        browser: Browser = await create_browser(p, headless=headless)
        try:
            context = await create_stealth_context(browser)
            detail_page = await context.new_page()

            logger.info(f"Scraping {len(results)} halaman detail job...")
            for i, job in enumerate(results, 1):
                try:
                    await detail_page.goto(job["job_url"], wait_until="domcontentloaded", timeout=30000)

                    # Ambil data detail dengan selector spesifik TechInAsia
                    detail = await detail_page.evaluate("""() => {
                        // Job title dari h1 (kalau ada), fallback dari meta
                        const h1 = document.querySelector('h1');
                        const title = h1 ? h1.innerText.trim() : '';
                        // Company
                        const companyLink = document.querySelector('a[href^="/companies/"]');
                        const company = companyLink ? companyLink.innerText.trim() : '';
                        // Description section (bullets) - cari tag b job type & YOE
                        const bTags = Array.from(document.querySelectorAll('b')).map(b => b.innerText.trim());
                        const jobType = bTags.find(t => /full.?time|part.?time|contract|intern/i.test(t)) || '';
                        const yoe = bTags.find(t => /year|yoe|experience/i.test(t)) || '';
                        // Description body (main content)
                        const main = document.querySelector('main') || document.body;
                        const description = main ? main.innerText.trim() : '';
                        return { title, company, jobType, yoe, description };
                    }""")

                    parts = [
                        detail.get("title") or "",
                        detail.get("company") or "",
                        detail.get("jobType") or "",
                        detail.get("yoe") or "",
                        detail.get("description") or "",
                    ]
                    full_text = "\n".join(p for p in parts if p).strip()
                    job["job_description"] = full_text or None
                    logger.info(f"  [{i}/{len(results)}] {len(full_text)} chars")
                except Exception as e:
                    logger.warning(f"  [{i}/{len(results)}] Gagal: {e}")

            return results

        finally:
            await browser.close()


async def jobscraper_techinasia(url: str, headless: bool = True, seen_ids: set = None) -> list:
    """Main orchestrator: collect cards -> filter manifest -> scrape details."""
    import asyncio
    from src.utils.manifest import filter_new_jobs

    results = await collect_job_cards(url, headless=headless)

    if seen_ids is not None:
        results = filter_new_jobs(results, seen_ids)

    if results:
        results = await scrape_job_details(results, headless=headless)

    return results


if __name__ == "__main__":
    import asyncio
    import logging
    from urllib.parse import quote
    from src.utils.manifest import read_manifest, filter_new_jobs

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    async def main():
        keyword = "data engineer"
        # TechInAsia pakai %20 untuk spasi (bukan + atau -)
        query = quote(keyword)
        url = f"https://www.techinasia.com/jobs/search?query={query}&country_name[]=Indonesia"

        seen_ids = read_manifest("techinasia")
        logger.info(f"Sudah ada {len(seen_ids)} job_id di manifest")

        all_cards = await collect_job_cards(url, headless=True)
        logger.info(f"Total card dari listing: {len(all_cards)}")

        new_cards = filter_new_jobs(all_cards, seen_ids)
        logger.info(f"Job baru (belum di manifest): {len(new_cards)}")

        if new_cards:
            results = await scrape_job_details(new_cards, headless=True)
            logger.info(f"Total: {len(results)} job baru discrape")
        else:
            logger.info("Semua job sudah ada di manifest, tidak ada yang perlu discrape")

    asyncio.run(main())
