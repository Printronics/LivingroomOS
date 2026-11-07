/* LivingroomOS – focus navigation for TVs.

   Standalone: knows nothing about the remote control or the app. Manages which element has
   focus and moves it in the direction of the arrow key.

   Markup
     data-focusable          Element can receive focus (button, tile, row, etc.)
     data-key="id"           stabile Kennung; der Fokus findet das Element nach einem
                             Neuaufbau der Liste wieder
     data-nav-default        bevorzugtes Startelement einer Ansicht
     data-nav-up|down|left|right="id | #selektor | none"
                             feste Zielvorgabe statt Geometrie ("none" sperrt die Richtung)
     data-repeatable         Enter may activate this element repeatedly in quick succession
     data-busy               Element is busy; Enter is ignored

   A "scope" (view or dialog) limits which elements can be reached.

   Handling rapid and repeated key presses
   - Movement is calculated synchronously; scrolling is immediate (not "smooth") so that the
     next key press always uses the current positions.
   - Verschwindet das fokussierte Element (Neuaufbau, Fensterwechsel, Mausklick ins Leere),
     navigation restores focus itself: focus is never "lost".
   - When a new area opens (for example, a dialog), Enter is briefly ignored so that
     a double press does not immediately activate the first dialog button. When the
     user returns to an area where they already made a selection, the lock does not apply.
   - The same element cannot be activated twice within activateCooldown. */

const DEFAULT_FOCUSABLE = "[data-focusable]:not([disabled]):not([aria-disabled='true'])";
const NATIVELY_FOCUSABLE = "a[href], button, input, select, textarea, [tabindex]";
const OPPOSITE_AXIS_WEIGHT = 4;   // Sideways deviation counts four times as much when the elements do not overlap
const EDGE_FEEDBACK_MS = 260;

function isShown(el) {
  if (el.closest("[inert]")) return false;
  if (typeof el.checkVisibility === "function") return el.checkVisibility({ visibilityProperty: true });
  return el.getClientRects().length > 0;
}

/** Scores a candidate in direction `dir`; lower is better, Infinity means unreachable. */
function score(origin, candidate, dir) {
  const horizontal = dir === "left" || dir === "right";
  const sign = dir === "right" || dir === "down" ? 1 : -1;

  const oMain = horizontal ? origin.left + origin.width / 2 : origin.top + origin.height / 2;
  const cMain = horizontal ? candidate.left + candidate.width / 2 : candidate.top + candidate.height / 2;
  const main = (cMain - oMain) * sign;
  if (main <= 2) return Infinity; // not in the requested direction (or at the same position)

  const oCross = horizontal ? origin.top + origin.height / 2 : origin.left + origin.width / 2;
  const cCross = horizontal ? candidate.top + candidate.height / 2 : candidate.left + candidate.width / 2;
  const cross = Math.abs(cCross - oCross);

  const oStart = horizontal ? origin.top : origin.left;
  const oEnd = horizontal ? origin.bottom : origin.right;
  const cStart = horizontal ? candidate.top : candidate.left;
  const cEnd = horizontal ? candidate.bottom : candidate.right;
  const overlaps = Math.min(oEnd, cEnd) - Math.max(oStart, cStart) > 0;

  return main + cross * (overlaps ? 1 : OPPOSITE_AXIS_WEIGHT);
}

export class Navigator {
  #scope = null;
  #memory = new WeakMap();      // Scope -> last focused element (key and position)
  #opts;
  #settleUntil = 0;
  #last = { el: null, at: 0 };
  #observer;
  #ensureQueued = false;
  #edgeTimer = 0;
  #edgeEl = null;

