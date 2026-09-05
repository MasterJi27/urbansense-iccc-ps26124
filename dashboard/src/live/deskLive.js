import { api, wsUrl } from "../api";

export function mergeLiveSensor(prev, msg) {
  if (!msg || msg.type !== "live.heartbeat") return prev;
  const id = msg.sensor_id || msg.sensor_code;
  const code = msg.sensor_code || msg.sensor_id;
  if (!id && !code) return prev;
  const rest = (Array.isArray(prev) ? prev : []).filter(
    (s) => s.id !== id && s.id !== code && s.code !== code && s.code !== id,
  );
  return [
    ...rest,
    {
      id,
      code,
      bus_code: msg.bus_code,
      latitude: msg.latitude,
      longitude: msg.longitude,
      heading: msg.heading,
      last_boxes: msg.last_boxes || [],
      person_count: msg.person_count || 0,
      overlay_mode: msg.overlay_mode,
      overlay_backend: msg.overlay_backend,
      overlay_fps: msg.overlay_fps,
      infer_ms: msg.infer_ms,
      camera_status: "ONLINE",
      processing_mode: msg.processing_mode,
      seen_at: Date.now(),
    },
  ];
}

export function mergeEventRow(prev, event, cap = 40) {
  if (!event?.id) return prev;
  return [event, ...(Array.isArray(prev) ? prev : []).filter((x) => x.id !== event.id)].slice(0, cap);
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
