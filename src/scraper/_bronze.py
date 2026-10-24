"""Source-backed Bronze mapping. Narrative fields never contain serialized metadata."""

import json
import re
from urllib.parse import quote, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from src.scraper import _api_common as api

FIELDS = (
    "job_id job_title company_name job_url platform scraped_at keyword job_description "
    "role location salary_min salary_max salary_currency salary_period job_type seniority "
    "work_mode experience_min experience_max education company_industry skills benefits posting_date"
).split()
INTEGER_FIELDS = {"salary_min", "salary_max", "experience_min", "experience_max"}


def get(obj, path, default=None):
    for key in path.split("."):
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key)
    return default if obj is None else obj


def clean(value):
    """Decode HTML or rich-text editor nodes without leaking JSON into narrative."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return clean(json.loads(stripped))
            except ValueError:
                pass
        return api.text(stripped).strip() or None
    if isinstance(value, list):
        parts = [clean(item) for item in value]
        return "\n".join(dict.fromkeys(p for p in parts if p)) or None
    if isinstance(value, dict):
        for key in (
            "text",
            "insert",
            "blocks",
            "ops",
            "children",
            "paragraphs",
            "content",
        ):
            if key in value:
                return clean(value[key])
    return None


def narrative(*sections):
    seen, output = set(), []
    for label, value in sections:
        content = clean(value)
        if content and content not in seen:
            seen.add(content)
            output.append(f"{label}\n{content}" if label else content)
    return "\n\n".join(output) or None


def names(values, path="name"):
    return [get(v, path) if isinstance(v, dict) else v for v in values or []]


def array(values):
    if values is None:
        return None
    if not isinstance(values, list):
        values = [values]
    items = list(dict.fromkeys(clean(v) for v in values if clean(v)))
    return json.dumps(items, ensure_ascii=False)


def join(values):
    return (
        ", ".join(dict.fromkeys(v for v in values if isinstance(v, str) and v.strip()))
        or None
    )


def salary_label(label):
    """Parse only an explicit rupiah label; never infer a currency or period."""
    if not label or not re.search(r"\bRp\b|IDR", label, re.I):
        return {}
    amounts = re.findall(r"(?:Rp\s*|IDR\s*)([\d.,]+)", label, re.I)
    values = [int(v.replace(".", "").replace(",", "")) for v in amounts]
    result = {"salary_currency": "IDR"}
    if len(values) == 2:
        result.update(salary_min=values[0], salary_max=values[1])
    if re.search(r"per month|/month|bulan", label, re.I):
        result["salary_period"] = "month"
    return result


def map_record(platform, job, scraped_at):
    from src.utils.manifest import is_relevant_title

    title = (
        job.get("role")
        if platform == "dealls"
        else job.get("name")
        if platform == "kalibrr"
        else job.get("title")
    )
    if not is_relevant_title(title):
        return None
    native_id = job.get("id") or job.get("objectID")
    if native_id is None:
        raise ValueError("Listing lacks native ID")
    row = dict.fromkeys(FIELDS)
    company = job.get("company") or {}
    row.update(
        job_id=str(native_id),
        job_title=clean(title),
        company_name=clean(company.get("name")),
        platform=platform,
        scraped_at=scraped_at,
    )
    qid = quote(str(native_id), safe="-")
    if platform == "dealls":
        slug = job.get("slug")
        if not slug or not company.get("slug"):
            raise ValueError("Dealls lacks URL slug")
        row.update(
            job_url=f"https://dealls.com/loker/{quote(slug, safe='-')}~{quote(company['slug'], safe='-')}",
            role=get(job, "jobRole.name"),
            location=join(
                [
                    get(job, "location.city.name") or get(job, "city.name"),
                    get(job, "location.country.name"),
                ]
            ),
            job_type=join(job.get("employmentTypes") or []),
            work_mode=job.get("workplaceType"),
            company_industry=company.get("sector"),
            posting_date=job.get("publishedAt"),
            skills=array(
                names(get(job, "candidatePreference.skills") or job.get("skills"))
            ),
            benefits=array(
                names(job.get("perks"))
                + names(get(company, "insight.benefits"))
                + ([job["customPerks"]] if job.get("customPerks") else [])
            ),
            job_description=narrative(
                ("JOB DESCRIPTION", job.get("description")),
                ("RESPONSIBILITIES", job.get("responsibilities")),
                ("QUALIFICATIONS", job.get("requirements")),
                ("ABOUT COMPANY", company.get("description")),
            ),
        )
        salary = job.get("salaryRange")
        if isinstance(salary, dict):
            row.update(salary_min=salary.get("min"), salary_max=salary.get("max"))
    elif platform == "glints":
        salary = (job.get("salaries") or [{}])[0] if job.get("shouldShowSalary") else {}
        row.update(
            job_url=f"https://glints.com/id/opportunities/jobs/{api.slugify(title)}/{qid}",
            role=get(job, "hierarchicalJobCategory.name"),
            location=get(job, "location.formattedName")
            or get(job, "location.name")
            or get(job, "city.name"),
            salary_min=salary.get("minAmount"),
            salary_max=salary.get("maxAmount"),
            salary_currency=salary.get("CurrencyCode"),
            salary_period=salary.get("salaryMode"),
            job_type=job.get("type"),
            work_mode=job.get("workArrangementOption"),
            experience_min=job.get("minYearsOfExperience"),
            experience_max=job.get("maxYearsOfExperience"),
            education=job.get("educationLevel"),
            company_industry=get(company, "industry.name"),
            skills=array(names(job.get("skills"), "skill.name")),
            benefits=array(names(job.get("benefits"), "title"))
            if "benefits" in job
            else None,
            posting_date=job.get("createdAt"),
            job_description=narrative(
                ("JOB DESCRIPTION", job.get("descriptionJsonString")),
                ("ABOUT COMPANY", company.get("descriptionJsonString")),
            ),
        )
    elif platform == "jobstreet":
        row.update(
            job_url=f"https://id.jobstreet.com/id/job/{qid}",
            company_name=clean(
                job.get("companyName") or get(job, "advertiser.description")
            ),
            location=join(names(job.get("locations"), "label")),
            job_type=join(job.get("workTypes") or []),
            work_mode=join(names(get(job, "workArrangements.data"), "label.text")),
            posting_date=job.get("listingDate"),
            job_description=clean(job.get("teaser")),
        )
        row.update(salary_label(job.get("salaryLabel")))
    elif platform == "kalibrr":
        if not job.get("slug") or not company.get("code"):
            raise ValueError("Kalibrr lacks URL components")
        loc = get(job, "google_location.address_components") or {}
        if isinstance(loc, list):
            location = join(names(loc, "long_name"))
        else:
            location = join(
                [loc.get(k) for k in ("city", "region", "province", "country")]
            )
        row.update(
            job_url=f"https://www.kalibrr.com/c/{quote(company['code'], safe='-')}/jobs/{qid}/{quote(job['slug'], safe='-')}",
            company_name=clean(company.get("name") or job.get("company_name")),
            role=job.get("function")
            if isinstance(job.get("function"), str)
            else get(job, "function.name"),
            location=location,
            salary_min=job.get("base_salary"),
            salary_max=job.get("maximum_salary"),
            salary_currency=job.get("salary_currency"),
            salary_period=job.get("salary_interval"),
            job_type=job.get("tenure"),
            company_industry=company.get("industry")
            or get(job, "company_info.industry"),
            skills=array(names(job.get("job_sds_skills"), "sds_skill.name")),
            benefits=array(
                (get(job, "perks.types") or [])
                + ([get(job, "perks.other")] if get(job, "perks.other") else [])
            ),
            posting_date=job.get("activation_date"),
            job_description=narrative(
                ("JOB DESCRIPTION", job.get("description")),
                ("QUALIFICATIONS", job.get("qualifications")),
                (
                    "ABOUT COMPANY",
                    company.get("description") or get(job, "company_info.description"),
                ),
            ),
        )
        if job.get("is_hybrid") is True:
            row["work_mode"] = "hybrid"
        elif job.get("is_work_from_home") is True:
            row["work_mode"] = "remote"
        elif job.get("is_hybrid") is False and job.get("is_work_from_home") is False:
            row["work_mode"] = "on-site"
    else:
        import os

        url = job.get("external_link") or os.getenv(
            "TECHINASIA_JOB_URL_TEMPLATE", "https://www.techinasia.com/jobs/{id}"
        ).format(id=qid)
        row.update(
            job_url=url,
            role=get(job, "position.name"),
            location=join([get(job, "city.name"), get(job, "city.country_name")]),
            salary_min=job.get("salary_min") or None,
            salary_max=job.get("salary_max") or None,
            salary_currency=get(job, "currency.currency_code"),
            job_type=get(job, "job_type.name"),
            work_mode=job.get("work_arrangement"),
            experience_min=job.get("experience_min"),
            experience_max=job.get("experience_max"),
            skills=array(names(job.get("job_skills"))),
            posting_date=job.get("published_at"),
            company_industry=join(names(job.get("industries"))),
            job_description=narrative(
                ("JOB DESCRIPTION", job.get("description")),
                ("ABOUT COMPANY", company.get("description")),
            ),
        )
    parsed = urlsplit(row["job_url"])
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Invalid job URL")
    row["job_url"] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    for key in INTEGER_FIELDS:
        value = row[key]
        if value is not None:
            row[key] = (
                int(value)
                if not isinstance(value, bool) and str(value).isdigit()
                else None
            )
    return row


async def enrich_details(rows, platform):
    if platform not in {"dealls", "glints", "jobstreet"}:
        return rows
    async with api.client() as session:
        for row in rows:
            if platform == "dealls":
                slug = row["job_url"].split("/loker/", 1)[1].split("~")[0]
                body = await api.request_json(
                    session,
                    "GET",
                    f"https://api.sejutacita.id/v1/job-portal/job/public/slug/{slug}",
                )
                job = get(body, "data.result")
                if not isinstance(job, dict) or str(job.get("id")) != row["job_id"]:
                    raise RuntimeError("Dealls detail identity/contract mismatch")
                mapped = map_record(platform, job, row["scraped_at"])
            elif platform == "glints":
                response = await session.get(row["job_url"])
                if response.is_error:
                    raise RuntimeError(
                        f"Glints detail returned HTTP {response.status_code}"
                    )
                soup = BeautifulSoup(response.text, "html.parser")
                node = soup.find("script", id="__NEXT_DATA__")
                if not node:
                    raise RuntimeError("Glints detail lacks __NEXT_DATA__")
                job = get(
                    json.loads(node.string or node.get_text()),
                    "props.pageProps.initialData.data",
                )
                if not isinstance(job, dict) or str(job.get("id")) != row["job_id"]:
                    raise RuntimeError("Glints detail identity/contract mismatch")
                mapped = map_record(platform, job, row["scraped_at"])
                # Listing salaries may be absent from detail; keep source values.
            else:
                body = await api.request_json(
                    session,
                    "POST",
                    "https://id.jobstreet.com/graphql",
                    json={
                        "operationName": "jobDetails",
                        "variables": {
                            "id": row["job_id"],
                            "locale": "id-ID",
                            "zone": "asia-4",
                        },
                        "query": JOBSTREET_QUERY,
                    },
                )
                detail = get(body, "data.jobDetails")
                if (
                    not isinstance(detail, dict)
                    or str(get(detail, "job.id")) != row["job_id"]
                ):
                    raise RuntimeError("Jobstreet detail identity/contract mismatch")
                job = detail["job"]
                mapped = {
                    "job_description": narrative(
                        ("JOB DESCRIPTION", job.get("content")),
                        ("ADDITIONAL DESCRIPTION", job.get("content2")),
                        (
                            "ABOUT COMPANY",
                            get(detail, "companyProfile.overview.description"),
                        ),
                    ),
                    "company_industry": get(detail, "companyProfile.overview.industry"),
                    "benefits": array(
                        names(get(detail, "companyProfile.perksAndBenefits"), "title")
                    ),
                    "role": get(detail, "seoInfo.normalisedRoleTitle"),
                    "location": get(job, "location.label"),
                    "job_type": get(job, "workTypes.label"),
                    "work_mode": join(
                        names(get(detail, "workArrangements.arrangements"), "type")
                    ),
                    "posting_date": get(job, "listedAt.dateTimeUtc"),
                    **salary_label(get(job, "salary.label")),
                }
            if not mapped:
                raise RuntimeError(f"{platform} detail could not be mapped")
            row.update(
                {
                    k: v
                    for k, v in mapped.items()
                    if v is not None and k not in {"keyword", "job_url", "job_id"}
                }
            )
    return rows


JOBSTREET_QUERY = """query jobDetails($id: ID!, $locale: Locale!, $zone: Zone!) {
  jobDetails(id: $id) {
    job { id title content content2(zone: $zone) listedAt { dateTimeUtc }
      salary { label } workTypes { label(locale: $locale) } location { label } }
    companyProfile(zone: $zone) { overview { industry description { paragraphs } } perksAndBenefits { title } }
    seoInfo { normalisedRoleTitle }
  }
}"""
