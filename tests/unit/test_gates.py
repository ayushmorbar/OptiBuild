"""Unit tests for the solver data gates checking functionality."""

from app.schema import LoadReport, PivotSchema
from solver_app.gates import check_gates


def make_test_schema(
    constraints=None,
    objectives=None,
    derived_variables=None,
    decision_variables=None,
):
    if constraints is None:
        constraints = []
    if objectives is None:
        objectives = [
            {
                "target_variable": "cpu.price",
                "direction": "minimize",
            }
        ]
    if derived_variables is None:
        derived_variables = []
    if decision_variables is None:
        decision_variables = [
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
        ]

    return PivotSchema.model_validate(
        {
            "user_intent": "Test intent",
            "decision_variables": decision_variables,
            "derived_variables": derived_variables,
            "objectives": objectives,
            "constraints": constraints,
        }
    )


def test_gates_full_coverage():
    schema = make_test_schema()
    load_report = LoadReport.model_validate(
        {
            "dataset_handle": "handle",
            "coverage": [
                {
                    "category": "cpu",
                    "found_columns": ["price"],
                    "missing_columns": [],
                    "row_count": 5,
                },
                {
                    "category": "memory",
                    "found_columns": ["price"],
                    "missing_columns": [],
                    "row_count": 8,
                },
            ],
        }
    )

    res = check_gates(schema, load_report)
    assert res.proceed is True
    assert len(res.missing_attributes) == 0
    assert len(res.stripped_terms) == 0


def test_gates_missing_descriptive_attribute():
    schema = make_test_schema()
    load_report = LoadReport.model_validate(
        {
            "dataset_handle": "handle",
            "coverage": [
                {
                    "category": "cpu",
                    "found_columns": ["price"],
                    "missing_columns": ["tdp"],
                    "row_count": 5,
                },
                {
                    "category": "memory",
                    "found_columns": ["price"],
                    "missing_columns": [],
                    "row_count": 8,
                },
            ],
        }
    )

    res = check_gates(schema, load_report)
    assert res.proceed is True
    assert len(res.missing_attributes) == 0
    assert res.stripped_terms == ["cpu.tdp"]


