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


top_most_relevant_tables = int(os.getenv("TOP_MOST_RELEVANT_TABLES", "6"))


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


def filter_schema(state: State, vector_store=None):
    """Filter schema to only the most relevant tables based on the query."""
    full_schema = state["schema"]
    user_query = state["user_question"]

    logger.info(
        "Starting schema filtering",
        extra={
            "total_tables": len(full_schema),
            "top_k": top_most_relevant_tables,
            "user_query": user_query,
        },
    )

    # Get the appropriate embedding model
    embedding_model = get_embedding_model()

    # Create documents with rich content
    documents = [
        Document(page_content=get_page_content(entry), metadata=entry)
        for entry in full_schema
    ]

    # Debug: Save the embedded content to a file
    debug_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "debug/embedded_content.json"
    )
    try:
        with open(debug_path, "w", encoding="utf-8") as f:
            debug_data = {
                "user_query": user_query,
                "embedded_documents": [
                    {
                        "table_name": doc.metadata.get("table_name"),
                        "embedded_text": doc.page_content,
                    }
                    for doc in documents
                ],
            }
            json.dump(debug_data, f, indent=2)
    except Exception as e:
        logger.warning(
            f"Could not save debug embedded content: {str(e)}",
            exc_info=True,
            extra={"debug_path": debug_path},
        )

    with log_execution_time(logger, "create_vector_store_and_search"):
        vector_store = InMemoryVectorStore.from_documents(
            documents=documents, embedding=embedding_model
        )

        relevant_tables = vector_store.similarity_search(
            query=user_query, k=top_most_relevant_tables
        )

    filtered_schema = [doc.metadata for doc in relevant_tables]

    # Log which tables were selected
    selected_tables = [table.get("table_name", "Unknown") for table in filtered_schema]
    logger.info(
        "Schema filtering completed",
        extra={
            "full_table_count": len(full_schema),
            "filtered_table_count": len(filtered_schema),
            "selected_tables": selected_tables,
        },
    )

    return {**state, "last_step": "filter_schema", "filtered_schema": filtered_schema}
