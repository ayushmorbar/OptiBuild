"""Unit tests for the prefilter MCP tool function."""

import pandas as pd

from app.mcp_server.prefilter import prefilter
from app.mcp_server.store import store


def test_prefilter_scenarios():
    # Setup data
    cpu_df = pd.DataFrame(
        {
            "name": ["Ryzen 5 7600", "Core i5-13600K", "Ryzen 9 7900X"],
            "price": [199.00, 299.99, 399.00],
            "tdp": [65, 125, 170],
        }
    )

    handle = store.create({"cpu": cpu_df})

    constraints = [
        # 1. Single-component literal hard constraint -> Should filter CPU (3 -> 2 rows, price <= 300)
        {
            "name": "budget_cap",
            "left_side": "cpu.price",
            "operator": "<=",
            "right_side": {"kind": "literal", "value": 300.0},
            "is_hard": True,
            "origin": "user_explicit",
        },
        # 2. Solver-stage constraint (soft constraint) -> Should be IGNORED
        {
            "name": "soft_tdp",
            "left_side": "cpu.tdp",
            "operator": "<=",
            "right_side": {"kind": "literal", "value": 100},
            "is_hard": False,
            "origin": "user_explicit",
        },
        # 3. Solver-stage constraint (var_ref right_side) -> Should be IGNORED
        {
            "name": "gpu_cap",
            "left_side": "cpu.price",
            "operator": "<=",
            "right_side": {"kind": "var_ref", "ref": "gpu.price"},
            "is_hard": True,
            "origin": "user_explicit",
        },
        # 4. Solver-stage constraint (no dot in left_side -> derived var) -> Should be IGNORED
        {
            "name": "derived_cap",
            "left_side": "total_cost",
            "operator": "<=",
            "right_side": {"kind": "literal", "value": 1000},
            "is_hard": True,
            "origin": "user_explicit",
        },
        # 5. Column is absent -> Should be skipped without error
        {
            "name": "missing_col",
            "left_side": "cpu.nonexistent_column",
            "operator": "==",
            "right_side": {"kind": "literal", "value": 10},
            "is_hard": True,
            "origin": "user_explicit",
        },
    ]

    report = prefilter(handle, constraints)

    # Assertions
    assert "cpu" in report.per_category
    assert report.per_category["cpu"].rows_before == 3
    # Only constraint 1 should be applied, filtering price <= 300 -> 2 rows remain
    assert report.per_category["cpu"].rows_after == 2
    assert len(report.emptied_categories) == 0

    # Verify store got updated
    updated_df = store.get(handle)["cpu"]
    assert len(updated_df) == 2
    assert list(updated_df["name"]) == ["Ryzen 5 7600", "Core i5-13600K"]


def test_prefilter_emptied_categories():
    # Setup data
    cpu_df = pd.DataFrame(
        {
            "name": ["Ryzen 5 7600"],
            "price": [199.00],
        }
    )

    handle = store.create({"cpu": cpu_df})

    constraints = [
        # Over-restrictive constraint -> leaves 0 rows
        {
            "name": "over_restrictive",
            "left_side": "cpu.price",
            "operator": "<",
            "right_side": {"kind": "literal", "value": 100.0},
            "is_hard": True,
            "origin": "user_explicit",
        }
    ]

    report = prefilter(handle, constraints)

    assert report.per_category["cpu"].rows_before == 1
    assert report.per_category["cpu"].rows_after == 0
    assert report.emptied_categories == ["cpu"]

    # Verify store reflects emptied frame
    updated_df = store.get(handle)["cpu"]
    assert len(updated_df) == 0
