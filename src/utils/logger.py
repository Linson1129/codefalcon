"""日志配置"""

import logging
import sys


def setup_logger(level: str = "INFO") -> logging.Logger:
    """配置项目日志"""
    logger = logging.getLogger("codefalcon")
    logger.setLevel(getattr(logging, level.upper()))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
