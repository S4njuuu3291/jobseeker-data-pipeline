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

            # Penanganan modal login
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

            # Scroll perlahan
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
                    full_url = f"https://id.jobstreet.com{relative_url}"
                    job_id = hashlib.md5(normalize_url(full_url).encode()).hexdigest()
                    
                    if seen_ids is not None:
                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                    results.append({
                        "job_id": job_id,
                        "job_title": job_title,
                        "job_url": full_url,
                        "platform": "jobstreet",
                        "scraped_at": timestamp,
                    })
                except Exception:
                    continue
            
            # 🔥 Detail scraping dengan safe_text
            if results:
                print(f"\n📄 Scraping {len(results)} halaman detail job...")
                
                async def safe_text(detail_page, selector, timeout=3000):
                    try:
                        element = await detail_page.wait_for_selector(selector, timeout=timeout)
                        return (await element.text_content()).strip() if element else ""
                    except:
                        return ""
                
                for i, job in enumerate(results, 1):
                    try:
                        detail_page = await context.new_page()
                        await detail_page.goto(job["job_url"], wait_until="domcontentloaded", timeout=30000)
                        
                        # Ambil semua data dengan timeout pendek
                        desc = await safe_text(detail_page, '[data-automation="jobAdDetails"]', 5000)
                        title = await safe_text(detail_page, '[data-automation="job-detail-title"]', 2000)
                        company = await safe_text(detail_page, '[data-automation="advertiser-name"]', 2000)
                        location = await safe_text(detail_page, '[data-automation="job-detail-location"]', 2000)
                        salary = await safe_text(detail_page, '[data-automation="job-detail-salary"]', 2000)
                        work_type = await safe_text(detail_page, '[data-automation="job-detail-work-type"]', 2000)
                        
                        full_text = f"{title or ''}\n{company or ''}\n{location or ''}\n{salary or ''}\n{work_type or ''}\n\n{desc or ''}"
                        job["job_description"] = full_text.strip() if full_text.strip() else None
                        
                        if job.get("job_description"):
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
