"""
EcoTrace Automated Test Suite
Tests power modeling, carbon intensity, SCI specification, and optimizer algorithms.
"""

import unittest
from datetime import datetime
from ecotrace.core.power_model import (
    calculate_instantaneous_power,
    calculate_carbon_rate,
    compute_eco_rating
)
from ecotrace.core.grid_data import (
    calculate_diurnal_intensity,
    get_region_with_forecast,
    GRID_REGIONS_DATABASE
)
from ecotrace.core.optimizer import (
    WorkloadOptimizer,
    CustomJobCalculationRequest
)
from ecotrace.core.models import (
    WorkloadProfile,
    WorkloadType,
    WorkloadPriority,
    WorkloadStatus
)


class TestEcoTraceCore(unittest.TestCase):

    def test_power_calculation(self):
        """Test CPU, RAM, and PUE electrical power modeling."""
        power = calculate_instantaneous_power(
            vcpus=4,
            cpu_percent=50.0,
            memory_gb=16.0,
            pue=1.15
        )
        # 4 vCPUs * 18W TDP = 72W max. Idle = 12.96W. At 50% = 12.96 + 29.52 = 42.48W
        # Memory: 16 * 0.38 = 6.08W
        # Subtotal ~ 48.56W
        # PUE adjusted: 48.56 * 1.15 ~ 55.84W
        self.assertGreater(power["cpu_watts"], 35.0)
        self.assertLess(power["cpu_watts"], 50.0)
        self.assertAlmostEqual(power["memory_watts"], 6.08, places=1)
        self.assertGreater(power["pue_adjusted_watts"], power["subtotal_watts"])

    def test_carbon_rate_calculation(self):
        """Test operational and embodied carbon calculation according to SCI."""
        op_c, emb_c, total_c = calculate_carbon_rate(
            pue_adjusted_watts=100.0,
            carbon_intensity_gco2_kwh=300.0,
            vcpus=4,
            memory_gb=16
        )
        # Operational: (100W / 1000) * 300 gCO2/kWh = 30.0 gCO2/hr
        self.assertAlmostEqual(op_c, 30.0, places=1)
        # Embodied: 4 * 0.557 + 16 * 0.012 = 2.228 + 0.192 = 2.42 gCO2/hr
        self.assertAlmostEqual(emb_c, 2.42, places=1)
        self.assertAlmostEqual(total_c, 32.42, places=1)

    def test_eco_ratings(self):
        """Test eco rating grades based on carbon intensity."""
        self.assertEqual(compute_eco_rating(25.0, 80.0), "A+")
        self.assertEqual(compute_eco_rating(90.0, 70.0), "A")
        self.assertEqual(compute_eco_rating(200.0, 60.0), "B")
        self.assertEqual(compute_eco_rating(350.0, 50.0), "C")
        self.assertEqual(compute_eco_rating(420.0, 40.0), "D")
        self.assertEqual(compute_eco_rating(500.0, 30.0), "F")

    def test_diurnal_curve(self):
        """Midday solar generation should be lower carbon intensity than evening peak."""
        base = 300.0
        swing = 0.25
        midday_intensity = calculate_diurnal_intensity(base, swing, hour=13)
        evening_intensity = calculate_diurnal_intensity(base, swing, hour=20)
        self.assertLess(midday_intensity, evening_intensity)

    def test_spatial_shifting(self):
        """Workload in high-emission Bangladesh grid should find clean alternatives like eu-north-1."""
        dirty_workload = WorkloadProfile(
            id="wkld-test-batch",
            name="Test Big Data Job",
            workload_type=WorkloadType.DATA_PIPELINE,
            priority=WorkloadPriority.FLEXIBLE_BATCH,
            status=WorkloadStatus.RUNNING,
            region_id="bd-tier4-gazipur",
            vcpus=16.0,
            memory_gb=64.0,
            current_cpu_utilization=80.0,
            estimated_watts=250.0,
            carbon_rate_gco2_hr=145.0
        )
        shifts = WorkloadOptimizer.analyze_spatial_shift(dirty_workload)
        self.assertGreater(len(shifts), 0)
        best = shifts[0]
        # Should reduce emissions significantly (more than 70%)
        self.assertGreater(best.carbon_reduction_percent, 70.0)

    def test_custom_job_calculator(self):
        """Test hypothetical cloud job carbon calculation."""
        req = CustomJobCalculationRequest(
            vcpus=8,
            memory_gb=32,
            cpu_utilization_pct=75.0,
            duration_hours=4.0,
            region_id="bd-tier4-gazipur",
            data_transfer_gb=20.0
        )
        res = WorkloadOptimizer.calculate_custom_workload(req)
        self.assertGreater(res.workload_energy_kwh, 0.1)
        self.assertGreater(res.carbon_emissions_gco2, 10.0)
        self.assertGreater(res.spatial_shift_carbon_savings_pct, 50.0)


if __name__ == "__main__":
    unittest.main()
