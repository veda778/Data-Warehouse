import os
from dotenv import load_dotenv

load_dotenv()

db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")

try:
    from sqlalchemy import create_engine, text
except ModuleNotFoundError:
    raise SystemExit(
        "sqlalchemy is not installed. Install it with: pip install sqlalchemy mysql-connector-python"
    )


engine = create_engine(f"mysql+mysqlconnector://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")


try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM gold.dim_customers"))
        print("Connection successful. Row count:", result.scalar())
except Exception as e:
    print("Connection failed:", e)