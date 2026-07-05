"""Unit tests for the dynamic cleaning planning prompt template builder."""

from solver_app.dynamic_clean_prompt import build_dynamic_clean_prompt


def test_build_dynamic_clean_prompt():
    user_request = "Drop all CPUs with price above 500"
    categories = ["cpu", "memory"]
    columns_by_category = {
        "cpu": ["name", "price", "tdp"],
        "memory": ["name", "price"],
    }

    prompt = build_dynamic_clean_prompt(user_request, categories, columns_by_category)

    # 1. User request wrapped in tag (treated as data)
    assert f"<user_request>\n{user_request}\n</user_request>" in prompt

    # 2. Lists the full closed CleanOp vocabulary (5 ops)
    assert "filter_contains" in prompt
    assert "filter_rows" in prompt
    assert "drop_nulls" in prompt
    assert "map_values" in prompt
    assert "clip_range" in prompt

    # 3. Role: translate qualitative/keyword requirements into filters
    assert "qualitative" in prompt.lower()
    assert "Intel" in prompt  # the brand example anchors the filter_contains usage

    # 4. Provided categories and columns appear
    assert "- Category: cpu, Columns: name, price, tdp" in prompt
    assert "- Category: memory, Columns: name, price" in prompt

    # 5. Guardrails retained
    assert "Never invent values" in prompt
    assert "empty list" in prompt


def test_build_dynamic_clean_prompt_with_samples():
    prompt = build_dynamic_clean_prompt(
        "an Intel CPU",
        ["cpu"],
        {"cpu": ["name", "price"]},
        samples_by_category={"cpu": "name: Intel Xeon, AMD Ryzen 5"},
    )
    assert "Sample values: name: Intel Xeon, AMD Ryzen 5" in prompt
