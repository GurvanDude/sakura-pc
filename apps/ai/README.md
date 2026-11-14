# Sakura AI

Sakura AI est l'assistante locale de Sakura PC. Elle permet de discuter avec un modèle Ollama dans une fenêtre
Sakura, disponible en thème jour ou nuit grâce au kit UI commun. Les discussions restent disponibles au prochain
démarrage et se retrouvent dans la colonne de gauche, regroupées par date.

## Discussions

- **＋ Nouvelle discussion** prépare un fil vierge sans créer de fichier inutile ;
- le bouton **☰** affiche ou masque la liste (elle devient un panneau sur une fenêtre étroite) ;
- les boutons **✎** et **🗑** permettent de renommer une discussion ou de la placer dans la corbeille ;
- après le premier échange, Ollama propose automatiquement un titre court, sans remplacer un titre choisi à la main.

Une conversation est enregistrée dans `%APPDATA%\SakuraPC\ai\chats` au premier message. Une discussion supprimée
est déplacée dans le sous-dossier `.trash` et reste donc récupérable. L'ancien `chat.json`, lorsqu'il existe, est
migré une seule fois puis conservé sous le nom `chat.migrated.json`.

## Ce que Sakura sait faire

En plus de répondre aux messages, Sakura peut maintenant utiliser des outils locaux pour :

- ouvrir une application ou un jeu enregistré dans Sakura Launcher ;
- lister les applications et les jeux disponibles ;
- régler le volume général ou couper le son ;
- chercher un fichier par son nom dans les dossiers personnels ;
- fermer une application, uniquement après une confirmation dans la conversation.

Les actions et les confirmations sont journalisées sans enregistrer le contenu des messages.

## Prérequis

- Python 3.13 ;
- [Ollama](https://ollama.com) installé et lancé ;
- le modèle `qwen3:14b` téléchargé avec `ollama pull qwen3:14b`.

Installer les dépendances Python :

```powershell
python -m pip install -r apps/ai/requirements.txt
```

Le modèle peut être changé dans `%APPDATA%\SakuraPC\config.json` :

```json
{
  "ai": { "model": "qwen3:14b" }
}
```

Sans ce réglage, Sakura utilise `qwen3:14b` automatiquement.

## Lancer

Depuis la racine du dépôt :

```powershell
python apps/ai/ai.py
```

## Tester

Les tests n'utilisent ni Internet ni un vrai serveur Ollama :

```powershell
python -m pytest apps/ai/tests -q
```

## Créer le raccourci Bureau

Après avoir installé les dépendances :

```powershell
python apps/ai/tools/make_shortcut.py
```

Le raccourci **Sakura AI** lance la fenêtre sans ouvrir de terminal.
