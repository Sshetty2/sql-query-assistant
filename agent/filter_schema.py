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
from utils.llm_factory import is_using_ollama, get_model_for_stage
from utils.logger import get_logger, log_execution_time
from utils.stream_utils import emit_node_status, log_and_stream

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


def load_table_metadata():
    """Load table metadata from the domain-specific JSON file."""
    metadata_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "domain_specific_guidance",
        "domain-specific-table-metadata.json",
    )
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata_list = json.load(f)
            # Convert to dict for O(1) lookups
            return {item["table_name"]: item for item in metadata_list}
    except Exception as e:
        logger.warning(
            f"Could not load table metadata file: {str(e)}",
            exc_info=True,
            extra={"metadata_path": metadata_path},
        )
        return {}


def load_domain_guidance():
    """Load domain-specific guidance markdown if available."""
    guidance_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "domain_specific_guidance",
        "domain-specific-guidance-instructions.md",
    )
    try:
        if os.path.exists(guidance_path):
            with open(guidance_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        logger.warning(
            f"Could not load domain guidance: {str(e)}",
            exc_info=True,
            extra={"guidance_path": guidance_path},
        )
    return None


def expand_with_mapping_tables(selected_tables, all_tables, table_metadata):
    """
    Recursively expand the selected tables with their associated mapping/junction tables.

    Mapping tables are often junction tables that link entities together (e.g.,
    tb_CVECDAMap links CVEs to CDAs). These tables might not show up in vector
    search but are crucial for accurate query construction.

    This function continues recursively until no new mapping tables are found.
    No depth limit - the mapping_tables in metadata are already curated and critical.

    Args:
        selected_tables: List of table schema entries selected by vector search
        all_tables: Complete list of all table schema entries
        table_metadata: Dictionary mapping table_name -> metadata (with mapping_tables)

    Returns:
        Expanded list including all mapping tables recursively associated with selected tables
    """
    if not table_metadata:
        logger.info("No table metadata available, skipping mapping table expansion")
        return selected_tables

    # Create lookup for O(1) access
    table_lookup = {table.get("table_name"): table for table in all_tables}
    selected_table_names = {table.get("table_name") for table in selected_tables}
    expanded_table_names = set(selected_table_names)

    mapping_tables_added = []
    iteration = 0

    logger.info(
        "Starting recursive mapping table expansion (no depth limit)",
        extra={
            "initial_table_count": len(selected_table_names),
            "initial_tables": list(selected_table_names),
        },
    )

    # Keep expanding until no new tables are added
    while True:
        iteration += 1
        new_tables_this_iteration = []

        # Check all currently expanded tables for their mapping tables
        for table_name in list(expanded_table_names):
            metadata = table_metadata.get(table_name, {})
            mapping_tables = metadata.get("mapping_tables", [])

            for mapping_table in mapping_tables:
                if (
                    mapping_table not in expanded_table_names
                    and mapping_table in table_lookup
                ):
                    expanded_table_names.add(mapping_table)
                    new_tables_this_iteration.append(mapping_table)
                    mapping_tables_added.append(
                        {
                            "iteration": iteration,
                            "from_table": table_name,
                            "mapping_table": mapping_table,
                        }
                    )
                    logger.debug(
                        f"Adding mapping table at iteration {iteration}",
                        extra={
                            "iteration": iteration,
                            "from_table": table_name,
                            "mapping_table": mapping_table,
                        },
                    )

        # If no new tables were added, we're done
        if not new_tables_this_iteration:
            logger.info(
                f"Mapping table expansion converged after {iteration} iterations",
                extra={"iteration": iteration},
            )
            break

        logger.debug(
            f"Iteration {iteration}: Added {len(new_tables_this_iteration)} new tables",
            extra={
                "iteration": iteration,
                "new_tables": new_tables_this_iteration,
                "total_expanded": len(expanded_table_names),
            },
        )

    # Convert table names back to schema entries
    expanded_tables = []
    for name in expanded_table_names:
        if name in table_lookup:
            expanded_tables.append(table_lookup[name])

    logger.info(
        "Recursive mapping table expansion completed",
        extra={
            "initial_count": len(selected_tables),
            "final_count": len(expanded_tables),
            "total_iterations": iteration,
            "mapping_tables_added": [m["mapping_table"] for m in mapping_tables_added],
            "detailed_additions": mapping_tables_added,
        },
    )

    return expanded_tables


def expand_with_foreign_keys(
    selected_tables, all_tables, foreign_keys_data, max_depth=2
):
    """
    Recursively expand the selected tables with tables linked via foreign keys.

    Args:
        selected_tables: List of table schema entries selected by vector search or LLM
        all_tables: Complete list of all table schema entries
        foreign_keys_data: Foreign key mappings loaded from JSON
        max_depth: Maximum recursion depth (default: 2 = immediate + 1 level indirect)

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
        "Starting recursive foreign key expansion",
        extra={
            "initial_table_count": len(selected_table_names),
            "selected_tables": list(selected_table_names),
            "max_depth": max_depth,
        },
    )

    # Track tables added at each depth level for logging
    depth_additions = {0: list(selected_table_names)}

    # Recursively expand FK relationships up to max_depth
    current_level_tables = set(selected_table_names)
    for depth in range(1, max_depth + 1):
        next_level_tables = set()

        # For each table at current level, find FK references
        for table_name in current_level_tables:
            if table_name in fk_lookup:
                foreign_keys = fk_lookup[table_name]
                for fk in foreign_keys:
                    referenced_table = fk.get("primary_key_table", "")
                    if referenced_table and referenced_table in table_lookup:
                        if referenced_table not in expanded_table_names:
                            logger.debug(
                                f"Adding FK table at depth {depth}",
                                extra={
                                    "from_table": table_name,
                                    "foreign_key": fk.get("foreign_key"),
                                    "referenced_table": referenced_table,
                                    "depth": depth,
                                },
                            )
                            expanded_table_names.add(referenced_table)
                            next_level_tables.add(referenced_table)

        depth_additions[depth] = list(next_level_tables)

        # If no new tables added, stop early
        if not next_level_tables:
            logger.info(
                f"FK expansion stopped at depth {depth} (no new tables)",
                extra={"depth": depth},
            )
            break

        # Prepare for next iteration
        current_level_tables = next_level_tables

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
        "Recursive foreign key expansion completed",
        extra={
            "initial_count": len(selected_table_names),
            "final_count": len(expanded_tables),
            "added_tables": list(expanded_table_names - selected_table_names),
            "tables_by_depth": depth_additions,
        },
    )

    return expanded_tables


def filter_schema(state: State, vector_store=None):
    """
    Filter schema to only the most relevant tables based on the query.

    This uses a five-stage approach:
    1. Vector search to get top-k candidate tables
    1.5. Mapping table expansion - add junction tables from metadata
    2. Recursive foreign key expansion on candidates (2 levels deep)
    3. LLM reasoning to select relevant tables/columns from expanded candidates
    4. Return filtered schema with column filtering applied
    """
    from utils.llm_factory import get_chat_llm
    from models.table_selection import TableSelectionOutput

    # Emit status update
    emit_node_status("filter_schema", "running", "Filtering relevant tables")

    full_schema = state["schema"]
    user_query = state["user_question"]

    log_and_stream(
        logger,
        "filter_schema",
        "Starting 5-stage schema filtering",
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

    # Debug: Save the vector search results
    try:
        save_debug_file(
            "vector_search_candidates.json",
            {
                "user_query": user_query,
                "top_k": top_most_relevant_tables_vector,
                "candidate_count": len(candidate_tables),
                "candidate_tables": candidate_table_names,
                "candidates_with_scores": [
                    {
                        "table_name": doc.metadata.get("table_name"),
                        "description": doc.metadata.get("metadata", {}).get(
                            "description", ""
                        ),
                        "page_content": (str(doc.page_content)),
                    }
                    for doc in candidate_docs
                ],
            },
            step_name="filter_schema_stage1_results",
            include_timestamp=True,
        )
    except Exception as e:
        logger.warning(f"Failed to save debug file for stage1 results: {e}")

    logger.info(
        "Stage 1 completed: Vector search candidates",
        extra={
            "candidate_count": len(candidate_tables),
            "candidate_tables": candidate_table_names,
        },
    )

    # ============================================================================
    # STAGE 1.5: Mapping Table Expansion - Add associated junction/mapping tables
    # ============================================================================
    logger.info("Stage 1.5: Adding mapping tables from metadata")

    table_metadata = load_table_metadata()

    with log_execution_time(logger, "stage1.5_mapping_table_expansion"):
        # Add mapping tables that are associated with selected candidates
        # This ensures junction tables (like tb_CVECDAMap) are included
        mapping_expanded_candidates = expand_with_mapping_tables(
            selected_tables=candidate_tables,
            all_tables=full_schema,
            table_metadata=table_metadata,
        )

    mapping_expanded_table_names = [
        table.get("table_name", "Unknown") for table in mapping_expanded_candidates
    ]

    # Debug: Save mapping expansion results
    save_debug_file(
        "mapping_expansion_results.json",
        {
            "user_query": user_query,
            "stage1_candidates": candidate_table_names,
            "mapping_expanded_count": len(mapping_expanded_candidates),
            "mapping_expanded_tables": mapping_expanded_table_names,
            "tables_added_by_mapping": list(
                set(mapping_expanded_table_names) - set(candidate_table_names)
            ),
        },
        step_name="filter_schema_stage1_5_results",
        include_timestamp=True,
    )

    logger.info(
        "Stage 1.5 completed: Mapping table expansion",
        extra={
            "mapping_expanded_count": len(mapping_expanded_candidates),
            "mapping_expanded_tables": mapping_expanded_table_names,
            "tables_added_by_mapping": list(
                set(mapping_expanded_table_names) - set(candidate_table_names)
            ),
        },
    )

    # ============================================================================
    # STAGE 2: Foreign Key Expansion - Add FK-related tables to candidates
    # ============================================================================
    logger.info("Stage 2: Recursively expanding candidates with FK-related tables")

    foreign_keys_data = load_foreign_keys()

    with log_execution_time(logger, "stage2_foreign_key_expansion"):
        # Expand candidates with FK-related tables (2 levels deep)
        # This ensures LLM can see and filter columns from junction/join tables
        fk_expanded_candidates = expand_with_foreign_keys(
            selected_tables=mapping_expanded_candidates,  # Use mapping-expanded list
            all_tables=full_schema,
            foreign_keys_data=foreign_keys_data,
            max_depth=2,  # Immediate FKs + 1 level of indirect relationships
        )

    fk_expanded_table_names = [
        table.get("table_name", "Unknown") for table in fk_expanded_candidates
    ]

    # Debug: Save FK expansion results
    save_debug_file(
        "fk_expansion_results.json",
        {
            "user_query": user_query,
            "stage1_5_mapping_expanded": mapping_expanded_table_names,
            "fk_expanded_count": len(fk_expanded_candidates),
            "fk_expanded_tables": fk_expanded_table_names,
            "tables_added_by_fk": list(
                set(fk_expanded_table_names) - set(mapping_expanded_table_names)
            ),
        },
        step_name="filter_schema_stage2_fk_expansion",
        include_timestamp=True,
    )

    logger.info(
        "Stage 2 completed: FK expansion",
        extra={
            "initial_candidates": len(candidate_tables),
            "after_fk_expansion": len(fk_expanded_candidates),
            "added_by_fk": list(
                set(fk_expanded_table_names) - set(candidate_table_names)
            ),
        },
    )

    # Update candidate_tables to use FK-expanded set for LLM stage
    candidate_tables = fk_expanded_candidates
    candidate_table_names = fk_expanded_table_names

    # ============================================================================
    # STAGE 3: LLM Reasoning - Select truly relevant tables and columns
    # ============================================================================
    logger.info("Stage 3: Using LLM to reason about table/column relevance")

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
                extra={"table": table_name},
            )

        table_summaries.append(summary)

    # Load domain guidance if available
    domain_guidance = load_domain_guidance()
    domain_guidance_section = ""
    if domain_guidance:
        domain_guidance_section = f"""
        ## Domain-Specific Guidance

        The following domain-specific guidance will help you understand the database structure,
        terminology, and common query patterns for this domain:

        {domain_guidance}

        ---
        """

    # Construct the system message (context about the problem)
    system_message = dedent(
        f"""
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

        {domain_guidance_section}

        ## Guidelines for Column Selection

        **CRITICAL CONSTRAINT:** You MUST only select columns from the exact "Available columns"
        list shown for each table. Do NOT invent, suggest, or assume column names that aren't
        explicitly listed. Use the EXACT column names as shown (preserve casing).

        Please be selective and only include columns that are:
        - **Displayed in output** - Information the user explicitly wants to see
        - **Human-readable identifiers** - User-facing names, labels, descriptions (e.g., CDAName, Vendor, ProductName)
        - **Used for filtering** - Columns users might reference in queries (not just internal IDs)
        - **Used for aggregation** - Columns needed in COUNT, SUM, AVG, etc.
        - **Used for sorting** - Columns needed in ORDER BY
        - **Required for joins** - Foreign key columns that connect tables

        **IMPORTANT - Include Display Columns:**
        When selecting columns, prioritize human-readable columns over internal IDs:
        - ✅ Include: CDAName, Vendor, ProductName, Description (user-facing identifiers)
        - ⚠️ Also include: CDAID, ProductID (needed for joins/relationships)
        - Don't rely solely on primary keys - users reference things by name, not ID

        **Example:**
        If a table shows: "Available columns: ID, ScanID, ComputerID, Name, Description"
        Then you can ONLY select from: ID, ScanID, ComputerID, Name, Description
        You CANNOT select: computer_id, scan_id, DeviceName, or any other columns not in the list.

        **Important:** When in doubt, be liberal and include columns from the available list,
        especially human-readable names and identifiers that users might reference or want to see.
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
        filtering_model = get_model_for_stage("filtering")
        llm = get_chat_llm(model_name=filtering_model)
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
                step_name="filter_schema_stage3_llm",
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
            llm_selected_tables_truncated = (
                []
            )  # Truncated columns (for truncated_schema)

            for table_name in relevant_table_names_set:
                # Get the FULL table with columns from the original schema
                table = full_schema_lookup.get(table_name)
                if not table:
                    logger.warning(
                        f"Table {table_name} not found in full schema, skipping"
                    )
                    continue

                relevant_cols = column_filter_map.get(table_name, [])

                # Always add full table to filtered_schema (for modification options)
                llm_selected_tables_full.append(table)

                # If LLM provided specific columns, create truncated version
                if relevant_cols:
                    truncated_table = dict(table)  # Copy the table dict
                    all_columns = truncated_table.get("columns", [])

                    # Create normalized set of relevant columns for matching
                    # Remove underscores and lowercase (e.g., email_address -> emailaddress, EmailAddress -> emailaddress)  # noqa: E501
                    relevant_cols_normalized = {
                        col.lower().replace("_", "") for col in relevant_cols
                    }

                    # Keep only columns that match (case-insensitive, underscore-insensitive)
                    truncated_columns = [
                        col
                        for col in all_columns
                        if col.get("column_name", "").lower().replace("_", "")
                        in relevant_cols_normalized
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
                "Stage 3 completed: LLM selected relevant tables and columns",
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
                step_name="filter_schema_stage3",
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
    # Finalize filtered schema
    # ============================================================================
    # Note: FK expansion already happened in Stage 2, so LLM selections already
    # include FK-related tables with appropriate column filtering

    filtered_schema_with_fks = llm_selected_tables_full
    truncated_schema_with_fks = llm_selected_tables_truncated

    final_table_names = [
        table.get("table_name", "Unknown") for table in filtered_schema_with_fks
    ]

    logger.info(
        "4-stage schema filtering completed",
        extra={
            "full_table_count": len(full_schema),
            "stage1_vector_candidates": top_most_relevant_tables_vector,
            "stage2_fk_expanded": len(fk_expanded_candidates),
            "stage3_llm_selected": len(llm_selected_tables_full),
            "final_filtered_schema": len(filtered_schema_with_fks),
            "final_truncated_schema": len(truncated_schema_with_fks),
            "final_tables": final_table_names,
        },
    )

    emit_node_status("filter_schema", "completed")

    return {
        **state,
        "last_step": "filter_schema",
        "filtered_schema": filtered_schema_with_fks,  # Full columns for modification options
        "truncated_schema": truncated_schema_with_fks,  # Truncated columns for planner
    }
