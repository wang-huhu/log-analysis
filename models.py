from dataclasses import dataclass
from typing import List


TOP_BUSINESS_FRAMES_DEFAULT_N = 3


def compute_top_business_frames(frames: list[str], n: int = TOP_BUSINESS_FRAMES_DEFAULT_N) -> list[str]:
    """从业务栈帧中选取前 N 条（按栈顺序），用于后续多文件源码定位与截取。"""
    if not frames or n <= 0:
        return []
    return list(frames[:n])


@dataclass
class AppConfig:
    """应用运行所需配置（主要来自环境变量）。"""

    # 日志接口 URL
    log_api_url: str

    # OpenAI 兼容接口的 API Key
    openai_api_key: str
    # OpenAI 兼容接口 Base URL
    openai_base_url: str
    # 模型名称
    openai_model: str

    # 飞书机器人 webhook URL
    feishu_webhook_url: str

    # GitLab Base URL
    gitlab_base_url: str
    # GitLab project_id
    gitlab_project_id: str
    # GitLab private token
    gitlab_private_token: str
    # GitLab ref（branch/tag/commit）
    gitlab_ref: str

    # 循环模式每轮间隔秒数
    poll_interval_seconds: int
    # 每轮查询的时间窗口（分钟）
    query_window_minutes: int
    # 同指纹冷却时间（分钟）
    cooldown_minutes: int

    # 本地状态文件路径
    state_file_path: str
    # 业务包名前缀列表，用于过滤业务栈帧
    business_package_prefixes: List[str]


@dataclass
class LogEvent:
    """从日志接口解析出的单条日志事件（包含异常与栈信息）。"""

    # 日志时间戳（字符串，保持原始格式）
    timestamp: str
    # 服务名/应用名（如果原始日志提供）
    service_name: str | None
    # K8s namespace（如果原始日志提供）
    namespace: str | None
    # K8s pod 名称（如果原始日志提供）
    pod_name: str | None
    # K8s container 名称（如果原始日志提供）
    container_name: str | None

    # 原始 logmessage 文本
    raw_log: str

    # 异常类型（例如 java.lang.NullPointerException）
    exception_type: str | None
    # root cause message（若能解析）
    root_cause_message: str | None

    # 栈追踪前若干行（用于摘要展示）
    top_stack_lines: list[str]
    # 按业务包名前缀过滤后的栈帧列表
    business_stack_frames: list[str]
    # 第一条业务栈帧（用于指纹生成）
    first_business_frame: str | None
    # 当没有业务栈帧时，退化使用的首条可用框架栈帧
    fallback_frame: str | None
    # 按顺序取前 N 条业务栈帧（用于源码定位）
    top_business_frames: list[str]


@dataclass
class ErrorGroup:
    """按指纹聚合后的错误组，作为通知与源码定位的最小处理单元。"""

    # 错误指纹（严格由异常类型+root cause+第一业务栈帧组成）
    fingerprint: str
    # 该指纹在时间窗口内出现次数
    count: int
    # 首次出现时间戳
    first_seen_at: str
    # 最后出现时间戳
    last_seen_at: str

    # 用于展示/定位的样例事件
    sample_event: LogEvent
    # 该组内全部相关事件
    all_related_events: list[LogEvent]

    # 用于源码定位的前 N 条业务栈帧（可选覆盖）
    top_business_frames: list[str] | None = None
    # 与 top_business_frames 对应的源码片段列表
    code_snippets: list["CodeSnippet"] | None = None


@dataclass
class CodeSnippet:
    """从仓库源码中截取的片段（带文件路径）。"""

    # 仓库内文件路径
    file_path: str
    # 截取的源码内容（带行号）
    content: str


@dataclass
class AnalysisResult:
    """LLM 分析输出的结构化结果（用于拼装通知消息）。"""

    # 总结
    summary: str
    # 根因判断
    root_cause: str
    # 依据要点列表
    evidence: list[str]
    # 影响评估
    impact: str
    # 修复/缓解建议列表
    suggestions: list[str]
    # 风险等级
    risk_level: str
    # 是否需要人工确认及原因
    need_human_check: str
