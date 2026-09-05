import { useEffect, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import { Link } from "react-router-dom";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { api } from "../api";

export default function BridgeHealth(){
  const [bridges,setBridges]=useState([]);
  const [events,setEvents]=useState([]);
  const [history,setHistory]=useState([]);
  const [sel,setSel]=useState(null);
  const [btab,setBtab]=useState("overview");
  const [visual,setVisual]=useState(null);
  const [visualLoading,setVisualLoading]=useState(false);
  const [err,setErr]=useState("");
  function load(){
    Promise.all([api("/bridge/health"), api("/events?limit=200")])
      .then(([b,e])=>{ setBridges(b); setEvents(e.filter(x=> String(x.event_type).includes("BRIDGE")||String(x.event_type).includes("FLYOVER"))); if(b[0] && !sel) loadHist(b[0]); })
      .catch(ex=> setErr(ex.message));
  }
  function loadVisual(b){
    if(!b) return;
    setVisualLoading(true);
    api(`/bridge/${b.id}/visual-check`).then(v=>setVisual(v)).catch(()=>setVisual(null)).finally(()=>setVisualLoading(false));
  }
  function loadHist(b){
    setSel(b);
    api(`/bridge/${b.id}/history`).then(setHistory).catch(()=>setHistory([]));
    loadVisual(b);
  }
  useEffect(load,[]);
  if(err) return <p className="err">{err}</p>;

  async function simulate(rms=0.55, peak=1.1, freqJitter=0){
    const b = sel || bridges[0];
    if(!b) return;
    const samples = Array.from({length:200},(_,i)=>({t:Date.now()/1000 + i*0.018 + Math.random()*0.002, ax:(Math.random()-0.5)*rms*2, ay:(Math.random()-0.5)*rms*1.4, az:(Math.random()-0.5)*peak + Math.sin(i*0.6+freqJitter)*0.2}));
    await api("/bridge/batch",{method:"POST", body: JSON.stringify({latitude:b.latitude, longitude:b.longitude, gps_accuracy:5, speed_kmh:26+Math.random()*8, source_type:"PHONE", source_id:"BUS-042", simulated:true, samples, extra:{temp_c:34}})} );
    load();
    if(sel) loadHist(sel);
  }

  return (
    <div>
      <div className="page-header">
        <div><div className="crumbs">INFRASTRUCTURE • BRIDGE HEALTH</div><h2 className="page-title">Structural Pulse — Continuous Screening</h2><p className="page-sub muted" role="status"><span className="table-num">{bridges.length}</span> bridges • <span className="table-num">{events.length}</span> SHM events • Buses as mobile structural sensors • <b>Sense</b> IMU+GPS on bridge • <b>Learn</b> per-structure signature • <b>Flag</b> persistent drift → inspection (not collapse) • 70m geofence • RULE_BASED</p></div>
        <div className="filters">
          <button className="btn ghost" title="Inject normal pass" onClick={()=>simulate(0.30,0.65,0)}>Normal pass</button>
          <button className="btn" style={{background:"var(--warn)"}} title="Inject joint knock" onClick={()=>simulate(0.48,1.05,0.8)}>Joint knock</button>
          <button className="btn" style={{background:"var(--danger)"}} title="Inject critical anomaly" onClick={()=>simulate(0.62,1.35,1.2)}>CRITICAL anomaly</button>
        </div>
      </div>

      <div className="filters" role="tablist" aria-label="Bridge sections" style={{marginBottom:12}}>
        <button role="tab" aria-selected={btab==="overview"} className={`chip ${btab==="overview" ? "active" : ""}`} onClick={()=>setBtab("overview")} aria-pressed={btab==="overview"}>Overview</button>
        <button role="tab" aria-selected={btab==="history"} className={`chip ${btab==="history" ? "active" : ""}`} onClick={()=>setBtab("history")} aria-pressed={btab==="history"}>History</button>
        <button role="tab" aria-selected={btab==="visual"} className={`chip ${btab==="visual" ? "active" : ""}`} onClick={()=>setBtab("visual")} aria-pressed={btab==="visual"}>Visual</button>
        <button role="tab" aria-selected={btab==="events"} className={`chip ${btab==="events" ? "active" : ""}`} onClick={()=>setBtab("events")} aria-pressed={btab==="events"}>Events</button>
      </div>

      {btab==="overview" && (
      <div className="kpis kpis-3">
        {bridges.map(b=>(
          <div key={b.id} onClick={()=>loadHist(b)} className={`kpi-card ${b.health_score<50?"crit":b.health_score<70?"warn":""}`} style={{cursor:"pointer", borderColor: sel?.id===b.id?"var(--text)":undefined, outline: sel?.id===b.id?"2px solid var(--text)":"none"}} role="button" tabIndex={0} aria-pressed={sel?.id===b.id} onKeyDown={(e)=>{if(e.key==="Enter")loadHist(b);}}>
            <small>{b.asset_type} • {b.code} {b.span_m?`• ${b.span_m}m`:""} {sel?.id===b.id?"• selected":""}</small>
            <b className="table-num">{Number(b.health_score).toFixed(0)}<span style={{fontSize:14,color:"var(--muted)"}}>/100</span></b>
            <div style={{display:"flex",alignItems:"center",gap:6,marginTop:6}}><span className={`status-dot ${b.health_score<50?"bad":b.health_score<70?"warn":"on"}`} aria-hidden="true" /><span className={`tag ${b.health_score<50?"sim":b.health_score<70?"rule":"real"}`} style={{fontSize:10}}>{b.health_score<50?"watch":b.health_score<70?"fair":"healthy"}</span></div>
            <div className="delta table-num">rms base {b.baseline_rms? Number(b.baseline_rms).toFixed(3):"—"} → last {b.last_rms? Number(b.last_rms).toFixed(3):"—"}g • f {b.baseline_freq? Number(b.baseline_freq).toFixed(1):"—"}→{b.last_freq? Number(b.last_freq).toFixed(1):"—"}Hz • {b.anomaly_count} anomalies</div>
            <div className="delta" style={{color: b.predicted_days? "var(--danger)":"var(--muted)"}}>{b.predicted_days? `⚠ ${b.predicted_days} days to maintenance (slope extrap.)` : "stable / no slope"}</div>
            <div style={{width:"100%",height:6,background:"var(--line)",borderRadius:999,overflow:"hidden",marginTop:8}}><div style={{width:`${b.health_score}%`,height:"100%",background: b.health_score<50?"var(--danger)": b.health_score<70?"var(--warn)":"var(--accent)"}} /></div>
          </div>
        ))}
      </div>
      )}

      {btab==="history" && sel && (
        <div className="card" style={{marginTop:12}}>
          <h4>{sel.name} — vibration history (last 80 passes) {sel.predicted_days?`• predicted ${sel.predicted_days}d`:""}</h4>
          <div role="img" aria-label="Bridge vibration history">
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={history}>
              <XAxis dataKey="at" tick={{fontSize:9, fill:"var(--muted)"}} tickFormatter={v=> String(v).slice(11,16)} />
              <YAxis tick={{fontSize:10, fill:"var(--muted)"}} domain={[0,0.7]} />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 10 }} />
              <Line type="monotone" dataKey="rms" stroke="var(--accent)" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="freq" stroke="var(--violet)" strokeOpacity={.85} strokeWidth={1} dot={false} />
              <ReferenceLine y={0.55} stroke="var(--danger)" strokeDasharray="6 4" label={{ value: "critical 0.55g", fontSize: 10, fill: "var(--danger)", position: "insideTopRight" }} />
              <ReferenceLine y={0.45} stroke="var(--warn)" strokeDasharray="6 4" label={{ value: "high 0.45g", fontSize: 10, fill: "var(--warn)", position: "insideTopRight" }} />
            </LineChart>
          </ResponsiveContainer>
          </div>
          <div className="muted" style={{fontSize:11}}>green=RMS, violet=f_dom, red dashed=critical, amber=high. Screening only — rising RMS slope extrap. → inspection, not collapse prediction. Tap Simulate to inject.</div>
        </div>
      )}
      {btab==="history" && !sel && (
        <div className="empty">No bridge selected — pick one in Overview to load history.</div>
      )}

      {btab==="visual" && sel && (
        <div className="card bridge-visual-grid" style={{marginTop:12}}>
          <div>
            <div style={{width:"100%", height:160, background:"var(--surface-2)", border:"1px dashed var(--line-strong)", borderRadius:12, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:6, overflow:"hidden", position:"relative"}}>
              <div style={{fontSize:28}} aria-hidden="true">📷</div>
              <b style={{fontSize:12, letterSpacing:".04em", textTransform:"uppercase"}}>Joint Photo</b>
              <span className="muted" style={{fontSize:11, textAlign:"center", padding:"0 12px"}}>Placeholder — visual RULE_BASED<br/>not ML crack segmentation</span>
              {visual && <span className="tag rule" style={{fontSize:10, marginTop:4}}>{visual.joint_gap_mm} mm gap • {visual.bearing_condition || visual.bearing}</span>}
              <img src={visual?.joint_photo_placeholder || visual?.joint_photo_url} alt="" aria-hidden="true" style={{position:"absolute", inset:0, width:"100%", height:"100%", objectFit:"cover", opacity:0.08, pointerEvents:"none"}} onError={e=>e.target.style.display='none'} />
            </div>
            <div className="muted" style={{fontSize:10, marginTop:6, textAlign:"center"}}>{visual ? `Crack ${visual.crack_length_mm} mm • ${visual.crack_severity}` : visualLoading ? "loading visual check…" : "—"} • {sel.code}</div>
            <div style={{marginTop:10, padding:"8px 10px", background:"var(--surface-2)", border:"1px solid var(--line)", borderRadius:8}}>
              <div className="muted" style={{fontSize:10,letterSpacing:".07em",textTransform:"uppercase",fontWeight:700}}>Evidence • EXIF GPS</div>
              <div className="mono" style={{fontSize:11,marginTop:4}}>📍 {sel.latitude.toFixed(5)}, {sel.longitude.toFixed(5)} • {sel.code} • GPS embedded in evidence_url</div>
              <div className="muted" style={{fontSize:10,marginTop:4}}>Mobile _attachJointPhoto embeds ?lat=&lon=&t=&acc=&bridge= in evidence_url + extra lat/lon; queued → POST /work-orders/{"{id}"}/repair</div>
              <div style={{display:"flex",gap:6,marginTop:6,flexWrap:"wrap"}}><span className="tag real" style={{fontSize:10}}>EXIF lat/lon/time</span><span className="tag info" style={{fontSize:10}}>joint photo queued</span><span className="tag rule" style={{fontSize:10}}>offline intact</span></div>
            </div>
          </div>
          <div>
            <div style={{display:"flex", alignItems:"center", gap:8, flexWrap:"wrap", marginBottom:8}}>
              <h4 style={{margin:0}}>Visual Check — {sel.code}</h4>
              {visual ? (
                <span className={`badge ${visual.waterlogging?.under_deck || visual.waterlogging_under_deck || visual.under_deck_waterlogging ? "HIGH" : "LOW"}`} style={{fontSize:11, borderWidth:1}}>
                  {visual.waterlogging?.under_deck || visual.waterlogging_under_deck || visual.under_deck_waterlogging ? "WATERLOGGED under-deck" : "DRY under-deck"}
                </span>
              ) : <span className="badge LOW" style={{fontSize:11}}>{visualLoading ? "checking…" : "no data"}</span>}
              <span className="muted" style={{fontSize:11, marginLeft:"auto"}}>{visual?.checked_at ? new Date(visual.checked_at).toLocaleTimeString() : ""} • mock</span>
            </div>
            {visual ? (
              <div style={{display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:10}}>
                <div style={{background:"var(--surface-2)", border:"1px solid var(--line)", borderRadius:10, padding:"10px 12px"}}>
                  <div className="muted" style={{fontSize:10, letterSpacing:".08em", textTransform:"uppercase", fontWeight:700}}>Joint Gap</div>
                  <div className="table-num" style={{fontSize:20, fontWeight:700}}>{visual.joint_gap_mm}<span style={{fontSize:12, color:"var(--muted)"}}> mm</span></div>
                  <div style={{fontSize:11, marginTop:4}} className={`badge ${visual.joint_gap_status==="ALERT"?"HIGH":visual.joint_gap_status==="WATCH"?"MEDIUM":"LOW"}`}>{visual.joint_gap_status}</div>
                  <div className="muted" style={{fontSize:10, marginTop:6}}>typ 10–20 mm</div>
                </div>
                <div style={{background:"var(--surface-2)", border:"1px solid var(--line)", borderRadius:10, padding:"10px 12px"}}>
                  <div className="muted" style={{fontSize:10, letterSpacing:".08em", textTransform:"uppercase", fontWeight:700}}>Bearing</div>
                  <div className="table-num" style={{fontSize:16, fontWeight:700}}>{visual.bearing_condition || visual.bearing}</div>
                  <div className="muted" style={{fontSize:11}}>{visual.bearing_displacement_mm} mm displacement</div>
                  <span className={`badge ${visual.bearing==="CRITICAL"?"HIGH":visual.bearing==="WORN"?"MEDIUM":"LOW"}`} style={{fontSize:10, marginTop:6, display:"inline-block"}}>{visual.bearing_status || visual.bearing}</span>
                </div>
                <div style={{background:"var(--surface-2)", border:"1px solid var(--line)", borderRadius:10, padding:"10px 12px"}}>
                  <div className="muted" style={{fontSize:10, letterSpacing:".08em", textTransform:"uppercase", fontWeight:700}}>Crack Length</div>
                  <div className="table-num" style={{fontSize:20, fontWeight:700}}>{visual.crack_length_mm}<span style={{fontSize:12, color:"var(--muted)"}}> mm</span></div>
                  <span className={`badge ${visual.crack_severity==="HIGH"?"HIGH":visual.crack_severity==="MEDIUM"?"MEDIUM":"LOW"}`} style={{fontSize:10, marginTop:4, display:"inline-block"}}>{visual.crack_severity}</span>
                </div>
              </div>
            ) : <div className="muted" style={{fontSize:12}}>{visualLoading ? "Loading mock visual assessment…" : "No visual data yet."}</div>}
            {visual && (
              <div style={{marginTop:10, display:"flex", gap:8, flexWrap:"wrap", alignItems:"center"}}>
                <span className={`tag ${visual.waterlogging?.under_deck ? "real" : "info"}`} style={{fontSize:11}}>
                  Under-deck: {visual.waterlogging?.depth_mm ?? visual.waterlogging_depth_mm} mm • {visual.waterlogging?.severity || (visual.waterlogging_under_deck ? "WATERLOGGED" : "DRY")}
                </span>
                {visual.waterlogging?.under_deck || visual.waterlogging_under_deck ? (
                  <span className="badge HIGH" style={{fontSize:10}}>⚠ Waterlogging flag — inspect drains</span>
                ) : (
                  <span className="badge LOW" style={{fontSize:10}}>✓ No waterlogging under deck</span>
                )}
                <span className="tag rule" style={{fontSize:10, marginLeft:"auto"}}>RULE_BASED • mock</span>
              </div>
            )}
            <div className="muted" style={{fontSize:10, marginTop:8}}>{visual?.method || "Camera joint check is visual (RULE_BASED), not ML crack segmentation"} • <span className="mono">{visual?.joint_photo_placeholder || ""}</span></div>
          </div>
        </div>
      )}
      {btab==="visual" && !sel && (
        <div className="empty">No bridge selected — pick one in Overview to load visual check.</div>
      )}

      {btab==="overview" && (
      <div className="bridge-main-grid">
        <div className="maprail">
          <div style={{padding:"10px 14px",display:"flex",justifyContent:"space-between",borderBottom:"1px solid var(--line)"}}><b style={{fontSize:11,letterSpacing:".08em",textTransform:"uppercase",color:"var(--muted)"}}>Delhi bridges + SHM events</b><span className="muted" style={{fontSize:11}}>{bridges.length} bridges • {events.length} SHM events</span></div>
          <MapContainer center={[28.60,77.20]} zoom={11} style={{height:460}}>
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {bridges.map(b=>(
              <CircleMarker key={b.id} center={[b.latitude,b.longitude]} radius={15} pathOptions={{color: b.health_score<50?"#e5484d": b.health_score<70?"#b7790f":"#0bb98a", fillOpacity:.14, weight:2, dashArray: sel?.id===b.id?"6 4":null}}>
                <Popup><b>{b.name}</b><div>{b.code} • {b.health_score.toFixed(0)}/100 • f {b.baseline_freq?.toFixed(1)}→{b.last_freq?.toFixed(1)}Hz</div><div className="muted" style={{fontSize:11}}>{b.predicted_days?`${b.predicted_days}d to maintenance`:"stable"}</div><Link to={`/assets/${b.id}`}>Passport →</Link></Popup>
              </CircleMarker>
            ))}
            {events.map(e=>(
              <CircleMarker key={e.id} center={[e.latitude,e.longitude]} radius={e.severity==="CRITICAL"?9:6} pathOptions={{color: e.severity==="CRITICAL"?"#e5484d": e.severity==="HIGH"?"#ef7a18":"#0bb98a", fillOpacity:.9, weight:2}}>
                <Popup><Link to={`/events/${e.id}`}>{e.public_code}</Link> • {e.event_type} • <span className={`badge ${e.severity}`} style={{fontSize:10}}>{e.severity}</span><div className="mono muted" style={{fontSize:10}}>{e.extra?.shm_reason?.slice(0,130)}</div>{e.extra?.predicted_days? <div style={{fontSize:11,color:"var(--danger)"}}>predicted {e.extra.predicted_days}d</div>:null}</Popup>
              </CircleMarker>
            ))}
          </MapContainer>
          <div style={{padding:10,display:"flex",gap:6,flexWrap:"wrap"}}><span className="tag real" style={{fontSize:10}}>FFT f_dom tracked</span><span className="tag rule" style={{fontSize:10}}>temp-comp</span><span className="tag sim" style={{fontSize:10}}>auto WO on CRITICAL</span><span className="muted" style={{fontSize:11,marginLeft:"auto"}}>70m geofence</span></div>
        </div>

        <div style={{display:"grid",gap:12}}>
          <div className="card">
            <h4>Sense → Learn → Flag <span className="tag info" style={{fontSize:10}}>screening layer</span></h4>
            <p className="muted" style={{fontSize:11,margin:"0 0 8px"}}>Not collapse prediction. Persistent drift across buses → inspection recommendation.</p>
            <div className="timeline">
              <div className="tl-item active"><div className="title">Sense — IMU+GPS on crossing</div><div className="meta">RMS/peak/crest + FFT f_dom per bridge geofence</div></div>
              <div className="tl-item"><div className="title">Learn — per-structure EMA baseline</div><div className="meta">0.92/0.08, longitudinal history 80 pts, temp-aware</div></div>
              <div className="tl-item"><div className="title">Flag — persistent drift</div><div className="meta">≥0.9Hz shift or ratio≥1.6 across multiple buses → ANOMALOUS → auto WO</div></div>
              <div className="tl-item"><div className="title">Why buses?</div><div className="meta">No sensor per bridge — fleet already traverses daily. Network-scale.</div></div>
            </div>
          </div>
        </div>
      </div>
      )}

      {btab==="events" && (
        <div className="card" style={{marginTop:12}}>
          <h4>Recent SHM events ({events.length})</h4>
          <div style={{maxHeight:380,overflow:"auto"}}>
            {events.slice(0,14).map(e=>(
              <Link key={e.id} to={`/events/${e.id}`} style={{display:"block",padding:"8px 0",borderBottom:"1px solid var(--line)"}}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><b style={{fontSize:12}}>{e.public_code}</b><span className={`badge ${e.severity}`} style={{fontSize:10}}>{e.severity}</span></div>
                <div className="muted" style={{fontSize:11}}>{e.event_type} • {e.source_id} • {(e.confidence*100).toFixed(0)}% • {new Date(e.timestamp).toLocaleTimeString()}</div>
                <div className="mono muted" style={{fontSize:10,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{e.extra?.shm_reason}</div>
                {e.extra?.shm_features?.dominant_freq? <span className="tag info" style={{fontSize:10,marginTop:4,display:"inline-block"}}>f {e.extra.shm_features.dominant_freq.toFixed(1)}Hz</span>:null}
              </Link>
            ))}
            {events.length===0 && <div className="empty">No SHM yet — tap Simulate.</div>}
          </div>
        </div>
      )}
    </div>
  );
}
