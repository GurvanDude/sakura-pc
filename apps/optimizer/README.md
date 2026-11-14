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

## Historique

Sakura garde les mesures des 7 derniers jours dans `%APPDATA%\SakuraPC\history.db`. Elles restent uniquement
sur le PC. Tant que la fenêtre est ouverte, elle complète elle-même l'historique ; pour continuer quand elle est
fermée :

1. Ouvre un PowerShell **normal** (surtout pas en administrateur).
2. Depuis la racine du dépôt, colle :

   ```powershell
   powershell -ExecutionPolicy Bypass -File apps/optimizer/tools/install_history_task.ps1
   ```

3. Réponds **O**. L'enregistreur démarre tout de suite, puis à chaque ouverture de session.

Pour le désinstaller, ouvre aussi un PowerShell normal et colle :

```powershell
powershell -ExecutionPolicy Bypass -File apps/optimizer/tools/install_history_task.ps1 -Uninstall
```

La désinstallation arrête l'enregistreur et retire sa tâche planifiée, sans effacer l'historique déjà enregistré.

## Diagnostic

Quand un jeu rame, ouvre Sakura Optimizer puis clique sur **Pourquoi ça rame ?**. Choisis **2 min**, **5 min**
ou **15 min** : l'outil relit tout de suite les mesures déjà gardées, ajoute l'état actuel du PC et indique le
frein principal avec les chiffres mesurés et les gestes utiles. Il n'y a rien à lancer en administrateur et tu
n'as pas à attendre de nouvelles mesures.

La même analyse est disponible dans un terminal :

```powershell
python optimizer.py diagnose --minutes 5
python optimizer.py diagnose --minutes 5 --json
```

La première commande donne une explication simple. La seconde renvoie le résultat complet au format JSON.

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
