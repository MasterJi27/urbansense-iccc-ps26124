import { useEffect, useState } from "react";
import { ageLabel, phoneSlotFromCode } from "../live/deskLive.js";

const IMU_CAP = 24;

export function useImuHistory(sensors, cap = IMU_CAP) {
  const [hist, setHist] = useState({});
  useEffect(() => {
    setHist((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const s of (Array.isArray(sensors) ? sensors : [])) {
        const key = s.code || s.id;
        if (key == null || s.imu_mag == null) continue;
        const mag = Number(s.imu_mag);
        if (!Number.isFinite(mag)) continue;
        const list = next[key] || [];
        if (list[list.length - 1] === mag) continue;
        next[key] = [...list, mag].slice(-cap);
        changed = true;
      }
      return changed ? next : prev;
    });
  }, [sensors, cap]);
  return hist;
}

export function ImuSpark({ samples }) {
  const pts = Array.isArray(samples) ? samples.filter((n) => Number.isFinite(n)) : [];
  if (pts.length < 2) {
    return <span className="imu-spark is-empty" title="No IMU yet">—</span>;
  }
  const w = 72;
  const h = 22;
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const d = pts.map((v, i) => {
    const x = (i / (pts.length - 1)) * w;
    const y = h - 2 - ((v - min) / span) * (h - 4);
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg className="imu-spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-label={`IMU ${pts[pts.length - 1].toFixed(1)}`} title={`imu_mag ${pts[pts.length - 1].toFixed(1)}`}>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function gpsText(s) {
  if (s.latitude == null || s.longitude == null) return "no fix";
  const acc = s.gps_accuracy != null ? ` ±${Number(s.gps_accuracy).toFixed(0)} m` : "";
  return `${Number(s.latitude).toFixed(5)}, ${Number(s.longitude).toFixed(5)}${acc}`;
}

export default function LiveFeed({ sensors }) {
  const rows = (Array.isArray(sensors) ? sensors : [])
    .filter((s) => {
      const age = s.seen_at ? Date.now() - s.seen_at : 99999;
      return s.camera_status === "ONLINE" || s.overlay_mode || (s.last_boxes || []).length || s.person_count || age < 15000;
    })
    .sort((a, b) => (b.seen_at || 0) - (a.seen_at || 0));
  const imuHist = useImuHistory(rows);

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <h4 style={{ margin: "0 0 6px" }}>LIVE FIELD</h4>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 10px" }}>
        Boxes on the phone overlay — local, tens–hundreds of ms. Official ticket is the Azure still. Not 1 ms Azure.
      </p>
      {rows.length === 0 ? (
        <div className="empty">No live phone yet. Pick a bus, arm a PIN, open /field, allow location, keep AUTO on.</div>
      ) : (
        <div aria-live="polite" className="live-roster">
          {rows.slice(0, 12).map((s) => {
            const code = s.code || s.id;
            const slot = phoneSlotFromCode(code);
            const boxes = (s.last_boxes || []).length;
            const gpsOk = s.gps_ok != null ? Boolean(s.gps_ok) : (s.latitude != null && s.longitude != null);
            return (
              <div key={code} className="live-roster-card">
                <div className="live-roster-head">
                  <span>
                    <b className="mono">{s.bus_code || code}</b>
                    <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>{code}</span>
                  </span>
                  <span className={`tag ${boxes ? "real" : "off"}`}>{boxes ? `${boxes} box` : "IDLE"}</span>
                </div>
                <div className="live-roster-meta">
                  <div><span className="muted">Slot</span> <b>P{slot || "—"}</b></div>
                  <div><span className="muted">People</span> <b className="table-num">{s.person_count || 0}</b></div>
                  <div><span className="muted">infer</span> <b className="table-num">{s.infer_ms ? `${Math.round(s.infer_ms)} ms` : "—"}</b></div>
                  <div><span className="muted">Age</span> <b className="table-num">{ageLabel(s.seen_at)}</b></div>
                  <div>
                    <span className={`gps-chip ${gpsOk ? "is-ok" : "is-bad"}`}>{gpsOk ? "GPS OK" : "GPS DEGRADED"}</span>
                  </div>
                  <div className="live-roster-imu">
                    <span className="muted">IMU</span>
                    <ImuSpark samples={imuHist[code]} />
                    {s.imu_mag != null ? <b className="table-num">{Number(s.imu_mag).toFixed(1)}</b> : null}
                  </div>
                </div>
                <div className="mono muted" style={{ fontSize: 11 }}>{gpsText(s)}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
