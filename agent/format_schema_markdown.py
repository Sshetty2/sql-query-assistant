"""Convert JSON schema to markdown format for better LLM readability."""

import os
from langchain_core.messages import AIMessage
from agent.state import State
from utils.logger import get_logger
from utils.stream_utils import emit_node_status

logger = get_logger()


def resolve_foreign_key_column(fk: dict, to_table_name: str, all_tables: list) -> str:
    """
    Intelligently resolve the primary key column name for a foreign key relationship.

    Args:
        fk: Foreign key dictionary with 'foreign_key' and optional 'to_column'
        to_table_name: Name of the referenced table
        all_tables: List of all table dictionaries in the schema

    Returns:
        The primary key column name to use

    Resolution strategy:
    1. Use explicit 'to_column' if specified in FK definition
    2. Look up actual primary key from referenced table's schema
    3. Try matching FK column name (e.g., CVEID → CVEID, CompanyID → CompanyID)
    4. Fall back to "ID" as last resort
    """
    # 1. Use explicit to_column if provided
    if fk.get("to_column"):
        return fk["to_column"]

    # 2. Find the referenced table in schema and check for primary key
    referenced_table = next(
        (t for t in all_tables if t.get("table_name") == to_table_name), None
    )

    if referenced_table:
        # Check metadata first for primary_key (from domain-specific config)
        metadata = referenced_table.get("metadata", {})
        if metadata.get("primary_key"):
            pk = metadata["primary_key"]
            # Could be a list or a single column
            if isinstance(pk, list) and pk:
                return pk[0]  # Use first PK column for composite keys
            elif isinstance(pk, str):
                return pk

        # Fall back to schema-level primary_key field
        if referenced_table.get("primary_key"):
            pk = referenced_table["primary_key"]
            # Could be a list or a single column
            if isinstance(pk, list) and pk:
                return pk[0]  # Use first PK column for composite keys
            elif isinstance(pk, str):
                return pk

        # 3. Try matching FK column name with columns in referenced table
        fk_col_name = fk.get("foreign_key", "")
        if fk_col_name and referenced_table.get("columns"):
            # Check if a column with the same name exists in the referenced table
            matching_col = next(
                (
                    col
                    for col in referenced_table["columns"]
                    if col.get("column_name") == fk_col_name
                ),
                None,
            )
            if matching_col:
                logger.debug(
                    f"FK resolution: Matched {fk_col_name} to {to_table_name}.{fk_col_name} "
                    f"(no explicit PK, using name matching)"
                )
                return fk_col_name

    # 4. Fall back to "ID" as last resort
    logger.debug(
        f"FK resolution: Using default 'ID' for {fk.get('foreign_key')} → {to_table_name} "
        f"(no PK found, no name match)"
    )
    return "ID"


def format_schema_to_markdown(schema: list) -> str:
    """
    Convert JSON schema to well-organized markdown format.

    Args:
        schema: List of table dictionaries with columns, metadata, and foreign keys

    Returns:
        Formatted markdown string
    """
    markdown_lines = ["# DATABASE SCHEMA", ""]

    # Group tables by whether they have foreign keys (for better organization)
    tables_with_fks = []
    tables_without_fks = []

    for table in schema:
        if table.get("foreign_keys"):
            tables_with_fks.append(table)
        else:
            tables_without_fks.append(table)

    # Process all tables
    all_tables = tables_with_fks + tables_without_fks

    for table in all_tables:
        table_name = table.get("table_name", "Unknown")
        is_filtered = table.get("column_filtered", False)

        # Add indicator if columns have been filtered
        if is_filtered:
            markdown_lines.append(f"## TABLE: {table_name} (filtered columns)")
        else:
            markdown_lines.append(f"## {table_name}")
        markdown_lines.append("")

        # Add metadata description if available
        metadata = table.get("metadata", {})
        if metadata.get("description"):
            markdown_lines.append(f"**Description:** {metadata['description']}")
            markdown_lines.append("")

        # Add primary key if available
        if metadata.get("primary_key"):
            primary_key = metadata["primary_key"]
            markdown_lines.append(f"**Primary Key:** {primary_key}")
            markdown_lines.append("")

        # Add columns table
        columns = table.get("columns", [])
        if columns:
            markdown_lines.append("### Columns")
            markdown_lines.append("")
            markdown_lines.append("| Column Name | Data Type |")
            markdown_lines.append("|-------------|-----------|")

            for col in columns:
                col_name = col.get("column_name", "")
                data_type = col.get("data_type", "")
                markdown_lines.append(f"| {col_name} | {data_type} |")

            markdown_lines.append("")

        # Add foreign keys section
        foreign_keys = table.get("foreign_keys", [])
        if foreign_keys:
            markdown_lines.append("### Foreign Keys")
            markdown_lines.append("")

            for fk in foreign_keys:
                # Handle the actual schema format
                # Schema uses: "foreign_key" and "primary_key_table"
                from_col = fk.get("foreign_key", fk.get("from_column", ""))
                to_table = fk.get("primary_key_table", fk.get("to_table", ""))

                # Intelligently resolve the PK column name
                to_col = resolve_foreign_key_column(fk, to_table, all_tables)

                if from_col and to_table:
                    markdown_lines.append(f"- **{from_col}** → `{to_table}.{to_col}`")

            markdown_lines.append("")

        markdown_lines.append("---")
        markdown_lines.append("")

    return "\n".join(markdown_lines)


def convert_schema_to_markdown(state: State):
    """
    Convert the JSON schema to markdown format and update state.

    This step runs after filter_schema and formats the filtered schema
    (or full schema if filtering didn't occur) into markdown for better
    LLM parsing and understanding.
    """
    emit_node_status("format_schema_markdown", "running", "Formatting schema for AI")

    logger.info("Starting schema markdown formatting")

    try:
        # Use truncated schema if available (for planner context), otherwise filtered, otherwise full
        # truncated_schema = only relevant columns (best for planner)
        # filtered_schema = all columns (used for modification options)
        # schema = full schema (fallback)
        schema = (
            state.get("truncated_schema")
            or state.get("filtered_schema")
            or state.get("schema", [])
        )

        if not schema:
            return {
                **state,
                "messages": [AIMessage(content="No schema to format")],
                "last_step": "format_schema_markdown",
            }

        # Convert to markdown
        schema_markdown = format_schema_to_markdown(schema)

        # Debug: Save markdown schema
        from utils.debug_utils import is_debug_enabled, get_debug_dir

        if is_debug_enabled():
            try:
                # Save as markdown file (raw text)
                debug_path = os.path.join(get_debug_dir(), "debug_schema_markdown.md")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(schema_markdown)
                logger.debug(f"Debug markdown schema saved to: {debug_path}")
            except Exception as e:
                logger.warning(
                    f"Could not save debug markdown schema: {str(e)}", exc_info=True
                )

        logger.info(
            "Schema markdown formatting completed",
            extra={"markdown_length": len(schema_markdown), "table_count": len(schema)},
        )

        # Store markdown version in state (keep JSON version too)
        return {
            **state,
            "messages": [AIMessage(content="Schema formatted to markdown")],
            "schema_markdown": schema_markdown,
            "last_step": "format_schema_markdown",
        }

    except Exception as e:
        logger.error(f"Error formatting schema to markdown: {str(e)}", exc_info=True)
        return {
            **state,
            "messages": [AIMessage(content=f"Error formatting schema: {e}")],
            "last_step": "format_schema_markdown",
        }
