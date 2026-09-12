import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("POSTGRESQL_HOST")
PORT = os.getenv("POSTGRESQL_PORT")
DATABASE = os.getenv("DATABASE")
USER = os.getenv("POSTGRESQL_USER")
PASSWORD = os.getenv("POSTGRESQL_PASSWORD")

def get_db_connection():
    """Create and return a PostgreSQL connection using environment settings."""
    return psycopg2.connect(
        host=HOST,
        port=PORT,
        database=DATABASE,
        user=USER,
        password=PASSWORD,
    )
