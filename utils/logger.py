"""Central logger instance for the SQL Query Assistant."""

import logging
from utils.logging_config import configure_logging, log_execution_time

# Initialize logging on module import
_logger = None


def get_logger(process_name: str = "app") -> logging.Logger:
    """
    Get the configured logger instance for the application.

    Args:
        process_name: Name of the process for log file naming (default: "app")
                     Use different names for different processes to avoid file locks.

    Returns:
        logging.Logger: Configured logger instance

    Example:
        >>> from utils.logger import get_logger
        >>> logger = get_logger()  # Uses default "app.log"
        >>> logger.info("Application started")

        >>> # For a separate process like Streamlit
        >>> logger = get_logger("streamlit")  # Uses "streamlit.log"
    """
    global _logger
    if _logger is None:
        _logger = configure_logging(process_name)
    return _logger


# Export the context manager for execution time tracking
__all__ = ["get_logger", "log_execution_time"]
