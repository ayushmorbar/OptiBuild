"""scripts/gen_metadata.py — Dataset metadata catalog generator."""

import glob
import json
import os

import pandas as pd

METADATA_PATH = "data/pc-csv/metadata.json"

HAND_AUTHORED_DEFAULTS = {
    "case-accessory": {
        "description": "Accessories for PC cases such as brackets, mounts, and lighting.",
        "synonyms": ["case bracket", "mount", "rgb strip"],
        "known_quirks": [],
    },
    "case-fan": {
        "description": "Cooling fans designed for PC cases to improve airflow.",
        "synonyms": ["chassis fan", "cooling fan", "rgb fan"],
        "known_quirks": [],
    },
    "case": {
        "description": "PC cases and enclosures of various form factors.",
        "synonyms": ["chassis", "enclosure", "tower"],
        "known_quirks": ["no GPU-length column"],
    },
    "cpu-cooler": {
        "description": "Air and liquid coolers to keep processors within safe temperatures.",
        "synonyms": ["heatsink", "aio cooler", "liquid cooler"],
        "known_quirks": [],
    },
    "cpu": {
        "description": "Central processing units for computing performance.",
        "synonyms": ["processor", "central processing unit", "microprocessor"],
        "known_quirks": ["no socket column"],
    },
    "external-hard-drive": {
        "description": "Portable and external storage drives.",
        "synonyms": ["external drive", "portable hdd", "external ssd"],
        "known_quirks": [],
    },
    "fan-controller": {
        "description": "Controllers for fan speed and RGB lighting.",
        "synonyms": ["fan hub", "fan controller", "rgb controller"],
        "known_quirks": [],
    },
    "headphones": {
        "description": "Headphones and headsets for audio output and input.",
        "synonyms": ["headset", "earphones", "audio headset"],
        "known_quirks": [],
    },
    "internal-hard-drive": {
        "description": "Internal storage drives including SSDs and HDDs.",
        "synonyms": ["solid state drive", "hard drive", "ssd", "hdd"],
        "known_quirks": [],
    },
    "keyboard": {
        "description": "Keyboards with various layouts and switch types.",
        "synonyms": ["input keyboard", "mechanical keyboard"],
        "known_quirks": [],
    },
    "memory": {
        "description": "System RAM modules for temporary data storage.",
        "synonyms": ["ram", "random access memory", "memory modules"],
        "known_quirks": ["packs speed='5,6000'", "packs modules='2,16'"],
    },
    "monitor": {
        "description": "Display monitors of various resolutions and refresh rates.",
        "synonyms": ["display", "screen", "gaming monitor"],
        "known_quirks": [],
    },
    "motherboard": {
        "description": "Motherboards connecting all system components.",
        "synonyms": ["mainboard", "system board", "mobo"],
        "known_quirks": [],
    },
    "mouse": {
        "description": "Optical and laser mice for cursor input.",
        "synonyms": ["pointer", "input mouse", "gaming mouse"],
        "known_quirks": [],
    },
    "optical-drive": {
        "description": "DVD, Blu-ray, and CD read/write drives.",
        "synonyms": ["dvd drive", "cd drive", "blu-ray drive"],
        "known_quirks": [],
    },
    "os": {
        "description": "Operating systems licenses like Windows and Linux.",
        "synonyms": ["operating system", "windows license"],
        "known_quirks": [],
    },
    "power-supply": {
        "description": "Power supply units delivering power to internal hardware.",
        "synonyms": ["psu", "power supply unit"],
        "known_quirks": [],
    },
    "sound-card": {
        "description": "Sound cards for high-fidelity audio processing.",
        "synonyms": ["audio card", "sound board"],
        "known_quirks": [],
    },
    "speakers": {
        "description": "External speakers for audio playback.",
        "synonyms": ["audio speakers", "pc speakers"],
        "known_quirks": [],
    },
    "thermal-paste": {
        "description": "Thermal interface materials for CPU/GPU heat transfer.",
        "synonyms": ["thermal compound", "heatsink paste"],
        "known_quirks": [],
    },
    "ups": {
        "description": "Uninterruptible power supplies for battery backup.",
        "synonyms": ["battery backup", "uninterruptible power supply"],
        "known_quirks": [],
    },
    "video-card": {
        "description": "Graphics processing units for visual rendering.",
        "synonyms": ["gpu", "graphics card", "display adapter"],
        "known_quirks": [],
    },
    "webcam": {
        "description": "Web cameras for video recording and streaming.",
        "synonyms": ["camera", "video camera"],
        "known_quirks": [],
    },
    "wired-network-card": {
        "description": "PCIe and USB wired ethernet network adapters.",
        "synonyms": ["ethernet card", "network interface card", "nic"],
        "known_quirks": [],
    },
    "wireless-network-card": {
        "description": "Wi-Fi and Bluetooth wireless network adapters.",
        "synonyms": ["wifi card", "wireless adapter", "wlan card"],
        "known_quirks": [],
    },
}


