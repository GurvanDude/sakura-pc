"""Affichage temps réel des mesures système dans le terminal."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from rich import box
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .sensors import Sampler

SAKURA = "#ff5fa8"
SAKURA_DEEP = "#e0236f"
SAKURA_PALE = "#ffd3e6"
NEON_CYAN = "#7fd8ff"


def _section(status: dict[str, Any], name: str) -> dict[str, Any]:
    value = status.get(name)
    return value if isinstance(value, dict) else {}


def _number(value: Any, unit: str = "") -> Text:
    """Formate un nombre à la française, sans laisser remonter d'erreur."""
    if value is None or isinstance(value, bool):
        return Text("—", style="grey50")
    try:
        result = f"{float(value):.1f}".replace(".", ",")
    except (TypeError, ValueError):
        return Text("—", style="grey50")
    if result.endswith(",0"):
        result = result[:-2]
    return Text(result + unit)


def _percent(value: Any) -> float | None:
    try:
        return None if value is None else min(100.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return None


def _bar(value: Any, width: int = 14, partition: bool = False) -> Text:
    percent = _percent(value)
    if percent is None:
        return Text("—", style="grey50")
    color = SAKURA_PALE if percent < 60 else SAKURA if percent <= 85 else SAKURA_DEEP
    style = f"bold {color}" if percent > 85 else color
    filled = round(width * percent / 100)
    result = Text("█" * filled, style=style)
    result.append("░" * (width - filled), style="grey23")
    result.append(f" {percent:.1f} %".replace(".", ","))
    if partition and percent > 90:
        result.append("  presque plein", style=f"bold {SAKURA_DEEP}")
    return result


def _pair(first: Any, second: Any, unit: str) -> Text:
    if first is None and second is None:
        return Text("—", style="grey50")
    result = Text()
    result.append_text(_number(first))
    result.append(" / ")
    result.append_text(_number(second))
    result.append(f" {unit}")
    return result


def _metric_table() -> Table:
    table = Table.grid(expand=True, padding=(0, 1))
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)
    return table


def _cpu_panel(status: dict[str, Any]) -> Panel:
    cpu, temps = _section(status, "cpu"), _section(status, "temps")
    summary = _metric_table()
    summary.add_row("Total", _bar(cpu.get("percent"), 18))
    summary.add_row("Fréquence", _number(cpu.get("freq_mhz"), " MHz"))
    summary.add_row("Température", _number(temps.get("cpu"), " °C"))
    cores = Table.grid(expand=True, padding=(0, 1))
    for _ in range(4):
        cores.add_column(ratio=1)
    values = cpu.get("per_core")
    if isinstance(values, list) and values:
        half = (len(values) + 1) // 2
        for index in range(half):
            other = index + half
            cells: list[Any] = [f"Cœur {index + 1}", _bar(values[index], 7)]
            cells += [f"Cœur {other + 1}", _bar(values[other], 7)] if other < len(values) else ["", ""]
            cores.add_row(*cells)
    else:
        cores.add_row("Cœurs", Text("—", style="grey50"), "", "")
    return Panel(Group(summary, Text(), cores), title="CPU", border_style=SAKURA, box=box.ROUNDED)


def _ram_panel(status: dict[str, Any]) -> Panel:
    ram = _section(status, "ram")
    table = _metric_table()
    table.add_row("Mémoire", _bar(ram.get("percent")))
    table.add_row("Utilisée", _pair(ram.get("used_gb"), ram.get("total_gb"), "Go"))
    table.add_row("Swap", _bar(ram.get("swap_percent")))
    return Panel(table, title="RAM", border_style=SAKURA, box=box.ROUNDED)


def _gpu_panel(status: dict[str, Any]) -> Panel:
    gpu, temps = _section(status, "gpu"), _section(status, "temps")
    table = _metric_table()
    table.add_row("Charge", _bar(gpu.get("percent")))
    table.add_row("VRAM", _pair(gpu.get("vram_used_gb"), gpu.get("vram_total_gb"), "Go"))
    table.add_row("Température", _number(temps.get("gpu"), " °C"))
    table.add_row("Hotspot", _number(temps.get("gpu_hotspot"), " °C"))
    return Panel(table, title="GPU", border_style=SAKURA, box=box.ROUNDED)


