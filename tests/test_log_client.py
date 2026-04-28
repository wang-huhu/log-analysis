from unittest.mock import Mock, patch

import pytest
import requests

from log_client import _build_payload, fetch_logs
from models import AppConfig


@pytest.fixture
def sample_config():
    return AppConfig(
        log_api_url="https://example.com/logs",
        openai_api_key="test-key",
        openai_base_url="https://example.com/v1",
        openai_model="gpt-test",
        feishu_webhook_url="https://example.com/feishu",
        gitlab_base_url="https://gitlab.example.com",
        gitlab_project_id="123",
        gitlab_private_token="gitlab-token",
        gitlab_ref="main",
        poll_interval_seconds=60,
        query_window_minutes=1,
        cooldown_minutes=10,
        state_file_path="state.json",
        business_package_prefixes=["org.lumo."],
    )


def test_build_payload_matches_expected_top_level_shape():
    payload = _build_payload("2026-04-21T08:00:00Z", "2026-04-21T08:01:00Z")

    assert payload["serverStrategy"] == "es"
    assert payload["params"]["rest_total_hits_as_int"] is True
    assert payload["params"]["ignore_unavailable"] is True
    assert payload["params"]["ignore_throttled"] is True
    assert payload["params"]["timeout"] == "30000ms"
    assert payload["params"]["body"]["query"]["bool"]["filter"][1]["range"]["@timestamp"] == {
        "gte": "2026-04-21T08:00:00Z",
        "lte": "2026-04-21T08:01:00Z",
        "format": "strict_date_optional_time",
    }


def test_fetch_logs_returns_json(sample_config, capsys):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"ok": True}

    with patch("log_client.requests.post", return_value=response):
        result = fetch_logs(sample_config, "2026-04-21T08:00:00Z", "2026-04-21T08:01:00Z")

    captured = capsys.readouterr()

    assert result == {"ok": True}
    assert "响应状态码: 200" in captured.out
    assert "响应顶层 keys: ['ok']" in captured.out
    assert response.json.call_count == 1


def test_fetch_logs_raises_on_non_200(sample_config):
    response = Mock()
    response.status_code = 500
    response.text = "server error"

    with patch("log_client.requests.post", return_value=response):
        with pytest.raises(RuntimeError, match="server error"):
            fetch_logs(sample_config, "2026-04-21T08:00:00Z", "2026-04-21T08:01:00Z")


def test_fetch_logs_truncates_response_text_on_non_200(sample_config):
    response = Mock()
    response.status_code = 500
    response.text = "x" * 500

    with patch("log_client.requests.post", return_value=response):
        with pytest.raises(RuntimeError) as exc_info:
            fetch_logs(sample_config, "2026-04-21T08:00:00Z", "2026-04-21T08:01:00Z")

    assert len(str(exc_info.value)) < 300
    assert "..." in str(exc_info.value)


def test_fetch_logs_raises_on_timeout(sample_config):
    with patch("log_client.requests.post", side_effect=requests.Timeout):
        with pytest.raises(RuntimeError):
            fetch_logs(sample_config, "2026-04-21T08:00:00Z", "2026-04-21T08:01:00Z")
