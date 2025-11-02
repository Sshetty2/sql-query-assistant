"""Pre-planning step: Generate strategic query plan before structured JSON output.

This module implements a two-stage planning approach:
1. Pre-Planner (this module): Analyzes schema and generates text-based strategy
2. Planner (planner.py): Translates strategy into structured JSON format

Benefits:
- Separates reasoning from formatting
- Reduces cognitive load on the planner
- Faster planner LLM calls (no schema to process)
- More accurate table/column selection
"""

import os
import json
from datetime import datetime
from textwrap import dedent
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from utils.llm_factory import get_chat_llm
from utils.logger import get_logger, log_execution_time
from agent.state import State

load_dotenv()
logger = get_logger()


def load_domain_guidance():
    """Load domain-specific guidance if available."""
    guidance_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "domain_specific_guidance",
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


def get_planner_complexity():
    """Get the planner complexity level from environment variable."""
    complexity = os.getenv("PLANNER_COMPLEXITY", "full").lower()
    valid_levels = ["minimal", "standard", "full"]
    if complexity not in valid_levels:
        logger.warning(
            f"Invalid PLANNER_COMPLEXITY='{complexity}', defaulting to 'full'. "
            f"Valid options: {valid_levels}"
        )
        return "full"
    return complexity


def _create_minimal_preplan_prompt(**format_params):
    """Create a minimal pre-plan prompt for small LLMs (8GB models)."""
    system_instructions = dedent(
        """
        # Pre-Planning Assistant (Strategy Phase)

        You're helping build a SQL query by analyzing the database schema and creating a strategic plan.
        Your strategy will guide another agent that converts it to structured JSON.

        **Current Date:** {current_date}

        ## Your Role

        Create a clear, flexible strategy for answering the user's question.
        Think through which tables, columns, joins, and filters are needed.

        ## Strategy Components

        Consider including:
        - **Tables**: Which tables contain the data needed?
        - **Columns**: Which columns should be selected or filtered?
        - **Joins**: How do tables connect? (use FK relationships from schema)
        - **Filters**: What conditions should be applied?
        - **Aggregations**: Any counts, sums, averages needed?
        - **Ordering**: How should results be sorted?
        - **Limiting**: How many rows to return?

        ## ⚠️ CRITICAL: Column Name Accuracy

        **The database schema is your ONLY source of truth for column names.**

        ❌ **WRONG:** Guessing column names
        - User asks for "company name" → You write "tb_Company.CompanyName" (doesn't exist!)
        - User asks for "company ID" → You write "tb_Company.CompanyID" (doesn't exist!)

        ✅ **CORRECT:** Using EXACT column names from schema
        - Schema shows: `tb_Company.Name` → Use "tb_Company.Name"
        - Schema shows: `tb_Company.ID` → Use "tb_Company.ID"

        **Common Mistakes to Avoid:**
        1. **Don't invent column names** - Even if they seem logical, check the schema
        2. **Primary keys vs Foreign keys** - Foreign keys often have different names
           - Example: `tb_SaasPendingPatch.CompanyID` joins to `tb_Company.ID` (NOT CompanyID!)
        3. **Case sensitivity** - Use the exact case from schema
        4. **Table prefixes** - Always specify table name: `tb_Company.Name` not just `Name`

        ## Other Guidelines

        - For date filters, calculate actual dates from: {current_date}
        - For "last N" queries, use ORDER BY ... DESC with LIMIT
        - Include lookup tables when selecting foreign key columns

        ## Output Format

        Write your strategy in **markdown format** with clear structure.
        Use headings, bullet points, and code blocks as needed.
        Be specific and detailed - the next agent will follow your plan exactly.

        # DOMAIN GUIDANCE

        {domain_guidance}

        # DATABASE SCHEMA

        {schema}

        # PARAMETERS

        {parameters}
        """
    ).strip()

    user_message = dedent(
        """
        # USER QUERY

        {user_query}

        Please analyze this query and generate a strategic plan following the instructions above.
        """
    ).strip()

    return (system_instructions.format(**format_params), user_message.format(**format_params))


