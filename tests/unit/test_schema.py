import pytest
from pydantic import ValidationError

from app.schema import (
    Constraint,
    DerivedVariable,
    LiteralThreshold,
    PivotSchema,
    VarRefThreshold,
)


def make_valid_schema_data():
    return {
        "user_intent": "Build a gaming PC under $1500",
        "decision_variables": [
            {
                "category": "cpu",
                "required_attributes": [
                    {"name": "price", "data_type": "float", "unit": "USD"},
                    {"name": "tdp", "data_type": "int", "unit": "W"},
                ],
                "optional": False,
            },
            {
                "category": "video-card",
                "required_attributes": [
                    {"name": "price", "data_type": "float", "unit": "USD"},
                    {"name": "memory", "data_type": "int", "unit": "GB"},
                ],
                "optional": False,
            },
        ],
        "derived_variables": [
            {
                "name": "total_price",
                "formula": "sum(cpu.price, video-card.price)",
                "dependencies": ["cpu", "video-card"],
            }
        ],
        "objectives": [
            {
                "target_variable": "total_price",
                "direction": "minimize",
                "weight": 1.0,
                "rationale": "Minimize total price.",
            }
        ],
        "constraints": [
            {
                "name": "budget_cap",
                "left_side": "total_price",
                "operator": "<=",
                "right_side": {"kind": "literal", "value": 1500.0},
                "is_hard": True,
                "origin": "user_explicit",
            }
        ],
    }


def test_valid_pivot_schema_roundtrip():
    data = make_valid_schema_data()
    model = PivotSchema.model_validate(data)
    dumped = model.model_dump()
    re_validated = PivotSchema.model_validate(dumped)
    assert re_validated.user_intent == model.user_intent
    assert len(re_validated.decision_variables) == 2
    assert re_validated.schema_version == "1.0"


def test_derived_variable_formula_grammar():
    # Valid formulas
    DerivedVariable(
        name="total_price",
        formula="sum(cpu.price, video-card.price, memory.price)",
        dependencies=["cpu", "video-card", "memory"],
    )
    DerivedVariable(
        name="gpu_memory",
        formula="video-card.memory",
        dependencies=["video-card"],
    )
    DerivedVariable(
        name="cpu_cooler_count",
        formula="count(cpu.price, cooler.price)",
        dependencies=["cpu", "cooler"],
    )

    # Invalid formulas
    # 1. Lambda
    with pytest.raises(ValidationError) as exc_info:
        DerivedVariable(
            name="dv",
            formula="lambda x: x.price",
            dependencies=["cpu"],
        )
    assert "formula" in str(exc_info.value) and "restricted grammar" in str(
        exc_info.value
    )

    # 2. Call like os.system
    with pytest.raises(ValidationError) as exc_info:
        DerivedVariable(
            name="dv",
            formula="os.system('x')",
            dependencies=["cpu"],
        )
    assert "formula" in str(exc_info.value) and "restricted grammar" in str(
        exc_info.value
    )

    # 3. Import-like string
    with pytest.raises(ValidationError) as exc_info:
        DerivedVariable(
            name="dv",
            formula="import os",
            dependencies=["cpu"],
        )
    assert "formula" in str(exc_info.value) and "restricted grammar" in str(
        exc_info.value
    )


def test_dangling_objective_rejected():
    data = make_valid_schema_data()
    data["objectives"][0]["target_variable"] = "nonexistent_variable"
    with pytest.raises(ValidationError) as exc_info:
        PivotSchema.model_validate(data)
    assert "objective targets unknown variable" in str(exc_info.value)


def test_dangling_constraint_var_ref_rejected():
    data = make_valid_schema_data()
    data["constraints"].append(
        {
            "name": "cmp_constraint",
            "left_side": "cpu.price",
            "operator": "<=",
            "right_side": {"kind": "var_ref", "ref": "nonexistent_term"},
            "is_hard": True,
        }
    )
    with pytest.raises(ValidationError) as exc_info:
        PivotSchema.model_validate(data)
    assert "unknown var_ref" in str(exc_info.value)


