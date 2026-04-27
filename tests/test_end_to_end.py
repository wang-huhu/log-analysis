import json

import pipeline
from models import AppConfig


def test_end_to_end(monkeypatch):
    called = {
        "fetch": 0,
        "gitlab": 0,
        "analyze": [],
        "send": [],
        "should_send": [],
        "mark": [],
    }

    def fake_fetch_logs(config, start_time, end_time):
        called["fetch"] += 1
        return {
            "rawResponse": {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-01-01T00:00:00Z",
                                "logmessage": "java.lang.IllegalStateException: A\n\tat com.acme.profile.avatars.AvatarService.update(AvatarService.kt:10)\n\tat com.acme.app.Controller.handle(Controller.kt:1)",
                            }
                        },
                        {
                            "_source": {
                                "@timestamp": "2026-01-01T00:00:01Z",
                                "logmessage": "java.lang.IllegalStateException: B\n\tat com.acme.profile.resources.ResourceService.update(ResourceService.kt:20)\n\tat com.acme.app.Controller.handle(Controller.kt:1)",
                            }
                        },
                    ]
                }
            }
        }

    def fake_get_first_existing_file(**kwargs):
        called["gitlab"] += 1
        return None

    def fake_should_send(fp, now, cooldown_minutes, path):
        called["should_send"].append(fp)
        return True

    def fake_analyze(prompt, config):
        assert "{{" not in prompt
        assert "}}" not in prompt
        assert "${" not in prompt
        called["analyze"].append(prompt)
        return {
            "summary": "ok",
            "root_cause": "rc",
            "evidence": ["e1"],
            "impact": "i",
            "suggestions": ["s1"],
            "risk_level": "low",
            "need_human_check": "no",
        }

    def fake_render_message(group, analysis_result):
        if isinstance(analysis_result, str):
            data = json.loads(analysis_result)
        elif isinstance(analysis_result, dict):
            data = analysis_result
        else:
            data = vars(analysis_result)
        return {"title": group.fingerprint, "analysis": data.get("summary")}

    def fake_send_message(config, message):
        called["send"].append(message)

    def fake_mark_sent(fp, now, path):
        called["mark"].append(fp)

    monkeypatch.setattr(pipeline.log_client, "fetch_logs", fake_fetch_logs)
    monkeypatch.setattr(pipeline.gitlab_client, "get_first_existing_file", fake_get_first_existing_file)
    monkeypatch.setattr(pipeline.state_store, "should_send", fake_should_send)
    monkeypatch.setattr(pipeline.analyzer, "analyze", fake_analyze)
    monkeypatch.setattr(pipeline.feishu_notifier, "render_message", fake_render_message)
    monkeypatch.setattr(pipeline.feishu_notifier, "send_message", fake_send_message)
    monkeypatch.setattr(pipeline.state_store, "mark_sent", fake_mark_sent)

    config = AppConfig(
        log_api_url="http://example.invalid",
        openai_api_key="x",
        openai_base_url="http://example.invalid",
        openai_model="fake",
        feishu_webhook_url="http://example.invalid",
        gitlab_base_url="http://example.invalid",
        gitlab_project_id="1",
        gitlab_private_token="x",
        gitlab_ref="main",
        poll_interval_seconds=1,
        query_window_minutes=5,
        cooldown_minutes=0,
        state_file_path="/dev/null",
        business_package_prefixes=["com.acme"],
    )

    messages = pipeline.run_once(config)

    assert len(messages) == 2
    assert len(called["send"]) == 2

    fp_set = set(called["should_send"])
    assert len(fp_set) == 2

    titles = [m.get("title", "") for m in called["send"]]
    assert titles[0] != titles[1]
