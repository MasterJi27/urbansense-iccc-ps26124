import { useEffect, useState } from "react";
import { getToken } from "../api";
import Empty from "../components/Empty.jsx";
import { ImuSpark, useImuHistory } from "../components/LiveFeed.jsx";
import { ageLabel, mergeLiveSensor, mergeSensorPoll, openAuthedSocket, phoneSlotFromCode, pollJson } from "../live/deskLive.js";

function gpsText(s) {
  if (s.latitude == null || s.longitude == null) return "no map fix";
  const acc = s.gps_accuracy != null ? ` ±${Number(s.gps_accuracy).toFixed(0)} m` : "";
  return `${Number(s.latitude).toFixed(5)}, ${Number(s.longitude).toFixed(5)}${acc}`;
}

export default function Sensors() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const imuHist = useImuHistory(rows);

  useEffect(() => {
    const token = getToken();
    const stopLive = openAuthedSocket("/ws/live", token, (m) => {
      try {
        const msg = JSON.parse(m.data);
        setRows((prev) => mergeLiveSensor(prev, msg));
      } catch {
        /* ignore */
      }
    });
    const stopPoll = pollJson("/sensor-nodes", (sn) => {
      if (Array.isArray(sn)) setRows((prev) => mergeSensorPoll(prev, sn));
    }, 1000);
    return () => {
      stopLive();
      stopPoll();
    };
  }, []);

  const filtered = rows.filter((s) => !q || `${s.code} ${s.bus_code} ${s.device_label}`.toLowerCase().includes(q.toLowerCase()));
  const online = rows.filter((s) => s.camera_status === "ONLINE").length;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="crumbs">SYSTEM • SENSORS</div>
          <h2 className="page-title">Sensor fleet</h2>
          <p className="page-sub muted">
            Live roster · poll 1s · IMU mag from the phone heartbeat.
            {" "}
            <span role="status">
              <span className="table-num">{filtered.length}</span> of <span className="table-num">{rows.length}</span> sensors
              {" · "}
              <span className="table-num">{online}/{rows.length}</span> cameras online
            </span>
          </p>
        </div>
        <div className="filters">
          <input placeholder="Search sensor / bus" aria-label="Search sensors" value={q} onChange={(e) => setQ(e.target.value)} />
          <span className={`tag ${online > 0 ? "real" : "rule"}`}>{online} online</span>
        </div>
      </div>
      <div className="live-roster">
        {filtered.map((s) => {
          const code = s.code || s.id;
          const slot = phoneSlotFromCode(code);
          const boxes = (s.last_boxes || []).length;
          const gpsOk = s.gps_ok != null ? Boolean(s.gps_ok) : (s.latitude != null && s.longitude != null);
          return (
            <div className="live-roster-card" key={s.id || code}>
              <div className="live-roster-head">
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <span className={`status-dot ${s.camera_status === "ONLINE" ? "on" : "off"}`} aria-hidden="true" />
                  <b className="mono">{s.bus_code || code}</b>
                  <span className="muted" style={{ fontSize: 12 }}>{code}</span>
                </span>
                <span className={`tag ${s.camera_status === "ONLINE" ? "real" : "rule"}`}>{s.camera_status}</span>
              </div>
              <div className="live-roster-meta">
                <div><span className="muted">Slot</span> <b>P{slot || "—"}</b></div>
                <div><span className="muted">Boxes</span> <b className="table-num">{boxes}</b></div>
                <div><span className="muted">People</span> <b className="table-num">{s.person_count || 0}</b></div>
                <div><span className="muted">infer</span> <b className="table-num">{s.infer_ms ? `${Math.round(s.infer_ms)} ms` : "—"}</b></div>
                <div><span className="muted">Age</span> <b className="table-num">{ageLabel(s.seen_at || s.last_heartbeat_at)}</b></div>
                <div><span className={`gps-chip ${gpsOk ? "is-ok" : "is-bad"}`}>{gpsOk ? "GPS OK" : "GPS DEGRADED"}</span></div>
                <div className="live-roster-imu">
                  <span className="muted">IMU</span>
                  <ImuSpark samples={imuHist[code]} />
                  {s.imu_mag != null ? <b className="table-num">{Number(s.imu_mag).toFixed(1)}</b> : <span className="muted">{s.imu_status || "—"}</span>}
                </div>
              </div>
              <div className="mono muted" style={{ fontSize: 11 }}>{gpsText(s)}</div>
            </div>
          );
        })}
      </div>
      {filtered.length === 0 && (
        <Empty
          icon="◉"
          title="No sensors match"
          description={q ? `No sensors match “${q}”` : "No sensor nodes registered"}
          actionLabel={q ? "Clear search" : undefined}
          onAction={q ? () => setQ("") : undefined}
          style={{ marginTop: 12 }}
        />
      )}
    </div>
  );
}
