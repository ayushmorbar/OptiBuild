"""MCP Prefilter operations for filtering DataFrames before solver specialists."""

import operator

from pydantic import TypeAdapter, ValidationError

from app.mcp_server.store import store
from app.schema import Constraint, PrefilterReport, RowsBeforeAfter

OPS_MAP = {
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    ">=": operator.ge,
    ">": operator.gt,
    "!=": operator.ne,
}


def prefilter(handle: str, constraints: list[dict]) -> PrefilterReport:
    """Parse and apply stage=='prefilter' constraints to loaded datasets under handle."""
    constraint_adapter = TypeAdapter(Constraint)
    parsed_constraints = []

    for _i, c_dict in enumerate(constraints):
        try:
            constraint = constraint_adapter.validate_python(c_dict)
            if constraint.stage == "prefilter":
                parsed_constraints.append(constraint)
        except ValidationError:
            # Skip invalid constraints
            continue

    try:
        frames = store.get(handle)
        working_frames = {cat: df.copy() for cat, df in frames.items()}
        original_frames = {cat: df.copy() for cat, df in frames.items()}
    except KeyError:
        return PrefilterReport(handle=handle, per_category={}, emptied_categories=[])

    touched_categories = set()

    for constraint in parsed_constraints:
        category, attr = constraint.left_side.split(".", 1)
        if category not in working_frames:
            continue

        df = working_frames[category]
        if attr not in df.columns:
            continue

        touched_categories.add(category)
        value = constraint.right_side.value
        op_func = OPS_MAP.get(constraint.operator)

        if op_func:
            try:
                mask = op_func(df[attr], value)
                working_frames[category] = df[mask]
            except Exception:
                # In case of type mismatch or other errors, skip and leave frame unchanged
                pass

    # Save filtered frames
    store.replace(handle, working_frames)

    # Build report
    per_category = {}
    for cat in touched_categories:
        per_category[cat] = RowsBeforeAfter(
            rows_before=len(original_frames[cat]),
            rows_after=len(working_frames[cat]),
        )

    emptied_categories = [cat for cat, df in working_frames.items() if len(df) == 0]

    return PrefilterReport(
        handle=handle,
        per_category=per_category,
        emptied_categories=emptied_categories,
    )
