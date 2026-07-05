"""Orchestrates the 4 staged modelization extraction steps."""

import json
import logging
import re

from app.prompt_contracts import (
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
    build_stage4_prompt,
)
from app.schema import (
    AttributeRequirement,
    Constraint,
    DecisionVariable,
    DerivedVariable,
    Objective,
    PivotSchema,
)

logger = logging.getLogger(__name__)

STAGE_MODELS = {
    1: DecisionVariable,
    2: DerivedVariable,
    3: Objective,
    4: Constraint,
}

# A single grammar term: 'category.attribute' or a derived-variable name
_TERM_RE = re.compile(r"^[a-z0-9_-]+(?:\.[a-z0-9_]+)?$")


def normalize_raw_dict(stage: int, d: dict) -> dict:
    """Rewrite known LLM synonyms in raw dictionary before strict validation."""
    import copy

    d = copy.deepcopy(d)

    if stage == 1:
        req_attrs = d.get("required_attributes")
        if isinstance(req_attrs, list):
            for attr in req_attrs:
                if isinstance(attr, dict) and "data_type" in attr:
                    dt = str(attr["data_type"]).lower().strip()
                    dt_map = {
                        "string": "str",
                        "integer": "int",
                        "number": "float",
                        "boolean": "bool",
                    }
                    attr["data_type"] = dt_map.get(dt, dt)
    elif stage == 2:
        # The formula grammar is lowercase-only; LLMs also like writing
        # 'a.x + b.y' instead of 'sum(a.x, b.y)' — rewrite that form.
        if isinstance(d.get("formula"), str):
            formula = d["formula"].strip().lower()
            parts = [p.strip() for p in formula.split("+")]
            if len(parts) > 1 and all(_TERM_RE.match(p) for p in parts):
                formula = f"sum({', '.join(parts)})"
            d["formula"] = formula
        if isinstance(d.get("name"), str):
            d["name"] = d["name"].strip().lower()
        # dependencies must be category keys; LLMs often emit full
        # 'category.attribute' terms — strip to the category part, dedupe.
        if isinstance(d.get("dependencies"), list):
            norm_deps = []
            for dep in d["dependencies"]:
                s = str(dep).strip().lower()
                if "." in s:
                    s = s.split(".", 1)[0]
                if s and s not in norm_deps:
                    norm_deps.append(s)
            d["dependencies"] = norm_deps
    elif stage == 3:
        if "direction" in d:
            direc = str(d["direction"]).lower().strip()
            dir_map = {
                "min": "minimize",
                "max": "maximize",
            }
            d["direction"] = dir_map.get(direc, direc)
    elif stage == 4:
        right_side = d.get("right_side")
        if isinstance(right_side, dict) and "kind" in right_side:
            right_side["kind"] = str(right_side["kind"]).lower().strip()
        # origin is provenance metadata; LLMs improvise variants -> normalize,
        # defaulting anything unknown to 'user_explicit' (the safe provenance).
        if "origin" in d:
            origin = str(d["origin"]).lower().strip()
            origin_map = {
                "user_request": "user_explicit",
                "user": "user_explicit",
                "user_stated": "user_explicit",
                "user_provided": "user_explicit",
                "explicit": "user_explicit",
                "kb": "kb_derived",
                "knowledge_base": "kb_derived",
                "compat": "compatibility",
                "compatibility_rule": "compatibility",
                "system": "system_default",
                "default": "system_default",
            }
            origin = origin_map.get(origin, origin)
            if origin not in (
                "user_explicit",
                "kb_derived",
                "compatibility",
                "system_default",
            ):
                origin = "user_explicit"
            d["origin"] = origin

    return d


_STAGE_LABELS = {
    1: "decision variable",
    2: "derived variable",
    3: "objective",
    4: "constraint",
}


