import json
import re
from typing import Any, Callable

from models import AppConfig, AnalysisResult


_FENCED_JSON_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _try_load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_fenced_content(text: str) -> str | None:
    stripped = text.strip()
    match = _FENCED_JSON_PATTERN.match(stripped)
    if not match:
        return None
    return match.group(1).strip()


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return None
    return text[start : end + 1]


def _load_analysis_payload(text: str) -> Any:
    payload = _try_load_json(text)
    if payload is not None:
        return payload

    fenced_content = _extract_fenced_content(text)
    if fenced_content is not None:
        payload = _try_load_json(fenced_content)
        if payload is not None:
            return payload

    extracted_object = _extract_first_json_object(text)
    if extracted_object is not None:
        payload = _try_load_json(extracted_object)
        if payload is not None:
            return payload

    raise ValueError("模型返回不是合法 JSON")


def _parse_analysis_json(text: str) -> AnalysisResult:
    # 将模型输出解析为结构化 AnalysisResult，并对 schema 做严格校验
    preview = text[:1000]
    suffix = "...（已截断）" if len(text) > 1000 else ""
    print(f"模型原始返回内容（前 1000 字符）：\n{preview}{suffix}")
    try:
        payload = _load_analysis_payload(text)
    except ValueError as e:
        raise ValueError(str(e)) from e

    if not isinstance(payload, dict):
        raise ValueError("模型返回 JSON 必须是 object")

    required = [
        "summary",
        "root_cause",
        "evidence",
        "impact",
        "suggestions",
        "risk_level",
        "need_human_check",
    ]
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"模型返回 JSON 缺少字段: {', '.join(missing)}")

    evidence = payload["evidence"]
    suggestions = payload["suggestions"]
    if not isinstance(evidence, list) or not all(isinstance(x, str) for x in evidence):
        raise ValueError("模型返回 JSON 字段 evidence 必须是 string 列表")
    if not isinstance(suggestions, list) or not all(isinstance(x, str) for x in suggestions):
        raise ValueError("模型返回 JSON 字段 suggestions 必须是 string 列表")

    return AnalysisResult(
        summary=str(payload["summary"]),
        root_cause=str(payload["root_cause"]),
        evidence=evidence,
        impact=str(payload["impact"]),
        suggestions=suggestions,
        risk_level=str(payload["risk_level"]),
        need_human_check=str(payload["need_human_check"]),
    )


def _call_llm_via_langchain(prompt: str, config: AppConfig) -> str:
    # 通过 langchain_openai 调用 OpenAI 兼容接口，要求仅返回 JSON
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as e:
        raise ImportError("缺少依赖: langchain-openai / langchain-core") from e

    llm = ChatOpenAI(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url,
        model=config.openai_model,
        temperature=0,
    )

    system = (
        "你是日志诊断助手。你必须只输出一个 JSON object，不能输出任何额外文本。"
        "JSON schema: {summary: string, root_cause: string, evidence: string[], impact: string, "
        "suggestions: string[], risk_level: string, need_human_check: string}."
    )

    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    content = getattr(resp, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("模型返回为空或不包含文本 content")
    return content.strip()


def analyze(
    prompt: str,
    config: AppConfig,
    *,
    llm_call: Callable[[str, AppConfig], str] | None = None,
) -> AnalysisResult:
    # 允许注入 llm_call 便于测试/离线运行
    call = llm_call or _call_llm_via_langchain
    text = call(prompt, config)
    return _parse_analysis_json(text)
