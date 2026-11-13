"""Lecture des températures fournies par LibreHardwareMonitor."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import time
from typing import Any

from core import paths


_computer: Any | None = None
_load_error: str | None = None
_loaded_from: Path | None = None


def _empty(reason: str | None = None) -> dict[str, Any]:
    """Construit une réponse vide et sérialisable."""
    return {
        "cpu": None,
        "gpu": None,
        "gpu_hotspot": None,
        "cpu_clock_mhz": None,
        "cpu_power_w": None,
        "disks": {},
        "source": None,
        "reason": reason,
    }


def _load_computer(dll_path: Path) -> Any:
    """Charge et ouvre LibreHardwareMonitor une seule fois."""
    global _computer, _load_error, _loaded_from

    if _computer is not None and _loaded_from == dll_path:
        return _computer
    if _load_error is not None and _loaded_from == dll_path:
        raise RuntimeError(_load_error)

    _loaded_from = dll_path
    try:
        import clr

        clr.AddReference(str(dll_path))
        from LibreHardwareMonitor.Hardware import Computer

        computer = Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = True
        computer.IsStorageEnabled = True
        computer.Open()
        _computer = computer
        _load_error = None
        return computer
    except Exception as exc:
        _computer = None
        _load_error = str(exc)
        raise


def _hardware_tree(hardware: Any):
    """Parcourt un matériel et tous ses sous-matériels après mise à jour."""
    hardware.Update()
    yield hardware
    for child in hardware.SubHardware:
        yield from _hardware_tree(child)


def _sensors(hardware: Any, sensor_type: str) -> list[tuple[str, float]]:
    """Renvoie les capteurs renseignés d'un type donné."""
    values = []
    for sensor in hardware.Sensors:
        if str(sensor.SensorType) != sensor_type or sensor.Value is None:
            continue
        try:
            values.append((str(sensor.Name), float(sensor.Value)))
        except (TypeError, ValueError, OverflowError):
            continue
    return values


def _valid_temperature(value: Any) -> float | None:
    """Écarte les températures absentes ou physiquement incohérentes."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and 0 < number <= 150 else None


def _rounded_temperature(value: Any) -> float | None:
    valid = _valid_temperature(value)
    return round(valid, 1) if valid is not None else None


def _positive(value: Any) -> float | None:
    """Normalise une mesure qui n'a de sens qu'au-dessus de zéro."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round(number, 1) if math.isfinite(number) and number > 0 else None


def _find_dll() -> Path:
    """Cherche d'abord la copie protégée, puis les emplacements de développement."""
    name = Path("LibreHardwareMonitor") / "LibreHardwareMonitorLib.dll"
    candidates = [
        _program_data() / "SakuraPC" / "temps" / name,
        paths.USER / "vendor" / name,
        paths.app("optimizer") / "vendor" / name,
    ]
    return next((c for c in candidates if c.is_file()), candidates[0])


def _program_data() -> Path:
    """Renvoie ProgramData, surchargeable par l'environnement pour les tests."""
    return Path(os.environ.get("PROGRAMDATA", os.environ.get("ProgramData", r"C:\ProgramData")))


def read_direct(dll_path: Path | None = None) -> dict[str, Any]:
    """Lit directement le matériel, sans jamais propager une erreur."""
    path = dll_path or _find_dll()
    if not path.is_file():
        return _empty("LibreHardwareMonitor n'est pas installé")

    try:
        computer = _load_computer(path)
        cpu_temperatures: list[tuple[str, float]] = []
        gpu_temperatures: list[tuple[str, float]] = []
        cpu_clocks: list[float] = []
        cpu_powers: list[tuple[str, float]] = []
        disks: dict[str, float] = {}

        for root in computer.Hardware:
            kind = str(root.HardwareType).lower()
            root_temperatures: list[tuple[str, float]] = []
            for hardware in _hardware_tree(root):
                root_temperatures.extend(_sensors(hardware, "Temperature"))
                if "cpu" in kind:
                    cpu_clocks.extend(
                        value for name, value in _sensors(hardware, "Clock")
                        if name.startswith("Core #") and value > 0
                    )
                    cpu_powers.extend(_sensors(hardware, "Power"))

            if "cpu" in kind:
                cpu_temperatures.extend(root_temperatures)
            elif "gpu" in kind:
                gpu_temperatures.extend(root_temperatures)
            elif "storage" in kind:
                temperature = next(
                    (_rounded_temperature(value) for _, value in root_temperatures
                     if _valid_temperature(value) is not None),
                    None,
                )
                if temperature is not None:
                    disks[str(root.Name)] = temperature

        cpu = _rounded_temperature(_preferred(cpu_temperatures, ("Core (Tctl/Tdie)", "Tctl"), fallback=True))
        gpu = _rounded_temperature(_preferred(gpu_temperatures, ("GPU Core",)))
        hotspot = _rounded_temperature(_preferred(gpu_temperatures, ("GPU Hot Spot",)))
        package_power = _preferred(cpu_powers, ("Package", "CPU Package"))
        reason = (
            None if cpu is not None
            else "température du processeur : il faut installer le lecteur de températures"
        )
        return {
            "cpu": cpu,
            "gpu": gpu,
            "gpu_hotspot": hotspot,
            "cpu_clock_mhz": _positive(sum(cpu_clocks) / len(cpu_clocks)) if cpu_clocks else None,
            "cpu_power_w": _positive(package_power),
            "disks": disks,
            "source": "LibreHardwareMonitor",
            "reason": reason,
        }
    except Exception as exc:
        return _empty(f"LibreHardwareMonitor indisponible : {exc}")


def read_temps(dll_path: Path | None = None) -> dict[str, Any]:
    """Préfère une mesure admin récente, puis tente la lecture directe."""
    relay_file = _program_data() / "SakuraPC" / "temps" / "temps.json"
    try:
        cached = json.loads(relay_file.read_text(encoding="utf-8"))
        age = time.time() - float(cached.get("time"))
        if isinstance(cached, dict) and 0 <= age < 10 and _valid_temperature(cached.get("cpu")) is not None:
            result = dict(cached)
            result["cpu"] = _rounded_temperature(result.get("cpu"))
            result["gpu"] = _rounded_temperature(result.get("gpu"))
            result["gpu_hotspot"] = _rounded_temperature(result.get("gpu_hotspot"))
            result["cpu_clock_mhz"] = _positive(result.get("cpu_clock_mhz"))
            result["cpu_power_w"] = _positive(result.get("cpu_power_w"))
            disks = result.get("disks")
            result["disks"] = {
                str(name): temperature
                for name, value in (disks.items() if isinstance(disks, dict) else [])
                if (temperature := _rounded_temperature(value)) is not None
            }
            result["source"] = "lecteur admin"
            result["reason"] = None
            return result
    except Exception:
        pass
    return read_direct(dll_path)


def _preferred(
    sensors: list[tuple[str, float]], names: tuple[str, ...], fallback: bool = False
) -> float | None:
    """Choisit un capteur par ordre de préférence."""
    for wanted in names:
        for name, value in sensors:
            if name == wanted:
                return value
    return sensors[0][1] if fallback and sensors else None