def _validate_items(stage: int, raw: list[dict]) -> list:
    """Normalize + validate raw LLM items; drops are logged with their reason."""
    validated = []
    for d in raw:
        try:
            normalized = normalize_raw_dict(stage, d)
            validated.append(STAGE_MODELS[stage].model_validate(normalized))
        except Exception as e:
            ident = d.get("name") or d.get("category") or d.get("target_variable") or d
            logger.warning("dropping invalid %s %r: %s", _STAGE_LABELS[stage], ident, e)
    return validated


def _assemble_schema(
    user_request: str,
    dvs: list[DecisionVariable],
    dervs: list[DerivedVariable],
    objs: list[Objective],
    consts: list[Constraint],
) -> PivotSchema:
    """Assemble a PivotSchema from validated items, repairing dangling references.

    Individual-item validation may have dropped items (e.g. a derived variable
    with an off-grammar formula), leaving objectives/constraints pointing at
    unknown variables. Repair strategy:
    1. Drop derived variables whose dependencies reference undeclared categories.
    2. Auto-add a missing 'category.attribute' to the decision variable when the
       category itself is declared (the LLM referenced a real column it forgot
       to list in required_attributes).
    3. Drop objectives/constraints still referencing unknown variables.
    4. If no objective survives, raise a clear error (feeds the REPAIR loop).
    """
    categories = {d.category for d in dvs}
    derived_names = {dv.name for dv in dervs}

    # 1. Derived variables with undeclared dependencies can never compile
    kept_dervs = []
    for dv in dervs:
        bad = [
            d for d in dv.dependencies if d not in categories and d not in derived_names
        ]
        if bad:
            logger.warning(
                "dropping derived variable %r: unknown dependencies %s", dv.name, bad
            )
        else:
            kept_dervs.append(dv)
    derived_names = {dv.name for dv in kept_dervs}

    known = set(derived_names)
    for d in dvs:
        for attr in d.required_attributes:
            known.add(f"{d.category}.{attr.name}")

    dropped: list[str] = []

    def declare_attr(cat: str, attr: str) -> str:
        term = f"{cat}.{attr}"
        for d in dvs:
            if d.category == cat:
                d.required_attributes.append(
                    AttributeRequirement(name=attr, data_type="float")
                )
                known.add(term)
                logger.info("auto-declared missing attribute %r", term)
                break
        return term

    def resolve_term(term: str) -> str | None:
        """Return the canonical term for `term`, or None if unresolvable.

        Repairs: auto-declares missing attributes of declared categories, and
        rewrites snake_case terms like 'memory_capacity' (or
        'power_supply_wattage') into dotted 'category.attribute' terms.
        """
        if term in known:
            return term
        if "." in term:
            cat, attr = term.split(".", 1)
            if cat in categories and re.match(r"^[a-z0-9_]+$", attr):
                return declare_attr(cat, attr)
            return None
        # No dot: try '<category>_<attribute>' (with '-' vs '_' tolerance)
        for cat in categories:
            prefix = cat.replace("-", "_") + "_"
            if term.startswith(prefix):
                attr = term[len(prefix) :]
                if re.match(r"^[a-z0-9_]+$", attr):
                    if f"{cat}.{attr}" in known:
                        return f"{cat}.{attr}"
                    return declare_attr(cat, attr)
        return None

    kept_objs = []
    for o in objs:
        resolved = resolve_term(o.target_variable)
        if resolved is not None:
            o.target_variable = resolved
            kept_objs.append(o)
        else:
            dropped.append(f"objective -> {o.target_variable!r}")
            logger.warning("dropping objective targeting unknown %r", o.target_variable)

    kept_consts = []
    for c in consts:
        left = resolve_term(c.left_side)
        ok = left is not None
        if ok:
            c.left_side = left
        if ok and c.right_side.kind == "var_ref":
            ref = resolve_term(c.right_side.ref)
            ok = ref is not None
            if ok:
                c.right_side.ref = ref
        if ok:
            kept_consts.append(c)
        else:
            dropped.append(f"constraint {c.name!r}")
            logger.warning("dropping constraint %r with unknown reference", c.name)

    if not kept_objs:
        raise ValueError(
            "modelization produced no valid objective: every extracted objective "
            f"referenced an unknown variable (dropped: {dropped or objs}). "
            "Re-extract with objectives targeting declared decision-variable "
            "attributes or derived variables."
        )

    return PivotSchema(
        user_intent=user_request,
        decision_variables=dvs,
        derived_variables=kept_dervs,
        objectives=kept_objs,
        constraints=kept_consts,
    )


