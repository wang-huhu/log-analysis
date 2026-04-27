import os

import pytest

from config import load_config


def test_load_config_requires_required_env(monkeypatch):
    monkeypatch.delenv("LOG_API_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("GITLAB_BASE_URL", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_ID", raising=False)
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_REF", raising=False)

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
    monkeypatch.delenv("POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("QUERY_WINDOW_MINUTES", raising=False)
    monkeypatch.delenv("COOLDOWN_MINUTES", raising=False)
    monkeypatch.delenv("STATE_FILE_PATH", raising=False)
    monkeypatch.delenv("BUSINESS_PACKAGE_PREFIXES", raising=False)

    config = load_config()

    assert config.poll_interval_seconds == 60
    assert config.query_window_minutes == 1
    assert config.cooldown_minutes == 10
    assert config.state_file_path == "state.json"
    assert config.business_package_prefixes == ["org.lumo."]
    assert config.openai_model == "gpt-test"
    assert config.gitlab_ref == "main"
