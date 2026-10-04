"""
Medallion Architecture ETL Automation
---------------------------------------
Automates the bronze -> silver -> gold pipeline for the SQL Data Warehouse project.

What it does:
1. Calls load_bronze() stored procedure
2. Calls load_silver() stored procedure
3. Validates gold layer views are returning data (dim_customers, dim_products, fact_sales)
4. Logs every step (timing, row counts, errors) to console AND a timestamped log file

Usage:
    python run_pipeline.py
"""

import logging
import sys
import time
from datetime import datetime
import mysql.connector
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

import os
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# CONFIG - update these to match your environment
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    # No single "database" here - bronze, silver, and gold are separate DBs,
    # so every call/query below is fully qualified with its DB name instead.
}

BRONZE_PROC = "bronze.load_bronze"
SILVER_PROC = "silver.load_silver"
GOLD_VIEWS = ["gold.dim_customers", "gold.dim_products", "gold.fact_sales"]

LOG_FILE = f"pipeline_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# ---------------------------------------------------------------------------
# LOGGING SETUP
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def get_engine():
    """Create and return a SQLAlchemy engine for the target MySQL database."""
    conn_str = (
        f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/"
    )
    return create_engine(conn_str)


def run_procedure(engine, proc_name: str):
    """Call a stored procedure and log timing + success/failure.

    Uses a fresh, standalone mysql.connector connection (NOT SQLAlchemy's
    pooled raw_connection()) because CALL statements to procedures with
    multiple internal SELECT/status statements can leave a pooled
    connection in a dirty state after a failure, causing every subsequent
    attempt to fail with 'Unread result found' even on a clean retry.
    """
    logger.info(f"Starting stored procedure: {proc_name}()")
    start = time.time()
    conn = mysql.connector.connect(
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
    )
    try:
        cursor = conn.cursor(buffered=True)
        cursor.callproc(proc_name)
        for result in cursor.stored_results():
            result.fetchall()
        conn.commit()
        cursor.close()
        elapsed = round(time.time() - start, 2)
        logger.info(f"Finished {proc_name}() successfully in {elapsed}s")
        return True
    except Exception as e:
        conn.rollback()
        elapsed = round(time.time() - start, 2)
        logger.error(f"FAILED {proc_name}() after {elapsed}s | Error: {e}")
        return False
    finally:
        conn.close()


def validate_gold_layer(engine):
    """Query each gold view and log row counts to confirm the chain worked."""
    logger.info("Validating gold layer views...")
    all_ok = True
    for view in GOLD_VIEWS:
        try:
            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {view}"))
                count = result.scalar()
                if count and count > 0:
                    logger.info(f"  {view}: {count} rows OK")
                else:
                    logger.warning(f"  {view}: returned 0 rows - check silver layer data")
                    all_ok = False
        except SQLAlchemyError as e:
            logger.error(f"  {view}: FAILED to query | Error: {e}")
            all_ok = False
    return all_ok


def main():
    pipeline_start = time.time()
    logger.info("=" * 60)
    logger.info("PIPELINE RUN STARTED")
    logger.info("=" * 60)

    engine = get_engine()

    # Sanity check connection before doing anything else
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified.")
    except SQLAlchemyError as e:
        logger.critical(f"Could not connect to database. Aborting. Error: {e}")
        sys.exit(1)

    # Step 1: Bronze
    if not run_procedure(engine, BRONZE_PROC):
        logger.critical("Bronze layer failed. Aborting pipeline - silver/gold not run.")
        sys.exit(1)

    # Step 2: Silver
    if not run_procedure(engine, SILVER_PROC):
        logger.critical("Silver layer failed. Aborting pipeline - gold not validated.")
        sys.exit(1)

    # Step 3: Gold validation
    gold_ok = validate_gold_layer(engine)

    total_elapsed = round(time.time() - pipeline_start, 2)
    logger.info("=" * 60)
    if gold_ok:
        logger.info(f"PIPELINE RUN COMPLETED SUCCESSFULLY in {total_elapsed}s")
    else:
        logger.warning(f"PIPELINE RUN COMPLETED WITH WARNINGS in {total_elapsed}s")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()