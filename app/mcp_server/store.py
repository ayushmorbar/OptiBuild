"""Dataset store registry for managing in-memory DataFrames on the MCP server."""

import uuid

import pandas as pd


class DatasetStore:
    """In-memory, session-scoped registry mapping a string handle to a dictionary

    mapping category keys to pandas DataFrames.
    """

    def __init__(self):
        self._store: dict[str, dict[str, pd.DataFrame]] = {}

    def create(self, frames: dict[str, pd.DataFrame]) -> str:
        """Stores a new collection of DataFrames and returns a unique handle."""
        handle = uuid.uuid4().hex
        self._store[handle] = dict(frames)
        return handle

    def get(self, handle: str) -> dict[str, pd.DataFrame]:
        """Retrieves the collection of DataFrames associated with the handle.

        Raises KeyError if the handle is not found.
        """
        if handle not in self._store:
            raise KeyError(f"Handle '{handle}' not found in store.")
        return self._store[handle]

    def replace(self, handle: str, frames: dict[str, pd.DataFrame]) -> None:
        """Replaces the DataFrames associated with an existing handle.

        Raises KeyError if the handle is not found.
        """
        if handle not in self._store:
            raise KeyError(f"Handle '{handle}' not found in store.")
        self._store[handle] = dict(frames)

    def release(self, handle: str) -> None:
        """Removes the handle and its associated DataFrames. Idempotent."""
        self._store.pop(handle, None)


# Module-level singleton instance
store = DatasetStore()
