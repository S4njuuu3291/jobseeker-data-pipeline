"""Evidence-grounded extraction and preserving source values through Silver."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.ai.extraction import FIELDS, validate_proposals
from src.ai.nlp import parse_job
from src.scraper.bronze_schema import BRONZE_COLUMNS
from src.silver_layer.orchestrator import (
    RateLimiter,
    is_missing,
    parse_single_job,
    transform_silver,
)


def proposal(value, evidence):
    return {"value": value, "evidence": evidence}


def response(payload):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload)),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=30, total_tokens=50),
    )


@pytest.mark.parametrize(
    "field,value,quote,source",
    [
        ("seniority", "senior", "5 years of experience", "5 years of experience"),
        (
            "seniority",
            "senior",
            "Work with senior engineers",
            "Work with senior engineers",
        ),
        ("salary_min", 10000000, "Build pipelines", "Build pipelines"),
        ("salary_currency", "IDR", "Based in Indonesia", "Based in Indonesia"),
        ("salary_period", "monthly", "Salary negotiable", "Salary negotiable"),
        ("posting_date", "2026-10-23", "Posted today", "Posted today"),
        (
            "experience_max",
            3,
            "Minimum 3 years of experience",
            "Minimum 3 years of experience",
        ),
        (
            "experience_min",
            5,
            "Minimum 3 years of experience",
            "Minimum 3 years of experience",
        ),
        ("skills", ["Python", "Rust"], "Python", "Python"),
        ("benefits", ["BPJS"], "No BPJS", "No BPJS"),
        ("education", "master", "Bachelor degree", "Bachelor degree"),
        ("education", "master", "Master degree preferred", "Master degree preferred"),
        (
            "location",
            "Jakarta",
            "Jakarta",
            "JOB DESCRIPTION\nBuild pipelines.\nABOUT COMPANY\nJakarta",
        ),
        (
            "work_mode",
            "remote",
            "We work remote",
            "JOB DESCRIPTION\nBuild pipelines.\nABOUT COMPANY\nWe work remote",
        ),
        ("skills", ["Python"], "Use Python", "Build pipelines"),
    ],
)
def test_unsupported_values_remain_null(field, value, quote, source):
    values, evidence, rejected = validate_proposals(
        {field: proposal(value, quote)}, [field], "Data Engineer", source
    )
    assert values[field] is None
    assert evidence == {}
    assert rejected == [field]


@pytest.mark.parametrize(
    "field,value,quote,title",
    [
        ("seniority", "senior", "Senior Data Engineer", "Senior Data Engineer"),
        ("education", "bachelor", "Bachelor degree required", "Data Engineer"),
        ("experience_min", 3, "Minimum 3 years of experience", "Data Engineer"),
        ("experience_max", 5, "3–5 years of experience", "Data Engineer"),
        (
            "salary_min",
            7000000,
            "Rp 7.000.000 – Rp 10.000.000 per month",
            "Data Engineer",
        ),
        ("salary_max", 10000000, "Rp 7–10 juta per bulan", "Data Engineer"),
        ("salary_currency", "IDR", "Rp 7–10 juta per bulan", "Data Engineer"),
        ("salary_period", "monthly", "Rp 7–10 juta per bulan", "Data Engineer"),
        (
            "skills",
            ["Python", "SQL"],
            "Required skills: Python and SQL",
            "Data Engineer",
        ),
        ("benefits", ["BPJS"], "Benefits: BPJS", "Data Engineer"),
        ("posting_date", "2026-10-01", "Posted 2026-10-01", "Data Engineer"),
        (
            "company_industry",
            "Financial Services",
            "Our industry is Financial Services",
            "Data Engineer",
        ),
    ],
)
def test_explicit_values_with_supported_quotes_are_accepted(field, value, quote, title):
    values, evidence, rejected = validate_proposals(
        {field: proposal(value, quote)}, [field], title, quote
    )
    assert values[field] == value
    assert evidence[field] == quote
    assert rejected == []


def complete_row():
    row = dict.fromkeys(BRONZE_COLUMNS)
    row.update({field: "Known source value" for field in FIELDS})
    row.update(
        job_id="native-123",
        job_title="Senior Data Engineer",
        company_name="Source company",
        job_description="Required skills: Python and SQL",
        job_url="https://example.com/jobs/123",
        platform="glints",
        scraped_at="20261023_120000",
        keyword="data engineer",
        location="Jakarta",
        salary_min=7000000,
        salary_max=10000000,
        experience_min=0,
        experience_max=3,
        posting_date="2026-10-01",
        skills='["SQL"]',
        benefits='["BPJS"]',
    )
    return row


def test_complete_bronze_skips_ai_and_keeps_real_zero():
    row = complete_row()
    with patch("src.silver_layer.orchestrator.parse_job") as parse:
        result = parse_single_job(row, 0, RateLimiter())
    parse.assert_not_called()
    assert result["api_finish_reason"] == "not_needed"
    assert result["api_model"] is None
    assert result["api_cost_usd"] == 0
    assert result["api_usage_total_tokens"] == 0
    assert not is_missing(0)


def test_end_to_end_fills_only_missing_fields_without_duplicates_or_losing_nulls():
    row = complete_row()
    row.update(skills=None, seniority=None, salary_max=None, posting_date=None)
    client = Mock()
    client.chat.completions.create.return_value = response(
        {
            "skills": proposal(["Python", "SQL"], "Required skills: Python and SQL"),
            "seniority": proposal("senior", "Senior Data Engineer"),
            "salary_max": None,
            "posting_date": None,
            # Unexpected fields cannot overwrite Bronze even if the AI emits them.
            "salary_min": proposal(1, "Required skills: Python and SQL"),
            "company_name": "Invented company",
            "job_id": "invented-id",
        }
    )
    frame = pd.DataFrame([row], index=[99])
    original = frame.copy(deep=True)
    with (
        patch("src.ai.nlp._get_client", return_value=client),
        patch(
            "src.silver_layer.orchestrator.upload_to_silver",
            return_value="silver.parquet",
        ) as upload,
    ):
        assert transform_silver(frame) == "silver.parquet"
    result = upload.call_args.args[0]
    assert result.columns.is_unique
    assert len(result.columns) == 36
    assert result.at[0, "job_id"] == "native-123"
    assert result.at[0, "company_name"] == "Source company"
    assert result.at[0, "salary_min"] == 7000000
    assert result.at[0, "experience_min"] == 0
    assert result.at[0, "seniority"] == "senior"
    assert json.loads(result.at[0, "skills"]) == ["Python", "SQL"]
    assert pd.isna(result.at[0, "salary_max"])
    assert pd.isna(result.at[0, "posting_date"])
    assert str(result.salary_max.dtype) == "Int64"
    assert result.at[0, "api_usage_total_tokens"] == 50
    sent = json.loads(
        client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    )
    assert set(sent["requested_fields"]) == {
        "skills",
        "seniority",
        "salary_max",
        "posting_date",
    }
    assert "keyword" not in sent and "job_url" not in sent
    pd.testing.assert_frame_equal(frame, original)


def test_no_missing_fields_api_call_is_skipped_even_for_direct_parser():
    with patch("src.ai.nlp._get_client") as client:
        result = parse_job("Data Engineer", "Anything", fields=[])
    client.assert_not_called()
    assert result["api_finish_reason"] == "not_needed"
    assert result["api_usage_total_tokens"] == 0


def test_null_location_remains_null_after_transformation():
    from src.silver_layer.transformations import apply_location_normalization

    result = apply_location_normalization(pd.DataFrame({"location": [None, pd.NA, ""]}))
    assert result.location.isna().all()


@pytest.mark.parametrize(
    "field,value,quote,source,title",
    [
        ("work_mode", "remote", "remote", "This job is not remote.", "Data Engineer"),
        ("benefits", ["BPJS"], "BPJS", "We do not provide BPJS.", "Data Engineer"),
        (
            "education",
            "master",
            "Master degree",
            "Master degree preferred.",
            "Data Engineer",
        ),
        (
            "work_mode",
            "remote",
            "remote",
            "Hybrid schedule with remote and onsite days.",
            "Data Engineer",
        ),
        (
            "seniority",
            "senior",
            "Senior",
            "Build pipelines.",
            "Junior / Senior Data Engineer",
        ),
    ],
)
def test_cherry_picked_quotes_cannot_hide_negation_or_ambiguity(
    field, value, quote, source, title
):
    values, _, rejected = validate_proposals(
        {field: proposal(value, quote)}, [field], title, source
    )
    assert values[field] is None
    assert rejected == [field]


@pytest.mark.parametrize(
    "field,value,quote,source",
    [
        (
            "posting_date",
            "2026-12-01",
            "Application deadline 2026-12-01",
            "Application deadline 2026-12-01",
        ),
        (
            "company_industry",
            "banking",
            "Experience in banking industry",
            "Experience in banking industry",
        ),
        (
            "role",
            "Data Scientist",
            "Collaborate with Data Scientist",
            "Collaborate with Data Scientist",
        ),
    ],
)
def test_wrong_business_context_does_not_count_as_evidence(field, value, quote, source):
    values, _, rejected = validate_proposals(
        {field: proposal(value, quote)}, [field], "Data Engineer", source
    )
    assert values[field] is None
    assert rejected == [field]
