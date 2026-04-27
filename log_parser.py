from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from models import LogEvent, compute_top_business_frames

# 正则表达式：匹配异常类型（如 java.lang.NullPointerException）
_EXCEPTION_TYPE_RE = re.compile(r"^([A-Za-z_][\w$]*\.)+[A-Za-z_][\w$]*(?:Exception|Error)\b")
# 正则表达式：匹配 "Caused by:" 行，提取异常类型和消息
_CAUSED_BY_RE = re.compile(r"^Caused by:\s*([^:]+)(?::\s*(.*))?$")
# 正则表达式：匹配栈帧行（以 "at " 开头）
_STACK_LINE_RE = re.compile(r"^\s*at\s+(.+)$")
# 新日志块起始行：用于把一个 logmessage 切成多个子块
# 格式示例：10:23:45.678 [http-nio-8080-exec-1] ERROR
_LOG_BLOCK_START_RE = re.compile(
    r"^(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\s+\[(?P<thread>[^\]]+)\]\s+(?P<level>[A-Z]+)\b"
)


@dataclass
class _LogChunk:
    """日志块数据结构，表示一条完整的日志记录（可能包含多行）。"""
    timestamp_text: str | None  # 时间戳文本（如 "10:23:45.678"）
    timestamp_value: datetime | None  # 解析后的时间对象
    thread_name: str | None  # 线程名
    level: str | None  # 日志级别（INFO/ERROR/WARN等）
    lines: list[str]  # 原始行列表

    @property
    def text(self) -> str:
        """将所有行合并为完整文本。"""
        return "\n".join(self.lines)


def _normalize_log_text(text: str) -> str:
    """
    标准化日志文本：将转义的换行符转换为真实换行。

    Args:
        text: 原始日志文本

    Returns:
        标准化后的文本
    """
    if not text:
        return ""
    if "\\n" in text:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    return text


def parse_raw_response(payload: dict[str, Any], package_prefixes: list[str] | None = None) -> list[LogEvent]:
    """
    解析 Elasticsearch 查询响应，提取并结构化日志事件。

    Args:
        payload: ES 查询响应数据
        package_prefixes: 业务包名前缀列表，用于过滤业务栈帧

    Returns:
        结构化的日志事件列表
    """
    # 从嵌套的 ES 响应中提取日志记录列表（兼容 rawResponse.hits.hits 结构）
    hits = payload.get("rawResponse", {}).get("hits", {}).get("hits", [])

    # 业务包名前缀用于筛出业务栈帧，提升指纹与定位的稳定性
    prefixes = package_prefixes or []

    events: list[LogEvent] = []
    for hit in hits:
        # 提取日志源数据
        source = hit.get("_source", {}) or {}
        timestamp = source.get("@timestamp") or source.get("timestamp") or ""
        raw_log = source.get("logmessage") or source.get("message") or ""
        raw_log = _normalize_log_text(str(raw_log))

        # 将一个 logmessage 拆分为多个独立的错误事件（处理多日志块场景）
        for event_log in _split_error_events(raw_log):
            # 从原始日志中提取异常信息、栈帧，并过滤出业务相关栈帧
            stack_frames = extract_stack_frames(event_log)  # 提取所有栈帧
            business_frames = extract_business_frames(stack_frames, prefixes)  # 过滤业务栈帧
            first_business = business_frames[0] if business_frames else None  # 第一个业务栈帧
            top_business_frames = compute_top_business_frames(business_frames)  # 前N个关键业务栈帧

            # 构建结构化日志事件对象
            events.append(
                LogEvent(
                    timestamp=str(timestamp),
                    service_name=source.get("service_name"),
                    namespace=source.get("namespace"),
                    pod_name=source.get("pod_name"),
                    container_name=source.get("container_name"),
                    raw_log=event_log,
                    exception_type=extract_exception_type(event_log),  # 异常类型
                    root_cause_message=extract_root_cause(event_log),  # 根因消息
                    top_stack_lines=stack_frames,  # 完整栈帧列表
                    business_stack_frames=business_frames,  # 业务栈帧列表
                    first_business_frame=first_business,  # 首个业务栈帧
                    top_business_frames=top_business_frames,  # 关键业务栈帧
                )
            )

    return events


