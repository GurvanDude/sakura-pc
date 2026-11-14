"""Diagnostic compréhensible des ralentissements récents."""

from __future__ import annotations

from collections import Counter, defaultdict
import math

import psutil
from typing import Any, Callable


SUSTAINED_RATIO = 0.60
ENOUGH_DATA_SECONDS = 120
GPU_LIMIT_PERCENT = 95
GPU_GAME_PERCENT = 70
VRAM_FULL_PERCENT = 95
CPU_FULL_PERCENT = 90
CPU_LOW_PERCENT = 50
CPU_CORE_FULL_PERCENT = 95
CPU_CORE_BUSY_PERCENT = 75   # cœur le plus chargé, quand une appli occupe à elle seule ~1 cœur
ONE_CORE_SHARE = 0.8         # part d'un cœur entier (psutil normalise sur tous les cœurs)
RAM_FULL_PERCENT = 90
RAM_PRESSURE_PERCENT = 85
DISK_BUSY_PERCENT = 90
DISK_PRESSURE_PERCENT = 50
SWAP_RISE_PERCENT = 1
C_FREE_GB = 15
CPU_HOT_C = 90
CPU_THROTTLE_C = 85
CPU_THROTTLE_RATIO = 0.80
GPU_HOT_C = 90
GPU_HOTSPOT_C = 105
BACKGROUND_CPU_PERCENT = 15
BACKGROUND_RAM_GB = 2
HOTTER_THAN_USUAL_C = 10

SEVERITY_ORDER = {"grave": 3, "attention": 2, "info": 1}
PRIORITY = {
    "ram": 100,
    "chaleur_cpu": 95,
    "chaleur_gpu": 94,
    "vram": 85,
    "cpu": 80,
    "cpu_core": 75,
    "disque": 70,
    "disk_space": 69,
    "fond": 60,
    "gpu": 50,
}
BOTTLENECK = {"disk_space": "disque"}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _section(status: dict[str, Any], key: str) -> dict[str, Any]:
    value = status.get(key)
    return value if isinstance(value, dict) else {}


