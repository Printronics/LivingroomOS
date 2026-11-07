/* LivingroomOS – interface state, rendering, and flow.
   The backend is the single source of truth for running processes; this script
   only displays what /api/v1/apps/status reports and sends user intentions. */

import { api, ApiError } from "./api.js";
import { Navigator } from "./navigation.js";
import { initRemote } from "./remote.js";

const $ = (id) => document.getElementById(id);
const nav = new Navigator();

const POLL_MS = { idle: 4000, active: 1200, offline: 3000, hidden: 6000 };
const IDLE_STATUS = Object.freeze({ state: "idle", app_id: null, last_exit: null });
const HEX_COLOR = /^#[0-9a-f]{6}$/i;

const SETTINGS = [
  { key: "clock_24h", label: "Uhrzeit-Format", values: [[true, "24 Stunden"], [false, "12 Stunden"]], tab: "general" },
  { key: "show_clock", label: "Uhr anzeigen", values: [[true, "Ja"], [false, "Nein"]], tab: "general" },
  { key: "tile_size", label: "Tile size", values: [["normal", "Normal"], ["large", "Large"]], tab: "general" },
  { key: "show_app_subtitles", label: "App-Beschreibungen anzeigen", values: [[true, "Ja"], [false, "Nein"]], tab: "general" },
  { key: "reduce_motion", label: "Bewegungen reduzieren", values: [[true, "Ja"], [false, "Nein"]], tab: "general" },
  { key: "confirm_power", label: "Confirm before power off", values: [[true, "Ja"], [false, "Nein"]], tab: "system" },
];

const state = {
  apps: [],
  status: IDLE_STATUS,
  ui: { clock_24h: true, show_clock: true, tile_size: "normal", show_app_subtitles: true, reduce_motion: false, confirm_power: true },
  online: null,        // null = unbekannt, sonst true/false
  view: "home",        // "home" | "settings"
  settingsTab: "general",
  dialog: null,        // { key, onBack } solange ein Dialog offen ist
  seenExit: 0,         // höchste bereits gezeigte last_exit.seq
  firstStatus: true,
  launching: false,
};

let pollTimer = null;
let polling = false;
let toastTimer = null;
let saveSeq = 0;
let saveQueue = Promise.resolve();

/* ------------------------------------------------------------------ Helfer */

/** Baut Elemente ausschließlich über textContent (kein innerHTML → kein XSS). */
function h(tag, { class: cls, text, attrs = {}, on = {} } = {}, ...children) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  for (const [name, handler] of Object.entries(on)) node.addEventListener(name, handler);
  node.append(...children);
  return node;
}

const appById = (id) => state.apps.find((a) => a.id === id);
const viewEl = () => $(`view-${state.view}`);

