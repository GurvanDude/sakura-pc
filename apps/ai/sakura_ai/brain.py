"""Dialogue en continu avec le modèle local Ollama."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from typing import Any

from core import paths

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:14b"
MAX_MESSAGES = 30
SYSTEM_PROMPT = (
    "Tu t'appelles Sakura. Tu es l'assistante du PC de Gurvan. "
    "Tu réponds en français, avec un ton simple et chaleureux. "
    "Tes réponses sont courtes, sauf si Gurvan demande des détails. "
    "Tu peux agir sur son PC avec les outils fournis. Si Gurvan demande une action, "
    "appelle immédiatement l'outil adapté : n'annonce jamais « je vais chercher » ou une action sans l'appeler. "
    "N'invente jamais le résultat d'un outil. Après son exécution, dis simplement ce qui s'est passé. "
    "Si plusieurs noms correspondent, demande à Gurvan lequel il veut."
)
MAX_TOOL_ROUNDS = 4


class OllamaError(RuntimeError):
    """Erreur présentable directement dans l'interface."""


def model_name() -> str:
    """Lit le modèle choisi, ou utilise le modèle conseillé."""
    try:
        data = json.loads(paths.CONFIG.read_text(encoding="utf-8"))
        model = data.get("ai", {}).get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return DEFAULT_MODEL


def _request(request: urllib.request.Request | str, timeout: float = 5.0):
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OllamaError("Impossible de joindre Ollama. Vérifie qu'il est bien lancé.") from exc


