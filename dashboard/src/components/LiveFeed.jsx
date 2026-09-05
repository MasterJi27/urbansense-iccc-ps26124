import DetectionOverlay from "./DetectionOverlay.jsx";

export default function LiveFeed({ sensors }) {
  const rows = (Array.isArray(sensors) ? sensors : [])
    .filter((s) => {
      const age = s.seen_at ? Date.now() - s.seen_at : 99999;
      return s.camera_status === "ONLINE" || s.overlay_mode || (s.last_boxes || []).length || s.person_count || age < 15000;
    })
    .sort((a, b) => (b.seen_at || 0) - (a.seen_at || 0));
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <h4 style={{ margin: "0 0 6px" }}>LIVE FIELD</h4>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 10px" }}>
        Phone overlay: road-band 640 + IoU tracker. WASM on the phone; WebGPU only if the runtime attaches. Round-trip is tens of ms, not 1 ms. Official ticket still waits for the Azure still.
      </p>
      {rows.length === 0 ? (
        <div className="empty">No live phone yet. Arm a PIN, open /field on the phone, keep AUTO on.</div>
      ) : (
        <div aria-live="polite" className="live-feed-grid">
          {rows.slice(0, 8).map((s) => {
            const boxes = s.last_boxes || [];
            const top = boxes[0];
            const backend = (s.overlay_backend || "").toUpperCase();
            return (
              <div key={s.id || s.code} className="live-feed-row">
                <div className="live-glass" aria-hidden={boxes.length === 0}>
                  <DetectionOverlay boxes={boxes} compact />
                </div>
                <div className="stat-row" style={{ margin: 0, alignItems: "flex-start" }}>
                  <span>
                    <b className="mono">{s.bus_code || s.code}</b>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {top ? `${top.klass || top.event_type} ${Math.round((top.confidence || 0) * 100)}%` : "no box this tick"}
                      {" · "}people {s.person_count || 0}
                      {" · "}{boxes.length} box
                      {s.overlay_mode ? ` · ${s.overlay_mode}` : ""}
                      {backend ? ` · ${backend}` : ""}
                      {s.infer_ms ? ` · ${Math.round(s.infer_ms)} ms` : ""}
                      {s.overlay_fps ? ` · ${Math.round(s.overlay_fps)} fps` : ""}
                    </div>
                  </span>
                  <span className={`tag ${boxes.length ? "real" : "off"}`}>{boxes.length ? "LIVE" : "IDLE"}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
