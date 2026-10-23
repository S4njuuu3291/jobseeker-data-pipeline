"""Offline contract checks for the temporary listing API adapters."""

import asyncio
import copy
import hashlib
import importlib
import json
from pathlib import Path
from urllib.parse import parse_qs
from unittest.mock import patch

import httpx
import pandas as pd
import pytest

from src.main.main import build_search_url
from src.scraper import _api_common as api
from src.utils.data_validator import validate_job_data
from src.utils.scraper_utils import normalize_url

DATA = Path(__file__).resolve().parent / "fixtures" / "scraper_api"
FILES = {
    "dealls": "dealls_response.json",
    "glints": "glints_response.json",
    "jobstreet": "jobstreet_search_response.json",
    "kalibrr": "kalibrr_response.json",
    "techinasia": "techinasia_response.json",
}
FIELDS = {
    "job_id",
    "job_title",
    "company_name",
    "job_url",
    "platform",
    "scraped_at",
    "job_description",
}


def module(platform):
    return importlib.import_module(f"src.scraper.jobscraper_{platform}_api")


def fixture(platform):
    return json.loads((DATA / FILES[platform]).read_text(encoding="utf-8"))


def jobs_in(body, platform):
    if platform == "dealls":
        return body["data"]["docs"]
    if platform == "glints":
        return body["data"]["searchJobsV3"]["jobsInPage"]
    if platform == "techinasia":
        return body["results"][0]["hits"]
    return body["jobs" if platform == "kalibrr" else "data"]


def install_mock(monkeypatch, handler):
    monkeypatch.setenv("GLINTS_COOKIE", "session=test-only")
    monkeypatch.setenv("TECHINASIA_API_KEY", "test-search-key")
    monkeypatch.delenv("TECHINASIA_JOB_URL_TEMPLATE", raising=False)

    def client(headers=None):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler), headers=headers or {}
        )

    monkeypatch.setattr(api, "client", client)


@pytest.mark.parametrize("platform", FILES)
def test_recorded_listing_matches_bronze_and_manifest_contract(platform, monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=fixture(platform))

    install_mock(monkeypatch, respond)
    runner = getattr(module(platform), f"jobscraper_{platform}")
    url = build_search_url(platform, "data engineer")
    # Even local previews/adapters must never accidentally touch AWS.
    with patch("boto3.client", side_effect=AssertionError("Unexpected AWS call")):
        records = asyncio.run(runner(url, max_pages=1))
        assert len(requests) == 1
        if platform == "kalibrr":
            # Sanitized example retains an unrelated title from the observed result.
            assert records == []
        else:
            assert records
            validate_job_data(pd.DataFrame(records))
            for row in records:
                assert set(row) == FIELDS
                assert row["platform"] == platform
                assert (
                    row["job_id"]
                    == hashlib.md5(normalize_url(row["job_url"]).encode()).hexdigest()
                )
                assert row["job_description"]
                assert "<p>" not in row["job_description"]
            seen = {row["job_id"] for row in records}
            unchanged = seen.copy()
            assert asyncio.run(runner(url, seen_ids=seen, max_pages=1)) == []
            assert seen == unchanged

    first = requests[0]
    if platform == "glints":
        payload = json.loads(first.content)
        assert payload["variables"]["data"]["SearchTerm"] == "data engineer"
        assert payload["variables"]["data"]["sortBy"] == "LATEST"
        assert first.headers["cookie"] == "session=test-only"
    elif platform == "techinasia":
        assert first.headers["x-algolia-api-key"] == "test-search-key"
        params = parse_qs(json.loads(first.content)["requests"][0]["params"])
        assert params["query"] == ["data engineer"]
        assert json.loads(params["facetFilters"][0]) == [
            ["city.country_name:Indonesia"]
        ]
    else:
        key = {"dealls": "search", "kalibrr": "text", "jobstreet": "keywords"}[platform]
        assert first.url.params[key] == "data engineer"


