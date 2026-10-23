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

from src.scraper.bronze_schema import BRONZE_COLUMNS, INTEGER_COLUMNS
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


async def request(session, method, url, **kwargs):
    """Retry transient failures without exposing credentials or response bodies."""
    for attempt in range(3):
        try:
            response = await session.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt == 2:
                raise RuntimeError("HTTP connection failed after 3 attempts") from None
        else:
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                if response.is_error:
                    raise RuntimeError(f"API returned HTTP {response.status_code}")
                return response
        logger.warning("API request failed temporarily; retry %s/3", attempt + 2)
        await asyncio.sleep(2**attempt)


async def request_json(session, method, url, **kwargs):
    response = await request(session, method, url, **kwargs)
    try:
        body = response.json()
    except ValueError:
        raise RuntimeError("API returned non-JSON content") from None
    if not isinstance(body, dict):
        raise RuntimeError("API returned an unexpected JSON structure")
    if body.get("errors"):
        raise RuntimeError("GraphQL returned errors; check query and session")
    return body


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
    if "<" not in str(value) and "&" not in str(value):
        return str(value).strip()
    soup = BeautifulSoup(str(value), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def summary(*sections):
    """Join cleaned source text and company context for subsequent AI enrichment."""
    parts = []
    for label, value in sections:
        content = text(value)
        if content:
            parts.append(f"{label}\n{content}" if label else content)
    return "\n".join(parts) or None


def clean(value):
    return text(value).strip() or None


def integer(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return int(number) if number >= 0 and number.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def array_string(values):
    values = list(dict.fromkeys(filter(None, (clean(v) for v in values or []))))
    return json.dumps(values, ensure_ascii=False) if values else None


def joined(values, separator=", "):
    values = list(dict.fromkeys(filter(None, (clean(v) for v in values))))
    return separator.join(values) or None


def normalize(value, mapping):
    value = clean(value)
    return (
        mapping.get(re.sub(r"[^a-z0-9]", "", value.lower()), value) if value else None
    )


def record(
    platform, title, company, url, description, timestamp, *, native_id, **fields
):
    from src.utils.manifest import is_relevant_title

    title = clean(title)
    if not is_relevant_title(title):
        return None
    if native_id is None or not str(native_id).strip():
        raise ValueError("Missing native job ID")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.path:
        raise ValueError("Invalid job URL from API listing")
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    result = dict.fromkeys(BRONZE_COLUMNS)
    result.update(
        job_id=str(native_id),
        job_title=title,
        company_name=clean(company),
        job_url=normalized,
        platform=platform,
        scraped_at=timestamp,
        keyword="",
        job_description=description,
    )
    if set(fields) - set(BRONZE_COLUMNS):
        raise ValueError("Unexpected Bronze columns")
    result.update(fields)
    for key in INTEGER_COLUMNS:
        result[key] = integer(result[key])
    result["job_type"] = normalize(
        result["job_type"],
        {
            "fulltime": "Full-time",
            "parttime": "Part-time",
            "contract": "Contract",
            "contractual": "Contract",
            "intern": "Internship",
            "internship": "Internship",
            "permanent": "Full-time",
            "freelance": "Freelance",
        },
    )
    result["work_mode"] = normalize(
        result["work_mode"],
        {
            "onsite": "On-site",
            "office": "On-site",
            "hybrid": "Hybrid",
            "remote": "Remote",
            "workfromhome": "Remote",
        },
    )
    for key, value in result.items():
        if key not in INTEGER_COLUMNS and value is not None:
            result[key] = (
                str(value).strip() if key in {"skills", "benefits"} else clean(value)
            )
    return result


def legacy_id(url):
    p = urlparse(url)
    normalized = urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    return hashlib.md5(normalized.encode()).hexdigest()


def text_attributes(description):
    """Extract only explicit education and year boundaries, without guessing levels."""
    value = clean(description) or ""
    attrs = {}
    education_patterns = [
        (r"(?:bachelor|sarjana|\bS1\b)", "Bachelor"),
        (r"(?:diploma|\bD3\b)", "Diploma"),
        (r"(?:master|magister|\bS2\b)", "Master"),
        (r"(?:high school|\bSMA\b|\bSMK\b)", "High School"),
    ]
    education_matches = [
        (match.start(), label)
        for pattern, label in education_patterns
        if (match := re.search(pattern, value, re.I))
    ]
    if education_matches:
        attrs["education"] = min(education_matches)[1]
    match = re.search(
        r"(\d+)\s*[-–]\s*(\d+)\s*(?:years?|tahun)(?:\s+of)?\s*(?:working\s+|work\s+)?(?:experience|pengalaman)",
        value,
        re.I,
    )
    if match:
        attrs.update(experience_min=int(match[1]), experience_max=int(match[2]))
    else:
        match = re.search(
            r"(?:min(?:imum|imal)?\.?|at least)\s*(\d+)\s*(?:years?|tahun)(?:\s+of)?\s*(?:working\s+|work\s+)?(?:experience|pengalaman)",
            value,
            re.I,
        )
        if not match:
            match = re.search(
                r"pengalaman\s+(?:kerja\s+)?(?:min(?:imum|imal)?\.?|setidaknya)\s*(\d+)\s*tahun",
                value,
                re.I,
            )
        if match:
            attrs["experience_min"] = int(match[1])
    return attrs


def salary_label(value):
    """Parse explicit labelled ranges; return nulls for ambiguous labels."""
    value = clean(value) or ""
    attrs = {}
    if re.search(r"\b(?:Rp|IDR)\b", value, re.I):
        attrs["salary_currency"] = "IDR"
        match = re.search(r"([\d.]+)\s*[-–]\s*(?:Rp\s*)?([\d.]+)", value)
        if match:
            attrs.update(
                salary_min=int(match[1].replace(".", "")),
                salary_max=int(match[2].replace(".", "")),
            )
    for pattern, period in [
        (r"per month|/month|bulanan|per bulan", "Monthly"),
        (r"per year|/year|tahunan|per tahun", "Yearly"),
        (r"per hour|/hour|per jam", "Hourly"),
    ]:
        if re.search(pattern, value, re.I):
            attrs["salary_period"] = period
            break
    return attrs


def with_keyword(records, keyword):
    for row in records:
        row["keyword"] = keyword
    return records


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
    """Read native IDs and exact URL hashes retained by the legacy manifest."""
    seen = set(seen_ids or ())
    results = []
    for row in records:
        if row["job_id"] in seen or legacy_id(row["job_url"]) in seen:
            continue
        seen.add(row["job_id"])
        results.append(row)
    logger.info(
        "%s: %s listing setelah filter judul, %s job baru, %s dilewati manifest/duplikat",
        records[0]["platform"] if records else "API",
        len(records),
        len(results),
        len(records) - len(results),
    )
    return results


async def listing_details(results, platform):
    """Log records whose listing already supplies the available detail text."""
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