def test_gates_missing_referenced_by_constraint():
    # Make cpu optional, and tdp is a required attribute for cpu
    schema = make_test_schema(
        decision_variables=[
            {
                "category": "cpu",
                "required_attributes": [
                    {"name": "price", "data_type": "float"},
                    {"name": "tdp", "data_type": "float"},
                ],
                "optional": True,
            },
            {
                "category": "memory",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
        ],
        constraints=[
            {
                "name": "tdp_limit",
                "left_side": "cpu.tdp",
                "operator": "<=",
                "right_side": {"kind": "literal", "value": 65.0},
                "is_hard": True,
            }
        ],
    )
    load_report = LoadReport.model_validate(
        {
            "dataset_handle": "handle",
            "coverage": [
                {
                    "category": "cpu",
                    "found_columns": ["price"],
                    "missing_columns": ["tdp"],
                    "row_count": 5,
                },
                {
                    "category": "memory",
                    "found_columns": ["price"],
                    "missing_columns": [],
                    "row_count": 8,
                },
            ],
        }
    )

    res = check_gates(schema, load_report)
    assert res.proceed is False
    assert len(res.missing_attributes) == 1
    assert res.missing_attributes[0].category == "cpu"
    assert res.missing_attributes[0].attribute == "tdp"
    assert res.missing_attributes[0].referenced_by == ["tdp_limit"]


def test_gates_missing_referenced_by_objective():
    # Make cpu optional, and tdp is a required attribute for cpu
    schema = make_test_schema(
        decision_variables=[
            {
                "category": "cpu",
                "required_attributes": [
                    {"name": "price", "data_type": "float"},
                    {"name": "tdp", "data_type": "float"},
                ],
                "optional": True,
            },
            {
                "category": "memory",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
        ],
        objectives=[
            {
                "target_variable": "cpu.tdp",
                "direction": "minimize",
            }
        ],
    )
    load_report = LoadReport.model_validate(
        {
            "dataset_handle": "handle",
            "coverage": [
                {
                    "category": "cpu",
                    "found_columns": ["price"],
                    "missing_columns": ["tdp"],
                    "row_count": 5,
                },
                {
                    "category": "memory",
                    "found_columns": ["price"],
                    "missing_columns": [],
                    "row_count": 8,
                },
            ],
        }
    )

    res = check_gates(schema, load_report)
    assert res.proceed is False
    assert len(res.missing_attributes) == 1
    assert res.missing_attributes[0].category == "cpu"
    assert res.missing_attributes[0].attribute == "tdp"
    assert res.missing_attributes[0].referenced_by == ["objective:cpu.tdp"]


def test_gates_missing_poisons_derived_variable():
    # Make cpu/memory optional, tdp required for both
    schema = make_test_schema(
        decision_variables=[
            {
                "category": "cpu",
                "required_attributes": [
                    {"name": "price", "data_type": "float"},
                    {"name": "tdp", "data_type": "float"},
                ],
                "optional": True,
            },
            {
                "category": "memory",
                "required_attributes": [
                    {"name": "price", "data_type": "float"},
                    {"name": "tdp", "data_type": "float"},
                ],
                "optional": True,
            },
        ],
        derived_variables=[
            {
                "name": "total_tdp",
                "formula": "sum(cpu.tdp, memory.tdp)",
                "dependencies": ["cpu", "memory"],
            }
        ],
        objectives=[
            {
                "target_variable": "total_tdp",
                "direction": "minimize",
            }
        ],
    )
    load_report = LoadReport.model_validate(
        {
            "dataset_handle": "handle",
            "coverage": [
                {
                    "category": "cpu",
                    "found_columns": ["price"],
                    "missing_columns": ["tdp"],
                    "row_count": 5,
                },
                {
                    "category": "memory",
                    "found_columns": ["price", "tdp"],
                    "missing_columns": [],
                    "row_count": 8,
                },
            ],
        }
    )

    res = check_gates(schema, load_report)
    assert res.proceed is False
    assert len(res.missing_attributes) == 1
    assert res.missing_attributes[0].category == "cpu"
    assert res.missing_attributes[0].attribute == "tdp"
    assert res.missing_attributes[0].referenced_by == ["objective:total_tdp"]


def test_gates_optional_category_missing():
    schema = make_test_schema(
        decision_variables=[
            {
                "category": "cpu",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
            {
                "category": "psu",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": True,
            },
        ]
    )

    load_report = LoadReport.model_validate(
        {
            "dataset_handle": "handle",
            "coverage": [
                {
                    "category": "cpu",
                    "found_columns": ["price"],
                    "missing_columns": [],
                    "row_count": 5,
                },
                {
                    "category": "psu",
                    "found_columns": [],
                    "missing_columns": ["price"],
                    "row_count": 0,
                },
            ],
        }
    )

    res = check_gates(schema, load_report)
    assert res.proceed is True
    assert len(res.missing_attributes) == 0
    assert "psu.price" in res.stripped_terms


def test_gates_required_category_absent():
    schema = make_test_schema(
        decision_variables=[
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
        ]
    )

    load_report = LoadReport.model_validate(
        {
            "dataset_handle": "handle",
            "coverage": [
                {
                    "category": "cpu",
                    "found_columns": [],
                    "missing_columns": ["price"],
                    "row_count": 0,
                },
                {
                    "category": "memory",
                    "found_columns": ["price"],
                    "missing_columns": [],
                    "row_count": 8,
                },
            ],
        }
    )

    res = check_gates(schema, load_report)
    assert res.proceed is False
    assert len(res.missing_attributes) == 1
    assert res.missing_attributes[0].category == "cpu"
    assert res.missing_attributes[0].attribute == ""
    assert res.missing_attributes[0].referenced_by == ["required_category_absent"]


def test_gates_required_attribute_missing_but_unreferenced():
    schema = make_test_schema(
        decision_variables=[
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
        objectives=[
            {
                "target_variable": "memory.price",
                "direction": "minimize",
            }
        ],
    )

    load_report = LoadReport.model_validate(
        {
            "dataset_handle": "handle",
            "coverage": [
                {
                    "category": "cpu",
                    "found_columns": [],
                    "missing_columns": ["price"],
                    "row_count": 5,
                },
                {
                    "category": "memory",
                    "found_columns": ["price"],
                    "missing_columns": [],
                    "row_count": 8,
                },
            ],
        }
    )

    res = check_gates(schema, load_report)
    assert res.proceed is True
    assert len(res.missing_attributes) == 0
    assert "cpu.price" in res.stripped_terms
