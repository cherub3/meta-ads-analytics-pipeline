"""
01_validate.py
--------------
Validation layer for the Meta Ads Performance Analytics Pipeline.

Reads the raw CSV, applies validation rules, separates valid from rejected
records, and writes validation_log + validation_summary to DuckDB.

Run this script first. Nothing enters the warehouse before passing validation.
"""

import pandas as pd
import duckdb
import json
from datetime import datetime
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent
DATA_PATH   = BASE_DIR / "dataset" / "data.csv"
DB_PATH     = BASE_DIR / "warehouse" / "meta_ads.duckdb"

# ── Constants ──────────────────────────────────────────────────────────────────
VALID_CAMPAIGN_IDS = {"916", "936", "1178"}

RUN_TIMESTAMP = datetime.now()


# ── Load raw CSV ───────────────────────────────────────────────────────────────
def load_raw(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)   # load everything as string first
    print(f"[validate] Raw rows loaded     : {len(df):,}")
    return df


# ── Validation rules ───────────────────────────────────────────────────────────
def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (valid_df, rejected_df).
    rejected_df has an extra column 'rejection_reason'.
    A row can only have one reason — the first failing rule wins.
    """
    rejection_reasons = {}  # index → reason

    # Rule 1 — invalid campaign_id (catches all 382 column-shifted rows)
    bad_campaign = ~df["campaign_id"].isin(VALID_CAMPAIGN_IDS)
    for idx in df[bad_campaign].index:
        if idx not in rejection_reasons:
            rejection_reasons[idx] = "invalid_campaign_id"

    # Rule 2 — both conversion columns are null
    # Cast to float for null check; non-numeric strings become NaN automatically
    conv_total    = pd.to_numeric(df["total_conversion"],    errors="coerce")
    conv_approved = pd.to_numeric(df["approved_conversion"], errors="coerce")
    both_null = conv_total.isna() & conv_approved.isna()
    for idx in df[both_null].index:
        if idx not in rejection_reasons:
            rejection_reasons[idx] = "null_conversion"

    # Rule 3 — negative spend
    spend = pd.to_numeric(df["spent"], errors="coerce")
    neg_spend = spend < 0
    for idx in df[neg_spend].index:
        if idx not in rejection_reasons:
            rejection_reasons[idx] = "negative_spend"

    # Rule 4 — duplicate ad_id on the same reporting_start date
    dupes = df.duplicated(subset=["ad_id", "reporting_start"], keep="first")
    for idx in df[dupes].index:
        if idx not in rejection_reasons:
            rejection_reasons[idx] = "duplicate_ad_id"

    # Split
    rejected_idx = set(rejection_reasons.keys())
    valid_idx    = set(df.index) - rejected_idx

    valid_df    = df.loc[sorted(valid_idx)].copy()
    rejected_df = df.loc[sorted(rejected_idx)].copy()
    rejected_df["rejection_reason"] = rejected_df.index.map(rejection_reasons)

    return valid_df, rejected_df


# ── Write to DuckDB ────────────────────────────────────────────────────────────
def write_to_duckdb(valid_df: pd.DataFrame, rejected_df: pd.DataFrame) -> None:
    con = duckdb.connect(str(DB_PATH))

    # ── validation_log ─────────────────────────────────────────────────────────
    con.execute("""
        CREATE TABLE IF NOT EXISTS validation_log (
            ad_id            VARCHAR,
            reporting_start  VARCHAR,
            campaign_id      VARCHAR,
            rejection_reason VARCHAR,
            raw_row          VARCHAR,
            rejected_at      TIMESTAMP
        )
    """)

    if len(rejected_df) > 0:
        log_rows = []
        for _, row in rejected_df.iterrows():
            raw = {k: v for k, v in row.items() if k != "rejection_reason"}
            log_rows.append({
                "ad_id":            str(row.get("ad_id", "")),
                "reporting_start":  str(row.get("reporting_start", "")),
                "campaign_id":      str(row.get("campaign_id", "")),
                "rejection_reason": row["rejection_reason"],
                "raw_row":          json.dumps(raw),
                "rejected_at":      RUN_TIMESTAMP,
            })

        log_df = pd.DataFrame(log_rows)
        con.execute("DELETE FROM validation_log")   # replace on each full run
        con.execute("INSERT INTO validation_log SELECT * FROM log_df")

    # ── validation_summary ─────────────────────────────────────────────────────
    con.execute("""
        CREATE TABLE IF NOT EXISTS validation_summary (
            run_timestamp       TIMESTAMP,
            total_rows          INTEGER,
            valid_rows          INTEGER,
            rejected_rows       INTEGER,
            pct_rejected        DOUBLE,
            reason_invalid_campaign   INTEGER,
            reason_null_conversion    INTEGER,
            reason_negative_spend     INTEGER,
            reason_duplicate          INTEGER
        )
    """)

    total    = len(valid_df) + len(rejected_df)
    rejected = len(rejected_df)
    reason_counts = rejected_df["rejection_reason"].value_counts().to_dict() if rejected > 0 else {}

    summary = pd.DataFrame([{
        "run_timestamp":            RUN_TIMESTAMP,
        "total_rows":               total,
        "valid_rows":               len(valid_df),
        "rejected_rows":            rejected,
        "pct_rejected":             round(rejected / total * 100, 2) if total > 0 else 0,
        "reason_invalid_campaign":  reason_counts.get("invalid_campaign_id", 0),
        "reason_null_conversion":   reason_counts.get("null_conversion", 0),
        "reason_negative_spend":    reason_counts.get("negative_spend", 0),
        "reason_duplicate":         reason_counts.get("duplicate_ad_id", 0),
    }])

    con.execute("DELETE FROM validation_summary")
    con.execute("INSERT INTO validation_summary SELECT * FROM summary")

    con.close()


# ── Console report ─────────────────────────────────────────────────────────────
def print_summary(valid_df: pd.DataFrame, rejected_df: pd.DataFrame) -> None:
    total    = len(valid_df) + len(rejected_df)
    rejected = len(rejected_df)
    pct      = rejected / total * 100 if total > 0 else 0

    print(f"\n{'='*50}")
    print(f"  VALIDATION SUMMARY")
    print(f"{'='*50}")
    print(f"  Total rows read       : {total:,}")
    print(f"  Valid rows            : {len(valid_df):,}")
    print(f"  Rejected rows         : {rejected:,}  ({pct:.1f}%)")

    if rejected > 0:
        counts = rejected_df["rejection_reason"].value_counts()
        print(f"\n  Rejection breakdown:")
        for reason, count in counts.items():
            print(f"    {reason:<30}: {count:,}")

    print(f"{'='*50}")
    print(f"  validation_log        -> written to DuckDB")
    print(f"  validation_summary    -> written to DuckDB")
    print(f"{'='*50}\n")


# ── Entry point ────────────────────────────────────────────────────────────────
def run():
    print("\n[validate] Starting validation layer...")
    raw_df              = load_raw(DATA_PATH)
    valid_df, rejected_df = validate(raw_df)
    write_to_duckdb(valid_df, rejected_df)
    print_summary(valid_df, rejected_df)
    print("[validate] Done.\n")
    return valid_df     # returned so 02_ingest.py can call this in sequence


if __name__ == "__main__":
    run()
