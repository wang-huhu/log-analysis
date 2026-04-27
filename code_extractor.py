import re
from typing import Optional


_LINE_NUMBER_RE = re.compile(r"\(?[^()\s]+\.kt:(\d+)\)?")


def extract_line_number_from_frame(frame: str) -> Optional[int]:
    # 从栈帧字符串中提取 Kotlin 文件行号（若缺失/非法则返回 None）
    if not frame:
        return None
    m = _LINE_NUMBER_RE.search(frame)
    if not m:
        return None
    try:
        n = int(m.group(1))
    except ValueError:
        return None
    return n if n > 0 else None


def extract_snippet(source_code: str, line_number: Optional[int], before: int = 20, after: int = 40) -> str:
    # 根据行号从源码中截取上下文片段，并输出带行号文本，供提示词与通知使用
    lines = (source_code or "").splitlines()
    if not lines:
        return ""

    total = len(lines)
    if line_number is None or line_number <= 0:
        start = 1
        end = min(total, 60)
    else:
        ln = min(line_number, total)
        start = max(1, ln - max(0, before))
        end = min(total, ln + max(0, after))

    out = []
    for i in range(start, end + 1):
        out.append(f"{i}: {lines[i - 1]}")
    return "\n".join(out)
