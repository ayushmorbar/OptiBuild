"""Solver specialist deterministic optimization pipeline."""

from app.mcp_server import catalog, cleaning, cpsat
from app.mcp_server import prefilter as prefilter_mod
from app.schema import (
    ObjectiveReportItem,
    RelaxationSuggestion,
    SolverFeedback,
    SolverRequest,
    SolverResponse,
    SolverResult,
)
from solver_app.gates import check_gates


def run_solver_pipeline(
    request: SolverRequest, dynamic_clean_hook=None
) -> SolverResponse:
    """Run the deterministic solver pipeline, orchestrating the FastMCP tool functions in-process."""
    metadata = catalog.load_metadata()
    cost_column = metadata.get("primary_cost_column")

    # 0. Resolve decision-variable categories to catalog keys (exact -> synonym -> fuzzy)
    try:
        schema, category_mapping, unresolved = catalog.resolve_schema_categories(
            request.pivot_schema, metadata
        )
        resolution_trace = {}
        if category_mapping:
            resolution_trace["category_resolution"] = category_mapping
        if unresolved:
            resolution_trace["unresolved_categories"] = unresolved
    except Exception as e:
        # Resolution is a safety net: on any rewrite failure, solve the original schema
        schema = request.pivot_schema
        resolution_trace = {"category_resolution_error": str(e)}

    # 1. Load Data
    categories = [dv.category for dv in schema.decision_variables]
    required_columns = {
        dv.category: [a.name for a in dv.required_attributes]
        for dv in schema.decision_variables
    }
    load = catalog.load_data(categories, required_columns, metadata)
    handle = load.dataset_handle

    # 2. Gate checks
    gate = check_gates(schema, load)
    if not gate.proceed:
        return SolverResponse(
            transaction_id=request.transaction_id,
            status="MISSING_DATA",
            feedback=SolverFeedback(
                reason="missing data referenced by goals/constraints",
                missing_attributes=gate.missing_attributes,
                failed_constraints=[],
                relaxation_suggestions=[],
            ),
            trace={"stripped_terms": gate.stripped_terms, **resolution_trace},
        )

    # 3. Systematic cleaning
    cleaning.clean_systematic(handle, metadata)

    # 4. Injectable dynamic cleaning hook
    if dynamic_clean_hook is not None:
        dynamic_clean_hook(handle, schema)

    # 5. Prefilter
    prefilter_report = prefilter_mod.prefilter(
        handle, [c.model_dump() for c in schema.constraints]
    )

    required_cats = {dv.category for dv in schema.decision_variables if not dv.optional}
    emptied_req = required_cats.intersection(prefilter_report.emptied_categories)
    if emptied_req:
        return SolverResponse(
            transaction_id=request.transaction_id,
            status="INFEASIBLE",
            feedback=SolverFeedback(
                reason="a required category was emptied by prefilter",
                failed_constraints=sorted(emptied_req),
                missing_attributes=[],
                relaxation_suggestions=[],
            ),
            trace={
                "rows_after_prefilter": prefilter_report.per_category,
                "solve_ms": 0,
                "stripped_terms": gate.stripped_terms,
                **resolution_trace,
            },
        )

    # 6. CP-SAT Solver
    report = cpsat.solve_build(handle, schema.model_dump(), cost_column=cost_column)

    # 7. Map report to response
    if report.status in ("OPTIMAL", "FEASIBLE"):
        result = SolverResult(
            selections=report.selections,
            derived_values=report.derived_values,
            objective_report=[
                ObjectiveReportItem(
                    target=o.target_variable,
                    direction=o.direction,
                    value=report.derived_values.get(o.target_variable, 0.0),
                )
                for o in schema.objectives
            ],
            ranking=report.ranking,
        )
        return SolverResponse(
            transaction_id=request.transaction_id,
            status="SUCCESS",
            result=result,
            feedback=None,
            trace={
                "rows_after_prefilter": prefilter_report.per_category,
                "solve_ms": report.solve_ms,
                "stripped_terms": gate.stripped_terms,
                **resolution_trace,
            },
        )
    else:
        origin_priority = {
            "system_default": 0,
            "kb_derived": 1,
            "user_explicit": 2,
        }
        hard_constraints = [
            c for c in schema.constraints if c.is_hard and c.origin != "compatibility"
        ]
        hard_constraints.sort(key=lambda c: origin_priority.get(c.origin, 999))

        rel_suggestions = []
        for c in hard_constraints:
            rhs = (
                c.right_side.value
                if c.right_side.kind == "literal"
                else c.right_side.ref
            )
            suggestion_text = (
                f"Relax hard constraint '{c.name}' "
                f"(current: {c.left_side} {c.operator} {rhs})"
            )
            rel_suggestions.append(
                RelaxationSuggestion(
                    constraint=c.name,
                    suggestion=suggestion_text,
                )
            )

        feedback = SolverFeedback(
            reason="no feasible build",
            failed_constraints=report.failed_constraints,
            missing_attributes=[],
            relaxation_suggestions=rel_suggestions,
        )

        return SolverResponse(
            transaction_id=request.transaction_id,
            status="INFEASIBLE",
            result=None,
            feedback=feedback,
            trace={
                "rows_after_prefilter": prefilter_report.per_category,
                "solve_ms": report.solve_ms,
                "stripped_terms": gate.stripped_terms,
                **resolution_trace,
            },
        )
