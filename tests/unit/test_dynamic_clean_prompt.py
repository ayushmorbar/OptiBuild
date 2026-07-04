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

    # 1. User request wrapped in tag
    assert f"<user_request>\n{user_request}\n</user_request>" in prompt

    # 2. Lists 4 CleanOp names
    assert "filter_rows" in prompt
    assert "drop_nulls" in prompt
    assert "map_values" in prompt
    assert "clip_range" in prompt

    # 3. Mentions query_data and aggregates first
    assert "query_data" in prompt
    assert "sample" in prompt
    assert "describe" in prompt
    assert "value_counts" in prompt

    # 4. Provided categories and columns appear
    assert "- Category: cpu, Columns: name, price, tdp" in prompt
    assert "- Category: memory, Columns: name, price" in prompt