def extract_exception_type(logmessage: str) -> str | None:
    """
    从日志第一行提取异常类型。

    Args:
        logmessage: 原始日志内容

    Returns:
        异常类型字符串（如 NullPointerException），未找到返回 None
    """
    if not logmessage:
        return None

    first_line = _strip_log_prefix(logmessage.splitlines()[0].strip())
    m = _EXCEPTION_TYPE_RE.match(first_line)
    if m:
        return m.group(0)

    # 回退：从 "Caused by:" 行提取异常类型
    for line in logmessage.splitlines():
        stripped = _strip_log_prefix(line.strip())
        m = _CAUSED_BY_RE.match(stripped)
        if m:
            exc = (m.group(1) or "").strip()
            return exc or None

    # 再次回退：从文本中查找类全限定名
    exception_from_line = _extract_exception_type_from_text(first_line)
    return exception_from_line


def extract_root_cause(logmessage: str) -> str | None:
    """
    提取异常的根因消息。

    优先从最后一个 "Caused by:" 行提取（最内层异常），否则回退到第一行冒号后的文本。

    Args:
        logmessage: 原始日志内容

    Returns:
        根因消息字符串，未找到返回 None
    """
    if not logmessage:
        return None

    # 遍历所有行，保留最后一个 "Caused by:" 的消息（最内层根因）
    root_cause_message: str | None = None
    for line in logmessage.splitlines():
        stripped = _strip_log_prefix(line.strip())
        m = _CAUSED_BY_RE.match(stripped)
        if m:
            msg = (m.group(2) or "").strip()
            if msg:
                root_cause_message = msg

    if root_cause_message:
        return root_cause_message

    # 回退：从第一行冒号后提取消息
    first_line = _strip_log_prefix(logmessage.splitlines()[0].strip())
    if ":" in first_line:
        msg = first_line.split(":", 1)[1].strip()
        return msg or None
    return None


def extract_stack_frames(logmessage: str) -> list[str]:
    """
    从日志中提取所有栈帧（"at ..." 行）。

    Args:
        logmessage: 原始日志内容

    Returns:
        栈帧字符串列表，保持原始顺序
    """
    if not logmessage:
        return []

    frames: list[str] = []
    for line in logmessage.splitlines():
        m = _STACK_LINE_RE.match(line)
        if not m:
            continue
        frames.append(m.group(1).strip())
    return frames


def extract_business_frames(stack_frames: list[str], package_prefixes: list[str]) -> list[str]:
    """
    从栈帧列表中过滤出业务相关的栈帧。

    仅保留以指定业务包名前缀开头的栈帧，排除第三方库和框架代码，
    避免噪声影响异常指纹生成和问题定位。

    Args:
        stack_frames: 完整栈帧列表
        package_prefixes: 业务包名前缀列表（如 ["com.lumosoft"]）

    Returns:
        业务栈帧列表
    """
    if not stack_frames:
        return []
    if not package_prefixes:
        return []

    prefixes = tuple(package_prefixes)
    return [f for f in stack_frames if f.startswith(prefixes)]


