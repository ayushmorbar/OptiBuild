"""Security-safe pandas query operations and expression allowlisting using AST."""

import ast

import pandas as pd
from pydantic import TypeAdapter, ValidationError

from app.mcp_server.store import store
from app.schema import CleanOp, DynCleanReport, QueryReport, RejectedOp, RowsBeforeAfter


def validate_expr(expr: str, allowed_columns: set[str]) -> None:
    """Validate that the query expression contains only allowed columns

    and safe AST nodes (strictly no execution of arbitrary Python code).
    """
    if len(expr) > 300:
        raise ValueError("Expression is too long (> 300 characters)")
    if "@" in expr:
        raise ValueError("Expression contains forbidden character '@'")
    if "`" in expr:
        raise ValueError("Expression contains forbidden character '`'")

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Syntax error in expression: {e}") from e

    allowed_nodes = (
        ast.Expression,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.UnaryOp,
        ast.Not,
        ast.USub,
        ast.BinOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Compare,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
        ast.Gt,
        ast.GtE,
        ast.Name,
        ast.Load,
        ast.Constant,
    )

    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"Forbidden AST node type: {type(node).__name__}")

        if isinstance(node, ast.Name):
            if "__" in node.id:
                raise ValueError(f"Forbidden name structure: {node.id}")
            if node.id not in allowed_columns:
                raise ValueError(f"Forbidden variable reference: {node.id}")

        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float, str, bool, type(None))):
                raise ValueError(
                    f"Forbidden constant type: {type(node.value).__name__}"
                )


def safe_query(df: pd.DataFrame, expr: str, allowed_columns: set[str]) -> pd.DataFrame:
    """Validate and execute a query expression on a DataFrame.

    The expression is AST-allowlisted by ``validate_expr`` before execution, so the
    default pandas engine is safe here. We deliberately do NOT force ``engine="numexpr"``:
    numexpr is optional and cannot evaluate string/object-column comparisons such as
    ``brand == "AMD"`` (a core filter for this catalog). The default engine uses numexpr
    when it is installed and beneficial, and transparently falls back to python otherwise.
    """
    validate_expr(expr, allowed_columns)
    return df.query(expr)


def query_data(
    handle: str,
    category: str,
    expr: str | None = None,
    columns: list[str] | None = None,
    agg: str = "sample",
    limit: int = 20,
) -> QueryReport:
    """Retrieve and aggregate category data safely and without mutating the store."""
    try:
        frames = store.get(handle)
        if category not in frames:
            return QueryReport(rows=[], stats=None, dtypes={}, row_count=0)
        df = frames[category].copy()
    except KeyError:
        return QueryReport(rows=[], stats=None, dtypes={}, row_count=0)

    # Apply safe query filtering if expression is provided
    if expr:
        try:
            filtered = safe_query(df, expr, set(df.columns))
        except Exception as e:
            # Re-raise validation errors or syntax/query errors
            raise ValueError(f"Safe query failed: {e}") from e
    else:
        filtered = df

    # Apply column filtering
    if columns is not None:
        selected_cols = [c for c in columns if c in filtered.columns]
        filtered = filtered[selected_cols]

    rows = []
    stats = None

    if agg == "sample":
        rows = filtered.head(limit).to_dict(orient="records")
    elif agg == "describe":
        stats = filtered.describe(include="all").to_dict()
    elif agg == "value_counts":
        stats = {
            col: filtered[col].value_counts().head(limit).to_dict()
            for col in filtered.columns
        }

    dtypes = {col: str(dt) for col, dt in filtered.dtypes.items()}
    row_count = len(filtered)

    return QueryReport(rows=rows, stats=stats, dtypes=dtypes, row_count=row_count)


