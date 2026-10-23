"""Critical schema, detail recovery, S3 storage, and manifest guarantees."""

import asyncio
import io
from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from botocore.exceptions import ClientError

from src.scraper import _api_common as api
from src.scraper._api_details import enrich
from src.scraper._api_mapping import kalibrr, techinasia
from src.scraper.bronze_schema import BRONZE_COLUMNS, INTEGER_COLUMNS
from src.utils.data_validator import validate_api_job_data
from src.utils.manifest import read_manifest
from src.utils.upload_to_s3 import upload_to_s3


def sample_row():
    row = api.record(
        "jobstreet",
        "Data Engineer",
        None,
        "https://id.jobstreet.com/id/job/123",
        None,
        "20261023_080000",
        native_id="123",
    )
    row["keyword"] = "data engineer"
    return row


def test_bronze_columns_match_silver_core(monkeypatch):
    monkeypatch.setenv("platform", "glints,jobstreet,dealls,kalibrr,techinasia")
    from src.silver_layer.config import JOB_SILVER_SCHEMA

    assert len(BRONZE_COLUMNS) == 24
    assert set(BRONZE_COLUMNS) == set(JOB_SILVER_SCHEMA.columns)


def test_nullable_schema_and_parquet_preserve_all_24_physical_types(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
    row = sample_row()
    frame = validate_api_job_data(pd.DataFrame([row]))
    assert all(str(frame[c].dtype) == "Int64" for c in INTEGER_COLUMNS)
    s3 = MagicMock()
    with patch("src.utils.upload_to_s3.boto3.client", return_value=s3):
        assert upload_to_s3(frame, "jobstreet")
        assert upload_to_s3(frame, "jobstreet")
    s3.delete_object.assert_not_called()
    first, second = (call.kwargs for call in s3.put_object.call_args_list)
    assert first["Key"] != second["Key"]
    assert first["Key"].startswith("platform=jobstreet/ingestion_date=")
    schema = pq.read_schema(io.BytesIO(first["Body"]))
    assert schema.names == list(BRONZE_COLUMNS)
    for name in BRONZE_COLUMNS:
        assert schema.field(name).type == (
            pa.int64() if name in INTEGER_COLUMNS else pa.string()
        )


@pytest.mark.parametrize(
    "bad", [{"extra": "unexpected"}, {"skills": '{"not": "an array"}'}]
)
def test_invalid_api_contract_rejected(bad):
    row = {**sample_row(), **bad}
    with pytest.raises(Exception):
        validate_api_job_data(pd.DataFrame([row]))


def test_null_and_zero_are_not_invented_salary_values():
    assert api.salary_label("Rp 7.000.000 – Rp 10.000.000 per month") == {
        "salary_min": 7000000,
        "salary_max": 10000000,
        "salary_currency": "IDR",
        "salary_period": "Monthly",
    }
    assert api.salary_label("Competitive") == {}
    row = techinasia(
        {
            "id": "native-id",
            "title": "Data Engineer",
            "salary_min": 0,
            "salary_max": 0,
            "is_salary_visible": 1,
        },
        "20261023_080000",
    )
    assert row["salary_min"] is None and row["salary_max"] is None
    assert row["seniority"] is None


def test_kalibrr_codes_are_not_years_and_company_context_is_retained():
    row = kalibrr(
        {
            "id": 123,
            "name": "Data Engineer",
            "slug": "data-engineer",
            "company": {
                "code": "example",
                "name": "Example",
                "description": "<p>About example</p>",
            },
            "work_experience": 200,
            "education_level": 450,
            "qualifications": "<p>Pengalaman minimal 2 tahun. Pendidikan minimal D3.</p>",
        },
        "20261023_080000",
    )
    assert row["job_id"] == "123"
    assert row["experience_min"] == 2
    assert row["experience_max"] is None
    assert row["education"] == "Diploma"
    assert row["work_mode"] is None
    assert "About example" in row["job_description"]
    assert "<p>" not in row["job_description"]


@pytest.mark.parametrize(
    "status,body", [(403, None), (200, {"data": {"jobDetails": None}})]
)
def test_failed_detail_excluded_so_manifest_can_retry(monkeypatch, status, body):
    def client(headers=None):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(status, json=body))
        )

    monkeypatch.setattr(api, "client", client)
    assert asyncio.run(enrich([sample_row()], "jobstreet")) == []


@pytest.mark.parametrize("error_code", ["AccessDenied", "SlowDown"])
def test_manifest_read_errors_do_not_start_fresh(monkeypatch, error_code):
    monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
    s3 = MagicMock()
    s3.get_object.side_effect = ClientError(
        {"Error": {"Code": error_code}}, "GetObject"
    )
    with patch("src.utils.manifest.boto3.client", return_value=s3):
        with pytest.raises(RuntimeError, match="refusing to rescrape"):
            read_manifest("jobstreet")


def test_missing_manifest_is_valid_first_run(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
    s3 = MagicMock()
    s3.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey"}}, "GetObject"
    )
    with patch("src.utils.manifest.boto3.client", return_value=s3):
        assert read_manifest("jobstreet") == set()


def test_corrupt_manifest_cannot_turn_into_empty_history(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
    buffer = io.BytesIO()
    pd.DataFrame({"wrong_column": ["123"]}).to_parquet(buffer)
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": io.BytesIO(buffer.getvalue())}
    with patch("src.utils.manifest.boto3.client", return_value=s3):
        with pytest.raises(RuntimeError, match="refusing to rescrape"):
            read_manifest("jobstreet")


def test_explicit_minimum_education_uses_first_requirement():
    attrs = api.text_attributes("Pendidikan minimal Diploma (D3), Sarjana diutamakan.")
    assert attrs["education"] == "Diploma"


def test_detail_identity_mismatch_cannot_overwrite_listing():
    from src.scraper._api_details import merge

    original = sample_row()
    other = {**original, "job_id": "different"}
    with pytest.raises(ValueError, match="ID"):
        merge(original, other)
    assert original["job_id"] == "123"
