"""Integration smoke test for the complete MCP Gauss data and solver pipeline."""

import json
from pathlib import Path

import pytest

from app.mcp_server import catalog, cleaning, cpsat, prefilter
from app.mcp_server.server import _json_safe


@pytest.mark.skipif(
    not Path("data/pc-csv/cpu.csv").exists(),
    reason="raw CSV files are absent (expected in local dev clone only)",
)
def test_mcp_pipeline_integration():
    # 1. Load metadata
    metadata = catalog.load_metadata()
    assert "datasets" in metadata
    assert len(metadata["datasets"]) > 0

    # 2. Load data
    load_report = catalog.load_data(
        categories=["cpu", "memory"],
        required_columns={"cpu": ["price"], "memory": ["price"]},
        metadata=metadata,
    )
    handle = load_report.dataset_handle
    assert isinstance(handle, str)
    assert len(handle) > 0

    # 3. Clean systematically
    clean_report = cleaning.clean_systematic(handle, metadata)
    assert handle in clean_report.handle

    # 4. Define pivot schema
    # A $2000 budget is extremely feasible for a CPU + Memory combo
    pivot_schema = {
        "schema_version": "1.0",
        "user_intent": "Build cheapest PC under $2000 budget cap",
        "decision_variables": [
            {
                "category": "cpu",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
            {
                "category": "memory",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
        ],
        "derived_variables": [
            {
                "name": "total_price",
                "formula": "sum(cpu.price, memory.price)",
                "dependencies": ["cpu", "memory"],
            }
        ],
        "objectives": [
            {
                "target_variable": "total_price",
                "direction": "minimize",
            }
        ],
        "constraints": [
            {
                "name": "budget_cap",
                "left_side": "total_price",
                "operator": "<=",
                "right_side": {"kind": "literal", "value": 2000.0},
                "is_hard": True,
                "origin": "user_explicit",
            }
        ],
    }

    # 5. Prefilter
    prefilter_report = prefilter.prefilter(handle, pivot_schema["constraints"])
    assert prefilter_report.handle == handle

    # 6. Solve build
    report = cpsat.solve_build(handle, pivot_schema)

    # 7. Asserts
    assert report.status in ("OPTIMAL", "FEASIBLE")
    assert "cpu" in report.selections
    assert "memory" in report.selections
    assert "price" in report.selections["cpu"]
    assert "price" in report.selections["memory"]
    assert "total_price" in report.derived_values

    # Check json serialization succeeds using the sanitizer
    serialized = json.dumps(_json_safe(report.model_dump()))
    assert isinstance(serialized, str)
    assert len(serialized) > 0
