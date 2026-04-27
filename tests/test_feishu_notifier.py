from dataclasses import dataclass

import pytest

from feishu_notifier import render_message, send_message
from models import AnalysisResult, ErrorGroup, LogEvent


@dataclass
class DummyConfig:
    feishu_webhook_url: str = "https://example.invalid/webhook"


def _mk_group(fingerprint: str) -> ErrorGroup:
    ev = LogEvent(
        timestamp="2026-01-01T00:00:00Z",
        service_name="svc",
        namespace="ns",
        pod_name="pod",
        container_name=None,
        raw_log="raw",
        exception_type="java.lang.RuntimeException",
        root_cause_message="boom",
        top_stack_lines=["a", "b", "c"],
        business_stack_frames=["org.lumo.Foo.bar(Foo.kt:1)"],
        first_business_frame="org.lumo.Foo.bar(Foo.kt:1)",
        top_business_frames=["org.lumo.Foo.bar(Foo.kt:1)"],
    )
    return ErrorGroup(
        fingerprint=fingerprint,
        count=2,
        first_seen_at="2026-01-01T00:00:00Z",
        last_seen_at="2026-01-01T00:01:00Z",
        sample_event=ev,
        all_related_events=[ev],
    )


def _mk_analysis() -> AnalysisResult:
    return AnalysisResult(
        summary="s",
        root_cause="r",
        evidence=["e1"],
        impact="i",
        suggestions=["s1"],
        risk_level="high",
        need_human_check="no",
    )


def test_render_message_titles_differ_by_fingerprint():
    a = render_message(_mk_group("fp-a"), _mk_analysis())
    b = render_message(_mk_group("fp-b"), _mk_analysis())

    assert a["msg_type"] == "text"
    assert "content" in a and "text" in a["content"]
    assert a["content"]["text"].splitlines()[0] != b["content"]["text"].splitlines()[0]


def test_send_message_posts_expected_payload(monkeypatch):
    seen = {}

    class DummyResp:
        status_code = 200

        def json(self):
            return {"code": 0}

        text = "ok"

    def fake_post(url, json, timeout):
        seen["url"] = url
        seen["json"] = json
        seen["timeout"] = timeout
        return DummyResp()

    monkeypatch.setattr("feishu_notifier.requests.post", fake_post)

    cfg = DummyConfig()
    msg = {"msg_type": "text", "content": {"text": "hi"}}
    send_message(cfg, msg)

    assert seen["url"] == cfg.feishu_webhook_url
    assert seen["json"] == msg
    assert seen["timeout"] == 10


def test_send_message_raises_on_http_error(monkeypatch):
    class DummyResp:
        status_code = 400
        text = "bad"

        def json(self):
            return {"code": 19001, "msg": "invalid"}

    def fake_post(url, json, timeout):
        return DummyResp()

    monkeypatch.setattr("feishu_notifier.requests.post", fake_post)

    with pytest.raises(Exception):
        send_message(DummyConfig(), {"msg_type": "text", "content": {"text": "hi"}})
