import { api, wsUrl } from "../api";

export function phoneSlotFromCode(code) {
  const m = String(code || "").match(/-P(\d+)\b/i);
  return m ? Number(m[1]) : null;
}

export function ageLabel(seenAt) {
  if (!seenAt) return "never";
  const t = typeof seenAt === "number" ? seenAt : Date.parse(seenAt);
  if (!Number.isFinite(t)) return "never";
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 0) return "just now";
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export function mergeLiveSensor(prev, msg) {
  if (!msg || msg.type !== "live.heartbeat") return prev;
  const id = msg.sensor_id || msg.sensor_code;
  const code = msg.sensor_code || msg.sensor_id;
  if (!id && !code) return prev;
  const list = Array.isArray(prev) ? prev : [];
  const existing = list.find((s) => s.id === id || s.id === code || s.code === code || s.code === id) || {};
  const rest = list.filter((s) => s.id !== id && s.id !== code && s.code !== code && s.code !== id);
  const hasGps = msg.latitude != null && msg.longitude != null;
  const gpsOk = msg.gps_ok != null ? Boolean(msg.gps_ok) : hasGps;
  return [
    ...rest,
    {
      ...existing,
      id,
      code,
      bus_code: msg.bus_code ?? existing.bus_code,
      latitude: hasGps ? msg.latitude : existing.latitude,
      longitude: hasGps ? msg.longitude : existing.longitude,
      heading: msg.heading ?? existing.heading,
      gps_accuracy: msg.gps_accuracy ?? existing.gps_accuracy,
      gps_ok: gpsOk,
      imu_mag: msg.imu_mag ?? existing.imu_mag,
      gyro_z: msg.gyro_z ?? existing.gyro_z,
      last_boxes: Array.isArray(msg.last_boxes) ? msg.last_boxes : (existing.last_boxes || []),
      person_count: msg.person_count != null ? msg.person_count : (existing.person_count || 0),
      overlay_mode: msg.overlay_mode || existing.overlay_mode,
      overlay_backend: msg.overlay_backend || existing.overlay_backend,
      overlay_fps: msg.overlay_fps ?? existing.overlay_fps,
      infer_ms: msg.infer_ms ?? existing.infer_ms,
      camera_status: msg.camera_status || "ONLINE",
      processing_mode: msg.processing_mode || existing.processing_mode,
      gps_status: gpsOk ? "ONLINE" : (msg.gps_status || existing.gps_status || "DEGRADED"),
      seen_at: Date.now(),
    },
  ];
}

export function mergeSensorPoll(prev, rows) {
  if (!Array.isArray(rows)) return prev;
  const live = Array.isArray(prev) ? prev : [];
  const byCode = new Map(live.map((s) => [s.code || s.id, s]));
  for (const row of rows) {
    const key = row.code || row.id;
    if (!key) continue;
    const had = byCode.get(key) || {};
    const pollBoxes = Array.isArray(row.last_boxes) ? row.last_boxes : [];
    byCode.set(key, {
      ...had,
      ...row,
      last_boxes: pollBoxes.length ? pollBoxes : (had.last_boxes || []),
      overlay_mode: row.overlay_mode || had.overlay_mode,
      overlay_backend: row.overlay_backend || had.overlay_backend,
      overlay_fps: row.overlay_fps ?? had.overlay_fps,
      infer_ms: row.infer_ms ?? had.infer_ms,
      imu_mag: row.imu_mag ?? had.imu_mag,
      gyro_z: row.gyro_z ?? had.gyro_z,
      gps_accuracy: row.gps_accuracy ?? had.gps_accuracy,
      gps_ok: row.gps_ok ?? had.gps_ok,
      seen_at: had.seen_at || (row.last_heartbeat_at ? Date.parse(row.last_heartbeat_at) : 0),
    });
  }
  return [...byCode.values()];
}

export function isSeedTicket(event) {
  if (!event) return false;
  const extra = event.extra && typeof event.extra === "object" ? event.extra : {};
  return Boolean(event.simulated) || extra.payload_kind === "SEED";
}

export function dropEvent(prev, eventId) {
  if (!eventId) return prev;
  return (Array.isArray(prev) ? prev : []).filter((e) => e.id !== eventId && e.public_code !== eventId);
}

export function applyEventMessage(prev, msg, cap = 40, hideSeed = true) {
  if (!msg) return prev;
  if (msg.type === "events.cleared") return [];
  if (msg.type === "event.deleted") {
    return dropEvent(prev, msg.event_id || msg.event?.id);
  }
  if (!msg.event) return prev;
  if (hideSeed && isSeedTicket(msg.event)) return prev;
  return mergeEventRow(prev, msg.event, cap);
}

export function mergeEventRow(prev, event, cap = 40) {
  if (!event?.id) return prev;
  return [event, ...(Array.isArray(prev) ? prev : []).filter((x) => x.id !== event.id)].slice(0, cap);
}

export function mergeEventPoll(prev, rows, cap = 40) {
  if (!Array.isArray(rows)) return prev;
  const byId = new Map();
  for (const event of rows) {
    if (event?.id) byId.set(event.id, event);
  }
  return [...byId.values()].slice(0, cap);
}

export function openAuthedSocket(path, token, onMessage) {
  let sock;
  let ping = 0;
  let retry = 0;
  let dead = false;

  function connect() {
    if (dead || !token) return;
    sock = new WebSocket(wsUrl(path, token));
    sock.onopen = () => {
      retry = 0;
      if (ping) window.clearInterval(ping);
      ping = window.setInterval(() => {
        if (sock && sock.readyState === 1) sock.send("ping");
      }, 12000);
    };
    sock.onmessage = (ev) => {
      if (typeof onMessage === "function") onMessage(ev);
    };
    sock.onclose = () => {
      if (ping) window.clearInterval(ping);
      ping = 0;
      if (dead) return;
      retry = Math.min(retry + 1, 6);
      window.setTimeout(connect, 400 * retry);
    };
  }

  connect();
  return () => {
    dead = true;
    if (ping) window.clearInterval(ping);
    if (sock) sock.close();
  };
}

export function pollJson(path, onData, ms) {
  let dead = false;
  const beat = () => {
    if (dead) return;
    api(path).then((data) => {
      if (!dead) onData(data);
    }).catch(() => {});
  };
  beat();
  const id = window.setInterval(beat, ms);
  return () => {
    dead = true;
    window.clearInterval(id);
  };
}
