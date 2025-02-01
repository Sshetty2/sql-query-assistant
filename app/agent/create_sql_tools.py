from langchain_openai import ChatOpenAI
from langchain_community.agent_toolkits import SQLDatabaseToolkit
import os   
from dotenv import load_dotenv

load_dotenv()

def create_sql_tools(db):
    """Initialize SQL tools for interacting with the database."""
    toolkit = SQLDatabaseToolkit(db=db, llm=ChatOpenAI(model=os.getenv("OPENAI_MODEL")))
    return toolkit.get_tools()