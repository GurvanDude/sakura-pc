# Sakura Musique : feuille de route

Ton Spotify dans une vraie fenêtre Sakura, plus belle et plus calme que l'appli officielle. Sakura Musique est la
**façade et la télécommande** : le son est joué par Spotify, caché en arrière-plan (Spotify Connect). Compte
Premium requis pour piloter la lecture.

**Fini quand :** tu ouvres Sakura Musique, tu retrouves tes playlists, tu lances un morceau, et l'appli officielle
reste invisible.

- [ ] 1. **Connexion Spotify** : Gurvan crée une appli gratuite sur developer.spotify.com (adresse de retour
      `http://127.0.0.1:<port>/callback`), on se connecte depuis la fenêtre (OAuth PKCE, sans mot de passe dans
      l'appli). Jeton dans `%APPDATA%\SakuraPC` via `core.paths`, jamais dans le dépôt ; « Se déconnecter » efface tout.
- [ ] 2. **Lecteur** : morceau en cours (pochette, titre, artiste, progression), lecture/pause, suivant/précédent,
      volume, aléatoire/répétition, choix de l'appareil. Si aucun appareil n'est actif, Spotify est lancé caché.
- [ ] 3. **Bibliothèque** : playlists, titres likés, albums, recherche, file d'attente, ajouter aux favoris.
- [ ] 4. **Look Sakura** : charte jour/nuit, couleur d'accent prise sur la pochette (comme les jaquettes du
      Launcher), mini-lecteur (petite fenêtre au-dessus des autres).
- [ ] 5. **Branchements** : commandes `musique.py now|play|pause|next --json` (contrat entre applis) pour Sakura AI
      (« mets de la musique ») et le Launcher ; option : Sakura Light prend la couleur de la pochette.
- [ ] 6. **Plus tard** : ambiances selon l'heure (playlist du matin, du soir), raccourcis clavier globaux.

Limites connues : l'API officielle ne donne pas les paroles ; Spotify doit tourner (même caché) pour jouer le son.
