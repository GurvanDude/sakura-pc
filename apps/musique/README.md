# Sakura Musique

Première étape de l’application : connecter le compte Spotify de Gurvan avec OAuth PKCE, sans secret client.

## Lancer

```powershell
python apps/musique/app.py
```

La commande inter-applications est :

```powershell
python apps/musique/musique.py status --json
```

Elle renvoie toujours `connected` (booléen) et `user` (nom affiché Spotify ou `null`).

## Préparer Spotify

Dans le tableau de bord de [Spotify for Developers](https://developer.spotify.com/dashboard), crée une appli, ajoute
`http://127.0.0.1:47823/callback` à ses adresses de retour, puis copie son Client ID dans Sakura Musique.

Le Client ID et les jetons sont enregistrés hors du dépôt dans
`%APPDATA%\SakuraPC\musique\token.json` (ou sous `SAKURA_HOME`). « Se déconnecter » efface ce fichier.
