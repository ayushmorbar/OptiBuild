"""Solver data gates for verifying dataset coverage before optimization."""

import re

from pydantic import BaseModel

from app.schema import LoadReport, MissingAttribute, PivotSchema


class GateResult(BaseModel):
    """Pydantic model representing the result of solver gate checks."""

    proceed: bool
    missing_attributes: list[MissingAttribute]
    stripped_terms: list[str]


def missing_terms(load_report: LoadReport) -> set[str]:
    """Retrieve all missing terms 'category.attribute' from the load report."""
    return {
        f"{cov.category}.{attr}"
        for cov in load_report.coverage
        for attr in cov.missing_columns
    }


def get_formula_terms(formula: str) -> set[str]:
    """Extract term tokens (category.attribute or derived_name) from a formula."""
    agg_names = {"sum", "min", "max", "avg", "count"}
    tokens = re.findall(r"[a-z0-9_-]+(?:\.[a-z0-9_]+)?", formula)
    return {t for t in tokens if t not in agg_names}


def gate1_required_covered(
    schema: PivotSchema, load_report: LoadReport
) -> tuple[bool, list[str]]:
    """Verify that all required (non-optional) decision variable categories

    are present and have all required attributes covered.
    """
    missing_reasons = []
    coverage_dict = {cov.category: cov for cov in load_report.coverage}

    for dv in schema.decision_variables:
        if dv.optional:
            continue

        cat = dv.category
        cov = coverage_dict.get(cat)

        if cov is None or cov.row_count == 0:
            missing_reasons.append(cat)
            continue

        found_cols = set(cov.found_columns)
        for req_attr in dv.required_attributes:
            if req_attr.name not in found_cols:
                missing_reasons.append(f"{cat}.{req_attr.name}")

    return len(missing_reasons) == 0, missing_reasons


def poisoned_derived(schema: PivotSchema, missing: set[str]) -> set[str]:
    """Transitively identify derived variables poisoned by missing terms."""
    poisoned = set()
    dv_terms = {}

    for dv in schema.derived_variables:
        dv_terms[dv.name] = get_formula_terms(dv.formula)

    while True:
        added = False
        for dv in schema.derived_variables:
            if dv.name in poisoned:
                continue
            terms = dv_terms[dv.name]
            if any(t in missing or t in poisoned for t in terms):
                poisoned.add(dv.name)
                added = True
        if not added:
            break

    return poisoned


def references_of(term: str, schema: PivotSchema) -> list[str]:
    """Return constraints or objectives referencing the term directly."""
    refs = []
    for c in schema.constraints:
        left_match = c.left_side == term
        right_match = c.right_side.kind == "var_ref" and c.right_side.ref == term
        if left_match or right_match:
            refs.append(c.name)

    for obj in schema.objectives:
        if obj.target_variable == term:
            refs.append(f"objective:{term}")

    return refs


def get_all_references(term: str, schema: PivotSchema, poisoned: set[str]) -> list[str]:
    """Recursively identify all constraint/objective references of a term,

    including indirect references through poisoned derived variables.
    """
    refs = set(references_of(term, schema))
    to_process = [term]
    visited = set()

    while to_process:
        curr = to_process.pop(0)
        if curr in visited:
            continue
        visited.add(curr)

        refs.update(references_of(curr, schema))

        for dv in schema.derived_variables:
            if dv.name in poisoned:
                if curr in get_formula_terms(dv.formula):
                    to_process.append(dv.name)

    return sorted(refs)


def check_gates(schema: PivotSchema, load_report: LoadReport) -> GateResult:
    """Run Gate 1 and Gate 2 check pipeline to verify data integrity."""
    # 1. Gate 1 (hard): a required (non-optional) category that is absent or has row_count == 0
    # -> UNCONDITIONAL MISSING_DATA (proceed=False)
    coverage_dict = {cov.category: cov for cov in load_report.coverage}
    absent_required = []
    for dv in schema.decision_variables:
        if not dv.optional:
            cat = dv.category
            cov = coverage_dict.get(cat)
            if cov is None or cov.row_count == 0:
                absent_required.append(cat)

    if absent_required:
        missing_attrs = [
            MissingAttribute(
                category=cat,
                attribute="",
                referenced_by=["required_category_absent"],
            )
            for cat in absent_required
        ]
        return GateResult(
            proceed=False,
            missing_attributes=missing_attrs,
            stripped_terms=[],
        )

    # 2. Gate 2 check
    missing = missing_terms(load_report)
    poisoned = poisoned_derived(schema, missing)

    missing_attrs = []
    for term in sorted(missing):
        refs = get_all_references(term, schema, poisoned)
        if refs:
            category, attribute = term.split(".", 1)
            missing_attrs.append(
                MissingAttribute(
                    category=category,
                    attribute=attribute,
                    referenced_by=refs,
                )
            )

    if missing_attrs:
        return GateResult(
            proceed=False,
            missing_attributes=missing_attrs,
            stripped_terms=[],
        )

    return GateResult(
        proceed=True,
        missing_attributes=[],
        stripped_terms=sorted(missing),
    )
