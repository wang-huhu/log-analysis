from __future__ import annotations

from pathlib import Path
from typing import Any
import re


_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def load_prompt_template(path: str | Path) -> str:
    # 读取提示词模板文件（UTF-8）
    return Path(path).read_text(encoding="utf-8")


def _normalize_code_snippet(code_snippet: Any) -> tuple[str, str]:
    # 将多种形态的 code_snippet 归一化为 (file_path, text)
    if code_snippet is None:
        return "", ""

    if isinstance(code_snippet, str):
        return "", code_snippet

    if isinstance(code_snippet, (list, tuple)):
        parts: list[str] = []
        file_path = ""
        for i, item in enumerate(code_snippet):
            if item is None:
                continue
            if isinstance(item, str):
                parts.append(item)
                continue
            item_file_path = getattr(item, "file_path", "") or ""
            item_content = getattr(item, "content", "")
            if not file_path and item_file_path:
                file_path = item_file_path
            if item_content:
                parts.append(f"# snippet[{i}] {item_file_path}\n{item_content}".rstrip())
        return file_path, "\n\n".join([p for p in parts if p]).strip()

    file_path = getattr(code_snippet, "file_path", "") or ""
    content = getattr(code_snippet, "content", "")
    if isinstance(content, str):
        return file_path, content

    return file_path, str(code_snippet)


def build_prompt(error_group: Any, code_snippet: Any, template: str) -> str:
    # 将错误信息与源码上下文渲染进模板，生成最终喂给模型的 prompt
    sample_event = getattr(error_group, "sample_event", None)
    error_summary = getattr(sample_event, "exception_type", None) or ""

    stack_lines = getattr(sample_event, "top_stack_lines", None) or []
    if not isinstance(stack_lines, list):
        stack_lines = [str(stack_lines)]
    stack_trace_top_5_lines = "\n".join([str(x) for x in stack_lines[:5]])

    root_cause_message = getattr(sample_event, "root_cause_message", None) or ""

    file_path_from_snippet, code_snippet_text = _normalize_code_snippet(code_snippet)
    file_path = file_path_from_snippet or ""

    values: dict[str, str] = {
        "error_summary": str(error_summary),
        "stack_trace_top_5_lines": str(stack_trace_top_5_lines),
        "root_cause_message": str(root_cause_message),
        "file_path": str(file_path),
        "code_snippet": str(code_snippet_text),
    }

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, "")

    # 先替换 {{var}}，再兼容替换 ${var}（旧模板写法），最后清理残留占位符
    rendered = _VAR_PATTERN.sub(repl, template)
    rendered = rendered.replace("${error_summary}", values["error_summary"])
    rendered = rendered.replace("${stack_trace_top_5_lines}", values["stack_trace_top_5_lines"])
    rendered = rendered.replace("${root_cause_message}", values["root_cause_message"])
    rendered = rendered.replace("${file_path}", values["file_path"])
    rendered = rendered.replace("${code_snippet}", values["code_snippet"])

    rendered = _VAR_PATTERN.sub("", rendered)
    rendered = re.sub(r"\$\{[^}]+\}", "", rendered)
    return rendered
