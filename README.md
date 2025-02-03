# 🛠️ SQL Query Assistant

A natural language to SQL query interface powered by **LangChain** and **OpenAI**, with an interactive **Streamlit frontend** for intuitive SQL generation.

---

## 🌟 Features

**Natural Language Querying**: Convert plain English into SQL queries  
**Interactive Query Builder**: Pre-built query templates for easy selection  
**Real-Time Execution**: Run queries instantly and view results  
**Custom Query Parameters**:
   - Sort order (ASC/DESC)
   - Result limits
   - Time-based filtering  
**Results Visualization**: View in **tables** and export to **CSV**  
**Smart Error Handling**: Detects and corrects SQL errors  

---


## 🔧 Prerequisites

- Python 3.13+
- SQL Server with ODBC Driver 17
- OpenAI API key

## 📦 Installation

1. Clone the repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up your environment variables:

```bash
OPENAI_API_KEY=your_api_key_here
DB_SERVER=your_server_name
DB_NAME=your_database_name
DB_USER=your_database_user
DB_PASSWORD=your_database_password
OPENAI_MODEL=gpt-4-turbo-preview
```

## 🚀 Usage

1. Start the application:

```bash
streamlit run app/streamlit_app.py
```

2. Select a query category or create a custom query
3. Customize query parameters (sort order, result limit, time filter)
4. Click "Generate Query" to execute

## 🏗️ Project Structure

```graph
app/
├── streamlit_app.py            # Main Streamlit application
├── agent/
│   ├── analyze_schema.py       # Schema retrieval & analysis
│   ├── handle_tool_error.py    # SQL error handling & correction
│   ├── create_agent.py         # LangChain agent setup
│   ├── execute_query.py        # Query execution logic
│   ├── generate_query.py       # SQL query generation from natural language
│   ├── query_database.py       # Manages full query pipeline
│   └── state.py                # Tracks state & workflow
```

## Running API Locally with Uvicorn

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

Test the API at:

```bash
http://localhost:8000/docs
```

## Running The Application in a Docker Container

1. Set up the environment variables in the .env file 

   Important: 
   -- (DB_SERVER should be "host.docker.internal")
   -- (DB_USER and DB_PASSWORD must be set to the credentials of an authorized database user)

```bash
OPENAI_API_KEY=your_api_key_here
DB_SERVER=host.docker.internal
DB_NAME=your_DB_NAME
DB_USER=your_DB_USER
DB_PASSWORD=your_DB_PASSWORD
```

2. Build and run the Docker container

```bash
docker build -t sql-query-assistant .
docker run -d --env-file .env -p 8000:8000 sql-query-assistant
```

## 🛠️ Technical Details

### Architecture
- Uses LangGraph for workflow management
- Implements a state machine pattern for query processing
- Leverages OpenAI's language models for query generation
- Uses Streamlit for the user interface
- Connects to SQL Server via ODBC

### Query Pipeline
1. Schema Analysis
2. Query Generation
3. Query Execution
4. Error Handling & Correction
5. Result Formatting