"""
05_anomaly.py
-------------
Rule-based anomaly detection on daily campaign performance trends.

Reads mart_campaign_monitoring and flags unusual patterns.
All anomalies are written to anomaly_log in DuckDB.

No machine learning. Rules are simple, transparent, and interview-defensible.
Run after 04_mart.py.
"""

import pandas as pd
import duckdb
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "warehouse" / "meta_ads.duckdb"

DETECTED_AT = datetime.now()


# ── Load monitoring data ───────────────────────────────────────────────────────
def load_monitoring(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            campaign_id,
            date,
            impressions,
            clicks,
            spend,
            approved_conversion,
            ctr_pct,
            cpa,
            cpm,
            conversion_rate_pct,
            ctr_3day_avg,
            cpa_3day_avg
        FROM mart_campaign_monitoring
        ORDER BY campaign_id, date
    """).df()


# ── Anomaly detection rules ────────────────────────────────────────────────────
def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies four rules to the daily monitoring data.
    Returns a DataFrame of flagged rows with anomaly_type and severity.
    """
    anomalies = []

    # Pre-compute per-campaign average daily spend (for spend spike rule)
    avg_spend = df.groupby("campaign_id")["spend"].mean().rename("avg_daily_spend")
    df = df.join(avg_spend, on="campaign_id")

    for _, row in df.iterrows():
        campaign = row["campaign_id"]
        date     = row["date"]
        flags    = []

        # Rule 1 — CTR Drop > 30% below 3-day rolling average
        # Only flag if we have enough history (ctr_3day_avg is populated)
        if (
            pd.notna(row["ctr_3day_avg"])
            and row["ctr_3day_avg"] > 0
            and row["ctr_pct"] < row["ctr_3day_avg"] * 0.70
        ):
            drop_pct = (1 - row["ctr_pct"] / row["ctr_3day_avg"]) * 100
            flags.append({
                "anomaly_type": "CTR_DROP",
                "severity":     "HIGH",
                "metric_value": round(row["ctr_pct"], 4),
                "baseline":     round(row["ctr_3day_avg"], 4),
                "description":  f"CTR dropped {drop_pct:.1f}% below 3-day average "
                                f"({row['ctr_pct']:.4f}% vs baseline {row['ctr_3day_avg']:.4f}%)"
            })

        # Rule 2 — CPA Spike > 50% above 3-day rolling average
        if (
            pd.notna(row["cpa_3day_avg"])
            and row["cpa_3day_avg"] > 0
            and pd.notna(row["cpa"])
            and row["cpa"] > row["cpa_3day_avg"] * 1.50
        ):
            spike_pct = (row["cpa"] / row["cpa_3day_avg"] - 1) * 100
            flags.append({
                "anomaly_type": "CPA_SPIKE",
                "severity":     "HIGH",
                "metric_value": round(row["cpa"], 4),
                "baseline":     round(row["cpa_3day_avg"], 4),
                "description":  f"CPA spiked {spike_pct:.1f}% above 3-day average "
                                f"(${row['cpa']:.2f} vs baseline ${row['cpa_3day_avg']:.2f})"
            })

        # Rule 3 — Spend Spike > 3x average daily spend for this campaign
        if (
            row["avg_daily_spend"] > 0
            and row["spend"] > row["avg_daily_spend"] * 3.0
        ):
            multiple = row["spend"] / row["avg_daily_spend"]
            flags.append({
                "anomaly_type": "SPEND_SPIKE",
                "severity":     "MEDIUM",
                "metric_value": round(row["spend"], 2),
                "baseline":     round(row["avg_daily_spend"], 2),
                "description":  f"Daily spend ${row['spend']:.2f} is {multiple:.1f}x "
                                f"the campaign average (${row['avg_daily_spend']:.2f}/day)"
            })

        # Rule 4 — Zero conversions on a day with non-zero spend
        if row["approved_conversion"] == 0 and row["spend"] > 0:
            flags.append({
                "anomaly_type": "ZERO_CONVERSIONS",
                "severity":     "HIGH",
                "metric_value": 0.0,
                "baseline":     None,
                "description":  f"Zero approved conversions despite ${row['spend']:.2f} spend"
            })

        for flag in flags:
            anomalies.append({
                "campaign_id":  campaign,
                "date":         date,
                "detected_at":  DETECTED_AT,
                **flag,
            })

    if anomalies:
        return pd.DataFrame(anomalies)
    return pd.DataFrame(columns=[
        "campaign_id", "date", "detected_at",
        "anomaly_type", "severity", "metric_value", "baseline", "description"
    ])


# ── Write anomaly_log ──────────────────────────────────────────────────────────
def write_anomaly_log(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    con.execute("DROP TABLE IF EXISTS anomaly_log")
    con.execute("""
        CREATE TABLE anomaly_log (
            campaign_id     VARCHAR,
            date            DATE,
            detected_at     TIMESTAMP,
            anomaly_type    VARCHAR,
            severity        VARCHAR,
            metric_value    DOUBLE,
            baseline        DOUBLE,
            description     VARCHAR
        )
    """)

    if len(df) > 0:
        con.execute("INSERT INTO anomaly_log SELECT * FROM df")

    n = con.execute("SELECT COUNT(*) FROM anomaly_log").fetchone()[0]
    print(f"[anomaly] anomaly_log            : {n} anomalies detected")


# ── Console report ─────────────────────────────────────────────────────────────
def print_anomaly_report(df: pd.DataFrame) -> None:
    print("\n" + "=" * 65)
    print("  ANOMALY DETECTION REPORT")
    print("=" * 65)

    if len(df) == 0:
        print("  No anomalies detected.")
        print("=" * 65 + "\n")
        return

    by_type = df.groupby(["anomaly_type", "severity"]).size().reset_index(name="count")
    print(f"  Total anomalies: {len(df)}")
    print()
    for _, row in by_type.iterrows():
        print(f"  [{row['severity']:<6}] {row['anomaly_type']:<20}: {row['count']} occurrence(s)")

    print()
    print("  Sample anomalies:")
    print()
    for _, row in df.head(6).iterrows():
        print(f"  Campaign {row['campaign_id']} | {row['date']} | {row['anomaly_type']}")
        print(f"  {row['description']}")
        print()

    print("=" * 65 + "\n")


# ── Entry point ────────────────────────────────────────────────────────────────
def run() -> None:
    print("\n[anomaly] Starting anomaly detection...")
    con = duckdb.connect(str(DB_PATH))

    monitoring_df = load_monitoring(con)
    print(f"[anomaly] Daily trend rows loaded : {len(monitoring_df)}")

    anomaly_df = detect_anomalies(monitoring_df)
    write_anomaly_log(con, anomaly_df)
    print_anomaly_report(anomaly_df)

    con.close()
    print("[anomaly] Done.\n")


if __name__ == "__main__":
    run()
