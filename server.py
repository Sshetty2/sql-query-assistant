from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal
import pyodbc
import os
from langchain_community.utilities import SQLDatabase
from dotenv import load_dotenv
from agent.query_database import query_database

# Load environment variables
load_dotenv()

# Define constants for valid options
SORT_ORDER_OPTIONS = Literal["Default", "Ascending", "Descending"]
TIME_FILTER_OPTIONS = Literal["All Time", "Last 24 Hours", "Last 7 Days", "Last 30 Days", "Last Year"]

# Initialize FastAPI app
app = FastAPI(
    title="SQL Query Assistant API",
    description="""
    This API converts natural language queries into SQL queries and executes them on an SQL Server database. 
    - Supports **sorting, result limits, and time filters** for enhanced querying.
    - Uses **LangChain-powered SQL generation** for natural language understanding.
    - Designed for **Wiznucleus data analysis**.
    """,
    version="1.0.0",
    contact={
        "name": "Wiznucleus Dev Team",
        "email": "support@wiznucleus.com",
    },
)

# Request model
class QueryRequest(BaseModel):
    """Represents a natural language query request for SQL generation."""
    
    prompt: str = Field(
        ...,  # Required
        title="Query Prompt",
        description="Natural language query to be converted into SQL.",
        examples=[
            "Show all users who logged in last week",
            "List the top 5 users with the most login attempts",
            "Show all vulnerabilities found in the last 30 days"
        ]
    )
    sort_order: Optional[SORT_ORDER_OPTIONS] = Field(
        default="Default",
        title="Sort Order",
        description="Sorting preference for query results.",
        examples=["Default", "Ascending", "Descending"]
    )
    result_limit: Optional[int] = Field(
        default=0,
        title="Result Limit",
        description="Maximum number of results to return (0 for no limit).",
        ge=0,  # Ensure value is ≥ 0
        examples=[0, 5, 10, 25, 100]
    )
    time_filter: Optional[TIME_FILTER_OPTIONS] = Field(
        default="All Time",
        title="Time Filter",
        description="Filter results based on a specific time range.",
        examples=["All Time", "Last 24 Hours", "Last 7 Days", "Last 30 Days", "Last Year"]
    )

    class Config:
        schema_extra = {
            "example": {
                "prompt": "Show me the top 5 users with most login attempts",
                "sort_order": "Descending",
                "result_limit": 5,
                "time_filter": "Last 30 Days"
            }
        }

@app.post("/query", summary="Generate SQL Query from Natural Language", description="""
    Converts a **natural language question** into an **executable SQL query**.
    
    Supports:
    - **Sorting:** Ascending/Descending order
    - **Limiting results:** Specify a max number of records
    - **Time filtering:** Filter results by time range (e.g., last 30 days)

    Example Input:
    ```json
    {
        "prompt": "List the top 5 users with the most login attempts",
        "sort_order": "Descending",
        "result_limit": 5,
        "time_filter": "Last 30 Days"
    }
    ```
    
    Example Response:
    ```json
    {
        "query": "SELECT TOP 5 UserID, COUNT(*) AS LoginAttempts FROM tb_UserLogs WHERE Timestamp >= DATEADD(day, -30, GETDATE()) GROUP BY UserID ORDER BY LoginAttempts DESC"
    }
    ```
""")
async def process_query(request: QueryRequest):
    """Process a natural language query and return SQL query."""
    try:
        result = query_database(
            request.prompt,
            sort_order=request.sort_order,
            result_limit=request.result_limit,
            time_filter=request.time_filter
        )

        return {
            "query": result["query"]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@app.get("/", summary="Health Check", description="Returns the API status.")
def health_check():
    return {"message": "SQL Query Assistant API is running!"}
