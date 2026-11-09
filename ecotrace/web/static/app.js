/**
 * EcoTrace Frontend Application Logic
 * Real-time WebSocket telemetry streaming, interactive Chart.js visualizations,
 * workload management, and green carbon optimization scheduler.
 */

// State
let activeRegionId = "bd-tier4-gazipur";
let regionsData = [];
let realtimeChart = null;
let diurnalChart = null;
let ws = null;

// DOM Elements
const metricPower = document.getElementById("metric-power");
const metricCpuLoad = document.getElementById("metric-cpu-load");
const metricIntensity = document.getElementById("metric-intensity");
const metricRenewables = document.getElementById("metric-renewables");
const metricGridStatus = document.getElementById("metric-grid-status");
const metricCarbonRate = document.getElementById("metric-carbon-rate");
const metricCumulativeCarbon = document.getElementById("metric-cumulative-carbon");
const metricCumulativeKwh = document.getElementById("metric-cumulative-kwh");
const metricEquivPhones = document.getElementById("metric-equiv-phones");
const headerRegionName = document.getElementById("header-region-name");
const recsContainer = document.getElementById("recommendations-container");
const recsCountBadge = document.getElementById("recs-count-badge");
const workloadsTbody = document.getElementById("workloads-table-body");
const regionsGrid = document.getElementById("regions-grid");

// Calculator Modal
const modalCalc = document.getElementById("modal-calc");
const btnOpenCalc = document.getElementById("btn-open-calc");
const btnCloseCalc = document.getElementById("btn-close-calc");
const calcForm = document.getElementById("calc-form");
const calcResults = document.getElementById("calc-results");
const calcRegionSelect = document.getElementById("calc-region");

// Add Workload Modal
const modalAddWorkload = document.getElementById("modal-add-workload");
const btnAddWorkload = document.getElementById("btn-add-workload");
const btnCloseWorkloadModal = document.getElementById("btn-close-workload-modal");
const addWorkloadForm = document.getElementById("add-workload-form");
const wRegionSelect = document.getElementById("w-region");

// Export Report Button
const btnExportReport = document.getElementById("btn-export-report");


// Initialize Application
document.addEventListener("DOMContentLoaded", async () => {
  lucide.createIcons();
  initCharts();
  await loadRegions();
  await loadWorkloads();
  await loadRecommendations();
  initWebSocket();
  setupEventListeners();

  // Polling fallback / periodic refresh for workloads and recommendations
  setInterval(loadWorkloads, 3000);
  setInterval(loadRecommendations, 6000);
});


