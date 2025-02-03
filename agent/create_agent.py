from langgraph.graph import StateGraph, END, START
from agent.state import State
from agent.analyze_schema import analyze_schema
from agent.generate_query import generate_query
from agent.execute_query import execute_query
from agent.create_sql_tools import create_sql_tools
from langchain.schema import AIMessage
from agent.handle_tool_error import handle_tool_error
import streamlit as st
import pyodbc
import os
from dotenv import load_dotenv
from typing import Literal

load_dotenv()

connection_params = [
    "DRIVER={ODBC Driver 17 for SQL Server}",
    f"SERVER={os.getenv('DB_SERVER')}",
    f"DATABASE={os.getenv('DB_NAME')}",
]

if os.getenv('DB_USER') and os.getenv('DB_PASSWORD'):
    connection_params.extend([
        f"UID={os.getenv('DB_USER')}",
        f"PWD={os.getenv('DB_PASSWORD')}"
    ])
else:
    connection_params.append("Trusted_Connection=yes")

# Join all parameters with semicolons
connection_string = ";".join(connection_params)

def debug_node(state: State):
    """Debug node to print current state and update status"""
    current_step = state["current_step"]
    
    # if 'status' in st.session_state:
    #     status = st.session_state.status
    #     status.update(label=current_step, state="running")
    
    return {
        "messages": [AIMessage(content=f"Step completed: {current_step}")],
        **state
    }

def should_continue(state: State) -> Literal[END, "debug_execute", "handle_error"]:
    """Determine the next step based on the current state."""
    messages = state["messages"]
    last_message = messages[-1]
    retry_count = state.get("retry_count", 0)
    
    # Stop if we've tried 3 times
    if retry_count >= 3:
        return END
    
    # If we hit rate limit, end the process
    if "Rate limit timeout" in last_message.content:
        return END  
    if "corrected_query" in state and state["corrected_query"]:
        return "debug_execute"
    if "Error" in last_message.content:
        return "handle_error"
    elif "Query Successfully Executed" in last_message.content:
        return "debug_execute"
    return END

def create_sql_agent(db):
    workflow = StateGraph(State)
    
    db_connection = pyodbc.connect(connection_string)
    
    tools = create_sql_tools(db)

    workflow.add_node("analyze_schema", lambda state: analyze_schema(state, tools, db_connection))
    workflow.add_node("generate_query", lambda state: generate_query(state))
    workflow.add_node("execute_query", lambda state: execute_query(state, tools, db_connection))
    workflow.add_node("handle_error", handle_tool_error)
    workflow.add_node("cleanup", lambda state: cleanup_connection(state, db_connection))
    
    workflow.add_node("debug_schema", debug_node)
    workflow.add_node("debug_query", debug_node)
    workflow.add_node("debug_execute", debug_node)

    workflow.add_edge(START, "analyze_schema")
    workflow.add_edge("analyze_schema", "debug_schema")
    workflow.add_edge("debug_schema", "generate_query")
    workflow.add_edge("generate_query", "debug_query")
    workflow.add_edge("debug_query", "execute_query")

    workflow.add_conditional_edges(
        "execute_query",
        should_continue,
    )
    
    workflow.add_edge("handle_error", "execute_query")
    
    workflow.add_edge("debug_execute", "cleanup")
    workflow.add_edge("cleanup", END)

    return workflow.compile()

def cleanup_connection(state: State, connection):
    """Cleanup node to ensure connection is closed"""
    try:
        connection.close()
    except Exception as e:
        print(f"Error closing connection: {e}")
    return state

