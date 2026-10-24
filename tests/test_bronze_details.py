"""HTTP contract tests for detail enrichment and the 24-column Bronze boundary."""

import asyncio
import json
from unittest.mock import patch

import httpx
import pytest

from src.scraper import _api_common as api
from src.scraper._bronze import FIELDS, clean, enrich_details, map_record


def glints_job():
    return {
        "id": "native-1",
        "title": "Data Engineer",
        "company": {
            "name": "Example",
            "descriptionJsonString": json.dumps(
                {"blocks": [{"text": "We build tools."}]}
            ),
            "industry": {"name": "Software"},
        },
        "descriptionJsonString": json.dumps(
            {"blocks": [{"text": "Build pipelines."}, {"text": "SQL required."}]}
        ),
        "location": {"formattedName": "Jakarta, Indonesia"},
        "shouldShowSalary": True,
        "salaries": [
            {
                "minAmount": 100,
                "maxAmount": 200,
                "CurrencyCode": "IDR",
                "salaryMode": "MONTHLY",
            }
        ],
        "skills": [{"skill": {"name": "Python"}}],
        "benefits": [{"title": "Health insurance"}],
        "minYearsOfExperience": 0,
        "maxYearsOfExperience": 2,
    }


def mock_client(monkeypatch, handler):
    monkeypatch.setattr(
        api,
        "client",
        lambda *args, **kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
    )


def test_narrative_is_clean_and_metadata_stays_structured():
    row = map_record("glints", glints_job(), "20261024_080000")
    assert set(row) == set(FIELDS)
    assert row["job_id"] == "native-1"
    assert (
        row["job_description"]
        == "JOB DESCRIPTION\nBuild pipelines.\nSQL required.\n\nABOUT COMPANY\nWe build tools."
    )
    assert "Jakarta" not in row["job_description"]
    assert "Python" not in row["job_description"]
    assert row["location"] == "Jakarta, Indonesia"
    assert json.loads(row["skills"]) == ["Python"]
    assert row["salary_min"] == 100
    assert row["experience_min"] == 0
    assert row["seniority"] is None
    assert clean("<p>A &amp; B</p><script>bad</script>") == "A & B"


@pytest.mark.parametrize("platform", ["glints", "dealls", "jobstreet"])
def test_real_detail_mapping(platform, monkeypatch):
    if platform == "glints":
        listing = glints_job()
        detail = glints_job()
        detail.pop("salaries")
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps({"props": {"pageProps": {"initialData": {"data": detail}}}})
            + "</script>"
        )
        response = httpx.Response(200, text=html)
    elif platform == "dealls":
        listing = {
            "id": "native-1",
            "role": "Data Engineer",
            "slug": "data-engineer",
            "company": {"name": "Example", "slug": "example"},
        }
        detail = {
            **listing,
            "responsibilities": "<p>Build pipelines.</p>",
            "requirements": "<p>SQL required.</p>",
            "company": {**listing["company"], "description": "<p>We build tools.</p>"},
        }
        response = httpx.Response(200, json={"code": 200, "data": {"result": detail}})
    else:
        listing = {"id": "native-1", "title": "Data Engineer", "companyName": "Example"}
        response = httpx.Response(
            200,
            json={
                "data": {
                    "jobDetails": {
                        "job": {
                            "id": "native-1",
                            "content": "<p>Build pipelines.</p>",
                            "content2": "<p>SQL required.</p>",
                            "salary": {
                                "label": "Rp 7.000.000 – Rp 10.000.000 per month"
                            },
                        },
                        "companyProfile": {
                            "overview": {
                                "description": {"paragraphs": ["We build tools."]},
                                "industry": "Software",
                            },
                            "perksAndBenefits": [{"title": "Health insurance"}],
                        },
                    }
                }
            },
        )
    requests = []

    def respond(request):
        requests.append(request)
        return response

    mock_client(monkeypatch, respond)
    row = map_record(platform, listing, "20261024_080000")
    result = asyncio.run(enrich_details([row], platform))[0]
    assert len(requests) == 1
    if platform == "dealls":
        assert requests[0].url.path == "/v1/job-portal/job/public/slug/data-engineer"
    assert set(result) == set(FIELDS)
    assert all(
        s in result["job_description"]
        for s in ["Build pipelines.", "SQL required.", "We build tools."]
    )
    assert "<p>" not in result["job_description"]
    if platform == "glints":
        assert result["salary_min"] == 100
    if platform == "jobstreet":
        payload = json.loads(requests[0].content)
        assert payload["variables"] == {
            "id": "native-1",
            "locale": "id-ID",
            "zone": "asia-4",
        }
        assert result["salary_min"] == 7000000
        assert result["salary_max"] == 10000000
        assert result["salary_period"] == "month"


@pytest.mark.parametrize("platform", ["dealls", "glints", "jobstreet"])
def test_seen_native_id_prevents_detail_requests(platform, monkeypatch):
    from importlib import import_module

    module = import_module(f"src.scraper.jobscraper_{platform}")
    row = map_record("glints", glints_job(), "20261024_080000")
    mock_client(monkeypatch, lambda request: pytest.fail("Seen job requested detail"))
    with patch.object(module, "collect_job_cards", return_value=[row]):
        result = asyncio.run(
            getattr(module, f"jobscraper_{platform}")(
                "https://example.com/?keyword=data&searchJob=data&keywords=data",
                seen_ids={"native-1"},
            )
        )
    assert result == []


@pytest.mark.parametrize("platform", ["dealls", "glints", "jobstreet"])
def test_invalid_detail_fails_instead_of_persisting_incomplete_job(
    platform, monkeypatch
):
    row = map_record("glints", glints_job(), "20261024_080000")
    if platform == "dealls":
        row["job_url"] = "https://dealls.com/loker/data-engineer~example"
    mock_client(monkeypatch, lambda request: httpx.Response(200, json={"data": {}}))
    with pytest.raises(RuntimeError):
        asyncio.run(enrich_details([row], platform))


def test_legacy_hash_is_filtered_without_mutating_manifest():
    import hashlib

    row = map_record("glints", glints_job(), "20261024_080000")
    seen = {hashlib.md5(row["job_url"].encode()).hexdigest()}
    original = seen.copy()
    assert api.new_records([row], seen) == []
    assert seen == original


def test_manifest_read_failure_does_not_restart_from_empty(monkeypatch):
    from src.utils.manifest import read_manifest

    monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bronze")

    class Client:
        class exceptions:
            class NoSuchKey(Exception):
                pass

        def get_object(self, **kwargs):
            raise PermissionError("Access denied")

    with patch("boto3.client", return_value=Client()):
        with pytest.raises(RuntimeError, match="scraping dibatalkan"):
            read_manifest("glints")