def _create_standard_preplan_prompt(**format_params):
    """Create a standard pre-plan prompt for medium LLMs (13B-30B models)."""
    system_instructions = dedent(
        """
        # Pre-Planning Assistant (Strategy Phase)

        We're building a SQL query assistant using a two-stage planning approach.
        You're at the FIRST stage: strategic analysis.

        **Current Date:** {current_date}

        ## The Two-Stage Approach

        **Stage 1 (YOU):** Analyze schema → Generate text-based strategy
        **Stage 2:** Strategy → Planner converts to JSON → SQL generation

        ## Why Two Stages?

        Separating reasoning from formatting improves accuracy and speed:
        - You focus on understanding the query and schema
        - The planner focuses on correct JSON formatting
        - Faster execution (planner doesn't need schema)

        ## Your Task

        Analyze the database schema and user's question to create a detailed strategy.

        ### What to Include

        1. **Decision**
           - proceed: Can create a viable plan
           - clarify: Answerable but has ambiguities
           - terminate: Completely impossible (RARE)

        2. **Intent Summary**
           - One sentence describing what user wants

        3. **Tables to Use**
           - List each table needed
           - Reason: Why this table is needed
           - Confidence: 0.0-1.0
           - Join-only: True if table is only for connecting others

        4. **Columns to Select**
           - For each column:
             - Table and column name (exact from schema)
             - Role: "projection" (display) or "filter" (condition only)
             - Reason: Why selecting this column

        5. **Joins Required**
           - For each join:
             - From table and column
             - To table and column
             - Reason: Why joining these tables
             - Join type: inner (default), left, right, full

        6. **Filters to Apply**
           - For each filter:
             - Table and column
             - Operator: =, !=, >, <, between, in, like, etc.
             - Value: The filter value
             - Reason: Why this filter

        7. **Aggregations** (if needed)
           - Group by columns
           - Aggregate functions (COUNT, SUM, AVG, MIN, MAX)
           - Having filters (filters on aggregated results)
           - Reason: Why aggregating

        8. **Ordering and Limiting**
           - Order by: Table, column, direction (ASC/DESC)
           - Limit: Number of rows
           - Reason: Why this ordering/limiting

        9. **Ambiguities**
           - List any assumptions or unclear points

        ## ⚠️ CRITICAL: Column Name Accuracy

        **The database schema is your ONLY source of truth for column names.**

        ❌ **WRONG:** Guessing column names based on user's words
        - User asks for "company name" → You write "tb_Company.CompanyName" (doesn't exist!)
        - User asks for "company ID" → You write "tb_Company.CompanyID" (doesn't exist!)

        ✅ **CORRECT:** Using EXACT column names from schema
        - Schema shows: `tb_Company.Name` → Use "tb_Company.Name"
        - Schema shows: `tb_Company.ID` → Use "tb_Company.ID"

        **Common Mistakes to Avoid:**
        1. **Don't invent column names** - Even if they seem logical, check the schema
        2. **Primary keys vs Foreign keys** - Foreign keys often have different names
           - Example: `tb_SaasPendingPatch.CompanyID` joins to `tb_Company.ID` (NOT CompanyID!)
        3. **Case sensitivity** - Use the exact case from schema
        4. **Table prefixes** - Always specify: `tb_Company.Name` not just `Name`

        ### Foreign Key Relationships
        - Check the foreign_keys arrays in schema
        - FK columns often have different names than PKs
        - Always verify both sides of the join in the schema

        ### 3. Include Lookup Tables
        When selecting FK columns (CompanyID, TagID, etc.):
        - Include the related table to get human-readable names
        - Add the join
        - Select the name column from the related table

        ### 4. Date Handling
        For relative dates ("last 30 days", "past week"):
        - Calculate actual date from current date: {current_date}
        - Use ISO format: YYYY-MM-DD
        - Example: "last 30 days" from {current_date} = "2025-10-01" (if today is 2025-10-31)

        ### 5. ORDER BY for Temporal Queries
        - "Last N" → ORDER BY timestamp DESC, LIMIT N
        - "First N" → ORDER BY timestamp ASC, LIMIT N
        - "Top N" → ORDER BY metric DESC, LIMIT N

        ### 6. Complete GROUP BY
        When aggregating:
        - ALL projection columns must be in group by
        - Exception: Columns from join-only tables

        ### 7. Column Roles and Filters
        **CRITICAL:** When filtering on a column:
        - Mark column role as "projection" (to display) or "filter" (condition only)
        - AND create a filter predicate with operator and value
        - Don't just mark role - actually create the filter!

        ## Output Format

        Write a detailed, well-structured strategy in plain text.
        Use clear headings, bullet points, and explanations.
        Be specific about exact table/column names and reasoning.

        # DOMAIN GUIDANCE

        {domain_guidance}

        # DATABASE SCHEMA

        {schema}

        # PARAMETERS

        {parameters}
        """
    ).strip()

    user_message = dedent(
        """
        # USER QUERY

        {user_query}

        Please analyze this query and generate a strategic plan following the instructions above.
        """
    ).strip()

    return (system_instructions.format(**format_params), user_message.format(**format_params))


