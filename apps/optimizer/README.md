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

## Ménage

L'onglet **Ménage** commence toujours par un aperçu : il indique exactement la place et le nombre d'éléments,
sans rien modifier. Les fichiers confirmés sont déplacés pendant 7 jours dans une quarantaine sur le disque fixe
hors C: qui a le plus de place ; s'il n'y en a pas, elle reste dans le dossier utilisateur Sakura PC. L'onglet
**Ce que j'ai fait** permet de les remettre ou de vider définitivement la quarantaine.

La corbeille est différente : Windows la vide pour de bon, uniquement après une confirmation qui le dit clairement.
Opera GX doit être fermé avant de vider son cache. Tout fonctionne avec un compte Windows normal, sans droits
administrateur.

Commandes prévues pour Sakura AI :

```powershell
python optimizer.py cleanup --preview --json
python optimizer.py cleanup --apply temp,plantages --json
python optimizer.py actions --json
python optimizer.py undo <id> --json
```

## Démarrage de Windows

Dans l'onglet **Ménage**, la section **Au démarrage de Windows** montre les programmes lancés avec Windows.
Une entrée de ton compte peut être coupée puis remise en un clic. Pour que cela fonctionne aussi quand Sakura
Launcher remplace le bureau Windows, une entrée `Run` coupée est retirée du Registre et sa commande exacte est
gardée dans le journal. Les raccourcis sont rangés dans `%APPDATA%\SakuraPC\demarrage_coupe`, hors de la
quarantaine, et les applications du Store retrouvent leur état précédent lors de la remise.

Les réglages communs à tous les comptes restent en lecture seule : l'Optimizer ne demande jamais les droits
administrateur. Les applications lancées par Sakura Launcher se règlent dans **Sakura Launcher › Réglages ›
Démarrage**.

Commandes prévues pour Sakura AI :

```powershell
python optimizer.py startup --json
python optimizer.py startup --disable <id> --json
python optimizer.py startup --enable <id> --json
```

## Fichiers en double

La troisième section de l’onglet **Ménage** cherche les contenus strictement identiques dans les dossiers connus
Documents, Téléchargements, Images, Vidéos, Musique et Bureau. Elle regarde seulement les formats courants de
photos, vidéos, musique, documents et archives. Les installeurs `.exe` et `.msi` sont acceptés uniquement lorsqu’ils
traînent directement dans Documents, Téléchargements ou le Bureau.

Les petits fichiers sont laissés tranquilles. Sakura ne parcourt jamais les projets de code, les liens et jonctions,
les fichiers OneDrive en ligne seulement, les dossiers de logiciels, de jeux, de plugins ou de banques de sons, ni
les dossiers que tu as exclus. Une copie n’est proposée que si son contenu entier est identique à celui de la copie
gardée. Rien n’est coché automatiquement.

Les copies que tu confirmes vont dans la même quarantaine annulable que le ménage pendant 7 jours. Les fichiers sont
revérifiés juste avant leur déplacement et Sakura refuse toujours d’enlever toutes les copies d’un groupe. La commande
suivante fait seulement l’analyse, sans aucune action :

```powershell
python optimizer.py duplicates --json
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
