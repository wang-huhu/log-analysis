import os

from config import load_config
from pipeline import run_once
from scheduler import run_forever


if __name__ == '__main__':
    # 程序入口：读取配置并按 RUN_MODE 选择单次/循环运行
    config = load_config()

    mode = os.getenv('RUN_MODE', 'once').strip().lower()
    interval_seconds = int(os.getenv('INTERVAL_SECONDS', '60'))

    if mode in {'loop', 'forever'}:
        run_forever(lambda: run_once(config), interval_seconds)
    else:
        run_once(config)
