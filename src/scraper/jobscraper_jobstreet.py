# Lazy import untuk cold start cepat
async def jobscraper_jobstreet(url: str, headless: bool = True, seen_ids: set = None):
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
    from tenacity import retry, stop_after_attempt, wait_exponential
    import hashlib
    import asyncio

    async def _scrape():
        async with async_playwright() as p:
            browser: Browser = await create_browser(p, headless=headless)
            print("Berhasil create browser")
            context: BrowserContext = await create_stealth_context(browser)
            print("Berhasil create stealth_context")

            print("Creating new page...")
            page = await context.new_page()
            print("Page created successfully")
            # Resource blocking DISABLED - JobStreet detects when resources are blocked
            # Allow all resources to load normally for stealth

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
                print("Successfully loaded page (domcontentloaded)")
                print("Waiting 5 seconds for hydration...")
                await page.wait_for_timeout(5000)
            except Exception as e:
                print(f"Error during page.goto: {type(e).__name__}: {str(e)}")
                raise

            # Penanganan modal login yang sering muncul di JobStreet
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

            # Strategi Scroll: Lakukan scroll perlahan 3 kali saja
            # Ini memicu lazy loading tanpa mencekik RAM 8GB
            for i in range(3):
                await fast_human_scroll(page)
                await asyncio.sleep(1)

            results = []

            # Mengincar atribut data-automation yang sangat stabil di JobStreet
            job_cards = await page.locator('article[data-automation="normalJob"]').all()
            timestamp = now_wib().strftime("%Y%m%d_%H%M%S")

            for card in job_cards:
                try:
                    # 1. Job Title
                    title_elem = card.locator('[data-automation="jobTitle"]').first
                    job_title = (await title_elem.text_content()).strip()
                    
                    # Filter IT jobs
                    from src.ai.nlp import filter_job
                    if not filter_job(job_title):
                        continue

                    # 2. URL (Path relatif, perlu prefix)
                    relative_url = await title_elem.get_attribute("href")
                    full_url = f"https://id.jobstreet.com{relative_url}"

                    # 5. Job ID (Hash dari URL tanpa parameter tracking)
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
                            "platform": "jobstreet",
                            "scraped_at": timestamp,
                        }
                    )
                except Exception:
                    continue
            
                        # 🔄 Loop halaman detail untuk ambil job description
            if results:
                print(f"\n📄 Scraping {len(results)} halaman detail job...")
                for i, job in enumerate(results, 1):
                    try:
                        detail_page = await context.new_page()
                        await detail_page.goto(job["job_url"], wait_until="domcontentloaded", timeout=30000)
                        
                        # 1. Ambil job description (selector stabil)
                        desc_selector = '[data-automation="jobAdDetails"]'
                        job_desc = await detail_page.text_content(desc_selector)
                        
                        # 2. Ambil metadata
                        title = await detail_page.text_content('[data-automation="job-detail-title"]')
                        company = await detail_page.text_content('[data-automation="advertiser-name"]')
                        location = await detail_page.text_content('[data-automation="job-detail-location"]')
                        salary = await detail_page.text_content('[data-automation="job-detail-salary"]')
                        work_type = await detail_page.text_content('[data-automation="job-detail-work-type"]')
                        
                        # 3. Gabungkan semua
                        if job_desc:
                            full_text = f"{title or ''}\n{company or ''}\n{location or ''}\n{salary or ''}\n{work_type or ''}\n\n{job_desc}"
                            job["job_description"] = full_text.strip()
                            print(f"  [{i}/{len(results)}] ✅ {job['job_url']}")

                        else:
                            print(f"  [{i}/{len(results)}] ⚠️ Kosong - {job['job_title'][:30]}...")
                        
                        await detail_page.close()
                        
                    except Exception as e:
                        print(f"  [{i}/{len(results)}] ❌ Gagal: {e}")
                    
            await context.close()
            await browser.close()

            return results

    return await _scrape()


if __name__ == "__main__":
    import asyncio

    async def main():
        keyword = "data-engineer-intern"
        url = f"https://id.jobstreet.com/id/{keyword}-jobs?daterange=7"

        print(f"🧪 Test scraping JobStreet with keyword: {keyword}")
        results = await jobscraper_jobstreet(url, headless=True)
        print(f"\n📊 Total results: {len(results)}")
        if results:
            print(f"📄 Sample: {results[0]}")

    asyncio.run(main())
