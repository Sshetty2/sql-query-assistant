from typing import Dict, Any
from pydantic import BaseModel, Field
from agent.state import State
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv
from agent.generate_query import get_json_format_instructions, get_sql_return_instructions

load_dotenv()

class QueryRefinement(BaseModel):
    reasoning: str = Field(description="Explanation of how and why the query was refined")
    sql_query: str = Field(description="The refined SQL query")

def refine_query(state: State) -> Dict[str, Any]:
    """
    Please refine the SQL query because the initial results are None.
    Do your best to broaden and the query.
    """
    original_query = state["query"]
    schema_info = state["schema"]
    user_question = state["user_question"]

    refined_queries = state["refined_queries"]

    previous_attempts = ""
    if refined_queries:
        previous_attempts = "Previous refinement attempts that still returned no results:\n"
        for i, query in enumerate(refined_queries, 1):
            previous_attempts += f"{i}. {query}\n"

    model = ChatOpenAI(model=os.getenv("AI_MODEL_REFINE"), temperature=0.7)
    structured_model = model.with_structured_output(QueryRefinement)

    json_instructions = get_json_format_instructions()
    sql_return_instructions = get_sql_return_instructions()

    prompt = f"""
    Please help refine and broaden this SQL query that returned no results.
    Original question: {user_question}
    Original query: {original_query}
    Truncated Database schema: {schema_info}
    
    {previous_attempts}

    You may need to change the content of the query so that it makes logical sense. Consider:
    1. Broadening WHERE clauses
    2. Using LIKE instead of exact matches
    3. Removing overly restrictive conditions
    4. Checking for NULL values
    5. Using OR conditions where appropriate

    {json_instructions}

    {sql_return_instructions}
    """

    response = structured_model.invoke(prompt)

    return {
        **state,
        "messages": [AIMessage(content=f"Query refined for broader results")],
        "query": response.sql_query,
        "last_step": "refine_query",
        "refined_queries": state["refined_queries"] + [original_query],
        "refined_reasoning": state["refined_reasoning"] + [response.reasoning],
        "refined_count": state["refined_count"] + 1,
    } 