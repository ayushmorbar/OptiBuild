from app.utils.compatibility import (
    check_socket_compatible,
    check_ram_compatible,
    check_case_compatible,
    check_cooler_socket_compatible,
    check_psu_wattage_compatible,
    check_build_compatible
)

# Mock components for testing
cpu_am5 = {"specs": {"socket": "AM5", "power_draw_w": 65}}
cpu_lga1700 = {"specs": {"socket": "LGA1700", "power_draw_w": 125}}

gpu_high = {"specs": {"power_draw_w": 250}}
gpu_low = {"specs": {"power_draw_w": 100}}

mb_am5_ddr5_atx = {"specs": {"socket": "AM5", "form_factor": "ATX", "ram_generation": "DDR5"}}
mb_lga_ddr4_matx = {"specs": {"socket": "LGA1700", "form_factor": "Micro-ATX", "ram_generation": "DDR4"}}

ram_ddr5 = {"specs": {"generation": "DDR5"}}
ram_ddr4 = {"specs": {"generation": "DDR4"}}

case_atx = {"specs": {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"]}}
case_itx = {"specs": {"supported_form_factors": ["Mini-ITX"]}}

cooler_am5 = {"specs": {"supported_sockets": ["AM5"]}}
cooler_both = {"specs": {"supported_sockets": ["AM5", "LGA1700"]}}

psu_600 = {"specs": {"wattage": 600}}
psu_400 = {"specs": {"wattage": 400}}

def test_socket_compatibility():
    assert check_socket_compatible(cpu_am5, mb_am5_ddr5_atx) is True
    assert check_socket_compatible(cpu_am5, mb_lga_ddr4_matx) is False

def test_ram_compatibility():
    assert check_ram_compatible(ram_ddr5, mb_am5_ddr5_atx) is True
    assert check_ram_compatible(ram_ddr5, mb_lga_ddr4_matx) is False
    assert check_ram_compatible(ram_ddr4, mb_lga_ddr4_matx) is True

def test_case_compatibility():
    assert check_case_compatible(mb_am5_ddr5_atx, case_atx) is True
    assert check_case_compatible(mb_am5_ddr5_atx, case_itx) is False

def test_cooler_compatibility():
    assert check_cooler_socket_compatible(cpu_am5, cooler_am5) is True
    assert check_cooler_socket_compatible(cpu_lga1700, cooler_am5) is False
    assert check_cooler_socket_compatible(cpu_lga1700, cooler_both) is True

def test_psu_compatibility():
    # cpu (65) + gpu (100) + base (50) = 215. Required: 1.2 * 215 = 258W.
    # PSU 400W should be compatible
    assert check_psu_wattage_compatible(cpu_am5, gpu_low, psu_400) is True
    
    # cpu (125) + gpu (250) + base (50) = 425. Required: 1.2 * 425 = 510W.
    # PSU 400W should NOT be compatible, PSU 600W should be
    assert check_psu_wattage_compatible(cpu_lga1700, gpu_high, psu_400) is False
    assert check_psu_wattage_compatible(cpu_lga1700, gpu_high, psu_600) is True

def test_full_build_compatibility():
    assert check_build_compatible(
        cpu=cpu_am5,
        motherboard=mb_am5_ddr5_atx,
        ram=ram_ddr5,
        gpu=gpu_low,
        cooler=cooler_both,
        psu=psu_600,
        case=case_atx
    ) is True

from app.agent import sanitize_budget

def test_sanitize_budget():
    assert sanitize_budget("$1400") == 1400.0
    assert sanitize_budget("1200.50 USD") == 1200.50
    assert sanitize_budget("1500") == 1500.0
    assert sanitize_budget("invalid") == 0.0
    assert sanitize_budget("") == 0.0
