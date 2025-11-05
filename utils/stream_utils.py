"""Utilities for custom streaming with LangGraph."""

from typing import Optional
from langgraph.config import get_stream_writer


def emit_node_status(
    node_name: str, status: str = "running", message: Optional[str] = None
):
    """
    Emit a status update for the current workflow node.

    Args:
        node_name: Name of the current node
        status: Status of the node ("running", "completed", "error")
        message: Optional custom message
    """
    try:
        writer = get_stream_writer()
        writer(
            {
                "node_name": node_name,
                "node_status": status,
                "node_message": message,
            }
        )
    except Exception:
        # Stream writer not available (non-streaming mode), silently continue
        pass


def emit_log(node_name: str, log_message: str, level: str = "info"):
    """
    Emit a log message to the stream (without 'extra' information).

    Args:
        node_name: Name of the current node
        log_message: The log message
        level: Log level ("debug", "info", "warning", "error")
    """
    try:
        writer = get_stream_writer()
        writer(
            {
                "node_name": node_name,
                "node_logs": log_message,
                "log_level": level,
            }
        )
    except Exception:
        # Stream writer not available (non-streaming mode), silently continue
        pass


def log_and_stream(
    logger, node_name: str, message: str, level: str = "info", **logger_kwargs
):
    """
    Log a message and emit it to the stream.

    This combines standard logging with stream emission for better visibility.

    Args:
        logger: Logger instance
        node_name: Name of the current node
        message: The message to log
        level: Log level ("debug", "info", "warning", "error")
        **logger_kwargs: Additional kwargs for the logger (e.g., exc_info, extra)
    """
    # Call the logger
    log_func = getattr(logger, level, logger.info)
    log_func(message, **logger_kwargs)

    # Emit to stream (without 'extra' information for cleaner stream)
    emit_log(node_name, message, level)