// Chart Initialization
function initCharts() {
  const ctxRealtime = document.getElementById("realtime-chart").getContext("2d");
  realtimeChart = new Chart(ctxRealtime, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Power (Watts)",
          data: [],
          borderColor: "#06b6d4",
          backgroundColor: "rgba(6, 182, 212, 0.1)",
          borderWidth: 2,
          tension: 0.3,
          fill: true,
          yAxisID: "y"
        },
        {
          label: "Carbon Rate (gCO₂/hr)",
          data: [],
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.05)",
          borderWidth: 2,
          borderDash: [4, 4],
          tension: 0.3,
          yAxisID: "y1"
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: { color: "#6b7280", maxTicksLimit: 8, font: { size: 10 } }
        },
        y: {
          type: "linear",
          display: true,
          position: "left",
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#06b6d4", font: { size: 10 } },
          title: { display: true, text: "Watts", color: "#06b6d4", font: { size: 10 } }
        },
        y1: {
          type: "linear",
          display: true,
          position: "right",
          grid: { drawOnChartArea: false },
          ticks: { color: "#f59e0b", font: { size: 10 } },
          title: { display: true, text: "gCO₂/hr", color: "#f59e0b", font: { size: 10 } }
        }
      }
    }
  });

  const ctxDiurnal = document.getElementById("diurnal-chart").getContext("2d");
  diurnalChart = new Chart(ctxDiurnal, {
    type: "bar",
    data: {
      labels: Array.from({ length: 24 }, (_, i) => `${i}:00`),
      datasets: [{
        label: "Carbon Intensity (gCO₂/kWh)",
        data: [],
        backgroundColor: [],
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.parsed.y} gCO₂/kWh`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "#6b7280", font: { size: 9 }, maxTicksLimit: 8 }
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#9ca3af", font: { size: 10 } }
        }
      }
    }
  });
}


// WebSocket Live Telemetry
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/stream`;

  ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateLiveTelemetry(data);
    } catch (e) {
      console.error("Error parsing WS message:", e);
    }
  };

  ws.onclose = () => {
    // Retry connection after 2 seconds
    setTimeout(initWebSocket, 2000);
  };

  ws.onerror = () => {
    // Fallback polling if WS is blocked
    fetchLiveMetrics();
  };
}

async function fetchLiveMetrics() {
  try {
    const res = await fetch("/api/metrics/live");
    if (res.ok) {
      const data = await res.json();
      updateLiveTelemetry({
        timestamp: new Date().toLocaleTimeString(),
        watts: data.energy.pue_adjusted_watts,
        cpu_pct: data.telemetry.cpu_percent,
        carbon_intensity: data.energy.current_carbon_intensity,
        carbon_rate: data.energy.carbon_rate_gco2_per_hr,
        cumulative_kwh: data.energy.cumulative_energy_kwh,
        cumulative_gco2: data.energy.cumulative_carbon_gco2,
        active_region: activeRegionId
      });
    }
  } catch (err) {
    console.error("Fetch metrics error:", err);
  }
}

function updateLiveTelemetry(data) {
  metricPower.innerText = data.watts.toFixed(1);
  metricCpuLoad.innerText = `CPU ${data.cpu_pct.toFixed(1)}%`;
  metricIntensity.innerText = data.carbon_intensity.toFixed(1);
  metricCarbonRate.innerText = data.carbon_rate.toFixed(1);
  metricCumulativeCarbon.innerText = data.cumulative_gco2.toFixed(2);
  metricCumulativeKwh.innerText = `${data.cumulative_kwh.toFixed(5)} kWh`;

  const phones = (data.cumulative_gco2 / 5.5).toFixed(1);
  metricEquivPhones.innerText = `📱 ~${phones} phones`;

  // Update realtime line chart
  if (realtimeChart) {
    realtimeChart.data.labels.push(data.timestamp);
    realtimeChart.data.datasets[0].data.push(data.watts);
    realtimeChart.data.datasets[1].data.push(data.carbon_rate);

    if (realtimeChart.data.labels.length > 30) {
      realtimeChart.data.labels.shift();
      realtimeChart.data.datasets[0].data.shift();
      realtimeChart.data.datasets[1].data.shift();
    }
    realtimeChart.update("none");
  }
}


// Load and render regions
async function loadRegions() {
  try {
    const res = await fetch("/api/regions");
    regionsData = await res.json();

    // Populate selects
    calcRegionSelect.innerHTML = "";
    wRegionSelect.innerHTML = "";
    regionsGrid.innerHTML = "";

    regionsData.forEach((r) => {
      // Calculator select
      const opt1 = document.createElement("option");
      opt1.value = r.id;
      opt1.innerText = `${r.name} (${r.carbon_intensity_gco2_kwh} gCO₂/kWh)`;
      if (r.id === activeRegionId) opt1.selected = true;
      calcRegionSelect.appendChild(opt1);

      // Workload select
      const opt2 = document.createElement("option");
      opt2.value = r.id;
      opt2.innerText = r.name;
      wRegionSelect.appendChild(opt2);

      // Regional Card
      const isSelected = r.id === activeRegionId;
      const card = document.createElement("div");
      card.className = `p-3 rounded-xl border cursor-pointer transition relative overflow-hidden ${
        isSelected
          ? "bg-brand-950/40 border-brand-500 shadow-md shadow-brand-500/20"
          : "bg-gray-900/60 border-gray-800 hover:border-gray-700 hover:bg-gray-850"
      }`;

      let intensityColor = "text-emerald-400";
      let badgeBg = "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
      if (r.carbon_intensity_gco2_kwh > 300) {
        intensityColor = "text-rose-400";
        badgeBg = "bg-rose-500/15 text-rose-400 border-rose-500/30";
      } else if (r.carbon_intensity_gco2_kwh > 100) {
        intensityColor = "text-amber-400";
        badgeBg = "bg-amber-500/15 text-amber-400 border-amber-500/30";
      }

      card.innerHTML = `
        <div class="flex items-center justify-between mb-1.5">
          <span class="text-[10px] font-bold uppercase tracking-wider text-gray-400">${r.provider}</span>
          <span class="px-1.5 py-0.5 text-[9px] font-semibold rounded border ${badgeBg}">
            ${r.renewable_percentage.toFixed(0)}% Green
          </span>
        </div>
        <div class="font-bold text-xs text-white truncate" title="${r.name}">${r.name}</div>
        <div class="text-[11px] text-gray-400">${r.country}</div>
        <div class="mt-2 flex items-baseline justify-between border-t border-gray-800/60 pt-2">
          <span class="text-[10px] text-gray-400">Carbon Rate:</span>
          <span class="font-extrabold text-xs ${intensityColor}">${r.carbon_intensity_gco2_kwh} <span class="text-[9px] font-normal">g/kWh</span></span>
        </div>
      `;

      card.onclick = () => switchRegion(r.id);
      regionsGrid.appendChild(card);
    });

    updateDiurnalChart();
  } catch (err) {
    console.error("Error loading regions:", err);
  }
}

async function switchRegion(regionId) {
  try {
    const res = await fetch("/api/regions/active", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ region_id: regionId })
    });
    if (res.ok) {
      activeRegionId = regionId;
      const reg = regionsData.find((r) => r.id === regionId);
      if (reg) {
        headerRegionName.innerText = reg.name;
        metricRenewables.innerText = `Renewables: ${reg.renewable_percentage.toFixed(0)}%`;
        metricGridStatus.innerText = reg.carbon_intensity_gco2_kwh < 50 ? "Clean 🌱" : (reg.carbon_intensity_gco2_kwh < 200 ? "Moderate" : "Dirty 🔥");
        metricGridStatus.className = `px-1.5 py-0.5 rounded text-[10px] font-bold ${
          reg.carbon_intensity_gco2_kwh < 50
            ? "bg-emerald-500/20 text-emerald-300"
            : (reg.carbon_intensity_gco2_kwh < 200 ? "bg-amber-500/20 text-amber-300" : "bg-rose-500/20 text-rose-300")
        }`;
      }
      await loadRegions();
      await loadWorkloads();
      await loadRecommendations();
    }
  } catch (err) {
    console.error("Error switching region:", err);
  }
}

