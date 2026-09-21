import os
import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Always create logs folder at project root — not relative to where you run from
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB per log file

def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger that writes to binance.log, bybit.log, or app.log
    based on the logger name passed in or the script being run.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    # Check name first — e.g. get_logger("BinanceMain") → binance.log
    # Then check running script name as backup
    ctx = (name + (sys.argv[0] if sys.argv else "")).lower()

    if "binance" in ctx:
        log_file = LOG_DIR / "binance.log"
    elif "bybit" in ctx:
        log_file = LOG_DIR / "bybit.log"
    else:
        log_file = LOG_DIR / "app.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if get_logger called multiple times
    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # File handler — rotates at 5MB, keeps 5 backups
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=MAX_BYTES,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler — prints to terminal as well
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger