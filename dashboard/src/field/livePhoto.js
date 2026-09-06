function pickRecorderMime() {
  if (typeof MediaRecorder === "undefined") return "";
  const types = ["video/webm;codecs=vp8", "video/webm", "video/mp4"];
  return types.find((t) => MediaRecorder.isTypeSupported(t)) || "";
}

export function startLiveBuffer(getStream, windowMs = 2200) {
  let last = null;
  let rec = null;
  let timer = 0;
  let dead = false;
  const mime = pickRecorderMime();
  const span = Math.max(800, Number(windowMs) || 2200);

  function cycle() {
    if (dead) return;
    const stream = getStream();
    if (!stream || !mime) return;
    const chunks = [];
    try {
      rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 500000 });
    } catch {
      return;
    }
    rec.ondataavailable = (ev) => {
      if (ev.data && ev.data.size) chunks.push(ev.data);
    };
    rec.onstop = () => {
      if (chunks.length) last = new Blob(chunks, { type: mime.split(";")[0] });
      if (!dead) cycle();
    };
    rec.start();
    timer = window.setTimeout(() => {
      try {
        if (rec && rec.state === "recording") rec.stop();
      } catch {
        if (!dead) cycle();
      }
    }, span);
  }

  cycle();
  return {
    take() {
      return last;
    },
    extension() {
      return mime.includes("mp4") ? "mp4" : "webm";
    },
    stop() {
      dead = true;
      window.clearTimeout(timer);
      try {
        if (rec && rec.state === "recording") rec.stop();
      } catch {
        /* ignore */
      }
    },
  };
}

export function vpnHint(lat, lng) {
  if (lat == null || lng == null) return null;
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  const india = lat >= 6 && lat <= 37 && lng >= 68 && lng <= 98;
  const indiaTz = tz === "Asia/Kolkata" || tz === "Asia/Calcutta";
  if (india && !indiaTz) return "GPS is India, clock is not IST — VPN or mock location possible";
  if (!india && indiaTz) return "Clock is IST, GPS is not India — VPN or mock location possible";
  return null;
}

export function readNetwork() {
  const nav = typeof navigator !== "undefined" ? navigator : null;
  const conn = nav?.connection || nav?.mozConnection || nav?.webkitConnection;
  if (!conn) return { type: "CELL", label: "NET ?", downlink: null, rtt: null };
  const raw = String(conn.effectiveType || conn.type || "CELL").toUpperCase();
  const type = raw.includes("WIFI") || raw.includes("WLAN") ? "WIFI" : raw;
  return {
    type,
    label: type,
    downlink: Number.isFinite(conn.downlink) ? conn.downlink : null,
    rtt: Number.isFinite(conn.rtt) ? conn.rtt : null,
  };
}
