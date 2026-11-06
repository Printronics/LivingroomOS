import { Navigator } from "../js/navigation.js";
import { initRemote } from "../js/remote.js";

const $ = (id) => document.getElementById(id);
const nav = new Navigator();
let count = 0;

function h(tag, cls, text, attrs = {}) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text != null) el.textContent = text;
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

function bump(label) { $("count").textContent = `${++count} Aktionen · ${label}`; }

// Ungleich breite Kacheln; die letzte Reihe ist kürzer.
const layout = [["a", ""], ["b", "w2"], ["c", ""], ["d", ""], ["e", "w3"], ["f", "w3"], ["g", ""], ["h", ""], ["i", "w2"]];
$("grid").replaceChildren(...layout.map(([id, cls]) => {
  const li = h("li", cls);
  const b = h("button", "tile", null, { type: "button", "data-focusable": "", "data-key": id, id: `t-${id}` });
  b.append(h("span", "tile__title", `Kachel ${id.toUpperCase()}`));
  b.addEventListener("click", () => bump(`Kachel ${id}`));
  li.append(b);
  return li;
}));

const rows = [["Zeile 1", "r1"], ["Zeile 2 (öffnet Dialog)", "r2"], ["Zeile 3", "r3"]];
$("list").replaceChildren(...rows.map(([label, id]) => {
  const li = h("li");
  const b = h("button", "row", null, { type: "button", "data-focusable": "", "data-key": id, id: `row-${id}` });
  b.append(h("span", null, label));
  b.addEventListener("click", () => (id === "r2" ? openDialog() : bump(label)));
  li.append(b);
  return li;
}));

let dialogOpen = false;
function openDialog() {
  dialogOpen = true;
  $("overlay").hidden = false;
  document.querySelector(".shell").inert = true;
  const close = h("button", "btn", "Schließen", { type: "button", "data-focusable": "", "data-key": "close", id: "dlg-close" });
  close.addEventListener("click", closeDialog);
  $("dlg-actions").replaceChildren(close);
  nav.setScope($("dlg-actions"), { reset: true });
}
function closeDialog() {
  dialogOpen = false;
  $("overlay").hidden = true;
  document.querySelector(".shell").inert = false;
  nav.setScope($("view"));
}

const remote = initRemote((action, detail) => {
  $("k-action").textContent = action + (detail.repeat ? " (hält)" : "");
  switch (action) {
    case "up": case "down": case "left": case "right": return nav.move(action);
    case "next": return nav.step(1);
    case "prev": return nav.step(-1);
    case "ok": return nav.activate();
    case "back": return dialogOpen ? closeDialog() : bump("zurück");
    case "home": return nav.setScope($("view"), { reset: true });
  }
}, { onUnknownKey: (e) => { $("k-unknown").textContent = `key="${e.key}" code="${e.code}" keyCode=${e.keyCode}`; } });

document.addEventListener("keydown", (e) => {
  $("k-key").textContent = e.key === " " ? "␣" : e.key;
  $("k-code").textContent = e.code || "–";
  $("k-keycode").textContent = e.keyCode;
}, true);

window.__demo = { nav, remote }; // für Tests im Browser
nav.setScope($("view"));
