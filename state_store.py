from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


DEFAULT_STATE_PATH = "state.json"


@dataclass
class State:
    last_run_at: str | None
    fingerprints: dict[str, str]


def _empty_state() -> State:
    return State(last_run_at=None, fingerprints={})


def _ensure_state(state: Any) -> State:
    # 将外部读取到的任意结构归一化为 State，尽量容错避免阻塞主流程
    if isinstance(state, State):
        return state
    if isinstance(state, dict):
        last_run_at = state.get("last_run_at")
        fingerprints = state.get("fingerprints")
        if last_run_at is not None and not isinstance(last_run_at, str):
            last_run_at = str(last_run_at)
        if not isinstance(fingerprints, dict):
            fingerprints = {}
        clean_fps: dict[str, str] = {}
        for k, v in fingerprints.items():
            if k is None:
                continue
            if v is None:
                continue
            clean_fps[str(k)] = str(v)
        return State(last_run_at=last_run_at, fingerprints=clean_fps)
    return _empty_state()


def _parse_now(now: str | datetime) -> datetime:
    # 解析 ISO8601 时间（支持 Z 后缀），并确保携带 tzinfo
    if isinstance(now, datetime):
        dt = now
    else:
        s = now.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _dt_to_iso(dt: datetime) -> str:
    # 将时间统一编码为 UTC ISO 字符串并以 Z 结尾，便于比较与持久化
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_state(path: str) -> State:
    # 从本地 JSON 文件加载状态；任何异常都返回空状态，避免影响告警链路
    if not path:
        return _empty_state()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _ensure_state(data)
    except FileNotFoundError:
        return _empty_state()
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return _empty_state()


def save_state(path: str, state: State | dict[str, Any]) -> None:
    # 原子写入 state.json（先写 tmp 再 replace），避免中途崩溃导致文件损坏
    if not path:
        return
    st = _ensure_state(state)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = f"{path}.tmp"
    payload = {"last_run_at": st.last_run_at, "fingerprints": st.fingerprints}
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def should_send(fingerprint: str, now: str | datetime, cooldown_minutes: int, path: str = DEFAULT_STATE_PATH) -> bool:
    # 冷却窗口内同指纹不重复发送；解析失败时默认允许发送
    if cooldown_minutes <= 0:
        return True
    if not fingerprint:
        return True
    st = load_state(path)
    last = st.fingerprints.get(fingerprint)
    if not last:
        return True
    try:
        last_dt = _parse_now(last)
    except Exception:
        return True
    now_dt = _parse_now(now)
    return now_dt - last_dt >= timedelta(minutes=cooldown_minutes)


def mark_sent(fingerprint: str, now: str | datetime, path: str = DEFAULT_STATE_PATH) -> None:
    # 记录指纹最后发送时间与 last_run_at，用于后续冷却判断
    if not fingerprint:
        return
    st = load_state(path)
    now_dt = _parse_now(now)
    st.fingerprints[fingerprint] = _dt_to_iso(now_dt)
    st.last_run_at = _dt_to_iso(now_dt)
    save_state(path, st)
