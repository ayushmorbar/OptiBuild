"""Unit tests for the clean_dynamic MCP tool function."""

import pandas as pd

from app.mcp_server.safe_ops import clean_dynamic
from app.mcp_server.store import store


def test_clean_dynamic_success_ops():
    # Setup data
    cpu_df = pd.DataFrame(
        {
            "name": ["Ryzen 5 7600", "Core i5-13600K", "Ryzen 9 7900X", None],
            "price": [199.00, 299.99, 399.00, 150.00],
            "tdp": [65, 125, 170, 65],
            "color": ["Black", "White / Black", "Black", "Black"],
        }
    )

    handle = store.create({"cpu": cpu_df})

    ops = [
        # 1. drop_nulls on 'name' -> drops the None row (4 -> 3)
        {"op": "drop_nulls", "category": "cpu", "columns": ["name"]},
        # 2. map_values on 'color' -> normalizes 'White / Black' -> 'White' (3 rows remain)
        {
            "op": "map_values",
            "category": "cpu",
            "column": "color",
            "mapping": {"White / Black": "White"},
        },
        # 3. clip_range on 'tdp' -> drops Ryzen 9 7900X with tdp=170 (> 130) (3 -> 2)
        {"op": "clip_range", "category": "cpu", "column": "tdp", "max": 130},
        # 4. filter_rows on 'price' -> drops Ryzen 5 7600 with price < 200 (2 -> 1)
        {"op": "filter_rows", "category": "cpu", "expr": "price > 200.0"},
    ]

    report = clean_dynamic(handle, ops)

    assert report.accepted_ops == 4
    assert len(report.rejected) == 0
    assert report.per_category["cpu"].rows_before == 4
    assert report.per_category["cpu"].rows_after == 1
    assert "color" in report.columns_changed

    # Check store got updated
    updated_df = store.get(handle)["cpu"]
    assert len(updated_df) == 1
    assert updated_df.iloc[0]["name"] == "Core i5-13600K"
    assert updated_df.iloc[0]["color"] == "White"


def test_clean_dynamic_rejections_and_security():
    # Setup data
    cpu_df = pd.DataFrame(
        {
            "name": ["Ryzen 5 7600", "Core i5-13600K", "Ryzen 9 7900X"],
            "price": [199.00, 299.99, 399.00],
            "tdp": [65, 125, 170],
        }
    )

    handle = store.create({"cpu": cpu_df})

    ops = [
        # 1. Unknown op type -> rejected
        {"op": "unknown_op", "category": "cpu"},
        # 2. Op with extra field -> rejected (extra="forbid")
        {
            "op": "clip_range",
            "category": "cpu",
            "column": "tdp",
            "max": 130,
            "extra_field": "not_allowed",
        },
        # 3. Valid op -> accepted (price > 200 -> drops Ryzen 5 7600)
        {"op": "filter_rows", "category": "cpu", "expr": "price > 200.0"},
        # 4. Hostile expression in filter_rows -> rejected
        {
            "op": "filter_rows",
            "category": "cpu",
            "expr": "os.system('x')",
        },
    ]

    report = clean_dynamic(handle, ops)

    assert report.accepted_ops == 1
    assert len(report.rejected) == 3
    reasons = [r.reason for r in report.rejected]
    assert any(
        "Extra inputs are not permitted" in r or "extra_field" in r or "extra" in r
        for r in reasons
    )
    assert any("Forbidden AST node type" in r for r in reasons)
    assert any(
        "Input tag" in r or "discriminator" in r or "union" in r for r in reasons
    )

    # Check store reflects only accepted changes (original 3 rows -> 2 rows after price > 200)
    updated_df = store.get(handle)["cpu"]
    assert len(updated_df) == 2
    assert list(updated_df["name"]) == ["Core i5-13600K", "Ryzen 9 7900X"]


def test_clean_dynamic_effect_validation_and_batch_revert():
    # Setup data with 10 rows
    cpu_df = pd.DataFrame(
        {
            "name": [f"CPU_{i}" for i in range(10)],
            "price": [100.0] * 10,
            "tdp": [65] * 10,
        }
    )

    handle = store.create({"cpu": cpu_df})

    # 1. Test effect validation: filter that empties category is rejected (0 < len(candidate) violated)
    ops_empty = [{"op": "filter_rows", "category": "cpu", "expr": "price > 500.0"}]
    report_empty = clean_dynamic(handle, ops_empty)
    assert report_empty.accepted_ops == 0
    assert len(report_empty.rejected) == 1
    assert "category became empty" in report_empty.rejected[0].reason
    assert store.get(handle)["cpu"].shape[0] == 10  # Unchanged

    # 2. Test batch revert: drop >90% of rows (10 out of 11 rows) -> category is reverted to original 11 rows
    cpu_df_11 = pd.DataFrame(
        {
            "name": [f"CPU_{i}" for i in range(11)],
            "price": [100.0] * 11,
            "tdp": [65] * 11,
        }
    )
    handle_11 = store.create({"cpu": cpu_df_11})

    ops_batch_drop = [
        # Keep only the first row -> drops 10 rows (>90% drop)
        {"op": "filter_rows", "category": "cpu", "expr": "name == 'CPU_0'"}
    ]
    report_batch = clean_dynamic(handle_11, ops_batch_drop)
    assert report_batch.accepted_ops == 1  # The individual op was accepted initially
    assert len(report_batch.rejected) == 1  # But batch drop revert adds a rejection
    assert "batch dropped >90% of rows (reverted)" in report_batch.rejected[0].reason
    assert store.get(handle_11)["cpu"].shape[0] == 11  # Reverted back to 11
