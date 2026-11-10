"""
EcoTrace Hardware & Workload Profiler
Instruments real host telemetry via psutil and simulates cloud microservices / container workloads.
Calculates continuous energy consumption and carbon emissions.
"""

import time
import psutil
from datetime import datetime
from typing import Dict, List, Optional
import threading

from ecotrace.core.models import (
    HardwareTelemetry,
    EnergyMetrics,
    WorkloadProfile,
    WorkloadType,
    WorkloadPriority,
    WorkloadStatus
)
from ecotrace.core.grid_data import get_region_with_forecast, GRID_REGIONS_DATABASE
from ecotrace.core.power_model import (
    calculate_instantaneous_power,
    calculate_carbon_rate,
    compute_eco_rating
)


class SystemProfiler:
    def __init__(self, default_region_id: str = "bd-tier4-gazipur"):
        self.active_region_id = default_region_id
        self.lock = threading.Lock()
        self.is_running = False
        
        # Cumulative tracking
        self.start_time = datetime.now()
        self.cumulative_energy_kwh = 0.0
        self.cumulative_carbon_gco2 = 0.0
        
        # Metrics history for chart streaming (capped at 60 points)
        self.history_limit = 60
        self.metrics_history: List[Dict] = []
        
        # Current snapshot
        self.latest_telemetry: Optional[HardwareTelemetry] = None
        self.latest_energy: Optional[EnergyMetrics] = None
        
        # Simulated Cloud Container Workloads
        self.workloads: Dict[str, WorkloadProfile] = {}
        self._init_default_workloads()
        
        # Previous I/O states for delta rate calculations
        self._last_disk_io = psutil.disk_io_counters()
        self._last_net_io = psutil.net_io_counters()
        self._last_io_time = time.time()
        
        # Start background monitoring thread
        self.start()

    def _init_default_workloads(self):
        """Initializes representative Bangladesh & regional cloud microservices."""
        defaults = [
            WorkloadProfile(
                id="wkld-bangla-nlp",
                name="Bangla Tokenizer & Document Parsing Service",
                workload_type=WorkloadType.DATA_PIPELINE,
                priority=WorkloadPriority.FLEXIBLE_BATCH,
                status=WorkloadStatus.RUNNING,
                region_id="bd-tier4-gazipur",
                vcpus=32.0,
                memory_gb=128.0,
                current_cpu_utilization=88.5,
                estimated_watts=540.0,
                carbon_rate_gco2_hr=324.0,
                eco_rating="D"
            ),
            WorkloadProfile(
                id="wkld-mfs-webhook",
                name="bKash / Nagad Payment Gateway Dispatcher",
                workload_type=WorkloadType.WEB_API,
                priority=WorkloadPriority.CRITICAL_REALTIME,
                status=WorkloadStatus.RUNNING,
                region_id="bd-tier4-gazipur",
                vcpus=8.0,
                memory_gb=16.0,
                current_cpu_utilization=42.0,
                estimated_watts=78.0,
                carbon_rate_gco2_hr=46.8,
                eco_rating="C"
            ),
            WorkloadProfile(
                id="wkld-bdix-stream",
                name="BDIX Cache & Local Video Streaming Node (Mohakhali)",
                workload_type=WorkloadType.MICROSERVICE,
                priority=WorkloadPriority.STANDARD,
                status=WorkloadStatus.RUNNING,
                region_id="bd-dhaka-colocation",
                vcpus=16.0,
                memory_gb=64.0,
                current_cpu_utilization=72.0,
                estimated_watts=295.0,
                carbon_rate_gco2_hr=181.4,
                eco_rating="D"
            ),
            WorkloadProfile(
                id="wkld-pathao-route",
                name="Pathao / Chaldal Delivery Route Optimization Engine",
                workload_type=WorkloadType.DATA_PIPELINE,
                priority=WorkloadPriority.FLEXIBLE_BATCH,
                status=WorkloadStatus.RUNNING,
                region_id="ap-south-1",
                vcpus=16.0,
                memory_gb=32.0,
                current_cpu_utilization=65.0,
                estimated_watts=220.0,
                carbon_rate_gco2_hr=140.8,
                eco_rating="D"
            ),
            WorkloadProfile(
                id="wkld-nid-kyc",
                name="Smart Citizen / NID Verification Worker",
                workload_type=WorkloadType.MICROSERVICE,
                priority=WorkloadPriority.CRITICAL_REALTIME,
                status=WorkloadStatus.RUNNING,
                region_id="bd-tier4-gazipur",
                vcpus=4.0,
                memory_gb=16.0,
                current_cpu_utilization=28.0,
                estimated_watts=42.0,
                carbon_rate_gco2_hr=25.2,
                eco_rating="C"
            )
        ]
        for w in defaults:
            self.workloads[w.id] = w

    def set_region(self, region_id: str):
        if region_id in GRID_REGIONS_DATABASE:
            with self.lock:
                self.active_region_id = region_id

    def sample_host_telemetry(self) -> HardwareTelemetry:
        """Collects instantaneous host hardware telemetry using psutil."""
        now = time.time()
        dt = max(0.1, now - self._last_io_time)
        
        cpu_pct = psutil.cpu_percent(interval=None)
        cpu_count = psutil.cpu_count(logical=True) or 4
        mem = psutil.virtual_memory()
        
        # Disk IO rate in MB/s
        curr_disk = psutil.disk_io_counters()
        disk_read_mbs = 0.0
        disk_write_mbs = 0.0
        if curr_disk and self._last_disk_io:
            disk_read_mbs = max(0.0, (curr_disk.read_bytes - self._last_disk_io.read_bytes) / (1024 * 1024 * dt))
            disk_write_mbs = max(0.0, (curr_disk.write_bytes - self._last_disk_io.write_bytes) / (1024 * 1024 * dt))
        self._last_disk_io = curr_disk

        # Network IO rate in MB/s
        curr_net = psutil.net_io_counters()
        net_recv_mbs = 0.0
        net_sent_mbs = 0.0
        if curr_net and self._last_net_io:
            net_recv_mbs = max(0.0, (curr_net.bytes_recv - self._last_net_io.bytes_recv) / (1024 * 1024 * dt))
            net_sent_mbs = max(0.0, (curr_net.bytes_sent - self._last_net_io.bytes_sent) / (1024 * 1024 * dt))
        self._last_net_io = curr_net
        self._last_io_time = now

        return HardwareTelemetry(
            timestamp=datetime.now(),
            cpu_percent=cpu_pct,
            cpu_cores_active=cpu_count,
            memory_used_gb=round(mem.used / (1024 ** 3), 2),
            memory_total_gb=round(mem.total / (1024 ** 3), 2),
            disk_io_read_mbs=round(disk_read_mbs, 2),
            disk_io_write_mbs=round(disk_write_mbs, 2),
            network_recv_mbs=round(net_recv_mbs, 2),
            network_sent_mbs=round(net_sent_mbs, 2)
        )

    def _tick(self):
        """Single profiling tick: samples telemetry, updates energy & carbon, updates workloads."""
        telemetry = self.sample_host_telemetry()
        current_hour = datetime.now().hour
        region_info = get_region_with_forecast(self.active_region_id, current_hour)
        
        # Calculate host power
        power = calculate_instantaneous_power(
            vcpus=telemetry.cpu_cores_active,
            cpu_percent=telemetry.cpu_percent,
            memory_gb=telemetry.memory_used_gb,
            disk_read_mbs=telemetry.disk_io_read_mbs,
            disk_write_mbs=telemetry.disk_io_write_mbs,
            network_recv_mbs=telemetry.network_recv_mbs,
            network_sent_mbs=telemetry.network_sent_mbs,
            pue=region_info.pue
        )
        
        # Calculate carbon rates
        op_c_rate, emb_c_rate, total_c_rate = calculate_carbon_rate(
            pue_adjusted_watts=power["pue_adjusted_watts"],
            carbon_intensity_gco2_kwh=region_info.carbon_intensity_gco2_kwh,
            vcpus=telemetry.cpu_cores_active,
            memory_gb=telemetry.memory_used_gb
        )
        
        # Increment cumulative totals (assuming 1-second sample interval)
        dt_hours = 1.0 / 3600.0
        energy_increment_kwh = (power["pue_adjusted_watts"] / 1000.0) * dt_hours
        carbon_increment_gco2 = total_c_rate * dt_hours
        
        with self.lock:
            self.cumulative_energy_kwh += energy_increment_kwh
            self.cumulative_carbon_gco2 += carbon_increment_gco2
            
            self.latest_telemetry = telemetry
            self.latest_energy = EnergyMetrics(
                timestamp=telemetry.timestamp,
                cpu_watts=power["cpu_watts"],
                memory_watts=power["memory_watts"],
                disk_watts=power["disk_watts"],
                network_watts=power["network_watts"],
                total_watts=power["subtotal_watts"],
                pue_adjusted_watts=power["pue_adjusted_watts"],
                current_carbon_intensity=region_info.carbon_intensity_gco2_kwh,
                carbon_rate_gco2_per_hr=total_c_rate,
                cumulative_energy_kwh=round(self.cumulative_energy_kwh, 5),
                cumulative_carbon_gco2=round(self.cumulative_carbon_gco2, 3)
            )
            
            # Append to history ring buffer
            self.metrics_history.append({
                "time": telemetry.timestamp.strftime("%H:%M:%S"),
                "watts": power["pue_adjusted_watts"],
                "cpu_pct": telemetry.cpu_percent,
                "carbon_intensity": region_info.carbon_intensity_gco2_kwh,
                "carbon_rate": total_c_rate,
                "cumulative_carbon": round(self.cumulative_carbon_gco2, 2)
            })
            if len(self.metrics_history) > self.history_limit:
                self.metrics_history.pop(0)

            # Update simulated workloads
            for w in self.workloads.values():
                if w.status == WorkloadStatus.RUNNING:
                    w.runtime_seconds += 1
                    w_region = get_region_with_forecast(w.region_id, current_hour)
                    w_power = calculate_instantaneous_power(
                        vcpus=w.vcpus,
                        cpu_percent=w.current_cpu_utilization,
                        memory_gb=w.memory_gb,
                        pue=w_region.pue
                    )
                    _, _, w_crate = calculate_carbon_rate(
                        pue_adjusted_watts=w_power["pue_adjusted_watts"],
                        carbon_intensity_gco2_kwh=w_region.carbon_intensity_gco2_kwh,
                        vcpus=w.vcpus,
                        memory_gb=w.memory_gb
                    )
                    w.estimated_watts = w_power["pue_adjusted_watts"]
                    w.carbon_rate_gco2_hr = w_crate
                    w.accumulated_energy_wh += (w_power["pue_adjusted_watts"] * (1.0 / 3600.0))
                    w.accumulated_carbon_g += (w_crate * (1.0 / 3600.0))
                    w.eco_rating = compute_eco_rating(w_region.carbon_intensity_gco2_kwh, w.current_cpu_utilization)

    def _worker_loop(self):
        while self.is_running:
            try:
                self._tick()
            except Exception as e:
                print(f"[EcoTrace Profiler] Error in tick: {e}")
            time.sleep(1.0)

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.is_running = False

    def get_workloads_list(self) -> List[WorkloadProfile]:
        with self.lock:
            return list(self.workloads.values())

    def add_workload(self, workload: WorkloadProfile):
        with self.lock:
            self.workloads[workload.id] = workload

    def delete_workload(self, workload_id: str) -> bool:
        with self.lock:
            if workload_id in self.workloads:
                del self.workloads[workload_id]
                return True
        return False


# Singleton profiler instance
profiler_instance = SystemProfiler()
