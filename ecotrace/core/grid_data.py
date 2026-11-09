"""
EcoTrace Global Grid Carbon Data
Maintains realistic regional carbon intensities, renewable mixes, and 24-hour diurnal curve models
based on public grid data (Electricity Maps, EPA eGRID, and Green Software Foundation dataset).
"""

import math
from typing import Dict, List
from ecotrace.core.models import GridRegion, CloudProvider


# Baseline carbon intensities in gCO2eq/kWh and typical PUE
GRID_REGIONS_DATABASE: Dict[str, Dict] = {
    "bd-tier4-gazipur": {
        "name": "Bangladesh National Tier-IV Datacenter (Gazipur)",
        "country": "Bangladesh",
        "provider": CloudProvider.ON_PREM,
        "base_intensity": 585.0,  # Bangladesh National Grid (BPDB mix: Natural Gas + HFO + Coal)
        "renewable_pct": 4.5,
        "pue": 1.28,  # Modern Tier-IV facility in Bangabandhu Hi-Tech City, Kaliakoir
        "sources": {"Natural Gas": 52, "Coal": 21, "Fuel Oil (HFO/HSD)": 18, "Imports": 5, "Solar/Hydro": 4},
        "diurnal_swing": 0.28,  # High evening peaker plant spike (6 PM - 11 PM)
        "grid_operator": "PGCB / BPDB",
        "currency": "BDT",
        "kwh_tariff_bdt": 11.85  # Commercial/Industrial server tariff
    },
    "bd-dhaka-colocation": {
        "name": "Dhaka BDIX Colocation & Telecom Hub (Mohakhali)",
        "country": "Bangladesh",
        "provider": CloudProvider.ON_PREM,
        "base_intensity": 615.0,
        "renewable_pct": 3.8,
        "pue": 1.48,  # Urban datacenter with standard cooling
        "sources": {"Natural Gas": 50, "Coal": 22, "Fuel Oil (HFO/HSD)": 20, "Solar/Hydro": 4, "Imports": 4},
        "diurnal_swing": 0.32,
        "grid_operator": "DPDC / DESCO",
        "currency": "BDT",
        "kwh_tariff_bdt": 12.50
    },
    "bd-enterprise-dg": {
        "name": "Dhaka Enterprise Server (Grid + Diesel Generator)",
        "country": "Bangladesh",
        "provider": CloudProvider.ON_PREM,
        "base_intensity": 780.0,  # Elevated due to backup Diesel Generator (DG) runs during load shedding
        "renewable_pct": 2.0,
        "pue": 1.65,
        "sources": {"Diesel Generator": 28, "Natural Gas": 38, "Coal": 18, "Fuel Oil": 14, "Renewables": 2},
        "diurnal_swing": 0.35,
        "grid_operator": "DESCO / Captive DG",
        "currency": "BDT",
        "kwh_tariff_bdt": 22.00  # Diesel generation costs ~22-26 BDT/kWh
    },
    "ap-south-1": {
        "name": "AWS Asia Pacific (Mumbai) - Closest AWS Node",
        "country": "India",
        "provider": CloudProvider.AWS,
        "base_intensity": 640.0,  # Central Indian grid (high coal share)
        "renewable_pct": 22.0,
        "pue": 1.15,
        "sources": {"Coal": 68, "Solar/Wind": 18, "Hydro": 9, "Gas/Nuclear": 5},
        "diurnal_swing": 0.25,
        "grid_operator": "POWERGRID",
        "currency": "USD",
        "kwh_tariff_bdt": 12.00
    },
    "ap-southeast-1": {
        "name": "AWS Asia Pacific (Singapore) - Regional Hub",
        "country": "Singapore",
        "provider": CloudProvider.AWS,
        "base_intensity": 415.0,  # Natural gas baseload
        "renewable_pct": 7.0,
        "pue": 1.25,
        "sources": {"Gas": 92, "Solar": 5, "Other": 3},
        "diurnal_swing": 0.12,
        "grid_operator": "EMA",
        "currency": "USD",
        "kwh_tariff_bdt": 14.50
    },
    "eu-north-1": {
        "name": "AWS Europe North (Stockholm - Hydro & Nuclear)",
        "country": "Sweden",
        "provider": CloudProvider.AWS,
        "base_intensity": 22.0,  # Clean Nordic green baseload
        "renewable_pct": 94.0,
        "pue": 1.10,
        "sources": {"Hydro": 45, "Nuclear": 35, "Wind": 14, "Fossil": 6},
        "diurnal_swing": 0.08,
        "grid_operator": "Svenska Kraftnät",
        "currency": "USD",
        "kwh_tariff_bdt": 9.20
    },
    "ca-central-1": {
        "name": "AWS Canada Central (Montreal - Clean Hydro)",
        "country": "Canada",
        "provider": CloudProvider.AWS,
        "base_intensity": 32.0,  # Hydro-Québec clean hydro
        "renewable_pct": 92.0,
        "pue": 1.12,
        "sources": {"Hydro": 88, "Wind": 4, "Fossil": 8},
        "diurnal_swing": 0.10,
        "grid_operator": "Hydro-Québec",
        "currency": "USD",
        "kwh_tariff_bdt": 8.50
    },
    "us-east-1": {
        "name": "AWS US East (N. Virginia)",
        "country": "USA",
        "provider": CloudProvider.AWS,
        "base_intensity": 375.0,
        "renewable_pct": 21.0,
        "pue": 1.18,
        "sources": {"Gas": 48, "Nuclear": 29, "Coal": 15, "Solar/Wind": 8},
        "diurnal_swing": 0.28,
        "grid_operator": "PJM",
        "currency": "USD",
        "kwh_tariff_bdt": 11.00
    }
}


