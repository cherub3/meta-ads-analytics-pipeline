"""
02_ingest.py
------------
Bronze layer ingestion with incremental (checkpoint-based) loading.

Reads valid rows from the source CSV, filters by last_loaded_date,
appends new rows to raw_campaign_performance in DuckDB, and updates
the checkpoint file.

Always run 01_validate.py before this script.
"""

import pandas as pd
import duckdb
from datetime import datetime, date
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent.parent
DATA_PATH       = BASE_DIR / "dataset" / "data.csv"
DB_PATH         = BASE_DIR / "warehouse" / "meta_ads.duckdb"
CHECKPOINT_PATH = BASE_DIR / "checkpoints" / "last_loaded_date.txt"

VALID_CAMPAIGN_IDS = {"916", "936", "1178"}


# ── Checkpoint helpers ─────────────────────────────────────────────────────────
def read_checkpoint() -> date:
    """Returns the last successfully loaded date. Defaults to 1900-01-01."""
    if CHECKPOINT_PATH.exists():
        raw = CHECKPOINT_PATH.read_text().strip()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date(1900, 1, 1)


def write_checkpoint(last_date: date) -> None:
    CHECKPOINT_PATH.write_text(last_date.strftime("%Y-%m-%d"))
    print(f"[ingest] Checkpoint updated     : {last_date}")


# ── Load and filter ────────────────────────────────────────────────────────────
def load_valid_rows(last_loaded_date: date) -> pd.DataFrame:
    """Loads source CSV, applies validation filter, then date filter."""
    df = pd.read_csv(DATA_PATH, dtype={
        "campaign_id":      str,
        "fb_campaign_id":   str,
        "age":              str,
        "gender":           str,
    })

    # Keep only clean rows (mirrors 01_validate.py rule 1)
    df = df[df["campaign_id"].isin(VALID_CAMPAIGN_IDS)].copy()

    # Parse dates
    df["reporting_start"] = pd.to_datetime(df["reporting_start"], dayfirst=True).dt.date
    df["reporting_end"]   = pd.to_datetime(df["reporting_end"],   dayfirst=True).dt.date

    # Incremental filter — only rows newer than the checkpoint
    new_rows = df[df["reporting_start"] > last_loaded_date].copy()

    print(f"[ingest] Last loaded date       : {last_loaded_date}")
    print(f"[ingest] Valid rows in source   : {len(df):,}")
    print(f"[ingest] New rows to load       : {len(new_rows):,}")

    return new_rows


# ── Create bronze table ────────────────────────────────────────────────────────
def ensure_bronze_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw_campaign_performance (
            ad_id               INTEGER,
            reporting_start     DATE,
            reporting_end       DATE,
            campaign_id         VARCHAR,
            fb_campaign_id      VARCHAR,
            age                 VARCHAR,
            gender              VARCHAR,
            interest1           INTEGER,
            interest2           INTEGER,
            interest3           INTEGER,
            impressions         DOUBLE,
            clicks              INTEGER,
            spent               DOUBLE,
            total_conversion    DOUBLE,
            approved_conversion DOUBLE,
            loaded_at           TIMESTAMP
        )
    """)


# ── Write to DuckDB ────────────────────────────────────────────────────────────
def ingest(df: pd.DataFrame) -> None:
    if len(df) == 0:
        print("[ingest] No new rows to load. Pipeline is up to date.")
        return

    df = df.copy()
    df["loaded_at"] = datetime.now()

    # Select only the columns the bronze table expects
    columns = [
        "ad_id", "reporting_start", "reporting_end",
        "campaign_id", "fb_campaign_id",
        "age", "gender",
        "interest1", "interest2", "interest3",
        "impressions", "clicks", "spent",
        "total_conversion", "approved_conversion",
        "loaded_at",
    ]
    df = df[columns]

    con = duckdb.connect(str(DB_PATH))
    ensure_bronze_table(con)

    # Append — bronze is append-only (never delete, never overwrite)
    con.execute("INSERT INTO raw_campaign_performance SELECT * FROM df")

    row_count = con.execute("SELECT COUNT(*) FROM raw_campaign_performance").fetchone()[0]
    con.close()

    print(f"[ingest] Rows inserted          : {len(df):,}")
    print(f"[ingest] Total rows in bronze   : {row_count:,}")


# ── Entry point ────────────────────────────────────────────────────────────────
def run() -> pd.DataFrame:
    print("\n[ingest] Starting ingestion layer...")

    last_loaded_date = read_checkpoint()
    new_rows         = load_valid_rows(last_loaded_date)

    ingest(new_rows)

    if len(new_rows) > 0:
        max_date = new_rows["reporting_start"].max()
        write_checkpoint(max_date)

    print("[ingest] Done.\n")
    return new_rows


if __name__ == "__main__":
    run()
