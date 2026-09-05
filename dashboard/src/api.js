const KEY = "urbansense_token";
/** Dev: Vite proxy. Production: same origin unless VITE_API_URL is set. */
export const API = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "/api" : "");

export function wsUrl(path, token) {
  if (import.meta.env.VITE_WS_URL) return `${import.meta.env.VITE_WS_URL}${path}?token=${token}`;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  if (import.meta.env.DEV) {
    return `${proto}//${window.location.host}${path}?token=${token}`;
  }
  if (import.meta.env.VITE_API_URL) {
    const api = new URL(import.meta.env.VITE_API_URL, window.location.origin);
    const wsProto = api.protocol === "https:" ? "wss:" : "ws:";
    return `${wsProto}//${api.host}${path}?token=${token}`;
  }
  return `${proto}//${window.location.host}${path}?token=${token}`;
}

export function getToken() {
  return localStorage.getItem(KEY);
}
export function setSession(data) {
  localStorage.setItem(KEY, data.access_token);
  localStorage.setItem("urbansense_role", data.role);
  localStorage.setItem("urbansense_name", data.full_name);
  localStorage.setItem("urbansense_scope", data.scope || "iccc");
}
export function getScope() {
  return localStorage.getItem("urbansense_scope") || "iccc";
}
export function clearSession() {
  localStorage.removeItem(KEY);
  localStorage.removeItem("urbansense_role");
  localStorage.removeItem("urbansense_name");
  localStorage.removeItem("urbansense_scope");
}

export async function api(path, opts = {}) {
  const headers = { Accept: "application/json", ...(opts.headers || {}) };
  if (!(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(`${API}${path}`, { cache: "no-store", ...opts, headers });
  } catch {
    throw new Error("Cannot reach API. Local: keep FastAPI on :8000 and use Vite. Azure: refresh — the API is the same host as this page.");
  }
  if (res.status === 401) {
    clearSession();
    const onField = window.location.pathname.startsWith("/field") || window.location.pathname.startsWith("/cctv") || window.location.pathname.startsWith("/report");
    const joining = path.includes("/auth/login") || path.includes("/auth/field-join") || path.includes("/citizen/");
    if (!joining && !onField) {
      const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
      window.location.href = `/login?next=${next}`;
    }
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = Array.isArray(err.detail) ? err.detail.map((d) => d.msg || JSON.stringify(d)).join("; ") : err.detail;
    throw new Error(detail || JSON.stringify(err));
  }
  return res.json();
}
