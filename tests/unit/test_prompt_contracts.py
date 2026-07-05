"""Unit tests for the modelization prompt contracts."""

from app.prompt_contracts import (
    GUARDRAILS,
    build_guardrails,
    build_judge_prompt,
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
    build_stage4_prompt,
)
from app.schema import DomainContext


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

    # 6. Guardrails are generic: scope lock + integrity, no domain hardcode
    assert "scope lock" in GUARDRAILS.lower()
    assert "integrity" in GUARDRAILS.lower()
    assert "overclocking" not in GUARDRAILS.lower()
    assert "drm" not in GUARDRAILS.lower()

    # 7. No occurrence of "kb_ref" or "use_cases"
    for p in (p1, p2, p3, p4, pj, GUARDRAILS):
        assert "kb_ref" not in p
        assert "use_cases" not in p

    # 8. Prompts contain no PC-domain vocabulary without a domain context
    for p in (p1, p2, p3, p4):
        assert "PC" not in p


def test_build_guardrails_with_domain_safety_notes():
    domain = DomainContext(
        name="PC build",
        safety_notes=["overclocking or thermal-limit overrides", "DRM circumvention"],
    )
    g = build_guardrails(domain)
    assert "overclocking" in g.lower()
    assert "drm" in g.lower()
    # Without a domain, plain generic guardrails
    assert build_guardrails(None) == GUARDRAILS


def test_domain_context_propagates_into_stage_prompts():
    domain = DomainContext(name="meal plan", primary_cost_column="cost")
    p1 = build_stage1_prompt("cheap healthy week", "- protein: ...", domain=domain)
    assert "meal plan" in p1
    assert "'cost' attribute is always implicitly required" in p1

    # Without a domain: generic label, no implicit-cost invariant
    p1_generic = build_stage1_prompt("cheap healthy week", "- protein: ...")
    assert "configuration optimization problem" in p1_generic
    assert "implicitly required" not in p1_generic