def run_modelization(
    user_request: str,
    catalog_summary: str,
    extractor,
    prior_schema: PivotSchema | None = None,
    target_stages: list[int] | None = None,
    repair_feedback: str | None = None,
    domain=None,
) -> PivotSchema:
    """Run the 4 extraction stages in order and assemble a PivotSchema.

    - extractor: callable(stage: int, prompt: str) -> list[dict]
    - domain: optional DomainContext from the active pack's metadata (prompt flavoring)
    """
    stages_to_run = target_stages or [1, 2, 3, 4]

    # Seed outputs from prior_schema if provided
    outputs = {}
    if prior_schema is not None:
        outputs[1] = prior_schema.decision_variables
        outputs[2] = prior_schema.derived_variables
        outputs[3] = prior_schema.objectives
        outputs[4] = prior_schema.constraints
    else:
        outputs[1] = []
        outputs[2] = []
        outputs[3] = []
        outputs[4] = []

    for stage in [1, 2, 3, 4]:
        if stage not in stages_to_run:
            continue

        if stage == 1:
            prompt = build_stage1_prompt(
                user_request, catalog_summary, repair_feedback, domain=domain
            )
        elif stage == 2:
            prior_dict = {
                "decision_variables": [dv.model_dump() for dv in outputs.get(1, [])]
            }
            prior_json = json.dumps(prior_dict, indent=2)
            prompt = build_stage2_prompt(
                user_request, prior_json, repair_feedback, domain=domain
            )
        elif stage == 3:
            prior_dict = {
                "decision_variables": [dv.model_dump() for dv in outputs.get(1, [])],
                "derived_variables": [dv.model_dump() for dv in outputs.get(2, [])],
            }
            prior_json = json.dumps(prior_dict, indent=2)
            prompt = build_stage3_prompt(
                user_request, prior_json, repair_feedback, domain=domain
            )
        else:
            # stage 4
            prior_dict = {
                "decision_variables": [dv.model_dump() for dv in outputs.get(1, [])],
                "derived_variables": [dv.model_dump() for dv in outputs.get(2, [])],
                "objectives": [obj.model_dump() for obj in outputs.get(3, [])],
            }
            prior_json = json.dumps(prior_dict, indent=2)
            prompt = build_stage4_prompt(
                user_request,
                prior_json,
                catalog_summary,
                repair_feedback,
                domain=domain,
            )

        raw = extractor(stage, prompt)
        outputs[stage] = _validate_items(stage, raw)

    return _assemble_schema(
        user_request,
        outputs.get(1, []),
        outputs.get(2, []),
        outputs.get(3, []),
        outputs.get(4, []),
    )


def build_schema_oneshot(
    user_request: str, catalog_summary: str, oneshot_extractor, domain=None
) -> PivotSchema:
    """Extract and compile the entire PivotSchema in one shot."""
    from app.prompt_contracts import build_oneshot_prompt

    prompt = build_oneshot_prompt(user_request, catalog_summary, domain=domain)
    raw_schema = oneshot_extractor(prompt)

    dvs = _validate_items(1, raw_schema.get("decision_variables", []))
    dervs = _validate_items(2, raw_schema.get("derived_variables", []))
    objs = _validate_items(3, raw_schema.get("objectives", []))
    consts = _validate_items(4, raw_schema.get("constraints", []))

    return _assemble_schema(user_request, dvs, dervs, objs, consts)
