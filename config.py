import os
from pathlib import Path

from models import AppConfig


REQUIRED_ENV_VARS = [
    # 日志查询接口地址（当前用于请求 ES/Kibana 代理接口）
    "LOG_API_URL",
    # OpenAI 兼容模型的 API Key
    "OPENAI_API_KEY",
    # OpenAI 兼容模型的 Base URL
    "OPENAI_BASE_URL",
    # 使用的模型名称
    "OPENAI_MODEL",
    # 飞书机器人 webhook 地址
    "FEISHU_WEBHOOK_URL",
    # GitLab 服务地址
    "GITLAB_BASE_URL",
    # GitLab 项目 ID
    "GITLAB_PROJECT_ID",
    # GitLab 私有访问 Token
    "GITLAB_PRIVATE_TOKEN",
    # GitLab 代码分支/标签/提交引用
    "GITLAB_REF",
]


def _load_root_dotenv() -> dict[str, str]:
    # 启动时自动读取项目根目录 .env；仅返回候选值，不直接污染进程环境
    env_path = Path.cwd() / ".env"
    if not env_path.is_file():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        loaded[key] = value.strip()
    return loaded


def _get_config_value(key: str, dotenv_values: dict[str, str]) -> str | None:
    return os.getenv(key) or dotenv_values.get(key)


def _get_openai_api_key(dotenv_values: dict[str, str]) -> str | None:
    return _get_config_value("OPENAI_API_KEY", dotenv_values) or _get_config_value("ZHIPU_API_KEY", dotenv_values)


def load_dotenv_values() -> dict[str, str]:
    return _load_root_dotenv()


def load_config() -> AppConfig:
    dotenv_values = _load_root_dotenv()

    # 从环境变量加载运行配置，并对必要项做强校验
    missing = [
        key
        for key in REQUIRED_ENV_VARS
        if not (_get_openai_api_key(dotenv_values) if key == "OPENAI_API_KEY" else _get_config_value(key, dotenv_values))
    ]
    if missing:
        raise ValueError(f"缺少必要环境变量: {', '.join(missing)}")

    # 业务包名前缀用于过滤业务栈帧（用于指纹与定位）
    prefixes = _get_config_value("BUSINESS_PACKAGE_PREFIXES", dotenv_values) or "org.lumo."

    return AppConfig(
        # 日志查询接口地址
        log_api_url=_get_config_value("LOG_API_URL", dotenv_values),
        # OpenAI 兼容模型 API Key；兼容回退到智谱 Key
        openai_api_key=_get_openai_api_key(dotenv_values),
        # OpenAI 兼容模型 Base URL
        openai_base_url=_get_config_value("OPENAI_BASE_URL", dotenv_values),
        # 模型名称
        openai_model=_get_config_value("OPENAI_MODEL", dotenv_values),
        # 飞书 webhook 地址
        feishu_webhook_url=_get_config_value("FEISHU_WEBHOOK_URL", dotenv_values),
        # GitLab 服务地址
        gitlab_base_url=_get_config_value("GITLAB_BASE_URL", dotenv_values),
        # GitLab 项目 ID
        gitlab_project_id=_get_config_value("GITLAB_PROJECT_ID", dotenv_values),
        # GitLab 私有 Token
        gitlab_private_token=_get_config_value("GITLAB_PRIVATE_TOKEN", dotenv_values),
        # GitLab 代码引用（分支/标签/提交）
        gitlab_ref=_get_config_value("GITLAB_REF", dotenv_values),
        # 循环模式每轮执行间隔秒数
        poll_interval_seconds=int(_get_config_value("POLL_INTERVAL_SECONDS", dotenv_values) or "60"),
        # 每次查询日志的时间窗口（分钟）
        query_window_minutes=int(_get_config_value("QUERY_WINDOW_MINUTES", dotenv_values) or "1"),
        # 同一错误指纹重复通知的冷却时间（分钟）
        cooldown_minutes=int(_get_config_value("COOLDOWN_MINUTES", dotenv_values) or "10"),
        # 本地状态文件路径
        state_file_path=_get_config_value("STATE_FILE_PATH", dotenv_values) or "state.json",
        # 业务包名前缀列表（逗号分隔）
        business_package_prefixes=[item.strip() for item in prefixes.split(",") if item.strip()],
    )
