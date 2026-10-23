import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.ai.nlp import AI_DEFAULTS, parse_job


def response(content, finish="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content), finish_reason=finish
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )


@pytest.mark.parametrize(
    "first",
    [
        response(""),
        response('{"role": "cut off', "length"),
        response("[]"),
        response('{"role": "only one field"}'),
    ],
)
def test_retry_recovers_and_counts_both_requests(first):
    client = Mock()
    payload = {
        **AI_DEFAULTS,
        "role": {"value": "Data Engineer", "evidence": "Data Engineer"},
        "company_name": "AI Company",
    }
    client.chat.completions.create.side_effect = [first, response(json.dumps(payload))]
    gate = Mock(return_value=True)
    with (
        patch("src.ai.nlp._get_client", return_value=client),
        patch("src.ai.nlp.time.sleep"),
    ):
        result = parse_job(
            "Data Engineer", "Build pipelines", verbose=False, request_gate=gate
        )
    assert result["parsed_success"]
    assert result["role"] == "Data Engineer"
    assert "job_title" not in result
    assert "company_name" not in result
    assert result["api_usage_total_tokens"] == 60
    assert result["api_attempt"] == 2
    assert gate.call_count == 2
    calls = client.chat.completions.create.call_args_list
    assert calls[0].kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert calls[0].kwargs["max_tokens"] == 4096
    assert calls[1].kwargs["max_tokens"] == (
        8192 if first.choices[0].finish_reason == "length" else 4096
    )


def test_truncated_json_never_counts_as_success_even_if_repairable():
    client = Mock()
    client.chat.completions.create.return_value = response(
        json.dumps(AI_DEFAULTS), "length"
    )
    with (
        patch("src.ai.nlp._get_client", return_value=client),
        patch("src.ai.nlp.time.sleep"),
    ):
        result = parse_job("Engineer", "Build pipelines", verbose=False)
    assert not result["parsed_success"]
    assert result["api_finish_reason"] == "extraction_failed"
    assert result["api_usage_total_tokens"] == 120
    assert result["api_cost_usd"] > 0
    assert result["api_attempt"] == 4
    assert all(result[key] is None for key in AI_DEFAULTS)


def test_empty_source_skips_api_and_has_no_guessed_defaults():
    with patch("src.ai.nlp._get_client") as client:
        result = parse_job("", "", verbose=False)
    client.assert_not_called()
    assert not result["parsed_success"]
    assert result["api_usage_total_tokens"] == 0
    assert all(result[key] is None for key in AI_DEFAULTS)


def test_orchestrator_reports_failure_and_accounts_for_its_usage(caplog):
    import pandas as pd
    from src.silver_layer.orchestrator import parse_jobs_parallel

    with (
        patch(
            "src.silver_layer.orchestrator.parse_job",
            return_value={
                "parsed_success": False,
                "api_usage_total_tokens": 120,
                "api_cost_usd": 0.01,
            },
        ),
        caplog.at_level("INFO"),
    ):
        result = parse_jobs_parallel(pd.DataFrame([{"job_title": "Engineer"}]))
    assert result[0]["_parse_success"] is False
    assert "AI success: 0/1" in caplog.text
    assert "Unresolved/error: 1/1" in caplog.text
    assert "Total tokens: 120" in caplog.text


def test_json_mode_prompt_meets_provider_keyword_requirement():
    from src.ai.nlp import SYSTEM_PROMPT_PARSE

    assert "json" in SYSTEM_PROMPT_PARSE.lower()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_permanent_request_errors_are_not_retried(status, caplog):
    import httpx
    from openai import APIStatusError

    req = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    res = httpx.Response(status, request=req)
    client = Mock()
    client.chat.completions.create.side_effect = APIStatusError(
        "Request rejected", response=res, body={"message": "Invalid request parameter"}
    )
    with (
        patch("src.ai.nlp._get_client", return_value=client),
        patch("src.ai.nlp.time.sleep") as sleep,
    ):
        result = parse_job("Engineer", "Build pipelines.", fields=["seniority"])
    assert client.chat.completions.create.call_count == 1
    sleep.assert_not_called()
    assert result["api_finish_reason"] == f"http_{status}"
    assert result["api_attempt"] == 1
    assert result["seniority"] is None
    assert result["parsed_success"] is False
    assert "Invalid request parameter" in caplog.text


@pytest.mark.parametrize("status", [429, 503])
def test_transient_provider_errors_still_retry(status):
    import httpx
    from openai import APIStatusError

    req = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    client = Mock()
    client.chat.completions.create.side_effect = [
        APIStatusError(
            "Temporary error", response=httpx.Response(status, request=req), body={}
        ),
        response(json.dumps({"seniority": None})),
    ]
    with (
        patch("src.ai.nlp._get_client", return_value=client),
        patch("src.ai.nlp.time.sleep"),
    ):
        result = parse_job("Engineer", "Build pipelines.", fields=["seniority"])
    assert result["parsed_success"] is True
    assert result["api_attempt"] == 2
    assert result["api_usage_total_tokens"] == 30


def test_rejection_diagnostics_redact_credentials(monkeypatch):
    from src.ai.nlp import api_error_message

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-private-key")
    message = api_error_message(
        SimpleNamespace(
            body={
                "message": "Invalid test-private-key Bearer secret-token sk-secret123"
            }
        )
    )
    assert "test-private-key" not in message
    assert "secret-token" not in message
    assert "sk-secret123" not in message
