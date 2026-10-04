# Data-warehouse-Project
# Retail Sales Data Warehouse & Analytics Platform

![MySQL](https://img.shields.io/badge/MySQL-00758F?style=flat&logo=mysql&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=flat&logo=scikit-learn&logoColor=white)
![Power BI](https://img.shields.io/badge/Power%20BI-F2C811?style=flat&logo=powerbi&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-green)

An end-to-end data platform that takes raw CRM and ERP exports through a medallion-architecture warehouse in MySQL, automates the pipeline with Python, layers a Random Forest churn model on top of the customer data, and surfaces everything in a four-page Power BI report with row-level security.

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Key Components](#key-components)
- [Tech Stack](#tech-stack)
- [Data Sources](#data-sources)
- [Repository Structure](#repository-structure)
- [How to Run](#how-to-run)
- [Results](#results)

## Overview

Raw sales, customer, and product data arrives from two disconnected source systems — a CRM and an ERP — in inconsistent formats (mismatched date formats, duplicate customer records, inconsistent product categories). This project builds a warehouse that cleans, conforms, and models that data into a single star schema, then extends it two ways: an ML layer that flags customers likely to churn, and a BI layer that makes the whole thing usable by a non-technical business audience.

## Architecture

The warehouse follows the **medallion architecture** pattern — Bronze, Silver, Gold — with each layer implemented as its own MySQL database.

```mermaid
flowchart LR
    subgraph Sources["Source Systems"]
        A1["CRM: cust_info, prd_info, sales_details"]
        A2["ERP: CUST_AZ12, LOC_A101, PX_CAT_G1V2"]
    end

    subgraph Bronze["Bronze — raw ingestion"]
        B["Raw tables, loaded as-is"]
    end

    subgraph Silver["Silver — cleaned & conformed"]
        S["Deduplicated, standardized, business rules applied"]
    end

    subgraph Gold["Gold — star schema (views)"]
        G1["dim_customers"]
        G2["dim_products"]
        G3["fact_sales"]
    end

    P["Python ETL Automation Layer"]
    M["Random Forest Churn Model\nROC-AUC ~0.974"]
    R["Power BI Report\n4 pages · DAX · Row-Level Security"]

    A1 --> B
    A2 --> B
    B --> S
    S --> G1
    S --> G2
    S --> G3
    P -.orchestrates.-> B
    P -.orchestrates.-> S
    P -.orchestrates.-> G1
    G1 --> M
    G3 --> M
    G1 --> R
    G2 --> R
    G3 --> R
    M --> R
```

- **Bronze:** raw CRM/ERP data loaded with no transformation, preserving source fidelity.
- **Silver:** deduplication via `ROW_NUMBER()`, date normalization with `STR_TO_DATE()`, standardized keys and categories, all handled through stored procedures.
- **Gold:** business-ready views (`dim_customers`, `dim_products`, `fact_sales`, plus reporting views `report_customers` / `report_products`) built on a star schema, with surrogate keys generated via `ROW_NUMBER()`.

## Key Components

**1. SQL Data Warehouse (MySQL)**
Bronze/Silver/Gold layers as separate databases, star schema in Gold, ETL between layers handled by stored procedures.

**2. Python ETL Automation**
`run_pipeline.py` orchestrates the Bronze → Silver → Gold pipeline end-to-end using **SQLAlchemy** and **mysql-connector-python**, invoking the MySQL stored procedures via `callproc()`. Credentials are loaded securely from environment variables (`.env`, not committed) rather than hardcoded.

**3. Churn Prediction Model**
A **Random Forest classifier** (`churn_model.py`) trained on customer data from the Gold layer. A customer is labeled **churned if they have made no purchase in the last 90 days**. The model uses **RFM (Recency, Frequency, Monetary) features** and achieves **~0.974 ROC-AUC**. Predictions are written back to `gold.customer_churn_scores` for use in the Power BI report.

**4. Power BI Report**
A four-page report built on the Gold-layer views, with 13 custom DAX measures, row-level security, a custom navy/teal theme, and a dedicated DateTable for time intelligence:
- **Executive Summary**
- **Customer & Churn Risk**
- **Product Performance**
- **RFM Segmentation**
## Tech Stack
- **Database:** MySQL, MySQL Workbench
- **ETL:** SQL stored procedures, Python *(fill in specific libraries)*
- **Machine Learning:** Python, scikit-learn (Random Forest)
- **BI / Reporting:** Power BI, DAX, Row-Level Security

## Data Sources
| System | Files |
|---|---|
| CRM | `cust_info.csv`, `prd_info.csv`, `sales_details.csv` |
| ERP | `CUST_AZ12.csv`, `LOC_A101.csv`, `PX_CAT_G1V2.csv` |

## Repository Structure
```
Data-warehouse-Project/
├── datasets/       # Raw source CSVs (CRM + ERP)
├── docs/           # Architecture notes, data catalog, naming conventions
├── scripts/
│   ├── database creation/
│   ├── Bronze/     # Raw ingestion scripts
│   ├── silver/     # Cleaning & transformation procedures
│   └── Gold/       # Star schema view definitions
├── etl/            # Python ETL automation
├── ml/             # Churn prediction notebook + model
├── power-bi/       # .pbix file + report screenshots
├── tests/          # Data quality checks
└── README.md
```

## How to Run
1. Create the Bronze, Silver, and Gold databases in MySQL Workbench using the scripts in `scripts/database creation/`.
2. Run the Bronze ingestion scripts to load raw CSVs from `datasets/`.
3. Run the Silver transformation procedures to clean and conform the data.
4. Run the Gold layer scripts to build the star-schema views.
5. *(fill in: how to run the Python ETL script — command/entry point)*
6. Open `power-bi/*.pbix` in Power BI Desktop and refresh against the Gold layer to explore the report.

## Results
- Deduplicated and standardized data across two disconnected source systems into a single conformed star schema.
- Churn model reaches **~0.974 ROC-AUC** on held-out data.
- Power BI report delivers role-based, secured access to sales, customer, and product insights across 4 pages.

---
*Adapted and extended from a SQL Server-based warehouse course, rebuilt for MySQL with additional Python automation, ML, and BI layers.*
