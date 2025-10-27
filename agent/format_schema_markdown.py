"""Convert JSON schema to markdown format for better LLM readability."""

import os
from langchain_core.messages import AIMessage
from agent.state import State
from utils.logger import get_logger

logger = get_logger()


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
        markdown_lines.append(f"## {table_name}")
        markdown_lines.append("")

        # Add metadata description if available
        metadata = table.get("metadata", {})
        if metadata.get("description"):
            markdown_lines.append(f"**Description:** {metadata['description']}")
            markdown_lines.append("")

        # Add key columns if available
        if metadata.get("key_columns"):
            key_cols = metadata["key_columns"]
            if isinstance(key_cols, list):
                markdown_lines.append(f"**Key Columns:** {', '.join(key_cols)}")
            else:
                markdown_lines.append(f"**Key Columns:** {key_cols}")
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
                to_col = fk.get("to_column", "ID")  # Assume ID if not specified

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
    logger.info("Starting schema markdown formatting")

    try:
        # Use filtered schema if available, otherwise use full schema
        schema = state.get("filtered_schema") or state.get("schema", [])

        if not schema:
            return {
                **state,
                "messages": [AIMessage(content="No schema to format")],
                "last_step": "format_schema_markdown",
            }

        # Convert to markdown
        schema_markdown = format_schema_to_markdown(schema)

        # Debug: Save markdown schema
        from utils.debug_utils import save_debug_file, is_debug_enabled, get_debug_dir
        if is_debug_enabled():
            try:
                # Save as markdown file (raw text)
                debug_path = os.path.join(get_debug_dir(), "debug_schema_markdown.md")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(schema_markdown)
                logger.debug(f"Debug markdown schema saved to: {debug_path}")
            except Exception as e:
                logger.warning(
                    f"Could not save debug markdown schema: {str(e)}",
                    exc_info=True
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
