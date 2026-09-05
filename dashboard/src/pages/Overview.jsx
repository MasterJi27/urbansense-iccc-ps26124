import { CircleMarker, Popup } from "react-leaflet";
import CorridorMap, { useCorridorTiles } from "../components/CorridorMap.jsx";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getToken, wsUrl } from "../api";
import { Skeleton } from "../components/Skeleton.jsx";
import HonestyChip from "../components/HonestyChip.jsx";
import ConfirmationStrip from "../components/ConfirmationStrip.jsx";
import FieldBoothCard from "../components/FieldBoothCard.jsx";
import CctvBoothCard from "../components/CctvBoothCard.jsx";
import HonestGaps from "../components/HonestGaps.jsx";
import { useUi } from "../i18n.jsx";
import DemoTruth from "../components/DemoTruth.jsx";
import { isMonsoon, isVru, patrolLabel } from "../honesty.js";
import { useToast } from "../components/Toast.jsx";

const color = { CRITICAL: "#e5484d", HIGH: "#ef7a18", MEDIUM: "#b7790f", LOW: "#0bb98a" };

export default function Overview() {
  const { t, monsoon, setMonsoon, vru, setVru } = useUi();
  const [sum, setSum] = useState(null);
  const [events, setEvents] = useState([]);
  const [buses, setBuses] = useState([]);
  const [sensors, setSensors] = useState([]);
  const [realEngines, setRealEngines] = useState(null);
  const [ps, setPs] = useState(null);
  const [filter, setFilter] = useState("ALL");
  const [err, setErr] = useState("");
  const [jury, setJury] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("urbansense_jury_run") || "null"); } catch { return null; }
  });
  const [juryBusy, setJuryBusy] = useState(false);
  const [heroLedger, setHeroLedger] = useState(null);
  const toast = useToast();
  const tiles = useCorridorTiles();

  useEffect(() => {
    Promise.all([
      api("/analytics/summary"),
      api("/events?limit=40"),
      api("/buses").catch(() => []),
      api("/sensor-nodes").catch(() => []),
      api("/ai/capabilities").catch(() => null),
      api("/ai/ps26124").catch(() => null),
    ])
      .then(([s, e, b, sn, caps, coverage]) => {
        setSum(s);
        setEvents(e);
        setBuses(b || []);
        setSensors(sn || []);
        if (caps) setRealEngines(Object.values(caps).filter((v) => v && v.ai_status === "REAL").length);
        if (coverage) setPs(coverage);
      })
      .catch((ex) => setErr(ex.message));
    const token = getToken();
    const ws = new WebSocket(wsUrl("/ws/events", token));
    ws.onmessage = (m) => {
      try {
        const msg = JSON.parse(m.data);
        if (msg.event) setEvents((prev) => [msg.event, ...prev.filter((x) => x.id !== msg.event.id)].slice(0, 40));
      } catch {}
    };
    return () => ws.close();
  }, []);

  const fused = events.find((e) => (e.extra || {}).patrol_state === "FLEET_CONFIRMED" && e.event_type === "POTHOLE")
    || events.find((e) => (e.extra || {}).patrol_state === "REPAIR_VERIFIED" && e.event_type === "POTHOLE")
    || events.find((e) => (e.extra || {}).patrol_state === "FLEET_CONFIRMED")
    || events.find((e) => e.event_type === "POTHOLE" && e.status === "UNVERIFIED")
    || events.find((e) => e.event_type === "POTHOLE")
    || events[0];

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

  async function runJury() {
    setJuryBusy(true);
    try {
      const body = await api("/demo/jury-run", { method: "POST", body: "{}" });
      try { sessionStorage.setItem("urbansense_jury_run", JSON.stringify(body)); } catch { /* ignore */ }
      setJury(body);
      const evs = await api("/events?limit=40");
      setEvents(evs);
      toast.success("Jury run ready — walk the checklist");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setJuryBusy(false);
    }
  }

  const filtered = events.filter((e) => {
    if (filter !== "ALL" && e.severity !== filter) return false;
    if (vru || monsoon) {
      if (!((vru && isVru(e)) || (monsoon && isMonsoon(e)))) return false;
    }
    return true;
  });
  const needsAttention = [...events]
    .filter((e) => (e.severity === "CRITICAL" || e.severity === "HIGH") && e.status === "UNVERIFIED")
    .sort((a, b) => sevRank(a.severity) - sevRank(b.severity) || new Date(b.timestamp || b.created_at || b.updated_at) - new Date(a.timestamp || a.created_at || a.updated_at))
    .slice(0, 5);
  const attentionTotal = events.filter((e) => (e.severity === "CRITICAL" || e.severity === "HIGH") && e.status === "UNVERIFIED").length;

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
          <button className="btn" type="button" disabled={juryBusy} onClick={runJury}>{juryBusy ? "Running…" : t("juryRun")}</button>
        </div>
      </div>

      <ConfirmationStrip event={fused} ledger={heroLedger} />

      <DemoTruth events={events} realEngines={realEngines} />

      <FieldBoothCard />

      <CctvBoothCard />

      <HonestGaps />

      {jury && (
        <div className="card" style={{ marginBottom: 12 }}>
          <h4>JURY RUN — 8 min checklist</h4>
          <p className="muted" style={{ fontSize: 13, margin: "0 0 10px" }}>{jury.usp || "Fleet confirms. One bus cannot."} {t("uspAbsence")}</p>
          <ol className="jury-checklist">
            {(jury.steps || []).map((step, i) => (
              <li key={`${step.event_id || step.public_code || i}`}>
                <span className="muted table-num">{String(i + 1).padStart(2, "0")}</span>
                {step.url ? <Link className="evlink" to={step.url}>{step.public_code}</Link> : <span className="mono">{step.public_code}</span>}
                <span>{step.ps_line}</span>
                {step.patrol_state && <span className={`tag ${step.patrol_state === "FLEET_CONFIRMED" ? "real" : "info"}`}>{step.patrol_state}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}

      {ps && (
        <div className="card" style={{ marginBottom: 12 }}>
          <h4>BEL PS 26124</h4>
          <p className="muted" style={{ fontSize: 13, margin: "0 0 10px" }}>{ps.note}</p>
          <div className="stat-row"><span className="muted">Camera bays</span><b className="mono" style={{ fontSize: 12 }}>{(ps.camera_bays || []).join(" · ")}</b></div>
          <div className="stat-row"><span className="muted">Coverage</span><b className="table-num">{Object.entries(ps.counts || {}).map(([k, v]) => `${v} ${k}`).join(" · ")}</b></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 10 }}>
            {(ps.items || []).map((row) => (
              <div key={row.id} className="stat-row" style={{ margin: 0 }}>
                <span style={{ fontSize: 12 }}>{row.requirement}</span>
                <span className={`tag ${row.status === "REAL" ? "real" : row.status === "RULE_BASED" ? "rule" : row.status === "DISABLED" ? "off" : "sim"}`} style={{ fontSize: 10 }}>{row.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="cards" style={{ marginBottom: 12 }}>
        <div className="card">
          <h4>{t("juryTitle")}</h4>
          <div className="stat-row"><span><b>{t("jury1t")}</b><div className="muted" style={{ fontSize: 12 }}>{t("jury1m")}</div></span></div>
          <div className="stat-row"><span><b>{t("jury2t")}</b><div className="muted" style={{ fontSize: 12 }}>{t("jury2m")}</div></span></div>
          <div className="stat-row"><span><b>{t("jury3t")}</b><div className="muted" style={{ fontSize: 12 }}>{t("jury3m")}</div></span></div>
          <div className="stat-row"><span><b>{t("jury4t")}</b><div className="muted" style={{ fontSize: 12 }}>{t("jury4m")}</div></span></div>
        </div>
        <div className="card">
          <h4>{t("evidenceG")}</h4>
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>{t("evidenceP")}</p>
          <p className="muted" style={{ fontSize: 12, margin: "10px 0 0" }}>{t("dpdpBanner")}</p>
        </div>
      </div>

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
              <p className="muted">No fused event yet. JURY RUN creates BUS-042 first sighting, then BUS-017 fleet-confirm on the same pothole.</p>
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