def test_dangling_constraint_left_side_rejected():
    data = make_valid_schema_data()
    data["constraints"].append(
        {
            "name": "budget_cap_invalid",
            "left_side": "nonexistent_variable",
            "operator": "<=",
            "right_side": {"kind": "literal", "value": 1500.0},
            "is_hard": True,
        }
    )
    with pytest.raises(ValidationError) as exc_info:
        PivotSchema.model_validate(data)
    assert "unknown left_side" in str(exc_info.value)


def test_dangling_derived_variable_dependency_rejected():
    data = make_valid_schema_data()
    data["derived_variables"].append(
        {
            "name": "invalid_dv",
            "formula": "sum(cpu.price, motherboard.price)",
            "dependencies": ["cpu", "motherboard"],
        }
    )
    with pytest.raises(ValidationError) as exc_info:
        PivotSchema.model_validate(data)
    assert "unknown dependency" in str(exc_info.value)


def test_non_unique_constraint_names_rejected():
    data = make_valid_schema_data()
    data["constraints"] = [
        {
            "name": "budget_cap",
            "left_side": "total_price",
            "operator": "<=",
            "right_side": {"kind": "literal", "value": 1500.0},
            "is_hard": True,
        },
        {
            "name": "budget_cap",
            "left_side": "cpu.price",
            "operator": "<=",
            "right_side": {"kind": "literal", "value": 500.0},
            "is_hard": True,
        },
    ]
    with pytest.raises(ValidationError) as exc_info:
        PivotSchema.model_validate(data)
    assert "constraint names must be unique" in str(exc_info.value)


def test_weight_normalization():
    data = make_valid_schema_data()
    data["objectives"] = [
        {
            "target_variable": "total_price",
            "direction": "minimize",
            "weight": 3.0,
            "rationale": "Minimize total price.",
        },
        {
            "target_variable": "cpu.tdp",
            "direction": "minimize",
            "weight": 1.0,
            "rationale": "Minimize CPU heat.",
        },
    ]
    model = PivotSchema.model_validate(data)
    # Total weight is 4.0, so weights should be 0.75 and 0.25
    assert model.objectives[0].weight == 0.75
    assert model.objectives[1].weight == 0.25


def test_invalid_weight_rejected():
    # Weight <= 0 is rejected
    data = make_valid_schema_data()
    data["objectives"][0]["weight"] = 0.0
    with pytest.raises(ValidationError) as exc_info:
        PivotSchema.model_validate(data)
    assert "greater than 0" in str(exc_info.value)

    data["objectives"][0]["weight"] = -0.5
    with pytest.raises(ValidationError) as exc_info:
        PivotSchema.model_validate(data)
    assert "greater than 0" in str(exc_info.value)


def test_constraint_stage_truth_table():
    # 1. single-component + literal + hard -> "prefilter"
    c1 = Constraint(
        name="c1",
        left_side="cpu.price",
        operator="<=",
        right_side=LiteralThreshold(kind="literal", value=300),
        is_hard=True,
    )
    assert c1.stage == "prefilter"

    # 3. single-component + var_ref + hard -> "solver"
    c3 = Constraint(
        name="c3",
        left_side="cpu.price",
        operator="<=",
        right_side=VarRefThreshold(kind="var_ref", ref="video-card.price"),
        is_hard=True,
    )
    assert c3.stage == "solver"

    # 4. derived variable + literal + hard -> "solver"
    c4 = Constraint(
        name="c4",
        left_side="total_price",
        operator="<=",
        right_side=LiteralThreshold(kind="literal", value=1500),
        is_hard=True,
    )
    assert c4.stage == "solver"

    # 5. single-component + literal + soft -> "solver"
    c5 = Constraint(
        name="c5",
        left_side="cpu.price",
        operator="<=",
        right_side=LiteralThreshold(kind="literal", value=300),
        is_hard=False,
    )
    assert c5.stage == "solver"

    # 6. derived variable + literal + soft -> "solver"
    c6 = Constraint(
        name="c6",
        left_side="total_price",
        operator="<=",
        right_side=LiteralThreshold(kind="literal", value=1500),
        is_hard=False,
    )
    assert c6.stage == "solver"
