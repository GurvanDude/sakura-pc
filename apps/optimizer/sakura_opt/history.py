"""Historique local et compact des mesures de Sakura Optimizer."""

from __future__ import annotations

from collections import Counter
from contextlib import closing
import math
import os
from pathlib import Path
import sqlite3
import statistics
import threading
import time
from typing import Any, Callable

from core import paths

from .names import group_apps


FIELDS = (
    "cpu", "ram", "gpu", "vram_gb", "cpu_temp", "gpu_temp",
    "gpu_hotspot", "cpu_clock", "disk_read", "disk_write",
    "core_max", "swap", "vram_total_gb", "disk_busy", "c_free_gb",
    "top_cpu", "top_ram_gb",
)
TEMPERATURE_FIELDS = {"cpu_temp", "gpu_temp", "gpu_hotspot"}
TEXT_FIELDS = ("top_app", "fg_app", "top_cpu_app", "top_ram_app")
NEW_COLUMNS = {
    "core_max": "REAL",
    "swap": "REAL",
    "vram_total_gb": "REAL",
    "disk_busy": "REAL",
    "c_free_gb": "REAL",
    "fg_app": "TEXT",
    "top_cpu_app": "TEXT",
    "top_cpu": "REAL",
    "top_ram_app": "TEXT",
    "top_ram_gb": "REAL",
}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _section(status: dict[str, Any], name: str) -> dict[str, Any]:
    value = status.get(name)
    return value if isinstance(value, dict) else {}


