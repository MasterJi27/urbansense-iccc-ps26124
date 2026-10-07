const KEY = "urbansense_field_outbox";
const MAX = 5;

function read() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

function write(rows) {
  const kept = rows.slice(0, MAX);
  localStorage.setItem(KEY, JSON.stringify(kept));
  return kept;
}

export function listOutbox() {
  return read();
}

export function rememberTicket(row) {
  const next = [{ id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, at: new Date().toISOString(), ...row }, ...read().filter((r) => r.id !== row.id)];
  return write(next);
}

export async function queueStill(blob, meta) {
  const dataUrl = await blobToDataUrl(blob);
  return rememberTicket({ status: "queued", code: "", note: meta.note || "Waiting for network", dataUrl, meta });
}

export async function flushOutbox(postDataUrl) {
  const pending = read().filter((row) => row.status === "queued" && row.dataUrl);
  let rows = read();
  for (const row of pending) {
    try {
      const blob = await (await fetch(row.dataUrl)).blob();
      const ingested = await postDataUrl(blob, row.meta || {});
      const code = ingested?.event?.public_code || "";
      rows = rows.map((item) => (item.id === row.id ? { ...item, status: "sent", code, dataUrl: "", note: code } : item));
      write(rows);
    } catch (err) {
      rows = rows.map((item) => (item.id === row.id ? { ...item, status: "failed", note: String(err.message || err) } : item));
      write(rows);
    }
  }
  return read();
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Could not store the still"));
    reader.readAsDataURL(blob);
  });
}
