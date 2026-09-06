import { CircleMarker, Popup } from "react-leaflet";
import CorridorMap, { useCorridorTiles } from "../components/CorridorMap.jsx";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getToken } from "../api";
import { Skeleton } from "../components/Skeleton.jsx";
import HonestyChip from "../components/HonestyChip.jsx";
import ConfirmationStrip from "../components/ConfirmationStrip.jsx";
import FieldBoothCard from "../components/FieldBoothCard.jsx";
import LiveFeed from "../components/LiveFeed.jsx";
import { useUi } from "../i18n.jsx";
import { dualHonesty, isMonsoon, isVru, patrolLabel } from "../honesty.js";
import { applyEventMessage, mergeEventPoll, mergeLiveSensor, mergeSensorPoll, openAuthedSocket, pollJson } from "../live/deskLive.js";

const color = { CRITICAL: "#e5484d", HIGH: "#ef7a18", MEDIUM: "#b7790f", LOW: "#0bb98a" };

const EMPTY_SUMMARY = {
  active_buses: 0,
  active_sensors: 0,
  total_sensors: 0,
  total_events: 0,
  critical_events: 0,
  unverified_events: 0,
  road_health: 0,
  open_work_orders: 0,
};

export default function Overview() {
  const { t, monsoon, setMonsoon, vru, setVru } = useUi();
  const [sum, setSum] = useState(null);
  const [events, setEvents] = useState([]);
  const [buses, setBuses] = useState([]);
  const [sensors, setSensors] = useState([]);
  const [realEngines, setRealEngines] = useState(null);
  const [filter, setFilter] = useState("ALL");
  const [err, setErr] = useState("");
  const [heroLedger, setHeroLedger] = useState(null);
  const tiles = useCorridorTiles();

  useEffect(() => {
    Promise.all([
      api("/analytics/summary").catch(() => null),
      api("/events?live=1&limit=40").catch(() => []),
      api("/buses").catch(() => []),
      api("/sensor-nodes").catch(() => []),
      api("/ai/capabilities").catch(() => null),
    ])
      .then(([s, e, b, sn, caps]) => {
        setSum(s || EMPTY_SUMMARY);
        setEvents(Array.isArray(e) ? e : []);
        setBuses(b || []);
        setSensors(sn || []);
        if (caps) setRealEngines(Object.values(caps).filter((v) => v && v.ai_status === "REAL").length);
      })
      .catch((ex) => setErr(ex.message));
    const token = getToken();
    const stopEvents = openAuthedSocket("/ws/events", token, (m) => {
      try {
        const msg = JSON.parse(m.data);
        if (msg.event || msg.type === "event.deleted" || msg.type === "events.cleared") {
          setEvents((prev) => applyEventMessage(prev, msg, 40, true));
        }
      } catch {}
    });
    const stopLive = openAuthedSocket("/ws/live", token, (m) => {
      try {
        const msg = JSON.parse(m.data);
        setSensors((prev) => mergeLiveSensor(prev, msg));
      } catch {}
    });
    const stopEventPoll = pollJson("/events?live=1&limit=40", (e) => {
      if (Array.isArray(e)) setEvents((prev) => mergeEventPoll(prev, e, 40));
    }, 800);
    const stopSensorPoll = pollJson("/sensor-nodes", (sn) => {
      if (Array.isArray(sn)) setSensors((prev) => mergeSensorPoll(prev, sn));
    }, 600);
    return () => {
      stopEvents();
      stopLive();
      stopEventPoll();
      stopSensorPoll();
    };
  }, []);

  const liveEvents = events.filter((e) => !dualHonesty(e).seed && e.event_type !== "WATERLOGGING");
  const fused = liveEvents.find((e) => (e.extra || {}).patrol_state === "FLEET_CONFIRMED" && e.event_type === "POTHOLE")
    || liveEvents.find((e) => (e.extra || {}).patrol_state === "REPAIR_VERIFIED" && e.event_type === "POTHOLE")
    || liveEvents.find((e) => (e.extra || {}).patrol_state === "FLEET_CONFIRMED")
    || liveEvents.find((e) => e.event_type === "POTHOLE" && e.status === "UNVERIFIED")
    || liveEvents.find((e) => e.event_type === "POTHOLE")
    || liveEvents[0];

  useEffect(() => {
    if (!fused?.id) { setHeroLedger(null); return; }
    api(`/events/${fused.id}/ledger`).then(setHeroLedger).catch(() => setHeroLedger(null));
  }, [fused?.id]);

  if (err) return <p className="err">{err}</p>;
  if (!sum) return (
    <div>
      <div className="kpis">
        {[0,1,2,3].map((i) => (
          <div key={i} className="card">
            <Skeleton width="55%" height={10} style={{ marginBottom: 14 }} />
            <Skeleton width="40%" height={28} style={{ marginBottom: 8 }} />
            <Skeleton width="78%" height={12} />
          </div>
        ))}
      </div>
      <div className="cards" style={{ marginTop: 12 }}>
        {[0,1,2].map((i) => (
          <div key={i} className="card">
            <Skeleton width="38%" height={12} style={{ marginBottom: 12 }} />
            <Skeleton height={14} style={{ marginBottom: 8 }} />
            <Skeleton height={14} width="92%" style={{ marginBottom: 8 }} />
            <Skeleton width="68%" height={14} />
          </div>
        ))}
      </div>
      <div className="card" style={{ marginTop: 12 }}>
        <Skeleton height={220} />
      </div>
    </div>
  );

  const filtered = liveEvents.filter((e) => {
    if (filter !== "ALL" && e.severity !== filter) return false;
    if (vru || monsoon) {
      if (!((vru && isVru(e)) || (monsoon && isMonsoon(e)))) return false;
    }
    return true;
  });
  const needsAttention = [...liveEvents]
    .filter((e) => (e.severity === "CRITICAL" || e.severity === "HIGH") && e.status === "UNVERIFIED")
    .sort((a, b) => sevRank(a.severity) - sevRank(b.severity) || new Date(b.timestamp || b.created_at || b.updated_at) - new Date(a.timestamp || a.created_at || a.updated_at))
    .slice(0, 5);
  const attentionTotal = liveEvents.filter((e) => (e.severity === "CRITICAL" || e.severity === "HIGH") && e.status === "UNVERIFIED").length;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="crumbs">ICCC &gt; {t("overview").toUpperCase()}</div>
          <h2 className="page-title">{t("pageOv")}</h2>
          <p className="page-sub muted">
            {t("pageOvSub")}
            {" "}<span role="status">{filtered.length} events · {buses.length} buses</span>
          </p>
        </div>
        <div className="filters">
          {["ALL","CRITICAL","HIGH","MEDIUM","LOW"].map(f=>(
            <button key={f} className={`chip ${filter===f?"active":""}`} onClick={()=>setFilter(f)} aria-pressed={filter===f}>{t(f)}</button>
          ))}
          <button className={`chip ${vru?"active":""}`} onClick={()=>setVru((v)=>!v)} aria-pressed={vru}>{t("schoolZone")}</button>
          <button className={`chip ${monsoon?"active":""}`} onClick={()=>setMonsoon((v)=>!v)} aria-pressed={monsoon}>{t("monsoon")}</button>
        </div>
      </div>

      <ConfirmationStrip event={fused} ledger={heroLedger} />

      <LiveFeed sensors={sensors} />

      <FieldBoothCard />

      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h4 style={{ margin: 0 }}>{t("needsAttention")} <span className="table-num muted">{attentionTotal}</span></h4>
          <Link to="/events" className="muted" style={{ fontSize: 12, fontWeight: 700 }}>{t("viewAll")}</Link>
        </div>
        {needsAttention.length === 0 ? (
          <div className="empty">All clear — no CRITICAL/HIGH unverified.</div>
        ) : (
          <div aria-live="polite" style={{ display: "grid" }}>
            {needsAttention.map((e) => (
              <div className="stat-row" key={e.id}>
                <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", minWidth: 0 }}>
                  <span className={`badge ${e.severity}`}>{e.severity}</span>
                  <Link className="evlink" to={`/events/${e.id}`}>{e.public_code}</Link>
                  <span className="muted" style={{ fontSize: 12 }}>{e.event_type}</span>
                  <HonestyChip event={e} compact />
                  <span className="muted table-num" style={{ fontSize: 12 }}>{timeAgo(e.timestamp || e.created_at || e.updated_at)}</span>
                </span>
                <Link to={`/events/${e.id}`} className="muted" style={{ fontSize: 12, fontWeight: 700 }}>Open</Link>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="kpis">
        <div className="kpi-card">
          <div className="kpi-top"><small>{t("activeBuses")}</small></div>
          <b className="table-num">{sum.active_buses}</b>
          <div className="delta"><span className="status-dot on" aria-hidden="true" /> {sensors.filter(s=>s.camera_status==="ONLINE").length} {t("camerasOnline")}</div>
        </div>
        <div className={`kpi-card ${sum.critical_events > 0 ? "crit" : ""}`}>
          <div className="kpi-top"><small>{t("openEventsKpi")}</small></div>
          <b className="table-num">{sum.total_events}</b>
          <div className="delta">{sum.unverified_events} {t("unverified")} • {sum.critical_events} {t("CRITICAL")}/{t("HIGH")}</div>
        </div>
        <div className={`kpi-card ${sum.road_health < 60 ? "warn" : ""}`}>
          <div className="kpi-top"><small>{t("roadHealthKpi")}</small></div>
          <b className="table-num">{sum.road_health}<span className="muted" style={{fontSize:14}}>/100</span></b>
          <div className="delta">{t("ruleBased")}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-top"><small>{t("aiReal")}</small></div>
          <b className="table-num">{realEngines ?? "—"}</b>
          <div className="delta">YOLO RDD + Vehicles/Track + ANPR</div>
        </div>
      </div>

      <div className="ops-grid">
        <div>
          <div className="card">
            <h4>Latest fused event</h4>
            {fused ? (
              <div>
                <Link className="evlink" to={`/events/${fused.id}`}>{fused.public_code}</Link>
                <span className="muted"> · {fused.event_type} · {patrolLabel(fused)} · {fused.observation_count} observations</span>
                <p className="muted" style={{ margin: "8px 0 0", fontSize: 13 }}>{fused.fusion_reason}</p>
              </div>
            ) : (
              <p className="muted">No live ticket yet. Arm a PIN, open /field, keep AUTO on.</p>
            )}
          </div>
          <div className="card" style={{ marginTop: 12 }}>
            <h4>{t("workQueue")}</h4>
            <div className="stat-row"><span className="muted">{t("openWo")}</span><b className="table-num">{sum.open_work_orders}</b></div>
            <div className="stat-row"><span className="muted">{t("needsVerify")}</span><b className="table-num">{sum.unverified_events}</b></div>
            <Link to="/work-orders" className="btn ghost" style={{ marginTop: 10 }}>{t("workOrders")}</Link>
          </div>
        </div>
        <div className="maprail">
          <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--line)" }}>
            <h4 style={{ margin: 0 }}>Map · {tiles.caption}</h4>
          </div>
          <CorridorMap center={[28.62, 77.22]} zoom={11} height={320} hideCaption>
            {filtered.map((e) => (
              <CircleMarker key={e.id} center={[e.latitude, e.longitude]} radius={e.observation_count > 1 ? 10 : 6} pathOptions={{ color: color[e.severity] || "#155a8a", fillColor: color[e.severity] || "#155a8a", fillOpacity: 0.28, weight: 2 }}>
                <Popup><Link to={`/events/${e.id}`}>{e.public_code}</Link> · {e.event_type}</Popup>
              </CircleMarker>
            ))}
            {sensors.filter((s) => s.latitude != null && s.longitude != null).map((s) => {
              const hot = (s.last_boxes || []).length > 0;
              return (
                <CircleMarker
                  key={`live-${s.id || s.code}`}
                  center={[s.latitude, s.longitude]}
                  radius={hot ? 10 : 6}
                  pathOptions={{ color: "#111", fillColor: hot ? "#e5484d" : "#5b8def", fillOpacity: 0.9, weight: 1 }}
                >
                  <Popup>{s.bus_code || s.code} · people {s.person_count || 0} · boxes {(s.last_boxes || []).length}</Popup>
                </CircleMarker>
              );
            })}
          </CorridorMap>
        </div>
      </div>
    </div>
  );
}

function sevRank(s){
  if (s === "CRITICAL") return 0;
  if (s === "HIGH") return 1;
  if (s === "MEDIUM") return 2;
  if (s === "LOW") return 3;
  return 9;
}

function timeAgo(ts){
  if (!ts) return "—";
  const t = new Date(ts).getTime();
  if (Number.isNaN(t)) return "—";
  const m = Math.floor((Date.now() - t) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return `${Math.floor(d / 30)}mo ago`;
}

