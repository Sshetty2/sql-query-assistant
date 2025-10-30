"""Filter the schema to only the most relevant tables based on the query with a vector search."""

import os
import json
from textwrap import dedent
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_community.vectorstores.utils import filter_complex_metadata

from agent.state import State
from utils.llm_factory import is_using_ollama
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger()


def get_embedding_model():
    """Get the appropriate embedding model based on environment configuration."""
    if is_using_ollama():
        # Use local HuggingFace embeddings for local LLM
        embedding_model_name = os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        return HuggingFaceEmbeddings(
            model_name=embedding_model_name,
            encode_kwargs={"normalize_embeddings": True},
            show_progress=True,  # Set to True if you want to see progress
        )
    else:
        # Use OpenAI embeddings for cloud LLM
        return OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL"))


top_most_relevant_tables_vector = int(os.getenv("TOP_MOST_RELEVANT_TABLES", "10"))


def get_page_content(entry):
    """
    Get the page content for the schema entry.

    Creates a rich text representation including:
    - Table name
    - Description
    - Key columns
    - Foreign key relationships
    """
    table_name = entry.get("table_name", "")
    content_parts = [f"Table: {table_name}"]

    # Add metadata description if available
    metadata = entry.get("metadata", {})
    if metadata.get("description"):
        content_parts.append(f"Description: {metadata['description']}")

    # Add key columns if available
    if metadata.get("key_columns"):
        key_cols = metadata["key_columns"]
        if isinstance(key_cols, list) and key_cols:
            content_parts.append(f"Key columns: {', '.join(key_cols)}")

    # Add foreign key relationships
    foreign_keys = entry.get("foreign_keys", [])
    if foreign_keys:
        fk_references = []
        for fk in foreign_keys:
            fk_col = fk.get("foreign_key", "")
            ref_table = fk.get("primary_key_table", "")
            if fk_col and ref_table:
                fk_references.append(f"{fk_col} -> {ref_table}")
        if fk_references:
            content_parts.append(f"Related to: {', '.join(fk_references)}")

    return ". ".join(content_parts)


