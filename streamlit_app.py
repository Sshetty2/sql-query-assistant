"""Streamlit app for querying the database. The agent is intended to be used from an API"""

import os
import json
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from agent.query_database import query_database

load_dotenv()

use_test_db = os.getenv("USE_TEST_DB").lower() == "true"


def load_sample_queries():
    """Load sample queries based on database type."""
    current_dir = os.path.dirname(os.path.abspath(__file__))

    filename = "test-db-queries.json" if use_test_db else "cwp-sample-queries.json"
    file_path = os.path.join(current_dir, filename)

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading sample queries: {e}")
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
        print(f"Error formatting results: {str(e)}")
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
            index=1,
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

                if not output["query"]:
                    status.update(label=output["result"], state="error")
                    st.error("Query error.")
                    return

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
                                    st.write(f"Attempt {i}:")
                                    st.write(f"Error: {output['error_history'][i-1]}")
                                    st.code(query, language="sql")

                        with col2:
                            if output["refined_count"] > 0:
                                st.subheader("Query Refinements")
                                st.write("Refinement count:", output["refined_count"])
                                for i, query in enumerate(output["refined_queries"], 1):
                                    st.write(f"Refinement {i}:")
                                    st.write(
                                        f"Reasoning: {output['refined_reasoning'][i-1]}"
                                    )
                                    st.code(query, language="sql")

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
                            use_container_width=True,
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
