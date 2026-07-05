"""Domain-agnosticism proof: the full deterministic pipeline on a non-PC pack.

Runs the same engine (load -> gates -> cleaning -> prefilter -> CP-SAT) against
the meal-plan toy pack (tests/fixtures/toy-pack), whose cost column is named
'cost' (not 'price'). Zero LLM calls, zero PC vocabulary.
"""

from pathlib import Path

import pytest

from app.evaluator import evaluate_deterministic
from app.mcp_server import catalog
from app.schema import (
    PivotSchema,
    SolverRequest,
    SolverRequestContext,
)
from solver_app.pipeline import run_solver_pipeline

TOY_PACK = Path(__file__).resolve().parents[1] / "fixtures" / "toy-pack"


@pytest.fixture(autouse=True)
def use_toy_pack(monkeypatch):
    monkeypatch.setenv("GAUSS_DATA_DIR", str(TOY_PACK))


def make_meal_schema(protein_key: str = "protein") -> PivotSchema:
    return PivotSchema.model_validate(
        {
            "user_intent": "cheapest full meal under budget",
            "decision_variables": [
                {
                    "category": protein_key,
                    "required_attributes": [
                        {"name": "cost", "data_type": "float"},
                        {"name": "calories", "data_type": "int"},
                    ],
                },
                {
                    "category": "side",
                    "required_attributes": [
                        {"name": "cost", "data_type": "float"},
                    ],
                },
            ],
            "derived_variables": [
                {
                    "name": "total_cost",
                    "formula": f"sum({protein_key}.cost, side.cost)",
                    "dependencies": [protein_key, "side"],
                }
            ],
            "objectives": [{"target_variable": "total_cost", "direction": "minimize"}],
            "constraints": [
                {
                    "name": "budget_cap",
                    "left_side": "total_cost",
                    "operator": "<=",
                    "right_side": {"kind": "literal", "value": 10.0},
                }
            ],
        }
    )


def _request(schema: PivotSchema) -> SolverRequest:
    return SolverRequest(
        transaction_id="toy-1",
        pivot_schema=schema,
        context=SolverRequestContext(original_prompt="cheapest full meal under $10"),
    )


def test_toy_pack_end_to_end_success():
    response = run_solver_pipeline(_request(make_meal_schema()))

    assert response.status == "SUCCESS"
    assert set(response.result.selections.keys()) == {"protein", "side"}
    # Cheapest combination: lentil patty (2.10) + steamed rice (1.20)
    assert response.result.derived_values["total_cost"] == pytest.approx(3.30)


def test_toy_pack_category_resolution_via_synonym():
    # The user-facing modelization said "main-dish"; the pack's category is "protein"
    schema = make_meal_schema(protein_key="main-dish")
    response = run_solver_pipeline(_request(schema))

    assert response.status == "SUCCESS"
    assert response.trace["category_resolution"] == {"main-dish": "protein"}
    assert "protein" in response.result.selections


def test_toy_pack_metadata_driven_completeness():
    metadata = catalog.load_metadata()
    required = metadata.get("required_categories")
    assert required == ["protein", "side"]

    # Full schema satisfies the toy pack's required set
    feedback = evaluate_deterministic(
        make_meal_schema(), iteration=1, required_categories=required
    )
    assert feedback.scores.completeness == 1.0
    assert feedback.passed is True

    # A protein-only schema misses 'side'
    partial = PivotSchema.model_validate(
        {
            "user_intent": "just a protein",
            "decision_variables": [
                {
                    "category": "protein",
                    "required_attributes": [{"name": "cost", "data_type": "float"}],
                }
            ],
            "objectives": [
                {"target_variable": "protein.cost", "direction": "minimize"}
            ],
        }
    )
    feedback = evaluate_deterministic(
        partial, iteration=1, required_categories=required
    )
    assert feedback.scores.completeness == 0.5
    assert feedback.feedback_details.missing_categories == ["side"]
    assert feedback.passed is False


def test_toy_pack_infeasible_budget():
    schema = make_meal_schema()
    schema.constraints[0].right_side.value = 1.0  # impossible budget
    response = run_solver_pipeline(_request(schema))

    assert response.status == "INFEASIBLE"
    assert response.feedback is not None


def test_toy_pack_direct_attribute_objective_reported():
    """objective_report must carry real values for direct 'category.attribute' targets."""
    schema = PivotSchema.model_validate(
        {
            "user_intent": "cheapest protein",
            "decision_variables": [
                {
                    "category": "protein",
                    "required_attributes": [{"name": "cost", "data_type": "float"}],
                },
                {
                    "category": "side",
                    "required_attributes": [{"name": "cost", "data_type": "float"}],
                },
            ],
            "objectives": [
                {"target_variable": "protein.cost", "direction": "minimize"}
            ],
        }
    )
    response = run_solver_pipeline(_request(schema))

    assert response.status == "SUCCESS"
    item = response.result.objective_report[0]
    assert item.target == "protein.cost"
    # Cheapest protein: lentil patty at 2.10 — value must not be the old 0.0 default
    assert item.value == pytest.approx(2.10)
    assert item.value == pytest.approx(response.result.selections["protein"]["cost"])
