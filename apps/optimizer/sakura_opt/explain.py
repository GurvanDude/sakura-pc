"""Traduit les mesures techniques en explications courantes et testables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .names import group_apps


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _fr(value: float, digits: int = 1) -> str:
    text = f"{value:.{digits}f}" if digits else f"{value:.0f}"
    return text.replace(".", ",")


def _measure(value: float, digits: int = 1) -> str:
    """Écrit un nombre français sans décimale artificielle."""
    if value.is_integer():
        digits = 0
    return _fr(value, digits)


def _figure(label: str, value: str, hint: str = "") -> dict[str, str]:
    return {"label": label, "value": value, "hint": hint}


def _section(status: dict[str, Any], name: str) -> dict[str, Any] | None:
    value = status.get(name)
    return value if isinstance(value, dict) else None


def _known_name(_pid: int, name: str) -> str:
    """Repli sans accès système : les vrais noms sont préparés par le thread de mesure."""
    return name[:-4] if name.lower().endswith(".exe") else name


def _temp_sentence(value: Any) -> str:
    temp = _number(value)
    if temp is None:
        return ""
    comment = "il chauffe beaucoup" if temp > 85 else "c'est normal"
    return f" Il est à {_fr(temp, 0)} °C, {comment}."


def _level(percent: float | None, low: float, high: float) -> str:
    if percent is None:
        return "inconnu"
    if percent < low:
        return "calme"
    if percent <= high:
        return "occupe"
    return "fond"


def _card(
    ident: str, icon: str, title: str, role: str, percent: float | None,
    low: float, high: float, words: tuple[str, str, str], sentence: str,
    detail: str, figures: list[dict[str, str]],
) -> dict[str, Any]:
    level = _level(percent, low, high)
    return {
        "id": ident, "icon": icon, "title": title, "role": role,
        "level": level,
        "word": "inconnu" if level == "inconnu" else words[("calme", "occupe", "fond").index(level)],
        "percent": round(percent, 1) if percent is not None else 0,
        "sentence": "Impossible de le lire pour l'instant." if level == "inconnu" else sentence,
        "detail": detail if level != "inconnu" else "Aucune mesure disponible.",
        "figures": figures,
    }


def _temperature_hint(value: float, warm: float, hot: float) -> str:
    if value < warm:
        return "normal"
    if value <= hot:
        return "chaud, mais ça va"
    return "très chaud"


def _history_value(value: Any, unit: str) -> str:
    number = _number(value)
    return f"{_measure(number)} {unit}" if number is not None else "—"


def _history_time(value: Any) -> str:
    timestamp = _number(value)
    if timestamp is None:
        return "—"
    try:
        return datetime.fromtimestamp(timestamp).strftime("%H:%M")
    except (OSError, OverflowError, ValueError):
        return "—"


def _history_usage_hint(value: Any, low: float, high: float) -> str:
    number = _number(value)
    if number is None:
        return "mesure indisponible"
    if number < low:
        return "tranquille"
    if number <= high:
        return "bien occupé"
    return "à fond"


def history_view(
    series: list[dict[str, Any]] | None,
    summary: dict[str, Any] | None,
    period_label: str,
) -> dict[str, Any]:
    """Transforme les souvenirs techniques en bilan simple et chiffré."""
    series = series if isinstance(series, list) else []
    summary = summary if isinstance(summary, dict) else {}
    if _number(summary.get("duration_s")) is None or (_number(summary.get("duration_s")) or 0) < 120:
        return {
            "sentence": "Je n'ai pas encore assez de souvenirs, reviens dans quelques minutes.",
            "facts": [],
        }

    cpu_avg = _number(summary.get("avg_cpu"))
    cpu_temp = _number(summary.get("max_cpu_temp"))
    app = str(summary.get("top_app") or "tes programmes")
    pieces = [f"Sur {period_label}, ton PC a surtout servi à {app}."]
    if cpu_avg is not None:
        pieces.append(f"Le processeur a tourné en moyenne à {_measure(cpu_avg)} %.")
    if cpu_temp is not None:
        pieces.append(
            f"Il a chauffé au plus à {_measure(cpu_temp)} °C vers "
            f"{_history_time(summary.get('max_cpu_temp_t'))} "
            f"({_temperature_hint(cpu_temp, 70, 85)})."
        )

    facts = [
        _figure("Processeur moyen", _history_value(summary.get("avg_cpu"), "%"), _history_usage_hint(summary.get("avg_cpu"), 35, 75)),
        _figure("Processeur au maximum", _history_value(summary.get("max_cpu"), "%"), f"{_history_usage_hint(summary.get('max_cpu'), 35, 75)} · vers {_history_time(summary.get('max_cpu_t'))}"),
        _figure("Carte graphique au maximum", _history_value(summary.get("max_gpu"), "%"), f"{_history_usage_hint(summary.get('max_gpu'), 35, 75)} · vers {_history_time(summary.get('max_gpu_t'))}"),
    ]
    for label, field in (("Température processeur", "cpu_temp"), ("Température carte graphique", "gpu_temp")):
        value = _number(summary.get(f"max_{field}"))
        hint = "mesure indisponible"
        if value is not None:
            hint = f"{_temperature_hint(value, 70, 85)} · vers {_history_time(summary.get(f'max_{field}_t'))}"
        facts.append(_figure(label, _history_value(value, "°C"), hint))
    facts.append(_figure(
        "Mémoire au maximum", _history_value(summary.get("max_ram"), "%"),
        f"{_history_usage_hint(summary.get('max_ram'), 60, 85)} · vers {_history_time(summary.get('max_ram_t'))}",
    ))
    return {"sentence": " ".join(pieces), "facts": facts}


def _disk_hint(percent: float) -> str:
    if percent > 90:
        return "presque plein"
    if percent >= 75:
        return "bien rempli"
    return "largement de la place"


def explain(status: dict[str, Any] | None) -> dict[str, Any]:
    """Construit toute la vue sans effectuer la moindre lecture matérielle."""
    status = status if isinstance(status, dict) else {}
    cpu, ram, gpu, disk, temps = (_section(status, key) for key in ("cpu", "ram", "gpu", "disk", "temps"))
    cpu_p = _number(cpu and cpu.get("percent"))
    ram_p = _number(ram and ram.get("percent"))
    gpu_p = _number(gpu and gpu.get("percent"))
    apps = group_apps(status, name_reader=_known_name)

    partitions = disk.get("partitions") if disk else None
    valid_parts = []
    if isinstance(partitions, list):
        for part in partitions:
            if isinstance(part, dict) and _number(part.get("percent")) is not None:
                valid_parts.append(part)
    fullest = max(valid_parts, key=lambda part: _number(part.get("percent")) or 0) if valid_parts else None
    disk_p = _number(fullest and fullest.get("percent"))
    disk_free = _number(fullest and fullest.get("free_gb"))
    disk_name = str(fullest.get("mount", "le disque")).rstrip("\\/").rstrip(":") if fullest else "le disque"

    cpu_figures = [_figure("Utilisation", f"{_measure(cpu_p)} %" if cpu_p is not None else "—")]
    cpu_temp = _number(temps and temps.get("cpu"))
    if cpu_temp is not None:
        cpu_figures.append(_figure(
            "Température", f"{_measure(cpu_temp)} °C", _temperature_hint(cpu_temp, 70, 85)
        ))
    cpu_clock = _number(temps and temps.get("cpu_clock_mhz"))
    if cpu_clock is not None and cpu_clock > 0:
        cpu_figures.append(_figure(
            "Vitesse", f"{_measure(cpu_clock / 1000)} GHz", "plus c'est haut, plus il va vite"
        ))
    per_core = cpu.get("per_core") if cpu else None
    valid_cores = [_number(value) for value in per_core] if isinstance(per_core, list) else []
    valid_cores = [value for value in valid_cores if value is not None]
    if valid_cores:
        core_count = len(valid_cores)
        active_count = sum(value > 50 for value in valid_cores)
        cpu_figures.extend([
            _figure("Cœurs", str(core_count), f"il peut faire {core_count} choses en même temps"),
            _figure("Le plus actif", f"{active_count} cœurs sur {core_count} au-dessus de 50 %"),
        ])

    ram_used = _number(ram and ram.get("used_gb"))
    ram_total = _number(ram and ram.get("total_gb"))
    ram_free = _number(ram and ram.get("available_gb"))
    ram_value = "—"
    if ram_used is not None and ram_total is not None and ram_p is not None:
        ram_value = f"{_measure(ram_used)} Go sur {_measure(ram_total)} Go ({_measure(ram_p)} %)"
    ram_figures = [_figure("Utilisée", ram_value)]
    if ram_free is not None:
        free_hint = "ça commence à être juste" if ram_p is not None and ram_p >= 85 else "de quoi ouvrir encore pas mal de programmes"
        ram_figures.append(_figure("Libre", f"{_measure(ram_free)} Go", free_hint))
    swap = _number(ram and ram.get("swap_percent"))
    if swap is not None:
        ram_figures.append(_figure(
            "Mémoire de secours", f"{_measure(swap)} %",
            "Windows s'en sert quand la vraie mémoire est pleine ; bas = bien",
        ))

    gpu_figures = [_figure("Utilisation", f"{_measure(gpu_p)} %" if gpu_p is not None else "—")]
    vram_used = _number(gpu and gpu.get("vram_used_gb"))
    vram_total = _number(gpu and gpu.get("vram_total_gb"))
    if vram_used is not None and vram_total is not None:
        remaining = max(0.0, vram_total - vram_used)
        gpu_figures.append(_figure(
            "Mémoire vidéo", f"{_measure(vram_used)} Go sur {_measure(vram_total)} Go",
            f"textures et images du jeu ; il en reste {_measure(remaining)} Go",
        ))
    gpu_temp = _number(temps and temps.get("gpu"))
    if gpu_temp is not None:
        gpu_figures.append(_figure(
            "Température", f"{_measure(gpu_temp)} °C", _temperature_hint(gpu_temp, 70, 85)
        ))
    hotspot = _number(temps and temps.get("gpu_hotspot"))
    if hotspot is not None:
        gpu_figures.append(_figure(
            "Point le plus chaud", f"{_measure(hotspot)} °C", _temperature_hint(hotspot, 90, 105)
        ))

    disk_figures: list[dict[str, str]] = []
    for part in valid_parts:
        part_p = _number(part.get("percent"))
        part_free = _number(part.get("free_gb"))
        if part_p is None:
            continue
        name = str(part.get("mount") or "").rstrip("\\/").rstrip(":") or "?"
        free_text = f"{_measure(part_free)} Go libres" if part_free is not None else "espace libre inconnu"
        disk_figures.append(_figure(
            f"Disque {name}", f"{_measure(part_p)} % plein · {free_text}", _disk_hint(part_p)
        ))
    if not disk_figures:
        disk_figures.append(_figure("Stockage", "—"))
    read_speed = _number(disk and disk.get("read_mb_s"))
    write_speed = _number(disk and disk.get("write_mb_s"))
    per_disk = disk.get("per_disk") if disk else None
    if isinstance(per_disk, dict):
        rows = [row for row in per_disk.values() if isinstance(row, dict)]
        if read_speed is None:
            reads = [_number(row.get("read_mb_s")) for row in rows]
            known_reads = [value for value in reads if value is not None]
            read_speed = sum(known_reads) if known_reads else None
        if write_speed is None:
            writes = [_number(row.get("write_mb_s")) for row in rows]
            known_writes = [value for value in writes if value is not None]
            write_speed = sum(known_writes) if known_writes else None
    if read_speed is not None or write_speed is not None:
        read_text = _measure(read_speed or 0)
        write_text = _measure(write_speed or 0)
        activity = (read_speed or 0) + (write_speed or 0)
        disk_figures.append(_figure(
            "Activité", f"lecture {read_text} Mo/s · écriture {write_text} Mo/s",
            "le disque travaille beaucoup" if activity > 50 else "le disque travaille peu",
        ))

    cpu_sentence = "Le processeur a encore beaucoup de marge." if (cpu_p or 0) < 35 else "Il s'occupe des programmes ouverts."
    if cpu_p is not None and cpu_p > 75:
        cpu_sentence = "Il travaille très fort en ce moment."
    cpu_sentence += _temp_sentence(temps and temps.get("cpu"))
    ram_sentence = f"Il reste {_fr(ram_free)} Go pour ouvrir d'autres programmes." if ram_free is not None else "Les programmes ouverts ont encore de la place."
    gpu_sentence = "Il a peu de travail en ce moment." if (gpu_p or 0) < 35 else "Il dessine beaucoup d'images en ce moment."
    if gpu_p is not None and gpu_p > 75:
        gpu_sentence = "Un jeu ou un programme lui demande beaucoup de travail."
    gpu_sentence += _temp_sentence(temps and temps.get("gpu"))
    if disk_free is None:
        disk_sentence = "Tes fichiers ont encore de la place."
    elif disk_p is not None and disk_p > 90:
        disk_sentence = f"Il ne reste que {_fr(disk_free)} Go de libre."
    elif disk_p is not None and disk_p >= 75:
        disk_sentence = f"Il reste {_fr(disk_free)} Go de libre : ça commence à se remplir."
    else:
        disk_sentence = f"Il en reste {_fr(disk_free)} Go de libre, largement assez."

    cards = [
        _card("processeur", "🧠", "Processeur", "le cerveau du PC", cpu_p, 35, 75,
              ("tranquille", "bien occupé", "à fond"), cpu_sentence,
              f"Utilisation : {_fr(cpu_p)} %" if cpu_p is not None else "", cpu_figures),
        _card("memoire", "🗂️", "Mémoire", "la place pour les programmes ouverts", ram_p, 60, 85,
              ("tranquille", "bien occupée", "à fond"), ram_sentence,
              (f"Utilisation : {_fr(ram_p)} % · {_fr(_number(ram and ram.get('used_gb')) or 0)} / "
               f"{_fr(_number(ram and ram.get('total_gb')) or 0)} Go") if ram_p is not None else "", ram_figures),
        _card("graphique", "🎨", "Graphique", "dessine les images, surtout en jeu", gpu_p, 35, 75,
              ("tranquille", "bien occupé", "à fond"), gpu_sentence,
              f"Utilisation : {_fr(gpu_p)} %" if gpu_p is not None else "", gpu_figures),
        _card("stockage", "💾", "Stockage", "là où sont rangés tes fichiers", disk_p, 75, 90,
              ("tranquille", "se remplit", "presque plein"), disk_sentence,
              f"Disque {disk_name} : {_fr(disk_p)} % utilisé" if disk_p is not None else "", disk_figures),
    ]

    tips: list[dict[str, str]] = []
    problems: list[tuple[int, str, str]] = []
    temp_reason = str(temps.get("reason") or "") if temps else ""
    if "lecteur de températures" in temp_reason.lower():
        tips.append({
            "icon": "🌡️",
            "text": (
                "Pour voir la température du processeur, installe le lecteur de températures "
                "(une seule fois, voir le README)."
            ),
        })
    if cpu_temp is not None and cpu_temp > 85:
        problems.append((5, "Ton processeur chauffe beaucoup", (
            "Vérifie que les ventilateurs tournent et dépoussière le PC."
        )))
    if hotspot is not None and hotspot > 105:
        problems.append((4, "Ta carte graphique chauffe beaucoup", (
            "Vérifie que les ventilateurs tournent et dépoussière le PC."
        )))
    if fullest and disk_p is not None and disk_p > 90:
        title = f"Ton disque {disk_name} est presque plein"
        text = f"Il ne reste que {_fr(disk_free or 0)} Go. Quand il est plein, Windows ralentit."
        problems.append((3, title, text))
        alternatives = [p for p in valid_parts if p is not fullest and (_number(p.get("free_gb")) or 0) > 20]
        extra = ""
        if alternatives:
            best = max(alternatives, key=lambda p: _number(p.get("free_gb")) or 0)
            other = str(best.get("mount", "")).rstrip("\\/").rstrip(":")
            extra = f", ou installe les prochains sur {other} ({_fr(_number(best.get('free_gb')) or 0, 0)} Go libres)"
        tips.append({"icon": "💾", "text": f"Libère de la place sur {disk_name} : vide la corbeille, désinstalle les jeux que tu n'utilises plus{extra}."})
    if ram_p is not None and ram_p > 90:
        problems.append((2, "La mémoire est presque pleine", "Les programmes ouverts n'ont presque plus de place."))
    if ram_p is not None and ram_p > 85:
        heavy = next((a["name"] for a in sorted(apps, key=lambda a: a["ram_gb"], reverse=True) if a["name"] != "Windows"), None)
        example = f", par exemple {heavy}" if heavy else ""
        tips.append({"icon": "🗂️", "text": f"Ferme les programmes que tu n'utilises pas{example}."})

    if problems:
        problems.sort(reverse=True)
        _, title, text = problems[0]
        for _, other_title, other_text in problems[1:]:
            tips.append({"icon": "⚠️", "text": f"{other_title}. {other_text}"})
        verdict = {"mood": "warn", "emoji": "⚠️", "title": title, "text": text}
    elif (cpu_p is not None and cpu_p > 70) or (gpu_p is not None and gpu_p > 70):
        app = next((a["name"] for a in apps if a["name"] != "Windows"), "un programme")
        if gpu_p is not None and gpu_p > 70:
            title = f"Ton PC travaille dur pour un jeu ou {app}."
            text = "C'est normal pendant un jeu ou un gros programme."
        else:
            title = f"Ton PC travaille dur pour {app}."
            text = "C'est normal pendant un jeu ou un gros programme."
        verdict = {"mood": "busy", "emoji": "✨", "title": title, "text": text}
    else:
        verdict = {"mood": "ok", "emoji": "🌸", "title": "Tout va bien", "text": "Ton PC est tranquille."}

    return {"verdict": verdict, "cards": cards, "apps": apps, "tips": tips}
