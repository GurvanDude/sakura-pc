"""Enregistrement local de la conversation en cours."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core import paths


def _valid_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    return [
        {"role": item["role"], "content": item["content"]}
        for item in value
        if isinstance(item, dict)
        and item.get("role") in {"user", "assistant"}
        and isinstance(item.get("content"), str)
    ]


class ChatHistory:
    """Conversation persistée dans le dossier personnel Sakura PC."""

    def __init__(self, file: Path | None = None) -> None:
        self.file = file or paths.USER / "ai" / "chat.json"
        self.messages = self.load()

    def load(self) -> list[dict[str, str]]:
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
            return _valid_messages(data)
        except (OSError, ValueError, TypeError):
            return []

    def save(self) -> None:
        """Écrit d'abord un fichier temporaire, puis le remplace."""
        self.file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.file.with_name(f".{self.file.name}.tmp")
        temporary.write_text(
            json.dumps(self.messages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.file)

    def append(self, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("Rôle de message inconnu")
        self.messages.append({"role": role, "content": content})
        self.save()

    def clear(self) -> None:
        self.messages = []
        self.save()

