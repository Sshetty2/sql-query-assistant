"""Utilities for saving debug files during workflow execution."""

import os
import json
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger()

# Debug mode controlled by environment variable
DEBUG_ENABLED = os.getenv("ENABLE_DEBUG_FILES", "false").lower() == "true"

# Base debug directory
DEBUG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug")


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime and Decimal objects."""

    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            # Convert Decimal to float for JSON serialization
            return float(obj)
        # Let the base class raise TypeError for other non-serializable objects
        return super().default(obj)


def ensure_debug_dir():
    """Ensure the debug directory exists."""
    os.makedirs(DEBUG_DIR, exist_ok=True)


def save_debug_file(
    filename: str,
    data: Dict[str, Any],
    step_name: Optional[str] = None,
    include_timestamp: bool = False,
) -> Optional[str]:
    """
    Save debug data to a JSON file if debug mode is enabled.

    Args:
        filename: Name of the debug file (e.g., "planner_prompt.json")
        data: Dictionary of data to save
        step_name: Optional workflow step name for logging
        include_timestamp: If True, adds a timestamp to the data

    Returns:
        Path to saved file if successful, None otherwise

    Example:
        save_debug_file(
            "planner_prompt.json",
            {
                "user_question": question,
                "prompt": prompt_text,
                "model": model_name
            },
            step_name="planner"
        )
    """
    if not DEBUG_ENABLED:
        return None

    try:
        ensure_debug_dir()

        # Add timestamp if requested
        if include_timestamp:
            data = {
                "timestamp": datetime.now().isoformat(),
                **data,
            }

        # Construct full path
        if not filename.startswith("debug_"):
            filename = f"debug_{filename}"

        file_path = os.path.join(DEBUG_DIR, filename)

        # Write the file (with custom encoder for datetime objects)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, cls=DateTimeEncoder)

        log_extra = {"file_path": file_path}
        if step_name:
            log_extra["step"] = step_name

        logger.debug(
            f"Debug file saved: {filename}",
            extra=log_extra
        )

        return file_path

    except Exception as e:
        # Note: Use "debug_filename" instead of "filename" to avoid conflict with LogRecord's filename attribute
        logger.warning(
            f"Failed to save debug file {filename}: {str(e)}",
            exc_info=True,
            extra={
                "debug_filename": filename,
                "step_name": step_name,
            }
        )
        return None


def save_llm_interaction(
    step_name: str,
    prompt: str,
    response: Any,
    model: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Save LLM prompt and response for debugging.

    Args:
        step_name: Name of the workflow step (e.g., "planner", "router", "refine")
        prompt: The prompt sent to the LLM
        response: The LLM response (will be converted to dict if possible)
        model: Optional model name
        metadata: Optional additional metadata to include

    Returns:
        Path to saved file if successful, None otherwise
    """
    if not DEBUG_ENABLED:
        return None

    try:
        # Convert response to dict if it's a Pydantic model
        if hasattr(response, "model_dump"):
            response_data = response.model_dump()
        elif hasattr(response, "dict"):
            response_data = response.dict()
        elif isinstance(response, dict):
            response_data = response
        else:
            response_data = str(response)

        data = {
            "step": step_name,
            "prompt": prompt,
            "response": response_data,
        }

        if model:
            data["model"] = model

        if metadata:
            data["metadata"] = metadata

        filename = f"{step_name}_llm_interaction.json"
        return save_debug_file(filename, data, step_name=step_name, include_timestamp=True)

    except Exception as e:
        logger.warning(
            f"Failed to save LLM interaction for {step_name}: {str(e)}",
            exc_info=True
        )
        return None


def save_workflow_state(
    step_name: str,
    state: Dict[str, Any],
    keys_to_include: Optional[list[str]] = None,
) -> Optional[str]:
    """
    Save a snapshot of workflow state at a specific step.

    Args:
        step_name: Name of the workflow step
        state: The state dictionary
        keys_to_include: Optional list of specific keys to save (defaults to all)

    Returns:
        Path to saved file if successful, None otherwise
    """
    if not DEBUG_ENABLED:
        return None

    try:
        # Filter to specific keys if requested
        if keys_to_include:
            filtered_state = {k: state.get(k) for k in keys_to_include if k in state}
        else:
            # Save most important keys, skip large binary data
            filtered_state = {
                k: v for k, v in state.items()
                if k not in ["messages", "connection"]  # Skip large/non-serializable
            }

        data = {
            "step": step_name,
            "state": filtered_state,
        }

        filename = f"{step_name}_state.json"
        return save_debug_file(filename, data, step_name=step_name, include_timestamp=True)

    except Exception as e:
        logger.warning(
            f"Failed to save workflow state for {step_name}: {str(e)}",
            exc_info=True
        )
        return None


