"""
04_mart.py
----------
Gold layer: campaign KPIs, health scores, recommendations, and daily monitoring trends.

Builds:
  - mart_campaign_kpis        : campaign-level KPIs + health score + recommendation
  - mart_campaign_monitoring  : daily metrics per campaign for trend/anomaly analysis

Run after 03_transform.py.
"""

import pandas as pd
import duckdb
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "warehouse" / "meta_ads.duckdb"


# ── KPI Calculation ────────────────────────────────────────────────────────────
def calculate_campaign_kpis(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    Aggregates fact table to campaign level and calculates all KPIs.
    Division-safe: NULLIF prevents divide-by-zero and returns NULL instead.
    """
    df = con.execute("""
        SELECT
            campaign_id,
            SUM(impressions)                                        AS total_impressions,
            SUM(clicks)                                             AS total_clicks,
            ROUND(SUM(spend), 2)                                    AS total_spend,
            SUM(total_conversion)                                   AS total_conversions,
            SUM(approved_conversion)                                AS total_approved_conv,
            COUNT(*)                                                AS fact_rows,

            -- CTR: what fraction of people who saw the ad clicked it
            ROUND(SUM(clicks) / NULLIF(SUM(impressions), 0) * 100, 4)
                                                                    AS ctr_pct,

            -- CPC: average cost per click
            ROUND(SUM(spend) / NULLIF(SUM(clicks), 0), 4)          AS cpc,

            -- CPA: cost per approved conversion (the key efficiency metric)
            ROUND(SUM(spend) / NULLIF(SUM(approved_conversion), 0), 4)
                                                                    AS cpa,

            -- Conversion Rate: of people who clicked, how many converted
            ROUND(SUM(approved_conversion) / NULLIF(SUM(clicks), 0) * 100, 4)
                                                                    AS conversion_rate_pct,

            -- CPM: cost per 1000 impressions (media buying metric)
            ROUND(SUM(spend) / NULLIF(SUM(impressions), 0) * 1000, 4)
                                                                    AS cpm

        FROM fact_campaign_performance
        GROUP BY campaign_id
        ORDER BY campaign_id
    """).df()

    return df


# ── Normalized Health Score ────────────────────────────────────────────────────
def add_health_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns a 0-100 health score using min-max normalization across campaigns.

    Four components, each worth 0-25 points:
      CTR Score        : higher CTR = higher score
      Conv Rate Score  : higher conversion rate = higher score
      CPA Score        : lower CPA = higher score  (inverted)
      CPM Score        : lower CPM = higher score  (inverted)

    With only 3 campaigns, the best campaign will score ~100 and the worst ~0.
    The score is relative — it shows how campaigns compare to each other,
    not against an external industry benchmark.
    """

    def minmax(series: pd.Series, invert: bool = False) -> pd.Series:
        lo, hi = series.min(), series.max()
        if hi == lo:
            return pd.Series([12.5] * len(series), index=series.index)
        normalized = (series - lo) / (hi - lo) * 25
        return (25 - normalized) if invert else normalized

    df = df.copy()

    df["score_ctr"]             = minmax(df["ctr_pct"])
    df["score_conversion_rate"] = minmax(df["conversion_rate_pct"])
    df["score_cpa"]             = minmax(df["cpa"], invert=True)   # lower is better
    df["score_cpm"]             = minmax(df["cpm"], invert=True)   # lower is better

    df["health_score"] = (
        df["score_ctr"] +
        df["score_conversion_rate"] +
        df["score_cpa"] +
        df["score_cpm"]
    ).round(2)

    # Label
    def label(score: float) -> str:
        if score >= 90:   return "Excellent"
        elif score >= 70: return "Good"
        elif score >= 50: return "Average"
        else:             return "Poor"

    df["health_label"] = df["health_score"].apply(label)

    return df


# ── Performance Tier + Recommendation ─────────────────────────────────────────
def add_recommendations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns a performance tier and a business recommendation to each campaign.

    Logic uses health_score as the primary signal, with CPA and conversion
    rate as secondary context. Thresholds are relative to the dataset median.
    """
    df = df.copy()

    median_cpa  = df["cpa"].median()
    median_cr   = df["conversion_rate_pct"].median()
    median_spend = df["total_spend"].median()

    tiers        = []
    recommendations = []

    for _, row in df.iterrows():
        score = row["health_score"]
        cpa   = row["cpa"]
        cr    = row["conversion_rate_pct"]
        spend = row["total_spend"]

        # High performer: top health score and good CPA
        if score >= 70 and cpa <= median_cpa:
            tier = "High Performer"
            rec  = "Scale Budget - Strong efficiency and conversion rate"

        # Wasteful: high spend but weak conversion rate
        elif spend >= median_spend and cr < median_cr:
            tier = "Poor Performer"
            rec  = "Review / Pause - High spend with low conversion rate"

        # High CPA despite spend
        elif cpa > median_cpa * 1.5:
            tier = "Poor Performer"
            rec  = "Reduce Budget - CPA is too high relative to other campaigns"

        # Moderate but not alarming
        else:
            tier = "Standard Performer"
            rec  = "Optimize - Test new audiences or ad creatives to improve CPA"

        tiers.append(tier)
        recommendations.append(rec)

    df["performance_tier"] = tiers
    df["recommendation"]   = recommendations

    return df


# ── Write mart_campaign_kpis ───────────────────────────────────────────────────
def write_campaign_kpis(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    df = df.copy()
    df["last_updated"] = datetime.now()

    con.execute("DROP TABLE IF EXISTS mart_campaign_kpis")
    con.execute("""
        CREATE TABLE mart_campaign_kpis (
            campaign_id             VARCHAR,
            total_impressions       DOUBLE,
            total_clicks            DOUBLE,
            total_spend             DOUBLE,
            total_conversions       DOUBLE,
            total_approved_conv     DOUBLE,
            fact_rows               INTEGER,
            ctr_pct                 DOUBLE,
            cpc                     DOUBLE,
            cpa                     DOUBLE,
            conversion_rate_pct     DOUBLE,
            cpm                     DOUBLE,
            score_ctr               DOUBLE,
            score_conversion_rate   DOUBLE,
            score_cpa               DOUBLE,
            score_cpm               DOUBLE,
            health_score            DOUBLE,
            health_label            VARCHAR,
            performance_tier        VARCHAR,
            recommendation          VARCHAR,
            last_updated            TIMESTAMP
        )
    """)
    con.execute("INSERT INTO mart_campaign_kpis SELECT * FROM df")
    print(f"[mart] mart_campaign_kpis       : {len(df)} rows")


# ── Build mart_campaign_monitoring ────────────────────────────────────────────
def build_monitoring_mart(con: duckdb.DuckDBPyConnection) -> None:
    """
    Daily campaign metrics for trend analysis and anomaly detection.
    This is what the monitoring dashboard and 05_anomaly.py read from.
    """
    con.execute("DROP TABLE IF EXISTS mart_campaign_monitoring")
    con.execute("""
        CREATE TABLE mart_campaign_monitoring AS
        SELECT
            campaign_id,
            date,
            SUM(impressions)                                                AS impressions,
            SUM(clicks)                                                     AS clicks,
            ROUND(SUM(spend), 2)                                            AS spend,
            SUM(approved_conversion)                                        AS approved_conversion,

            -- Daily KPIs
            ROUND(SUM(clicks) / NULLIF(SUM(impressions), 0) * 100, 4)      AS ctr_pct,
            ROUND(SUM(spend) / NULLIF(SUM(approved_conversion), 0), 4)     AS cpa,
            ROUND(SUM(spend) / NULLIF(SUM(impressions), 0) * 1000, 4)      AS cpm,
            ROUND(SUM(approved_conversion) / NULLIF(SUM(clicks), 0) * 100, 4)
                                                                            AS conversion_rate_pct,

            -- 3-day rolling average CTR (for anomaly baseline)
            ROUND(AVG(SUM(clicks) / NULLIF(SUM(impressions), 0) * 100)
                OVER (
                    PARTITION BY campaign_id
                    ORDER BY date
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                ), 4)                                                       AS ctr_3day_avg,

            -- 3-day rolling average CPA
            ROUND(AVG(SUM(spend) / NULLIF(SUM(approved_conversion), 0))
                OVER (
                    PARTITION BY campaign_id
                    ORDER BY date
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                ), 4)                                                       AS cpa_3day_avg

        FROM fact_campaign_performance
        GROUP BY campaign_id, date
        ORDER BY campaign_id, date
    """)
    n = con.execute("SELECT COUNT(*) FROM mart_campaign_monitoring").fetchone()[0]
    print(f"[mart] mart_campaign_monitoring  : {n} rows")


# ── Build campaign_summary ────────────────────────────────────────────────────
def build_campaign_summary(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    """
    A lean, human-readable summary table for dashboard cards and README findings.
    top_strength and biggest_risk are derived from the campaign's KPI profile.
    """
    rows = []
    for _, row in df.iterrows():
        # Determine top strength — the KPI component with the highest score
        component_scores = {
            "CTR":             row["score_ctr"],
            "Conversion Rate": row["score_conversion_rate"],
            "CPA Efficiency":  row["score_cpa"],
            "CPM Efficiency":  row["score_cpm"],
        }
        top_strength = max(component_scores, key=component_scores.get)

        # Determine biggest risk — the KPI component with the lowest score
        biggest_risk_key = min(component_scores, key=component_scores.get)
        risk_map = {
            "CTR":             "Low click-through rate — ad relevance may be weak",
            "Conversion Rate": "Low conversion rate — clicks not converting to customers",
            "CPA Efficiency":  "High cost per acquisition — budget not working efficiently",
            "CPM Efficiency":  "High cost per thousand impressions — expensive reach",
        }
        biggest_risk = risk_map[biggest_risk_key]

        rows.append({
            "campaign_id":   row["campaign_id"],
            "health_score":  row["health_score"],
            "health_label":  row["health_label"],
            "performance_tier": row["performance_tier"],
            "recommendation": row["recommendation"],
            "top_strength":  top_strength,
            "biggest_risk":  biggest_risk,
        })

    summary_df = pd.DataFrame(rows)
    con.execute("DROP TABLE IF EXISTS campaign_summary")
    con.execute("""
        CREATE TABLE campaign_summary (
            campaign_id      VARCHAR,
            health_score     DOUBLE,
            health_label     VARCHAR,
            performance_tier VARCHAR,
            recommendation   VARCHAR,
            top_strength     VARCHAR,
            biggest_risk     VARCHAR
        )
    """)
    con.execute("INSERT INTO campaign_summary SELECT * FROM summary_df")
    print(f"[mart] campaign_summary          : {len(summary_df)} rows")


# ── Console report ─────────────────────────────────────────────────────────────
def print_kpi_report(df: pd.DataFrame) -> None:
    print("\n" + "=" * 65)
    print("  CAMPAIGN KPI SUMMARY")
    print("=" * 65)
    cols = ["campaign_id", "total_spend", "total_approved_conv",
            "ctr_pct", "cpa", "conversion_rate_pct", "cpm",
            "health_score", "health_label", "performance_tier"]
    print(df[cols].to_string(index=False))
    print("=" * 65 + "\n")

    print("  RECOMMENDATIONS")
    print("=" * 65)
    for _, row in df.iterrows():
        print(f"  Campaign {row['campaign_id']} ({row['performance_tier']})")
        print(f"  -> {row['recommendation']}")
        print()


# ── Entry point ────────────────────────────────────────────────────────────────
def run() -> None:
    print("\n[mart] Starting mart layer...")
    con = duckdb.connect(str(DB_PATH))

    df = calculate_campaign_kpis(con)
    df = add_health_score(df)
    df = add_recommendations(df)
    write_campaign_kpis(con, df)
    build_monitoring_mart(con)
    build_campaign_summary(con, df)
    print_kpi_report(df)

    con.close()
    print("[mart] Done.\n")


if __name__ == "__main__":
    run()
