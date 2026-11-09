"""
EcoTrace FastAPI Server
Exposes RESTful APIs, WebSocket live streams, and static dashboard serving.
"""

import asyncio
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Dict

from ecotrace.core.models import (
    WorkloadProfile,
    GridRegion,
    EnergyMetrics,
    CustomJobCalculationRequest,
    CustomJobCalculationResponse,
    OptimizationRecommendation
)
from ecotrace.core.grid_data import get_all_regions, get_region_with_forecast, GRID_REGIONS_DATABASE
from ecotrace.core.profiler import profiler_instance
from ecotrace.core.optimizer import WorkloadOptimizer

app = FastAPI(
    title="EcoTrace API",
    description="Granular Cloud Carbon & Energy Footprint Profiler",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status")
def get_status():
    """Returns profiler uptime and active region."""
    return {
        "status": "online",
        "active_region_id": profiler_instance.active_region_id,
        "active_region_name": GRID_REGIONS_DATABASE[profiler_instance.active_region_id]["name"],
        "start_time": profiler_instance.start_time.isoformat(),
        "workloads_count": len(profiler_instance.workloads)
    }


@app.get("/api/metrics/live")
def get_live_metrics():
    """Instantaneous power, carbon rates, and cumulative energy."""
    energy = profiler_instance.latest_energy
    telem = profiler_instance.latest_telemetry
    if not energy or not telem:
        raise HTTPException(status_code=503, detail="Telemetry initializing")
    
    # Real-world equivalents
    cum_gco2 = energy.cumulative_carbon_gco2
    smartphones = round(cum_gco2 / 5.5, 2)
    car_km = round(cum_gco2 / 120.0, 4)
    tree_months = round(cum_gco2 / (21000.0 / 12.0), 5)  # A mature tree absorbs ~21kg CO2/year

    return {
        "energy": energy,
        "telemetry": telem,
        "equivalents": {
            "smartphones_charged": smartphones,
            "car_km_driven": car_km,
            "tree_absorption_months": tree_months
        }
    }


@app.get("/api/metrics/history")
def get_metrics_history():
    """Returns historical time-series buffer for charts."""
    with profiler_instance.lock:
        return list(profiler_instance.metrics_history)


@app.get("/api/workloads", response_model=List[WorkloadProfile])
def list_workloads():
    """Returns all monitored container/microservice workloads."""
    return profiler_instance.get_workloads_list()


@app.post("/api/workloads", response_model=WorkloadProfile)
def create_workload(workload: WorkloadProfile):
    """Registers a new cloud workload or pod to profile."""
    profiler_instance.add_workload(workload)
    return workload


@app.delete("/api/workloads/{workload_id}")
def delete_workload(workload_id: str):
    """Deletes or stops a monitored workload."""
    success = profiler_instance.delete_workload(workload_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workload not found")
    return {"status": "deleted", "workload_id": workload_id}


@app.get("/api/regions", response_model=List[GridRegion])
def list_regions():
    """Returns all global regions with live carbon intensities and 24h forecasts."""
    current_hour = datetime.now().hour
    return get_all_regions(current_hour)


@app.post("/api/regions/active")
def switch_active_region(payload: Dict[str, str]):
    """Switches the default active simulation region."""
    region_id = payload.get("region_id")
    if not region_id or region_id not in GRID_REGIONS_DATABASE:
        raise HTTPException(status_code=400, detail="Invalid region_id")
    profiler_instance.set_region(region_id)
    return {
        "status": "updated",
        "active_region_id": region_id,
        "region_name": GRID_REGIONS_DATABASE[region_id]["name"]
    }


@app.get("/api/optimizer/recommendations", response_model=List[OptimizationRecommendation])
def get_recommendations():
    """Computes actionable spatial and temporal carbon shifting recommendations."""
    workloads = profiler_instance.get_workloads_list()
    return WorkloadOptimizer.generate_all_recommendations(workloads)


@app.post("/api/optimizer/apply")
def apply_recommendation(payload: Dict[str, str]):
    """
    Applies an optimization (e.g. migrate workload to green region or right-size cores)
    instantly altering the workload's carbon footprint.
    """
    rec_id = payload.get("recommendation_id")
    workload_id = payload.get("workload_id")
    
    with profiler_instance.lock:
        if workload_id not in profiler_instance.workloads:
            raise HTTPException(status_code=404, detail="Workload not found")
        
        w = profiler_instance.workloads[workload_id]
        
        if "spatial" in rec_id:
            target_region = payload.get("target_region", "eu-north-1")
            old_region = w.region_id
            w.region_id = target_region
            return {
                "success": True,
                "message": f"Successfully shifted '{w.name}' from {old_region} to {target_region}. Live emissions reduced immediately!"
            }
        elif "rightsize" in rec_id:
            w.vcpus = max(2.0, w.vcpus / 2.0)
            return {
                "success": True,
                "message": f"Right-sized '{w.name}' to {int(w.vcpus)} vCPUs. Idle power waste reduced."
            }
        elif "temporal" in rec_id:
            return {
                "success": True,
                "message": f"Scheduled '{w.name}' for execution during solar peak window."
            }
            
    return {"success": False, "message": "Unknown recommendation type"}


@app.post("/api/optimizer/calculate", response_model=CustomJobCalculationResponse)
def calculate_custom_job(req: CustomJobCalculationRequest):
    """Calculates what-if carbon footprint and green scheduling for any hypothetical workload."""
    return WorkloadOptimizer.calculate_custom_workload(req)


@app.get("/api/export/report")
def export_carbon_report():
    """Generates a downloadable full Green Software Carbon audit report."""
    energy = profiler_instance.latest_energy
    telem = profiler_instance.latest_telemetry
    workloads = profiler_instance.get_workloads_list()
    recs = WorkloadOptimizer.generate_all_recommendations(workloads)
    region = get_region_with_forecast(profiler_instance.active_region_id, datetime.now().hour)
    
    total_workload_watts = sum(w.estimated_watts for w in workloads)
    total_workload_carbon_rate = sum(w.carbon_rate_gco2_hr for w in workloads)

    report = {
        "title": "EcoTrace Cloud Carbon & Energy Footprint Audit",
        "generated_at": datetime.now().isoformat(),
        "sci_standard_version": "GSF SCI 1.0",
        "datacenter_context": {
            "region_id": region.id,
            "region_name": region.name,
            "country": region.country,
            "carbon_intensity_gco2_kwh": region.carbon_intensity_gco2_kwh,
            "renewable_percentage": region.renewable_percentage,
            "pue": region.pue
        },
        "system_host_telemetry": {
            "cpu_utilization_pct": telem.cpu_percent if telem else 0,
            "memory_used_gb": telem.memory_used_gb if telem else 0,
            "instantaneous_power_watts": energy.pue_adjusted_watts if energy else 0,
            "cumulative_kwh": energy.cumulative_energy_kwh if energy else 0,
            "cumulative_gco2": energy.cumulative_carbon_gco2 if energy else 0
        },
        "cloud_workloads_summary": {
            "total_monitored": len(workloads),
            "aggregate_power_watts": round(total_workload_watts, 2),
            "aggregate_carbon_rate_gco2_hr": round(total_workload_carbon_rate, 2),
            "workloads": [w.dict() for w in workloads]
        },
        "optimization_opportunities": [r.dict() for r in recs]
    }
    return report


@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """Streams live telemetry at 1Hz over WebSocket."""
    await websocket.accept()
    try:
        while True:
            energy = profiler_instance.latest_energy
            telem = profiler_instance.latest_telemetry
            if energy and telem:
                payload = {
                    "timestamp": energy.timestamp.strftime("%H:%M:%S"),
                    "watts": energy.pue_adjusted_watts,
                    "cpu_pct": telem.cpu_percent,
                    "carbon_intensity": energy.current_carbon_intensity,
                    "carbon_rate": energy.carbon_rate_gco2_per_hr,
                    "cumulative_kwh": energy.cumulative_energy_kwh,
                    "cumulative_gco2": energy.cumulative_carbon_gco2,
                    "active_region": profiler_instance.active_region_id
                }
                await websocket.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# Mount Web Dashboard
static_path = Path(__file__).resolve().parent.parent / "web" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def serve_index():
    index_file = static_path / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>EcoTrace Web Dashboard is loading...</h1>")
