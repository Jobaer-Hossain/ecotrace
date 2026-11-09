"""
EcoTrace Data Models
Defines Pydantic schemas for hardware telemetry, grid data, workloads, and optimization plans.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum


class CloudProvider(str, Enum):
    AWS = "AWS"
    GCP = "GCP"
    AZURE = "Azure"
    ON_PREM = "On-Premises"


class WorkloadStatus(str, Enum):
    RUNNING = "running"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    PAUSED = "paused"


class WorkloadPriority(str, Enum):
    CRITICAL_REALTIME = "critical"      # Cannot be delayed or shifted
    STANDARD = "standard"               # Can tolerate minor regional shift
    FLEXIBLE_BATCH = "flexible_batch"   # Can be temporally shifted to green windows


class WorkloadType(str, Enum):
    WEB_API = "Web API / Gateway"
    ML_TRAINING = "ML Training / Fine-tuning"
    DATA_PIPELINE = "ETL / Data Pipeline"
    DATABASE = "Database / Storage"
    MICROSERVICE = "Background Microservice"
    SYSTEM_HOST = "Host System Workload"


class GridRegion(BaseModel):
    id: str
    name: str
    country: str
    provider: CloudProvider
    carbon_intensity_gco2_kwh: float = Field(..., description="Current carbon intensity in gCO2eq/kWh")
    renewable_percentage: float = Field(..., description="Percentage of power from wind/solar/hydro/nuclear")
    grid_source_breakdown: Dict[str, float] = Field(default_factory=dict, description="Percentage by fuel type")
    pue: float = Field(1.15, description="Power Usage Effectiveness of datacenter (1.0 = perfect efficiency)")
    hourly_forecast: List[float] = Field(default_factory=list, description="24-hour forecasted carbon intensity")


class HardwareTelemetry(BaseModel):
    timestamp: datetime
    cpu_percent: float
    cpu_cores_active: int
    memory_used_gb: float
    memory_total_gb: float
    disk_io_read_mbs: float
    disk_io_write_mbs: float
    network_recv_mbs: float
    network_sent_mbs: float


class EnergyMetrics(BaseModel):
    timestamp: datetime
    cpu_watts: float
    memory_watts: float
    disk_watts: float
    network_watts: float
    total_watts: float
    pue_adjusted_watts: float
    current_carbon_intensity: float  # gCO2/kWh
    carbon_rate_gco2_per_hr: float
    cumulative_energy_kwh: float
    cumulative_carbon_gco2: float


class WorkloadProfile(BaseModel):
    id: str
    name: str
    workload_type: WorkloadType
    priority: WorkloadPriority
    status: WorkloadStatus
    region_id: str
    vcpus: float
    memory_gb: float
    current_cpu_utilization: float
    estimated_watts: float
    carbon_rate_gco2_hr: float
    accumulated_energy_wh: float = 0.0
    accumulated_carbon_g: float = 0.0
    eco_rating: str = "B"  # A+, A, B, C, D, F
    runtime_seconds: int = 0


class SpatialShiftOption(BaseModel):
    target_region_id: str
    target_region_name: str
    current_carbon_intensity: float
    target_carbon_intensity: float
    carbon_reduction_percent: float
    carbon_saved_gco2_per_day: float
    estimated_latency_delta_ms: int


class TemporalShiftOption(BaseModel):
    workload_id: str
    workload_name: str
    current_scheduled_hour: int
    recommended_green_hour: int
    current_intensity: float
    green_intensity: float
    carbon_reduction_percent: float
    carbon_saved_gco2: float
    solar_peak_window: str


class OptimizationRecommendation(BaseModel):
    id: str
    title: str
    category: str  # "spatial_shift", "temporal_shift", "right_sizing"
    description: str
    potential_carbon_savings_percent: float
    potential_carbon_savings_gco2_per_day: float
    actionable_action: str
    details: Dict[str, str] = Field(default_factory=dict)


class CustomJobCalculationRequest(BaseModel):
    vcpus: int = 4
    memory_gb: int = 16
    cpu_utilization_pct: float = 80.0
    duration_hours: float = 6.0
    region_id: str = "us-east-1"
    start_hour: int = 14
    data_transfer_gb: float = 50.0


class CustomJobCalculationResponse(BaseModel):
    workload_energy_kwh: float
    carbon_emissions_gco2: float
    equivalent_km_driven: float
    equivalent_smartphones_charged: float
    cost_usd_estimate: float
    current_region_name: str
    optimal_region_name: str
    spatial_shift_carbon_savings_pct: float
    optimal_hour: int
    temporal_shift_carbon_savings_pct: float
    recommended_action: str
