"""Unit tests for the staged modelization orchestration pipeline."""

from app.modelization import run_modelization
from app.schema import PivotSchema

# Canned data fixtures
CANNED_DECISION_VARIABLES = [
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

CANNED_DERIVED_VARIABLES = [
    {
        "name": "total_price",
        "formula": "sum(cpu.price, memory.price)",
        "dependencies": ["cpu", "memory"],
    }
]

CANNED_OBJECTIVES = [
    {
        "target_variable": "total_price",
        "direction": "minimize",
        "weight": 1.0,
        "rationale": "Minimize total cost",
    }
]

CANNED_CONSTRAINTS = [
    {
        "name": "budget_cap",
        "left_side": "total_price",
        "operator": "<=",
        "right_side": {"kind": "literal", "value": 1500.0},
        "is_hard": True,
    }
]


def test_modelization_full_run():
    called_stages = []

    def mock_extractor(stage: int, prompt: str) -> list[dict]:
        called_stages.append(stage)
        if stage == 1:
            return CANNED_DECISION_VARIABLES
        elif stage == 2:
            return CANNED_DERIVED_VARIABLES
        elif stage == 3:
            return CANNED_OBJECTIVES
        elif stage == 4:
            return CANNED_CONSTRAINTS
        return []

    schema = run_modelization(
        user_request="Build me a computer under $1500",
        catalog_summary="cpu: price\nmemory: price",
        extractor=mock_extractor,
        prior_schema=None,
        target_stages=None,
    )

    assert called_stages == [1, 2, 3, 4]
    assert isinstance(schema, PivotSchema)
    assert len(schema.decision_variables) == 2
    assert len(schema.derived_variables) == 1
    assert len(schema.objectives) == 1
    assert len(schema.constraints) == 1
    assert schema.constraints[0].name == "budget_cap"


def test_modelization_repair_run():
    prior_schema = PivotSchema.model_validate(
        {
            "user_intent": "Build me a computer under $1500",
            "decision_variables": CANNED_DECISION_VARIABLES,
            "derived_variables": CANNED_DERIVED_VARIABLES,
            "objectives": CANNED_OBJECTIVES,
            "constraints": CANNED_CONSTRAINTS,
        }
    )

    called_stages = []
    new_objectives = [
        {
            "target_variable": "total_price",
            "direction": "minimize",
            "weight": 0.5,
            "rationale": "Maximize savings",
        }
    ]

    def mock_extractor(stage: int, prompt: str) -> list[dict]:
        called_stages.append(stage)
        if stage == 3:
            return new_objectives
        return []

    schema = run_modelization(
        user_request="Build me a computer under $1500",
        catalog_summary="cpu: price\nmemory: price",
        extractor=mock_extractor,
        prior_schema=prior_schema,
        target_stages=[3],
    )

    assert called_stages == [3]
    assert len(schema.decision_variables) == 2
    assert len(schema.derived_variables) == 1
    assert len(schema.constraints) == 1
    assert schema.constraints[0].name == "budget_cap"
    assert len(schema.objectives) == 1
    assert schema.objectives[0].rationale == "Maximize savings"