class History:
    """Accès SQLite sans conserver de connexion ouverte entre les appels."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(db_path) if db_path is not None else paths.USER / "history.db"
        self.now = now
        self._last_prune: float | None = None
        self._prune_lock = threading.Lock()

    def _connect(self, timeout: float = 2.0) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=timeout)
        connection.row_factory = sqlite3.Row
        return connection

    def _create(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS samples (
                t REAL NOT NULL,
                cpu REAL, ram REAL, gpu REAL, vram_gb REAL,
                cpu_temp REAL, gpu_temp REAL, gpu_hotspot REAL,
                cpu_clock REAL, disk_read REAL, disk_write REAL,
                top_app TEXT
            )
            """
        )
        existing = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(samples)").fetchall()
        }
        for name, sql_type in NEW_COLUMNS.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE samples ADD COLUMN {name} {sql_type}")
        connection.execute("CREATE INDEX IF NOT EXISTS samples_t ON samples(t)")

    @staticmethod
    def _foreground_app() -> str | None:
        """Lit l'application au premier plan sans demander de droit supplémentaire."""
        try:
            import win32gui
            import win32process

            handle = win32gui.GetForegroundWindow()
            if not handle:
                return None
            title = str(win32gui.GetWindowText(handle) or "")
            if "sakura optimizer" in title.casefold():
                return None
            _thread, pid = win32process.GetWindowThreadProcessId(handle)
            if not pid or int(pid) == os.getpid():
                return None
            import psutil

            raw_name = psutil.Process(int(pid)).name()
            plain = Path(raw_name).stem.casefold()
            if plain == "explorer" or "sakura optimizer" in plain:
                return None
            from .names import friendly_name

            name = friendly_name(int(pid), raw_name).strip()
            if not name or name == "Windows" or "sakura optimizer" in name.casefold():
                return None
            return name
        except Exception:
            return None

    @staticmethod
    def _top_process(status: dict[str, Any], key: str, value_key: str) -> tuple[str | None, float | None]:
        rows = status.get(key)
        if not isinstance(rows, list):
            return None, None
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("friendly_name") or row.get("name") or "").strip()
            if not name or name == "Windows":
                continue
            value = _number(row.get(value_key))
            return (Path(name).stem if name.lower().endswith(".exe") else name), value
        return None, None

    @staticmethod
    def _top_app(status: dict[str, Any]) -> str | None:
        try:
            return next(
                (str(app["name"]) for app in group_apps(status) if app.get("name") != "Windows"),
                None,
            )
        except Exception:
            return None

    def record(self, status: dict[str, Any] | None, temps: dict[str, Any] | None = None) -> None:
        """Ajoute une mesure ; une valeur de capteur absente reste NULL."""
        status = status if isinstance(status, dict) else {}
        cpu, ram, gpu, disk = (_section(status, key) for key in ("cpu", "ram", "gpu", "disk"))
        temperatures = temps if isinstance(temps, dict) else _section(status, "temps")
        cores = cpu.get("per_core") if isinstance(cpu.get("per_core"), list) else []
        core_values = [value for value in (_number(item) for item in cores) if value is not None]
        per_disk = disk.get("per_disk") if isinstance(disk.get("per_disk"), dict) else {}
        busy_values = [
            value
            for item in per_disk.values() if isinstance(item, dict)
            for value in [_number(item.get("busy_percent"))]
            if value is not None
        ]
        partitions = disk.get("partitions") if isinstance(disk.get("partitions"), list) else []
        c_free = next(
            (
                _number(item.get("free_gb")) for item in partitions
                if isinstance(item, dict) and str(item.get("mount") or "").upper().startswith("C:")
            ),
            None,
        )
        top_cpu_app, top_cpu = self._top_process(status, "top_cpu", "cpu_percent")
        top_ram_app, top_ram_mb = self._top_process(status, "top_ram", "ram_mb")
        values = (
            self.now(),
            _number(cpu.get("percent")),
            _number(ram.get("percent")),
            _number(gpu.get("percent")),
            _number(gpu.get("vram_used_gb")),
            _number(temperatures.get("cpu")),
            _number(temperatures.get("gpu")),
            _number(temperatures.get("gpu_hotspot")),
            _number(temperatures.get("cpu_clock_mhz")),
            _number(disk.get("read_mb_s")),
            _number(disk.get("write_mb_s")),
            self._top_app(status),
            max(core_values) if core_values else None,
            _number(ram.get("swap_percent")),
            _number(gpu.get("vram_total_gb")),
            max(busy_values) if busy_values else None,
            c_free,
            self._foreground_app(),
            top_cpu_app,
            top_cpu,
            top_ram_app,
            round(top_ram_mb / 1024, 3) if top_ram_mb is not None else None,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                self._create(connection)
                columns = (
                    "t, cpu, ram, gpu, vram_gb, cpu_temp, gpu_temp, gpu_hotspot, "
                    "cpu_clock, disk_read, disk_write, top_app, core_max, swap, "
                    "vram_total_gb, disk_busy, c_free_gb, fg_app, top_cpu_app, "
                    "top_cpu, top_ram_app, top_ram_gb"
                )
                placeholders = ", ".join("?" for _ in values)
                connection.execute(
                    f"INSERT INTO samples ({columns}) VALUES ({placeholders})", values
                )
        self._prune_if_due()

    def _prune_if_due(self, days: int = 7) -> None:
        now = self.now()
        with self._prune_lock:
            if self._last_prune is not None and now - self._last_prune < 3600:
                return
            self._last_prune = now
        self.prune(days)

    def prune(self, days: int = 7) -> None:
        """Supprime les souvenirs plus anciens que la durée demandée."""
        if not self.path.exists():
            return
        try:
            with closing(self._connect(timeout=0.0)) as connection:
                with connection:
                    connection.execute("DELETE FROM samples WHERE t < ?", (self.now() - days * 86400,))
        except (OSError, sqlite3.Error):
            return

    def _rows(self, since_s: float) -> list[sqlite3.Row]:
        if not self.path.exists():
            return []
        try:
            with closing(self._connect(timeout=0.0)) as connection:
                with connection:
                    self._create(connection)
                    return connection.execute(
                        "SELECT * FROM samples WHERE t >= ? ORDER BY t",
                        (self.now() - max(0.0, float(since_s)),),
                    ).fetchall()
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return []

    def query(self, since_s: float, points: int = 120) -> list[dict[str, Any]]:
        """Réduit la période en tranches temporelles, sans inventer les trous."""
        try:
            duration = max(0.0, float(since_s))
            point_count = int(points)
        except (TypeError, ValueError, OverflowError):
            return []
        rows = self._rows(duration)
        if not rows or point_count <= 0:
            return []
        start = self.now() - duration
        width = max(duration / point_count, 0.001)
        buckets: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            index = min(point_count - 1, max(0, int((float(row["t"]) - start) / width)))
            buckets.setdefault(index, []).append(row)

        result = []
        for bucket in buckets.values():
            item: dict[str, Any] = {"t": round(sum(float(row["t"]) for row in bucket) / len(bucket), 3)}
            for field in FIELDS:
                values = [float(row[field]) for row in bucket if row[field] is not None]
                item[field] = (
                    round(max(values) if field in TEMPERATURE_FIELDS else sum(values) / len(values), 2)
                    if values else None
                )
            for field in TEXT_FIELDS:
                names = Counter(str(row[field]) for row in bucket if row[field])
                item[field] = names.most_common(1)[0][0] if names else None
            result.append(item)
        return result

    def baseline(self, since_s: float = 7 * 86400) -> dict[str, float]:
        """Renvoie les valeurs médianes connues pour comparer avec l'habitude."""
        rows = self._rows(since_s)
        result: dict[str, float] = {}
        for field in ("cpu_temp", "gpu_temp", "gpu_hotspot"):
            values = [float(row[field]) for row in rows if row[field] is not None]
            if values:
                result[field] = round(statistics.median(values), 2)
        return result

    def summary(self, since_s: float) -> dict[str, Any]:
        """Résume une période. Une base absente ou occupée donne un résultat vide."""
        try:
            return self._summary(since_s)
        except Exception:
            return {}

    def _summary(self, since_s: float) -> dict[str, Any]:
        rows = self._rows(since_s)
        if not rows:
            return {}
        result: dict[str, Any] = {
            "sample_count": len(rows),
            "duration_s": max(0.0, float(rows[-1]["t"]) - float(rows[0]["t"])),
        }
        for field in FIELDS:
            known = [(float(row[field]), float(row["t"])) for row in rows if row[field] is not None]
            if not known:
                result[f"avg_{field}"] = None
                result[f"max_{field}"] = None
                result[f"max_{field}_t"] = None
                continue
            maximum = max(known, key=lambda pair: pair[0])
            result[f"avg_{field}"] = round(sum(value for value, _ in known) / len(known), 2)
            result[f"max_{field}"] = round(maximum[0], 2)
            result[f"max_{field}_t"] = maximum[1]
        apps = Counter(str(row["top_app"]) for row in rows if row["top_app"])
        result["top_app"] = apps.most_common(1)[0][0] if apps else None
        return result


_default = History()


def record(status: dict[str, Any] | None, temps: dict[str, Any] | None = None) -> None:
    _default.record(status, temps)


def prune(days: int = 7) -> None:
    _default._prune_if_due(days)


def query(since_s: float, points: int = 120) -> list[dict[str, Any]]:
    return _default.query(since_s, points)


def summary(since_s: float) -> dict[str, Any]:
    return _default.summary(since_s)