def load_foreign_keys():
    """Load foreign key mappings from the domain-specific JSON file."""
    fk_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "domain_specific_guidance",
        "domain-specific-foreign-keys.json",
    )
    try:
        with open(fk_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(
            f"Could not load foreign keys file: {str(e)}",
            exc_info=True,
            extra={"fk_path": fk_path},
        )
        return []


def expand_with_foreign_keys(selected_tables, all_tables, foreign_keys_data):
    """
    Expand the selected tables with tables linked via foreign keys.

    Args:
        selected_tables: List of table schema entries selected by LLM (may have filtered columns)
        all_tables: Complete list of all table schema entries
        foreign_keys_data: Foreign key mappings loaded from JSON

    Returns:
        Expanded list of table schema entries including foreign key related tables
        Note: Originally selected tables preserve their column filtering (if any),
              while FK-added tables include all columns (needed for joins)
    """
    # Create a mapping of table_name -> schema entry for quick lookup
    table_lookup = {table.get("table_name"): table for table in all_tables}

    # Create a mapping of table_name -> selected table entry (may have filtered columns)
    selected_table_lookup = {
        table.get("table_name"): table for table in selected_tables
    }

    # Create a mapping of table_name -> foreign key info
    fk_lookup = {item["table_name"]: item["foreign_keys"] for item in foreign_keys_data}

    # Start with selected tables
    selected_table_names = {table.get("table_name") for table in selected_tables}
    expanded_table_names = set(selected_table_names)

    logger.info(
        "Starting foreign key expansion",
        extra={
            "initial_table_count": len(selected_table_names),
            "selected_tables": list(selected_table_names),
        },
    )

    # For each selected table, add tables it references via foreign keys
    for table_name in selected_table_names:
        if table_name in fk_lookup:
            foreign_keys = fk_lookup[table_name]
            for fk in foreign_keys:
                referenced_table = fk.get("primary_key_table", "")
                if referenced_table and referenced_table in table_lookup:
                    if referenced_table not in expanded_table_names:
                        logger.info(
                            "Adding foreign key referenced table",
                            extra={
                                "from_table": table_name,
                                "foreign_key": fk.get("foreign_key"),
                                "referenced_table": referenced_table,
                            },
                        )
                        expanded_table_names.add(referenced_table)

    # Convert table names back to schema entries
    # IMPORTANT: Use selected_table_lookup for originally selected tables (preserves column filtering)
    #            Use table_lookup for FK-added tables (full columns for joins)
    expanded_tables = []
    for name in expanded_table_names:
        if name in selected_table_lookup:
            # This was an originally selected table - use the (possibly filtered) version
            expanded_tables.append(selected_table_lookup[name])
        elif name in table_lookup:
            # This was FK-added - use full table with all columns
            expanded_tables.append(table_lookup[name])

    logger.info(
        "Foreign key expansion completed",
        extra={
            "initial_count": len(selected_table_names),
            "final_count": len(expanded_tables),
            "added_tables": list(expanded_table_names - selected_table_names),
        },
    )

    return expanded_tables


def filter_schema(state: State, vector_store=None):
    """
    Filter schema to only the most relevant tables based on the query.

    This uses a three-stage approach:
    1. Vector search to get top-k candidate tables
    2. LLM reasoning to select truly relevant tables from candidates
    3. Foreign key expansion to ensure join tables are included
    """
    from utils.llm_factory import get_chat_llm
    from models.table_selection import TableSelectionOutput

    full_schema = state["schema"]
    user_query = state["user_question"]

    logger.info(
        "Starting 3-stage schema filtering",
        extra={
            "total_tables": len(full_schema),
            "vector_search_k": top_most_relevant_tables_vector,
            "user_query": user_query,
        },
    )

    # ============================================================================
    # STAGE 1: Vector Search - Get top-k candidate tables
    # ============================================================================
    logger.info("Stage 1: Running vector search for candidate tables")

    # Get the appropriate embedding model
    embedding_model = get_embedding_model()

    # Create documents with rich content
    documents = [
        Document(page_content=get_page_content(entry), metadata=entry)
        for entry in full_schema
    ]

    # Debug: Save the embedded content to a file
    from utils.debug_utils import save_debug_file

    save_debug_file(
        "embedded_content.json",
        {
            "user_query": user_query,
            "embedded_documents": [
                {
                    "table_name": doc.metadata.get("table_name"),
                    "embedded_text": doc.page_content,
                }
                for doc in documents
            ],
        },
        step_name="filter_schema_stage1",
        include_timestamp=True,
    )

    with log_execution_time(logger, "stage1_vector_search"):
        # Filter complex metadata (Chroma only supports simple types)
        documents = filter_complex_metadata(documents)

        vector_store = Chroma.from_documents(
            documents=documents,
            embedding=embedding_model,
            collection_name="schema_filtering",
        )

        candidate_docs = vector_store.similarity_search(
            query=user_query, k=top_most_relevant_tables_vector
        )

    candidate_tables = [doc.metadata for doc in candidate_docs]
    candidate_table_names = [
        table.get("table_name", "Unknown") for table in candidate_tables
    ]

    logger.info(
        "Stage 1 completed: Vector search candidates",
        extra={
            "candidate_count": len(candidate_tables),
            "candidate_tables": candidate_table_names,
        },
    )

    # ============================================================================
    # STAGE 2: LLM Reasoning - Select truly relevant tables
    # ============================================================================
    logger.info("Stage 2: Using LLM to reason about table relevance")

    # Build a lookup map from table_name to full table data (with columns)
    # Note: candidate_tables from vector search have filtered metadata (no complex types like lists)
    # So we need to look up the full table data from full_schema to get columns
    full_schema_lookup = {table.get("table_name"): table for table in full_schema}

    # Prepare a concise summary for each candidate table with column information
    table_summaries = []
    for candidate_table in candidate_tables:
        table_name = candidate_table.get("table_name", "Unknown")

        # Look up the FULL table data (with columns) from the original schema
        full_table = full_schema_lookup.get(table_name, candidate_table)

        metadata = full_table.get("metadata", {})
        description = metadata.get("description", "No description available")
        key_columns = metadata.get("key_columns", [])

        # Get all column names for the LLM to choose from
        columns = full_table.get("columns", [])
        column_names = [
            col.get("column_name", "") for col in columns if col.get("column_name")
        ]

        summary = f"**{table_name}**\n"
        summary += f"Description: {description}\n"
        if key_columns:
            summary += f"Key columns: {', '.join(key_columns)}\n"
        if column_names:
            summary += f"Available columns: {', '.join(column_names)}"
        else:
            # WARNING: If we have no columns, the LLM will hallucinate!
            logger.warning(
                f"No columns found for table {table_name}. LLM may hallucinate column names.",
                extra={"table": table_name}
            )

        table_summaries.append(summary)

    # Construct the system message (context about the problem)
    system_message = dedent(
        """
        # Schema Filtering Assistant

        We're building a SQL query assistant that converts natural language questions into SQL queries.
        To optimize performance and accuracy, we need to identify which database tables and columns
        are truly relevant to answering each user question.

        ## The Problem We're Solving

        Our database has many tables with hundreds of columns. Sending all this information to the
        query planner overwhelms it with irrelevant context, leading to:
        - Slower processing
        - Higher API costs
        - Increased chance of errors
        - Difficulty focusing on what matters

        ## What We Need Help With

        We've already used vector similarity search to narrow down to candidate tables that might be
        relevant. Now we need your help to:

        1. **Determine which tables are actually needed** for this specific query
        2. **Select only the relevant columns** from each table

        ## Guidelines for Column Selection

        **CRITICAL CONSTRAINT:** You MUST only select columns from the exact "Available columns"
        list shown for each table. Do NOT invent, suggest, or assume column names that aren't
        explicitly listed. Use the EXACT column names as shown (preserve casing).

        Please be selective and only include columns that are:
        - **Displayed in output** - Information the user explicitly wants to see
        - **Used for filtering** - Columns needed in WHERE conditions
        - **Used for aggregation** - Columns needed in COUNT, SUM, AVG, etc.
        - **Used for sorting** - Columns needed in ORDER BY
        - **Required for joins** - Foreign key columns that connect tables

        **Example:**
        If a table shows: "Available columns: ID, ScanID, ComputerID, Name, Description"
        Then you can ONLY select from: ID, ScanID, ComputerID, Name, Description
        You CANNOT select: computer_id, scan_id, DeviceName, or any other columns not in the list.

        **Important:** Don't include columns just because they exist. Focus on what this specific
        query actually needs. When in doubt, be liberal and include columns from the available list.
    """
    ).strip()

    # Construct the user message (the actual query and data)
    user_message = dedent(
        f"""
        ## User's Question

        {user_query}

        ## Candidate Tables

        {chr(10).join(f"### {i+1}. {summary}" for i, summary in enumerate(table_summaries))}

        ---

        ## Your Task

        For each candidate table above, please provide:

        1. **Relevance Assessment** - Is this table needed to answer the user's question?
        2. **Column Selection** - Which specific columns from the "Available columns" list are required?
           - ONLY select from the exact columns listed in "Available columns" for each table
           - Use the EXACT column names as shown (preserve casing)
           - Do NOT invent or suggest columns not in the list
        3. **Reasoning** - Brief explanation of your decision

        Remember: Be liberal and include the table or column, but ONLY select from available columns.
    """
    ).strip()

    with log_execution_time(logger, "stage2_llm_reasoning"):
        llm = get_chat_llm(model_name=os.getenv("AI_MODEL"), temperature=0)
        structured_llm = llm.with_structured_output(TableSelectionOutput)

        # Create message list for chat models
        messages = [
            SystemMessage(content=system_message),
            HumanMessage(content=user_message),
        ]

        try:
            selection_output = structured_llm.invoke(messages)

            # Debug: Save LLM interaction for filtering stage
            from utils.debug_utils import save_llm_interaction

            save_llm_interaction(
                step_name="filter_schema_stage2_llm",
                prompt={"system_message": system_message, "user_message": user_message},
                response=selection_output,
                model=os.getenv("AI_MODEL"),
                metadata={
                    "user_query": user_query,
                    "candidate_table_count": len(candidate_tables),
                    "stage": "stage2_table_and_column_selection",
                },
            )

            # Filter to only relevant tables
            relevant_assessments = [
                assessment
                for assessment in selection_output.selected_tables
                if assessment.is_relevant
            ]

            relevant_table_names_set = {
                assessment.table_name for assessment in relevant_assessments
            }

            # Create a mapping of table_name -> relevant_columns
            column_filter_map = {
                assessment.table_name: assessment.relevant_columns
                for assessment in relevant_assessments
            }

            # Get the actual schema entries for relevant tables
            # We need TWO versions:
            # 1. filtered_schema - tables with ALL columns (for modification options)
            # 2. truncated_schema - tables with ONLY relevant columns (for planner context)
            # NOTE: Use full_schema_lookup to get tables WITH columns (candidate_tables has filtered metadata)

            llm_selected_tables_full = []  # Full columns (for filtered_schema)
            llm_selected_tables_truncated = []  # Truncated columns (for truncated_schema)

            for table_name in relevant_table_names_set:
                # Get the FULL table with columns from the original schema
                table = full_schema_lookup.get(table_name)
                if not table:
                    logger.warning(f"Table {table_name} not found in full schema, skipping")
                    continue

                relevant_cols = column_filter_map.get(table_name, [])

                # Always add full table to filtered_schema (for modification options)
                llm_selected_tables_full.append(table)

                # If LLM provided specific columns, create truncated version
                if relevant_cols:
                    truncated_table = dict(table)  # Copy the table dict
                    all_columns = truncated_table.get("columns", [])

                    # Create normalized set of relevant columns for matching
                    # Remove underscores and lowercase (e.g., email_address -> emailaddress, EmailAddress -> emailaddress)
                    relevant_cols_normalized = {col.lower().replace("_", "") for col in relevant_cols}

                    # Keep only columns that match (case-insensitive, underscore-insensitive)
                    truncated_columns = [
                        col
                        for col in all_columns
                        if col.get("column_name", "").lower().replace("_", "") in relevant_cols_normalized
                    ]

                    # If no columns matched (LLM hallucinated column names), keep all columns
                    if not truncated_columns:
                        logger.warning(
                            f"Column filtering failed for {table_name} - no matching columns found. "
                            f"LLM selected: {relevant_cols}. Keeping all columns.",
                            extra={
                                "table": table_name,
                                "llm_columns": relevant_cols,
                                "actual_columns": [
                                    col.get("column_name") for col in all_columns[:10]
                                ],
                            },
                        )
                        # Fallback to all columns
                        llm_selected_tables_truncated.append(table)
                    else:
                        # Update the table with truncated columns
                        truncated_table["columns"] = truncated_columns
                        truncated_table["column_filtered"] = True  # Mark as filtered
                        llm_selected_tables_truncated.append(truncated_table)

                        logger.debug(
                            f"Filtered columns for {table_name}",
                            extra={
                                "table": table_name,
                                "original_count": len(all_columns),
                                "filtered_count": len(truncated_columns),
                                "relevant_columns": relevant_cols,
                            },
                        )
                else:
                    # No specific columns provided, include all columns in both versions
                    llm_selected_tables_truncated.append(table)

            logger.info(
                "Stage 2 completed: LLM selected relevant tables and columns",
                extra={
                    "llm_selected_count": len(llm_selected_tables_full),
                    "selected_tables": list(relevant_table_names_set),
                    "tables_with_column_filtering": len(llm_selected_tables_truncated),
                    "assessments": [
                        {
                            "table": a.table_name,
                            "relevant": a.is_relevant,
                            "reasoning": a.reasoning,
                            "relevant_columns": a.relevant_columns,
                        }
                        for a in selection_output.selected_tables
                    ],
                },
            )

            # Debug: Save the LLM selection reasoning
            save_debug_file(
                "llm_table_selection.json",
                {
                    "user_query": user_query,
                    "candidate_tables": candidate_table_names,
                    "llm_assessments": [
                        {
                            "table": a.table_name,
                            "is_relevant": a.is_relevant,
                            "reasoning": a.reasoning,
                            "relevant_columns": a.relevant_columns,
                            "column_count": len(a.relevant_columns),
                        }
                        for a in selection_output.selected_tables
                    ],
                    "selected_tables": list(relevant_table_names_set),
                    "column_filtering_summary": {
                        table_name: {
                            "relevant_columns": column_filter_map.get(table_name, []),
                            "column_count": len(column_filter_map.get(table_name, [])),
                        }
                        for table_name in relevant_table_names_set
                    },
                },
                step_name="filter_schema_stage2",
                include_timestamp=True,
            )

        except Exception as e:
            logger.warning(
                f"LLM table selection failed, falling back to all candidates: {str(e)}",
                exc_info=True,
            )
            # Fallback to all candidate tables if LLM fails
            llm_selected_tables_full = candidate_tables
            llm_selected_tables_truncated = candidate_tables

    # ============================================================================
    # STAGE 3: Foreign Key Expansion - Add tables needed for joins
    # ============================================================================
    logger.info("Stage 3: Expanding with foreign key related tables")

    foreign_keys_data = load_foreign_keys()

    with log_execution_time(logger, "stage3_foreign_key_expansion"):
        # Expand both schemas with FK-related tables
        # filtered_schema: Full columns (for modification options)
        filtered_schema_with_fks = expand_with_foreign_keys(
            selected_tables=llm_selected_tables_full,
            all_tables=full_schema,
            foreign_keys_data=foreign_keys_data,
        )

        # truncated_schema: Only relevant columns (for planner context)
        truncated_schema_with_fks = expand_with_foreign_keys(
            selected_tables=llm_selected_tables_truncated,
            all_tables=full_schema,
            foreign_keys_data=foreign_keys_data,
        )

    final_table_names = [
        table.get("table_name", "Unknown") for table in filtered_schema_with_fks
    ]

    logger.info(
        "3-stage schema filtering completed",
        extra={
            "full_table_count": len(full_schema),
            "stage1_candidates": len(candidate_tables),
            "stage2_llm_selected": len(llm_selected_tables_full),
            "stage3_filtered_with_fks": len(filtered_schema_with_fks),
            "stage3_truncated_with_fks": len(truncated_schema_with_fks),
            "final_tables": final_table_names,
        },
    )

    return {
        **state,
        "last_step": "filter_schema",
        "filtered_schema": filtered_schema_with_fks,  # Full columns for modification options
        "truncated_schema": truncated_schema_with_fks,  # Truncated columns for planner
    }
