"""Unit tests for the MCP dataset store."""

import pandas as pd
import pytest

from app.mcp_server.store import DatasetStore


def test_store_operations():
    # Create a fresh store instance for testing to isolate from the singleton
    test_store = DatasetStore()

    df_cpu = pd.DataFrame({"name": ["Ryzen 5 7600"], "price": [199.0]})
    df_gpu = pd.DataFrame({"name": ["RX 7600"], "price": [269.0]})
    frames = {"cpu": df_cpu, "gpu": df_gpu}

    # 1. create -> get round-trip
    handle1 = test_store.create(frames)
    assert isinstance(handle1, str)
    assert len(handle1) > 0

    retrieved = test_store.get(handle1)
    assert "cpu" in retrieved
    assert "gpu" in retrieved
    pd.testing.assert_frame_equal(retrieved["cpu"], df_cpu)

    # 2. get(unknown) raises KeyError
    with pytest.raises(KeyError):
        test_store.get("unknown_handle")

    # 3. two creates give different handles
    handle2 = test_store.create(frames)
    assert handle1 != handle2

    # 4. replace updates frames
    df_cpu_updated = pd.DataFrame({"name": ["Ryzen 5 7600X"], "price": [229.0]})
    updated_frames = {"cpu": df_cpu_updated}
    test_store.replace(handle1, updated_frames)

    retrieved_updated = test_store.get(handle1)
    assert "gpu" not in retrieved_updated
    pd.testing.assert_frame_equal(retrieved_updated["cpu"], df_cpu_updated)

    # replace of unknown handle raises KeyError
    with pytest.raises(KeyError):
        test_store.replace("unknown_handle", updated_frames)

    # 5. release removes the handle
    test_store.release(handle1)
    with pytest.raises(KeyError):
        test_store.get(handle1)

    # 6. release of unknown handle does not raise
    test_store.release("unknown_handle")
