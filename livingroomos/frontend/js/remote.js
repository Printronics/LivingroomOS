/* LivingroomOS – Fernbedienung und Tastatur.

   Eigenständig: kennt weder Navigation noch Oberfläche. Übersetzt Tastendrücke in Aktionen
   und ruft handler(action, detail) auf.

   Aktionen:  up | down | left | right | ok | back | home | menu | next | prev
   (next/prev entstehen aus Tab/Shift+Tab, damit Tab nie den Browser-Fokus verschiebt)

   Schutz vor Tastenwiederholung (Halten, prellende Fernbedienungen, Doppelklicks):
   - Richtungen dürfen wiederholen, aber höchstens alle `repeatInterval` ms. Ein langsamer
     Bildaufbau staut deshalb keine Ereignisse an.
   - ok/back/home/menu lösen nie durch Halten (Auto-Repeat) aus und werden entprellt.
   - Ein Fehler im handler blockiert nie die nächsten Tasten.

   Neue Fernbedienung einbinden: zuerst herausfinden, was sie sendet (siehe onUnknownKey und
   dev/navigation-demo.html), dann remote.bind("<key oder code>", "<aktion>") aufrufen oder
   die Tabellen unten ergänzen. Andere Quellen (Gamepad, evdev über das Backend) rufen
   remote.emit("ok") auf und durchlaufen dieselbe Entprellung. */

const REPEATABLE = new Set(["up", "down", "left", "right", "next", "prev"]);

/** event.key → Aktion (zuerst geprüft). */
const BY_KEY = new Map(Object.entries({
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
  Enter: "ok", " ": "ok", Select: "ok",
  Escape: "back", Backspace: "back", BrowserBack: "back", GoBack: "back", XF86Back: "back", Exit: "back",
  Home: "home", BrowserHome: "home", GoHome: "home", XF86HomePage: "home",
  ContextMenu: "menu", Menu: "menu", XF86Menu: "menu",
}));

/** event.code → Aktion, falls event.key fehlt oder "Unidentified" ist (HID-Fernbedienungen). */
const BY_CODE = new Map(Object.entries({
  NumpadEnter: "ok", BrowserBack: "back", BrowserHome: "home", ContextMenu: "menu",
}));

/** event.keyCode → Aktion für alte oder TV-eigene Browser (Android TV, Tizen, webOS). */
const BY_KEYCODE = new Map([
  [37, "left"], [38, "up"], [39, "right"], [40, "down"],
  [13, "ok"], [27, "back"], [8, "back"],
  [4, "back"], [10009, "back"], [461, "back"],
]);

const EDITABLE = "input, textarea, select, [contenteditable]:not([contenteditable='false'])";

/**
 * @param {(action: string, detail: {key: string, repeat: boolean, source: string}) => void} handler
 * @param {object} [options]
 * @param {number} [options.repeatInterval=90]  Mindestabstand gehaltener Richtungstasten (ms)
 * @param {number} [options.pressInterval=30]   Mindestabstand frischer Richtungsdrücke (Prellen)
 * @param {number} [options.debounce=120]       Mindestabstand für ok/back/home/menu (ms)
 * @param {(event: KeyboardEvent) => void} [options.onUnknownKey]  Für unbekannte Tasten
 * @param {EventTarget} [options.target=document]
 */
export function initRemote(handler, options = {}) {
  const {
    repeatInterval = 90,
    pressInterval = 30,
    debounce = 120,
    onUnknownKey = null,
    target = document,
  } = options;

  const custom = new Map();           // eigene Zuordnungen: key oder code → Aktion
  const lastDelivered = new Map();    // Aktion → Zeitpunkt der letzten Zustellung
  const swallowOnKeyup = new Set();   // Tasten, deren keyup wir unterdrücken

  function resolve(event) {
    return (
      custom.get(event.key) ?? custom.get(event.code) ??
      BY_KEY.get(event.key) ??
      BY_CODE.get(event.code) ??
      BY_KEYCODE.get(event.keyCode) ??
      null
    );
  }

  function deliver(action, detail) {
    if (detail.repeat && !REPEATABLE.has(action)) return false;
    const now = performance.now();
    const previous = lastDelivered.get(action) ?? -Infinity;
    let gap = debounce;
    if (REPEATABLE.has(action)) gap = detail.repeat ? repeatInterval : pressInterval;
    if (now - previous < gap) return false;
    lastDelivered.set(action, now);
    try {
      const result = handler(action, detail);
      if (result && typeof result.catch === "function") result.catch((err) => console.error(err));
    } catch (err) {
      console.error(err); // ein Fehler darf die nächsten Tasten nicht blockieren
    }
    return true;
  }

  function onKeyDown(event) {
    if (event.defaultPrevented || event.isComposing) return;
    if (event.ctrlKey || event.altKey || event.metaKey) return; // Browser-Kürzel nicht stören

    let action = event.key === "Tab" ? (event.shiftKey ? "prev" : "next") : resolve(event);
    if (!action) {
      onUnknownKey?.(event);
      return;
    }
    // In Eingabefeldern gehören Pfeile, Leertaste und Rücktaste dem Feld; nur Escape zählt.
    if (event.target instanceof Element && event.target.closest(EDITABLE) && event.key !== "Escape") return;

    event.preventDefault();
    swallowOnKeyup.add(event.code || event.key);
    // Google Chrome setzt event.repeat zuverlässig; ältere TV-Browser lassen es weg.
    const repeat = typeof event.repeat === "boolean" ? event.repeat : false;
    deliver(action, { key: event.key, repeat, source: "keyboard" });
  }

  /* Der Browser aktiviert fokussierte Schaltflächen bei Leertaste erst beim Loslassen.
     Das würde zusätzlich zu unserem eigenen Klick ein zweites Mal auslösen. */
  function onKeyUp(event) {
    const id = event.code || event.key;
    if (swallowOnKeyup.delete(id)) event.preventDefault();
  }

  const onBlur = () => swallowOnKeyup.clear();

  target.addEventListener("keydown", onKeyDown, true);
  target.addEventListener("keyup", onKeyUp, true);
  window.addEventListener("blur", onBlur);

  return {
    /** Aktion von anderer Quelle auslösen (Gamepad, Backend-Ereignis …). */
    emit(action, source = "api") {
      return deliver(action, { key: "", repeat: false, source });
    },
    /** Eigene Zuordnung: id ist ein event.key oder event.code, zum Beispiel "BrowserBack". */
    bind(id, action) { custom.set(id, action); },
    unbind(id) { custom.delete(id); },
    destroy() {
      target.removeEventListener("keydown", onKeyDown, true);
      target.removeEventListener("keyup", onKeyUp, true);
      window.removeEventListener("blur", onBlur);
    },
  };
}
