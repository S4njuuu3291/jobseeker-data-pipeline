"""Verify all dev platform routes survive migration to the shared runner."""
from unittest.mock import AsyncMock, patch
import pytest
from src.entrypoint.handlers import scraper_handler

@pytest.mark.parametrize("platform", ["kalibrr", "glints", "jobstreet", "dealls", "techinasia"])
def test_dev_platform_dispatch_preserved(platform, monkeypatch):
    monkeypatch.setenv("SCRAPE_KEYWORDS", "etl")
    with patch("src.entrypoint.handlers._load_runtime_secret"), patch(f"src.main.main.run_{platform}_pipeline", new=AsyncMock(return_value=1)) as runner:
        response = scraper_handler({"platform": platform}, None)
    assert response["statusCode"] == 200
    assert response["platform"] == platform
    runner.assert_awaited_once_with(["etl"])
