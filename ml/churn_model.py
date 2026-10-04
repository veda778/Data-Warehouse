"""
Customer Churn Prediction Model
---------------------------------
Builds RFM (Recency, Frequency, Monetary) features from the gold layer,
derives a churn label, trains and compares two classifiers, and outputs
a scored table (customer_key, churn_probability, risk_segment) that can
be visualized in Power BI.

Usage:
    python churn_model.py
"""

import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    roc_auc_score,
    confusion_matrix,
)

load_dotenv()

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "3306")

CHURN_THRESHOLD_DAYS = 90   # no purchase within this many days of snapshot = churned
RANDOM_STATE = 42

OUTPUT_CSV = "churn_scores.csv"
WRITE_TO_DB = True                       # also write results back to a gold table
OUTPUT_TABLE = "gold.customer_churn_scores"


def get_engine():
    conn_str = (
        f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/"
    )
    return create_engine(conn_str)


def load_rfm_features(engine) -> pd.DataFrame:
    """Pull RFM + tenure features per customer from the gold layer.

    Snapshot date is the latest order_date in the dataset (not today's real
    date), since this is historical data ending in early 2014.
    """
    query = """
        SELECT
            f.customer_key,
            MAX(f.order_date)                                   AS last_order_date,
            MIN(f.order_date)                                   AS first_order_date,
            COUNT(DISTINCT f.order_number)                      AS frequency,
            SUM(f.sales_amount)                                 AS monetary,
            (SELECT MAX(order_date) FROM gold.fact_sales)        AS snapshot_date
        FROM gold.fact_sales f
        GROUP BY f.customer_key
    """
    df = pd.read_sql(query, engine)

    df["last_order_date"] = pd.to_datetime(df["last_order_date"])
    df["first_order_date"] = pd.to_datetime(df["first_order_date"])
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])

    df["recency_days"] = (df["snapshot_date"] - df["last_order_date"]).dt.days
    df["tenure_days"] = (df["snapshot_date"] - df["first_order_date"]).dt.days

    # A handful of rows in this dataset have NULL sales_amount (missing
    # price/quantity), which makes SUM() return NULL for those customers.
    # Treat missing monetary value as 0 rather than dropping the customer.
    df["monetary"] = df["monetary"].fillna(0)

    return df[["customer_key", "recency_days", "frequency", "monetary", "tenure_days"]]


def add_churn_label(df: pd.DataFrame) -> pd.DataFrame:
    df["churned"] = (df["recency_days"] > CHURN_THRESHOLD_DAYS).astype(int)
    return df


def train_and_compare_models(df: pd.DataFrame):
    features = ["frequency", "monetary", "tenure_days"]
    # Note: recency_days is deliberately excluded from features since it was
    # used to construct the label itself - including it would leak the answer.
    X = df[features]
    y = df["churned"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=RANDOM_STATE, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    results = {}

    # --- Logistic Regression (baseline) ---
    log_reg = LogisticRegression(random_state=RANDOM_STATE, class_weight="balanced")
    log_reg.fit(X_train_scaled, y_train)
    log_reg_proba = log_reg.predict_proba(X_test_scaled)[:, 1]
    log_reg_pred = log_reg.predict(X_test_scaled)

    print("\n=== Logistic Regression ===")
    print(classification_report(y_test, log_reg_pred, digits=3))
    print("ROC-AUC:", round(roc_auc_score(y_test, log_reg_proba), 3))
    print("Confusion Matrix:\n", confusion_matrix(y_test, log_reg_pred))
    results["logistic_regression"] = roc_auc_score(y_test, log_reg_proba)

    # --- Random Forest ---
    rf = RandomForestClassifier(
        n_estimators=200, random_state=RANDOM_STATE, class_weight="balanced"
    )
    rf.fit(X_train, y_train)  # tree models don't need scaling
    rf_proba = rf.predict_proba(X_test)[:, 1]
    rf_pred = rf.predict(X_test)

    print("\n=== Random Forest ===")
    print(classification_report(y_test, rf_pred, digits=3))
    print("ROC-AUC:", round(roc_auc_score(y_test, rf_proba), 3))
    print("Confusion Matrix:\n", confusion_matrix(y_test, rf_pred))
    results["random_forest"] = roc_auc_score(y_test, rf_proba)

    print("\n=== Feature Importance (Random Forest) ===")
    for feat, imp in sorted(
        zip(features, rf.feature_importances_), key=lambda x: -x[1]
    ):
        print(f"  {feat}: {round(imp, 3)}")

    # Pick the better model by ROC-AUC to score the full customer base
    best_model_name = max(results, key=results.get)
    print(f"\nBest model: {best_model_name} (ROC-AUC {round(results[best_model_name], 3)})")

    best_model = rf if best_model_name == "random_forest" else log_reg
    use_scaled = best_model_name == "logistic_regression"

    return best_model, use_scaled, scaler, features


def score_all_customers(df, model, use_scaled, scaler, features):
    X_all = df[features]
    X_input = scaler.transform(X_all) if use_scaled else X_all

    df["churn_probability"] = model.predict_proba(X_input)[:, 1].round(4)

    def risk_segment(p):
        if p >= 0.7:
            return "High Risk"
        elif p >= 0.4:
            return "Medium Risk"
        else:
            return "Low Risk"

    df["risk_segment"] = df["churn_probability"].apply(risk_segment)
    return df[["customer_key", "recency_days", "frequency", "monetary",
               "tenure_days", "churned", "churn_probability", "risk_segment"]]


def main():
    print("Connecting to database...")
    engine = get_engine()

    print("Loading RFM features from gold layer...")
    df = load_rfm_features(engine)
    print(f"Loaded {len(df)} customers.")

    df = add_churn_label(df)
    churn_rate = df["churned"].mean()
    print(f"Churn rate at {CHURN_THRESHOLD_DAYS}-day threshold: {round(churn_rate * 100, 1)}%")

    n_before = len(df)
    df = df.dropna(subset=["recency_days", "frequency", "monetary", "tenure_days"])
    n_after = len(df)
    if n_before != n_after:
        print(f"Dropped {n_before - n_after} customer(s) with missing feature values.")

    print("\nTraining models...")
    best_model, use_scaled, scaler, features = train_and_compare_models(df)

    print("\nScoring full customer base...")
    scored_df = score_all_customers(df, best_model, use_scaled, scaler, features)

    scored_df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved scored results to {OUTPUT_CSV}")

    if WRITE_TO_DB:
        scored_df.to_sql(
            OUTPUT_TABLE.split(".")[-1],
            engine,
            schema=OUTPUT_TABLE.split(".")[0],
            if_exists="replace",
            index=False,
        )
        print(f"Wrote scored results to {OUTPUT_TABLE} (for Power BI to consume)")

    print("\nDone.")


if __name__ == "__main__":
    main()