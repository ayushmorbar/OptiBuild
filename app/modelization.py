"""Orchestrates the 4 staged modelization extraction steps."""

import json

from app.prompt_contracts import (
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
    build_stage4_prompt,
)
from app.schema import (
    Constraint,
    DecisionVariable,
    DerivedVariable,
    Objective,
    PivotSchema,
)

STAGE_MODELS = {
    1: DecisionVariable,
    2: DerivedVariable,
    3: Objective,
    4: Constraint,
}


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

    return d


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
        validated_items = []
        for d in raw:
            try:
                normalized = normalize_raw_dict(stage, d)
                validated_items.append(STAGE_MODELS[stage].model_validate(normalized))
            except Exception:
                pass
        outputs[stage] = validated_items

    return PivotSchema(
        user_intent=user_request,
        decision_variables=outputs.get(1, []),
        derived_variables=outputs.get(2, []),
        objectives=outputs.get(3, []),
        constraints=outputs.get(4, []),
    )


def build_schema_oneshot(
    user_request: str, catalog_summary: str, oneshot_extractor, domain=None
) -> PivotSchema:
    """Extract and compile the entire PivotSchema in one shot."""
    from app.prompt_contracts import build_oneshot_prompt

    prompt = build_oneshot_prompt(user_request, catalog_summary, domain=domain)
    raw_schema = oneshot_extractor(prompt)

    raw_dvs = raw_schema.get("decision_variables", [])
    raw_dervs = raw_schema.get("derived_variables", [])
    raw_objs = raw_schema.get("objectives", [])
    raw_consts = raw_schema.get("constraints", [])

    dvs = []
    for item in raw_dvs:
        try:
            norm = normalize_raw_dict(1, item)
            dvs.append(STAGE_MODELS[1].model_validate(norm))
        except Exception:
            pass

    dervs = []
    for item in raw_dervs:
        try:
            norm = normalize_raw_dict(2, item)
            dervs.append(STAGE_MODELS[2].model_validate(norm))
        except Exception:
            pass

    objs = []
    for item in raw_objs:
        try:
            norm = normalize_raw_dict(3, item)
            objs.append(STAGE_MODELS[3].model_validate(norm))
        except Exception:
            pass

    consts = []
    for item in raw_consts:
        try:
            norm = normalize_raw_dict(4, item)
            consts.append(STAGE_MODELS[4].model_validate(norm))
        except Exception:
            pass

    return PivotSchema(
        user_intent=user_request,
        decision_variables=dvs,
        derived_variables=dervs,
        objectives=objs,
        constraints=consts,
    )
