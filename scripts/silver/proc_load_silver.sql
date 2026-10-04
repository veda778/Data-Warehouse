-- =============================================================
--   Silver Layer Stored Procedure — FIXED VERSION
--   Database : silver
--   Purpose  : Clean and transform data from bronze → silver
-- =============================================================

USE silver;

DELIMITER $$

DROP PROCEDURE IF EXISTS silver.load_silver$$

CREATE PROCEDURE silver.load_silver()
BEGIN
    DECLARE start_time  DATETIME;
    DECLARE end_time    DATETIME;
    DECLARE batch_start DATETIME;

    SET batch_start = NOW();

    SELECT '=====================================' AS '';
    SELECT 'Loading Silver Layer'                 AS '';
    SELECT '=====================================' AS '';

    -- ─────────────────────────────────────────
    --  CRM TABLES
    -- ─────────────────────────────────────────

    SELECT '-------------------------------------' AS '';
    SELECT 'Loading CRM Tables'                   AS '';
    SELECT '-------------------------------------' AS '';

    -- ① crm_cust_info
    --   FIX: deduplicate on cst_id — keep the row with the latest
    --        cst_create_date using ROW_NUMBER() in a subquery.
    --        (15 duplicate cst_id rows found in source data.)
    SET start_time = NOW();
    SELECT 'Truncating + Loading: silver.crm_cust_info' AS '';

    TRUNCATE TABLE silver.crm_cust_info;
    INSERT INTO silver.crm_cust_info (
        cst_id,
        cst_key,
        cst_firstname,
        cst_lastname,
        cst_marital_status,
        cst_gndr,
        cst_create_date
    )
    SELECT
        CAST(NULLIF(TRIM(cst_id), '') AS UNSIGNED),
        NULLIF(TRIM(cst_key), ''),
        NULLIF(TRIM(cst_firstname), ''),
        NULLIF(TRIM(cst_lastname), ''),
        CASE UPPER(TRIM(cst_marital_status))
            WHEN 'M' THEN 'Married'
            WHEN 'S' THEN 'Single'
            ELSE 'N/A'
        END,
        CASE UPPER(TRIM(cst_gndr))
            WHEN 'M' THEN 'Male'
            WHEN 'F' THEN 'Female'
            ELSE 'N/A'
        END,
        STR_TO_DATE(NULLIF(TRIM(cst_create_date), ''), '%d-%m-%Y')
    FROM (
        -- Keep only the most-recent record per cst_id
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY cst_id
                   ORDER BY STR_TO_DATE(NULLIF(TRIM(cst_create_date), ''), '%d-%m-%Y') DESC
               ) AS rn
        FROM bronze.crm_cust_info
        WHERE cst_id IS NOT NULL
          AND TRIM(cst_id) != ''
    ) ranked
    WHERE rn = 1;

    SET end_time = NOW();
    SELECT CONCAT('>> Done. Duration: ', TIMESTAMPDIFF(SECOND, start_time, end_time), 's') AS '';

    -- ② crm_prd_info
    --   No date format issues — prd_start_dt / prd_end_dt are all
    --   '%d-%m-%Y' and NULLs are handled by NULLIF. No changes needed.
    SET start_time = NOW();
    SELECT 'Truncating + Loading: silver.crm_prd_info' AS '';

    TRUNCATE TABLE silver.crm_prd_info;
    INSERT INTO silver.crm_prd_info (
        prd_id,
        cat_id,
        prd_key,
        prd_nm,
        prd_cost,
        prd_line,
        prd_start_dt,
        prd_end_dt
    )
    SELECT
        CAST(NULLIF(TRIM(prd_id), '') AS UNSIGNED),
        REPLACE(LEFT(TRIM(prd_key), 5), '-', '_'),
        SUBSTRING(TRIM(prd_key), 7),
        NULLIF(TRIM(prd_nm), ''),
        CASE
            WHEN NULLIF(TRIM(prd_cost), '') IS NULL THEN NULL
            WHEN CAST(NULLIF(TRIM(prd_cost), '') AS DECIMAL(10,2)) < 0 THEN NULL
            ELSE CAST(NULLIF(TRIM(prd_cost), '') AS DECIMAL(10,2))
        END,
        CASE UPPER(TRIM(prd_line))
            WHEN 'M' THEN 'Mountain'
            WHEN 'R' THEN 'Road'
            WHEN 'S' THEN 'Other Sales'
            WHEN 'T' THEN 'Touring'
            ELSE 'N/A'
        END,
        STR_TO_DATE(NULLIF(TRIM(prd_start_dt), ''), '%d-%m-%Y'),
        STR_TO_DATE(NULLIF(TRIM(prd_end_dt),   ''), '%d-%m-%Y')
    FROM bronze.crm_prd_info;

    SET end_time = NOW();
    SELECT CONCAT('>> Done. Duration: ', TIMESTAMPDIFF(SECOND, start_time, end_time), 's') AS '';

    -- ③ crm_sales_details
    --   FIX: sls_order_dt contains '0', '32154', '5489' (19 rows).
    --        STR_TO_DATE throws Error 1411 on non-8-digit values.
    --        Guard: only convert when CHAR_LENGTH of trimmed value = 8,
    --        otherwise treat as NULL.
    --        Same guard applied to sls_ship_dt and sls_due_dt
    --        defensively (they are clean today but same risk exists).
    SET start_time = NOW();
    SELECT 'Truncating + Loading: silver.crm_sales_details' AS '';

    TRUNCATE TABLE silver.crm_sales_details;
    INSERT INTO silver.crm_sales_details (
        sls_ord_num,
        sls_prd_key,
        sls_cust_id,
        sls_order_dt,
        sls_ship_dt,
        sls_due_dt,
        sls_sales,
        sls_quantity,
        sls_price
    )
    SELECT
        NULLIF(TRIM(sls_ord_num), ''),
        NULLIF(TRIM(sls_prd_key), ''),
        CAST(NULLIF(TRIM(sls_cust_id), '') AS UNSIGNED),

        -- FIX: guard date conversion with CHAR_LENGTH = 8 check
        CASE
            WHEN NULLIF(TRIM(sls_order_dt), '') IS NULL               THEN NULL
            WHEN CHAR_LENGTH(TRIM(sls_order_dt)) <> 8                 THEN NULL
            ELSE STR_TO_DATE(TRIM(sls_order_dt), '%Y%m%d')
        END,

        CASE
            WHEN NULLIF(TRIM(sls_ship_dt), '') IS NULL                THEN NULL
            WHEN CHAR_LENGTH(TRIM(sls_ship_dt)) <> 8                  THEN NULL
            ELSE STR_TO_DATE(TRIM(sls_ship_dt), '%Y%m%d')
        END,

        CASE
            WHEN NULLIF(TRIM(sls_due_dt), '') IS NULL                 THEN NULL
            WHEN CHAR_LENGTH(TRIM(sls_due_dt)) <> 8                   THEN NULL
            ELSE STR_TO_DATE(TRIM(sls_due_dt), '%Y%m%d')
        END,

        -- Fix sales: if missing or <= 0, derive from quantity * |price|
        CASE
            WHEN NULLIF(TRIM(sls_sales), '') IS NULL
              OR CAST(NULLIF(TRIM(sls_sales), '') AS DECIMAL(10,2)) <= 0
            THEN CAST(NULLIF(TRIM(sls_quantity), '') AS UNSIGNED)
               * ABS(CAST(NULLIF(TRIM(sls_price), '') AS DECIMAL(10,2)))
            ELSE CAST(NULLIF(TRIM(sls_sales), '') AS DECIMAL(10,2))
        END,

        CAST(NULLIF(TRIM(sls_quantity), '') AS UNSIGNED),

        -- Fix price: if negative, use absolute value
        CASE
            WHEN NULLIF(TRIM(sls_price), '') IS NULL THEN NULL
            WHEN CAST(NULLIF(TRIM(sls_price), '') AS DECIMAL(10,2)) < 0
            THEN ABS(CAST(NULLIF(TRIM(sls_price), '') AS DECIMAL(10,2)))
            ELSE CAST(NULLIF(TRIM(sls_price), '') AS DECIMAL(10,2))
        END

    FROM bronze.crm_sales_details;

    SET end_time = NOW();
    SELECT CONCAT('>> Done. Duration: ', TIMESTAMPDIFF(SECOND, start_time, end_time), 's') AS '';

    -- ─────────────────────────────────────────
    --  ERP TABLES
    -- ─────────────────────────────────────────

    SELECT '-------------------------------------' AS '';
    SELECT 'Loading ERP Tables'                   AS '';
    SELECT '-------------------------------------' AS '';

    -- ④ erp_cust_az12
    --   Source data is clean — all BDATE values are '%d-%m-%Y'.
    --   No changes needed from original; keeping as-is.
    SET start_time = NOW();
    SELECT 'Truncating + Loading: silver.erp_cust_az12' AS '';

    TRUNCATE TABLE silver.erp_cust_az12;
    INSERT INTO silver.erp_cust_az12 (
        cid,
        bdate,
        gen
    )
    SELECT
        CASE
            WHEN TRIM(cid) LIKE 'NAS%' THEN SUBSTRING(TRIM(cid), 4)
            ELSE NULLIF(TRIM(cid), '')
        END,
        CASE
            WHEN NULLIF(TRIM(bdate), '') IS NULL                    THEN NULL
            WHEN STR_TO_DATE(TRIM(bdate), '%d-%m-%Y') > NOW()      THEN NULL
            ELSE STR_TO_DATE(TRIM(bdate), '%d-%m-%Y')
        END,
        CASE UPPER(TRIM(gen))
            WHEN 'M'      THEN 'Male'
            WHEN 'F'      THEN 'Female'
            WHEN 'MALE'   THEN 'Male'
            WHEN 'FEMALE' THEN 'Female'
            ELSE 'N/A'
        END
    FROM bronze.erp_cust_az12;

    SET end_time = NOW();
    SELECT CONCAT('>> Done. Duration: ', TIMESTAMPDIFF(SECOND, start_time, end_time), 's') AS '';

    -- ⑤ erp_loc_a101
    --   Source has both ISO codes (DE, US, AU, GB, FR, CA) AND already-
    --   expanded names (Australia, United Kingdom, United States, etc.)
    --   plus whitespace-only values ('  ', ' ', '   ').
    --   NULLIF(TRIM(cntry),'') already handles whitespace-only → NULL.
    --   Already-expanded country names fall to the ELSE clause and pass
    --   through unchanged. No changes needed from original.
    SET start_time = NOW();
    SELECT 'Truncating + Loading: silver.erp_loc_a101' AS '';

    TRUNCATE TABLE silver.erp_loc_a101;
    INSERT INTO silver.erp_loc_a101 (
        cid,
        cntry
    )
    SELECT
        NULLIF(REPLACE(TRIM(cid), '-', ''), ''),
        CASE UPPER(TRIM(cntry))
            WHEN 'DE'  THEN 'Germany'
            WHEN 'US'  THEN 'United States'
            WHEN 'USA' THEN 'United States'
            WHEN 'AU'  THEN 'Australia'
            WHEN 'AUS' THEN 'Australia'
            WHEN 'GB'  THEN 'United Kingdom'
            WHEN 'UK'  THEN 'United Kingdom'
            WHEN 'FR'  THEN 'France'
            WHEN 'CA'  THEN 'Canada'
            ELSE NULLIF(TRIM(cntry), '')
        END
    FROM bronze.erp_loc_a101;

    SET end_time = NOW();
    SELECT CONCAT('>> Done. Duration: ', TIMESTAMPDIFF(SECOND, start_time, end_time), 's') AS '';

    -- ⑥ erp_px_cat_g1v2
    --   No issues in source data. No changes needed from original.
    SET start_time = NOW();
    SELECT 'Truncating + Loading: silver.erp_px_cat_g1v2' AS '';

    TRUNCATE TABLE silver.erp_px_cat_g1v2;
    INSERT INTO silver.erp_px_cat_g1v2 (
        id,
        cat,
        subcat,
        maintenance
    )
    SELECT
        NULLIF(TRIM(id),          ''),
        NULLIF(TRIM(cat),         ''),
        NULLIF(TRIM(subcat),      ''),
        NULLIF(TRIM(maintenance), '')
    FROM bronze.erp_px_cat_g1v2;

    SET end_time = NOW();
    SELECT CONCAT('>> Done. Duration: ', TIMESTAMPDIFF(SECOND, start_time, end_time), 's') AS '';

    -- ─────────────────────────────────────────
    --  SUMMARY
    -- ─────────────────────────────────────────

    SELECT '=====================================' AS '';
    SELECT CONCAT(
        'Silver Load Complete. Total Duration: ',
        TIMESTAMPDIFF(SECOND, batch_start, NOW()), 's'
    ) AS '';
    SELECT '=====================================' AS '';

END$$

DELIMITER ;

-- Run the procedure
CALL silver.load_silver();
