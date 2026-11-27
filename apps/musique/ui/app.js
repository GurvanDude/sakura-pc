(function () {
  "use strict";

  const $ = selector => document.querySelector(selector);
  let bridge = null;
  let pollTimer = null;
  let lastError = null;

  const screens = {
    setup: $("#setup-screen"),
    login: $("#login-screen"),
    connected: $("#connected-screen")
  };

  function show(name) {
    Object.entries(screens).forEach(([key, element]) => { element.hidden = key !== name; });
  }

  function render(state) {
    const loginState = state.login || {};
    if (state.redirect_uri) $("#redirect-uri").textContent = state.redirect_uri;
    if (!state.client_id_present) {
      show("setup");
    } else if (state.connected) {
      show("connected");
      $("#welcome").textContent = "Salut " + (state.user || "Gurvan") + " !";
      $("#profile-name").textContent = state.user || "Gurvan";
      const hasImage = Boolean(state.image);
      $("#avatar").hidden = !hasImage;
      $("#avatar-fallback").hidden = hasImage;
      if (hasImage) $("#avatar").src = state.image;
      const premium = state.product === "premium";
      $("#premium-badge").hidden = !premium;
      $("#premium-tip").hidden = premium;
    } else {
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
      Sakura.toast(loginState.error, { kind: "warn" });
    }
  }

  async function refresh() {
    if (!bridge) return;
    try {
      const state = await bridge.state();
      render(state);
      if (state.login && state.login.active) {
        pollTimer = window.setTimeout(refresh, 450);
      }
    } catch (_) {
      Sakura.toast("Je n’arrive pas à lire l’état de Spotify.", { kind: "warn" });
    }
  }

  async function waitForApi() {
    if (window.pywebview && window.pywebview.api) return window.pywebview.api;
    return new Promise(resolve => {
      window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true });
    });
  }

  $("#save-client-id").addEventListener("click", async () => {
    const input = $("#client-id");
    const value = input.value.trim();
    if (!/^[0-9a-fA-F]{32}$/.test(value)) {
      $("#client-id-help").textContent = "Ce Client ID ne semble pas bon : il faut exactement 32 caractères hexadécimaux.";
      input.focus();
      return;
    }
    const result = await bridge.save_client_id(value);
    if (!result.ok) {
      $("#client-id-help").textContent = result.error;
      return;
    }
    lastError = null;
    await refresh();
  });

  $("#copy-redirect").addEventListener("click", async () => {
    const result = await bridge.copy_redirect();
    Sakura.toast(result.ok ? "Adresse copiée." : result.error, { kind: result.ok ? "ok" : "warn" });
  });

  $("#login").addEventListener("click", async () => {
    lastError = null;
    const result = await bridge.login();
    if (!result.ok) {
      Sakura.toast(result.error, { kind: "warn" });
      return;
    }
    window.clearTimeout(pollTimer);
    await refresh();
  });

  $("#cancel-login").addEventListener("click", async () => {
    await bridge.cancel_login();
    window.clearTimeout(pollTimer);
    window.setTimeout(refresh, 300);
  });

  $("#change-client").addEventListener("click", async () => {
    await bridge.logout();
    $("#client-id").value = "";
    await refresh();
  });

  $("#logout").addEventListener("click", async () => {
    const confirmed = await Sakura.confirm({
      title: "Déconnecter ton compte Spotify ?",
      text: "Le Client ID et les jetons enregistrés sur ce PC seront effacés.",
      yes: "Oui, déconnecte",
      no: "Non, laisse"
    });
    if (!confirmed) return;
    await bridge.logout();
    $("#client-id").value = "";
    await refresh();
  });

  async function start() {
    const windowNode = $("#musique-window");
    windowNode.prepend(Sakura.titlebar({ title: "Sakura Musique" }));
    Sakura.init(windowNode);
    bridge = await waitForApi();
    await refresh();
  }

  start();
}());
