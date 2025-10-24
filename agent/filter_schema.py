"""Filter the schema to only the most relevant tables based on the query with a vector search."""

import os
import json
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.documents import Document

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
        "domain-specific-foreign-keys.json"
    )
    try:
        with open(fk_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(
            f"Could not load foreign keys file: {str(e)}",
            exc_info=True,
            extra={"fk_path": fk_path}
        )
        return []


def expand_with_foreign_keys(selected_tables, all_tables, foreign_keys_data):
    """
    Expand the selected tables with tables linked via foreign keys.

    Args:
        selected_tables: List of table schema entries selected by LLM
        all_tables: Complete list of all table schema entries
        foreign_keys_data: Foreign key mappings loaded from JSON

    Returns:
        Expanded list of table schema entries including foreign key related tables
    """
    # Create a mapping of table_name -> schema entry for quick lookup
    table_lookup = {table.get("table_name"): table for table in all_tables}

    # Create a mapping of table_name -> foreign key info
    fk_lookup = {item["table_name"]: item["foreign_keys"] for item in foreign_keys_data}

    # Start with selected tables
    selected_table_names = {table.get("table_name") for table in selected_tables}
    expanded_table_names = set(selected_table_names)

    logger.info(
        "Starting foreign key expansion",
        extra={
            "initial_table_count": len(selected_table_names),
            "selected_tables": list(selected_table_names)
        }
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
                                "referenced_table": referenced_table
                            }
                        )
                        expanded_table_names.add(referenced_table)

    # Convert table names back to schema entries
    expanded_tables = [
        table_lookup[name] for name in expanded_table_names
        if name in table_lookup
    ]

    logger.info(
        "Foreign key expansion completed",
        extra={
            "initial_count": len(selected_table_names),
            "final_count": len(expanded_tables),
            "added_tables": list(expanded_table_names - selected_table_names)
        }
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
        include_timestamp=True
    )

    with log_execution_time(logger, "stage1_vector_search"):
        vector_store = InMemoryVectorStore.from_documents(
            documents=documents, embedding=embedding_model
        )

        candidate_docs = vector_store.similarity_search(
            query=user_query, k=top_most_relevant_tables_vector
        )

    candidate_tables = [doc.metadata for doc in candidate_docs]
    candidate_table_names = [table.get("table_name", "Unknown") for table in candidate_tables]

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

    # Prepare a concise summary for each candidate table
    table_summaries = []
    for table in candidate_tables:
        table_name = table.get("table_name", "Unknown")
        metadata = table.get("metadata", {})
        description = metadata.get("description", "No description available")
        key_columns = metadata.get("key_columns", [])

        summary = f"**{table_name}**\n"
        summary += f"Description: {description}\n"
        if key_columns:
            summary += f"Key columns: {', '.join(key_columns)}"

        table_summaries.append(summary)

    # Construct the LLM prompt
    llm_prompt = f"""You are analyzing database tables to determine which ones are relevant for answering a user's query.

User Query: {user_query}

Candidate Tables (from vector search):
{chr(10).join(f"{i+1}. {summary}" for i, summary in enumerate(table_summaries))}

For each table, determine if it is directly relevant to answering the user's query.
Be selective - only mark a table as relevant if it's truly needed.
Consider:
- Does the table contain data that directly answers the query?
- Is the table needed for filtering, aggregation, or joining to get the answer?
- Avoid including tables that are only tangentially related.

Provide your assessment for each table."""

    with log_execution_time(logger, "stage2_llm_reasoning"):
        llm = get_chat_llm(model_name=os.getenv("AI_MODEL"), temperature=0)
        structured_llm = llm.with_structured_output(TableSelectionOutput)

        try:
            selection_output = structured_llm.invoke(llm_prompt)

            # Filter to only relevant tables
            relevant_assessments = [
                assessment for assessment in selection_output.selected_tables
                if assessment.is_relevant
            ]

            relevant_table_names_set = {
                assessment.table_name for assessment in relevant_assessments
            }

            # Get the actual schema entries for relevant tables
            llm_selected_tables = [
                table for table in candidate_tables
                if table.get("table_name") in relevant_table_names_set
            ]

            logger.info(
                "Stage 2 completed: LLM selected relevant tables",
                extra={
                    "llm_selected_count": len(llm_selected_tables),
                    "selected_tables": list(relevant_table_names_set),
                    "assessments": [
                        {
                            "table": a.table_name,
                            "relevant": a.is_relevant,
                            "reasoning": a.reasoning
                        }
                        for a in selection_output.selected_tables
                    ]
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
                            "reasoning": a.reasoning
                        }
                        for a in selection_output.selected_tables
                    ],
                    "selected_tables": list(relevant_table_names_set)
                },
                step_name="filter_schema_stage2",
                include_timestamp=True
            )

        except Exception as e:
            logger.warning(
                f"LLM table selection failed, falling back to all candidates: {str(e)}",
                exc_info=True
            )
            # Fallback to all candidate tables if LLM fails
            llm_selected_tables = candidate_tables

    # ============================================================================
    # STAGE 3: Foreign Key Expansion - Add tables needed for joins
    # ============================================================================
    logger.info("Stage 3: Expanding with foreign key related tables")

    foreign_keys_data = load_foreign_keys()

    with log_execution_time(logger, "stage3_foreign_key_expansion"):
        final_schema = expand_with_foreign_keys(
            selected_tables=llm_selected_tables,
            all_tables=full_schema,
            foreign_keys_data=foreign_keys_data
        )

    final_table_names = [table.get("table_name", "Unknown") for table in final_schema]

    logger.info(
        "3-stage schema filtering completed",
        extra={
            "full_table_count": len(full_schema),
            "stage1_candidates": len(candidate_tables),
            "stage2_llm_selected": len(llm_selected_tables),
            "stage3_final_with_fks": len(final_schema),
            "final_tables": final_table_names,
        },
    )

    return {**state, "last_step": "filter_schema", "filtered_schema": final_schema}
