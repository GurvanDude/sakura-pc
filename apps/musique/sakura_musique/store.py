"""Stockage local du Client ID et des jetons Spotify."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from core import paths

_CLIENT_ID = re.compile(r"^[0-9a-fA-F]{32}$")


def validate_client_id(client_id: str) -> bool:
    """Spotify fournit un Client ID de 32 caractères hexadécimaux."""
    return bool(_CLIENT_ID.fullmatch((client_id or "").strip()))


def data_dir() -> Path:
    """Choisit un dossier personnel, jamais le dossier de code de l'application."""
    if os.environ.get("SAKURA_HOME"):
        return Path(os.environ["SAKURA_HOME"]) / "musique"
    candidate = Path(paths.app("musique"))
    try:
        candidate.relative_to(paths.REPO)
    except ValueError:
        return candidate
    return Path(paths.USER) / "musique"


def token_path() -> Path:
    return data_dir() / "token.json"


def load() -> dict[str, Any]:
    try:
        value = json.loads(token_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write(value: dict[str, Any]) -> None:
    target = token_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(target)


def save_client_id(client_id: str) -> str:
    clean = (client_id or "").strip()
    if not validate_client_id(clean):
        raise ValueError("Le Client ID doit contenir exactement 32 lettres ou chiffres hexadécimaux.")
    value = load()
    if value.get("client_id") != clean:
        value = {"client_id": clean}
    else:
        value["client_id"] = clean
    _write(value)
    return clean


def save_tokens(tokens: dict[str, Any]) -> None:
    value = load()
    value["tokens"] = dict(tokens)
    _write(value)


def logout() -> None:
    """Efface les jetons et le Client ID en supprimant leur unique fichier."""
    try:
        token_path().unlink()
    except FileNotFoundError:
        pass

