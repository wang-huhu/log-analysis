from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
from typing import Callable, Tuple


def build_time_window(now: datetime, minutes: int) -> Tuple[datetime, datetime]:
    # 构建 datetime 形式的时间窗口（用于需要 datetime 的场景）
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    end_time = now
    start_time = now - timedelta(minutes=minutes)
    return start_time, end_time


def run_forever(run_once: Callable[[], None], interval_seconds: int) -> None:
    # 循环执行 run_once，并按 interval_seconds 休眠
    while True:
        run_once()
        if interval_seconds > 0:
            time.sleep(interval_seconds)
