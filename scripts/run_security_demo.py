"""Security show-case demonstrating rejections of hostile, malformed, and destructive operations."""

import json

import pandas as pd

from app.mcp_server.safe_ops import clean_dynamic, query_data
from app.mcp_server.store import store


def main():
    # Setup initial mock dataset in the store
    tiny_frames = {
        "cpu": pd.DataFrame(
            [
                {"name": "Intel Core i5-12400F", "price": 150.0, "tdp": 65},
                {"name": "AMD Ryzen 5 5600X", "price": 160.0, "tdp": 65},
                {"name": "Intel Core i9-12900K", "price": 400.0, "tdp": 125},
                {"name": "AMD Ryzen 9 5900X", "price": 350.0, "tdp": 105},
            ]
        ),
        "memory": pd.DataFrame(
            [
                {"name": "Corsair Vengeance LPX 16GB", "price": 50.0, "capacity": 16},
                {"name": "G.Skill Ripjaws V 32GB", "price": 90.0, "capacity": 32},
            ]
        ),
    }
    handle = store.create(tiny_frames)

    # 1. Hostile query expressions in query_data / safe_query
    print("======================================================================")
    print("1. Hostile query expression rejection:")
    print("======================================================================")
    hostile_exprs = [
        "price.__class__",
        "price > @budget",
        "price > 0 and os.system('x')",
    ]
    for expr in hostile_exprs:
        try:
            query_data(handle, "cpu", expr=expr)
            print(f"FAIL: Expression '{expr}' was NOT rejected!")
        except Exception as e:
            print(f"Expression: {expr}")
            print(f"Result: Rejected with reason: {e}")
            print("-" * 50)

    # 2. Closed-vocabulary violation
    print("\n======================================================================")
    print("2. Closed-vocabulary violation rejection:")
    print("======================================================================")
    malformed_ops = [
        {
            "op": "unknown_op",
            "category": "cpu",
        },
        {
            "op": "clip_range",
            "category": "cpu",
            "column": "price",
            "min": 100,
            "extra_field": "not_allowed",
        },
    ]
    report = clean_dynamic(handle, malformed_ops)
    print(json.dumps(report.model_dump(), indent=2))

    # 3. Destructive batch (filter dropping >90% of rows)
    print("\n======================================================================")
    print("3. Destructive batch drop detection and automatic revert:")
    print("======================================================================")
    destructive_ops = [
        {
            "op": "filter_rows",
            "category": "cpu",
            "expr": "price > 1000.0",  # Drops 100% of rows
        }
    ]
    report = clean_dynamic(handle, destructive_ops)
    print(json.dumps(report.model_dump(), indent=2))

    # 4. Legitimate operation
    print("\n======================================================================")
    print("4. Legitimate clean operation execution:")
    print("======================================================================")
    legit_ops = [
        {
            "op": "clip_range",
            "category": "cpu",
            "column": "price",
            "min": 100.0,
            "max": 380.0,
        }
    ]
    report = clean_dynamic(handle, legit_ops)
    print(json.dumps(report.model_dump(), indent=2))


if __name__ == "__main__":
    main()
