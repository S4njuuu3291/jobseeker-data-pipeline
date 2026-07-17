# Lazy import untuk cold start cepat
import asyncio


async def jobscraper_kalibrr(url: str, headless: bool = True, seen_ids: set = None):
    # Import HANYA saat fungsi dipanggil (lazy loading)
    from playwright.async_api import Browser, BrowserContext, async_playwright
    from src.utils.scraper_utils import (
        normalize_url,
        create_browser,
        create_stealth_context,
        human_delay,
    )
    from src.utils.time_utils import now_wib
    from src.utils.keywords import ALLOWED, BLOCKED
    from tenacity import retry, stop_after_attempt, wait_exponential
    import hashlib

    async def _scrape():
        async with async_playwright() as p:
            browser: Browser = await create_browser(p, headless=headless)
            print("Berhasil create browser")
            context: BrowserContext = await create_stealth_context(browser)
            print("Berhasil create stealth_context")

            print("Creating new page...")
            page = await context.new_page()
            print("Page created successfully")
            print("Setting up selective resource blocking...")
            ad_hosts = [
                "doubleclick.net",
                "googlesyndication.com",
                "google-analytics.com",
                "googletagmanager.com",
                "adsystem.com",
                "ads.yahoo.com",
                "adservice.google.com",
            ]

            async def route_handler(route):
                url_lower = route.request.url.lower()
                if any(host in url_lower for host in ad_hosts) or any(
                    url_lower.endswith(ext)
                    for ext in [
                        ".png",
                        ".jpg",
                        ".jpeg",
                        ".gif",
                        ".webp",
                        ".svg",
                        ".ico",
                    ]
                ):
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", route_handler)
            print("Selective resource blocking enabled")

            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                reraise=True,
            )
            async def navigate_with_retry():
                print(f"Navigating to URL: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            try:
                await navigate_with_retry()
                print("Successfully loaded page")
                print("Waiting 2 seconds for hydration...")
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"Error during page.goto: {type(e).__name__}: {str(e)}")
                raise

            results = []

            max_clicks = 1
            button_selector = "button.k-btn-primary:has-text('Load more jobs')"

            for i in range(max_clicks):
                load_more_button = page.locator(button_selector)

                if await load_more_button.is_visible():
                    print(f"Klik Load More ke-{i + 1}...")
                    await load_more_button.scroll_into_view_if_needed()
                    await human_delay()

                    await load_more_button.click()

                    await human_delay(min_ms=1500, max_ms=2000)
                else:
                    print("Selesai: Tombol Load More sudah tidak ada.")
                    break
            else:
                print("Selesai: Mencapai batas maksimal klik (limit keamanan).")

            job_cards = await page.locator("div.css-1otdiuc").all()
            timestamp = now_wib().strftime("%Y%m%d_%H%M%S")

            for card in job_cards:
                try:
                    # 1. Job Title & URL (Pakai atribut itemprop="name" yang ada di tag <a>)
                    title_elem = card.locator('h2 a[itemprop="name"]').first
                    job_title = (await title_elem.text_content()).strip()

                    # Filter IT jobs
                    from src.ai.nlp import filter_job
                    if not filter_job(job_title):
                        continue

                    relative_url = await title_elem.get_attribute("href")
                    full_url = f"https://www.kalibrr.com{relative_url}"

                    # 4. Create Job ID (Hash dari URL tanpa parameter tracking)
                    job_id = hashlib.md5(normalize_url(full_url).encode()).hexdigest()
                    # Skip job yang sudah pernah discrap
                    if seen_ids is not None:
                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                    results.append(
                        {
                            "job_id": job_id,
                            "job_title": job_title,
                            "job_url": full_url,
                            "platform": "kalibrr",
                            "scraped_at": timestamp,
                        }
                    )

                except Exception as e:
                    print(f"Gagal ekstrak card: {e}")
                    continue

            print(f"📥 Terkumpul {len(results)} URL job")

            # 🔄 Loop halaman detail untuk ambil job description
            if results:
                print(f"\n📄 Scraping {len(results)} halaman detail job...")
                for i, job in enumerate(results, 1):
                    try:
                        detail_page = await context.new_page()
                        await detail_page.goto(job["job_url"], wait_until="domcontentloaded", timeout=30000)
                        
                        page_html = await detail_page.content()
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(page_html, "html.parser")
                        container = soup.select_one('div.k-bg-white.k-relative.k-p-4.md\\:k-rounded-b-lg')
                        job_desc = container.get_text(separator="\n", strip=True) if container else ""
                        print(f"  [{i}/{len(results)}] ✅ {job['job_url']}")

                        if job_desc:
                            job["job_description"] = job_desc
                        
                        await detail_page.close()
                    except Exception as e:
                        print(f"  [{i}/{len(results)}] ⚠️ Gagal: {e}")
                    
            await context.close()
            await browser.close()

            return results

    return await _scrape()  # list


if __name__ == "__main__":
    import asyncio

    async def main():
        keyword = "data-engineer-intern"
        url = f"https://kalibrr.id/id-ID/home/te/{keyword}?sort=Freshness"

        print(f"🧪 Test scraping Kalibrr with keyword: {keyword}")
        results = await jobscraper_kalibrr(url, headless=False)
        print(f"\n📊 Total results: {len(results)}")
        if results:
            print(f"📄 Sample: {results[0]}")

    asyncio.run(main())
