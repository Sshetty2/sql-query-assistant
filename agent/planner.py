"""Plan the SQL query by analyzing schema and user intent."""

import os
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from models.planner_output import PlannerOutput

from agent.state import State

load_dotenv()


def load_planner_output_example():
    """Load the planner output example JSON structure."""
    example_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "models",
        "planner_output.json",
    )
    with open(example_path, "r") as f:
        return json.load(f)


def load_schema_model_description():
    """Load the schema model description."""
    schema_model_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "models", "schema_model.json"
    )
    with open(schema_model_path, "r") as f:
        return json.load(f)


def load_domain_guidance():
    """Load domain-specific guidance if available."""
    guidance_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "models", "domain_guidance.json"
    )
    try:
        if os.path.exists(guidance_path):
            with open(guidance_path, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load domain guidance: {e}")
    return None


def create_planner_prompt_template(mode: str = None):
    """Create the prompt template for the planner.

    Args:
        mode: Optional mode - "update" for plan updates, "rewrite" for full replan, None for initial
    """

    if mode == "update":
        system_message = """You are revising an existing SQL query execution plan based on user feedback.

            ## Context
            You previously created a query plan, and now the user has requested modifications.
            Your job is to UPDATE the existing plan incrementally, not create a new one from scratch.

            ## Your Task
            1. Review the previous plan and understand what was already decided
            2. Read the routing instructions carefully - they specify what needs to change
            3. Make ONLY the changes requested, preserving the rest of the plan
            4. Ensure the updated plan remains internally consistent

            ## What to Preserve
            - Keep the same tables unless instructions say otherwise
            - Keep existing joins unless they need modification
            - Keep existing columns unless specifically adding/removing
            - Maintain the overall query structure

            ## What to Update
            - Add/remove/modify filters as instructed
            - Add/remove columns as requested
            - Adjust joins if needed for new requirements
            - Update confidence if assumptions have changed

            ## Return ONLY a JSON object that conforms to the following json structure:
            {planner_example}"""

    elif mode == "rewrite":
        system_message = """You are creating a NEW SQL query execution plan based on an updated user request.

            ## Context
            The user had a previous query, but now wants something significantly different.
            While you should be aware of the previous plan for context, you need to create
            a FRESH plan from scratch that addresses the new request.

            ## Your Task
            1. Understand the new user request and routing instructions
            2. Review the previous plan to understand context (but don't be constrained by it)
            3. Analyze the full database schema
            4. Create a completely new plan optimized for the new request

            ## Considerations
            - This is a major change - different tables, different intent, or different domain
            - Start fresh but learn from previous assumptions/ambiguities
            - Use the full schema to make the best decisions
            - Don't force-fit the old plan structure onto the new request

            ## Return ONLY a JSON object that conforms to the following json structure:
            {planner_example}"""

    else:  # Initial mode (None)
        system_message = """You are analyzing a natural language query against a SQL database schema
            to create a query execution plan.

            We have a multi-step SQL query generation system.

            Your role in this pipeline is to:

            1. Understand the user's intent from their natural language query
            2. Analyze the provided database schema (tables, columns, relationships)
            3. Create a structured plan that identifies:
            - Which tables are relevant and why
            - Which columns are needed (for display, filtering, grouping, or ordering)
            - What filters/conditions should be applied
            - How tables might be related (based on foreign keys and context)
            - Any time-based constraints
            - Ambiguities or assumptions being made

            ## Return ONLY a JSON object that conforms to the following json structure:
            {planner_example}"""

    # Common continuation of system message
    system_message += """

            ## Domain-Specific Guidance

            {domain_guidance}

            ## Advanced SQL Features (Use When Needed)

            The planner supports advanced SQL features. Use them ONLY when the user query requires:

            **Aggregations (GROUP BY):**
            - When user asks for totals, counts, averages, min/max (e.g., "total sales by company")
            - Set `group_by` with:
              - `group_by_columns`: Columns to group by (typically dimensions like company name, category)
              - `aggregates`: List of aggregate functions (COUNT, SUM, AVG, MIN, MAX)
              - `having_filters`: Filters on aggregated results (e.g., "companies with more than 100 sales")
            - Example: "Show total sales by company" → GROUP BY company, SUM(sales)

            **Window Functions:**
            - When user asks for rankings, running totals, or row numbers (e.g., "rank users by sales")
            - Set `window_functions` with function, partition_by, order_by, and alias
            - Example: "Rank employees by salary within each department" → ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC)

            **Subqueries (in filters):**
            - When filtering based on results from another query (e.g., "users from top companies")
            - Set `subquery_filters` for WHERE col IN (SELECT...) patterns
            - Keep subqueries simple - single table with filters
            - Example: "Users from companies with >50 employees" → WHERE CompanyID IN (SELECT ID FROM Companies WHERE EmployeeCount > 50)

            **CTEs (WITH clauses):**
            - For complex queries that benefit from intermediate results
            - Use sparingly - only when query logic is clearer with a CTE
            - Set `ctes` with name, selections, joins, filters, and optional group_by

            **Important:** Leave these fields empty (null or []) when not needed. Most queries don't require them.

            ## Filter Operator Examples

            When creating FilterPredicate objects in the `filters` array, use these operator patterns:

            - Equality: {{"op": "=", "value": "Cisco"}}
            - Inequality: {{"op": "!=", "value": "Active"}}
            - Comparison: {{"op": ">", "value": 100}}
            - Between: {{"op": "between", "value": [0, 100]}} — MUST be array [low, high]
            - In list: {{"op": "in", "value": ["Cisco", "Microsoft", "Google"]}} — MUST be array
            - Not in list: {{"op": "not_in", "value": ["Inactive", "Suspended"]}} — MUST be array
            - Like pattern: {{"op": "like", "value": "%cisco%"}} — Use for pattern matching (case-insensitive in SQL Server)
            - Starts with: {{"op": "starts_with", "value": "CVE-"}}
            - Ends with: {{"op": "ends_with", "value": ".com"}}
            - Is null: {{"op": "is_null", "value": null}}
            - Is not null: {{"op": "is_not_null", "value": null}}

            ## Database Schema Structure

            The schema you'll receive follows this format:

            {schema_model}

            ## Hard Rules (MUST follow)

            1. **Exact names only**: Use table/column names exactly as they appear in the schema. Never invent names.

            2. **Always specify joins**: If you select 2+ tables in `selections`, you MUST populate `join_edges` with explicit column-to-column join conditions. Use foreign keys from the schema to identify the correct columns (e.g., from_table.CompanyID = to_table.ID).

            3. **Include lookup tables for foreign keys**: When selecting columns that are foreign keys (fields ending in ID like CompanyID, UserID, etc.), you MUST also include the referenced table in `selections` to retrieve human-readable names/descriptions. Add the corresponding join edge and include the name column from the related table with role="projection".

            4. **Completeness of joins**: Every table referenced in `join_edges` must also appear in `selections`.

            5. **Join-only tables**: If a table is needed only to connect others (not for data display), set `include_only_for_join = true` and leave its `columns` list empty.

            6. **Keep it minimal**: Use the smallest number of tables required (prefer ≤ 6 tables).

            7. **Localize filters**: Put a filter in the table's `filters` array where the column lives; use `global_filters` only if the constraint genuinely spans multiple tables.

            8. **No extras**: Do not include grouping, ordering, time context, or instructions for later agents. Focus only on table selection, columns, filters, and joins.

            IMPORTANT: Do NOT create filter predicates for the "Time filter" parameter (e.g., "Last 30 Days", "Last 7 Days"). These will be handled by a downstream agent. Only include filters that are explicitly mentioned in the user's natural language query (e.g., "active users", "vendor = Cisco").

            9. **Confidence bounds**: All confidence values must be between 0.0 and 1.0.

            10. **Time filter handling**: When a "Time filter" parameter is provided (e.g., "Last 30 Days"), do NOT create filter predicates. Instead, include relevant timestamp columns (CreatedOn, UpdatedOn, etc.) in the selections with role="projection" or role="filter" to indicate they may be used for time filtering. Let the downstream agent handle the actual date range calculation.

            11. **If unclear → clarify**: If critical information is missing, set `decision = "clarify"` and populate `ambiguities` with concrete questions.

            ## Reasoning Hints

            - **Create explicit joins**: For every pair of related tables in `selections`, add a `join_edges` entry specifying the exact columns to join (from_column and to_column). Look for foreign keys in the schema's `foreign_keys` arrays.
            - **Prefer foreign keys**: Use the `foreign_keys` arrays and `...ID` column naming patterns to identify relationships. For example, if Table A has a foreign key "CompanyID" and Table B has a primary key "ID", create a join edge: {{from_table: "TableA", from_column: "CompanyID", to_table: "TableB", to_column: "ID"}}.
            - **Auto-join for human-readable names**: When a table has a foreign key (e.g., CompanyID, UserID, ProductID), automatically include the related table and join to it to retrieve the name/description column. For example, if selecting from tb_Users which has CompanyID, include tb_Company in selections and add a join edge to retrieve the company Name for display purposes.
            - **Choose carefully**: When multiple candidate tables exist, choose the one with stronger evidence (metadata, foreign keys) and higher confidence
            - **Ask when stuck**: If the user mentions a column you can't find, switch to "clarify" and ask for the exact field or acceptable alternative

            ## Final Checklist (validate before responding)

            ✓ If 2+ tables in `selections`, `join_edges` must be populated with explicit joins
            ✓ All tables in `join_edges` exist in `selections`
            ✓ Each join edge specifies both from_column and to_column (not just table names)
            ✓ Bridge/lookup tables without projections have `include_only_for_join = true`
            ✓ No columns appear from tables that aren't in `selections`
            ✓ No invented table or column names
            ✓ Output is valid PlannerOutput JSON and nothing else
            """

    # User message varies by mode
    if mode == "update":
        user_message = """## Previous Plan
{previous_plan}

## Routing Instructions
{router_instructions}

## User Query History
{conversation_history}

## Latest User Request
{user_query}

## Query Parameters
{parameters}

Please update the plan according to the routing instructions."""

    elif mode == "rewrite":
        user_message = """## Previous Plan (for context)
{previous_plan}

## Routing Instructions
{router_instructions}

## User Query History
{conversation_history}

## Latest User Request
{user_query}

## Available Database Schema
{schema}

## Query Parameters
{parameters}

Please create a new plan for the updated request."""

    else:  # Initial mode
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

        # Check for router mode (conversational flow)
        router_mode = state.get("router_mode")
        router_instructions = state.get("router_instructions", "")

        # Get query parameters
        sort_order = state["sort_order"]
        result_limit = state["result_limit"]
        time_filter = state["time_filter"]

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
        planner_example = load_planner_output_example()
        domain_guidance = load_domain_guidance()

        # Format domain guidance text
        if domain_guidance:
            domain_text = f"""This system works with a {domain_guidance.get('domain', 'specialized')} domain.

**Terminology Mappings:**
"""
            for term, info in domain_guidance.get("terminology_mappings", {}).items():
                domain_text += (
                    f"\n- **'{term}'** → {info['refers_to']}: {info['description']}"
                )
                domain_text += f"\n  Primary table: {info['primary_table']}"
                if info.get("related_tables"):
                    domain_text += (
                        f"\n  Related tables: {', '.join(info['related_tables'])}"
                    )

            if domain_guidance.get("important_fields"):
                domain_text += "\n\n**Important Fields:**\n"
                for field, desc in domain_guidance.get("important_fields", {}).items():
                    domain_text += f"- {field}: {desc}\n"

            if domain_guidance.get("default_behaviors"):
                domain_text += "\n**Default Behaviors:**\n"
                for behavior, desc in domain_guidance.get(
                    "default_behaviors", {}
                ).items():
                    domain_text += f"- {desc}\n"
        else:
            domain_text = "No domain-specific guidance available. Use general database query planning principles."

        # Create prompt (with mode)
        prompt_template = create_planner_prompt_template(mode=router_mode)

        # Format the prompt based on mode
        format_params = {
            "planner_example": json.dumps(planner_example, indent=2),
            "domain_guidance": domain_text,
            "schema_model": json.dumps(schema_model, indent=2),
            "user_query": user_query,
            "parameters": parameters_text,
        }

        # Add mode-specific parameters
        if router_mode in ["update", "rewrite"]:
            # Get conversation history
            user_questions = state.get("user_questions", [])
            conversation_history = "\n".join(
                [f"{i+1}. {q}" for i, q in enumerate(user_questions[:-1])]
            )

            # Get previous plan
            planner_outputs = state.get("planner_outputs", [])
            previous_plan = (
                json.dumps(planner_outputs[-1], indent=2)
                if planner_outputs
                else "No previous plan available"
            )

            format_params["conversation_history"] = conversation_history
            format_params["previous_plan"] = previous_plan
            format_params["router_instructions"] = router_instructions

            # Only include schema for rewrite mode
            if router_mode == "rewrite":
                format_params["schema"] = json.dumps(full_schema, indent=2)
        else:
            # Initial mode - include full schema
            format_params["schema"] = json.dumps(full_schema, indent=2)

        formatted_prompt = prompt_template.format_messages(**format_params)

        # Use structured output with JSON schema
        llm = ChatOpenAI(model=os.getenv("AI_MODEL"), temperature=0.7)
        structured_llm = llm.with_structured_output(PlannerOutput)

        # Get the plan
        plan = structured_llm.invoke(formatted_prompt)

        if plan is None:
            return {
                **state,
                "messages": [AIMessage(content="Error creating query plan")],
                "last_step": "planner",
            }

        # Append to planner_outputs history
        planner_outputs = state.get("planner_outputs", [])
        # Convert Pydantic model to dict for storage
        plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else plan
        planner_outputs = planner_outputs + [plan_dict]

        return {
            **state,
            "messages": [AIMessage(content="Query plan created successfully")],
            "planner_output": plan,
            "planner_outputs": planner_outputs,
            "last_step": "planner",
        }

    except Exception as e:
        print(f"EXCEPTION IN PLAN_QUERY: {str(e)}")
        import traceback

        traceback.print_exc()
        return {
            **state,
            "messages": [AIMessage(content=f"Error creating query plan: {str(e)}")],
            "last_step": "planner",
        }
