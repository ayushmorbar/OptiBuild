"""Unit tests for the MCP Catalog search and load functions."""

import pandas as pd

from app.mcp_server.catalog import load_data, load_metadata, search_datasets
from app.mcp_server.store import store


def test_search_datasets_real_metadata():
    # 1. Load real metadata
    metadata = load_metadata()

    # 2. Exact match "cpu" -> returns cpu first with score 1.0
    matches_cpu = search_datasets("cpu", metadata)
    assert len(matches_cpu) > 0
    assert matches_cpu[0].category_key == "cpu"
    assert matches_cpu[0].score == 1.0

    # 3. Synonym "processor" -> matches cpu
    matches_syn = search_datasets("processor", metadata)
    assert any(m.category_key == "cpu" for m in matches_syn)

    # 4. Nonsense query -> returns no matches with high score
    matches_nonsense = search_datasets("xyznonsense123", metadata)
    assert all(m.score < 0.5 for m in matches_nonsense)


def test_load_data_temp_fixture(tmp_path):
    # 1. Write 2 tiny CSVs
    cpu_data = pd.DataFrame(
        {
            "name": ["Ryzen 5 7600", "Core i5-13600K"],
            "price": [199.00, 299.99],
            "core_count": [6, 14],
        }
    )
    gpu_data = pd.DataFrame(
        {
            "name": ["RX 7600 XT", "RTX 4060 Ti"],
            "price": [329.99, 399.00],
            "memory": [16, 8],
        }
    )

    cpu_csv = tmp_path / "cpu.csv"
    gpu_csv = tmp_path / "video-card.csv"

    cpu_data.to_csv(cpu_csv, index=False)
    gpu_data.to_csv(gpu_csv, index=False)

    # 2. Write a small metadata dict
    metadata = {
        "version": "1.0",
        "datasets": [
            {
                "file_name": "cpu.csv",
                "category_key": "cpu",
                "description": "Processors",
                "synonyms": ["cpu"],
                "record_count": 2,
                "columns": {
                    "name": {"type": "str", "required": True},
                    "price": {"type": "float", "required": True},
                    "core_count": {"type": "int", "required": False},
                },
            },
            {
                "file_name": "video-card.csv",
                "category_key": "video-card",
                "description": "Graphics Cards",
                "synonyms": ["gpu"],
                "record_count": 2,
                "columns": {
                    "name": {"type": "str", "required": True},
                    "price": {"type": "float", "required": True},
                    "memory": {"type": "int", "required": False},
                },
            },
        ],
    }

    # 3. Call load_data
    required_columns = {
        "cpu": ["core_count"],
        "video-card": ["memory", "unknown_col"],
    }

    report = load_data(
        categories=["cpu", "video-card"],
        required_columns=required_columns,
        metadata=metadata,
        data_dir=tmp_path,
    )

    # 4. Assert handle is returned and store holds the frames
    handle = report.dataset_handle
    assert isinstance(handle, str)
    assert len(handle) > 0

    stored_frames = store.get(handle)
    assert "cpu" in stored_frames
    assert "video-card" in stored_frames
    pd.testing.assert_frame_equal(stored_frames["cpu"], cpu_data)
    pd.testing.assert_frame_equal(stored_frames["video-card"], gpu_data)

    # 5. Assert coverage reports correct found/missing columns and row count
    coverage_map = {item.category: item for item in report.coverage}
    assert len(coverage_map) == 2

    # For cpu:
    # Required: "core_count", "price"
    # Found: "core_count", "price"
    # Missing: []
    # Row count: 2
    assert coverage_map["cpu"].row_count == 2
    assert sorted(coverage_map["cpu"].found_columns) == ["core_count", "price"]
    assert coverage_map["cpu"].missing_columns == []

    # For video-card:
    # Required: "memory", "unknown_col", "price"
    # Found: "memory", "price"
    # Missing: ["unknown_col"]
    # Row count: 2
    assert coverage_map["video-card"].row_count == 2
    assert sorted(coverage_map["video-card"].found_columns) == ["memory", "price"]
    assert coverage_map["video-card"].missing_columns == ["unknown_col"]
