"""Retrieve schema information for the database."""

import json
import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage

from agent.combine_json_schema import combine_schema
from agent.state import State

load_dotenv()


def get_schema_query():
    """Get the appropriate schema query based on database type."""
    if os.getenv("USE_TEST_DB", "").lower() == "true":
        return """
        SELECT json_group_array(
            json_object(
                'table_name', m.name,
                'columns', (
                    SELECT json_group_array(
                        json_object(
                            'column_name', p.name,
                            'data_type', p.type,
                            'is_nullable', (
                                CASE
                                    WHEN p."notnull" = 0 THEN 'YES'
                                    ELSE 'NO'
                                END
                            )
                        )
                    )
                    FROM pragma_table_info(m.name) p
                )
            )
        ) AS json
        FROM sqlite_master m
        WHERE m.type = 'table';
        """
    else:
        return """
        select ((
            SELECT
                t.TABLE_NAME AS table_name,
                c.COLUMN_NAME AS column_name,
                c.DATA_TYPE AS data_type,
                c.IS_NULLABLE AS is_nullable
            FROM INFORMATION_SCHEMA.COLUMNS c
            JOIN INFORMATION_SCHEMA.TABLES t ON c.TABLE_NAME = t.TABLE_NAME
            WHERE t.TABLE_SCHEMA = 'dbo'
            FOR JSON AUTO
        )) as json
        """


def fetch_lean_schema(connection):
    """Fetch only the necessary schema details for efficient LLM processing."""
    schema_query = get_schema_query()

    try:
        cursor = connection.cursor()
        cursor.execute(schema_query)
        schema_result = cursor.fetchall()
        cursor.close()
        return schema_result[0][0] if schema_result else None
    except Exception as e:
        if cursor:
            cursor.close()
        raise Exception(f"Failed to fetch schema: {e}")


def analyze_schema(state: State, db_connection):
    """Retrieve schema information for the database."""

    try:
        schema = fetch_lean_schema(db_connection)

        try:
            schema = json.loads(schema)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON schema: {e}")
            schema = []

        combined_schema_with_metadata = combine_schema(schema)

        return {
            **state,
            "messages": [AIMessage(content="Schema information gathered.")],
            "schema": combined_schema_with_metadata,
            "last_step": "analyze_schema",
        }
    except Exception as e:
        return {
            **state,
            "messages": [AIMessage(content=f"Error retrieving schema: {e}")],
            "last_step": "analyze_schema",
        }
