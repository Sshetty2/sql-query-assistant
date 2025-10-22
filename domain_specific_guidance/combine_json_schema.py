"""Combine schema with table metadata and foreign keys."""

import os
import json
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger()

use_test_db = os.getenv("USE_TEST_DB").lower() == "true"


def load_domain_specific_json(filename):
    """Utility function to load JSON from the domain-specific-guidance directory.

    Returns None if file doesn't exist (which is expected and not an error).
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, filename)

    if not os.path.exists(file_path):
        logger.info(f"Domain-specific file not found (this is optional): {filename}")
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
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


def combine_schema(json_schema):
    """Combine schema with domain-specific table metadata and foreign keys.

    This function looks for domain-specific JSON files in the domain-specific-guidance directory:
    - domain-specific-table-metadata.json
    - domain-specific-foreign-keys.json

    If these files don't exist, the original schema is returned unchanged.

    Args:
        json_schema: The database schema to enrich with metadata

    Returns:
        Combined schema with metadata and foreign keys (if domain-specific files exist)
    """
    if use_test_db:
        logger.info("Using test database, skipping domain-specific metadata")
        return json_schema

    # Look for domain-specific files
    table_metadata = load_domain_specific_json("domain-specific-table-metadata.json")
    foreign_keys = load_domain_specific_json("domain-specific-foreign-keys.json")

    if not table_metadata and not foreign_keys:
        logger.info(
            "No domain-specific metadata or foreign keys found, returning original schema"
        )
        return json_schema

    metadata_map = {entry["table_name"]: entry for entry in (table_metadata or [])}
    foreign_keys_map = {
        entry["table_name"]: entry["foreign_keys"] for entry in (foreign_keys or [])
    }

    for table in json_schema:
        table_name = table.get("table_name")

        if table_name in metadata_map:
            table["metadata"] = metadata_map[table_name]

        if table_name in foreign_keys_map:
            table["foreign_keys"] = foreign_keys_map[table_name]

    # Fields to keep in metadata (all others will be removed)
    metadata_fields_to_keep = {"description", "key_columns"}

    for table in json_schema:
        if "metadata" in table:
            # Remove extraneous fields - only keep essential ones
            filtered_metadata = {
                k: v
                for k, v in table["metadata"].items()
                if k in metadata_fields_to_keep
            }
            table["metadata"] = filtered_metadata

            # Convert key_columns from string to list if needed
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
