from app.tools import find_optimal_builds

def test_find_optimal_builds_success():
    """Verify that solver returns successful builds for a standard budget."""
    result = find_optimal_builds(
        budget=1400.0,
        purpose="gaming"
    )
    
    assert "error" not in result
    assert result["count"] > 0
    
    # Check that all configurations are under the budget
    for config in result["configurations"]:
        assert config["total_cost"] <= 1400.0
        assert len(config["parts"]) == 8 # has all 8 components
        assert config["score"] > 0

def test_find_optimal_builds_brand_preferences():
    """Verify that solver respects CPU/GPU brand preferences."""
    result = find_optimal_builds(
        budget=1500.0,
        purpose="gaming",
        cpu_brand="Intel",
        gpu_brand="NVIDIA"
    )
    
    assert "error" not in result
    
    # Check that the parts list has matching brands
    # Since find_optimal_builds doesn't return brand in output parts, we check names indirectly
    for config in result["configurations"]:
        assert "Intel" in config["parts"]["CPU"]["name"]
        assert "GeForce" in config["parts"]["GPU"]["name"] or "RTX" in config["parts"]["GPU"]["name"]

def test_find_optimal_builds_too_low_budget():
    """Verify that solver returns 0 configurations when budget is extremely low."""
    result = find_optimal_builds(
        budget=200.0,
        purpose="office"
    )
    
    assert "error" not in result
    assert result["count"] == 0
    assert len(result["configurations"]) == 0
