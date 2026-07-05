"""Unit tests for the Concierge optimizer loop orchestration."""

from app.concierge import run_concierge
from app.schema import FidelityViolation, PivotSchema, SolverFeedback, SolverResponse

# Canned submodel structures
CANNED_DECISION_VARIABLES = [
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
]

CANNED_DERIVED_VARIABLES = [
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


def test_concierge_first_try_success():
    # Setup mocks
    def mock_extractor(stage: int, prompt: str) -> list[dict]:
        if stage == 1:
            return CANNED_DECISION_VARIABLES
        elif stage == 2:
            return CANNED_DERIVED_VARIABLES
        elif stage == 3:
            return CANNED_OBJECTIVES
        elif stage == 4:
            return CANNED_CONSTRAINTS
        return []

    judge_called = []

    def mock_judge(
        user_request: str, schema: PivotSchema
    ) -> tuple[float, list[FidelityViolation]]:
        judge_called.append(schema)
        return 1.0, []

    def mock_solver_client(request) -> SolverResponse:
        return SolverResponse(
            transaction_id=request.transaction_id,
            status="SUCCESS",
            result={
                "selections": {"cpu": {}, "memory": {}},
                "derived_values": {"total_price": 500.0},
            },
        )

    res = run_concierge(
        user_request="Build PC",
        catalog_summary="cpu: price\nmemory: price",
        extractor=mock_extractor,
        judge=mock_judge,
        solver_client=mock_solver_client,
    )

    assert res["status"] == "SUCCESS"
    assert res["iterations"] == 1
    assert len(judge_called) == 1


def test_concierge_coherence_fail_then_fixed():
    first_try = True
    extractor_calls = []

    judge_called = []

    def mock_judge(
        user_request: str, schema: PivotSchema
    ) -> tuple[float, list[FidelityViolation]]:
        judge_called.append(schema)
        return 1.0, []

    def mock_solver_client(request) -> SolverResponse:
        return SolverResponse(
            transaction_id=request.transaction_id,
            status="SUCCESS",
            result={
                "selections": {"cpu": {}, "memory": {}},
                "derived_values": {"total_price": 500.0},
            },
        )

    def mock_extractor_dynamic(stage: int, prompt: str) -> list[dict]:
        nonlocal first_try
        extractor_calls.append(stage)
        if stage == 1:
            return CANNED_DECISION_VARIABLES
        elif stage == 2:
            return CANNED_DERIVED_VARIABLES
        elif stage == 3:
            return CANNED_OBJECTIVES
        elif stage == 4:
            if first_try:
                first_try = False
                return [
                    {
                        "name": "cap1",
                        "left_side": "total_price",
                        "operator": "<=",
                        "right_side": {"kind": "literal", "value": 500.0},
                        "is_hard": True,
                    },
                    {
                        "name": "cap2",
                        "left_side": "total_price",
                        "operator": ">=",
                        "right_side": {"kind": "literal", "value": 600.0},
                        "is_hard": True,
                    },
                ]
            else:
                return CANNED_CONSTRAINTS
        return []

    res = run_concierge(
        user_request="Build PC",
        catalog_summary="cpu: price\nmemory: price",
        extractor=mock_extractor_dynamic,
        judge=mock_judge,
        solver_client=mock_solver_client,
    )

    assert res["status"] == "SUCCESS"
    assert res["iterations"] == 2
    # The judge is NOT called on first iteration because coherence failed (0.0 < 0.80)
    # The judge is called on second iteration when coherence passes
    assert len(judge_called) == 1


def test_concierge_solver_infeasible_exhausted():
    def mock_extractor(stage: int, prompt: str) -> list[dict]:
        if stage == 1:
            return CANNED_DECISION_VARIABLES
        elif stage == 2:
            return CANNED_DERIVED_VARIABLES
        elif stage == 3:
            return CANNED_OBJECTIVES
        elif stage == 4:
            return CANNED_CONSTRAINTS
        return []

    def mock_judge(
        user_request: str, schema: PivotSchema
    ) -> tuple[float, list[FidelityViolation]]:
        return 1.0, []

    def mock_solver_client(request) -> SolverResponse:
        return SolverResponse(
            transaction_id=request.transaction_id,
            status="INFEASIBLE",
            feedback=SolverFeedback(
                reason="Budget too low",
                missing_attributes=[],
                failed_constraints=[],
                relaxation_suggestions=[],
            ),
        )

    res = run_concierge(
        user_request="Build PC",
        catalog_summary="cpu: price\nmemory: price",
        extractor=mock_extractor,
        judge=mock_judge,
        solver_client=mock_solver_client,
        max_iterations=3,
    )

    assert res["status"] == "NEEDS_CLARIFICATION"
    assert res["iterations"] == 3
    assert res["questions"] == ["Budget too low"]


def test_concierge_robust_modelization_failure():
    def mock_extractor(stage: int, prompt: str) -> list[dict]:
        return []

    def mock_judge(
        user_request: str, schema: PivotSchema
    ) -> tuple[float, list[FidelityViolation]]:
        return 1.0, []

    def mock_solver_client(request) -> SolverResponse:
        return SolverResponse(
            transaction_id=request.transaction_id,
            status="SUCCESS",
            result={
                "selections": {},
                "derived_values": {},
            },
        )

    res = run_concierge(
        user_request="Build PC",
        catalog_summary="cpu: price",
        extractor=mock_extractor,
        judge=mock_judge,
        solver_client=mock_solver_client,
        max_iterations=2,
    )

    assert res["status"] == "NEEDS_CLARIFICATION"
    assert res["iterations"] == 2
    assert any(
        "validation error" in q.lower()
        or "at least 1 item" in q.lower()
        or "value" in q.lower()
        for q in res["questions"]
    )
