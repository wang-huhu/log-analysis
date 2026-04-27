import os

from models import AppConfig


REQUIRED_ENV_VARS = [
    "LOG_API_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "FEISHU_WEBHOOK_URL",
    "GITLAB_BASE_URL",
    "GITLAB_PROJECT_ID",
    "GITLAB_PRIVATE_TOKEN",
    "GITLAB_REF",
]


def load_config() -> AppConfig:
    # 从环境变量加载运行配置，并对必要项做强校验
    missing = [key for key in REQUIRED_ENV_VARS if not os.getenv(key)]
    if missing:
        raise ValueError(f"缺少必要环境变量: {', '.join(missing)}")

    # 业务包名前缀用于过滤业务栈帧（用于指纹与定位）
    prefixes = os.getenv("BUSINESS_PACKAGE_PREFIXES", "org.lumo.")

    return AppConfig(
        log_api_url=os.environ["LOG_API_URL"],
        openai_api_key=os.environ["OPENAI_API_KEY"],
        openai_base_url=os.environ["OPENAI_BASE_URL"],
        openai_model=os.environ["OPENAI_MODEL"],
        feishu_webhook_url=os.environ["FEISHU_WEBHOOK_URL"],
        gitlab_base_url=os.environ["GITLAB_BASE_URL"],
        gitlab_project_id=os.environ["GITLAB_PROJECT_ID"],
        gitlab_private_token=os.environ["GITLAB_PRIVATE_TOKEN"],
        gitlab_ref=os.environ["GITLAB_REF"],
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
        query_window_minutes=int(os.getenv("QUERY_WINDOW_MINUTES", "1")),
        cooldown_minutes=int(os.getenv("COOLDOWN_MINUTES", "10")),
        state_file_path=os.getenv("STATE_FILE_PATH", "state.json"),
        business_package_prefixes=[item.strip() for item in prefixes.split(",") if item.strip()],
    )