def calculate_diurnal_intensity(base_intensity: float, diurnal_swing: float, hour: int) -> float:
    """
    Computes realistic hour-of-day carbon intensity.
    Midday (11:00 - 15:00) sees higher solar generation, lowering grid intensity.
    Evening (18:00 - 22:00) sees peak domestic load & gas peaker plants, raising intensity.
    """
    # Solar peak dip centered at hour 13 (1 PM): maximum negative offset (cleanest solar power)
    solar_effect = -math.cos((hour - 13) * math.pi / 12) * diurnal_swing
    # Evening demand spike centered at hour 20 (8 PM): fossil peaker plants
    evening_peak = 0.5 * diurnal_swing * math.exp(-((hour - 20) ** 2) / 8.0)
    
    multiplier = 1.0 + solar_effect + evening_peak
    return round(max(10.0, base_intensity * multiplier), 1)


def get_region_with_forecast(region_id: str, current_hour: int = 12) -> GridRegion:
    """Returns a GridRegion model populated with 24h hourly carbon intensity forecast."""
    info = GRID_REGIONS_DATABASE.get(region_id, GRID_REGIONS_DATABASE["bd-tier4-gazipur"])
    base = info["base_intensity"]
    swing = info["diurnal_swing"]
    
    current_val = calculate_diurnal_intensity(base, swing, current_hour)
    
    # 24-hour rolling forecast
    forecast: List[float] = [
        calculate_diurnal_intensity(base, swing, (current_hour + h) % 24)
        for h in range(24)
    ]
    
    return GridRegion(
        id=region_id,
        name=info["name"],
        country=info["country"],
        provider=info["provider"],
        carbon_intensity_gco2_kwh=current_val,
        renewable_percentage=info["renewable_pct"],
        grid_source_breakdown=info["sources"],
        pue=info["pue"],
        hourly_forecast=forecast
    )


def get_all_regions(current_hour: int = 12) -> List[GridRegion]:
    """Returns all supported global regions with live estimated carbon intensities."""
    return [get_region_with_forecast(rid, current_hour) for rid in GRID_REGIONS_DATABASE.keys()]
