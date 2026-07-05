import json
import os

import pandas as pd

METADATA_PATH = "data/pc-csv/metadata.json"


def test_metadata_assets_and_integrity():
    assert os.path.exists(METADATA_PATH), f"{METADATA_PATH} does not exist"

    with open(METADATA_PATH, encoding="utf-8") as f:
        metadata = json.load(f)

    assert metadata.get("version") == "1.0", "Metadata version should be '1.0'"
    datasets = metadata.get("datasets", [])
    assert len(datasets) == 25, f"Expected 25 datasets, found {len(datasets)}"

    # Pack-level domain fields (all domain knowledge lives here, not in code)
    assert metadata.get("primary_cost_column") == "price"
    domain = metadata.get("domain", {})
    assert domain.get("name"), "domain.name must be declared for the PC pack"
    required_categories = metadata.get("required_categories", [])
    assert set(required_categories) == {
        "cpu",
        "motherboard",
        "memory",
        "internal-hard-drive",
        "power-supply",
        "case",
        "cpu-cooler",
        "video-card",
    }
    assert isinstance(metadata.get("safety_notes"), list) and metadata["safety_notes"]

    cost_col = metadata["primary_cost_column"]
    category_keys = set()

    for ds in datasets:
        file_name = ds.get("file_name")
        category_key = ds.get("category_key")
        record_count = ds.get("record_count")
        columns = ds.get("columns", {})

        # 1. Unique category key
        assert category_key is not None
        assert category_key not in category_keys, (
            f"Duplicate category key: {category_key}"
        )
        category_keys.add(category_key)

        # 2. Record count > 0
        assert record_count > 0, f"Record count for {category_key} must be > 0"

        # 3. CSV file must exist
        csv_path = os.path.join("data", "pc-csv", file_name)
        assert os.path.exists(csv_path), f"CSV file {csv_path} does not exist"

        # 4. Load CSV header and compare with metadata columns keys
        df_header = pd.read_csv(csv_path, nrows=0)
        csv_columns = list(df_header.columns)

        metadata_columns = list(columns.keys())

        # Assert headers match exactly
        assert csv_columns == metadata_columns, (
            f"Columns mismatch in {file_name}.\n"
            f"CSV columns: {csv_columns}\n"
            f"Metadata columns: {metadata_columns}"
        )

        # 5. Hand-authored fields presence
        assert "description" in ds and len(ds["description"]) > 0
        assert (
            "synonyms" in ds
            and isinstance(ds["synonyms"], list)
            and len(ds["synonyms"]) >= 2
        )
        assert "known_quirks" in ds and isinstance(ds["known_quirks"], list)

        # 6. Column validations
        for col_name, col_meta in columns.items():
            assert "type" in col_meta, (
                f"Type missing for column '{col_name}' in {category_key}"
            )
            assert col_meta["type"] in ("int", "float", "str", "bool")
            assert "required" in col_meta, (
                f"Required flag missing for column '{col_name}' in {category_key}"
            )

            # Check that name and the pack's cost column are always required: true
            if col_name in ("name", cost_col):
                assert col_meta["required"] is True, (
                    f"'{col_name}' must be required in {category_key}"
                )

    # 7. required_categories must all exist in the catalog
    assert set(required_categories) <= category_keys
