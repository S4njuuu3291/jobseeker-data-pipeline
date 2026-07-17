# Lazy import untuk cold start cepat
async def jobscraper_glints(url: str, headless: bool = True, seen_ids: set = None):
    # Import HANYA saat fungsi dipanggil (lazy loading)
    from playwright.async_api import Browser, BrowserContext, async_playwright
    from src.utils.scraper_utils import (
        normalize_url,
        create_browser,
        create_stealth_context,
        fast_human_scroll,
    )
    from src.utils.keywords import ALLOWED, BLOCKED
    from src.utils.time_utils import now_wib
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
    )
    import hashlib
    import json
    import os

    async def _scrape():
        async with async_playwright() as p:
            browser: Browser = await create_browser(p, headless=headless)
            print("Berhasil create browser")
            context: BrowserContext = await create_stealth_context(browser)
            print("Berhasil create stealth_context")

            print("Creating new page...")
            page = await context.new_page()

            # Resource blocking selektif: hanya gambar dan iklan
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

            timestamp = now_wib().strftime("%Y%m%d_%H%M%S")
            filename = f"glints_raw_{timestamp}.json"
            results = []

            # Fungsi Navigasi dengan Retry khusus
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
                print("Waiting 5 seconds for hydration...")
                await page.wait_for_timeout(5000)

                # Tunggu selector kartu muncul (PENTING agar tidak TargetClosed)
                print("Waiting for job cards...")
                selector = '[data-glints-tracking-element-name="job_card"]'
                await page.wait_for_selector(selector, timeout=20000)

                await fast_human_scroll(page)

                job_cards = await page.locator(selector).all()
                print(f"Found {len(job_cards)} potential cards")

                for card in job_cards:
                    try:
                        title_elem = card.locator('h2[class*="JobTitle"] a').first
                        job_title = (await title_elem.text_content()).strip()
                        
                        # Filter IT jobs pake AI + regex
                        from src.ai.nlp import filter_job
                        if not filter_job(job_title):
                            continue
                        
                        # URL - ambil dari link di card
                        link_elem = card.locator('a[href*="/opportunities/jobs/"]').first
                        relative_url = await link_elem.get_attribute("href")
                        if not relative_url:
                            continue
                        full_url = f"https://glints.com{relative_url}"
                        job_id = hashlib.md5(normalize_url(full_url).encode()).hexdigest()
                        
                        # Skip job yang sudah pernah discrap (dedup antar keyword)
                        if seen_ids is not None:
                            if job_id in seen_ids:
                                print(f"  ⏭️ Skip existing job: {job_title[:30]}...")
                                continue
                            seen_ids.add(job_id)
                        
                        results.append(
                            {
                                "job_id": job_id,
                                "job_title": job_title,
                                "job_url": full_url,
                                "platform": "glints",
                                "scraped_at": timestamp,
                            }
                        )
                        
                    except Exception as e:
                        print(f"  ⚠️ Skip card: {e}")
                        continue

                print(f"📥 Terkumpul {len(results)} URL job")

                # 🔄 Loop halaman detail untuk ambil job description
                if results:
                    print(f"\n📄 Scraping {len(results)} halaman detail job...")
                    for i, job in enumerate(results, 1):
                        try:
                            detail_page = await context.new_page()
                            await detail_page.goto(job["job_url"], wait_until="domcontentloaded", timeout=30000)
                            
                            # Ambil semua teks dari container utama job description
                            desc_selector = ".Opportunitysc__Main-sc-gb4ubh-2"
                            job_desc = await detail_page.text_content(desc_selector)
                            print(f"  [{i}/{len(results)}] ✅ {len(job_desc or chr(48))} chars")
                            if job_desc:
                                job["job_description"] = job_desc.strip()
                            print(f"  [{i}/{len(results)}] ✅ {job['job_url']}")

                            await detail_page.close()
                        except Exception as e:
                            print(f"  [{i}/{len(results)}] ⚠️ Gagal: {e}")
                        
            except Exception as e:
                print(f"❌ Error during scraping: {type(e).__name__}: {str(e)}")
            finally:
                await context.close()
                await browser.close()

            return results

    return await _scrape()


if __name__ == "__main__":
    import asyncio

    async def main():
        keyword = "data+engineer+intern"
        url = f"https://glints.com/id/opportunities/jobs/explore?keyword={keyword}&country=ID&locationName=All+Cities%2FProvinces&lowestLocationLevel=1&sortBy=LATEST"

        print(f"🧪 Test scraping Glints with keyword: {keyword}")
        results = await jobscraper_glints(url, headless=True)
        print(f"\n📊 Total results: {len(results)}")
        if results:
            print(f"📄 Sample: {results[0]}")

    asyncio.run(main())
