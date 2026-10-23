"""HTTP-only detail enrichment, after manifest filtering."""

import json
import logging
from urllib.parse import quote, unquote, urlparse
from uuid import uuid4

from bs4 import BeautifulSoup

from src.scraper import _api_common as api
from src.scraper import _api_mapping as mapping

logger = logging.getLogger(__name__)
DEALLS_DETAIL = "https://api.sejutacita.id/v1/job-portal/job/public/slug/{}"
JOBSTREET_DETAIL = "https://id.jobstreet.com/graphql"
JOBSTREET_QUERY = """
query jobDetails($jobId: ID!, $correlationId: String!, $sessionId: String!,
 $zone: Zone!, $locale: Locale!, $language: LanguageCodeIso!, $visitorId: UUID!) {
 jobDetails(id: $jobId, tracking: {channel: "WEB", jobDetailsViewedCorrelationId: $correlationId, sessionId: $sessionId}) {
  job {
   id title abstract content(platform: WEB) content2(zone: $zone)
   listedAt { dateTimeUtc }
   salary { currencyLabel(zone: $zone) label }
   shareLink(platform: WEB, zone: $zone, locale: $locale)
   workTypes { label(locale: $locale) }
   advertiser { id name(locale: $locale) }
   location { label(locale: $locale, type: LONG) }
   classifications { label(languageCode: $language) }
   products { bullets questionnaire { questions } }
  }
  companyProfile(zone: $zone) {
   id name overview { industry description { paragraphs } }
   perksAndBenefits { title }
  }
  workArrangements(visitorId: $visitorId, channel: "JDV", platform: WEB) {
   arrangements { type label(locale: $locale) }
  }
  seoInfo { normalisedRoleTitle }
 }
}
"""


def merge(row, details):
    if not details or details["job_id"] != row["job_id"]:
        raise ValueError("Detail ID does not match listing ID")
    result = {
        k: details.get(k) if details.get(k) is not None else v for k, v in row.items()
    }
    result["keyword"] = row["keyword"]
    return result


async def dealls(session, row):
    slug = unquote(urlparse(row["job_url"]).path.rsplit("/", 1)[-1].split("~")[0])
    body = await api.request_json(
        session, "GET", DEALLS_DETAIL.format(quote(slug, safe="-"))
    )
    job = (body.get("data") or {}).get("result")
    if body.get("code") != 200 or not isinstance(job, dict):
        raise RuntimeError("Dealls detail contract is missing data.result")
    return merge(row, mapping.dealls(job, row["scraped_at"]))


