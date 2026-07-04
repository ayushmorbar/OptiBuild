"""MCP systematic data cleaning rules and functions."""

import pandas as pd

from app.mcp_server.store import store
from app.schema import CleanCategoryReport, CleanReport


def drop_invalid_prices(
    df: pd.DataFrame, category: str, ds_meta: dict
) -> tuple[pd.DataFrame, list[str], int]:
    """Drop rows where price is null or non-positive."""
    if "price" not in df.columns:
        return df, [], 0
    initial_rows = len(df)
    df_clean = df[df["price"].notna() & (df["price"] > 0)]
    dropped = initial_rows - len(df_clean)
    fixes = []
    if dropped > 0:
        fixes.append(f"dropped {dropped} rows: null/<=0 price")
    return df_clean, fixes, dropped


def coerce_numeric_columns(
    df: pd.DataFrame, category: str, ds_meta: dict
) -> tuple[pd.DataFrame, list[str], int]:
    """Coerce declared numeric columns and drop rows with invalid values."""
    initial_rows = len(df)
    df_clean = df.copy()

    num_cols = []
    for col_name, col_meta in ds_meta.get("columns", {}).items():
        if col_name in df.columns and col_meta.get("type") in ("int", "float"):
            num_cols.append(col_name)

    for col in num_cols:
        # Persist the numeric conversion (not just drop failures) so downstream
        # comparisons operate on real numeric dtypes, then drop rows that failed.
        df_clean = df_clean.assign(
            **{col: pd.to_numeric(df_clean[col], errors="coerce")}
        )
        df_clean = df_clean[df_clean[col].notna()]

    dropped = initial_rows - len(df_clean)
    fixes = []
    if dropped > 0:
        fixes.append(f"coerced numeric columns, dropped {dropped} non-numeric row")
    return df_clean, fixes, dropped


def remove_price_outliers(
    df: pd.DataFrame, category: str, ds_meta: dict
) -> tuple[pd.DataFrame, list[str], int]:
    """Remove price outliers using the IQR rule."""
    if "price" not in df.columns or len(df) == 0:
        return df, [], 0
    initial_rows = len(df)

    q1 = df["price"].quantile(0.25)
    q3 = df["price"].quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    df_clean = df[(df["price"] >= lower_bound) & (df["price"] <= upper_bound)]
    dropped = initial_rows - len(df_clean)

    fixes = []
    if dropped > 0:
        fixes.append(f"dropped {dropped} price outliers (IQR)")
    return df_clean, fixes, dropped


SYSTEMATIC_RULES = [
    drop_invalid_prices,
    coerce_numeric_columns,
    remove_price_outliers,
]


def clean_systematic(handle: str, metadata: dict) -> CleanReport:
    """Apply systematic cleaning pipeline to stored datasets under handle."""
    frames = store.get(handle)
    cleaned_frames = {}
    per_category_report = {}

    for category, df in frames.items():
        ds_meta = {}
        for ds in metadata.get("datasets", []):
            if ds["category_key"] == category:
                ds_meta = ds
                break

        current_df = df
        fixes = []
        total_dropped = 0

        for rule in SYSTEMATIC_RULES:
            current_df, rule_fixes, rule_dropped = rule(current_df, category, ds_meta)
            fixes.extend(rule_fixes)
            total_dropped += rule_dropped

        cleaned_frames[category] = current_df
        per_category_report[category] = CleanCategoryReport(
            rows_dropped=total_dropped, fixes=fixes
        )

    store.replace(handle, cleaned_frames)

    return CleanReport(handle=handle, per_category=per_category_report)
