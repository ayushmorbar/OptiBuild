"""Unit tests for the deterministic Evaluator check functions."""

from app.evaluator import check_coherence, evaluate_deterministic
from app.schema import PivotSchema


def make_clean_schema_data():
    return {
        "user_intent": "Build cheapest gaming PC",
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
    assert feedback.feedback_details.target_stages == []


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