function updateDiurnalChart() {
  const currentRegion = regionsData.find((r) => r.id === activeRegionId) || regionsData[0];
  if (!currentRegion || !diurnalChart) return;

  const forecast = currentRegion.hourly_forecast || [];
  const minVal = Math.min(...forecast);

  const colors = forecast.map((val) => {
    if (val <= minVal * 1.05) return "#10b981"; // Best green solar window
    if (val > 300) return "#f43f5e";
    if (val > 150) return "#f59e0b";
    return "#34d399";
  });

  diurnalChart.data.datasets[0].data = forecast;
  diurnalChart.data.datasets[0].backgroundColor = colors;
  diurnalChart.update();
}


// Load and render Workloads Table
async function loadWorkloads() {
  try {
    const res = await fetch("/api/workloads");
    const workloads = await res.json();

    workloadsTbody.innerHTML = "";
    workloads.forEach((w) => {
      const tr = document.createElement("tr");
      tr.className = "hover:bg-gray-800/40 transition group";

      let ratingBadge = "badge-eco-B";
      if (w.eco_rating === "A+") ratingBadge = "badge-eco-A-plus";
      else if (w.eco_rating === "A") ratingBadge = "badge-eco-A";
      else if (w.eco_rating === "C") ratingBadge = "badge-eco-C";
      else if (w.eco_rating === "D" || w.eco_rating === "F") ratingBadge = "badge-eco-D";

      tr.innerHTML = `
        <td class="py-3 px-4 font-semibold text-white">
          <div class="flex items-center space-x-2">
            <span class="w-1.5 h-1.5 rounded-full ${w.status === 'running' ? 'bg-emerald-400' : 'bg-amber-400'}"></span>
            <span>${w.name}</span>
          </div>
        </td>
        <td class="py-3 px-3 text-gray-400">${w.workload_type}</td>
        <td class="py-3 px-3">
          <span class="px-2 py-0.5 rounded text-[10px] font-medium ${
            w.priority === 'critical' ? 'bg-rose-500/15 text-rose-300' : (w.priority === 'flexible_batch' ? 'bg-brand-500/15 text-brand-300' : 'bg-blue-500/15 text-blue-300')
          }">${w.priority.replace('_', ' ')}</span>
        </td>
        <td class="py-3 px-3 text-gray-300 font-mono text-[11px]">${w.region_id}</td>
        <td class="py-3 px-3 text-right text-gray-300 font-mono">${w.vcpus}c / ${w.memory_gb}GB</td>
        <td class="py-3 px-3 text-right text-cyan-400 font-mono font-medium">${w.estimated_watts.toFixed(1)} W</td>
        <td class="py-3 px-3 text-right text-amber-400 font-mono font-medium">${w.carbon_rate_gco2_hr.toFixed(1)} g/h</td>
        <td class="py-3 px-3 text-center">
          <span class="px-2 py-0.5 rounded text-[11px] font-bold ${ratingBadge}">${w.eco_rating}</span>
        </td>
        <td class="py-3 px-3 text-center">
          <button onclick="deleteWorkload('${w.id}')" class="p-1 rounded text-gray-400 hover:text-rose-400 hover:bg-rose-500/10 transition" title="Delete Workload">
            <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
          </button>
        </td>
      `;
      workloadsTbody.appendChild(tr);
    });

    lucide.createIcons();
  } catch (err) {
    console.error("Error loading workloads:", err);
  }
}