def _create_full_preplan_prompt(**format_params):
    """Create a comprehensive pre-plan prompt for large LLMs (GPT-4+)."""
    system_instructions = dedent(
        """
        # Pre-Planning Assistant (Strategic Query Analysis)

        We're building a SQL query assistant with a two-stage planning architecture.
        You're at Stage 1: strategic analysis and schema reasoning.

        **Current Date:** {current_date}

        ## Architecture Overview

        **Stage 1 (YOU - Pre-Planner):**
        - Input: User query + Database schema + Domain guidance
        - Output: Text-based strategic plan
        - Focus: Understanding intent, analyzing schema, determining approach

        **Stage 2 (Planner):**
        - Input: User query + Your strategy (no schema)
        - Output: Structured JSON (PlannerOutput)
        - Focus: Translating strategy to correct JSON format

        **Stage 3 (SQL Generator):**
        - Input: PlannerOutput JSON
        - Output: Executable SQL
        - Focus: Deterministic SQL generation via SQLGlot

        ## Why This Approach?

        **Separation of Concerns:**
        - You handle the complex reasoning about schema and intent
        - Planner handles the simpler task of JSON formatting
        - Results in better accuracy and faster execution

        **Benefits:**
        - Reduced cognitive load (you don't worry about JSON format)
        - Faster planner LLM call (no schema to process)
        - Better table/column selection (your focus)
        - Clearer reasoning trail (text-based strategy)

        ## Your Comprehensive Task

        Create a detailed strategic plan that covers all aspects of query execution.

        ## ⚠️ CRITICAL: Column Name Accuracy

        **The database schema is your ONLY source of truth for column names.**

        ❌ **WRONG:** Guessing column names based on user's words
        - User asks for "company name" → You write "tb_Company.CompanyName" (doesn't exist!)
        - User asks for "company ID" → You write "tb_Company.CompanyID" (doesn't exist!)

        ✅ **CORRECT:** Using EXACT column names from schema
        - Schema shows: `tb_Company.Name` → Use "tb_Company.Name"
        - Schema shows: `tb_Company.ID` → Use "tb_Company.ID"

        **Common Mistakes to Avoid:**
        1. **Don't invent column names** - Even if they seem logical, check the schema
        2. **Primary keys vs Foreign keys** - Foreign keys often have different names
           - Example: `tb_SaasPendingPatch.CompanyID` joins to `tb_Company.ID` (NOT CompanyID!)
        3. **Case sensitivity** - Use the exact case from schema
        4. **Table prefixes** - Always specify: `tb_Company.Name` not just `Name`

        ### 1. Decision Analysis

        Determine the appropriate decision:
        - **proceed**: You can create a viable plan (default choice)
        - **clarify**: Answerable but has significant ambiguities
        - **terminate**: Completely impossible, zero relevant tables (EXTREMELY RARE)

        **CRITICAL:** If you identify ANY relevant tables, use "proceed" (not terminate).
        Only terminate when the query has ZERO overlap with the schema.

        ### 2. Intent Summary

        One clear sentence describing what the user wants to accomplish.

        ### 3. Table Selection Strategy

        For each table you select:
        - **Table name** (exact from schema)
        - **Confidence** (0.0-1.0): How confident this table is needed
        - **Reason**: Detailed explanation of why this table is required
        - **Include only for join** (yes/no): True if table is only for connecting others
        - **Data projection** (yes/no): True if table provides display columns

        Consider:
        - Primary data tables (answer the core question)
        - Lookup tables (provide human-readable names for foreign keys)
        - Bridge tables (connect other tables via many-to-many relationships)
        - Keep table count minimal (prefer ≤ 6 tables)

        ### 4. Column Selection Strategy

        For each column you select:
        - **Table.Column** (exact from schema)
        - **Role**: "projection" (displayed to user) or "filter" (condition only)
        - **Reason**: Why selecting this column
        - **Data type**: From schema (helps with operators)
        - **Nullable**: Yes/no (affects NULL handling)

        Consider:
        - User-requested columns (explicit in query)
        - Context columns (provide useful context)
        - Join columns (foreign keys)
        - Filter columns (even if not displayed)
        - Timestamp columns (for ordering)

        ### 5. Join Strategy

        For each join:
        - **From table and column** (left side)
        - **To table and column** (right side)
        - **Join type**: inner (default), left, right, full
        - **Reason**: Why joining these tables
        - **Confidence** (0.0-1.0): How confident in this join

        **Important Foreign Key Patterns:**
        - FK columns often have different names than PK columns
        - Example: tb_Applications.CompanyID → tb_Company.ID (not CompanyID!)
        - Always check the foreign_keys arrays in schema
        - Look for ...ID naming patterns
        - Consider inferred foreign keys (marked with "inferred": true)

        ### 6. Filter Strategy

        For each filter:
        - **Table.Column** (exact from schema)
        - **Operator**: =, !=, >, >=, <, <=, between, in, not_in, like, starts_with, ends_with, is_null, is_not_null
        - **Value**: The filter value (or array for 'in'/'between')
        - **Reason**: Why this filter
        - **Filter type**: table-level, global, or having

        **Filter Placement:**
        - Table-level: Filter applies to one table (most common)
        - Global: Filter condition spans multiple tables
        - Having: Filter on aggregated results (after GROUP BY)

        **Date Filter Handling:**
        For relative dates ("last 30 days", "past week"):
        - Calculate actual date from current date: {current_date}
        - Use ISO format: YYYY-MM-DD for dates
        - Use YYYY-MM-DD HH:MM:SS for datetimes
        - Example: "last 30 days" from {current_date} → "2025-10-01" (if today is 2025-10-31)

        **CRITICAL Rule:**
        If a column is used for filtering:
        1. Mark the column with appropriate role ("projection" or "filter")
        2. AND create a filter predicate with operator and value
        Don't just mark the role without creating the filter!

        ### 7. Aggregation Strategy (if applicable)

        For queries requiring COUNT, SUM, AVG, MIN, MAX:

        **Group By Columns:**
        - List all columns to group by
        - Reason: Why grouping by these dimensions

        **Aggregate Functions:**
        - For each aggregate:
          - Function: COUNT, SUM, AVG, MIN, MAX, COUNT_DISTINCT
          - Table.Column (or * for COUNT(*))
          - Alias: Output column name
          - Reason: What this aggregate calculates

        **Having Filters:**
        - Filters on aggregated results
        - Example: "companies with more than 100 sales" → HAVING COUNT > 100

        **CRITICAL GROUP BY Rule:**
        ALL projection columns must be in GROUP BY
        (Exception: Columns from join-only tables)

        ### 8. Advanced Features (if applicable)

        **Window Functions:**
        For rankings, running totals, row numbers:
        - Function: ROW_NUMBER(), RANK(), DENSE_RANK(), LAG(), LEAD()
        - Partition by: Grouping columns
        - Order by: Sorting columns
        - Alias: Output column name

        **Subquery Filters:**
        For filtering based on another query result:
        - Pattern: WHERE col IN (SELECT...)
        - Keep subqueries simple

        **CTEs (WITH clauses):**
        For complex queries benefiting from intermediate results:
        - Use sparingly
        - Name and describe each CTE

        ### 9. Ordering and Limiting Strategy

        **ORDER BY:**
        For queries asking for specific ordering:
        - Table and column to sort by
        - Direction: ASC (ascending) or DESC (descending)
        - Reason: Why this ordering

        **Temporal Query Patterns:**
        - "Last N" / "Most recent N" → ORDER BY timestamp DESC, LIMIT N
        - "First N" / "Oldest N" → ORDER BY timestamp ASC, LIMIT N
        - "Top N" / "Bottom N" → ORDER BY metric DESC/ASC, LIMIT N

        **LIMIT:**
        - Number of rows to return
        - Reason: Why this limit

        ### 10. Ambiguities and Assumptions

        List any:
        - Assumptions you're making
        - Unclear aspects of the query
        - Multiple possible interpretations
        - Missing information
        - Risky decisions

        Be honest about uncertainty - document concerns here.

        ## Output Format

        Write a comprehensive, well-structured strategic plan in plain text.

        Use clear headings, sections, and bullet points.
        Be specific about exact table/column names.
        Provide detailed reasoning for each decision.

        **Structure:**
        ```
        STRATEGIC QUERY PLAN
        ====================

        USER QUERY: [repeat query]

        DECISION: [proceed/clarify/terminate]
        CONFIDENCE: [0.0-1.0]

        INTENT SUMMARY:
        [One sentence describing what user wants]

        TABLE SELECTION STRATEGY:
        ---
        1. [table_name] (confidence: X.X)
           - Reason: [detailed explanation]
           - Join-only: [yes/no]
           - Data projection: [yes/no]

        2. [table_name] (confidence: X.X)
           ...

        COLUMN SELECTION STRATEGY:
        ---
        [table].[column] - role: [projection/filter]
        - Reason: [explanation]
        - Data type: [type]

        JOIN STRATEGY:
        ---
        [from_table].[from_column] = [to_table].[to_column] ([join_type])
        - Reason: [explanation]
        - Confidence: [0.0-1.0]

        FILTER STRATEGY:
        ---
        [table].[column] [operator] [value]
        - Reason: [explanation]
        - Filter type: [table-level/global/having]

        AGGREGATION STRATEGY:
        ---
        [if applicable]
        Group by: [columns]
        Aggregates: [functions]
        Having: [filters]

        ORDERING STRATEGY:
        ---
        ORDER BY [table].[column] [ASC/DESC]
        LIMIT [N]
        - Reason: [explanation]

        AMBIGUITIES:
        ---
        - [list any assumptions or unclear points]
        ```

        # DOMAIN GUIDANCE

        {domain_guidance}

        # DATABASE SCHEMA

        {schema}

        # PARAMETERS

        {parameters}
        """
    ).strip()

    user_message = dedent(
        """
        # USER QUERY

        {user_query}

        Please analyze this query and generate a strategic plan following the instructions above.
        """
    ).strip()

    return (system_instructions.format(**format_params), user_message.format(**format_params))


