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
- diagnostiquer les lenteurs, les lags et la chauffe du PC sur les 2, 5 ou 15 dernières minutes ;
- fermer une application, uniquement après une confirmation dans la conversation.

Les actions et les confirmations sont journalisées sans enregistrer le contenu des messages.

## Voix locale

Sakura peut écouter le micro avec Whisper puis lire ses réponses avec Kokoro. L'enregistrement, la transcription
et la synthèse restent entièrement sur le PC : aucun son ni texte dicté n'est envoyé en ligne ou écrit sur disque.

L'installation est séparée des dépendances principales. Depuis la racine du dépôt, lance ce script (un
double-clic sur le fichier fonctionne aussi) :

```powershell
python apps/ai/tools/setup_voice.py
```

Le script installe les paquets dans `apps/ai/vendor/site-packages/` et place les modèles dans
`apps/ai/vendor/models/`. Il peut être relancé sans retélécharger les fichiers déjà complets. Une fois
l'installation finie, le bouton **🎤** permet de dicter un message, `Ctrl + Espace` démarre ou arrête l'écoute,
et la pilule **🔊 Voix** active ou coupe la lecture des réponses.

## Contrat avec Sakura Optimizer

Sakura AI n'importe aucun code de l'Optimizer. Pour expliquer pourquoi le PC rame, elle lance uniquement sa
commande JSON avec le même interpréteur Python :

```powershell
python apps/optimizer/optimizer.py diagnose --minutes 5 --json
```

La sortie standard est lue comme du JSON puis réduite aux informations utiles pour la conversation : verdict,
frein principal, application concernée, disponibilité de suffisamment de mesures et quatre constats au maximum.
Les détails techniques restent dans le journal en cas d'erreur et ne sont pas affichés dans le chat.

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

Les tests n'utilisent ni Internet, ni vrai serveur Ollama, ni micro ou haut-parleur :

```powershell
python -m pytest apps/ai/tests -q
```

## Créer le raccourci Bureau

Après avoir installé les dépendances :

```powershell
python apps/ai/tools/make_shortcut.py
```

Le raccourci **Sakura AI** lance la fenêtre sans ouvrir de terminal.
