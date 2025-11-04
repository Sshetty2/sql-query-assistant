"""Plan the SQL query by analyzing schema and user intent."""

import os
import json
import re
from datetime import datetime
from textwrap import dedent
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.exceptions import OutputParserException
from models.planner_output import PlannerOutput
from models.planner_output_minimal import PlannerOutputMinimal
from models.planner_output_standard import PlannerOutputStandard
from utils.llm_factory import is_using_ollama, get_model_for_stage
from utils.logger import get_logger, log_execution_time

from agent.state import State

load_dotenv()
logger = get_logger()

# Maximum number of retries for output parsing errors
MAX_PARSING_RETRIES = 3


def auto_fix_join_edges(planner_output_dict: dict) -> dict:
    """
    Auto-add missing tables referenced in join_edges to selections.

    This fixes the most common planner error where LLMs create join_edges
    referencing tables not included in the selections array.

    Args:
        planner_output_dict: Raw planner output dictionary (before Pydantic validation)

    Returns:
        Fixed planner output dictionary with missing tables added to selections
    """
    # Get currently selected tables
    selections = planner_output_dict.get("selections", [])
    selected_tables = {sel.get("table") for sel in selections if sel.get("table")}

    # Get all tables referenced in join_edges
    join_tables = set()
    for edge in planner_output_dict.get("join_edges", []):
        if edge.get("from_table"):
            join_tables.add(edge["from_table"])
        if edge.get("to_table"):
            join_tables.add(edge["to_table"])

    # Find tables in joins but not in selections
    missing_tables = join_tables - selected_tables

    # Auto-add missing tables to selections
    if missing_tables:
        logger.info(
            "Auto-fixing join_edges: Adding missing tables to selections",
            extra={
                "missing_tables": list(missing_tables),
                "selected_tables": list(selected_tables),
                "join_tables": list(join_tables),
            },
        )

        for table in missing_tables:
            # Add table to selections with lower confidence since it was auto-added
            selections.append(
                {
                    "table": table,
                    "confidence": 0.7,  # Lower confidence for auto-added tables
                    "columns": [],  # No specific columns needed
                    "include_only_for_join": True,  # Table added only for joining
                    "filters": [],
                }
            )

        planner_output_dict["selections"] = selections

    return planner_output_dict


def repair_planner_output(planner_output_dict: dict) -> dict:
    """
    Repair common validation issues in planner output before Pydantic validation.

    This function adds missing required fields with sensible defaults and fixes
    common formatting issues that cause Pydantic validation errors.

    Fixes applied:
    - Add missing 'intent_summary' field
    - Add missing 'decision' field
    - Add missing 'selections' field
    - Add missing 'confidence' fields in selections
    - Convert string columns to dict objects
    - Remove extra forbidden fields

    Args:
        planner_output_dict: Raw planner output dictionary (before Pydantic validation)

    Returns:
        Repaired planner output dictionary
    """
    # Add intent_summary if missing
    if "intent_summary" not in planner_output_dict:
        planner_output_dict["intent_summary"] = "Query plan generated"
        logger.info("Repair: Added missing intent_summary field")

    # Add decision if missing
    if "decision" not in planner_output_dict:
        planner_output_dict["decision"] = "proceed"
        logger.info("Repair: Added missing decision field")

    # Add selections if missing
    if "selections" not in planner_output_dict:
        # This is a critical error - try to infer from other fields
        planner_output_dict["selections"] = []
        logger.warning(
            "Repair: Added missing selections field (will likely fail downstream)"
        )

    # Fix selections array
    selections = planner_output_dict.get("selections", [])
    for i, sel in enumerate(selections):
        # Add confidence if missing
        if "confidence" not in sel:
            sel["confidence"] = 0.7

        # Fix columns format - convert strings to dicts
        if "columns" in sel:
            fixed_columns = []
            for col in sel["columns"]:
                if isinstance(col, str):
                    # Convert string to dict
                    fixed_columns.append({"column": col, "role": "projection"})
                    logger.info(
                        f"Repair: Converted string column '{col}' to dict in selection {i}"
                    )
                else:
                    fixed_columns.append(col)
            sel["columns"] = fixed_columns

        # Remove forbidden fields that exist in older schema versions
        forbidden_fields = ["conditions", "date_filters"]
        for field in forbidden_fields:
            if field in sel:
                del sel[field]
                logger.info(
                    f"Repair: Removed forbidden field '{field}' from selection {i}"
                )

    planner_output_dict["selections"] = selections

    # Remove forbidden top-level fields
    top_level_forbidden = [
        "filters",
        "aggregations",
        "join_only_tables",
        "date_filters",
    ]
    for field in top_level_forbidden:
        if field in planner_output_dict:
            del planner_output_dict[field]
            logger.info(f"Repair: Removed forbidden top-level field '{field}'")

    return planner_output_dict


def extract_validation_error_details(error_message: str) -> dict:
    """
    Extract structured validation error details from Pydantic validation error.

    Args:
        error_message: The error message from OutputParserException

    Returns:
        dict with extracted error details
    """
    error_info = {
        "error_type": "unknown",
        "missing_tables": [],
        "problematic_field": None,
        "raw_message": error_message,
    }

    # Extract validation error type and details
    # Example: "join_edges reference tables not in selections: ['tb_Company']"
    if "join_edges reference tables not" in error_message:
        error_info["error_type"] = "join_edges_invalid_tables"
        error_info["problematic_field"] = "join_edges"

        # Extract missing tables using regex
        match = re.search(r"\['([^']+)'(?:,\s*'([^']+)')*\]", error_message)
        if match:
            error_info["missing_tables"] = [g for g in match.groups() if g]

    elif "join_edges reference tables not present in selections" in error_message:
        error_info["error_type"] = "join_edges_missing_selections"
        error_info["problematic_field"] = "join_edges"

        # Extract missing tables
        match = re.search(r"\['([^']+)'(?:,\s*'([^']+)')*\]", error_message)
        if match:
            error_info["missing_tables"] = [g for g in match.groups() if g]

    return error_info


# Planner complexity levels configuration
# Controls prompt verbosity and model complexity based on LLM size
PLANNER_COMPLEXITY_LEVELS = {
    "minimal": {
        "description": "For 8GB models (qwen3:8b, llama3:8b)",
        "target_tokens": 1500,
        "include_json_examples": False,  # Remove verbose JSON examples
        "include_filter_operators": False,  # Model can infer operators
        "include_reasoning_hints": False,  # Remove extra guidance
        "include_advanced_sql_docs": False,  # No window functions, CTEs docs
        "max_rules": 7,  # Only essential rules
        "terminate_guidance_lines": 3,  # Minimal terminate explanation
        "decision_options": ["proceed", "clarify", "terminate"],
        "model_class": "PlannerOutputMinimal",
    },
    "standard": {
        "description": "For 13B-30B models (mixtral, qwen2.5:14b)",
        "target_tokens": 2500,
        "include_json_examples": True,  # Keep examples but condensed
        "include_filter_operators": True,
        "include_reasoning_hints": True,
        "include_advanced_sql_docs": False,  # No rare features
        "max_rules": 12,  # Most rules
        "terminate_guidance_lines": 10,  # Moderate explanation
        "decision_options": ["proceed", "clarify", "terminate"],
        "model_class": "PlannerOutputStandard",
    },
    "full": {
        "description": "For large models (GPT-4, Claude, etc.)",
        "target_tokens": 4000,
        "include_json_examples": True,  # All examples
        "include_filter_operators": True,
        "include_reasoning_hints": True,
        "include_advanced_sql_docs": True,  # Include all features
        "max_rules": 14,  # All rules
        "terminate_guidance_lines": 40,  # Complete explanation
        "decision_options": ["proceed", "clarify", "terminate"],
        "model_class": "PlannerOutput",
    },
}


