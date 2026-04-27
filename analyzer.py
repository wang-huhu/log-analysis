import json
from typing import Any, Callable

from models import AppConfig, AnalysisResult


def _parse_analysis_json(text: str) -> AnalysisResult:
    # 将模型输出解析为结构化 AnalysisResult，并对 schema 做严格校验
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"模型返回不是合法 JSON: {e.msg} (pos={e.pos})") from e

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
