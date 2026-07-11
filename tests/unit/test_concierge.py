"""Unit tests for the Concierge optimizer loop orchestration."""

from app.concierge import (
    make_oneshot_modelizer,
    make_staged_modelizer,
    run_concierge,
)
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
        modelize=make_staged_modelizer(
            "Build PC", "cpu: price\nmemory: price", mock_extractor
        ),
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
        modelize=make_staged_modelizer(
            "Build PC", "cpu: price\nmemory: price", mock_extractor_dynamic
        ),
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
        modelize=make_staged_modelizer(
            "Build PC", "cpu: price\nmemory: price", mock_extractor
        ),
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
        modelize=make_staged_modelizer("Build PC", "cpu: price", mock_extractor),
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
        or "no valid objective" in q.lower()  # _assemble_schema clear error
        for q in res["questions"]
    )


# Fast config = the SAME loop parametrized: one-shot modelizer, judge=None,
# max_iterations=1 (what concierge_runner.run selects for GAUSS_FAST_MODELIZATION=1).

CANNED_ONESHOT = {
    "user_intent": "cheap pc",
    "decision_variables": [
        {
            "category": "cpu",
            "required_attributes": [{"name": "price", "data_type": "float"}],
        },
    ],
    "derived_variables": [],
    "objectives": [{"target_variable": "cpu.price", "direction": "minimize"}],
    "constraints": [],
}


def test_fast_config_oneshot_success():
    def fake_solver(req):
        return SolverResponse(
            transaction_id=req.transaction_id,
            status="SUCCESS",
            result={"selections": {"cpu": {"name": "X", "price": 10.0}}},
        )

    res = run_concierge(
        user_request="cheap pc",
        modelize=make_oneshot_modelizer("cheap pc", "- cpu: price", lambda p: CANNED_ONESHOT),
        solver_client=fake_solver,
        judge=None,
        max_iterations=1,
    )

    assert res["status"] == "SUCCESS"
    assert res["iterations"] == 1
    assert res["solver_response"].result.selections["cpu"]["name"] == "X"


def test_fast_config_eval_failure_names_missing_categories():
    def fake_solver(req):
        raise AssertionError("solver must not be reached")

    res = run_concierge(
        user_request="cheap pc",
        modelize=make_oneshot_modelizer("cheap pc", "- cpu: price", lambda p: CANNED_ONESHOT),
        solver_client=fake_solver,
        judge=None,
        max_iterations=1,
        required_categories=["cpu", "motherboard"],
    )

    assert res["status"] == "NEEDS_CLARIFICATION"
    assert res["iterations"] == 1
    assert res["schema"] is not None
    assert any("motherboard" in q for q in res["questions"])
    assert "solver_response" not in res


def test_fast_config_solver_failure_attaches_response():
    def fake_solver(req):
        return SolverResponse(
            transaction_id=req.transaction_id,
            status="INFEASIBLE",
            feedback=SolverFeedback(
                reason="Budget too low",
                missing_attributes=[],
                failed_constraints=[],
                relaxation_suggestions=[],
            ),
        )

    res = run_concierge(
        user_request="cheap pc",
        modelize=make_oneshot_modelizer("cheap pc", "- cpu: price", lambda p: CANNED_ONESHOT),
        solver_client=fake_solver,
        judge=None,
        max_iterations=1,
    )

    assert res["status"] == "NEEDS_CLARIFICATION"
    assert res["iterations"] == 1
    assert res["questions"] == ["Budget too low"]
    assert res["solver_response"].status == "INFEASIBLE"


def test_fast_config_modelization_error():
    def fake_solver(req):
        raise AssertionError("solver must not be reached")

    res = run_concierge(
        user_request="cheap pc",
        modelize=make_oneshot_modelizer("cheap pc", "- cpu: price", lambda p: {}),
        solver_client=fake_solver,
        judge=None,
        max_iterations=1,
    )

    assert res["status"] == "NEEDS_CLARIFICATION"
    assert res["iterations"] == 1
    assert res["schema"] is None
    assert any("no valid objective" in q for q in res["questions"])


def test_run_dispatch_fast_mode(monkeypatch):
    """GAUSS_FAST_MODELIZATION=1 selects (oneshot modelize, judge=None, 1 iteration)."""
    from unittest.mock import patch

    import app.concierge_runner as runner

    monkeypatch.setenv("GAUSS_FAST_MODELIZATION", "1")
    captured = {}

    def fake_run_concierge(**kwargs):
        captured.update(kwargs)
        return {"status": "SUCCESS", "iterations": 1}

    with (
        patch("app.concierge.run_concierge", side_effect=fake_run_concierge),
        patch("app.llm_extractor.make_oneshot_extractor", return_value=lambda p: {}),
        patch("app.mcp_server.catalog.load_metadata", return_value={"datasets": []}),
        patch("app.mcp_server.catalog.build_catalog_summary", return_value=""),
        patch("app.mcp_server.catalog.get_domain_context", return_value=None),
    ):
        res = runner.run("cheap pc", safety_checker=lambda r: (True, None))

    assert res == {"status": "SUCCESS", "iterations": 1}
    assert captured["judge"] is None
    assert captured["max_iterations"] == 1
    assert callable(captured["modelize"])
    assert captured["user_request"] == "cheap pc"