def clean_dynamic(handle: str, ops: list[dict], rationale: str = "") -> DynCleanReport:
    """Validate and execute a list of CleanOps on stored DataFrames under handle."""
    clean_op_adapter = TypeAdapter(CleanOp)
    parsed_ops = []
    rejected = []

    for i, op_dict in enumerate(ops):
        try:
            parsed_op = clean_op_adapter.validate_python(op_dict)
            parsed_ops.append((i, parsed_op))
        except ValidationError as e:
            rejected.append(RejectedOp(op_index=i, reason=str(e)))

    try:
        frames = store.get(handle)
        working_frames = {cat: df.copy() for cat, df in frames.items()}
        original_frames = {cat: df.copy() for cat, df in frames.items()}
    except KeyError as e:
        for i, _ in parsed_ops:
            rejected.append(
                RejectedOp(op_index=i, reason=f"Handle '{handle}' not found: {e}")
            )
        return DynCleanReport(
            accepted_ops=0,
            rejected=rejected,
            per_category={},
            columns_changed=[],
        )

    touched_categories = set()
    accepted_ops = 0
    columns_changed = []

    for i, op in parsed_ops:
        category = op.category
        if category not in working_frames:
            rejected.append(
                RejectedOp(
                    op_index=i,
                    reason=f"Category '{category}' absent from loaded datasets",
                )
            )
            continue

        touched_categories.add(category)
        working = working_frames[category]
        candidate = None
        error_reason = None

        if op.op == "filter_rows":
            try:
                candidate = safe_query(working, op.expr, set(working.columns))
            except Exception as e:
                error_reason = f"filter_rows failed: {e}"

        elif op.op == "drop_nulls":
            missing_cols = [c for c in op.columns if c not in working.columns]
            if missing_cols:
                error_reason = f"drop_nulls failed: columns {missing_cols} absent"
            else:
                candidate = working.dropna(subset=op.columns)

        elif op.op == "map_values":
            if op.column not in working.columns:
                error_reason = f"map_values failed: column '{op.column}' absent"
            else:
                candidate = working.copy()
                candidate[op.column] = candidate[op.column].replace(op.mapping)

        elif op.op == "clip_range":
            if op.column not in working.columns:
                error_reason = f"clip_range failed: column '{op.column}' absent"
            else:
                col_series = working[op.column]
                mask = pd.Series(True, index=working.index)
                if op.min is not None:
                    mask &= col_series >= op.min
                if op.max is not None:
                    mask &= col_series <= op.max
                candidate = working[mask]

        elif op.op == "filter_contains":
            if op.column not in working.columns:
                error_reason = f"filter_contains failed: column '{op.column}' absent"
            elif not op.value.strip():
                error_reason = "filter_contains failed: empty value"
            else:
                # Literal substring match, case-insensitive, NEVER a regex.
                mask = (
                    working[op.column]
                    .astype(str)
                    .str.contains(op.value, case=False, regex=False, na=False)
                )
                if op.negate:
                    mask = ~mask
                candidate = working[mask]

        if error_reason:
            rejected.append(RejectedOp(op_index=i, reason=error_reason))
            continue

        # Effect validation
        cols_match = set(candidate.columns) == set(working.columns)
        dtypes_match = candidate.dtypes.equals(working.dtypes)
        rows_valid = 0 < len(candidate) <= len(working)

        if cols_match and dtypes_match and rows_valid:
            working_frames[category] = candidate
            accepted_ops += 1
            if op.op == "map_values":
                columns_changed.append(op.column)
        else:
            reasons = []
            if not cols_match:
                reasons.append("columns changed")
            if not dtypes_match:
                reasons.append("dtypes changed")
            if not rows_valid:
                if len(candidate) == 0:
                    reasons.append("category became empty (0 rows)")
                else:
                    reasons.append("row count increased")
            rejected.append(
                RejectedOp(
                    op_index=i,
                    reason=f"Effect validation failed: {', '.join(reasons)}",
                )
            )

    # Batch drop check
    for cat in touched_categories:
        rows_before = len(original_frames[cat])
        rows_after = len(working_frames[cat])
        if rows_after < 0.1 * rows_before:
            working_frames[cat] = original_frames[cat].copy()
            rejected.append(
                RejectedOp(
                    op_index=-1,
                    reason=f"batch dropped >90% of rows (reverted) in category '{cat}'",
                )
            )

    # Replace frames in store
    store.replace(handle, working_frames)

    # Build report
    per_category = {}
    for cat, df in working_frames.items():
        per_category[cat] = RowsBeforeAfter(
            rows_before=len(original_frames[cat]),
            rows_after=len(df),
        )

    unique_columns_changed = sorted(set(columns_changed))

    return DynCleanReport(
        accepted_ops=accepted_ops,
        rejected=rejected,
        per_category=per_category,
        columns_changed=unique_columns_changed,
    )
