import logging
import logging.handlers
import os
import queue
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from pythonjsonlogger import jsonlogger
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

_is_configured = False
_log_queue = queue.Queue(-1)
_queue_listener = None
_info_color_cycle = None


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields"""

    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        log_record["timestamp"] = datetime.utcnow().isoformat()
        log_record["level"] = record.levelname
        log_record["function"] = record.funcName
        log_record["module"] = record.module

        if record.exc_info:
            log_record["error_type"] = record.exc_info[0].__name__
            log_record["error_message"] = str(record.exc_info[1])


class ColoredFormatter(logging.Formatter):
    """Colored formatter for terminal output"""

    RESET = "\033[0m"
    BOLD = "\033[1m"

    # Background colors for log level tags
    INFO_BG = "\033[44m"  # Blue background
    WARNING_BG = "\033[43m"  # Yellow background
    ERROR_BG = "\033[41m"  # Red background
    CRITICAL_BG = "\033[45m"  # Magenta background
    DEBUG_BG = "\033[100m"  # Gray background

    # Foreground colors for messages
    INFO_START = "\033[38;5;45m"  # Light Blue for "started" operations
    INFO_COMPLETE = "\033[38;5;35m"  # Green for "completed" operations
    INFO_DEFAULT = "\033[38;5;39m"  # Blue for regular INFO messages
    WARNING = "\033[38;5;208m"  # Orange
    ERROR = "\033[38;5;196m"  # Red
    CRITICAL = "\033[38;5;197m\033[1m"  # Bold Magenta
    DEBUG = "\033[38;5;245m"  # Gray

    def format(self, record):
        if record.levelno == logging.INFO:
            level_fmt = f"{self.INFO_BG}{self.BOLD} INFO {self.RESET}"
        elif record.levelno == logging.WARNING:
            level_fmt = f"{self.WARNING_BG}{self.BOLD} WARNING {self.RESET}"
        elif record.levelno == logging.ERROR:
            level_fmt = f"{self.ERROR_BG}{self.BOLD} ERROR {self.RESET}"
        elif record.levelno == logging.CRITICAL:
            level_fmt = f"{self.CRITICAL_BG}{self.BOLD} CRITICAL {self.RESET}"
        elif record.levelno == logging.DEBUG:
            level_fmt = f"{self.DEBUG_BG}{self.BOLD} DEBUG {self.RESET}"
        else:
            level_fmt = f"{record.levelname:8}"

        original_levelname = record.levelname
        record.levelname = level_fmt

        if record.levelno == logging.INFO:
            message = record.getMessage().lower()
            if "starting operation" in message or "started" in message:
                color = self.INFO_START
            elif "completed" in message or "finished" in message:
                color = self.INFO_COMPLETE
            else:
                color = self.INFO_DEFAULT
        elif record.levelno == logging.WARNING:
            color = self.WARNING
        elif record.levelno == logging.ERROR:
            color = self.ERROR
        elif record.levelno == logging.CRITICAL:
            color = self.CRITICAL
        elif record.levelno == logging.DEBUG:
            color = self.DEBUG
        else:
            color = self.RESET

        DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

        # Check if execution time is in the record (from log_execution_time)
        execution_time = getattr(record, "execution_time_ms", None)
        if execution_time is not None:
            # Add execution time to the message
            original_msg = record.getMessage()
            record.msg = f"{original_msg} [{execution_time}ms]"
            record.args = ()  # Clear args since we've formatted the message

        format_string = f"%(levelname)s {color}%(asctime)s %(message)s{self.RESET}"

        formatter = logging.Formatter(format_string, datefmt=DATE_FORMAT)

        result = formatter.format(record)

        record.levelname = original_levelname

        return result


@contextmanager
def log_execution_time(logger: logging.Logger, operation: str):
    """Context manager to log operation execution time"""
    start_time = time.time()
    try:
        logger.info(f"Operation {operation} STARTED")
        yield
    finally:
        execution_time = time.time() - start_time
        logger.info(
            f"Operation {operation} COMPLETED",
            extra={
                "execution_time_ms": round(execution_time * 1000, 2),
            },
        )


def configure_logging(process_name: str = "app") -> logging.Logger:
    """Configure logging for the application with structured JSON logging and colored console output

    Args:
        process_name: Name of the process for log file naming (default: "app")
                     This allows multiple processes to have separate log files.
                     Examples: "app", "streamlit", "api"
    """
    global _is_configured, _queue_listener

    if _is_configured:
        return logging.getLogger("sql_query_assistant")

    # Get configuration from environment variables
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_file = log_dir / f"{process_name}.log"
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    log_dir.mkdir(exist_ok=True, parents=True)

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.setLevel(log_level)

    json_formatter = CustomJsonFormatter(
        "%(level)s %(timestamp)s %(message)s", json_ensure_ascii=False
    )

    color_formatter = ColoredFormatter()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(color_formatter)
    console_handler.setLevel(log_level)

    app_handler = logging.handlers.TimedRotatingFileHandler(
        str(log_file),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_handler.setFormatter(json_formatter)
    app_handler.setLevel(log_level)

    error_handler = logging.handlers.TimedRotatingFileHandler(
        str(log_dir / f"{process_name}_error.log"),
        when="midnight",
        interval=1,
        backupCount=90,
        encoding="utf-8",
    )
    error_handler.setFormatter(json_formatter)
    error_handler.setLevel(logging.ERROR)

    _queue_listener = logging.handlers.QueueListener(
        _log_queue,
        console_handler,
        app_handler,
        error_handler,
        respect_handler_level=True,
    )
    _queue_listener.start()

    queue_handler = logging.handlers.QueueHandler(_log_queue)
    root_logger.addHandler(queue_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore.http11").setLevel(logging.WARNING)

    logger = logging.getLogger("sql_query_assistant")
    logger.info(
        "Logging initialized",
        extra={
            "log_level": log_level_str,
            "log_file": str(log_file),
            "log_dir": str(log_dir),
        },
    )

    _is_configured = True
    return logger