async function deleteWorkload(id) {
  try {
    await fetch(`/api/workloads/${id}`, { method: "DELETE" });
    await loadWorkloads();
    await loadRecommendations();
  } catch (err) {
    console.error("Error deleting workload:", err);
  }
}


// Load and render Recommendations
async function loadRecommendations() {
  try {
    const res = await fetch("/api/optimizer/recommendations");
    const recs = await res.json();

    recsCountBadge.innerText = `${recs.length} Actionable Opportunities`;
    recsContainer.innerHTML = "";

    if (recs.length === 0) {
      recsContainer.innerHTML = `
        <div class="col-span-full p-4 rounded-xl bg-gray-900/40 border border-gray-800 text-center text-xs text-gray-400">
          🌱 Workloads are currently running at peak green efficiency!
        </div>
      `;
      return;
    }

    recs.forEach((r) => {
      const card = document.createElement("div");
      card.className = "p-4 rounded-xl bg-gray-900/80 border border-brand-500/20 hover:border-brand-500/50 shadow-md space-y-2.5 transition flex flex-col justify-between";

      let icon = "globe";
      let badgeText = "SPATIAL SHIFT";
      let badgeClass = "bg-emerald-500/20 text-emerald-300";
      if (r.category === "temporal_shift") {
        icon = "clock";
        badgeText = "TEMPORAL SHIFT";
        badgeClass = "bg-amber-500/20 text-amber-300";
      } else if (r.category === "right_sizing") {
        icon = "cpu";
        badgeText = "RIGHT-SIZING";
        badgeClass = "bg-indigo-500/20 text-indigo-300";
      }

      card.innerHTML = `
        <div class="space-y-1.5">
          <div class="flex items-center justify-between">
            <span class="px-2 py-0.5 rounded text-[10px] font-bold ${badgeClass}">${badgeText}</span>
            <span class="text-xs font-extrabold text-brand-400">-${r.potential_carbon_savings_percent.toFixed(1)}% CO₂</span>
          </div>
          <h3 class="text-xs font-bold text-white leading-tight">${r.title}</h3>
          <p class="text-[11px] text-gray-400 line-clamp-3 leading-relaxed">${r.description}</p>
        </div>
        <div class="pt-2 border-t border-gray-800 flex items-center justify-between">
          <span class="text-[10px] text-gray-400">-${r.potential_carbon_savings_gco2_per_day.toFixed(1)} g/day</span>
          <button onclick='applyOptimization(${JSON.stringify(r)})' class="px-2.5 py-1 text-[11px] font-semibold rounded bg-brand-600 hover:bg-brand-500 text-white shadow-sm transition flex items-center space-x-1">
            <i data-lucide="check" class="w-3 h-3"></i>
            <span>Apply Now</span>
          </button>
        </div>
      `;
      recsContainer.appendChild(card);
    });

    lucide.createIcons();
  } catch (err) {
    console.error("Error loading recommendations:", err);
  }
}

