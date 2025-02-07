from langgraph.graph import StateGraph, END, START
from agent.state import State
from agent.analyze_schema import analyze_schema
from agent.generate_query import generate_query
from agent.execute_query import execute_query
from agent.create_sql_tools import create_sql_tools
from langchain.schema import AIMessage
from agent.handle_tool_error import handle_tool_error
import pyodbc
import os
from dotenv import load_dotenv
from typing import Literal
from database.connection import get_pyodbc_connection
from database.connection import init_database
from agent.refine_query import refine_query

load_dotenv()
use_test_db = os.getenv("USE_TEST_DB").lower() == "true"

def is_none_result(result):
    noneResult = False
    
    ## SQL-lite specific syntax
    if use_test_db:
        if result is None:
            return True
        if isinstance(result, list) and len(result) > 0:
            first_entry = result[0]
            if len(first_entry) > 0:
                noneResult = first_entry[0] == '[]'
        return noneResult

    ## SQL-Server specific syntax
    if isinstance(result, list) and len(result) > 0:
        first_entry = result[0]
        if len(first_entry) > 0:
            noneResult = first_entry[0] is None
    return noneResult


def should_continue(state: State) -> Literal["handle_error", "refine_query", "cleanup"]:
    """Determine the next step based on the current state."""
    
    messages = state["messages"]
    last_message = messages[-1]
    retry_count = state["retry_count"]
    refined_count = state["refined_count"] 
    result = state["result"]

    env_retry_count = int(os.getenv("RETRY_COUNT")) if os.getenv("RETRY_COUNT") else 3
    env_refine_count = int(os.getenv("REFINE_COUNT")) if os.getenv("REFINE_COUNT") else 2
    noneResult = is_none_result(result)

    # Handle errors
    if "Error" in last_message.content and retry_count < env_retry_count:
        return "handle_error"
    
    # If result is None and refinement is not exhausted, refine
    if noneResult and refined_count < env_refine_count:
        return "refine_query"
    
    # Default path if no errors/refinements are needed
    return "cleanup"

def create_sql_agent():
    workflow = StateGraph(State)
    
    db = init_database()
    db_connection = get_pyodbc_connection()
    tools = create_sql_tools(db)

    workflow.add_node("analyze_schema", lambda state: analyze_schema(state, tools, db_connection))
    workflow.add_node("generate_query", lambda state: generate_query(state))
    workflow.add_node("execute_query", lambda state: execute_query(state, tools, db_connection))
    workflow.add_node("handle_error", lambda state: handle_tool_error(state))
    workflow.add_node("cleanup", lambda state: cleanup_connection(state, db_connection))
    workflow.add_node("refine_query", lambda state: refine_query(state))

    workflow.add_edge(START, "analyze_schema")
    workflow.add_edge("analyze_schema", "generate_query")

    workflow.add_conditional_edges("execute_query", should_continue)

    workflow.add_edge("generate_query", "execute_query")
    workflow.add_edge("handle_error", "execute_query")
    workflow.add_edge("refine_query", "execute_query")
    workflow.add_edge("cleanup", END)

    return workflow.compile()

def cleanup_connection(state: State, connection):
    """Cleanup node to ensure connection is closed"""

    try:
        connection.close()
    except Exception as e:
        print(f"Error closing connection: {e}")
    return state

