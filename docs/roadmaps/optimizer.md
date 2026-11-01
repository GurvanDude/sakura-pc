# Sakura Optimizer : feuille de route

**Fini quand :** tu lances un gros programme et l'outil te dit précisément pourquoi ça rame.

- [ ] 1. **Base** : structure du projet, moniteur CLI en temps réel (CPU, RAM, GPU, disque, températures).
- [ ] 2. **Mémoire** : historique des métriques en SQLite.
- [ ] 3. **Diagnostic** : détecteur de goulot et commande `diagnose` avec un verdict lisible.
- [ ] 4. **Dashboard** : interface Sakura avec graphes live.
- [ ] 5. **Optimisations sûres** : démarrage Windows, caches, doublons, avec aperçu, annulation et journal.
- [ ] 6. **Profils auto** : Jeu / Travail / Éco.
- [ ] 7. **Ouverture à l'IA** : le cœur exposé comme outils (`get_status`, `diagnose`, `apply_action`).

Notes : le pilote PawnIO (déjà utilisé par Sakura Light pour la RAM) permet aussi de lire les températures.
