"""Streamlit app for querying the database. The agent is intended to be used from an API"""

import os
import json
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from agent.query_database import query_database
from utils.logger import get_logger

load_dotenv()
logger = get_logger()

use_test_db = os.getenv("USE_TEST_DB").lower() == "true"


def load_sample_queries():
    """Load sample queries based on database type."""
    current_dir = os.path.dirname(os.path.abspath(__file__))

    filename = "test-db-queries.json" if use_test_db else "cwp_sample_queries.json"
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


def main():
    """Main function for the Streamlit app."""
    col1, col2 = st.columns([2, 2])

    with col1:
        category = st.selectbox(
            "Select a query category", ["Custom Query"] + list(SAMPLE_QUERIES.keys())
        )

    with col2:
        if category != "Custom Query":
            selected_query = st.selectbox(
                "Select a sample query", SAMPLE_QUERIES[category]
            )
        else:
            selected_query = ""

    # Use session state for question input to support suggestion selection
    if "question_input" not in st.session_state:
        st.session_state.question_input = selected_query
    else:
        # If we just selected a suggestion, use it
        if st.session_state.question_input != selected_query:
            selected_query = st.session_state.question_input
            # Reset after using
            st.session_state.question_input = selected_query

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

    col1, col2, col3 = st.columns(3)

    with col1:
        sort_order = st.selectbox(
            "Sort Order",
            ["Default", "Ascending", "Descending"],
            help="Choose the sort order for the results",
        )

    with col2:
        result_limit = st.selectbox(
            "Limit Results",
            [0, 1, 5, 25, 100, 1000],
            help="Limit the number of returned records (0 = no limit)",
            index=4,
        )

    with col3:
        time_filter = st.selectbox(
            "Time Filter",
            ["All Time", "Last 30 Days", "Last 60 Days", "Last 90 Days", "Last Year"],
            help="Filter results by time period",
            index=0,
        )

    if st.button("Generate Query", type="primary"):
        if user_question:
            status = st.status("Querying database...")
            try:
                output = query_database(
                    user_question,
                    sort_order=sort_order,
                    result_limit=result_limit,
                    time_filter=time_filter,
                )

                # Check if clarification is needed
                if output.get("needs_clarification"):
                    status.update(label="Clarification needed", state="error")
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
                                key=f"suggestion_{i}",
                                use_container_width=True,
                            ):
                                # Set the suggestion as the new question in session state
                                st.session_state.question_input = suggestion
                                st.rerun()

                        st.divider()
                        st.write("**Or modify your original question:**")
                        st.code(user_question, language="text")

                    # Show planner output for debugging
                    if output.get("planner_output"):
                        with st.expander("Planner Analysis", icon="🔍"):
                            planner_output = output["planner_output"]
                            st.write(
                                f"**Intent:** {planner_output.get('intent_summary', 'N/A')}"
                            )
                            ambiguities = planner_output.get("ambiguities", [])
                            if ambiguities:
                                st.write("**Ambiguities:**")
                                for amb in ambiguities:
                                    st.write(f"  - {amb}")
                            st.json(planner_output)

                    return

                if not output["query"]:
                    status.update(label=output["result"], state="error")
                    st.error("Query error.")
                    return

                # Display the executed SQL query
                with st.expander("Executed SQL Query", icon="📝", expanded=True):
                    st.code(output["query"], language="sql")

                # Display the query plan that generated this query
                if output.get("planner_output"):
                    with st.expander("Query Plan Used", icon="🗺️"):
                        st.write(
                            "This is the plan that was used to generate the executed query."
                        )
                        planner_output = output["planner_output"]

                        # Show key information at the top
                        if isinstance(planner_output, dict):
                            st.write(
                                f"**Intent:** {planner_output.get('intent_summary', 'N/A')}"
                            )
                            st.write(
                                f"**Decision:** {planner_output.get('decision', 'N/A')}"
                            )

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

                if output.get("corrected_queries") or output.get("refined_queries"):
                    with st.expander("Query History", icon="📜"):
                        col1, col2 = st.columns(2)

                        with col1:
                            if output["retry_count"] > 0:
                                st.subheader("Error Corrections")
                                st.write("Retry count:", output["retry_count"])
                                for i, query in enumerate(
                                    output["corrected_queries"], 1
                                ):
                                    st.write(f"**Attempt {i}:**")
                                    st.write(
                                        f"❌ Error: `{output['error_history'][i-1]}`"
                                    )

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
                            if output["refined_count"] > 0:
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

                tab1, tab2 = st.tabs(["Table View", "Raw Data"])

                if output["result"] is None:
                    status.update(label="No results found", state="error")
                    st.warning("Query returned no results.")
                    return

                df = format_results(output["result"])

                with tab1:
                    if not df.empty:
                        status.update(
                            label="Query executed successfully!", state="complete"
                        )

                        st.dataframe(
                            df,
                            hide_index=True,
                            column_config={
                                col: st.column_config.TextColumn(
                                    col, help="", width="auto"
                                )
                                for col in df.columns
                            },
                        )

                        csv = df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "Download CSV",
                            csv,
                            "query_results.csv",
                            "text/csv",
                            key="download-csv",
                        )
                    else:
                        status.update(label="No results found", state="error")
                        st.warning("Query returned no results.")

                with tab2:
                    st.text_area(
                        "Raw Results:",
                        value=output["result"],
                        height=200,
                        disabled=True,
                    )

            except Exception as e:
                status.update(label=f"Error: {str(e)}", state="error")
                st.error(f"An error occurred: {str(e)}")
                st.exception(e)
        else:
            st.warning("Please enter a question first.")


if __name__ == "__main__":
    main()
