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


def apply_column_patch(output: dict, table: str, column: str, operation: str, immediate_rerun: bool = True):
    """
    Apply a column add/remove patch and optionally re-execute the query.

    Args:
        output: Current state dict
        table: Table name
        column: Column name
        operation: "add_column" or "remove_column"
        immediate_rerun: If True, trigger rerun immediately. If False, store for batch processing.
    """
    try:
        executed_plan = output.get("executed_plan")
        filtered_schema = output.get("filtered_schema")
        thread_id = output.get("thread_id")

        if not executed_plan or not filtered_schema:
            st.error("Cannot apply patch: missing executed plan or schema")
            return

        # Build patch operation
        patch_op = {
            "operation": operation,
            "table": table,
            "column": column
        }

        if immediate_rerun:
            # Store patch in session state and trigger rerun immediately
            st.session_state.pending_patch = {
                "operation": patch_op,
                "executed_plan": executed_plan,
                "filtered_schema": filtered_schema,
                "thread_id": thread_id,
                "user_question": output.get("user_question", ""),
            }
            # Increment generation to get fresh controls after applying patch
            st.session_state.controls_generation = st.session_state.get("controls_generation", 0) + 1
            st.rerun()
        else:
            # Store for batch processing (will be applied when batch is triggered)
            if not hasattr(st.session_state, 'pending_batch_patches'):
                st.session_state.pending_batch_patches = []

            st.session_state.pending_batch_patches.append({
                "operation": patch_op,
                "executed_plan": executed_plan,
                "filtered_schema": filtered_schema,
                "thread_id": thread_id,
                "user_question": output.get("user_question", ""),
            })

    except Exception as e:
        st.error(f"Error applying column patch: {str(e)}")
        logger.error(f"Error in apply_column_patch: {str(e)}", exc_info=True)


def apply_sort_patch(output: dict, selected_sort: str, direction: str, sortable_columns: list, immediate_rerun: bool = True):
    """
    Apply an ORDER BY patch and optionally re-execute the query.

    Args:
        output: Current state dict
        selected_sort: Selected sort column display name or "No sorting"
        direction: "ASC" or "DESC"
        sortable_columns: List of sortable column dicts
        immediate_rerun: If True, trigger rerun immediately. If False, store for batch processing.
    """
    try:
        executed_plan = output.get("executed_plan")
        filtered_schema = output.get("filtered_schema")
        thread_id = output.get("thread_id")

        if not executed_plan or not filtered_schema:
            st.error("Cannot apply patch: missing executed plan or schema")
            return

        # Build ORDER BY specification
        order_by = []
        if selected_sort != "No sorting":
            # Find the matching column
            for col in sortable_columns:
                if col["display_name"] == selected_sort:
                    order_by.append({
                        "table": col["table"],
                        "column": col["column"],
                        "direction": direction
                    })
                    break

        # Build patch operation
        patch_op = {
            "operation": "modify_order_by",
            "order_by": order_by
        }

        if immediate_rerun:
            # Store patch in session state and trigger rerun immediately
            st.session_state.pending_patch = {
                "operation": patch_op,
                "executed_plan": executed_plan,
                "filtered_schema": filtered_schema,
                "thread_id": thread_id,
                "user_question": output.get("user_question", ""),
            }
            # Increment generation to get fresh controls after applying patch
            st.session_state.controls_generation = st.session_state.get("controls_generation", 0) + 1
            st.rerun()
        else:
            # Store for batch processing
            if not hasattr(st.session_state, 'pending_batch_patches'):
                st.session_state.pending_batch_patches = []

            st.session_state.pending_batch_patches.append({
                "operation": patch_op,
                "executed_plan": executed_plan,
                "filtered_schema": filtered_schema,
                "thread_id": thread_id,
                "user_question": output.get("user_question", ""),
            })

    except Exception as e:
        st.error(f"Error applying sort patch: {str(e)}")
        logger.error(f"Error in apply_sort_patch: {str(e)}", exc_info=True)