def _split_error_events(raw_log: str) -> list[str]:
    """
    将一个 logmessage 拆分为多个独立的错误事件。

    处理场景：一个 logmessage 可能包含多条 ERROR 日志（时间接近、同线程），
    需要将它们合并为一个完整事件或拆分为独立事件。

    Args:
        raw_log: 原始日志文本

    Returns:
        拆分后的错误事件文本列表
    """
    if not raw_log:
        return []

    # 第1步：将原始文本切分为多个日志块（每个块以时间戳+线程+级别开头）
    chunks = _split_log_chunks(raw_log)
    if not chunks:
        return [raw_log]

    # 第2步：按规则合并相关的 ERROR 日志块
    merged_events: list[list[str]] = []
    current_group: list[_LogChunk] = []

    for chunk in chunks:
        # 非 ERROR 级别的日志块，结束当前分组
        if chunk.level != "ERROR":
            if current_group:
                merged_events.append(_merge_group_lines(current_group))
                current_group = []
            continue

        # 判断是否与上一个 ERROR 块属于同一事件
        if current_group and not _should_merge_chunks(current_group[-1], chunk):
            # 不属于同一事件，保存当前分组并开始新分组
            merged_events.append(_merge_group_lines(current_group))
            current_group = []

        current_group.append(chunk)

    # 处理最后一个分组
    if current_group:
        merged_events.append(_merge_group_lines(current_group))

    if merged_events:
        return ["\n".join(lines) for lines in merged_events]
    return [raw_log]


def _split_log_chunks(raw_log: str) -> list[_LogChunk]:
    """
    将原始日志文本按日志块起始行切分为多个块。

    每个块以 "HH:MM:SS.mmm [thread] LEVEL" 格式开头，后续行属于该块直到下一个块开始。

    Args:
        raw_log: 原始日志文本

    Returns:
        日志块列表
    """
    lines = raw_log.splitlines()
    if not lines:
        return []

    chunks: list[_LogChunk] = []
    current_lines: list[str] = []
    current_match: re.Match[str] | None = None

    for line in lines:
        match = _LOG_BLOCK_START_RE.match(line)
        if match:
            # 遇到新的日志块起始行，保存之前的块
            if current_lines:
                chunks.append(_build_chunk(current_lines, current_match))
            current_lines = [line]
            current_match = match
            continue
        # 非起始行，追加到当前块
        current_lines.append(line)

    # 保存最后一个块
    if current_lines:
        chunks.append(_build_chunk(current_lines, current_match))

    return chunks


def _build_chunk(lines: list[str], match: re.Match[str] | None) -> _LogChunk:
    """
    根据日志块的行和起始行匹配结果，构建 _LogChunk 对象。

    Args:
        lines: 日志块的所有行
        match: 起始行的正则匹配结果

    Returns:
        日志块对象
    """
    time_text = match.group("time") if match else None
    return _LogChunk(
        timestamp_text=time_text,
        timestamp_value=_parse_time_text(time_text),
        thread_name=match.group("thread") if match else None,
        level=match.group("level") if match else None,
        lines=list(lines),
    )


def _parse_time_text(time_text: str | None) -> datetime | None:
    """
    解析时间文本为 datetime 对象。

    Args:
        time_text: 时间文本（格式：HH:MM:SS.mmm）

    Returns:
        datetime 对象，解析失败返回 None
    """
    if not time_text:
        return None
    try:
        return datetime.strptime(time_text, "%H:%M:%S.%f")
    except ValueError:
        return None


def _should_merge_chunks(previous: _LogChunk, current: _LogChunk) -> bool:
    """
    判断两个连续的 ERROR 日志块是否应该合并为同一个错误事件。

    合并条件（满足任一即可）：
    1. 同线程 + 时间接近（默认1.5秒内）+ 根因消息相同
    2. 同线程 + 时间接近 + 异常类型相同
    3. 同线程 + 时间接近 + 前一个块的消息包含在后一个块的根因中（兼容 JDBC/Servlet 双 ERROR 场景）

    Args:
        previous: 前一个日志块
        current: 当前日志块

    Returns:
        是否应该合并
    """
    # 条件1：必须是同一线程
    if previous.thread_name != current.thread_name:
        return False

    # 条件2：时间必须接近（默认阈值1.5秒）
    if not _is_time_close(previous.timestamp_value, current.timestamp_value):
        return False

    # 条件3：根因消息相同 → 合并
    previous_root = extract_root_cause(previous.text)
    current_root = extract_root_cause(current.text)
    if previous_root and current_root and previous_root == current_root:
        return True

    # 条件4：异常类型相同 → 合并
    previous_exception = extract_exception_type(previous.text)
    current_exception = extract_exception_type(current.text)
    if previous_exception and current_exception and previous_exception == current_exception:
        return True

    # 条件5：兼容 JDBC/Servlet 双 ERROR 场景
    # 前一个块只打印底层数据库错误消息，后一个块带完整异常链
    previous_message = _extract_primary_message(previous.text)
    if previous_message and current_root and _messages_match(previous_message, current_root):
        return True

    return False


