"""
EcoTrace Green Scheduling & Workload Carbon Optimizer
Performs Spatial Shifting, Temporal Shifting, and Hardware Right-sizing recommendations.
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime
from ecotrace.core.models import (
    WorkloadProfile,
    WorkloadPriority,
    WorkloadStatus,
    SpatialShiftOption,
    TemporalShiftOption,
    OptimizationRecommendation,
    CustomJobCalculationRequest,
    CustomJobCalculationResponse
)
from ecotrace.core.grid_data import get_region_with_forecast, get_all_regions, GRID_REGIONS_DATABASE
from ecotrace.core.power_model import calculate_instantaneous_power, calculate_carbon_rate


# Cleanest baseline regions for spatial shifting recommendations
CLEAN_TARGET_REGIONS = ["eu-north-1", "ca-central-1", "sa-east-1"]


class WorkloadOptimizer:

    @staticmethod
    def analyze_spatial_shift(workload: WorkloadProfile, current_hour: int = 12) -> List[SpatialShiftOption]:
        """Calculates savings if a workload is migrated to a green datacenter region."""
        options: List[SpatialShiftOption] = []
        curr_region = get_region_with_forecast(workload.region_id, current_hour)
        
        # Calculate daily emissions at current region
        daily_kwh = (workload.estimated_watts * 24.0) / 1000.0
        current_daily_carbon = daily_kwh * curr_region.carbon_intensity_gco2_kwh

        for target_id in CLEAN_TARGET_REGIONS:
            if target_id == workload.region_id:
                continue
            
            target_region = get_region_with_forecast(target_id, current_hour)
            if target_region.carbon_intensity_gco2_kwh >= curr_region.carbon_intensity_gco2_kwh:
                continue

            target_daily_carbon = daily_kwh * target_region.carbon_intensity_gco2_kwh
            saved_gco2 = current_daily_carbon - target_daily_carbon
            reduction_pct = ((curr_region.carbon_intensity_gco2_kwh - target_region.carbon_intensity_gco2_kwh) / curr_region.carbon_intensity_gco2_kwh) * 100.0

            # Approximate latency impact based on geographical hop
            latency_delta = 45 if "eu" in target_id and "us" in workload.region_id else 25

            options.append(SpatialShiftOption(
                target_region_id=target_id,
                target_region_name=target_region.name,
                current_carbon_intensity=curr_region.carbon_intensity_gco2_kwh,
                target_carbon_intensity=target_region.carbon_intensity_gco2_kwh,
                carbon_reduction_percent=round(reduction_pct, 1),
                carbon_saved_gco2_per_day=round(saved_gco2, 1),
                estimated_latency_delta_ms=latency_delta
            ))

        options.sort(key=lambda x: x.carbon_reduction_percent, reverse=True)
        return options

    @staticmethod
    def analyze_temporal_shift(workload: WorkloadProfile, scheduled_hour: int = 19) -> Optional[TemporalShiftOption]:
        """Identifies optimal low-carbon window (solar/wind peak) within next 24 hours."""
        region = get_region_with_forecast(workload.region_id, scheduled_hour)
        forecast = region.hourly_forecast  # 24 hours from current
        
        current_intensity = forecast[0]
        # Find minimum intensity in the forecast
        min_intensity = min(forecast)
        min_hour_offset = forecast.index(min_intensity)
        optimal_hour = (scheduled_hour + min_hour_offset) % 24

        if min_intensity < current_intensity * 0.90:  # At least 10% cleaner
            reduction_pct = ((current_intensity - min_intensity) / current_intensity) * 100.0
            job_hours = 3.0  # estimate
            saved_gco2 = ((workload.estimated_watts * job_hours) / 1000.0) * (current_intensity - min_intensity)

            return TemporalShiftOption(
                workload_id=workload.id,
                workload_name=workload.name,
                current_scheduled_hour=scheduled_hour,
                recommended_green_hour=optimal_hour,
                current_intensity=current_intensity,
                green_intensity=min_intensity,
                carbon_reduction_percent=round(reduction_pct, 1),
                carbon_saved_gco2=round(saved_gco2, 1),
                solar_peak_window=f"{optimal_hour:02d}:00 - {(optimal_hour + 3) % 24:02d}:00"
            )
        return None

    @classmethod
    def generate_all_recommendations(cls, workloads: List[WorkloadProfile]) -> List[OptimizationRecommendation]:
        """Scans current workloads and generates prioritized recommendations."""
        recommendations: List[OptimizationRecommendation] = []
        current_hour = datetime.now().hour

        for w in workloads:
            # 1. Spatial shifting for flexible or high-emission workloads in dirty regions
            if w.priority in [WorkloadPriority.FLEXIBLE_BATCH, WorkloadPriority.STANDARD]:
                spatial_opts = cls.analyze_spatial_shift(w, current_hour)
                if spatial_opts:
                    best = spatial_opts[0]
                    if best.carbon_reduction_percent > 30.0:
                        recommendations.append(OptimizationRecommendation(
                            id=f"rec-spatial-{w.id}",
                            title=f"Migrate '{w.name}' to {best.target_region_name}",
                            category="spatial_shift",
                            description=(
                                f"Workload currently runs in high-carbon region with {best.current_carbon_intensity} gCO2/kWh. "
                                f"Moving to {best.target_region_name} ({best.target_carbon_intensity} gCO2/kWh) reduces emissions by "
                                f"{best.carbon_reduction_percent}% with ~{best.estimated_latency_delta_ms}ms latency overhead."
                            ),
                            potential_carbon_savings_percent=best.carbon_reduction_percent,
                            potential_carbon_savings_gco2_per_day=best.carbon_saved_gco2_per_day,
                            actionable_action=f"Update deployment manifest: region = '{best.target_region_id}'",
                            details={"workload_id": w.id, "target_region": best.target_region_id}
                        ))

            # 2. Temporal shifting for batch jobs
            if w.priority == WorkloadPriority.FLEXIBLE_BATCH:
                temp_opt = cls.analyze_temporal_shift(w, current_hour)
                if temp_opt:
                    recommendations.append(OptimizationRecommendation(
                        id=f"rec-temporal-{w.id}",
                        title=f"Shift Batch Job '{w.name}' to Solar Peak ({temp_opt.solar_peak_window})",
                        category="temporal_shift",
                        description=(
                            f"Scheduling this job at {temp_opt.recommended_green_hour:02d}:00 aligns with high renewable generation, "
                            f"dropping grid intensity from {temp_opt.current_intensity} to {temp_opt.green_intensity} gCO2/kWh."
                        ),
                        potential_carbon_savings_percent=temp_opt.carbon_reduction_percent,
                        potential_carbon_savings_gco2_per_day=temp_opt.carbon_saved_gco2,
                        actionable_action=f"Update cron schedule to run at {temp_opt.recommended_green_hour:02d}:00 UTC",
                        details={"workload_id": w.id, "green_hour": str(temp_opt.recommended_green_hour)}
                    ))

            # 3. Hardware Right-Sizing
            if w.current_cpu_utilization < 25.0 and w.vcpus >= 8.0:
                potential_saving_pct = 45.0
                daily_kwh_saved = ((w.estimated_watts * 0.45) * 24.0) / 1000.0
                curr_reg = get_region_with_forecast(w.region_id, current_hour)
                carbon_saved = daily_kwh_saved * curr_reg.carbon_intensity_gco2_kwh
                recommendations.append(OptimizationRecommendation(
                    id=f"rec-rightsize-{w.id}",
                    title=f"Right-size '{w.name}' (Overprovisioned vCPUs)",
                    category="right_sizing",
                    description=(
                        f"Workload is allocated {w.vcpus} vCPUs but utilizes only {w.current_cpu_utilization:.1f}%. "
                        f"Downscaling to {int(w.vcpus / 2)} vCPUs saves idle thermal power and embodied carbon."
                    ),
                    potential_carbon_savings_percent=potential_saving_pct,
                    potential_carbon_savings_gco2_per_day=round(carbon_saved, 1),
                    actionable_action=f"Resize container CPU requests to {int(w.vcpus / 2)} cores",
                    details={"workload_id": w.id, "recommended_vcpus": str(int(w.vcpus / 2))}
                ))

        recommendations.sort(key=lambda r: r.potential_carbon_savings_gco2_per_day, reverse=True)
        return recommendations

    @staticmethod
    def calculate_custom_workload(req: CustomJobCalculationRequest) -> CustomJobCalculationResponse:
        """Calculates carbon footprint for any hypothetical cloud job with spatial & temporal comparisons."""
        current_region = get_region_with_forecast(req.region_id, req.start_hour)
        
        # Calculate instantaneous power
        power = calculate_instantaneous_power(
            vcpus=req.vcpus,
            cpu_percent=req.cpu_utilization_pct,
            memory_gb=req.memory_gb,
            network_sent_mbs=(req.data_transfer_gb * 1024.0) / max(1.0, (req.duration_hours * 3600.0)),
            pue=current_region.pue
        )
        
        total_kwh = (power["pue_adjusted_watts"] * req.duration_hours) / 1000.0
        
        # Operational Carbon
        op_carbon = total_kwh * current_region.carbon_intensity_gco2_kwh
        # Embodied Carbon
        emb_carbon = (req.vcpus * 0.557 + req.memory_gb * 0.012) * req.duration_hours
        total_carbon_gco2 = round(op_carbon + emb_carbon, 2)
        
        # Real-world equivalencies:
        # Typical passenger car emits ~120 g CO2 / km
        # Charging a smartphone consumes ~0.015 kWh (approx 5.5 g CO2 on avg grid)
        km_driven = round(total_carbon_gco2 / 120.0, 2)
        smartphones = round(total_carbon_gco2 / 5.5, 1)
        # Approximate cloud / local datacenter cost:
        # If Bangladesh datacenter: electricity tariff is ~11.85-22 BDT / kWh
        kwh_tariff = GRID_REGIONS_DATABASE.get(req.region_id, {}).get("kwh_tariff_bdt", 12.0)
        cost_bdt = round(total_kwh * kwh_tariff + (req.vcpus * 4.5 * req.duration_hours), 2)
        cost_usd = round(cost_bdt / 122.0, 2)

        # Find best spatial shift
        all_regions = get_all_regions(req.start_hour)
        cleanest_region = min(all_regions, key=lambda r: r.carbon_intensity_gco2_kwh)
        spatial_savings_pct = round(
            max(0.0, ((current_region.carbon_intensity_gco2_kwh - cleanest_region.carbon_intensity_gco2_kwh) / current_region.carbon_intensity_gco2_kwh) * 100.0),
            1
        )

        # Find best temporal shift
        forecast = current_region.hourly_forecast
        min_hour_intensity = min(forecast)
        optimal_hour = (req.start_hour + forecast.index(min_hour_intensity)) % 24
        curr_intensity = forecast[0]
        temporal_savings_pct = round(
            max(0.0, ((curr_intensity - min_hour_intensity) / curr_intensity) * 100.0),
            1
        )

        action = (
            f"Migrating this job from {current_region.name} to {cleanest_region.name} would cut emissions by {spatial_savings_pct}%. "
            f"Alternatively, running at {optimal_hour:02d}:00 in the same region saves {temporal_savings_pct}%."
        )

        return CustomJobCalculationResponse(
            workload_energy_kwh=round(total_kwh, 3),
            carbon_emissions_gco2=total_carbon_gco2,
            equivalent_km_driven=km_driven,
            equivalent_smartphones_charged=smartphones,
            cost_usd_estimate=cost_usd,
            current_region_name=current_region.name,
            optimal_region_name=cleanest_region.name,
            spatial_shift_carbon_savings_pct=spatial_savings_pct,
            optimal_hour=optimal_hour,
            temporal_shift_carbon_savings_pct=temporal_savings_pct,
            recommended_action=action
        )
