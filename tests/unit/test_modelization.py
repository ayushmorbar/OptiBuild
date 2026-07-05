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


def test_build_schema_oneshot():
    from app.modelization import build_schema_oneshot

    canned_full_schema = {
        "user_intent": "Build me a computer under $1500",
        "decision_variables": CANNED_DECISION_VARIABLES,
        "derived_variables": CANNED_DERIVED_VARIABLES,
        "objectives": CANNED_OBJECTIVES,
        "constraints": CANNED_CONSTRAINTS,
    }

    def mock_oneshot_extractor(prompt: str) -> dict:
        return canned_full_schema

    schema = build_schema_oneshot(
        user_request="Build me a computer under $1500",
        catalog_summary="cpu: price\nmemory: price",
        oneshot_extractor=mock_oneshot_extractor,
    )

    assert isinstance(schema, PivotSchema)
    assert len(schema.decision_variables) == 2
    assert len(schema.derived_variables) == 1
    assert len(schema.objectives) == 1
    assert len(schema.constraints) == 1
    assert schema.constraints[0].name == "budget_cap"


def test_build_schema_oneshot_skips_invalid():
    from app.modelization import build_schema_oneshot

    canned_full_schema = {
        "user_intent": "Build me a computer under $1500",
        "decision_variables": CANNED_DECISION_VARIABLES,
        "derived_variables": CANNED_DERIVED_VARIABLES,
        "objectives": CANNED_OBJECTIVES,
        "constraints": [
            {
                "name": "INVALID CAP NAME WITH SPACES",
                "left_side": "total_price",
                "operator": "<=",
                "right_side": {"kind": "literal", "value": 1500.0},
                "is_hard": True,
            },
            CANNED_CONSTRAINTS[0],
        ],
    }

    def mock_oneshot_extractor(prompt: str) -> dict:
        return canned_full_schema

    schema = build_schema_oneshot(
        user_request="Build me a computer under $1500",
        catalog_summary="cpu: price\nmemory: price",
        oneshot_extractor=mock_oneshot_extractor,
    )

    assert len(schema.constraints) == 1
    assert schema.constraints[0].name == "budget_cap"


def test_oneshot_repairs_dangling_references():
    """Reproduces the live failure: derived var dropped (off-grammar formula)
    while an objective still targets it -> must repair, not crash."""
    from app.modelization import build_schema_oneshot

    canned = {
        "user_intent": "cheap PC",
        "decision_variables": CANNED_DECISION_VARIABLES,
        "derived_variables": [
            {
                # 'a + b' form is off-grammar but normalizable -> sum(...)
                "name": "total_price",
                "formula": "cpu.price + memory.price",
                "dependencies": ["cpu", "memory"],
            }
        ],
        "objectives": [
            {"target_variable": "total_price", "direction": "minimize"},
            # References a declared category but an undeclared attribute:
            # must be auto-declared on the decision variable, not crash
            {"target_variable": "memory.capacity", "direction": "maximize"},
            # References nothing known at all: must be dropped
            {"target_variable": "ghost_var", "direction": "maximize"},
        ],
        "constraints": [
            {
                "name": "ghost_cap",
                "left_side": "ghost_var",
                "operator": "<=",
                "right_side": {"kind": "literal", "value": 10},
            }
        ],
    }

    schema = build_schema_oneshot("cheap PC", "cpu: price", lambda p: canned)

    # Formula normalized into the grammar
    assert schema.derived_variables[0].formula == "sum(cpu.price, memory.price)"
    # Auto-declared attribute
    mem = next(d for d in schema.decision_variables if d.category == "memory")
    assert any(a.name == "capacity" for a in mem.required_attributes)
    # ghost objective and constraint dropped, valid ones kept
    targets = {o.target_variable for o in schema.objectives}
    assert targets == {"total_price", "memory.capacity"}
    assert schema.constraints == []


def test_oneshot_no_valid_objective_raises_clear_error():
    import pytest

    from app.modelization import build_schema_oneshot

    canned = {
        "user_intent": "x",
        "decision_variables": CANNED_DECISION_VARIABLES,
        "derived_variables": [],
        "objectives": [{"target_variable": "ghost_var", "direction": "minimize"}],
        "constraints": [],
    }

    with pytest.raises(ValueError, match="no valid objective"):
        build_schema_oneshot("x", "cpu: price", lambda p: canned)


def test_oneshot_repairs_live_llm_output_shape():
    """Exact shape observed live: dotted dependencies + snake_case objective."""
    from app.modelization import build_schema_oneshot

    canned = {
        "user_intent": "cheap PC build, minimize total price, maximize memory",
        "decision_variables": [
            {
                "category": c,
                "required_attributes": [{"name": "price", "data_type": "float"}],
            }
            for c in [
                "cpu",
                "motherboard",
                "memory",
                "power-supply",
                "case",
                "internal-hard-drive",
            ]
        ],
        "derived_variables": [
            {
                "name": "total_price",
                "formula": "sum(cpu.price, motherboard.price, memory.price, power-supply.price, case.price, internal-hard-drive.price)",
                # LLM emitted dotted terms instead of category keys:
                "dependencies": [
                    "cpu.price",
                    "motherboard.price",
                    "memory.price",
                    "power-supply.price",
                    "case.price",
                    "internal-hard-drive.price",
                ],
            }
        ],
        "objectives": [
            {"target_variable": "total_price", "direction": "minimize"},
            # LLM emitted snake_case instead of a dotted term:
            {"target_variable": "memory_capacity", "direction": "maximize"},
        ],
        "constraints": [
            {
                "name": "budget_cap",
                "left_side": "total_price",
                "operator": "<=",
                "right_side": {"kind": "literal", "value": 1500},
            }
        ],
    }

    schema = build_schema_oneshot("cheap PC build", "catalog", lambda p: canned)

    # Dotted dependencies normalized to category keys
    assert schema.derived_variables[0].dependencies == [
        "cpu",
        "motherboard",
        "memory",
        "power-supply",
        "case",
        "internal-hard-drive",
    ]
    # snake_case objective resolved to a dotted term + attribute auto-declared
    targets = {o.target_variable for o in schema.objectives}
    assert targets == {"total_price", "memory.capacity"}
    mem = next(d for d in schema.decision_variables if d.category == "memory")
    assert any(a.name == "capacity" for a in mem.required_attributes)
    assert schema.constraints[0].name == "budget_cap"


def test_constraint_origin_synonyms_normalized():
    """LLMs improvise origin values ('user_request'...) — must normalize, not drop."""
    from app.modelization import normalize_raw_dict
    from app.schema import Constraint

    for raw_origin, expected in [
        ("user_request", "user_explicit"),
        ("USER", "user_explicit"),
        ("knowledge_base", "kb_derived"),
        ("compat", "compatibility"),
        ("default", "system_default"),
        ("something_weird", "user_explicit"),  # unknown -> safe default
        ("compatibility", "compatibility"),  # valid values untouched
    ]:
        d = {
            "name": "budget_limit",
            "left_side": "total_price",
            "operator": "<=",
            "right_side": {"kind": "literal", "value": 1500},
            "origin": raw_origin,
        }
        norm = normalize_raw_dict(4, d)
        assert norm["origin"] == expected
        # And the normalized dict validates into a strict Constraint
        # (needs a known left_side only at PivotSchema level, not here)
        assert Constraint.model_validate(norm).origin == expected