def _clean_app(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    name = value.strip()
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name


def _top_process(status: dict[str, Any], key: str, value_key: str) -> tuple[str | None, float | None]:
    rows = status.get(key)
    if not isinstance(rows, list):
        return None, None
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _clean_app(row.get("friendly_name") or row.get("name"))
        if name and name != "Windows":
            return name, _number(row.get(value_key))
    return None, None


def _status_row(status: dict[str, Any] | None) -> dict[str, Any]:
    """Aplatit une mesure actuelle dans le même format que SQLite."""
    status = status if isinstance(status, dict) else {}
    cpu, ram, gpu, disk, temps = (
        _section(status, key) for key in ("cpu", "ram", "gpu", "disk", "temps")
    )
    cores = cpu.get("per_core") if isinstance(cpu.get("per_core"), list) else []
    core_values = [value for value in (_number(item) for item in cores) if value is not None]
    per_disk = disk.get("per_disk") if isinstance(disk.get("per_disk"), dict) else {}
    busy = [
        value
        for item in per_disk.values() if isinstance(item, dict)
        for value in [_number(item.get("busy_percent"))]
        if value is not None
    ]
    partitions = disk.get("partitions") if isinstance(disk.get("partitions"), list) else []
    c_free = next((
        _number(item.get("free_gb"))
        for item in partitions
        if isinstance(item, dict) and str(item.get("mount") or "").upper().startswith("C:")
    ), None)
    top_cpu_app, top_cpu = _top_process(status, "top_cpu", "cpu_percent")
    top_ram_app, top_ram_mb = _top_process(status, "top_ram", "ram_mb")
    top_app = top_cpu_app or top_ram_app
    return {
        "t": None,
        "cpu": _number(cpu.get("percent")),
        "core_max": max(core_values) if core_values else None,
        "ram": _number(ram.get("percent")),
        "swap": _number(ram.get("swap_percent")),
        "gpu": _number(gpu.get("percent")),
        "vram_gb": _number(gpu.get("vram_used_gb")),
        "vram_total_gb": _number(gpu.get("vram_total_gb")),
        "cpu_temp": _number(temps.get("cpu")),
        "gpu_temp": _number(temps.get("gpu")),
        "gpu_hotspot": _number(temps.get("gpu_hotspot")),
        "cpu_clock": _number(temps.get("cpu_clock_mhz") or cpu.get("freq_mhz")),
        "disk_busy": max(busy) if busy else None,
        "c_free_gb": c_free,
        "fg_app": _clean_app(status.get("fg_app")),
        "top_app": top_app,
        "top_cpu_app": top_cpu_app,
        "top_cpu": top_cpu,
        "top_ram_app": top_ram_app,
        "top_ram_gb": top_ram_mb / 1024 if top_ram_mb is not None else None,
    }


def _pct(value: float) -> str:
    rounded = round(value, 1)
    digits = 0 if rounded.is_integer() else 1
    return f"{rounded:.{digits}f}".replace(".", ",") + " %"


def _decimal(value: float, unit: str) -> str:
    return f"{value:.1f}".replace(".", ",") + f" {unit}"


def _values(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [value for row in rows for value in [_number(row.get(field))] if value is not None]


def _sustained(rows: list[dict[str, Any]], condition: Callable[[dict[str, Any]], bool],
               known: Callable[[dict[str, Any]], bool]) -> tuple[bool, float]:
    considered = [row for row in rows if known(row)]
    if not considered:
        return False, 0.0
    ratio = sum(1 for row in considered if condition(row)) / len(considered)
    return ratio >= SUSTAINED_RATIO, ratio


def _mode(rows: list[dict[str, Any]], field: str) -> str | None:
    names = Counter(
        name for row in rows for name in [_clean_app(row.get(field))] if name
    )
    return names.most_common(1)[0][0] if names else None


def _finding(identifier: str, severity: str, title: str, explanation: str,
             evidence: list[dict[str, str]], advice: list[str]) -> dict[str, Any]:
    return {
        "id": identifier,
        "severity": severity,
        "title": title,
        "explanation": explanation,
        "evidence": evidence,
        "advice": advice,
    }


def _sustained_evidence(ratio: float, threshold: str) -> dict[str, str]:
    return {
        "label": "Mesures concernées",
        "value": f"{_pct(ratio * 100)} à {threshold} : c'est soutenu",
    }


def _temperature_baseline_evidence(
    evidence: list[dict[str, str]], maximum: float, baseline: dict[str, Any] | None
) -> None:
    baseline = baseline if isinstance(baseline, dict) else {}
    usual = _number(baseline.get("cpu_temp") or baseline.get("median_cpu_temp"))
    if usual is None or maximum - usual < HOTTER_THAN_USUAL_C:
        return
    difference = round(maximum - usual)
    evidence.append({
        "label": "Par rapport à d'habitude",
        "value": f"plus chaud que d'habitude (+{difference} °C)",
    })


def diagnose(
    samples: list[dict[str, Any]] | None,
    status: dict[str, Any] | None,
    baseline: dict[str, Any] | None = None,
    *,
    minutes: int | float = 5,
) -> dict[str, Any]:
    """Analyse des lignes déjà mesurées, sans accès au matériel ni au disque."""
    history_rows = [dict(row) for row in (samples or []) if isinstance(row, dict)]
    times = sorted(value for row in history_rows for value in [_number(row.get("t"))] if value is not None)
    steps = [later - earlier for earlier, later in zip(times, times[1:]) if later > earlier]
    typical_step = sorted(steps)[len(steps) // 2] if steps else 0.0
    covered_seconds = times[-1] - times[0] + typical_step if len(times) >= 2 else 0.0
    enough_data = covered_seconds >= ENOUGH_DATA_SECONDS
    current = _status_row(status)
    rows = history_rows + [current] if enough_data else [current]
    if not any(any(value is not None for key, value in row.items() if key != "t") for row in rows):
        rows = history_rows[-1:] or [current]

    app = _mode(history_rows, "fg_app") or _mode(history_rows, "top_app") or current.get("top_app")
    findings: list[dict[str, Any]] = []

    gpu_limited, gpu_ratio = _sustained(
        rows,
        lambda row: _number(row.get("gpu")) >= GPU_LIMIT_PERCENT
        and _number(row.get("cpu")) < GPU_GAME_PERCENT,
        lambda row: _number(row.get("gpu")) is not None and _number(row.get("cpu")) is not None,
    )
    if gpu_limited:
        findings.append(_finding(
            "gpu", "info", "Ton jeu est limité par la carte graphique",
            "C'est elle qui fixe le nombre d'images par seconde. C'est normal quand un jeu utilise toute sa puissance.",
            [_sustained_evidence(gpu_ratio, f"{GPU_LIMIT_PERCENT} % ou plus")],
            [
                "Baisse la qualité des ombres et des effets.",
                "Baisse la résolution si tu veux gagner beaucoup de fluidité.",
                "Active FSR si le jeu le propose avec ta carte Radeon.",
                "Tu peux aussi limiter les images par seconde pour garder un rythme stable.",
            ],
        ))

    vram_full, vram_ratio = _sustained(
        rows,
        lambda row: _number(row.get("vram_total_gb")) > 0
        and _number(row.get("vram_gb")) / _number(row.get("vram_total_gb")) * 100 >= VRAM_FULL_PERCENT,
        lambda row: _number(row.get("vram_gb")) is not None
        and (_number(row.get("vram_total_gb")) or 0) > 0,
    )
    if vram_full:
        used_values = _values(rows, "vram_gb")
        total_values = _values(rows, "vram_total_gb")
        evidence = [_sustained_evidence(vram_ratio, f"{VRAM_FULL_PERCENT} % ou plus")]
        if used_values and total_values:
            evidence.append({
                "label": "Mémoire vidéo au plus haut",
                "value": f"{_decimal(max(used_values), 'Go')} utilisés sur {_decimal(max(total_values), 'Go')}",
            })
        findings.append(_finding(
            "vram", "attention", "La mémoire vidéo est pleine",
            "Quand les textures ne tiennent plus dans la carte graphique, le jeu peut avoir des saccades.",
            evidence,
            ["Baisse d'abord la qualité des textures dans le jeu."],
        ))

    cpu_full, cpu_ratio = _sustained(
        rows, lambda row: _number(row.get("cpu")) >= CPU_FULL_PERCENT,
        lambda row: _number(row.get("cpu")) is not None,
    )
    if cpu_full:
        cpu_app = _mode(rows, "top_cpu_app")
        cpu_values = [
            _number(row.get("top_cpu")) for row in rows
            if _clean_app(row.get("top_cpu_app")) == cpu_app and _number(row.get("top_cpu")) is not None
        ]
        evidence = [_sustained_evidence(cpu_ratio, f"{CPU_FULL_PERCENT} % ou plus")]
        if cpu_app:
            value = f"{cpu_app}"
            if cpu_values:
                value += f" · {_pct(sum(cpu_values) / len(cpu_values))} du processeur en moyenne quand il était premier"
            evidence.append({"label": "Application la plus gourmande", "value": value})
        findings.append(_finding(
            "cpu", "attention", "Le processeur est à fond",
            "Il n'a presque plus de temps disponible pour le jeu et les autres programmes.",
            evidence,
            ["Ferme les programmes dont tu n'as pas besoin.", "Baisse la distance d'affichage, la foule ou la physique dans le jeu."],
        ))

    # Windows promène un fil de calcul d'un cœur à l'autre : un cœur saturé se voit rarement à 95 %.
    # On le repère donc aussi par l'appli au premier plan qui consomme à elle seule ~1 cœur entier.
    one_core = 100 / max(1, psutil.cpu_count() or 1)

    def _main_thread_bound(row: dict[str, Any]) -> bool:
        if not (_number(row.get("cpu")) < CPU_LOW_PERCENT and _number(row.get("gpu")) < 80):
            return False
        if _number(row.get("core_max")) >= CPU_CORE_FULL_PERCENT:
            return True
        app_name = row.get("top_cpu_app")
        return (
            _number(row.get("core_max")) >= CPU_CORE_BUSY_PERCENT
            and app_name is not None and app_name == row.get("fg_app")
            and (_number(row.get("top_cpu")) or 0) >= ONE_CORE_SHARE * one_core
        )

    core_full, core_ratio = _sustained(
        rows,
        _main_thread_bound,
        lambda row: all(_number(row.get(field)) is not None for field in ("core_max", "cpu", "gpu")),
    )
    if core_full:
        findings.append(_finding(
            "cpu_core", "attention", "Un seul cœur du processeur est à fond",
            "Le jeu ou l'application dépend surtout d'un cœur. La carte graphique attend qu'il ait fini.",
            [_sustained_evidence(core_ratio, "un cœur entier occupé par l'appli au premier plan")],
            [
                "Ferme ce qui tourne en fond.",
                "Baisse la distance d'affichage, la foule ou la physique dans le jeu.",
            ],
        ))

    ram_full, ram_ratio = _sustained(
        rows, lambda row: _number(row.get("ram")) >= RAM_FULL_PERCENT,
        lambda row: _number(row.get("ram")) is not None,
    )
    swaps = _values(rows, "swap")
    swap_rising = len(swaps) >= 2 and swaps[-1] - swaps[0] >= SWAP_RISE_PERCENT
    ram_pressure, pressure_ratio = _sustained(
        rows,
        lambda row: _number(row.get("ram")) >= RAM_PRESSURE_PERCENT
        and _number(row.get("disk_busy")) >= DISK_PRESSURE_PERCENT,
        lambda row: _number(row.get("ram")) is not None and _number(row.get("disk_busy")) is not None,
    )
    if ram_full or (ram_pressure and swap_rising):
        evidence = [_sustained_evidence(
            ram_ratio if ram_full else pressure_ratio,
            f"{RAM_FULL_PERCENT} % de mémoire ou plus" if ram_full else f"{RAM_PRESSURE_PERCENT} % avec le disque occupé",
        )]
        ram_app = _mode(rows, "top_ram_app")
        weights = [
            _number(row.get("top_ram_gb")) for row in rows
            if _clean_app(row.get("top_ram_app")) == ram_app and _number(row.get("top_ram_gb")) is not None
        ]
        average_weight = sum(weights) / len(weights) if weights else None
        if ram_app:
            weight = f" · {_decimal(average_weight, 'Go')} en moyenne" if average_weight is not None else ""
            evidence.append({"label": "Application la plus lourde", "value": ram_app + weight})
        if swap_rising:
            evidence.append({"label": "Mémoire de secours", "value": f"elle a augmenté de {_pct(swaps[-1] - swaps[0])}"})
        advice = ["Ferme les applications dont tu ne te sers pas."]
        if ram_app and ram_app != app:
            weight = f" ({_decimal(average_weight, 'Go')})" if average_weight is not None else ""
            advice.insert(0, f"Ferme {ram_app}{weight} si tu ne t'en sers pas : c'est l'application la plus lourde.")
        findings.append(_finding(
            "ram", "grave", "La mémoire est pleine, Windows se sert du disque à la place",
            "Le disque est beaucoup plus lent que la mémoire. Ce remplacement provoque des pauses et des saccades.",
            evidence, advice,
        ))

    cpu_temps = _values(rows, "cpu_temp")
    clocks = _values(rows, "cpu_clock")
    cpu_hot = max(cpu_temps) if cpu_temps else None
    throttle = bool(clocks) and any(
        (_number(row.get("cpu_temp")) or -1) >= CPU_THROTTLE_C
        and (_number(row.get("cpu_clock")) or math.inf) < CPU_THROTTLE_RATIO * max(clocks)
        for row in rows
    )
    if cpu_hot is not None and (cpu_hot >= CPU_HOT_C or throttle):
        evidence = [{"label": "Température maximale", "value": _decimal(cpu_hot, "°C")}]
        if throttle:
            evidence.append({
                "label": "Vitesse du processeur",
                "value": f"elle est passée sous {round(CPU_THROTTLE_RATIO * 100)} % de son maximum : il ralentit pour se protéger",
            })
        _temperature_baseline_evidence(evidence, cpu_hot, baseline)
        findings.append(_finding(
            "chaleur_cpu", "grave", "Le processeur chauffe trop",
            "À cette température, il peut ralentir tout seul pour éviter de s'abîmer.",
            evidence,
            ["Vérifie que les ventilateurs tournent.", "Dépoussière le PC.", "Si le PC est ancien, fais vérifier la pâte thermique."],
        ))

    gpu_temps = _values(rows, "gpu_temp")
    hotspots = _values(rows, "gpu_hotspot")
    gpu_hot = max(gpu_temps) if gpu_temps else None
    hotspot = max(hotspots) if hotspots else None
    if (gpu_hot is not None and gpu_hot >= GPU_HOT_C) or (hotspot is not None and hotspot >= GPU_HOTSPOT_C):
        evidence = []
        if gpu_hot is not None:
            evidence.append({"label": "Carte graphique au plus haut", "value": _decimal(gpu_hot, "°C")})
        if hotspot is not None:
            evidence.append({"label": "Point le plus chaud", "value": _decimal(hotspot, "°C")})
        findings.append(_finding(
            "chaleur_gpu", "grave", "La carte graphique chauffe trop",
            "À cette température, elle peut ralentir pour se protéger.",
            evidence,
            ["Vérifie que les ventilateurs tournent.", "Dépoussière le PC.", "Si le PC est ancien, fais vérifier la pâte thermique.", "Limite les images par seconde dans le jeu."],
        ))

    disk_full, disk_ratio = _sustained(
        rows, lambda row: _number(row.get("disk_busy")) >= DISK_BUSY_PERCENT,
        lambda row: _number(row.get("disk_busy")) is not None,
    )
    if disk_full:
        disk_app = _mode(rows, "top_app") or _mode(rows, "top_cpu_app")
        evidence = [_sustained_evidence(disk_ratio, f"{DISK_BUSY_PERCENT} % ou plus")]
        if disk_app:
            evidence.append({"label": "Application visible", "value": disk_app})
        findings.append(_finding(
            "disque", "attention", "Le disque est débordé",
            "Il répond trop lentement aux demandes, ce qui peut bloquer le jeu quelques instants.",
            evidence,
            ["Laisse finir les copies, téléchargements ou mises à jour.", "Ferme l'application qui utilise le disque si tu n'en as pas besoin."],
        ))

    free_values = _values(rows, "c_free_gb")
    if free_values and min(free_values) < C_FREE_GB:
        free = min(free_values)
        findings.append(_finding(
            "disk_space", "attention", "Ton disque C est presque plein",
            "Windows a besoin de place pour sa mémoire de secours et pour les mises à jour.",
            [{"label": "Place libre sur C", "value": _decimal(free, "Go")}],
            ["Clique sur « Faire de la place » pour ouvrir les réglages de stockage de Windows."],
        ))

    gaming, _gaming_ratio = _sustained(
        rows, lambda row: _number(row.get("gpu")) >= GPU_GAME_PERCENT,
        lambda row: _number(row.get("gpu")) is not None,
    )
    if gaming:
        resources: dict[str, dict[str, float]] = defaultdict(lambda: {"cpu": 0.0, "ram": 0.0})
        for row in rows:
            foreground = _clean_app(row.get("fg_app")) or app
            cpu_name = _clean_app(row.get("top_cpu_app"))
            ram_name = _clean_app(row.get("top_ram_app"))
            if cpu_name and cpu_name != foreground:
                resources[cpu_name]["cpu"] += _number(row.get("top_cpu")) or 0.0
            if ram_name and ram_name != foreground:
                resources[ram_name]["ram"] += _number(row.get("top_ram_gb")) or 0.0
        ignored = {"windows", "explorer", "sakura optimizer"}
        candidates = [
            (name, values["cpu"] / len(rows), values["ram"] / len(rows))
            for name, values in resources.items()
            if name.casefold() not in ignored and name != app
        ]
        candidates.sort(key=lambda item: max(item[1] / BACKGROUND_CPU_PERCENT, item[2] / BACKGROUND_RAM_GB), reverse=True)
        if candidates and (candidates[0][1] >= BACKGROUND_CPU_PERCENT or candidates[0][2] >= BACKGROUND_RAM_GB):
            name, cpu_average, ram_average = candidates[0]
            evidence = []
            if cpu_average > 0:
                evidence.append({"label": "Processeur pris en moyenne", "value": _pct(cpu_average)})
            if ram_average > 0:
                evidence.append({"label": "Mémoire prise en moyenne", "value": _decimal(ram_average, "Go")})
            severity = "attention" if cpu_average >= 25 or ram_average >= 4 else "info"
            findings.append(_finding(
                "fond", severity, f"{name} tourne en fond et prend des ressources",
                "Cette application n'était pas au premier plan pendant le jeu, mais elle utilisait quand même le PC.",
                evidence,
                [f"Ferme {name} pendant le jeu si tu n'en as pas besoin."],
            ))

    findings.sort(
        key=lambda finding: (SEVERITY_ORDER[finding["severity"]], PRIORITY[finding["id"]]),
        reverse=True,
    )
    prefix = f"Pendant {app}, " if app else "Pendant la période analysée, "
    confidence = " Je n'ai que quelques secondes de souvenirs, l'analyse est moins sûre." if not enough_data else ""
    if findings:
        first = findings[0]
        bottleneck = BOTTLENECK.get(first["id"], first["id"])
        phrases = {
            "gpu": "c'est la carte graphique qui limite.",
            "vram": "la mémoire vidéo est pleine.",
            "cpu": "le processeur est à fond.",
            "cpu_core": "un cœur du processeur est à fond.",
            "ram": "la mémoire pleine force Windows à utiliser le disque.",
            "chaleur_cpu": "le processeur ralentit à cause de la chaleur.",
            "chaleur_gpu": "la carte graphique chauffe trop.",
            "disque": "le disque freine le PC.",
            "fond": first["title"].removesuffix(".") + ".",
        }
        mood = "warn" if first["severity"] in ("attention", "grave") else "busy"
        verdict = {
            "mood": mood,
            "title": prefix + phrases[bottleneck],
            "text": first["explanation"] + confidence,
        }
    else:
        bottleneck = "aucun"
        label = str(int(minutes)) if float(minutes).is_integer() else str(minutes).replace(".", ",")
        verdict = {
            "mood": "ok",
            "title": "Rien ne freine ton PC",
            "text": (
                f"Sur les {label} dernières minutes, rien n'était à sa limite. "
                "Si ça rame quand même, ça peut venir du jeu lui-même, d'Internet ou des pilotes."
                + confidence
            ),
        }
    return {
        "minutes": int(minutes) if float(minutes).is_integer() else float(minutes),
        "app": app,
        "bottleneck": bottleneck,
        "verdict": verdict,
        "findings": findings,
        "enough_data": enough_data,
    }


def run_diagnosis(
    minutes: int | float = 5,
    *,
    history: Any | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lit les souvenirs récents, prend la mesure actuelle et lance l'analyse."""
    from .history import History
    from .names import add_friendly_names
    from .sensors import Sampler

    duration = max(1.0, min(60.0, float(minutes)))
    source = history or History()
    try:
        samples = source.query(duration * 60, points=max(120, int(duration * 12) + 1))
    except TypeError:
        samples = source.query(duration * 60)
    current = status
    if current is None:
        current = Sampler().sample()
        add_friendly_names(current)
    baseline = source.baseline() if hasattr(source, "baseline") else None
    return diagnose(samples, current, baseline, minutes=duration)
