/* LivingroomOS – Fokusnavigation für Fernseher.

   Eigenständig: kennt weder Fernbedienung noch Anwendung. Verwaltet, welches Element den
   Fokus hat, und bewegt ihn in Pfeilrichtung.

   Markup
     data-focusable          Element ist anwählbar (Schaltfläche, Kachel, Zeile …)
     data-key="id"           stabile Kennung; der Fokus findet das Element nach einem
                             Neuaufbau der Liste wieder
     data-nav-default        bevorzugtes Startelement einer Ansicht
     data-nav-up|down|left|right="id | #selektor | none"
                             feste Zielvorgabe statt Geometrie ("none" sperrt die Richtung)
     data-repeatable         Enter darf dieses Element schnell hintereinander auslösen
     data-busy               Element ist beschäftigt, Enter wird ignoriert

   Ein "Scope" (Ansicht oder Dialog) begrenzt, welche Elemente erreichbar sind.

   Robustheit gegen schnelle und wiederholte Tasten
   - Bewegung wird synchron berechnet; Scrollen springt sofort (kein "smooth"), damit die
     nächste Taste immer auf aktuellen Positionen aufbaut.
   - Verschwindet das fokussierte Element (Neuaufbau, Fensterwechsel, Mausklick ins Leere),
     holt sich die Navigation den Fokus selbst zurück: er ist nie "weg".
   - Öffnet sich ein neuer Bereich (z. B. ein Dialog), ignoriert Enter kurz, damit ein
     Doppelklick auf die Taste nicht sofort die erste Dialogschaltfläche bestätigt. Kehrt der
     Nutzer in einen Bereich zurück, in dem er schon gewählt hatte, gilt die Sperre nicht.
   - Dasselbe Element löst nicht zweimal innerhalb von activateCooldown aus. */

const DEFAULT_FOCUSABLE = "[data-focusable]:not([disabled]):not([aria-disabled='true'])";
const NATIVELY_FOCUSABLE = "a[href], button, input, select, textarea, [tabindex]";
const OPPOSITE_AXIS_WEIGHT = 4;   // Abweichung zur Seite zählt vierfach, wenn sich die Elemente nicht überlappen
const EDGE_FEEDBACK_MS = 260;

function isShown(el) {
  if (el.closest("[inert]")) return false;
  if (typeof el.checkVisibility === "function") return el.checkVisibility({ visibilityProperty: true });
  return el.getClientRects().length > 0;
}

/** Bewertung eines Kandidaten in Richtung `dir`; kleiner ist besser, Infinity = nicht erreichbar. */
function score(origin, candidate, dir) {
  const horizontal = dir === "left" || dir === "right";
  const sign = dir === "right" || dir === "down" ? 1 : -1;

  const oMain = horizontal ? origin.left + origin.width / 2 : origin.top + origin.height / 2;
  const cMain = horizontal ? candidate.left + candidate.width / 2 : candidate.top + candidate.height / 2;
  const main = (cMain - oMain) * sign;
  if (main <= 2) return Infinity; // nicht in Richtung (oder auf gleicher Höhe)

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
  #memory = new WeakMap();      // Scope → zuletzt fokussiertes Element (Schlüssel und Position)
  #opts;
  #settleUntil = 0;
  #last = { el: null, at: 0 };
  #observer;
  #ensureQueued = false;
  #edgeTimer = 0;
  #edgeEl = null;

  /**
   * @param {object} [options]
   * @param {string} [options.focusable]        Selektor anwählbarer Elemente
   * @param {number} [options.activateCooldown=400]  ms, in denen dasselbe Element nicht erneut auslöst
   * @param {number} [options.settleMs=350]     ms Enter-Sperre nach einem Scope-Wechsel
   * @param {(el: HTMLElement) => void} [options.onFocus]
   * @param {(dir: string, el: HTMLElement) => void} [options.onEdge]  Rand erreicht
   */
  constructor(options = {}) {
    this.#opts = { focusable: DEFAULT_FOCUSABLE, activateCooldown: 400, settleMs: 350, onFocus: null, onEdge: null, ...options };

    // Auch Mausklicks oder programmatischer Fokus werden gemerkt.
    document.addEventListener("focusin", (event) => {
      if (this.#scope?.contains(event.target)) this.#remember(event.target);
    });
    // Fokus verloren (Klick ins Leere, Element entfernt, Fenster zurück von einer externen App).
    document.addEventListener("focusout", (event) => { if (!event.relatedTarget) this.#queueEnsure(); });
    window.addEventListener("focus", () => this.#queueEnsure());
    document.addEventListener("visibilitychange", () => { if (!document.hidden) this.#queueEnsure(); });
    this.#observer = new MutationObserver(() => this.#queueEnsure());
  }

  get scope() { return this.#scope; }

  /** Setzt den aktiven Bereich und fokussiert das zuletzt gewählte Element. */
  setScope(root, { reset = false } = {}) {
    // "Frisch": der Fokus landet auf einer Vorgabe, nicht auf einer früheren Wahl des Nutzers.
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

  /** Alle derzeit sichtbaren, anwählbaren Elemente des Scopes in DOM-Reihenfolge. */
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
    // behavior "instant": kein Animieren, sonst rechnet die nächste Taste mit alten Positionen.
    el.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
    this.#remember(el);
    this.#opts.onFocus?.(el);
    return el;
  }

  /** Pfeiltaste: bewegt den Fokus; am Rand bleibt er stehen. Gibt das fokussierte Element zurück. */
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

  /** Enter: löst die Aktion des fokussierten Elements aus. Gibt zurück, ob etwas ausgelöst wurde. */
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
    } catch { /* ungültiger Selektor: Geometrie verwenden */ }
    return target && this.items().includes(target) ? target : null;
  }

  #edge(el, dir) {
    // Kurzes Wackeln zeigt: hier geht es nicht weiter. Gehaltene Taste startet es nicht neu.
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

  /** Sorgt (gebündelt pro Frame) dafür, dass immer ein Element im Scope den Fokus hat. */
  #queueEnsure() {
    if (this.#ensureQueued) return;
    this.#ensureQueued = true;
    requestAnimationFrame(() => {
      this.#ensureQueued = false;
      if (this.#scope?.isConnected && !this.current()) this.restoreFocus();
    });
  }
}
