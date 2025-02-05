import streamlit as st
import pandas as pd
from langchain_community.utilities import SQLDatabase
from agent.query_database import query_database
import json
import os
from dotenv import load_dotenv
from database.connection import get_db_connection

load_dotenv()

st.set_page_config(
    page_title="SQL Query Assistant",
    layout="wide",
    initial_sidebar_state="auto"
)

st.title("SQL Query Assistant")

SAMPLE_QUERIES = {
    "User and Activity Queries": [
        "Show me all users in the system.",
        "List the last 10 user login attempts.",
        "How many users are in the system?",
        "Who are the top 5 users with the most logins?"
    ],
    "Company and Asset Queries": [
        "List all companies and their associated assets.",
        "Show all computers along with their processor details.",
        "List all installed applications on each computer."
    ],
    "Vulnerability and Patch Queries": [
        "List all vulnerabilities found in the last 30 days.",
        "Show all computers with pending patches.",
        "Which computers have the most critical CVEs?"
    ],
    "Hardware and Peripheral Queries": [
        "Show all disk drives installed on computers.",
        "List all USB devices connected to computers.",
        "How many computers have printers attached?"
    ],
    "Tagging and Application Tracking": [
        "List all applications tagged with security risk.",
        "Which companies have applications with critical vulnerabilities?"
    ],
    "Network and Configuration Queries": [
        "Show all network domains in the database.",
        "List computers and their associated network domains.",
        "How many computers are there per network domain?"
    ],
    "System and Scan Queries": [
        "When was the last scan performed for each asset?",
        "List all scheduled scans in the system.",
        "Which scans detected the most vulnerabilities?"
    ]
}

def format_results(result):
    """Convert query results into a pandas DataFrame."""
    try:
        if not result or not result[0] or not result[0][0]:
            return pd.DataFrame()
            
        data = json.loads(result[0][0])
        
        if not data:
            return pd.DataFrame()
            
        return pd.DataFrame(data)
    except (json.JSONDecodeError, IndexError, TypeError) as e:
        print(f"Error formatting results: {str(e)}")
        return pd.DataFrame()

def main():
    col1, col2 = st.columns([2, 2])
    
    with col1:
        category = st.selectbox(
            "Select a query category",
            ["Custom Query"] + list(SAMPLE_QUERIES.keys())
        )
    
    with col2:
        if category != "Custom Query":
            selected_query = st.selectbox(
                "Select a sample query",
                SAMPLE_QUERIES[category]
            )
        else:
            selected_query = ""
    
    user_question = st.text_area(
        "What would you like to know about the database?",
        value=selected_query,
        height=100,
        placeholder="e.g., What are the top 5 CVEs with the highest CVSS scores?"
    )
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        sort_order = st.selectbox(
            "Sort Order",
            ["Default", "Ascending", "Descending"],
            help="Choose the sort order for the results"
        )
    
    with col2:
        result_limit = st.selectbox(
            "Limit Results",
            [0, 1, 5, 25, 100, 1000],
            help="Limit the number of returned records (0 = no limit)",
            index=4
        )
    
    with col3:
        time_filter = st.selectbox(
            "Time Filter",
            ["All Time", "Last 30 Days", "Last 60 Days", "Last 90 Days", "Last Year"],
            help="Filter results by time period",
            index=1
        )
    
    if st.button("Generate Query", type="primary"):
        if user_question:
            status = st.status("Analyzing database schema...")
            try:
                output = query_database(
                    user_question, 
                    sort_order=sort_order,
                    result_limit=result_limit,
                    time_filter=time_filter
                )
                
                if not output["query"]:
                    status.update(label=output["result"], state="error")
                    st.error("Query error.")
                    return

                st.code(output["query"], language="sql")
                
                if "corrected_query" in output and output["corrected_query"]:
                    with st.expander("Query Correction Details", icon="🚨"):
                        st.write("Retry count:", output["retry_count"])
                        st.write("Error history:", output["error_history"])
                        st.write("Original query that generated an error:")
                        st.code(output["corrected_query"], language="sql")
                        st.write("Corrected and executed query:")
                        st.code(output["query"], language="sql")

                tab1, tab2 = st.tabs(["Table View", "Raw Data"])
                

                if type(output["result"]) == str:
                    status.update(label="No results found", state="error")
                    st.warning("Query returned no results.")
                    return 

                with tab1:
                    df = format_results(output["result"])

                    if not df.empty:
                        status.update(label="Query executed successfully!", state="complete")
                        
                        st.dataframe(
                            df,
                            use_container_width=True,
                            hide_index=True,
                            column_config={col: st.column_config.TextColumn(col, help="", width="auto") for col in df.columns}
                        )
                        
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            "Download CSV",
                            csv,
                            "query_results.csv",
                            "text/csv",
                            key='download-csv'
                        )
                    else:
                        status.update(label="No results found", state="error")
                        st.warning("Query returned no results.")
                
                with tab2:
                    st.text_area(
                        "Raw Results:",
                        value=output["result"][0],
                        height=200,
                        disabled=True
                    )
                    
            except Exception as e:
                status.update(label=f"Error: {str(e)}", state="error")
                st.error(f"An error occurred: {str(e)}")
                st.exception(e)
        else:
            st.warning("Please enter a question first.")

if __name__ == "__main__":
    main()