"""Infer foreign key relationships from column naming patterns and vector similarity."""

import re
import os
from typing import List, Dict, Tuple, Optional
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.vectorstores import VectorStore
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_community.vectorstores.utils import filter_complex_metadata

from utils.llm_factory import is_using_ollama
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger("fk_inference")

# ID column naming patterns (case-sensitive regex)
ID_PATTERNS = [
    r'^(.+)ID$',           # ApplicationID, CompanyID
    r'^(.+)Id$',           # TagId, UserId
    r'^(.+)_ID$',          # Tag_ID, User_ID
    r'^(.+)_Id$',          # Tag_Id, User_Id
    r'^(.+)_id$',          # tag_id, user_id
]


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
            show_progress=False,
        )
    else:
        # Use OpenAI embeddings for cloud LLM
        return OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL"))


def detect_id_columns(table: Dict) -> List[Tuple[str, str]]:
    """
    Detect potential foreign key columns by ID naming pattern.

    Args:
        table: Table schema entry with columns

    Returns:
        List of (column_name, base_name) tuples
        Example: [("CompanyID", "Company"), ("UserID", "User")]
    """
    id_columns = []

    for column in table.get("columns", []):
        col_name = column["column_name"]

        for pattern in ID_PATTERNS:
            match = re.match(pattern, col_name, re.IGNORECASE)
            if match:
                base_name = match.group(1)
                id_columns.append((col_name, base_name))
                logger.debug(
                    f"Detected ID column: {col_name} (base: {base_name})",
                    extra={"table": table["table_name"], "column": col_name, "base": base_name}
                )
                break

    return id_columns


def has_existing_fk(column_name: str, existing_fks: List[Dict]) -> bool:
    """
    Check if a foreign key already exists for this column.

    Args:
        column_name: Column name to check
        existing_fks: List of existing foreign key entries

    Returns:
        True if FK already exists for this column
    """
    return any(fk.get("foreign_key") == column_name for fk in existing_fks)


def infer_pk_column(table: Dict) -> Optional[str]:
    """
    Infer the primary key column name from table metadata.

    Args:
        table: Table schema entry

    Returns:
        Primary key column name, or None if not found
    """
    # Check metadata for primary_key
    metadata = table.get("metadata", {})
    if metadata.get("primary_key"):
        return metadata["primary_key"]

    # Fallback: look for column named "ID" or "{TableName}ID"
    table_name = table.get("table_name", "")
    for column in table.get("columns", []):
        col_name = column["column_name"]
        if col_name in ("ID", "Id", "id"):
            return col_name
        # Try TableNameID pattern
        if col_name == f"{table_name}ID" or col_name == f"{table_name}Id":
            return col_name

    return None


def build_table_description(table: Dict) -> str:
    """
    Build searchable text description for a table.

    Note: We use a minimal structure ("Table: tb_Name") without long descriptions.
    Testing showed that adding full table descriptions dilutes the table name signal and
    reduces accuracy significantly (precision dropped from 70.5% to 68%, recall from 56.7% to 35%).

    Args:
        table: Table schema entry

    Returns:
        Minimal table description for optimal FK matching accuracy
    """
    return f"Table: {table['table_name']}"


def find_candidate_tables(
    base_name: str,
    filtered_schema: List[Dict],
    vector_store: VectorStore,
    source_table: str,
    top_k: int = 3
) -> List[Tuple[Dict, float]]:
    """
    Find candidate tables that might be referenced by a foreign key.

    Uses vector similarity search to find tables whose names/descriptions
    match the base name extracted from the ID column.

    Args:
        base_name: Base name extracted from ID column (e.g., "Company" from "CompanyID")
        filtered_schema: List of filtered table schema entries
        vector_store: Initialized vector store with table documents
        source_table: Table name containing the foreign key (to avoid self-reference)
        top_k: Number of candidates to return

    Returns:
        List of (table_dict, confidence_score) tuples
    """
    # Build search query matching the document format
    search_query = f"Table related to {base_name}"

    logger.debug(
        f"Searching for FK target: {search_query}",
        extra={"base_name": base_name, "source_table": source_table}
    )

    # Perform similarity search
    results = vector_store.similarity_search_with_score(
        query=search_query,
        k=min(top_k + 1, len(filtered_schema))  # +1 to account for self-reference filtering
    )

    # Filter out self-references and convert to (table, score) tuples
    candidates = []
    for doc, score in results:
        candidate_table = doc.metadata
        candidate_name = candidate_table.get("table_name")

        # Skip self-references
        if candidate_name == source_table:
            logger.debug(
                f"Skipping self-reference: {candidate_name}",
                extra={"source_table": source_table}
            )
            continue

        candidates.append((candidate_table, score))

        if len(candidates) >= top_k:
            break

    logger.debug(
        f"Found {len(candidates)} candidates for {base_name}",
        extra={
            "base_name": base_name,
            "candidates": [
                {"table": c[0]["table_name"], "score": c[1]}
                for c in candidates
            ]
        }
    )

    return candidates