def apply_limit_patch(output: dict, new_limit: int, immediate_rerun: bool = True):
    """
    Apply a LIMIT patch and optionally re-execute the query.

    Args:
        output: Current state dict
        new_limit: New row limit value
        immediate_rerun: If True, trigger rerun immediately. If False, store for batch processing.
    """
    try:
        executed_plan = output.get("executed_plan")
        filtered_schema = output.get("filtered_schema")
        thread_id = output.get("thread_id")

        if not executed_plan or not filtered_schema:
            st.error("Cannot apply patch: missing executed plan or schema")
            return

        # Build patch operation
        patch_op = {
            "operation": "modify_limit",
            "limit": new_limit
        }

        if immediate_rerun:
            # Store patch in session state and trigger rerun immediately
            st.session_state.pending_patch = {
                "operation": patch_op,
                "executed_plan": executed_plan,
                "filtered_schema": filtered_schema,
                "thread_id": thread_id,
                "user_question": output.get("user_question", ""),
            }
            # Increment generation to get fresh controls after applying patch
            st.session_state.controls_generation = st.session_state.get("controls_generation", 0) + 1
            st.rerun()
        else:
            # Store for batch processing
            if not hasattr(st.session_state, 'pending_batch_patches'):
                st.session_state.pending_batch_patches = []

            st.session_state.pending_batch_patches.append({
                "operation": patch_op,
                "executed_plan": executed_plan,
                "filtered_schema": filtered_schema,
                "thread_id": thread_id,
                "user_question": output.get("user_question", ""),
            })

    except Exception as e:
        st.error(f"Error applying limit patch: {str(e)}")
        logger.error(f"Error in apply_limit_patch: {str(e)}", exc_info=True)