def get_planner_complexity():
    """
    Get the planner complexity level from environment variable.

    Returns:
        str: Complexity level ("minimal", "standard", or "full")
    """
    complexity = os.getenv("PLANNER_COMPLEXITY", "full").lower()
    if complexity not in PLANNER_COMPLEXITY_LEVELS:
        logger.warning(
            f"Invalid PLANNER_COMPLEXITY='{complexity}', defaulting to 'full'. "
            f"Valid options: {list(PLANNER_COMPLEXITY_LEVELS.keys())}"
        )
        return "full"
    return complexity


def get_planner_model_class(complexity: str = None):
    """
    Get the appropriate Pydantic model class for the complexity level.

    Args:
        complexity: Complexity level ("minimal", "standard", or "full")
                   If None, will be determined from environment

    Returns:
        Pydantic model class (PlannerOutputMinimal, PlannerOutputStandard, or PlannerOutput)
    """
    if complexity is None:
        complexity = get_planner_complexity()

    model_class_name = PLANNER_COMPLEXITY_LEVELS[complexity]["model_class"]

    if model_class_name == "PlannerOutputMinimal":
        return PlannerOutputMinimal
    elif model_class_name == "PlannerOutputStandard":
        return PlannerOutputStandard
    else:  # "PlannerOutput"
        return PlannerOutput


