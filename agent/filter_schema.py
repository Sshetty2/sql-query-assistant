from langchain.embeddings import OpenAIEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.documents import Document
from agent.state import State
import os

embedding_model = OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL"))

def get_page_content(entry):
    if "metadata" in entry:
        return f"{entry['table_name']}: {entry['metadata'].get('description', '')}".strip()
    else:
        return f"{entry['table_name']}".strip()

def filter_schema(state: State, vector_store=None):
    """Filter schema to only the most relevant tables based on the query."""
    full_schema = state["schema"]
    user_query = state["user_question"]

    # Prepare documents: Use table description if available, otherwise just table name
    documents = [
        Document(
            page_content=get_page_content(entry),
            metadata=entry  # Store the entire entry
        )
        for entry in full_schema  # Iterate directly over list items
    ]

    # Create vector store from documents    
    vector_store = InMemoryVectorStore.from_documents(
        documents=documents, 
        embedding=embedding_model
    )

    # Get most relevant tables
    relevant_tables = vector_store.similarity_search(
        query=user_query,
        k=5
    )

    # Extract filtered schema with full table information
    filtered_schema = [
        doc.metadata for doc in relevant_tables
    ]
    
    return {
        **state,
        "last_step": "filter_schema",
        "schema": filtered_schema
    }