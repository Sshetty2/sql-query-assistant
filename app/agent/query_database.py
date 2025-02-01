from langchain_core.messages import HumanMessage
from agent.create_agent import create_sql_agent

def query_database(question: str, db, sort_order="Default", result_limit=0, time_filter="All Time"):
    """Run the query workflow for a given question."""
    agent = create_sql_agent(db)
    initial_state = {
        "messages": [HumanMessage(content=question)],
        "schema": "",
        "query": "",
        "result": "",
        "sort_order": sort_order,
        "result_limit": result_limit,
        "time_filter": time_filter,
        "current_step": "Starting Query Pipeline"
    }
    result = agent.invoke(initial_state)

    final_message = result["messages"][-1].content
    if "Query Successfully Executed" in final_message:
        return {
            "result": result.get("result"), 
            "query": result.get("query", ""), 
            "corrected_query": result.get("corrected_query", "")
        }
    return {
        "result": final_message,
        "query": {},
    }
