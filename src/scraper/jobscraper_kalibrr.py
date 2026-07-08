# Lazy import untuk cold start cepat
import asyncio


async def jobscraper_kalibrr(url: str, headless: bool = True):
    # Import HANYA saat fungsi dipanggil (lazy loading)
    from playwright.async_api import Browser, BrowserContext, async_playwright
    from src.utils.scraper_utils import (
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

                    job_title_lower = job_title.lower()

                    is_relevant = any(word in job_title_lower for word in ALLOWED)
                    is_trash = any(word in job_title_lower for word in BLOCKED)

                    if not is_relevant or is_trash:
                        continue

                    relative_url = await title_elem.get_attribute("href")
                    full_url = f"https://www.kalibrr.com{relative_url}"

                    # 2. Company Name (Pakai selector class yang lebih simpel)
                    company_name = (
                        await card.locator(
                            "a.k-text-subdued.k-font-bold"
                        ).first.text_content()
                    ).strip()

                    # 3. Location (Mencari icon map atau class lokasi)
                    location = (
                        await card.locator("span.k-text-gray-500").first.text_content()
                    ).strip()

                    # 4. Create Job ID (Sesuai diskusi kita: Hash dari URL)
                    job_id = hashlib.md5(full_url.encode()).hexdigest()

                    results.append(
                        {
                            "job_id": job_id,
                            "job_title": job_title,
                            "company_name": company_name,
                            "location": location,
                            "job_url": full_url,
                            "platform": "kalibrr",
                            "scraped_at": timestamp,
                        }
                    )

                except Exception as e:
                    print(f"Gagal ekstrak card: {e}")
                    continue

            await context.close()
            await browser.close()

            return results

    return await _scrape()  # list


if __name__ == "__main__":
    URL = "https://kalibrr.id/id-ID/home/w/100-internship-_-ojt/te/data-engineer-intern"

    asyncio.run(jobscraper_kalibrr(URL))