def render_modification_controls(output: dict, modification_options: dict, placeholder=None):
    """
    Render interactive controls for modifying the query plan.

    Args:
        output: The state dict containing executed_plan, filtered_schema, etc.
        modification_options: Dict with available modification options
        placeholder: Optional st.empty() placeholder for clearing controls before rerun
    """
    with st.expander("🔧 Modify Query", icon="✏️", expanded=False):
        st.write("Make multiple modifications and click **'Apply Changes'** to re-execute the query.")

        # Create tabs for different modification types
        col_tab, sort_tab = st.tabs(["📊 Columns", "🔀 Sort & Limit"])

        # Track changes to be applied
        column_changes = []
        sort_change = None
        limit_change = None

        # Generate stable key prefix that only changes when patches are applied
        # This ensures checkboxes keep their state during normal interaction
        if "controls_generation" not in st.session_state:
            st.session_state.controls_generation = 0

        thread_id = output.get("thread_id", "default")
        generation = st.session_state.controls_generation
        key_prefix = f"{thread_id}_{generation}"

        with col_tab:
            st.write("**Select columns to display:**")

            tables = modification_options.get("tables", {})

            for table_name, table_info in tables.items():
                alias = table_info.get("alias")
                table_display = f"{table_name} ({alias})" if alias else table_name

                st.write(f"**{table_display}**")

                columns = table_info.get("columns", [])

                # Group columns into rows of 3
                col_groups = [columns[i:i+3] for i in range(0, len(columns), 3)]

                for col_group in col_groups:
                    cols = st.columns(3)

                    for idx, col_info in enumerate(col_group):
                        with cols[idx]:
                            col_name = col_info["name"]
                            is_selected = col_info["selected"]
                            role = col_info.get("role")
                            is_pk = col_info.get("is_primary_key", False)

                            # Build label
                            label = col_name
                            if is_pk:
                                label += " 🔑"
                            if role == "filter":
                                label += " (filter only)"

                            # Create checkbox with unique key including prefix
                            checkbox_key = f"col_{key_prefix}_{table_name}_{col_name}"

                            # Only show checkbox if it's a projection or not selected
                            # (don't show filter-only columns as checkboxes)
                            if role != "filter" or not is_selected:
                                checked = st.checkbox(
                                    label,
                                    value=is_selected and role == "projection",
                                    key=checkbox_key,
                                    help=f"Type: {col_info['type']}",
                                )

                                # Track changes (but don't apply yet)
                                if checked != (is_selected and role == "projection"):
                                    column_changes.append({
                                        "operation": "add_column" if checked else "remove_column",
                                        "table": table_name,
                                        "column": col_name
                                    })
                            else:
                                # Show as disabled for filter-only columns
                                st.checkbox(
                                    label,
                                    value=False,
                                    key=checkbox_key,
                                    disabled=True,
                                    help="This column is used in filters only"
                                )

                st.divider()

        with sort_tab:
            st.write("**Order results by:**")

            # Get sortable columns
            sortable_columns = modification_options.get("sortable_columns", [])
            current_order_by = modification_options.get("current_order_by", [])
            current_limit = modification_options.get("current_limit")

            # Build options for selectbox
            sort_options = ["No sorting"] + [col["display_name"] for col in sortable_columns]

            # Determine current selection
            current_sort_col = None
            current_sort_dir = "ASC"
            if current_order_by and len(current_order_by) > 0:
                first_order = current_order_by[0]
                current_sort_col = f"{first_order['table']}.{first_order['column']}"
                current_sort_dir = first_order.get("direction", "ASC")

            default_index = 0
            if current_sort_col:
                try:
                    default_index = sort_options.index(current_sort_col)
                except ValueError:
                    default_index = 0

            sort_col1, sort_col2 = st.columns([3, 1])

            with sort_col1:
                selected_sort = st.selectbox(
                    "Column",
                    sort_options,
                    index=default_index,
                    key=f"sort_column_select_{key_prefix}"
                )

            with sort_col2:
                direction = st.radio(
                    "Direction",
                    ["ASC", "DESC"],
                    index=0 if current_sort_dir == "ASC" else 1,
                    key=f"sort_direction_radio_{key_prefix}",
                    horizontal=True
                )

            # Track sort changes
            new_sort_col = selected_sort if selected_sort != "No sorting" else None
            old_sort_col = current_sort_col if current_order_by else None

            if new_sort_col != old_sort_col or (new_sort_col and direction != current_sort_dir):
                sort_change = {
                    "selected_sort": selected_sort,
                    "direction": direction,
                    "sortable_columns": sortable_columns
                }

            st.divider()

            st.write("**Limit number of rows:**")

            # Limit slider
            limit_value = current_limit if current_limit else 100

            new_limit = st.slider(
                "Row limit",
                min_value=10,
                max_value=2000,
                value=min(max(limit_value, 10), 2000),
                step=10,
                key=f"limit_slider_{key_prefix}"
            )

            # Track limit changes
            if new_limit != current_limit:
                limit_change = new_limit

        # Single Apply Changes button at the bottom
        st.divider()

        # Show what will be applied
        changes_pending = bool(column_changes or sort_change or limit_change)
        if changes_pending:
            change_summary = []
            if column_changes:
                adds = sum(1 for c in column_changes if c["operation"] == "add_column")
                removes = sum(1 for c in column_changes if c["operation"] == "remove_column")
                if adds:
                    change_summary.append(f"➕ {adds} column(s)")
                if removes:
                    change_summary.append(f"➖ {removes} column(s)")
            if sort_change:
                change_summary.append("🔀 Sorting")
            if limit_change:
                change_summary.append(f"📊 Limit: {limit_change}")

            st.info(f"**Pending changes:** {', '.join(change_summary)}")

        apply_col1, apply_col2 = st.columns([1, 3])
        with apply_col1:
            if st.button(
                "Apply Changes" if changes_pending else "No changes to apply",
                key=f"apply_all_changes_btn_{key_prefix}",
                type="primary",
                disabled=not changes_pending,
                use_container_width=True
            ):
                # Apply all changes in sequence
                try:
                    # Clear any existing batch patches
                    st.session_state.pending_batch_patches = []

                    # Add column changes to batch
                    for change in column_changes:
                        apply_column_patch(
                            output,
                            change["table"],
                            change["column"],
                            change["operation"],
                            immediate_rerun=False
                        )

                    # Add sort change to batch
                    if sort_change:
                        apply_sort_patch(
                            output,
                            sort_change["selected_sort"],
                            sort_change["direction"],
                            sort_change["sortable_columns"],
                            immediate_rerun=False
                        )

                    # Add limit change to batch
                    if limit_change:
                        apply_limit_patch(output, limit_change, immediate_rerun=False)

                    # Set flag to trigger batch processing and rerun
                    if st.session_state.pending_batch_patches:
                        st.session_state.apply_batch_patches = True
                        # Increment generation to get fresh controls after applying patches
                        st.session_state.controls_generation = st.session_state.get("controls_generation", 0) + 1
                        # Clear the controls using the placeholder before rerunning
                        if placeholder:
                            placeholder.empty()
                        st.rerun()

                except Exception as e:
                    st.error(f"Error applying changes: {str(e)}")


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

    # Display modification controls if options are available
    # Skip rendering during batch processing to avoid conflicts
    is_batch_processing = st.session_state.get("apply_batch_patches", False)
    modification_options = output.get("modification_options")
    if modification_options and output.get("executed_plan") and not is_batch_processing:
        # Create a placeholder for the controls so they can be cleared before rerun
        controls_placeholder = st.empty()
        with controls_placeholder.container():
            render_modification_controls(output, modification_options, controls_placeholder)

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

    if "pending_patch" not in st.session_state:
        st.session_state.pending_patch = None


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

    # Check if there's a pending patch operation to execute
    # Handle batch patch operations
    if hasattr(st.session_state, 'apply_batch_patches') and st.session_state.apply_batch_patches:
        st.session_state.apply_batch_patches = False  # Clear the flag
        patches = st.session_state.get('pending_batch_patches', [])

        if patches:
            status = st.status(f"Applying {len(patches)} modification(s)...")
            try:
                # Apply patches sequentially
                current_output = None
                for i, patch_info in enumerate(patches, 1):
                    status.update(label=f"Applying modification {i} of {len(patches)}...")

                    # For all patches except the first, use the output from the previous patch
                    if current_output:
                        # Update patch_info with latest executed_plan and filtered_schema
                        patch_info["executed_plan"] = current_output.get("executed_plan")
                        patch_info["filtered_schema"] = current_output.get("filtered_schema")

                    # Apply the patch
                    response = query_database(
                        patch_info["user_question"],
                        patch_operation=patch_info["operation"],
                        executed_plan=patch_info["executed_plan"],
                        filtered_schema=patch_info["filtered_schema"],
                        thread_id=patch_info.get("thread_id"),
                    )

                    # Update current_output for next iteration
                    current_output = response["state"]

                # Use the final output
                output = current_output

                # Reload thread states to show the updated query in the sidebar
                reload_thread_states()

                # Update session state
                st.session_state.show_results = True

                # Update status
                if output.get("result") is None:
                    status.update(label="No results found", state="error")
                else:
                    status.update(label=f"All {len(patches)} modifications applied successfully!", state="complete")

                # Render the results and store dataframe
                df = render_query_results(output, status_label=f"{len(patches)} modifications applied!")
                st.session_state.current_dataframe = df

                # Clear the batch patches
                st.session_state.pending_batch_patches = []

            except Exception as e:
                status.update(label=f"Error: {str(e)}", state="error")
                st.error(f"An error occurred applying modifications: {str(e)}")
                st.exception(e)
                # Clear the batch patches even on error
                st.session_state.pending_batch_patches = []

    # Handle single patch operation (for backward compatibility)
    elif hasattr(st.session_state, 'pending_patch') and st.session_state.pending_patch:
        patch_info = st.session_state.pending_patch
        st.session_state.pending_patch = None  # Clear the pending patch

        status = st.status("Applying modification...")
        try:
            # Apply the patch by calling query_database with patch parameters
            response = query_database(
                patch_info["user_question"],
                patch_operation=patch_info["operation"],
                executed_plan=patch_info["executed_plan"],
                filtered_schema=patch_info["filtered_schema"],
                thread_id=patch_info.get("thread_id"),
            )

            # Extract state from response
            output = response["state"]

            # Reload thread states to show the updated query in the sidebar
            reload_thread_states()

            # Update session state
            st.session_state.show_results = True

            # Update status
            if output.get("result") is None:
                status.update(label="No results found", state="error")
            else:
                status.update(label="Modification applied successfully!", state="complete")

            # Render the results and store dataframe
            df = render_query_results(output, status_label="Modification applied!")
            st.session_state.current_dataframe = df

        except Exception as e:
            status.update(label=f"Error: {str(e)}", state="error")
            st.error(f"An error occurred applying modification: {str(e)}")
            st.exception(e)

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
