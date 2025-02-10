"""Filter the schema to only the most relevant tables based on the query with a vector search."""

import os
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.documents import Document

from agent.state import State

load_dotenv()

embedding_model = OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL"))

top_most_relevant_tables = int(os.getenv("TOP_MOST_RELEVANT_TABLES")) or 3


def get_page_content(entry):
    """Get the page content for the schema entry."""
    if "metadata" in entry:
        return (
            f"{entry['table_name']}: {entry['metadata'].get('description', '')}".strip()
        )
    else:
        return f"{entry['table_name']}".strip()


def filter_schema(state: State, vector_store=None):
    """Filter schema to only the most relevant tables based on the query."""
    full_schema = state["schema"]
    user_query = state["user_question"]

    documents = [
        Document(page_content=get_page_content(entry), metadata=entry)
        for entry in full_schema
    ]

    vector_store = InMemoryVectorStore.from_documents(
        documents=documents, embedding=embedding_model
    )

    relevant_tables = vector_store.similarity_search(
        query=user_query, k=top_most_relevant_tables
    )

    filtered_schema = [doc.metadata for doc in relevant_tables]

    return {**state, "last_step": "filter_schema", "schema": filtered_schema}
