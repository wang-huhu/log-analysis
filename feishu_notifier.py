import requests

from models import AnalysisResult, ErrorGroup


class FeishuNotifyError(RuntimeError):
    pass


def _build_title(error_group: ErrorGroup) -> str:
    # 优先使用指纹作为标题，便于同类错误聚合识别
    if getattr(error_group, "fingerprint", None):
        return f"错误告警: {error_group.fingerprint}"

    # 回退：从样例事件拼接可读标题
    sample = getattr(error_group, "sample_event", None)
    exception_type = getattr(sample, "exception_type", None) if sample else None
    root_cause = getattr(sample, "root_cause_message", None) if sample else None
    first_business_frame = getattr(sample, "first_business_frame", None) if sample else None

    parts = [p for p in [exception_type, root_cause, first_business_frame] if p]
    suffix = " | ".join(parts) if parts else "未知错误"
    return f"错误告警: {suffix}"


def render_message(error_group: ErrorGroup, analysis_result: AnalysisResult) -> dict:
    # 将错误组 + 模型分析结果渲染为飞书文本消息 payload
    title = _build_title(error_group)

    lines: list[str] = [title]

    if getattr(error_group, "count", None) is not None:
        lines.append(f"出现次数: {error_group.count}")

    first_seen_at = getattr(error_group, "first_seen_at", None)
    last_seen_at = getattr(error_group, "last_seen_at", None)
    if first_seen_at or last_seen_at:
        lines.append(f"时间范围: {first_seen_at or '-'} ~ {last_seen_at or '-'}")

    # 样例事件信息：用于快速定位环境与栈顶
    sample = getattr(error_group, "sample_event", None)
    if sample:
        if getattr(sample, "service_name", None):
            lines.append(f"服务: {sample.service_name}")
        if getattr(sample, "namespace", None) or getattr(sample, "pod_name", None):
            lines.append(f"Pod: {(sample.namespace or '-')} / {(sample.pod_name or '-')}")
        if getattr(sample, "exception_type", None):
            lines.append(f"异常: {sample.exception_type}")
        if getattr(sample, "root_cause_message", None):
            lines.append(f"RootCause: {sample.root_cause_message}")

        top_stack_lines = getattr(sample, "top_stack_lines", None)
        if top_stack_lines:
            lines.append("\n".join(["\n栈顶(Top):", *top_stack_lines[:5]]))

    # 模型分析结构化输出
    lines.extend(
        [
            "\n分析:",
            f"- 总结: {analysis_result.summary}",
            f"- 根因: {analysis_result.root_cause}",
            f"- 影响: {analysis_result.impact}",
            f"- 风险: {analysis_result.risk_level}",
            f"- 需人工确认: {analysis_result.need_human_check}",
        ]
    )

    if getattr(analysis_result, "evidence", None):
        lines.append("\n依据:")
        for item in analysis_result.evidence[:10]:
            lines.append(f"- {item}")

    if getattr(analysis_result, "suggestions", None):
        lines.append("\n建议:")
        for item in analysis_result.suggestions[:10]:
            lines.append(f"- {item}")

    text = "\n".join(lines).strip()

    return {"msg_type": "text", "content": {"text": text}}


def send_message(config, message):
    # 通过飞书机器人 webhook 发送消息，检查 HTTP 与业务 code
    url = getattr(config, "feishu_webhook_url", None)
    if not url:
        raise FeishuNotifyError("缺少 feishu_webhook_url")

    payload = message if isinstance(message, dict) else {"msg_type": "text", "content": {"text": str(message)}}

    try:
        resp = requests.post(url, json=payload, timeout=10)
    except requests.RequestException as e:
        raise FeishuNotifyError(f"飞书发送失败: {e}") from e

    if resp.status_code != 200:
        raise FeishuNotifyError(f"飞书发送失败: HTTP {resp.status_code} {getattr(resp, 'text', '')}")

    try:
        data = resp.json()
    except ValueError:
        data = None

    if isinstance(data, dict):
        code = data.get("code")
        if code not in (0, None):
            msg = data.get("msg") or data.get("message") or "未知错误"
            raise FeishuNotifyError(f"飞书发送失败: code={code} msg={msg}")

    return resp
