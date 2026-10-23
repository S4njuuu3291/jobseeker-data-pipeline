"""HTTP, Bronze record mapping, and local preview helpers for API adapters."""

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from src.utils.time_utils import now_wib

logger = logging.getLogger(__name__)
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/152.0.0.0 Safari/537.36",
}


def client(headers=None):
    return httpx.AsyncClient(
        headers={**HEADERS, **(headers or {})}, timeout=25, follow_redirects=True
    )


async def request_json(session, method, url, **kwargs):
    """Retry transient failures; never log request URLs, cookies, or API keys."""
    for attempt in range(3):
        try:
            response = await session.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt == 2:
                raise RuntimeError("API connection failed after 3 attempts") from None
        else:
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                if response.is_error:
                    raise RuntimeError(f"API returned HTTP {response.status_code}")
                try:
                    body = response.json()
                except ValueError:
                    raise RuntimeError("API returned non-JSON content") from None
                if not isinstance(body, dict):
                    raise RuntimeError("API returned an unexpected JSON structure")
                if body.get("errors"):
                    raise RuntimeError(
                        "GraphQL returned errors; check query and session"
                    )
                return body
        logger.warning("API request failed temporarily; retry %s/3", attempt + 2)
        await asyncio.sleep(2**attempt)


def list_field(body, key):
    """A missing list is a contract error, not a successful empty search."""
    value = body.get(key)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise RuntimeError(f"API response is missing the list field {key}")
    return value


def search_keyword(url, platform):
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    key = {
        "glints": "keyword",
        "dealls": "searchJob",
        "techinasia": "query",
        "jobstreet": "keywords",
        "kalibrr": "text",
    }[platform]
    keyword = (params.get(key) or [""])[0]
    if not keyword and platform == "dealls":
        keyword = (params.get("search") or [""])[0]
    if not keyword and platform == "jobstreet":
        match = re.search(r"/([^/]+)-jobs/?$", parsed.path)
        keyword = unquote(match.group(1)).replace("-", " ") if match else ""
    if not keyword and platform == "kalibrr":
        match = re.search(r"/home/te/([^/]+)", parsed.path)
        keyword = unquote(match.group(1)).replace("-", " ") if match else ""
    if not keyword.strip():
        raise ValueError(f"Cannot find a search keyword in the {platform} URL")
    return keyword.strip()


def slugify(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        if not value:
            return ""
        return json.dumps(value, ensure_ascii=False)
    soup = BeautifulSoup(str(value), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def summary(*sections):
    """Keep listing information in the existing free-text Bronze field."""
    parts = []
    for label, value in sections:
        content = text(value)
        if content:
            parts.append(f"{label}\n{content}" if label else content)
    return "\n".join(parts) or None


def record(platform, title, company, url, description, timestamp):
    from src.utils.manifest import is_relevant_title

    title = (title or "").strip()
    if not is_relevant_title(title):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.path:
        raise ValueError("Invalid job URL from API listing")
    # Exactly the same normalization/hash algorithm as scraper_utils.normalize_url.
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    return {
        "job_id": hashlib.md5(normalized.encode()).hexdigest(),
        "job_title": title,
        "company_name": (company or "").strip() or "Unknown",
        "job_url": url,
        "platform": platform,
        "scraped_at": timestamp,
        "job_description": description,
    }


def timestamp():
    return now_wib().strftime("%Y%m%d_%H%M%S")


def add_record(results, seen, candidate):
    if candidate and candidate["job_id"] not in seen:
        results.append(candidate)
        seen.add(candidate["job_id"])


def positive_pages(max_pages):
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")


def new_records(records, seen_ids):
    from src.utils.manifest import filter_new_jobs

    return filter_new_jobs(records, seen_ids if seen_ids is not None else set())


async def listing_details(results, platform):
    """API listing already contains the available text; no HTML/detail fallback."""
    for i, job in enumerate(results, 1):
        job.setdefault("job_description", None)
        logger.info(
            "[%s/%s] %s: %s chars",
            i,
            len(results),
            platform,
            len(job.get("job_description") or ""),
        )
    return results


def preview_cli(platform, runner):
    """Run one adapter locally and emit records, without reading/writing S3."""
    import argparse
    from dotenv import load_dotenv
    from src.main.main import build_search_url

    load_dotenv()
    parser = argparse.ArgumentParser(
        description=f"Preview {platform} API Bronze records locally"
    )
    parser.add_argument("--keyword", default="data engineer")
    parser.add_argument("--url", help="Override the website search URL")
    parser.add_argument(
        "--max-pages", type=int, default=3 if platform == "kalibrr" else 1
    )
    parser.add_argument(
        "--output", type=Path, help="Save JSON instead of printing to stdout"
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    separator = "+" if platform in {"glints", "dealls"} else "-"
    keyword = (
        args.keyword
        if platform == "techinasia"
        else args.keyword.replace(" ", separator)
    )
    url = args.url or build_search_url(platform, keyword)
    records = asyncio.run(runner(url, seen_ids=set(), max_pages=args.max_pages))
    for job in records:
        job["keyword"] = search_keyword(url, platform) if args.url else keyword
    output = json.dumps(records, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
        logger.info("Saved %s records to %s", len(records), args.output)
    else:
        print(output)