def is_ready() -> tuple[bool, str]:
    """Vérifie qu'Ollama répond et que le modèle est disponible."""
    try:
        with _request(f"{OLLAMA_URL}/api/tags") as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OllamaError, urllib.error.URLError, TimeoutError, OSError):
        return False, "Ollama n'est pas lancé. Ouvre l'appli Ollama puis réessaie."
    except (ValueError, UnicodeError, TypeError):
        return False, "Ollama a répondu d'une façon inattendue. Réessaie dans un instant."

    if not isinstance(payload, dict):
        return False, "Ollama a répondu d'une façon inattendue. Réessaie dans un instant."
    wanted = model_name()
    models = payload.get("models", [])
    if not isinstance(models, list):
        return False, "Ollama a répondu d'une façon inattendue. Réessaie dans un instant."
    names = {
        item.get("name")
        for item in models
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if wanted not in names:
        return False, f"Le modèle {wanted} n'est pas téléchargé."
    return True, "Sakura est prête."


def _trim_messages(messages: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Garde les derniers messages valides avec le prompt en tête."""
    cleaned = [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if isinstance(message, dict)
        and message.get("role") in {"user", "assistant"}
        and isinstance(message.get("content"), str)
    ]
    return [{"role": "system", "content": SYSTEM_PROMPT}, *cleaned[-MAX_MESSAGES:]]


def _partial_suffix(text: str, marker: str) -> int:
    """Trouve une balise potentiellement coupée en fin de morceau."""
    limit = min(len(text), len(marker) - 1)
    for size in range(limit, 0, -1):
        if text.endswith(marker[:size]):
            return size
    return 0


class ThinkFilter:
    """Retire les blocs de réflexion, même entre plusieurs morceaux."""

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self) -> None:
        self.buffer = ""
        self.thinking = False

    def feed(self, text: str) -> str:
        self.buffer += text
        output: list[str] = []
        while self.buffer:
            marker = self.CLOSE if self.thinking else self.OPEN
            position = self.buffer.find(marker)
            if position >= 0:
                if not self.thinking:
                    output.append(self.buffer[:position])
                self.buffer = self.buffer[position + len(marker):]
                self.thinking = not self.thinking
                continue

            kept = _partial_suffix(self.buffer, marker)
            ready = self.buffer[:-kept] if kept else self.buffer
            if not self.thinking:
                output.append(ready)
            self.buffer = self.buffer[-kept:] if kept else ""
            break
        return "".join(output)

    def finish(self) -> str:
        """Rend le texte restant seulement s'il est visible."""
        result = self.buffer if not self.thinking else ""
        self.buffer = ""
        return result


def chat_stream(
    messages: Iterable[dict[str, Any]],
    on_chunk: Callable[[str], None],
    stop_event: threading.Event,
    tools: Any = None,
    confirm: Callable[[Any, dict[str, Any]], bool] | None = None,
    on_action: Callable[[str], None] | None = None,
) -> str:
    """Diffuse la réponse et exécute jusqu'à quatre tours d'outils."""
    conversation: list[dict[str, Any]] = list(_trim_messages(messages))
    complete: list[str] = []

    for tool_round in range(MAX_TOOL_ROUNDS):
        if stop_event.is_set():
            break
        payload: dict[str, Any] = {
            "model": model_name(),
            "messages": conversation,
            "stream": True,
            "think": False,
        }
        if tools is not None:
            payload["tools"] = tools.schemas()
        request = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        filtered = ThinkFilter()
        round_content: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        try:
            with _request(request, timeout=120.0) as response:
                for raw_line in response:
                    if stop_event.is_set():
                        break
                    if not raw_line.strip():
                        continue
                    try:
                        item = json.loads(raw_line.decode("utf-8"))
                    except (ValueError, UnicodeError) as exc:
                        raise OllamaError("La réponse d'Ollama est illisible. Réessaie.") from exc
                    if not isinstance(item, dict):
                        raise OllamaError("La réponse d'Ollama est illisible. Réessaie.")
                    if item.get("error"):
                        raise OllamaError("Ollama n'a pas pu préparer la réponse. Réessaie.")
                    message = item.get("message")
                    content = message.get("content", "") if isinstance(message, dict) else ""
                    if isinstance(content, str) and content:
                        visible = filtered.feed(content)
                        if visible:
                            round_content.append(visible)
                            complete.append(visible)
                            on_chunk(visible)
                    calls = message.get("tool_calls") if isinstance(message, dict) else None
                    if isinstance(calls, list):
                        tool_calls.extend(call for call in calls if isinstance(call, dict))
                    if item.get("done"):
                        break
        except OllamaError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OllamaError("La connexion avec Ollama a été interrompue. Réessaie.") from exc

        tail = filtered.finish()
        if tail:
            round_content.append(tail)
            complete.append(tail)
            on_chunk(tail)
        if stop_event.is_set() or not tool_calls:
            break
        conversation.append({"role": "assistant", "content": "".join(round_content), "tool_calls": tool_calls})
        for call in tool_calls:
            if stop_event.is_set():
                break
            function = call.get("function", {})
            name = function.get("name", "") if isinstance(function, dict) else ""
            args = _tool_arguments(function.get("arguments", {}) if isinstance(function, dict) else {})
            definition = tools.get(name) if hasattr(tools, "get") else None
            risky = bool(getattr(definition, "risky", False))
            if risky and (confirm is None or not confirm(definition, args)):
                result = {"ok": False, "message": "Action annulée : Gurvan a répondu non. Dis-lui simplement que tu ne l'as pas fait."}
            else:
                result = tools.run(name, args)
                if on_action is not None and result.get("ok"):
                    try:
                        # le nom exact trouvé (ex. « Minecraft (moddé) ») plutôt que celui tapé
                        on_action(tools.describe(name, {**args, **({"name": result["name"]} if "name" in result else {})}))
                    except (AttributeError, TypeError):
                        on_action(name)
            conversation.append({
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result, ensure_ascii=False),
            })
        if tool_round == MAX_TOOL_ROUNDS - 1 and not stop_event.is_set():
            warning = "J'ai atteint la limite de quatre tours d'outils. Reformule ta demande pour continuer."
            complete.append(warning)
            on_chunk(warning)

    return "".join(complete)


def _tool_arguments(value: Any) -> dict[str, Any]:
    """Accepte les arguments Ollama sous forme d'objet ou de JSON."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except ValueError:
            return {}
    return {}

