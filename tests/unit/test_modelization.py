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


def test_lite_to_strict_validation():
    from app.extraction_schemas import ConstraintLite, ObjectiveLite, ThresholdLite
    from app.schema import Constraint, Objective

    # 1. Test ObjectiveLite -> strict Objective
    obj_lite = ObjectiveLite(
        target_variable="total_price",
        direction="minimize",
        weight=1.5,
        rationale="Save money",
    )
    obj_strict = Objective.model_validate(obj_lite.model_dump())
    assert obj_strict.target_variable == "total_price"
    assert obj_strict.weight == 1.5

    # 2. Test ConstraintLite -> strict Constraint (with ThresholdLite -> Threshold union)
    thresh_lite = ThresholdLite(kind="literal", value=1500.0)
    const_lite = ConstraintLite(
        name="budget_cap",
        left_side="total_price",
        operator="<=",
        right_side=thresh_lite,
        is_hard=True,
    )
    const_strict = Constraint.model_validate(const_lite.model_dump())
    assert const_strict.name == "budget_cap"
    assert const_strict.right_side.kind == "literal"
    assert const_strict.right_side.value == 1500.0


def test_modelization_extractor_skips_invalid_keeps_valid():
    # Setup extractor to return one invalid dict (missing name, pattern error) and one valid dict for stage 4
    valid_constraint = {
        "name": "budget_cap",
        "left_side": "total_price",
        "operator": "<=",
        "right_side": {"kind": "literal", "value": 1500.0},
        "is_hard": True,
    }
    invalid_constraint = {
        "name": "INVALID CAP WITH SPACES AND PATTERN ERROR",
        "left_side": "total_price",
        "operator": "<=",
        "right_side": {"kind": "literal", "value": 1500.0},
        "is_hard": True,
    }

    def mock_extractor(stage: int, prompt: str) -> list[dict]:
        if stage == 1:
            return CANNED_DECISION_VARIABLES
        elif stage == 2:
            return CANNED_DERIVED_VARIABLES
        elif stage == 3:
            return CANNED_OBJECTIVES
        elif stage == 4:
            return [invalid_constraint, valid_constraint]
        return []

    schema = run_modelization(
        user_request="Build PC",
        catalog_summary="cpu: price",
        extractor=mock_extractor,
    )

    # Validate that invalid was skipped, valid kept, no crash
    assert len(schema.constraints) == 1
    assert schema.constraints[0].name == "budget_cap"


def test_synonym_normalization():
    # Stage 1: data_type "string" -> "str"
    # Stage 3: direction "min" -> "minimize"
    def mock_extractor(stage: int, prompt: str) -> list[dict]:
        if stage == 1:
            return [
                {
                    "category": "cpu",
                    "required_attributes": [{"name": "price", "data_type": "string"}],
                    "optional": False,
                },
                {
                    "category": "memory",
                    "required_attributes": [{"name": "price", "data_type": "string"}],
                    "optional": False,
                },
            ]
        elif stage == 2:
            return CANNED_DERIVED_VARIABLES
        elif stage == 3:
            return [
                {
                    "target_variable": "total_price",
                    "direction": "min",
                    "weight": 1.0,
                    "rationale": "Minimize cost",
                }
            ]
        elif stage == 4:
            return CANNED_CONSTRAINTS
        return []

    schema = run_modelization(
        user_request="Build PC",
        catalog_summary="cpu: price\nmemory: price",
        extractor=mock_extractor,
    )

    assert len(schema.decision_variables) == 2
    assert schema.decision_variables[0].required_attributes[0].data_type == "str"
    assert schema.decision_variables[1].required_attributes[0].data_type == "str"
    assert len(schema.objectives) == 1
    assert schema.objectives[0].direction == "minimize"
