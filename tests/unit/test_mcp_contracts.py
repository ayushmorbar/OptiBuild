import pytest
from pydantic import TypeAdapter, ValidationError

from app.schema import (
    CleanOp,
    ClipRangeOp,
    DropNullsOp,
    FilterRowsOp,
    LoadReport,
    MapValuesOp,
    SolveReport,
)


def test_clean_op_discriminator_parsing():
    # Helper to parse CleanOp union using TypeAdapter
    adapter = TypeAdapter(CleanOp)

    # 1. filter_rows
    op_filter = adapter.validate_python(
        {"op": "filter_rows", "category": "cpu", "expr": "price < 300"}
    )
    assert isinstance(op_filter, FilterRowsOp)
    assert op_filter.category == "cpu"
    assert op_filter.expr == "price < 300"

    # 2. drop_nulls
    op_drop = adapter.validate_python(
        {"op": "drop_nulls", "category": "memory", "columns": ["price", "speed"]}
    )
    assert isinstance(op_drop, DropNullsOp)
    assert op_drop.category == "memory"
    assert op_drop.columns == ["price", "speed"]

    # 3. map_values
    op_map = adapter.validate_python(
        {
            "op": "map_values",
            "category": "video-card",
            "column": "color",
            "mapping": {"White / Black": "White"},
        }
    )
    assert isinstance(op_map, MapValuesOp)
    assert op_map.column == "color"
    assert op_map.mapping == {"White / Black": "White"}

    # 4. clip_range
    op_clip = adapter.validate_python(
        {"op": "clip_range", "category": "cpu", "column": "tdp", "min": 65, "max": 125}
    )
    assert isinstance(op_clip, ClipRangeOp)
    assert op_clip.min == 65.0
    assert op_clip.max == 125.0

    # 5. Unknown op is rejected
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"op": "unknown_op_type", "category": "cpu", "column": "tdp"}
        )


def test_clean_op_extra_forbid():
    # Any unexpected extra field must raise ValidationError due to extra="forbid"
    with pytest.raises(ValidationError):
        FilterRowsOp(
            op="filter_rows",
            category="cpu",
            expr="price < 300",
            extra_field="not_allowed",  # type: ignore
        )

    with pytest.raises(ValidationError):
        DropNullsOp(
            op="drop_nulls",
            category="memory",
            columns=["price"],
            extra_field="not_allowed",  # type: ignore
        )

    with pytest.raises(ValidationError):
        MapValuesOp(
            op="map_values",
            category="video-card",
            column="color",
            mapping={"A": "B"},
            extra_field="not_allowed",  # type: ignore
        )

    with pytest.raises(ValidationError):
        ClipRangeOp(
            op="clip_range",
            category="cpu",
            column="tdp",
            min=65,
            extra_field="not_allowed",  # type: ignore
        )


def test_clip_range_min_max_combinations():
    # Only min
    op1 = ClipRangeOp(category="cpu", column="tdp", min=65.0)
    assert op1.min == 65.0
    assert op1.max is None

    # Only max
    op2 = ClipRangeOp(category="cpu", column="tdp", max=125.0)
    assert op2.min is None
    assert op2.max == 125.0

    # Neither min nor max
    op3 = ClipRangeOp(category="cpu", column="tdp")
    assert op3.min is None
    assert op3.max is None

    # Both min and max
    op4 = ClipRangeOp(category="cpu", column="tdp", min=35.0, max=105.0)
    assert op4.min == 35.0
    assert op4.max == 105.0


def test_load_report_validation():
    data = {
        "dataset_handle": "handle_xyz_123",
        "coverage": [
            {
                "category": "cpu",
                "found_columns": ["name", "price", "tdp"],
                "missing_columns": [],
                "row_count": 150,
            },
            {
                "category": "motherboard",
                "found_columns": ["name", "price"],
                "missing_columns": ["chipset"],
                "row_count": 80,
            },
        ],
    }

    report = LoadReport.model_validate(data)
    assert report.dataset_handle == "handle_xyz_123"
    assert len(report.coverage) == 2
    assert report.coverage[0].category == "cpu"
    assert report.coverage[1].missing_columns == ["chipset"]


def test_solve_report_validation():
    # SolveReport without ranking
    data_no_ranking = {
        "status": "OPTIMAL",
        "selections": {
            "cpu": {"name": "Intel Core i5-13600K", "price": 299.99},
            "motherboard": {"name": "MSI PRO Z790-A", "price": 219.99},
        },
        "derived_values": {"total_price": 519.98},
        "solve_ms": 150,
    }

    report1 = SolveReport.model_validate(data_no_ranking)
    assert report1.status == "OPTIMAL"
    assert report1.selections["cpu"]["name"] == "Intel Core i5-13600K"
    assert report1.derived_values["total_price"] == 519.98
    assert report1.ranking is None
    assert report1.failed_constraints == []

    # SolveReport with ranking
    data_with_ranking = {
        "status": "FEASIBLE",
        "selections": {
            "cpu": {"name": "AMD Ryzen 5 7600", "price": 199.00},
        },
        "derived_values": {"total_price": 199.00},
        "ranking": {
            "method": "topsis",
            "score": 0.95,
            "candidates_ranked": 10,
        },
        "failed_constraints": ["price_limit"],
        "solve_ms": 80,
    }

    report2 = SolveReport.model_validate(data_with_ranking)
    assert report2.status == "FEASIBLE"
    assert report2.ranking is not None
    assert report2.ranking.method == "topsis"
    assert report2.ranking.score == 0.95
    assert report2.failed_constraints == ["price_limit"]
