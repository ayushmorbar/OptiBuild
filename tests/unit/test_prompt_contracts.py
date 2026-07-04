"""Unit tests for the modelization prompt contracts."""

from app.prompt_contracts import (
    GUARDRAILS,
    build_judge_prompt,
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
    build_stage4_prompt,
)


def test_prompt_contracts_wrapping_and_content():
    user_req = "Build me a computer with 16GB memory"
    cat_summary = "cpu: price, cores\nmemory: price, capacity"
    prior_json = '{"stage1": []}'

    p1 = build_stage1_prompt(user_req, cat_summary)
    p2 = build_stage2_prompt(user_req, prior_json)
    p3 = build_stage3_prompt(user_req, prior_json)
    p4 = build_stage4_prompt(user_req, prior_json, cat_summary)
    pj = build_judge_prompt(user_req, prior_json)

    # 1. Wrapping in <user_request>
    for p in (p1, p2, p3, p4, pj):
        assert f"<user_request>\n{user_req}\n</user_request>" in p

    # 2. Stage 2 mentions sum(...)
    assert "sum(" in p2

    # 3. Stage 4 mentions LiteralThreshold vs VarRefThreshold and "never invent"
    assert "LiteralThreshold" in p4
    assert "VarRefThreshold" in p4
    assert "never invent" in p4.lower()

    # 4. Stage 3 mentions qualitative goals
    assert "qualitative" in p3.lower()

    # 5. Catalog summary appears in stages 1 and 4
    assert cat_summary in p1
    assert cat_summary in p4

    # 6. Guardrails contains scope lock and overclocking/DRM
    assert "scope lock" in GUARDRAILS.lower()
    assert "overclocking" in GUARDRAILS.lower()
    assert "drm" in GUARDRAILS.lower()

    # 7. No occurrence of "kb_ref" or "use_cases"
    for p in (p1, p2, p3, p4, pj, GUARDRAILS):
        assert "kb_ref" not in p
        assert "use_cases" not in p
