import pyodbc
from agent.state import State
from langchain_core.messages import AIMessage

def analyze_schema(state: State, tools, db_connection):
    """Retrieve schema information for the database."""
    try:
        schema = fetch_lean_schema(db_connection)
        return {
            "messages": [AIMessage(content="Schema information gathered.")],
            "schema": schema,
            "sort_order": state["sort_order"],
            "result_limit": state["result_limit"],
            "time_filter": state["time_filter"],
            "current_step": "Analyzing Schema"
        }
    except Exception as e:
        return {
            "messages": [AIMessage(content=f"Error retrieving schema: {e}")],
            "current_step": "Error in Schema Analysis"
        }

def fetch_lean_schema(connection):
    """Fetch only the necessary schema details for efficient LLM processing."""
    schema_query = """
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