/* LivingroomOS – remote control and keyboard.

   Standalone: knows nothing about navigation or the interface. Converts key presses into actions
   and calls handler(action, detail).

   Actions:  up | down | left | right | ok | back | home | menu | next | prev
   (next/prev are generated from Tab/Shift+Tab so Tab never moves browser focus)

   Protection against repeated key events (held keys, bouncing remote controls, double presses):
   - Direction keys may repeat, but no more often than every `repeatInterval` ms. A slow
     rendering frame therefore does not queue up events.
   - ok/back/home/menu are never triggered by holding a key (auto-repeat) and are debounced.
   - An error in the handler never blocks subsequent key presses.

   To add a remote control: first find out what it sends (see onUnknownKey and
   dev/navigation-demo.html), then call remote.bind("<key or code>", "<action>") or
   add entries to the tables below. Other sources (gamepad, evdev through the backend) call
   remote.emit("ok") and use the same debouncing. */

const REPEATABLE = new Set(["up", "down", "left", "right", "next", "prev"]);

/** event.key → Action (checked first). */
const BY_KEY = new Map(Object.entries({
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
  Enter: "ok", " ": "ok", Select: "ok",
  Escape: "back", Backspace: "back", BrowserBack: "back", GoBack: "back", XF86Back: "back", Exit: "back",
  Home: "home", BrowserHome: "home", GoHome: "home", XF86HomePage: "home",
  ContextMenu: "menu", Menu: "menu", XF86Menu: "menu",
}));

/** event.code → Action if event.key is missing or "Unidentified" (HID remote controls). */
const BY_CODE = new Map(Object.entries({
  NumpadEnter: "ok", BrowserBack: "back", BrowserHome: "home", ContextMenu: "menu",
}));

/** event.keyCode → Action for older or TV-specific browsers (Android TV, Tizen, webOS). */
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
 * @param {number} [options.pressInterval=30]   Minimum interval between new direction key presses (bounce filtering)
 * @param {number} [options.debounce=120]       Minimum interval for ok/back/home/menu (ms)
 * @param {(event: KeyboardEvent) => void} [options.onUnknownKey]  For unknown keys
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

  const custom = new Map();           // custom mappings: key or code -> action
  const lastDelivered = new Map();    // Action -> time of last delivery
  const swallowOnKeyup = new Set();   // keys whose keyup event is suppressed

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
      console.error(err); // an error must not block subsequent key presses
    }
    return true;
  }

  function onKeyDown(event) {
    if (event.defaultPrevented || event.isComposing) return;
    if (event.ctrlKey || event.altKey || event.metaKey) return; // do not interfere with browser shortcuts

    let action = event.key === "Tab" ? (event.shiftKey ? "prev" : "next") : resolve(event);
    if (!action) {
      onUnknownKey?.(event);
      return;
    }
    // In input fields, arrows, Space, and Backspace belong to the field; only Escape is handled.
    if (event.target instanceof Element && event.target.closest(EDITABLE) && event.key !== "Escape") return;

    event.preventDefault();
    swallowOnKeyup.add(event.code || event.key);
    // Google Chrome sets event.repeat reliably; older TV browsers may omit it.
    const repeat = typeof event.repeat === "boolean" ? event.repeat : false;
    deliver(action, { key: event.key, repeat, source: "keyboard" });
  }

  /* The browser activates focused buttons on Space keyup.
     That would trigger a second activation in addition to our own click. */
  function onKeyUp(event) {
    const id = event.code || event.key;
    if (swallowOnKeyup.delete(id)) event.preventDefault();
  }

  const onBlur = () => swallowOnKeyup.clear();

  target.addEventListener("keydown", onKeyDown, true);
  target.addEventListener("keyup", onKeyUp, true);
  window.addEventListener("blur", onBlur);

  return {
    /** Trigger an action from another source (gamepad, backend event, etc.). */
    emit(action, source = "api") {
      return deliver(action, { key: "", repeat: false, source });
    },
    /** Custom mapping: id is an event.key or event.code, for example "BrowserBack". */
    bind(id, action) { custom.set(id, action); },
    unbind(id) { custom.delete(id); },
    destroy() {
      target.removeEventListener("keydown", onKeyDown, true);
      target.removeEventListener("keyup", onKeyUp, true);
      window.removeEventListener("blur", onBlur);
    },
  };
}
