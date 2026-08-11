# Lazy import untuk cold start cepat
import logging

logger = logging.getLogger(__name__)


async def collect_job_cards(url: str, headless: bool = True) -> list:
    """Scrape listing page, kumpulin semua job card (title, URL, job_id).

    Args:
        url: Dealls search URL dengan keyword
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

            # Selector card Dealls: link di dalam #jobs-container
            selector = '#jobs-container a[href*="/loker/"]'
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
                    title_elem = card.locator("h2").first
                    job_title = (await title_elem.text_content()).strip()

                    # Filter IT jobs
                    if not is_relevant_title(job_title):
                        continue

                    relative_url = await card.get_attribute("href")
                    if not relative_url:
                        continue

                    full_url = f"https://dealls.com{relative_url}"
                    job_id = hashlib.md5(normalize_url(full_url).encode()).hexdigest()

                    results.append({
                        "job_id": job_id,
                        "job_title": job_title,
                        "job_url": full_url,
                        "platform": "dealls",
                        "scraped_at": timestamp,
                    })
                except Exception as e:
                    logger.warning(f"  Skip card: {e}")

            logger.info(f"Terkumpul {len(results)} URL job")
            return results

        finally:
            await browser.close()

async def scrape_job_details(results: list, headless: bool = True) -> list:
    """Scrape halaman detail untuk ambil job description + company detail.

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

            logger.info(
                f"Scraping {len(results)} halaman detail job..."
            )

            for i, job in enumerate(results, 1):
                try:
                    await detail_page.goto(
                        job["job_url"],
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )

                    # Tunggu job header muncul supaya React/Next hydration selesai.
                    try:
                        await detail_page.wait_for_selector(
                            "#job-header h1",
                            timeout=10000,
                        )
                    except Exception:
                        logger.warning(
                            f"  [{i}/{len(results)}] "
                            "Job header belum muncul setelah timeout"
                        )

                    # Ambil job detail + company detail.
                    detail = await detail_page.evaluate(
                        """() => {
                            function text(sel) {
                                const el = document.querySelector(sel);
                                return el
                                    ? el.innerText.trim()
                                    : '';
                            }

                            function sectionText(headingText) {
                                const headings =
                                    document.querySelectorAll(
                                        'h1, h2, h3'
                                    );

                                for (const h of headings) {
                                    if (
                                        h.innerText.trim() ===
                                        headingText
                                    ) {
                                        let node =
                                            h.nextElementSibling;

                                        const parts = [];

                                        while (node) {
                                            const value =
                                                node.innerText?.trim();

                                            if (value) {
                                                parts.push(value);
                                            }

                                            node =
                                                node.nextElementSibling;
                                        }

                                        return parts.join('\\n');
                                    }
                                }

                                return '';
                            }

                            function companyDetail() {
                                /*
                                 * Cari section:
                                 *
                                 * Tentang PT Lawencon Internasional
                                 * Selengkapnya
                                 * <company description>
                                 * Industri
                                 * IT Consultant
                                 * Lokasi
                                 * Jakarta Selatan, Indonesia
                                 * Ukuran Perusahaan
                                 * ...
                                 */

                                const allElements =
                                    document.querySelectorAll(
                                        'span, h1, h2, h3'
                                    );

                                let aboutElement = null;

                                for (const el of allElements) {
                                    const value =
                                        el.innerText?.trim() || '';

                                    if (
                                        value.startsWith('Tentang ')
                                    ) {
                                        aboutElement = el;
                                        break;
                                    }
                                }

                                if (!aboutElement) {
                                    return {
                                        description: '',
                                        industry: '',
                                        location: '',
                                        size: ''
                                    };
                                }

                                /*
                                 * Cari container section perusahaan.
                                 *
                                 * Jangan bergantung pada generated class
                                 * seperti:
                                 *
                                 * AboutTheCompany_...__bPVta
                                 *
                                 * karena suffix dapat berubah.
                                 */
                                let container = aboutElement;

                                while (
                                    container &&
                                    container !== document.body
                                ) {
                                    const content =
                                        container.innerText || '';

                                    if (
                                        content.includes('Industri') &&
                                        content.includes('Lokasi') &&
                                        content.includes(
                                            'Ukuran Perusahaan'
                                        )
                                    ) {
                                        break;
                                    }

                                    container =
                                        container.parentElement;
                                }

                                if (
                                    !container ||
                                    container === document.body
                                ) {
                                    return {
                                        description: '',
                                        industry: '',
                                        location: '',
                                        size: ''
                                    };
                                }

                                /*
                                 * COMPANY DESCRIPTION
                                 *
                                 * Gunakan prefix CSS module saja,
                                 * jangan suffix hash-nya.
                                 */
                                let description = '';

                                const descriptionElement =
                                    container.querySelector(
                                        '[class*="AboutTheCompany_' +
                                        'about_the_company"] p'
                                    );

                                if (descriptionElement) {
                                    description =
                                        descriptionElement
                                            .innerText
                                            .trim();
                                }

                                /*
                                 * Helper untuk mengambil value
                                 * berdasarkan label:
                                 *
                                 * Industri -> IT Consultant
                                 * Lokasi -> Jakarta Selatan, Indonesia
                                 * Ukuran Perusahaan -> – employees
                                 */
                                function valueAfterLabel(label) {
                                    const elements =
                                        container.querySelectorAll(
                                            'div'
                                        );

                                    for (const el of elements) {
                                        /*
                                         * Hanya element yang text-nya
                                         * persis sama dengan label.
                                         *
                                         * Ini menghindari parent div
                                         * yang innerText-nya berisi
                                         * label + value sekaligus.
                                         */
                                        if (
                                            el.innerText?.trim() ===
                                            label
                                        ) {
                                            const sibling =
                                                el.nextElementSibling;

                                            if (sibling) {
                                                return (
                                                    sibling
                                                        .innerText
                                                        ?.trim() ||
                                                    ''
                                                );
                                            }

                                            /*
                                             * Fallback:
                                             * parent biasanya:
                                             *
                                             * <div>
                                             *   <div>Industri</div>
                                             *   <div>
                                             *     IT Consultant
                                             *   </div>
                                             * </div>
                                             */
                                            const parent =
                                                el.parentElement;

                                            if (parent) {
                                                const children =
                                                    Array.from(
                                                        parent.children
                                                    );

                                                const index =
                                                    children.indexOf(
                                                        el
                                                    );

                                                if (
                                                    index >= 0 &&
                                                    children[
                                                        index + 1
                                                    ]
                                                ) {
                                                    return (
                                                        children[
                                                            index + 1
                                                        ].innerText
                                                            ?.trim() ||
                                                        ''
                                                    );
                                                }
                                            }
                                        }
                                    }

                                    return '';
                                }

                                return {
                                    description,
                                    industry:
                                        valueAfterLabel(
                                            'Industri'
                                        ),
                                    location:
                                        valueAfterLabel(
                                            'Lokasi'
                                        ),
                                    size:
                                        valueAfterLabel(
                                            'Ukuran Perusahaan'
                                        )
                                };
                            }

                            const companyInfo =
                                companyDetail();

                            return {
                                title:
                                    text('#job-header h1'),

                                company:
                                    text(
                                        '#job-header ' +
                                        'a[href^="/karir/"]'
                                    ),

                                location:
                                    text(
                                        '#job-header ' +
                                        'a[href*="cityIds="]'
                                    ),

                                description:
                                    sectionText(
                                        'Deskripsi Pekerjaan'
                                    ),

                                qualification:
                                    sectionText(
                                        'Kualifikasi'
                                    ),

                                company_description:
                                    companyInfo.description,

                                company_industry:
                                    companyInfo.industry,

                                company_location:
                                    companyInfo.location,

                                company_size:
                                    companyInfo.size
                            };
                        }"""
                    )

                    # Gabungkan menjadi satu blok teks.
                    #
                    # Dibuat explicit section supaya downstream AI
                    # bisa membedakan job location dengan
                    # company location.
                    parts = [
                        detail.get("title") or "",
                        detail.get("company") or "",
                        detail.get("location") or "",

                        "JOB DESCRIPTION",
                        detail.get("description") or "",

                        "QUALIFICATIONS",
                        detail.get("qualification") or "",

                        "ABOUT COMPANY",
                        detail.get("company_description") or "",

                        "INDUSTRY",
                        detail.get("company_industry") or "",

                        "COMPANY LOCATION",
                        detail.get("company_location") or "",

                        "COMPANY SIZE",
                        detail.get("company_size") or "",
                    ]

                    full_text = "\n".join(
                        part
                        for part in parts
                        if part
                    ).strip()

                    job["job_description"] = (
                        full_text or None
                    )

                    logger.info(
                        f"  [{i}/{len(results)}] "
                        f"{len(full_text)} chars "
                        f"| company_detail="
                        f"{bool(detail.get('company_description'))}"
                    )

                except Exception as e:
                    logger.warning(
                        f"  [{i}/{len(results)}] "
                        f"Gagal: {e}"
                    )

            return results

        finally:
            await browser.close()


async def jobscraper_dealls(url: str, headless: bool = True, seen_ids: set = None) -> list:
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
    from src.utils.manifest import read_manifest, filter_new_jobs

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    print("Memulai")

    async def main():
        keyword = "data+engineer"
        url = f"https://dealls.com/?sortParam=publishedAt&searchJob={keyword}"

        seen_ids = read_manifest("dealls")
        logger.info(f"Sudah ada {len(seen_ids)} job_id di manifest")

        all_cards = await collect_job_cards(url, headless=True)
        logger.info(f"Total card dari listing: {len(all_cards)}")

        new_cards = filter_new_jobs(all_cards, seen_ids)
        logger.info(f"Job baru (belum di manifest): {len(new_cards)}")

        if new_cards:
            results = await scrape_job_details(new_cards, headless=True)
            logger.info(f"Total: {len(results)} job baru discrape")
            # NOTE: testing lokal gak update manifest (avoid AWS write).
            # Update manifest dilakukan di main_dealls.py / Lambda (production).
        else:
            logger.info("Semua job sudah ada di manifest, tidak ada yang perlu discrape")

    asyncio.run(main())
