# Charte UI Sakura PC

Validée avec Gurvan le 14/11/2026. Toutes les applis (sauf l'écran du Launcher lui-même, déjà fini) suivent
cette charte et utilisent le kit commun `design/ui/` (`sakura.css` + `sakura.js`). Démo vivante :
`design/ui/demo.html` (ouvrir dans un navigateur, bouton ☀/☾ pour changer de mode).

## Règle pour les agents d'appli

- **Réutilise le kit.** Pas de couleur, police, bouton ou carte recréé à la main : classes `sk-*` et variables `--sk-*`.
- **Besoin d'un nouvel élément ?** Construis-le à partir de ce qui existe, puis propose-le à l'agent principal
  pour qu'il entre dans le kit (PR sur `shared`). Ne modifie jamais `design/` depuis une branche d'appli.
- Chaque écran existe en **jour et nuit** ; on teste les deux avant une PR.

## Base commune à toutes les fenêtres

- **Fenêtre sans bordure Windows**, avec la barre de titre Sakura (32 px) : 🌸 + nom de l'appli à gauche ;
  à droite, d'éventuels boutons d'appli (pilule), la pilule ☀ Jour / ☾ Nuit, puis — ☐ ✕ façon Windows
  (40×32, ✕ rouge #e81123 au survol).
- **Polices** : Zen Maru Gothic pour titres et chiffres, Nunito pour le texte. Japonais seulement en déco.
- **Ton** : français simple, on tutoie, on explique (« Ton PC est calme », pas de jargon). Bouton principal sans émoji.
- **Disposition type** : phrase de verdict (médaillon d'humeur + petit texte japonais + titre + sous-titre),
  puis le contenu principal, puis les détails repliés (« Détails ▾ »).
- **Boutons d'action en bas à gauche**, le principal en premier. Barre « changements à enregistrer » :
  Enregistrer, Annuler, puis le message avec une pastille kaki à droite.

## Mode jour : « sakura en fleur »

- Fond dégradé crème → rose `#fff6f9 → #ffe6f0`, filigrane 桜 vertical à droite (opacité .07), 2 pétales lents.
- Texte prune foncé `#3a1028`, secondaire `#7a4a62`.
- **Pinceaux : peu présents mais bien faits.** Coup de pinceau sec (encre qui manque par endroits, départ
  arrondi, poils effilés à droite), 4 variantes. Uniquement sur l'élément principal de l'écran :
  - indicateurs de l'Optimizer, une couleur fixe par type : processeur sakura `#f6a9c1`, mémoire glycine
    `#c3b6ee`, carte graphique ciel `#a9d4f2`, disque / alertes kaki `#f8bd86` ;
  - lignes de jeux du configurateur du Launcher : couleur de la jaquette, texte blanc si elle est sombre ;
  - zones de Lights : toutes en rose ; la couleur des LED est dans une pastille lumineuse.
  - Partout ailleurs (conseils, titres de section, chat) : **pas de pinceau**. L'onglet actif est souligné d'un petit trait de pinceau rose.
- Bouton principal : pilule dégradé `#e0528a → #c13d78` avec reflet. Secondaire : contour rose sur blanc translucide.
- Conseils et confirmations : carte blanche douce, bord gauche kaki `#f0a35e`.

## Mode nuit : « néon sakura » (jamais de pinceau)

- Fond `#12061a → #24093a` avec halos violet (haut droite) et rose (bas droite), quelques étoiles qui
  scintillent, pétales lumineux, 桜 en contour néon rose (jamais blanc), **torii néon rose en bas à droite**
  (vrai torii : poutre haute relevée, poutre basse, poteau central, piliers écartés ; plus discret derrière du contenu).
- Texte blanc, secondaire `#f1d9e8`, étiquettes `#e3c6ef`.
- Cartes : tube néon de leur couleur, intérieur teinté de la même couleur (jamais noir plat).
  Néons : processeur `#ff2fa6`, mémoire `#a77bff`, carte graphique `#3fc8ff`, disque / alertes `#ff9a3c`,
  jaquette sombre → néon lilas pâle `#c9c3e6`. Zones de Lights : toutes en rose.
- États : bon `#7dffcb`, attention `#ffbe7a`.
- Bouton principal : pilule `#ff2fa6 → #a03cff` qui brille. Secondaire : verre translucide, contour rose.
- Onglet actif : trait néon rose. Champs, listes : verre translucide `rgba(255,255,255,.07)`.

## Composants du kit

Barre de titre · fond jour/nuit (filigrane, pétales, étoiles, torii) · médaillon d'humeur + verdict ·
indicateur (pinceau / néon) · onglets · boutons principal / secondaire / petit / danger (« Retirer », kaki) ·
carte douce et ligne de liste · conseil · confirmation d'action risquée (« Oui, … » / « Non, laisse ») ·
bouton Détails repliable · barre d'enregistrement · toast · curseur, sélecteur, segmenté (Jour / Nuit / Auto) ·
bulles de chat + zone de saisie + « Sakura écrit… ».

## Maquettes validées par appli

- **Launcher** : écran principal inchangé. Configurateur (Réglages) : onglets, lignes de jeux sur pinceau
  couleur jaquette (jour) / néon couleur jaquette (nuit), boutons Image ↑ ↓ Retirer en pastilles.
- **Lights** : onglet Ambiances, segmenté Jour / Nuit / Auto, zones en grille 2 colonnes, réglages dans un encadré blanc (jour) / verre (nuit).
- **Optimizer** : verdict, 4 indicateurs, « Qui utilise ton PC ? » (barres processeur rose, mémoire glycine), conseil, actions.
- **Sakura AI** : chat, « ＋ Nouvelle discussion » dans la barre de titre, confirmation dans la bulle, saisie en pilule.