def _is_time_close(previous: datetime | None, current: datetime | None, threshold_ms: int = 1500) -> bool:
    """
    判断两个时间点是否接近（在阈值范围内）。

    Args:
        previous: 前一个时间
        current: 当前时间
        threshold_ms: 阈值（毫秒），默认1500ms

    Returns:
        是否在阈值范围内
    """
    if previous is None or current is None:
        return True  # 无法解析时间时保守合并
    delta_ms = abs((current - previous).total_seconds() * 1000)
    return delta_ms <= threshold_ms


def _merge_group_lines(chunks: list[_LogChunk]) -> list[str]:
    """
    将一组日志块的所有行合并为一个列表。

    Args:
        chunks: 日志块列表

    Returns:
        合并后的行列表
    """
    merged_lines: list[str] = []
    for chunk in chunks:
        merged_lines.extend(chunk.lines)
    return merged_lines


def _strip_log_prefix(line: str) -> str:
    """
    去除日志行的前缀（时间戳+线程+级别），提取实际消息内容。

    示例：
    输入："10:23:45.678 [http-nio-8080-exec-1] ERROR com.example.Service - NullPointerException"
    输出："NullPointerException"

    Args:
        line: 原始日志行

    Returns:
        去除前缀后的消息内容
    """
    match = _LOG_BLOCK_START_RE.match(line)
    if not match:
        return line

    prefix = match.group(0)
    remainder = line[len(prefix):].lstrip()
    if " - " in remainder:
        return remainder.split(" - ", 1)[1].strip()
    return remainder.strip()


def _extract_exception_type_from_text(text: str) -> str | None:
    """
    从文本中提取异常类型的类全限定名。

    优先匹配常见的 Java/Kotlin 包名前缀（org./com./java.等）。

    Args:
        text: 待提取的文本

    Returns:
        异常类型字符串，未找到返回 None
    """
    for candidate in re.findall(r"([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)+(?:Exception|Error))", text):
        if candidate.startswith(("org.", "com.", "java.", "javax.", "jakarta.", "kotlin.")):
            return candidate
    return None


def _extract_primary_message(logmessage: str) -> str | None:
    """
    提取日志的主要消息部分（第一行冒号后的内容）。

    Args:
        logmessage: 日志文本

    Returns:
        主要消息，未找到返回 None
    """
    if not logmessage:
        return None

    first_line = _strip_log_prefix(logmessage.splitlines()[0].strip())
    return _extract_trailing_message(first_line)


def _extract_trailing_message(text: str) -> str | None:
    """
    提取文本中冒号后的所有内容（处理多个冒号的场景）。

    Args:
        text: 待提取的文本

    Returns:
        冒号后的消息，未找到返回 None
    """
    if not text or ":" not in text:
        return None

    parts = [part.strip() for part in text.split(":") if part.strip()]
    if len(parts) < 2:
        return None

    return ": ".join(parts[1:]).strip() or None


def _messages_match(left: str, right: str) -> bool:
    """
    判断两条消息是否匹配（完全相等或存在包含关系）。

    Args:
        left: 第一条消息
        right: 第二条消息

    Returns:
        是否匹配
    """
    left_normalized = left.strip()
    right_normalized = right.strip()
    if not left_normalized or not right_normalized:
        return False
    return (
            left_normalized == right_normalized
            or left_normalized in right_normalized
            or right_normalized in left_normalized
    )