def get_inferred_type(dtype) -> str:
    dtype_str = str(dtype)
    if "int" in dtype_str:
        return "int"
    elif "float" in dtype_str:
        return "float"
    elif "bool" in dtype_str:
        return "bool"
    else:
        return "str"


def main():
    # Load existing metadata if it exists
    existing_data = {}
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, encoding="utf-8") as f:
                old_meta = json.load(f)
                for ds in old_meta.get("datasets", []):
                    existing_data[ds["category_key"]] = ds
        except Exception as e:
            print(f"Warning: could not parse existing metadata.json: {e}")

    # Scan directory for CSVs
    csv_files = glob.glob("data/pc-csv/*.csv")
    datasets = []

    for filepath in sorted(csv_files):
        filename = os.path.basename(filepath)
        category_key = os.path.splitext(filename)[0]

        try:
            df = pd.read_csv(filepath)
            record_count = len(df)
            columns_info = {
                col_name: {"type": get_inferred_type(dtype)}
                for col_name, dtype in df.dtypes.items()
            }
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            continue

        # Get existing dataset metadata or default
        old_ds = existing_data.get(category_key, {})
        default_ds = HAND_AUTHORED_DEFAULTS.get(category_key, {})

        description = old_ds.get("description") or default_ds.get("description") or ""
        synonyms = old_ds.get("synonyms") or default_ds.get("synonyms") or []
        known_quirks = (
            old_ds.get("known_quirks") or default_ds.get("known_quirks") or []
        )

        # Merge columns metadata
        old_columns = old_ds.get("columns", {})
        merged_columns = {}
        for col_name, col_meta in columns_info.items():
            old_col = old_columns.get(col_name, {})
            # Keep inferred type
            merged_col = {"type": col_meta["type"]}

            # Merge required
            if "required" in old_col:
                merged_col["required"] = old_col["required"]
            else:
                merged_col["required"] = col_name in ("name", "price")

            # Merge unit
            if "unit" in old_col:
                merged_col["unit"] = old_col["unit"]
            elif col_name == "price":
                merged_col["unit"] = "USD"
            elif col_name in ("tdp", "wattage"):
                merged_col["unit"] = "W"

            # Merge note
            if "note" in old_col:
                merged_col["note"] = old_col["note"]
            elif category_key == "cpu" and col_name == "microarchitecture":
                merged_col["note"] = (
                    "socket is NOT a column; derived via kb compatibility map (§7)"
                )

            # Keep any other old keys
            for k, v in old_col.items():
                if k not in merged_col:
                    merged_col[k] = v

            merged_columns[col_name] = merged_col

        dataset_entry = {
            "file_name": filename,
            "category_key": category_key,
            "description": description,
            "synonyms": synonyms,
            "record_count": record_count,
            "columns": merged_columns,
            "known_quirks": known_quirks,
        }
        datasets.append(dataset_entry)

    output_data = {
        "version": "1.0",
        "datasets": datasets,
    }

    os.makedirs(os.path.dirname(METADATA_PATH), exist_ok=True)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"Successfully generated {METADATA_PATH} with {len(datasets)} datasets.")


if __name__ == "__main__":
    main()
