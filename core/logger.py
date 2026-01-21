"""
OpenAver 統一日誌模組

使用方式：
    from core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("訊息")
    logger.debug("除錯訊息")
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 全域設定
_initialized = False
_log_dir = None


def setup_logging(log_dir: Path = None, console_level: int = logging.INFO):
    """
    初始化日誌系統（由 standalone.py 呼叫一次）

    Args:
        log_dir: 日誌目錄，預設 ~/OpenAver/logs/
        console_level: Console 輸出等級，Debug 模式可設為 logging.DEBUG
    """
    global _initialized, _log_dir

    if _initialized:
        return

    # 日誌目錄
    if log_dir is None:
        log_dir = Path.home() / "OpenAver" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_dir = log_dir

    log_file = log_dir / "debug.log"

    # Root logger 設定
    root_logger = logging.getLogger('OpenAver')
    root_logger.setLevel(logging.DEBUG)

    # 避免重複加入 handler
    if root_logger.handlers:
        return

    # 檔案 Handler (DEBUG 等級，保留詳細記錄)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Console Handler (可調整等級)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    _initialized = True
    root_logger.info(f"日誌系統初始化完成: {log_file}")


def get_logger(name: str) -> logging.Logger:
    """
    取得指定模組的 logger

    Args:
        name: 模組名稱，通常傳入 __name__

    Returns:
        Logger 實例
    """
    # 使用 OpenAver 作為 parent logger
    if name.startswith('core.') or name.startswith('web.'):
        logger_name = f"OpenAver.{name}"
    else:
        logger_name = f"OpenAver.{name}"

    return logging.getLogger(logger_name)


def set_console_level(level: int):
    """動態調整 console 輸出等級"""
    root_logger = logging.getLogger('OpenAver')
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
            handler.setLevel(level)