def _disk_panel(status: dict[str, Any]) -> Panel:
    disk = _section(status, "disk")
    table = Table(expand=True, box=None, padding=(0, 1))
    table.add_column("Disque / partition", style=NEON_CYAN)
    table.add_column("Lecture", justify="right")
    table.add_column("Écriture", justify="right")
    table.add_column("Occupation", ratio=1)
    count = 0
    per_disk = disk.get("per_disk")
    if isinstance(per_disk, dict):
        for name, values in per_disk.items():
            values = values if isinstance(values, dict) else {}
            table.add_row(str(name), _number(values.get("read_mb_s"), " Mo/s"),
                          _number(values.get("write_mb_s"), " Mo/s"), "")
            count += 1
    partitions = disk.get("partitions")
    if isinstance(partitions, list):
        for item in partitions:
            item = item if isinstance(item, dict) else {}
            table.add_row(str(item.get("mount") or "—"), "", "", _bar(item.get("percent"), partition=True))
            count += 1
    if not count:
        missing = Text("—", style="grey50")
        table.add_row(missing, missing.copy(), missing.copy(), missing.copy())
    return Panel(table, title="Disques", border_style=SAKURA, box=box.ROUNDED)


def _process_panel(status: dict[str, Any]) -> Panel:
    table = Table(expand=True, box=None, padding=(0, 1))
    for title, justify in (("Top CPU", "left"), ("%", "right"), ("Mo", "right"),
                           ("Top RAM", "left"), ("%", "right"), ("Mo", "right")):
        table.add_column(title, justify=justify, style=NEON_CYAN if "Top" in title else None,
                         overflow="ellipsis")
    cpu = status.get("top_cpu") if isinstance(status.get("top_cpu"), list) else []
    ram = status.get("top_ram") if isinstance(status.get("top_ram"), list) else []
    for index in range(max(len(cpu), len(ram), 1)):
        left = cpu[index] if index < len(cpu) and isinstance(cpu[index], dict) else {}
        right = ram[index] if index < len(ram) and isinstance(ram[index], dict) else {}
        table.add_row(str(left.get("name") or "—"), _number(left.get("cpu_percent")),
                      _number(left.get("ram_mb")), str(right.get("name") or "—"),
                      _number(right.get("cpu_percent")), _number(right.get("ram_mb")))
    return Panel(table, title="Plus gourmands", border_style=SAKURA, box=box.ROUNDED)


def _header(status: dict[str, Any]) -> Text:
    clock = "—"
    if isinstance(status.get("time"), str):
        try:
            clock = datetime.fromisoformat(status["time"]).strftime("%H:%M:%S")
        except ValueError:
            pass
    text = Text("🌸 Sakura Optimizer", style=f"bold {SAKURA}")
    text.append(f"  {clock}", style=NEON_CYAN if clock != "—" else "grey50")
    return text


def _footer(status: dict[str, Any]) -> Text:
    notes = []
    reason = _section(status, "temps").get("reason")
    if reason:
        notes.append(str(reason))
    errors = status.get("errors")
    if isinstance(errors, dict) and errors:
        notes.append("Erreurs : " + " · ".join(f"{key}: {value}" for key, value in errors.items()))
    return Text("  |  ".join(notes) if notes else "Capteurs opérationnels", style="dim grey62")


def render(status: dict) -> Group:
    """Construit un objet Rich pur, sans aucune lecture matérielle."""
    status = status if isinstance(status, dict) else {}
    upper = Table.grid(expand=True, padding=(0, 1))
    upper.add_column(ratio=3)
    upper.add_column(ratio=2)
    upper.add_row(_cpu_panel(status), Group(_ram_panel(status), _gpu_panel(status)))
    return Group(Panel(_header(status), border_style=SAKURA, box=box.ROUNDED), upper,
                 _disk_panel(status), _process_panel(status), _footer(status))


def run(interval: float = 1.0) -> int:
    """Actualise le moniteur jusqu'à Ctrl+C."""
    try:
        sampler = Sampler()
        status = sampler.sample()
        with Live(render(status), screen=False, refresh_per_second=4) as live:
            while True:
                time.sleep(interval)
                live.update(render(sampler.sample()), refresh=True)
    except KeyboardInterrupt:
        print("À bientôt 🌸")
    return 0
