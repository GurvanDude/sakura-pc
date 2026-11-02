# Sakura Optimizer

Sakura Optimizer surveille le PC et explique simplement pourquoi il rame.

## Prérequis

```powershell
pip install -r requirements.txt
```

## Lancement

```powershell
python optimizer.py monitor
```

Le moniteur affiche en temps réel le CPU, la RAM, le GPU, les disques, les températures et les processus les
plus gourmands. `Ctrl+C` permet de le quitter proprement.

Pour choisir la fréquence d'actualisation, faire une seule mesure ou obtenir du JSON :

```powershell
python optimizer.py monitor --interval 0.5
python optimizer.py monitor --once
python optimizer.py monitor --json
```

## Tests

Depuis la racine du dépôt :

```powershell
python -m pytest apps/optimizer/tests
```

La suite du projet est décrite dans la [feuille de route](../../docs/roadmaps/optimizer.md).
