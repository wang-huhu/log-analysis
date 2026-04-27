from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import analyzer
import code_extractor
import feishu_notifier
import fingerprinter
import gitlab_client
import locator
import log_client
import log_parser
import prompt_builder
import state_store
from models import AppConfig, CodeSnippet, ErrorGroup


def _iso_utc(dt: datetime) -> str:
    # 统一将 datetime 编码为 UTC ISO 字符串（Z 后缀）
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_time_window(now: datetime, minutes: int) -> tuple[str, str]:
    # 构建查询时间窗口（以当前时间为 end，向前 minutes 为 start）
    if minutes <= 0:
        minutes = 1
    end_dt = now
    start_dt = now - timedelta(minutes=minutes)
    return _iso_utc(start_dt), _iso_utc(end_dt)


def _candidate_roots() -> list[str]:
    # 业务 Kotlin 代码可能存在的根目录（用于从类名反推文件路径）
    return [
        "src/main/kotlin",
        "app/src/main/kotlin",
    ]


def _decode_gitlab_file_content(file_json: dict) -> str:
    # 解码 GitLab repository/files API 的 content（常见为 base64）
    import base64

    content = file_json.get("content")
    encoding = file_json.get("encoding")
    if not isinstance(content, str) or not content:
        return ""
    if encoding == "base64":
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            return ""
    return content


def _build_group_prompt(config: AppConfig, group: ErrorGroup) -> str:
    # 为单个错误组构建模型 prompt：模板 + 栈信息 +（可选）源码片段
    template = prompt_builder.load_prompt_template("prompt.md")

    top_frames = (
        list(group.top_business_frames)
        if group.top_business_frames
        else list(getattr(group.sample_event, "top_business_frames", []) or [])
    )

    # 基于业务栈帧推导候选源码路径，并从 GitLab 拉取第一个存在的文件
    candidate_paths = locator.locate_candidate_files(group, _candidate_roots())

    snippets: list[CodeSnippet] = []
    if candidate_paths:
        file_json = gitlab_client.get_first_existing_file(
            candidate_paths=candidate_paths,
            project_id=config.gitlab_project_id,
            ref=config.gitlab_ref,
            token=config.gitlab_private_token,
            base_url=config.gitlab_base_url,
        )
        if file_json:
            source = _decode_gitlab_file_content(file_json)
            file_path = str(file_json.get("file_path") or file_json.get("path") or "")
            # 对 top_frames 逐个尝试提取行号并截取片段，形成多 snippet 上下文
            for frame in top_frames[: max(1, len(top_frames))]:
                ln = code_extractor.extract_line_number_from_frame(frame)
                snippet_text = code_extractor.extract_snippet(source, ln)
                if snippet_text.strip():
                    snippets.append(CodeSnippet(file_path=file_path or "", content=snippet_text))

    # 兼容旧逻辑：聚合 snippet 文本（当前 prompt_builder 支持直接传 snippets）
    if not snippets:
        code_context = ""
    else:
        parts: list[str] = []
        for i, snip in enumerate(snippets[:10]):
            parts.append(f"snippet[{i}] {snip.file_path}\n{snip.content}".rstrip())
        code_context = "\n\n".join(parts).strip()

    prompt = prompt_builder.build_prompt(group, snippets, template)
    return prompt


def run_once(config: AppConfig) -> list[dict]:
    # 单次运行主链路：拉日志 -> 解析 -> 聚合 -> 冷却判断 -> 拉源码 -> LLM 分析 -> 飞书通知 -> 记录状态
    now = datetime.now(timezone.utc)
    start_time, end_time = _build_time_window(now, getattr(config, "query_window_minutes", 1))

    payload = log_client.fetch_logs(config, start_time=start_time, end_time=end_time)
    events = log_parser.parse_raw_response(payload, package_prefixes=getattr(config, "business_package_prefixes", []))
    groups = fingerprinter.group_events(events)

    state_path = getattr(config, "state_file_path", state_store.DEFAULT_STATE_PATH)
    _ = state_store.load_state(state_path)

    messages: list[dict] = []

    for group in groups:
        fp = getattr(group, "fingerprint", "") or ""
        # 冷却窗口：同指纹在 cooldown_minutes 内不重复通知
        try:
            if not state_store.should_send(fp, now, getattr(config, "cooldown_minutes", 0), path=state_path):
                continue
        except Exception:
            pass

        try:
            # 确保 top_business_frames 存在（用于定位与多 frame snippet 提取）
            group_to_process = group
            if getattr(group_to_process, "top_business_frames", None) is None:
                top_frames = getattr(group.sample_event, "top_business_frames", None)
                if top_frames is not None:
                    group_to_process = replace(group_to_process, top_business_frames=list(top_frames))

            prompt = _build_group_prompt(config, group_to_process)

            # 模型调用失败不阻塞整体（该错误组跳过通知）
            analysis_result = None
            try:
                analysis_result = analyzer.analyze(prompt, config)
            except Exception:
                analysis_result = None

            if analysis_result is not None:
                message = feishu_notifier.render_message(group_to_process, analysis_result)
                try:
                    feishu_notifier.send_message(config, message)
                except Exception:
                    pass
                messages.append(message)

        except Exception:
            pass

        # 无论是否发送成功，都尝试落盘标记，避免同一窗口重复刷屏
        try:
            state_store.mark_sent(fp, now, path=state_path)
        except Exception:
            pass

    return messages
