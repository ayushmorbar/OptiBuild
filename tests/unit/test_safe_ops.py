"""Unit tests for AST-based expression validation and safe pandas querying."""

import pandas as pd
import pytest

from app.mcp_server.safe_ops import query_data, safe_query, validate_expr
from app.mcp_server.store import store


def test_validate_expr_rejects():
    allowed = {"price", "tdp", "cores"}

    # 1. os.system('x') -> rejects Call node
    with pytest.raises(ValueError) as exc:
        validate_expr("os.system('x')", allowed)
    assert "Forbidden AST node type" in str(exc.value)

    # 2. price.__class__ -> rejects Attribute node
    with pytest.raises(ValueError) as exc:
        validate_expr("price.__class__", allowed)
    assert "Forbidden AST node type" in str(exc.value)

    # 3. Name containing '__' -> rejects dunder structures
    with pytest.raises(ValueError) as exc:
        validate_expr("price__foo > 5", allowed | {"price__foo"})
    assert "Forbidden name structure" in str(exc.value)

    # 4. @budget -> contains forbidden character @
    with pytest.raises(ValueError) as exc:
        validate_expr("@budget", allowed)
    assert "forbidden character" in str(exc.value)

    # 5. `col` -> contains forbidden character backtick
    with pytest.raises(ValueError) as exc:
        validate_expr("`col`", allowed)
    assert "forbidden character" in str(exc.value)

    # 6. >300-char expression -> rejects too long
    long_expr = "price < 100 " + "and price < 100 " * 30
    assert len(long_expr) > 300
    with pytest.raises(ValueError) as exc:
        validate_expr(long_expr, allowed)
    assert "Expression is too long" in str(exc.value)

    # 7. Name not in allowed_columns -> rejects unknown variable
    with pytest.raises(ValueError) as exc:
        validate_expr("nonexistent_col < 5", allowed)
    assert "Forbidden variable reference" in str(exc.value)


def test_validate_expr_accepts():
    allowed = {"price", "tdp", "cores"}

    # Accept valid comparisons and basic bin ops/bool ops
    validate_expr("price < 500", allowed)
    validate_expr("price >= 100 and tdp < 65", allowed)
    validate_expr("cores * 2 >= 8", allowed)


def test_safe_query_filtering():
    df = pd.DataFrame({"price": [100, 200, 300], "tdp": [65, 125, 65]})
    allowed = {"price", "tdp"}

    result = safe_query(df, "price > 150 and tdp == 65", allowed)
    assert len(result) == 1
    assert result.iloc[0]["price"] == 300


def test_query_data_operations():
    df = pd.DataFrame(
        {
            "name": ["A", "B", "C", "D", "E"],
            "price": [100.0, 150.0, 200.0, 250.0, 300.0],
            "cores": [4, 6, 8, 8, 12],
        }
    )

    handle = store.create({"cpu": df})

    # 1. Sample returns <= limit rows
    report_sample = query_data(handle, "cpu", expr="price < 250", agg="sample", limit=2)
    assert report_sample.row_count == 3  # total matching rows (100, 150, 200)
    assert len(report_sample.rows) == 2  # capped by limit
    assert report_sample.rows[0]["name"] == "A"
    assert report_sample.rows[1]["name"] == "B"
    assert report_sample.stats is None

    # 2. Describe works
    report_desc = query_data(handle, "cpu", expr="price >= 200", agg="describe")
    assert report_desc.stats is not None
    assert "price" in report_desc.stats
    assert report_desc.stats["price"]["count"] == 3.0  # 200, 250, 300
    assert len(report_desc.rows) == 0

    # 3. Value counts works
    report_vc = query_data(handle, "cpu", agg="value_counts", limit=2)
    assert report_vc.stats is not None
    assert "cores" in report_vc.stats
    assert report_vc.stats["cores"][8] == 2
    assert len(report_vc.rows) == 0

    # 4. Hostile expression raises ValueError
    with pytest.raises(ValueError):
        query_data(handle, "cpu", expr="os.system('x')")

    # 5. Stored frame is UNCHANGED after query_data
    stored_df = store.get(handle)["cpu"]
    pd.testing.assert_frame_equal(stored_df, df)
