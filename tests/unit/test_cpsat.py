"""Unit tests for the CP-SAT solver core and build optimization solver."""

import pandas as pd

from app.mcp_server.cpsat import build_and_solve
from app.schema import PivotSchema


def test_cpsat_solver():
    # Setup data
    cpu_df = pd.DataFrame(
        {
            "name": ["Ryzen 5 7600", "Core i5-13600K"],
            "price": [199.00, 299.00],
        }
    )
    memory_df = pd.DataFrame(
        {
            "name": ["Corsair 16GB", "G.Skill 32GB"],
            "price": [50.00, 100.00],
        }
    )

    frames = {"cpu": cpu_df, "memory": memory_df}

    # 1. Feasible case: minimize total_price = sum(cpu.price, memory.price)
    # Cheapest combo should be Ryzen 5 7600 ($199) + Corsair 16GB ($50) = $249
    schema_dict = {
        "schema_version": "1.0",
        "user_intent": "Build cheapest PC",
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
        "objectives": [{"target_variable": "total_price", "direction": "minimize"}],
        "constraints": [],
    }

    schema = PivotSchema.model_validate(schema_dict)
    report = build_and_solve(frames, schema)

    assert report.status == "OPTIMAL"
    assert "cpu" in report.selections
    assert "memory" in report.selections
    assert report.selections["cpu"]["name"] == "Ryzen 5 7600"
    assert report.selections["memory"]["name"] == "Corsair 16GB"
    assert report.derived_values["total_price"] == 249.00

    # 2. Budget constraint (total_price <= 200) -> INFEASIBLE (cheapest is 249)
    schema_dict_infeasible = schema_dict.copy()
    schema_dict_infeasible["constraints"] = [
        {
            "name": "price_cap",
            "left_side": "total_price",
            "operator": "<=",
            "right_side": {"kind": "literal", "value": 200.0},
            "is_hard": True,
            "origin": "user_explicit",
        }
    ]
    schema_inf = PivotSchema.model_validate(schema_dict_infeasible)
    report_inf = build_and_solve(frames, schema_inf)
    assert report_inf.status == "INFEASIBLE"

    # 3. Required category with 0 rows -> INFEASIBLE with cpu in failed_constraints
    empty_frames = {"cpu": pd.DataFrame(), "memory": memory_df}
    report_empty = build_and_solve(empty_frames, schema)
    assert report_empty.status == "INFEASIBLE"
    assert "cpu" in report_empty.failed_constraints

    # 4. Exactly-one is enforced: test that only one row is selected per category
    assert len(report.selections) == 2
    assert report.selections["cpu"]["price"] == 199.00
    assert report.selections["memory"]["price"] == 50.00


def test_cpsat_solver_capacity_var_ref():
    # Setup data
    cpu_df = pd.DataFrame({"name": ["Ryzen 5 7600"], "price": [199.00], "tdp": [65.0]})
    gpu_df = pd.DataFrame({"name": ["RTX 4070"], "price": [599.00], "tdp": [200.0]})
    psu_df = pd.DataFrame(
        {
            "name": ["PSU 300W", "PSU 400W", "PSU 500W"],
            "price": [40.00, 60.00, 80.00],
            "wattage": [300.0, 400.0, 500.0],
        }
    )

    frames = {"cpu": cpu_df, "gpu": gpu_df, "psu": psu_df}

    schema_dict = {
        "schema_version": "1.0",
        "user_intent": "Build with sufficient PSU headroom",
        "decision_variables": [
            {
                "category": "cpu",
                "required_attributes": [
                    {"name": "price", "data_type": "float"},
                    {"name": "tdp", "data_type": "float"},
                ],
                "optional": False,
            },
            {
                "category": "gpu",
                "required_attributes": [
                    {"name": "price", "data_type": "float"},
                    {"name": "tdp", "data_type": "float"},
                ],
                "optional": False,
            },
            {
                "category": "psu",
                "required_attributes": [
                    {"name": "price", "data_type": "float"},
                    {"name": "wattage", "data_type": "float"},
                ],
                "optional": False,
            },
        ],
        "derived_variables": [
            {
                "name": "total_draw",
                "formula": "sum(cpu.tdp, gpu.tdp)",
                "dependencies": ["cpu", "gpu"],
            },
            {
                "name": "total_price",
                "formula": "sum(cpu.price, gpu.price, psu.price)",
                "dependencies": ["cpu", "gpu", "psu"],
            },
        ],
        "objectives": [{"target_variable": "total_price", "direction": "minimize"}],
        "constraints": [
            {
                "name": "psu_headroom",
                "left_side": "psu.wattage",
                "operator": ">=",
                "right_side": {"kind": "var_ref", "ref": "total_draw"},
                "coefficient": 1.3,
                "is_hard": True,
                "origin": "user_explicit",
            }
        ],
    }

    schema = PivotSchema.model_validate(schema_dict)
    report = build_and_solve(frames, schema)

    assert report.status == "OPTIMAL"
    assert report.selections["psu"]["name"] == "PSU 400W"


