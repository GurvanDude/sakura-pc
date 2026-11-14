(function (global) {
  "use strict";

  const doc = global.document;
  const listeners = new Set();
  const SVG_NS = "http://www.w3.org/2000/svg";
  const colors = { cpu: "var(--sk-cpu)", ram: "var(--sk-ram)", gpu: "var(--sk-gpu)", disk: "var(--sk-disk)" };

  function el(tag, className, text) {
    const node = doc.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function esc(value) {
    return String(value).replace(/[&<>'"]/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[char];
    });
  }

  function storageGet(key) {
    try { return global.localStorage.getItem(key); } catch (_) { return null; }
  }

  function storageSet(key, value) {
    try { global.localStorage.setItem(key, value); } catch (_) { /* stockage parfois bloque dans WebView2 */ }
  }

  function initialTheme() {
    const saved = storageGet("sakura.theme");
    if (saved === "day" || saved === "night") return saved;
    const hour = new Date().getHours();
    return hour >= 8 && hour < 18 ? "day" : "night";
  }

  function getTheme() {
    return doc.documentElement.dataset.theme === "night" ? "night" : "day";
  }

  function setTheme(theme) {
    const next = theme === "night" ? "night" : "day";
    doc.documentElement.dataset.theme = next;
    storageSet("sakura.theme", next);
    doc.querySelectorAll("[data-sk-theme-label]").forEach(function (button) {
      button.textContent = next === "day" ? "☾ Nuit" : "☀ Jour";
      button.setAttribute("aria-label", next === "day" ? "Passer au thème nuit" : "Passer au thème jour");
    });
    listeners.forEach(function (callback) { callback(next); });
    return next;
  }

  function toggleTheme() { return setTheme(getTheme() === "day" ? "night" : "day"); }
  function onThemeChange(callback) {
    if (typeof callback !== "function") return function () {};
    listeners.add(callback);
    return function () { listeners.delete(callback); };
  }

  function svgNode(name, attrs) {
    const node = doc.createElementNS(SVG_NS, name);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    return node;
  }

  function decor(target, options) {
    const host = typeof target === "string" ? doc.querySelector(target) : target;
    if (!host || host.querySelector(":scope > .sk-decor")) return host;
    const opts = Object.assign({ torii: "full" }, options || {});
    const layer = el("div", "sk-decor");
    layer.setAttribute("aria-hidden", "true");
    layer.appendChild(el("div", "sk-watermark", "桜"));
    layer.appendChild(el("i", "sk-petal sk-petal--1"));
    layer.appendChild(el("i", "sk-petal sk-petal--2"));
    for (let i = 0; i < 5; i += 1) layer.appendChild(el("i", "sk-star"));
    if (opts.torii !== false) {
      const svg = svgNode("svg", { viewBox: "0 0 200 170", class: "sk-torii" + (opts.torii === "faint" ? " is-faint" : "") });
      svg.style.fill = "rgba(255,47,166,.16)";
      svg.style.stroke = "#ff5cbb";
      svg.style.strokeWidth = "1.8";
      svg.style.filter = "drop-shadow(0 0 3px #ff2fa6) drop-shadow(0 0 12px rgba(255,47,166,.7))";
      [
        ["path", { d: "M2,14 C32,27 62,30 100,30 C138,30 168,27 198,14 L194,27 C166,37 138,40 100,40 C62,40 34,37 6,27 Z" }],
        ["rect", { x: "20", y: "40", width: "160", height: "7" }],
        ["rect", { x: "93", y: "47", width: "14", height: "17" }],
        ["rect", { x: "12", y: "64", width: "176", height: "9" }],
        ["path", { d: "M44,47 L57,47 L54,170 L37,170 Z" }],
        ["path", { d: "M143,47 L156,47 L163,170 L146,170 Z" }]
      ].forEach(function (part) { svg.appendChild(svgNode(part[0], part[1])); });
      layer.appendChild(svg);
    }
    host.insertBefore(layer, host.firstChild);
    return layer;
  }

  function callWindowApi(name) {
    const api = global.pywebview && global.pywebview.api;
    if (api && typeof api[name] === "function") return api[name]();
    return undefined;
  }

  function titlebar(options) {
    const opts = options || {};
    const bar = el("header", "sk-titlebar");
    const drag = el("div", "sk-titlebar-drag pywebview-drag-region");
    drag.append(el("span", "", "🌸"), el("span", "", opts.title || "Sakura PC"));
    const actions = el("div", "sk-titlebar-actions");
    (opts.actions || []).forEach(function (action) {
      const button = el("button", "sk-btn sk-btn--secondary sk-btn--small", action.label || "Action");
      button.type = "button";
      button.addEventListener("click", function () { if (typeof action.onClick === "function") action.onClick(); });
      actions.appendChild(button);
    });
    const themeButton = el("button", "sk-btn sk-btn--secondary sk-btn--small", "");
    themeButton.type = "button";
    themeButton.dataset.skThemeLabel = "";
    themeButton.addEventListener("click", toggleTheme);
    actions.appendChild(themeButton);
    const controls = el("div", "sk-window-controls");
    [
      ["—", "Réduire", opts.onMinimize, "minimize", ""],
      ["☐", "Agrandir ou restaurer", opts.onMaximize, "toggle_maximize", ""],
      ["✕", "Fermer", opts.onClose, "close", " sk-winbtn--close"]
    ].forEach(function (item) {
      const button = el("button", "sk-winbtn" + item[4], item[0]);
      button.type = "button";
      button.setAttribute("aria-label", item[1]);
      button.addEventListener("click", function () {
        if (typeof item[2] === "function") item[2](); else callWindowApi(item[3]);
      });
      controls.appendChild(button);
    });
    bar.append(drag, actions, controls);
    setTheme(getTheme());
    return bar;
  }

  function ensureBrushDefs() {
    if (doc.getElementById("sk-brush-defs")) return;
    const root = svgNode("svg", { id: "sk-brush-defs", width: "0", height: "0", "aria-hidden": "true" });
    root.style.position = "absolute";
    const defs = svgNode("defs");
    const noiseSeeds = [4, 13, 22, 35];
    const edgeSeeds = [8, 17, 26, 39];
    noiseSeeds.forEach(function (seed, index) {
      const filter = svgNode("filter", { id: "sk-ink" + index, x: "-10%", y: "-30%", width: "120%", height: "160%" });
      filter.appendChild(svgNode("feTurbulence", { type: "fractalNoise", baseFrequency: ".008 .55", numOctaves: "2", seed: String(seed), result: "n" }));
      filter.appendChild(svgNode("feColorMatrix", { in: "n", type: "matrix", values: "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 3.2 0 0 0 -.4", result: "a" }));
      filter.appendChild(svgNode("feComposite", { in: "SourceGraphic", in2: "a", operator: "in", result: "dry" }));
      filter.appendChild(svgNode("feTurbulence", { type: "fractalNoise", baseFrequency: ".03 .25", numOctaves: "2", seed: String(edgeSeeds[index]), result: "e" }));
      filter.appendChild(svgNode("feDisplacementMap", { in: "dry", in2: "e", scale: "7" }));
      defs.appendChild(filter);
    });
    root.appendChild(defs);
    (doc.body || doc.documentElement).appendChild(root);
  }

  const shapeA = [
    ["M10,22 C6,16 14,10 26,10 C70,6 120,4 160,8 C168,8 172,12 170,16 C150,18 120,20 30,24 Z", ".8"],
    ["M8,30 C4,22 16,18 30,18 C80,14 130,14 166,18 C176,20 178,30 172,34 L168,76 C130,82 80,84 28,84 C12,84 4,78 8,70 Z", "1"],
    ["M18,80 C60,76 120,74 160,76 C170,78 168,88 158,90 C120,92 70,94 24,92 C14,92 12,84 18,80 Z", ".75"],
    ["M168,22 L196,18 L194,21 L168,27 Z M170,40 L198,38 L196,42 L170,46 Z M170,58 L192,58 L190,62 L170,64 Z M166,74 L188,78 L186,81 L166,80 Z M160,86 L182,90 L178,92 L160,91 Z", ".85"]
  ];
  const shapeB = [
    ["M12,16 C4,12 10,6 24,6 C80,2 130,4 168,10 C178,12 176,22 168,24 L170,82 C130,88 80,88 26,86 C10,86 4,78 10,72 L8,26 C6,20 8,18 12,16 Z", "1"],
    ["M22,84 C70,80 120,80 156,84 C166,86 164,96 154,96 C110,98 66,98 26,96 C16,94 16,86 22,84 Z", ".7"],
    ["M170,14 L196,10 L194,14 L170,20 Z M172,34 L199,34 L196,38 L172,40 Z M172,52 L194,54 L192,57 L172,58 Z M170,70 L196,74 L192,77 L170,76 Z", ".85"]
  ];

  function parseColor(value) {
    const probe = el("span");
    probe.style.color = value || "#e0528a";
    probe.style.display = "none";
    doc.body.appendChild(probe);
    const resolved = global.getComputedStyle(probe).color;
    probe.remove();
    return resolved;
  }

  function rgbValues(value) {
    const match = parseColor(value).match(/[\d.]+/g);
    return match ? match.slice(0, 3).map(Number) : [224, 82, 138];
  }

  function neonColor(value, isDark) {
    if (isDark) return "#c9c3e6";
    const rgb = rgbValues(value);
    const max = Math.max.apply(null, rgb);
    const boosted = rgb.map(function (channel) { return Math.round(Math.min(255, channel + (255 - max) * .28)); });
    return "rgb(" + boosted.join(",") + ")";
  }

  function coverColor(img) {
    return new Promise(function (resolve) {
      const fallback = { color: "#e0528a", dark: false };
      if (!img) { resolve(fallback); return; }
      function sample() {
        try {
          const canvas = doc.createElement("canvas");
          canvas.width = canvas.height = 24;
          const context = canvas.getContext("2d", { willReadFrequently: true });
          context.drawImage(img, 0, 0, 24, 24);
          const data = context.getImageData(0, 0, 24, 24).data;
          let r = 0, g = 0, b = 0, count = 0;
          for (let i = 0; i < data.length; i += 16) {
            if (data[i + 3] < 80) continue;
            r += data[i]; g += data[i + 1]; b += data[i + 2]; count += 1;
          }
          if (!count) { resolve(fallback); return; }
          r = Math.round(r / count); g = Math.round(g / count); b = Math.round(b / count);
          const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
          resolve({ color: "rgb(" + r + "," + g + "," + b + ")", dark: luminance < .5 });
        } catch (_) { resolve(fallback); }
      }
      if (img.tagName === "CANVAS" || (img.complete && img.naturalWidth)) sample();
      else if (img.complete) resolve(fallback);
      else {
        img.addEventListener("load", sample, { once: true });
        img.addEventListener("error", function () { resolve(fallback); }, { once: true });
      }
    });
  }

  function brush(target, options) {
    const host = typeof target === "string" ? doc.querySelector(target) : target;
    if (!host) return Promise.resolve(null);
    const opts = Object.assign({ color: null, variant: 0 }, options || {});
    const variant = Math.abs(Number(opts.variant) || 0) % 4;
    function paint(result) {
      const chosen = result.color || opts.color || global.getComputedStyle(host).getPropertyValue("--sk-c").trim() || "#f6a9c1";
      if (result.dark) host.classList.add("is-dark"); else host.classList.remove("is-dark");
      host.style.setProperty("--sk-c", chosen);
      host.style.setProperty("--sk-n", neonColor(chosen, result.dark));
      const previous = host.querySelector(":scope > .sk-brush");
      if (previous) previous.remove();
      ensureBrushDefs();
      const svg = svgNode("svg", { class: "sk-brush", viewBox: "0 0 200 100", preserveAspectRatio: "none", "aria-hidden": "true" });
      const group = svgNode("g", { fill: chosen, filter: "url(#sk-ink" + variant + ")" });
      if (variant > 1) group.setAttribute("transform", "translate(0,100) scale(1,-1)");
      (variant % 2 === 0 ? shapeA : shapeB).forEach(function (part) { group.appendChild(svgNode("path", { d: part[0], opacity: part[1] })); });
      svg.appendChild(group);
      host.insertBefore(svg, host.firstChild);
      return host;
    }
    return opts.color === "auto" ? coverColor(opts.img).then(paint) : Promise.resolve(paint({ color: opts.color, dark: false }));
  }

  function tabs(container, onChange) {
    const root = typeof container === "string" ? doc.querySelector(container) : container;
    if (!root) return;
    const buttons = Array.from(root.querySelectorAll(":scope > .sk-tab"));
    const panelScope = root.parentElement || doc;
    function activate(button) {
      buttons.forEach(function (item) {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
        item.tabIndex = active ? 0 : -1;
      });
      panelScope.querySelectorAll("[data-panel]").forEach(function (panel) { panel.hidden = panel.dataset.panel !== button.dataset.tab; });
      if (typeof onChange === "function") onChange(button.dataset.tab, button);
    }
    buttons.forEach(function (button) { button.addEventListener("click", function () { activate(button); }); });
    activate(root.querySelector(".sk-tab.is-active") || buttons[0]);
  }

  function details(button, panel) {
    const trigger = typeof button === "string" ? doc.querySelector(button) : button;
    const content = typeof panel === "string" ? doc.querySelector(panel) : panel;
    if (!trigger || !content) return;
    const base = trigger.dataset.label || "Détails";
    function update(open) {
      trigger.setAttribute("aria-expanded", String(open));
      content.hidden = !open;
      trigger.textContent = open ? "Masquer les détails ▴" : base + " ▾";
    }
    update(false);
    trigger.addEventListener("click", function () { update(trigger.getAttribute("aria-expanded") !== "true"); });
  }

  function confirmAction(options) {
    const opts = Object.assign({ title: "Tu veux continuer ?", text: "Cette action demande une confirmation.", yes: "Oui, continuer", no: "Non, laisse" }, options || {});
    return new Promise(function (resolve) {
      const card = el("section", "sk-tip sk-confirm");
      card.setAttribute("role", "dialog");
      card.setAttribute("aria-modal", opts.into ? "false" : "true");
      const body = el("div", "sk-tip-body");
      body.append(el("div", "sk-tip-title", opts.title), el("p", "", opts.text));
      const actions = el("div", "sk-actions");
      const yes = el("button", "sk-btn sk-btn--danger", opts.yes);
      const no = el("button", "sk-btn sk-btn--secondary", opts.no);
      yes.type = no.type = "button";
      actions.append(yes, no); body.appendChild(actions); card.appendChild(body);
      const shell = opts.into ? card : el("div", "sk-modal");
      if (!opts.into) shell.appendChild(card);
      const destination = opts.into || doc.body;
      destination.appendChild(shell);
      function finish(value) { doc.removeEventListener("keydown", keydown); shell.remove(); resolve(value); }
      function keydown(event) { if (event.key === "Escape") finish(false); }
      yes.addEventListener("click", function () { finish(true); });
      no.addEventListener("click", function () { finish(false); });
      doc.addEventListener("keydown", keydown);
      no.focus();
    });
  }

  function savebar(options) {
    const opts = Object.assign({ message: "Des changements attendent" }, options || {});
    const bar = el("div", "sk-savebar");
    const save = el("button", "sk-btn sk-btn--primary", "Enregistrer");
    const cancel = el("button", "sk-btn sk-btn--secondary", "Annuler");
    const message = el("span", "sk-savebar-message", opts.message);
    message.appendChild(el("i", "sk-savebar-dot"));
    save.type = cancel.type = "button";
    save.addEventListener("click", function () { if (typeof opts.onSave === "function") opts.onSave(); });
    cancel.addEventListener("click", function () { if (typeof opts.onCancel === "function") opts.onCancel(); });
    bar.append(save, cancel, message);
    (doc.querySelector(".sk-window") || doc.body).appendChild(bar);
    return { element: bar, show: function () { bar.classList.add("is-visible"); }, hide: function () { bar.classList.remove("is-visible"); } };
  }

  function toast(text, options) {
    const opts = Object.assign({ kind: "ok" }, options || {});
    let zone = doc.querySelector(".sk-toast-zone");
    if (!zone) {
      zone = el("div", "sk-toast-zone"); zone.setAttribute("aria-live", "polite"); zone.setAttribute("aria-atomic", "true");
      doc.body.appendChild(zone);
    }
    const item = el("div", "sk-toast is-" + (opts.kind === "warn" ? "warn" : "ok"), text);
    zone.appendChild(item);
    global.setTimeout(function () { item.remove(); }, 3000);
    return item;
  }

  function updateRange(input) {
    const min = Number(input.min || 0), max = Number(input.max || 100), value = Number(input.value || 0);
    input.style.setProperty("--sk-progress", ((value - min) / Math.max(1, max - min) * 100) + "%");
  }

  function init(root) {
    const scope = root || doc;
    if (!doc.documentElement.dataset.theme) setTheme(initialTheme()); else setTheme(getTheme());
    scope.querySelectorAll(".sk-window").forEach(function (windowNode) { decor(windowNode, { torii: windowNode.dataset.torii === "faint" ? "faint" : windowNode.dataset.torii === "false" ? false : "full" }); });
    scope.querySelectorAll(".sk-stat, [data-sk-brush]").forEach(function (item) {
      if (item.querySelector(":scope > .sk-brush")) return;
      const siblings = Array.from(item.parentElement ? item.parentElement.children : [item]).filter(function (node) { return node.matches && node.matches(".sk-stat, [data-sk-brush]"); });
      const variant = siblings.indexOf(item) % 4;
      const type = ["cpu", "ram", "gpu", "disk"].find(function (name) { return item.classList.contains("sk-stat--" + name); });
      brush(item, { color: item.dataset.skBrush || (type ? colors[type] : null), variant: variant });
    });
    scope.querySelectorAll(".sk-range").forEach(function (input) { updateRange(input); input.addEventListener("input", function () { updateRange(input); }); });
  }

  const Sakura = Object.freeze({
    esc: esc, init: init, decor: decor, titlebar: titlebar,
    setTheme: setTheme, toggleTheme: toggleTheme, getTheme: getTheme, onThemeChange: onThemeChange,
    brush: brush, coverColor: coverColor, tabs: tabs, confirm: confirmAction,
    details: details, savebar: savebar, toast: toast
  });

  global.Sakura = Sakura;
  if (!doc.documentElement.dataset.theme) doc.documentElement.dataset.theme = initialTheme();
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", function () { init(); }, { once: true });
  else init();
}(window));
