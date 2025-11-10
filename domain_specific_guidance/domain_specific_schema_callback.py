"""Domain-specific schema callback for modifying schema based on domain requirements."""

import os
import json
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger()


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


def remove_misleading_tables(json_schema):
    """Remove tables that are misleading and interfere with query generation.

    This function removes entire tables that should not be considered during
    schema filtering and query planning.

    Args:
        json_schema: The database schema with tables and columns

    Returns:
        Schema with misleading tables removed

    Example:
        Nessus-related tables are removed because they are outdated/misleading
        and cause the LLM to generate incorrect queries.
    """
    # Tables to remove (case-insensitive matching)
    table_patterns_to_remove = [
        "nessus",  # Any table containing "nessus" (case-insensitive)
    ]

    original_count = len(json_schema)

    # Filter out tables matching any of the patterns
    filtered_schema = []
    removed_tables = []

    for table in json_schema:
        table_name = table.get("table_name", "").lower()
        should_remove = any(
            pattern.lower() in table_name for pattern in table_patterns_to_remove
        )

        if should_remove:
            removed_tables.append(table.get("table_name"))
        else:
            filtered_schema.append(table)

    removed_count = len(removed_tables)
    if removed_count > 0:
        logger.info(
            f"Removed {removed_count} misleading table(s) from schema",
            extra={
                "removed_tables": removed_tables,
                "original_count": original_count,
                "filtered_count": len(filtered_schema),
            },
        )

    return filtered_schema


def remove_misleading_columns(json_schema):
    """Remove columns that are misleading due to data quality issues.

    This function removes columns that appear to be boolean flags (0/1) but actually
    contain NULL values, which breaks filter logic and leads to incorrect queries.

    Exception: StatusID is kept for tb_CVECDAMap as it contains important CVE status
    information (Matched/Unmatched/Assessment states).

    Args:
        json_schema: The database schema with tables and columns

    Returns:
        Schema with misleading columns removed

    Example:
        IsDeleted column appears to be a boolean (0 or 1) but contains NULL values.
        Filters like "WHERE IsDeleted = 0" fail because NULL != 0, returning no results.
    """
    columns_to_remove = [
        "IsDeleted",
        "StatusID",
        "OrgID",
    ]  # Add more column names here as needed

    # Tables where StatusID should be kept (exception to the removal rule)
    statusid_exceptions = ["tb_CVECDAMap"]

    removed_count = 0
    for table in json_schema:
        table_name = table.get("table_name")
        columns = table.get("columns", [])

        # Track original count
        original_count = len(columns)

        # Determine which columns to remove for this specific table
        columns_to_remove_for_table = columns_to_remove.copy()
        if table_name in statusid_exceptions:
            # Keep StatusID for exception tables
            columns_to_remove_for_table.remove("StatusID")

        # Filter out misleading columns
        filtered_columns = [
            col for col in columns if col.get("column_name") not in columns_to_remove_for_table
        ]

        # Update table columns
        table["columns"] = filtered_columns

        # Log if columns were removed
        removed_this_table = original_count - len(filtered_columns)
        if removed_this_table > 0:
            removed_count += removed_this_table
            logger.debug(
                f"Removed {removed_this_table} misleading column(s) from {table_name}",
                extra={
                    "table": table_name,
                    "removed_columns": [
                        col
                        for col in columns_to_remove_for_table
                        if col in [c.get("column_name") for c in columns]
                    ],
                },
            )

    if removed_count > 0:
        logger.info(
            f"Removed {removed_count} misleading column(s) total across all tables",
            extra={"columns_removed": columns_to_remove},
        )

    return json_schema


def combine_schema(json_schema, include_foreign_keys=True):
    """Combine schema with domain-specific table metadata and foreign keys.

    This function:
    1. Removes misleading tables (like Nessus tables that interfere with queries)
    2. Removes misleading columns (like IsDeleted with NULL values)
    3. Enriches schema with domain-specific table metadata
    4. Adds domain-specific foreign key relationships

    This function looks for domain-specific JSON files in the domain-specific-guidance directory:
    - domain-specific-table-metadata.json
    - domain-specific-foreign-keys.json

    If these files don't exist, the original schema is returned with only table/column filtering applied.

    Args:
        json_schema: The database schema to enrich with metadata
        include_foreign_keys: If False, skip loading foreign keys from domain-specific files.
                             Useful for FK inference testing where you want metadata (descriptions)
                             but not ground truth FKs. (default: True)

    Returns:
        Modified schema with misleading tables/columns removed, metadata added,
        and optionally foreign keys (if domain-specific files exist)
    """
    # Check environment variable at runtime instead of module load time
    # This allows tests to override the value
    use_test_db = os.getenv("USE_TEST_DB", "false").lower() == "true"

    if use_test_db:
        logger.info("Using test database, skipping domain-specific modifications")
        return json_schema

    # Step 1: Remove misleading tables (always do this first)
    json_schema = remove_misleading_tables(json_schema)

    # Step 2: Remove misleading columns (always do this)
    json_schema = remove_misleading_columns(json_schema)

    # Step 3: Load domain-specific metadata and foreign keys
    table_metadata = load_domain_specific_json("domain-specific-table-metadata.json")

    # Only load foreign keys if requested
    foreign_keys = None
    if include_foreign_keys:
        foreign_keys = load_domain_specific_json("domain-specific-foreign-keys.json")

    if not table_metadata and not foreign_keys:
        logger.info(
            "No domain-specific metadata or foreign keys found, returning schema with table/column filtering only"
        )
        return json_schema

    # Step 4: Combine metadata and foreign keys

    metadata_map = {entry["table_name"]: entry for entry in (table_metadata or [])}
    foreign_keys_map = {}
    if foreign_keys:
        foreign_keys_map = {
            entry["table_name"]: entry["foreign_keys"] for entry in foreign_keys
        }

    for table in json_schema:
        table_name = table.get("table_name")

        if table_name in metadata_map:
            table["metadata"] = metadata_map[table_name]

        if table_name in foreign_keys_map:
            table["foreign_keys"] = foreign_keys_map[table_name]

    # Fields to keep in metadata (all others will be removed)
    metadata_fields_to_keep = {"description", "primary_key"}

    for table in json_schema:
        if "metadata" in table:
            # Remove extraneous fields - only keep essential ones
            filtered_metadata = {
                k: v
                for k, v in table["metadata"].items()
                if k in metadata_fields_to_keep
            }
            table["metadata"] = filtered_metadata
        if "c" in table:
            table["columns"] = table.pop("c")

    combined_schema = remove_empty_properties(json_schema)

    return combined_schema
