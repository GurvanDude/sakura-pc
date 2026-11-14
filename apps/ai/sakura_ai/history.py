"""Historique local des conversations de Sakura AI."""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths

_ID = re.compile(r"^[0-9a-f]{32}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def short_title(text: str, limit: int = 40) -> str:
    """Produit un titre court sans couper un mot quand c'est possible."""
    cleaned = " ".join(str(text).split()).strip()
    if not cleaned:
        return "Nouvelle discussion"
    if len(cleaned) <= limit:
        return cleaned
    shortened = cleaned[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,.;:!?—–-")
    if not shortened or len(shortened) > limit:
        shortened = cleaned[:limit].rstrip()
    return shortened


def _messages(value: Any) -> list[dict[str, Any]]:
    """Valide les messages sans perdre leurs champs annexes (actions, etc.)."""
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if (
            isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
        ):
            result.append(deepcopy(item))
    return result


class ChatStore:
    """Stocke une conversation par fichier JSON, avec des accès sûrs et atomiques."""

    def __init__(self, folder: Path | None = None, logger: logging.Logger | None = None) -> None:
        self._folder = Path(folder) if folder is not None else paths.USER / "ai" / "chats"
        self._logger = logger or logging.getLogger("sakura.ai.history")
        self._pending: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._migrate()

    @staticmethod
    def _validate(chat_id: str) -> str:
        if not isinstance(chat_id, str) or not _ID.fullmatch(chat_id):
            raise ValueError("Identifiant de conversation invalide")
        return chat_id

    def _path(self, chat_id: str) -> Path:
        return self._folder / f"{self._validate(chat_id)}.json"

    def _read(self, file: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or not _ID.fullmatch(str(data.get("id", "")))
                or data.get("id") != file.stem
            ):
                raise ValueError("structure invalide")
            messages = _messages(data.get("messages"))
            if data.get("messages") is not None and not isinstance(data.get("messages"), list):
                raise ValueError("messages invalides")
            return {
                **data,
                "id": data["id"],
                "title": short_title(data.get("title", "Nouvelle discussion")),
                "created": str(data.get("created") or _now()),
                "updated": str(data.get("updated") or data.get("created") or _now()),
                "messages": messages,
            }
        except (OSError, ValueError, TypeError, UnicodeError):
            self._logger.warning("Conversation illisible ignorée : %s", file, exc_info=True)
            return None

    def _write(self, chat: dict[str, Any]) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        file = self._path(chat["id"])
        temporary = file.with_name(f".{file.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(chat, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(file)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _migrate(self) -> None:
        legacy = self._folder.parent / "chat.json"
        migrated = legacy.with_name("chat.migrated.json")
        try:
            if migrated.exists():
                return
            if not legacy.exists() or not legacy.read_text(encoding="utf-8").strip():
                return
            messages = _messages(json.loads(legacy.read_text(encoding="utf-8")))
            if not messages:
                return
            first = next((m["content"] for m in messages if m["role"] == "user"), "Nouvelle discussion")
            moment = _now()
            chat = {
                "id": uuid.uuid4().hex,
                "title": short_title(first),
                "created": moment,
                "updated": moment,
                "messages": messages,
                "_title_source": "provisional",
            }
            self._write(chat)
            if not migrated.exists():
                legacy.replace(migrated)
            self._logger.info("Ancienne conversation migrée : %s", chat["id"])
        except (OSError, ValueError, TypeError, UnicodeError):
            self._logger.warning("Ancienne conversation impossible à migrer : %s", legacy, exc_info=True)

    def list(self) -> list[dict[str, str]]:
        chats: list[dict[str, str]] = []
        try:
            files = list(self._folder.glob("*.json"))
        except OSError:
            return chats
        for file in files:
            if not _ID.fullmatch(file.stem):
                continue
            chat = self._read(file)
            if chat is not None:
                chats.append({"id": chat["id"], "title": chat["title"], "updated": chat["updated"]})
        return sorted(chats, key=lambda item: item["updated"], reverse=True)

    def create(self) -> dict[str, Any]:
        moment = _now()
        chat = {
            "id": uuid.uuid4().hex,
            "title": "Nouvelle discussion",
            "created": moment,
            "updated": moment,
            "messages": [],
            "_title_source": "provisional",
        }
        self._pending[chat["id"]] = chat
        return deepcopy(chat)

    def load(self, chat_id: str) -> dict[str, Any]:
        chat_id = self._validate(chat_id)
        if chat_id in self._pending:
            return deepcopy(self._pending[chat_id])
        chat = self._read(self._path(chat_id))
        if chat is None:
            raise FileNotFoundError("Conversation introuvable")
        return chat

    def append(self, chat_id: str, role: str, content: str, **extra: Any) -> dict[str, Any]:
        if role not in {"user", "assistant"}:
            raise ValueError("Rôle de message inconnu")
        if not isinstance(content, str):
            raise TypeError("Le contenu du message doit être du texte")
        with self._lock:
            chat = self.load(chat_id)
            if not chat["messages"] and role == "user":
                chat["title"] = short_title(content)
                chat["_title_source"] = "provisional"
            chat["messages"].append({"role": role, "content": content, **deepcopy(extra)})
            chat["updated"] = _now()
            self._write(chat)
            self._pending.pop(chat_id, None)
            return deepcopy(chat)

    def rename(self, chat_id: str, title: str, *, automatic: bool = False) -> dict[str, Any]:
        with self._lock:
            chat = self.load(chat_id)
            if automatic and chat.get("_title_source") == "user":
                return chat
            chat["title"] = short_title(title)
            chat["_title_source"] = "automatic" if automatic else "user"
            chat["updated"] = _now()
            if chat["messages"]:
                self._write(chat)
            else:
                self._pending[chat_id] = chat
            return deepcopy(chat)

    def delete(self, chat_id: str) -> None:
        chat_id = self._validate(chat_id)
        self._pending.pop(chat_id, None)
        file = self._path(chat_id)
        if not file.exists():
            return
        trash = self._folder / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        destination = trash / file.name
        if destination.exists():
            destination = trash / f"{chat_id}-{uuid.uuid4().hex}.json"
        file.replace(destination)

    def clear(self, chat_id: str) -> dict[str, Any]:
        chat = self.load(chat_id)
        chat["messages"] = []
        chat["updated"] = _now()
        if self._path(chat_id).exists():
            self._write(chat)
        else:
            self._pending[chat_id] = chat
        return deepcopy(chat)


class ChatHistory:
    """Façade de compatibilité pour l'ancien historique à conversation unique."""

    def __init__(self, file: Path | None = None) -> None:
        folder = file.parent / "chats" if file is not None else None
        self._store = ChatStore(folder=folder)
        listed = self._store.list()
        self._id = listed[0]["id"] if listed else self._store.create()["id"]
        self.messages = self._store.load(self._id)["messages"]

    def load(self) -> list[dict[str, Any]]:
        self.messages = self._store.load(self._id)["messages"]
        return self.messages

    def save(self) -> None:
        chat = self._store.load(self._id)
        chat["messages"] = deepcopy(self.messages)
        if self.messages:
            self._store._write(chat)

    def append(self, role: str, content: str, **extra: Any) -> None:
        self.messages = self._store.append(self._id, role, content, **extra)["messages"]

    def clear(self) -> None:
        self.messages = self._store.clear(self._id)["messages"]
