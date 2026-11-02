"""Lecture des températures fournies par LibreHardwareMonitor."""

from __future__ import annotations

from pathlib import Path
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


def _temperature_sensors(hardware: Any) -> list[tuple[str, float]]:
    """Renvoie les capteurs de température valides d'un matériel."""
    values = []
    for sensor in hardware.Sensors:
        if str(sensor.SensorType) != "Temperature" or sensor.Value is None:
            continue
        values.append((str(sensor.Name), float(sensor.Value)))
    return values


def read_temps(dll_path: Path | None = None) -> dict[str, Any]:
    """Lit les températures sans jamais propager une erreur de matériel."""
    path = dll_path or paths.USER / "vendor" / "LibreHardwareMonitor" / "LibreHardwareMonitorLib.dll"
    if not path.is_file():
        return _empty("LibreHardwareMonitor n'est pas installé")

    try:
        computer = _load_computer(path)
        cpu_candidates: list[tuple[str, float]] = []
        gpu_candidates: list[tuple[str, float]] = []
        disks: dict[str, float] = {}

        for root in computer.Hardware:
            kind = str(root.HardwareType).lower()
            root_temperatures: list[tuple[str, float]] = []
            for hardware in _hardware_tree(root):
                root_temperatures.extend(_temperature_sensors(hardware))

            if "cpu" in kind:
                cpu_candidates.extend(root_temperatures)
            elif "gpu" in kind:
                gpu_candidates.extend(root_temperatures)
            elif "storage" in kind and root_temperatures:
                disks[str(root.Name)] = round(root_temperatures[0][1], 1)

        cpu = _preferred(cpu_candidates, ("Core (Tctl/Tdie)", "Tctl"), fallback=True)
        gpu = _preferred(gpu_candidates, ("GPU Core",))
        hotspot = _preferred(gpu_candidates, ("GPU Hot Spot",))
        reason = None if cpu is not None else "température CPU : droits admin requis"
        return {
            "cpu": _rounded(cpu),
            "gpu": _rounded(gpu),
            "gpu_hotspot": _rounded(hotspot),
            "disks": disks,
            "source": "LibreHardwareMonitor",
            "reason": reason,
        }
    except Exception as exc:
        return _empty(f"LibreHardwareMonitor indisponible : {exc}")


def _preferred(
    sensors: list[tuple[str, float]], names: tuple[str, ...], fallback: bool = False
) -> float | None:
    """Choisit un capteur par ordre de préférence."""
    for wanted in names:
        for name, value in sensors:
            if name == wanted:
                return value
    return sensors[0][1] if fallback and sensors else None


def _rounded(value: float | None) -> float | None:
    """Arrondit une température quand elle existe."""
    return round(value, 1) if value is not None else None
