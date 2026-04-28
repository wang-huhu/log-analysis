import os
from pathlib import Path

import pytest

from config import load_config


@pytest.fixture(autouse=True)
def clear_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    keys = [
        "LOG_API_URL",
        "OPENAI_API_KEY",
        "ZHIPU_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "FEISHU_WEBHOOK_URL",
        "GITLAB_BASE_URL",
        "GITLAB_PROJECT_ID",
        "GITLAB_PRIVATE_TOKEN",
        "GITLAB_REF",
        "POLL_INTERVAL_SECONDS",
        "QUERY_WINDOW_MINUTES",
        "COOLDOWN_MINUTES",
        "STATE_FILE_PATH",
        "BUSINESS_PACKAGE_PREFIXES",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_load_config_requires_required_env(monkeypatch):
    with pytest.raises(ValueError):
        load_config()


def test_load_config_uses_defaults(monkeypatch):
    monkeypatch.setenv("LOG_API_URL", "https://example.com/logs")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.com/feishu")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "123")
    monkeypatch.setenv("GITLAB_PRIVATE_TOKEN", "gitlab-token")
    monkeypatch.setenv("GITLAB_REF", "main")

    config = load_config()

    assert config.poll_interval_seconds == 60
    assert config.query_window_minutes == 1
    assert config.cooldown_minutes == 10
    assert config.state_file_path == "state.json"
    assert config.business_package_prefixes == ["org.lumo."]
    assert config.openai_model == "gpt-test"
    assert config.gitlab_ref == "main"


def test_load_config_uses_zhipu_api_key_as_openai_fallback(monkeypatch):
    monkeypatch.setenv("LOG_API_URL", "https://example.com/logs")
    monkeypatch.setenv("ZHIPU_API_KEY", "zhipu-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "glm-test")
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.com/feishu")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "123")
    monkeypatch.setenv("GITLAB_PRIVATE_TOKEN", "gitlab-token")
    monkeypatch.setenv("GITLAB_REF", "main")

    config = load_config()

    assert config.openai_api_key == "zhipu-key"


def test_load_config_reads_root_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LOG_API_URL=https://example.com/logs",
                "OPENAI_API_KEY=test-key",
                "OPENAI_BASE_URL=https://example.com/v1",
                "OPENAI_MODEL=gpt-test",
                "FEISHU_WEBHOOK_URL=https://example.com/feishu",
                "GITLAB_BASE_URL=https://gitlab.example.com",
                "GITLAB_PROJECT_ID=123",
                "GITLAB_PRIVATE_TOKEN=gitlab-token",
                "GITLAB_REF=main",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config()

    assert config.log_api_url == "https://example.com/logs"
    assert config.openai_api_key == "test-key"