def infer_foreign_keys(
    filtered_schema: List[Dict],
    confidence_threshold: float = 0.6,
    top_k: int = 3
) -> List[Dict]:
    """
    Infer foreign key relationships for filtered schema tables.

    This function:
    1. Detects ID columns in each table
    2. Uses vector similarity to find candidate target tables
    3. Adds inferred FKs above confidence threshold

    Args:
        filtered_schema: List of filtered table schema entries (typically 6-10 tables)
        confidence_threshold: Minimum confidence score to include an inferred FK (0.0-1.0)
        top_k: Number of candidate tables to consider per ID column

    Returns:
        Same schema with augmented foreign_keys fields
    """
    logger.info(
        "Starting foreign key inference",
        extra={
            "filtered_table_count": len(filtered_schema),
            "confidence_threshold": confidence_threshold,
            "top_k": top_k
        }
    )

    if not filtered_schema:
        logger.warning("No filtered schema provided for FK inference")
        return filtered_schema

    # Get embedding model
    embedding_model = get_embedding_model()

    # Build vector store from filtered tables
    with log_execution_time(logger, "build_vector_store"):
        table_docs = []
        for table in filtered_schema:
            content = build_table_description(table)
            table_docs.append(Document(page_content=content, metadata=table))

        # Filter complex metadata (Chroma only supports simple types)
        table_docs = filter_complex_metadata(table_docs)

        vector_store = Chroma.from_documents(
            documents=table_docs,
            embedding=embedding_model,
            collection_name="fk_inference_filtered"
        )

    logger.info(
        f"Built Chroma vector store with {len(table_docs)} tables",
        extra={"table_count": len(table_docs)}
    )

    # Track inference statistics
    total_id_columns = 0
    total_inferred_fks = 0
    total_skipped_existing = 0
    total_below_threshold = 0

    # Process each table
    for table in filtered_schema:
        table_name = table.get("table_name")
        existing_fks = table.get("foreign_keys", [])
        inferred_fks = []

        # Find ID columns
        id_columns = detect_id_columns(table)
        total_id_columns += len(id_columns)

        if not id_columns:
            logger.debug(
                f"No ID columns found in {table_name}",
                extra={"table": table_name}
            )
            continue

        logger.debug(
            f"Processing {len(id_columns)} ID columns in {table_name}",
            extra={
                "table": table_name,
                "id_columns": [col[0] for col in id_columns]
            }
        )

        # Process each ID column
        for column_name, base_name in id_columns:
            # Skip if FK already exists for this column
            if has_existing_fk(column_name, existing_fks):
                logger.debug(
                    f"FK already exists for {table_name}.{column_name}, skipping",
                    extra={"table": table_name, "column": column_name}
                )
                total_skipped_existing += 1
                continue

            # Find candidate tables
            candidates = find_candidate_tables(
                base_name=base_name,
                filtered_schema=filtered_schema,
                vector_store=vector_store,
                source_table=table_name,
                top_k=top_k
            )

            if not candidates:
                logger.debug(
                    f"No candidates found for {table_name}.{column_name}",
                    extra={"table": table_name, "column": column_name, "base_name": base_name}
                )
                continue

            # Take best candidate above threshold
            best_candidate, best_score = candidates[0]
            candidate_table_name = best_candidate.get("table_name")

            if best_score >= confidence_threshold:
                # Infer primary key column
                pk_column = infer_pk_column(best_candidate)

                inferred_fk = {
                    "foreign_key": column_name,
                    "primary_key_table": candidate_table_name,
                    "primary_key_column": pk_column,
                    "inferred": True,
                    "confidence": round(best_score, 3)
                }

                inferred_fks.append(inferred_fk)
                total_inferred_fks += 1

                logger.info(
                    f"Inferred FK: {table_name}.{column_name} → {candidate_table_name}.{pk_column}",
                    extra={
                        "source_table": table_name,
                        "foreign_key": column_name,
                        "target_table": candidate_table_name,
                        "target_column": pk_column,
                        "confidence": best_score,
                        "all_candidates": [
                            {"table": c[0]["table_name"], "score": c[1]}
                            for c in candidates
                        ]
                    }
                )
            else:
                total_below_threshold += 1
                logger.debug(
                    f"Best candidate below threshold for {table_name}.{column_name}: "
                    f"{candidate_table_name} (score: {best_score:.3f}, threshold: {confidence_threshold})",
                    extra={
                        "table": table_name,
                        "column": column_name,
                        "candidate": candidate_table_name,
                        "score": best_score,
                        "threshold": confidence_threshold
                    }
                )

        # Augment existing FKs with inferred ones
        if inferred_fks:
            table["foreign_keys"] = existing_fks + inferred_fks
            logger.debug(
                f"Added {len(inferred_fks)} inferred FKs to {table_name}",
                extra={
                    "table": table_name,
                    "inferred_count": len(inferred_fks),
                    "total_fks": len(table["foreign_keys"])
                }
            )

    logger.info(
        "Foreign key inference completed",
        extra={
            "total_id_columns": total_id_columns,
            "total_inferred_fks": total_inferred_fks,
            "total_skipped_existing": total_skipped_existing,
            "total_below_threshold": total_below_threshold,
            "tables_with_inferred_fks": sum(
                1 for t in filtered_schema
                if any(fk.get("inferred") for fk in t.get("foreign_keys", []))
            )
        }
    )

    return filtered_schema
