"""Thread management utility for JSON-based state persistence."""

import os
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from utils.logger import get_logger

logger = get_logger()

THREAD_STATE_FILE = "thread_states.json"


def serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serialize state to make it JSON-compatible.
    Converts LangChain message objects to dictionaries.

    Args:
        state: The state dict with potential non-serializable objects

    Returns:
        JSON-serializable state dict
    """
    serialized = state.copy()

    # Convert messages to serializable format
    if "messages" in serialized and serialized["messages"]:
        serialized["messages"] = [
            {
                "type": msg.__class__.__name__,
                "content": msg.content,
            }
            for msg in serialized["messages"]
        ]

    return serialized


def deserialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deserialize state to restore LangChain message objects.

    Args:
        state: The JSON state dict

    Returns:
        State dict with LangChain message objects restored
    """
    if not state:
        return state

    deserialized = state.copy()

    # Convert message dicts back to LangChain message objects
    if "messages" in deserialized and deserialized["messages"]:
        messages = []
        for msg_dict in deserialized["messages"]:
            msg_type = msg_dict.get("type", "HumanMessage")
            content = msg_dict.get("content", "")

            if msg_type == "HumanMessage":
                messages.append(HumanMessage(content=content))
            elif msg_type == "AIMessage":
                messages.append(AIMessage(content=content))
            elif msg_type == "SystemMessage":
                messages.append(SystemMessage(content=content))
            else:
                # Default to HumanMessage if unknown type
                messages.append(HumanMessage(content=content))

        deserialized["messages"] = messages

    return deserialized


def get_state_file_path() -> str:
    """Get the absolute path to the thread state file."""
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)), THREAD_STATE_FILE
    )


def load_thread_states() -> Dict[str, Any]:
    """
    Load thread states from JSON file.

    Returns:
        Dict with structure: {"threads": {"thread-id": {...}}}
    """
    file_path = get_state_file_path()

    if not os.path.exists(file_path):
        logger.info("Thread state file not found, creating new one")
        return {"threads": {}}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            states = json.load(f)
            logger.debug(f"Loaded {len(states.get('threads', {}))} threads")
            return states
    except Exception as e:
        logger.error(f"Error loading thread states: {e}", exc_info=True)
        return {"threads": {}}


def save_thread_states(states: Dict[str, Any]) -> None:
    """
    Save thread states to JSON file.

    Args:
        states: Thread states dict to save
    """
    file_path = get_state_file_path()

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(states, f, indent=2, ensure_ascii=False)
        logger.debug(f"Saved {len(states.get('threads', {}))} threads to state file")
    except Exception as e:
        logger.error(f"Error saving thread states: {e}", exc_info=True)


def create_thread(original_query: str) -> str:
    """
    Create a new thread and return its ID.

    Args:
        original_query: The first query that starts this conversation thread

    Returns:
        The generated thread_id (UUID)
    """
    thread_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    states = load_thread_states()

    states["threads"][thread_id] = {
        "thread_id": thread_id,
        "original_query": original_query,
        "created_at": timestamp,
        "last_updated": timestamp,
        "queries": [],  # Will be populated when first query executes
    }

    save_thread_states(states)

    logger.info(f"Created new thread: {thread_id}", extra={"query": original_query})

    return thread_id


def save_query_state(thread_id: str, user_question: str, state: Dict[str, Any]) -> str:
    """
    Save a query execution state to a thread.

    Args:
        thread_id: The thread ID
        user_question: The user's question for this query
        state: The complete workflow state/result to save

    Returns:
        The generated query_id (UUID)
    """
    query_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    states = load_thread_states()

    if thread_id not in states["threads"]:
        logger.warning(f"Thread {thread_id} not found, creating it")
        create_thread(user_question)

    # Serialize state to make it JSON-compatible
    serialized_state = serialize_state(state)

    # Add query to thread
    states["threads"][thread_id]["queries"].append({
        "query_id": query_id,
        "timestamp": timestamp,
        "user_question": user_question,
        "state": serialized_state,  # Store serialized workflow result
    })

    states["threads"][thread_id]["last_updated"] = timestamp

    save_thread_states(states)

    logger.debug(
        f"Saved query state to thread {thread_id}",
        extra={
            "query_id": query_id,
            "user_question": user_question,
            "query_count": len(states["threads"][thread_id]["queries"]),
        },
    )

    return query_id


def get_latest_query_state(thread_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the latest query state for a thread (for continuation).

    Args:
        thread_id: The thread ID

    Returns:
        The state dict from the latest query, or None if no queries
    """
    states = load_thread_states()

    if thread_id not in states["threads"]:
        logger.warning(f"Thread {thread_id} not found")
        return None

    queries = states["threads"][thread_id].get("queries", [])

    if not queries:
        return None

    # Deserialize state to restore LangChain message objects
    return deserialize_state(queries[-1]["state"])


def get_query_state(thread_id: str, query_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific query state by query_id.

    Args:
        thread_id: The thread ID
        query_id: The query ID

    Returns:
        The state dict for the query, or None if not found
    """
    states = load_thread_states()

    if thread_id not in states["threads"]:
        return None

    queries = states["threads"][thread_id].get("queries", [])

    for query in queries:
        if query["query_id"] == query_id:
            # Deserialize state to restore LangChain message objects
            return deserialize_state(query["state"])

    return None


def get_thread_queries(thread_id: str) -> List[Dict[str, Any]]:
    """
    Get all queries for a thread (for display in UI).

    Args:
        thread_id: The thread ID

    Returns:
        List of query dicts with 'query_id', 'timestamp', 'user_question', 'state'
    """
    states = load_thread_states()

    if thread_id not in states["threads"]:
        logger.warning(f"Thread {thread_id} not found")
        return []

    return states["threads"][thread_id].get("queries", [])


def get_thread_info(thread_id: str) -> Optional[Dict[str, Any]]:
    """
    Get full information about a thread.

    Args:
        thread_id: The thread ID

    Returns:
        Thread info dict or None if not found
    """
    states = load_thread_states()
    return states["threads"].get(thread_id)


def get_all_threads() -> Dict[str, Dict[str, Any]]:
    """
    Get all threads (for display in UI).

    Returns:
        Dict of thread_id -> thread info
    """
    states = load_thread_states()
    return states.get("threads", {})
