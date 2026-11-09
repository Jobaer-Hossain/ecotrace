"""
EcoTrace Power & Carbon Calculation Engine
Adheres to the Green Software Foundation Software Carbon Intensity (SCI) Specification:
SCI = ((E * I) + M) per Functional Unit / Time

Energy (E):
  P_total = (P_cpu + P_memory + P_disk + P_network) * PUE
Carbon Intensity (I):
  Location-based real-time carbon intensity (gCO2eq / kWh)
Embodied Carbon (M):
  Amortized manufacturing footprint of server hardware allocated over workload lifecycle.
"""

from typing import Dict, Tuple


# Power coefficients (in Watts) based on SPECpower benchmark standards
CPU_TDP_PER_VCPU = 18.0          # Max thermal design power per virtual CPU core (Intel/AMD cloud server)
CPU_IDLE_FRACTION = 0.18        # Power drawn at 0% utilization (idle baseline)
MEMORY_WATTS_PER_GB = 0.38      # DDR4/DDR5 server RAM power draw per active GB
DISK_ACTIVE_WATTS_PER_MBPS = 0.0008  # NVMe / SSD dynamic I/O power per MB/s
NETWORK_WATTS_PER_MBPS = 0.0012      # NIC dynamic power per MB/s throughput

# Embodied carbon constant:
# Average 2U cloud host server: ~1,250 kg CO2eq manufacturing emission
# Lifespan: 4 years (35,040 hours), 64 vCPUs average density
# Embodied emission per vCPU-hour = 1,250,000 g / (64 * 35,040) ≈ 0.557 g CO2eq / vCPU-hour
EMBODIED_CO2_PER_VCPU_HOUR = 0.557
EMBODIED_CO2_PER_GB_HOUR = 0.012


def calculate_instantaneous_power(
    vcpus: float,
    cpu_percent: float,
    memory_gb: float,
    disk_read_mbs: float = 0.0,
    disk_write_mbs: float = 0.0,
    network_recv_mbs: float = 0.0,
    network_sent_mbs: float = 0.0,
    pue: float = 1.15
) -> Dict[str, float]:
    """
    Calculates instantaneous electrical power in Watts for a given workload slice or host system.
    """
    # CPU Power
    max_cpu_watts = vcpus * CPU_TDP_PER_VCPU
    idle_cpu_watts = max_cpu_watts * CPU_IDLE_FRACTION
    dynamic_cpu_watts = (max_cpu_watts - idle_cpu_watts) * (min(100.0, max(0.0, cpu_percent)) / 100.0)
    cpu_watts = idle_cpu_watts + dynamic_cpu_watts

    # Memory Power
    memory_watts = memory_gb * MEMORY_WATTS_PER_GB

    # Storage & Network dynamic I/O power
    disk_watts = (disk_read_mbs + disk_write_mbs) * DISK_ACTIVE_WATTS_PER_MBPS
    network_watts = (network_recv_mbs + network_sent_mbs) * NETWORK_WATTS_PER_MBPS

    subtotal_watts = cpu_watts + memory_watts + disk_watts + network_watts
    pue_adjusted_watts = subtotal_watts * pue

    return {
        "cpu_watts": round(cpu_watts, 2),
        "memory_watts": round(memory_watts, 2),
        "disk_watts": round(disk_watts, 3),
        "network_watts": round(network_watts, 3),
        "subtotal_watts": round(subtotal_watts, 2),
        "pue_adjusted_watts": round(pue_adjusted_watts, 2)
    }


def calculate_carbon_rate(
    pue_adjusted_watts: float,
    carbon_intensity_gco2_kwh: float,
    vcpus: float = 1.0,
    memory_gb: float = 4.0
) -> Tuple[float, float, float]:
    """
    Computes:
    - Operational carbon emission rate (gCO2eq / hour)
    - Embodied carbon rate (gCO2eq / hour)
    - Total SCI carbon rate (gCO2eq / hour)
    """
    # Operational: (Watts / 1000 kW) * (gCO2 / kWh) = gCO2 per hour
    kwh_per_hour = pue_adjusted_watts / 1000.0
    operational_carbon_rate = kwh_per_hour * carbon_intensity_gco2_kwh

    # Embodied carbon (M)
    embodied_carbon_rate = (vcpus * EMBODIED_CO2_PER_VCPU_HOUR) + (memory_gb * EMBODIED_CO2_PER_GB_HOUR)

    total_carbon_rate = operational_carbon_rate + embodied_carbon_rate

    return (
        round(operational_carbon_rate, 2),
        round(embodied_carbon_rate, 2),
        round(total_carbon_rate, 2)
    )


def compute_eco_rating(carbon_intensity_gco2_kwh: float, cpu_utilization: float) -> str:
    """
    Assigns an intuitive Energy Efficiency & Carbon Grade (A+, A, B, C, D, F).
    Takes into account grid cleanliness and utilization efficiency.
    """
    # Clean grid + good utilization (above 40% not wasting idle energy) = A+
    score = carbon_intensity_gco2_kwh

    if score < 40.0:
        return "A+"
    elif score < 120.0:
        return "A"
    elif score < 250.0:
        return "B"
    elif score < 360.0:
        return "C"
    elif score < 450.0:
        return "D"
    else:
        return "F"
