"""CP-SAT solver core for PC build optimization."""

import re
import time

import pandas as pd
from ortools.sat.python import cp_model

from app.mcp_server.ranking import topsis_rank
from app.mcp_server.store import store
from app.schema import PivotSchema, Ranking, SolveReport

SCALE = 100
ROW_CAP = 200


def build_and_solve(
    frames: dict[str, pd.DataFrame], schema: PivotSchema
) -> SolveReport:
    """Build and solve the CP-SAT optimization model based on the pivot schema."""
    model = cp_model.CpModel()
    capped_frames = {}
    x = {}

    # 1. Decision Variables
    for var in schema.decision_variables:
        category = var.category
        is_optional = var.optional

        if category not in frames or len(frames[category]) == 0:
            if not is_optional:
                # Required category is missing or empty -> infeasible
                return SolveReport(
                    status="INFEASIBLE",
                    selections={},
                    derived_values={},
                    ranking=None,
                    failed_constraints=[category],
                    solve_ms=0,
                )
            else:
                x[category] = {}
                capped_frames[category] = pd.DataFrame()
                continue

        # Cap to cheapest ROW_CAP rows by ascending price
        df_cat = frames[category].sort_values("price").head(ROW_CAP)
        capped_frames[category] = df_cat

        x[category] = {}
        for idx in df_cat.index:
            x[category][idx] = model.NewBoolVar(f"x_{category}_{idx}")

        if not is_optional:
            model.AddExactlyOne(x[category].values())
        else:
            model.AddAtMostOne(x[category].values())

    # Helper term_expr(term)
    def term_expr(term: str):
        if "." not in term:
            raise ValueError(f"Invalid term format: {term}")
        category, attr = term.split(".", 1)
        if category not in x:
            raise ValueError(
                f"Category '{category}' referenced in term '{term}' is unknown."
            )

        df_cat = capped_frames[category]
        if df_cat.empty:
            return 0

        if attr not in df_cat.columns:
            raise ValueError(
                f"Attribute '{attr}' in category '{category}' referenced in term '{term}' is unknown."
            )

        expr_terms = []
        for idx, row in df_cat.iterrows():
            val = row[attr]
            if pd.isna(val):
                continue
            try:
                scaled_val = round(float(val) * SCALE)
                expr_terms.append(scaled_val * x[category][idx])
            except (ValueError, TypeError):
                continue

        return sum(expr_terms)

    # 2. Derived Variables
    derived_exprs = {}
    skipped = []
    derived_names = {v.name for v in schema.derived_variables}

    for var in schema.derived_variables:
        formula_str = var.formula
        m = re.match(r"^sum\((.+)\)$", formula_str.strip())
        if not m:
            skipped.append(var.name)
            continue

        terms = [t.strip() for t in m.group(1).split(",")]
        # Skip if references another derived variable or contains unsupported aggregate
        if any(term in derived_names for term in terms):
            skipped.append(var.name)
            continue

        try:
            compiled_exprs = [term_expr(term) for term in terms]
            derived_exprs[var.name] = sum(compiled_exprs)
        except Exception:
            skipped.append(var.name)
            continue

    # 3. Solver Constraints
    COEF_SCALE = 1000
    for constraint in schema.constraints:
        if constraint.stage != "solver" or not constraint.is_hard:
            continue

        # Resolve left_expr
        left_side = constraint.left_side
        left_expr = None
        if left_side in derived_exprs:
            left_expr = derived_exprs[left_side]
        elif "." in left_side:
            try:
                left_expr = term_expr(left_side)
            except Exception:
                continue
        else:
            continue

        # Resolve right_expr
        right_expr = None
        right_kind = constraint.right_side.kind

        if right_kind == "literal":
            right_expr = round(float(constraint.right_side.value) * SCALE)
        elif right_kind == "var_ref":
            ref = constraint.right_side.ref
            if ref in derived_exprs:
                right_expr = derived_exprs[ref]
            elif "." in ref:
                # Categorical/string var_ref (e.g. socket equality) deferred - needs value encoding + enriched data.
                try:
                    right_expr = term_expr(ref)
                except Exception:
                    continue
                if isinstance(right_expr, int) and right_expr == 0:
                    continue
            else:
                continue
        else:
            continue

        if right_expr is None:
            continue

        coefficient = constraint.coefficient
        left_scaled = COEF_SCALE * left_expr
        right_scaled = round(coefficient * COEF_SCALE) * right_expr

        op = constraint.operator

        if op == "<":
            model.Add(left_scaled < right_scaled)
        elif op == "<=":
            model.Add(left_scaled <= right_scaled)
        elif op == "==":
            model.Add(left_scaled == right_scaled)
        elif op == ">=":
            model.Add(left_scaled >= right_scaled)
        elif op == ">":
            model.Add(left_scaled > right_scaled)
        elif op == "!=":
            model.Add(left_scaled != right_scaled)

    # 4. Objectives Resolution
    obj_exprs = []
    for obj in schema.objectives:
        target = obj.target_variable
        if target in derived_exprs:
            obj_expr = derived_exprs[target]
        elif "." in target:
            try:
                obj_expr = term_expr(target)
            except Exception as e:
                raise ValueError(
                    f"Objective target '{target}' could not be resolved: {e}"
                ) from e
        else:
            raise ValueError(f"Objective target '{target}' could not be resolved.")
        obj_exprs.append(obj_expr)

    if len(schema.objectives) <= 1:
        # Single-objective path
        if len(schema.objectives) == 1:
            obj = schema.objectives[0]
            direction = obj.direction
            if direction == "minimize":
                model.Minimize(obj_exprs[0])
            else:
                model.Maximize(obj_exprs[0])

        solver = cp_model.CpSolver()
        start_time = time.perf_counter()
        status = solver.Solve(model)
        solve_ms = int((time.perf_counter() - start_time) * 1000)

        if status == cp_model.OPTIMAL:
            status_str = "OPTIMAL"
        elif status == cp_model.FEASIBLE:
            status_str = "FEASIBLE"
        else:
            status_str = "INFEASIBLE"

        if status_str in ("OPTIMAL", "FEASIBLE"):
            selections = {}
            for cat, cat_vars in x.items():
                for idx, var_bool in cat_vars.items():
                    if solver.Value(var_bool) == 1:
                        selections[cat] = capped_frames[cat].loc[idx].to_dict()
                        break

            derived_values = {}
            for name, expr in derived_exprs.items():
                try:
                    scaled_val = solver.Value(expr)
                    derived_values[name] = float(scaled_val) / SCALE
                except Exception:
                    pass

            return SolveReport(
                status=status_str,
                selections=selections,
                derived_values=derived_values,
                ranking=None,
                failed_constraints=[],
                solve_ms=solve_ms,
            )
        else:
            return SolveReport(
                status="INFEASIBLE",
                selections={},
                derived_values={},
                ranking=None,
                failed_constraints=[],
                solve_ms=solve_ms,
            )
    else:
        # Multi-objective path: K-candidate enumeration + TOPSIS ranking
        anchor_obj = schema.objectives[0]
        if anchor_obj.direction == "minimize":
            model.Minimize(obj_exprs[0])
        else:
            model.Maximize(obj_exprs[0])

        solver = cp_model.CpSolver()
        start_time = time.perf_counter()

        candidates = []
        K_CANDIDATES = 50

        for _ in range(K_CANDIDATES):
            status = solver.Solve(model)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                break

            candidate_selections = {}
            active_vars = []
            for cat, cat_vars in x.items():
                for idx, var_bool in cat_vars.items():
                    if solver.Value(var_bool) == 1:
                        candidate_selections[cat] = (
                            capped_frames[cat].loc[idx].to_dict()
                        )
                        active_vars.append(var_bool)
                        break

            candidate_obj_vals = []
            for expr in obj_exprs:
                try:
                    val = float(solver.Value(expr)) / SCALE
                except Exception:
                    val = 0.0
                candidate_obj_vals.append(val)

            candidate_derived = {}
            for name, expr in derived_exprs.items():
                try:
                    candidate_derived[name] = float(solver.Value(expr)) / SCALE
                except Exception:
                    pass

            candidates.append(
                {
                    "selections": candidate_selections,
                    "obj_vals": candidate_obj_vals,
                    "derived_values": candidate_derived,
                }
            )

            # Add no-good clause to block this combination of selections
            if active_vars:
                model.Add(sum(active_vars) <= len(active_vars) - 1)
            else:
                break

        solve_ms = int((time.perf_counter() - start_time) * 1000)

        if not candidates:
            return SolveReport(
                status="INFEASIBLE",
                selections={},
                derived_values={},
                ranking=None,
                failed_constraints=[],
                solve_ms=solve_ms,
            )

        # Build matrix (candidates x objectives)
        matrix = [c["obj_vals"] for c in candidates]
        weights = [obj.weight for obj in schema.objectives]
        directions = [obj.direction for obj in schema.objectives]

        best_idx, scores = topsis_rank(matrix, weights, directions)
        best_cand = candidates[best_idx]
        best_score = scores[best_idx]

        return SolveReport(
            status="FEASIBLE",
            selections=best_cand["selections"],
            derived_values=best_cand["derived_values"],
            ranking=Ranking(
                method="topsis",
                score=float(best_score),
                candidates_ranked=len(candidates),
            ),
            failed_constraints=[],
            solve_ms=solve_ms,
        )


def solve_build(handle: str, pivot_schema: dict) -> SolveReport:
    """Load pre-filtered data and solve the optimization model using CP-SAT."""
    frames = store.get(handle)
    schema = PivotSchema.model_validate(pivot_schema)
    return build_and_solve(frames, schema)
