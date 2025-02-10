import json
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Any
from dotenv import load_dotenv
from agent.query_database import query_database

load_dotenv()

SORT_ORDER_OPTIONS = Literal["Default", "Ascending", "Descending"]
TIME_FILTER_OPTIONS = Literal[
    "All Time", "Last 24 Hours", "Last 7 Days", "Last 30 Days", "Last Year"
]

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


def parse_query_result(result):
    """Parse the nested query result into JSON if it exists."""
    try:
        if not result:
            return None

        if result and result[0] and result[0][0]:
            json_str = result[0][0]
            if json_str:
                return json.loads(json_str)

        return result
    except (IndexError, json.JSONDecodeError) as e:
        print(f"Error parsing query result: {e}")
        return None


class QueryRequest(BaseModel):
    """Represents a natural language query request for SQL generation."""

    prompt: str = Field(
        ...,  # Required
        title="Query Prompt",
        description="Natural language query to be converted into SQL.",
        examples=[
            "Show all users who logged in last week",
            "List the top 5 users with the most login attempts",
            "Show all vulnerabilities found in the last 30 days",
        ],
    )
    sort_order: Optional[SORT_ORDER_OPTIONS] = Field(
        default="Default",
        title="Sort Order",
        description="Sorting preference for query results.",
        examples=["Default", "Ascending", "Descending"],
    )
    result_limit: Optional[int] = Field(
        default=0,
        title="Result Limit",
        description="Maximum number of results to return (0 for no limit).",
        ge=0,
        examples=[0, 5, 10, 25, 100],
    )
    time_filter: Optional[TIME_FILTER_OPTIONS] = Field(
        default="All Time",
        title="Time Filter",
        description="Filter results based on a specific time range.",
        examples=[
            "All Time",
            "Last 24 Hours",
            "Last 7 Days",
            "Last 30 Days",
            "Last Year",
        ],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "Show me the top 5 users with most login attempts",
                "sort_order": "Descending",
                "result_limit": 5,
                "time_filter": "Last 30 Days",
            }
        }


class QueryResponse(BaseModel):
    """Response model for the query endpoint."""

    messages: List[str] = Field(
        description="List of messages showing the progression of query processing"
    )
    user_question: str = Field(description="Original question asked by the user")
    query: str = Field(description="Final SQL query that was executed")
    result: Optional[Any] = Field(
        description="JSON representation of the query results"
    )
    sort_order: str = Field(description="Sort order used for the query")
    result_limit: int = Field(description="Maximum number of results requested")
    time_filter: str = Field(description="Time filter applied to the query")
    last_step: str = Field(description="Last step executed in the query pipeline")
    corrected_queries: List[str] = Field(
        default_factory=list,
        description="List of queries that were corrected due to errors",
    )
    refined_queries: List[str] = Field(
        default_factory=list,
        description="List of queries that were refined to improve results",
    )
    retry_count: int = Field(description="Number of times the query was retried")
    refined_count: int = Field(description="Number of times the query was refined")
    error_history: List[str] = Field(
        default_factory=list,
        description="List of errors encountered during query execution",
    )
    refined_reasoning: List[str] = Field(
        default_factory=list, description="Explanations for why queries were refined"
    )
    last_attempt_time: Optional[datetime] = Field(
        description="Timestamp of the last query attempt"
    )
    tables_used: List[str] = Field(
        description="List of database tables referenced in the query"
    )


@app.post(
    "/query",
    response_model=QueryResponse,
    summary="Generate and Execute SQL Query from Natural Language",
    description="""
    Converts a natural language question into an executable SQL query and returns the results.

    The endpoint:
    - Analyzes the question and relevant schema
    - Generates an appropriate SQL query
    - Executes the query against the database
    - Refines the query if needed for better results
    - Returns both the query process details and results

    Features:
    - **Smart Query Generation**: Converts natural language to SQL
    - **Query Refinement**: Automatically improves queries that return no results
    - **Error Handling**: Includes detailed error history and corrections
    - **Process Transparency**: Returns all steps in the query generation process

    The response includes:
    - Messages showing the query processing steps
    - The final SQL query used
    - Query results in JSON format
    - Details about any refinements or corrections made
    - List of database tables referenced
    """,
)
async def process_query(request: QueryRequest) -> QueryResponse:
    """Process a natural language query and return both the SQL query and results."""
    try:
        full_query_results = query_database(
            request.prompt,
            sort_order=request.sort_order,
            result_limit=request.result_limit,
            time_filter=request.time_filter,
        )

        message_contents = [
            message.content for message in full_query_results["messages"]
        ]
        parsed_result = parse_query_result(full_query_results["result"])
        tables_used = [
            table["table_name"] for table in full_query_results.get("schema", [])
        ]

        response = {
            **full_query_results,
            "messages": message_contents,
            "result": parsed_result,
            "tables_used": tables_used,
        }

        response.pop("schema", None)

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", summary="Health Check", description="Returns the API status.")
def health_check():
    return {"message": "SQL Query Assistant API is running!"}