function toast(message, ms = 4000) {
  const el = $("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}

function gearIcon() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("aria-hidden", "true");
  const teeth = document.createElementNS(ns, "circle");
  for (const [k, v] of Object.entries({ cx: 12, cy: 12, r: 8.5, "stroke-width": 4, "stroke-dasharray": "3.3 3.3" })) teeth.setAttribute(k, v);
  const ring = document.createElementNS(ns, "circle");
  for (const [k, v] of Object.entries({ cx: 12, cy: 12, r: 5.5, "stroke-width": 2.6 })) ring.setAttribute(k, v);
  svg.append(teeth, ring);
  return svg;
}

/* ------------------------------------------------------------------- Kacheln */

function tileFor(app) {
  const tile = h(
    "button",
    {
      class: "tile",
      attrs: { type: "button", "data-focusable": "", "data-key": app.id, "data-app": app.id },
      on: { click: () => launchApp(app) },
    },
    h("span", { class: "tile__icon", text: app.icon, attrs: { "aria-hidden": "true" } }),
    h("span", {}, h("span", { class: "tile__title", text: app.title }), h("span", { class: "tile__sub", text: state.ui.show_app_subtitles ? app.subtitle : "" })),
    h("span", { class: "tile__badge", attrs: { "data-role": "badge" } }),
  );
  if (HEX_COLOR.test(app.color)) tile.style.setProperty("--tile-color", app.color);
  return h("li", { class: "tiles__item" }, tile);
}

function settingsTile() {
  const icon = h("span", { class: "tile__icon", attrs: { "aria-hidden": "true" } }, gearIcon());
  const tile = h(
    "button",
    {
      class: "tile",
      attrs: { type: "button", "data-focusable": "", "data-key": "__settings" },
      on: { click: () => showView("settings") },
    },
    icon,
    h("span", {}, h("span", { class: "tile__title", text: "Settings" }), h("span", { class: "tile__sub", text: "System, display, and diagnostics" })),
  );
  return h("li", { class: "tiles__item" }, tile);
}

function renderTiles() {
  $("tiles").replaceChildren(...state.apps.filter((a) => a.category !== "debug").map(tileFor), settingsTile());
  updateTileStates();
  if (!state.dialog && state.view === "home") nav.setScope(viewEl());
}

function updateTileStates() {
  const { state: st, app_id: activeId } = state.status;
  for (const app of state.apps) {
    const tile = $("tiles").querySelector(`[data-app="${app.id}"]`);
    if (!tile) continue;
    const active = activeId === app.id && st !== "idle";
    let label = "";
    if (active) label = { starting: "Starting …", running: "Running", stopping: "Stopping …" }[st] ?? "";
    else if (!app.available) label = "Not installed";
    const badge = tile.querySelector('[data-role="badge"]');
    badge.textContent = label;
    badge.hidden = !label;
    badge.dataset.tone = active ? "active" : "muted";
    tile.classList.toggle("is-unavailable", !app.available && !active);
  }
}

/* ------------------------------------------------------------ Settings */
function renderSettings() {
  const rows = [];

  // Einstellungs-Tabs
  for (const [key, label] of [
    ["general", "Allgemein"],
    ["system", "System"],
    ["debug", "Debug"]
  ]) {
    rows.push(h("li", {}, h("button", {
      class: "row",
      attrs: {
        type: "button",
        "data-focusable": "",
        "data-key": `tab-${key}`
      },
      on: {
        click: () => {
          state.settingsTab = key;
          renderSettings();
          nav.setScope(viewEl());
        }
      }
    },
      h("span", { text: label }),
      h("span", {
        class: "row__value",
        text: state.settingsTab === key ? "Active" : "Open"
      })
    )));
  }

  // Allgemeine und System-Settings
  if (state.settingsTab === "general" || state.settingsTab === "system") {
    for (const setting of SETTINGS.filter(
      (item) => item.tab === state.settingsTab
    )) {
      rows.push(h("li", {}, h("button", {
        class: "row",
        attrs: {
          type: "button",
          "data-focusable": "",
          "data-repeatable": "",
          "data-key": setting.key,
          "data-setting": setting.key
        },
        on: {
          click: () => cycleSetting(setting.key, 1)
        }
      },
        h("span", { text: setting.label }),
        h("span", {
          class: "row__value",
          attrs: { "data-role": "value" }
        })
      )));
    }
  } else {
    // Debug-Settings
    rows.push(h("li", {}, h("p", {
      class: "row__value",
      text: "Test apps – diagnostics only"
    })));

    for (const app of state.apps.filter(
      (item) => item.category === "debug"
    )) {
      rows.push(h("li", {}, h("button", {
        class: "row",
        attrs: {
          type: "button",
          "data-focusable": "",
          "data-key": `debug-${app.id}`
        },
        on: {
          click: () => launchApp(app)
        }
      },
        h("span", { text: `${app.title} · ${app.subtitle}` }),
        h("span", {
          class: "row__value",
          text: "Starten"
        })
      )));
    }

    rows.push(h("li", {}, h("button", {
      class: "row",
      attrs: {
        type: "button",
        "data-focusable": "",
        "data-key": "debug-stop"
      },
      on: { click: stopApp }
    },
      h("span", { text: "Stop running test app" })
    )));
  }

  // Systemaktionen
  if (state.settingsTab === "system") {
    for (const [action, label] of [
      ["restart", "PC neu starten"],
      ["shutdown", "Shut down PC"]
    ]) {
      rows.push(h("li", {}, h("button", {
        class: "row",
        attrs: {
          type: "button",
          "data-focusable": "",
          "data-key": action
        },
        on: {
          click: () => requestPower(action)
        }
      },
        h("span", { text: label })
      )));
    }
  }

  // License and project information
  rows.push(h("li", {}, h("button", {
    class: "row",
    attrs: {
      type: "button",
      "data-focusable": "",
      "data-key": "about"
    },
    on: { click: showAbout }
  },
    h("span", { text: "About LivingroomOS" }),
    h("span", {
      class: "row__value",
      text: "License and source code"
    })
  )));

  // Back button
  rows.push(h("li", {}, h("button", {
    class: "row",
    attrs: {
      type: "button",
      "data-focusable": "",
      "data-key": "back"
    },
    on: {
      click: () => showView("home")
    }
  },
    h("span", { text: "Back" })
  )));

  // Liste anzeigen
  const list = $("settings-list");
  list.replaceChildren(...rows);

  // Einstellungswerte aktualisieren
  updateSettingValues();
}

function updateSettingValues() {
  for (const s of SETTINGS) {
    const out = $("settings-list").querySelector(
      `[data-setting="${s.key}"] [data-role="value"]`
    );

    const current = s.values.find(
      ([value]) => value === state.ui[s.key]
    );

    if (out) {
      out.textContent = `‹  ${current ? current[1] : "?"}  ›`;
    }
  }
}

async function cycleSetting(key, step) {
  const def = SETTINGS.find((s) => s.key === key);
  const index = Math.max(0, def.values.findIndex(([value]) => value === state.ui[key]));
  const next = def.values[(index + step + def.values.length) % def.values.length][0];
  const previous = state.ui[key];
  const ticket = ++saveSeq;

  state.ui[key] = next; // update immediately; revert if saving fails
  applyUi();
  updateSettingValues();
  // Keep PATCH requests in key-press order so an older write cannot overwrite a newer value.
  const pendingSave = saveQueue.then(() => api.saveSettings({ ui: { [key]: next } }));
  saveQueue = pendingSave.catch(() => undefined);
  try {
    const saved = (await pendingSave).ui;
    if (ticket === saveSeq) state.ui = saved; // only the latest response updates the UI
  } catch (err) {
    if (ticket === saveSeq) state.ui[key] = previous;
    toast(err.network ? "Backend unavailable – setting was not saved." : `Saving failed: ${err.message}`);
  }
  applyUi();
  updateSettingValues();
}

async function requestPower(action) {
  const restart = action === "restart";
  const perform = async () => {
    try {
      closeDialog();
      await api.power(action);
      showDialog({ key: `power:${action}`, spinner: true, title: restart ? "Preparing to restart" : "Shutting down system", text: "The system is carrying out the action.", actions: [] });
    } catch (err) { toast(`Systemaktion fehlgeschlagen: ${err.message}`); }
  };
  if (state.ui.confirm_power) showDialog({
    key: `confirm-power:${action}`, tone: "error",
    title: restart ? "Restart PC?" : "Shut down PC?",
    text: "Unsaved work in other applications may be lost.",
    actions: [{ label: "Cancel", run: closeDialog }, { label: restart ? "Restart" : "Shut down", run: perform }],
    onBack: closeDialog,
  });
  else await perform();
}

function applyUi() {
  document.body.dataset.tileSize = state.ui.tile_size;
  document.body.dataset.reduceMotion = String(state.ui.reduce_motion);
  $("clock").hidden = !state.ui.show_clock;
  updateClock();
}

function updateClock() {
  const fmt = new Intl.DateTimeFormat("de-DE", { weekday: "short", hour: "2-digit", minute: "2-digit", hour12: !state.ui.clock_24h });
  $("clock").textContent = fmt.format(new Date());
}

/* ------------------------------------------------------------------- Ansichten */

function showView(name) {
  state.view = name;
  document.body.dataset.view = name;
  $("view-home").hidden = name !== "home";
  $("view-settings").hidden = name !== "settings";
  if (!state.dialog) nav.setScope(viewEl());
}

/* --------------------------------------------------------------------- Dialoge */

/** Displays a modal dialog. The first action is selected by default. */
function showDialog({ key, title, text = "", tone = "info", spinner = false, actions = [], onBack }) {
  if (state.dialog?.key === key) return;
  state.dialog = { key, onBack };
  $("dialog").dataset.tone = tone;
  $("overlay-spinner").hidden = !spinner;
  $("overlay-title").textContent = title;
  $("overlay-text").textContent = text;
  $("overlay-text").hidden = !text;
  $("overlay-actions").replaceChildren(
    ...actions.map((action, i) =>
      h("button", { class: "btn", text: action.label, attrs: { type: "button", "data-focusable": "", "data-key": `a${i}` }, on: { click: action.run } }),
    ),
  );
  $("overlay").hidden = false;
  document.querySelector(".shell").inert = true;
  nav.setScope($("overlay-actions"), { reset: true });
}

function closeDialog() {
  if (!state.dialog) return;
  state.dialog = null;
  $("overlay").hidden = true;
  document.querySelector(".shell").inert = false;
  nav.setScope(viewEl());
}

function showAbout() {
  showDialog({
    key: "about-livingroomos",
    title: "About LivingroomOS",
    text: "LivingroomOS ist freie Software unter der GNU Affero General Public License Version 3 (AGPL-3.0). The full license text and source code are available through the links below.",
    actions: [
      {
        label: "AGPL-3.0 Lizenztext",
        run: () => {
          window.open(
            "https://github.com/Printronics/LivingroomOS/blob/main/LICENSE",
            "_blank",
            "noopener,noreferrer"
          );
        }
      },
      {
        label: "LivingroomOS Quellcode",
        run: () => {
          window.open(
            "https://github.com/Printronics/LivingroomOS",
            "_blank",
            "noopener,noreferrer"
          );
        }
      },
      {
        label: "Close",
        run: closeDialog
      }
    ],
    onBack: closeDialog
  });
}

/* ---------------------------------------------------------------- Anwendungen */

async function launchApp(app) {
  if (state.launching) return;
  state.launching = true;
  try {
    applyStatus(await api.launch(app.id), { force: true });
  } catch (err) {
    onLaunchError(err, app);
  } finally {
    state.launching = false;
  }
}

function onLaunchError(err, app) {
  if (!(err instanceof ApiError)) throw err;
  if (err.network) return setOnline(false, err);
  if (err.code === "busy" && err.data?.error?.status) {
    toast(err.message);
    return applyStatus(err.data.error.status, { force: true });
  }
  const notInstalled = err.code === "not_installed";
  showDialog({
    key: `launch-error:${app.id}`,
    tone: "error",
    title: notInstalled ? `${app.title} is not installed` : `${app.title} could not be started`,
    text: err.message,
    actions: notInstalled
      ? [{ label: "OK", run: closeDialog }]
      : [{ label: "Erneut versuchen", run: () => { closeDialog(); launchApp(app); } }, { label: "Cancel", run: closeDialog }],
    onBack: closeDialog,
  });
}

async function stopApp() {
  try {
    applyStatus(await api.stop());
  } catch (err) {
    if (err.network) return setOnline(false, err);
    toast(`Failed to stop: ${err.message}`);
  }
}

/** Applies backend status and reacts only to changes. */
function applyStatus(next, { force = false } = {}) {
  const prev = state.status;
  state.status = next;
  updateTileStates();
  if (force || prev.state !== next.state || prev.app_id !== next.app_id) onStatusChange(next);

  const exit = next.last_exit;
  state.seenExit = Math.min(state.seenExit, exit?.seq ?? 0); // A backend restart resets the counter
  if (state.firstStatus) {
    state.seenExit = exit?.seq ?? 0; // Do not report old events again when loading
    state.firstStatus = false;
  } else if (exit && exit.seq > state.seenExit) {
    state.seenExit = exit.seq;
    onExit(exit);
  }
}

function onStatusChange(next) {
  const name = appById(next.app_id)?.title ?? "The application";
  const key = `${next.state}:${next.app_id}`;
  switch (next.state) {
    case "starting":
      return showDialog({ key, spinner: true, title: `${name} wird gestartet …`, text: "Please wait.", actions: [{ label: "Cancel", run: stopApp }], onBack: stopApp });
    case "running":
      return showDialog({
        key,
        tone: "ok",
        title: `${name} läuft`,
        text: "The application ist in einem eigenen Fenster geöffnet. Nach dem Beenden erscheint wieder diese Oberfläche.",
        actions: [{ label: "Stop app", run: stopApp }, { label: "Hide", run: closeDialog }],
        onBack: closeDialog,
      });
    case "stopping":
      return showDialog({ key, spinner: true, title: `${name} wird beendet …` });
    default:
      if (state.dialog && /^(starting|running|stopping):/.test(state.dialog.key)) closeDialog();
  }
}

function onExit(exit) {
  const app = appById(exit.app_id);
  const name = app?.title ?? exit.app_id;
  if (exit.reason === "crashed" || exit.reason === "start_failed") {
    const detail = exit.signal ? `Signal ${exit.signal}` : `Exit-Code ${exit.code}`;
    const actions = [{ label: "OK", run: closeDialog }];
    if (app) actions.unshift({ label: "Erneut starten", run: () => { closeDialog(); launchApp(app); } });
    showDialog({
      key: `exit:${exit.seq}`,
      tone: "error",
      title: exit.reason === "crashed" ? `${name} exited unexpectedly` : `${name} could not be started`,
      text: `${detail} nach ${Math.round(exit.runtime_s)} s.`,
      actions,
      onBack: closeDialog,
    });
  } else if (exit.reason === "ok") {
    toast(`${name} has exited.`);
  }
}

/* ---------------------------------------------------------- Verbindung zum Backend */

async function loadAll() {
  const [apps, settings] = await Promise.all([api.apps(), api.settings()]);
  state.apps = apps.apps;
  state.ui = settings.ui;
  state.status = IDLE_STATUS; // erzwingt den Neuaufbau eines evtl. verdeckten Dialogs
  renderTiles();
  renderSettings();
  applyUi();
  applyStatus(apps.status);
}

function setOnline(flag, err) {
  state.online = flag;
  const pill = $("conn");
  pill.dataset.state = flag ? "online" : "offline";
  pill.textContent = flag ? "Verbunden" : "Offline";

  if (!flag && state.dialog?.key !== "offline") {
    const backendError = err instanceof ApiError && !err.network;
    showDialog({
      key: "offline",
      tone: "error",
      spinner: true,
      title: "Backend unavailable",
      text: backendError ? `The backend reports an error: ${err.message}` : "LivingroomOS will reconnect automatically …",
      actions: [{ label: "Jetzt erneut versuchen", run: retryNow }],
      onBack: () => {}, // cannot be dismissed
    });
  } else if (flag && state.dialog?.key === "offline") {
    closeDialog();
  }
}

async function tick() {
  if (polling) return;
  polling = true;
  let delay = POLL_MS.offline;
  try {
    if (state.online) applyStatus(await api.status());
    else await loadAll();
    setOnline(true);
    delay = state.status.state === "idle" ? POLL_MS.idle : POLL_MS.active;
  } catch (err) {
    if (!(err instanceof ApiError)) console.error(err);
    setOnline(false, err);
  } finally {
    polling = false;
  }
  if (document.hidden) delay = Math.max(delay, POLL_MS.hidden);
  clearTimeout(pollTimer);
  pollTimer = setTimeout(tick, delay);
}

function retryNow() {
  clearTimeout(pollTimer);
  tick();
}

/* ------------------------------------------------------------------ Eingabe */

function onAction(action) {
  switch (action) {
    case "up":
    case "down":
    case "left":
    case "right": {
      const el = nav.current();
      if (!state.dialog && state.view === "settings" && el?.dataset.setting && (action === "left" || action === "right")) {
        return cycleSetting(el.dataset.setting, action === "right" ? 1 : -1);
      }
      return nav.move(action);
    }
    case "next":
    case "prev":
      return nav.step(action === "next" ? 1 : -1);
    case "ok":
      return nav.activate();
    case "back":
      if (state.dialog) return (state.dialog.onBack ?? closeDialog)();
      if (state.view !== "home") showView("home");
      return;
    case "home":
      if (state.dialog && state.dialog.key !== "offline") closeDialog();
      if (!state.dialog) showView("home");
  }
}

/* -------------------------------------------------------------------- Start */

function init() {
  initRemote(onAction);
  setInterval(updateClock, 10_000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) retryNow(); });
  applyUi();
  showView("home");
  tick();
}

init();