async function applyOptimization(rec) {
  try {
    const payload = {
      recommendation_id: rec.id,
      workload_id: rec.details.workload_id || "",
      target_region: rec.details.target_region || "eu-north-1"
    };

    const res = await fetch("/api/optimizer/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      await loadWorkloads();
      await loadRecommendations();
    }
  } catch (err) {
    console.error("Error applying recommendation:", err);
  }
}


// Event Listeners Setup
function setupEventListeners() {
  // Calculator Modal
  btnOpenCalc.onclick = () => {
    modalCalc.classList.remove("hidden");
  };
  btnCloseCalc.onclick = () => {
    modalCalc.classList.add("hidden");
  };

  calcForm.onsubmit = async (e) => {
    e.preventDefault();
    const req = {
      vcpus: parseInt(document.getElementById("calc-vcpus").value),
      memory_gb: parseInt(document.getElementById("calc-ram").value),
      cpu_utilization_pct: parseFloat(document.getElementById("calc-util").value),
      duration_hours: parseFloat(document.getElementById("calc-duration").value),
      region_id: calcRegionSelect.value,
      data_transfer_gb: parseFloat(document.getElementById("calc-data").value)
    };

    try {
      const res = await fetch("/api/optimizer/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req)
      });
      const data = await res.json();

      const bdtCost = (data.cost_usd_estimate * 122).toFixed(0);
      document.getElementById("res-kwh").innerText = `${data.workload_energy_kwh} kWh`;
      document.getElementById("res-carbon").innerText = `${data.carbon_emissions_gco2} gCO₂`;
      document.getElementById("res-cost").innerText = `৳ ${bdtCost} ($${data.cost_usd_estimate.toFixed(2)})`;
      document.getElementById("res-recommendation").innerText = data.recommended_action;

      calcResults.classList.remove("hidden");
    } catch (err) {
      console.error("Calculation error:", err);
    }
  };

  // Add Workload Modal
  btnAddWorkload.onclick = () => {
    modalAddWorkload.classList.remove("hidden");
  };
  btnCloseWorkloadModal.onclick = () => {
    modalAddWorkload.classList.add("hidden");
  };

  addWorkloadForm.onsubmit = async (e) => {
    e.preventDefault();
    const newWkld = {
      id: `wkld-${Date.now()}`,
      name: document.getElementById("w-name").value,
      workload_type: document.getElementById("w-type").value,
      priority: document.getElementById("w-priority").value,
      status: "running",
      region_id: wRegionSelect.value,
      vcpus: parseFloat(document.getElementById("w-vcpus").value),
      memory_gb: parseFloat(document.getElementById("w-ram").value),
      current_cpu_utilization: 65.0,
      estimated_watts: 80.0,
      carbon_rate_gco2_hr: 25.0
    };

    try {
      await fetch("/api/workloads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newWkld)
      });
      modalAddWorkload.classList.add("hidden");
      addWorkloadForm.reset();
      await loadWorkloads();
      await loadRecommendations();
    } catch (err) {
      console.error("Error creating workload:", err);
    }
  };

  // Export JSON Audit Report
  btnExportReport.onclick = async () => {
    try {
      const res = await fetch("/api/export/report");
      const report = await res.json();
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ecotrace-audit-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Error exporting report:", err);
    }
  };
}
