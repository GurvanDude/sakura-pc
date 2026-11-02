# Sakura Optimizer

Sakura Optimizer explique simplement ce que fait le PC et propose des gestes concrets quand quelque chose mérite
de l'attention.

## Lancement

Double-cliquer sur le raccourci **Sakura Optimizer** du Bureau, ou lancer sans terminal :

```powershell
pythonw optimizer.py
```

Le raccourci peut être créé une fois avec `python tools/make_shortcut.py`.

## Outil technique

Le moniteur terminal reste disponible pour le diagnostic technique :

```powershell
python optimizer.py monitor
python optimizer.py monitor --once
python optimizer.py monitor --json
```

## Tests

Depuis la racine du dépôt :

```powershell
python -m pytest apps/optimizer/tests -q
```
