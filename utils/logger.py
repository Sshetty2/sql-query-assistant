"""Central logger instance for the SQL Query Assistant."""

import logging
from utils.logging_config import configure_logging, log_execution_time

# Cache loggers by process name
_loggers = {}


def get_logger(process_name: str = "app", console_output: bool = None) -> logging.Logger:
    """
    Get the configured logger instance for the application.

    Args:
        process_name: Name of the process for log file naming (default: "app")
                     Use different names for different processes to avoid file locks.
        console_output: Whether to output logs to console (default: True for most, False for fk_agent)
                       Set to False for CLI tools where log output interferes with user prompts.

    Returns:
        logging.Logger: Configured logger instance

    Example:
        >>> from utils.logger import get_logger
        >>> logger = get_logger()  # Uses default "app.log"
        >>> logger.info("Application started")

        >>> # For a separate process like Streamlit
        >>> logger = get_logger("streamlit")  # Uses "streamlit.log"

        >>> # For CLI tools (no console output to avoid interference)
        >>> logger = get_logger("fk_agent", console_output=False)
    """
    global _loggers
    if process_name not in _loggers:
        # Auto-enable console output only for main app and streamlit
        if console_output is None:
            console_output = process_name in ["app", "streamlit"]
        _loggers[process_name] = configure_logging(process_name, console_output=console_output)
    return _loggers[process_name]


# Export the context manager for execution time tracking
__all__ = ["get_logger", "log_execution_time"]
