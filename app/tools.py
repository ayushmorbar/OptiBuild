"""Deterministic PC build solver tool for the Optimization Agent."""

import os
import json
import itertools
from typing import Optional, List, Dict, Any

from app.utils.compatibility import check_build_compatible

def _load_components() -> Dict[str, List[Dict[str, Any]]]:
    """Load components from the database file."""
    db_path = os.path.join(os.path.dirname(__file__), "data", "components.json")
    with open(db_path, "r") as f:
        return json.load(f)

def _match_pre_owned(pre_owned_name: str, category_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Match a pre-owned component name to an item in the database."""
    name_lower = pre_owned_name.lower().strip()
    # 1. Exact ID match
    for item in category_items:
        if name_lower == item["id"].lower():
            return item
    # 2. Substring match on name
    for item in category_items:
        if name_lower in item["name"].lower() or item["name"].lower() in name_lower:
            return item
    return None

def _calculate_score(build: Dict[str, Dict[str, Any]], purpose: str) -> float:
    """Calculate heuristic score for a build based on target purpose."""
    cpu = build["cpu"]
    gpu = build["gpu"]
    ram = build["ram"]
    storage = build["storage"]
    
    cpu_perf = cpu.get("specs", {}).get("performance_rating", 50)
    cpu_cores = cpu.get("specs", {}).get("cores", 4)
    gpu_perf = gpu.get("specs", {}).get("performance_rating", 50)
    gpu_vram = gpu.get("specs", {}).get("vram_gb", 4)
    ram_cap = ram.get("specs", {}).get("capacity_gb", 8)
    storage_cap = storage.get("specs", {}).get("capacity_gb", 500)
    
    purpose_lower = purpose.lower()
    
    if "gaming" in purpose_lower:
        return (gpu_perf * 0.6) + (cpu_perf * 0.3) + (ram_cap * 0.1)
    elif "ai" in purpose_lower or "deep learning" in purpose_lower or "training" in purpose_lower:
        return (gpu_vram * 7.0) + (gpu_perf * 0.2) + (cpu_perf * 0.1)
    else:
        # Office / Development / Workstation
        gpu_price = gpu.get("price", 0.0)
        return (cpu_cores * 6.0) + (ram_cap * 3.0) + (storage_cap / 100.0) - (gpu_price * 0.05)

def find_optimal_builds(
    budget: float,
    purpose: str,
    cpu_brand: Optional[str] = None,
    gpu_brand: Optional[str] = None,
    form_factor: Optional[str] = None,
    cooling_type: Optional[str] = None,
    pre_owned_parts: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Finds up to 3 optimal, fully compatible PC configurations under a given budget.

    Args:
        budget: The maximum budget for the PC build in USD.
        purpose: The target usage of the PC (e.g., Gaming, AI training, Office).
        cpu_brand: Optional brand preference for CPU (e.g., AMD, Intel).
        gpu_brand: Optional brand preference for GPU (e.g., NVIDIA, AMD).
        form_factor: Optional size preference (e.g., ATX, Micro-ATX, Mini-ITX).
        cooling_type: Optional CPU cooler preference (e.g., air, liquid).
        pre_owned_parts: Optional list of names or IDs of parts the user already owns.

    Returns:
        A dictionary containing the list of optimal builds and any summary information.
    """
    try:
        data = _load_components()
    except Exception as e:
        return {"error": f"Failed to load components database: {str(e)}"}
        
    categories = ["cpus", "gpus", "motherboards", "ram", "storage", "psus", "cases", "coolers"]
    
    # Process pre-owned parts
    pre_owned_by_category = {}
    if pre_owned_parts:
        for part_name in pre_owned_parts:
            matched_item = None
            matched_cat = None
            for cat in categories:
                matched_item = _match_pre_owned(part_name, data[cat])
                if matched_item:
                    matched_cat = cat
                    break
            if matched_item:
                pre_owned_by_category[matched_cat] = matched_item

    # Filter components based on inputs
    filtered = {}
    
    # CPUs
    if "cpus" in pre_owned_by_category:
        filtered["cpus"] = [pre_owned_by_category["cpus"]]
    else:
        filtered["cpus"] = data["cpus"]
        if cpu_brand:
            filtered["cpus"] = [c for c in filtered["cpus"] if c["brand"].lower() == cpu_brand.lower()]

    # GPUs
    if "gpus" in pre_owned_by_category:
        filtered["gpus"] = [pre_owned_by_category["gpus"]]
    else:
        filtered["gpus"] = data["gpus"]
        if gpu_brand:
            filtered["gpus"] = [g for g in filtered["gpus"] if g["brand"].lower() == gpu_brand.lower()]

    # Motherboards
    if "motherboards" in pre_owned_by_category:
        filtered["motherboards"] = [pre_owned_by_category["motherboards"]]
    else:
        filtered["motherboards"] = data["motherboards"]
        if form_factor:
            filtered["motherboards"] = [m for m in filtered["motherboards"] if m["specs"]["form_factor"].lower() == form_factor.lower()]

    # RAM
    if "ram" in pre_owned_by_category:
        filtered["ram"] = [pre_owned_by_category["ram"]]
    else:
        filtered["ram"] = data["ram"]

    # Storage
    if "storage" in pre_owned_by_category:
        filtered["storage"] = [pre_owned_by_category["storage"]]
    else:
        filtered["storage"] = data["storage"]

    # PSUs
    if "psus" in pre_owned_by_category:
        filtered["psus"] = [pre_owned_by_category["psus"]]
    else:
        filtered["psus"] = data["psus"]

    # Cases
    if "cases" in pre_owned_by_category:
        filtered["cases"] = [pre_owned_by_category["cases"]]
    else:
        filtered["cases"] = data["cases"]
        if form_factor:
            filtered["cases"] = [c for c in filtered["cases"] if form_factor.lower() in [f.lower() for f in c["specs"]["supported_form_factors"]]]

    # Coolers
    if "coolers" in pre_owned_by_category:
        filtered["coolers"] = [pre_owned_by_category["coolers"]]
    else:
        filtered["coolers"] = data["coolers"]
        if cooling_type:
            filtered["coolers"] = [c for c in filtered["coolers"] if c["specs"]["type"].lower() == cooling_type.lower()]

    # Generate combinations and run optimization
    valid_builds = []
    
    # We do a product of all lists
    combinations = itertools.product(
        filtered["cpus"],
        filtered["gpus"],
        filtered["motherboards"],
        filtered["ram"],
        filtered["storage"],
        filtered["psus"],
        filtered["cases"],
        filtered["coolers"]
    )
    
    for comb in combinations:
        cpu, gpu, motherboard, ram, storage, psu, case, cooler = comb
        
        # Check compatibility
        compatible = check_build_compatible(
            cpu=cpu,
            motherboard=motherboard,
            ram=ram,
            gpu=gpu,
            cooler=cooler,
            psu=psu,
            case=case
        )
        
        if not compatible:
            continue
            
        # Calculate cost
        # Pre-owned items contribute $0 to the cost
        build_cost = 0.0
        parts_list = {
            "cpu": cpu, "gpu": gpu, "motherboard": motherboard, "ram": ram,
            "storage": storage, "psu": psu, "case": case, "cooler": cooler
        }
        
        for cat_name, part in parts_list.items():
            if cat_name in pre_owned_by_category:
                # Pre-owned
                build_cost += 0.0
            else:
                build_cost += part["price"]
                
        if build_cost > budget:
            continue
            
        # Score the build
        score = _calculate_score(parts_list, purpose)
        
        valid_builds.append({
            "parts": {
                "CPU": {"name": cpu["name"], "price": 0.0 if "cpus" in pre_owned_by_category else cpu["price"], "link": cpu["link"], "pre_owned": "cpus" in pre_owned_by_category},
                "GPU": {"name": gpu["name"], "price": 0.0 if "gpus" in pre_owned_by_category else gpu["price"], "link": gpu["link"], "pre_owned": "gpus" in pre_owned_by_category},
                "Motherboard": {"name": motherboard["name"], "price": 0.0 if "motherboards" in pre_owned_by_category else motherboard["price"], "link": motherboard["link"], "pre_owned": "motherboards" in pre_owned_by_category},
                "RAM": {"name": ram["name"], "price": 0.0 if "ram" in pre_owned_by_category else ram["price"], "link": ram["link"], "pre_owned": "ram" in pre_owned_by_category},
                "Storage": {"name": storage["name"], "price": 0.0 if "storage" in pre_owned_by_category else storage["price"], "link": storage["link"], "pre_owned": "storage" in pre_owned_by_category},
                "PSU": {"name": psu["name"], "price": 0.0 if "psus" in pre_owned_by_category else psu["price"], "link": psu["link"], "pre_owned": "psus" in pre_owned_by_category},
                "Case": {"name": case["name"], "price": 0.0 if "cases" in pre_owned_by_category else case["price"], "link": case["link"], "pre_owned": "cases" in pre_owned_by_category},
                "Cooler": {"name": cooler["name"], "price": 0.0 if "coolers" in pre_owned_by_category else cooler["price"], "link": cooler["link"], "pre_owned": "coolers" in pre_owned_by_category}
            },
            "total_cost": build_cost,
            "score": score
        })
        
    # Sort builds by score descending, then by cost ascending
    valid_builds.sort(key=lambda x: (-x["score"], x["total_cost"]))
    
    # Return top 3
    results = valid_builds[:3]
    return {
        "configurations": results,
        "count": len(results),
        "total_valid_options": len(valid_builds)
    }
