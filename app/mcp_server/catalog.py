"""MCP Catalog functions for searching datasets and loading data."""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from app.mcp_server import pack
from app.mcp_server.store import store
from app.schema import (
    CoverageItem,
    DatasetMatch,
    DomainContext,
    LoadReport,
    PivotSchema,
)

# Minimum fuzzy score required to auto-rewrite a category to a matched dataset key.
# search_datasets itself keeps its own lower threshold (0.5) for surfacing candidates.
RESOLVE_THRESHOLD = 0.7

_AGG_NAMES = {"sum", "min", "max", "avg", "count"}
_TERM_RE = re.compile(r"[a-z0-9_-]+(?:\.[a-z0-9_]+)?")


def load_metadata(path: Path | None = None) -> dict:
    """Load the metadata.json catalog of the active dataset pack."""
    path = path or pack.get_metadata_path()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_domain_context(metadata: dict) -> DomainContext:
    """Extract the pack's domain descriptor (name, description, safety notes, cost column)."""
    d = metadata.get("domain") or {}
    return DomainContext(
        name=d.get("name", "configuration"),
        description=d.get("description", ""),
        safety_notes=metadata.get("safety_notes", []),
        primary_cost_column=metadata.get("primary_cost_column"),
    )


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


_SUMMARY_DESC_MAX = 60


def build_catalog_summary(metadata: dict, categories: list[str] | None = None) -> str:
    """One compact line per dataset (key, short description, typed columns) for LLM prompts.

    Deliberately lean to avoid context bloating: synonyms are NOT included (user
    vocabulary is resolved server-side by resolve_schema_categories), descriptions
    are truncated, and `categories` optionally restricts the summary to a subset
    (e.g. stage 4 only needs the categories selected at stage 1).
    """
    wanted = set(categories) if categories is not None else None
    lines = []
    for ds in metadata.get("datasets", []):
        if wanted is not None and ds["category_key"] not in wanted:
            continue
        cols = ", ".join(
            f"{name}({info.get('type', 'str')}"
            + (f", {info['unit']}" if info.get("unit") else "")
            + ")"
            for name, info in ds.get("columns", {}).items()
        )
        desc = ds.get("description", "")
        if len(desc) > _SUMMARY_DESC_MAX:
            desc = desc[: _SUMMARY_DESC_MAX - 1].rstrip() + "…"
        lines.append(f"- {ds['category_key']}: {desc} | columns: {cols}")
    return "\n".join(lines)


def resolve_schema_categories(
    schema: PivotSchema, metadata: dict
) -> tuple[PivotSchema, dict[str, str], list[str]]:
    """Resolve each decision-variable category to the best-matching dataset key.

    Categories already matching a catalog key are untouched. Others are resolved
    via search_datasets (exact -> synonym -> fuzzy); fuzzy matches below
    RESOLVE_THRESHOLD are not rewritten. The whole schema (formulas, dependencies,
    objectives, constraint sides) is rewritten to the resolved keys and re-validated.

    Returns (schema, mapping {original: resolved}, unresolved_categories).
    Unresolved categories keep their original key, so downstream Gate 1
    produces MISSING_DATA for them — no new failure path.
    """
    known_keys = {ds["category_key"] for ds in metadata.get("datasets", [])}
    mapping: dict[str, str] = {}
    unresolved: list[str] = []
    taken = {
        dv.category for dv in schema.decision_variables if dv.category in known_keys
    }

    for dv in schema.decision_variables:
        if dv.category in known_keys:
            continue
        matches = search_datasets(dv.category, metadata)
        best = matches[0] if matches else None
        if (
            best is not None
            and best.score >= RESOLVE_THRESHOLD
            and best.category_key not in taken  # anti-collision guard
        ):
            mapping[dv.category] = best.category_key
            taken.add(best.category_key)
        else:
            unresolved.append(dv.category)

    if not mapping:
        return schema, {}, unresolved

    def sub_term(term: str) -> str:
        if "." in term:
            cat, attr = term.split(".", 1)
            return f"{mapping.get(cat, cat)}.{attr}"
        return term  # derived-variable names pass through unchanged

    data = schema.model_dump()
    for dv in data["decision_variables"]:
        dv["category"] = mapping.get(dv["category"], dv["category"])
    for dv in data["derived_variables"]:
        dv["formula"] = _TERM_RE.sub(
            lambda m: m.group(0) if m.group(0) in _AGG_NAMES else sub_term(m.group(0)),
            dv["formula"],
        )
        dv["dependencies"] = [mapping.get(d, d) for d in dv["dependencies"]]
    for obj in data["objectives"]:
        obj["target_variable"] = sub_term(obj["target_variable"])
    for c in data["constraints"]:
        c["left_side"] = sub_term(c["left_side"])
        if c["right_side"].get("kind") == "var_ref":
            c["right_side"]["ref"] = sub_term(c["right_side"]["ref"])

    return PivotSchema.model_validate(data), mapping, unresolved


def load_data(
    categories: list[str],
    required_columns: dict[str, list[str]],
    metadata: dict,
    data_dir: Path | None = None,
) -> LoadReport:
    """Load requested category datasets into store and return a LoadReport."""
    data_dir = data_dir or pack.get_data_dir()
    coverage = []
    frames = {}

    # The pack's primary cost column (if declared) is implicitly required
    primary_cost_column = metadata.get("primary_cost_column")

    for category in categories:
        req_cols = set(required_columns.get(category, []))
        if primary_cost_column:
            req_cols.add(primary_cost_column)

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
