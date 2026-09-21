import os
import psycopg2
import datetime
from pathlib import Path
from dotenv import load_dotenv
from cryptosight.utils.logger import get_logger

# Initialize logging for the database manager
logger = get_logger("DBManager")

# Load environment configuration variables from the root .env file
current_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=current_dir.parent / ".env")

def get_connection():
    """Reads database configurations from env and connects to PostgreSQL."""
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    # Confirm all necessary credentials are present
    if not all([db_host, db_name, db_user, db_password]):
        raise ValueError("Missing database configuration in .env")

    try:
        # Establish the connection
        connection = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password
        )
        # Force session to UTC timezone
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC';")
        connection.commit()

        logger.info(f"Connected to database '{db_name}' (timezone forced to UTC).")
        return connection
    except Exception as error:
        logger.error(f"Failed to connect to the database: {error}")
        raise error

def create_schema_and_table(conn, exchange: str, symbol: str, timeframe: str):
    """Dynamically creates the PostgreSQL schema and table for a specific market."""
    schema_name = f"{exchange.lower()}_data"
    clean_symbol = symbol.lower().replace("/", "_")
    table_name = f"{exchange.lower()}_{clean_symbol}_{timeframe.lower()}"

    # SQL definition for schema and table using TIMESTAMP (without timezone) for clean UTC values
    create_schema_sql = f"CREATE SCHEMA IF NOT EXISTS {schema_name};"
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {schema_name}.{table_name} (
        timestamp TIMESTAMP PRIMARY KEY,
        open      NUMERIC NOT NULL,
        high      NUMERIC NOT NULL,
        low       NUMERIC NOT NULL,
        close     NUMERIC NOT NULL,
        volume    NUMERIC NOT NULL,
        volume_pct NUMERIC
    );
    """
    try:
        with conn.cursor() as cursor:
            # Check if the table already exists to log the correct status
            cursor.execute(
                "SELECT 1 FROM pg_tables WHERE schemaname = %s AND tablename = %s", 
                (schema_name, table_name)
            )
            table_exists = cursor.fetchone() is not None

            # Execute creation scripts
            cursor.execute(create_schema_sql)
            cursor.execute(create_table_sql)
            conn.commit()

            if table_exists:
                logger.info(f"Table '{schema_name}.{table_name}' verified.")
            else:
                logger.info(f"Table '{schema_name}.{table_name}' created.")
    except Exception as error:
        conn.rollback()
        logger.error(f"Error creating schema/table '{schema_name}.{table_name}': {error}")
        raise error

def insert_ohlcv(conn, exchange: str, symbol: str, timeframe: str, ohlcv_data: list):
    """Inserts or updates OHLCV data records into the database."""
    if not ohlcv_data:
        return

    schema_name = f"{exchange.lower()}_data"
    clean_symbol = symbol.lower().replace("/", "_")
    table_name = f"{exchange.lower()}_{clean_symbol}_{timeframe.lower()}"

    # Upsert query using ON CONFLICT (timestamp) to prevent duplicate key errors
    upsert_sql = f"""
    INSERT INTO {schema_name}.{table_name} (timestamp, open, high, low, close, volume, volume_pct)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (timestamp) 
    DO UPDATE SET 
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        volume_pct = EXCLUDED.volume_pct;
    """
    try:
        with conn.cursor() as cursor:
            # Execute batch insert
            cursor.executemany(upsert_sql, ohlcv_data)
            conn.commit()
            logger.info(f"Saved {len(ohlcv_data)} records to '{schema_name}.{table_name}'.")
    except Exception as error:
        conn.rollback()
        logger.error(f"Error inserting data into '{schema_name}.{table_name}': {error}")
        raise error

def get_latest_timestamp(conn, exchange: str, symbol: str, timeframe: str):
    """Gets the latest timestamp available for the given market table."""
    schema_name = f"{exchange.lower()}_data"
    clean_symbol = symbol.lower().replace("/", "_")
    table_name = f"{exchange.lower()}_{clean_symbol}_{timeframe.lower()}"

    # Verify if the table exists before querying it
    table_exists_query = "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = %s AND tablename = %s);"
    try:
        with conn.cursor() as cursor:
            cursor.execute(table_exists_query, (schema_name, table_name))
            if not cursor.fetchone()[0]:
                return None

            # Get the maximum stored timestamp
            cursor.execute(f"SELECT MAX(timestamp) FROM {schema_name}.{table_name};")
            result = cursor.fetchone()
            return result[0] if result else None
    except Exception as error:
        logger.error(f"Error getting latest timestamp from '{schema_name}.{table_name}': {error}")
        return None


