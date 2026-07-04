"""Unit tests for the TOPSIS ranking functionality."""

from app.mcp_server.ranking import topsis_rank


def test_topsis_rank_scenarios():
    # 1. Single-candidate matrix returns index 0
    idx, scores = topsis_rank([[10.0, 5.0]], [1.0, 1.0], ["maximize", "minimize"])
    assert idx == 0
    assert scores == [1.0]

    # 2. Two alternatives, two criteria: C0 (minimize), C1 (maximize)
    # Alt 0: [100.0, 50.0]
    # Alt 1: [200.0, 150.0]
    matrix = [[100.0, 50.0], [200.0, 150.0]]
    directions = ["minimize", "maximize"]

    # Shifting weights changes the winner:
    # Focus heavily on performance (C1)
    idx_perf, _ = topsis_rank(matrix, [0.1, 0.9], directions)
    assert idx_perf == 1

    # Focus heavily on price (C0)
    idx_price, _ = topsis_rank(matrix, [0.9, 0.1], directions)
    assert idx_price == 0
