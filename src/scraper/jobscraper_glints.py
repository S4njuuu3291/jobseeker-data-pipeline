# Lazy import untuk cold start cepat
import logging

logger = logging.getLogger(__name__)


async def collect_job_cards(url: str, headless: bool = True) -> list:
    """Scrape listing page, kumpulin semua job card (title, URL, job_id).

    Args:
        url: Glints explore URL dengan keyword
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

            nav_state = {"browser": browser, "context": context, "page": page, "attempt": 0}

            async def navigate_safe():
                nav_state["attempt"] += 1
                attempt = nav_state["attempt"]
                try:
                    logger.info(f"  Navigate attempt {attempt}: {url}")
                    await nav_state["page"].goto(url, wait_until="domcontentloaded", timeout=30000)
                    if "not-found" in nav_state["page"].url:
                        raise Exception("Page not found")
                    return True
                except Exception as e:
                    logger.warning(f"  Navigate attempt {attempt} failed: {e}")
                    if attempt >= 3:
                        raise
                    await asyncio.sleep(2)
                    # Recreate context & page jika closed
                    try:
                        await nav_state["page"].close()
                    except:
                        pass
                    try:
                        await nav_state["context"].close()
                    except:
                        pass
                    nav_state["context"] = await create_stealth_context(nav_state["browser"])
                    nav_state["page"] = await nav_state["context"].new_page()
                    await nav_state["page"].route("**/*", route_handler)
                    return await navigate_safe()

            await navigate_safe()
            page = nav_state["page"]

            logger.info("Waiting 5 seconds for hydration...")
            await page.wait_for_timeout(5000)

            logger.info("Waiting for job cards...")
            for _ in range(3):
                await fast_human_scroll(page)
                await asyncio.sleep(1)

            selector = '[data-glints-tracking-element-name="job_card"]'
            await page.wait_for_selector(selector, timeout=20000)

            job_cards = await page.locator(selector).all()
            logger.info(f"Found {len(job_cards)} potential cards")

            results = []
            for card in job_cards:
                try:
                    title_elem = card.locator('h2[class*="JobTitle"] a').first
                    job_title = (await title_elem.text_content()).strip()

                    from src.utils.manifest import is_relevant_title
                    if not is_relevant_title(job_title):
                        continue

                    link_elem = card.locator('a[href*="/opportunities/jobs/"]').first
                    relative_url = await link_elem.get_attribute("href")
                    if not relative_url:
                        continue

                    full_url = f"https://glints.com{relative_url}"
                    job_id = hashlib.md5(normalize_url(full_url).encode()).hexdigest()

                    results.append({
                        "job_id": job_id,
                        "job_title": job_title,
                        "job_url": full_url,
                        "platform": "glints",
                        "scraped_at": timestamp,
                    })
                except Exception as e:
                    logger.warning(f"  \u26a0\ufe0f Skip card: {e}")

            logger.info(f"\U0001f4e5 Terkumpul {len(results)} URL job")
            return results

        finally:
            await browser.close()

async def scrape_job_details(results: list, headless: bool = True) -> list:
    from playwright.async_api import Browser, async_playwright
    from src.utils.scraper_utils import create_browser, create_stealth_context

    """Scrape halaman detail Glints untuk mengambil informasi lengkap pekerjaan,

    persyaratan, hingga profil perusahaan.
    """
    if not results:
        return results

    async with async_playwright() as p:
        browser: Browser = await create_browser(p, headless=headless)
        try:
            context = await create_stealth_context(browser)
            detail_page = await context.new_page()

            logger.info(f"\n📄 Scraping {len(results)} halaman detail job...")
            for i, job in enumerate(results, 1):
                try:
                    await detail_page.goto(
                        job["job_url"],
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )

                    # Ambil satu blok teks mentah murni tanpa parsing
                    raw_text = await detail_page.evaluate("""() => {
                        const container = document.querySelector('main') || document.body;
                        return container ? container.innerText.trim() : '';
                    }""")

                    job["job_description"] = raw_text

                    logger.info(
                        f"  [{i}/{len(results)}] ✅ Got raw text ({len(raw_text)} chars)"
                    )
                except Exception as e:
                    logger.warning(
                        f"  [{i}/{len(results)}] ⚠️ Gagal: {e}"
                    )

            return results

        finally:
            await browser.close()

async def jobscraper_glints(url: str, headless: bool = True, seen_ids: set = None) -> list:
    """Main orchestrator: collect cards -> filter manifest -> scrape details."""
    import asyncio
    from src.utils.manifest import filter_new_jobs

    try:
        results = await collect_job_cards(url, headless=headless)
    except Exception as e:
        logger.error(f"collect_job_cards gagal: {e}")
        return []

    # Filter: buang job yang sudah ada di manifest
    if seen_ids is not None:
        results = filter_new_jobs(results, seen_ids)

    if results:
        results = await scrape_job_details(results, headless=headless)
        # Pastikan job_description ada
        for j in results:
            j.setdefault("job_description", "")
    return results


if __name__ == "__main__":
    import asyncio
    from src.utils.manifest import read_manifest, update_manifest, filter_new_jobs

    async def main():
        keyword = "data+engineer+intern"
        url = f"https://glints.com/id/opportunities/jobs/explore?keyword={keyword}&country=ID&locationName=All+Cities%2FProvinces&lowestLocationLevel=1&sortBy=LATEST"

        # 1. Baca manifest
        seen_ids = read_manifest("glints")
        logger.info(f"\U0001f4cb Sudah ada {len(seen_ids)} job_id di manifest")

        # 2. Kumpulin semua card
        all_cards = await collect_job_cards(url, headless=True)
        logger.info(f"\U0001f4e5 Total card dari listing: {len(all_cards)}")

        # 3. Filter: buang yang sudah ada di manifest
        new_cards = filter_new_jobs(all_cards, seen_ids)
        logger.info(f"\U0001f195 Job baru (belum di manifest): {len(new_cards)}")

        if new_cards:
            results = await scrape_job_details(new_cards, headless=True)
            new_ids = {c["job_id"] for c in new_cards}
            seen_ids.update(new_ids)
            update_manifest("glints", seen_ids)
            logger.info(f"\n Total: {len(results)} job baru discrape & disimpan")
        else:
            logger.info(" Semua job sudah ada di manifest, tidak ada yang perlu discrape")

    asyncio.run(main())
