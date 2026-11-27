# Sakura Musique

Façade Sakura du lecteur Spotify : connexion OAuth PKCE, lecture en cours et télécommande Spotify Connect.
Spotify Premium est nécessaire pour piloter la lecture.

## Lancer

```powershell
python apps/musique/app.py
```

## Contrat entre applications

Les commandes JSON disponibles sont :

```powershell
python apps/musique/musique.py status --json
python apps/musique/musique.py now --json
python apps/musique/musique.py play --json
python apps/musique/musique.py pause --json
python apps/musique/musique.py next --json
```

`status` renvoie toujours :

- `connected` : booléen ;
- `user` : nom affiché Spotify ou `null`.

`now`, `play`, `pause` et `next` renvoient toujours `ok` (booléen) et `error` (texte ou `null`).
En cas de morceau disponible, les champs stables ajoutés sont :

- `is_playing`, `progress_ms`, `duration_ms` ;
- `title`, `artists` (tous les artistes dans un texte), `album`, `cover_url` ;
- `shuffle`, `repeat` (`off`, `context` ou `track`), `volume` ;
- `device`, avec `id`, `name` et `type`.

Quand rien ne joue, `now` renvoie aussi `playing: false`. Une commande de lecture réveille Spotify sur ce PC
si aucun appareil n’est actif. Les commandes en erreur terminent avec un code non nul et gardent un objet JSON
lisible sur la sortie standard.

## Préparer Spotify

Dans le tableau de bord de [Spotify for Developers](https://developer.spotify.com/dashboard), crée une appli, ajoute
`http://127.0.0.1:47823/callback` à ses adresses de retour, puis copie son Client ID dans Sakura Musique.

Le Client ID et les jetons sont enregistrés hors du dépôt dans
`%APPDATA%\SakuraPC\musique\token.json` (ou sous `SAKURA_HOME`). « Se déconnecter » efface ce fichier.
