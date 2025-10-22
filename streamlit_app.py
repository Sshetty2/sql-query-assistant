"""Streamlit app for querying the database. The agent is intended to be used from an API"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from agent.query_database import query_database
from utils.logger import get_logger
from utils.thread_manager import (
    get_all_threads,
    load_thread_states,
    get_thread_queries,
    get_query_state,
)

load_dotenv()
logger = get_logger()

use_test_db = os.getenv("USE_TEST_DB").lower() == "true"


def load_sample_queries():
    """Load sample queries based on database type."""
    current_dir = os.path.dirname(os.path.abspath(__file__))

    filename = (
        "test-db-queries.json"
        if use_test_db
        else "domain_specific_guidance/domain-specific-sample-queries.json"
    )
    file_path = os.path.join(current_dir, filename)

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        logger.error(
            f"Error loading sample queries: {str(e)}",
            exc_info=True,
            extra={"file_path": file_path},
        )
        return {}


SAMPLE_QUERIES = load_sample_queries()

st.set_page_config(
    page_title="SQL Query Assistant", layout="wide", initial_sidebar_state="auto"
)

st.title("SQL Query Assistant")


def format_results(result):
    """Convert query results into a pandas DataFrame."""
    try:
        if not result:
            return pd.DataFrame()

        # Result is now a JSON string from execute_query
        if isinstance(result, str):
            data = json.loads(result)
        else:
            data = result

        if not data:
            return pd.DataFrame()

        return pd.DataFrame(data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"Error formatting results: {str(e)}", exc_info=True)
        return pd.DataFrame()


def render_query_results(
    output: dict, status_label: str = "Query executed successfully!"
) -> pd.DataFrame:
    """
    Render query results UI elements based on output state.
    This function can be used for both fresh executions and loaded history.

    Args:
        output: The state dict containing query, result, planner_output, etc.
        status_label: Label to show in the status message

    Returns:
        pandas DataFrame of results, or empty DataFrame if no results
    """
    # Check if clarification is needed
    if output.get("needs_clarification"):
        st.warning(
            "⚠️ Your question is ambiguous. Please select one of the "
            "suggestions below or rephrase your question."
        )

        # Display clarification suggestions
        suggestions = output.get("clarification_suggestions", [])
        if suggestions:
            st.subheader("💡 Suggested Query Rewrites")
            st.write("Click on a suggestion to use it:")

            # Display each suggestion as a button
            for i, suggestion in enumerate(suggestions, 1):
                if st.button(
                    f"{i}. {suggestion}",
                    key=f"suggestion_{i}_{output.get('timestamp', '')}",
                    use_container_width=True,
                    type="primary",
                ):
                    # Set the suggestion as the new question in session state
                    st.session_state.question_input = suggestion
                    st.session_state.selected_query_id = None
                    st.rerun()

            st.divider()
            st.write("**Or modify your original question:**")
            st.code(output.get("user_question", ""), language="text")

        # Show planner output for debugging
        if output.get("planner_output"):
            with st.expander("Planner Analysis", icon="🔍"):
                planner_output = output["planner_output"]
                st.write(f"**Intent:** {planner_output.get('intent_summary', 'N/A')}")
                ambiguities = planner_output.get("ambiguities", [])
                if ambiguities:
                    st.write("**Ambiguities:**")
                    for amb in ambiguities:
                        st.write(f"  - {amb}")
                st.json(planner_output)

        return pd.DataFrame()

    if not output.get("query"):
        st.error("Query error.")
        st.error(output.get("result", "Unknown error"))
        return pd.DataFrame()

    # Display the executed SQL query
    with st.expander("Executed SQL Query", icon="📝", expanded=True):
        st.code(output["query"], language="sql")

    # Display the query plan that generated this query
    if output.get("planner_output"):
        with st.expander("Query Plan Used", icon="🗺️"):
            st.write("This is the plan that was used to generate the executed query.")
            planner_output = output["planner_output"]

            # Show key information at the top
            if isinstance(planner_output, dict):
                st.write(f"**Intent:** {planner_output.get('intent_summary', 'N/A')}")
                st.write(f"**Decision:** {planner_output.get('decision', 'N/A')}")

                # Show tables involved
                selections = planner_output.get("selections", [])
                if selections:
                    tables = [sel.get("table") for sel in selections]
                    st.write(f"**Tables:** {', '.join(tables)}")

                # Show join information if present
                join_edges = planner_output.get("join_edges", [])
                if join_edges:
                    st.write(f"**Joins:** {len(join_edges)} join(s)")
                    for i, join in enumerate(join_edges, 1):
                        st.write(
                            f"  {i}. `{join.get('from_table')}.{join.get('from_column')}` "
                            f"→ `{join.get('to_table')}.{join.get('to_column')}` "
                            f"({join.get('join_type', 'inner')})"
                        )

            st.divider()
            st.write("**Full Plan JSON:**")
            st.json(planner_output)

    # Display error corrections and refinements
    if output.get("corrected_queries") or output.get("refined_queries"):
        with st.expander("Query History", icon="📜"):
            col1, col2 = st.columns(2)

            with col1:
                if output.get("retry_count", 0) > 0:
                    st.subheader("Error Corrections")
                    st.write("Retry count:", output["retry_count"])
                    for i, query in enumerate(output["corrected_queries"], 1):
                        st.write(f"**Attempt {i}:**")
                        st.write(f"❌ Error: `{output['error_history'][i-1]}`")

                        # Display error correction reasoning if available
                        if output.get("error_reasoning") and i <= len(
                            output["error_reasoning"]
                        ):
                            st.write(
                                f"💡 **Reasoning:** {output['error_reasoning'][i-1]}"
                            )

                        # Display the original failing query
                        st.write("**Original failing query:**")
                        st.code(query, language="sql")

                        # Display the corrected plan if available
                        if output.get("corrected_plans") and i <= len(
                            output["corrected_plans"]
                        ):
                            with st.expander("View corrected plan"):
                                st.json(output["corrected_plans"][i - 1])

                        st.divider()

            with col2:
                if output.get("refined_count", 0) > 0:
                    st.subheader("Query Refinements")
                    st.write("Refinement count:", output["refined_count"])
                    for i, query in enumerate(output["refined_queries"], 1):
                        st.write(f"**Refinement {i}:**")
                        st.write("⚠️ Previous query returned no results")

                        # Display refinement reasoning
                        st.write(
                            f"💡 **Reasoning:** {output['refined_reasoning'][i-1]}"
                        )

                        # Display the original query that returned no results
                        st.write("**Original query:**")
                        st.code(query, language="sql")

                        # Display the refined plan if available
                        if output.get("refined_plans") and i <= len(
                            output["refined_plans"]
                        ):
                            with st.expander("View refined plan"):
                                st.json(output["refined_plans"][i - 1])

                        st.divider()

    # Display results
    tab1, tab2 = st.tabs(["Table View", "Raw Data"])

    if output.get("result") is None:
        st.warning("Query returned no results.")
        return pd.DataFrame()

    df = format_results(output["result"])

    with tab1:
        if not df.empty:
            st.success(status_label)

            st.dataframe(
                df,
                hide_index=True,
                column_config={
                    col: st.column_config.TextColumn(col, help="", width="auto")
                    for col in df.columns
                },
            )
        else:
            st.warning("Query returned no results.")

    with tab2:
        st.text_area(
            "Raw Results:",
            value=output["result"],
            height=200,
            disabled=True,
        )

    return df


def initialize_session_state():
    """Initialize Streamlit session state for thread management."""
    if "selected_thread_id" not in st.session_state:
        st.session_state.selected_thread_id = None

    if "selected_query_id" not in st.session_state:
        st.session_state.selected_query_id = None

    if "thread_states" not in st.session_state:
        st.session_state.thread_states = load_thread_states()

    if "question_input" not in st.session_state:
        st.session_state.question_input = ""

    if "loaded_state" not in st.session_state:
        st.session_state.loaded_state = None

    if "current_dataframe" not in st.session_state:
        st.session_state.current_dataframe = None

    if "show_results" not in st.session_state:
        st.session_state.show_results = False


def reload_thread_states():
    """Reload thread states from file."""
    st.session_state.thread_states = load_thread_states()


def main():
    """Main function for the Streamlit app."""
    # Initialize session state
    initialize_session_state()

    # Create 3-column layout for thread management
    thread_col, query_col, history_col = st.columns([1.2, 2.5, 1.3])

    # --- LEFT COLUMN: Thread List ---
    with thread_col:
        st.subheader("💬 Conversations")

        # New conversation button
        if st.button("➕ New Conversation", use_container_width=True, type="primary"):
            st.session_state.selected_thread_id = None
            st.session_state.selected_query_id = None
            st.session_state.loaded_state = None
            st.session_state.question_input = ""
            st.rerun()

        st.divider()

        # Display thread list
        threads = st.session_state.thread_states.get("threads", {})

        if threads:
            # Sort threads by last_updated descending
            sorted_threads = sorted(
                threads.items(),
                key=lambda x: x[1].get("last_updated", ""),
                reverse=True,
            )

            for thread_id, thread_info in sorted_threads:
                original_query = thread_info.get("original_query", "Untitled")
                query_count = len(thread_info.get("queries", []))

                # Truncate query for display
                display_query = (
                    original_query[:47] + "..."
                    if len(original_query) > 50
                    else original_query
                )

                # Highlight selected thread
                is_selected = st.session_state.selected_thread_id == thread_id
                button_type = "primary" if is_selected else "secondary"

                if st.button(
                    f"{'🔵 ' if is_selected else ''}{display_query}\n({query_count} queries)",
                    key=f"thread_{thread_id}",
                    use_container_width=True,
                    type=button_type,
                ):
                    st.session_state.selected_thread_id = thread_id
                    st.rerun()
        else:
            st.info("No conversations yet. Click 'New Conversation' to start!")

    # --- MIDDLE COLUMN: Query Input ---
    with query_col:
        # Show thread context
        if st.session_state.selected_thread_id:
            thread_info = threads.get(st.session_state.selected_thread_id, {})
            original_query = thread_info.get("original_query", "Unknown")
            st.caption(
                f"📍 Continuing: _{original_query[:60]}{'...' if len(original_query) > 60 else ''}_"
            )
        else:
            st.caption("📍 New Conversation")

        # Sample query selector
        sample_col1, sample_col2 = st.columns([1, 1])

        with sample_col1:
            category = st.selectbox(
                "Select a query category",
                ["Custom Query"] + list(SAMPLE_QUERIES.keys()),
            )

        with sample_col2:
            if category != "Custom Query":
                selected_query = st.selectbox(
                    "Select a sample query", SAMPLE_QUERIES[category]
                )
            else:
                selected_query = ""

        # Handle suggestion selection
        if (
            st.session_state.question_input
            and st.session_state.question_input != selected_query
        ):
            selected_query = st.session_state.question_input

        user_question = st.text_area(
            "What would you like to know about the database?",
            value=selected_query,
            height=100,
            placeholder=(
                "Find tracks that belong to a specific genre, like 'Rock'."
                if use_test_db
                else "e.g., What are the top 5 CVEs with the highest CVSS scores?"
            ),
        )

        # Query preferences in middle column
        pref_col1, pref_col2, pref_col3 = st.columns(3)

        with pref_col1:
            sort_order = st.selectbox(
                "Sort Order",
                ["Default", "Ascending", "Descending"],
                help="Choose the sort order for the results",
            )

        with pref_col2:
            result_limit = st.selectbox(
                "Limit Results",
                [0, 1, 5, 25, 100, 1000],
                help="Limit the number of returned records (0 = no limit)",
                index=4,
            )

        with pref_col3:
            time_filter = st.selectbox(
                "Time Filter",
                [
                    "All Time",
                    "Last 30 Days",
                    "Last 60 Days",
                    "Last 90 Days",
                    "Last Year",
                ],
                help="Filter results by time period",
                index=0,
            )

    # --- RIGHT COLUMN: Invocation History ---
    with history_col:
        st.subheader("📜 Query History")

        if st.session_state.selected_thread_id:
            queries = get_thread_queries(st.session_state.selected_thread_id)

            if queries:
                st.caption(f"{len(queries)} queries in this conversation")
                st.divider()

                for i, query_item in enumerate(reversed(queries), 1):
                    inv_query = query_item.get("user_question", "Unknown")
                    inv_timestamp = query_item.get("timestamp", "")

                    # Parse timestamp for display
                    try:
                        dt = datetime.fromisoformat(inv_timestamp)
                        time_display = dt.strftime("%m/%d %H:%M")
                    except Exception as e:
                        logger.error(
                            f"Error parsing timestamp: {str(e)}", exc_info=True
                        )
                        time_display = inv_timestamp[:16] if inv_timestamp else ""

                    # Truncate query for display
                    display_inv = (
                        inv_query[:40] + "..." if len(inv_query) > 43 else inv_query
                    )

                    # Highlight if this query is currently selected
                    is_query_selected = (
                        st.session_state.selected_query_id == query_item.get("query_id")
                    )
                    query_button_type = "primary" if is_query_selected else "secondary"

                    if st.button(
                        f"**{i}.** {display_inv}\n`{time_display}`",
                        key=f"inv_{st.session_state.selected_thread_id}_{i}",
                        use_container_width=True,
                        type=query_button_type,
                    ):
                        # Load the full query state for display
                        st.session_state.selected_query_id = query_item.get("query_id")
                        st.session_state.loaded_state = query_item.get("state")
                        st.rerun()
            else:
                st.info("No queries yet in this conversation")
        else:
            st.info("Select a conversation to view its history")

    # --- QUERY EXECUTION (spans full width) ---
    st.divider()

    # Button row: Generate Query and Download CSV on the same line
    button_col1, button_col2, button_col3 = st.columns([1, 1, 4])

    with button_col1:
        generate_clicked = st.button(
            "Generate Query", type="primary", use_container_width=True
        )

    with button_col2:
        # Only show download button if we have results
        if (
            st.session_state.current_dataframe is not None
            and not st.session_state.current_dataframe.empty
        ):
            csv = st.session_state.current_dataframe.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download CSV",
                csv,
                "query_results.csv",
                "text/csv",
                key="download-csv-main",
                use_container_width=True,
            )

    # Handle Generate Query button click
    if generate_clicked:
        if user_question:
            # Clear previous results and loaded state
            st.session_state.selected_query_id = None
            st.session_state.loaded_state = None
            st.session_state.show_results = False
            st.session_state.current_dataframe = None

            status = st.status("Querying database...")
            try:
                # Call query_database with thread_id
                response = query_database(
                    user_question,
                    sort_order=sort_order,
                    result_limit=result_limit,
                    time_filter=time_filter,
                    thread_id=st.session_state.selected_thread_id,
                )

                # Extract state, thread_id, and query_id from response
                output = response["state"]
                thread_id = response["thread_id"]
                query_id = response["query_id"]

                # Update session state with new/updated thread
                st.session_state.selected_thread_id = thread_id
                st.session_state.selected_query_id = query_id
                st.session_state.show_results = True
                reload_thread_states()

                # Update status based on result
                if output.get("needs_clarification"):
                    status.update(label="Clarification needed", state="error")
                elif not output.get("query"):
                    status.update(
                        label=output.get("result", "Query error"), state="error"
                    )
                elif output.get("result") is None:
                    status.update(label="No results found", state="error")
                else:
                    status.update(
                        label="Query executed successfully!", state="complete"
                    )

                # Render the results and store dataframe
                df = render_query_results(output)
                st.session_state.current_dataframe = df

            except Exception as e:
                status.update(label=f"Error: {str(e)}", state="error")
                st.error(f"An error occurred: {str(e)}")
                st.exception(e)
        else:
            st.warning("Please enter a question first.")

    # Display loaded state if a query from history is selected
    elif st.session_state.loaded_state:
        st.info(
            "📂 Viewing saved query results. Click 'Generate Query' to run a new query."
        )
        df = render_query_results(
            st.session_state.loaded_state, status_label="Loaded from history"
        )
        st.session_state.current_dataframe = df
        st.session_state.show_results = True


if __name__ == "__main__":
    main()
