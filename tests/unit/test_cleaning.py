"""Unit tests for the MCP systematic data cleaning function."""

import pandas as pd

from app.mcp_server.cleaning import clean_systematic
from app.mcp_server.store import store


def test_clean_systematic():
    # 1. Prepare raw dataframe with various dirty rows
    # Row 0: valid normal row
    # Row 1: price <= 0 (invalid price)
    # Row 2: price is None (null price)
    # Row 3: non-numeric string "invalid_int" in core_count (declared int)
    # Row 4: normal row
    # Row 5: normal row
    # Row 6: normal row
    # Row 7: extreme price outlier (1000.0) compared to 100-120 range
    cpu_df = pd.DataFrame(
        {
            "name": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "price": [100.0, 0.0, None, 110.0, 105.0, 115.0, 120.0, 1000.0],
            "core_count": [6, 8, 4, "invalid_int", 6, 8, 6, 8],
        }
    )

    handle = store.create({"cpu": cpu_df})

    # 2. Setup mock metadata dict (declares its cost column, like the PC pack)
    metadata = {
        "version": "1.0",
        "primary_cost_column": "price",
        "datasets": [
            {
                "category_key": "cpu",
                "file_name": "cpu.csv",
                "description": "Processors",
                "synonyms": ["processor"],
                "columns": {
                    "name": {"type": "str", "required": True},
                    "price": {"type": "float", "required": True},
                    "core_count": {"type": "int", "required": False},
                },
            }
        ],
    }

    # 3. Apply cleaning
    report = clean_systematic(handle, metadata)

    # 4. Assert report correctness
    assert report.handle == handle
    assert "cpu" in report.per_category
    cat_report = report.per_category["cpu"]

    # After dropping invalid prices (price=0 and price=None) and invalid core_count ("invalid_int"),
    # the remaining prices are [100, 105, 115, 120, 1000].
    # Q1 of [100, 105, 115, 120, 1000] is 105.0, Q3 is 120.0. IQR = 15.0.
    # Outlier threshold is 120.0 + 1.5 * 15.0 = 142.5. Thus, 1000.0 is dropped.
    # Total drops: Row 1 & 2 (invalid price), Row 3 (invalid core_count), Row 7 (outlier) = 4 drops.
    assert cat_report.rows_dropped == 4
    assert len(cat_report.fixes) == 3
    assert any("null/<=0 price" in f for f in cat_report.fixes)
    assert any("coerced numeric columns" in f for f in cat_report.fixes)
    assert any("price outliers" in f for f in cat_report.fixes)

    # 5. Assert database stored value got updated
    cleaned_frames = store.get(handle)
    assert "cpu" in cleaned_frames
    cleaned_df = cleaned_frames["cpu"]
    assert len(cleaned_df) == 4
    assert list(cleaned_df["name"]) == ["A", "E", "F", "G"]
    assert list(cleaned_df["price"]) == [100.0, 105.0, 115.0, 120.0]
    assert float(cleaned_df.iloc[0]["core_count"]) == 6.0


def test_clean_systematic_without_cost_column():
    """Packs without a primary cost column only get metadata-driven numeric coercion."""
    df = pd.DataFrame(
        {
            "name": ["a", "b", "c"],
            "cost": [5.0, -2.0, 3.0],  # negative would be dropped IF declared as cost
            "score": ["10", "bad", "30"],
        }
    )
    handle = store.create({"item": df})
    metadata = {
        "version": "1.0",
        "datasets": [
            {
                "category_key": "item",
                "file_name": "item.csv",
                "description": "Items",
                "synonyms": [],
                "columns": {
                    "name": {"type": "str", "required": True},
                    "cost": {"type": "float", "required": False},
                    "score": {"type": "int", "required": False},
                },
            }
        ],
    }

    report = clean_systematic(handle, metadata)
    cat_report = report.per_category["item"]

    # Only the non-numeric 'score' row dropped; negative cost kept (no cost rules)
    assert cat_report.rows_dropped == 1
    assert all("outliers" not in f and "null/<=0" not in f for f in cat_report.fixes)
    assert len(store.get(handle)["item"]) == 2
