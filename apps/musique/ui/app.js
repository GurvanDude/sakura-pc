(function () {
  "use strict";

  const $ = selector => document.querySelector(selector);
  let bridge = null;
  let loginTimer = null;
  let apiTimer = null;
  let clockTimer = null;
  let volumeTimer = null;
  let lastError = null;
  let current = null;
  let lastTick = 0;
  let draggingProgress = false;
  let playerBusy = false;
  let paintedCover = null;

  const screens = { setup: $("#setup-screen"), login: $("#login-screen"), connected: $("#connected-screen") };

  function show(name) {
    Object.entries(screens).forEach(([key, element]) => { element.hidden = key !== name; });
    if (name === "connected") startPlayerPolling(); else stopPlayerPolling();
  }

  function toastError(message) {
    const text = message || "Spotify ne répond pas, je réessaie.";
    Sakura.toast(text, { kind: "warn" });
  }

  function renderAccount(state) {
    $("#profile-name").textContent = state.user || "Gurvan";
    const hasImage = Boolean(state.image);
    $("#avatar").hidden = !hasImage;
    $("#avatar-fallback").hidden = hasImage;
    if (hasImage) $("#avatar").src = state.image;
    const premium = state.product === "premium";
    $("#premium-badge").hidden = !premium;
    $("#premium-tip").hidden = premium;
  }

  function renderState(state) {
    const loginState = state.login || {};
    if (state.redirect_uri) $("#redirect-uri").textContent = state.redirect_uri;
    if (!state.client_id_present) show("setup");
    else if (state.connected) { show("connected"); renderAccount(state); }
    else {
      show("login");
      $("#waiting").hidden = !loginState.active;
      $("#login").hidden = Boolean(loginState.active);
      $("#cancel-login").hidden = !loginState.active;
      $("#change-client").hidden = Boolean(loginState.active);
      $("#login-subtitle").textContent = loginState.active
        ? "Le navigateur est ouvert : je reste ici avec toi."
        : "Spotify va s’ouvrir dans ton navigateur.";
    }
    if (loginState.error && !loginState.cancelled && loginState.error !== lastError) {
      lastError = loginState.error;
      toastError(loginState.error);
    }
  }

  async function refreshState() {
    if (!bridge) return;
    try {
      const state = await bridge.state();
      renderState(state);
      if (state.login && state.login.active) loginTimer = window.setTimeout(refreshState, 450);
    } catch (_) { toastError("Je n’arrive pas à lire l’état de Spotify."); }
  }

  function formatTime(milliseconds) {
    const seconds = Math.max(0, Math.floor((Number(milliseconds) || 0) / 1000));
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
  }

  function applyAccent() {
    const card = $("#player-card");
    const cover = $("#cover");
    card.classList.toggle("sk-neon", Sakura.getTheme() === "night");
    if (!current || !current.cover_url) {
      const oldBrush = card.querySelector(":scope > .sk-brush");
      if (oldBrush) oldBrush.remove();
      card.classList.remove("is-dark");
      card.style.setProperty("--sk-n", "#c9c3e6");
      return;
    }
    Sakura.coverColor(cover).then(result => {
      const neon = result.dark ? "#c9c3e6" : result.color;
      card.style.setProperty("--sk-n", neon);
      if (Sakura.getTheme() === "day") Sakura.brush(card, { color: "auto", img: cover, variant: 1 });
    });
  }

  function renderPlayer(state) {
    current = state;
    lastTick = Date.now();
    const hasTrack = Boolean(state && state.title);
    $("#player-empty").hidden = hasTrack;
    $("#player-content").hidden = !hasTrack;
    if (!hasTrack) {
      $("#player-verdict").textContent = "Rien ne joue pour l’instant";
      $("#player-subtitle").textContent = "Lance Spotify en arrière-plan pour commencer.";
      applyAccent();
      return;
    }
    $("#player-verdict").textContent = state.is_playing ? "Ça joue : " + state.title : "En pause";
    $("#player-subtitle").textContent = state.artists || "Spotify";
    $("#track-title").textContent = state.title;
    $("#track-artists").textContent = state.artists;
    $("#track-album").textContent = state.album;
    const cover = $("#cover");
    if (state.cover_url && paintedCover !== state.cover_url) {
      paintedCover = state.cover_url;
      cover.crossOrigin = "anonymous";
      cover.onload = applyAccent;
      cover.src = state.cover_url;
    }
    if (!draggingProgress) {
      $("#progress").max = Math.max(1, state.duration_ms || 1);
      $("#progress").value = Math.min(state.progress_ms || 0, state.duration_ms || 1);
    }
    $("#elapsed").textContent = formatTime(state.progress_ms);
    $("#duration").textContent = formatTime(state.duration_ms);
    $("#volume").value = state.volume;
    const play = $("#toggle-play");
    play.textContent = state.is_playing ? "Ⅱ" : "▶";
    play.setAttribute("aria-label", state.is_playing ? "Mettre en pause" : "Lire");
    play.title = state.is_playing ? "Mettre en pause" : "Lire";
    $("#shuffle").classList.toggle("is-active", state.shuffle);
    $("#shuffle").setAttribute("aria-label", state.shuffle ? "Désactiver la lecture aléatoire" : "Activer la lecture aléatoire");
    $("#repeat-mark").textContent = state.repeat === "track" ? "1" : state.repeat === "context" ? "•" : "";
    $("#repeat").classList.toggle("is-active", state.repeat !== "off");
    $("#repeat").setAttribute("aria-label", "Répétition : " + ({ off: "désactivée", context: "playlist", track: "morceau" }[state.repeat] || "désactivée"));
    if (state.device && state.device.id) $("#device").value = state.device.id;
  }

  async function refreshDevices() {
    if (!bridge) return;
    const result = await bridge.devices();
    if (!result.ok) { toastError(result.error); return; }
    const select = $("#device");
    const selected = current && current.device ? current.device.id : select.value;
    select.replaceChildren();
    if (!result.devices.length) select.add(new Option("Aucun appareil", ""));
    result.devices.forEach(device => select.add(new Option(device.name + (device.type ? " · " + device.type : ""), device.id)));
    if (selected) select.value = selected;
  }

  async function refreshPlayer(withDevices) {
    if (!bridge || playerBusy) return;
    playerBusy = true;
    try {
      const result = await bridge.player();
      if (!result.ok) toastError(result.error); else renderPlayer(result.player);
      if (withDevices) await refreshDevices();
    } catch (_) { toastError("Spotify ne répond pas, je réessaie."); }
    finally { playerBusy = false; }
  }

  function advanceClock() {
    if (!current || !current.is_playing || draggingProgress) return;
    const now = Date.now();
    current.progress_ms = Math.min(current.duration_ms, current.progress_ms + (now - lastTick));
    lastTick = now;
    $("#progress").value = current.progress_ms;
    $("#elapsed").textContent = formatTime(current.progress_ms);
  }

  function startPlayerPolling() {
    if (!apiTimer) {
      refreshPlayer(true);
      apiTimer = window.setInterval(() => refreshPlayer(true), 3000);
      clockTimer = window.setInterval(advanceClock, 1000);
    }
  }

  function stopPlayerPolling() {
    window.clearInterval(apiTimer); window.clearInterval(clockTimer);
    apiTimer = null; clockTimer = null;
  }

  async function action(call) {
    try {
      const result = await call();
      if (!result.ok) toastError(result.error);
      else renderPlayer(result.player);
      await refreshPlayer(true);
    } catch (_) { toastError("Spotify ne répond pas, je réessaie."); }
  }

  async function waitForApi() {
    if (window.pywebview && window.pywebview.api) return window.pywebview.api;
    return new Promise(resolve => window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true }));
  }

  $("#save-client-id").addEventListener("click", async () => {
    const input = $("#client-id"), value = input.value.trim();
    if (!/^[0-9a-fA-F]{32}$/.test(value)) {
      $("#client-id-help").textContent = "Ce Client ID ne semble pas bon : il faut exactement 32 caractères hexadécimaux.";
      input.focus(); return;
    }
    const result = await bridge.save_client_id(value);
    if (!result.ok) { $("#client-id-help").textContent = result.error; return; }
    lastError = null; await refreshState();
  });
  $("#copy-redirect").addEventListener("click", async () => {
    const result = await bridge.copy_redirect();
    Sakura.toast(result.ok ? "Adresse copiée." : result.error, { kind: result.ok ? "ok" : "warn" });
  });
  $("#login").addEventListener("click", async () => {
    lastError = null; const result = await bridge.login();
    if (!result.ok) { toastError(result.error); return; }
    window.clearTimeout(loginTimer); await refreshState();
  });
  $("#cancel-login").addEventListener("click", async () => { await bridge.cancel_login(); window.clearTimeout(loginTimer); window.setTimeout(refreshState, 300); });
  $("#change-client").addEventListener("click", async () => { await bridge.logout(); $("#client-id").value = ""; await refreshState(); });
  $("#logout").addEventListener("click", async () => {
    const confirmed = await Sakura.confirm({ title: "Déconnecter ton compte Spotify ?", text: "Le Client ID et les jetons enregistrés sur ce PC seront effacés.", yes: "Oui, déconnecte", no: "Non, laisse" });
    if (!confirmed) return;
    await bridge.logout(); $("#client-id").value = ""; await refreshState();
  });

  $("#toggle-play").addEventListener("click", () => action(() => bridge.toggle_play()));
  $("#next").addEventListener("click", () => action(() => bridge.next()));
  $("#previous").addEventListener("click", () => action(() => bridge.previous()));
  $("#shuffle").addEventListener("click", () => action(() => bridge.shuffle(!(current && current.shuffle))));
  $("#repeat").addEventListener("click", () => {
    const order = ["off", "context", "track"], mode = current ? current.repeat : "off";
    action(() => bridge.repeat(order[(order.indexOf(mode) + 1) % order.length]));
  });
  $("#progress").addEventListener("pointerdown", () => { draggingProgress = true; });
  $("#progress").addEventListener("input", event => { $("#elapsed").textContent = formatTime(event.target.value); });
  $("#progress").addEventListener("change", event => { draggingProgress = false; action(() => bridge.seek(Number(event.target.value))); });
  $("#volume").addEventListener("input", event => {
    window.clearTimeout(volumeTimer);
    const value = Number(event.target.value);
    volumeTimer = window.setTimeout(() => action(() => bridge.volume(value)), 300);
  });
  $("#volume").addEventListener("change", event => { window.clearTimeout(volumeTimer); action(() => bridge.volume(Number(event.target.value))); });
  $("#device").addEventListener("change", event => { if (event.target.value) action(() => bridge.choose_device(event.target.value)); });
  $("#wake-spotify").addEventListener("click", async () => {
    $("#empty-title").textContent = "Je réveille Spotify…";
    $("#empty-text").textContent = "Ça peut prendre une vingtaine de secondes.";
    $("#wake-spotify").disabled = true;
    const result = await bridge.wake_spotify();
    if (!result.ok) toastError(result.error);
    const watcher = window.setInterval(async () => {
      const wake = await bridge.wake_state();
      if (!wake.active) {
        window.clearInterval(watcher); $("#wake-spotify").disabled = false;
        if (wake.error) toastError(wake.error);
        $("#empty-title").textContent = "Rien ne joue pour l’instant";
        $("#empty-text").textContent = "Choisis ta musique dans Spotify, puis reviens ici.";
        await refreshPlayer(true);
      }
    }, 600);
  });
  $("#show-spotify").addEventListener("click", async () => { const result = await bridge.show_spotify(); if (!result.ok) toastError(result.error); });

  async function start() {
    const windowNode = $("#musique-window");
    windowNode.prepend(Sakura.titlebar({ title: "Sakura Musique" }));
    Sakura.init(windowNode);
    Sakura.details($("#details-toggle"), $("#account-details"));
    Sakura.onThemeChange(applyAccent);
    bridge = await waitForApi();
    await refreshState();
  }

  start();
}());