  /**
   * @param {object} [options]
   * @param {string} [options.focusable]        Selector for focusable elements
   * @param {number} [options.activateCooldown=400]  ms during which the same element cannot be activated again
   * @param {number} [options.settleMs=350]     ms Enter-Sperre nach einem Scope-Wechsel
   * @param {(el: HTMLElement) => void} [options.onFocus]
   * @param {(dir: string, el: HTMLElement) => void} [options.onEdge]  Rand erreicht
   */
  constructor(options = {}) {
    this.#opts = { focusable: DEFAULT_FOCUSABLE, activateCooldown: 400, settleMs: 350, onFocus: null, onEdge: null, ...options };

    // Mouse clicks and programmatic focus are remembered too.
    document.addEventListener("focusin", (event) => {
      if (this.#scope?.contains(event.target)) this.#remember(event.target);
    });
    // Focus was lost (click on empty space, element removed, window returned from an external app).
    document.addEventListener("focusout", (event) => { if (!event.relatedTarget) this.#queueEnsure(); });
    window.addEventListener("focus", () => this.#queueEnsure());
    document.addEventListener("visibilitychange", () => { if (!document.hidden) this.#queueEnsure(); });
    this.#observer = new MutationObserver(() => this.#queueEnsure());
  }

  get scope() { return this.#scope; }

  /** Sets the active area and focuses the last selected element. */
  setScope(root, { reset = false } = {}) {
    // "Fresh": focus moves to a default element, not to the user's previous selection.
    const fresh = reset || (root !== null && !this.#memory.has(root));
    this.#scope = root;
    this.#observer.disconnect();
    if (root) {
      this.#observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden", "disabled", "inert", "aria-disabled"] });
    }
    if (reset && root) this.#memory.delete(root);
    if (fresh) this.#settleUntil = performance.now() + this.#opts.settleMs;
    return this.restoreFocus();
  }

  /** All currently visible, focusable elements in the scope, in DOM order. */
  items() {
    if (!this.#scope) return [];
    return [...this.#scope.querySelectorAll(this.#opts.focusable)].filter((el) => {
      if (!isShown(el)) return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });
  }

  current() {
    const el = document.activeElement;
    if (!el || !el.isConnected || !this.#scope?.contains(el)) return null;
    return el.matches(this.#opts.focusable) && isShown(el) ? el : null;
  }

  restoreFocus() {
    const items = this.items();
    if (!items.length) return null;
    const memo = this.#memory.get(this.#scope);
    const target =
      (memo?.key && items.find((el) => el.dataset.key === memo.key)) ||
      (memo && items[Math.min(memo.index, items.length - 1)]) ||
      items.find((el) => el.hasAttribute("data-nav-default")) ||
      items[0];
    return this.focus(target);
  }

  focus(el) {
    if (!el.matches(NATIVELY_FOCUSABLE)) el.tabIndex = -1; // z. B. <div data-focusable>
    el.focus({ preventScroll: true });
    // behavior "instant": no animation, so the next key press does not use stale positions.
    el.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
    this.#remember(el);
    this.#opts.onFocus?.(el);
    return el;
  }

  /** Arrow key: moves focus; focus stays in place at an edge. Returns the focused element. */
  move(direction) {
    const from = this.current();
    if (!from) return this.restoreFocus(); // Fokus war verloren: erst wiederherstellen, dann bewegen

    const forced = this.#forcedTarget(from, direction);
    if (forced === "blocked") return this.#edge(from, direction);
    if (forced) return this.focus(forced);

    const origin = from.getBoundingClientRect();
    let best = null;
    let bestScore = Infinity;
    for (const el of this.items()) {
      if (el === from) continue;
      const s = score(origin, el.getBoundingClientRect(), direction);
      if (s < bestScore) { best = el; bestScore = s; }
    }
    return best ? this.focus(best) : this.#edge(from, direction);
  }

  /** Tab/Shift+Tab: der Reihe nach, ohne Umbruch. */
  step(delta) {
    const from = this.current();
    if (!from) return this.restoreFocus();
    const items = this.items();
    const next = items[items.indexOf(from) + delta];
    return next ? this.focus(next) : this.#edge(from, delta > 0 ? "down" : "up");
  }

  /** Enter: activates the focused element. Returns whether an action was triggered. */
  activate() {
    const el = this.current();
    if (!el) { this.restoreFocus(); return false; }
    const now = performance.now();
    if (now < this.#settleUntil) return false; // Scope eben gewechselt: Doppelklick abfangen
    if (el.hasAttribute("data-busy") || el.getAttribute("aria-busy") === "true") return false;
    if (!el.hasAttribute("data-repeatable") && this.#last.el === el && now - this.#last.at < this.#opts.activateCooldown) return false;
    this.#last = { el, at: now };
    el.click();
    return true;
  }

  /* ---------------------------------------------------------------- intern */

  #forcedTarget(from, dir) {
    const spec = from.getAttribute(`data-nav-${dir}`);
    if (!spec) return null;
    if (spec === "none") return "blocked";
    let target = null;
    try {
      target = spec.startsWith("#")
        ? document.querySelector(spec)
        : this.#scope.querySelector(`[data-key="${CSS.escape(spec)}"]`);
    } catch { /* invalid selector: use geometry */ }
    return target && this.items().includes(target) ? target : null;
  }

  #edge(el, dir) {
    // A brief shake indicates that movement cannot continue. Holding the key does not restart it.
    if (this.#edgeEl && this.#edgeEl !== el) delete this.#edgeEl.dataset.edge;
    if (el.dataset.edge !== dir) el.dataset.edge = dir;
    this.#edgeEl = el;
    clearTimeout(this.#edgeTimer);
    this.#edgeTimer = setTimeout(() => { delete el.dataset.edge; this.#edgeEl = null; }, EDGE_FEEDBACK_MS);
    this.#opts.onEdge?.(dir, el);
    return el;
  }

  #remember(el) {
    if (!this.#scope) return;
    this.#memory.set(this.#scope, { key: el.dataset.key ?? null, index: this.items().indexOf(el) });
  }

  /** Ensures (once per frame) that an element in the scope always has focus. */
  #queueEnsure() {
    if (this.#ensureQueued) return;
    this.#ensureQueued = true;
    requestAnimationFrame(() => {
      this.#ensureQueued = false;
      if (this.#scope?.isConnected && !this.current()) this.restoreFocus();
    });
  }
}
