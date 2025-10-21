"""Combine schema with table metadata and foreign keys."""

import os
import json
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger()

use_test_db = os.getenv("USE_TEST_DB").lower() == "true"


def load_json(filename):
    """Utility function to load JSON from a file."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)
    file_path = os.path.join(root_dir, filename)

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error(f"Schema file not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(
            f"Error decoding JSON: {str(e)}", exc_info=True, extra={"file": file_path}
        )
        return None


def remove_empty_properties(data):
    """Recursively remove properties with empty strings or None values."""
    if isinstance(data, dict):
        return {
            k: remove_empty_properties(v)
            for k, v in data.items()
            if v not in ("", None)
        }
    elif isinstance(data, list):
        return [
            remove_empty_properties(item) for item in data if item not in ("", None)
        ]
    else:
        return data


def combine_schema(
    json_schema,
    cwp_table_metadata_path="cwp_table_metadata.json",
    cwp_foreign_keys_path="cwp_foreign_keys.json",
):
    """Combine schema with table metadata and foreign keys."""
    if use_test_db:
        return json_schema

    cwp_table_metadata = load_json(cwp_table_metadata_path)
    cwp_foreign_keys = load_json(cwp_foreign_keys_path)

    if not cwp_table_metadata and not cwp_foreign_keys:
        logger.info("No metadata or foreign keys found, returning original schema")
        return json_schema

    metadata_map = {entry["table_name"]: entry for entry in (cwp_table_metadata or [])}
    foreign_keys_map = {
        entry["table_name"]: entry["foreign_keys"] for entry in (cwp_foreign_keys or [])
    }

    for table in json_schema:
        table_name = table.get("table_name")

        if table_name in metadata_map:
            table["metadata"] = metadata_map[table_name]

        if table_name in foreign_keys_map:
            table["foreign_keys"] = foreign_keys_map[table_name]

    for table in json_schema:
        if "metadata" in table:
            table["metadata"].pop("table_name", None)
            if "key_columns" in table["metadata"] and isinstance(
                table["metadata"]["key_columns"], str
            ):
                table["metadata"]["key_columns"] = [
                    col.strip()
                    for col in table["metadata"]["key_columns"].split("\n")
                    if col.strip()
                ]
        if "c" in table:
            table["columns"] = table.pop("c")

    combined_schema = remove_empty_properties(json_schema)

    return combined_schema
