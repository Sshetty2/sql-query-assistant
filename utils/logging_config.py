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

_configured_processes = set()
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


def configure_logging(process_name: str = "app", console_output: bool = True) -> logging.Logger:
    """Configure logging for the application with structured JSON logging and colored console output

    Args:
        process_name: Name of the process for log file naming (default: "app")
                     This allows multiple processes to have separate log files.
                     Examples: "app", "streamlit", "api", "fk_agent"
        console_output: Whether to output logs to console (default: True)
                       Set to False for background processes or CLI tools
    """
    global _configured_processes

    # Return existing logger if already configured for this process
    logger_name = f"sql_query_assistant.{process_name}"
    if process_name in _configured_processes:
        return logging.getLogger(logger_name)

    # Get configuration from environment variables
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_file = log_dir / f"{process_name}.log"
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    log_dir.mkdir(exist_ok=True, parents=True)

    # Create process-specific logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    logger.propagate = False  # Don't propagate to root logger

    # Remove any existing handlers (in case of re-configuration)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    json_formatter = CustomJsonFormatter(
        "%(level)s %(timestamp)s %(message)s", json_ensure_ascii=False
    )

    # File handler for main log
    app_handler = logging.handlers.TimedRotatingFileHandler(
        str(log_file),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_handler.setFormatter(json_formatter)
    app_handler.setLevel(log_level)
    logger.addHandler(app_handler)

    # File handler for errors
    error_handler = logging.handlers.TimedRotatingFileHandler(
        str(log_dir / f"{process_name}_error.log"),
        when="midnight",
        interval=1,
        backupCount=90,
        encoding="utf-8",
    )
    error_handler.setFormatter(json_formatter)
    error_handler.setLevel(logging.ERROR)
    logger.addHandler(error_handler)

    # Add console handler if requested
    if console_output:
        color_formatter = ColoredFormatter()
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(color_formatter)
        console_handler.setLevel(log_level)
        logger.addHandler(console_handler)

    # Suppress noisy third-party loggers (only once)
    if not _configured_processes:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("httpcore.http11").setLevel(logging.WARNING)

    logger.info(
        "Logging initialized",
        extra={
            "process_name": process_name,
            "log_level": log_level_str,
            "log_file": str(log_file),
            "console_output": console_output,
        },
    )

    _configured_processes.add(process_name)
    return logger
