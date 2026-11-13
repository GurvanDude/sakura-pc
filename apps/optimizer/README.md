# Sakura Optimizer

Sakura Optimizer explique simplement ce que fait le PC et propose des gestes concrets quand quelque chose mérite
de l'attention.

## Lancement

Double-cliquer sur le raccourci **Sakura Optimizer** du Bureau, ou lancer sans terminal :

```powershell
pythonw optimizer.py
```

Le raccourci peut être créé une fois avec `python tools/make_shortcut.py`.

## Températures

Pour voir la température du processeur :

1. Ouvre **PowerShell en administrateur**.
2. Colle cette ligne depuis la racine du dépôt :

   ```powershell
   powershell -ExecutionPolicy Bypass -File apps/optimizer/tools/install_temps_task.ps1
   ```

3. Réponds **O**. C'est tout : le lecteur démarrera tout seul avec Windows.

L'installeur place le lecteur et LibreHardwareMonitor 0.9.6 dans un dossier protégé de
`C:\ProgramData\SakuraPC\temps`. Il télécharge l'archive officielle, vérifie son SHA-256 avant de l'extraire et
n'exécute aucun Python avec les droits administrateur.

Mise à jour : relance la même commande. L'ancienne tâche et tous ses fichiers sont remplacés proprement.

Pour le retirer, ouvre de nouveau PowerShell en administrateur et colle :

```powershell
powershell -ExecutionPolicy Bypass -File apps/optimizer/tools/install_temps_task.ps1 -Uninstall
```

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
