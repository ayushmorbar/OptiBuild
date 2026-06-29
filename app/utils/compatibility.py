"""Compatibility verification checks for PC components."""

def check_socket_compatible(cpu: dict, motherboard: dict) -> bool:
    """Check if the CPU socket matches the motherboard socket."""
    return cpu.get("specs", {}).get("socket") == motherboard.get("specs", {}).get("socket")

def check_ram_compatible(ram: dict, motherboard: dict) -> bool:
    """Check if the RAM generation matches the motherboard ram_generation."""
    return ram.get("specs", {}).get("generation") == motherboard.get("specs", {}).get("ram_generation")

def check_case_compatible(motherboard: dict, case: dict) -> bool:
    """Check if the case supports the motherboard's form factor."""
    supported_form_factors = case.get("specs", {}).get("supported_form_factors", [])
    mb_form_factor = motherboard.get("specs", {}).get("form_factor")
    return mb_form_factor in supported_form_factors

def check_cooler_socket_compatible(cpu: dict, cooler: dict) -> bool:
    """Check if the CPU cooler supports the CPU's socket."""
    supported_sockets = cooler.get("specs", {}).get("supported_sockets", [])
    cpu_socket = cpu.get("specs", {}).get("socket")
    return cpu_socket in supported_sockets

def check_psu_wattage_compatible(cpu: dict, gpu: dict, psu: dict) -> bool:
    """Check if the PSU wattage is sufficient with a 20% safety margin."""
    cpu_power = cpu.get("specs", {}).get("power_draw_w", 0)
    gpu_power = gpu.get("specs", {}).get("power_draw_w", 0)
    base_power = 50  # estimated base system consumption
    
    required_wattage = 1.2 * (cpu_power + gpu_power + base_power)
    psu_wattage = psu.get("specs", {}).get("wattage", 0)
    
    return psu_wattage >= required_wattage

def check_build_compatible(cpu: dict, motherboard: dict, ram: dict, gpu: dict, cooler: dict, psu: dict, case: dict) -> bool:
    """Check if all components in a build are compatible with each other."""
    return (
        check_socket_compatible(cpu, motherboard) and
        check_ram_compatible(ram, motherboard) and
        check_case_compatible(motherboard, case) and
        check_cooler_socket_compatible(cpu, cooler) and
        check_psu_wattage_compatible(cpu, gpu, psu)
    )
