"""The 24 business columns shared by API Bronze records and Silver."""

BRONZE_COLUMNS = (
    "job_id",
    "job_title",
    "job_url",
    "platform",
    "scraped_at",
    "keyword",
    "job_description",
    "role",
    "company_name",
    "location",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "job_type",
    "seniority",
    "work_mode",
    "experience_min",
    "experience_max",
    "education",
    "company_industry",
    "skills",
    "benefits",
    "posting_date",
)
INTEGER_COLUMNS = ("salary_min", "salary_max", "experience_min", "experience_max")
