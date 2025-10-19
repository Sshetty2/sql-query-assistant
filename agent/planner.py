"""Plan the SQL query by analyzing schema and user intent."""

import os
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage

from models.planner_output import PlannerOutput

from agent.state import State

load_dotenv()


def load_planner_output_schema():
    """Load the planner output JSON schema."""
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "models",
        "planner_output_schema.json",
    )
    with open(schema_path, "r") as f:
        return json.load(f)


def load_schema_model_description():
    """Load the schema model description."""
    schema_model_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "models", "schema_model.json"
    )
    with open(schema_model_path, "r") as f:
        return json.load(f)


def create_planner_prompt_template():
    """Create the prompt template for the planner."""

    system_message = """You are analyzing a natural language query against a database schema
to create a query execution plan.

## Context

We have a multi-step SQL query generation system. Your role in this pipeline is to:
1. Understand the user's intent from their natural language query
2. Analyze the provided database schema (tables, columns, relationships)
3. Create a structured plan that identifies:
   - Which tables are relevant and why
   - Which columns are needed (for display, filtering, grouping, or ordering)
   - What filters/conditions should be applied
   - How tables might be related (based on foreign keys and context)
   - Any time-based constraints
   - Ambiguities or assumptions being made

## Database Schema Structure

The schema you'll receive follows this format:
{schema_model}

Each table has:
- Basic column information (name, data type, nullability)
- Optional metadata (descriptions, primary keys, row counts)
- Optional foreign key relationships to other tables

## Your Output Format

Your plan should follow this JSON structure:
{output_schema}

## Important Considerations

- **Accuracy**: Only reference tables and columns that exist in the provided schema
- **Relationships**: Use the foreign_keys arrays to identify how tables connect
- **Confidence**: Provide honest confidence scores (0.0-1.0) based on clarity of the request
- **Ambiguities**: Note any assumptions you're making or information that's unclear
- **Decision**: Use "clarify" if critical information is missing; "proceed" if you can plan the query
- **Filters**: Distinguish between table-specific filters and global filters that span tables
- **Time Context**: If temporal language is used ("last 30 days", "this year"), capture it

## Strategy

Think through:
1. What is the user trying to accomplish?
2. Which tables contain the data they need?
3. How should those tables be connected?
4. What conditions narrow down the results?
5. How should results be grouped or ordered?
6. What assumptions am I making that might be wrong?"""

    user_message = """## User Query
{user_query}

## Available Database Schema
{schema}

## Query Parameters
{parameters}

Please analyze this query and create a structured execution plan."""

    return ChatPromptTemplate.from_messages(
        [("system", system_message), ("user", user_message)]
    )


def plan_query(state: State):
    """Create a structured query plan by analyzing schema and user intent."""
    try:
        user_query = state["user_question"]
        full_schema = state["schema"]

        # Get query parameters
        sort_order = state.get("sort_order", "Default")
        result_limit = state.get("result_limit", 0)
        time_filter = state.get("time_filter", "All Time")

        # Format parameters
        params = []
        if sort_order != "Default":
            params.append(f"- Sort order: {sort_order}")
        if result_limit > 0:
            params.append(f"- Result limit: {result_limit}")
        if time_filter != "All Time":
            params.append(f"- Time filter: {time_filter}")

        parameters_text = "\n".join(params) if params else "No additional parameters"

        # Load schemas
        schema_model = load_schema_model_description()
        output_schema = load_planner_output_schema()

        # Create prompt
        prompt_template = create_planner_prompt_template()

        # Format the prompt with schema descriptions
        formatted_prompt = prompt_template.format_messages(
            schema_model=json.dumps(schema_model, indent=2),
            output_schema=json.dumps(output_schema, indent=2),
            user_query=user_query,
            schema=json.dumps(full_schema, indent=2),
            parameters=parameters_text,
        )

        # Use structured output with JSON schema
        llm = ChatOpenAI(model=os.getenv("AI_MODEL"), temperature=0.7)

        structured_llm = llm.with_structured_output(PlannerOutput)

        # Get the plan
        plan = structured_llm.invoke(formatted_prompt)

        return {
            **state,
            "messages": [AIMessage(content="Query plan created successfully")],
            "planner_output": plan,
            "last_step": "planner",
        }

    except Exception as e:
        return {
            **state,
            "messages": [AIMessage(content=f"Error creating query plan: {str(e)}")],
            "last_step": "planner",
        }
