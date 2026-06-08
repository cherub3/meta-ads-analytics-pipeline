"""
03_transform.py
---------------
Silver layer transformation.

Reads raw_campaign_performance (bronze) and builds:
  - dim_campaign               : one row per campaign
  - dim_audience               : one row per age x gender combination
  - fact_campaign_performance  : aggregated metrics at campaign x date x audience grain

Run after 02_ingest.py.
"""

import duckdb
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "warehouse" / "meta_ads.duckdb"


def build_dim_campaign(con: duckdb.DuckDBPyConnection) -> None:
    """
    One row per campaign_id.
    Captures the date range and total ad row count for reference.
    """
    con.execute("DROP TABLE IF EXISTS dim_campaign")
    con.execute("""
        CREATE TABLE dim_campaign AS
        SELECT
            campaign_id,
            COUNT(DISTINCT fb_campaign_id)  AS distinct_fb_campaigns,
            COUNT(*)                        AS total_ad_rows,
            MIN(reporting_start)            AS first_seen_date,
            MAX(reporting_start)            AS last_seen_date
        FROM raw_campaign_performance
        GROUP BY campaign_id
        ORDER BY campaign_id
    """)
    n = con.execute("SELECT COUNT(*) FROM dim_campaign").fetchone()[0]
    print(f"[transform] dim_campaign         : {n} rows")


def build_dim_audience(con: duckdb.DuckDBPyConnection) -> None:
    """
    One row per age x gender combination.
    audience_id is a natural key: age_age_group + '_' + gender.
    """
    con.execute("DROP TABLE IF EXISTS dim_audience")
    con.execute("""
        CREATE TABLE dim_audience AS
        SELECT
            age || '_' || gender    AS audience_id,
            age                     AS age_group,
            gender
        FROM raw_campaign_performance
        WHERE age   IN ('30-34', '35-39', '40-44', '45-49')
          AND gender IN ('M', 'F')
        GROUP BY age, gender
        ORDER BY age, gender
    """)
    n = con.execute("SELECT COUNT(*) FROM dim_audience").fetchone()[0]
    print(f"[transform] dim_audience         : {n} rows")


def build_fact_campaign_performance(con: duckdb.DuckDBPyConnection) -> None:
    """
    Aggregates ad-level rows up to campaign x date x audience grain.
    Metrics are summed. ad_count tracks how many source rows rolled up.

    Only includes rows with a valid audience (age/gender pass the filter).
    Some rows in the bronze table have non-standard age/gender values
    (leftovers from column-shifted records that slipped through, if any).
    These are excluded here.
    """
    con.execute("DROP TABLE IF EXISTS fact_campaign_performance")
    con.execute("""
        CREATE TABLE fact_campaign_performance AS
        SELECT
            r.campaign_id,
            r.reporting_start                       AS date,
            r.age || '_' || r.gender                AS audience_id,
            SUM(r.impressions)                      AS impressions,
            SUM(r.clicks)                           AS clicks,
            ROUND(SUM(r.spent), 4)                  AS spend,
            SUM(r.total_conversion)                 AS total_conversion,
            SUM(r.approved_conversion)              AS approved_conversion,
            COUNT(*)                                AS ad_count
        FROM raw_campaign_performance r
        WHERE r.age    IN ('30-34', '35-39', '40-44', '45-49')
          AND r.gender IN ('M', 'F')
        GROUP BY r.campaign_id, r.reporting_start, r.age, r.gender
        ORDER BY r.campaign_id, r.reporting_start, r.age, r.gender
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_campaign_performance").fetchone()[0]
    print(f"[transform] fact_campaign_perf   : {n} rows")


def validate_fact(con: duckdb.DuckDBPyConnection) -> None:
    """Quick sanity checks on the fact table after build."""
    result = con.execute("""
        SELECT
            COUNT(*)                        AS total_rows,
            COUNT(DISTINCT campaign_id)     AS campaigns,
            COUNT(DISTINCT date)            AS dates,
            COUNT(DISTINCT audience_id)     AS audiences,
            ROUND(SUM(spend), 2)            AS total_spend,
            SUM(clicks)                     AS total_clicks,
            SUM(approved_conversion)        AS total_approved_conv
        FROM fact_campaign_performance
    """).df()
    print("\n[transform] Fact table summary:")
    print(result.to_string(index=False))

    # Check for negative values — should be zero
    neg = con.execute("""
        SELECT COUNT(*) FROM fact_campaign_performance
        WHERE spend < 0 OR clicks < 0 OR impressions < 0
    """).fetchone()[0]
    print(f"\n[transform] Negative metric rows : {neg} (expected: 0)")


def run() -> None:
    print("\n[transform] Starting transformation layer...")
    con = duckdb.connect(str(DB_PATH))

    build_dim_campaign(con)
    build_dim_audience(con)
    build_fact_campaign_performance(con)
    validate_fact(con)

    con.close()
    print("\n[transform] Done.\n")


if __name__ == "__main__":
    run()