def load_domain_guidance():
    """Load domain-specific guidance if available."""
    guidance_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "domain-specific-guidance",
        "domain-specific-guidance-instructions.json",
    )
    try:
        if os.path.exists(guidance_path):
            with open(guidance_path, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(
            f"Could not load domain guidance: {str(e)}",
            exc_info=True,
            extra={"guidance_path": guidance_path},
        )
    return None


def _create_minimal_prompt(**format_params):
    """Create a minimal, concise prompt for small LLMs (8GB models)."""
    system_instructions = dedent(
        """
        # Query Planning Assistant

        We're building a SQL query assistant that converts natural language questions into SQL queries.
        Your job is to analyze the user's question and create a structured query plan that identifies
        which tables, columns, joins, and filters are needed.

        **Current Date:** {current_date}

        ## What Happens Next

        Your plan will be sent to a deterministic join synthesizer that converts it into SQL.
        The synthesizer uses your exact specifications to build the query - so precision matters!

        # RULES

        ### 1. Exact Names
        Use table/column names EXACTLY as shown in schema. Never invent names.

        ### 2. Specify Joins
        If 2+ tables selected, add `join_edges` with columns:
        ```json
        {{"from_table": "X", "from_column": "XID", "to_table": "Y", "to_column": "ID"}}
        ```

        ### 3. Include Lookup Tables
        When selecting foreign key columns (CompanyID, UserID, etc.):
        - Include the related table to get human-readable names
        - Add join edge to connect them

        ### 4. Join-Only Tables
        Tables needed only for connecting (not data): set `include_only_for_join = true`

        ### 5. Decision Field
        - **"proceed"**: You found relevant tables and created a plan → USE THIS
        - **"clarify"**: Query is answerable but has ambiguities (use `ambiguities` field to list questions)
        - **"terminate"**: Query is COMPLETELY impossible, zero relevant tables → RARE

        **CRITICAL**: If you wrote ANY `selections` or `join_edges`, you MUST use `decision="proceed"` or `decision="clarify"`, NOT "terminate".

        ### 6. ORDER BY and LIMIT
        For "last N", "top N", "first N" queries, use `order_by` and `limit`:
        - "Last 10 logins" → `order_by: [{{"table": "tb_Logins", "column": "LoginDate", "direction": "DESC"}}], limit: 10`
        - "Top 5 customers" → `order_by: [{{"table": "tb_Customers", "column": "Revenue", "direction": "DESC"}}], limit: 5`
        - "Last" / "Most recent" → DESC, "First" / "Oldest" → ASC

        ### 7. Date Filters
        For relative date queries ("last 30 days", "past week"):
        - Use ISO format: `YYYY-MM-DD` (e.g., `2025-10-31`)
        - Calculate dates from current date shown above
        - Example: "last 30 days" → `{{"op": ">=", "value": "2025-10-01"}}` (30 days before {current_date})
        - For datetime columns, use `YYYY-MM-DD HH:MM:SS` format

        # DOMAIN GUIDANCE

        {domain_guidance}

        # USER QUERY

        "{user_query}"

        # DATABASE SCHEMA

        {schema}

        # PARAMETERS

        {parameters}
        """  # noqa: E501
    ).strip()

    return (
        system_instructions.format(**format_params),
        "",
    )  # No separate user message for minimal


def _create_minimal_planner_prompt_with_strategy(**format_params):
    """Create minimal planner prompt that uses pre-plan strategy (no schema)."""
    system_instructions = dedent(
        """
        # Query Plan Structuring Agent

        We're building a SQL query assistant using a two-stage approach.
        A strategic planning agent analyzed the database schema and created a plan.
        Your job: Structure that plan into PlannerOutputMinimal JSON.

        ## The Pipeline

        1. **Pre-Planner** (completed): Analyzed schema, created text-based strategy
        2. **You**: Convert strategy → structured JSON
        3. **SQL Generator**: Converts your JSON → executable SQL
        4. **Database**: Executes the SQL

        ## Your Role

        You're translating strategic intent into precise structure.
        The SQL generator will follow your JSON exactly, so accuracy matters.

        ## Key Responsibilities

        - Preserve all table/column names exactly as written in the strategy
        - Structure joins properly (every table in join_edges must be in selections)
        - Format filters correctly (arrays for 'between'/'in', scalars for others)
        - Maintain the strategic decisions (don't second-guess the pre-planner)

        ## JSON Structure

        - `decision`: "proceed", "clarify", or "terminate"
        - `intent_summary`: One sentence summary
        - `selections`: Tables with columns and filters
        - `join_edges`: Table joins (from_table/column → to_table/column)
        - `global_filters`: Cross-table filters
        - `group_by`: Aggregations (if needed)
        - `order_by`: Sorting (if needed)
        - `limit`: Row limit (if needed)
        - `ambiguities`: Assumptions
        - `termination_reason`: Why terminated (if decision='terminate')

        ## Filter Operators

        `=`, `!=`, `>`, `>=`, `<`, `<=`, `between` (array [low, high]), `in` (array), `not_in` (array), `like`, `starts_with`, `ends_with`, `is_null`, `is_not_null`

        # STRATEGY

        {pre_plan_strategy}

        # USER QUERY

        "{user_query}" # noqa: E501
        """
    ).strip()

    return (system_instructions.format(**format_params), "")


def _create_standard_planner_prompt_with_strategy(**format_params):
    """Create standard planner prompt that uses pre-plan strategy (no schema)."""
    system_instructions = dedent(
        """
        # Query Plan Structuring Agent (Standard Tier)

        We're building a SQL query assistant using a two-stage approach.
        A strategic planning agent analyzed the database and created a detailed plan with reasoning.
        Your job: Structure that plan into PlannerOutputStandard JSON with reasons preserved.

        ## The Pipeline

        1. **Pre-Planner** (completed): Analyzed schema, reasoned about approach, created strategy
        2. **You**: Convert strategy → structured JSON (preserving reasoning)
        3. **SQL Generator**: Converts your JSON → executable SQL
        4. **Database**: Executes the SQL

        ## Your Role

        You're translating strategic intent into precise structure while preserving the reasoning trail.
        This tier includes `reason` fields for debugging and transparency.

        ## Key Responsibilities

        - Preserve all table/column names exactly as written
        - Copy reasoning from the strategy into `reason` fields
        - Structure joins properly (every table in join_edges must be in selections)
        - Format filters correctly (arrays for 'between'/'in', scalars for others)
        - When aggregating, ensure all projection columns are in group_by_columns

        ## JSON Structure

        **Core:**
        - `decision`, `intent_summary`
        - `selections`: Tables with columns, filters, and reasons
        - `join_edges`: Joins with reasons
        - `global_filters`: Cross-table filters with reasons

        **Aggregations:**
        - `group_by`: GROUP BY columns, aggregates with reasons, having filters

        **Ordering:**
        - `order_by`: Sort specifications with reasons
        - `limit`: Row limit with reason

        **Metadata:**
        - `ambiguities`: Assumptions
        - `termination_reason`: If terminated

        ## Filter Operators

        `=`, `!=`, `>`, `>=`, `<`, `<=`, `between` (array [low, high]), `in` (array), `not_in` (array), `like`, `starts_with`, `ends_with`, `is_null`, `is_not_null`

        # STRATEGY

        {pre_plan_strategy}

        # USER QUERY

        "{user_query}"
        """  # noqa: E501
    ).strip()

    return (system_instructions.format(**format_params), "")


def _create_full_planner_prompt_with_strategy(**format_params):
    """Create full planner prompt that uses pre-plan strategy (no schema)."""
    system_instructions = dedent(
        """
        # Query Plan Structuring Agent (Full Tier)

        We're building a SQL query assistant using a two-stage approach.
        A strategic planning agent performed comprehensive analysis and created a detailed plan.
        Your job: Structure that plan into complete PlannerOutput JSON with all features.

        ## The Pipeline

        1. **Pre-Planner** (completed): Deep schema analysis, strategic reasoning, comprehensive planning
        2. **You**: Convert strategy → structured JSON (with advanced features)
        3. **SQL Generator**: Converts your JSON → executable SQL via SQLGlot
        4. **Database**: Executes the SQL and returns results

        ## Your Role

        You're the bridge between strategic thinking and deterministic SQL generation.
        The SQL generator is algorithmic - it will follow your structure exactly.
        Your accurate structuring ensures the query matches the user's intent.

        ## Key Responsibilities

        - Preserve all table/column names exactly as written
        - Copy reasoning from the strategy into `reason` fields
        - Structure joins properly (every table in join_edges must be in selections)
        - Format filters correctly (arrays for 'between'/'in', scalars for others)
        - When aggregating, ensure all projection columns are in group_by_columns
        - Structure advanced features (window functions, CTEs, subqueries) when present

        ## JSON Structure

        **Core:**
        - `decision`, `intent_summary`
        - `selections`: Tables with columns, filters, reasons
        - `join_edges`: Joins with reasons
        - `global_filters`: Cross-table filters with reasons

        **Aggregations:**
        - `group_by`: GROUP BY columns, aggregates with reasons, having filters

        **Advanced Features (if in strategy):**
        - `window_functions`: ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD, etc.
        - `subquery_filters`: WHERE col IN (SELECT...) patterns
        - `ctes`: WITH clause definitions

        **Ordering:**
        - `order_by`: Sort specifications with reasons
        - `limit`: Row limit with reason

        **Metadata:**
        - `ambiguities`: Assumptions made
        - `termination_reason`: If query impossible

        ## Filter Operators

        `=`, `!=`, `>`, `>=`, `<`, `<=`, `between` (array [low, high]), `in` (array), `not_in` (array), `like`, `starts_with`, `ends_with`, `is_null`, `is_not_null`

        # STRATEGY

        {pre_plan_strategy}

        # USER QUERY

        "{user_query}"
        """  # noqa: E501
    ).strip()

    return (system_instructions.format(**format_params), "")


def create_planner_prompt_with_strategy(mode: str = None, **format_params):
    """Create planner prompt that uses pre-plan strategy instead of schema.

    This is for the two-stage planning approach:
    1. Pre-planner generates text-based strategy
    2. Planner converts strategy to JSON

    Args:
        mode: Optional mode - "update", "rewrite", or None for initial
        format_params: Must include 'pre_plan_strategy' field

    Returns:
        Tuple of (system_instructions, user_input)
    """
    # Check complexity level and route to appropriate prompt builder
    complexity = get_planner_complexity()
    if complexity == "minimal":
        return _create_minimal_planner_prompt_with_strategy(**format_params)
    elif complexity == "standard":
        return _create_standard_planner_prompt_with_strategy(**format_params)
    else:  # full
        return _create_full_planner_prompt_with_strategy(**format_params)


def create_planner_prompt(mode: str = None, **format_params):
    """Create a simple formatted prompt for the planner.

    Args:
        mode: Optional mode - "update" for plan updates, "rewrite" for full replan, None for initial
        format_params: Parameters to format into the prompt

    Returns:
        Formatted prompt string with system instructions and user input
    """

    # Check complexity level and route to appropriate prompt builder
    complexity = get_planner_complexity()
    if complexity == "minimal":
        return _create_minimal_prompt(**format_params)
    # TODO: Add standard tier prompt
    # For now, "standard" falls through to "full"

    if mode == "update":
        system_instructions = dedent(
            """
            # Query Plan Update Assistant

            We're building a SQL query assistant. The user has asked for modifications to an existing query.
            Your job is to **update the current query plan** with the requested changes.

            ## Your Role in the Pipeline

            You're receiving a conversational follow-up from the user (e.g., "add the email column" or "filter by status=active").
            Update the existing plan incrementally - don't rebuild from scratch.

            ## Objective

            Revise an existing SQL query execution plan based on user feedback.

            ## Context

            - A previous query plan exists
            - The user has requested modifications
            - UPDATE the existing plan incrementally, not from scratch

            ## Task

            1. Review the previous plan and understand what was already decided
            2. Read the routing instructions carefully - they specify what needs to change
            3. Make ONLY the changes requested, preserving the rest of the plan
            4. Ensure the updated plan remains internally consistent

            ## What to Preserve

            - Same tables unless instructions say otherwise
            - Existing joins unless they need modification
            - Existing columns unless specifically adding/removing
            - Overall query structure

            ## What to Update

            - Add/remove/modify filters as instructed
            - Add/remove columns as requested
            - Adjust joins if needed for new requirements
            - Update confidence if assumptions have changed
            """  # noqa: E501
        ).strip()

    elif mode == "rewrite":
        system_instructions = dedent(
            """
            # Query Plan Rewrite Assistant

            We're building a SQL query assistant. The user has made a major change to their query.
            Your job is to **create a completely new query plan** that addresses the updated request.

            ## Your Role in the Pipeline

            The user's new request is significantly different from their previous query (different intent, domain, or approach).
            Create a fresh plan from scratch - but learn from the previous plan's assumptions/clarifications.

            ## Objective

            Create a NEW SQL query execution plan based on an updated user request.

            ## Context

            - The user had a previous query
            - Now wants something significantly different
            - Be aware of the previous plan for context
            - Create a FRESH plan from scratch that addresses the new request

            ## Task

            1. Understand the new user request and routing instructions
            2. Review the previous plan to understand context (but don't be constrained by it)
            3. Analyze the full database schema
            4. Create a completely new plan optimized for the new request

            ## Considerations

            - This is a major change - different tables, different intent, or different domain
            - Start fresh but learn from previous assumptions/ambiguities
            - Use the full schema to make the best decisions
            - Don't force-fit the old plan structure onto the new request
            """  # noqa: E501
        ).strip()

    else:  # Initial mode (None)
        system_instructions = dedent(
            """
            # Query Planning Assistant

            We're building a SQL query assistant that converts natural language questions into SQL queries.
            You're at a critical step in the pipeline: **translating the user's question into a structured query plan**.

            **Current Date:** {current_date}

            ## The Pipeline

            1. **Schema Filtering** (already done) - We've identified relevant tables/columns from the full database
            2. **Query Planning** (your step) - You create a structured plan with tables, joins, and filters
            3. **SQL Generation** (next step) - A deterministic synthesizer converts your plan to SQL
            4. **Execution** - The SQL runs and returns results to the user

            ## What We Need From You

            Create a structured query execution plan by:

            1. **Understanding the user's intent** from their natural language query
            2. **Analyzing the database schema** (tables, columns, foreign keys)
            3. **Specifying exactly what's needed:**
               - Which tables are required
               - Which columns to display, filter, or aggregate
               - How tables connect (join conditions)
               - What filters/conditions to apply
               - Any sorting or limits

            ## Why This Matters

            Your plan is a blueprint. The SQL generator follows it exactly - so precision is critical.
            If you specify the wrong table or forget a join, the query will fail or return incorrect results.
            """
        ).strip()

    # Common continuation of system instructions
    system_instructions += (
        "\n"
        + dedent(
            """
        ---

        # DOMAIN-SPECIFIC GUIDANCE

        {domain_guidance}

        ---

        # ADVANCED SQL FEATURES

        ## When to Use Advanced Features
        Use these ONLY when the user query requires them. Most queries don't need advanced features.

        ### Aggregations (GROUP BY)
        When user asks for totals, counts, averages, min/max (e.g., "total sales by company")
        - Set `group_by` with:
        - `group_by_columns`: Columns to group by (dimensions like company name, category)
        - `aggregates`: List of aggregate functions (COUNT, SUM, AVG, MIN, MAX)
        - `having_filters`: Filters on aggregated results (e.g., "companies with more than 100 sales")
        - Example: "Show total sales by company" → GROUP BY company, SUM(sales)

        ### Window Functions
        When user asks for rankings, running totals, or row numbers (e.g., "rank users by sales")
        - Set `window_functions` with function, partition_by, order_by, and alias
        - Example: "Rank employees by salary within each department" → ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC)

        ### Subqueries (in filters)
        When filtering based on results from another query (e.g., "users from top companies")
        - Set `subquery_filters` for WHERE col IN (SELECT...) patterns
        - Keep subqueries simple - single table with filters
        - Example: "Users from companies with >50 employees" → WHERE CompanyID IN (SELECT ID FROM Companies WHERE EmployeeCount > 50)

        ### CTEs (WITH clauses)
        For complex queries that benefit from intermediate results
        - Use sparingly - only when query logic is clearer with a CTE
        - Set `ctes` with name, selections, joins, filters, and optional group_by

        **Important:** Leave these fields empty (null or []) when not needed.

        ---

        # FILTER OPERATORS

        ## Available Operators
        When creating FilterPredicate objects in the `filters` array:

        | Operator | Example | Notes |
        |----------|---------|-------|
        | `=` | `{{"op": "=", "value": "Cisco"}}` | Equality |
        | `!=` | `{{"op": "!=", "value": "Active"}}` | Inequality |
        | `>` | `{{"op": ">", "value": 100}}` | Greater than |
        | `between` | `{{"op": "between", "value": [0, 100]}}` | MUST be array [low, high] |
        | `in` | `{{"op": "in", "value": ["Cisco", "Microsoft"]}}` | MUST be array |
        | `not_in` | `{{"op": "not_in", "value": ["Inactive"]}}` | MUST be array |
        | `like` | `{{"op": "like", "value": "%cisco%"}}` | Pattern matching (case-insensitive) |
        | `starts_with` | `{{"op": "starts_with", "value": "CVE-"}}` | String starts with |
        | `ends_with` | `{{"op": "ends_with", "value": ".com"}}` | String ends with |
        | `is_null` | `{{"op": "is_null", "value": null}}` | Check for NULL |
        | `is_not_null` | `{{"op": "is_not_null", "value": null}}` | Check for NOT NULL |

        ---

        # RULES AND REQUIREMENTS

        ## Hard Rules (MUST follow)

        ### 1. Exact Names Only
        Use table/column names exactly as they appear in the schema. Never invent names.

        ### 2. Always Specify Joins
        If you select 2+ tables in `selections`, you MUST populate `join_edges` with explicit column-to-column join conditions.
        - Use foreign keys from the schema to identify the correct columns
        - Example: `from_table.CompanyID = to_table.ID`

        ### 3. Include Lookup Tables for Foreign Keys
        When selecting columns that are foreign keys (fields ending in ID like CompanyID, UserID, etc.):
        - You MUST also include the referenced table in `selections` to retrieve human-readable names/descriptions
        - Add the corresponding join edge
        - Include the name column from the related table with `role="projection"`

        ### 4. Completeness of Joins
        Every table referenced in `join_edges` must also appear in `selections`.

        ### 5. Join-Only Tables
        If a table is needed only to connect others (not for data display):
        - Set `include_only_for_join = true`
        - Leave its `columns` list empty

        ### 6. Keep it Minimal
        Use the smallest number of tables required (prefer ≤ 6 tables).

        ### 7. Localize Filters
        - Put a filter in the table's `filters` array where the column lives
        - Use `global_filters` only if the constraint genuinely spans multiple tables

        ### 8. Column Roles and Filter Predicates
        **CRITICAL:** When a column should be filtered AND displayed, you must do BOTH:

        **Column Role Field:**
        - `role="projection"` → Column appears in SELECT clause (displayed to user)
        - `role="filter"` → Column is used for filtering but NOT displayed

        **Filter Predicate:**
        - You MUST create a FilterPredicate in the `filters` array when filtering is needed
        - Marking a column as `role="filter"` is NOT enough - you must also create the filter!

        **Common Pattern - "Tagged with X" queries:**

        User asks: "List all applications tagged with security risk"

        **✓ CORRECT APPROACH #1 (Display the tag):**
        ```json
        {{
        "selections": [
            {{
            "table": "tb_SoftwareTagsAndColors",
            "columns": [
                {{"table": "tb_SoftwareTagsAndColors", "column": "TagName", "role": "projection"}}
            ],
            "filters": [
                {{"table": "tb_SoftwareTagsAndColors", "column": "TagName", "op": "=", "value": "security risk"}}
            ]
            }}
        ]
        }}
        ```

        **✓ ALSO ACCEPTABLE (Don't display the tag):**
        ```json
        {{
        "selections": [
            {{
            "table": "tb_SoftwareTagsAndColors",
            "columns": [
                {{"table": "tb_SoftwareTagsAndColors", "column": "TagName", "role": "filter"}}
            ],
            "filters": [
                {{"table": "tb_SoftwareTagsAndColors", "column": "TagName", "op": "=", "value": "security risk"}}
            ]
            }}
        ]
        }}
        ```

        **✗ WRONG (Missing filter predicate):**
        ```json
        {{
        "selections": [
            {{
            "table": "tb_SoftwareTagsAndColors",
            "columns": [
                {{"table": "tb_SoftwareTagsAndColors", "column": "TagName", "role": "filter"}}
            ],
            "filters": []  // ← ERROR: No filter created!
            }}
        ]
        }}
        ```

        **Summary:** If user says "tagged with X", "labeled as Y", "status = Active", etc., you MUST create a FilterPredicate. Don't just mark the column role - actually create the filter!

        ### 9. ORDER BY and LIMIT for "Last/Top/First N" Queries

        **When the user asks for "last N", "top N", "first N", "most recent N", "oldest N", etc., you MUST use `order_by` and `limit` fields:**

        **Examples:**
        - "Last 10 logins" → `order_by: [{{"table": "tb_Logins", "column": "LoginDate", "direction": "DESC"}}], limit: 10`
        - "Top 5 customers by revenue" → `order_by: [{{"table": "tb_Customers", "column": "Revenue", "direction": "DESC"}}], limit: 5`
        - "First 3 entries" → `order_by: [{{"table": "...", "column": "CreatedOn", "direction": "ASC"}}], limit: 3`
        - "Most recent 20 tickets" → `order_by: [{{"table": "tb_Tickets", "column": "CreatedDate", "direction": "DESC"}}], limit: 20`

        **Key Points:**
        - "Last" / "Most recent" / "Latest" → Use `DESC` (descending) on timestamp column
        - "First" / "Oldest" / "Earliest" → Use `ASC` (ascending) on timestamp column
        - "Top" / "Bottom" → Use `DESC` or `ASC` on the relevant metric column (Revenue, Count, etc.)
        - Always set `limit` to the number specified by the user
        - Do NOT put this in `ambiguities` - specify the ORDER BY and LIMIT directly!

        ### 10. Date Filters for Relative Queries

        **When the user asks for relative date ranges ("last 30 days", "past week", "this month"):**

        **Date Format:**
        - Use ISO 8601 format: `YYYY-MM-DD` for dates (e.g., `2025-10-31`)
        - Use `YYYY-MM-DD HH:MM:SS` for datetimes (e.g., `2025-10-31 14:30:00`)

        **Date Calculation:**
        - Calculate dates relative to the current date shown at the top of these instructions
        - Example: If current date is 2025-10-31 and user asks "last 30 days":
        - Create filter: `{{"op": ">=", "value": "2025-10-01"}}`
        - This is 30 days before 2025-10-31

        **Common Patterns:**
        - "Last 7 days" → `{{"op": ">=", "value": "[7 days ago]"}}`
        - "Last 30 days" → `{{"op": ">=", "value": "[30 days ago]"}}`
        - "Past week" → `{{"op": ">=", "value": "[7 days ago]"}}`
        - "This month" → `{{"op": ">=", "value": "[first day of current month]"}}`
        - "Before date X" → `{{"op": "<", "value": "YYYY-MM-DD"}}`
        - "After date X" → `{{"op": ">", "value": "YYYY-MM-DD"}}`
        - "Between dates" → `{{"op": "between", "value": ["YYYY-MM-DD", "YYYY-MM-DD"]}}`

        **Important:**
        - Always calculate the actual date value - don't use expressions like "DATEADD"
        - Use string values in ISO format
        - The join synthesizer will convert these to proper SQL date literals

        ### 11. Time Filter Handling
        **IMPORTANT:** Do NOT create filter predicates for the "Time filter" parameter (e.g., "Last 30 Days", "Last 7 Days").
        - These will be handled by a downstream agent
        - Only include filters that are explicitly mentioned in the user's natural language query (e.g., "active users", "vendor = Cisco")
        - When a "Time filter" parameter is provided, include relevant timestamp columns (CreatedOn, UpdatedOn, etc.) in the selections with `role="projection"` or `role="filter"`
        - Let the downstream agent handle the actual date range calculation

        ### 12. Confidence Bounds
        All confidence values must be between 0.0 and 1.0.

        ### 13. Decision Field
        Choose the appropriate decision value:

        **proceed** - Use when you can create a viable query plan
        - The query makes sense for the schema
        - You've identified relevant tables and columns
        - May still have minor ambiguities (document in `ambiguities`)
        - **DEFAULT CHOICE** - Use this unless the query is truly impossible

        **clarify** - Use when the query is answerable but has significant ambiguities
        - Critical details are missing but you can make reasonable assumptions
        - The intent is clear but parameters need refinement
        - Populate `ambiguities` with specific questions
        - Note: The system will still proceed with your plan but show clarification options to the user

        **terminate** - EXTREMELY RARE - Use with extreme caution

        > **"With great power comes great responsibility."**

        Using `decision="terminate"` will **immediately end the entire workflow** and return an error to the user. Please only decide to terminate if there is **no way that a potentially valid query can be executed** against the available schema.

        **CRITICAL Rules:**
        - If you identified ANY relevant tables, columns, or joins → use "proceed" instead!
        - If you created a plan structure with selections/joins → you MUST use "proceed"!
        - Do NOT terminate just because the query is complex, uncertain, or requires assumptions!
        - Do NOT terminate because of "risky joins", "ambiguous schema", or "potential for incorrect results"!
        - When in doubt, use "proceed" with a lower confidence score and document concerns in `ambiguities`

        Only use "terminate" when ALL of these are true:
        1. The request has ZERO overlap with the available schema
        2. NO tables exist that could possibly answer any part of the query
        3. The query is completely nonsensical for this database domain
        4. You cannot create even a partial plan

        Examples of VALID "terminate" usage (query truly impossible):
        - "Order me a pizza" in a security/IT database → No food/restaurant tables exist
        - "Show me cat photos" in a financial database → No image/media tables exist
        - "What's the weather today?" in a user management database → No weather/location data

        Examples of INVALID "terminate" usage (use "proceed" instead):
        - ❌ "Show applications with security risk tag" when tag tables exist → Use "proceed"
        - ❌ "List vulnerable computers" when CVE/computer tables exist → Use "proceed"
        - ❌ Query is complex or requires multiple joins → Use "proceed"
        - ❌ Column names are uncertain but tables are relevant → Use "proceed" with ambiguities
        - ❌ You're not 100% confident in the plan → Use "proceed" with lower confidence score
        - ❌ Foreign key relationships are ambiguous → Use "proceed" (or "clarify" if severely ambiguous)
        - ❌ Query seems "too risky" due to schema concerns → Use "proceed" and let the query execute
        - ❌ Lack of filtering might produce broad results → Use "proceed" (broad results are better than no results)
        - ❌ You have concerns about query correctness → Use "proceed" with lower confidence and document in ambiguities

        **Rule of thumb:** If you wrote ANY `selections`, `join_edges`, or `filters` in your plan, you MUST use `decision="proceed"`, NOT "terminate".

        **⚠️ IMPORTANT VALIDATION RULE:**
        If you create a plan with tables, joins, or filters and use `decision="terminate"`, the validation system will **reject your response entirely** and you'll have to try again. Save time by using "proceed" when you have a plan!

        **When to use "clarify" vs "proceed":**
        - Use "clarify" when you genuinely cannot determine which table/column the user wants (e.g., "Status" exists in 5 tables)
        - Use "proceed" for everything else, even if you have concerns - document concerns in `ambiguities` field

        ### 14. GROUP BY Completeness Rule
        **CRITICAL SQL RULE:** When using aggregations (COUNT, SUM, AVG, etc.):
        - ALL columns with `role="projection"` MUST be included in `group_by_columns`
        - Exception: Columns from tables with `include_only_for_join=true` are excluded
        - This is a SQL requirement - non-aggregated columns in SELECT must be in GROUP BY
        - Failure to follow this will cause SQL errors

        **Examples:**

        ✓ **Correct:**
        - Selections: tb_Company.ID (projection), tb_Company.Name (projection)
        - Group by: [tb_Company.ID, tb_Company.Name]
        - Aggregates: COUNT(tb_Sales.ID)
        - Result: Both ID and Name are in GROUP BY ✓

        ✗ **Incorrect:**
        - Selections: tb_Company.ID (projection), tb_Company.Name (projection)
        - Group by: [tb_Company.ID] ONLY
        - Aggregates: COUNT(tb_Sales.ID)
        - Result: Name is missing from GROUP BY - SQL ERROR!

        **Action Required:**
        When you add aggregates to `group_by`, review ALL projection columns and ensure each one appears in `group_by_columns`.

        ### 15. HAVING Clause Table References
        When using HAVING filters in aggregated queries:
        - HAVING filters must reference the correct table where the column exists
        - If filtering on a joined table's column, use that table name (not the main table)
        - Check the schema to verify which table contains the column you're filtering on

        **Example:**
        - ✗ WRONG: Main table is tb_SaasComputerCVEMap, filtering on Impact (which is in tb_CVE_PatchImpact)
        - `having_filters: [{{"table": "tb_SaasComputerCVEMap", "column": "Impact"}}]` ← Error!
        - ✓ CORRECT: Reference the table that actually has the Impact column
        - `having_filters: [{{"table": "tb_CVE_PatchImpact", "column": "Impact"}}]` ← Correct

        ---

        ## Reasoning Hints

        ### Create Explicit Joins
        For every pair of related tables in `selections`, add a `join_edges` entry specifying the exact columns to join (from_column and to_column).
        - Look for foreign keys in the schema's `foreign_keys` arrays

        ### Prefer Foreign Keys
        Use the `foreign_keys` arrays and `...ID` column naming patterns to identify relationships.
        - **IMPORTANT:** Foreign keys often have different names than the primary keys they reference
        - Example: If Table A has foreign key "CompanyID" and Table B has primary key "ID"
        - Create join edge: `{{from_table: "TableA", from_column: "CompanyID", to_table: "TableB", to_column: "ID"}}`
        - **Common pattern:** `tb_ApplicationTagMap.TagID` joins to `tb_SoftwareTagsAndColors.ID` (NOT TagID!)
        - Check the schema's `foreign_keys` array to find the correct column mappings

        ### Auto-Join for Human-Readable Names
        When a table has a foreign key (e.g., CompanyID, UserID, ProductID):
        - Automatically include the related table
        - Join to it to retrieve the name/description column
        - Example: If selecting from tb_Users which has CompanyID, include tb_Company in selections and add a join edge to retrieve the company Name

        ### Choose Carefully
        When multiple candidate tables exist, choose the one with stronger evidence (metadata, foreign keys) and higher confidence.

        ### Ask When Stuck
        If the user mentions a column you can't find:
        - Switch to "clarify"
        - Ask for the exact field or acceptable alternative

        ### Verify Column-Table Ownership

        When receiving a strategy or adding columns to selections:
        1. Check the schema to find which table contains each column
        2. Don't assume columns are in the "main" table - check detail tables
        3. Common pattern: Detail tables end with "Details", "Map", "Info", "History"

        **Example:**
        - ❌ WRONG: {{"table": "tb_SaasComputers", "column": "NumberOfCores"}} ← Column doesn't exist in this table!
        - ✅ CORRECT: {{"table": "tb_SaasComputerProcessorDetails", "column": "NumberOfCores"}} ← Column is in this table

        **If you receive a strategy that references wrong tables:**
        - Correct the table references before generating JSON
        - Add necessary joins to the correct detail tables
        - Example: If strategy says "tb_SaasComputers.NumberOfCores", change to "tb_SaasComputerProcessorDetails.NumberOfCores"
          and add join: tb_SaasComputers.ID = tb_SaasComputerProcessorDetails.ComputerID

        ---

        ## Final Checklist

        Before responding, validate:
        - ✓ Chosen appropriate `decision` value (proceed/clarify/terminate)
        - ✓ If decision='terminate', provided clear `termination_reason`
        - ✓ If 2+ tables in `selections`, `join_edges` must be populated with explicit joins
        - ✓ All tables in `join_edges` exist in `selections`
        - ✓ Each join edge specifies both from_column and to_column (not just table names)
        - ✓ Bridge/lookup tables without projections have `include_only_for_join = true`
        - ✓ No columns appear from tables that aren't in `selections`
        - ✓ No invented table or column names
        - ✓ **FOR EACH COLUMN: Verified it exists in the SPECIFIC table referenced (not just exists somewhere)**
        - ✓ **Detail tables included when needed (e.g., tb_SaasComputerProcessorDetails for processor columns)**
        - ✓ Output is valid PlannerOutput JSON and nothing else
        """  # noqa: E501
        ).strip()
    )

    # User input varies by mode
    if mode == "update":
        user_input = dedent(
            """
            # USER INPUT

            ## ⚠️ LATEST USER REQUEST (READ THIS FIRST!)

            **THE USER ASKED:** "{user_query}"

            👉 **YOUR JOB:** Update the existing plan below to answer this EXACT request. Follow the routing instructions.

            ## Previous Plan

            {previous_plan}

            ## Routing Instructions

            {router_instructions}

            ## User Query History

            {conversation_history}

            ## Query Parameters

            {parameters}
            """  # noqa: E501
        ).strip()

    elif mode == "rewrite":
        user_input = dedent(
            """
            # USER INPUT

            ## Previous Plan (for context)

            {previous_plan}

            ## Routing Instructions

            {router_instructions}

            ## User Query History

            {conversation_history}

            ## ⚠️ LATEST USER REQUEST (READ THIS FIRST!)

            **THE USER ASKED:** "{user_query}"

            ## Available Database Schema

            {schema_note}
            {schema}

            ## Query Parameters

            {parameters}
            """
        ).strip()

    else:  # Initial mode
        user_input = dedent(
            """
            # USER INPUT

            ## ⚠️ USER QUERY (READ THIS FIRST!)

            **THE USER ASKED:** "{user_query}"

            👉 **YOUR JOB:** Create a query execution plan to answer this EXACT question. Use the schema below to identify which tables and columns are needed.

            ## Available Database Schema

            {schema_note}
            {schema}

            ## Query Parameters

            {parameters}
            """  # noqa: E501
        ).strip()

    # Format system and user messages separately
    formatted_system = system_instructions.format(**format_params)
    formatted_user = user_input.format(**format_params)

    # Return as a tuple (system, user) for proper message structure
    return (formatted_system, formatted_user)


def validate_group_by_completeness(plan_dict: dict) -> list[str]:
    """Validate that all projection columns are included in GROUP BY when aggregating.

    This catches a common SQL error where columns are selected but not grouped,
    which violates the SQL standard and causes query execution failures.

    Args:
        plan_dict: The planner output dictionary

    Returns:
        List of validation issue messages (empty if valid)
    """
    issues = []

    # Only validate if there are aggregates (indicating a GROUP BY query)
    group_by = plan_dict.get("group_by")
    if not group_by or not group_by.get("aggregates"):
        return issues  # No grouping, nothing to validate

    # Collect all projection columns from selections
    projection_cols = []
    for selection in plan_dict.get("selections", []):
        # Skip tables that are only used for joins
        if selection.get("include_only_for_join"):
            continue

        for col in selection.get("columns", []):
            if col.get("role") == "projection":
                projection_cols.append((col["table"], col["column"]))

    # Collect all group_by columns
    group_by_cols = []
    for col in group_by.get("group_by_columns", []):
        group_by_cols.append((col["table"], col["column"]))

    # Check if all projection columns are in group_by
    for table, column in projection_cols:
        if (table, column) not in group_by_cols:
            issues.append(
                f"⚠️  GROUP BY Validation Issue: Column {table}.{column} has role='projection' "
                f"but is not in group_by_columns. This will cause a SQL error. "
                f"SQL requires all non-aggregated columns in SELECT to be in GROUP BY."
            )

    return issues


def plan_query(state: State):
    """Create a structured query plan by analyzing schema and user intent."""
    user_query = state["user_question"]
    router_mode = state.get("router_mode")

    logger.info(
        "Starting query planning",
        extra={"user_query": user_query, "mode": router_mode or "initial"},
    )

    try:
        # Use truncated schema (with only relevant columns) for planner context if available
        # Otherwise fallback to filtered schema (all columns) or full schema
        # truncated_schema = best for planner (minimal context)
        # filtered_schema = used for modification options (all columns)
        # schema = full database schema (fallback)
        schema_to_use = (
            state.get("truncated_schema")
            or state.get("filtered_schema")
            or state["schema"]
        )
        schema_markdown = state.get("schema_markdown", "")

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

        # Load domain guidance
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

        # Check if we're using filtered/truncated schema
        is_truncated = state.get("truncated_schema") is not None
        is_filtered = state.get("filtered_schema") is not None
        if is_truncated:
            schema_note = "**NOTE:** This is a filtered subset of the most relevant tables and columns from the full database schema, selected based on the user's query."  # noqa: E501
        elif is_filtered:
            schema_note = "**NOTE:** This is a filtered subset of the most relevant tables from the full database schema, selected based on the user's query."  # noqa: E501
        else:
            schema_note = ""

        # Get current date for date-aware queries
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Get strategy: prioritize revised_strategy (from error/refinement) over pre_plan_strategy (from pre-planner)
        # This enables hybrid architecture: pre-planner for new queries, direct strategy revision for corrections
        revised_strategy = state.get("revised_strategy")
        pre_plan_strategy = state.get("pre_plan_strategy")

        # Use revised strategy if available, otherwise use pre-plan strategy
        strategy_to_use = revised_strategy or pre_plan_strategy
        using_two_stage = strategy_to_use is not None

        # Track which strategy source we're using
        if revised_strategy:
            logger.info(
                "Using revised strategy from error/refinement correction (bypassing pre-planner)",
                extra={"strategy_length": len(revised_strategy)},
            )
        elif pre_plan_strategy:
            logger.info(
                "Using pre-plan strategy from pre-planner",
                extra={"strategy_length": len(pre_plan_strategy)},
            )

        # Build format parameters
        format_params = {
            "domain_guidance": domain_text,
            "user_query": user_query,
            "parameters": parameters_text,
            "schema_note": schema_note,
            "current_date": current_date,
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

            # Only include schema for rewrite mode AND when NOT using two-stage planning
            if router_mode == "rewrite" and not using_two_stage:
                # Use markdown schema if available, otherwise fallback to JSON
                format_params["schema"] = schema_markdown or json.dumps(
                    schema_to_use, indent=2
                )
        else:
            # Initial mode - include schema ONLY if NOT using two-stage planning
            if not using_two_stage:
                # Use markdown schema if available, otherwise fallback to JSON
                format_params["schema"] = schema_markdown or json.dumps(
                    schema_to_use, indent=2
                )

        if using_two_stage:
            # Two-stage planning: Use strategy instead of schema
            format_params["pre_plan_strategy"] = (
                strategy_to_use  # Can be from pre-planner OR error/refinement
            )
            # Create the prompt with strategy (returns tuple of system and user messages)
            system_content, user_content = create_planner_prompt_with_strategy(
                mode=router_mode, **format_params
            )
        else:
            # Single-stage planning: Use schema directly
            logger.info("Using single-stage planning approach (direct schema)")
            # Create the prompt (returns tuple of system and user messages)
            system_content, user_content = create_planner_prompt(
                mode=router_mode, **format_params
            )

        # Debug: Save the prompt to a file
        from utils.debug_utils import save_debug_file

        save_debug_file(
            "planner_prompt.json",
            {
                "mode": router_mode or "initial",
                "system_message": system_content,
                "user_message": user_content,
                "format_params_keys": list(format_params.keys()),
            },
            step_name="planner",
            include_timestamp=True,
        )

        # Get planner model class and base LLM (not structured yet)
        planner_model_class = get_planner_model_class()
        from utils.llm_factory import get_chat_llm

        planning_model = get_model_for_stage("planning")
        base_llm = get_chat_llm(model_name=planning_model)

        # Create proper message structure for chat models
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=user_content),
        ]

        # Retry loop for handling output parsing errors
        plan = None
        last_parsing_error = None
        validation_feedback = None

        for retry_attempt in range(MAX_PARSING_RETRIES):
            try:
                # Add validation feedback to messages if this is a retry
                current_messages = messages.copy()
                if validation_feedback and retry_attempt > 0:
                    feedback_message = HumanMessage(
                        content=dedent(
                            f"""
                            VALIDATION ERROR - Please fix the following issue in your response:

                            {validation_feedback}

                            IMPORTANT: Ensure that ALL tables referenced in join_edges are also included in the selections array.
                            If you need to join to a table, you MUST add it to selections first.

                            Please regenerate your response with this issue corrected.
                            """  # noqa: E501
                        ).strip()
                    )
                    current_messages.append(feedback_message)

                # Get the plan with execution time tracking
                logger.info(
                    "Invoking LLM for query planning",
                    extra={
                        "retry_attempt": retry_attempt + 1,
                        "has_feedback": validation_feedback is not None,
                    },
                )

                # Use structured output with auto-fix applied
                # Make ONE LLM call, get JSON, apply auto-fix, then validate
                with log_execution_time(logger, "llm_planner_invocation"):
                    # Use structured output to get JSON
                    # For OpenAI: use function_calling (default, most reliable)
                    # For Ollama: use json_schema (required for local models)
                    if is_using_ollama():
                        structured_llm = base_llm.with_structured_output(
                            planner_model_class, method="json_schema"
                        )
                    else:
                        # OpenAI - don't specify method, uses function_calling by default
                        structured_llm = base_llm.with_structured_output(
                            planner_model_class
                        )

                    # Try structured output with auto-fix fallback
                    try:
                        # Attempt to get structured output directly
                        plan = structured_llm.invoke(current_messages)

                        # Success
                        if retry_attempt > 0:
                            logger.info(
                                "Successfully parsed planner output after retry",
                                extra={"retry_attempt": retry_attempt + 1},
                            )
                        break

                    except OutputParserException as parse_error:
                        # ANY validation error - try to repair
                        error_details = extract_validation_error_details(
                            str(parse_error)
                        )

                        logger.info(
                            "Detected validation error, attempting repair",
                            extra={
                                "error_type": error_details["error_type"],
                                "missing_tables": error_details["missing_tables"],
                                "problematic_field": error_details["problematic_field"],
                            },
                        )

                        # Extract raw JSON from exception (don't make a new LLM call!)
                        try:
                            # Get the raw LLM output that failed validation
                            raw_llm_output = parse_error.llm_output
                            if not raw_llm_output:
                                # If exception doesn't have llm_output, can't repair
                                raise parse_error

                            # Parse JSON from raw output
                            try:
                                raw_json = json.loads(raw_llm_output)
                            except json.JSONDecodeError:
                                # Try to extract from markdown code blocks
                                import re

                                json_match = re.search(
                                    r"```json\s*(\{.*?\})\s*```",
                                    raw_llm_output,
                                    re.DOTALL,
                                )
                                if json_match:
                                    raw_json = json.loads(json_match.group(1))
                                else:
                                    # Can't parse JSON, re-raise original error
                                    raise parse_error

                            # Apply ALL repair functions
                            fixed_json = repair_planner_output(
                                raw_json
                            )  # General repairs
                            fixed_json = auto_fix_join_edges(
                                fixed_json
                            )  # Join-specific fix

                            # Validate with Pydantic
                            plan = planner_model_class(**fixed_json)

                            logger.info(
                                "Successfully applied repairs and validated planner output",
                                extra={"retry_attempt": retry_attempt + 1},
                            )
                            break

                        except Exception as repair_error:
                            # Repair failed, re-raise original validation error to retry
                            logger.warning(
                                "Repair attempt failed, will retry with feedback",
                                extra={"repair_error": str(repair_error)},
                            )
                            raise parse_error

            except OutputParserException as e:
                last_parsing_error = e
                error_msg = str(e)

                # Extract validation error details
                error_details = extract_validation_error_details(error_msg)

                logger.warning(
                    "Output parsing error - validation failed",
                    extra={
                        "retry_attempt": retry_attempt + 1,
                        "max_retries": MAX_PARSING_RETRIES,
                        "error_type": error_details["error_type"],
                        "missing_tables": error_details["missing_tables"],
                        "problematic_field": error_details["problematic_field"],
                    },
                )

                # Save failed output to debug file
                from utils.debug_utils import save_debug_file

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_debug_file(
                    f"failed_planner_output_attempt_{retry_attempt + 1}_{timestamp}.json",
                    {
                        "attempt": retry_attempt + 1,
                        "error_message": error_msg,
                        "error_details": error_details,
                        "user_query": user_query,
                    },
                    step_name="planner_errors",
                    include_timestamp=False,  # Already in filename
                )

                # Create validation feedback for next retry
                if error_details["error_type"] in [
                    "join_edges_invalid_tables",
                    "join_edges_missing_selections",
                ]:
                    missing_tables_str = ", ".join(error_details["missing_tables"])
                    validation_feedback = dedent(
                        f"""
                        The 'join_edges' field references tables that are NOT in the 'selections' array: {missing_tables_str}

                        REQUIRED FIX:
                        - Add these tables to the 'selections' array: {missing_tables_str}
                        - OR remove the join_edges that reference these tables
                        - Every table in a join_edge MUST also appear in selections
                        """  # noqa: E501
                    ).strip()
                else:
                    validation_feedback = f"Validation error: {error_msg}"

                # If this was the last retry, we'll handle it after the loop
                if retry_attempt == MAX_PARSING_RETRIES - 1:
                    logger.error(
                        "Failed to parse planner output after all retries",
                        exc_info=True,
                        extra={
                            "total_attempts": MAX_PARSING_RETRIES,
                            "user_query": user_query,
                            "last_error": error_msg,
                        },
                    )

        # Check if we failed after all retries
        if plan is None:
            error_message = (
                "Unable to create a valid query plan after multiple attempts."
            )
            if last_parsing_error:
                error_details = extract_validation_error_details(
                    str(last_parsing_error)
                )
                if error_details["missing_tables"]:
                    error_message += f" The system had issues with tables: {', '.join(error_details['missing_tables'])}."  # noqa: E501

            return {
                **state,
                "messages": [AIMessage(content=error_message)],
                "planner_output": None,
                "needs_clarification": False,
                "last_step": "planner",
            }

        # Append to planner_outputs history
        planner_outputs = state.get("planner_outputs", [])
        # Convert Pydantic model to dict for storage
        plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else plan
        planner_outputs = planner_outputs + [plan_dict]

        # Validate the plan for GROUP BY completeness
        validation_issues = validate_group_by_completeness(plan_dict)
        if validation_issues:
            logger.warning(
                "Plan validation issues detected",
                extra={
                    "validation_issues": validation_issues,
                    "issue_count": len(validation_issues),
                },
            )
            # Log each issue separately for visibility
            for issue in validation_issues:
                logger.warning(issue)

        logger.info(
            "Query planning completed",
            extra={
                "decision": plan.decision if hasattr(plan, "decision") else "unknown",
                "confidence": plan.confidence if hasattr(plan, "confidence") else None,
                "table_count": (
                    len(plan.selections)
                    if hasattr(plan, "selections") and plan.selections
                    else 0
                ),
                "validation_passed": len(validation_issues) == 0,
            },
        )

        # Debug: Save the planner output to a file (with validation results)
        save_debug_file(
            "generated_planner_output.json",
            {
                "plan": plan_dict,
                "validation": {
                    "passed": len(validation_issues) == 0,
                    "issues": validation_issues,
                },
            },
            step_name="planner",
            include_timestamp=True,
        )

        # Check if clarification is needed based on planner decision
        needs_clarification = (
            plan.decision == "clarify" if hasattr(plan, "decision") else False
        )

        # Prepare return state
        return_state = {
            **state,
            "messages": [AIMessage(content="Query plan created successfully")],
            "planner_output": plan_dict,  # Store as dict, not Pydantic model
            "planner_outputs": planner_outputs,
            "needs_clarification": needs_clarification,
            "last_step": "planner",
        }

        # Clear revised_strategy after consumption (if it was used)
        # This ensures it's only used once and doesn't interfere with future iterations
        if revised_strategy:
            return_state["revised_strategy"] = None
            logger.info("Cleared revised_strategy after consumption")

        return return_state

    except Exception as e:
        logger.error(
            f"Exception in plan_query: {str(e)}",
            exc_info=True,
            extra={"user_query": state.get("user_question", "")},
        )
        return {
            **state,
            "messages": [AIMessage(content=f"Error creating query plan: {str(e)}")],
            "last_step": "planner",
        }
