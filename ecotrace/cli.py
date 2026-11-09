"""
EcoTrace Command Line Interface (CLI)
Provides interactive terminal commands for real-time carbon monitoring, command profiling, and green audits.
"""

import sys
import io
import time
import subprocess
import argparse
from datetime import datetime

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn

from ecotrace.core.grid_data import get_all_regions, get_region_with_forecast
from ecotrace.core.profiler import profiler_instance
from ecotrace.core.optimizer import WorkloadOptimizer
from ecotrace.core.power_model import calculate_instantaneous_power, calculate_carbon_rate

console = Console(force_terminal=True)


def show_banner():
    console.print(
        Panel.fit(
            "[bold green]🌱 EcoTrace[/bold green] — [bold white]Granular Cloud Carbon & Energy Footprint Profiler[/bold white]\n"
            "[dim]Adhering to the Green Software Foundation Software Carbon Intensity (SCI) Specification[/dim]",
            border_style="green"
        )
    )


def command_regions(args):
    """Lists global cloud datacenter regions and their current carbon intensity."""
    show_banner()
    hour = datetime.now().hour
    regions = get_all_regions(hour)

    table = Table(title=f"Global Grid Carbon Intensities (Hour: {hour:02d}:00)", header_style="bold cyan")
    table.add_column("Region ID", style="bold yellow")
    table.add_column("Datacenter Name")
    table.add_column("Country")
    table.add_column("Provider")
    table.add_column("Carbon Intensity", justify="right")
    table.add_column("Renewables %", justify="right")
    table.add_column("PUE", justify="right")
    table.add_column("Eco Status", justify="center")

    for r in sorted(regions, key=lambda x: x.carbon_intensity_gco2_kwh):
        if r.carbon_intensity_gco2_kwh < 50:
            status = "[bold green]🌱 Clean (Low Carbon)[/bold green]"
            color = "green"
        elif r.carbon_intensity_gco2_kwh < 200:
            status = "[bold yellow]⚡ Moderate[/bold yellow]"
            color = "yellow"
        else:
            status = "[bold red]🔥 Fossil Intensive[/bold red]"
            color = "red"

        table.add_row(
            r.id,
            r.name,
            r.country,
            r.provider.value,
            f"[{color}]{r.carbon_intensity_gco2_kwh:.1f} gCO2/kWh[/{color}]",
            f"{r.renewable_percentage:.0f}%",
            f"{r.pue:.2f}",
            status
        )

    console.print(table)


