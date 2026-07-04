import pytest
from pydantic import ValidationError

from app.schema import (
    EvaluationFeedback,
    SolverRequest,
    SolverResponse,
)


def make_valid_pivot_schema_data():
    return {
        "user_intent": "Build a gaming PC under $1500",
        "use_cases": ["gaming_cyberpunk_2077"],
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


def test_solver_response_success_validation():
    # 1. SUCCESS status with ranking
    response_data = {
        "transaction_id": "test-uuid-12345",
        "status": "SUCCESS",
        "result": {
            "selections": {
                "cpu": {"name": "AMD Ryzen 7 7800X3D", "price": 340.05, "tdp": 120},
                "video-card": {
                    "name": "Sapphire PULSE RX 7800 XT",
                    "price": 499.99,
                    "memory": 16,
                },
            },
            "derived_values": {"total_price": 840.04},
            "objective_report": [
                {"target": "total_price", "direction": "minimize", "value": 840.04}
            ],
            "ranking": {
                "method": "topsis",
                "score": 0.87,
                "candidates_ranked": 50,
            },
        },
        "feedback": None,
        "trace": {"solve_ms": 120},
    }

    response = SolverResponse.model_validate(response_data)
    assert response.status == "SUCCESS"
    assert response.result is not None
    assert response.result.ranking is not None
    assert response.result.ranking.score == 0.87
    assert response.result.selections["cpu"]["name"] == "AMD Ryzen 7 7800X3D"

    # 2. SUCCESS status without ranking
    response_data_no_ranking = response_data.copy()
    response_data_no_ranking["result"] = response_data["result"].copy()
    response_data_no_ranking["result"]["ranking"] = None

    response_no_ranking = SolverResponse.model_validate(response_data_no_ranking)
    assert response_no_ranking.result is not None
    assert response_no_ranking.result.ranking is None


def test_solver_response_non_success_validation():
    # 1. INFEASIBLE response with feedback
    infeasible_data = {
        "transaction_id": "test-uuid-12345",
        "status": "INFEASIBLE",
        "result": None,
        "feedback": {
            "reason": "Total price constraint is too tight",
            "missing_attributes": [],
            "failed_constraints": ["budget_cap"],
            "relaxation_suggestions": [
                {
                    "constraint": "budget_cap",
                    "suggestion": "raise right_side to 1450 (cheapest feasible)",
                }
            ],
        },
        "trace": {"solve_ms": 45},
    }
    response = SolverResponse.model_validate(infeasible_data)
    assert response.status == "INFEASIBLE"
    assert response.result is None
    assert response.feedback is not None
    assert response.feedback.failed_constraints == ["budget_cap"]
    assert response.feedback.relaxation_suggestions[0].constraint == "budget_cap"

    # 2. MISSING_DATA response with feedback
    missing_data = {
        "transaction_id": "test-uuid-12345",
        "status": "MISSING_DATA",
        "result": None,
        "feedback": {
            "reason": "Missing required data attribute in video-card category",
            "missing_attributes": [
                {
                    "category": "video-card",
                    "attribute": "noise_db",
                    "referenced_by": ["quiet_gpu_cap"],
                }
            ],
            "failed_constraints": [],
            "relaxation_suggestions": [],
        },
        "trace": {},
    }
    response_missing = SolverResponse.model_validate(missing_data)
    assert response_missing.status == "MISSING_DATA"
    assert response_missing.feedback is not None
    assert len(response_missing.feedback.missing_attributes) == 1
    assert response_missing.feedback.missing_attributes[0].category == "video-card"

    # 3. Invalid status value is rejected
    invalid_data = infeasible_data.copy()
    invalid_data["status"] = (
        "COMPLETED"  # Invalid status (not in SUCCESS, INFEASIBLE, MISSING_DATA, ERROR)
    )
    with pytest.raises(ValidationError):
        SolverResponse.model_validate(invalid_data)


def test_solver_request_validation_and_roundtrip():
    schema_data = make_valid_pivot_schema_data()
    request_data = {
        "transaction_id": "request-uuid-5678",
        "iteration": 2,
        "pivot_schema": schema_data,
        "context": {
            "original_prompt": "I want a build with Ryzen cpu",
            "locale_currency": "USD",
        },
    }

    request = SolverRequest.model_validate(request_data)
    assert request.transaction_id == "request-uuid-5678"
    assert request.iteration == 2
    assert request.context.locale_currency == "USD"
    assert request.pivot_schema.user_intent == "Build a gaming PC under $1500"

    # Roundtrip test
    dumped = request.model_dump()
    re_validated = SolverRequest.model_validate(dumped)
    assert re_validated.transaction_id == request.transaction_id
    assert re_validated.pivot_schema.user_intent == request.pivot_schema.user_intent


def test_evaluation_feedback_validation():
    feedback_data = {
        "passed": False,
        "iteration": 2,
        "scores": {
            "completeness": 0.71,
            "coherence": 1.0,
            "intent_fidelity": 0.5,
        },
        "feedback_details": {
            "target_stages": [1, 4],
            "missing_categories": ["power-supply", "cpu-cooler"],
            "coherence_violations": [],
            "fidelity_violations": [
                {
                    "user_phrase": "as quiet as possible",
                    "problem": "no noise-related objective or constraint",
                    "suggestion": "add minimize objective on a noise-proxy or a kb_ref constraint",
                }
            ],
            "solver_feedback": {
                "reason": "No components found for category motherboard",
                "missing_attributes": [],
                "failed_constraints": [],
                "relaxation_suggestions": [],
            },
        },
    }

    feedback = EvaluationFeedback.model_validate(feedback_data)
    assert feedback.passed is False
    assert feedback.iteration == 2
    assert feedback.scores.completeness == 0.71
    assert feedback.feedback_details.target_stages == [1, 4]
    assert len(feedback.feedback_details.fidelity_violations) == 1
    assert (
        feedback.feedback_details.fidelity_violations[0].user_phrase
        == "as quiet as possible"
    )
    assert feedback.feedback_details.solver_feedback is not None
    assert (
        feedback.feedback_details.solver_feedback.reason
        == "No components found for category motherboard"
    )
