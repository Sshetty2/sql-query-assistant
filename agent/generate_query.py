from agent.state import State 
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
import os
from dotenv import load_dotenv

load_dotenv()

def get_sql_return_instructions():
    """Get instructions for returning only the raw SQL query."""
    return """
    Important: Return ONLY the raw SQL query without any markdown formatting, quotes, or code blocks.
    For example, instead of:
    ```sql
    SELECT * FROM table
    ```
    Just return:
    SELECT * FROM table
    """

def get_json_format_instructions():
    """Get database-specific JSON formatting instructions."""
    if os.getenv('USE_TEST_DB', '').lower() == 'true':
        return """
        The Database is SQLite.
        Format the results as JSON using SQLite's json functions:
        SELECT json_group_array(
            json_object(
                'column1', column1,
                'column2', column2
            )
        ) AS json_result
        FROM (
            <your query here>
        );
        """
    else:
        return """
        The Database is SQL Server.
        Also, please append 'FOR JSON AUTO' to the query to format the result as JSON
        and wrap the query in another select statement that returns json.

        select (
            <query> FOR JSON AUTO
        ) as json
        """

def generate_query(state: State):
    """Generate SQL query based on the question and schema."""
    try:
        question = state["messages"][0].content  # Get the original question
        schema = state["schema"]  # Schema information
        
        sort_order = state["sort_order"]
        result_limit = state["result_limit"]
        time_filter = state["time_filter"]

        query_modifications = []
        
        if sort_order != "Default":
            query_modifications.append(f"The results should be ordered {sort_order.lower()}")
            
        if result_limit > 0:
            query_modifications.append(f"Limit the results to {result_limit} records")
            
        if time_filter != "All Time":
            days_map = {
                "Last 30 Days": 30,
                "Last 60 Days": 60,
                "Last 90 Days": 90,
                "Last Year": 365
            }
            days = days_map.get(time_filter)
            if days:
                query_modifications.append(
                    f"Filter the results to only include records from the last {days} days "
                    "using appropriate date/timestamp columns"
                )

        modifications_text = "\n".join([f"- {mod}" for mod in query_modifications])
        
        json_instructions = get_json_format_instructions()
        
        prompt = f"""Given this truncated database schema:
        {schema}

        Generate a SQL query to answer this question: {question}

        {get_sql_return_instructions()}

        Additional requirements:
        {modifications_text if modifications_text else ""}

        {json_instructions}
        """

        llm = ChatOpenAI(model=os.getenv("AI_MODEL"), temperature=0.3)
        response = llm.invoke(prompt)
        
        query = response.content.strip()

        return {
            **state,
            "messages": [AIMessage(content=f"Generated SQL Query")],
            "query": query,
            "last_step": "generate_query",
        }
    except Exception as e:
        return {
            **state,
            "messages": [AIMessage(content=f"Error generating query: {str(e)}")],
            "last_step": "generate_query",
        }
        