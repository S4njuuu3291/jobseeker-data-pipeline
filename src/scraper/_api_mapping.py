"""Source-specific mappings; no AI calls or fabricated defaults."""

import json
import os
from urllib.parse import quote

from src.scraper import _api_common as api


def dealls(job, scraped_at):
    company = job.get("company") or {}
    if not job.get("slug") or not company.get("slug"):
        raise ValueError("Dealls listing lacks job/company slug")
    preference = job.get("candidatePreference") or {}
    salary = job.get("salaryRange") or {}
    # Only map keys explicitly named by the source; never interpret 'paid' as a period.
    if not isinstance(salary, dict):
        salary = {}
    narrative = api.summary(
        ("JOB DESCRIPTION", job.get("description")),
        ("RESPONSIBILITIES", job.get("responsibilities")),
        ("QUALIFICATIONS", job.get("requirements")),
    )
    attrs = api.text_attributes(narrative)
    city = job.get("city") or (job.get("location") or {}).get("city") or {}
    benefits = (company.get("insight") or {}).get("benefits") or []
    benefits = [*benefits, *(job.get("perks") or [])]
    if job.get("customPerks"):
        benefits.append(job["customPerks"])
    return api.record(
        "dealls",
        job.get("role"),
        company.get("name"),
        f"https://dealls.com/loker/{quote(job['slug'], safe='-')}~{quote(company['slug'], safe='-')}",
        api.summary(
            ("", narrative),
            ("EDUCATION CODES", preference.get("lastEducations")),
            ("ABOUT COMPANY", company.get("description")),
        ),
        scraped_at,
        native_id=job.get("id"),
        role=(job.get("jobRole") or {}).get("name"),
        location=city.get("name"),
        salary_min=salary.get("min"),
        salary_max=salary.get("max"),
        salary_currency=salary.get("currency"),
        salary_period=salary.get("period"),
        job_type=api.joined(job.get("employmentTypes") or []),
        work_mode=job.get("workplaceType"),
        company_industry=company.get("sector"),
        skills=api.array_string(
            s.get("name") for s in (preference.get("skills") or job.get("skills") or [])
        ),
        benefits=api.array_string(benefits),
        posting_date=job.get("publishedAt"),
        **attrs,
    )


def glints(job, scraped_at, url=None, structured=None):
    company = job.get("company") or {}
    structured = structured or {}
    salaries = job.get("salaries") or []
    # Prefer base salary, never combine bounds from different salary entries.
    salary = (
        next(
            (s for s in salaries if str(s.get("salaryType", "")).upper() == "BASIC"),
            salaries[0] if salaries else {},
        )
        if job.get("shouldShowSalary")
        else {}
    )
    location = job.get("location") or job.get("city") or {}
    description = job.get("descriptionJsonString")
    if description:
        blocks = json.loads(description).get("blocks", [])
        description = "\n".join(b.get("text", "") for b in blocks)
    description = description or structured.get("description")
    about = company.get("descriptionJsonString")
    if about:
        about = "\n".join(
            b.get("text", "") for b in json.loads(about).get("blocks", [])
        )
    about = about or company.get("description") or structured.get("employerOverview")
    skills = []
    for entry in job.get("skills") or job.get("JobSkills") or []:
        skill = entry.get("skill") or entry.get("Skill") or entry
        if skill.get("name"):
            skills.append(skill["name"])
    if not skills and structured.get("skills"):
        skills = structured["skills"].split(",")
    benefits = [b.get("title") for b in job.get("benefits") or []]
    if not benefits and structured.get("jobBenefits"):
        benefits = structured["jobBenefits"].split(",")
    return api.record(
        "glints",
        job.get("title"),
        company.get("name"),
        url
        or f"https://glints.com/id/opportunities/jobs/{api.slugify(job.get('title'))}/{quote(str(job.get('id')), safe='-')}",
        api.summary(("JOB DESCRIPTION", description), ("ABOUT COMPANY", about)),
        scraped_at,
        native_id=job.get("id"),
        role=(job.get("hierarchicalJobCategory") or {}).get("name")
        or structured.get("occupationalCategory"),
        location=location.get("formattedName") or location.get("name"),
        salary_min=salary.get("minAmount"),
        salary_max=salary.get("maxAmount"),
        salary_currency=salary.get("CurrencyCode"),
        salary_period=salary.get("salaryMode"),
        job_type=job.get("type"),
        work_mode=job.get("workArrangementOption"),
        experience_min=job.get("minYearsOfExperience"),
        experience_max=job.get("maxYearsOfExperience"),
        education=job.get("educationLevel"),
        company_industry=(company.get("industry") or {}).get("name"),
        skills=api.array_string(skills),
        benefits=api.array_string(benefits),
        posting_date=structured.get("datePosted") or job.get("createdAt"),
    )


