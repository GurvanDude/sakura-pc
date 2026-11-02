"""Mesures système réutilisables par l'interface et Sakura AI."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import time
from typing import Any, Callable
import winreg

import psutil

from .temps import read_temps


BYTES_PER_GB = 1024**3
BYTES_PER_MB = 1024**2
ENGINE_TYPE = re.compile(r"engtype_([^_#]+)", re.IGNORECASE)
PID_PREFIX = re.compile(r"^pid_\d+_", re.IGNORECASE)


class _PdhGpuReader:
    """Garde une requête PDH ouverte pour les compteurs GPU dynamiques."""

    def __init__(self, pdh: Any | None = None) -> None:
        if pdh is None:
            import win32pdh as pdh

        self.pdh = pdh
        self.query = pdh.OpenQuery()
        self.engine_counter = pdh.AddEnglishCounter(
            self.query, r"\GPU Engine(*)\Utilization Percentage"
        )
        self.memory_counter = pdh.AddEnglishCounter(
            self.query, r"\GPU Adapter Memory(*)\Dedicated Usage"
        )
        pdh.CollectQueryData(self.query)

    def read(self) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        """Collecte les tableaux PDH, dont les instances sont réévaluées."""
        self.pdh.CollectQueryData(self.query)
        return self._array(self.engine_counter), self._array(self.memory_counter)

    def _array(self, counter: Any) -> list[tuple[str, float]]:
        """Normalise le résultat variable de GetFormattedCounterArray."""
        result = self.pdh.GetFormattedCounterArray(counter, self.pdh.PDH_FMT_DOUBLE)
        entries = result[1] if isinstance(result, tuple) and len(result) == 2 else result
        if isinstance(entries, dict):   # pywin32 renvoie {instance: valeur}
            entries = entries.items()
        return [(str(name), float(value)) for name, value in entries]


def _read_vram_total() -> float | None:
    """Lit dans le registre la VRAM de la carte physique, hors Parsec."""
    base = (
        r"SYSTEM\CurrentControlSet\Control\Class"
        r"\{4d36e968-e325-11ce-bfc1-08002be10318}"
    )
    sizes = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as key:
            for index in range(winreg.QueryInfoKey(key)[0]):
                name = winreg.EnumKey(key, index)
                if not re.fullmatch(r"\d{4}", name):
                    continue
                try:
                    with winreg.OpenKey(key, name) as adapter:
                        description = str(winreg.QueryValueEx(adapter, "DriverDesc")[0])
                        if "parsec" in description.lower():
                            continue
                        raw = winreg.QueryValueEx(adapter, "HardwareInformation.qwMemorySize")[0]
                        size = int.from_bytes(raw, "little") if isinstance(raw, bytes) else int(raw)
                        if size > 0:
                            sizes.append(size / BYTES_PER_GB)
                except (FileNotFoundError, OSError, ValueError, TypeError):
                    continue
    except OSError:
        return None
    return max(sizes) if sizes else None


class Sampler:
    """Prend des mesures et conserve les compteurs nécessaires aux débits."""

    def __init__(
        self,
        psutil_module: Any = psutil,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] | None = None,
        temps_reader: Callable[[], dict[str, Any]] = read_temps,
        gpu_reader: Any | None = None,
        vram_total_reader: Callable[[], float | None] = _read_vram_total,
        pdh_module: Any | None = None,
    ) -> None:
        self.psutil = psutil_module
        self.monotonic = monotonic
        self.now = now or (lambda: datetime.now(timezone.utc).astimezone())
        self.temps_reader = temps_reader
        self.vram_total_reader = vram_total_reader
        self._previous_disks: dict[str, Any] | None = None
        self._previous_disk_time: float | None = None
        self._gpu_init_error: str | None = None
        if gpu_reader is not None:
            self.gpu_reader = gpu_reader
        else:
            try:
                self.gpu_reader = _PdhGpuReader(pdh_module)
            except Exception as exc:
                self.gpu_reader = None
                self._gpu_init_error = str(exc)

    def sample(self) -> dict[str, Any]:
        """Renvoie un échantillon entièrement sérialisable, sans lever."""
        try:
            timestamp = self.now().isoformat()
        except Exception:
            timestamp = datetime.now(timezone.utc).isoformat()
        result: dict[str, Any] = {"time": timestamp}
        errors: dict[str, str] = {}

        self._capture(result, errors, "cpu", self._cpu)
        self._capture(result, errors, "ram", self._ram)
        self._capture(result, errors, "disk", self._disk)
        self._capture(result, errors, "gpu", self._gpu)
        self._capture(result, errors, "temps", self.temps_reader)
        self._processes(result, errors)
        if errors:
            result["errors"] = errors
        return result

    @staticmethod
    def _capture(
        result: dict[str, Any], errors: dict[str, str], section: str, reader: Callable[[], Any]
    ) -> None:
        """Isole l'erreur d'un capteur du reste de l'échantillon."""
        try:
            result[section] = reader()
        except Exception as exc:
            result[section] = None
            errors[section] = str(exc) or type(exc).__name__

    def _cpu(self) -> dict[str, Any]:
        """Lit l'utilisation et la fréquence du processeur."""
        percent = self.psutil.cpu_percent(interval=None)
        per_core = self.psutil.cpu_percent(interval=None, percpu=True)
        frequency = self.psutil.cpu_freq()
        return {
            "percent": _round(percent),
            "per_core": [_round(value) for value in per_core],
            "freq_mhz": _round(frequency.current) if frequency else None,
        }

    def _ram(self) -> dict[str, Any]:
        """Lit la mémoire vive et le fichier d'échange."""
        memory = self.psutil.virtual_memory()
        swap = self.psutil.swap_memory()
        return {
            "percent": _round(memory.percent),
            "used_gb": _round(memory.used / BYTES_PER_GB),
            "total_gb": _round(memory.total / BYTES_PER_GB),
            "available_gb": _round(memory.available / BYTES_PER_GB),
            "swap_percent": _round(swap.percent),
        }

    def _disk(self) -> dict[str, Any]:
        """Calcule les débits par différence entre deux lectures."""
        current_time = self.monotonic()
        counters = self.psutil.disk_io_counters(perdisk=True) or {}
        elapsed = current_time - self._previous_disk_time if self._previous_disk_time is not None else None
        per_disk: dict[str, dict[str, float | None]] = {}
        total_read = 0.0
        total_write = 0.0
        for name, counter in counters.items():
            previous = (self._previous_disks or {}).get(name)
            read_rate = self._rate(counter.read_bytes, previous, "read_bytes", elapsed, BYTES_PER_MB)
            write_rate = self._rate(
                counter.write_bytes, previous, "write_bytes", elapsed, BYTES_PER_MB
            )
            busy = (
                self._rate(counter.busy_time, previous, "busy_time", elapsed, 10.0)
                if hasattr(counter, "busy_time")
                else None
            )
            if busy is not None:
                busy = min(100.0, max(0.0, busy))
            per_disk[str(name)] = {
                "read_mb_s": _round(read_rate),
                "write_mb_s": _round(write_rate),
                "busy_percent": _round(busy) if busy is not None else None,
            }
            total_read += read_rate
            total_write += write_rate

        partitions = []
        for partition in self.psutil.disk_partitions(all=False):
            try:
                usage = self.psutil.disk_usage(partition.mountpoint)
            except (OSError, self.psutil.AccessDenied):
                continue
            partitions.append(
                {
                    "mount": str(partition.mountpoint),
                    "percent": _round(usage.percent),
                    "free_gb": _round(usage.free / BYTES_PER_GB),
                }
            )

        self._previous_disks = counters
        self._previous_disk_time = current_time
        return {
            "read_mb_s": _round(total_read),
            "write_mb_s": _round(total_write),
            "per_disk": per_disk,
            "partitions": partitions,
        }

    @staticmethod
    def _rate(
        current: float, previous: Any | None, attribute: str, elapsed: float | None, divisor: float
    ) -> float:
        """Calcule un débit positif, nul pour la première lecture."""
        if previous is None or elapsed is None or elapsed <= 0:
            return 0.0
        return max(0.0, (current - getattr(previous, attribute)) / elapsed / divisor)

    def _gpu(self) -> dict[str, Any]:
        """Agrège les moteurs GPU comme le Gestionnaire des tâches."""
        if self.gpu_reader is None:
            raise RuntimeError(self._gpu_init_error or "compteurs GPU indisponibles")
        engines, memory = self.gpu_reader.read()
        totals: dict[str, float] = {}
        for instance, value in engines:
            if ENGINE_TYPE.search(instance):
                # un moteur = carte (luid) + moteur physique ; on additionne ses processus
                engine = PID_PREFIX.sub("", instance)
                totals[engine] = totals.get(engine, 0.0) + max(0.0, float(value))
        if not totals and not memory:
            raise RuntimeError("aucun compteur GPU disponible")
        percent = min(100.0, max(totals.values(), default=0.0))
        used = max((max(0.0, float(value)) for _, value in memory), default=0.0)
        total = self.vram_total_reader()
        return {
            "percent": _round(percent),
            "vram_used_gb": _round(used / BYTES_PER_GB),
            "vram_total_gb": _round(total) if total is not None else None,
        }

    def _processes(self, result: dict[str, Any], errors: dict[str, str]) -> None:
        """Construit les classements CPU et mémoire en une seule passe."""
        try:
            logical_cpus = self.psutil.cpu_count(logical=True) or 1
            rows = []
            for process in self.psutil.process_iter(["pid", "name", "memory_info"]):
                try:
                    name = process.info.get("name") or "Processus sans nom"
                    if name.lower() == "system idle process":
                        continue
                    memory = process.info.get("memory_info")
                    rows.append(
                        {
                            "pid": int(process.info["pid"]),
                            "name": str(name),
                            "cpu_percent": _round(
                                min(100.0, max(0.0, process.cpu_percent(interval=None) / logical_cpus))
                            ),
                            "ram_mb": _round(memory.rss / BYTES_PER_MB if memory else 0.0),
                        }
                    )
                except (self.psutil.NoSuchProcess, self.psutil.AccessDenied, KeyError, TypeError):
                    continue
            result["top_cpu"] = sorted(rows, key=lambda row: row["cpu_percent"], reverse=True)[:5]
            result["top_ram"] = sorted(rows, key=lambda row: row["ram_mb"], reverse=True)[:5]
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            result["top_cpu"] = None
            result["top_ram"] = None
            errors["top_cpu"] = message
            errors["top_ram"] = message


def _round(value: float) -> float:
    """Arrondit les mesures au dixième."""
    return round(float(value), 1)