def command_audit(args):
    """Performs full green workload audit with optimization recommendations."""
    show_banner()
    workloads = profiler_instance.get_workloads_list()
    recs = WorkloadOptimizer.generate_all_recommendations(workloads)

    table = Table(title="Monitored Cloud Workloads & Containers", header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Workload Name", style="bold")
    table.add_column("Type")
    table.add_column("Region")
    table.add_column("Power (W)", justify="right")
    table.add_column("Carbon (gCO2/hr)", justify="right")
    table.add_column("Rating", justify="center")

    for w in workloads:
        color = "green" if "A" in w.eco_rating else ("yellow" if "B" in w.eco_rating else "red")
        table.add_row(
            w.id,
            w.name,
            w.workload_type.value,
            w.region_id,
            f"{w.estimated_watts:.1f} W",
            f"{w.carbon_rate_gco2_hr:.1f} g/h",
            f"[{color} bold]{w.eco_rating}[/{color} bold]"
        )
    console.print(table)
    console.print("\n")

    rec_table = Table(title="🌱 Top Carbon Optimization Recommendations", header_style="bold green")
    rec_table.add_column("Category", style="bold magenta")
    rec_table.add_column("Recommendation", style="bold white")
    rec_table.add_column("Est. Carbon Savings", justify="right", style="bold green")
    rec_table.add_column("Action", style="yellow")

    for r in recs:
        cat_badge = r.category.replace("_", " ").upper()
        rec_table.add_row(
            f"[{cat_badge}]",
            f"{r.title}\n[dim]{r.description}[/dim]",
            f"-{r.potential_carbon_savings_percent:.1f}%\n({r.potential_carbon_savings_gco2_per_day:.1f} g/day)",
            r.actionable_action
        )
    console.print(rec_table)


def command_profile(args):
    """Executes a command and calculates exact energy (Joules/kWh) and grams of CO2."""
    show_banner()
    cmd = args.cmd
    region_id = args.region or "us-east-1"
    region = get_region_with_forecast(region_id, datetime.now().hour)

    console.print(f"[bold cyan]Profiling Command:[/bold cyan] [yellow]{cmd}[/yellow]")
    console.print(f"[bold cyan]Target Grid Region:[/bold cyan] [green]{region.name} ({region.carbon_intensity_gco2_kwh} gCO2/kWh)[/green]\n")

    start_time = time.time()
    proc = subprocess.Popen(cmd, shell=True)

    power_samples = []
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("[green]Sampling CPU/RAM power draws...", total=None)
        while proc.poll() is None:
            telemetry = profiler_instance.sample_host_telemetry()
            power = calculate_instantaneous_power(
                vcpus=telemetry.cpu_cores_active,
                cpu_percent=telemetry.cpu_percent,
                memory_gb=telemetry.memory_used_gb,
                pue=region.pue
            )
            power_samples.append(power["pue_adjusted_watts"])
            time.sleep(0.5)

    duration = time.time() - start_time
    avg_watts = sum(power_samples) / max(1, len(power_samples)) if power_samples else 45.0
    energy_kwh = (avg_watts * (duration / 3600.0)) / 1000.0
    energy_joules = avg_watts * duration

    op_carbon = energy_kwh * region.carbon_intensity_gco2_kwh
    vcpus = profiler_instance.latest_telemetry.cpu_cores_active if profiler_instance.latest_telemetry else 4
    emb_carbon = (vcpus * 0.557) * (duration / 3600.0)
    total_carbon = op_carbon + emb_carbon

    console.print(Panel(
        f"[bold green]✔ Execution Complete in {duration:.2f} seconds[/bold green]\n\n"
        f"• [bold]Average Power:[/bold] {avg_watts:.2f} Watts\n"
        f"• [bold]Energy Consumed:[/bold] {energy_joules:.2f} Joules ({energy_kwh:.6f} kWh)\n"
        f"• [bold]Operational Carbon:[/bold] {op_carbon:.4f} gCO2eq\n"
        f"• [bold]Embodied Hardware Carbon:[/bold] {emb_carbon:.4f} gCO2eq\n"
        f"• [bold yellow]Total Carbon Footprint (SCI):[/bold yellow] [bold red]{total_carbon:.4f} gCO2eq[/bold red]\n"
        f"• [bold]Equivalency:[/bold] ~{total_carbon / 5.5 * 100:.2f}% of a full smartphone charge",
        title="EcoTrace Profile Results",
        border_style="green"
    ))


def command_live(args):
    """Interactive real-time terminal dashboard."""
    console.clear()
    region_id = args.region or "us-east-1"
    profiler_instance.set_region(region_id)

    with Live(console=console, screen=True, refresh_per_second=2) as live:
        try:
            while True:
                energy = profiler_instance.latest_energy
                telem = profiler_instance.latest_telemetry
                workloads = profiler_instance.get_workloads_list()
                region = get_region_with_forecast(profiler_instance.active_region_id, datetime.now().hour)

                if not energy or not telem:
                    time.sleep(0.5)
                    continue

                layout = Layout()
                layout.split_column(
                    Layout(name="header", size=4),
                    Layout(name="metrics", size=7),
                    Layout(name="workloads", size=12),
                    Layout(name="footer", size=3)
                )

                # Header
                layout["header"].update(
                    Panel(
                        f"[bold green]🌱 EcoTrace Real-Time Energy & Carbon Monitor[/bold green] | "
                        f"Region: [bold cyan]{region.name}[/bold cyan] | "
                        f"Grid Intensity: [bold yellow]{region.carbon_intensity_gco2_kwh} gCO2/kWh[/bold yellow] | "
                        f"PUE: [bold]{region.pue:.2f}[/bold]",
                        border_style="green"
                    )
                )

                # Metrics grid
                metric_table = Table.grid(expand=True)
                metric_table.add_column(ratio=1)
                metric_table.add_column(ratio=1)
                metric_table.add_column(ratio=1)
                metric_table.add_column(ratio=1)

                metric_table.add_row(
                    Panel(f"[bold cyan]{energy.pue_adjusted_watts:.1f} W[/bold cyan]\n[dim]Instantaneous Power[/dim]", border_style="cyan"),
                    Panel(f"[bold yellow]{energy.carbon_rate_gco2_per_hr:.2f} g/h[/bold yellow]\n[dim]Carbon Flow Rate[/dim]", border_style="yellow"),
                    Panel(f"[bold magenta]{energy.cumulative_energy_kwh:.6f} kWh[/bold magenta]\n[dim]Cumulative Energy[/dim]", border_style="magenta"),
                    Panel(f"[bold red]{energy.cumulative_carbon_gco2:.3f} gCO2[/bold red]\n[dim]Total Carbon Emitted[/dim]", border_style="red")
                )
                layout["metrics"].update(metric_table)

                # Workloads table
                w_table = Table(title="Monitored Microservices & Pods", expand=True, header_style="bold blue")
                w_table.add_column("Workload")
                w_table.add_column("Type")
                w_table.add_column("Priority")
                w_table.add_column("vCPU / RAM")
                w_table.add_column("Watts", justify="right")
                w_table.add_column("Carbon Rate", justify="right")
                w_table.add_column("Rating", justify="center")

                for w in workloads:
                    color = "green" if "A" in w.eco_rating else ("yellow" if "B" in w.eco_rating else "red")
                    w_table.add_row(
                        w.name,
                        w.workload_type.value,
                        w.priority.value,
                        f"{w.vcpus:.0f} cores / {w.memory_gb:.0f} GB",
                        f"{w.estimated_watts:.1f} W",
                        f"{w.carbon_rate_gco2_hr:.1f} g/h",
                        f"[{color} bold]{w.eco_rating}[/{color} bold]"
                    )
                layout["workloads"].update(w_table)

                layout["footer"].update(
                    Panel("[dim]Press Ctrl+C to exit EcoTrace live monitor.[/dim]", border_style="dim")
                )

                live.update(layout)
                time.sleep(0.8)
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description="EcoTrace Carbon Profiler CLI")
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to run")

    # live command
    live_parser = subparsers.add_parser("live", help="Start real-time terminal dashboard")
    live_parser.add_argument("--region", default="us-east-1", help="Target cloud region ID")

    # regions command
    subparsers.add_parser("regions", help="List all global cloud regions and carbon intensity")

    # audit command
    subparsers.add_parser("audit", help="Run green carbon optimization audit on workloads")

    # profile command
    prof_parser = subparsers.add_parser("profile", help="Profile energy & carbon of an arbitrary command")
    prof_parser.add_argument("--cmd", required=True, help="Command to run and profile")
    prof_parser.add_argument("--region", default="us-east-1", help="Cloud region to simulate")

    args = parser.parse_args()

    if args.subcommand == "live":
        command_live(args)
    elif args.subcommand == "regions":
        command_regions(args)
    elif args.subcommand == "audit":
        command_audit(args)
    elif args.subcommand == "profile":
        command_profile(args)
    else:
        show_banner()
        parser.print_help()


if __name__ == "__main__":
    main()
