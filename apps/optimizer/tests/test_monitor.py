"""Tests de l'affichage terminal de Sakura Optimizer."""

import json
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from sakura_opt.monitor import render

OPTIMIZER = Path(__file__).resolve().parents[1] / "optimizer.py"


def _text(status):
    console = Console(record=True, width=100)
    console.print(render(status))
    return console.export_text()


def test_render_status_complet():
    status = {
        "time": "2026-11-02T14:08:09+01:00",
        "cpu": {"percent": 42.1, "per_core": [12.0, 64.0, 91.0, 32.0], "freq_mhz": 4200.0},
        "ram": {"percent": 57.4, "used_gb": 18.3, "total_gb": 31.9, "swap_percent": 2.0},
        "gpu": {"percent": 73.0, "vram_used_gb": 7.2, "vram_total_gb": 16.0},
        "temps": {"cpu": 62.0, "gpu": 58.0, "gpu_hotspot": 72.0, "reason": None},
        "disk": {"per_disk": {"PhysicalDrive0": {"read_mb_s": 12.4, "write_mb_s": 3.1}},
                 "partitions": [{"mount": "C:\\", "percent": 91.0}]},
        "top_cpu": [{"name": "jeu.exe", "cpu_percent": 24.5, "ram_mb": 850.0}],
        "top_ram": [{"name": "navigateur.exe", "cpu_percent": 3.0, "ram_mb": 2100.0}],
    }
    assert "Sakura Optimizer" in _text(status)


def test_render_status_vide_affiche_des_tirets():
    status = {key: None for key in (
        "time", "cpu", "ram", "gpu", "temps", "disk", "top_cpu", "top_ram", "errors"
    )}
    text = _text(status)
    assert "Sakura Optimizer" in text
    assert "—" in text


def test_monitor_json_est_valide():
    result = subprocess.run(
        [sys.executable, str(OPTIMIZER), "monitor", "--json"],
        capture_output=True,
        text=True, encoding="utf-8",
    )
    assert result.returncode == 0
    assert "cpu" in json.loads(result.stdout)
