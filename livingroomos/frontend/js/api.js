/* LivingroomOS – Client für die lokale HTTP-API.
   Das Frontend sendet nur Absichten (z. B. "starte App <id>"), nie Befehle. */

const BASE = "/api/v1";
const DEFAULT_TIMEOUT_MS = 4000;

export class ApiError extends Error {
  constructor(message, { code = "unknown", status = 0, network = false, data = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;       // maschinenlesbar, z. B. "busy", "not_installed"
    this.status = status;   // HTTP-Status, 0 bei Netzwerkfehlern
    this.network = network; // true: Backend nicht erreichbar
    this.data = data;       // komplette Fehlerantwort
  }
}

async function request(method, path, { body, timeout = DEFAULT_TIMEOUT_MS } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  const headers = { Accept: "application/json", "X-LivingroomOS": "1" }; // Pflicht bei Schreibzugriffen
  const init = { method, headers, signal: ctrl.signal, cache: "no-store" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  try {
    let res;
    try {
      res = await fetch(BASE + path, init);
    } catch (err) {
      const timedOut = err?.name === "AbortError";
      throw new ApiError(timedOut ? "Das Backend antwortet nicht." : "Das Backend ist nicht erreichbar.", {
        code: timedOut ? "timeout" : "unreachable",
        network: true,
      });
    }

    let data = null;
    try {
      data = await res.json();
    } catch {
      /* Antwort ohne JSON (z. B. Fehlerseite eines Proxys) */
    }

    if (!res.ok) {
      const e = data?.error;
      throw new ApiError(e?.message ?? `Unerwarteter Fehler (HTTP ${res.status}).`, {
        code: e?.code ?? `http_${res.status}`,
        status: res.status,
        data,
        network: res.status === 502 || res.status === 503 || res.status === 504,
      });
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health: () => request("GET", "/health"),
  apps: () => request("GET", "/apps"),
  status: () => request("GET", "/apps/status"),
  launch: (id) => request("POST", `/apps/${encodeURIComponent(id)}/launch`),
  stop: () => request("POST", "/apps/stop", { timeout: 10000 }), // Backend wartet bis zu 5 s auf SIGTERM
  settings: () => request("GET", "/settings"),
  saveSettings: (patch) => request("PATCH", "/settings", { body: patch }),
  system: () => request("GET", "/system/status"),
  power: (action) => request("POST", `/system/power/${action}`, { timeout: 5000 }),
  power: (action) => request("POST", `/system/power/${action}`, { timeout: 5000 }),
};
