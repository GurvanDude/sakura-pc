<p align="center"><img src="design/logo/sakura-pc.png" width="140" alt="Sakura PC"></p>

<h1 align="center">Sakura PC</h1>
<p align="center">Un écosystème d'applis Windows aux couleurs du sakura 🌸</p>

| | Appli | Ce qu'elle fait | État |
|---|---|---|---|
| <img src="design/logo/launcher.png" width="40"> | **Sakura Launcher** | Remplace le bureau au démarrage : choisis ton jeu et tes applis, tout se lance dans l'ordre | ✅ utilisé tous les jours |
| <img src="design/logo/light.png" width="40"> | **Sakura Light** | Éclairage RGB synchronisé : tempête de sakura au démarrage, ambiances jour / nuit | ✅ utilisé tous les jours |
| <img src="design/logo/optimizer.png" width="40"> | **Sakura Optimizer** | Surveille le PC et explique pourquoi ça rame | 🚧 en préparation |
| <img src="design/logo/ai.png" width="40"> | **Sakura AI** | Assistante locale (Ollama) qui pilote le PC, à la voix | 🚧 en préparation |
| 🤖 | **Sakura Robot** | Sakura AI dans un petit robot posé sous l'écran : visage animé, voix, s'allume avec le PC | 💭 idée |

## Organisation du dépôt

```
apps/        une appli par dossier (launcher, lights, optimizer, ai, robot)
core/        code partagé (chemins, fenêtres Sakura…)
design/      direction artistique : logos, couleurs, règles
docs/        feuilles de route de chaque appli
```

- **`main` ne contient que ce qui marche.** Chaque appli avance sur sa propre branche
  (`launcher`, `lights`, `optimizer`, `ai`, `robot`), le socle commun sur `shared`, puis on fusionne dans `main`.
- **Une branche ne touche que son projet** : vérifié par GitHub à chaque push
  (`.github/scripts/branch_guard.py`) et en local par un hook (`git config core.hooksPath .githooks`).
- **Rien de personnel dans le dépôt** : la config, les journaux, les jaquettes et les icônes vivent
  dans `%APPDATA%\SakuraPC`. Au premier lancement, la config part de `apps/launcher/config.example.json`.

## Pour quel PC ?

Pour l'instant, Sakura PC est fait **pour un PC précis** (le mien) : Windows 11, carte mère GIGABYTE B550 AORUS
ELITE AX V2, RAM Corsair Vengeance RGB Pro, deux écrans. Le code est public pour être lu et pour s'en inspirer ;
une version installable sur n'importe quel PC viendra bien plus tard.

## Prérequis

Windows 11, Python 3.13 (`pywebview`, `psutil`, `pycaw`, `openrgb-python`, `hidapi`).
Sakura Light utilise aussi [OpenRGB](https://openrgb.org) et le pilote [PawnIO](https://pawnio.eu).

## Licence

MIT
