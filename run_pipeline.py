"""
run_pipeline.py
---------------
Orchestrates all pipeline stages in order:

  01_validate  ->  02_ingest  ->  03_transform  ->  04_mart  ->  05_anomaly

Run this from the project root:
    python run_pipeline.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "pipeline"))

import importlib
from datetime import datetime


def run_stage(module_name: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  STAGE: {module_name}")
    print(f"{'=' * 60}")
    mod = importlib.import_module(module_name)
    mod.run()


if __name__ == "__main__":
    start = datetime.now()
    print(f"\nMeta Ads Performance Analytics Pipeline")
    print(f"Started at: {start.strftime('%Y-%m-%d %H:%M:%S')}")

    stages = [
        "validate",    # maps to pipeline/01_validate.py
        "ingest",      # maps to pipeline/02_ingest.py
        "transform",   # maps to pipeline/03_transform.py
        "mart",        # maps to pipeline/04_mart.py
        "anomaly",     # maps to pipeline/05_anomaly.py
    ]

    # Rename modules to match file names without numeric prefix
    import os, importlib.util

    pipeline_dir = Path(__file__).parent / "pipeline"
    file_map = {
        "validate":  "01_validate",
        "ingest":    "02_ingest",
        "transform": "03_transform",
        "mart":      "04_mart",
        "anomaly":   "05_anomaly",
    }

    for stage_key in stages:
        filename = file_map[stage_key]
        filepath = pipeline_dir / f"{filename}.py"
        spec = importlib.util.spec_from_file_location(stage_key, filepath)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.run()

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\nPipeline completed in {elapsed:.1f}s\n")
