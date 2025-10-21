"""Central logger instance for the SQL Query Assistant."""

import logging
from utils.logging_config import configure_logging, log_execution_time

# Initialize logging on module import
_logger = None


def get_logger() -> logging.Logger:
    """
    Get the configured logger instance for the application.

    Returns:
        logging.Logger: Configured logger instance

    Example:
        >>> from utils.logger import get_logger
        >>> logger = get_logger()
        >>> logger.info("Application started")
    """
    global _logger
    if _logger is None:
        _logger = configure_logging()
    return _logger


# Export the context manager for execution time tracking
__all__ = ["get_logger", "log_execution_time"]
