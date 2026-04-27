from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace

from models import ErrorGroup, LogEvent


def _norm(s: str | None) -> str:
    """标准化字符串：去除首尾空格，None 转为空字符串。"""
    return (s or "").strip()


def build_fingerprint(event: LogEvent) -> str:
    """
    构建异常事件的唯一指纹，用于聚合和去重。

    指纹由三部分组成：
    - 异常类型（如 NullPointerException）
    - 根因消息（异常的具体描述）
    - 第一条业务栈帧（定位到具体业务代码位置）

    Args:
        event: 结构化的日志事件

    Returns:
        指纹字符串，格式为 "异常类型|根因消息|业务栈帧"
    """
    exc = _norm(event.exception_type) or "<none>"  # 异常类型，缺失时用 <none> 占位
    cause = _norm(event.root_cause_message) or "<none>"  # 根因消息
    frame = _norm(event.first_business_frame) or "<none>"  # 首个业务栈帧
    return f"{exc}|{cause}|{frame}"


def group_events(events: list[LogEvent]) -> list[ErrorGroup]:
    """
    按指纹聚合日志事件，生成错误分组。

    相同指纹的事件会被归为一组（表示同一类异常），保留：
    - 首次和最后出现时间
    - 发生次数
    - 样例事件（用于后续分析和通知）
    - 所有相关事件列表

    Args:
        events: 日志事件列表

    Returns:
        错误分组列表，按首次出现顺序排列
    """
    # 使用 OrderedDict 保持插入顺序，key 为指纹，value 为该指纹下的所有事件
    groups: OrderedDict[str, list[LogEvent]] = OrderedDict()

    # 遍历所有事件，按指纹分组
    for ev in events:
        fp = build_fingerprint(ev)
        groups.setdefault(fp, []).append(ev)

    # 将分组转换为 ErrorGroup 对象列表
    out: list[ErrorGroup] = []
    for fp, evs in groups.items():
        if not evs:
            continue

        # 找出最早和最晚的事件（基于时间戳字符串比较）
        first_seen = min(evs, key=lambda e: _norm(e.timestamp))
        last_seen = max(evs, key=lambda e: _norm(e.timestamp))
        sample = first_seen  # 使用最早的事件作为样例

        out.append(
            ErrorGroup(
                fingerprint=fp,  # 指纹标识
                count=len(evs),  # 该异常出现的次数
                first_seen_at=_norm(first_seen.timestamp),  # 首次出现时间
                last_seen_at=_norm(last_seen.timestamp),  # 最后出现时间
                sample_event=replace(sample),  # 样例事件（深拷贝避免修改原对象）
                all_related_events=list(evs),  # 所有相关事件
            )
        )

    return out
