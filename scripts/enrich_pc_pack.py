"""PC-pack data tooling: unpack memory.csv's packed columns into real columns.

Pack-owned domain knowledge (like gen_metadata's hand-authored defaults): the raw
dataset encodes DDR generation + speed as speed="5,6000" and module layout as
modules="2,16" (count,GB-per-module). Modelization needs real numeric columns
(e.g. "at least 32GB RAM" -> memory.capacity_gb >= 32), so this one-shot script adds:

- ddr_gen (int), speed_mhz (int)        from `speed`
- module_count (int), module_gb (int)   from `modules`
- capacity_gb (int) = module_count * module_gb

Original packed columns are kept (string-typed, harmless). Idempotent.
Run once, then regenerate the catalog:  uv run python scripts/gen_metadata.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mcp_server.pack import get_data_dir


def split_packed(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Split 'a,b' packed strings into two numeric series (NaN on bad rows)."""
    parts = series.astype(str).str.split(",", n=1, expand=True)
    left = pd.to_numeric(parts[0], errors="coerce")
    right = pd.to_numeric(parts[1] if 1 in parts.columns else None, errors="coerce")
    return left, right


def main():
    csv_path = get_data_dir() / "memory.csv"
    df = pd.read_csv(csv_path)

    if "capacity_gb" in df.columns:
        print(f"{csv_path} already enriched — nothing to do.")
        return

    df["ddr_gen"], df["speed_mhz"] = split_packed(df["speed"])
    df["module_count"], df["module_gb"] = split_packed(df["modules"])
    df["capacity_gb"] = df["module_count"] * df["module_gb"]

    before = len(df)
    # Drop the rare rows where unpacking failed (they'd be dropped at cleaning anyway)
    df = df.dropna(subset=["ddr_gen", "speed_mhz", "module_count", "module_gb"])
    for col in ("ddr_gen", "speed_mhz", "module_count", "module_gb", "capacity_gb"):
        df[col] = df[col].astype(int)

    df.to_csv(csv_path, index=False)
    print(
        f"Enriched {csv_path}: +5 columns "
        f"(ddr_gen, speed_mhz, module_count, module_gb, capacity_gb), "
        f"{before - len(df)} unparseable row(s) dropped, {len(df)} rows."
    )


if __name__ == "__main__":
    main()
