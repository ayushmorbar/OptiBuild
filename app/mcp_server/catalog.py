"""MCP Catalog functions for searching datasets and loading data."""

import json
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from app.mcp_server.store import store
from app.schema import CoverageItem, DatasetMatch, LoadReport

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "pc-csv"
METADATA_PATH = DATA_DIR / "metadata.json"


def load_metadata(path: Path = METADATA_PATH) -> dict:
    """Load the metadata.json file containing dataset schemas."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def search_datasets(query: str, metadata: dict) -> list[DatasetMatch]:
    """Search for datasets matching the query using case-insensitive matching

    with a priority order:
    1. Exact category_key match (score 1.0)
    2. Exact synonym match (score 0.9)
    3. Fuzzy match over category_key, synonyms, and description (score = ratio)
    """
    query_lower = query.lower()
    matches = []

    for ds in metadata.get("datasets", []):
        category_key = ds["category_key"]
        synonyms = ds.get("synonyms", [])
        description = ds.get("description", "")
        file_name = ds["file_name"]

        columns = {
            col_name: col_info["type"] for col_name, col_info in ds["columns"].items()
        }

        score = 0.0

        # 1. Exact category_key match
        if query_lower == category_key.lower():
            score = 1.0
        # 2. Exact synonym match
        elif any(query_lower == syn.lower() for syn in synonyms):
            score = 0.9
        # 3. Fuzzy match (SequenceMatcher)
        else:
            ratios = [SequenceMatcher(None, query_lower, category_key.lower()).ratio()]
            for syn in synonyms:
                ratios.append(SequenceMatcher(None, query_lower, syn.lower()).ratio())
            ratios.append(
                SequenceMatcher(None, query_lower, description.lower()).ratio()
            )
            max_ratio = max(ratios)
            if max_ratio >= 0.5:
                score = max_ratio

        if score > 0.0:
            matches.append(
                DatasetMatch(
                    category_key=category_key,
                    file_name=file_name,
                    description=description,
                    columns=columns,
                    score=score,
                )
            )

    # RAG Fallback stub extension point:
    # RAG/embeddings fallback triggers only when catalog exceeds ~50 datasets
    # or exact+synonym matching fails. Not needed for current V1 catalog size.

    # Sort desc by score
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches


def load_data(
    categories: list[str],
    required_columns: dict[str, list[str]],
    metadata: dict,
    data_dir: Path = DATA_DIR,
) -> LoadReport:
    """Load requested category datasets into store and return a LoadReport."""
    coverage = []
    frames = {}

    for category in categories:
        # Resolve required columns (price is implicitly required)
        req_cols = set(required_columns.get(category, []))
        req_cols.add("price")

        actual_cols = set()
        row_count = 0
        df = None

        # Find dataset entry
        ds_entry = None
        for ds in metadata.get("datasets", []):
            if ds["category_key"] == category:
                ds_entry = ds
                break

        if ds_entry is not None:
            csv_path = data_dir / ds_entry["file_name"]
            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    actual_cols = set(df.columns)
                    row_count = len(df)
                except Exception:
                    # Treat as unread / empty
                    pass

        if df is not None:
            frames[category] = df

        found_cols = sorted(req_cols.intersection(actual_cols))
        missing_cols = sorted(req_cols.difference(actual_cols))

        coverage.append(
            CoverageItem(
                category=category,
                found_columns=found_cols,
                missing_columns=missing_cols,
                row_count=row_count,
            )
        )

    # Store successfully read frames as one single dataset_handle
    handle = store.create(frames)

    return LoadReport(dataset_handle=handle, coverage=coverage)
