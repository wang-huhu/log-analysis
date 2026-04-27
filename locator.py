from __future__ import annotations

import os
import re

from models import ErrorGroup


_FRAME_CLASS_RE = re.compile(r"^([A-Za-z_][\w$]*\.)+[A-Za-z_][\w$]*(?=\.)")


def stack_frame_to_class_name(frame: str) -> str | None:
    # 从栈帧中提取类的全限定名（用于反推源码路径）
    if not frame:
        return None

    s = frame.strip()
    if not s:
        return None

    m = _FRAME_CLASS_RE.match(s)
    if not m:
        return None

    class_name = m.group(0).strip(".")
    if not class_name:
        return None

    return class_name


def class_name_to_candidate_paths(class_name: str, roots: list[str]) -> list[str]:
    # 将类名 org.foo.Bar 映射为 roots 下可能的 Kotlin 文件路径 org/foo/Bar.kt
    if not class_name:
        return []
    if not roots:
        return []

    cls = class_name.strip().strip(".")
    if not cls or "/" in cls or "\\" in cls:
        return []

    parts = cls.split(".")
    if len(parts) < 2:
        return []

    file_name = parts[-1] + ".kt"
    rel_dir = os.path.join(*parts[:-1])

    out: list[str] = []
    seen: set[str] = set()

    for root in roots:
        if not root:
            continue
        base = os.path.normpath(root)
        cand = os.path.normpath(os.path.join(base, rel_dir, file_name))
        if cand in seen:
            continue
        seen.add(cand)
        out.append(cand)

    return out


def _iter_business_frames(error_group: ErrorGroup) -> list[str]:
    # 优先使用已算好的 top_business_frames；否则回退到 sample_event 的栈帧集合
    frames: list[str] = []
    if getattr(error_group, "top_business_frames", None):
        frames = list(error_group.top_business_frames or [])
    elif getattr(error_group, "sample_event", None) and getattr(error_group.sample_event, "top_business_frames", None):
        frames = list(error_group.sample_event.top_business_frames or [])
    elif getattr(error_group, "sample_event", None) and getattr(error_group.sample_event, "business_stack_frames", None):
        frames = list(error_group.sample_event.business_stack_frames or [])
    return frames


def locate_candidate_files(error_group: ErrorGroup, roots: list[str]) -> list[str]:
    # 基于业务栈帧推导候选源码文件路径；异常时返回空列表，避免影响主流程
    try:
        frames = _iter_business_frames(error_group)
        out: list[str] = []
        seen: set[str] = set()

        for frame in frames:
            cls = stack_frame_to_class_name(frame)
            if not cls:
                continue
            for p in class_name_to_candidate_paths(cls, roots):
                if p in seen:
                    continue
                seen.add(p)
                out.append(p)

        return out
    except Exception:
        return []
