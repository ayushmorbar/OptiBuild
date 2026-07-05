"""Dataset-pack resolution: which data directory and metadata the system runs against.

A "dataset pack" is a directory of CSVs plus a metadata.json catalog. All domain
knowledge (categories, columns, required categories, primary cost column, safety
notes) lives in the pack — the engine itself is domain-agnostic. The active pack
is selected via the GAUSS_DATA_DIR environment variable (absolute path or path
relative to the repo root); it defaults to the bundled PC-components demo pack.
"""

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK_DIR = _REPO_ROOT / "data" / "pc-csv"
ENV_VAR = "GAUSS_DATA_DIR"


def get_data_dir() -> Path:
    """Return the active pack directory ($GAUSS_DATA_DIR or the default pack).

    Resolved lazily on every call so tests and deployments can switch packs
    via the environment without re-importing modules.
    """
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        return DEFAULT_PACK_DIR
    p = Path(raw)
    return p if p.is_absolute() else (_REPO_ROOT / p)


def get_metadata_path() -> Path:
    """Return the metadata.json path of the active pack."""
    return get_data_dir() / "metadata.json"