def test_run_dispatch_default_mode(monkeypatch):
    """Default mode selects (staged modelize, LLM judge, 3 iterations)."""
    from unittest.mock import patch

    import app.concierge_runner as runner

    monkeypatch.delenv("GAUSS_FAST_MODELIZATION", raising=False)
    captured = {}

    def fake_run_concierge(**kwargs):
        captured.update(kwargs)
        return {"status": "SUCCESS", "iterations": 1}

    def sentinel_judge(user_request, schema):
        return 1.0, []

    with (
        patch("app.concierge.run_concierge", side_effect=fake_run_concierge),
        patch("app.llm_extractor.make_llm_extractor", return_value=lambda s, p: []),
        patch("app.llm_judge.make_llm_judge", return_value=sentinel_judge),
        patch("app.mcp_server.catalog.load_metadata", return_value={"datasets": []}),
        patch("app.mcp_server.catalog.build_catalog_summary", return_value=""),
        patch("app.mcp_server.catalog.get_domain_context", return_value=None),
    ):
        res = runner.run("cheap pc", safety_checker=lambda r: (True, None))

    assert res == {"status": "SUCCESS", "iterations": 1}
    assert captured["judge"] is sentinel_judge
    assert captured["max_iterations"] == 3
    assert callable(captured["modelize"])


def test_run_refused_skips_loop():
    """The imposed safety gate refuses BEFORE the loop: run_concierge never runs."""
    from unittest.mock import patch

    import app.concierge_runner as runner

    with (
        patch("app.concierge.run_concierge") as loop,
        patch("app.mcp_server.catalog.load_metadata", return_value={"datasets": []}),
    ):
        res = runner.run("bad request", safety_checker=lambda r: (False, "nope"))

    assert res == {"status": "REFUSED", "questions": ["nope"], "iterations": 0}
    loop.assert_not_called()


def test_run_safe_enters_loop(monkeypatch):
    """A safe verdict proceeds into the (single) concierge loop."""
    from unittest.mock import patch

    import app.concierge_runner as runner

    monkeypatch.delenv("GAUSS_FAST_MODELIZATION", raising=False)
    with (
        patch(
            "app.concierge.run_concierge",
            return_value={"status": "SUCCESS", "iterations": 1},
        ) as loop,
        patch("app.llm_extractor.make_llm_extractor", return_value=lambda s, p: []),
        patch("app.llm_judge.make_llm_judge", return_value=lambda u, s: (1.0, [])),
        patch("app.mcp_server.catalog.load_metadata", return_value={"datasets": []}),
        patch("app.mcp_server.catalog.build_catalog_summary", return_value=""),
        patch("app.mcp_server.catalog.get_domain_context", return_value=None),
    ):
        res = runner.run("cheap pc", safety_checker=lambda r: (True, None))

    assert res == {"status": "SUCCESS", "iterations": 1}
    assert loop.call_count == 1
    assert loop.call_args.kwargs["user_request"] == "cheap pc"


def test_repair_feedback_names_missing_categories():
    """Completeness failures must feed the missing categories back to stage 1,
    so the agent self-completes instead of asking the user."""
    seen_feedback = []

    def mock_extractor(stage: int, prompt: str) -> list[dict]:
        if "[REPAIR]" in prompt:
            seen_feedback.append(prompt)
        if stage == 1:
            # Always returns an incomplete set (only cpu)
            return [
                {
                    "category": "cpu",
                    "required_attributes": [{"name": "price", "data_type": "float"}],
                }
            ]
        if stage == 3:
            return [{"target_variable": "cpu.price", "direction": "minimize"}]
        return []

    def mock_judge(user_request, schema):
        return 1.0, []

    def mock_solver_client(request):
        raise AssertionError("solver must not be reached")

    res = run_concierge(
        user_request="cheapest Intel PC",
        modelize=make_staged_modelizer("cheapest Intel PC", "- cpu: ...", mock_extractor),
        judge=mock_judge,
        solver_client=mock_solver_client,
        max_iterations=2,
        required_categories=["cpu", "motherboard", "power-supply"],
    )

    # Iteration 2's REPAIR prompt must name exactly what to add
    assert any(
        "missing REQUIRED categories" in fb and "motherboard, power-supply" in fb
        for fb in seen_feedback
    ), f"repair feedback did not name missing categories: {seen_feedback}"
    # And the final clarification (budget exhausted) also names them
    assert res["status"] == "NEEDS_CLARIFICATION"
    assert any("motherboard" in q for q in res["questions"])