@pytest.mark.parametrize("platform", FILES)
def test_pagination_continues_after_filtered_page_and_stops_on_repeated_ids(
    platform, monkeypatch
):
    base = fixture(platform)
    original = copy.deepcopy(jobs_in(base, platform)[0])
    title_key = {"dealls": "role", "kalibrr": "name"}.get(platform, "title")
    bodies = []
    for index, title in enumerate(
        ["Data Entry Clerk", "Data Engineer", "Data Engineer"]
    ):
        body = copy.deepcopy(base)
        job = copy.deepcopy(original)
        job[title_key] = title
        if index:
            job["id"] = str(job["id"]) + "-next"
            job["objectID"] = job["id"]
            job["slug"] = (job.get("slug") or "data-engineer") + "-next"
        jobs_in(body, platform)[:] = [job]
        if platform == "dealls":
            body["data"]["totalPages"] = 10
        elif platform == "glints":
            body["data"]["searchJobsV3"]["hasMore"] = True
        elif platform == "techinasia":
            body["results"][0]["nbPages"] = 10
        else:
            body["count" if platform == "kalibrr" else "totalCount"] = 100
        bodies.append(body)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=bodies[min(len(requests) - 1, 2)])

    install_mock(monkeypatch, respond)
    runner = getattr(module(platform), f"jobscraper_{platform}")
    records = asyncio.run(
        runner(build_search_url(platform, "data engineer"), max_pages=5)
    )
    assert len(records) == 1
    assert records[0]["job_title"] == "Data Engineer"
    assert len(requests) == 3
    if platform == "kalibrr":
        assert [r.url.params["offset"] for r in requests] == ["0", "20", "40"]


def test_kalibrr_preserves_html_description_and_qualifications():
    job = fixture("kalibrr")["jobs"][0]
    job["name"] = "Data Engineer"  # Exercise mapping independently of the title filter.
    row = module("kalibrr").listing_to_record(job, "20261023_080000")
    assert "/c/example-company/jobs/900001/field-education-consultant" in row["job_url"]
    assert "JOB DESCRIPTION" in row["job_description"]
    assert "QUALIFICATIONS" in row["job_description"]
    assert "Membangun pipeline data" in row["job_description"]
    assert "Pendidikan minimal Diploma" in row["job_description"]


def test_glints_rejects_expired_session_instead_of_accepting_wrong_results(monkeypatch):
    body = fixture("glints")
    body["isAuthenticated"] = False
    install_mock(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(RuntimeError, match="session is missing or expired"):
        asyncio.run(
            module("glints").jobscraper_glints(
                build_search_url("glints", "data engineer")
            )
        )


@pytest.mark.parametrize(
    "platform,env", [("glints", "GLINTS_COOKIE"), ("techinasia", "TECHINASIA_API_KEY")]
)
def test_credentials_are_explicit_and_never_read_from_notes(platform, env, monkeypatch):
    monkeypatch.delenv(env, raising=False)
    with pytest.raises(ValueError, match=env):
        asyncio.run(
            getattr(module(platform), f"jobscraper_{platform}")(
                build_search_url(platform, "data engineer")
            )
        )


@pytest.mark.parametrize(
    "body",
    [{"errors": [{"message": "private error"}]}, {"message": "changed contract"}],
)
def test_errors_are_not_reported_as_successful_empty_listing(body, monkeypatch):
    install_mock(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(RuntimeError):
        asyncio.run(
            module("jobstreet").jobscraper_jobstreet(
                build_search_url("jobstreet", "data engineer")
            )
        )


def test_http_retries_and_errors_do_not_expose_credentials(monkeypatch, caplog):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(503, text="unavailable")

    async def no_wait(seconds):
        pass

    monkeypatch.setattr(api.asyncio, "sleep", no_wait)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as session:
            with pytest.raises(RuntimeError, match="HTTP 503") as error:
                await api.request_json(
                    session, "GET", "https://example.com/?key=secret-value"
                )
            assert "secret-value" not in str(error.value)

    asyncio.run(run())
    assert len(requests) == 3
    assert "secret-value" not in caplog.text


@pytest.mark.parametrize(
    "platform,keyword",
    [
        ("glints", "data+engineer"),
        ("dealls", "data+engineer"),
        ("kalibrr", "data-engineer"),
        ("jobstreet", "data-engineer"),
        ("techinasia", "data engineer"),
    ],
)
def test_existing_search_url_keyword_formats(platform, keyword):
    assert (
        api.search_keyword(build_search_url(platform, keyword), platform)
        == "data engineer"
    )


def test_record_identity_matches_existing_tracking_normalization():
    url = "https://id.jobstreet.com/id/job/123;params?tracking=one#details"
    row = api.record("jobstreet", "Data Engineer", None, url, None, "20261023_080000")
    assert row["job_id"] == hashlib.md5(normalize_url(url).encode()).hexdigest()
    assert row["company_name"] == "Unknown"
    assert row["job_description"] is None