def create_preplan_strategy(state: State):
    """Generate a text-based strategic plan before structured JSON planning.

    This is the first stage of two-stage planning:
    1. Pre-planner (this function): Analyzes schema and generates text strategy
    2. Planner (agent/planner.py): Translates strategy into structured JSON

    Args:
        state: Current workflow state

    Returns:
        Updated state with pre_plan_strategy field
    """
    user_query = state["user_question"]
    complexity = get_planner_complexity()

    logger.info(
        "Starting pre-planning (strategy generation)",
        extra={"user_query": user_query, "complexity": complexity},
    )

    try:
        # Use truncated schema if available, otherwise filtered schema, otherwise full schema
        schema_to_use = (
            state.get("truncated_schema")
            or state.get("filtered_schema")
            or state["schema"]
        )
        schema_markdown = state.get("schema_markdown", "")

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
            domain_text = "No domain-specific guidance available."

        # Get current date for date-aware queries
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Build format parameters
        format_params = {
            "domain_guidance": domain_text,
            "user_query": user_query,
            "parameters": parameters_text,
            "schema": schema_markdown or json.dumps(schema_to_use, indent=2),
            "current_date": current_date,
        }

        # Select prompt based on complexity - returns (system_message, user_message) tuple
        if complexity == "minimal":
            system_content, user_content = _create_minimal_preplan_prompt(**format_params)
        elif complexity == "standard":
            system_content, user_content = _create_standard_preplan_prompt(**format_params)
        else:  # full
            system_content, user_content = _create_full_preplan_prompt(**format_params)

        # Create messages - SystemMessage for instructions, HumanMessage with user query
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=user_content)
        ]

        # Get LLM and generate strategy with high temperature for creativity
        llm = get_chat_llm(model_name=os.getenv("AI_MODEL"), temperature=1.0)

        logger.info("Invoking LLM for pre-planning strategy generation")

        with log_execution_time(logger, "llm_preplan_invocation"):
            response = llm.invoke(messages)

        strategy = response.content

        logger.info(
            "Pre-planning strategy generated successfully",
            extra={"strategy_length": len(strategy), "complexity": complexity},
        )

        # Debug: Save the strategy
        from utils.debug_utils import save_debug_file

        save_debug_file(
            "preplan_strategy.json",
            {
                "strategy": strategy,
                "complexity": complexity,
                "user_query": user_query,
                "strategy_length": len(strategy),
            },
            step_name="pre_planner",
            include_timestamp=True,
        )

        return {
            **state,
            "pre_plan_strategy": strategy,
            "messages": [AIMessage(content="Pre-planning strategy created")],
            "last_step": "pre_planner",
        }

    except Exception as e:
        logger.error(
            f"Exception in create_preplan_strategy: {str(e)}",
            exc_info=True,
            extra={"user_query": user_query},
        )
        return {
            **state,
            "messages": [
                AIMessage(content=f"Error creating pre-plan strategy: {str(e)}")
            ],
            "last_step": "pre_planner",
        }
