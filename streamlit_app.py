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
    load_thread_states,
    get_thread_queries,
)

load_dotenv()
logger = get_logger("streamlit")

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

# Custom CSS for layout and styling
st.markdown(
    """
    <style>
    /* Reduce main container vertical padding */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
    }

    /* Scrollable container styling */
    .scrollable-container {
        height: 200px;
        overflow-y: auto;
        overflow-x: hidden;
        padding-right: 10px;
    }
    /* Customize scrollbar */
    .scrollable-container::-webkit-scrollbar {
        width: 8px;
    }
    .scrollable-container::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 10px;
    }
    .scrollable-container::-webkit-scrollbar-thumb {
        background: #888;
        border-radius: 10px;
    }
    .scrollable-container::-webkit-scrollbar-thumb:hover {
        background: #555;
    }
    </style>
    """,
    unsafe_allow_html=True,
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
    # Check if query was terminated
    planner_output = output.get("planner_output", {})
    if planner_output.get("decision") == "terminate":
        st.error("🚫 Query Terminated")
        termination_reason = planner_output.get(
            "termination_reason",
            "The query cannot be answered with the available database schema.",
        )
        st.warning(termination_reason)
        st.info(
            "💡 **Tip:** Try asking a question related to the data in this database."
        )
        return None  # Return early, no results to display

    # Check if clarification is needed
    has_clarification = output.get("needs_clarification")
    if has_clarification:
        st.warning(
            "⚠️ Your question may benefit from clarification. "
            "The query was executed with best-guess assumptions - results are shown below. "
            "You can select a clarification to refine the query."
        )

        # Display clarification suggestions
        suggestions = output.get("clarification_suggestions", [])
        if suggestions:
            st.subheader("💡 Clarification Options")
            st.write("Click on a clarification to refine your query:")

            # Display each suggestion as a button
            for i, suggestion in enumerate(suggestions, 1):
                if st.button(
                    f"{i}. {suggestion}",
                    key=f"suggestion_{i}_{output.get('timestamp', '')}",
                    use_container_width=True,
                    type="secondary",
                ):
                    # Combine the original question with the clarification
                    original_question = output.get(
                        "user_question", st.session_state.question_input
                    )
                    combined_question = f"{original_question}. {suggestion}"
                    st.session_state.question_input = combined_question
                    # st.session_state.selected_query_id = None  # Commented out - no conversation tracking
                    st.rerun()

            st.divider()

        # Show planner output for debugging
        if output.get("planner_output"):
            with st.expander(
                "Planner Analysis (Ambiguities Detected)", icon="🔍", expanded=False
            ):
                planner_output = output["planner_output"]
                st.write(f"**Intent:** {planner_output.get('intent_summary', 'N/A')}")
                ambiguities = planner_output.get("ambiguities", [])
                if ambiguities:
                    st.write("**Ambiguities:**")
                    for amb in ambiguities:
                        st.write(f"  - {amb}")
                st.json(planner_output)

        # Continue to show query and results below
        # (Don't return early - let the rest of the function display results)

    if not output.get("query"):
        st.error("Query error.")
        st.error(output.get("result", "Unknown error"))
        return pd.DataFrame()

    # Display the executed SQL query
    with st.expander("Executed SQL Query", icon="📝", expanded=True):
        st.code(output["query"], language="sql")

    # Display planner ambiguities if they exist
    planner_output = output.get("planner_output", {})
    if isinstance(planner_output, dict):
        ambiguities = planner_output.get("ambiguities", [])
        if ambiguities:
            with st.expander(
                "⚠️ Planner Ambiguities & Assumptions", icon="💭", expanded=False
            ):
                st.write(
                    "The query planner detected the following ambiguities or made assumptions:"
                )
                for i, ambiguity in enumerate(ambiguities, 1):
                    st.write(f"{i}. {ambiguity}")
                st.info(
                    "💡 **Tip:** If the results don't match your expectations, "
                    "try asking a follow-up question to clarify these points."
                )

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
            # Adjust status message if clarification was suggested
            if has_clarification:
                st.info(
                    "✅ Query executed successfully (with assumptions - see clarifications above)"
                )
            else:
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
    """Initialize Streamlit session state."""
    # Query history state (each query is independent, not conversational)
    if "selected_thread_id" not in st.session_state:
        st.session_state.selected_thread_id = None

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

    # Create 2-column layout: Recent Queries sidebar + Main content
    query_list_col, main_col = st.columns([1.5, 3.5])

    # --- LEFT COLUMN: Recent Queries ---
    with query_list_col:
        st.subheader("📜 Recent Queries")

        # New query button
        if st.button("➕ New Query", use_container_width=True, type="primary"):
            st.session_state.selected_thread_id = None
            st.session_state.loaded_state = None
            st.session_state.question_input = ""
            st.session_state.show_results = False
            st.session_state.current_dataframe = None
            st.rerun()

        # Display query list in scrollable container
        threads = st.session_state.thread_states.get("threads", {})

        if threads:
            # Use container with max height for scrolling
            query_container = st.container(height=200)

            with query_container:
                # Sort threads by last_updated descending (most recent first)
                sorted_threads = sorted(
                    threads.items(),
                    key=lambda x: x[1].get("last_updated", ""),
                    reverse=True,
                )

                for thread_id, thread_info in sorted_threads:
                    original_query = thread_info.get("original_query", "Untitled")
                    queries = thread_info.get("queries", [])

                    # Get timestamp for display
                    try:
                        from datetime import datetime

                        dt = datetime.fromisoformat(thread_info.get("last_updated", ""))
                        time_display = dt.strftime("%m/%d %H:%M")
                    except Exception:
                        time_display = ""

                    # Truncate query for display
                    display_query = (
                        original_query[:50] + "..."
                        if len(original_query) > 50
                        else original_query
                    )

                    # Highlight selected query
                    is_selected = st.session_state.selected_thread_id == thread_id
                    button_type = "primary" if is_selected else "secondary"

                    if st.button(
                        f"{'🔵 ' if is_selected else ''}{display_query}\n`{time_display}`",
                        key=f"query_{thread_id}",
                        use_container_width=True,
                        type=button_type,
                    ):
                        # Load the query results
                        st.session_state.selected_thread_id = thread_id
                        if queries:
                            st.session_state.loaded_state = queries[0].get("state")
                        st.rerun()
        else:
            st.info("No queries yet. Enter a question below to get started!")

    # --- RIGHT COLUMN: Query Input and Parameters ---
    with main_col:
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

        # Query preferences
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
                index=0,
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

    # --- QUERY EXECUTION (Full Width Below) ---
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
            st.session_state.selected_thread_id = (
                None  # Clear selection to show new query
            )
            st.session_state.loaded_state = None
            st.session_state.show_results = False
            st.session_state.current_dataframe = None

            status = st.status("Querying database...")
            try:
                # Call query_database (creates a new independent thread)
                response = query_database(
                    user_question,
                    sort_order=sort_order,
                    result_limit=result_limit,
                    time_filter=time_filter,
                    thread_id=None,  # Each query is independent
                )

                # Extract state from response
                output = response["state"]

                # Reload thread states to show the new query in the sidebar
                reload_thread_states()

                # Update session state
                st.session_state.show_results = True

                # Update status based on result
                planner_output = output.get("planner_output", {})
                if planner_output.get("decision") == "terminate":
                    status.update(label="Query terminated", state="error")
                elif output.get("needs_clarification"):
                    status.update(
                        label="Query executed (clarification suggested)",
                        state="complete",
                    )
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
