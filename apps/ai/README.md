# Sakura AI

Assistante locale de Sakura PC : un modèle de langage qui tourne sur le PC (Ollama), dans une fenêtre Sakura.
Feuille de route : `docs/roadmaps/ai.md`.

## Prérequis

- [Ollama](https://ollama.com) installé et lancé (il écoute sur `http://127.0.0.1:11434`).
- Un modèle téléchargé, par exemple `ollama pull qwen3:14b` (16 Go de VRAM sur la RX 6800).
- Python 3.13 avec `pywebview`.

## Organisation (prévue)

```
apps/ai/
  ai.py        point d'entrée : ouvre la fenêtre Sakura AI
  brain.py     dialogue avec Ollama (envoi des messages, réponse en continu)
  ui/          interface du chat (HTML/CSS/JS)
```

Les réglages perso (modèle choisi, historique) vivent dans `%APPDATA%\SakuraPC` via `core.paths`, jamais dans le dépôt.
