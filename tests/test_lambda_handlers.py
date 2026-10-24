"""Runtime contracts for ZIP handlers, using no AWS/AI network requests."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.entrypoint.handlers import (
    _load_runtime_secret,
    scraper_handler,
    silver_layer_handler,
)


def test_secret_is_fetched_at_runtime_without_logging_value(monkeypatch, capsys):
    monkeypatch.delenv("GLINTS_COOKIE", raising=False)
    monkeypatch.setenv("GLINTS_COOKIE_PARAMETER", "/jobscraper/glints/cookie-dev")
    client = Mock()
    client.get_parameter.return_value = {"Parameter": {"Value": "private-cookie"}}
    with patch("boto3.client", return_value=client):
        _load_runtime_secret("GLINTS_COOKIE")
        _load_runtime_secret("GLINTS_COOKIE")
    client.get_parameter.assert_called_once_with(
        Name="/jobscraper/glints/cookie-dev", WithDecryption=True
    )
    import os

    assert os.environ["GLINTS_COOKIE"] == "private-cookie"
    assert "private-cookie" not in capsys.readouterr().out


def test_placeholder_stops_scraper_instead_of_returning_empty_jobs(monkeypatch):
    monkeypatch.delenv("TECHINASIA_API_KEY", raising=False)
    monkeypatch.setenv(
        "TECHINASIA_API_KEY_PARAMETER", "/jobscraper/techinasia/api_key-dev"
    )
    client = Mock()
    client.get_parameter.return_value = {"Parameter": {"Value": "placeholder"}}
    with patch("boto3.client", return_value=client):
        with pytest.raises(ValueError, match="Populate SSM parameter"):
            scraper_handler({"platform": "techinasia"}, None)


def test_platform_without_credentials_does_not_call_ssm():
    with (
        patch("boto3.client", side_effect=AssertionError("Unexpected SSM call")),
        patch("src.main.main.run_dealls_pipeline", new=AsyncMock(return_value=2)),
    ):
        assert scraper_handler({"platform": "dealls"}, None)["statusCode"] == 200