def jobstreet(job, scraped_at):
    company = job.get("companyName") or (job.get("advertiser") or {}).get("description")
    arrangements = (job.get("workArrangements") or {}).get("data") or []
    mode = api.joined((a.get("label") or {}).get("text") for a in arrangements)
    return api.record(
        "jobstreet",
        job.get("title"),
        company,
        f"https://id.jobstreet.com/id/job/{quote(str(job.get('id')), safe='')}",
        api.summary(
            ("SUMMARY", job.get("teaser")), ("HIGHLIGHTS", job.get("bulletPoints"))
        ),
        scraped_at,
        native_id=job.get("id"),
        location=api.joined(x.get("label") for x in job.get("locations") or []),
        job_type=api.joined(job.get("workTypes") or []),
        work_mode=mode,
        posting_date=job.get("listingDate"),
        **api.salary_label(job.get("salaryLabel")),
    )


def kalibrr(job, scraped_at):
    company = job.get("company") or job.get("company_info") or {}
    if not job.get("slug") or not company.get("code"):
        raise ValueError("Kalibrr listing lacks slug/company code")
    address = (job.get("google_location") or {}).get("address_components") or {}
    perks = job.get("perks") or {}
    benefits = list(perks.get("types") or [])
    if perks.get("other"):
        benefits.append(perks["other"])
    qualifications = job.get("qualifications")
    attrs = api.text_attributes(qualifications)
    # Unknown combinations stay null; do not assert onsite from two false flags.
    mode = (
        "Hybrid"
        if job.get("is_hybrid") is True
        else "Remote"
        if job.get("is_work_from_home") is True
        else None
    )
    return api.record(
        "kalibrr",
        job.get("name"),
        company.get("name") or job.get("company_name"),
        "https://www.kalibrr.com/c/{}/jobs/{}/{}".format(
            quote(company["code"], safe="-"),
            quote(str(job.get("id")), safe=""),
            quote(job["slug"], safe="-"),
        ),
        api.summary(
            ("JOB DESCRIPTION", job.get("description")),
            ("QUALIFICATIONS", qualifications),
            ("EDUCATION CODE", job.get("education_level")),
            ("EXPERIENCE CODE", job.get("work_experience")),
            (
                "ABOUT COMPANY",
                company.get("description")
                or (job.get("company_info") or {}).get("description"),
            ),
        ),
        scraped_at,
        native_id=job.get("id"),
        role=job.get("function"),
        location=api.joined(address.get(k) for k in ("city", "region", "country")),
        salary_min=job.get("base_salary") if job.get("salary_shown") else None,
        salary_max=job.get("maximum_salary") if job.get("salary_shown") else None,
        salary_currency=job.get("salary_currency") if job.get("salary_shown") else None,
        salary_period=job.get("salary_interval") if job.get("salary_shown") else None,
        job_type=job.get("tenure"),
        work_mode=mode,
        company_industry=company.get("industry"),
        skills=api.array_string(
            (s.get("sds_skill") or {}).get("name")
            for s in job.get("job_sds_skills") or []
        ),
        benefits=api.array_string(benefits),
        posting_date=job.get("activation_date"),
        **attrs,
    )


def techinasia(job, scraped_at):
    company = job.get("company") or {}
    # External links may lead to a company-wide careers page, not this job.
    template = os.getenv(
        "TECHINASIA_JOB_URL_TEMPLATE", "https://www.techinasia.com/jobs/{id}"
    )
    url = job.get("url") or template.format(
        id=quote(str(job.get("id") or job.get("objectID")), safe="-")
    )
    description = job.get("description")
    attrs = api.text_attributes(description)
    attrs.pop("experience_min", None)
    attrs.pop("experience_max", None)
    positive_salary = (api.integer(job.get("salary_min")) or 0) > 0 and (
        api.integer(job.get("salary_max")) or 0
    ) > 0
    salary_visible = bool(job.get("is_salary_visible")) and positive_salary
    return api.record(
        "techinasia",
        job.get("title"),
        company.get("name"),
        url,
        api.summary(
            ("JOB DESCRIPTION", description),
            ("ABOUT COMPANY", company.get("description")),
            ("COMPANY SIZE", company.get("employee_count")),
        ),
        scraped_at,
        native_id=job.get("id") or job.get("objectID"),
        role=(job.get("position") or {}).get("name"),
        location=api.joined(
            (job.get("city") or {}).get(k) for k in ("name", "country_name")
        ),
        salary_min=job.get("salary_min") if salary_visible else None,
        salary_max=job.get("salary_max") if salary_visible else None,
        salary_currency=(job.get("currency") or {}).get("currency_code")
        if job.get("is_salary_visible")
        else None,
        job_type=(job.get("job_type") or {}).get("name"),
        work_mode=job.get("work_arrangement"),
        experience_min=job.get("experience_min"),
        experience_max=job.get("experience_max"),
        company_industry=api.joined(i.get("name") for i in job.get("industries") or []),
        skills=api.array_string(s.get("name") for s in job.get("job_skills") or []),
        posting_date=job.get("published_at"),
        **attrs,
    )
