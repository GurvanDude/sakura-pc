# Sakura Optimizer : feuille de route

**Fini quand :** tu lances un gros programme et l'outil te dit précisément pourquoi ça rame.

**Principe :** tout est expliqué en français simple, avec le chiffre exact ET sa traduction en mots
(« bien occupé · 61 % »). Le terminal n'est qu'un outil technique.

- [x] 1. **Mesures** : structure du projet, moteur `get_status()` (CPU, RAM, GPU, disques, processus) et
      moniteur technique dans le terminal (`optimizer.py monitor`, `--once`, `--json`).
- [x] 2. **Fenêtre simple** : fenêtre Sakura avec une phrase-résumé, 4 cartes (chiffres + explication),
      « Qui utilise ton PC ? », conseils, bouton Détails ; raccourci Bureau (`tools/make_shortcut.py`).
- [x] 3. **Températures** : LibreHardwareMonitor + petite tâche admin au démarrage (comme OpenRGB).
- [x] 4. **Mémoire** : historique des mesures en SQLite, petits graphes dans la fenêtre.
- [ ] 5. **Diagnostic** : « Pourquoi ça rame ? » analyse les 2, 5 ou 15 dernières minutes et l'instant présent,
      nomme le frein avec ses chiffres et donne les gestes utiles (fenêtre + commande `diagnose`).
- [ ] 6. **Optimisations sûres** : démarrage Windows, caches, doublons, avec aperçu, annulation et journal.
- [ ] 7. **Profils auto** : Jeu / Travail / Éco.
- [ ] 8. **Ouverture à l'IA** : le cœur exposé comme outils (`get_status`, `diagnose`, `apply_action`).

Notes : le pilote PawnIO (déjà utilisé par Sakura Light pour la RAM) permet aussi de lire les températures.
Sous Windows, `psutil` donne la fréquence de base du CPU (3801 MHz), pas la vraie : LibreHardwareMonitor la donnera.
