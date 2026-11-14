# Kit UI Sakura

Ce dossier contient l'interface commune des applications Sakura PC. Il fonctionne directement dans une page HTML pywebview / Edge WebView2, sans framework ni build.

## Chargement

Charge les fichiers dans cet ordre :

```html
<link rel="stylesheet" href="../design/tokens.css">
<link rel="stylesheet" href="../design/ui/sakura.css">
<script src="../design/ui/sakura.js"></script>
```

Place toute la page dans `.sk-window`. Le thème actif est porté par `<html data-theme="day">` ou `<html data-theme="night">`. `Sakura.init()` choisit automatiquement le thème mémorisé, ajoute le décor et prépare les pinceaux et curseurs. La page [demo.html](demo.html) montre tous les composants.

## Classes principales

- Structure : `.sk-window`, `.sk-main`, `.sk-section`, `.sk-grid`, `.sk-stack`, `.sk-titlebar`.
- Verdict : `.sk-verdict`, `.sk-mood`, `.sk-tag`, `.sk-title`, `.sk-sub`.
- Indicateurs : `.sk-stat` avec `--cpu`, `--ram`, `--gpu` ou `--disk`, puis `.sk-stat-label`, `.sk-stat-value`, `.sk-stat-state`, `.is-ok`, `.is-warn`.
- Navigation : `.sk-tabs`, `.sk-tab`, `.is-active`, panneaux `[data-panel]`.
- Actions : `.sk-actions`, `.sk-btn` avec `--primary`, `--secondary`, `--small`, `--danger` ou `--icon`, et `.sk-chip`.
- Contenu : `.sk-card`, `.sk-neon`, `.sk-row`, `.sk-meter` avec `--cpu` ou `--ram`, `.sk-tip`, `.sk-encart`.
- Détails : `.sk-details-toggle`, `.sk-details`.
- Formulaires : `.sk-input`, `.sk-select`, `.sk-range`, `.sk-swatch`, `.sk-led`, `.sk-seg`.
- Chat : `.sk-chat`, `.sk-msg--sakura`, `.sk-msg--me`, `.sk-avatar`, `.sk-bubble`, `.sk-typing`, `.sk-composer`, `.sk-hint`.
- Pinceau libre : ajoute `[data-sk-brush]`. Tu peux donner une couleur avec `data-sk-brush="#f6a9c1"`.

Les couleurs se règlent uniquement avec les variables `--sk-*` définies dans `tokens.css`. Pour une carte néon libre, définis `--sk-n`. Pour une couleur de LED, de pinceau ou de barre, définis `--sk-c`.

## API JavaScript

- `Sakura.init(root?)` : initialise une page ou une partie de page.
- `Sakura.decor(el, {torii: 'full'|'faint'|false})` : ajoute le décor de fond.
- `Sakura.titlebar(options)` : crée la barre de titre. Options : `title`, `actions`, `onMinimize`, `onMaximize`, `onClose`.
- `Sakura.setTheme('day'|'night')`, `toggleTheme()`, `getTheme()`, `onThemeChange(callback)` : gèrent le thème.
- `Sakura.brush(el, {color, variant, img})` : pose un pinceau. `color: 'auto'` lit la couleur de `img`.
- `Sakura.coverColor(img)` : renvoie une promesse `{color, dark}`.
- `Sakura.tabs(container, onChange)` : active les onglets et leurs panneaux.
- `Sakura.details(button, panel)` : ouvre et ferme une zone de détails.
- `Sakura.confirm(options)` : affiche une confirmation et renvoie une promesse booléenne. `into` permet de l'insérer dans un élément.
- `Sakura.savebar({onSave, onCancel, message})` : renvoie `{element, show(), hide()}`.
- `Sakura.toast(text, {kind: 'ok'|'warn'})` : affiche un message pendant trois secondes.
- `Sakura.esc(value)` : échappe un texte avant une insertion HTML exceptionnelle. Préfère toujours `textContent`.

Les boutons d'icône doivent avoir un `aria-label`. Les animations sont automatiquement coupées si Windows demande moins de mouvements.
