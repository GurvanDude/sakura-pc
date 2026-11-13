# Sakura Robot : feuille de route

Sakura AI dans un petit robot mignon posé sous l'écran, au lieu de vivre dans le PC. Le robot est le **corps**
(visage animé, voix, micro) ; le **cerveau** reste dans le PC (Sakura AI, Optimizer, Light…). Branché en USB,
il s'allume et s'éteint avec le PC.

**Fini quand :** au démarrage du PC, le robot se réveille, te dit bonjour, et tu peux lui demander à la voix
d'agir sur le PC.

Matériel de départ : kit tout fait sans soudure, ESP32-S3 avec écran, haut-parleur et micro intégrés
(ESP32-S3-BOX-3 ou M5Stack CoreS3, ~50 €). Pas d'imprimante 3D : la coque sera imprimée en ligne.

- [ ] 1. **Choix et achat du kit** : comparer les deux kits, valider avec Gurvan.
- [ ] 2. **Visage vivant** : yeux animés (cligne, dort, s'étonne), allumage avec le PC via USB.
- [ ] 3. **Passerelle PC ↔ robot** : le PC envoie l'humeur du robot selon l'état du PC (Optimizer, jeu lancé, nuit).
- [ ] 4. **Il parle** : Sakura AI écrit, le PC fait la voix, le robot la joue (phrases de temps en temps).
- [ ] 5. **Il écoute** : micro du robot → le PC comprend → Sakura AI agit sur le PC (confirmation si risqué).
- [ ] 6. **Coque mignonne** : modèle 3D sakura, impression par un service en ligne.
- [ ] 7. **Plus tard** : tête qui bouge (servo), puis roues ou pattes et station de recharge.

Dépend de : Sakura AI étapes 1-2 (étape 4), étape 4 Voix (étape 5) ; Optimizer `get_status` (étape 3).
