import os

from config import load_config, load_dotenv_values
from pipeline import run_once
from scheduler import run_forever


if __name__ == '__main__':
    # 程序入口：读取配置并按 RUN_MODE 选择单次/循环运行
    dotenv_values = load_dotenv_values()
    config = load_config()

    mode = (os.getenv('RUN_MODE') or dotenv_values.get('RUN_MODE') or 'once').strip().lower()
    interval_seconds = int(os.getenv('INTERVAL_SECONDS') or dotenv_values.get('INTERVAL_SECONDS') or '60')

    if mode in {'loop', 'forever'}:
        run_forever(lambda: run_once(config), interval_seconds)
    else:
        run_once(config)
