import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.main.main import build_search_url, run_scraper_pipeline
from src.utils.manifest import filter_new_jobs


@pytest.mark.parametrize("platform", ["glints", "kalibrr", "jobstreet", "dealls", "techinasia"])
def test_upload_precedes_manifest_and_keywords_share_seen_ids(platform):
    calls = []

    async def scrape(url, headless, seen_ids):
        assert headless
        assert "old" in seen_ids
        if not calls:
            assert "new" not in seen_ids
        else:
            assert "new" in seen_ids
        calls.append(url)
        return [{"job_id": "new", "company_name": "Listing company"}] * 2

    events = []

    def upload(df, platform):
        assert df.job_id.tolist() == ["new"]
        assert df.keyword.tolist() == ["first"]
        assert df.company_name.tolist() == ["Listing company"]
        events.append("upload")
        return True

    def persist(platform, ids):
        assert ids == {"old", "new"}
        events.append("manifest")
        return True

    with (
        patch(f"src.scraper.jobscraper_{platform}.jobscraper_{platform}", side_effect=scrape),
        patch("src.utils.manifest.read_manifest", return_value={"old"}) as read,
        patch("src.utils.manifest.update_manifest", side_effect=persist),
        patch("src.utils.data_validator.validate_job_data", side_effect=lambda df: df),
        patch("src.utils.upload_to_s3.upload_to_s3", side_effect=upload),
    ):
        assert asyncio.run(run_scraper_pipeline(platform, ["first", "second"])) == 1
        read.assert_called_once_with(platform)
    assert events == ["upload", "manifest"]


@pytest.mark.parametrize("outcome", ["upload_failed", "validation_failed", "empty", "manifest_failed"])
def test_failed_or_empty_runs_do_not_persist_unsaved_ids(outcome):
    jobs = [] if outcome == "empty" else [{"job_id": "new"}]
    with (
        patch("src.scraper.jobscraper_glints.jobscraper_glints", new=AsyncMock(return_value=jobs)),
        patch("src.utils.manifest.read_manifest", return_value=set()),
        patch("src.utils.manifest.update_manifest", return_value=False) as persist,
        patch("src.utils.data_validator.validate_job_data", side_effect=ValueError("invalid") if outcome == "validation_failed" else lambda df: df),
        patch("src.utils.upload_to_s3.upload_to_s3", return_value=outcome != "upload_failed") as upload,
    ):
        if outcome == "validation_failed":
            with pytest.raises(ValueError):
                asyncio.run(run_scraper_pipeline("glints", ["data+engineer"]))
            upload.assert_not_called()
        elif outcome == "manifest_failed":
            with pytest.raises(RuntimeError, match="manifest update failed"):
                asyncio.run(run_scraper_pipeline("glints", ["data+engineer"]))
            persist.assert_called_once()
        else:
            assert asyncio.run(run_scraper_pipeline("glints", ["data+engineer"])) == 0
        if outcome != "manifest_failed":
            persist.assert_not_called()


def test_cards_deduplicate_within_batch_without_mutating_manifest():
    seen = {"old"}
    cards = [{"job_id": jid} for jid in ["old", "new", "new"]]
    assert filter_new_jobs(cards, seen) == [{"job_id": "new"}]
    assert seen == {"old"}


def test_search_urls_preserve_platform_formats():
    assert "query=data%20engineer" in build_search_url("techinasia", "data engineer")
    assert "keyword=data+engineer" in build_search_url("glints", "data+engineer")
    assert "/data-engineer-jobs?daterange=7" in build_search_url("jobstreet", "data-engineer")