def test_cpsat_solver_literal_coefficient():
    cpu_df = pd.DataFrame({"name": ["Ryzen 5 7600"], "price": [199.00]})
    memory_df = pd.DataFrame({"name": ["Corsair 16GB"], "price": [50.00]})

    frames = {"cpu": cpu_df, "memory": memory_df}

    schema_dict = {
        "schema_version": "1.0",
        "user_intent": "Build cheapest PC",
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
        "objectives": [{"target_variable": "total_price", "direction": "minimize"}],
        "constraints": [
            {
                "name": "price_cap",
                "left_side": "total_price",
                "operator": "<=",
                "right_side": {"kind": "literal", "value": 100.0},
                "coefficient": 1.5,
                "is_hard": True,
                "origin": "user_explicit",
            }
        ],
    }

    schema = PivotSchema.model_validate(schema_dict)
    report = build_and_solve(frames, schema)
    assert report.status == "INFEASIBLE"

    schema_dict["constraints"][0]["coefficient"] = 2.5
    schema_opt = PivotSchema.model_validate(schema_dict)
    report_opt = build_and_solve(frames, schema_opt)
    assert report_opt.status == "OPTIMAL"


def test_cpsat_solver_multi_objective():
    # Setup data
    cpu_df = pd.DataFrame(
        {
            "name": ["Ryzen 5 7600", "Core i5-13600K"],
            "price": [199.00, 299.00],
            "perf": [100.0, 150.0],
        }
    )
    memory_df = pd.DataFrame(
        {
            "name": ["Corsair 16GB", "G.Skill 32GB"],
            "price": [50.00, 100.00],
            "perf": [80.0, 120.0],
        }
    )

    frames = {"cpu": cpu_df, "memory": memory_df}

    schema_dict = {
        "schema_version": "1.0",
        "user_intent": "Optimize for performance and price",
        "decision_variables": [
            {
                "category": "cpu",
                "required_attributes": [
                    {"name": "price", "data_type": "float"},
                    {"name": "perf", "data_type": "float"},
                ],
                "optional": False,
            },
            {
                "category": "memory",
                "required_attributes": [
                    {"name": "price", "data_type": "float"},
                    {"name": "perf", "data_type": "float"},
                ],
                "optional": False,
            },
        ],
        "derived_variables": [
            {
                "name": "total_price",
                "formula": "sum(cpu.price, memory.price)",
                "dependencies": ["cpu", "memory"],
            },
            {
                "name": "total_perf",
                "formula": "sum(cpu.perf, memory.perf)",
                "dependencies": ["cpu", "memory"],
            },
        ],
        "objectives": [
            {
                "target_variable": "total_price",
                "direction": "minimize",
                "weight": 0.9,
                "rationale": "Focus heavily on price",
            },
            {
                "target_variable": "total_perf",
                "direction": "maximize",
                "weight": 0.1,
                "rationale": "Focus weakly on performance",
            },
        ],
        "constraints": [],
    }

    # 1. Price is heavily weighted (0.9 vs 0.1) -> selects Ryzen 5 7600 + Corsair 16GB
    schema = PivotSchema.model_validate(schema_dict)
    report = build_and_solve(frames, schema)

    assert report.status == "FEASIBLE"
    assert report.ranking is not None
    assert report.ranking.method == "topsis"
    assert report.selections["cpu"]["name"] == "Ryzen 5 7600"
    assert report.selections["memory"]["name"] == "Corsair 16GB"

    # 2. Shifting weights flips the build: performance heavily weighted (0.1 price vs 0.9 performance)
    schema_dict_perf = schema_dict.copy()
    schema_dict_perf["objectives"] = [
        {
            "target_variable": "total_price",
            "direction": "minimize",
            "weight": 0.1,
            "rationale": "Focus weakly on price",
        },
        {
            "target_variable": "total_perf",
            "direction": "maximize",
            "weight": 0.9,
            "rationale": "Focus heavily on performance",
        },
    ]

    schema_perf = PivotSchema.model_validate(schema_dict_perf)
    report_perf = build_and_solve(frames, schema_perf)

    assert report_perf.status == "FEASIBLE"
    assert report_perf.selections["cpu"]["name"] == "Core i5-13600K"
    assert report_perf.selections["memory"]["name"] == "G.Skill 32GB"
