import { MapContainer, CircleMarker, Marker, Popup, useMapEvents } from "react-leaflet";
import { CorridorTiles, useCorridorTiles } from "../components/CorridorMap.jsx";
import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, getToken } from "../api";
import HonestyChip from "../components/HonestyChip.jsx";
import LiveFeed from "../components/LiveFeed.jsx";
import { useUi } from "../i18n.jsx";
import { dualHonesty, isMonsoon, isVru } from "../honesty.js";
import { mergeEventRow, mergeLiveSensor, openAuthedSocket, pollJson } from "../live/deskLive.js";

const color = { CRITICAL: "#e5484d", HIGH: "#ef7a18", MEDIUM: "#b7790f", LOW: "#0bb98a" };
const rank = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };

function ZoomTracker({ onZoom }) {
  const map = useMapEvents({
    zoomend: () => onZoom(map.getZoom()),
    moveend: () => onZoom(map.getZoom()),
  });
  return null;
}

function clusterEvents(list, zoom) {
  const cell = zoom >= 14 ? 0.002 : zoom >= 12 ? 0.008 : 0.02;
  const groups = new Map();
  for (const e of list) {
    const key = `${Math.floor(e.latitude / cell)}:${Math.floor(e.longitude / cell)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(e);
  }
  return [...groups.values()].map((items) => {
    const lat = items.reduce((a, b) => a + b.latitude, 0) / items.length;
    const lon = items.reduce((a, b) => a + b.longitude, 0) / items.length;
    const top = items.slice().sort((a, b) => (rank[b.severity] || 0) - (rank[a.severity] || 0))[0];
    return { items, lat, lon, top, count: items.length };
  });
}

export default function LiveMap() {
  const { t, monsoon, setMonsoon, vru, setVru } = useUi();
  const tiles = useCorridorTiles();
  const [events, setEvents] = useState([]);
  const [sensors, setSensors] = useState([]);
  const [assets, setAssets] = useState([]);
  const [segs, setSegs] = useState([]);
  const [sev, setSev] = useState("ALL");
  const [typeF, setTypeF] = useState("ALL");
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const [zoom, setZoom] = useState(12);
  const [clusterOn, setClusterOn] = useState(true);
  const [heatOn, setHeatOn] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);
  const [show, setShow] = useState({ sensors: true, assets: true, segments: true });

  useEffect(() => {
    Promise.all([api("/events?limit=200"), api("/sensor-nodes"), api("/assets"), api("/road-health")])
      .then(([e, s, a, r]) => { setEvents(e); setSensors(s); setAssets(a); setSegs(r); })
      .catch((ex) => setErr(ex.message));
    const token = getToken();
    const stopLive = openAuthedSocket("/ws/live", token, (m) => {
      try {
        const msg = JSON.parse(m.data);
        setSensors((prev) => mergeLiveSensor(prev, msg));
      } catch { /* ignore */ }
    });
    const stopEvents = openAuthedSocket("/ws/events", token, (m) => {
      try {
        const msg = JSON.parse(m.data);
        if (msg.event) setEvents((prev) => mergeEventRow(prev, msg.event, 200));
      } catch { /* ignore */ }
    });
    const stopSensorPoll = pollJson("/sensor-nodes", (s) => {
      if (Array.isArray(s)) {
        setSensors((prev) => {
          const live = Array.isArray(prev) ? prev : [];
          const byCode = new Map(live.map((row) => [row.code || row.id, row]));
          for (const row of s) {
            const key = row.code || row.id;
            const had = byCode.get(key) || {};
            byCode.set(key, {
              ...row,
              last_boxes: (row.last_boxes && row.last_boxes.length) ? row.last_boxes : (had.last_boxes || []),
              overlay_mode: row.overlay_mode || had.overlay_mode,
              overlay_backend: row.overlay_backend || had.overlay_backend,
              overlay_fps: row.overlay_fps || had.overlay_fps,
              infer_ms: row.infer_ms || had.infer_ms,
              seen_at: had.seen_at || (row.last_heartbeat_at ? Date.parse(row.last_heartbeat_at) : 0),
            });
          }
          return [...byCode.values()];
        });
      }
    }, 1000);
    const stopEventPoll = pollJson("/events?limit=200", (e) => {
      if (Array.isArray(e)) setEvents(e);
    }, 2000);
    return () => {
      stopLive();
      stopEvents();
      stopSensorPoll();
      stopEventPoll();
    };
  }, []);

  const filtered = useMemo(() => {
    return events.filter((e)=>{
      if (dualHonesty(e).seed) return false;
      if (e.event_type === "WATERLOGGING") return false;
      if (sev !== "ALL" && e.severity !== sev) return false;
      if (typeF !== "ALL" && e.event_type !== typeF) return false;
      if (q && !(`${e.public_code} ${e.event_type} ${e.status}`.toLowerCase().includes(q.toLowerCase()))) return false;
      if (vru || monsoon) {
        if (!((vru && isVru(e)) || (monsoon && isMonsoon(e)))) return false;
      }
      return true;
    });
  }, [events, sev, typeF, q, vru, monsoon]);

  const clusters = useMemo(
    () => (clusterOn ? clusterEvents(filtered, zoom) : filtered.map((e) => ({ items: [e], lat: e.latitude, lon: e.longitude, top: e, count: 1 }))),
    [filtered, zoom, clusterOn]
  );

  const types = [...new Set(events.map(e=>e.event_type))].sort();
  const clusteredCount = clusters.filter((c) => c.count > 1).length;

  if (err) return <p className="err">{err}</p>;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="crumbs">ICCC • {t("liveMap").toUpperCase()}</div>
          <h2 className="page-title">{t("pageMap")}</h2>
          <p className="page-sub muted">{t("pageMapSub")} <span role="status"><span className="table-num">{filtered.length} {t("of")} {events.length}</span> • <span className="table-num">{clusters.length}</span> pins (<span className="table-num">{clusteredCount}</span> clusters @z<span className="table-num">{zoom}</span>)</span></p>
        </div>
        <div className="filters">
          <span className="section-title" style={{ margin: 0, alignSelf: "center" }}>{tiles.caption}</span>
          <input placeholder="Search code / type" aria-label="Search events" value={q} onChange={e=>setQ(e.target.value)} style={{minWidth:200,padding:"8px 12px",borderRadius:999,border:"1px solid var(--line)"}} />
          <select value={sev} onChange={e=>setSev(e.target.value)} aria-label="Severity filter" style={{borderRadius:999}}><option value="ALL">{t("allSev")}</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select>
          <select value={typeF} onChange={e=>setTypeF(e.target.value)} aria-label="Type filter" style={{borderRadius:999}}><option value="ALL">{t("allTypes")}</option>{types.map((tp)=><option key={tp} value={tp}>{tp}</option>)}</select>
          <button className={`chip ${vru ? "active" : ""}`} onClick={()=>setVru((v)=>!v)} aria-pressed={vru}>{t("schoolZone")}</button>
          <button className={`chip ${monsoon ? "active" : ""}`} onClick={()=>setMonsoon((v)=>!v)} aria-pressed={monsoon}>{t("monsoon")}</button>
          <button className={`chip ${clusterOn ? "active" : ""}`} onClick={()=>setClusterOn((v)=>!v)} title="Group nearby pins" aria-pressed={clusterOn} aria-label="Toggle event clustering">{t("cluster")} {clusterOn ? "ON" : "OFF"}</button>
          <button className={`chip ${panelOpen ? "active" : ""}`} onClick={()=>setPanelOpen((v)=>!v)} title="Show or hide side panel" aria-pressed={panelOpen} aria-expanded={panelOpen} aria-label="Toggle side panel">{t("panel")} {panelOpen ? "ON" : "OFF"}</button>
        </div>
      </div>

      {(monsoon || vru) && (
        <div className={`ops-banner ${monsoon ? "warn" : "info"}`}>
          <div>
            <b>{monsoon ? t("monsoon") : t("schoolZone")}</b>
            {monsoon
              ? "Monsoon filter is off the map until a real flood model ships. School / VRU overlay stays."
              : "School / VRU overlay uses PEDESTRIAN_RISK + SCHOOL_CROSSING (bbox proximity)."}
          </div>
        </div>
      )}
      <LiveFeed sensors={sensors} />
      <div className="livemap-grid">
        <div className="maprail">
          <MapContainer center={[28.62, 77.22]} zoom={12} style={{ height: 640 }}>
            <CorridorTiles />
            <ZoomTracker onZoom={setZoom} />
            {heatOn && filtered.filter((e) => e.severity === "CRITICAL" || e.severity === "HIGH").map((e) => (
              <CircleMarker key={`heat-${e.id}`} center={[e.latitude, e.longitude]} radius={22} pathOptions={{ fillColor: color[e.severity] || color.HIGH, fillOpacity: 0.10, weight: 0 }} />
            ))}
            {filtered.filter(isVru).map((e) => (
              <CircleMarker key={`vru-${e.id}`} center={[e.latitude, e.longitude]} radius={28} pathOptions={{ color: "var(--info)", fillColor: "var(--info)", fillOpacity: 0.08, weight: 1, dashArray: "4 3" }} />
            ))}
            {filtered.filter(isMonsoon).map((e) => (
              <CircleMarker key={`mon-${e.id}`} center={[e.latitude, e.longitude]} radius={26} pathOptions={{ color: "var(--violet)", fillColor: "var(--violet)", fillOpacity: 0.10, weight: 1, dashArray: "2 4" }} />
            ))}
            {clusters.map((c, i) => c.count === 1 ? (
              <CircleMarker key={c.items[0].id} center={[c.lat, c.lon]} radius={c.top.observation_count>1?11:7} pathOptions={{ color: color[c.top.severity] || "var(--info)", fillColor: color[c.top.severity]||"var(--info)", fillOpacity: c.top.status==="RESOLVED"?0.12:0.26, weight:2 }}>
                <Popup>
                  <div style={{fontWeight:700}}><Link to={`/events/${c.top.id}`}>{c.top.public_code}</Link></div>
                  <div>{c.top.event_type} • <span className={`badge ${c.top.severity}`} style={{fontSize:10}}>{c.top.severity}</span> • {c.top.status}</div>
                  <div style={{margin:"4px 0"}}><HonestyChip event={c.top} compact /></div>
                  <div className="muted" style={{fontSize:12}}>obs {c.top.observation_count} • sources {c.top.source_count} • {(c.top.confidence*100).toFixed(0)}%</div>
                </Popup>
              </CircleMarker>
            ) : (
              <Marker
                key={`c-${i}`}
                position={[c.lat, c.lon]}
                icon={L.divIcon({
                  className: "",
                  html: `<div class="cluster-bubble ${c.top.severity === "CRITICAL" ? "crit" : c.top.severity === "HIGH" ? "high" : c.top.severity === "MEDIUM" ? "med" : "low"}" style="width:${Math.min(46, 28 + c.count * 2)}px;height:${Math.min(46, 28 + c.count * 2)}px">${c.count}</div>`,
                  iconSize: [Math.min(46, 28 + c.count * 2), Math.min(46, 28 + c.count * 2)],
                  iconAnchor: [Math.min(46, 28 + c.count * 2) / 2, Math.min(46, 28 + c.count * 2) / 2],
                })}
              >
                <Popup>
                  <div style={{fontWeight:700}}>{c.count} events here <span className={`badge ${c.top.severity}`} style={{fontSize:10}}>{c.top.severity} top</span></div>
                  <div className="muted" style={{fontSize:12}}>Zoom in to split • grid @z{zoom}</div>
                  <div style={{maxHeight:160,overflow:"auto",marginTop:6}}>
                    {c.items.slice(0,8).map((e)=>(
                      <div key={e.id} style={{padding:"4px 0",borderBottom:"1px solid var(--line)"}}>
                        <Link to={`/events/${e.id}`} style={{fontWeight:700,fontSize:12}}>{e.public_code}</Link>
                        <span className="muted" style={{fontSize:12}}> • {e.event_type}</span>
                      </div>
                    ))}
                    {c.count > 8 && <div className="muted" style={{fontSize:12}}>+{c.count - 8} more — zoom in</div>}
                  </div>
                </Popup>
              </Marker>
            ))}
            {show.sensors && sensors.filter((s) => s.latitude).map((s) => {
              const hot = (s.last_boxes || []).length > 0;
              return (
                <CircleMarker key={s.id} center={[s.latitude, s.longitude]} radius={hot ? 10 : 5} pathOptions={{ color: "var(--text)", fillColor: hot ? "#e5484d" : "var(--info)", fillOpacity: .9, weight: 1 }}>
                  <Popup>Sensor {s.code} {s.bus_code} · people {s.person_count || 0} · boxes {(s.last_boxes || []).length} · {s.overlay_mode || s.processing_mode}</Popup>
                </CircleMarker>
              );
            })}
            {show.assets && assets.map((a) => (
              <CircleMarker key={a.id} center={[a.latitude, a.longitude]} radius={4} pathOptions={{ color: "var(--violet)", fillColor:"var(--violet)", fillOpacity:.9 }}>
                <Popup><Link to={`/assets/${a.id}`}>{a.code}</Link> {a.asset_type} • {a.condition}</Popup>
              </CircleMarker>
            ))}
            {show.segments && segs.map((s) => (
              <CircleMarker key={s.id} center={[s.latitude, s.longitude]} radius={12} pathOptions={{ color: s.health_score < 50 ? color.CRITICAL : color.LOW, fillOpacity: 0.12, weight:1 }}>
                <Popup>{s.name} health {Number(s.health_score).toFixed(0)}</Popup>
              </CircleMarker>
            ))}
          </MapContainer>
          <div className="legend">
            {Object.entries(color).map(([k,v])=><span key={k} className="tag" style={{background:"var(--surface)",color:v,borderColor:v}}>{k}</span>)}
            <span className="muted" style={{fontSize:12}}>Numbered bubble holds N grouped events. Zoom in or click it to split.</span>
          </div>
        </div>

        <div style={{display: panelOpen ? "grid" : "none",gap:12}}>
          <div className="card">
            <h4>{t("layers")}</h4>
            <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:10}}>
              {Object.entries(color).map(([k,v])=><span key={k} className="tag" style={{background:"var(--surface)",color:v,borderColor:v,fontSize:11}}>{k}</span>)}
            </div>
            <label className="stat-row" style={{cursor:"pointer"}}><span><input type="checkbox" checked={show.sensors} onChange={e=>setShow(s=>({...s,sensors:e.target.checked}))}/> Sensors</span><span className="muted table-num">{sensors.length}</span></label>
            <label className="stat-row" style={{cursor:"pointer"}}><span><input type="checkbox" checked={show.assets} onChange={e=>setShow(s=>({...s,assets:e.target.checked}))}/> Assets</span><span className="muted table-num">{assets.length}</span></label>
            <label className="stat-row" style={{cursor:"pointer"}}><span><input type="checkbox" checked={show.segments} onChange={e=>setShow(s=>({...s,segments:e.target.checked}))}/> Road segments</span><span className="muted table-num">{segs.length}</span></label>
            <label className="stat-row" style={{cursor:"pointer"}}><span><input type="checkbox" checked={clusterOn} onChange={e=>setClusterOn(e.target.checked)}/> Clustering</span><span className="muted table-num">{clusters.length} pins</span></label>
            <label className="stat-row" style={{cursor:"pointer"}} aria-pressed={heatOn}><span><input type="checkbox" checked={heatOn} onChange={e=>setHeatOn(e.target.checked)}/> {t("heat")}</span><span className="muted">HIGH/CRITICAL</span></label>
            <div className="muted" style={{fontSize:12,marginTop:8}}>Dashed blue ring = school / VRU (bbox proximity). Big dot = 2+ reports from different buses.</div>
          </div>

          <div className="card">
            <h4>{t("visible")} (<span className="table-num">{filtered.length}</span>)</h4>
            <div style={{maxHeight:380,overflow:"auto"}}>
              {filtered.slice(0,30).map(e=>(
                <Link key={e.id} to={`/events/${e.id}`} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"8px 0",borderBottom:"1px solid var(--line)"}}>
                  <span><b style={{fontSize:12}}>{e.public_code}</b><span className="muted" style={{marginLeft:6,fontSize:12}}>{e.event_type}</span> <HonestyChip event={e} compact /></span>
                  <span className={`badge ${e.severity}`} style={{fontSize:10}}>{e.severity}</span>
                </Link>
              ))}
              {filtered.length===0 && <div className="empty">No events match these filters. Clear search, set severity to ALL, or zoom out to load more area.</div>}
            </div>
          </div>

          <div className="card">
            <h4>Tips</h4>
            <p className="muted" style={{fontSize:12,margin:0}}>Search an EVENT code to jump to it. Open a big dot to read why reports merged and which buses sent them.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
