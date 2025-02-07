from langchain_core.messages import HumanMessage
from agent.create_agent import create_sql_agent

def query_database(question: str, sort_order="Default", result_limit=0, time_filter="All Time"):
    """Run the query workflow for a given question."""
    agent = create_sql_agent()
    
    initial_state = {
        "messages": [HumanMessage(content=question)],
        "schema": "",
        "query": "",
        "result": "",
        "sort_order": sort_order,
        "result_limit": result_limit,
        "time_filter": time_filter,
        "last_step": "start_query_pipeline",
        "user_question": question,
        "retry_count": 0,
        "refined_count": 0,
        "error_history": [],
        "last_attempt_time": None,
        "refined_queries": [],
        "corrected_queries": [],
    }

    result = agent.invoke(initial_state)

    return result