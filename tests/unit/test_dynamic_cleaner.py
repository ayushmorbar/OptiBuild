"""Tests for the on-the-fly dynamic cleaning path (filter_contains + LLM hook)."""

import pandas as pd

from app.mcp_server import safe_ops
from app.mcp_server.store import store
from solver_app.dynamic_cleaner import CleanOpLite, _op_to_dict


def _cpu_frame():
    return pd.DataFrame(
        {
            "name": [
                "Intel Xeon E3-1220 V6",
                "AMD Ryzen 5 7600",
                "Intel Core i5-13600K",
                "AMD Ryzen 7 7800X3D",
            ],
            "price": [25.0, 199.0, 285.0, 340.0],
        }
    )


def test_filter_contains_keeps_matching_rows():
    handle = store.create({"cpu": _cpu_frame()})
    report = safe_ops.clean_dynamic(
        handle,
        [
            {
                "op": "filter_contains",
                "category": "cpu",
                "column": "name",
                "value": "intel",
            }
        ],
        rationale="user wants an Intel CPU",
    )
    assert report.accepted_ops == 1
    assert report.rejected == []
    names = list(store.get(handle)["cpu"]["name"])
    assert names == [
        "Intel Xeon E3-1220 V6",
        "Intel Core i5-13600K",
    ]  # case-insensitive


def test_filter_contains_negate_excludes():
    handle = store.create({"cpu": _cpu_frame()})
    safe_ops.clean_dynamic(
        handle,
        [
            {
                "op": "filter_contains",
                "category": "cpu",
                "column": "name",
                "value": "Intel",
                "negate": True,
            }
        ],
    )
    assert all("AMD" in n for n in store.get(handle)["cpu"]["name"])


def test_filter_contains_rejects_bad_input():
    handle = store.create({"cpu": _cpu_frame()})
    report = safe_ops.clean_dynamic(
        handle,
        [
            {
                "op": "filter_contains",
                "category": "cpu",
                "column": "ghost",
                "value": "x",
            },
            {
                "op": "filter_contains",
                "category": "cpu",
                "column": "name",
                "value": "  ",
            },
            # value is a literal, never a regex: this matches nothing -> empty -> rejected
            {
                "op": "filter_contains",
                "category": "cpu",
                "column": "name",
                "value": ".*",
            },
        ],
    )
    assert report.accepted_ops == 0
    assert len(report.rejected) == 3


def test_op_to_dict_strips_irrelevant_fields():
    op = CleanOpLite(op="drop_nulls", category="cpu", columns=["price"])
    d = _op_to_dict(op)
    assert d == {"op": "drop_nulls", "category": "cpu", "columns": ["price"]}


def test_pipeline_passes_original_prompt_to_hook():
    from app.schema import PivotSchema, SolverRequest, SolverRequestContext
    from solver_app.pipeline import run_solver_pipeline

    seen = {}

    def stub_hook(handle, schema, original_prompt=""):
        seen["prompt"] = original_prompt

    schema = PivotSchema.model_validate(
        {
            "user_intent": "cheapest cpu",
            "decision_variables": [
                {
                    "category": "cpu",
                    "required_attributes": [{"name": "price", "data_type": "float"}],
                }
            ],
            "objectives": [{"target_variable": "cpu.price", "direction": "minimize"}],
        }
    )
    run_solver_pipeline(
        SolverRequest(
            transaction_id="t",
            pivot_schema=schema,
            context=SolverRequestContext(original_prompt="I want an Intel CPU"),
        ),
        dynamic_clean_hook=stub_hook,
    )
    assert seen["prompt"] == "I want an Intel CPU"