async def glints(session, row):
    response = await api.request(
        session, "GET", row["job_url"], headers={"Accept": "text/html"}
    )
    soup = BeautifulSoup(response.text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        raise RuntimeError("Glints detail is missing embedded job data")
    data = json.loads(script.string or script.get_text())
    job = data["props"]["pageProps"]["initialData"]["data"]
    if str(job.get("id")) != row["job_id"]:
        raise ValueError("Glints detail ID mismatch")
    structured = {}
    for block in soup.select('script[type="application/ld+json"]'):
        payload = json.loads(block.string or block.get_text())
        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if candidate.get("@type") == "JobPosting":
                structured = candidate
                break
    details = mapping.glints(job, row["scraped_at"], row["job_url"], structured)
    # The detail may intentionally omit salary fields for a hidden salary.
    result = merge(row, details)
    if not job.get("shouldShowSalary"):
        for key in ("salary_min", "salary_max", "salary_currency", "salary_period"):
            result[key] = None
    return result


async def jobstreet(session, row):
    variables = {
        "jobId": row["job_id"],
        "correlationId": str(uuid4()),
        "sessionId": str(uuid4()),
        "zone": "asia-4",
        "locale": "id-ID",
        "language": "id",
        "visitorId": str(uuid4()),
    }
    body = await api.request_json(
        session,
        "POST",
        JOBSTREET_DETAIL,
        json={
            "operationName": "jobDetails",
            "query": JOBSTREET_QUERY,
            "variables": variables,
        },
        headers={
            "Origin": "https://id.jobstreet.com",
            "Accept": "application/graphql-response+json,application/json;q=0.9",
        },
    )
    detail = (body.get("data") or {}).get("jobDetails")
    if not isinstance(detail, dict) or not isinstance(detail.get("job"), dict):
        raise RuntimeError("Jobstreet detail contract is missing jobDetails.job")
    job = detail["job"]
    company = detail.get("companyProfile") or {}
    overview = company.get("overview") or {}
    description = job.get("content2") or job.get("content")
    attrs = api.text_attributes(description)
    attrs.update(api.salary_label((job.get("salary") or {}).get("label")))
    fields = {
        "role": (detail.get("seoInfo") or {}).get("normalisedRoleTitle"),
        "location": (job.get("location") or {}).get("label"),
        "job_type": (job.get("workTypes") or {}).get("label"),
        "work_mode": api.joined(
            a.get("type")
            for a in (detail.get("workArrangements") or {}).get("arrangements") or []
        ),
        "company_industry": overview.get("industry"),
        "benefits": api.array_string(
            p.get("title") for p in company.get("perksAndBenefits") or []
        ),
        "posting_date": (job.get("listedAt") or {}).get("dateTimeUtc"),
        **attrs,
    }
    mapped = api.record(
        "jobstreet",
        job.get("title"),
        (job.get("advertiser") or {}).get("name") or company.get("name"),
        job.get("shareLink") or row["job_url"],
        api.summary(
            ("JOB DESCRIPTION", description),
            ("HIGHLIGHTS", (job.get("products") or {}).get("bullets")),
            (
                "ABOUT COMPANY",
                "\n".join((overview.get("description") or {}).get("paragraphs") or []),
            ),
        ),
        row["scraped_at"],
        native_id=job.get("id"),
        **fields,
    )
    return merge(row, mapped)


async def enrich(results, platform):
    """Failed required details remain out of Bronze/manifest so the next run retries."""
    if not results:
        return []
    handler = {"dealls": dealls, "glints": glints, "jobstreet": jobstreet}[platform]
    completed = []
    async with api.client() as session:
        for index, row in enumerate(results, 1):
            try:
                enriched = await handler(session, row)
                completed.append(enriched)
                logger.info(
                    "[%s/%s] %s detail: %s chars",
                    index,
                    len(results),
                    platform,
                    len(enriched.get("job_description") or ""),
                )
            except (RuntimeError, ValueError, KeyError, TypeError, AttributeError):
                logger.warning(
                    "[%s/%s] %s detail failed; excluded from upload and manifest",
                    index,
                    len(results),
                    platform,
                )
    return completed


async def techinasia_details(results):
    """Keep complete Algolia descriptions; optionally resolve canonical URL/company text."""
    company_cache = {}
    async with api.client() as session:
        for row in results:
            slug = row.pop("_company_slug", None)
            if urlparse(row["job_url"]).hostname == "www.techinasia.com":
                try:
                    response = await api.request(
                        session, "GET", row["job_url"], headers={"Accept": "text/html"}
                    )
                    soup = BeautifulSoup(response.text, "html.parser")
                    link = soup.find("link", rel="canonical")
                    canonical = link.get("href") if link else None
                    parsed = urlparse(canonical or "")
                    if (
                        parsed.scheme == "https"
                        and parsed.hostname in {"www.techinasia.com", "techinasia.com"}
                        and parsed.path.startswith("/jobs/")
                        and parsed.path != "/jobs/search"
                    ):
                        row["job_url"] = canonical.split("?")[0].split("#")[0]
                    else:
                        logger.warning(
                            "Tech in Asia canonical URL unavailable; keeping source/ID URL"
                        )
                except RuntimeError:
                    logger.warning(
                        "Tech in Asia detail HTTP unavailable; keeping Algolia data and ID URL"
                    )
            if slug and slug not in company_cache:
                company_cache[slug] = None
                try:
                    url = "https://www.techinasia.com/companies/" + quote(
                        slug, safe="-"
                    )
                    response = await api.request(
                        session, "GET", url, headers={"Accept": "text/html"}
                    )
                    soup = BeautifulSoup(response.text, "html.parser")
                    meta = soup.find("meta", attrs={"name": "description"})
                    company_cache[slug] = (
                        api.clean(meta.get("content")) if meta else None
                    )
                except RuntimeError:
                    logger.warning(
                        "Tech in Asia company context unavailable; not fabricated"
                    )
            if company_cache.get(slug):
                row["job_description"] = api.summary(
                    ("", row["job_description"]), ("ABOUT COMPANY", company_cache[slug])
                )
    return results
