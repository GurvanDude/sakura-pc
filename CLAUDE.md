# Sakura PC : consignes pour Claude

Écosystème d'applis Windows à l'esthétique sakura (voir README.md). Propriétaire : Gurvan, francophone.

**Cible : le PC de Gurvan.** Tout doit marcher sur SA machine (Windows 11, B550 AORUS ELITE AX V2, RAM Corsair
Vengeance RGB Pro, deux écrans). Ne pas sur-généraliser : la version « tous les PC » viendra beaucoup plus tard.
Garder quand même les données perso hors du dépôt (`core.paths`) pour que ce soit possible un jour.

## Règles du dépôt
- `main` = uniquement ce qui marche. Travailler sur la branche du projet : `launcher`, `lights`, `optimizer`,
  `ai`, ou `shared` pour `core/`, `design/`, `docs/` et l'outillage. Sous-branches possibles (`optimizer/graphes`).
- Une branche ne modifie que son projet (`.github/scripts/branch_guard.py`). Si une appli a besoin d'un
  changement dans `core/`, le faire d'abord sur `shared`, fusionner dans `main`, puis rebaser la branche.
- Rien de personnel dans le dépôt : tout ce qui est propre au PC passe par `core.paths` (`paths.USER`,
  `paths.CONFIG`, `paths.log()`), qui pointe vers `%APPDATA%\SakuraPC`.
- Tenir à jour la feuille de route de l'appli dans `docs/roadmaps/` (cases cochées).

## Conventions
- Python 3.13, interfaces en pywebview (HTML/CSS/JS servis en local), Windows uniquement.
- Textes à l'écran et commentaires en français, ton simple. Le japonais seulement en décoration.
- Couleurs et polices : `design/tokens.css` ; logos : `design/tools/make_logos.py`.
- Toute action risquée sur le PC (supprimer, désinstaller, modifier le registre ou le démarrage) :
  aperçu, confirmation, possibilité d'annuler, et journal.
- Les apps exposent leurs fonctions comme des outils simples pour que Sakura AI puisse les appeler.

## Répartition Claude / Codex (garder des crédits Claude)
- **Objectif :** quand les crédits Codex sont épuisés, il doit rester environ **80 % des crédits Claude** pour les
  commits, les PR et les petites retouches. Claude reste donc économe.
- **Codex** (compte ChatGPT de Gurvan) écrit l'essentiel du code. Depuis Bash :
  `codex exec -C <dossier> -s workspace-write -o <résumé.txt> "<consignes>" </dev/null`
  (le `</dev/null` est obligatoire, sinon Codex attend une saisie). Donner à Codex : les fichiers concernés,
  ce qu'il faut faire, les conventions ci-dessus, et ce qu'il ne doit pas toucher.
- **Claude** comprend la demande, découpe le travail, écrit des consignes courtes et précises, relit, teste,
  committe et gère les PR. Il ne code lui-même que les retouches de quelques lignes, ou quand Codex bloque.
- Relire sobrement : `git diff --stat` d'abord, puis seulement les parties qui comptent. Pas de lecture
  complète de gros fichiers ni d'exploration inutile.

## Feuilles de route
- `docs/roadmaps/launcher.md`, `lights.md`, `optimizer.md`, `ai.md`.
