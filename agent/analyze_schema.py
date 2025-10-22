"""Retrieve schema information for the database."""

import os
import json

from dotenv import load_dotenv
from langchain_core.messages import AIMessage

from domain_specific_guidance.combine_json_schema import combine_schema
from agent.state import State
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger()


def get_schema_query():
    """Get the appropriate schema query based on database type."""
    if os.getenv("USE_TEST_DB", "").lower() == "true":
        return """
        SELECT
            m.name AS table_name,
            p.name AS column_name,
            p.type AS data_type
        FROM sqlite_master m
        JOIN pragma_table_info(m.name) p
        WHERE m.type = 'table'
        ORDER BY m.name, p.cid;
        """
    else:
        return """
        SELECT
            t.TABLE_NAME AS table_name,
            c.COLUMN_NAME AS column_name,
            c.DATA_TYPE AS data_type
        FROM INFORMATION_SCHEMA.COLUMNS c
        JOIN INFORMATION_SCHEMA.TABLES t ON c.TABLE_NAME = t.TABLE_NAME
        WHERE t.TABLE_SCHEMA = 'dbo'
            AND t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION;
        """


def fetch_lean_schema(connection):
    """Fetch only the necessary schema details for efficient LLM processing."""
    schema_query = get_schema_query()
    cursor = None

    try:
        cursor = connection.cursor()
        cursor.execute(schema_query)
        results = cursor.fetchall()

        # Post-process results into structured format
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in results]

        # Group columns by table
        tables = {}
        for row in rows:
            table_name = row["table_name"]
            if table_name not in tables:
                tables[table_name] = {"table_name": table_name, "columns": []}
            tables[table_name]["columns"].append(
                {
                    "column_name": row["column_name"],
                    "data_type": row["data_type"],
                }
            )

        cursor.close()
        return list(tables.values())
    except Exception as e:
        if cursor:
            cursor.close()
        raise Exception(f"Failed to fetch schema: {e}")


def analyze_schema(state: State, db_connection):
    """Retrieve schema information for the database."""
    logger.info("Starting schema analysis")

    try:
        with log_execution_time(logger, "fetch_lean_schema"):
            schema = fetch_lean_schema(db_connection)

        logger.info(f"Retrieved schema with {len(schema)} tables")

        with log_execution_time(logger, "combine_schema_with_metadata"):
            combined_schema_with_metadata = combine_schema(schema)

        # Debug: Write full_schema to a JSON file
        with open("debug/combined_schema_with_metadata.json", "w") as f:
            json.dump(combined_schema_with_metadata, f, indent=2)

        logger.info(
            "Schema analysis completed",
            extra={
                "table_count": len(combined_schema_with_metadata),
                "has_metadata": any(
                    "metadata" in table for table in combined_schema_with_metadata
                ),
            },
        )

        return {
            **state,
            "messages": [AIMessage(content="Schema information gathered.")],
            "schema": combined_schema_with_metadata,
            "last_step": "analyze_schema",
        }
    except Exception as e:
        logger.error(f"Error retrieving schema: {str(e)}", exc_info=True)
        return {
            **state,
            "messages": [AIMessage(content=f"Error retrieving schema: {e}")],
            "last_step": "analyze_schema",
        }
