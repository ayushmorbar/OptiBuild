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

    # 4. Injectable dynamic cleaning hook (workflow n7: LLM queries the data
    # shape and submits declarative CleanOps — validated server-side)
    applied_clean_ops = []
    if dynamic_clean_hook is not None:
        applied_clean_ops = (
            dynamic_clean_hook(handle, schema, request.context.original_prompt) or []
        )

    # 5. Prefilter
    prefilter_report = prefilter_mod.prefilter(
        handle, [c.model_dump() for c in schema.constraints]
    )

    # Extract dataframe queries (prefilters + dynamic clean ops)
    def get_clean_op_query_string(op: dict) -> str:
        op_name = op.get("op")
        cat = op.get("category")
        col = op.get("column")
        if op_name == "filter_contains":
            neg = "~" if op.get("negate") else ""
            return f"df_{cat} = df_{cat}[{neg}df_{cat}['{col}'].str.contains({op.get('value')!r}, case=False, regex=False, na=False)]"
        elif op_name == "filter_rows":
            return f"df_{cat} = df_{cat}.query({op.get('expr')!r})"
        elif op_name == "drop_nulls":
            cols = op.get("columns", [])
            return f"df_{cat} = df_{cat}.dropna(subset={cols})"
        elif op_name == "map_values":
            return f"df_{cat}['{col}'] = df_{cat}['{col}'].replace({op.get('mapping')})"
        elif op_name == "clip_range":
            limits = []
            if op.get("min") is not None:
                limits.append(f"df_{cat}['{col}'] >= {op.get('min')}")
            if op.get("max") is not None:
                limits.append(f"df_{cat}['{col}'] <= {op.get('max')}")
            if not limits:
                return f"# clip_range {cat}.{col} (no-op)"
            return f"df_{cat} = df_{cat}[{' & '.join(limits)}]"
        return f"# clean_op: {op}"

    prefilters = [
        {
            "category": c.left_side.split(".", 1)[0],
            "column": c.left_side.split(".", 1)[1],
            "operator": c.operator,
            "value": c.right_side.value
            if c.right_side.kind == "literal"
            else c.right_side.ref,
            "constraint_name": c.name,
            "query_string": f"df_{c.left_side.split('.', 1)[0]} = df_{c.left_side.split('.', 1)[0]}[df_{c.left_side.split('.', 1)[0]}['{c.left_side.split('.', 1)[1]}'] {c.operator} {repr(c.right_side.value) if c.right_side.kind == 'literal' else c.right_side.ref}]",
        }
        for c in schema.constraints
        if c.stage == "prefilter"
    ]
    enriched_clean_ops = []
    for op in applied_clean_ops:
        op_copy = dict(op)
        op_copy["query_string"] = get_clean_op_query_string(op)
        enriched_clean_ops.append(op_copy)

    dataframe_queries = {
        "prefilters": prefilters,
        "dynamic_clean_ops": enriched_clean_ops,
    }
    generated_schema = schema.model_dump(exclude_defaults=True, exclude_none=True)

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
                "dataframe_queries": dataframe_queries,
                "generated_schema": generated_schema,
                **resolution_trace,
            },
        )

    # 6. CP-SAT Solver
    report = cpsat.solve_build(handle, schema.model_dump(), cost_column=cost_column)

    # 7. Map report to response
    if report.status in ("OPTIMAL", "FEASIBLE"):

        def objective_value(target: str) -> float:
            """Objective value from derived values, or from the selected item's attribute."""
            if target in report.derived_values:
                return report.derived_values[target]
            if "." in target:
                cat, attr = target.split(".", 1)
                selected = report.selections.get(cat, {})
                try:
                    return float(selected.get(attr))
                except (TypeError, ValueError):
                    pass
            return 0.0

        result = SolverResult(
            selections=report.selections,
            derived_values=report.derived_values,
            objective_report=[
                ObjectiveReportItem(
                    target=o.target_variable,
                    direction=o.direction,
                    value=objective_value(o.target_variable),
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
                "dataframe_queries": dataframe_queries,
                "generated_schema": generated_schema,
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
                "dataframe_queries": dataframe_queries,
                "generated_schema": generated_schema,
                **resolution_trace,
            },
        )