def is_debug_enabled() -> bool:
    """Check if debug file generation is enabled."""
    return DEBUG_ENABLED


def get_debug_dir() -> str:
    """Get the debug directory path."""
    return DEBUG_DIR


def append_to_debug_array(
    filename: str,
    data: Dict[str, Any],
    step_name: Optional[str] = None,
    array_key: str = "iterations",
) -> Optional[str]:
    """
    Append data to an array in a debug file. Useful for iterative steps.

    If the file doesn't exist, creates it with an array containing the data.
    If it exists, loads it, appends to the array, and saves.

    Args:
        filename: Name of the debug file (e.g., "error_corrections.json")
        data: Dictionary of data to append to the array
        step_name: Optional workflow step name for logging
        array_key: Key name for the array in the JSON (default: "iterations")

    Returns:
        Path to saved file if successful, None otherwise

    Example:
        # First call creates: {"iterations": [{"attempt": 1, ...}]}
        # Second call updates to: {"iterations": [{"attempt": 1, ...}, {"attempt": 2, ...}]}
        append_to_debug_array(
            "error_corrections.json",
            {
                "attempt": retry_count,
                "error": error_msg,
                "correction": corrected_plan
            },
            step_name="handle_error",
            array_key="corrections"
        )
    """
    if not DEBUG_ENABLED:
        return None

    try:
        ensure_debug_dir()

        # Add debug_ prefix if not present
        if not filename.startswith("debug_"):
            filename = f"debug_{filename}"

        file_path = os.path.join(DEBUG_DIR, filename)

        # Load existing file or create new structure
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        else:
            existing_data = {array_key: []}

        # Add timestamp to this iteration's data
        data_with_timestamp = {
            "timestamp": datetime.now().isoformat(),
            **data,
        }

        # Append to array
        if array_key not in existing_data:
            existing_data[array_key] = []

        existing_data[array_key].append(data_with_timestamp)

        # Also track total count
        existing_data["total_count"] = len(existing_data[array_key])

        # Write updated file (with custom encoder for datetime objects)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False, cls=DateTimeEncoder)

        log_extra = {
            "file_path": file_path,
            "array_length": existing_data["total_count"],
        }
        if step_name:
            log_extra["step"] = step_name

        logger.debug(
            f"Appended to debug array in {filename} (total: {existing_data['total_count']})",
            extra=log_extra
        )

        return file_path

    except Exception as e:
        # Note: Use "debug_filename" instead of "filename" to avoid conflict with LogRecord's filename attribute
        logger.warning(
            f"Failed to append to debug array {filename}: {str(e)}",
            exc_info=True,
            extra={
                "debug_filename": filename,
                "step_name": step_name,
            }
        )
        return None


def clear_debug_files(pattern: Optional[str] = None) -> int:
    """
    Clear debug files from the debug directory.

    Args:
        pattern: Optional glob pattern to match files (e.g., "planner_*.json")
                If None, clears all debug files (.json, .txt, .md)

    Returns:
        Number of files deleted
    """
    if not DEBUG_ENABLED:
        return 0

    try:
        from glob import glob

        ensure_debug_dir()

        if pattern:
            search_patterns = [os.path.join(DEBUG_DIR, pattern)]
        else:
            # Clear all common debug file types
            search_patterns = [
                os.path.join(DEBUG_DIR, "*.json"),
                os.path.join(DEBUG_DIR, "*.txt"),
                os.path.join(DEBUG_DIR, "*.md"),
            ]

        count = 0

        for search_pattern in search_patterns:
            files = glob(search_pattern)
            for file_path in files:
                try:
                    os.remove(file_path)
                    count += 1
                    logger.debug(f"Deleted debug file: {os.path.basename(file_path)}")
                except Exception as e:
                    logger.warning(f"Failed to delete {file_path}: {e}")

        if count > 0:
            logger.info(f"Cleared {count} debug files from previous run")

        return count

    except Exception as e:
        logger.warning(f"Failed to clear debug files: {e}")
        return 0
