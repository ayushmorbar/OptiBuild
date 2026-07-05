"""Unit tests for the deterministic Evaluator check functions."""

from app.evaluator import check_coherence, evaluate_deterministic
from app.schema import PivotSchema


def make_clean_schema_data():
    return {
        "user_intent": "Build cheapest gaming PC with all required components",
        "decision_variables": [
            {
                "category": "cpu",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
            {
                "category": "motherboard",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
            {
                "category": "memory",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
            {
                "category": "internal-hard-drive",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
            {
                "category": "power-supply",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
            {
                "category": "case",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
            {
                "category": "cpu-cooler",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
            {
                "category": "video-card",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
        ],
        "derived_variables": [
            {
                "name": "total_price",
                "formula": "sum(cpu.price, motherboard.price, memory.price, internal-hard-drive.price, power-supply.price, case.price, cpu-cooler.price, video-card.price)",
                "dependencies": [
                    "cpu",
                    "motherboard",
                    "memory",
                    "internal-hard-drive",
                    "power-supply",
                    "case",
                    "cpu-cooler",
                    "video-card",
                ],
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
                "name": "price_cap",
                "left_side": "total_price",
                "operator": "<=",
                "right_side": {"kind": "literal", "value": 1500.0},
                "is_hard": True,
            }
        ],
    }


def test_evaluator_clean_schema():
    data = make_clean_schema_data()
    schema = PivotSchema.model_validate(data)

    feedback = evaluate_deterministic(schema, iteration=1)

    assert feedback.passed is True
    assert feedback.scores.coherence == 1.0
    assert feedback.scores.completeness == 1.0
    assert feedback.scores.intent_fidelity == 1.0
    assert len(feedback.feedback_details.coherence_violations) == 0
    assert len(feedback.feedback_details.missing_categories) == 0
    assert feedback.feedback_details.target_stages == []


def test_evaluator_completeness_missing_categories():
    # Only cpu and video-card
    data = {
        "user_intent": "Build gaming PC with only cpu and video-card",
        "decision_variables": [
            {
                "category": "cpu",
                "required_attributes": [{"name": "price", "data_type": "float"}],
                "optional": False,
            },
            {
                "category": "video-card",
                "required_attributes": [{"name": "price", "data_type": "float"}],
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
            }
        ],
        "constraints": [],
    }
    schema = PivotSchema.model_validate(data)
    feedback = evaluate_deterministic(schema, iteration=1)

    assert feedback.passed is False
    assert feedback.scores.completeness == 0.25  # 2 present out of 8 required
    assert sorted(feedback.feedback_details.missing_categories) == [
        "case",
        "cpu-cooler",
        "internal-hard-drive",
        "memory",
        "motherboard",
        "power-supply",
    ]
    # Check that stage 1 is in target stages since completeness is less than 0.80
    assert 1 in feedback.feedback_details.target_stages


def test_evaluator_contradictory_bounds():
    data = make_clean_schema_data()
    data["constraints"] = [
        {
            "name": "price_cap_upper",
            "left_side": "total_price",
            "operator": "<=",
            "right_side": {"kind": "literal", "value": 500.0},
            "is_hard": True,
        },
        {
            "name": "price_cap_lower",
            "left_side": "total_price",
            "operator": ">=",
            "right_side": {"kind": "literal", "value": 600.0},
            "is_hard": True,
        },
    ]
    schema = PivotSchema.model_validate(data)

    feedback = evaluate_deterministic(schema, iteration=1)

    assert feedback.passed is False
    assert feedback.scores.coherence < 0.80
    assert len(feedback.feedback_details.coherence_violations) > 0
    assert 3 in feedback.feedback_details.target_stages
    assert 4 in feedback.feedback_details.target_stages


def test_evaluator_contradictory_objectives():
    data = make_clean_schema_data()
    data["objectives"] = [
        {
            "target_variable": "total_price",
            "direction": "minimize",
        },
        {
            "target_variable": "total_price",
            "direction": "maximize",
        },
    ]
    schema = PivotSchema.model_validate(data)

    score, violations = check_coherence(schema)
    assert score == 0.0
    assert any("Contradictory directions on objective" in v for v in violations)


def test_evaluator_low_intent_fidelity():
    data = make_clean_schema_data()
    schema = PivotSchema.model_validate(data)

    feedback = evaluate_deterministic(schema, iteration=1, intent_fidelity=0.5)

    assert feedback.passed is False
    assert feedback.scores.intent_fidelity == 0.5
    assert 3 in feedback.feedback_details.target_stages
    assert 4 in feedback.feedback_details.target_stages
