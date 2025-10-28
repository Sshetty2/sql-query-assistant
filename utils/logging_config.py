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
from rich.logging import RichHandler
from rich.console import Console
from rich.theme import Theme

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


# Rich theme for consistent log styling
rich_theme = Theme({
    "logging.level.debug": "dim cyan",
    "logging.level.info": "bold blue",
    "logging.level.warning": "bold yellow",
    "logging.level.error": "bold red",
    "logging.level.critical": "bold magenta on white",
})

# Create Rich console for logging
rich_console = Console(theme=rich_theme, force_terminal=True)


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

    # Add Rich console handler if requested
    if console_output:
        rich_handler = RichHandler(
            console=rich_console,
            show_time=True,
            show_level=True,
            show_path=False,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True,
            log_time_format="[%Y-%m-%d %H:%M:%S]",
        )
        rich_handler.setLevel(log_level)
        logger.addHandler(rich_handler)

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
